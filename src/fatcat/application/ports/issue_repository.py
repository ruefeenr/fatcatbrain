"""Port for user-confirmed issues."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import Issue


@runtime_checkable
class IssueRepository(Protocol):
    """Stores and retrieves user-confirmed learning questions."""

    def save(self, issue: Issue) -> None:
        ...

    def get(self, issue_id: str) -> Issue | None:
        ...

    def list_all(self) -> list[Issue]:
        ...

    def list_by_project(self, project_id: str) -> list[Issue]:
        ...

    def list_global(self) -> list[Issue]:
        ...
