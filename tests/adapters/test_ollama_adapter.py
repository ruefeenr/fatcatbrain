"""Tests for the Ollama adapter using a fake chat client (no real server)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fatcatbrain.adapters.llm.errors import LLMExtractionError
from fatcatbrain.adapters.llm.ollama_adapter import OllamaAdapter
from fatcatbrain.domain.models import Project, RawInput


class FakeClient:
    """Minimal stand-in for ollama.Client that returns a canned response."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.last_kwargs: dict | None = None

    def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return {"message": {"content": self._content}}


class BoomClient:
    def chat(self, **kwargs):
        raise ConnectionError("server down")


class ModelNotFoundClient:
    def chat(self, **kwargs):
        exc = RuntimeError("model 'gpt-oss' not found")
        exc.status_code = 404
        raise exc


def _raw() -> RawInput:
    return RawInput(content="I prefer FastAPI for small APIs.", source="brain_dump")


def test_ollama_parses_valid_json():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "content": "User prefers FastAPI for small APIs.",
                    "memory_type": "preference",
                    "suggested_scope": "global",
                    "confidence": 0.9,
                    "sensitivity": "low",
                    "reason": "stated directly",
                }
            ]
        }
    )
    raw = _raw()
    adapter = OllamaAdapter(client=FakeClient(payload))
    candidates = adapter.extract_memory_candidates(raw)
    assert len(candidates) == 1
    assert candidates[0].memory_type == "preference"
    assert candidates[0].source_input_id == raw.id
    assert candidates[0].confidence == 0.9


def test_ollama_sets_project_id_and_scope():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "content": "Keep the architecture lightweight.",
                    "memory_type": "project_context",
                    "suggested_scope": "project:demo",
                    "confidence": 0.8,
                    "sensitivity": "low",
                    "reason": "core direction",
                }
            ]
        }
    )
    adapter = OllamaAdapter(client=FakeClient(payload))
    candidates = adapter.extract_memory_candidates(
        _raw(), project=Project(id="demo", name="Demo")
    )
    assert candidates[0].project_id == "demo"


def test_ollama_empty_candidates():
    adapter = OllamaAdapter(client=FakeClient('{"candidates": []}'))
    assert adapter.extract_memory_candidates(_raw()) == []


def test_ollama_invalid_json_raises_and_logs(tmp_path: Path):
    log = tmp_path / "fail.log"
    adapter = OllamaAdapter(
        client=FakeClient("this is not json"), failure_log_path=log
    )
    with pytest.raises(LLMExtractionError) as exc_info:
        adapter.extract_memory_candidates(_raw())
    assert exc_info.value.raw_output == "this is not json"
    assert log.exists()
    assert "this is not json" in log.read_text(encoding="utf-8")


def test_ollama_schema_violation_raises(tmp_path: Path):
    bad = json.dumps(
        {"candidates": [{"content": "x", "memory_type": "banana", "confidence": 2}]}
    )
    adapter = OllamaAdapter(client=FakeClient(bad))
    with pytest.raises(LLMExtractionError):
        adapter.extract_memory_candidates(_raw())


def test_ollama_transport_error_wrapped():
    adapter = OllamaAdapter(client=BoomClient())
    with pytest.raises(LLMExtractionError):
        adapter.extract_memory_candidates(_raw())


def test_ollama_connection_error_is_fatal():
    adapter = OllamaAdapter(client=BoomClient())
    with pytest.raises(LLMExtractionError) as exc_info:
        adapter.extract_memory_candidates(_raw())
    assert exc_info.value.fatal is True


def test_ollama_model_not_found_is_fatal():
    adapter = OllamaAdapter(client=ModelNotFoundClient())
    with pytest.raises(LLMExtractionError) as exc_info:
        adapter.extract_memory_candidates(_raw())
    assert exc_info.value.fatal is True
