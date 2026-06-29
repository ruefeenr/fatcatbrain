"""Validated wire schema for untrusted LLM extraction output."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from fatcat.domain.models import (
    IssueCandidate,
    MemoryCandidate,
    RawInput,
    Scope,
)
from fatcat.domain.policies import (
    drop_non_user_evidence,
    evidence_quotes_from_raw_input,
)
from fatcat.domain.value_objects import (
    ExtractableMemoryType,
    Importance,
    LearningMemoryType,
    ScopeLevel,
    Sensitivity,
)


def _clean_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class LLMScopeOut(BaseModel):
    """Structured scope proposal returned by the LLM."""

    level: ScopeLevel = "global"
    reference_id: str | None = None

    def to_scope(
        self,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> Scope:
        reference_id = self.reference_id
        if self.level == "project":
            reference_id = reference_id or project_id
        elif self.level == "session":
            reference_id = reference_id or session_id
        if self.level != "global" and not reference_id:
            return Scope(level="global")
        return Scope(level=self.level, reference_id=reference_id)


ScopeWire = str | LLMScopeOut


def _to_scope(
    value: ScopeWire,
    *,
    project_id: str | None,
    session_id: str | None,
) -> Scope:
    if isinstance(value, str):
        return Scope.from_legacy(
            value or "global",
            project_id=project_id,
            session_id=session_id,
        )
    return value.to_scope(project_id=project_id, session_id=session_id)


class LLMMemoryCandidateOut(BaseModel):
    """A proposed reusable memory as returned by an LLM."""

    content: str = Field(min_length=1)
    memory_type: ExtractableMemoryType
    suggested_scope: ScopeWire = "global"
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity = "medium"
    reason: str = ""
    user_intention: str = ""
    reuse_hint: str = ""
    evidence: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    def to_candidate(
        self,
        *,
        raw_input: RawInput,
        project_id: str | None = None,
    ) -> MemoryCandidate:
        scope = _to_scope(
            self.suggested_scope,
            project_id=project_id,
            session_id=raw_input.session_id,
        )
        return MemoryCandidate(
            content=self.content.strip(),
            memory_type=self.memory_type,
            suggested_scope=scope.to_legacy(),
            confidence=self.confidence,
            sensitivity=self.sensitivity,
            source_input_id=raw_input.id,
            project_id=project_id,
            session_id=raw_input.session_id,
            reason=self.reason.strip(),
            user_intention=self.user_intention.strip(),
            reuse_hint=self.reuse_hint.strip(),
            evidence=drop_non_user_evidence(
                evidence_quotes_from_raw_input(raw_input, self.evidence)
            ),
            keywords=_clean_strings(self.keywords),
        )


class LLMIssueCandidateOut(BaseModel):
    """A proposed durable learning question about the user."""

    question: str = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    target_memory_types: list[LearningMemoryType] = Field(min_length=1)
    answer_signals: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    linked_memory_candidate_indices: list[int] = Field(default_factory=list)
    linked_memory_types: list[ExtractableMemoryType] = Field(default_factory=list)
    suggested_scope: ScopeWire | None = None
    suggested_importance: Importance | None = None
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""

    def to_candidate(
        self,
        *,
        raw_input: RawInput,
        project_id: str | None,
        memory_candidates: list[MemoryCandidate],
    ) -> IssueCandidate:
        linked_ids = [
            memory_candidates[index].id
            for index in self.linked_memory_candidate_indices
            if 0 <= index < len(memory_candidates)
        ]
        scope = (
            _to_scope(
                self.suggested_scope,
                project_id=project_id,
                session_id=raw_input.session_id,
            )
            if self.suggested_scope is not None
            else None
        )
        return IssueCandidate(
            question=self.question.strip(),
            learning_goal=self.learning_goal.strip(),
            target_memory_types=list(dict.fromkeys(self.target_memory_types)),
            answer_signals=_clean_strings(self.answer_signals),
            evidence=drop_non_user_evidence(
                evidence_quotes_from_raw_input(raw_input, self.evidence)
            ),
            linked_memory_candidate_ids=linked_ids,
            linked_memory_types=self.linked_memory_types,
            confidence=self.confidence,
            suggested_scope=scope,
            suggested_importance=self.suggested_importance,
            keywords=_clean_strings(self.keywords),
            reason=self.reason.strip(),
            session_id=raw_input.session_id,
            observed_in_project_id=project_id,
        )


# Public compatibility name for integrations importing the old wire type.
LLMCandidateOut = LLMMemoryCandidateOut


class LLMExtractionOut(BaseModel):
    """Top-level extraction object with a v1 validation alias."""

    memory_candidates: list[LLMMemoryCandidateOut] = Field(
        default_factory=list,
        validation_alias=AliasChoices("memory_candidates", "candidates"),
    )
    issue_candidates: list[LLMIssueCandidateOut] = Field(default_factory=list)
