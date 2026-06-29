"""Domain policy tests."""

from __future__ import annotations

from fatcat.domain.models import ConversationTurn, MemoryCandidate, RawInput
from fatcat.domain.policies import (
    PrivacyPolicy,
    candidate_to_memory_item,
    drop_non_user_evidence,
    evidence_quotes_from_raw_input,
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


def _dialogue_input(*turns: ConversationTurn) -> RawInput:
    rendered = "\n\n".join(turn.content for turn in turns)
    return RawInput(content=rendered, source="import", turns=list(turns))


def test_evidence_quotes_annotate_turn_provenance():
    raw = _dialogue_input(
        ConversationTurn(id="s1:1", role="user", content="I prefer FastAPI."),
        ConversationTurn(id="s1:2", role="assistant", content="FastAPI is great."),
    )
    quotes = evidence_quotes_from_raw_input(raw, ["I prefer FastAPI."])
    assert quotes[0].turn_id == "s1:1"
    assert quotes[0].role == "user"


def test_evidence_quote_prefers_user_turn_when_text_is_shared():
    raw = _dialogue_input(
        ConversationTurn(id="s1:1", role="assistant", content="Use PostgreSQL here."),
        ConversationTurn(id="s1:2", role="user", content="Use PostgreSQL here."),
    )
    quotes = evidence_quotes_from_raw_input(raw, ["Use PostgreSQL here."])
    assert quotes[0].role == "user"
    assert quotes[0].turn_id == "s1:2"


def test_drop_non_user_evidence_removes_assistant_and_system():
    raw = _dialogue_input(
        ConversationTurn(id="s1:1", role="user", content="I like type hints."),
        ConversationTurn(id="s1:2", role="assistant", content="Type hints help a lot."),
        ConversationTurn(id="s1:3", role="system", content="You are an assistant."),
    )
    quotes = evidence_quotes_from_raw_input(
        raw,
        ["I like type hints.", "Type hints help a lot.", "You are an assistant."],
    )
    kept = drop_non_user_evidence(quotes)
    assert [quote.text for quote in kept] == ["I like type hints."]


def test_drop_non_user_evidence_keeps_unknown_role_for_legacy_inputs():
    raw = RawInput(content="I like type hints.", source="import")
    quotes = evidence_quotes_from_raw_input(raw, ["I like type hints."])
    assert quotes[0].role is None
    assert drop_non_user_evidence(quotes) == quotes
