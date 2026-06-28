"""LLM port: the interface use cases use to extract memory candidates."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcat.domain.models import MemoryCandidate, MemoryItem, Project, RawInput


@runtime_checkable
class LLMPort(Protocol):
    """Extracts structured memory candidates from raw input.

    Implementations must never return unvalidated data: the returned candidates
    are already-validated domain objects.
    """

    def extract_memory_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
    ) -> list[MemoryCandidate]:
        ...
