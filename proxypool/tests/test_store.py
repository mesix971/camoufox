"""Store persistence tests."""

from __future__ import annotations

import pytest

from proxypool import Proxy, ProxyStatus, ProxyStore, parse


def _p(host: str = "198.51.100.1", port: int = 8080, **kwargs) -> Proxy:
    p = Proxy(id=Proxy.new_id(), label=f"{host}:{port}", host=host, port=port, scheme="http", **kwargs)
    return p


def test_save_and_load(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = _p()
    s.save(p)
    assert s.load(p.id) == p


def test_list_filters(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    a = _p("a.example.com", provider="iproyal", country="US", tags=["vip"])
    b = _p("b.example.com", provider="brightdata", country="FR")
    c = _p("c.example.com", provider="iproyal", country="DE")
    c.status = ProxyStatus.DEAD.value
    for x in (a, b, c):
        s.save(x)

    assert {e["id"] for e in s.list()} == {a.id, b.id, c.id}
    assert {e["id"] for e in s.list(provider="iproyal")} == {a.id, c.id}
    assert {e["id"] for e in s.list(country="US")} == {a.id}
    assert {e["id"] for e in s.list(tag="vip")} == {a.id}
    assert {e["id"] for e in s.list(status="dead")} == {c.id}


def test_save_many(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    proxies = [_p(f"{i}.example.com") for i in range(5)]
    n = s.save_many(proxies)
    assert n == 5
    assert len(s.list()) == 5


def test_find_by_host_port(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = _p("x.example.com", port=8888)
    s.save(p)
    assert s.find_by_host_port("x.example.com", 8888).id == p.id
    assert s.find_by_host_port("x.example.com", 9999) is None


def test_delete(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = _p()
    s.save(p)
    s.delete(p.id)
    assert not s.exists(p.id)
    with pytest.raises(KeyError):
        s.load(p.id)


def test_prune_dead(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    alive = _p("alive.example.com")
    dead = _p("dead.example.com")
    dead.status = ProxyStatus.DEAD.value
    s.save(alive)
    s.save(dead)
    assert s.prune() == 1
    assert [e["id"] for e in s.list()] == [alive.id]


def test_rebuild_index(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = _p()
    s.save(p)
    s.index_path.write_text("{}")
    assert s.list() == []
    n = s.rebuild_index()
    assert n == 1


def test_touch(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = _p()
    s.save(p)
    updated = s.touch(p.id)
    assert updated.use_count == 1
    assert updated.last_used_at is not None


def test_save_after_parse(tmp_path) -> None:
    s = ProxyStore(tmp_path)
    p = parse("http://u:pw@198.51.100.9:8080")
    s.save(p)
    loaded = s.load(p.id)
    assert loaded == p
    assert loaded.provider == "custom"
