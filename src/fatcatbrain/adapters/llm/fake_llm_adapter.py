"""Deterministic fake LLM adapter.

Produces stable, plausible candidates from raw input without any network access.
It is the default adapter so the core loop works out of the box and is testable.

The heuristic is intentionally simple: split the input into sentence-like chunks,
keep the substantial ones, and classify each with keyword matching.
"""

from __future__ import annotations

import re

from fatcatbrain.domain.models import (
    MemoryCandidate,
    MemoryItem,
    Project,
    RawInput,
)
from fatcatbrain.domain.value_objects import MemoryType

_MIN_CHUNK_LEN = 12
_MAX_CANDIDATES = 5

_TYPE_KEYWORDS: list[tuple[MemoryType, tuple[str, ...]]] = [
    ("todo", ("todo", "need to", "should ", "must ", "let's", "i will")),
    ("open_question", ("?", "how should", "should we", "not sure", "unclear")),
    ("decision", ("decided", "we will use", "going with", "chose", "pick ")),
    ("constraint", ("must not", "cannot", "no ", "without", "limit", "only ")),
    ("preference", ("prefer", "like", "favor", "rather", "want ", "love")),
    ("tech_context", ("python", "fastapi", "django", "sqlite", "ollama", "api", "cli")),
]


def _split_chunks(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= _MIN_CHUNK_LEN]


def _classify(chunk: str) -> MemoryType:
    lowered = chunk.lower()
    for memory_type, keywords in _TYPE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return memory_type
    return "project_context"


def _confidence_for(chunk: str) -> float:
    # Deterministic pseudo-confidence based on length, clamped to a sane band.
    score = 0.55 + min(len(chunk), 120) / 300.0
    return round(min(score, 0.95), 2)


class FakeLLMAdapter:
    """A stand-in LLM that extracts candidates deterministically."""

    def extract_memory_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
    ) -> list[MemoryCandidate]:
        chunks = _split_chunks(raw_input.content)
        if not chunks:
            return []

        suggested_scope = (
            f"project:{project.id}" if project is not None else "global"
        )

        candidates: list[MemoryCandidate] = []
        for chunk in chunks[:_MAX_CANDIDATES]:
            candidates.append(
                MemoryCandidate(
                    content=chunk,
                    memory_type=_classify(chunk),
                    suggested_scope=suggested_scope,
                    confidence=_confidence_for(chunk),
                    sensitivity="low",
                    source_input_id=raw_input.id,
                    project_id=project.id if project is not None else None,
                    reason="Extracted deterministically by the FakeLLM adapter.",
                )
            )
        return candidates
