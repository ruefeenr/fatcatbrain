"""Domain model validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fatcat.domain.models import MemoryCandidate, MemoryItem


def _candidate(**overrides) -> MemoryCandidate:
    base = dict(
        content="User prefers FastAPI for small APIs.",
        memory_type="preference",
        suggested_scope="global",
        confidence=0.82,
        sensitivity="low",
        source_input_id="raw_123",
    )
    base.update(overrides)
    return MemoryCandidate(**base)


def test_candidate_confidence_must_be_within_unit_interval():
    with pytest.raises(ValidationError):
        _candidate(confidence=1.5)
    with pytest.raises(ValidationError):
        _candidate(confidence=-0.1)


def test_candidate_accepts_boundary_confidence():
    assert _candidate(confidence=0.0).confidence == 0.0
    assert _candidate(confidence=1.0).confidence == 1.0


def test_candidate_rejects_unknown_memory_type():
    with pytest.raises(ValidationError):
        _candidate(memory_type="banana")


def test_memory_item_requires_non_empty_scope():
    with pytest.raises(ValidationError):
        MemoryItem(
            content="something",
            memory_type="preference",
            scope="",
        )


def test_memory_item_requires_non_empty_content():
    with pytest.raises(ValidationError):
        MemoryItem(
            content="",
            memory_type="preference",
            scope="global",
        )


def test_memory_item_defaults_to_active_status():
    item = MemoryItem(content="x", memory_type="preference", scope="global")
    assert item.status == "active"
    assert item.superseded_by is None
