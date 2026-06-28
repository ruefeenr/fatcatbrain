from __future__ import annotations

import pytest

from fatcat.application.use_cases import ReviewSession, SessionLifecycle
from fatcat.domain.models import IssueCandidate, MemoryCandidate

from .fakes import (
    InMemoryInboxRepository,
    InMemoryIssueCandidateRepository,
    InMemorySessionRepository,
)


def test_session_lifecycle_start_end_and_review():
    repository = InMemorySessionRepository()
    lifecycle = SessionLifecycle(repository)
    started = lifecycle.start(
        source="codex",
        project_id="fatcat",
        source_ref="/rollout.jsonl",
        title="FatCat workflow",
        session_id="codex_thread",
    )
    ended = lifecycle.end(started.id)
    reviewed = lifecycle.mark_reviewed(ended.id)

    assert started.status == "active"
    assert ended.status == "ended"
    assert reviewed.status == "reviewed"


def test_latest_unreviewed_is_project_scoped():
    repository = InMemorySessionRepository()
    lifecycle = SessionLifecycle(repository)
    alpha = lifecycle.start(source="brain_dump", project_id="alpha")
    lifecycle.end(alpha.id)
    beta = lifecycle.start(source="brain_dump", project_id="beta")
    lifecycle.end(beta.id)

    assert lifecycle.latest_unreviewed("alpha").id == alpha.id


def test_review_session_filters_candidates_and_completes_when_empty():
    sessions = InMemorySessionRepository()
    lifecycle = SessionLifecycle(sessions)
    session = lifecycle.start(source="brain_dump", project_id="fatcat")
    lifecycle.end(session.id)
    memories = InMemoryInboxRepository()
    issues = InMemoryIssueCandidateRepository()
    memories.add_candidates(
        [
            MemoryCandidate(
                content="Keep reviews concise.",
                memory_type="preference",
                suggested_scope="project:fatcat",
                confidence=0.9,
                source_input_id="raw_1",
                session_id=session.id,
            )
        ]
    )
    issues.add_candidates(
        [
            IssueCandidate(
                title="Review flow",
                description="Still open.",
                confidence=0.8,
                session_id="other",
            )
        ]
    )
    review = ReviewSession(sessions, memories, issues)

    loaded = review.load(session.id)

    assert len(loaded.memory_candidates) == 1
    assert loaded.issue_candidates == []
    with pytest.raises(ValueError, match="pending"):
        review.complete(session.id)

    memories.mark_reviewed(loaded.memory_candidates[0].id)
    assert review.complete(session.id).status == "reviewed"
