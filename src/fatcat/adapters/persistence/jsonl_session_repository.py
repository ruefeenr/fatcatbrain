"""JSONL adapter for capture sessions."""

from __future__ import annotations

from pathlib import Path

from fatcat.domain.models import Session

from .jsonl import append_jsonl, read_jsonl, write_jsonl


class JsonlSessionRepository:
    """Stores sessions by id; saving an existing session updates it."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def save(self, session: Session) -> None:
        sessions = self.list_all()
        for index, existing in enumerate(sessions):
            if existing.id == session.id:
                sessions[index] = session
                write_jsonl(
                    self._path,
                    [stored.model_dump(mode="json") for stored in sessions],
                )
                return
        append_jsonl(self._path, session.model_dump(mode="json"))

    def get(self, session_id: str) -> Session | None:
        return next(
            (session for session in self.list_all() if session.id == session_id),
            None,
        )

    def list_all(self) -> list[Session]:
        return [Session.model_validate(record) for record in read_jsonl(self._path)]

    def list_by_project(self, project_id: str) -> list[Session]:
        return [session for session in self.list_all() if session.project_id == project_id]
