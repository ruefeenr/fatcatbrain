"""Use case: capture a brain dump and fill the inbox with candidates.

Flow: store the raw input -> ask the LLM for candidates -> store candidates in the
inbox. Nothing is persisted as a confirmed memory here; that requires review.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatcatbrain.application.ports import (
    InboxRepository,
    LLMPort,
    MemoryRepository,
    ProjectRepository,
    RawInputRepository,
)
from fatcatbrain.domain.models import MemoryCandidate, RawInput
from fatcatbrain.domain.value_objects import SourceType


@dataclass(frozen=True)
class CaptureResult:
    """Outcome of capturing a brain dump."""

    raw_input: RawInput
    candidates: list[MemoryCandidate]


class CaptureBrainDump:
    """Turn free text into reviewable memory candidates."""

    def __init__(
        self,
        llm: LLMPort,
        raw_input_repo: RawInputRepository,
        inbox_repo: InboxRepository,
        *,
        memory_repo: MemoryRepository | None = None,
        project_repo: ProjectRepository | None = None,
        store_raw_input: bool = True,
        min_confidence: float = 0.0,
    ) -> None:
        self._llm = llm
        self._raw_input_repo = raw_input_repo
        self._inbox_repo = inbox_repo
        self._memory_repo = memory_repo
        self._project_repo = project_repo
        self._store_raw_input = store_raw_input
        self._min_confidence = min_confidence

    def execute(
        self,
        content: str,
        *,
        project_id: str | None = None,
        source: SourceType = "brain_dump",
    ) -> CaptureResult:
        content = content.strip()
        if not content:
            raise ValueError("Cannot capture an empty brain dump.")

        raw_input = RawInput(content=content, source=source, project_id=project_id)
        if self._store_raw_input:
            self._raw_input_repo.save(raw_input)

        project = None
        if project_id and self._project_repo is not None:
            project = self._project_repo.get(project_id)

        known_context = None
        if self._memory_repo is not None:
            known_context = (
                self._memory_repo.list_by_project(project_id)
                if project_id
                else self._memory_repo.list_global()
            )

        candidates = self._llm.extract_memory_candidates(
            raw_input, project=project, known_context=known_context
        )
        # The LLM may not know the active project; make sure candidates carry it.
        for candidate in candidates:
            if candidate.project_id is None:
                candidate.project_id = project_id

        # Drop low-confidence noise (useful for passive capture).
        if self._min_confidence > 0.0:
            candidates = [
                c for c in candidates if c.confidence >= self._min_confidence
            ]

        if candidates:
            self._inbox_repo.add_candidates(candidates)

        return CaptureResult(raw_input=raw_input, candidates=candidates)
