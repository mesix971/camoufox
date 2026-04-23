"""
Per-domain rate limiter shared across sessions.

Stored as a tiny JSON file keyed by hostname:
    {"www.example.com": {"events": [ts1, ts2, ...], "max_per_minute": 10}, ...}

Each `check_and_record(host)` call trims stale events (>60s old) and checks
if the host is under its cap. Atomic write-through to a shared file means
multiple session_runner processes see each other's requests.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse


class RateLimitExceeded(Exception):
    """Raised when a host is over its cap and `wait=False`."""


DEFAULT_MAX_PER_MINUTE = 30


class RateLimiter:
    def __init__(
        self,
        store_path: str | Path,
        default_max_per_minute: int = DEFAULT_MAX_PER_MINUTE,
    ):
        self.path = Path(store_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.default_max = default_max_per_minute

    def _load(self) -> Dict[str, Dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: Dict[str, Dict]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self.path)

    @staticmethod
    def _host(url_or_host: str) -> str:
        if "://" in url_or_host:
            return urlparse(url_or_host).hostname or url_or_host
        return url_or_host

    def set_limit(self, host: str, max_per_minute: int) -> None:
        data = self._load()
        entry = data.setdefault(host, {"events": [], "max_per_minute": max_per_minute})
        entry["max_per_minute"] = max_per_minute
        self._save(data)

    def check_and_record(
        self,
        url_or_host: str,
        wait: bool = True,
        max_wait_seconds: float = 60.0,
    ) -> float:
        """Check if we can hit `host` now. If yes, record the event and return 0.
        If no and `wait=True`, sleep until we can then record; return the waited seconds.
        If `wait=False`, raise RateLimitExceeded.
        """
        host = self._host(url_or_host)
        slept_total = 0.0
        while True:
            data = self._load()
            entry = data.setdefault(host, {"events": [], "max_per_minute": self.default_max})
            now = time.time()
            # Trim events older than 60s.
            fresh = [t for t in entry["events"] if now - t < 60.0]
            cap = int(entry.get("max_per_minute", self.default_max))
            if len(fresh) < cap:
                fresh.append(now)
                entry["events"] = fresh
                self._save(data)
                return slept_total
            # Over cap — wait until oldest event ages out.
            oldest = fresh[0]
            wait_needed = 60.0 - (now - oldest) + random.uniform(0.1, 1.0)
            if not wait:
                raise RateLimitExceeded(
                    f"{host}: {len(fresh)}/{cap} per minute, retry in {wait_needed:.1f}s"
                )
            if slept_total + wait_needed > max_wait_seconds:
                raise RateLimitExceeded(
                    f"{host}: would exceed max_wait={max_wait_seconds}s"
                )
            time.sleep(wait_needed)
            slept_total += wait_needed

    def stats(self, host: Optional[str] = None) -> Dict[str, Dict]:
        data = self._load()
        now = time.time()
        out: Dict[str, Dict] = {}
        for h, entry in data.items():
            if host and h != host:
                continue
            fresh = [t for t in entry["events"] if now - t < 60.0]
            out[h] = {
                "events_last_minute": len(fresh),
                "max_per_minute": entry.get("max_per_minute", self.default_max),
            }
        return out
