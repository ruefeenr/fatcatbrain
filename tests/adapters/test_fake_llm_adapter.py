"""Tests for the deterministic FakeLLM adapter."""

from __future__ import annotations

from fatcatbrain.adapters.llm import FakeLLMAdapter
from fatcatbrain.domain.models import Project, RawInput


def _raw(content: str) -> RawInput:
    return RawInput(content=content, source="brain_dump")


def test_fake_llm_returns_candidates_for_sentences():
    adapter = FakeLLMAdapter()
    raw = _raw(
        "I prefer FastAPI for small APIs. We decided to use SQLite later. "
        "Keep storage flexible."
    )
    candidates = adapter.extract_memory_candidates(raw)
    assert len(candidates) == 3
    assert all(c.source_input_id == raw.id for c in candidates)
    assert all(0.0 <= c.confidence <= 1.0 for c in candidates)


def test_fake_llm_is_deterministic():
    adapter = FakeLLMAdapter()
    raw = _raw("I prefer FastAPI for small APIs.")
    first = adapter.extract_memory_candidates(raw)
    second = adapter.extract_memory_candidates(raw)
    assert [c.content for c in first] == [c.content for c in second]
    assert [c.confidence for c in first] == [c.confidence for c in second]


def test_fake_llm_classifies_preference():
    adapter = FakeLLMAdapter()
    candidates = adapter.extract_memory_candidates(
        _raw("I prefer opinionated MVP recommendations.")
    )
    assert candidates[0].memory_type == "preference"


def test_fake_llm_uses_project_scope_when_project_given():
    adapter = FakeLLMAdapter()
    project = Project(id="demo", name="Demo")
    candidates = adapter.extract_memory_candidates(
        _raw("Keep the architecture lightweight."), project=project
    )
    assert candidates[0].suggested_scope == "project:demo"
    assert candidates[0].project_id == "demo"


def test_fake_llm_ignores_trivial_input():
    adapter = FakeLLMAdapter()
    assert adapter.extract_memory_candidates(_raw("ok")) == []
