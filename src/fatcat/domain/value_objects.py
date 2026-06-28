"""Value objects for the fatcat domain.

These are the small, stable vocabulary types shared across entities. They are kept
as ``Literal`` aliases (cheap, JSON-friendly, validated by Pydantic) rather than
``Enum`` to stay close to the wire format used in JSONL storage.
"""

from __future__ import annotations

from typing import Literal

MemoryType = Literal[
    "preference",
    "tech_context",
    "project_context",
    "decision",
    "constraint",
    "todo",
    "open_question",
    "rationale",
    "correction",
    "rejection",
    "principle",
    "keyword",
]
"""What kind of memory a candidate/item represents.

``open_question`` remains readable for backwards compatibility with existing
JSONL stores. New LLM extraction uses ``ExtractableMemoryType`` instead: an
unresolved question belongs in the issue inbox, not in both inboxes.
"""

ExtractableMemoryType = Literal[
    "preference",
    "tech_context",
    "project_context",
    "decision",
    "constraint",
    "todo",
    "rationale",
    "correction",
    "rejection",
    "principle",
    "keyword",
]
"""Memory types the LLM may propose for new input."""

LearningMemoryType = Literal[
    "preference",
    "decision",
    "constraint",
    "rationale",
    "correction",
    "rejection",
    "principle",
]
"""Memory types that can answer a durable question about the user."""

Sensitivity = Literal["low", "medium", "high"]
"""How sensitive the content is. Influences export and review defaults."""

SourceType = Literal[
    "brain_dump",
    "explicit_save",
    "import",
    "transcript",
    "quiz",
    "interview",
    "codex",
]
"""Where a raw input originated from."""

ReviewDecision = Literal["save", "edit", "project_only", "discard"]
"""The decision a user makes about a candidate in the inbox."""

IssueReviewDecision = Literal["confirm", "edit", "merge", "reject", "defer"]
"""The richer curation choices for issue candidates."""

CandidateStatus = Literal[
    "detected",
    "candidate",
    "confirmed",
    "edited",
    "rejected",
    "merged",
    "deferred",
    "legacy_resolved",
]
"""Lifecycle of a user-curated candidate."""

Importance = Literal["low", "medium", "high", "core"]
"""User-confirmed importance of an issue."""

ScopeLevel = Literal["session", "project", "domain", "global"]
"""How broadly a memory or issue applies."""

IssueStatus = Literal[
    "confirmed",
    "observing",
    "partially_answered",
    "resolved",
    "archived",
]
"""Lifecycle of a confirmed issue."""

SessionStatus = Literal["active", "ended", "reviewed"]
"""Lifecycle of a capture session."""

MemoryStatus = Literal["active", "archived", "superseded"]
"""Lifecycle status of a confirmed memory item."""

ProjectStatus = Literal["active", "paused", "archived"]
"""Lifecycle status of a project."""

GLOBAL_SCOPE = "global"
"""Scope value used for memories that are not tied to a single project."""


def project_scope(project_id: str) -> str:
    """Build the canonical scope string for a project-bound memory."""

    return f"project:{project_id}"
