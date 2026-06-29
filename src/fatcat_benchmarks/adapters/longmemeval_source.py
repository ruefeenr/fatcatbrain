"""LongMemEval download and conversion adapter.

The official dataset remains the source of truth. This adapter converts selected
question instances into FatCat's theory-neutral extraction benchmark format.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Literal
from urllib.request import Request, urlopen

from fatcat_benchmarks.domain.models import (
    BenchmarkCase,
    BenchmarkExpectation,
    CandidateExpectation,
    ConversationTurn,
)

LongMemEvalVariant = Literal["oracle", "s", "m"]

# A single-session-preference answer is a durable statement of user agency. The
# model may legitimately classify it as any of these closely related types
# rather than strictly ``preference``, so all of them count as a match.
_DURABLE_PREFERENCE_TYPES = [
    "preference",
    "decision",
    "principle",
    "constraint",
    "rationale",
]

_REPOSITORY = "xiaowu0162/longmemeval-cleaned"
_FILENAMES: dict[LongMemEvalVariant, str] = {
    "oracle": "longmemeval_oracle.json",
    "s": "longmemeval_s_cleaned.json",
    "m": "longmemeval_m_cleaned.json",
}


class LongMemEvalSource:
    """Read official LongMemEval JSON and produce extraction benchmark cases."""

    def __init__(
        self,
        path: Path,
        *,
        question_types: set[str] | None = None,
        limit: int | None = None,
    ) -> None:
        self._path = Path(path)
        self._question_types = question_types
        self._limit = limit

    def cases(self) -> Iterable[BenchmarkCase]:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("LongMemEval root must be a JSON list.")

        yielded = 0
        for item in payload:
            if not isinstance(item, dict):
                continue
            question_type = str(item.get("question_type") or "")
            if self._question_types and question_type not in self._question_types:
                continue
            case = self._to_case(item)
            if case is None:
                continue
            yield case
            yielded += 1
            if self._limit is not None and yielded >= self._limit:
                return

    def _to_case(self, item: dict[str, Any]) -> BenchmarkCase | None:
        question_id = str(item.get("question_id") or "").strip()
        question_type = str(item.get("question_type") or "").strip()
        sessions = item.get("haystack_sessions") or []
        session_ids = item.get("haystack_session_ids") or []
        session_dates = item.get("haystack_dates") or []
        if not question_id or not isinstance(sessions, list):
            return None

        turns: list[ConversationTurn] = []
        gold_user_evidence: list[str] = []
        gold_user_evidence_turn_ids: list[str] = []
        evidence_turn_ids: list[str] = []
        for session_index, session in enumerate(sessions):
            if not isinstance(session, list):
                continue
            session_id = (
                str(session_ids[session_index])
                if session_index < len(session_ids)
                else f"session-{session_index + 1}"
            )
            for turn_index, turn in enumerate(session):
                if not isinstance(turn, dict):
                    continue
                role = turn.get("role")
                content = turn.get("content")
                if role not in ("user", "assistant", "system"):
                    continue
                if not isinstance(content, str) or not content.strip():
                    continue
                turn_id = f"{session_id}:{turn_index + 1}"
                turns.append(
                    ConversationTurn(
                        id=turn_id,
                        role=role,
                        content=content,
                        language="English",
                    )
                )
                if turn.get("has_answer") is True:
                    evidence_turn_ids.append(turn_id)
                    if role == "user":
                        gold_user_evidence.append(content)
                        gold_user_evidence_turn_ids.append(turn_id)

        if not turns or not any(turn.role == "user" for turn in turns):
            return None

        expectation = None
        annotation_status = "unannotated"
        suite = "natural"
        if question_type == "single-session-preference" and gold_user_evidence:
            expectation = BenchmarkExpectation(
                max_issue_candidates=0,
                required=[
                    CandidateExpectation(
                        kind="memory",
                        memory_types=_DURABLE_PREFERENCE_TYPES,
                        evidence_source_texts=gold_user_evidence,
                        evidence_turn_ids=gold_user_evidence_turn_ids,
                    )
                ],
                notes=(
                    "LongMemEval marks a user turn as evidence for an implicit "
                    "or explicit preference. FatCat should extract a durable "
                    "preference-family memory grounded in that user turn or, at "
                    "least, the same source session."
                ),
            )
            annotation_status = "single_annotated"
            suite = "gold"

        return BenchmarkCase(
            id=f"longmemeval:{question_id}",
            suite=suite,
            annotation_status=annotation_status,
            language="English",
            turns=turns,
            expectation=expectation,
            metadata={
                "dataset": _REPOSITORY,
                "source_file": self._path.name,
                "question_id": question_id,
                "question_type": question_type,
                "question": item.get("question"),
                "answer": item.get("answer"),
                "question_date": item.get("question_date"),
                "session_ids": session_ids,
                "session_dates": session_dates,
                "answer_session_ids": item.get("answer_session_ids") or [],
                "evidence_turn_ids": evidence_turn_ids,
            },
        )


def download_longmemeval(
    variant: LongMemEvalVariant,
    output: Path,
    *,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Download a revision-pinned official file and write a provenance manifest."""

    filename = _FILENAMES[variant]
    revision = _repository_revision()
    url = (
        f"https://huggingface.co/datasets/{_REPOSITORY}/resolve/"
        f"{revision}/{filename}"
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    digest = hashlib.sha256()
    downloaded = 0

    request = Request(url, headers={"User-Agent": "fatcat-benchmark/0.1"})
    with urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
        total_header = response.headers.get("Content-Length")
        total = int(total_header) if total_header else None
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if on_progress is not None:
                on_progress(downloaded, total)
    temporary.replace(output)

    manifest = {
        "dataset": _REPOSITORY,
        "revision": revision,
        "variant": variant,
        "filename": filename,
        "bytes": downloaded,
        "sha256": digest.hexdigest(),
        "source_url": url,
    }
    manifest_path = output.with_name(output.name + ".meta.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _repository_revision() -> str:
    request = Request(
        f"https://huggingface.co/api/datasets/{_REPOSITORY}",
        headers={"User-Agent": "fatcat-benchmark/0.1"},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    revision = payload.get("sha")
    if not revision:
        raise RuntimeError("Hugging Face did not return a dataset revision.")
    return str(revision)
