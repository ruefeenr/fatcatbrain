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
]
"""What kind of memory a candidate/item represents."""

Sensitivity = Literal["low", "medium", "high"]
"""How sensitive the content is. Influences export and review defaults."""

SourceType = Literal["brain_dump", "explicit_save", "import", "transcript", "quiz"]
"""Where a raw input originated from."""

ReviewDecision = Literal["save", "edit", "project_only", "discard"]
"""The decision a user makes about a candidate in the inbox."""

CandidateStatus = Literal["pending", "accepted", "edited", "discarded"]
"""Lifecycle status of a candidate inside the inbox."""

MemoryStatus = Literal["active", "archived", "superseded"]
"""Lifecycle status of a confirmed memory item."""

ProjectStatus = Literal["active", "paused", "archived"]
"""Lifecycle status of a project."""

GLOBAL_SCOPE = "global"
"""Scope value used for memories that are not tied to a single project."""


def project_scope(project_id: str) -> str:
    """Build the canonical scope string for a project-bound memory."""

    return f"project:{project_id}"
