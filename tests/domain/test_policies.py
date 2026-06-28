"""Domain policy tests."""

from __future__ import annotations

from fatcat.domain.models import MemoryCandidate
from fatcat.domain.policies import (
    PrivacyPolicy,
    candidate_to_memory_item,
    scope_for_project_only,
)


def _candidate(**overrides) -> MemoryCandidate:
    base = dict(
        content="User prefers FastAPI for small APIs.",
        memory_type="preference",
        suggested_scope="global/coding",
        confidence=0.82,
        sensitivity="low",
        source_input_id="raw_123",
    )
    base.update(overrides)
    return MemoryCandidate(**base)


def test_privacy_policy_defaults_require_review():
    policy = PrivacyPolicy()
    assert policy.require_review_before_persist is True


def test_candidate_promotion_uses_suggested_scope_by_default():
    candidate = _candidate()
    item = candidate_to_memory_item(candidate)
    assert item.scope == "global/coding"
    assert item.content == candidate.content
    assert item.memory_type == "preference"
    assert item.source_input_ids == ["raw_123"]


def test_candidate_promotion_can_override_content_and_scope():
    candidate = _candidate()
    item = candidate_to_memory_item(
        candidate,
        scope="project:demo",
        project_id="demo",
        content="edited content",
    )
    assert item.scope == "project:demo"
    assert item.project_id == "demo"
    assert item.content == "edited content"


def test_promotion_falls_back_to_global_when_no_scope():
    candidate = _candidate(suggested_scope="")
    item = candidate_to_memory_item(candidate)
    assert item.scope == "global"


def test_scope_for_project_only_builds_project_scope():
    assert scope_for_project_only("demo") == "project:demo"
