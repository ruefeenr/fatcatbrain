from __future__ import annotations

from fatcat.application.ports import CandidateExtraction
from fatcat.domain.models import EvidenceQuote, MemoryCandidate, RawInput
from fatcat_benchmarks.application.runner import BenchmarkRunner
from fatcat_benchmarks.domain.models import (
    BenchmarkCase,
    BenchmarkExpectation,
    CandidateExpectation,
    ConversationTurn,
)


class PreferenceLLM:
    def extract_candidates(self, raw_input: RawInput, **_kwargs) -> CandidateExtraction:
        evidence = "I prefer explicit configuration"
        return CandidateExtraction(
            memory_candidates=[
                MemoryCandidate(
                    content="The user prefers explicit configuration.",
                    memory_type="preference",
                    suggested_scope="global",
                    confidence=0.9,
                    source_input_id=raw_input.id,
                    evidence=[
                        EvidenceQuote(
                            text=evidence,
                            source_type="import",
                            source_input_id=raw_input.id,
                        )
                    ],
                )
            ]
        )


class FailingLLM:
    def extract_candidates(self, raw_input: RawInput, **_kwargs) -> CandidateExtraction:
        raise ConnectionError("offline")


def test_runner_scores_required_candidate_and_review_burden():
    case = BenchmarkCase(
        id="preference",
        suite="challenge",
        annotation_status="adjudicated",
        turns=[
            ConversationTurn(
                id="u1",
                role="user",
                content="I prefer explicit configuration because it is predictable.",
            )
        ],
        expectation=BenchmarkExpectation(
            required=[
                CandidateExpectation(
                    kind="memory",
                    memory_types=["preference"],
                    evidence_contains="I prefer explicit configuration",
                )
            ]
        ),
    )

    report = BenchmarkRunner(
        PreferenceLLM(), model_name="test-model"
    ).run([case])

    assert report.metrics.assertion_pass_rate == 1.0
    assert report.metrics.candidates_per_100_user_turns == 100.0
    assert report.metrics.unsupported_evidence_count == 0
    assert report.metrics.memory_candidate_count == 1


def test_runner_counts_execution_failure_as_failed_assertion():
    case = BenchmarkCase(
        id="offline",
        suite="natural",
        turns=[ConversationTurn(id="u1", role="user", content="Hello")],
    )

    report = BenchmarkRunner(FailingLLM(), model_name="offline").run([case])

    assert report.metrics.failed_case_count == 1
    assert report.metrics.assertion_count == 1
    assert report.metrics.assertion_pass_rate == 0.0
    assert report.cases[0].assertions[0].name == "execution_success"


def test_runner_reports_progress_and_combines_existing_results():
    case = BenchmarkCase(
        id="new",
        suite="natural",
        turns=[
            ConversationTurn(
                id="u1",
                role="user",
                content="I prefer explicit configuration.",
            )
        ],
    )
    prior = BenchmarkRunner(FailingLLM(), model_name="offline").run(
        [
            BenchmarkCase(
                id="prior",
                suite="natural",
                turns=[ConversationTurn(id="u1", role="user", content="Hello")],
            )
        ]
    ).cases[0]
    progress = []

    report = BenchmarkRunner(PreferenceLLM(), model_name="test-model").run_resumable(
        [case],
        existing_results=[prior],
        on_result=lambda completed, total, result: progress.append(
            (completed, total, result.case_id)
        ),
    )

    assert [result.case_id for result in report.cases] == ["prior", "new"]
    assert progress == [(2, 2, "new")]


def test_runner_accepts_evidence_span_from_gold_source_turn():
    case = BenchmarkCase(
        id="gold-preference",
        suite="gold",
        annotation_status="single_annotated",
        turns=[
            ConversationTurn(
                id="u1",
                role="user",
                content=(
                    "When I need focus, I prefer explicit configuration over "
                    "hidden defaults."
                ),
            )
        ],
        expectation=BenchmarkExpectation(
            required=[
                CandidateExpectation(
                    kind="memory",
                        memory_types=["preference"],
                        evidence_source_texts=[
                            "When I need focus, I prefer explicit configuration "
                            "over hidden defaults."
                        ],
                )
            ]
        ),
    )

    report = BenchmarkRunner(PreferenceLLM(), model_name="test-model").run([case])

    assert report.metrics.assertion_pass_rate == 1.0


class SessionGroundedLLM:
    """Quotes a different turn than the gold one, but the same session."""

    def extract_candidates(self, raw_input: RawInput, **_kwargs) -> CandidateExtraction:
        return CandidateExtraction(
            memory_candidates=[
                MemoryCandidate(
                    content="The user prefers Vim.",
                    memory_type="decision",
                    suggested_scope="global",
                    confidence=0.9,
                    source_input_id=raw_input.id,
                    evidence=[
                        EvidenceQuote(
                            text="Vim keeps me focused.",
                            source_type="import",
                            source_input_id=raw_input.id,
                            turn_id="session-1:2",
                            role="user",
                        )
                    ],
                )
            ]
        )


def test_runner_accepts_same_session_evidence_and_preference_family():
    case = BenchmarkCase(
        id="gold-session",
        suite="gold",
        annotation_status="single_annotated",
        turns=[
            ConversationTurn(
                id="session-1:1",
                role="user",
                content="Which editor should I use day to day?",
            ),
            ConversationTurn(
                id="session-1:2",
                role="user",
                content="Vim keeps me focused.",
            ),
        ],
        expectation=BenchmarkExpectation(
            required=[
                CandidateExpectation(
                    kind="memory",
                    memory_types=["preference", "decision", "principle"],
                    evidence_source_texts=["I always choose Vim for focused editing."],
                    evidence_turn_ids=["session-1:1"],
                )
            ]
        ),
    )

    report = BenchmarkRunner(SessionGroundedLLM(), model_name="test-model").run([case])

    assert report.metrics.assertion_pass_rate == 1.0
