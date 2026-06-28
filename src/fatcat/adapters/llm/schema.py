"""Wire schema for LLM extraction output.

Both the fake and the Ollama adapter speak this JSON shape. Keeping it separate
from the domain model lets us validate untrusted LLM output before turning it into
a proper ``MemoryCandidate``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fatcat.domain.models import MemoryCandidate
from fatcat.domain.value_objects import MemoryType, Sensitivity


class LLMCandidateOut(BaseModel):
    """A single candidate as returned by an LLM."""

    content: str = Field(min_length=1)
    memory_type: MemoryType
    suggested_scope: str = "global"
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity = "medium"
    reason: str = ""

    def to_candidate(
        self, *, source_input_id: str, project_id: str | None = None
    ) -> MemoryCandidate:
        return MemoryCandidate(
            content=self.content.strip(),
            memory_type=self.memory_type,
            suggested_scope=self.suggested_scope or "global",
            confidence=self.confidence,
            sensitivity=self.sensitivity,
            source_input_id=source_input_id,
            project_id=project_id,
            reason=self.reason,
        )


class LLMExtractionOut(BaseModel):
    """Top-level JSON object the LLM is asked to return."""

    candidates: list[LLMCandidateOut] = Field(default_factory=list)
