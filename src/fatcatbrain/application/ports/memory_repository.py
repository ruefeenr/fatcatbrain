"""Memory repository port: persistence of confirmed memory items."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcatbrain.domain.models import MemoryItem


@runtime_checkable
class MemoryRepository(Protocol):
    """Stores and retrieves confirmed ``MemoryItem`` objects."""

    def save(self, item: MemoryItem) -> None:
        ...

    def find_duplicate(
        self, content: str, project_id: str | None
    ) -> MemoryItem | None:
        """Return an existing item with the same normalized content and scope."""
        ...

    def list_by_project(self, project_id: str) -> list[MemoryItem]:
        ...

    def list_global(self) -> list[MemoryItem]:
        ...

    def list_all(self) -> list[MemoryItem]:
        ...
