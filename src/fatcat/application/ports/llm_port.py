"""LLM port: structured candidate extraction behind the hexagonal boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from fatcat.domain.models import (
    Issue,
    IssueCandidate,
    MemoryCandidate,
    MemoryItem,
    Project,
    RawInput,
)


@dataclass(frozen=True)
class CandidateExtraction:
    """Validated proposals returned by any LLM adapter."""

    memory_candidates: list[MemoryCandidate] = field(default_factory=list)
    issue_candidates: list[IssueCandidate] = field(default_factory=list)


@runtime_checkable
class LLMPort(Protocol):
    """Extracts structured memory and issue candidates from raw input.

    Implementations must never return unvalidated data: the returned candidates
    are already-validated domain objects.
    """

    def extract_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
        known_issues: list[Issue] | None = None,
    ) -> CandidateExtraction:
        ...
