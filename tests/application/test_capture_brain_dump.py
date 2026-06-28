"""Tests for the CaptureBrainDump use case."""

from __future__ import annotations

import pytest

from fatcat.application.use_cases import CaptureBrainDump
from fatcat.domain.models import IssueCandidate, MemoryCandidate

from .fakes import (
    InMemoryInboxRepository,
    InMemoryIssueCandidateRepository,
    InMemoryRawInputRepository,
    StubLLM,
)


def _candidate(**overrides) -> MemoryCandidate:
    base = dict(
        content="User prefers FastAPI.",
        memory_type="preference",
        suggested_scope="global",
        confidence=0.8,
        sensitivity="low",
        source_input_id="placeholder",
    )
    base.update(overrides)
    return MemoryCandidate(**base)


def _issue_candidate(**overrides) -> IssueCandidate:
    base = dict(
        title="How should review work?",
        description="The review workflow is still open.",
        confidence=0.85,
    )
    base.update(overrides)
    return IssueCandidate(**base)


def test_capture_stores_raw_input_and_fills_inbox():
    raw_repo = InMemoryRawInputRepository()
    inbox = InMemoryInboxRepository()
    llm = StubLLM([_candidate(), _candidate(content="User likes local-first tools.")])
    uc = CaptureBrainDump(llm, raw_repo, inbox)

    result = uc.execute("Some long brain dump...")

    assert len(raw_repo.items) == 1
    assert len(result.candidates) == 2
    assert len(inbox.list_pending()) == 2
    assert llm.calls[0].content == "Some long brain dump..."


def test_capture_propagates_project_id_to_candidates():
    raw_repo = InMemoryRawInputRepository()
    inbox = InMemoryInboxRepository()
    llm = StubLLM([_candidate(project_id=None)])
    uc = CaptureBrainDump(llm, raw_repo, inbox)

    result = uc.execute("dump", project_id="demo")

    assert result.candidates[0].project_id == "demo"


def test_capture_rejects_empty_input():
    uc = CaptureBrainDump(
        StubLLM([]), InMemoryRawInputRepository(), InMemoryInboxRepository()
    )
    with pytest.raises(ValueError):
        uc.execute("  ")


def test_capture_with_no_candidates_leaves_inbox_empty():
    inbox = InMemoryInboxRepository()
    uc = CaptureBrainDump(StubLLM([]), InMemoryRawInputRepository(), inbox)
    result = uc.execute("nothing useful here")
    assert result.candidates == []
    assert inbox.list_pending() == []


def test_capture_filters_low_confidence_candidates():
    inbox = InMemoryInboxRepository()
    llm = StubLLM(
        [
            _candidate(content="strong", confidence=0.9),
            _candidate(content="weak", confidence=0.3),
        ]
    )
    uc = CaptureBrainDump(
        llm, InMemoryRawInputRepository(), inbox, min_confidence=0.6
    )
    result = uc.execute("dump")
    assert [c.content for c in result.candidates] == ["strong"]
    assert [c.content for c in inbox.list_pending()] == ["strong"]


def test_capture_can_skip_raw_input_storage():
    raw_repo = InMemoryRawInputRepository()
    inbox = InMemoryInboxRepository()
    uc = CaptureBrainDump(
        StubLLM([_candidate()]), raw_repo, inbox, store_raw_input=False
    )
    uc.execute("dump")
    assert raw_repo.items == []
    assert len(inbox.list_pending()) == 1


def test_capture_routes_issue_candidates_to_their_own_port():
    issue_inbox = InMemoryIssueCandidateRepository()
    llm = StubLLM([_candidate()], [_issue_candidate()])
    uc = CaptureBrainDump(
        llm,
        InMemoryRawInputRepository(),
        InMemoryInboxRepository(),
        issue_candidate_repo=issue_inbox,
    )

    result = uc.execute(
        "We still need to decide how review works.",
        project_id="fatcat",
        session_id="session_1",
        source_ref="transcript.jsonl",
    )

    assert len(result.issue_candidates) == 1
    assert result.total_candidates == 2
    assert issue_inbox.list_pending()[0].project_id == "fatcat"
    assert issue_inbox.list_pending()[0].session_id == "session_1"
    assert llm.calls[0].source_ref == "transcript.jsonl"


def test_capture_filters_low_confidence_issue_candidates():
    issue_inbox = InMemoryIssueCandidateRepository()
    llm = StubLLM(
        [],
        [
            _issue_candidate(title="strong", confidence=0.9),
            _issue_candidate(title="weak", confidence=0.2),
        ],
    )
    uc = CaptureBrainDump(
        llm,
        InMemoryRawInputRepository(),
        InMemoryInboxRepository(),
        issue_candidate_repo=issue_inbox,
        min_confidence=0.6,
    )

    result = uc.execute("There are open questions.")

    assert [candidate.title for candidate in result.issue_candidates] == ["strong"]
    assert [candidate.title for candidate in issue_inbox.list_pending()] == ["strong"]
