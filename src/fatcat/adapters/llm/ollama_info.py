"""Read-only helpers to inspect a local Ollama install (used by the setup flow).

Kept separate from the adapter so the interactive setup can probe Ollama without
constructing a full extraction adapter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaStatus:
    """Result of probing the local Ollama server."""

    reachable: bool
    models: list[str]
    error: str | None = None


def _model_name(entry) -> str | None:
    """Extract a model name from an ollama list entry (object or dict)."""

    for attr in ("model", "name"):
        value = getattr(entry, attr, None)
        if value:
            return str(value)
    if isinstance(entry, dict):
        return entry.get("model") or entry.get("name")
    return None


def probe_ollama(host: str | None = None) -> OllamaStatus:
    """Check whether Ollama is reachable and list installed models."""

    try:
        from ollama import Client

        client = Client(host=host) if host else Client()
        response = client.list()
    except Exception as exc:  # noqa: BLE001 - any failure means "not usable"
        return OllamaStatus(reachable=False, models=[], error=str(exc))

    raw = getattr(response, "models", None)
    if raw is None and isinstance(response, dict):
        raw = response.get("models", [])
    raw = raw or []

    models = [name for entry in raw if (name := _model_name(entry))]
    return OllamaStatus(reachable=True, models=models)
