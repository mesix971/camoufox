"""
proxypool — proxy management for Camoufox.

Imports, health-checks, stores, rotates and hands out proxies ready to drop
into camoufox.launch_options(proxy=...).

Public API:
    parse(line_or_url) -> Proxy
    parse_many(text)   -> List[Proxy]
    ProxyStore(path)
    to_camoufox_proxy(proxy) -> dict
    HealthChecker(workers=10).check(proxies)
    strategies: Fixed, RoundRobin, Random, LeastRecentlyUsed, StickyPerSite
    iproyal.rotate_session(proxy, new_session_id=None)
"""

from proxypool import iproyal
from proxypool.adapter import to_camoufox_proxy
from proxypool.health import HealthChecker, HealthResult
from proxypool.parsers import ParseError, parse, parse_many
from proxypool.proxy import Proxy, ProxyScheme, ProxyStatus
from proxypool.rotation import (
    Fixed,
    LeastRecentlyUsed,
    NoHealthyProxy,
    Random,
    RoundRobin,
    StickyPerSite,
    Strategy,
)
from proxypool.store import ProxyStore

__all__ = [
    "Fixed",
    "HealthChecker",
    "HealthResult",
    "LeastRecentlyUsed",
    "NoHealthyProxy",
    "ParseError",
    "Proxy",
    "ProxyScheme",
    "ProxyStatus",
    "ProxyStore",
    "Random",
    "RoundRobin",
    "StickyPerSite",
    "Strategy",
    "iproyal",
    "parse",
    "parse_many",
    "to_camoufox_proxy",
]

__version__ = "0.1.0"
