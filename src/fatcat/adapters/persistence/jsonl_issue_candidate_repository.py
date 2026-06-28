"""JSONL adapter for issue candidates awaiting curation."""

from __future__ import annotations

from pathlib import Path

from fatcat.domain.models import IssueCandidate
from fatcat.domain.policies import transition_issue_candidate
from fatcat.domain.value_objects import CandidateStatus

from .jsonl import append_jsonl, read_jsonl, write_jsonl


class JsonlIssueCandidateRepository:
    """Stores learning-question proposals with explicit curation lifecycle."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def add_candidates(self, candidates: list[IssueCandidate]) -> None:
        for candidate in candidates:
            append_jsonl(self._path, candidate.model_dump(mode="json"))

    def _load_all(self) -> list[IssueCandidate]:
        return [IssueCandidate.model_validate(record) for record in read_jsonl(self._path)]

    def list_pending(self, session_id: str | None = None) -> list[IssueCandidate]:
        candidates = [
            candidate
            for candidate in self._load_all()
            if candidate.status in ("detected", "candidate")
        ]
        if session_id is None:
            return candidates
        return [candidate for candidate in candidates if candidate.session_id == session_id]

    def list_deferred(self, session_id: str | None = None) -> list[IssueCandidate]:
        candidates = [
            candidate for candidate in self._load_all() if candidate.status == "deferred"
        ]
        if session_id is None:
            return candidates
        return [candidate for candidate in candidates if candidate.session_id == session_id]

    def get(self, candidate_id: str) -> IssueCandidate | None:
        return next(
            (candidate for candidate in self._load_all() if candidate.id == candidate_id),
            None,
        )

    def set_status(self, candidate_id: str, status: CandidateStatus) -> None:
        candidates = self._load_all()
        changed = False
        for index, candidate in enumerate(candidates):
            if candidate.id == candidate_id:
                candidates[index] = transition_issue_candidate(candidate, status)
                changed = True
                break
        if not changed:
            raise KeyError(f"No issue candidate with id {candidate_id!r}.")
        write_jsonl(
            self._path,
            [candidate.model_dump(mode="json") for candidate in candidates],
        )
