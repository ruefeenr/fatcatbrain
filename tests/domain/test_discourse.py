"""Tests for the conversation evidence layer (segments)."""

from __future__ import annotations

import pytest

from fatcat.domain.discourse import Segment, segments_from_turn, whole_turn_segment
from fatcat.domain.models import ConversationTurn


def _turn() -> ConversationTurn:
    return ConversationTurn(
        id="s1:1",
        role="user",
        content="I prefer FastAPI. It gives me type safety.",
    )


def test_segments_from_turn_keeps_verbatim_text_and_provenance():
    turn = _turn()
    segments = segments_from_turn(
        turn, [(0, 17), (18, len(turn.content))], session_id="s1"
    )
    assert [seg.text for seg in segments] == [
        "I prefer FastAPI.",
        "It gives me type safety.",
    ]
    assert [seg.order for seg in segments] == [0, 1]
    assert all(seg.turn_id == "s1:1" for seg in segments)
    assert all(seg.role == "user" for seg in segments)
    assert all(seg.session_id == "s1" for seg in segments)
    # The text always matches the source span exactly.
    assert all(turn.content[seg.start : seg.end] == seg.text for seg in segments)


def test_segments_skip_whitespace_only_spans():
    turn = _turn()
    segments = segments_from_turn(turn, [(17, 18)])  # the space between clauses
    assert segments == []


def test_segments_reject_out_of_range_span():
    turn = _turn()
    with pytest.raises(ValueError):
        segments_from_turn(turn, [(0, len(turn.content) + 5)])


def test_whole_turn_segment_covers_the_turn():
    turn = _turn()
    segment = whole_turn_segment(turn, session_id="s1")
    assert segment.text == turn.content
    assert segment.start == 0
    assert segment.end == len(turn.content)


def test_segment_span_requires_both_bounds():
    with pytest.raises(ValueError):
        Segment(turn_id="s1:1", role="user", text="hi", start=0)
