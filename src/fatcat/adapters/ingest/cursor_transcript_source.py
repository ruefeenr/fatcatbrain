"""Ingest source that watches Cursor agent chat transcripts.

Cursor stores each conversation as a ``*.jsonl`` file where every line is a JSON
object. User-authored messages have ``role == "user"`` and their hand-typed text
is wrapped in ``<user_query>...</user_query>`` (timestamps and attached files live
outside those tags, so we keep only the query content).

Only *new* lines are returned on each poll: the number of already-processed lines
per file is persisted in a small JSON state file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)


def _extract_user_text(record: dict) -> str | None:
    """Return the hand-typed user text from a transcript record, or None."""

    if record.get("role") != "user":
        return None
    message = record.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list):
        return None

    texts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(part.get("text", ""))
    joined = "\n".join(texts)

    queries = [m.group(1).strip() for m in _USER_QUERY_RE.finditer(joined)]
    queries = [q for q in queries if q]
    if not queries:
        return None
    return "\n\n".join(queries)


def read_user_texts(path: Path) -> list[str]:
    """Read every user message from a transcript file or directory (no state).

    Used for one-shot import of an existing chat history, independent of the live
    ``listen`` watch state. Returns messages oldest-first.
    """

    path = Path(path)
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.rglob("*.jsonl"))
    else:
        files = []

    texts: list[str] = []
    for file in files:
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _extract_user_text(record)
            if text:
                texts.append(text)
    return texts


class CursorTranscriptSource:
    """Polls Cursor transcript files for new user messages."""

    def __init__(self, transcripts_dir: Path, state_path: Path) -> None:
        self._dir = Path(transcripts_dir)
        self._state_path = Path(state_path)

    def describe(self) -> str:
        return f"Cursor transcripts in {self._dir}"

    def _load_state(self) -> dict[str, int]:
        if not self._state_path.exists():
            return {}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save_state(self, state: dict[str, int]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    def _transcript_files(self) -> list[Path]:
        if not self._dir.exists():
            return []
        return sorted(self._dir.rglob("*.jsonl"))

    def poll(self) -> list[str]:
        state = self._load_state()
        new_texts: list[str] = []

        for path in self._transcript_files():
            key = str(path)
            already = state.get(key, 0)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for line in lines[already:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = _extract_user_text(record)
                if text:
                    new_texts.append(text)

            state[key] = len(lines)

        self._save_state(state)
        return new_texts
