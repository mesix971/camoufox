"""Command handler tests.

Uses env-var overrides (FPGEN_STORE, PROXYPOOL_STORE, LAUNCHER_SESSIONS) to
point each command at a tmp dir. No network, no Camoufox launch.
"""

from __future__ import annotations

import pytest

from launcher.bridge import commands


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("FPGEN_STORE", str(tmp_path / "fpgen"))
    monkeypatch.setenv("PROXYPOOL_STORE", str(tmp_path / "proxypool"))
    monkeypatch.setenv("LAUNCHER_SESSIONS", str(tmp_path / "sessions"))
    yield


def test_list_profiles_empty() -> None:
    res = commands.list_profiles({})
    assert res == {"profiles": []}


def test_new_profile_then_list() -> None:
    created = commands.new_profile({"os": "windows", "locale": "fr-FR", "seed": 1})
    assert created["profile"]["os"] == "windows"
    assert created["profile"]["locale"] == "fr-FR"

    listed = commands.list_profiles({})
    assert len(listed["profiles"]) == 1
    assert listed["profiles"][0]["os"] == "windows"


def test_show_profile_returns_config() -> None:
    created = commands.new_profile({"os": "macos", "seed": 2})
    pid = created["profile"]["id"]
    shown = commands.show_profile({"id": pid})
    assert shown["profile"]["id"] == pid
    assert "navigator.userAgent" in shown["config"]
    assert shown["config"]["navigator.platform"] == "MacIntel"


def test_delete_profile() -> None:
    created = commands.new_profile({"os": "linux", "seed": 3})
    pid = created["profile"]["id"]
    commands.delete_profile({"id": pid})
    assert commands.list_profiles({})["profiles"] == []


def test_archetypes() -> None:
    res = commands.list_archetypes({})
    ids = {a["id"] for a in res["archetypes"]}
    assert "windows-11-mainstream" in ids
    assert "macos-14-retina" in ids


def test_add_then_list_proxies() -> None:
    commands.add_proxy({"line": "http://u:p@198.51.100.1:8080", "tags": ["btc"]})
    listed = commands.list_proxies({})["proxies"]
    assert len(listed) == 1
    assert listed[0]["host"] == "198.51.100.1"


def test_add_proxy_detects_duplicate() -> None:
    commands.add_proxy({"line": "http://u:p@198.51.100.2:9000"})
    second = commands.add_proxy({"line": "http://x:y@198.51.100.2:9000"})
    assert second["duplicate"] is True
    assert len(commands.list_proxies({})["proxies"]) == 1


def test_import_proxies_bulk() -> None:
    text = """
    http://a:b@198.51.100.10:8000
    198.51.100.11:8001
    bad-line
    geo.iproyal.com:12321:u:p_session-abc_country-US
    """
    res = commands.import_proxies({"text": text})
    assert res["saved"] == 3
    assert len(res["errors"]) == 1


def test_filter_proxies_by_country() -> None:
    commands.add_proxy({"line": "geo.iproyal.com:12321:u:p_country-US_session-a"})
    commands.add_proxy({"line": "geo.iproyal.com:12322:u:p_country-FR_session-b"})
    us = commands.list_proxies({"country": "US"})["proxies"]
    fr = commands.list_proxies({"country": "FR"})["proxies"]
    assert len(us) == 1
    assert len(fr) == 1


def test_rotate_proxy_session() -> None:
    commands.add_proxy({"line": "geo.iproyal.com:12321:user1:pw_country-US_session-old_lifetime-10m"})
    listed = commands.list_proxies({})["proxies"]
    pid = listed[0]["id"]
    res = commands.rotate_proxy_session({"id": pid})
    assert res["proxy"]["sticky_session_id"] != "old"
    assert "_session-" in res["proxy"]["password"]


def test_list_sessions_empty() -> None:
    res = commands.list_sessions({})
    assert res == {"sessions": []}


def test_launch_session_rejects_unknown_profile() -> None:
    with pytest.raises(KeyError):
        commands.launch_session({"profile_id": "does-not-exist"})


def test_launch_session_rejects_unknown_proxy() -> None:
    created = commands.new_profile({"os": "windows", "seed": 10})
    pid = created["profile"]["id"]
    with pytest.raises(KeyError):
        commands.launch_session({"profile_id": pid, "proxy_id": "nope"})


def test_prune_sessions_on_empty() -> None:
    res = commands.prune_sessions({})
    assert res == {"pruned": 0}
