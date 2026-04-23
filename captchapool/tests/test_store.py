"""ProviderStore CRUD + build_solver tests."""

from __future__ import annotations

import json

import pytest

from captchapool import (
    CapSolverProvider,
    ProviderStore,
    Solver,
    TwoCaptchaProvider,
)


def test_save_and_load(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    entry = s.save("main", api_key="SECRET-KEY-123", provider_type="capsolver", priority=5)
    assert entry["api_key"] == "SECRET-KEY-123"
    loaded = s.load("main")
    assert loaded["api_key"] == "SECRET-KEY-123"
    assert loaded["provider_type"] == "capsolver"
    assert loaded["priority"] == 5


def test_list_redacts_api_key(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("main", api_key="SUPER-SECRET-KEY-PLEASE-HIDE", provider_type="capsolver")
    entries = s.list()
    assert len(entries) == 1
    e = entries[0]
    assert "SECRET" not in e["api_key"]
    assert e["api_key"].startswith("SUPE")
    assert e["api_key"].endswith("DE")
    assert "*" in e["api_key"]


def test_list_is_sorted_by_priority(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("c", api_key="kc", provider_type="capsolver", priority=10)
    s.save("a", api_key="ka", provider_type="twocaptcha", priority=0)
    s.save("b", api_key="kb", provider_type="capsolver", priority=5)
    names = [e["name"] for e in s.list()]
    assert names == ["a", "b", "c"]


def test_list_filters_by_provider_type(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("a", api_key="ka", provider_type="capsolver")
    s.save("b", api_key="kb", provider_type="twocaptcha")
    caps = s.list(provider_type="capsolver")
    assert [e["name"] for e in caps] == ["a"]


def test_delete_removes_file_and_index(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("gone", api_key="k", provider_type="capsolver")
    assert s.exists("gone")
    s.delete("gone")
    assert not s.exists("gone")
    with pytest.raises(KeyError):
        s.load("gone")
    assert s.list() == []


def test_save_rejects_unknown_provider_type(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    with pytest.raises(ValueError):
        s.save("bad", api_key="k", provider_type="funcaptcha")


def test_save_rejects_empty_api_key(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    with pytest.raises(ValueError):
        s.save("empty", api_key="", provider_type="capsolver")


def test_save_rejects_unsafe_name(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    with pytest.raises(ValueError):
        s.save("../escape", api_key="k", provider_type="capsolver")
    with pytest.raises(ValueError):
        s.save("", api_key="k", provider_type="capsolver")


def test_rebuild_index(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("a", api_key="ka", provider_type="capsolver")
    s.save("b", api_key="kb", provider_type="twocaptcha")
    # Nuke the index
    s.index_path.write_text("{}")
    assert s.list() == []
    n = s.rebuild_index()
    assert n == 2
    assert {e["name"] for e in s.list()} == {"a", "b"}


def test_build_solver_instantiates_providers_in_priority_order(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("second", api_key="k1", provider_type="twocaptcha", priority=10)
    s.save("first", api_key="k2", provider_type="capsolver", priority=1)
    solver = s.build_solver(strategy="first")
    assert isinstance(solver, Solver)
    assert [p.name for p in solver.providers] == ["capsolver", "twocaptcha"]
    assert isinstance(solver.providers[0], CapSolverProvider)
    assert isinstance(solver.providers[1], TwoCaptchaProvider)


def test_build_solver_raises_when_empty(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    with pytest.raises(ValueError):
        s.build_solver()


def test_save_overwrites_same_name(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("main", api_key="old", provider_type="capsolver", priority=1)
    s.save("main", api_key="new", provider_type="twocaptcha", priority=2)
    loaded = s.load("main")
    assert loaded["api_key"] == "new"
    assert loaded["provider_type"] == "twocaptcha"
    assert loaded["priority"] == 2


def test_on_disk_json_layout(tmp_path) -> None:
    s = ProviderStore(tmp_path)
    s.save("main", api_key="K", provider_type="capsolver", priority=3)
    path = s.providers_dir / "main.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == {
        "name": "main",
        "provider_type": "capsolver",
        "api_key": "K",
        "priority": 3,
        "created_at": data["created_at"],  # opaque timestamp
    }
    idx = json.loads(s.index_path.read_text())
    assert "main" in idx
    assert idx["main"]["provider_type"] == "capsolver"
    assert idx["main"]["priority"] == 3
