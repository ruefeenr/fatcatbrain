from __future__ import annotations

import json
import os
from pathlib import Path

from fatcat.adapters.ingest import CodexSessionSource, CodexTranscriptSource


def _write_rollout(path: Path, *, session_id: str, cwd: str, user_messages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "session_meta", "payload": {"id": session_id, "cwd": cwd}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context>generated</environment_context>"}],
            },
        },
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "assistant text"}},
        *[
            {"type": "event_msg", "payload": {"type": "user_message", "message": message}}
            for message in user_messages
        ],
    ]
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_latest_discovers_active_rollout_and_only_real_user_messages(tmp_path: Path):
    old_id = "11111111-1111-1111-1111-111111111111"
    new_id = "22222222-2222-2222-2222-222222222222"
    old = tmp_path / "sessions/2026/01/01" / f"rollout-old-{old_id}.jsonl"
    new = tmp_path / "sessions/2026/01/02" / f"rollout-new-{new_id}.jsonl"
    _write_rollout(old, session_id=old_id, cwd="/old", user_messages=["old"])
    _write_rollout(
        new,
        session_id=new_id,
        cwd="/workspace",
        user_messages=["First real message", "Second real message"],
    )
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    (tmp_path / "session_index.jsonl").write_text(
        json.dumps({"id": new_id, "thread_name": "FatCat workflow"}) + "\n",
        encoding="utf-8",
    )

    document = CodexSessionSource(tmp_path).latest()

    assert document is not None
    assert document.id == new_id
    assert document.title == "FatCat workflow"
    assert document.cwd == "/workspace"
    assert document.user_messages == ["First real message", "Second real message"]
    assert document.source_ref == str(new)


def test_latest_returns_none_without_rollouts(tmp_path: Path):
    assert CodexSessionSource(tmp_path).latest() is None


def test_transcript_source_returns_only_new_real_user_messages(tmp_path: Path):
    session_id = "33333333-3333-3333-3333-333333333333"
    rollout = tmp_path / "sessions" / f"rollout-test-{session_id}.jsonl"
    _write_rollout(
        rollout,
        session_id=session_id,
        cwd="/workspace",
        user_messages=["First real message"],
    )
    state = tmp_path / "watch_state.json"
    source = CodexTranscriptSource(rollout, state, title="Live thread")

    assert source.describe() == "Codex session 'Live thread'"
    assert source.poll() == ["First real message"]
    assert source.poll() == []

    with rollout.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Second real message",
                    },
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "ignore me"},
                }
            )
            + "\n"
        )

    assert source.poll() == ["Second real message"]
    assert source.poll() == []
