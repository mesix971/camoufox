"""Tests for the on-disk ScriptStore."""

from __future__ import annotations

import pytest

from actions import ActionScript, ScriptStore


def _mk_script(name: str = "demo") -> ActionScript:
    return ActionScript(
        name=name,
        actions=[
            {"type": "goto", "url": "https://x.test"},
            {"type": "click", "selector": "#btn"},
        ],
        metadata={"author": "alice"},
    )


def test_save_and_load_round_trip(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    script = _mk_script()
    s.save(script)
    loaded = s.load("demo")
    assert loaded.name == script.name
    assert loaded.actions == script.actions
    assert loaded.metadata == script.metadata


def test_exists(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    assert not s.exists("demo")
    s.save(_mk_script())
    assert s.exists("demo")


def test_load_missing_raises_keyerror(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    with pytest.raises(KeyError):
        s.load("nope")


def test_list_returns_saved_scripts(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    s.save(_mk_script("b"))
    names = [e["name"] for e in s.list()]
    assert names == ["a", "b"]  # sorted


def test_list_reports_action_count(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    entry = next(e for e in s.list() if e["name"] == "a")
    assert entry["action_count"] == 2


def test_delete_removes_file_and_index_entry(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    s.delete("a")
    assert not s.exists("a")
    assert s.list() == []
    with pytest.raises(KeyError):
        s.load("a")


def test_delete_missing_is_noop(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.delete("never-existed")  # must not raise
    assert s.list() == []


def test_save_overwrites(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    updated = ActionScript(name="a", actions=[{"type": "log", "message": "hi"}])
    s.save(updated)
    loaded = s.load("a")
    assert loaded.actions == [{"type": "log", "message": "hi"}]


def test_invalid_name_rejected(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    for bad in ("", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            s.save(ActionScript(name=bad, actions=[]))


def test_rebuild_index(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    s.save(_mk_script("b"))
    # Corrupt the index — rebuild should recover from on-disk files.
    s.index_path.write_text("{}")
    assert s.list() == []
    n = s.rebuild_index()
    assert n == 2
    assert {e["name"] for e in s.list()} == {"a", "b"}


def test_index_ignores_tmp_files(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    (s.scripts_dir / "leftover.json.tmp").write_text("{}")
    n = s.rebuild_index()
    assert n == 1


def test_metadata_persisted_in_index(tmp_path) -> None:
    s = ScriptStore(tmp_path)
    s.save(_mk_script("a"))
    entry = next(e for e in s.list() if e["name"] == "a")
    assert entry["metadata"] == {"author": "alice"}
