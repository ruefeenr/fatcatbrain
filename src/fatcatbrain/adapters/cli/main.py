"""The ``fcb`` command-line interface (Typer + Rich)."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import typer

from fatcatbrain.adapters.cli.mascot import MascotRenderer
from fatcatbrain.adapters.cli.render import (
    console,
    render_candidate,
    render_memory_table,
)
from fatcatbrain.adapters.llm.errors import LLMExtractionError
from fatcatbrain.application.use_cases.capture_brain_dump import CaptureResult
from fatcatbrain.composition import Container, build_container, build_ingest_source
from fatcatbrain.config import Settings
from fatcatbrain.config.settings import (
    DEFAULT_PROJECT_ID,
    find_project_root,
    slugify_project,
)
from fatcatbrain.domain.models import Project
from fatcatbrain.domain.value_objects import MemoryType

app = typer.Typer(
    add_completion=False,
    help="fatcatbrain (fcb): a playful local context-capture companion.",
    no_args_is_help=True,
)
mascot = MascotRenderer()


def _container() -> Container:
    return build_container(Settings.from_env())


def _auto_transcripts_dir(
    home: Path | None = None, cwd: Path | None = None
) -> Path | None:
    """Best-effort guess of the current Cursor project's transcripts directory.

    Cursor stores transcripts under ``~/.cursor/projects/<slug>/agent-transcripts``
    where ``<slug>`` is the project path with slashes turned into dashes.
    """

    home = home or Path.home()
    cwd = cwd or Path.cwd()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(cwd)).strip("-")
    candidate = home / ".cursor" / "projects" / slug / "agent-transcripts"
    return candidate if candidate.exists() else None


def _llm_preflight(settings: Settings) -> str | None:
    """Return a friendly problem description if the configured LLM isn't usable.

    Only checks Ollama (the one wired up). Returns ``None`` when all is well.
    """

    if settings.llm != "ollama":
        return None

    from fatcatbrain.adapters.llm.ollama_info import probe_ollama

    status = probe_ollama(settings.ollama_host)
    if not status.reachable:
        return (
            "I can't reach Ollama.\n"
            "   Start it with:  ollama serve\n"
            f"   Then re-run:    {_invocation('listen')}"
        )
    if settings.ollama_model not in status.models:
        installed = ", ".join(status.models) or "(none)"
        return (
            f"The model '{settings.ollama_model}' isn't installed.\n"
            f"   Installed:  {installed}\n"
            f"   Pull it:    ollama pull {settings.ollama_model}\n"
            f"   Or pick another:  {_invocation('init')} --reconfigure"
        )
    return None


def _invocation(subcommand: str) -> str:
    """Build the command string the user should type, honouring `uv run`.

    When started via ``uv run fcb ...`` the bare ``fcb`` is not on the user's
    PATH, so the hint must keep the ``uv run`` prefix.
    """

    prog = Path(sys.argv[0]).name
    if prog in ("", "-", "-c", "python", "python3", "__main__.py"):
        prog = "fcb"
    prefix = "uv run " if os.environ.get("UV") else ""
    return f"{prefix}{prog} {subcommand}"


def _open_editor(initial_text: str = "") -> str | None:
    """Open the user's editor on a temp file and return the edited contents.

    Returns ``None`` if the editor exits non-zero. Uses ``$VISUAL``/``$EDITOR``,
    falling back to ``vi``.
    """

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="fcb_brain_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(initial_text)
        tmp_path = tmp.name
    try:
        completed = subprocess.run([*editor.split(), tmp_path])
        if completed.returncode != 0:
            return None
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _suggested_project_name(container: Container) -> str:
    """Human-friendly name for the active project, ideally the root folder name."""

    root_name = find_project_root().name
    if slugify_project(root_name) == container.project_id:
        return root_name
    return container.project_id.replace("-", " ").title()


def _ensure_project(container: Container, *, prompt_name: bool = False) -> Project:
    """Make sure the active project exists on disk.

    When ``prompt_name`` is set and we're on a TTY, the first time a project is
    created we suggest the working-directory's folder name and let the user adjust
    it. Otherwise the folder name is used silently.
    """

    project = container.project_repo.get(container.project_id)
    if project is not None:
        return project

    suggested = _suggested_project_name(container)
    name = suggested
    if prompt_name and sys.stdin.isatty():
        console.print(mascot.ask(f"New project detected: {suggested}"))
        name = typer.prompt("Project name", default=suggested).strip() or suggested

    project = Project(
        id=container.project_id,
        name=name,
        description="Auto-detected from the working directory.",
    )
    container.project_repo.save(project)
    return project


def _capture_and_report(
    container: Container,
    text: str,
    *,
    project_id: str | None,
    source: str = "brain_dump",
) -> None:
    """Run a capture, handling LLM failures gracefully."""

    try:
        with console.status(mascot.thinking(), spinner="dots"):
            result: CaptureResult = container.capture_brain_dump().execute(
                text, project_id=project_id, source=source  # type: ignore[arg-type]
            )
    except LLMExtractionError as exc:
        console.print(f"[red]The LLM could not produce valid candidates.[/red]\n{exc}")
        raise typer.Exit(code=1)
    console.print(mascot.candidates_found(len(result.candidates)))
    if result.candidates:
        console.print(f"Run [bold]{_invocation('inbox')}[/bold] to review them.")


def _write_config(settings: Settings, *, llm: str, ollama_model: str) -> None:
    """Persist config.json, preserving any unknown keys already present."""

    config_file = settings.paths.config_file
    config_file.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if config_file.exists():
        try:
            loaded = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}
    existing.update(
        {
            "version": 1,
            "default_project": settings.project_id,
            "llm": llm,
            "ollama_model": ollama_model,
        }
    )
    config_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _choose_ollama_model(settings: Settings) -> str:
    """Interactively pick a local Ollama model, guiding install/pull if needed."""

    from fatcatbrain.adapters.llm.ollama_info import probe_ollama

    status = probe_ollama(settings.ollama_host)

    if not status.reachable:
        console.print(mascot.confused("I can't reach Ollama right now."))
        console.print("   1) Install:  brew install ollama")
        console.print("   2) Start it: ollama serve")
        console.print("   3) Pull a model:  ollama pull gpt-oss:20b   (or qwen2.5)")
        console.print(f"   Then re-run [bold]{_invocation('init')}[/bold].")
        return typer.prompt(
            "Model name to use once Ollama is ready",
            default=settings.ollama_model or "gpt-oss:20b",
        ).strip()

    if not status.models:
        console.print(mascot.info("Ollama is running, but has no models yet."))
        console.print("   Pull one, e.g.:  ollama pull gpt-oss:20b   (or qwen2.5)")
        return typer.prompt(
            "Model name to use once pulled", default="gpt-oss:20b"
        ).strip()

    console.print(mascot.happy("Ollama is ready. Pick a model:"))
    default_index = 1
    for i, name in enumerate(status.models, start=1):
        if "gpt-oss" in name and default_index == 1:
            default_index = i
        console.print(f"   {i}) {name}", markup=False)

    selection = typer.prompt("Choose a number", default=str(default_index)).strip()
    try:
        return status.models[int(selection) - 1]
    except (ValueError, IndexError):
        return status.models[default_index - 1]


def _interactive_llm_setup(settings: Settings) -> tuple[str, str]:
    """Ask the user how the cat should think. Returns (llm, ollama_model)."""

    console.print(mascot.ask("How should I think?"))
    console.print("   1) Local model via Ollama  (private, runs on your machine)")
    console.print("   2) Cloud API")
    choice = typer.prompt("Choose", default="1").strip()

    if choice == "2":
        console.print(mascot.confused("Cloud APIs aren't wired up yet - coming soon."))
        console.print("   Let's set up a local model for now.")

    return "ollama", _choose_ollama_model(settings)


def _print_next_steps() -> None:
    """Tell the user, in the cat's voice, exactly how to use fcb from here."""

    console.print()
    console.print(mascot.ask("Here's how we work together:"))

    auto = _auto_transcripts_dir()
    if auto is not None:
        listen_cmd = _invocation("listen")
        listen_desc = "listen while you chat; I keep only the essence"
    else:
        listen_cmd = _invocation("listen --dir <folder>")
        listen_desc = "listen to a transcript folder for new thoughts"

    steps = [
        (listen_cmd, listen_desc),
        (_invocation("brain"), "hand me a thought yourself, any time"),
        (_invocation("inbox"), "review what I caught - nothing is kept without your OK"),
        (_invocation("memories"), "see what we've remembered together"),
    ]
    width = max(len(cmd) for cmd, _ in steps)
    for cmd, desc in steps:
        padding = " " * (width - len(cmd) + 3)
        console.print(f"  [bold]{cmd}[/bold]{padding}[dim]{desc}[/dim]")

    console.print(
        "  [dim]Tip: add --daemon to listen in the background "
        "(--status / --stop to manage it).[/dim]"
    )


@app.command()
def init(
    reconfigure: bool = typer.Option(
        False, "--reconfigure", help="Force the interactive LLM setup again."
    ),
) -> None:
    """Set up storage and choose how the cat thinks (interactive)."""

    settings = Settings.from_env()
    settings.paths.project_dir(settings.project_id).mkdir(parents=True, exist_ok=True)
    console.print(mascot.greeting())

    llm, model = settings.llm, settings.ollama_model
    already_configured = settings.paths.config_file.exists()
    env_forced = bool(os.environ.get("FCB_LLM"))

    if env_forced:
        console.print(mascot.info(f"Using LLM from environment: {llm}."))
    elif sys.stdin.isatty():
        if reconfigure or not already_configured:
            llm, model = _interactive_llm_setup(settings)
        else:
            current = llm + (f" ({model})" if llm == "ollama" else "")
            console.print(mascot.info(f"Already set up to think with: {current}."))
            if typer.confirm("Reconfigure how I think?", default=False):
                llm, model = _interactive_llm_setup(settings)

    _write_config(settings, llm=llm, ollama_model=model)
    project = _ensure_project(build_container(settings))

    suffix = f" ([bold]{model}[/bold])" if llm == "ollama" else ""
    console.print(mascot.happy(f"Storage ready at {settings.home}."))
    console.print(f"Active project: [bold]{project.id}[/bold] ({project.name}).")
    console.print(f"LLM: [bold]{llm}[/bold]{suffix}")

    _print_next_steps()


@app.command()
def save(
    thought: str = typer.Argument(..., help="The thought to remember."),
    memory_type: MemoryType = typer.Option(
        "preference", "--type", "-t", help="Memory type."
    ),
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Scope to the active project instead of global."
    ),
) -> None:
    """Directly save an explicit memory (low-friction path)."""

    container = _container()
    _ensure_project(container, prompt_name=project_scoped)
    project_id = container.project_id if project_scoped else None
    item = container.save_memory_item().execute(
        thought, memory_type=memory_type, project_id=project_id
    )
    console.print(mascot.saved(item))


def _read_lines_interactively() -> str:
    """Read typed lines until an empty line (or EOF). Intuitive, no Ctrl+D needed."""

    console.print(mascot.brain_prompt())
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)


@app.command()
def brain(
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Scope candidates to the active project."
    ),
    use_stdin: bool = typer.Option(
        False,
        "--stdin",
        help="Read raw from stdin (good for pasting/pipes; finish with CTRL+D).",
    ),
    use_editor: bool = typer.Option(
        False, "--editor", "-e", help="Compose the dump in your $EDITOR."
    ),
) -> None:
    """Capture a multi-line brain dump.

    Default: type line by line, finish with an empty line.
    Use --editor to compose in your editor, or --stdin to paste/pipe.
    """

    container = _container()
    _ensure_project(container, prompt_name=project_scoped)

    piped = not sys.stdin.isatty()
    if piped:
        text = sys.stdin.read()
    elif use_editor:
        text = _open_editor(
            "\n\n# Dump your thoughts above. Lines starting with # are ignored.\n"
            "# Save and close the editor when you're done.\n"
        )
        if text is not None:
            text = "\n".join(
                line for line in text.splitlines() if not line.startswith("#")
            )
    elif use_stdin:
        console.print(mascot.paste_prompt())
        text = sys.stdin.read()
    else:
        text = _read_lines_interactively()

    if not text or not text.strip():
        console.print(mascot.candidates_found(0))
        raise typer.Exit(code=0)

    project_id = container.project_id if project_scoped else None
    _capture_and_report(container, text, project_id=project_id)


@app.command("import")
def import_file(
    file: Path = typer.Argument(..., exists=True, readable=True, help="File to import."),
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Scope candidates to the active project."
    ),
) -> None:
    """Import a file as a brain dump."""

    container = _container()
    _ensure_project(container, prompt_name=project_scoped)
    text = file.read_text(encoding="utf-8")
    if not text.strip():
        console.print(mascot.candidates_found(0))
        raise typer.Exit(code=0)

    project_id = container.project_id if project_scoped else None
    _capture_and_report(container, text, project_id=project_id, source="import")


@app.command("import-chat")
def import_chat(
    path: Path = typer.Argument(
        None,
        help="Transcript file or folder. Defaults to this project's Cursor transcripts.",
    ),
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Scope captured candidates to the active project."
    ),
    per_message: bool = typer.Option(
        False,
        "--per-message",
        help="Analyse each message on its own (slower) instead of the whole chat.",
    ),
) -> None:
    """Document an existing chat history: distill a past transcript into the inbox.

    Useful when you start fatcatbrain after some work and want to capture what was
    already discussed. Reads only your own messages; stores no raw text.
    """

    from fatcatbrain.adapters.ingest import read_user_texts

    settings = Settings.from_env()
    container = build_container(settings)
    _ensure_project(container, prompt_name=project_scoped)

    target = path
    if target is None:
        target = _auto_transcripts_dir()
        if target is None:
            console.print(
                "[red]No transcript given and none auto-detected.[/red] "
                "Pass a file or folder path."
            )
            raise typer.Exit(code=2)
        console.print(mascot.info("Using this project's Cursor transcripts."))
    elif not target.exists():
        console.print(f"[red]Path not found:[/red] {target}")
        raise typer.Exit(code=2)

    texts = read_user_texts(target)
    if not texts:
        console.print(mascot.candidates_found(0))
        raise typer.Exit(code=0)

    problem = _llm_preflight(settings)
    if problem is not None:
        console.print(mascot.confused(problem))
        raise typer.Exit(code=2)

    capture = container.passive_capture()
    project_id = container.project_id if project_scoped else None
    console.print(
        mascot.info(f"Reading {len(texts)} of your messages from the history...")
    )

    added = 0
    try:
        if per_message:
            for text in texts:
                with console.status(mascot.thinking(), spinner="dots"):
                    result = capture.execute(
                        text, project_id=project_id, source="transcript"
                    )
                added += len(result.candidates)
        else:
            combined = "\n\n".join(texts)
            with console.status(mascot.thinking(), spinner="dots"):
                result = capture.execute(
                    combined, project_id=project_id, source="transcript"
                )
            added = len(result.candidates)
    except LLMExtractionError as exc:
        console.print(mascot.confused(f"The LLM isn't healthy:\n   {exc}"))
        raise typer.Exit(code=1)

    console.print(mascot.candidates_found(added))
    if added:
        console.print(f"Run [bold]{_invocation('inbox')}[/bold] to review them.")


@app.command()
def inbox() -> None:
    """Review pending memory candidates: save / edit / project only / discard."""

    container = _container()
    _ensure_project(container)
    pending = container.inbox_repo.list_pending()
    if not pending:
        console.print(mascot.inbox_empty())
        raise typer.Exit(code=0)

    console.print(mascot.inbox_intro(len(pending)))
    reviewer = container.review_memory_candidate()

    def _report(result) -> None:
        if result.created:
            console.print(mascot.saved(result.memory_item))
        else:
            console.print(mascot.already_known(result.memory_item))

    for index, candidate in enumerate(pending, start=1):
        console.print(mascot.candidate_intro(candidate))
        console.print(render_candidate(index, candidate))
        choice = typer.prompt("Decision [s/e/p/d/q]", default="s").strip().lower()

        if choice in ("q", "quit"):
            console.print(
                f"Pausing review. Run [bold]{_invocation('inbox')}[/bold] to continue."
            )
            break
        if choice in ("d", "discard"):
            reviewer.execute(candidate.id, "discard")
            console.print(mascot.discarded())
            continue
        if choice in ("e", "edit"):
            edited = typer.prompt("Edit content", default=candidate.content)
            result = reviewer.execute(candidate.id, "edit", edited_content=edited)
            _report(result)
            continue
        if choice in ("p", "project"):
            if not candidate.project_id:
                console.print(
                    "[yellow]Candidate has no project; saving globally instead.[/yellow]"
                )
                result = reviewer.execute(candidate.id, "save")
            else:
                result = reviewer.execute(candidate.id, "project_only")
            _report(result)
            continue
        # Default: save
        result = reviewer.execute(candidate.id, "save")
        _report(result)
    else:
        console.print(mascot.review_done())


def _distill_new_turns(container: Container, source, project_id: str | None) -> int:
    """Poll the source once and distill new turns into inbox candidates.

    Returns the number of candidates added. Raw input is never stored in this mode.
    """

    capture = container.passive_capture()
    added = 0
    for turn in source.poll():
        if not turn.strip():
            continue
        try:
            with console.status(mascot.thinking(), spinner="dots"):
                result = capture.execute(
                    turn, project_id=project_id, source="transcript"
                )
        except LLMExtractionError as exc:
            if exc.fatal:
                raise
            console.print(f"[yellow]Skipped a turn (LLM error): {exc}[/yellow]")
            continue
        added += len(result.candidates)
    return added


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _daemon_pid(settings: Settings) -> int | None:
    """Return the running background-listener pid, clearing a stale pid file."""

    pid_file = settings.paths.listen_pid_file
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    if _pid_alive(pid):
        return pid
    try:
        pid_file.unlink()
    except OSError:
        pass
    return None


def _start_daemon(
    settings: Settings,
    directory: Path | None,
    interval: float | None,
    project_scoped: bool,
) -> None:
    """Spawn a detached background listener and record its pid."""

    existing = _daemon_pid(settings)
    if existing is not None:
        console.print(
            mascot.info(f"Already listening in the background (pid {existing}).")
        )
        console.print(f"   Stop it with: [bold]{_invocation('listen --stop')}[/bold]")
        return

    settings.home.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "fatcatbrain.adapters.cli.main", "listen"]
    if directory is not None:
        cmd += ["--dir", str(directory)]
    if interval is not None:
        cmd += ["--interval", str(interval)]
    if project_scoped:
        cmd += ["--project"]

    log_file = settings.paths.listen_log_file
    with open(log_file, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(  # noqa: S603 - args are ours, not user shell input
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    settings.paths.listen_pid_file.write_text(str(proc.pid), encoding="utf-8")

    console.print(mascot.happy(f"Listening in the background (pid {proc.pid})."))
    console.print(f"   Logs:   {log_file}")
    console.print(f"   Review: [bold]{_invocation('inbox')}[/bold]")
    console.print(f"   Status: [bold]{_invocation('listen --status')}[/bold]")
    console.print(f"   Stop:   [bold]{_invocation('listen --stop')}[/bold]")


def _stop_daemon(settings: Settings) -> None:
    pid = _daemon_pid(settings)
    if pid is None:
        console.print(mascot.info("No background listener is running."))
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        console.print(mascot.confused(f"Couldn't stop pid {pid}: {exc}"))
        return
    try:
        settings.paths.listen_pid_file.unlink()
    except OSError:
        pass
    console.print(f"{mascot.stopped_listening()}  (pid {pid})")


def _status_daemon(settings: Settings) -> None:
    pid = _daemon_pid(settings)
    if pid is None:
        console.print(mascot.info("No background listener is running."))
        return
    console.print(mascot.info(f"Listening in the background (pid {pid})."))
    console.print(f"   Logs: {settings.paths.listen_log_file}")


@app.command()
def listen(
    directory: Path = typer.Option(
        None,
        "--dir",
        "-d",
        help="Transcript directory to watch (defaults to FCB_TRANSCRIPTS_DIR).",
    ),
    interval: float = typer.Option(
        None, "--interval", help="Seconds between polls (default from settings)."
    ),
    once: bool = typer.Option(
        False, "--once", help="Process the current backlog once and exit."
    ),
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Scope captured candidates to the active project."
    ),
    daemon: bool = typer.Option(
        False, "--daemon", "-D", help="Run in the background and free this terminal."
    ),
    stop: bool = typer.Option(
        False, "--stop", help="Stop the background listener."
    ),
    status: bool = typer.Option(
        False, "--status", help="Show whether a background listener is running."
    ),
) -> None:
    """Passively listen to chat transcripts and distill them into the inbox.

    The cat reads only your own messages, keeps just the essence as candidates,
    stores no raw text, and still requires review before anything becomes a memory.

    Use --daemon to run in the background; --status / --stop to manage it.
    """

    settings = Settings.from_env()

    if stop:
        _stop_daemon(settings)
        return
    if status:
        _status_daemon(settings)
        return

    container = build_container(settings)
    _ensure_project(container, prompt_name=project_scoped)

    resolved_dir = directory
    source = build_ingest_source(settings, transcripts_dir=directory)
    if source is None:
        auto = _auto_transcripts_dir()
        if auto is not None:
            console.print(
                mascot.info("Found this project's Cursor transcripts automatically.")
            )
            resolved_dir = auto
            source = build_ingest_source(settings, transcripts_dir=auto)
    if source is None:
        console.print(
            "[red]No transcript source found.[/red] "
            "Pass --dir or set FCB_TRANSCRIPTS_DIR."
        )
        raise typer.Exit(code=2)

    problem = _llm_preflight(settings)
    if problem is not None:
        console.print(mascot.confused(problem))
        raise typer.Exit(code=2)

    if daemon:
        _start_daemon(settings, resolved_dir, interval, project_scoped)
        return

    project_id = container.project_id if project_scoped else None
    poll_interval = interval or settings.listen_interval

    if once:
        try:
            added = _distill_new_turns(container, source, project_id)
        except LLMExtractionError as exc:
            console.print(mascot.confused(f"Stopping - the LLM isn't healthy:\n   {exc}"))
            raise typer.Exit(code=1)
        console.print(mascot.candidates_found(added))
        if added:
            console.print(f"Run [bold]{_invocation('inbox')}[/bold] to review them.")
        return

    console.print(mascot.listening(source.describe(), _invocation("inbox")))
    try:
        while True:
            added = _distill_new_turns(container, source, project_id)
            if added:
                console.print(
                    f"{mascot.candidates_found(added)}  "
                    f"(review in another terminal: [bold]{_invocation('inbox')}[/bold])"
                )
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        console.print("\n" + mascot.stopped_listening())
    except LLMExtractionError as exc:
        console.print(mascot.confused(f"Stopping - the LLM isn't healthy:\n   {exc}"))
        raise typer.Exit(code=1)


@app.command()
def memories(
    project_scoped: bool = typer.Option(
        False, "--project", "-p", help="Show only the active project's memories."
    ),
) -> None:
    """List confirmed memory items."""

    container = _container()
    if project_scoped:
        items = container.memory_repo.list_by_project(container.project_id)
    else:
        items = container.memory_repo.list_all()
    if not items:
        console.print(f"{MascotRenderer().greeting()}\nNo memories yet.")
        raise typer.Exit(code=0)
    console.print(render_memory_table(items))


def run() -> None:
    """Console-script entry point referenced by ``pyproject.toml``."""

    app()


if __name__ == "__main__":
    run()
