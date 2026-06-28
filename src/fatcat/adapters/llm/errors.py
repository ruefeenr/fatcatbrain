"""LLM adapter errors."""

from __future__ import annotations


class LLMExtractionError(RuntimeError):
    """Raised when an LLM response cannot be parsed into valid candidates.

    The offending raw output is attached so callers can show or persist it.
    ``fatal`` marks permanent, configuration-level problems (e.g. the model is
    not installed or the server is down) that won't recover by retrying the next
    turn, so callers should stop instead of skipping turn after turn.
    """

    def __init__(
        self, message: str, *, raw_output: str = "", fatal: bool = False
    ) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.fatal = fatal
