"""Core domain entities for fatcat.

Entities are Pydantic models so we get validation for free, but they carry no
infrastructure concerns. ``MemoryCandidate`` (a proposal) and ``MemoryItem`` (a
confirmed memory) are deliberately separate types.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from .value_objects import (
    CandidateStatus,
    HypothesisStatus,
    Importance,
    IssueStatus,
    LearningMemoryType,
    MemoryStatus,
    MemoryType,
    ProjectStatus,
    ScopeLevel,
    Sensitivity,
    SessionStatus,
    SourceType,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Scope(BaseModel):
    """A typed applicability boundary for memories and issues."""

    level: ScopeLevel
    reference_id: str | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "Scope":
        if self.level == "global" and self.reference_id is not None:
            raise ValueError("Global scope cannot have a reference_id.")
        if self.level != "global" and not self.reference_id:
            raise ValueError(f"{self.level.title()} scope requires a reference_id.")
        return self

    @classmethod
    def from_legacy(
        cls,
        value: str,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> "Scope":
        """Convert the v1 string representation without changing stored data."""

        if value == "global":
            return cls(level="global")
        if ":" in value:
            level, reference_id = value.split(":", 1)
            if level in ("session", "project", "domain") and reference_id:
                return cls(level=level, reference_id=reference_id)
        if session_id:
            return cls(level="session", reference_id=session_id)
        if project_id:
            return cls(level="project", reference_id=project_id)
        return cls(level="global")

    def to_legacy(self) -> str:
        """Return the v1 scope string used by the current CLI and stores."""

        if self.level == "global":
            return "global"
        return f"{self.level}:{self.reference_id}"


class ConversationTurn(BaseModel):
    """One role-attributed turn of a multi-message raw input.

    Optional structured provenance for inputs that arrive as a dialogue. When
    present, evidence can be traced back to the turn it came from, which lets the
    domain enforce that only user-authored turns justify a user memory.
    """

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    language: str | None = None


class EvidenceQuote(BaseModel):
    """A minimal source excerpt supporting a candidate or confirmed item."""

    text: str = Field(min_length=1)
    source_type: SourceType
    source_input_id: str | None = None
    source_ref: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    role: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Project(BaseModel):
    """A project is a first-class context boundary for memories."""

    id: str = Field(default_factory=lambda: _new_id("proj"))
    name: str
    description: str | None = None
    status: ProjectStatus = "active"
    tags: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class RawInput(BaseModel):
    """The unprocessed text a user provided, kept for traceability."""

    id: str = Field(default_factory=lambda: _new_id("raw"))
    content: str
    source: SourceType
    project_id: str | None = None
    session_id: str | None = None
    source_ref: str | None = None
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class MemoryCandidate(BaseModel):
    """A *proposed* memory, not yet confirmed by the user.

    Lives in the inbox until reviewed. Confidence is constrained to [0, 1].
    """

    schema_version: int = 2
    id: str = Field(default_factory=lambda: _new_id("cand"))
    content: str
    memory_type: MemoryType
    suggested_scope: str
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity = "medium"
    source_input_id: str
    project_id: str | None = None
    session_id: str | None = None
    reason: str = ""
    user_intention: str = ""
    reuse_hint: str = ""
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status: CandidateStatus = "candidate"
    reviewed: bool = False
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_status(cls, data):
        if isinstance(data, dict) and "status" not in data and data.get("reviewed"):
            data = {**data, "status": "legacy_resolved"}
        return data

    @property
    def scope_ref(self) -> Scope:
        return Scope.from_legacy(
            self.suggested_scope,
            project_id=self.project_id,
            session_id=self.session_id,
        )


class MemoryItem(BaseModel):
    """A *confirmed* memory. Requires an explicit scope.

    The model already supports the superseded lifecycle even though the
    promotion logic itself is out of scope for the MVP.
    """

    schema_version: int = 2
    id: str = Field(default_factory=lambda: _new_id("mem"))
    content: str = Field(min_length=1)
    memory_type: MemoryType
    scope: str = Field(min_length=1)
    project_id: str | None = None
    sensitivity: Sensitivity = "medium"
    allow_export: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: MemoryStatus = "active"
    superseded_by: str | None = None
    source_input_ids: list[str] = Field(default_factory=list)
    source_candidate_ids: list[str] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)
    user_intention: str = ""
    reuse_hint: str = ""
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def scope_ref(self) -> Scope:
        return Scope.from_legacy(self.scope, project_id=self.project_id)


class Hypothesis(BaseModel):
    """A tentative answer to a learning question, tested against user evidence.

    Hypotheses make a learning question's deliberation explicit: instead of one
    flat question, FatCat can track several candidate answers and the evidence
    that supports or refutes each over time.
    """

    id: str = Field(default_factory=lambda: _new_id("hyp"))
    statement: str = Field(min_length=1)
    status: HypothesisStatus = "open"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class LearningQuestionCandidate(BaseModel):
    """A proposed learning question about the user, awaiting curation.

    The project is where the question was observed; ``suggested_scope`` describes
    where its eventual answer may apply. Those are intentionally separate.
    """

    schema_version: int = 3
    item_type: Literal["learning_issue_candidate"] = "learning_issue_candidate"
    id: str = Field(default_factory=lambda: _new_id("issue_cand"))
    question: str = Field(
        min_length=1,
        validation_alias=AliasChoices("question", "title"),
    )
    learning_goal: str = Field(
        min_length=1,
        validation_alias=AliasChoices("learning_goal", "description"),
    )
    target_memory_types: list[LearningMemoryType] = Field(default_factory=list)
    answer_signals: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    linked_memory_candidate_ids: list[str] = Field(default_factory=list)
    linked_memory_types: list[MemoryType] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: CandidateStatus = "candidate"
    suggested_scope: Scope | None = None
    suggested_importance: Importance | None = None
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""
    session_id: str | None = None
    observed_in_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("observed_in_project_id", "project_id"),
    )
    requires_user_review: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def title(self) -> str:
        """Compatibility name used by older callers and CLI code."""

        return self.question

    @property
    def description(self) -> str:
        """Compatibility name for the former generic description."""

        return self.learning_goal

    @property
    def project_id(self) -> str | None:
        """Compatibility name; project id is observation provenance only."""

        return self.observed_in_project_id


class LearningQuestion(BaseModel):
    """A user-confirmed learning question being observed over time."""

    schema_version: int = 3
    item_type: Literal["learning_issue"] = "learning_issue"
    id: str = Field(default_factory=lambda: _new_id("issue"))
    question: str = Field(
        min_length=1,
        validation_alias=AliasChoices("question", "title"),
    )
    learning_goal: str = Field(
        min_length=1,
        validation_alias=AliasChoices("learning_goal", "description"),
    )
    target_memory_types: list[LearningMemoryType] = Field(default_factory=list)
    answer_signals: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    status: IssueStatus = "observing"
    scope: Scope
    importance: Importance
    confirmed_by_user: bool = True
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    linked_memory_ids: list[str] = Field(default_factory=list)
    linked_memory_candidate_ids: list[str] = Field(default_factory=list)
    answer_candidate_ids: list[str] = Field(default_factory=list)
    resolved_by_memory_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_candidate_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    observed_in_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("observed_in_project_id", "project_id"),
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def title(self) -> str:
        return self.question

    @property
    def description(self) -> str:
        return self.learning_goal

    @property
    def project_id(self) -> str | None:
        """Compatibility name; applicability is represented by ``scope``."""

        return self.observed_in_project_id


# Backward-compatible names. ``Issue`` was renamed to ``LearningQuestion`` to
# distinguish FatCat's meta question about the user from an IBIS ``DecisionIssue``
# (see fatcat.domain.deliberation). Stored ``item_type`` values are unchanged.
Issue = LearningQuestion
IssueCandidate = LearningQuestionCandidate


class Session(BaseModel):
    """A bounded capture period whose candidates can be reviewed together."""

    schema_version: int = 2
    id: str = Field(default_factory=lambda: _new_id("session"))
    source: SourceType
    status: SessionStatus = "active"
    title: str = ""
    project_id: str | None = None
    source_ref: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    reviewed_at: datetime | None = None


class ContextPack(BaseModel):
    """A curated, compact context bundle for an agent or LLM.

    Defined here for forward-compatibility; rich export is a later phase.
    """

    project_id: str | None = None
    project_summary: str = ""
    goals: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
