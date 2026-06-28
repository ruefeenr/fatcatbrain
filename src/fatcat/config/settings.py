"""Settings and storage path resolution, driven by environment variables.

Environment variables:
    FATCAT_HOME          Storage root directory       (default: ~/.fatcat)
    FATCAT_LLM           "fake" or "ollama"           (default: fake)
    FATCAT_OLLAMA_MODEL  Ollama model name            (default: llama3.1)
    FATCAT_OLLAMA_HOST   Ollama host URL              (default: ollama's own default)
    FATCAT_PROJECT       Active project id            (default: "default")
    FATCAT_TRANSCRIPTS_DIR  Dir to watch in listen mode (default: none)
    FATCAT_MIN_CONFIDENCE   Min candidate confidence in listen mode (default: 0.6)
    FATCAT_LISTEN_INTERVAL  Poll interval seconds in listen mode    (default: 10)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECT_ID = "default"


def find_project_root(start: Path | None = None) -> Path:
    """Return the project root for ``start``: the nearest ancestor with a ``.git``
    directory, or ``start`` itself when none is found."""

    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return start


def slugify_project(name: str) -> str:
    """Turn a folder name into a stable, filesystem-safe project id."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or DEFAULT_PROJECT_ID


def detect_project_id(start: Path | None = None) -> str:
    """Best-effort project id derived from the current working directory."""

    return slugify_project(find_project_root(start).name)
DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_LISTEN_INTERVAL = 10.0


def _default_home() -> Path:
    return Path.home() / ".fatcat"


def _as_float(value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _load_config_file(home: Path) -> dict:
    """Load the persisted config.json, or {} if missing/unreadable."""

    path = home / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class StoragePaths:
    """Resolved filesystem locations for a given storage root."""

    home: Path

    @property
    def config_file(self) -> Path:
        return self.home / "config.json"

    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def raw_inputs_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "raw_inputs.jsonl"

    def inbox_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "inbox.jsonl"

    def memory_items_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "memory_items.jsonl"

    @property
    def global_memory_items_file(self) -> Path:
        """Shared store for global memories, visible from every project."""
        return self.home / "global" / "memory_items.jsonl"

    @property
    def watch_state_file(self) -> Path:
        return self.home / "watch_state.json"

    @property
    def listen_pid_file(self) -> Path:
        return self.home / "listen.pid"

    @property
    def listen_log_file(self) -> Path:
        return self.home / "listen.log"


@dataclass(frozen=True)
class Settings:
    """Runtime configuration assembled from the environment."""

    home: Path
    llm: str
    ollama_model: str
    ollama_host: str | None
    project_id: str
    transcripts_dir: Path | None
    min_confidence: float
    listen_interval: float

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = dict(os.environ if env is None else env)
        home_raw = env.get("FATCAT_HOME")
        home = Path(home_raw).expanduser() if home_raw else _default_home()
        config = _load_config_file(home)

        def pick(env_key: str, config_key: str, default):
            """Resolve a value with precedence: env var > config.json > default."""
            if env.get(env_key):
                return env[env_key]
            if config.get(config_key) not in (None, ""):
                return config[config_key]
            return default

        transcripts_raw = pick("FATCAT_TRANSCRIPTS_DIR", "transcripts_dir", None)
        return cls(
            home=home,
            llm=str(pick("FATCAT_LLM", "llm", "fake")).strip().lower(),
            ollama_model=str(pick("FATCAT_OLLAMA_MODEL", "ollama_model", DEFAULT_OLLAMA_MODEL)),
            ollama_host=pick("FATCAT_OLLAMA_HOST", "ollama_host", None) or None,
            project_id=str(pick("FATCAT_PROJECT", "default_project", detect_project_id())),
            transcripts_dir=(
                Path(str(transcripts_raw)).expanduser() if transcripts_raw else None
            ),
            min_confidence=_as_float(
                str(pick("FATCAT_MIN_CONFIDENCE", "min_confidence", "")) or None,
                DEFAULT_MIN_CONFIDENCE,
            ),
            listen_interval=_as_float(
                str(pick("FATCAT_LISTEN_INTERVAL", "listen_interval", "")) or None,
                DEFAULT_LISTEN_INTERVAL,
            ),
        )

    @property
    def paths(self) -> StoragePaths:
        return StoragePaths(home=self.home)
