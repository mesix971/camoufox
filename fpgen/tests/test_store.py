"""Persistence layer tests."""

from __future__ import annotations

import pytest

from fpgen import ProfileStore, generate


def test_save_and_load(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    p = generate(seed=1)
    store.save(p)
    p2 = store.load(p.id)
    assert p == p2


def test_list_and_filters(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    a = generate(os="windows", seed=1)
    b = generate(os="macos", seed=2, tags=["vip"])
    c = generate(os="linux", seed=3)
    for p in (a, b, c):
        store.save(p)

    all_ids = {e["id"] for e in store.list()}
    assert all_ids == {a.id, b.id, c.id}

    windows_only = store.list(os="windows")
    assert {e["id"] for e in windows_only} == {a.id}

    vip = store.list(tag="vip")
    assert {e["id"] for e in vip} == {b.id}


def test_delete(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    p = generate(seed=4)
    store.save(p)
    assert store.exists(p.id)
    store.delete(p.id)
    assert not store.exists(p.id)
    with pytest.raises(KeyError):
        store.load(p.id)


def test_touch_increments_usage(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    p = generate(seed=5)
    store.save(p)
    assert p.use_count == 0
    p2 = store.touch(p.id)
    assert p2.use_count == 1
    assert p2.last_used_at is not None
    p3 = store.touch(p.id)
    assert p3.use_count == 2


def test_rotation_picks_lru(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    a = generate(os="windows", seed=10)
    b = generate(os="windows", seed=11)
    c = generate(os="windows", seed=12)
    for p in (a, b, c):
        store.save(p)

    # Touch a then b, leaving c never used.
    store.touch(a.id)
    store.touch(b.id)

    picked = store.pick_least_recently_used(os="windows")
    assert picked is not None
    assert picked["id"] == c.id  # never-used comes first


def test_rotation_exclude(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    a = generate(os="macos", seed=20)
    b = generate(os="macos", seed=21)
    store.save(a)
    store.save(b)
    picked = store.pick_least_recently_used(os="macos", exclude=[a.id])
    assert picked["id"] == b.id


def test_rebuild_index(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    p = generate(seed=30)
    store.save(p)
    # Corrupt the index
    store.index_path.write_text("{}")
    assert store.list() == []
    n = store.rebuild_index()
    assert n == 1
    assert len(store.list()) == 1
