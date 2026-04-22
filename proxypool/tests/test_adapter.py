"""Adapter tests: shape of the dict Camoufox consumes + profile binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from proxypool import Proxy, to_camoufox_proxy
from proxypool.adapter import bind_to_profile, unbind_from_profile


def _mk() -> Proxy:
    return Proxy(
        id=Proxy.new_id(), label="t", scheme="http",
        host="198.51.100.1", port=8080,
        username="u", password="p",
    )


def test_camoufox_shape_with_auth() -> None:
    p = _mk()
    d = to_camoufox_proxy(p)
    assert d["server"] == "http://198.51.100.1:8080"
    assert d["username"] == "u"
    assert d["password"] == "p"
    assert set(d.keys()) == {"server", "username", "password"}


def test_camoufox_shape_without_auth() -> None:
    p = _mk()
    p.username = None
    p.password = None
    d = to_camoufox_proxy(p)
    assert d == {"server": "http://198.51.100.1:8080"}


def test_camoufox_socks5_preserved() -> None:
    p = _mk()
    p.scheme = "socks5"
    d = to_camoufox_proxy(p)
    assert d["server"].startswith("socks5://")


def test_bind_stamps_proxy_id() -> None:
    @dataclass
    class FakeProfile:
        proxy_id: Optional[str] = None

    profile = FakeProfile()
    p = _mk()
    bind_to_profile(p, profile)
    assert profile.proxy_id == p.id


def test_unbind_returns_previous_id() -> None:
    @dataclass
    class FakeProfile:
        proxy_id: Optional[str] = None

    profile = FakeProfile(proxy_id="abc")
    previous = unbind_from_profile(profile)
    assert previous == "abc"
    assert profile.proxy_id is None


def test_bind_requires_proxy_id_attr() -> None:
    class Nope:
        pass

    with pytest.raises(AttributeError):
        bind_to_profile(_mk(), Nope())
