"""Memory repository that routes items by scope across two stores.

Global memories (``project_id is None``) live in a shared store visible from every
project, while project-scoped memories stay in the active project's store. This keeps
project context isolated while letting global facts follow the user everywhere.
"""

from __future__ import annotations

from fatcatbrain.domain.models import MemoryItem

from .jsonl_memory_repository import JsonlMemoryRepository


class ScopedMemoryRepository:
    """Dispatch reads/writes to a global or project store based on scope."""

    def __init__(
        self,
        global_repo: JsonlMemoryRepository,
        project_repo: JsonlMemoryRepository,
    ) -> None:
        self._global = global_repo
        self._project = project_repo

    def _target(self, project_id: str | None) -> JsonlMemoryRepository:
        return self._project if project_id else self._global

    def save(self, item: MemoryItem) -> None:
        self._target(item.project_id).save(item)

    def find_duplicate(
        self, content: str, project_id: str | None
    ) -> MemoryItem | None:
        return self._target(project_id).find_duplicate(content, project_id)

    def list_all(self) -> list[MemoryItem]:
        """Global memories plus the active project's memories."""
        return self._global.list_all() + self._project.list_all()

    def list_by_project(self, project_id: str) -> list[MemoryItem]:
        return [i for i in self._project.list_all() if i.project_id == project_id]

    def list_global(self) -> list[MemoryItem]:
        return self._global.list_all()
