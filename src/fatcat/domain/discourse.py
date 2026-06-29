"""Conversation evidence layer: functional segments of a turn.

A :class:`Segment` is a clause- or function-level slice of one
:class:`fatcat.domain.models.ConversationTurn`. Segments are the smallest units
that later carry dialogue-act and discourse-relation annotations. They are
non-authoritative observations with exact provenance (turn id, speaker role,
character span), never memories themselves.

Detecting where the clause boundaries are is an adapter concern (an LLM
``DiscourseAnalyzer``). The domain only provides the type and pure, verbatim
span validation so a segment's text always matches its source turn.

See docs/adr/0001-deliberation-ontology.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import ConversationTurn


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Segment(BaseModel):
    """A functional slice of a conversation turn with exact provenance."""

    id: str = Field(default_factory=lambda: _new_id("seg"))
    turn_id: str
    session_id: str | None = None
    role: Literal["user", "assistant", "system"]
    text: str = Field(min_length=1)
    start: int | None = None
    end: int | None = None
    order: int = 0
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def validate_span(self) -> "Segment":
        if (self.start is None) != (self.end is None):
            raise ValueError("A segment span needs both start and end, or neither.")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("Segment start must come before end.")
        return self


def segments_from_turn(
    turn: ConversationTurn,
    spans: list[tuple[int, int]],
    *,
    session_id: str | None = None,
) -> list[Segment]:
    """Build ordered segments from character spans within a turn.

    Each span must lie inside the turn and yield non-empty text. Whitespace-only
    spans are skipped. The segment text is taken verbatim from the turn so it
    can never drift from its source.
    """

    segments: list[Segment] = []
    length = len(turn.content)
    order = 0
    for start, end in spans:
        if not (0 <= start < end <= length):
            raise ValueError(
                f"Span ({start}, {end}) is out of range for turn {turn.id!r}."
            )
        text = turn.content[start:end]
        if not text.strip():
            continue
        segments.append(
            Segment(
                turn_id=turn.id,
                session_id=session_id,
                role=turn.role,
                text=text,
                start=start,
                end=end,
                order=order,
            )
        )
        order += 1
    return segments


def whole_turn_segment(
    turn: ConversationTurn,
    *,
    session_id: str | None = None,
) -> Segment:
    """Treat the entire turn as a single segment (trivial fallback)."""

    return Segment(
        turn_id=turn.id,
        session_id=session_id,
        role=turn.role,
        text=turn.content,
        start=0,
        end=len(turn.content),
        order=0,
    )
