"""Rotation strategy tests."""

from __future__ import annotations

import pytest

from proxypool import (
    Fixed,
    LeastRecentlyUsed,
    NoHealthyProxy,
    Proxy,
    ProxyStatus,
    Random,
    RoundRobin,
    StickyPerSite,
)


def _mk(host: str, status: str = ProxyStatus.ACTIVE.value,
        last_used_at: str = "", consec_fail: int = 0) -> Proxy:
    p = Proxy(id=Proxy.new_id(), label=host, host=host, port=80, scheme="http")
    p.status = status
    p.last_used_at = last_used_at or None
    p.consecutive_failures = consec_fail
    return p


def test_fixed_returns_specified() -> None:
    a, b = _mk("a"), _mk("b")
    strat = Fixed(a.id)
    assert strat.pick([a, b]) is a


def test_fixed_raises_when_dead() -> None:
    a = _mk("a", status=ProxyStatus.DEAD.value)
    strat = Fixed(a.id)
    with pytest.raises(NoHealthyProxy):
        strat.pick([a])


def test_fixed_raises_when_missing() -> None:
    strat = Fixed("nonexistent")
    with pytest.raises(NoHealthyProxy):
        strat.pick([_mk("a")])


def test_round_robin_cycles() -> None:
    a, b, c = _mk("a"), _mk("b"), _mk("c")
    strat = RoundRobin()
    picks = [strat.pick([a, b, c]).label for _ in range(6)]
    # sorted by id so order is deterministic; regardless, each of {a,b,c} appears twice
    assert sorted(picks) == sorted(["a", "b", "c"] * 2)


def test_round_robin_skips_dead() -> None:
    a = _mk("a", status=ProxyStatus.DEAD.value)
    b = _mk("b")
    strat = RoundRobin()
    for _ in range(4):
        assert strat.pick([a, b]).label == "b"


def test_round_robin_falls_back_to_flagged_if_no_active() -> None:
    a = _mk("a", status=ProxyStatus.FLAGGED.value)
    strat = RoundRobin(exclude_flagged=True)
    # exclude_flagged=True, but fallback should still return 'a'
    assert strat.pick([a]).label == "a"


def test_random_weighted_prefers_active() -> None:
    active = _mk("active")
    flagged = _mk("flagged", status=ProxyStatus.FLAGGED.value)
    pool = [active, flagged]
    strat = Random(weighted=True, seed=1)
    results = [strat.pick(pool).label for _ in range(500)]
    assert results.count("active") > results.count("flagged") * 2


def test_random_ignores_dead() -> None:
    active = _mk("active")
    dead = _mk("dead", status=ProxyStatus.DEAD.value)
    strat = Random(seed=1)
    for _ in range(20):
        assert strat.pick([active, dead]).label == "active"


def test_random_deterministic_with_seed() -> None:
    pool = [_mk(f"p{i}") for i in range(5)]
    a = Random(seed=42)
    b = Random(seed=42)
    assert [a.pick(pool).label for _ in range(10)] == [b.pick(pool).label for _ in range(10)]


def test_lru_picks_never_used_first() -> None:
    old = _mk("old", last_used_at="2024-01-01T00:00:00+00:00")
    never = _mk("never")
    strat = LeastRecentlyUsed()
    assert strat.pick([old, never]).label == "never"


def test_lru_picks_oldest_among_used() -> None:
    a = _mk("a", last_used_at="2025-01-01T00:00:00+00:00")
    b = _mk("b", last_used_at="2025-06-01T00:00:00+00:00")
    c = _mk("c", last_used_at="2024-01-01T00:00:00+00:00")
    strat = LeastRecentlyUsed()
    assert strat.pick([a, b, c]).label == "c"


def test_sticky_per_site_returns_same_proxy() -> None:
    pool = [_mk("a"), _mk("b"), _mk("c")]
    inner = RoundRobin()
    strat = StickyPerSite(ttl_seconds=60, inner=inner)

    p1 = strat.pick(pool, context={"site": "example.com"})
    p2 = strat.pick(pool, context={"site": "example.com"})
    assert p1.id == p2.id


def test_sticky_per_site_different_sites_can_differ() -> None:
    pool = [_mk("a"), _mk("b"), _mk("c")]
    strat = StickyPerSite(ttl_seconds=60, inner=RoundRobin())
    p1 = strat.pick(pool, context={"site": "one.com"})
    p2 = strat.pick(pool, context={"site": "two.com"})
    p3 = strat.pick(pool, context={"site": "three.com"})
    assert {p1.id, p2.id, p3.id} == {p.id for p in pool}


def test_sticky_per_site_requires_context() -> None:
    strat = StickyPerSite(ttl_seconds=60, inner=RoundRobin())
    with pytest.raises(ValueError):
        strat.pick([_mk("a")])


def test_sticky_forgets_on_demand() -> None:
    pool = [_mk("a"), _mk("b")]
    strat = StickyPerSite(ttl_seconds=60, inner=RoundRobin())
    strat.pick(pool, context={"site": "x.com"})
    strat.forget("x.com")
    assert "x.com" not in strat._map
    strat.pick(pool, context={"site": "x.com"})  # re-binds
    assert "x.com" in strat._map
