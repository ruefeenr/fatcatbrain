"""Routes confirmed issues to global or active-project JSONL stores."""

from __future__ import annotations

from fatcat.domain.models import Issue

from .jsonl_issue_repository import JsonlIssueRepository


class ScopedIssueRepository:
    """Expose global and active-project issues through one repository port."""

    def __init__(
        self,
        global_repo: JsonlIssueRepository,
        project_repo: JsonlIssueRepository,
    ) -> None:
        self._global = global_repo
        self._project = project_repo

    def _target(self, issue: Issue) -> JsonlIssueRepository:
        return self._project if issue.scope.level == "project" else self._global

    def save(self, issue: Issue) -> None:
        self._target(issue).save(issue)

    def get(self, issue_id: str) -> Issue | None:
        return self._project.get(issue_id) or self._global.get(issue_id)

    def list_all(self) -> list[Issue]:
        return self._global.list_all() + self._project.list_all()

    def list_by_project(self, project_id: str) -> list[Issue]:
        return self._project.list_by_project(project_id)

    def list_global(self) -> list[Issue]:
        return self._global.list_global()
