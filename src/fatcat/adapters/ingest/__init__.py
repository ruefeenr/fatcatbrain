"""Ingest adapters: passive input sources for the capture pipeline."""

from .cursor_transcript_source import CursorTranscriptSource, read_user_texts

__all__ = ["CursorTranscriptSource", "read_user_texts"]
