"""Domain policies: pure rules that constrain how memories are handled."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel

from .deliberation import DecisionIssue, DecisionIssueCandidate
from .models import (
    ConversationTurn,
    EvidenceQuote,
    Issue,
    IssueCandidate,
    MemoryCandidate,
    MemoryItem,
    RawInput,
    Scope,
    Session,
)
from .value_objects import (
    GLOBAL_SCOPE,
    CandidateStatus,
    Importance,
    Sensitivity,
    project_scope,
)

_UNSET = object()


class PrivacyPolicy(BaseModel):
    """User-controllable privacy rules for the MVP.

    The central guarantee: no automatically extracted candidate is ever persisted
    as a memory before the user reviews it.
    """

    require_review_before_persist: bool = True
    allow_raw_input_storage: bool = True
    allow_api_llm_processing: bool = False
    default_sensitivity: Sensitivity = "medium"


_ISSUE_CANDIDATE_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    "detected": {"candidate", "rejected"},
    "candidate": {"confirmed", "edited", "rejected", "merged", "deferred"},
    "deferred": {
        "candidate",
        "confirmed",
        "edited",
        "rejected",
        "merged",
        "deferred",
    },
}


def transition_issue_candidate(
    candidate: IssueCandidate,
    status: CandidateStatus,
    *,
    changed_at: datetime | None = None,
) -> IssueCandidate:
    """Apply a valid curation transition without mutating the source object."""

    allowed = _ISSUE_CANDIDATE_TRANSITIONS.get(candidate.status, set())
    if status not in allowed:
        raise ValueError(
            f"Cannot transition issue candidate from {candidate.status!r} "
            f"to {status!r}."
        )
    requires_review = status in ("detected", "candidate", "deferred")
    return candidate.model_copy(
        update={
            "status": status,
            "requires_user_review": requires_review,
            "updated_at": changed_at or datetime.now(timezone.utc),
        },
        deep=True,
    )


def _locate_turn(raw_input: RawInput, text: str) -> ConversationTurn | None:
    """Find the turn a verbatim quote came from, preferring a user turn.

    The same text could appear in both a user and an assistant turn (the
    assistant echoing the user). When it does, the user turn is credited so a
    legitimate user quote is never misattributed to the assistant.
    """

    fallback: ConversationTurn | None = None
    for turn in raw_input.turns:
        if text in turn.content:
            if turn.role == "user":
                return turn
            if fallback is None:
                fallback = turn
    return fallback


def evidence_quotes_from_raw_input(
    raw_input: RawInput,
    quotes: list[str],
) -> list[EvidenceQuote]:
    """Keep only deduplicated, verbatim excerpts present in the source input.

    When the raw input carries structured ``turns``, each quote is annotated
    with the originating ``turn_id`` and ``role`` for downstream provenance.
    """

    evidence: list[EvidenceQuote] = []
    seen: set[str] = set()
    for quote in quotes:
        text = quote.strip()
        if not text or text in seen or text not in raw_input.content:
            continue
        seen.add(text)
        turn = _locate_turn(raw_input, text)
        evidence.append(
            EvidenceQuote(
                text=text,
                source_type=raw_input.source,
                source_input_id=raw_input.id,
                source_ref=raw_input.source_ref,
                session_id=raw_input.session_id,
                turn_id=turn.id if turn is not None else None,
                role=turn.role if turn is not None else None,
            )
        )
    return evidence


def drop_non_user_evidence(quotes: list[EvidenceQuote]) -> list[EvidenceQuote]:
    """Keep only user-authored evidence for user memories and learning issues.

    A FatCat memory or issue is a claim about the *user*. Assistant or system
    text must never be cited as evidence of the user's agency. Quotes whose role
    is unknown (legacy flat inputs without structured turns) are kept unchanged,
    so this rule only tightens behaviour where role information is available.
    """

    return [quote for quote in quotes if quote.role in (None, "user")]


def learning_issue_has_sufficient_evidence(candidate: IssueCandidate) -> bool:
    """Reject speculative learning questions at the domain boundary.

    One quote is sufficient only when the user explicitly expresses uncertainty.
    Otherwise a question needs evidence from at least two distinct moments.
    """

    texts = list(dict.fromkeys(quote.text.strip() for quote in candidate.evidence))
    if len(texts) >= 2:
        return True
    if not texts:
        return False

    lowered = texts[0].lower()
    uncertainty_markers = (
        "not sure",
        "unsure",
        "undecided",
        "unclear whether",
        "i wonder whether",
        "weiß nicht",
        "weiss nicht",
        "nicht sicher",
        "unklar, ob",
        "unentschlossen",
        "ich schwanke",
    )
    if any(marker in lowered for marker in uncertainty_markers):
        return True

    # A first-person question such as "Do I prefer X or Y?" is explicit
    # uncertainty even without an uncertainty adjective.
    return "?" in lowered and bool(
        re.search(r"\b(i|me|my|ich|mir|mein(?:e|en|er|es)?)\b", lowered)
    )


def candidate_to_memory_item(
    candidate: MemoryCandidate,
    *,
    scope: str | None = None,
    project_id: str | None | object = _UNSET,
    content: str | None = None,
    allow_export: bool = True,
) -> MemoryItem:
    """Promote a reviewed candidate into a confirmed memory item.

    ``scope`` defaults to the candidate's suggested scope. ``content`` may be
    overridden when the user edits the candidate before saving.
    """

    effective_scope = scope or candidate.suggested_scope or GLOBAL_SCOPE
    effective_project_id = (
        candidate.project_id if project_id is _UNSET else project_id
    )
    now = datetime.now(timezone.utc)
    return MemoryItem(
        content=content if content is not None else candidate.content,
        memory_type=candidate.memory_type,
        scope=effective_scope,
        project_id=effective_project_id,
        sensitivity=candidate.sensitivity,
        allow_export=allow_export,
        confidence=candidate.confidence,
        status="active",
        source_input_ids=[candidate.source_input_id],
        source_candidate_ids=[candidate.id],
        session_ids=[candidate.session_id] if candidate.session_id else [],
        user_intention=candidate.user_intention,
        reuse_hint=candidate.reuse_hint,
        evidence=candidate.evidence,
        keywords=candidate.keywords,
        created_at=now,
        updated_at=now,
    )


def confirm_issue(
    candidate: IssueCandidate,
    *,
    scope: Scope,
    importance: Importance,
    linked_memory_ids: list[str] | None = None,
    title: str | None = None,
    description: str | None = None,
) -> Issue:
    """Create a confirmed issue from an explicit user review decision."""

    if candidate.status not in ("candidate", "deferred", "edited"):
        raise ValueError(f"Cannot confirm issue candidate in status {candidate.status!r}.")
    return Issue(
        question=title or candidate.question,
        learning_goal=description or candidate.learning_goal,
        target_memory_types=candidate.target_memory_types,
        answer_signals=candidate.answer_signals,
        scope=scope,
        importance=importance,
        evidence=candidate.evidence,
        linked_memory_ids=list(linked_memory_ids or []),
        linked_memory_candidate_ids=candidate.linked_memory_candidate_ids,
        keywords=candidate.keywords,
        source_candidate_ids=[candidate.id],
        session_id=candidate.session_id,
        observed_in_project_id=candidate.observed_in_project_id,
    )


def merge_issue_candidate(
    candidate: IssueCandidate,
    target: Issue,
    *,
    linked_memory_ids: list[str] | None = None,
) -> Issue:
    """Merge supporting context into an existing issue without changing its scope."""

    if candidate.status not in ("candidate", "deferred", "edited"):
        raise ValueError(f"Cannot merge issue candidate in status {candidate.status!r}.")

    evidence_by_key = {
        (
            evidence.text,
            evidence.source_input_id,
            evidence.session_id,
        ): evidence
        for evidence in [*target.evidence, *candidate.evidence]
    }
    return target.model_copy(
        update={
            "evidence": list(evidence_by_key.values()),
            "linked_memory_ids": list(
                dict.fromkeys(
                    [*target.linked_memory_ids, *(linked_memory_ids or [])]
                )
            ),
            "linked_memory_candidate_ids": list(
                dict.fromkeys(
                    [
                        *target.linked_memory_candidate_ids,
                        *candidate.linked_memory_candidate_ids,
                    ]
                )
            ),
            "keywords": list(dict.fromkeys([*target.keywords, *candidate.keywords])),
            "target_memory_types": list(
                dict.fromkeys(
                    [*target.target_memory_types, *candidate.target_memory_types]
                )
            ),
            "answer_signals": list(
                dict.fromkeys([*target.answer_signals, *candidate.answer_signals])
            ),
            "source_candidate_ids": list(
                dict.fromkeys([*target.source_candidate_ids, candidate.id])
            ),
            "updated_at": datetime.now(timezone.utc),
        },
        deep=True,
    )


def transition_decision_issue_candidate(
    candidate: DecisionIssueCandidate,
    status: CandidateStatus,
    *,
    changed_at: datetime | None = None,
) -> DecisionIssueCandidate:
    """Apply a valid curation transition to a decision-issue candidate."""

    allowed = _ISSUE_CANDIDATE_TRANSITIONS.get(candidate.status, set())
    if status not in allowed:
        raise ValueError(
            f"Cannot transition decision issue candidate from {candidate.status!r} "
            f"to {status!r}."
        )
    requires_review = status in ("detected", "candidate", "deferred")
    return candidate.model_copy(
        update={
            "status": status,
            "requires_user_review": requires_review,
            "updated_at": changed_at or datetime.now(timezone.utc),
        },
        deep=True,
    )


def confirm_decision_issue(
    candidate: DecisionIssueCandidate,
    *,
    scope: Scope,
    importance: Importance,
    linked_learning_question_ids: list[str] | None = None,
) -> DecisionIssue:
    """Create a confirmed decision issue from an explicit user review decision."""

    if candidate.status not in ("candidate", "deferred", "edited"):
        raise ValueError(
            f"Cannot confirm decision issue candidate in status {candidate.status!r}."
        )
    return DecisionIssue(
        question=candidate.question,
        scope=scope,
        importance=importance,
        positions=candidate.positions,
        criteria=candidate.criteria,
        arguments=candidate.arguments,
        evidence=candidate.evidence,
        keywords=candidate.keywords,
        linked_learning_question_ids=list(linked_learning_question_ids or []),
        source_candidate_ids=[candidate.id],
        session_id=candidate.session_id,
        observed_in_project_id=candidate.observed_in_project_id,
    )


def adopt_position(
    issue: DecisionIssue,
    position_id: str,
    *,
    rationale: str | None = None,
    changed_at: datetime | None = None,
) -> DecisionIssue:
    """Adopt one position as the issue's decision and mark the others rejected."""

    if not any(position.id == position_id for position in issue.positions):
        raise ValueError(f"Unknown position id {position_id!r} for this issue.")
    updated_positions = [
        position.model_copy(
            update={
                "status": "adopted" if position.id == position_id else "rejected"
            }
        )
        for position in issue.positions
    ]
    return issue.model_copy(
        update={
            "positions": updated_positions,
            "adopted_position_id": position_id,
            "status": "adopted",
            "rationale": rationale if rationale is not None else issue.rationale,
            "updated_at": changed_at or datetime.now(timezone.utc),
        },
        deep=True,
    )


def end_session(
    session: Session,
    *,
    ended_at: datetime | None = None,
) -> Session:
    """Close an active capture session."""

    if session.status != "active":
        raise ValueError(f"Cannot end session in status {session.status!r}.")
    return session.model_copy(
        update={
            "status": "ended",
            "ended_at": ended_at or datetime.now(timezone.utc),
        },
        deep=True,
    )


def mark_session_reviewed(
    session: Session,
    *,
    reviewed_at: datetime | None = None,
) -> Session:
    """Mark an ended session reviewed after its pending candidates are resolved."""

    if session.status != "ended":
        raise ValueError(f"Cannot review session in status {session.status!r}.")
    return session.model_copy(
        update={
            "status": "reviewed",
            "reviewed_at": reviewed_at or datetime.now(timezone.utc),
        },
        deep=True,
    )


def scope_for_project_only(project_id: str) -> str:
    """Scope string used when a user chooses 'project only' during review."""

    return project_scope(project_id)


def normalize_memory_content(content: str) -> str:
    """Canonical form for duplicate detection: lowercased, whitespace-collapsed.

    Two memories that differ only in casing or spacing are considered the same
    thought, so we don't clutter the store with near-identical entries.
    """

    return " ".join(content.lower().split())
