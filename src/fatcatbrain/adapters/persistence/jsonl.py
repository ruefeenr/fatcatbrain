"""Small, robust helpers for append-only JSONL files.

Reading is intentionally lenient: a single corrupt line should not make the whole
file unreadable. Bad lines are skipped and reported via the ``on_error`` callback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON record as a line to ``path`` (creating parents)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Overwrite ``path`` with the given records (used for in-place updates)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(
    path: Path,
    *,
    on_error: Callable[[int, str, Exception], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield records from ``path``; skip (and report) malformed lines."""

    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                if on_error is not None:
                    on_error(line_no, line, exc)
                continue
