"""Theory-neutral benchmark cases, expectations, and reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from fatcat.domain.value_objects import ExtractableMemoryType, ScopeLevel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationTurn(BaseModel):
    """One turn from a benchmark conversation."""

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    language: str | None = None


class CandidateExpectation(BaseModel):
    """A semantic assertion for one expected extraction.

    Content wording is deliberately not asserted. Candidate type, evidence,
    scope, and target memory types are stable enough to evaluate without making
    the benchmark prompt-specific.
    """

    kind: Literal["memory", "issue"]
    memory_types: list[ExtractableMemoryType] = Field(default_factory=list)
    evidence_contains: str | None = None
    evidence_source_texts: list[str] = Field(default_factory=list)
    evidence_turn_ids: list[str] = Field(default_factory=list)
    scope_level: ScopeLevel | None = None
    target_memory_types: list[ExtractableMemoryType] = Field(default_factory=list)


class BenchmarkExpectation(BaseModel):
    """Human-authored outcome constraints for challenge and gold cases."""

    forbid_any_candidates: bool = False
    max_memory_candidates: int | None = Field(default=None, ge=0)
    max_issue_candidates: int | None = Field(default=None, ge=0)
    required: list[CandidateExpectation] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def validate_forbidden_case(self) -> "BenchmarkExpectation":
        if self.forbid_any_candidates and self.required:
            raise ValueError("A forbidden case cannot also require candidates.")
        return self


class BenchmarkCase(BaseModel):
    """A natural, controlled, or manually annotated conversation."""

    schema_version: int = 1
    id: str
    suite: Literal["natural", "challenge", "gold"]
    annotation_status: Literal[
        "unannotated", "single_annotated", "adjudicated"
    ] = "unannotated"
    language: str | None = None
    turns: list[ConversationTurn] = Field(min_length=1)
    expectation: BenchmarkExpectation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_annotation(self) -> "BenchmarkCase":
        if self.annotation_status != "unannotated" and self.expectation is None:
            raise ValueError("Annotated cases require an expectation.")
        return self

    @property
    def user_turns(self) -> list[ConversationTurn]:
        return [turn for turn in self.turns if turn.role == "user"]

    def selected_turns(
        self, *, include_assistant_context: bool = False
    ) -> list[ConversationTurn]:
        """Turns actually shown to the model for a given rendering mode."""

        if include_assistant_context:
            return list(self.turns)
        return [turn for turn in self.turns if turn.role == "user"]

    def render(self, *, include_assistant_context: bool = False) -> str:
        """Render a role-labelled transcript for FatCat's existing LLM port."""

        selected = self.selected_turns(
            include_assistant_context=include_assistant_context
        )
        rendered: list[str] = []
        user_index = 0
        assistant_index = 0
        for turn in selected:
            if turn.role == "user":
                user_index += 1
                label = f"USER MESSAGE {user_index}"
            elif turn.role == "assistant":
                assistant_index += 1
                label = f"ASSISTANT CONTEXT {assistant_index} (NOT USER EVIDENCE)"
            else:
                label = "SYSTEM CONTEXT (NOT USER EVIDENCE)"
            rendered.append(f"[{label}]\n{turn.content.strip()}")
        return "\n\n".join(rendered)

    def evidence_roles(self, quote: str) -> set[str]:
        """Return the roles whose original content contains an evidence quote."""

        text = quote.strip()
        return {turn.role for turn in self.turns if text and text in turn.content}


class CandidateObservation(BaseModel):
    """Stable, serialisable projection of a FatCat proposal."""

    kind: Literal["memory", "issue"]
    content: str
    memory_type: str | None = None
    target_memory_types: list[str] = Field(default_factory=list)
    scope_level: str | None = None
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    evidence_turn_ids: list[str] = Field(default_factory=list)


class AssertionResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class BenchmarkCaseResult(BaseModel):
    case_id: str
    suite: str
    user_turns: int
    elapsed_ms: float
    candidates: list[CandidateObservation] = Field(default_factory=list)
    evidence_quote_count: int = 0
    unsupported_evidence_count: int = 0
    assistant_evidence_count: int = 0
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: str | None = None


class BenchmarkMetrics(BaseModel):
    case_count: int
    failed_case_count: int
    user_turn_count: int
    memory_candidate_count: int
    issue_candidate_count: int
    zero_candidate_case_count: int
    candidates_per_100_user_turns: float
    evidence_quote_count: int
    unsupported_evidence_count: int
    assistant_evidence_count: int
    assertion_count: int
    passed_assertion_count: int
    assertion_pass_rate: float | None


class BenchmarkReport(BaseModel):
    schema_version: int = 1
    created_at: datetime = Field(default_factory=_utcnow)
    model: str
    include_assistant_context: bool
    metrics: BenchmarkMetrics
    cases: list[BenchmarkCaseResult]


class BenchmarkCheckpoint(BaseModel):
    """Resumable state for a specific benchmark configuration."""

    schema_version: int = 1
    model: str
    include_assistant_context: bool
    case_ids: list[str]
    results: list[BenchmarkCaseResult] = Field(default_factory=list)
