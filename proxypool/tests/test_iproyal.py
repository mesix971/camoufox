"""iproyal session rotation tests (no network)."""

from __future__ import annotations

import pytest

from proxypool import Proxy, iproyal
from proxypool.iproyal import update_session_in_password


def _mk_iproyal() -> Proxy:
    return Proxy(
        id=Proxy.new_id(), label="ip-test", provider="iproyal",
        scheme="http", host="geo.iproyal.com", port=12321,
        username="user123",
        password="realpass_country-US_city-NewYork_session-abc123_lifetime-10m",
        country="US", city="NewYork",
        sticky_session_id="abc123", sticky_session_lifetime="10m",
    )


def test_rotate_session_changes_id() -> None:
    p = _mk_iproyal()
    new = iproyal.rotate_session(p, new_session_id="xyz789")
    assert new.sticky_session_id == "xyz789"
    assert "_session-xyz789" in new.password
    assert "_session-abc123" not in new.password


def test_rotate_session_generates_id_when_unspecified() -> None:
    p = _mk_iproyal()
    new = iproyal.rotate_session(p)
    assert new.sticky_session_id != "abc123"
    assert len(new.sticky_session_id) == 12


def test_rotate_session_preserves_other_modifiers() -> None:
    p = _mk_iproyal()
    new = iproyal.rotate_session(p, new_session_id="zzz")
    assert "_country-US" in new.password
    assert "_city-NewYork" in new.password
    assert "_lifetime-10m" in new.password


def test_rotate_session_overrides_country_and_lifetime() -> None:
    p = _mk_iproyal()
    new = iproyal.rotate_session(p, new_session_id="z", country="FR", lifetime="24h")
    assert new.country == "FR"
    assert "_country-FR" in new.password
    assert "_lifetime-24h" in new.password


def test_rotate_session_resets_observation_state() -> None:
    p = _mk_iproyal()
    p.observed_ip = "203.0.113.5"
    p.observed_country = "US"
    p.consecutive_failures = 2
    new = iproyal.rotate_session(p, new_session_id="q")
    assert new.observed_ip is None
    assert new.observed_country is None
    assert new.consecutive_failures == 0


def test_rotate_session_gets_new_id_by_default() -> None:
    p = _mk_iproyal()
    new = iproyal.rotate_session(p, new_session_id="q")
    assert new.id != p.id


def test_rotate_session_in_place_keeps_id() -> None:
    p = _mk_iproyal()
    original_id = p.id
    new = iproyal.rotate_session(p, new_session_id="q", in_place=True)
    assert new is p
    assert new.id == original_id


def test_rotate_session_rejects_non_iproyal() -> None:
    p = _mk_iproyal()
    p.provider = "brightdata"
    with pytest.raises(ValueError):
        iproyal.rotate_session(p)


def test_update_password_appends_when_missing() -> None:
    result = update_session_in_password("basepass", session_id="new123", lifetime="1h", country="DE")
    assert "_session-new123" in result
    assert "_lifetime-1h" in result
    assert "_country-DE" in result


def test_update_password_replaces_existing() -> None:
    orig = "pw_session-old_lifetime-5m"
    result = update_session_in_password(orig, session_id="new", lifetime="1h")
    assert "_session-new" in result
    assert "_session-old" not in result
    assert "_lifetime-1h" in result
    assert "_lifetime-5m" not in result
