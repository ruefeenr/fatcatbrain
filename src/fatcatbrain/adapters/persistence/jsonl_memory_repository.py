"""JSONL-backed memory repository (append-only)."""

from __future__ import annotations

from pathlib import Path

from fatcatbrain.domain.models import MemoryItem
from fatcatbrain.domain.policies import normalize_memory_content
from fatcatbrain.domain.value_objects import GLOBAL_SCOPE

from .jsonl import append_jsonl, read_jsonl


class JsonlMemoryRepository:
    """Stores confirmed memory items, one JSON object per line."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def save(self, item: MemoryItem) -> None:
        # Idempotent: never append a memory we already hold (same scope + text).
        if self.find_duplicate(item.content, item.project_id) is not None:
            return
        append_jsonl(self._path, item.model_dump(mode="json"))

    def find_duplicate(
        self, content: str, project_id: str | None
    ) -> MemoryItem | None:
        target = normalize_memory_content(content)
        for item in self.list_all():
            if (
                item.project_id == project_id
                and normalize_memory_content(item.content) == target
            ):
                return item
        return None

    def list_all(self) -> list[MemoryItem]:
        return [MemoryItem.model_validate(rec) for rec in read_jsonl(self._path)]

    def list_by_project(self, project_id: str) -> list[MemoryItem]:
        return [i for i in self.list_all() if i.project_id == project_id]

    def list_global(self) -> list[MemoryItem]:
        return [i for i in self.list_all() if i.scope == GLOBAL_SCOPE]
