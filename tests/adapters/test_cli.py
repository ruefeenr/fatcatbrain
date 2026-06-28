"""CLI smoke tests covering the brain -> inbox -> save loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

import fatcat.adapters.cli.main as cli_main
from fatcat.application.ports import ConversationSessionDocument
from fatcat.adapters.cli.main import (
    _invocation,
    _open_editor,
    _read_lines_interactively,
    app,
)

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "default",
    }


def test_init_creates_storage(tmp_path: Path):
    result = runner.invoke(app, ["init"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "How FatCat works" in result.stdout
    assert "Memory proposals" in result.stdout
    assert "Learning issue proposals" in result.stdout
    assert "nothing is confirmed automatically" in result.stdout
    assert (tmp_path / "home" / "config.json").exists()
    assert (tmp_path / "home" / "projects" / "default" / "project.json").exists()


def test_short_help_lists_every_public_command():
    result = runner.invoke(app, ["-h"])

    assert result.exit_code == 0
    for command in (
        "init",
        "save",
        "brain",
        "import",
        "import-chat",
        "import-codex",
        "inbox",
        "review",
        "listen",
        "reset",
        "memories",
        "issues",
        "sessions",
        "start",
        "stop",
        "show",
    ):
        assert command in result.stdout
    assert "Nothing is confirmed" in result.stdout


def test_init_persists_llm_and_model_from_env(tmp_path: Path):
    env = {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "ollama",
        "FATCAT_OLLAMA_MODEL": "qwen2.5",
    }
    result = runner.invoke(app, ["init"], env=env)
    assert result.exit_code == 0
    config = json.loads(
        (tmp_path / "home" / "config.json").read_text(encoding="utf-8")
    )
    assert config["llm"] == "ollama"
    assert config["ollama_model"] == "qwen2.5"


def test_start_detects_work_and_launches_background_learning(tmp_path: Path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        cli_main,
        "_detect_active_conversation",
        lambda: ("codex", None, "Codex conversation 'Current work'"),
    )
    monkeypatch.setattr(cli_main, "_llm_preflight", lambda settings: None)
    monkeypatch.setattr(
        cli_main,
        "_start_daemon",
        lambda settings, directory, interval, project_scoped, source_name: captured.update(
            source=source_name,
            project_scoped=project_scoped,
        ),
    )

    result = runner.invoke(app, ["start"], env=_env(tmp_path))

    assert result.exit_code == 0
    assert "Found Codex conversation 'Current work'" in result.stdout
    assert captured == {"source": "codex", "project_scoped": True}


def test_show_combines_learned_context_and_open_questions(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(app, ["save", "Prefer concise explanations."] , env=env)

    result = runner.invoke(app, ["show"], env=env)

    assert result.exit_code == 0
    assert "What I know about how you work" in result.stdout
    assert "Prefer concise explanations" in result.stdout
    assert "What I am still learning" in result.stdout


def test_choose_ollama_model_picks_by_number(monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["llama3.1", "gpt-oss:20b"]
        ),
    )
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: "1")
    settings = cli_main.Settings.from_env({"FATCAT_HOME": "/tmp/fcat_x"})
    assert cli_main._choose_ollama_model(settings) == "llama3.1"


def test_choose_ollama_model_defaults_to_gpt_oss(monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["llama3.1", "gpt-oss:20b"]
        ),
    )
    # Empty answer -> use the offered default (gpt-oss is preferred).
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: k.get("default"))
    settings = cli_main.Settings.from_env({"FATCAT_HOME": "/tmp/fcat_x"})
    assert cli_main._choose_ollama_model(settings) == "gpt-oss:20b"


def test_choose_ollama_model_when_unreachable_uses_prompted_name(monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=False, models=[], error="down"
        ),
    )
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: "my-model")
    settings = cli_main.Settings.from_env({"FATCAT_HOME": "/tmp/fcat_x"})
    assert cli_main._choose_ollama_model(settings) == "my-model"


def test_save_then_memories(tmp_path: Path):
    env = _env(tmp_path)
    save = runner.invoke(app, ["save", "I prefer FastAPI."], env=env)
    assert save.exit_code == 0
    mem = runner.invoke(app, ["memories"], env=env)
    assert mem.exit_code == 0
    assert "FastAPI" in mem.stdout


def test_reset_memories_clears_stores(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(app, ["save", "I prefer FastAPI."], env=env)
    runner.invoke(app, ["save", "Project note", "-p"], env=env)

    reset = runner.invoke(app, ["reset", "-y"], env=env)
    assert reset.exit_code == 0
    assert "Cleared" in reset.stdout

    mem = runner.invoke(app, ["memories"], env=env)
    assert mem.exit_code == 0
    assert "FastAPI" not in mem.stdout
    assert "No memories yet" in mem.stdout


def test_reset_global_only(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(app, ["save", "Global note"], env=env)
    runner.invoke(app, ["save", "Project note", "-p"], env=env)

    reset = runner.invoke(app, ["reset", "-y", "--global"], env=env)
    assert reset.exit_code == 0

    mem = runner.invoke(app, ["memories"], env=env)
    assert "Global note" not in mem.stdout
    assert "Project note" in mem.stdout


def test_reset_all_projects(tmp_path: Path):
    home = tmp_path / "home"
    env_a = {
        "FATCAT_HOME": str(home),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "alpha",
    }
    env_b = {
        "FATCAT_HOME": str(home),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "beta",
    }
    runner.invoke(app, ["init"], env=env_a)
    runner.invoke(app, ["save", "Alpha note", "-p"], env=env_a)
    runner.invoke(app, ["save", "Beta note", "-p"], env=env_b)

    reset = runner.invoke(app, ["reset", "-y", "--all-projects"], env=env_a)
    assert reset.exit_code == 0

    mem_a = runner.invoke(app, ["memories"], env=env_a)
    mem_b = runner.invoke(app, ["memories"], env=env_b)
    assert "Alpha note" not in mem_a.stdout
    assert "Beta note" not in mem_b.stdout


def test_brain_then_inbox_save_loop(tmp_path: Path):
    env = _env(tmp_path)
    brain = runner.invoke(
        app,
        ["brain"],
        input="I prefer FastAPI for small APIs. We decided to use SQLite.",
        env=env,
    )
    assert brain.exit_code == 0
    assert "shiny" in brain.stdout

    # Save the first candidate, discard the second.
    inbox = runner.invoke(app, ["inbox"], input="\nn\n", env=env)
    assert inbox.exit_code == 0
    assert "Keep this" in inbox.stdout
    assert "No, forget it" in inbox.stdout
    assert "None" not in inbox.stdout

    mem = runner.invoke(app, ["memories"], env=env)
    assert "FastAPI" in mem.stdout
    assert "SQLite" not in mem.stdout


def test_inbox_confirms_issue_with_explicit_importance_and_scope(tmp_path: Path):
    env = _env(tmp_path)
    brain = runner.invoke(
        app,
        ["brain"],
        input=(
            "Do I prefer reviewing learning questions at the end of a session "
            "or immediately?"
        ),
        env=env,
    )
    assert brain.exit_code == 0

    # An unresolved question appears only once: as an issue proposal.
    inbox = runner.invoke(app, ["inbox"], input="c\n\n\n\n", env=env)

    assert inbox.exit_code == 0
    assert "What I am still unsure about" in inbox.stdout
    assert "Memory proposal" not in inbox.stdout
    assert "Confirmed learning issue" in inbox.stdout
    assert "Importance [" not in inbox.stdout
    assert "Scope [" not in inbox.stdout
    listed = runner.invoke(app, ["issues"], env=env)
    assert listed.exit_code == 0
    assert "immediately?" in listed.stdout
    assert "medium" in listed.stdout
    assert "session:" in listed.stdout


def test_deferred_issue_can_be_revisited(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(
        app,
        ["brain"],
        input="Do I prefer deferred learning questions at the next session review?",
        env=env,
    )

    deferred = runner.invoke(app, ["inbox"], input="l\n", env=env)
    assert deferred.exit_code == 0
    assert "Put aside for later" in deferred.stdout

    ordinary_inbox = runner.invoke(app, ["inbox"], env=env)
    assert "No pending candidates" in ordinary_inbox.stdout

    revisited = runner.invoke(
        app,
        ["inbox", "--deferred"],
        input="c\n\n\n\n",
        env=env,
    )
    assert revisited.exit_code == 0
    assert "Confirmed learning issue" in revisited.stdout


def test_project_backlog_question_is_not_a_learning_issue(tmp_path: Path):
    env = _env(tmp_path)

    captured = runner.invoke(
        app,
        ["brain"],
        input="How should the review screen be implemented?",
        env=env,
    )

    assert captured.exit_code == 0
    inbox = runner.invoke(app, ["inbox"], env=env)
    assert "No pending candidates" in inbox.stdout


def test_memory_details_can_correct_applicability_scope(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(
        app,
        ["brain", "--project"],
        input="I prefer reviews at the end of a coding session.",
        env=env,
    )

    reviewed = runner.invoke(
        app,
        ["review"],
        input="d\ndomain\nsoftware-development\n",
        env=env,
    )

    assert reviewed.exit_code == 0
    memories = runner.invoke(app, ["memories"], env=env)
    assert "domain:software-development" in memories.stdout


def test_invocation_keeps_uv_run_prefix(monkeypatch):
    monkeypatch.setenv("UV", "/somewhere/uv")
    monkeypatch.setattr(cli_main.sys, "argv", ["fcat"])
    assert _invocation("inbox") == "uv run fcat inbox"


def test_invocation_without_uv(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(cli_main.sys, "argv", ["/usr/local/bin/fcat"])
    assert _invocation("inbox") == "fcat inbox"


def test_read_lines_interactively_stops_on_empty_line(monkeypatch):
    feed = iter(["first thought", "second thought", "", "ignored after blank"])
    monkeypatch.setattr(cli_main, "input", lambda *a, **k: next(feed), raising=False)
    assert _read_lines_interactively() == "first thought\nsecond thought"


def test_read_lines_interactively_stops_on_eof(monkeypatch):
    feed = iter(["only line"])

    def fake_input(*args, **kwargs):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr(cli_main, "input", fake_input, raising=False)
    assert _read_lines_interactively() == "only line"


def test_open_editor_returns_edited_text(tmp_path: Path, monkeypatch):
    fake_editor = tmp_path / "fake_editor.sh"
    fake_editor.write_text(
        '#!/bin/sh\necho "edited in editor" > "$1"\n', encoding="utf-8"
    )
    fake_editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(fake_editor))
    monkeypatch.delenv("VISUAL", raising=False)

    assert _open_editor("seed") == "edited in editor\n"


def test_open_editor_returns_none_on_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDITOR", "false")  # exits non-zero
    monkeypatch.delenv("VISUAL", raising=False)
    assert _open_editor("seed") is None


def test_listen_once_distills_transcripts_into_inbox(tmp_path: Path):
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    conv = transcripts / "conv.jsonl"
    record = json.dumps(
        {
            "role": "user",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "<user_query>\nI prefer FastAPI for small APIs.\n</user_query>",
                    }
                ]
            },
        }
    )
    conv.write_text(record + "\n", encoding="utf-8")

    env = {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "default",
        "FATCAT_TRANSCRIPTS_DIR": str(transcripts),
        "FATCAT_MIN_CONFIDENCE": "0.0",
    }
    result = runner.invoke(app, ["listen", "--once"], env=env)
    assert result.exit_code == 0

    # Candidates landed in the inbox, but no raw input was stored.
    raw_file = (
        tmp_path / "home" / "projects" / "default" / "raw_inputs.jsonl"
    )
    assert not raw_file.exists()
    inbox_file = tmp_path / "home" / "projects" / "default" / "inbox.jsonl"
    assert inbox_file.exists()
    assert "FastAPI" in inbox_file.read_text(encoding="utf-8")


def test_listen_once_can_watch_codex(tmp_path: Path, monkeypatch):
    class CodexSource:
        def describe(self):
            return "Codex session 'FatCat workflow'"

        def poll(self):
            return ["I prefer concise Codex review screens."]

    monkeypatch.setattr(
        cli_main,
        "build_codex_ingest_source",
        lambda settings: CodexSource(),
    )
    env = {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "default",
        "FATCAT_MIN_CONFIDENCE": "0.0",
    }

    result = runner.invoke(
        app,
        ["listen", "--source", "codex", "--project", "--once"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Watching Codex session 'FatCat workflow'" in result.stdout
    inbox = tmp_path / "home" / "projects" / "default" / "inbox.jsonl"
    assert "concise Codex" in inbox.read_text(encoding="utf-8")


def test_listen_codex_errors_when_no_session_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "build_codex_ingest_source",
        lambda settings: None,
    )
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}

    result = runner.invoke(
        app,
        ["listen", "--source", "codex", "--once"],
        env=env,
    )

    assert result.exit_code == 2
    assert "No Codex session found" in result.stdout


def test_listen_without_source_errors(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FATCAT_TRANSCRIPTS_DIR", raising=False)
    # Avoid accidentally auto-detecting a real Cursor dir during the test.
    monkeypatch.setattr(cli_main, "_auto_transcripts_dir", lambda: None)
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}
    result = runner.invoke(app, ["listen", "--once"], env=env)
    assert result.exit_code == 2


def test_auto_transcripts_dir_resolves_existing(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "Users" / "me" / "my_proj"
    cwd.mkdir(parents=True)
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(cwd)).strip("-")
    transcripts = home / ".cursor" / "projects" / slug / "agent-transcripts"
    transcripts.mkdir(parents=True)
    assert cli_main._auto_transcripts_dir(home=home, cwd=cwd) == transcripts


def test_auto_transcripts_dir_uses_git_root_from_nested_directory(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "Users" / "me" / "my_proj"
    nested = project / "src" / "feature"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(project)).strip("-")
    transcripts = home / ".cursor" / "projects" / slug / "agent-transcripts"
    transcripts.mkdir(parents=True)

    assert cli_main._auto_transcripts_dir(home=home, cwd=nested) == transcripts


def test_auto_transcripts_dir_none_when_missing(tmp_path: Path):
    assert (
        cli_main._auto_transcripts_dir(home=tmp_path / "home", cwd=tmp_path / "x")
        is None
    )


def test_llm_preflight_skips_non_ollama_test_adapter():
    settings = cli_main.Settings.from_env(
        {"FATCAT_HOME": "/tmp/fcat_x", "FATCAT_LLM": "test"}
    )
    assert cli_main._llm_preflight(settings) is None


def test_llm_preflight_flags_missing_model(monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["gpt-oss:20b"]
        ),
    )
    settings = cli_main.Settings.from_env(
        {"FATCAT_HOME": "/tmp/fcat_x", "FATCAT_LLM": "ollama", "FATCAT_OLLAMA_MODEL": "gpt-oss"}
    )
    msg = cli_main._llm_preflight(settings)
    assert msg is not None
    assert "isn't installed" in msg
    assert "ollama pull gpt-oss" in msg


def test_llm_preflight_flags_unreachable(monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=False, models=[], error="boom"
        ),
    )
    settings = cli_main.Settings.from_env(
        {"FATCAT_HOME": "/tmp/fcat_x", "FATCAT_LLM": "ollama", "FATCAT_OLLAMA_MODEL": "gpt-oss"}
    )
    msg = cli_main._llm_preflight(settings)
    assert msg is not None
    assert "reach Ollama" in msg


def _transcript_line(text: str) -> str:
    return json.dumps(
        {
            "role": "user",
            "message": {
                "content": [{"type": "text", "text": f"<user_query>{text}</user_query>"}]
            },
        }
    )


def test_import_chat_distills_history(tmp_path: Path):
    chat = tmp_path / "conv.jsonl"
    chat.write_text(
        "\n".join(
            [
                _transcript_line("I prefer FastAPI for small APIs."),
                _transcript_line("We should not commit to SQLite too early."),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "test",
        "FATCAT_PROJECT": "default",
    }
    result = runner.invoke(app, ["import-chat", str(chat)], env=env)
    assert result.exit_code == 0
    inbox = tmp_path / "home" / "projects" / "default" / "inbox.jsonl"
    assert inbox.exists()
    assert inbox.read_text(encoding="utf-8").strip() != ""


def test_global_memory_visible_across_projects(tmp_path: Path):
    home = str(tmp_path / "home")
    env_a = {"FATCAT_HOME": home, "FATCAT_LLM": "test", "FATCAT_PROJECT": "proja"}
    env_b = {"FATCAT_HOME": home, "FATCAT_LLM": "test", "FATCAT_PROJECT": "projb"}

    # Global save in project A, then a project-scoped save in A.
    runner.invoke(app, ["save", "shared note"], env=env_a)
    runner.invoke(app, ["save", "private note", "-p"], env=env_a)

    result = runner.invoke(app, ["memories"], env=env_b)
    assert result.exit_code == 0
    assert "shared note" in result.stdout
    # Project A's project-scoped memory is NOT visible from project B.
    assert "private note" not in result.stdout


def test_import_chat_missing_path_errors(tmp_path: Path):
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}
    result = runner.invoke(app, ["import-chat", str(tmp_path / "nope.jsonl")], env=env)
    assert result.exit_code == 2


def test_listen_status_when_not_running(tmp_path: Path):
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}
    result = runner.invoke(app, ["listen", "--status"], env=env)
    assert result.exit_code == 0
    assert "No background listener" in result.stdout


def test_listen_status_when_running(tmp_path: Path):
    import os as _os

    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / "listen.pid").write_text(str(_os.getpid()), encoding="utf-8")
    env = {"FATCAT_HOME": str(home), "FATCAT_LLM": "test"}
    result = runner.invoke(app, ["listen", "--status"], env=env)
    assert result.exit_code == 0
    assert f"pid {_os.getpid()}" in result.stdout


def test_listen_stop_running(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    pid_file = home / "listen.pid"
    pid_file.write_text("99999", encoding="utf-8")

    calls = []
    monkeypatch.setattr(cli_main.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    env = {"FATCAT_HOME": str(home), "FATCAT_LLM": "test"}
    result = runner.invoke(app, ["listen", "--stop"], env=env)
    assert result.exit_code == 0
    assert (99999, cli_main.signal.SIGTERM) in calls
    assert not pid_file.exists()


def test_listen_daemon_starts(tmp_path: Path, monkeypatch):
    class FakeProc:
        pid = 4242

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main, "_auto_transcripts_dir", lambda: None)
    watch = tmp_path / "transcripts"
    watch.mkdir()
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}
    result = runner.invoke(
        app, ["listen", "--daemon", "--dir", str(watch)], env=env
    )
    assert result.exit_code == 0
    assert "background" in result.stdout
    pid_file = tmp_path / "home" / "listen.pid"
    assert pid_file.read_text(encoding="utf-8").strip() == "4242"
    assert "listen" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--source") + 1] == "cursor"
    assert str(watch) in captured["cmd"]


def test_listen_codex_daemon_preserves_source(tmp_path: Path, monkeypatch):
    class FakeProc:
        pid = 4343

    class CodexSource:
        def describe(self):
            return "Codex session 'FatCat workflow'"

        def poll(self):
            return []

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        cli_main,
        "build_codex_ingest_source",
        lambda settings: CodexSource(),
    )
    env = {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_LLM": "test"}

    result = runner.invoke(
        app,
        ["listen", "--source", "codex", "--project", "--daemon"],
        env=env,
    )

    assert result.exit_code == 0
    assert captured["cmd"][captured["cmd"].index("--source") + 1] == "codex"
    assert "--project" in captured["cmd"]


def test_listen_exits_when_model_missing(tmp_path: Path, monkeypatch):
    from fatcat.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["gpt-oss:20b"]
        ),
    )
    watch_dir = tmp_path / "transcripts"
    watch_dir.mkdir()
    env = {
        "FATCAT_HOME": str(tmp_path / "home"),
        "FATCAT_LLM": "ollama",
        "FATCAT_OLLAMA_MODEL": "gpt-oss",
    }
    result = runner.invoke(
        app, ["listen", "--once", "--dir", str(watch_dir)], env=env
    )
    assert result.exit_code == 2
    assert "isn't installed" in result.stdout


def test_inbox_empty_message(tmp_path: Path):
    env = _env(tmp_path)
    runner.invoke(app, ["init"], env=env)
    result = runner.invoke(app, ["inbox"], env=env)
    assert result.exit_code == 0
    assert "sleeping" in result.stdout.lower()


def test_import_codex_and_complete_session_review(tmp_path: Path, monkeypatch):
    document = ConversationSessionDocument(
        id="thread-1",
        title="FatCat workflow",
        source_ref="/tmp/rollout-thread-1.jsonl",
        updated_at=datetime.now(timezone.utc),
        user_messages=["I prefer concise review screens."],
        cwd="/generated/codex/workspace",
    )

    class Source:
        def latest(self):
            return document

    monkeypatch.setattr(cli_main, "build_codex_session_source", lambda: Source())
    env = _env(tmp_path)

    imported = runner.invoke(app, ["import-codex", "--yes"], env=env)

    assert imported.exit_code == 0
    assert "Detected Codex session: FatCat workflow" in imported.stdout
    assert "1 shiny thought" in imported.stdout

    reviewed = runner.invoke(app, ["review"], input="s\n", env=env)
    assert reviewed.exit_code == 0
    assert "Session review complete" in reviewed.stdout

    sessions = runner.invoke(app, ["sessions"], env=env)
    assert sessions.exit_code == 0
    assert "FatCat workflow" in sessions.stdout
    assert "reviewed" in sessions.stdout


def test_import_codex_does_not_duplicate_session(tmp_path: Path, monkeypatch):
    document = ConversationSessionDocument(
        id="thread-1",
        title="FatCat workflow",
        source_ref="/tmp/rollout-thread-1.jsonl",
        updated_at=datetime.now(timezone.utc),
        user_messages=["I prefer concise review screens."],
    )

    class Source:
        def latest(self):
            return document

    monkeypatch.setattr(cli_main, "build_codex_session_source", lambda: Source())
    env = _env(tmp_path)
    runner.invoke(app, ["import-codex", "--yes"], env=env)

    repeated = runner.invoke(app, ["import-codex", "--yes"], env=env)

    assert repeated.exit_code == 0
    assert "already imported" in repeated.stdout
