"""Raw input repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fatcatbrain.domain.models import RawInput


@runtime_checkable
class RawInputRepository(Protocol):
    """Stores raw, unprocessed user inputs for traceability."""

    def save(self, raw_input: RawInput) -> None:
        ...

    def get(self, raw_input_id: str) -> RawInput | None:
        ...

    def list_all(self) -> list[RawInput]:
        ...
