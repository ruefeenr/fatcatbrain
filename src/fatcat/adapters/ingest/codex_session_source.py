"""Read user-authored messages from local Codex Desktop rollout sessions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fatcat.application.ports.conversation_session_source import (
    ConversationSessionDocument,
)


class CodexSessionSource:
    """Discover the most recently written Codex rollout without reading tool logs."""

    def __init__(self, codex_home: Path | None = None) -> None:
        self._home = Path(codex_home or (Path.home() / ".codex"))

    def latest(self) -> ConversationSessionDocument | None:
        files = list((self._home / "sessions").rglob("rollout-*.jsonl"))
        if not files:
            return None
        path = max(files, key=lambda candidate: candidate.stat().st_mtime)
        session_id = path.stem.rsplit("-", 5)[-5:]
        # UUIDs contain five groups; recover them from the filename suffix.
        external_id = "-".join(session_id)
        titles = self._load_titles()
        messages: list[str] = []
        cwd: str | None = None

        for record in _read_jsonl(path):
            record_type = record.get("type")
            payload = record.get("payload") or {}
            if record_type == "session_meta":
                external_id = str(payload.get("id") or external_id)
                cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else cwd
                continue
            message = _extract_user_message(record)
            if message:
                messages.append(message)

        return ConversationSessionDocument(
            id=external_id,
            title=titles.get(external_id, "Untitled Codex session"),
            source_ref=str(path),
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            user_messages=messages,
            cwd=cwd,
        )

    def _load_titles(self) -> dict[str, str]:
        titles: dict[str, str] = {}
        for record in _read_jsonl(self._home / "session_index.jsonl"):
            session_id = record.get("id")
            title = record.get("thread_name")
            if isinstance(session_id, str) and isinstance(title, str):
                titles[session_id] = title
        return titles


class CodexTranscriptSource:
    """Poll one Codex rollout for newly appended user-authored messages."""

    def __init__(self, rollout_path: Path, state_path: Path, title: str = "") -> None:
        self._path = Path(rollout_path)
        self._state_path = Path(state_path)
        self._title = title or self._path.stem

    def describe(self) -> str:
        return f"Codex session '{self._title}'"

    def _load_state(self) -> dict[str, int]:
        if not self._state_path.exists():
            return {}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): int(value) for key, value in data.items()}

    def _save_state(self, state: dict[str, int]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def poll(self) -> list[str]:
        state = self._load_state()
        key = str(self._path)
        already = state.get(key, 0)
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        messages: list[str] = []
        for line in lines[already:]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            message = _extract_user_message(record)
            if message:
                messages.append(message)

        state[key] = len(lines)
        self._save_state(state)
        return messages


def _extract_user_message(record: dict) -> str | None:
    """Return only a real Codex ``event_msg/user_message`` payload."""

    payload = record.get("payload") or {}
    if (
        record.get("type") != "event_msg"
        or payload.get("type") != "user_message"
        or not isinstance(payload.get("message"), str)
    ):
        return None
    return payload["message"].strip() or None


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record
