"""Tests for P3-finitions commands: binding, batch launch, dashboard."""

from __future__ import annotations

import pytest

from launcher.bridge import commands


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("FPGEN_STORE", str(tmp_path / "fpgen"))
    monkeypatch.setenv("PROXYPOOL_STORE", str(tmp_path / "proxypool"))
    monkeypatch.setenv("LAUNCHER_SESSIONS", str(tmp_path / "sessions"))
    yield


def test_bind_profile_proxy_happy_path() -> None:
    pf = commands.new_profile({"os": "windows", "seed": 1})["profile"]
    px = commands.add_proxy({"line": "http://u:p@198.51.100.1:8080"})["proxy"]
    res = commands.bind_profile_proxy({"profile_id": pf["id"], "proxy_id": px["id"]})
    assert res["proxy_id"] == px["id"]

    shown = commands.show_profile({"id": pf["id"]})
    assert shown["profile"]["proxy_id"] == px["id"]


def test_bind_profile_proxy_unbind() -> None:
    pf = commands.new_profile({"os": "windows", "seed": 2})["profile"]
    px = commands.add_proxy({"line": "http://u:p@198.51.100.2:8080"})["proxy"]
    commands.bind_profile_proxy({"profile_id": pf["id"], "proxy_id": px["id"]})
    res = commands.bind_profile_proxy({"profile_id": pf["id"], "proxy_id": None})
    assert res["proxy_id"] is None


def test_bind_profile_proxy_rejects_unknown_profile() -> None:
    with pytest.raises(KeyError):
        commands.bind_profile_proxy({"profile_id": "nope", "proxy_id": None})


def test_bind_profile_proxy_rejects_unknown_proxy() -> None:
    pf = commands.new_profile({"os": "windows", "seed": 3})["profile"]
    with pytest.raises(KeyError):
        commands.bind_profile_proxy({"profile_id": pf["id"], "proxy_id": "nope"})


def test_batch_launch_requires_profile_ids() -> None:
    with pytest.raises(ValueError):
        commands.batch_launch_session({"profile_ids": []})


def test_batch_launch_collects_failures_without_bailing(monkeypatch) -> None:
    """If one profile_id is unknown, others should still launch."""
    pf1 = commands.new_profile({"os": "windows", "seed": 10})["profile"]
    pf2 = commands.new_profile({"os": "macos", "seed": 11})["profile"]

    # Stub spawn so we don't actually launch Camoufox subprocesses.
    from launcher.bridge.sessions import Session, SessionManager
    stub_sessions = {}

    def fake_spawn(self, profile_id, proxy_id=None, url=None, headless=False, runner_argv_extra=None):
        s = Session(id=Session.new_id(), pid=1, profile_id=profile_id,
                    proxy_id=proxy_id, url=url, headless=headless)
        stub_sessions[s.id] = s
        return s

    monkeypatch.setattr(SessionManager, "spawn", fake_spawn)

    res = commands.batch_launch_session({
        "profile_ids": [pf1["id"], "does-not-exist", pf2["id"]],
        "strategy": "none",
    })
    assert res["count"] == 2
    assert len(res["failures"]) == 1
    assert res["failures"][0]["profile_id"] == "does-not-exist"


def test_batch_launch_round_robin_distributes_proxies(monkeypatch) -> None:
    # 4 profiles, 2 proxies => round-robin should pair p0+p2 with proxyA,
    # p1+p3 with proxyB.
    profiles = [
        commands.new_profile({"os": "windows", "seed": 100 + i})["profile"]
        for i in range(4)
    ]
    proxies = [
        commands.add_proxy({"line": f"http://u:p@198.51.100.{i}:8080"})["proxy"]
        for i in range(1, 3)
    ]
    # Mark both proxies active so list(status='active') finds them.
    from proxypool import ProxyStore
    store = ProxyStore(commands.proxy_store_path())
    for px in proxies:
        p = store.load(px["id"])
        p.status = "active"
        store.save(p)

    from launcher.bridge.sessions import Session, SessionManager
    captured = []

    def fake_spawn(self, profile_id, proxy_id=None, url=None, headless=False, runner_argv_extra=None):
        captured.append((profile_id, proxy_id))
        return Session(id=Session.new_id(), pid=1, profile_id=profile_id, proxy_id=proxy_id)

    monkeypatch.setattr(SessionManager, "spawn", fake_spawn)

    res = commands.batch_launch_session({
        "profile_ids": [p["id"] for p in profiles],
        "strategy": "round-robin",
    })
    assert res["count"] == 4
    assigned_proxies = [px for (_, px) in captured]
    # Each of the 2 proxies should appear exactly twice.
    from collections import Counter
    counts = Counter(assigned_proxies)
    assert len(counts) == 2
    assert set(counts.values()) == {2}


def test_batch_launch_bound_uses_profile_proxy(monkeypatch) -> None:
    pf = commands.new_profile({"os": "windows", "seed": 50})["profile"]
    px = commands.add_proxy({"line": "http://u:p@198.51.100.99:8080"})["proxy"]
    commands.bind_profile_proxy({"profile_id": pf["id"], "proxy_id": px["id"]})

    from launcher.bridge.sessions import Session, SessionManager
    captured = []

    def fake_spawn(self, profile_id, proxy_id=None, **kw):
        captured.append((profile_id, proxy_id))
        return Session(id=Session.new_id(), pid=1, profile_id=profile_id, proxy_id=proxy_id)

    monkeypatch.setattr(SessionManager, "spawn", fake_spawn)

    commands.batch_launch_session({"profile_ids": [pf["id"]], "strategy": "bound"})
    assert captured[0][1] == px["id"]


def test_dashboard_summary_empty() -> None:
    res = commands.dashboard_summary({})
    assert res["profiles"]["total"] == 0
    assert res["proxies"]["total"] == 0
    assert res["sessions"]["total"] == 0
    assert res["sessions"]["running"] == 0


def test_dashboard_summary_populated() -> None:
    commands.new_profile({"os": "windows", "seed": 1})
    commands.new_profile({"os": "macos", "seed": 2})
    commands.new_profile({"os": "macos", "seed": 3})
    commands.add_proxy({"line": "http://u:p@198.51.100.1:8080"})
    commands.add_proxy({"line": "http://u:p@198.51.100.2:8080"})
    res = commands.dashboard_summary({})
    assert res["profiles"]["total"] == 3
    assert res["profiles"]["by_os"]["macos"] == 2
    assert res["profiles"]["by_os"]["windows"] == 1
    assert res["proxies"]["total"] == 2
