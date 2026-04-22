"""
Rotation strategies.

All strategies take a list of Proxy objects (typically from ProxyStore.list()
after filtering) and expose .pick(context) -> Proxy. Dead proxies are
excluded by default; flagged are kept but deprioritised where possible.

Strategies:
    Fixed(proxy_id)                       — always the same proxy
    RoundRobin()                          — cycle through in list order
    Random(weighted=True)                 — healthy-weighted random
    LeastRecentlyUsed()                   — pick proxy with oldest last_used_at
    StickyPerSite(ttl_seconds, inner)     — same proxy per site, expires after ttl

Strategies are stateless wrt the pool (the pool is passed on each .pick()),
but they DO carry internal state (round-robin cursor, sticky map, etc.)
so reuse the same instance if you want consistent behaviour.
"""

from __future__ import annotations

import random
import time
from typing import Dict, Iterable, List, Optional, Protocol

from proxypool.proxy import Proxy, ProxyStatus


class NoHealthyProxy(RuntimeError):
    """Raised when a strategy has no candidate to return."""


class Strategy(Protocol):
    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy: ...


def _filter_usable(pool: Iterable[Proxy], exclude_flagged: bool = False) -> List[Proxy]:
    out = []
    for p in pool:
        if not p.is_usable():
            continue
        if exclude_flagged and p.status == ProxyStatus.FLAGGED.value:
            continue
        out.append(p)
    return out


class Fixed:
    def __init__(self, proxy_id: str):
        self.proxy_id = proxy_id

    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy:
        for p in pool:
            if p.id == self.proxy_id:
                if not p.is_usable():
                    raise NoHealthyProxy(f"proxy {self.proxy_id} is dead")
                return p
        raise NoHealthyProxy(f"proxy {self.proxy_id} not in pool")


class RoundRobin:
    def __init__(self, exclude_flagged: bool = True):
        self._cursor = 0
        self.exclude_flagged = exclude_flagged

    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy:
        candidates = _filter_usable(pool, exclude_flagged=self.exclude_flagged)
        if not candidates:
            # Retry including flagged if that's what drained the pool.
            candidates = _filter_usable(pool, exclude_flagged=False)
        if not candidates:
            raise NoHealthyProxy("no usable proxy in pool")
        candidates.sort(key=lambda p: p.id)  # stable order across runs
        p = candidates[self._cursor % len(candidates)]
        self._cursor += 1
        return p


class Random:
    def __init__(self, weighted: bool = True, exclude_flagged: bool = True, seed: Optional[int] = None):
        self.weighted = weighted
        self.exclude_flagged = exclude_flagged
        self._rng = random.Random(seed)

    def _weight(self, p: Proxy) -> float:
        if p.status == ProxyStatus.ACTIVE.value:
            base = 3.0
        elif p.status == ProxyStatus.UNTESTED.value:
            base = 1.5
        elif p.status == ProxyStatus.FLAGGED.value:
            base = 0.5
        else:
            base = 0.0
        # Penalise by recent failures.
        return max(0.1, base / (1 + p.consecutive_failures))

    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy:
        candidates = _filter_usable(pool, exclude_flagged=self.exclude_flagged)
        if not candidates:
            candidates = _filter_usable(pool, exclude_flagged=False)
        if not candidates:
            raise NoHealthyProxy("no usable proxy in pool")
        if not self.weighted:
            return self._rng.choice(candidates)
        weights = [self._weight(p) for p in candidates]
        return self._rng.choices(candidates, weights=weights, k=1)[0]


class LeastRecentlyUsed:
    def __init__(self, exclude_flagged: bool = True):
        self.exclude_flagged = exclude_flagged

    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy:
        candidates = _filter_usable(pool, exclude_flagged=self.exclude_flagged)
        if not candidates:
            candidates = _filter_usable(pool, exclude_flagged=False)
        if not candidates:
            raise NoHealthyProxy("no usable proxy in pool")
        candidates.sort(key=lambda p: (p.last_used_at or "", p.use_count))
        return candidates[0]


class StickyPerSite:
    """Returns the same proxy for the same site within ttl_seconds."""

    def __init__(self, ttl_seconds: int, inner: Strategy):
        self.ttl_seconds = ttl_seconds
        self.inner = inner
        # site -> (proxy_id, expires_at_unix)
        self._map: Dict[str, tuple] = {}

    def _now(self) -> float:
        return time.time()

    def pick(self, pool: Iterable[Proxy], context: Optional[Dict] = None) -> Proxy:
        if not context or "site" not in context:
            raise ValueError("StickyPerSite.pick() requires context={'site': '<domain>'}")
        site = context["site"]
        pool_list = list(pool)
        now = self._now()

        existing = self._map.get(site)
        if existing:
            proxy_id, expires = existing
            if now < expires:
                for p in pool_list:
                    if p.id == proxy_id and p.is_usable():
                        return p
                # Cached proxy is now gone/dead — fall through to re-pick.
            self._map.pop(site, None)

        p = self.inner.pick(pool_list, context=context)
        self._map[site] = (p.id, now + self.ttl_seconds)
        return p

    def forget(self, site: str) -> None:
        self._map.pop(site, None)

    def forget_all(self) -> None:
        self._map.clear()
