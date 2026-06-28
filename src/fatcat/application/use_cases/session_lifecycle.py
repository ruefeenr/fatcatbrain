"""Application service for capture-session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from fatcat.application.ports import SessionRepository
from fatcat.domain.models import Session
from fatcat.domain.policies import end_session, mark_session_reviewed
from fatcat.domain.value_objects import SourceType


class SessionLifecycle:
    """Start, end and complete reviewable capture sessions."""

    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    def start(
        self,
        *,
        source: SourceType,
        project_id: str | None,
        source_ref: str | None = None,
        title: str = "",
        session_id: str | None = None,
    ) -> Session:
        values = {
            "source": source,
            "project_id": project_id,
            "source_ref": source_ref,
            "title": title,
        }
        if session_id is not None:
            values["id"] = session_id
        session = Session.model_validate(values)
        self._repository.save(session)
        return session

    def end(self, session_id: str) -> Session:
        session = self._require(session_id)
        ended = end_session(session)
        self._repository.save(ended)
        return ended

    def mark_reviewed(self, session_id: str) -> Session:
        session = self._require(session_id)
        reviewed = mark_session_reviewed(session)
        self._repository.save(reviewed)
        return reviewed

    def latest_unreviewed(self, project_id: str | None) -> Session | None:
        sessions = (
            self._repository.list_by_project(project_id)
            if project_id is not None
            else self._repository.list_all()
        )
        pending = [session for session in sessions if session.status == "ended"]
        return max(pending, key=lambda session: session.started_at, default=None)

    def _require(self, session_id: str) -> Session:
        session = self._repository.get(session_id)
        if session is None:
            raise KeyError(f"No session with id {session_id!r}.")
        return session
