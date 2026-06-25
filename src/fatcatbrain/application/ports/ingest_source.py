"""Ingest source port: passive input channels that feed the capture pipeline.

A source is anything that can be polled for *new* text the user produced while
working (AI chat transcripts, clipboard, etc.). Sources are responsible for their
own bookkeeping so that ``poll`` only ever returns previously unseen text.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IngestSource(Protocol):
    """A pollable source of new user-authored text."""

    def describe(self) -> str:
        """A short human-readable description of what is being watched."""
        ...

    def poll(self) -> list[str]:
        """Return new text chunks since the last poll (oldest first)."""
        ...
