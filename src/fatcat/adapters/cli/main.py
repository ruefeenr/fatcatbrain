"""The ``fcat`` command-line interface (Typer + Rich)."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from enum import Enum
from pathlib import Path

import typer

from fatcat.adapters.cli.mascot import MascotRenderer
from fatcat.adapters.cli.render import (
    console,
    render_candidate,
    render_issue_candidate,
    render_issue_table,
    render_memory_table,
    render_session_table,
)
from fatcat.adapters.llm.errors import LLMExtractionError
from fatcat.application.use_cases.capture_brain_dump import CaptureResult
from fatcat.composition import (
    Container,
    build_codex_ingest_source,
    build_codex_session_source,
    build_container,
    build_ingest_source,
)
from fatcat.config import Settings
from fatcat.config.settings import (
    DEFAULT_PROJECT_ID,
    find_project_root,
    slugify_project,
)
from fatcat.domain.models import IssueCandidate, Project, Scope
from fatcat.domain.value_objects import MemoryType, SourceType

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "FatCat learns how you prefer to work from your own notes and AI "
        "conversations.\n\n"
        "Use start to begin, review to check what FatCat noticed, and show to "
        "see what it currently knows. Nothing is confirmed without your review."
    ),
    epilog="Use 'fcat COMMAND --help' to see every option for a command.",
    no_args_is_help=True,
)
mascot = MascotRenderer()


class ListenSource(str, Enum):
    """Conversation providers supported by passive listening."""

    cursor = "cursor"
    codex = "codex"


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
    project_root = find_project_root(cwd or Path.cwd())
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(project_root)).strip("-")
    candidate = home / ".cursor" / "projects" / slug / "agent-transcripts"
    return candidate if candidate.exists() else None


def _llm_preflight(settings: Settings) -> str | None:
    """Return a friendly problem description if the configured LLM isn't usable.

    Only checks Ollama (the one wired up). Returns ``None`` when all is well.
    """

    if settings.llm != "ollama":
        return None

    from fatcat.adapters.llm.ollama_info import probe_ollama

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

    When started via ``uv run fcat ...`` the bare ``fcat`` is not on the user's
    PATH, so the hint must keep the ``uv run`` prefix.
    """

    prog = Path(sys.argv[0]).name
    if prog in ("", "-", "-c", "python", "python3", "__main__.py"):
        prog = "fcat"
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
        prefix="fcat_brain_",
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
    session_id: str | None = None,
    source_ref: str | None = None,
) -> CaptureResult:
    """Run a capture, handling LLM failures gracefully."""

    try:
        with console.status(mascot.thinking(), spinner="dots"):
            result: CaptureResult = container.capture_brain_dump().execute(
                text,
                project_id=project_id,
                source=source,  # type: ignore[arg-type]
                session_id=session_id,
                source_ref=source_ref,
            )
    except LLMExtractionError as exc:
        console.print(f"[red]The LLM could not produce valid candidates.[/red]\n{exc}")
        raise typer.Exit(code=1)
    console.print(mascot.candidates_found(result.total_candidates))
    if result.total_candidates:
        console.print(f"Run [bold]{_invocation('review')}[/bold] to review them.")
    return result


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

    from fatcat.adapters.llm.ollama_info import probe_ollama

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
    """Tell the user, in the cat's voice, exactly how to use fcat from here."""

    console.print()
    console.print(mascot.ask("Here's how we work together:"))

    steps = [
        (_invocation("start"), "detect your work and listen in the background"),
        (_invocation("review"), "check what I learned and what I am unsure about"),
        (_invocation("show"), "see what I currently know about how you work"),
        (_invocation("stop"), "stop listening"),
    ]
    width = max(len(cmd) for cmd, _ in steps)
    for cmd, desc in steps:
        padding = " " * (width - len(cmd) + 3)
        console.print(f"  [bold]{cmd}[/bold]{padding}[dim]{desc}[/dim]")

    console.print("  [dim]Run fcat -h to see advanced commands.[/dim]")


def _print_how_it_works(settings: Settings) -> None:
    """Explain the product flow before asking setup questions."""

    console.print()
    console.print("[bold]How FatCat works[/bold]")
    console.print(
        "  [bold]1. Capture[/bold]  Give FatCat a brain dump or import/listen "
        "to a chat."
    )
    console.print(
        "  [bold]2. Propose[/bold]  Your local Ollama model suggests two distinct things:"
    )
    console.print(
        "     • [cyan]Memory proposals[/cyan] — reusable decisions, preferences "
        "and context"
    )
    console.print(
        "     • [yellow]Learning issue proposals[/yellow] — unanswered questions "
        "about how you prefer to work"
    )
    console.print(
        "  [bold]3. Review[/bold]   Proposals wait in the inbox; nothing is "
        "confirmed automatically."
    )
    console.print(
        "  [bold]4. Store[/bold]    Confirmed memories and learning questions "
        "stay locally under "
        f"[bold]{settings.home}[/bold]."
    )
    console.print(
        "  [dim]The active project is detected from the current Git repository.[/dim]"
    )
    console.print()


@app.command(rich_help_panel="Setup")
def init(
    reconfigure: bool = typer.Option(
        False, "--reconfigure", help="Force the interactive LLM setup again."
    ),
) -> None:
    """Set up storage and choose how the cat thinks (interactive)."""

    settings = Settings.from_env()
    settings.paths.project_dir(settings.project_id).mkdir(parents=True, exist_ok=True)
    console.print(mascot.greeting())
    _print_how_it_works(settings)

    llm, model = settings.llm, settings.ollama_model
    already_configured = settings.paths.config_file.exists()
    env_forced = bool(os.environ.get("FATCAT_LLM"))

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


def _detect_active_conversation():
    """Return the most recently active supported conversation source."""

    candidates: list[tuple[float, str, Path | None, str]] = []

    cursor_dir = _auto_transcripts_dir()
    if cursor_dir is not None:
        from fatcat.adapters.ingest import latest_transcript_file

        latest_cursor = latest_transcript_file(cursor_dir)
        if latest_cursor is not None:
            candidates.append(
                (
                    latest_cursor.stat().st_mtime,
                    "cursor",
                    cursor_dir,
                    f"Cursor conversation in {find_project_root().name}",
                )
            )

    codex_document = build_codex_session_source().latest()
    if codex_document is not None:
        candidates.append(
            (
                codex_document.updated_at.timestamp(),
                "codex",
                None,
                f"Codex conversation '{codex_document.title}'",
            )
        )

    if not candidates:
        return None
    _, source_name, directory, description = max(candidates, key=lambda item: item[0])
    return source_name, directory, description


@app.command(rich_help_panel="Everyday")
def start() -> None:
    """Automatically detect the current work and start learning in the background."""

    settings = Settings.from_env()
    if not settings.paths.config_file.exists():
        _write_config(
            settings,
            llm=settings.llm,
            ollama_model=settings.ollama_model,
        )
    container = build_container(settings)
    project = _ensure_project(container)

    detected = _detect_active_conversation()
    if detected is None:
        console.print(
            mascot.confused(
                "I could not find an active Cursor or Codex conversation.\n"
                f"   You can still tell me something with: {_invocation('brain')}"
            )
        )
        raise typer.Exit(code=2)

    problem = _llm_preflight(settings)
    if problem is not None:
        console.print(mascot.confused(problem))
        raise typer.Exit(code=2)

    source_name, directory, description = detected
    console.print(mascot.info(f"Found {description}."))
    console.print(mascot.info(f"Learning for project: {project.name}."))
    _start_daemon(
        settings,
        directory,
        None,
        True,
        source_name,
    )


@app.command(rich_help_panel="Everyday")
def stop() -> None:
    """Stop background learning."""

    _stop_daemon(Settings.from_env())


@app.command(rich_help_panel="Advanced")
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


@app.command(rich_help_panel="Advanced")
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
    session = container.session_lifecycle().start(
        source="brain_dump",
        project_id=container.project_id,
        title="Brain dump",
    )
    _capture_and_report(
        container,
        text,
        project_id=project_id,
        session_id=session.id,
    )
    container.session_lifecycle().end(session.id)
    if sys.stdin.isatty() and typer.confirm(
        "Review this session now?",
        default=True,
    ):
        _review_candidates(container, session_id=session.id)


@app.command("import", rich_help_panel="Advanced")
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


@app.command("import-chat", rich_help_panel="Advanced")
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

    Useful when you start fatcat after some work and want to capture what was
    already discussed. Reads only your own messages; stores no raw text.
    """

    from fatcat.adapters.ingest import latest_transcript_file, read_user_texts

    settings = Settings.from_env()
    container = build_container(settings)
    _ensure_project(container, prompt_name=project_scoped)

    target = path
    auto_selected = target is None
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

    if auto_selected and target.is_dir():
        latest = latest_transcript_file(target)
        if latest is not None:
            target = latest
            console.print(mascot.info("Using the latest Cursor conversation."))

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
    session = container.session_lifecycle().start(
        source="transcript",
        project_id=container.project_id,
        source_ref=str(target),
        title=f"Cursor import: {target.stem if target.is_file() else target.name}",
    )
    console.print(
        mascot.info(f"Reading {len(texts)} of your messages from the history...")
    )

    added = 0
    try:
        if per_message:
            for text in texts:
                with console.status(mascot.thinking(), spinner="dots"):
                    result = capture.execute(
                        text,
                        project_id=project_id,
                        source="transcript",
                        session_id=session.id,
                        source_ref=str(target),
                    )
                added += result.total_candidates
        else:
            combined = "\n\n".join(texts)
            with console.status(mascot.thinking(), spinner="dots"):
                result = capture.execute(
                    combined,
                    project_id=project_id,
                    source="transcript",
                    session_id=session.id,
                    source_ref=str(target),
                )
            added = result.total_candidates
    except LLMExtractionError as exc:
        container.session_lifecycle().end(session.id)
        console.print(mascot.confused(f"The LLM isn't healthy:\n   {exc}"))
        raise typer.Exit(code=1)

    container.session_lifecycle().end(session.id)
    console.print(mascot.candidates_found(added))
    if added:
        console.print(
            f"Run [bold]{_invocation(f'review {session.id}')}[/bold] "
            "to review this session."
        )


@app.command("import-codex", rich_help_panel="Advanced")
def import_codex(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Import the detected Codex session without confirmation.",
    ),
) -> None:
    """Import the most recently active Codex conversation into a FatCat session."""

    settings = Settings.from_env()
    container = build_container(settings)
    project = _ensure_project(container, prompt_name=True)
    document = build_codex_session_source().latest()
    if document is None:
        console.print(mascot.info("No local Codex session found."))
        raise typer.Exit(code=0)
    if not document.user_messages:
        console.print(mascot.info("The detected Codex session has no user messages."))
        raise typer.Exit(code=0)

    session_id = f"codex_{document.id}"
    existing = container.session_repo.get(session_id)
    if existing is not None:
        console.print(
            mascot.info(
                f"Codex session already imported: {existing.title or existing.id}."
            )
        )
        raise typer.Exit(code=0)

    console.print(
        mascot.info(
            f"Detected Codex session: {document.title}\n"
            f"   {len(document.user_messages)} user messages\n"
            f"   FatCat project: {project.name}"
        )
    )
    if not yes and not typer.confirm("Import this Codex session?", default=True):
        raise typer.Exit(code=0)

    problem = _llm_preflight(settings)
    if problem is not None:
        console.print(mascot.confused(problem))
        raise typer.Exit(code=2)

    lifecycle = container.session_lifecycle()
    session = lifecycle.start(
        source="codex",
        project_id=container.project_id,
        source_ref=document.source_ref,
        title=document.title,
        session_id=session_id,
    )
    combined = "\n\n".join(document.user_messages)
    try:
        with console.status(mascot.thinking(), spinner="dots"):
            result = container.passive_capture().execute(
                combined,
                project_id=container.project_id,
                source="codex",
                session_id=session.id,
                source_ref=document.source_ref,
            )
    except LLMExtractionError as exc:
        lifecycle.end(session.id)
        console.print(mascot.confused(f"The LLM isn't healthy:\n   {exc}"))
        raise typer.Exit(code=1)
    lifecycle.end(session.id)
    console.print(mascot.candidates_found(result.total_candidates))
    if result.total_candidates:
        console.print(
            f"Run [bold]{_invocation(f'review {session.id}')}[/bold] "
            "to review this session."
        )
        if not yes and typer.confirm("Review this session now?", default=True):
            _review_candidates(container, session_id=session.id)


def _prompt_issue_importance(candidate: IssueCandidate) -> str:
    allowed = ("low", "medium", "high", "core")
    default = candidate.suggested_importance or "medium"
    while True:
        value = typer.prompt(
            "Importance [low/medium/high/core]",
            default=default,
        ).strip().lower()
        if value in allowed:
            return value
        console.print("[yellow]Choose low, medium, high, or core.[/yellow]")


def _default_issue_scope(candidate: IssueCandidate) -> Scope:
    suggested = candidate.suggested_scope
    if suggested is not None:
        return suggested
    if candidate.session_id:
        return Scope(level="session", reference_id=candidate.session_id)
    return Scope(level="global")


def _prompt_issue_scope(candidate: IssueCandidate) -> Scope:
    suggested = _default_issue_scope(candidate)

    allowed = ("session", "project", "domain", "global")
    while True:
        level = typer.prompt(
            "Scope [session/project/domain/global]",
            default=suggested.level,
        ).strip().lower()
        if level in allowed:
            break
        console.print("[yellow]Choose session, project, domain, or global.[/yellow]")

    if level == "global":
        return Scope(level="global")

    default_reference = (
        suggested.reference_id
        if suggested.level == level
        else (
            candidate.session_id
            if level == "session"
            else candidate.observed_in_project_id if level == "project" else None
        )
    )
    while True:
        reference = typer.prompt(
            f"{level.title()} reference",
            default=default_reference or "",
        ).strip()
        if reference:
            return Scope(level=level, reference_id=reference)
        console.print("[yellow]A non-global scope needs a reference.[/yellow]")


def _prompt_memory_scope(candidate) -> str:
    """Let advanced users correct applicability without exposing it by default."""

    suggested = candidate.scope_ref
    allowed = ("session", "project", "domain", "global")
    while True:
        level = typer.prompt(
            "Applies to [session/project/domain/global]",
            default=suggested.level,
        ).strip().lower()
        if level in allowed:
            break
        console.print("[yellow]Choose session, project, domain, or global.[/yellow]")
    if level == "global":
        return "global"
    default_reference = (
        suggested.reference_id
        if suggested.level == level
        else candidate.session_id if level == "session"
        else candidate.project_id if level == "project"
        else None
    )
    while True:
        reference = typer.prompt(
            f"{level.title()} name",
            default=default_reference or "",
        ).strip()
        if reference:
            return Scope(level=level, reference_id=reference).to_legacy()
        console.print("[yellow]This scope needs a name.[/yellow]")


def _select_merge_target(container: Container):
    issues = container.issue_repo.list_all()
    if not issues:
        console.print("[yellow]There are no learning issues to merge into.[/yellow]")
        return None
    console.print(render_issue_table(issues, numbered=True))
    selection = typer.prompt("Merge into issue number").strip()
    try:
        return issues[int(selection) - 1]
    except (ValueError, IndexError):
        console.print("[yellow]Invalid issue number; candidate left unchanged.[/yellow]")
        return None


def _print_memory_review_actions() -> None:
    console.print("  [bold]Enter[/bold]  Keep this")
    console.print("  [bold]e[/bold]      Edit it first")
    console.print("  [bold]n[/bold]      No, forget it")
    console.print("  [bold]d[/bold]      Change details such as where it applies")
    console.print("  [bold]q[/bold]      Finish later")


def _print_issue_review_actions() -> None:
    console.print("  [bold]Enter[/bold]  Yes, watch for an answer")
    console.print("  [bold]e[/bold]      Edit the question first")
    console.print("  [bold]n[/bold]      No, this is not useful")
    console.print("  [bold]l[/bold]      Ask me later")
    console.print("  [bold]d[/bold]      Change advanced details")
    console.print("  [bold]q[/bold]      Finish later")


def _review_candidates(
    container: Container,
    *,
    include_deferred: bool = False,
    session_id: str | None = None,
) -> bool:
    """Run the shared interactive review loop."""

    memory_pending = container.inbox_repo.list_pending(session_id)
    issue_pending = container.issue_candidate_repo.list_pending(session_id)
    if include_deferred:
        issue_pending += container.issue_candidate_repo.list_deferred(session_id)

    if not memory_pending and not issue_pending:
        if session_id is not None:
            session = container.session_repo.get(session_id)
            if session is not None and session.status == "ended":
                container.review_session().complete(session_id)
                console.print(mascot.info("Session review complete."))
        else:
            console.print(mascot.inbox_empty())
        return True

    memory_reviewer = container.review_memory_candidate()

    def _report_memory(result) -> None:
        if result.created:
            console.print(mascot.saved(result.memory_item))
        else:
            console.print(mascot.already_known(result.memory_item))

    if memory_pending:
        console.print(mascot.memory_inbox_intro(len(memory_pending)))
    for index, candidate in enumerate(memory_pending, start=1):
        console.print(mascot.candidate_intro(candidate))
        console.print(render_candidate(index, candidate))
        _print_memory_review_actions()
        choice = typer.prompt("Choose", default="keep").strip().lower()

        if choice in ("q", "quit"):
            console.print(
                f"Saved for later. Run [bold]{_invocation('review')}[/bold] to continue."
            )
            return False
        if choice in ("n", "no", "discard", "reject", "x"):
            memory_reviewer.execute(candidate.id, "discard")
            console.print(mascot.discarded())
            continue
        if choice in ("e", "edit"):
            edited = typer.prompt("Edit content", default=candidate.content)
            result = memory_reviewer.execute(
                candidate.id,
                "edit",
                edited_content=edited,
            )
            _report_memory(result)
            continue
        if choice in ("d", "details"):
            console.print(f"  Type: {candidate.memory_type}")
            console.print(f"  Suggested scope: {candidate.suggested_scope}")
            console.print(f"  Confidence: {candidate.confidence:.2f}")
            selected_scope = _prompt_memory_scope(candidate)
            _report_memory(
                memory_reviewer.execute(
                    candidate.id,
                    "save",
                    scope=selected_scope,
                )
            )
            continue
        if choice in ("p", "project"):
            result = memory_reviewer.execute(
                candidate.id,
                "project_only",
                project_id=container.project_id,
            )
            _report_memory(result)
            continue
        _report_memory(memory_reviewer.execute(candidate.id, "save"))

    if issue_pending:
        console.print(mascot.issue_inbox_intro(len(issue_pending)))
    issue_reviewer = container.review_issue_candidate()
    for index, candidate in enumerate(issue_pending, start=1):
        console.print(render_issue_candidate(index, candidate))
        _print_issue_review_actions()
        choice = typer.prompt("Choose", default="watch").strip().lower()

        if choice in ("q", "quit"):
            console.print(
                f"Saved for later. Run [bold]{_invocation('review')}[/bold] to continue."
            )
            return False
        if choice in ("n", "no", "r", "reject"):
            issue_reviewer.execute(candidate.id, "reject")
            console.print(mascot.discarded())
            continue
        if choice in ("l", "later", "defer"):
            issue_reviewer.execute(candidate.id, "defer")
            console.print(mascot.info("Put aside for later."))
            continue
        if choice in ("m", "merge"):
            target = _select_merge_target(container)
            if target is None:
                continue
            result = issue_reviewer.execute(
                candidate.id,
                "merge",
                merge_target_id=target.id,
            )
            console.print(
                mascot.happy(f"Merged into learning issue: {result.issue.question}")
            )
            continue

        edited_title = None
        edited_description = None
        decision = "confirm"
        if choice in ("e", "edit"):
            decision = "edit"
            edited_title = typer.prompt("Edit question", default=candidate.question)
            edited_description = typer.prompt(
                "Edit learning goal",
                default=candidate.learning_goal,
            )
        if choice in ("d", "details"):
            console.print(
                "  Expected knowledge: "
                + (", ".join(candidate.target_memory_types) or "unspecified")
            )
            console.print(f"  Confidence: {candidate.confidence:.2f}")
            importance = _prompt_issue_importance(candidate)
            scope = _prompt_issue_scope(candidate)
        else:
            importance = candidate.suggested_importance or "medium"
            scope = _default_issue_scope(candidate)
        result = issue_reviewer.execute(
            candidate.id,
            decision,
            scope=scope,
            importance=importance,
            edited_title=edited_title,
            edited_description=edited_description,
        )
        console.print(
            mascot.happy(
                f"Confirmed learning issue: {result.issue.question} "
                f"({result.issue.importance}, {result.issue.scope.to_legacy()})"
            )
        )

    console.print(mascot.review_done())
    if session_id is not None:
        container.review_session().complete(session_id)
        console.print(mascot.info("Session review complete."))
    return True


@app.command(rich_help_panel="Advanced")
def inbox(
    include_deferred: bool = typer.Option(
        False,
        "--deferred",
        help="Include issue candidates previously put aside for later.",
    ),
) -> None:
    """Review pending memory and learning-issue proposals."""

    container = _container()
    _ensure_project(container)
    _review_candidates(container, include_deferred=include_deferred)


@app.command(rich_help_panel="Everyday")
def review(
    session_id: str = typer.Argument(
        None,
        help="Session id. Defaults to the latest unreviewed project session.",
    ),
    include_deferred: bool = typer.Option(
        False,
        "--deferred",
        help="Include issue candidates put aside for later.",
    ),
) -> None:
    """Review what FatCat learned and what it is still unsure about."""

    container = _container()
    _ensure_project(container)
    session = (
        container.session_repo.get(session_id)
        if session_id
        else container.session_lifecycle().latest_unreviewed(container.project_id)
    )
    if session is None:
        _review_candidates(
            container,
            include_deferred=include_deferred,
        )
        return
    console.print(
        mascot.info(
            f"Reviewing session: {session.title or session.id} "
            f"({session.source}, {session.id})"
        )
    )
    _review_candidates(
        container,
        include_deferred=include_deferred,
        session_id=session.id,
    )


def _distill_new_turns(
    container: Container,
    source,
    project_id: str | None,
    source_type: SourceType = "transcript",
) -> int:
    """Poll the source once and distill new turns into inbox candidates.

    Returns the number of candidates added. Raw input is never stored in this mode.
    """

    turns = [turn.strip() for turn in source.poll() if turn.strip()]
    if not turns:
        return 0

    # A poll is one observation window. Analyse its turns together so the model
    # can synthesize patterns instead of producing one candidate per message.
    combined = "\n\n".join(turns)
    try:
        with console.status(mascot.thinking(), spinner="dots"):
            result = container.passive_capture().execute(
                combined,
                project_id=project_id,
                source=source_type,
            )
    except LLMExtractionError as exc:
        if exc.fatal:
            raise
        console.print(f"[yellow]Skipped this observation window: {exc}[/yellow]")
        return 0
    return result.total_candidates


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
    source_name: str,
) -> None:
    """Spawn a detached background listener and record its pid."""

    existing = _daemon_pid(settings)
    if existing is not None:
        console.print(
            mascot.info(f"Already listening in the background (pid {existing}).")
        )
        console.print(f"   Stop it with: [bold]{_invocation('stop')}[/bold]")
        return

    settings.home.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "fatcat.adapters.cli.main", "listen"]
    cmd += ["--source", source_name]
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
    console.print(f"   Review: [bold]{_invocation('review')}[/bold]")
    console.print(f"   Status: [bold]{_invocation('listen --status')}[/bold]")
    console.print(f"   Stop:   [bold]{_invocation('stop')}[/bold]")


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


@app.command(rich_help_panel="Advanced")
def listen(
    source_name: ListenSource = typer.Option(
        ListenSource.cursor,
        "--source",
        help="Conversation source to watch.",
    ),
    directory: Path = typer.Option(
        None,
        "--dir",
        "-d",
        help="Transcript directory to watch (defaults to FATCAT_TRANSCRIPTS_DIR).",
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
    """Passively listen to Cursor or Codex and distill turns into the inbox.

    The cat reads only your own messages, keeps just the essence as candidates,
    stores no raw text, and still requires review before anything becomes a memory.

    Codex listening binds to the latest active session when the listener starts.

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

    source_name = source_name.value
    if source_name == "codex" and directory is not None:
        console.print("[red]--dir can only be used with --source cursor.[/red]")
        raise typer.Exit(code=2)

    resolved_dir = directory
    if source_name == "codex":
        source = build_codex_ingest_source(settings)
        if source is not None:
            console.print(mascot.info(f"Watching {source.describe()}."))
    else:
        source = build_ingest_source(settings, transcripts_dir=directory)
        if source is None:
            auto = _auto_transcripts_dir()
            if auto is not None:
                console.print(
                    mascot.info(
                        "Found this project's Cursor transcripts automatically."
                    )
                )
                resolved_dir = auto
                source = build_ingest_source(settings, transcripts_dir=auto)

    if source is None:
        if source_name == "codex":
            console.print(
                "[red]No Codex session found.[/red] Start a Codex conversation "
                "and try again."
            )
        else:
            console.print(
                "[red]No Cursor transcript source found.[/red] "
                "Pass --dir or set FATCAT_TRANSCRIPTS_DIR."
            )
        raise typer.Exit(code=2)

    problem = _llm_preflight(settings)
    if problem is not None:
        console.print(mascot.confused(problem))
        raise typer.Exit(code=2)

    if daemon:
        _start_daemon(
            settings,
            resolved_dir,
            interval,
            project_scoped,
            source_name,
        )
        return

    project_id = container.project_id if project_scoped else None
    poll_interval = interval or settings.listen_interval
    source_type: SourceType = "codex" if source_name == "codex" else "transcript"

    if once:
        try:
            added = _distill_new_turns(
                container,
                source,
                project_id,
                source_type,
            )
        except LLMExtractionError as exc:
            console.print(mascot.confused(f"Stopping - the LLM isn't healthy:\n   {exc}"))
            raise typer.Exit(code=1)
        console.print(mascot.candidates_found(added))
        if added:
            console.print(f"Run [bold]{_invocation('review')}[/bold] to review them.")
        return

    console.print(mascot.listening(source.describe(), _invocation("review")))
    try:
        while True:
            added = _distill_new_turns(
                container,
                source,
                project_id,
                source_type,
            )
            if added:
                console.print(
                    f"{mascot.candidates_found(added)}  "
                    f"(review in another terminal: [bold]{_invocation('review')}[/bold])"
                )
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        console.print("\n" + mascot.stopped_listening())
    except LLMExtractionError as exc:
        console.print(mascot.confused(f"Stopping - the LLM isn't healthy:\n   {exc}"))
        raise typer.Exit(code=1)


def _unlink_jsonl(path: Path) -> bool:
    if path.is_file():
        path.unlink()
        return True
    return False


def _memory_files_to_clear(
    settings: Settings,
    *,
    global_only: bool,
    project_only: bool,
    all_projects: bool,
) -> list[Path]:
    paths = settings.paths

    if all_projects:
        targets = [paths.global_memory_items_file]
        projects_root = paths.projects_dir
        if projects_root.is_dir():
            for project_dir in sorted(projects_root.iterdir()):
                if project_dir.is_dir():
                    targets.append(project_dir / "memory_items.jsonl")
        return targets

    if global_only:
        return [paths.global_memory_items_file]

    if project_only:
        return [paths.memory_items_file(settings.project_id)]

    return [
        paths.global_memory_items_file,
        paths.memory_items_file(settings.project_id),
    ]


def _describe_storage_paths(paths: list[Path], home: Path) -> str:
    labels: list[str] = []
    for path in paths:
        try:
            labels.append(str(path.relative_to(home)))
        except ValueError:
            labels.append(str(path))
    return ", ".join(labels)


@app.command(rich_help_panel="Advanced")
def reset(
    memories: bool = typer.Option(
        True,
        "--memories/--no-memories",
        help="Clear confirmed memory stores.",
    ),
    inbox: bool = typer.Option(
        False, "--inbox", help="Clear the active project's inbox."
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Clear the active project's raw inputs."
    ),
    all_projects: bool = typer.Option(
        False,
        "--all-projects",
        "-a",
        help="Clear memories for every project (and global).",
    ),
    global_only: bool = typer.Option(
        False, "--global", "-g", help="Clear only global memories."
    ),
    project_only: bool = typer.Option(
        False, "--project", "-p", help="Clear only the active project's memories."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete stored data — handy while developing or when you want a clean slate."""

    if global_only and project_only:
        console.print(mascot.confused("Pick either --global or --project, not both."))
        raise typer.Exit(code=1)
    if (global_only or project_only) and all_projects:
        console.print(
            mascot.confused(
                "--all-projects can't be combined with --global or --project."
            )
        )
        raise typer.Exit(code=1)
    if not memories and not inbox and not raw:
        console.print(
            mascot.confused("Nothing selected. Use --memories, --inbox, or --raw.")
        )
        raise typer.Exit(code=1)

    settings = Settings.from_env()
    paths = settings.paths
    targets: list[Path] = []

    if memories:
        targets.extend(
            _memory_files_to_clear(
                settings,
                global_only=global_only,
                project_only=project_only,
                all_projects=all_projects,
            )
        )
    if inbox:
        targets.append(paths.inbox_file(settings.project_id))
    if raw:
        targets.append(paths.raw_inputs_file(settings.project_id))

    seen: set[Path] = set()
    unique_targets: list[Path] = []
    for path in targets:
        if path not in seen:
            seen.add(path)
            unique_targets.append(path)

    existing = [path for path in unique_targets if path.is_file()]
    if not existing:
        console.print(mascot.info("Nothing to clear — stores are already empty."))
        raise typer.Exit(code=0)

    summary = _describe_storage_paths(existing, settings.home)
    if not yes and not typer.confirm(f"Delete {summary}?"):
        raise typer.Exit(code=0)

    cleared = sum(1 for path in existing if _unlink_jsonl(path))
    console.print(mascot.cleared(cleared, summary))


@app.command(rich_help_panel="Advanced")
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


@app.command(rich_help_panel="Advanced")
def issues(
    project_scoped: bool = typer.Option(
        False,
        "--project",
        "-p",
        help="Show only learning issues scoped to the active project.",
    ),
) -> None:
    """List user-confirmed learning questions."""

    container = _container()
    if project_scoped:
        items = container.issue_repo.list_by_project(container.project_id)
    else:
        items = container.issue_repo.list_all()
    if not items:
        console.print(f"{MascotRenderer().greeting()}\nNo learning issues yet.")
        raise typer.Exit(code=0)
    console.print(render_issue_table(items))


@app.command(rich_help_panel="Everyday")
def show() -> None:
    """Show what FatCat currently knows and is still learning about you."""

    container = _container()
    _ensure_project(container)
    memories = container.memory_repo.list_all()
    issues = container.issue_repo.list_all()

    console.print(mascot.greeting())
    console.print("\n[bold]What I know about how you work[/bold]")
    if memories:
        for item in memories:
            console.print(f"  • {item.content}")
    else:
        console.print("  [dim]Nothing confirmed yet.[/dim]")

    console.print("\n[bold]What I am still learning[/bold]")
    if issues:
        for item in issues:
            console.print(f"  • {item.question}")
            console.print(f"    [dim]{item.learning_goal}[/dim]")
    else:
        console.print("  [dim]No open learning questions.[/dim]")


@app.command(rich_help_panel="Advanced")
def sessions() -> None:
    """List capture sessions for the active project."""

    container = _container()
    items = container.session_repo.list_by_project(container.project_id)
    if not items:
        console.print(mascot.info("No capture sessions yet."))
        raise typer.Exit(code=0)
    console.print(render_session_table(items))


def run() -> None:
    """Console-script entry point referenced by ``pyproject.toml``."""

    app()


if __name__ == "__main__":
    run()
