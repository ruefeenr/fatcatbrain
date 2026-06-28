"""In-memory fakes used by application-layer tests."""

from __future__ import annotations

from fatcat.application.ports import CandidateExtraction
from fatcat.domain.models import (
    Issue,
    IssueCandidate,
    MemoryCandidate,
    MemoryItem,
    Project,
    RawInput,
    Session,
)
from fatcat.domain.policies import normalize_memory_content, transition_issue_candidate
from fatcat.domain.value_objects import CandidateStatus, GLOBAL_SCOPE


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self.items: list[MemoryItem] = []

    def save(self, item: MemoryItem) -> None:
        if self.find_duplicate(item.content, item.project_id) is not None:
            return
        self.items.append(item)

    def find_duplicate(
        self, content: str, project_id: str | None
    ) -> MemoryItem | None:
        target = normalize_memory_content(content)
        for item in self.items:
            if (
                item.project_id == project_id
                and normalize_memory_content(item.content) == target
            ):
                return item
        return None

    def find_by_source_candidate_id(
        self, candidate_id: str
    ) -> MemoryItem | None:
        return next(
            (
                item
                for item in self.items
                if candidate_id in item.source_candidate_ids
            ),
            None,
        )

    def list_by_project(self, project_id: str) -> list[MemoryItem]:
        return [i for i in self.items if i.project_id == project_id]

    def list_global(self) -> list[MemoryItem]:
        return [i for i in self.items if i.scope == GLOBAL_SCOPE]

    def list_all(self) -> list[MemoryItem]:
        return list(self.items)


class InMemoryRawInputRepository:
    def __init__(self) -> None:
        self.items: list[RawInput] = []

    def save(self, raw_input: RawInput) -> None:
        self.items.append(raw_input)

    def get(self, raw_input_id: str) -> RawInput | None:
        return next((r for r in self.items if r.id == raw_input_id), None)

    def list_all(self) -> list[RawInput]:
        return list(self.items)


class InMemoryInboxRepository:
    def __init__(self) -> None:
        self.candidates: list[MemoryCandidate] = []

    def add_candidates(self, candidates: list[MemoryCandidate]) -> None:
        self.candidates.extend(candidates)

    def list_pending(
        self, session_id: str | None = None
    ) -> list[MemoryCandidate]:
        candidates = [
            candidate
            for candidate in self.candidates
            if not candidate.reviewed
            and candidate.status in ("detected", "candidate")
        ]
        if session_id is None:
            return candidates
        return [
            candidate
            for candidate in candidates
            if candidate.session_id == session_id
        ]

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        return next(
            (c for c in self.candidates if c.id == candidate_id and not c.reviewed),
            None,
        )

    def mark_reviewed(
        self,
        candidate_id: str,
        status: CandidateStatus = "confirmed",
    ) -> None:
        for c in self.candidates:
            if c.id == candidate_id:
                c.reviewed = True
                c.status = status


class InMemoryIssueCandidateRepository:
    def __init__(self) -> None:
        self.candidates: list[IssueCandidate] = []

    def add_candidates(self, candidates: list[IssueCandidate]) -> None:
        self.candidates.extend(candidates)

    def list_pending(self, session_id: str | None = None) -> list[IssueCandidate]:
        candidates = [
            candidate
            for candidate in self.candidates
            if candidate.status in ("detected", "candidate")
        ]
        if session_id is None:
            return candidates
        return [candidate for candidate in candidates if candidate.session_id == session_id]

    def list_deferred(self, session_id: str | None = None) -> list[IssueCandidate]:
        candidates = [
            candidate for candidate in self.candidates if candidate.status == "deferred"
        ]
        if session_id is None:
            return candidates
        return [candidate for candidate in candidates if candidate.session_id == session_id]

    def get(self, candidate_id: str) -> IssueCandidate | None:
        return next(
            (candidate for candidate in self.candidates if candidate.id == candidate_id),
            None,
        )

    def set_status(self, candidate_id: str, status: CandidateStatus) -> None:
        for index, candidate in enumerate(self.candidates):
            if candidate.id == candidate_id:
                self.candidates[index] = transition_issue_candidate(candidate, status)
                return
        if self.get(candidate_id) is None:
            raise KeyError(candidate_id)


class InMemoryIssueRepository:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def save(self, issue: Issue) -> None:
        for index, existing in enumerate(self.issues):
            if existing.id == issue.id:
                self.issues[index] = issue
                return
        self.issues.append(issue)

    def get(self, issue_id: str) -> Issue | None:
        return next((issue for issue in self.issues if issue.id == issue_id), None)

    def list_all(self) -> list[Issue]:
        return list(self.issues)

    def list_by_project(self, project_id: str) -> list[Issue]:
        return [
            issue
            for issue in self.issues
            if issue.scope.level == "project"
            and issue.scope.reference_id == project_id
        ]

    def list_global(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.scope.level != "project"]


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}

    def save(self, project: Project) -> None:
        self.projects[project.id] = project

    def get(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def list_all(self) -> list[Project]:
        return list(self.projects.values())


class InMemorySessionRepository:
    def __init__(self) -> None:
        self.sessions: list[Session] = []

    def save(self, session: Session) -> None:
        for index, existing in enumerate(self.sessions):
            if existing.id == session.id:
                self.sessions[index] = session
                return
        self.sessions.append(session)

    def get(self, session_id: str) -> Session | None:
        return next(
            (session for session in self.sessions if session.id == session_id),
            None,
        )

    def list_all(self) -> list[Session]:
        return list(self.sessions)

    def list_by_project(self, project_id: str) -> list[Session]:
        return [
            session
            for session in self.sessions
            if session.project_id == project_id
        ]


class StubLLM:
    """Returns a preconfigured extraction regardless of input."""

    def __init__(
        self,
        candidates: list[MemoryCandidate],
        issue_candidates: list[IssueCandidate] | None = None,
    ) -> None:
        self._candidates = candidates
        self._issue_candidates = issue_candidates or []
        self.calls: list[RawInput] = []

    def extract_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
        known_issues: list[Issue] | None = None,
    ) -> CandidateExtraction:
        self.calls.append(raw_input)
        return CandidateExtraction(
            memory_candidates=[
                candidate.model_copy(deep=True) for candidate in self._candidates
            ],
            issue_candidates=[
                candidate.model_copy(deep=True) for candidate in self._issue_candidates
            ],
        )
