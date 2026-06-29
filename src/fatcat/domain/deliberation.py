"""IBIS/QOC deliberation ontology: decision issues the user worked through.

This is the curated semantic backbone for design rationale. A
:class:`DecisionIssue` is a question the *user* actually deliberated (unlike a
:class:`fatcat.domain.models.LearningQuestion`, which is FatCat's meta question
about the user). Positions are candidate answers, criteria are the dimensions
used to judge them (QOC), and arguments link the two with a stance. Design
rationale is later derived from this graph; it is not stored separately.

See docs/adr/0001-deliberation-ontology.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import EvidenceQuote, Scope
from .value_objects import (
    ArgumentStance,
    CandidateStatus,
    DecisionStatus,
    Importance,
    PositionStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Criterion(BaseModel):
    """A QOC criterion: a dimension used to judge positions.

    Criteria are the bridge from a single project decision to a durable user
    preference (e.g. *type safety* behind "Use FastAPI").
    """

    id: str = Field(default_factory=lambda: _new_id("crit"))
    name: str = Field(min_length=1)
    description: str = ""
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Position(BaseModel):
    """A candidate answer to a decision issue (e.g. "Use FastAPI")."""

    id: str = Field(default_factory=lambda: _new_id("pos"))
    statement: str = Field(min_length=1)
    status: PositionStatus = "proposed"
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Argument(BaseModel):
    """A reason that supports or opposes a position, optionally via a criterion."""

    id: str = Field(default_factory=lambda: _new_id("arg"))
    statement: str = Field(min_length=1)
    stance: ArgumentStance
    position_id: str | None = None
    criterion_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class DecisionIssueCandidate(BaseModel):
    """A proposed decision issue awaiting user curation."""

    schema_version: int = 1
    item_type: Literal["decision_issue_candidate"] = "decision_issue_candidate"
    id: str = Field(default_factory=lambda: _new_id("decision_cand"))
    question: str = Field(min_length=1)
    positions: list[Position] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    arguments: list[Argument] = Field(default_factory=list)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: CandidateStatus = "candidate"
    suggested_scope: Scope | None = None
    suggested_importance: Importance | None = None
    reason: str = ""
    # Criteria can seed a learning question about the user's standing preference.
    linked_learning_question_candidate_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    observed_in_project_id: str | None = None
    requires_user_review: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class DecisionIssue(BaseModel):
    """A user-confirmed IBIS issue with positions, criteria, and arguments."""

    schema_version: int = 1
    item_type: Literal["decision_issue"] = "decision_issue"
    id: str = Field(default_factory=lambda: _new_id("decision"))
    question: str = Field(min_length=1)
    status: DecisionStatus = "open"
    scope: Scope
    importance: Importance
    positions: list[Position] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    arguments: list[Argument] = Field(default_factory=list)
    adopted_position_id: str | None = None
    rationale: str = ""
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    linked_learning_question_ids: list[str] = Field(default_factory=list)
    source_candidate_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    observed_in_project_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def validate_adopted_position(self) -> "DecisionIssue":
        if self.adopted_position_id is not None and not any(
            position.id == self.adopted_position_id for position in self.positions
        ):
            raise ValueError(
                "adopted_position_id must reference one of the issue's positions."
            )
        if self.status == "adopted" and self.adopted_position_id is None:
            raise ValueError("An adopted decision issue requires an adopted position.")
        return self
