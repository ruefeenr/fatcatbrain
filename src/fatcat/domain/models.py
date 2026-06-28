"""Core domain entities for fatcat.

Entities are Pydantic models so we get validation for free, but they carry no
infrastructure concerns. ``MemoryCandidate`` (a proposal) and ``MemoryItem`` (a
confirmed memory) are deliberately separate types.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .value_objects import (
    MemoryStatus,
    MemoryType,
    ProjectStatus,
    Sensitivity,
    SourceType,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
    created_at: datetime = Field(default_factory=_utcnow)


class MemoryCandidate(BaseModel):
    """A *proposed* memory, not yet confirmed by the user.

    Lives in the inbox until reviewed. Confidence is constrained to [0, 1].
    """

    id: str = Field(default_factory=lambda: _new_id("cand"))
    content: str
    memory_type: MemoryType
    suggested_scope: str
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity = "medium"
    source_input_id: str
    project_id: str | None = None
    reason: str = ""
    reviewed: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class MemoryItem(BaseModel):
    """A *confirmed* memory. Requires an explicit scope.

    The model already supports the superseded lifecycle even though the
    promotion logic itself is out of scope for the MVP.
    """

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
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


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
