"""Tests for the situational cat faces of the mascot."""

from __future__ import annotations

from fatcatbrain.adapters.cli.mascot import (
    FACE_CURIOUS,
    FACE_HAPPY,
    FACE_IDLE,
    FACE_SUSPICIOUS,
    MascotRenderer,
)
from fatcatbrain.domain.models import MemoryCandidate, MemoryItem


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


def test_idle_face_when_inbox_empty():
    assert MascotRenderer().inbox_empty().startswith(FACE_IDLE)


def test_happy_face_when_saved():
    item = MemoryItem(content="x", memory_type="preference", scope="global")
    assert MascotRenderer().saved(item).startswith(FACE_HAPPY)


def test_suspicious_face_for_sensitive_candidate():
    line = MascotRenderer().candidate_intro(_candidate(sensitivity="high"))
    assert line.startswith(FACE_SUSPICIOUS)
    assert "sensitive" in line.lower()


def test_project_intro_mentions_project():
    line = MascotRenderer().candidate_intro(_candidate(project_id="demo"))
    assert "demo" in line
    assert line.startswith(FACE_CURIOUS)


def test_default_intro_mentions_memory_type():
    line = MascotRenderer().candidate_intro(_candidate(memory_type="decision"))
    assert "decision" in line
    assert line.startswith(FACE_CURIOUS)
