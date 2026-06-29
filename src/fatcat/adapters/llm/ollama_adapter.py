"""Ollama-backed LLM adapter for real candidate extraction.

It asks a local Ollama model for strict JSON, validates it with Pydantic against
``LLMExtractionOut``, and converts the result into domain candidates. Malformed
output is reported via :class:`LLMExtractionError` and optionally logged to disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from fatcat.application.ports.llm_port import CandidateExtraction
from fatcat.domain.models import Issue, MemoryCandidate, MemoryItem, Project, RawInput
from fatcat.domain.policies import learning_issue_has_sufficient_evidence

from .errors import LLMExtractionError
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schema import LLMExtractionOut


class OllamaAdapter:
    """Extract memory candidates using a local Ollama model."""

    def __init__(
        self,
        model: str = "qwen3:8b",
        *,
        host: str | None = None,
        client: Any | None = None,
        failure_log_path: Path | None = None,
        temperature: float = 0.0,
        think: bool | Literal["low", "medium", "high"] | None = False,
    ) -> None:
        self._model = model
        self._failure_log_path = (
            Path(failure_log_path) if failure_log_path else None
        )
        self._temperature = temperature
        self._think = think
        if client is not None:
            self._client = client
        else:
            # Imported here so the dependency is only required when actually used.
            from ollama import Client

            self._client = Client(host=host) if host else Client()

    def extract_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
        known_issues: list[Issue] | None = None,
    ) -> CandidateExtraction:
        user_prompt = build_user_prompt(
            raw_input,
            project,
            known_context,
            known_issues,
        )
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                # A concrete schema prevents smaller models from inventing enum
                # values such as ``interest`` and failing the entire extraction.
                format=LLMExtractionOut.model_json_schema(),
                # Candidate extraction benefits from deterministic classification,
                # not a long hidden reasoning trace. This is particularly important
                # for Qwen3, where thinking mode materially increases latency.
                think=self._think,
                options={"temperature": self._temperature},
            )
        except Exception as exc:  # noqa: BLE001 - surface transport errors uniformly
            raise LLMExtractionError(
                f"Ollama request failed: {exc}", fatal=_is_fatal_transport_error(exc)
            ) from exc

        content = _response_content(response)
        return self._parse(content, raw_input, project)

    def extract_memory_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
    ) -> list[MemoryCandidate]:
        """Compatibility wrapper for callers using the v1 adapter API."""

        return self.extract_candidates(
            raw_input,
            project,
            known_context,
        ).memory_candidates

    def _parse(
        self,
        content: str,
        raw_input: RawInput,
        project: Project | None,
    ) -> CandidateExtraction:
        try:
            data = json.loads(content)
            extraction = LLMExtractionOut.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            self._log_failure(content)
            raise LLMExtractionError(
                f"Could not parse LLM output as valid candidates: {exc}",
                raw_output=content,
            ) from exc

        project_id = project.id if project is not None else raw_input.project_id
        memory_candidates = []
        for item in extraction.memory_candidates:
            candidate = item.to_candidate(
                raw_input=raw_input, project_id=project_id
            )
            # A user memory must rest on user-authored evidence. If the model
            # cited evidence but none survived role and verbatim validation, the
            # claim is unfounded (e.g. grounded only in assistant text).
            if item.evidence and not candidate.evidence:
                continue
            memory_candidates.append(candidate)
        issue_candidates = [
            item.to_candidate(
                raw_input=raw_input,
                project_id=project_id,
                memory_candidates=memory_candidates,
            )
            for item in extraction.issue_candidates
        ]
        # Enforce the durable-question evidence bar at the extraction boundary so
        # every caller (capture use cases and benchmarks alike) sees the same
        # filtering. Speculative questions backed by a single weak signal, or by
        # only assistant text removed during evidence validation, are dropped.
        issue_candidates = [
            candidate
            for candidate in issue_candidates
            if learning_issue_has_sufficient_evidence(candidate)
        ]
        return CandidateExtraction(
            memory_candidates=memory_candidates,
            issue_candidates=issue_candidates,
        )

    def _log_failure(self, content: str) -> None:
        if self._failure_log_path is None:
            return
        self._failure_log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        with self._failure_log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"=== {stamp} ===\n{content}\n\n")


def _is_fatal_transport_error(exc: Exception) -> bool:
    """Heuristic: is this an Ollama error that won't fix itself next turn?

    Missing models (HTTP 404) and connection failures are configuration-level
    problems, so callers should stop rather than skip every single turn.
    """

    status = getattr(exc, "status_code", None)
    if status == 404:
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    text = (type(exc).__name__ + " " + str(exc)).lower()
    return any(
        marker in text
        for marker in ("not found", "connection", "refused", "max retries", "timeout")
    )


def _response_content(response: Any) -> str:
    """Extract the message content from an ollama response (object or dict)."""

    message = getattr(response, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content is not None:
            return content
    if isinstance(response, dict):
        return response.get("message", {}).get("content", "")
    raise LLMExtractionError("Unexpected Ollama response shape.")
