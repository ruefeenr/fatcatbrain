"""Use case: directly save a memory item (the low-friction ``fcb save`` path).

For clear user statements we skip the inbox: a raw input is recorded, a single
candidate is built and immediately promoted to a confirmed memory item.
"""

from __future__ import annotations

from fatcatbrain.application.ports import MemoryRepository, RawInputRepository
from fatcatbrain.domain.models import MemoryItem, RawInput
from fatcatbrain.domain.value_objects import (
    GLOBAL_SCOPE,
    MemoryType,
    Sensitivity,
    project_scope,
)


class SaveMemoryItem:
    """Persist an explicit memory item without going through review."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        raw_input_repo: RawInputRepository,
        *,
        store_raw_input: bool = True,
    ) -> None:
        self._memory_repo = memory_repo
        self._raw_input_repo = raw_input_repo
        self._store_raw_input = store_raw_input

    def execute(
        self,
        content: str,
        *,
        memory_type: MemoryType = "preference",
        project_id: str | None = None,
        sensitivity: Sensitivity = "low",
    ) -> MemoryItem:
        content = content.strip()
        if not content:
            raise ValueError("Cannot save an empty memory.")

        existing = self._memory_repo.find_duplicate(content, project_id)
        if existing is not None:
            return existing

        raw_input = RawInput(
            content=content,
            source="explicit_save",
            project_id=project_id,
        )
        if self._store_raw_input:
            self._raw_input_repo.save(raw_input)

        scope = project_scope(project_id) if project_id else GLOBAL_SCOPE
        item = MemoryItem(
            content=content,
            memory_type=memory_type,
            scope=scope,
            project_id=project_id,
            sensitivity=sensitivity,
            confidence=1.0,
            source_input_ids=[raw_input.id],
        )
        self._memory_repo.save(item)
        return item
