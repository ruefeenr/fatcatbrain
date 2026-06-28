"""Project repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import Project


@runtime_checkable
class ProjectRepository(Protocol):
    """Stores and retrieves ``Project`` entities."""

    def save(self, project: Project) -> None:
        ...

    def get(self, project_id: str) -> Project | None:
        ...

    def list_all(self) -> list[Project]:
        ...
