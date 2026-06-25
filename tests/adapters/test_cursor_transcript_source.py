"""Tests for the Cursor transcript ingest source."""

from __future__ import annotations

import json
from pathlib import Path

from fatcatbrain.adapters.ingest import CursorTranscriptSource, read_user_texts


def _user(text: str) -> str:
    return json.dumps(
        {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}
    )


def _assistant(text: str) -> str:
    return json.dumps(
        {"role": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    )


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _source(tmp_path: Path) -> CursorTranscriptSource:
    return CursorTranscriptSource(
        transcripts_dir=tmp_path / "transcripts",
        state_path=tmp_path / "state.json",
    )


def test_poll_extracts_only_user_query_content(tmp_path: Path):
    f = tmp_path / "transcripts" / "conv" / "conv.jsonl"
    _write(
        f,
        [
            _user("<timestamp>now</timestamp>\n<user_query>\nI prefer FastAPI.\n</user_query>"),
            _assistant("Sure, here is some help."),
        ],
    )
    src = _source(tmp_path)
    assert src.poll() == ["I prefer FastAPI."]


def test_poll_returns_only_new_lines(tmp_path: Path):
    f = tmp_path / "transcripts" / "conv.jsonl"
    _write(f, [_user("<user_query>first</user_query>")])
    src = _source(tmp_path)
    assert src.poll() == ["first"]
    # Nothing new yet.
    assert src.poll() == []
    # Append a new turn.
    with f.open("a", encoding="utf-8") as fh:
        fh.write(_user("<user_query>second</user_query>") + "\n")
    assert src.poll() == ["second"]


def test_poll_skips_records_without_user_query(tmp_path: Path):
    f = tmp_path / "transcripts" / "conv.jsonl"
    _write(
        f,
        [
            _user("just attached files, no query tag"),
            _assistant("<user_query>not a user role</user_query>"),
            _user("<user_query>real one</user_query>"),
        ],
    )
    assert _source(tmp_path).poll() == ["real one"]


def test_poll_handles_missing_dir(tmp_path: Path):
    assert _source(tmp_path).poll() == []


def test_poll_skips_corrupt_lines(tmp_path: Path):
    f = tmp_path / "transcripts" / "conv.jsonl"
    _write(f, ["not json", _user("<user_query>ok</user_query>")])
    assert _source(tmp_path).poll() == ["ok"]


def test_multiple_user_query_blocks_joined(tmp_path: Path):
    f = tmp_path / "transcripts" / "conv.jsonl"
    _write(f, [_user("<user_query>a</user_query> mid <user_query>b</user_query>")])
    assert _source(tmp_path).poll() == ["a\n\nb"]


def test_read_user_texts_from_file(tmp_path: Path):
    f = tmp_path / "conv.jsonl"
    _write(
        f,
        [
            _user("<user_query>first</user_query>"),
            _assistant("ignored"),
            _user("<user_query>second</user_query>"),
        ],
    )
    assert read_user_texts(f) == ["first", "second"]


def test_read_user_texts_from_dir_ignores_state(tmp_path: Path):
    d = tmp_path / "transcripts"
    _write(d / "a.jsonl", [_user("<user_query>one</user_query>")])
    _write(d / "b.jsonl", [_user("<user_query>two</user_query>")])
    # Always returns the full history, regardless of any prior listen state.
    assert read_user_texts(d) == ["one", "two"]
    assert read_user_texts(d) == ["one", "two"]


def test_read_user_texts_missing_path(tmp_path: Path):
    assert read_user_texts(tmp_path / "nope.jsonl") == []
