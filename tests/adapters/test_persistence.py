"""Round-trip tests for the file-based persistence adapters."""

from __future__ import annotations

from pathlib import Path

from fatcat.adapters.persistence import (
    JsonProjectRepository,
    JsonlInboxRepository,
    JsonlMemoryRepository,
    JsonlRawInputRepository,
    ScopedMemoryRepository,
)
from fatcat.adapters.persistence.jsonl import read_jsonl
from fatcat.domain.models import MemoryCandidate, MemoryItem, Project, RawInput


def _candidate(**overrides) -> MemoryCandidate:
    base = dict(
        content="User prefers FastAPI.",
        memory_type="preference",
        suggested_scope="global",
        confidence=0.8,
        sensitivity="low",
        source_input_id="raw_1",
    )
    base.update(overrides)
    return MemoryCandidate(**base)


def test_memory_repository_roundtrip(tmp_path: Path):
    repo = JsonlMemoryRepository(tmp_path / "memory_items.jsonl")
    item = MemoryItem(content="x", memory_type="preference", scope="global")
    proj_item = MemoryItem(
        content="y", memory_type="decision", scope="project:demo", project_id="demo"
    )
    repo.save(item)
    repo.save(proj_item)

    assert len(repo.list_all()) == 2
    assert [i.id for i in repo.list_global()] == [item.id]
    assert [i.id for i in repo.list_by_project("demo")] == [proj_item.id]


def test_memory_repository_skips_duplicates(tmp_path: Path):
    repo = JsonlMemoryRepository(tmp_path / "memory_items.jsonl")
    repo.save(MemoryItem(content="Use uv for tooling.", memory_type="decision", scope="global"))
    # Same thought, different casing/spacing -> treated as duplicate.
    repo.save(MemoryItem(content="use   UV for tooling.", memory_type="decision", scope="global"))
    assert len(repo.list_all()) == 1


def test_memory_repository_same_text_different_scope_kept(tmp_path: Path):
    repo = JsonlMemoryRepository(tmp_path / "memory_items.jsonl")
    repo.save(MemoryItem(content="Ship it.", memory_type="todo", scope="global"))
    repo.save(
        MemoryItem(
            content="Ship it.",
            memory_type="todo",
            scope="project:demo",
            project_id="demo",
        )
    )
    assert len(repo.list_all()) == 2


def test_memory_repository_find_duplicate(tmp_path: Path):
    repo = JsonlMemoryRepository(tmp_path / "memory_items.jsonl")
    item = MemoryItem(content="Prefer FastAPI.", memory_type="preference", scope="global")
    repo.save(item)
    assert repo.find_duplicate("prefer fastapi.", None) is not None
    assert repo.find_duplicate("something else", None) is None


def test_memory_repository_finds_item_by_source_candidate(tmp_path: Path):
    repo = JsonlMemoryRepository(tmp_path / "memories.jsonl")
    item = MemoryItem(
        content="User confirms issue candidates.",
        memory_type="principle",
        scope="global",
        source_candidate_ids=["cand_1"],
    )
    repo.save(item)

    assert repo.find_by_source_candidate_id("cand_1") == item
    assert repo.find_by_source_candidate_id("missing") is None


def test_scoped_memory_routes_by_scope(tmp_path: Path):
    g = JsonlMemoryRepository(tmp_path / "global.jsonl")
    p = JsonlMemoryRepository(tmp_path / "proj.jsonl")
    repo = ScopedMemoryRepository(g, p)

    gi = MemoryItem(content="global fact", memory_type="preference", scope="global")
    pi = MemoryItem(
        content="proj fact",
        memory_type="decision",
        scope="project:demo",
        project_id="demo",
    )
    repo.save(gi)
    repo.save(pi)

    assert [i.id for i in g.list_all()] == [gi.id]
    assert [i.id for i in p.list_all()] == [pi.id]
    assert len(repo.list_all()) == 2
    assert [i.id for i in repo.list_global()] == [gi.id]
    assert [i.id for i in repo.list_by_project("demo")] == [pi.id]


def test_scoped_memory_find_duplicate_is_scope_aware(tmp_path: Path):
    g = JsonlMemoryRepository(tmp_path / "global.jsonl")
    p = JsonlMemoryRepository(tmp_path / "proj.jsonl")
    repo = ScopedMemoryRepository(g, p)
    repo.save(MemoryItem(content="shared note", memory_type="preference", scope="global"))

    assert repo.find_duplicate("shared note", None) is not None
    # Same text but project scope routes to the (empty) project store.
    assert repo.find_duplicate("shared note", "demo") is None


def test_raw_input_repository_roundtrip(tmp_path: Path):
    repo = JsonlRawInputRepository(tmp_path / "raw_inputs.jsonl")
    raw = RawInput(content="hello", source="brain_dump")
    repo.save(raw)
    assert repo.get(raw.id) is not None
    assert repo.get(raw.id).content == "hello"
    assert len(repo.list_all()) == 1


def test_inbox_repository_mark_reviewed_removes_from_pending(tmp_path: Path):
    repo = JsonlInboxRepository(tmp_path / "inbox.jsonl")
    c1 = _candidate()
    c2 = _candidate(content="another")
    repo.add_candidates([c1, c2])

    assert len(repo.list_pending()) == 2
    repo.mark_reviewed(c1.id)
    pending = repo.list_pending()
    assert len(pending) == 1
    assert pending[0].id == c2.id
    # The reviewed candidate is still stored, just no longer pending.
    assert repo.get(c1.id) is None


def test_project_repository_roundtrip(tmp_path: Path):
    repo = JsonProjectRepository(tmp_path / "projects")
    project = Project(id="demo", name="Demo Project")
    repo.save(project)

    loaded = repo.get("demo")
    assert loaded is not None
    assert loaded.name == "Demo Project"
    assert [p.id for p in repo.list_all()] == ["demo"]


def test_read_jsonl_skips_corrupt_lines(tmp_path: Path):
    path = tmp_path / "broken.jsonl"
    path.write_text(
        '{"a": 1}\nnot json at all\n{"a": 2}\n', encoding="utf-8"
    )
    errors: list[int] = []
    records = list(read_jsonl(path, on_error=lambda ln, line, exc: errors.append(ln)))
    assert records == [{"a": 1}, {"a": 2}]
    assert errors == [2]


def test_get_missing_project_returns_none(tmp_path: Path):
    repo = JsonProjectRepository(tmp_path / "projects")
    assert repo.get("nope") is None
    assert repo.list_all() == []
