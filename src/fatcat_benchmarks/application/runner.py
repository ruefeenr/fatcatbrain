"""Run extraction without touching production persistence."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from time import perf_counter

from fatcat.application.ports import LLMPort
from fatcat.domain.models import ConversationTurn as DomainConversationTurn
from fatcat.domain.models import RawInput
from fatcat_benchmarks.domain.models import (
    AssertionResult,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkMetrics,
    BenchmarkReport,
    CandidateExpectation,
    CandidateObservation,
)


class BenchmarkRunner:
    """Evaluate the current extraction adapter in a persistence-free sandbox."""

    def __init__(
        self,
        llm: LLMPort,
        *,
        model_name: str,
        include_assistant_context: bool = False,
    ) -> None:
        self._llm = llm
        self._model_name = model_name
        self._include_assistant_context = include_assistant_context

    def run(self, cases: Iterable[BenchmarkCase]) -> BenchmarkReport:
        return self.run_resumable(cases)

    def run_resumable(
        self,
        cases: Iterable[BenchmarkCase],
        *,
        existing_results: Iterable[BenchmarkCaseResult] = (),
        on_result: Callable[[int, int, BenchmarkCaseResult], None] | None = None,
    ) -> BenchmarkReport:
        """Run pending cases and expose each completed result for checkpointing."""

        pending = list(cases)
        results = list(existing_results)
        total = len(results) + len(pending)
        for case in pending:
            result = self._run_case(case)
            results.append(result)
            if on_result is not None:
                on_result(len(results), total, result)
        return BenchmarkReport(
            model=self._model_name,
            include_assistant_context=self._include_assistant_context,
            metrics=_aggregate(results),
            cases=results,
        )

    def _run_case(self, case: BenchmarkCase) -> BenchmarkCaseResult:
        selected = case.selected_turns(
            include_assistant_context=self._include_assistant_context
        )
        raw_input = RawInput(
            content=case.render(
                include_assistant_context=self._include_assistant_context
            ),
            source="import",
            session_id=f"benchmark:{case.id}",
            source_ref=f"benchmark:{case.id}",
            turns=[
                DomainConversationTurn(
                    id=turn.id,
                    role=turn.role,
                    content=turn.content,
                    language=turn.language,
                )
                for turn in selected
            ],
        )
        started = perf_counter()
        try:
            extraction = self._llm.extract_candidates(raw_input)
        except Exception as exc:  # noqa: BLE001 - failures are benchmark data
            return BenchmarkCaseResult(
                case_id=case.id,
                suite=case.suite,
                user_turns=len(case.user_turns),
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                assertions=[
                    AssertionResult(
                        name="execution_success",
                        passed=False,
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                ],
                error=f"{type(exc).__name__}: {exc}",
            )

        observations = [
            CandidateObservation(
                kind="memory",
                content=candidate.content,
                memory_type=candidate.memory_type,
                scope_level=candidate.scope_ref.level,
                confidence=candidate.confidence,
                evidence=[quote.text for quote in candidate.evidence],
                evidence_turn_ids=[
                    quote.turn_id
                    for quote in candidate.evidence
                    if quote.turn_id is not None
                ],
            )
            for candidate in extraction.memory_candidates
        ]
        observations.extend(
            CandidateObservation(
                kind="issue",
                content=candidate.question,
                target_memory_types=list(candidate.target_memory_types),
                scope_level=(
                    candidate.suggested_scope.level
                    if candidate.suggested_scope is not None
                    else None
                ),
                confidence=candidate.confidence,
                evidence=[quote.text for quote in candidate.evidence],
                evidence_turn_ids=[
                    quote.turn_id
                    for quote in candidate.evidence
                    if quote.turn_id is not None
                ],
            )
            for candidate in extraction.issue_candidates
        )

        evidence = [quote for item in observations for quote in item.evidence]
        unsupported = 0
        assistant_only = 0
        for quote in evidence:
            roles = case.evidence_roles(quote)
            if not roles:
                unsupported += 1
            elif "user" not in roles:
                assistant_only += 1

        return BenchmarkCaseResult(
            case_id=case.id,
            suite=case.suite,
            user_turns=len(case.user_turns),
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
            candidates=observations,
            evidence_quote_count=len(evidence),
            unsupported_evidence_count=unsupported,
            assistant_evidence_count=assistant_only,
            assertions=_evaluate_expectation(case, observations),
        )


def _evaluate_expectation(
    case: BenchmarkCase,
    candidates: list[CandidateObservation],
) -> list[AssertionResult]:
    expected = case.expectation
    if expected is None:
        return []

    memories = [item for item in candidates if item.kind == "memory"]
    issues = [item for item in candidates if item.kind == "issue"]
    assertions: list[AssertionResult] = []

    if expected.forbid_any_candidates:
        assertions.append(
            AssertionResult(
                name="no_candidates",
                passed=not candidates,
                detail=f"Observed {len(candidates)} candidate(s).",
            )
        )
    if expected.max_memory_candidates is not None:
        assertions.append(
            AssertionResult(
                name="max_memory_candidates",
                passed=len(memories) <= expected.max_memory_candidates,
                detail=(
                    f"Observed {len(memories)}; maximum is "
                    f"{expected.max_memory_candidates}."
                ),
            )
        )
    if expected.max_issue_candidates is not None:
        assertions.append(
            AssertionResult(
                name="max_issue_candidates",
                passed=len(issues) <= expected.max_issue_candidates,
                detail=(
                    f"Observed {len(issues)}; maximum is "
                    f"{expected.max_issue_candidates}."
                ),
            )
        )
    for index, requirement in enumerate(expected.required, start=1):
        matches = any(
            _matches(candidate, requirement) for candidate in candidates
        )
        assertions.append(
            AssertionResult(
                name=f"required_candidate_{index}",
                passed=matches,
                detail=(
                    "Matched required candidate."
                    if matches
                    else f"No candidate matched {requirement.model_dump()}."
                ),
            )
        )
    return assertions


def _session_of(turn_id: str) -> str:
    """Session identifier embedded in a ``<session>:<index>`` turn id."""

    return turn_id.rsplit(":", 1)[0] if ":" in turn_id else turn_id


def _evidence_grounded(
    observed: CandidateObservation,
    expected: CandidateExpectation,
) -> bool:
    """Whether observed evidence is grounded in the expected gold source.

    A preference may legitimately surface in a different turn than the single
    one a dataset marks as gold, so matching accepts three signals, from
    strongest to weakest: an exact turn id, the same source session, or a
    bidirectional verbatim-span overlap with a gold source text.
    """

    if not expected.evidence_source_texts and not expected.evidence_turn_ids:
        return True

    for quote in observed.evidence:
        for source_text in expected.evidence_source_texts:
            if quote in source_text or source_text in quote:
                return True

    expected_sessions = {
        _session_of(turn_id) for turn_id in expected.evidence_turn_ids
    }
    for turn_id in observed.evidence_turn_ids:
        if turn_id in expected.evidence_turn_ids:
            return True
        if _session_of(turn_id) in expected_sessions:
            return True
    return False


def _matches(
    observed: CandidateObservation,
    expected: CandidateExpectation,
) -> bool:
    if observed.kind != expected.kind:
        return False
    if expected.memory_types and observed.memory_type not in expected.memory_types:
        return False
    if expected.evidence_contains and not any(
        expected.evidence_contains in quote for quote in observed.evidence
    ):
        return False
    if not _evidence_grounded(observed, expected):
        return False
    if expected.scope_level and observed.scope_level != expected.scope_level:
        return False
    if expected.target_memory_types and not set(expected.target_memory_types).issubset(
        observed.target_memory_types
    ):
        return False
    return True


def _aggregate(results: list[BenchmarkCaseResult]) -> BenchmarkMetrics:
    user_turns = sum(result.user_turns for result in results)
    candidates = [item for result in results for item in result.candidates]
    assertions = [item for result in results for item in result.assertions]
    passed = sum(item.passed for item in assertions)
    return BenchmarkMetrics(
        case_count=len(results),
        failed_case_count=sum(result.error is not None for result in results),
        user_turn_count=user_turns,
        memory_candidate_count=sum(item.kind == "memory" for item in candidates),
        issue_candidate_count=sum(item.kind == "issue" for item in candidates),
        zero_candidate_case_count=sum(not result.candidates for result in results),
        candidates_per_100_user_turns=(
            round(len(candidates) * 100 / user_turns, 2) if user_turns else 0.0
        ),
        evidence_quote_count=sum(result.evidence_quote_count for result in results),
        unsupported_evidence_count=sum(
            result.unsupported_evidence_count for result in results
        ),
        assistant_evidence_count=sum(
            result.assistant_evidence_count for result in results
        ),
        assertion_count=len(assertions),
        passed_assertion_count=passed,
        assertion_pass_rate=(round(passed / len(assertions), 4) if assertions else None),
    )
