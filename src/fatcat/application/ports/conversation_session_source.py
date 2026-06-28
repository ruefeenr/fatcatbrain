"""Port for discovering an external conversation session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConversationSessionDocument:
    """User-authored content from one external conversation."""

    id: str
    title: str
    source_ref: str
    updated_at: datetime
    user_messages: list[str] = field(default_factory=list)
    cwd: str | None = None


@runtime_checkable
class ConversationSessionSource(Protocol):
    def latest(self) -> ConversationSessionDocument | None:
        """Return the most recently active external conversation."""
        ...
