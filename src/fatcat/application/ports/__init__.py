"""Ports: the hexagonal boundary.

Use cases depend only on these ``Protocol`` interfaces; concrete adapters live in
``fatcat.adapters`` and are wired up in the composition root.
"""

from .inbox_repository import InboxRepository
from .conversation_session_source import (
    ConversationSessionDocument,
    ConversationSessionSource,
)
from .ingest_source import IngestSource
from .issue_candidate_repository import IssueCandidateRepository
from .issue_repository import IssueRepository
from .llm_port import CandidateExtraction, LLMPort
from .memory_repository import MemoryRepository
from .project_repository import ProjectRepository
from .raw_input_repository import RawInputRepository
from .session_repository import SessionRepository

__all__ = [
    "InboxRepository",
    "ConversationSessionDocument",
    "ConversationSessionSource",
    "IngestSource",
    "IssueCandidateRepository",
    "IssueRepository",
    "CandidateExtraction",
    "LLMPort",
    "MemoryRepository",
    "ProjectRepository",
    "RawInputRepository",
    "SessionRepository",
]
