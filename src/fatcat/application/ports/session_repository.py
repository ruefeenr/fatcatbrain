"""Port for bounded capture sessions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import Session


@runtime_checkable
class SessionRepository(Protocol):
    """Persists sessions independently of their source adapter."""

    def save(self, session: Session) -> None:
        ...

    def get(self, session_id: str) -> Session | None:
        ...

    def list_all(self) -> list[Session]:
        ...

    def list_by_project(self, project_id: str) -> list[Session]:
        ...
