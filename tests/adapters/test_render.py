from __future__ import annotations

from rich.panel import Panel

from fatcat.adapters.cli.render import render_candidate, render_issue_candidate
from fatcat.domain.models import IssueCandidate, MemoryCandidate


def test_memory_candidate_renderer_returns_panel():
    candidate = MemoryCandidate(
        content="Prefer concise review screens.",
        memory_type="preference",
        suggested_scope="project:fatcat",
        confidence=0.9,
        source_input_id="raw_1",
        reason="Explicit preference.",
    )

    rendered = render_candidate(1, candidate)

    assert isinstance(rendered, Panel)
    assert "What I learned" in str(rendered.title)
    assert "keep" in str(rendered.subtitle).lower()
    assert "details" in str(rendered.subtitle).lower()


def test_issue_candidate_renderer_returns_panel():
    candidate = IssueCandidate(
        question="Does the user prefer batch review?",
        learning_goal="Learn when review should interrupt the user.",
        target_memory_types=["preference"],
        answer_signals=["The user asks to postpone review until session end."],
        confidence=0.8,
    )

    rendered = render_issue_candidate(1, candidate)

    assert isinstance(rendered, Panel)
    assert "What I am still unsure about" in str(rendered.title)
    assert "watch" in str(rendered.subtitle).lower()
    assert "later" in str(rendered.subtitle).lower()
