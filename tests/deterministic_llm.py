"""Deterministic LLM test double; never imported by production code."""

from __future__ import annotations

import re

from fatcat.application.ports import CandidateExtraction
from fatcat.domain.models import (
    Issue,
    IssueCandidate,
    MemoryCandidate,
    MemoryItem,
    Project,
    RawInput,
    Scope,
)
from fatcat.domain.policies import evidence_quotes_from_raw_input
from fatcat.domain.value_objects import MemoryType

_MIN_CHUNK_LEN = 12
_MAX_CANDIDATES = 5

_TYPE_KEYWORDS: list[tuple[MemoryType, tuple[str, ...]]] = [
    ("todo", ("todo", "need to", "should ", "must ", "let's", "i will")),
    ("decision", ("decided", "we will use", "going with", "chose", "pick ")),
    ("constraint", ("must not", "cannot", "no ", "without", "limit", "only ")),
    ("preference", ("prefer", "like", "favor", "rather", "want ", "love")),
    ("tech_context", ("python", "fastapi", "django", "sqlite", "ollama", "api", "cli")),
]


def _split_chunks(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [part.strip() for part in parts if len(part.strip()) >= _MIN_CHUNK_LEN]


def _classify(chunk: str) -> MemoryType:
    lowered = chunk.lower()
    for memory_type, keywords in _TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return memory_type
    return "project_context"


def _is_open_question(chunk: str) -> bool:
    lowered = chunk.lower()
    return any(
        marker in lowered
        for marker in ("?", "how should", "should we", "not sure", "unclear")
    )


def _is_learning_question(chunk: str) -> bool:
    """Keep test behaviour aligned with the product's user-learning boundary."""

    lowered = f" {chunk.lower()} "
    return _is_open_question(chunk) and any(
        marker in lowered
        for marker in (
            " i ",
            " my ",
            " me ",
            " user ",
            " prefer",
            " working style",
            " workflow",
        )
    )


def _confidence_for(chunk: str) -> float:
    score = 0.55 + min(len(chunk), 120) / 300.0
    return round(min(score, 0.95), 2)


class DeterministicTestLLM:
    """Small offline adapter used only to exercise application and CLI tests."""

    def extract_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
        known_issues: list[Issue] | None = None,
    ) -> CandidateExtraction:
        chunks = _split_chunks(raw_input.content)
        if not chunks:
            return CandidateExtraction()

        project_id = project.id if project is not None else raw_input.project_id
        if project_id is not None:
            suggested_scope = f"project:{project_id}"
        elif raw_input.session_id is not None:
            suggested_scope = f"session:{raw_input.session_id}"
        else:
            suggested_scope = "global"

        memories: list[MemoryCandidate] = []
        issues: list[IssueCandidate] = []
        for chunk in chunks[:_MAX_CANDIDATES]:
            if _is_open_question(chunk):
                if not _is_learning_question(chunk):
                    continue
                issues.append(
                    IssueCandidate(
                        question=chunk,
                        learning_goal=(
                            "Learn a reusable preference or working principle "
                            "from future user choices."
                        ),
                        target_memory_types=["preference", "principle"],
                        answer_signals=[
                            "The user explicitly chooses or rejects an interaction."
                        ],
                        evidence=evidence_quotes_from_raw_input(raw_input, [chunk]),
                        confidence=_confidence_for(chunk),
                        suggested_scope=Scope.from_legacy(
                            suggested_scope,
                            project_id=project_id,
                            session_id=raw_input.session_id,
                        ),
                        keywords=["open question"],
                        reason="Detected by the deterministic test double.",
                        session_id=raw_input.session_id,
                        observed_in_project_id=project_id,
                    )
                )
                continue
            memory_type = _classify(chunk)
            memory = MemoryCandidate(
                content=chunk,
                memory_type=memory_type,
                suggested_scope=suggested_scope,
                confidence=_confidence_for(chunk),
                sensitivity="low",
                source_input_id=raw_input.id,
                project_id=project_id,
                session_id=raw_input.session_id,
                reason="Extracted by the deterministic test double.",
                evidence=evidence_quotes_from_raw_input(raw_input, [chunk]),
                keywords=[memory_type],
            )
            memories.append(memory)
        return CandidateExtraction(
            memory_candidates=memories,
            issue_candidates=issues,
        )
