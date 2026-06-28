"""Tests for the SaveMemoryItem use case."""

from __future__ import annotations

import pytest

from fatcat.application.use_cases import SaveMemoryItem

from .fakes import InMemoryMemoryRepository, InMemoryRawInputRepository


def _use_case(store_raw_input: bool = True) -> tuple[SaveMemoryItem, ...]:
    mem = InMemoryMemoryRepository()
    raw = InMemoryRawInputRepository()
    return SaveMemoryItem(mem, raw, store_raw_input=store_raw_input), mem, raw


def test_save_creates_memory_item_and_raw_input():
    uc, mem, raw = _use_case()
    item = uc.execute("I prefer FastAPI for small APIs.")
    assert item.content == "I prefer FastAPI for small APIs."
    assert item.scope == "global"
    assert len(mem.items) == 1
    assert len(raw.items) == 1
    assert item.source_input_ids == [raw.items[0].id]


def test_save_with_project_uses_project_scope():
    uc, mem, _ = _use_case()
    item = uc.execute("Keep storage flexible.", project_id="demo")
    assert item.project_id == "demo"
    assert item.scope == "project:demo"


def test_save_rejects_empty_content():
    uc, _, _ = _use_case()
    with pytest.raises(ValueError):
        uc.execute("   ")


def test_save_can_skip_raw_input_storage():
    uc, mem, raw = _use_case(store_raw_input=False)
    uc.execute("Something")
    assert len(mem.items) == 1
    assert raw.items == []


def test_save_is_idempotent_for_duplicates():
    uc, mem, raw = _use_case()
    first = uc.execute("I prefer FastAPI for small APIs.")
    second = uc.execute("i   prefer FastAPI for small apis.")
    assert len(mem.items) == 1
    assert second.id == first.id
    assert len(raw.items) == 1
