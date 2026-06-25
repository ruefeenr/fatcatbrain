"""CLI smoke tests covering the brain -> inbox -> save loop."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import fatcatbrain.adapters.cli.main as cli_main
from fatcatbrain.adapters.cli.main import (
    _invocation,
    _open_editor,
    _read_lines_interactively,
    app,
)

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "FCB_HOME": str(tmp_path / "home"),
        "FCB_LLM": "fake",
        "FCB_PROJECT": "default",
    }


def test_init_creates_storage(tmp_path: Path):
    result = runner.invoke(app, ["init"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert (tmp_path / "home" / "config.json").exists()
    assert (tmp_path / "home" / "projects" / "default" / "project.json").exists()


def test_init_persists_llm_and_model_from_env(tmp_path: Path):
    env = {
        "FCB_HOME": str(tmp_path / "home"),
        "FCB_LLM": "ollama",
        "FCB_OLLAMA_MODEL": "qwen2.5",
    }
    result = runner.invoke(app, ["init"], env=env)
    assert result.exit_code == 0
    config = json.loads(
        (tmp_path / "home" / "config.json").read_text(encoding="utf-8")
    )
    assert config["llm"] == "ollama"
    assert config["ollama_model"] == "qwen2.5"


def test_choose_ollama_model_picks_by_number(monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["llama3.1", "gpt-oss:20b"]
        ),
    )
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: "1")
    settings = cli_main.Settings.from_env({"FCB_HOME": "/tmp/fcb_x"})
    assert cli_main._choose_ollama_model(settings) == "llama3.1"


def test_choose_ollama_model_defaults_to_gpt_oss(monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["llama3.1", "gpt-oss:20b"]
        ),
    )
    # Empty answer -> use the offered default (gpt-oss is preferred).
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: k.get("default"))
    settings = cli_main.Settings.from_env({"FCB_HOME": "/tmp/fcb_x"})
    assert cli_main._choose_ollama_model(settings) == "gpt-oss:20b"


def test_choose_ollama_model_when_unreachable_uses_prompted_name(monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=False, models=[], error="down"
        ),
    )
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *a, **k: "my-model")
    settings = cli_main.Settings.from_env({"FCB_HOME": "/tmp/fcb_x"})
    assert cli_main._choose_ollama_model(settings) == "my-model"


def test_save_then_memories(tmp_path: Path):
    env = _env(tmp_path)
    save = runner.invoke(app, ["save", "I prefer FastAPI."], env=env)
    assert save.exit_code == 0
    mem = runner.invoke(app, ["memories"], env=env)
    assert mem.exit_code == 0
    assert "FastAPI" in mem.stdout


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
    inbox = runner.invoke(app, ["inbox"], input="s\nd\n", env=env)
    assert inbox.exit_code == 0

    mem = runner.invoke(app, ["memories"], env=env)
    assert "FastAPI" in mem.stdout
    assert "SQLite" not in mem.stdout


def test_invocation_keeps_uv_run_prefix(monkeypatch):
    monkeypatch.setenv("UV", "/somewhere/uv")
    monkeypatch.setattr(cli_main.sys, "argv", ["fcb"])
    assert _invocation("inbox") == "uv run fcb inbox"


def test_invocation_without_uv(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(cli_main.sys, "argv", ["/usr/local/bin/fcb"])
    assert _invocation("inbox") == "fcb inbox"


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
        "FCB_HOME": str(tmp_path / "home"),
        "FCB_LLM": "fake",
        "FCB_PROJECT": "default",
        "FCB_TRANSCRIPTS_DIR": str(transcripts),
        "FCB_MIN_CONFIDENCE": "0.0",
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


def test_listen_without_source_errors(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FCB_TRANSCRIPTS_DIR", raising=False)
    # Avoid accidentally auto-detecting a real Cursor dir during the test.
    monkeypatch.setattr(cli_main, "_auto_transcripts_dir", lambda: None)
    env = {"FCB_HOME": str(tmp_path / "home"), "FCB_LLM": "fake"}
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


def test_auto_transcripts_dir_none_when_missing(tmp_path: Path):
    assert (
        cli_main._auto_transcripts_dir(home=tmp_path / "home", cwd=tmp_path / "x")
        is None
    )


def test_llm_preflight_ok_for_fake():
    settings = cli_main.Settings.from_env({"FCB_HOME": "/tmp/fcb_x", "FCB_LLM": "fake"})
    assert cli_main._llm_preflight(settings) is None


def test_llm_preflight_flags_missing_model(monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=True, models=["gpt-oss:20b"]
        ),
    )
    settings = cli_main.Settings.from_env(
        {"FCB_HOME": "/tmp/fcb_x", "FCB_LLM": "ollama", "FCB_OLLAMA_MODEL": "gpt-oss"}
    )
    msg = cli_main._llm_preflight(settings)
    assert msg is not None
    assert "isn't installed" in msg
    assert "ollama pull gpt-oss" in msg


def test_llm_preflight_flags_unreachable(monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

    monkeypatch.setattr(
        ollama_info,
        "probe_ollama",
        lambda host=None: ollama_info.OllamaStatus(
            reachable=False, models=[], error="boom"
        ),
    )
    settings = cli_main.Settings.from_env(
        {"FCB_HOME": "/tmp/fcb_x", "FCB_LLM": "ollama", "FCB_OLLAMA_MODEL": "gpt-oss"}
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
        "FCB_HOME": str(tmp_path / "home"),
        "FCB_LLM": "fake",
        "FCB_PROJECT": "default",
    }
    result = runner.invoke(app, ["import-chat", str(chat)], env=env)
    assert result.exit_code == 0
    inbox = tmp_path / "home" / "projects" / "default" / "inbox.jsonl"
    assert inbox.exists()
    assert inbox.read_text(encoding="utf-8").strip() != ""


def test_global_memory_visible_across_projects(tmp_path: Path):
    home = str(tmp_path / "home")
    env_a = {"FCB_HOME": home, "FCB_LLM": "fake", "FCB_PROJECT": "proja"}
    env_b = {"FCB_HOME": home, "FCB_LLM": "fake", "FCB_PROJECT": "projb"}

    # Global save in project A, then a project-scoped save in A.
    runner.invoke(app, ["save", "shared note"], env=env_a)
    runner.invoke(app, ["save", "private note", "-p"], env=env_a)

    result = runner.invoke(app, ["memories"], env=env_b)
    assert result.exit_code == 0
    assert "shared note" in result.stdout
    # Project A's project-scoped memory is NOT visible from project B.
    assert "private note" not in result.stdout


def test_import_chat_missing_path_errors(tmp_path: Path):
    env = {"FCB_HOME": str(tmp_path / "home"), "FCB_LLM": "fake"}
    result = runner.invoke(app, ["import-chat", str(tmp_path / "nope.jsonl")], env=env)
    assert result.exit_code == 2


def test_listen_status_when_not_running(tmp_path: Path):
    env = {"FCB_HOME": str(tmp_path / "home"), "FCB_LLM": "fake"}
    result = runner.invoke(app, ["listen", "--status"], env=env)
    assert result.exit_code == 0
    assert "No background listener" in result.stdout


def test_listen_status_when_running(tmp_path: Path):
    import os as _os

    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / "listen.pid").write_text(str(_os.getpid()), encoding="utf-8")
    env = {"FCB_HOME": str(home), "FCB_LLM": "fake"}
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
    env = {"FCB_HOME": str(home), "FCB_LLM": "fake"}
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
    env = {"FCB_HOME": str(tmp_path / "home"), "FCB_LLM": "fake"}
    result = runner.invoke(
        app, ["listen", "--daemon", "--dir", str(watch)], env=env
    )
    assert result.exit_code == 0
    assert "background" in result.stdout
    pid_file = tmp_path / "home" / "listen.pid"
    assert pid_file.read_text(encoding="utf-8").strip() == "4242"
    assert "listen" in captured["cmd"]
    assert str(watch) in captured["cmd"]


def test_listen_exits_when_model_missing(tmp_path: Path, monkeypatch):
    from fatcatbrain.adapters.llm import ollama_info

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
        "FCB_HOME": str(tmp_path / "home"),
        "FCB_LLM": "ollama",
        "FCB_OLLAMA_MODEL": "gpt-oss",
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
