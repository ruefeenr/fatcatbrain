"""Inbox repository port: pending memory candidates awaiting review."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import MemoryCandidate
from fatcat.domain.value_objects import CandidateStatus


@runtime_checkable
class InboxRepository(Protocol):
    """Stores memory candidates and tracks their review status."""

    def add_candidates(self, candidates: list[MemoryCandidate]) -> None:
        ...

    def list_pending(
        self, session_id: str | None = None
    ) -> list[MemoryCandidate]:
        ...

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        ...

    def mark_reviewed(
        self,
        candidate_id: str,
        status: CandidateStatus = "confirmed",
    ) -> None:
        ...
