"""JSONL adapter for confirmed issues."""

from __future__ import annotations

from pathlib import Path

from fatcat.domain.models import Issue

from .jsonl import append_jsonl, read_jsonl, write_jsonl


class JsonlIssueRepository:
    """Stores learning issues by id and supports lifecycle updates."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def save(self, issue: Issue) -> None:
        issues = self.list_all()
        for index, existing in enumerate(issues):
            if existing.id == issue.id:
                issues[index] = issue
                write_jsonl(
                    self._path,
                    [stored.model_dump(mode="json") for stored in issues],
                )
                return
        append_jsonl(self._path, issue.model_dump(mode="json"))

    def get(self, issue_id: str) -> Issue | None:
        return next((issue for issue in self.list_all() if issue.id == issue_id), None)

    def list_all(self) -> list[Issue]:
        return [Issue.model_validate(record) for record in read_jsonl(self._path)]

    def list_by_project(self, project_id: str) -> list[Issue]:
        return [
            issue
            for issue in self.list_all()
            if issue.scope.level == "project"
            and issue.scope.reference_id == project_id
        ]

    def list_global(self) -> list[Issue]:
        """Return shared learning issues (global and domain scoped)."""

        return [issue for issue in self.list_all() if issue.scope.level != "project"]
