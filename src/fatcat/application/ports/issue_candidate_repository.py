"""Port for proposed issues awaiting explicit user review."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import IssueCandidate
from fatcat.domain.value_objects import CandidateStatus


@runtime_checkable
class IssueCandidateRepository(Protocol):
    """Stores issue proposals and their curation lifecycle."""

    def add_candidates(self, candidates: list[IssueCandidate]) -> None:
        ...

    def list_pending(self, session_id: str | None = None) -> list[IssueCandidate]:
        ...

    def list_deferred(self, session_id: str | None = None) -> list[IssueCandidate]:
        ...

    def get(self, candidate_id: str) -> IssueCandidate | None:
        ...

    def set_status(self, candidate_id: str, status: CandidateStatus) -> None:
        ...
