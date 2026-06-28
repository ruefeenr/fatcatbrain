"""Domain policies: pure rules that constrain how memories are handled."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from .models import MemoryCandidate, MemoryItem
from .value_objects import GLOBAL_SCOPE, Sensitivity, project_scope


class PrivacyPolicy(BaseModel):
    """User-controllable privacy rules for the MVP.

    The central guarantee: no automatically extracted candidate is ever persisted
    as a memory before the user reviews it.
    """

    require_review_before_persist: bool = True
    allow_raw_input_storage: bool = True
    allow_api_llm_processing: bool = False
    default_sensitivity: Sensitivity = "medium"


def candidate_to_memory_item(
    candidate: MemoryCandidate,
    *,
    scope: str | None = None,
    project_id: str | None = None,
    content: str | None = None,
    allow_export: bool = True,
) -> MemoryItem:
    """Promote a reviewed candidate into a confirmed memory item.

    ``scope`` defaults to the candidate's suggested scope. ``content`` may be
    overridden when the user edits the candidate before saving.
    """

    effective_scope = scope or candidate.suggested_scope or GLOBAL_SCOPE
    now = datetime.now(timezone.utc)
    return MemoryItem(
        content=content if content is not None else candidate.content,
        memory_type=candidate.memory_type,
        scope=effective_scope,
        project_id=project_id if project_id is not None else candidate.project_id,
        sensitivity=candidate.sensitivity,
        allow_export=allow_export,
        confidence=candidate.confidence,
        status="active",
        source_input_ids=[candidate.source_input_id],
        created_at=now,
        updated_at=now,
    )


def scope_for_project_only(project_id: str) -> str:
    """Scope string used when a user chooses 'project only' during review."""

    return project_scope(project_id)


def normalize_memory_content(content: str) -> str:
    """Canonical form for duplicate detection: lowercased, whitespace-collapsed.

    Two memories that differ only in casing or spacing are considered the same
    thought, so we don't clutter the store with near-identical entries.
    """

    return " ".join(content.lower().split())
