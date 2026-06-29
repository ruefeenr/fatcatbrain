from __future__ import annotations

from fatcat_benchmarks.domain.models import BenchmarkCase, ConversationTurn


def test_render_can_keep_assistant_context_visibly_non_evidential():
    case = BenchmarkCase(
        id="case-1",
        suite="natural",
        turns=[
            ConversationTurn(id="u1", role="user", content="My statement."),
            ConversationTurn(id="a1", role="assistant", content="Assistant claim."),
        ],
    )

    user_only = case.render()
    full = case.render(include_assistant_context=True)

    assert "My statement." in user_only
    assert "Assistant claim." not in user_only
    assert "ASSISTANT CONTEXT 1 (NOT USER EVIDENCE)" in full
    assert case.evidence_roles("Assistant claim.") == {"assistant"}
