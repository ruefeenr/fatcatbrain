"""JSONL-backed inbox repository.

Candidates are appended on add. Marking a candidate as reviewed rewrites the file
in place (acceptable for the MVP's small inbox sizes).
"""

from __future__ import annotations

from pathlib import Path

from fatcat.domain.models import MemoryCandidate
from fatcat.domain.value_objects import CandidateStatus

from .jsonl import append_jsonl, read_jsonl, write_jsonl


class JsonlInboxRepository:
    """Stores memory candidates and their review status."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def add_candidates(self, candidates: list[MemoryCandidate]) -> None:
        for candidate in candidates:
            append_jsonl(self._path, candidate.model_dump(mode="json"))

    def _load_all(self) -> list[MemoryCandidate]:
        return [MemoryCandidate.model_validate(rec) for rec in read_jsonl(self._path)]

    def list_pending(
        self, session_id: str | None = None
    ) -> list[MemoryCandidate]:
        candidates = [
            candidate
            for candidate in self._load_all()
            if not candidate.reviewed
            and candidate.status in ("detected", "candidate")
        ]
        if session_id is None:
            return candidates
        return [
            candidate
            for candidate in candidates
            if candidate.session_id == session_id
        ]

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        return next(
            (
                c
                for c in self._load_all()
                if c.id == candidate_id and not c.reviewed
            ),
            None,
        )

    def mark_reviewed(
        self,
        candidate_id: str,
        status: CandidateStatus = "confirmed",
    ) -> None:
        candidates = self._load_all()
        changed = False
        for candidate in candidates:
            if candidate.id == candidate_id and not candidate.reviewed:
                candidate.reviewed = True
                candidate.status = status
                changed = True
        if changed:
            write_jsonl(
                self._path, [c.model_dump(mode="json") for c in candidates]
            )
