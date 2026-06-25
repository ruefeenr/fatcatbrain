"""In-memory fakes used by application-layer tests."""

from __future__ import annotations

from fatcatbrain.domain.models import (
    MemoryCandidate,
    MemoryItem,
    Project,
    RawInput,
)
from fatcatbrain.domain.policies import normalize_memory_content
from fatcatbrain.domain.value_objects import GLOBAL_SCOPE


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

    def list_pending(self) -> list[MemoryCandidate]:
        return [c for c in self.candidates if not c.reviewed]

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        return next(
            (c for c in self.candidates if c.id == candidate_id and not c.reviewed),
            None,
        )

    def mark_reviewed(self, candidate_id: str) -> None:
        for c in self.candidates:
            if c.id == candidate_id:
                c.reviewed = True


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}

    def save(self, project: Project) -> None:
        self.projects[project.id] = project

    def get(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def list_all(self) -> list[Project]:
        return list(self.projects.values())


class StubLLM:
    """Returns a preconfigured list of candidates regardless of input."""

    def __init__(self, candidates: list[MemoryCandidate]) -> None:
        self._candidates = candidates
        self.calls: list[RawInput] = []

    def extract_memory_candidates(
        self,
        raw_input: RawInput,
        project: Project | None = None,
        known_context: list[MemoryItem] | None = None,
    ) -> list[MemoryCandidate]:
        self.calls.append(raw_input)
        # Return fresh copies so callers can mutate (e.g. set project_id) safely.
        return [c.model_copy(deep=True) for c in self._candidates]
