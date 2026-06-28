"""JSONL-backed raw input repository (append-only)."""

from __future__ import annotations

from pathlib import Path

from fatcat.domain.models import RawInput

from .jsonl import append_jsonl, read_jsonl


class JsonlRawInputRepository:
    """Stores raw user inputs, one JSON object per line."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def save(self, raw_input: RawInput) -> None:
        append_jsonl(self._path, raw_input.model_dump(mode="json"))

    def list_all(self) -> list[RawInput]:
        return [RawInput.model_validate(rec) for rec in read_jsonl(self._path)]

    def get(self, raw_input_id: str) -> RawInput | None:
        return next((r for r in self.list_all() if r.id == raw_input_id), None)
