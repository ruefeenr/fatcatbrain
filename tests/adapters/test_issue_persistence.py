from __future__ import annotations

import json

from fatcat.adapters.persistence import (
    JsonlInboxRepository,
    JsonlIssueCandidateRepository,
    JsonlIssueRepository,
    JsonlMemoryRepository,
    JsonlSessionRepository,
    ScopedIssueRepository,
)
from fatcat.domain.models import Issue, IssueCandidate, Scope, Session


def _candidate(*, session_id: str = "session_1") -> IssueCandidate:
    return IssueCandidate(
        question="Does the user prefer batch review?",
        learning_goal="Learn when review should interrupt the user.",
        target_memory_types=["preference"],
        answer_signals=["The user postpones review until session end."],
        confidence=0.9,
        session_id=session_id,
    )


def test_issue_candidate_repository_tracks_pending_and_deferred(tmp_path):
    repo = JsonlIssueCandidateRepository(tmp_path / "issue_inbox.jsonl")
    first = _candidate()
    second = _candidate(session_id="session_2")
    repo.add_candidates([first, second])

    stored = json.loads((tmp_path / "issue_inbox.jsonl").read_text().splitlines()[0])
    assert stored["item_type"] == "learning_issue_candidate"
    assert stored["question"] == first.question
    assert stored["learning_goal"] == first.learning_goal
    assert "title" not in stored and "description" not in stored

    assert repo.list_pending(session_id="session_1") == [first]

    repo.set_status(first.id, "deferred")

    assert repo.list_pending(session_id="session_1") == []
    assert repo.list_deferred(session_id="session_1")[0].id == first.id
    assert repo.get(first.id).requires_user_review is True

    repo.set_status(first.id, "rejected")
    assert repo.list_deferred(session_id="session_1") == []
    assert repo.get(first.id).requires_user_review is False


def test_issue_candidate_repository_rejects_unknown_id(tmp_path):
    repo = JsonlIssueCandidateRepository(tmp_path / "issue_inbox.jsonl")

    try:
        repo.set_status("missing", "rejected")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected a missing candidate to raise KeyError.")


def test_scoped_issue_repository_routes_and_updates(tmp_path):
    global_repo = JsonlIssueRepository(tmp_path / "global.jsonl")
    project_repo = JsonlIssueRepository(tmp_path / "project.jsonl")
    repo = ScopedIssueRepository(global_repo, project_repo)
    global_issue = Issue(
        title="Global review principle",
        description="The user confirms long-lived memories.",
        scope=Scope(level="global"),
        importance="core",
    )
    project_issue = Issue(
        title="FatCat issue model",
        description="Issues are first-class entities.",
        scope=Scope(level="project", reference_id="fatcat"),
        importance="high",
        project_id="fatcat",
    )
    domain_issue = Issue(
        question="How does the user evaluate storage trade-offs?",
        learning_goal="Learn a reusable technical decision principle.",
        target_memory_types=["principle", "rationale"],
        answer_signals=["The user explains why one storage model is rejected."],
        scope=Scope(level="domain", reference_id="software-development"),
        importance="high",
        observed_in_project_id="fatcat",
    )

    repo.save(global_issue)
    repo.save(project_issue)
    repo.save(domain_issue)

    assert global_repo.get(global_issue.id) == global_issue
    assert project_repo.get(project_issue.id) == project_issue
    assert global_repo.get(domain_issue.id) == domain_issue
    assert repo.list_by_project("fatcat") == [project_issue]
    assert repo.list_global() == [global_issue, domain_issue]

    project_issue.status = "resolved"
    repo.save(project_issue)
    assert len(project_repo.list_all()) == 1
    assert repo.get(project_issue.id).status == "resolved"


def test_session_repository_upserts_lifecycle(tmp_path):
    repo = JsonlSessionRepository(tmp_path / "sessions.jsonl")
    session = Session(source="transcript", project_id="fatcat")
    repo.save(session)

    session.status = "ended"
    repo.save(session)

    assert len(repo.list_all()) == 1
    assert repo.get(session.id).status == "ended"
    assert repo.list_by_project("fatcat")[0].id == session.id


def test_v1_memory_jsonl_remains_readable(tmp_path):
    memory_path = tmp_path / "memories.jsonl"
    memory_path.write_text(
        json.dumps(
            {
                "id": "mem_old",
                "content": "Keep explicit user review.",
                "memory_type": "principle",
                "scope": "global",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    inbox_path = tmp_path / "inbox.jsonl"
    inbox_path.write_text(
        json.dumps(
            {
                "id": "cand_old",
                "content": "Issues need confirmation.",
                "memory_type": "decision",
                "suggested_scope": "project:fatcat",
                "confidence": 0.8,
                "source_input_id": "raw_old",
                "reviewed": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    memory = JsonlMemoryRepository(memory_path).list_all()[0]
    candidate = JsonlInboxRepository(inbox_path).list_pending()[0]

    assert memory.id == "mem_old"
    assert memory.schema_version == 2
    assert candidate.id == "cand_old"
    assert candidate.status == "candidate"
