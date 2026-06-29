"""Local JSONL benchmark fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from fatcat_benchmarks.domain.models import BenchmarkCase


class JsonlBenchmarkSource:
    def __init__(self, paths: list[Path] | tuple[Path, ...]) -> None:
        self._paths = [Path(path) for path in paths]

    def cases(self) -> Iterable[BenchmarkCase]:
        for path in self._paths:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        yield BenchmarkCase.model_validate_json(line)
                    except Exception as exc:  # noqa: BLE001 - add fixture location
                        raise ValueError(
                            f"Invalid benchmark case at {path}:{line_number}: {exc}"
                        ) from exc


def write_cases(path: Path, cases: Iterable[BenchmarkCase]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(case.model_dump_json(exclude_none=True) + "\n")
            count += 1
    return count
