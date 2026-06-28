"""Tests for the ReviewMemoryCandidate use case."""

from __future__ import annotations

import pytest

from fatcat.application.use_cases import ReviewMemoryCandidate
from fatcat.domain.models import MemoryCandidate

from .fakes import InMemoryInboxRepository, InMemoryMemoryRepository


def _setup(candidate: MemoryCandidate):
    inbox = InMemoryInboxRepository()
    inbox.add_candidates([candidate])
    mem = InMemoryMemoryRepository()
    return ReviewMemoryCandidate(inbox, mem), inbox, mem


def _candidate(**overrides) -> MemoryCandidate:
    base = dict(
        content="User prefers FastAPI.",
        memory_type="preference",
        suggested_scope="global",
        confidence=0.8,
        sensitivity="low",
        source_input_id="raw_1",
    )
    base.update(overrides)
    return MemoryCandidate(**base)


def test_review_save_creates_memory_item():
    cand = _candidate()
    uc, inbox, mem = _setup(cand)
    result = uc.execute(cand.id, "save")
    assert result.memory_item is not None
    assert len(mem.items) == 1
    assert inbox.list_pending() == []


def test_review_save_skips_existing_duplicate():
    cand1 = _candidate()
    uc, inbox, mem = _setup(cand1)
    first = uc.execute(cand1.id, "save")
    assert first.created is True
    assert len(mem.items) == 1

    cand2 = _candidate(content="user PREFERS   fastapi.")
    inbox.add_candidates([cand2])
    second = uc.execute(cand2.id, "save")
    assert second.created is False
    assert second.memory_item.id == first.memory_item.id
    assert len(mem.items) == 1
    assert inbox.list_pending() == []


def test_review_discard_persists_nothing():
    cand = _candidate()
    uc, inbox, mem = _setup(cand)
    result = uc.execute(cand.id, "discard")
    assert result.memory_item is None
    assert mem.items == []
    assert inbox.list_pending() == []


def test_review_edit_uses_edited_content():
    cand = _candidate()
    uc, _, mem = _setup(cand)
    result = uc.execute(cand.id, "edit", edited_content="A clearer memory.")
    assert result.memory_item is not None
    assert mem.items[0].content == "A clearer memory."


def test_review_project_only_sets_project_scope():
    cand = _candidate(project_id="demo")
    uc, _, mem = _setup(cand)
    result = uc.execute(cand.id, "project_only")
    assert mem.items[0].scope == "project:demo"
    assert mem.items[0].project_id == "demo"


def test_review_project_only_without_project_raises():
    cand = _candidate(project_id=None)
    uc, _, _ = _setup(cand)
    with pytest.raises(ValueError):
        uc.execute(cand.id, "project_only")


def test_review_project_only_assigns_active_project_to_global_candidate():
    cand = _candidate(project_id=None)
    uc, _, mem = _setup(cand)
    result = uc.execute(cand.id, "project_only", project_id="alpha")
    assert result.created is True
    assert mem.items[0].project_id == "alpha"
    assert mem.items[0].scope == "project:alpha"


def test_review_unknown_candidate_raises():
    uc, _, _ = _setup(_candidate())
    with pytest.raises(KeyError):
        uc.execute("does_not_exist", "save")
