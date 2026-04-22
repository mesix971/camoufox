"""
Parallel health checker.

Each check does two sequential HTTP requests through the proxy:
    1. latency + IP: GET https://api.ipify.org (fast, text-only)
    2. optional geo: GET https://ipapi.co/<ip>/json (country + city)

Both the check and the geo step have their own timeouts. The proxy's
.record_success()/record_failure() is called based on the outcome, so after
check() returns the Proxy objects are ready to be saved.

Requests are parallelised across a ThreadPoolExecutor. The `requests`
library is used because Camoufox's pythonlib already depends on it, so we
don't introduce a new runtime dep.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, List, Optional

try:
    import requests
    from requests.exceptions import RequestException
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from proxypool.proxy import Proxy


log = logging.getLogger("proxypool.health")


_IP_URLS = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ipinfo.io/ip",
    "https://icanhazip.com",
]
_GEO_URL = "https://ipapi.co/{ip}/json/"


@dataclass
class HealthResult:
    proxy_id: str
    ok: bool
    latency_ms: Optional[float] = None
    ip: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    error: Optional[str] = None


class HealthChecker:
    def __init__(
        self,
        workers: int = 10,
        timeout: float = 15.0,
        geo_timeout: float = 10.0,
        geo_lookup: bool = True,
        dead_after: int = 3,
    ):
        if not _HAS_REQUESTS:
            raise RuntimeError(
                "proxypool.health requires the `requests` library. "
                "Install it with `pip install requests`."
            )
        self.workers = max(1, workers)
        self.timeout = timeout
        self.geo_timeout = geo_timeout
        self.geo_lookup = geo_lookup
        self.dead_after = dead_after

    # --- single proxy ---

    def _check_one(self, p: Proxy) -> HealthResult:
        proxy_url = p.to_url(include_auth=True)
        proxies = {"http": proxy_url, "https": proxy_url}
        last_err: Optional[str] = None

        ip: Optional[str] = None
        latency_ms: Optional[float] = None

        for url in _IP_URLS:
            start = time.perf_counter()
            try:
                resp = requests.get(url, proxies=proxies, timeout=self.timeout, verify=True)  # nosec: proxy health check
                resp.raise_for_status()
                ip = resp.text.strip()
                latency_ms = (time.perf_counter() - start) * 1000.0
                break
            except RequestException as e:
                last_err = f"{type(e).__name__}: {e}"
                continue

        if ip is None:
            return HealthResult(proxy_id=p.id, ok=False, error=last_err or "no IP URL succeeded")

        country: Optional[str] = None
        city: Optional[str] = None
        if self.geo_lookup:
            try:
                geo_resp = requests.get(
                    _GEO_URL.format(ip=ip),
                    proxies=proxies,
                    timeout=self.geo_timeout,
                    verify=True,
                )
                geo_resp.raise_for_status()
                data = geo_resp.json()
                country = data.get("country") or data.get("country_code")
                city = data.get("city")
            except (RequestException, ValueError) as e:
                log.debug("geo lookup failed for %s: %s", p.id, e)

        return HealthResult(
            proxy_id=p.id, ok=True, latency_ms=latency_ms,
            ip=ip, country=country, city=city,
        )

    # --- batch ---

    def check(self, proxies: Iterable[Proxy], apply: bool = True) -> List[HealthResult]:
        """Run health checks in parallel. If apply=True, update each Proxy in
        place via record_success()/record_failure(). Returns one HealthResult
        per proxy, in completion order."""
        proxies = list(proxies)
        results: List[HealthResult] = []
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = {ex.submit(self._check_one, p): p for p in proxies}
            for fut in as_completed(futures):
                p = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = HealthResult(proxy_id=p.id, ok=False, error=f"{type(e).__name__}: {e}")
                if apply:
                    if res.ok and res.latency_ms is not None and res.ip is not None:
                        p.record_success(res.ip, res.latency_ms, country=res.country, city=res.city)
                    else:
                        p.record_failure(dead_after=self.dead_after)
                results.append(res)
        return results
