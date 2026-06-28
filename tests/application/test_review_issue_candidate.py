from __future__ import annotations

import pytest

from fatcat.application.use_cases import ReviewIssueCandidate
from fatcat.domain.models import (
    EvidenceQuote,
    Issue,
    IssueCandidate,
    MemoryItem,
    Scope,
)

from .fakes import (
    InMemoryIssueCandidateRepository,
    InMemoryIssueRepository,
    InMemoryMemoryRepository,
)


def _candidate(**overrides) -> IssueCandidate:
    base = dict(
        question="Does the user prefer batch review?",
        learning_goal="Learn when review should interrupt the user.",
        target_memory_types=["preference", "principle"],
        answer_signals=["The user postpones review until session end."],
        confidence=0.9,
        evidence=[
            EvidenceQuote(
                text="We still need to decide the review interaction.",
                source_type="brain_dump",
            )
        ],
        linked_memory_candidate_ids=["cand_memory"],
        keywords=["review", "issues"],
        observed_in_project_id="fatcat",
    )
    base.update(overrides)
    return IssueCandidate(**base)


def _setup(candidate: IssueCandidate | None = None):
    candidates = InMemoryIssueCandidateRepository()
    issues = InMemoryIssueRepository()
    memories = InMemoryMemoryRepository()
    candidate = candidate or _candidate()
    candidates.add_candidates([candidate])
    use_case = ReviewIssueCandidate(candidates, issues, memories)
    return use_case, candidates, issues, memories, candidate


def test_confirm_creates_issue_with_user_scope_and_importance():
    use_case, candidates, issues, memories, candidate = _setup()
    memories.save(
        MemoryItem(
            id="mem_1",
            content="The user curates issue candidates.",
            memory_type="principle",
            scope="project:fatcat",
            project_id="fatcat",
            source_candidate_ids=["cand_memory"],
        )
    )

    result = use_case.execute(
        candidate.id,
        "confirm",
        scope=Scope(level="project", reference_id="fatcat"),
        importance="high",
    )

    assert result.created is True
    assert result.issue == issues.list_all()[0]
    assert result.issue.linked_memory_ids == ["mem_1"]
    assert result.issue.linked_memory_candidate_ids == ["cand_memory"]
    assert result.issue.status == "observing"
    assert result.issue.target_memory_types == ["preference", "principle"]
    assert candidates.get(candidate.id).status == "confirmed"


def test_confirm_requires_explicit_scope_and_importance():
    use_case, _, _, _, candidate = _setup()

    with pytest.raises(ValueError, match="requires scope and importance"):
        use_case.execute(candidate.id, "confirm")


def test_edit_confirms_edited_issue():
    use_case, candidates, _, _, candidate = _setup()

    result = use_case.execute(
        candidate.id,
        "edit",
        scope=Scope(level="global"),
        importance="core",
        edited_title="Edited title",
        edited_description="Edited description",
    )

    assert result.issue.title == "Edited title"
    assert result.issue.description == "Edited description"
    assert candidates.get(candidate.id).status == "edited"


@pytest.mark.parametrize(
    ("decision", "status"),
    [("reject", "rejected"), ("defer", "deferred")],
)
def test_non_confirming_decisions_persist_status(decision, status):
    use_case, candidates, _, _, candidate = _setup()

    result = use_case.execute(candidate.id, decision)

    assert result.issue is None
    assert candidates.get(candidate.id).status == status


def test_merge_adds_evidence_and_keywords_to_existing_issue():
    use_case, candidates, issues, _, candidate = _setup()
    target = Issue(
        id="issue_existing",
        question="When does the user prefer review?",
        learning_goal="Learn the preferred review timing.",
        target_memory_types=["preference"],
        answer_signals=["The user chooses immediate review."],
        scope=Scope(level="project", reference_id="fatcat"),
        importance="high",
        observed_in_project_id="fatcat",
        keywords=["workflow"],
    )
    issues.save(target)

    result = use_case.execute(
        candidate.id,
        "merge",
        merge_target_id=target.id,
    )

    assert result.created is False
    assert result.issue.id == target.id
    assert result.issue.keywords == ["workflow", "review", "issues"]
    assert result.issue.source_candidate_ids == [candidate.id]
    assert candidates.get(candidate.id).status == "merged"


def test_merge_requires_existing_target():
    use_case, candidates, _, _, candidate = _setup()

    with pytest.raises(KeyError, match="missing"):
        use_case.execute(candidate.id, "merge", merge_target_id="missing")

    assert candidates.get(candidate.id).status == "candidate"
