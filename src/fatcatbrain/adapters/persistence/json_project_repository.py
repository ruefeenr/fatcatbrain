"""JSON-backed project repository.

Each project lives in ``<projects_dir>/<project_id>/project.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fatcatbrain.domain.models import Project


class JsonProjectRepository:
    """Stores projects as one ``project.json`` per project directory."""

    def __init__(self, projects_dir: Path) -> None:
        self._projects_dir = Path(projects_dir)

    def _project_file(self, project_id: str) -> Path:
        return self._projects_dir / project_id / "project.json"

    def save(self, project: Project) -> None:
        path = self._project_file(project.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, project_id: str) -> Project | None:
        path = self._project_file(project_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Project.model_validate(data)

    def list_all(self) -> list[Project]:
        if not self._projects_dir.exists():
            return []
        projects: list[Project] = []
        for child in sorted(self._projects_dir.iterdir()):
            project_file = child / "project.json"
            if project_file.exists():
                data = json.loads(project_file.read_text(encoding="utf-8"))
                projects.append(Project.model_validate(data))
        return projects
