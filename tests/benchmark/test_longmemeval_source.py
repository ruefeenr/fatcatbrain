from __future__ import annotations

import json

from fatcat_benchmarks.adapters.longmemeval_source import LongMemEvalSource


def test_longmemeval_preference_maps_roles_evidence_and_expectation(tmp_path):
    source_file = tmp_path / "longmemeval_oracle.json"
    source_file.write_text(
        json.dumps(
            [
                {
                    "question_id": "preference-1",
                    "question_type": "single-session-preference",
                    "question": "Which editor does the user prefer?",
                    "answer": "Vim",
                    "question_date": "2025/01/02",
                    "haystack_session_ids": ["session-1"],
                    "haystack_dates": ["2025/01/01"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "assistant",
                                "content": "Which editor do you enjoy?",
                            },
                            {
                                "role": "user",
                                "content": "I always choose Vim for focused editing.",
                                "has_answer": True,
                            },
                        ]
                    ],
                    "answer_session_ids": ["session-1"],
                }
            ]
        ),
        encoding="utf-8",
    )

    case = next(
        iter(
            LongMemEvalSource(
                source_file,
                question_types={"single-session-preference"},
            ).cases()
        )
    )

    assert case.id == "longmemeval:preference-1"
    assert case.suite == "gold"
    assert case.annotation_status == "single_annotated"
    assert [turn.role for turn in case.turns] == ["assistant", "user"]
    assert case.metadata["evidence_turn_ids"] == ["session-1:2"]
    requirement = case.expectation.required[0]
    assert "preference" in requirement.memory_types
    assert "decision" in requirement.memory_types
    assert requirement.evidence_source_texts == [
        "I always choose Vim for focused editing."
    ]
    assert requirement.evidence_turn_ids == ["session-1:2"]


def test_longmemeval_non_preference_remains_unannotated(tmp_path):
    source_file = tmp_path / "longmemeval_oracle.json"
    source_file.write_text(
        json.dumps(
            [
                {
                    "question_id": "update-1",
                    "question_type": "knowledge-update",
                    "haystack_sessions": [
                        [{"role": "user", "content": "The deadline changed."}]
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    case = next(iter(LongMemEvalSource(source_file).cases()))

    assert case.suite == "natural"
    assert case.annotation_status == "unannotated"
    assert case.expectation is None
