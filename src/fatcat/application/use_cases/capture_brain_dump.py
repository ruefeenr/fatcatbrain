"""Use case: capture a brain dump and fill the inbox with candidates.

Flow: store the raw input -> ask the LLM for candidates -> route memory and issue
proposals to their inboxes. Nothing is confirmed here; that requires user review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fatcat.application.ports import (
    InboxRepository,
    IssueCandidateRepository,
    IssueRepository,
    LLMPort,
    MemoryRepository,
    ProjectRepository,
    RawInputRepository,
)
from fatcat.domain.models import IssueCandidate, MemoryCandidate, RawInput
from fatcat.domain.policies import learning_issue_has_sufficient_evidence
from fatcat.domain.value_objects import SourceType


@dataclass(frozen=True)
class CaptureResult:
    """Outcome of capturing a brain dump."""

    raw_input: RawInput
    candidates: list[MemoryCandidate]
    issue_candidates: list[IssueCandidate] = field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return len(self.candidates) + len(self.issue_candidates)


class CaptureBrainDump:
    """Turn free text into reviewable memory and issue candidates."""

    def __init__(
        self,
        llm: LLMPort,
        raw_input_repo: RawInputRepository,
        inbox_repo: InboxRepository,
        *,
        memory_repo: MemoryRepository | None = None,
        project_repo: ProjectRepository | None = None,
        issue_candidate_repo: IssueCandidateRepository | None = None,
        issue_repo: IssueRepository | None = None,
        store_raw_input: bool = True,
        min_confidence: float = 0.0,
        max_memory_candidates: int = 3,
        max_issue_candidates: int = 2,
    ) -> None:
        self._llm = llm
        self._raw_input_repo = raw_input_repo
        self._inbox_repo = inbox_repo
        self._memory_repo = memory_repo
        self._project_repo = project_repo
        self._issue_candidate_repo = issue_candidate_repo
        self._issue_repo = issue_repo
        self._store_raw_input = store_raw_input
        self._min_confidence = min_confidence
        self._max_memory_candidates = max_memory_candidates
        self._max_issue_candidates = max_issue_candidates

    def execute(
        self,
        content: str,
        *,
        project_id: str | None = None,
        source: SourceType = "brain_dump",
        session_id: str | None = None,
        source_ref: str | None = None,
    ) -> CaptureResult:
        content = content.strip()
        if not content:
            raise ValueError("Cannot capture an empty brain dump.")

        raw_input = RawInput(
            content=content,
            source=source,
            project_id=project_id,
            session_id=session_id,
            source_ref=source_ref,
        )
        if self._store_raw_input:
            self._raw_input_repo.save(raw_input)

        project = None
        if project_id and self._project_repo is not None:
            project = self._project_repo.get(project_id)

        known_context = None
        if self._memory_repo is not None:
            known_context = (
                self._memory_repo.list_global()
                + self._memory_repo.list_by_project(project_id)
                if project_id
                else self._memory_repo.list_global()
            )

        known_issues = None
        if self._issue_repo is not None:
            known_issues = (
                self._issue_repo.list_global()
                + self._issue_repo.list_by_project(project_id)
                if project_id
                else self._issue_repo.list_global()
            )

        extraction = self._llm.extract_candidates(
            raw_input,
            project=project,
            known_context=known_context,
            known_issues=known_issues,
        )
        candidates = extraction.memory_candidates
        issue_candidates = extraction.issue_candidates
        # The LLM may not know the active project; make sure candidates carry it.
        for candidate in candidates:
            if candidate.project_id is None:
                candidate.project_id = project_id
            if candidate.session_id is None:
                candidate.session_id = session_id
        for candidate in issue_candidates:
            if candidate.observed_in_project_id is None:
                candidate.observed_in_project_id = project_id
            if candidate.session_id is None:
                candidate.session_id = session_id

        issue_candidates = [
            candidate
            for candidate in issue_candidates
            if learning_issue_has_sufficient_evidence(candidate)
        ]

        # Drop low-confidence noise (useful for passive capture).
        if self._min_confidence > 0.0:
            candidates = [
                c for c in candidates if c.confidence >= self._min_confidence
            ]
            issue_candidates = [
                c for c in issue_candidates if c.confidence >= self._min_confidence
            ]

        # The LLM is instructed to rank by future value. Enforce the product's
        # low-noise review budget at the application boundary as well.
        candidates = candidates[: self._max_memory_candidates]
        issue_candidates = issue_candidates[: self._max_issue_candidates]

        if candidates:
            self._inbox_repo.add_candidates(candidates)
        if issue_candidates and self._issue_candidate_repo is not None:
            self._issue_candidate_repo.add_candidates(issue_candidates)

        return CaptureResult(
            raw_input=raw_input,
            candidates=candidates,
            issue_candidates=issue_candidates,
        )
