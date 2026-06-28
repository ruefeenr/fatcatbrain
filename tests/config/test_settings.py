"""Tests for settings resolution (env > config.json > default)."""

from __future__ import annotations

import json
from pathlib import Path

from fatcat.config import Settings
from fatcat.config.settings import (
    DEFAULT_OLLAMA_MODEL,
    detect_project_id,
    find_project_root,
    slugify_project,
)


def _write_config(home: Path, data: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps(data), encoding="utf-8")


def test_defaults_when_no_config(tmp_path: Path):
    s = Settings.from_env({"FATCAT_HOME": str(tmp_path / "home")})
    assert s.llm == "ollama"
    assert s.ollama_model == DEFAULT_OLLAMA_MODEL


def test_config_file_values_are_used(tmp_path: Path):
    home = tmp_path / "home"
    _write_config(home, {"llm": "ollama", "ollama_model": "qwen2.5"})
    s = Settings.from_env({"FATCAT_HOME": str(home)})
    assert s.llm == "ollama"
    assert s.ollama_model == "qwen2.5"


def test_env_overrides_config(tmp_path: Path):
    home = tmp_path / "home"
    _write_config(home, {"llm": "ollama", "ollama_model": "qwen2.5"})
    s = Settings.from_env({"FATCAT_HOME": str(home), "FATCAT_LLM": "custom"})
    assert s.llm == "custom"
    # ollama_model still comes from config since env didn't override it.
    assert s.ollama_model == "qwen2.5"


def test_corrupt_config_falls_back_to_defaults(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / "config.json").write_text("{ not json", encoding="utf-8")
    s = Settings.from_env({"FATCAT_HOME": str(home)})
    assert s.llm == "ollama"


def test_legacy_fake_config_migrates_to_ollama(tmp_path: Path):
    home = tmp_path / "home"
    _write_config(home, {"llm": "fake", "ollama_model": "gpt-oss:20b"})

    settings = Settings.from_env({"FATCAT_HOME": str(home)})

    assert settings.llm == "ollama"


def test_slugify_project():
    assert slugify_project("My Cool Project") == "my-cool-project"
    assert slugify_project("fatcat") == "fatcat"
    assert slugify_project("___") == "default"


def test_find_project_root_uses_git_dir(tmp_path: Path):
    root = tmp_path / "myrepo"
    (root / ".git").mkdir(parents=True)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == root.resolve()


def test_find_project_root_without_git_returns_start(tmp_path: Path):
    d = tmp_path / "plain"
    d.mkdir()
    assert find_project_root(d) == d.resolve()


def test_detect_project_id_from_folder(tmp_path: Path):
    root = tmp_path / "My App"
    (root / ".git").mkdir(parents=True)
    assert detect_project_id(root) == "my-app"


def test_env_project_overrides_detection(tmp_path: Path):
    s = Settings.from_env(
        {"FATCAT_HOME": str(tmp_path / "home"), "FATCAT_PROJECT": "explicit"}
    )
    assert s.project_id == "explicit"
