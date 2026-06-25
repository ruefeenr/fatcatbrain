"""Composition root: wire ports to concrete adapters based on settings.

This is the only place that knows about both the application and the adapters. It
keeps the wiring out of the CLI and out of the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatcatbrain.adapters.llm import FakeLLMAdapter
from fatcatbrain.adapters.persistence import (
    JsonProjectRepository,
    JsonlInboxRepository,
    JsonlMemoryRepository,
    JsonlRawInputRepository,
    ScopedMemoryRepository,
)
from fatcatbrain.application.ports import (
    InboxRepository,
    IngestSource,
    LLMPort,
    MemoryRepository,
    ProjectRepository,
    RawInputRepository,
)
from fatcatbrain.application.use_cases import (
    CaptureBrainDump,
    ReviewMemoryCandidate,
    SaveMemoryItem,
)
from fatcatbrain.config import Settings


@dataclass
class Container:
    """Assembled dependencies for the active project."""

    settings: Settings
    project_id: str
    llm: LLMPort
    memory_repo: MemoryRepository
    raw_input_repo: RawInputRepository
    inbox_repo: InboxRepository
    project_repo: ProjectRepository

    def capture_brain_dump(self) -> CaptureBrainDump:
        return CaptureBrainDump(
            self.llm,
            self.raw_input_repo,
            self.inbox_repo,
            memory_repo=self.memory_repo,
            project_repo=self.project_repo,
        )

    def passive_capture(self) -> CaptureBrainDump:
        """Capture variant for passive listening: no raw storage, noise filtered."""

        return CaptureBrainDump(
            self.llm,
            self.raw_input_repo,
            self.inbox_repo,
            memory_repo=self.memory_repo,
            project_repo=self.project_repo,
            store_raw_input=False,
            min_confidence=self.settings.min_confidence,
        )

    def review_memory_candidate(self) -> ReviewMemoryCandidate:
        return ReviewMemoryCandidate(self.inbox_repo, self.memory_repo)

    def save_memory_item(self) -> SaveMemoryItem:
        return SaveMemoryItem(self.memory_repo, self.raw_input_repo)


def _build_llm(settings: Settings) -> LLMPort:
    if settings.llm == "ollama":
        # Imported lazily so the fake path never requires the ollama client.
        from fatcatbrain.adapters.llm.ollama_adapter import OllamaAdapter

        failure_log = (
            settings.paths.project_dir(settings.project_id) / "llm_failures.log"
        )
        return OllamaAdapter(
            model=settings.ollama_model,
            host=settings.ollama_host,
            failure_log_path=failure_log,
        )
    return FakeLLMAdapter()


def build_ingest_source(
    settings: Settings, transcripts_dir=None
) -> IngestSource | None:
    """Build the passive ingest source, or None if no source is configured."""

    directory = transcripts_dir or settings.transcripts_dir
    if directory is None:
        return None
    from fatcatbrain.adapters.ingest import CursorTranscriptSource

    return CursorTranscriptSource(
        transcripts_dir=directory,
        state_path=settings.paths.watch_state_file,
    )


def build_container(settings: Settings) -> Container:
    paths = settings.paths
    project_id = settings.project_id
    memory_repo = ScopedMemoryRepository(
        JsonlMemoryRepository(paths.global_memory_items_file),
        JsonlMemoryRepository(paths.memory_items_file(project_id)),
    )
    return Container(
        settings=settings,
        project_id=project_id,
        llm=_build_llm(settings),
        memory_repo=memory_repo,
        raw_input_repo=JsonlRawInputRepository(paths.raw_inputs_file(project_id)),
        inbox_repo=JsonlInboxRepository(paths.inbox_file(project_id)),
        project_repo=JsonProjectRepository(paths.projects_dir),
    )
