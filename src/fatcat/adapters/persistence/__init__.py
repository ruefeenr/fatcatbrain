"""File-based persistence adapters (JSONL / JSON)."""

from .json_project_repository import JsonProjectRepository
from .jsonl_inbox_repository import JsonlInboxRepository
from .jsonl_issue_candidate_repository import JsonlIssueCandidateRepository
from .jsonl_issue_repository import JsonlIssueRepository
from .jsonl_memory_repository import JsonlMemoryRepository
from .jsonl_raw_input_repository import JsonlRawInputRepository
from .jsonl_session_repository import JsonlSessionRepository
from .scoped_issue_repository import ScopedIssueRepository
from .scoped_memory_repository import ScopedMemoryRepository

__all__ = [
    "JsonProjectRepository",
    "JsonlInboxRepository",
    "JsonlIssueCandidateRepository",
    "JsonlIssueRepository",
    "JsonlMemoryRepository",
    "JsonlRawInputRepository",
    "JsonlSessionRepository",
    "ScopedIssueRepository",
    "ScopedMemoryRepository",
]
