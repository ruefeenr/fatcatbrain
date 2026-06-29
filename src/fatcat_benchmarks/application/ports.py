"""Inbound data boundary for benchmark conversations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from fatcat_benchmarks.domain.models import BenchmarkCase


@runtime_checkable
class BenchmarkCaseSource(Protocol):
    def cases(self) -> Iterable[BenchmarkCase]:
        """Yield validated benchmark conversations."""
        ...
