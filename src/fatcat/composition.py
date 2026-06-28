"""Composition root: wire ports to concrete adapters based on settings.

This is the only place that knows about both the application and the adapters. It
keeps the wiring out of the CLI and out of the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatcat.adapters.persistence import (
    JsonProjectRepository,
    JsonlInboxRepository,
    JsonlIssueCandidateRepository,
    JsonlIssueRepository,
    JsonlMemoryRepository,
    JsonlRawInputRepository,
    JsonlSessionRepository,
    ScopedIssueRepository,
    ScopedMemoryRepository,
)
from fatcat.application.ports import (
    InboxRepository,
    IngestSource,
    IssueCandidateRepository,
    IssueRepository,
    LLMPort,
    MemoryRepository,
    ProjectRepository,
    RawInputRepository,
    SessionRepository,
)
from fatcat.application.use_cases import (
    CaptureBrainDump,
    ReviewIssueCandidate,
    ReviewMemoryCandidate,
    ReviewSession,
    SaveMemoryItem,
    SessionLifecycle,
)
from fatcat.config import Settings


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
    issue_candidate_repo: IssueCandidateRepository
    issue_repo: IssueRepository
    session_repo: SessionRepository

    def capture_brain_dump(self) -> CaptureBrainDump:
        return CaptureBrainDump(
            self.llm,
            self.raw_input_repo,
            self.inbox_repo,
            memory_repo=self.memory_repo,
            project_repo=self.project_repo,
            issue_candidate_repo=self.issue_candidate_repo,
            issue_repo=self.issue_repo,
        )

    def passive_capture(self) -> CaptureBrainDump:
        """Capture variant for passive listening: no raw storage, noise filtered."""

        return CaptureBrainDump(
            self.llm,
            self.raw_input_repo,
            self.inbox_repo,
            memory_repo=self.memory_repo,
            project_repo=self.project_repo,
            issue_candidate_repo=self.issue_candidate_repo,
            issue_repo=self.issue_repo,
            store_raw_input=False,
            min_confidence=self.settings.min_confidence,
        )

    def review_memory_candidate(self) -> ReviewMemoryCandidate:
        return ReviewMemoryCandidate(self.inbox_repo, self.memory_repo)

    def review_issue_candidate(self) -> ReviewIssueCandidate:
        return ReviewIssueCandidate(
            self.issue_candidate_repo,
            self.issue_repo,
            self.memory_repo,
        )

    def save_memory_item(self) -> SaveMemoryItem:
        return SaveMemoryItem(self.memory_repo, self.raw_input_repo)

    def session_lifecycle(self) -> SessionLifecycle:
        return SessionLifecycle(self.session_repo)

    def review_session(self) -> ReviewSession:
        return ReviewSession(
            self.session_repo,
            self.inbox_repo,
            self.issue_candidate_repo,
        )


def _build_llm(settings: Settings) -> LLMPort:
    if settings.llm != "ollama":
        raise ValueError(
            f"Unsupported LLM adapter {settings.llm!r}; FatCat requires Ollama."
        )

    from fatcat.adapters.llm.ollama_adapter import OllamaAdapter

    failure_log = (
        settings.paths.project_dir(settings.project_id) / "llm_failures.log"
    )
    return OllamaAdapter(
        model=settings.ollama_model,
        host=settings.ollama_host,
        failure_log_path=failure_log,
    )


def build_ingest_source(
    settings: Settings, transcripts_dir=None
) -> IngestSource | None:
    """Build the passive ingest source, or None if no source is configured."""

    directory = transcripts_dir or settings.transcripts_dir
    if directory is None:
        return None
    from fatcat.adapters.ingest import CursorTranscriptSource

    return CursorTranscriptSource(
        transcripts_dir=directory,
        state_path=settings.paths.watch_state_file,
    )


def build_codex_session_source(codex_home=None):
    """Build the local Codex conversation discovery adapter."""

    from fatcat.adapters.ingest import CodexSessionSource

    return CodexSessionSource(codex_home=codex_home)


def build_codex_ingest_source(settings: Settings, codex_home=None) -> IngestSource | None:
    """Watch the latest Codex rollout, fixed to that session for this run."""

    from fatcat.adapters.ingest import CodexTranscriptSource

    document = build_codex_session_source(codex_home=codex_home).latest()
    if document is None:
        return None
    return CodexTranscriptSource(
        rollout_path=document.source_ref,
        state_path=settings.paths.watch_state_file,
        title=document.title,
    )


def build_container(settings: Settings) -> Container:
    paths = settings.paths
    project_id = settings.project_id
    memory_repo = ScopedMemoryRepository(
        JsonlMemoryRepository(paths.global_memory_items_file),
        JsonlMemoryRepository(paths.memory_items_file(project_id)),
    )
    issue_repo = ScopedIssueRepository(
        JsonlIssueRepository(paths.global_issues_file),
        JsonlIssueRepository(paths.issues_file(project_id)),
    )
    return Container(
        settings=settings,
        project_id=project_id,
        llm=_build_llm(settings),
        memory_repo=memory_repo,
        raw_input_repo=JsonlRawInputRepository(paths.raw_inputs_file(project_id)),
        inbox_repo=JsonlInboxRepository(paths.inbox_file(project_id)),
        project_repo=JsonProjectRepository(paths.projects_dir),
        issue_candidate_repo=JsonlIssueCandidateRepository(
            paths.issue_candidates_file(project_id)
        ),
        issue_repo=issue_repo,
        session_repo=JsonlSessionRepository(paths.sessions_file(project_id)),
    )
