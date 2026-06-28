"""Shared test configuration."""

from __future__ import annotations

import pytest

from .deterministic_llm import DeterministicTestLLM


@pytest.fixture(autouse=True)
def use_deterministic_test_llm(monkeypatch):
    """Keep CLI/application tests offline without a production fake adapter."""

    monkeypatch.setattr(
        "fatcat.composition._build_llm",
        lambda settings: DeterministicTestLLM(),
    )
