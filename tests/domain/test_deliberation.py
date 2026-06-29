"""Tests for the IBIS/QOC deliberation ontology and learning-question rename."""

from __future__ import annotations

import pytest

from fatcat.domain.deliberation import (
    Argument,
    Criterion,
    DecisionIssue,
    DecisionIssueCandidate,
    Position,
)
from fatcat.domain.models import (
    Hypothesis,
    Issue,
    IssueCandidate,
    LearningQuestion,
    LearningQuestionCandidate,
)
from fatcat.domain.policies import (
    adopt_position,
    confirm_decision_issue,
    transition_decision_issue_candidate,
)
from fatcat.domain.models import Scope


def test_issue_aliases_point_at_learning_question():
    assert Issue is LearningQuestion
    assert IssueCandidate is LearningQuestionCandidate


def test_legacy_issue_record_still_validates_as_learning_question():
    legacy = {
        "item_type": "learning_issue",
        "question": "Does the user prefer relational databases?",
        "learning_goal": "Learn the user's database policy.",
        "scope": {"level": "global"},
        "importance": "medium",
    }
    question = LearningQuestion.model_validate(legacy)
    assert question.item_type == "learning_issue"
    assert question.hypotheses == []


def test_learning_question_carries_hypotheses():
    question = LearningQuestion(
        question="Under which conditions does the user prefer relational DBs?",
        learning_goal="Learn the user's database policy.",
        scope=Scope(level="global"),
        importance="medium",
        hypotheses=[
            Hypothesis(statement="The user prefers relational DBs for reporting.")
        ],
    )
    assert question.hypotheses[0].status == "open"


def test_decision_issue_rejects_unknown_adopted_position():
    with pytest.raises(ValueError):
        DecisionIssue(
            question="Which database should this project use?",
            scope=Scope(level="project", reference_id="demo"),
            importance="high",
            positions=[Position(id="pos_a", statement="Use PostgreSQL")],
            adopted_position_id="pos_missing",
        )


def test_decision_issue_adopted_status_requires_position():
    with pytest.raises(ValueError):
        DecisionIssue(
            question="Which database should this project use?",
            scope=Scope(level="project", reference_id="demo"),
            importance="high",
            status="adopted",
        )


def _decision_candidate(**overrides) -> DecisionIssueCandidate:
    base = dict(
        question="Which web framework should this project use?",
        positions=[Position(statement="Use FastAPI")],
        criteria=[Criterion(name="type safety")],
        arguments=[
            Argument(statement="FastAPI has strong typing support", stance="supports")
        ],
        confidence=0.8,
    )
    base.update(overrides)
    return DecisionIssueCandidate(**base)


def test_confirm_decision_issue_from_candidate():
    candidate = _decision_candidate()
    issue = confirm_decision_issue(
        candidate,
        scope=Scope(level="project", reference_id="demo"),
        importance="high",
    )
    assert issue.item_type == "decision_issue"
    assert issue.criteria[0].name == "type safety"
    assert issue.source_candidate_ids == [candidate.id]
    assert issue.status == "open"


def test_adopt_position_marks_decision_and_rejects_others():
    issue = DecisionIssue(
        question="Which web framework should this project use?",
        scope=Scope(level="project", reference_id="demo"),
        importance="high",
        positions=[
            Position(id="pos_fastapi", statement="Use FastAPI"),
            Position(id="pos_flask", statement="Use Flask"),
        ],
    )
    decided = adopt_position(issue, "pos_fastapi", rationale="Values type safety.")
    assert decided.status == "adopted"
    assert decided.adopted_position_id == "pos_fastapi"
    statuses = {p.id: p.status for p in decided.positions}
    assert statuses == {"pos_fastapi": "adopted", "pos_flask": "rejected"}
    assert decided.rationale == "Values type safety."


def test_adopt_position_rejects_unknown_id():
    issue = DecisionIssue(
        question="Which web framework should this project use?",
        scope=Scope(level="project", reference_id="demo"),
        importance="high",
        positions=[Position(id="pos_fastapi", statement="Use FastAPI")],
    )
    with pytest.raises(ValueError):
        adopt_position(issue, "pos_unknown")


def test_transition_decision_issue_candidate_enforces_lifecycle():
    candidate = _decision_candidate()
    confirmed = transition_decision_issue_candidate(candidate, "confirmed")
    assert confirmed.status == "confirmed"
    assert confirmed.requires_user_review is False
    with pytest.raises(ValueError):
        transition_decision_issue_candidate(confirmed, "candidate")
