"""Ports: the hexagonal boundary.

Use cases depend only on these ``Protocol`` interfaces; concrete adapters live in
``fatcat.adapters`` and are wired up in the composition root.
"""

from .inbox_repository import InboxRepository
from .ingest_source import IngestSource
from .llm_port import LLMPort
from .memory_repository import MemoryRepository
from .project_repository import ProjectRepository
from .raw_input_repository import RawInputRepository

__all__ = [
    "InboxRepository",
    "IngestSource",
    "LLMPort",
    "MemoryRepository",
    "ProjectRepository",
    "RawInputRepository",
]
