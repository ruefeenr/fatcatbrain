"""Ingest adapters: passive input sources for the capture pipeline."""

from .codex_session_source import CodexSessionSource, CodexTranscriptSource
from .cursor_transcript_source import (
    CursorTranscriptSource,
    latest_transcript_file,
    read_user_texts,
)

__all__ = [
    "CodexSessionSource",
    "CodexTranscriptSource",
    "CursorTranscriptSource",
    "latest_transcript_file",
    "read_user_texts",
]
