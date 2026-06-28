from __future__ import annotations

import pytest
from pydantic import ValidationError

from fatcat.domain.models import (
    EvidenceQuote,
    IssueCandidate,
    MemoryCandidate,
    RawInput,
    Scope,
    Session,
)
from fatcat.domain.policies import (
    candidate_to_memory_item,
    confirm_issue,
    evidence_quotes_from_raw_input,
    transition_issue_candidate,
)


def test_scope_roundtrips_legacy_values():
    scope = Scope.from_legacy("domain:software-architecture")

    assert scope.level == "domain"
    assert scope.reference_id == "software-architecture"
    assert scope.to_legacy() == "domain:software-architecture"


def test_non_global_scope_requires_reference():
    with pytest.raises(ValidationError):
        Scope(level="project")


def test_global_scope_rejects_reference():
    with pytest.raises(ValidationError):
        Scope(level="global", reference_id="anything")


def test_v1_reviewed_candidate_gets_honest_legacy_status():
    candidate = MemoryCandidate.model_validate(
        {
            "content": "Prefer explicit review.",
            "memory_type": "preference",
            "suggested_scope": "global",
            "confidence": 0.9,
            "source_input_id": "raw_old",
            "reviewed": True,
        }
    )

    assert candidate.schema_version == 2
    assert candidate.status == "legacy_resolved"


def test_candidate_promotion_preserves_reuse_metadata():
    evidence = EvidenceQuote(
        text="Das soll auch später gelten.",
        source_type="interview",
        source_input_id="raw_1",
        session_id="session_1",
    )
    candidate = MemoryCandidate(
        content="The choice applies to future sessions.",
        memory_type="principle",
        suggested_scope="project:fatcat",
        confidence=0.9,
        source_input_id="raw_1",
        project_id="fatcat",
        session_id="session_1",
        user_intention="Preserve a durable working rule.",
        reuse_hint="When another session makes the same design choice.",
        evidence=[evidence],
        keywords=["review", "agency"],
    )

    item = candidate_to_memory_item(candidate)

    assert item.scope_ref == Scope(level="project", reference_id="fatcat")
    assert item.session_ids == ["session_1"]
    assert item.user_intention == candidate.user_intention
    assert item.evidence == [evidence]
    assert item.keywords == ["review", "agency"]


def test_confirm_issue_requires_scope_and_importance_from_user_review():
    evidence = EvidenceQuote(
        text="FatCat soll Issues nur vorschlagen.",
        source_type="brain_dump",
        session_id="session_1",
    )
    candidate = IssueCandidate(
        title="How should issues be confirmed?",
        description="FatCat proposes candidates and the user decides.",
        confidence=0.87,
        evidence=[evidence],
        keywords=["issues", "curation"],
        project_id="fatcat",
        session_id="session_1",
    )

    issue = confirm_issue(
        candidate,
        scope=Scope(level="project", reference_id="fatcat"),
        importance="high",
        linked_memory_ids=["mem_1"],
    )

    assert issue.confirmed_by_user is True
    assert issue.importance == "high"
    assert issue.scope.level == "project"
    assert issue.source_candidate_ids == [candidate.id]
    assert issue.linked_memory_ids == ["mem_1"]
    assert issue.evidence == [evidence]


def test_learning_issue_separates_observation_from_applicability():
    candidate = IssueCandidate(
        question="Does the user prefer batch review?",
        learning_goal="Learn when review should interrupt the user.",
        target_memory_types=["preference", "principle"],
        answer_signals=["The user postpones review until session end."],
        confidence=0.9,
        observed_in_project_id="fatcat",
        suggested_scope=Scope(
            level="domain",
            reference_id="software-development",
        ),
    )

    issue = confirm_issue(
        candidate,
        scope=candidate.suggested_scope,
        importance="high",
    )

    assert issue.status == "observing"
    assert issue.item_type == "learning_issue"
    assert issue.observed_in_project_id == "fatcat"
    assert issue.scope == Scope(
        level="domain",
        reference_id="software-development",
    )
    assert issue.target_memory_types == ["preference", "principle"]
    assert issue.answer_signals == candidate.answer_signals


def test_legacy_issue_shape_is_readable_but_serializes_learning_names():
    candidate = IssueCandidate.model_validate(
        {
            "title": "Legacy question",
            "description": "Legacy description",
            "confidence": 0.8,
            "project_id": "fatcat",
        }
    )

    stored = candidate.model_dump(mode="json")

    assert candidate.question == "Legacy question"
    assert candidate.learning_goal == "Legacy description"
    assert candidate.observed_in_project_id == "fatcat"
    assert "question" in stored and "title" not in stored
    assert "learning_goal" in stored and "description" not in stored
    assert "observed_in_project_id" in stored and "project_id" not in stored


def test_rejected_issue_candidate_cannot_be_confirmed():
    candidate = IssueCandidate(
        title="Rejected",
        description="This proposal was rejected.",
        confidence=0.7,
        status="rejected",
    )

    with pytest.raises(ValueError, match="Cannot confirm"):
        confirm_issue(
            candidate,
            scope=Scope(level="global"),
            importance="low",
        )


def test_issue_candidate_transitions_are_domain_rules():
    candidate = IssueCandidate(
        title="Review flow",
        description="Decide how review works.",
        confidence=0.8,
    )

    deferred = transition_issue_candidate(candidate, "deferred")
    rejected = transition_issue_candidate(deferred, "rejected")

    assert candidate.status == "candidate"
    assert deferred.status == "deferred"
    assert deferred.requires_user_review is True
    assert rejected.requires_user_review is False
    with pytest.raises(ValueError, match="Cannot transition"):
        transition_issue_candidate(rejected, "candidate")


def test_evidence_policy_keeps_only_verbatim_source_quotes():
    raw = RawInput(
        content="The user confirms every issue.",
        source="transcript",
        session_id="session_1",
        source_ref="chat.jsonl",
    )

    evidence = evidence_quotes_from_raw_input(
        raw,
        [
            "The user confirms every issue.",
            "The user confirms every issue.",
            "A paraphrase that is not in the source.",
        ],
    )

    assert len(evidence) == 1
    assert evidence[0].source_input_id == raw.id
    assert evidence[0].session_id == "session_1"
    assert evidence[0].source_ref == "chat.jsonl"


def test_session_is_a_first_class_capture_boundary():
    session = Session(source="interview", project_id="fatcat", source_ref="cli")

    assert session.schema_version == 2
    assert session.status == "active"
    assert session.project_id == "fatcat"
