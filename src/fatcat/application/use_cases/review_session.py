"""Query and completion rules for session-end review."""

from __future__ import annotations

from dataclasses import dataclass

from fatcat.application.ports import (
    InboxRepository,
    IssueCandidateRepository,
    SessionRepository,
)
from fatcat.domain.models import IssueCandidate, MemoryCandidate, Session
from fatcat.domain.policies import mark_session_reviewed


@dataclass(frozen=True)
class SessionReview:
    session: Session
    memory_candidates: list[MemoryCandidate]
    issue_candidates: list[IssueCandidate]


class ReviewSession:
    """Load one session's candidates and complete it when none remain pending."""

    def __init__(
        self,
        sessions: SessionRepository,
        memory_inbox: InboxRepository,
        issue_inbox: IssueCandidateRepository,
    ) -> None:
        self._sessions = sessions
        self._memory_inbox = memory_inbox
        self._issue_inbox = issue_inbox

    def load(
        self,
        session_id: str,
        *,
        include_deferred: bool = False,
    ) -> SessionReview:
        session = self._require(session_id)
        issues = self._issue_inbox.list_pending(session_id)
        if include_deferred:
            issues += self._issue_inbox.list_deferred(session_id)
        return SessionReview(
            session=session,
            memory_candidates=self._memory_inbox.list_pending(session_id),
            issue_candidates=issues,
        )

    def complete(self, session_id: str) -> Session:
        review = self.load(session_id)
        if review.memory_candidates or review.issue_candidates:
            raise ValueError("Session still has pending candidates.")
        reviewed = mark_session_reviewed(review.session)
        self._sessions.save(reviewed)
        return reviewed

    def _require(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"No session with id {session_id!r}.")
        return session
