"""Proxy dataclass tests: state transitions and JSON round-trip."""

from __future__ import annotations

from proxypool import Proxy, ProxyStatus


def _mk() -> Proxy:
    return Proxy(
        id=Proxy.new_id(), label="t", scheme="http",
        host="198.51.100.1", port=8080,
        username="u", password="p",
    )


def test_record_success_sets_active() -> None:
    p = _mk()
    p.record_success(ip="203.0.113.5", latency_ms=123.4, country="US", city="NYC")
    assert p.status == ProxyStatus.ACTIVE.value
    assert p.observed_ip == "203.0.113.5"
    assert p.observed_country == "US"
    assert p.latency_ms == 123.4
    assert p.success_count == 1
    assert p.consecutive_failures == 0


def test_record_failure_flags_then_kills() -> None:
    p = _mk()
    p.record_failure(dead_after=3)
    assert p.status == ProxyStatus.FLAGGED.value
    p.record_failure(dead_after=3)
    assert p.status == ProxyStatus.FLAGGED.value
    p.record_failure(dead_after=3)
    assert p.status == ProxyStatus.DEAD.value
    assert p.fail_count == 3
    assert p.consecutive_failures == 3


def test_success_after_failures_resets_streak() -> None:
    p = _mk()
    p.record_failure()
    p.record_failure()
    assert p.consecutive_failures == 2
    p.record_success(ip="203.0.113.6", latency_ms=50.0)
    assert p.consecutive_failures == 0
    assert p.status == ProxyStatus.ACTIVE.value


def test_is_usable_dead_is_not() -> None:
    p = _mk()
    assert p.is_usable()
    for _ in range(3):
        p.record_failure()
    assert not p.is_usable()


def test_touch_increments_use_count() -> None:
    p = _mk()
    assert p.use_count == 0
    p.touch()
    p.touch()
    assert p.use_count == 2
    assert p.last_used_at is not None


def test_to_url_variants() -> None:
    p = _mk()
    assert p.to_url(include_auth=True) == "http://u:p@198.51.100.1:8080"
    assert p.to_url(include_auth=False) == "http://198.51.100.1:8080"
    p.username = None
    p.password = None
    assert p.to_url(include_auth=True) == "http://198.51.100.1:8080"


def test_json_round_trip() -> None:
    p = _mk()
    p.record_success("203.0.113.7", 99.0, country="FR")
    p.touch()
    p2 = Proxy.from_json(p.to_json())
    assert p == p2
