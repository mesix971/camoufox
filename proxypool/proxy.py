"""
Proxy dataclass.

A Proxy represents one routable endpoint + its provider metadata + its
observed health. Persisted as one JSON file per proxy by ProxyStore.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProxyScheme(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyStatus(str, Enum):
    UNTESTED = "untested"
    ACTIVE = "active"
    FLAGGED = "flagged"
    DEAD = "dead"


@dataclass
class Proxy:
    id: str
    label: str
    scheme: str = ProxyScheme.HTTP.value
    host: str = ""
    port: int = 0
    username: Optional[str] = None
    password: Optional[str] = None

    provider: str = "custom"
    country: Optional[str] = None
    city: Optional[str] = None
    asn: Optional[str] = None
    sticky_session_id: Optional[str] = None
    sticky_session_lifetime: Optional[str] = None

    status: str = ProxyStatus.UNTESTED.value
    last_checked_at: Optional[str] = None
    latency_ms: Optional[float] = None
    observed_ip: Optional[str] = None
    observed_country: Optional[str] = None
    observed_city: Optional[str] = None

    success_count: int = 0
    fail_count: int = 0
    consecutive_failures: int = 0
    total_checks: int = 0
    last_used_at: Optional[str] = None
    use_count: int = 0

    created_at: str = field(default_factory=_utc_now_iso)
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def to_url(self, include_auth: bool = True) -> str:
        """Scheme URL suitable for requests/urllib proxy config."""
        if include_auth and self.username:
            auth = self.username
            if self.password:
                auth += f":{self.password}"
            return f"{self.scheme}://{auth}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"

    def touch(self) -> None:
        self.last_used_at = _utc_now_iso()
        self.use_count += 1

    def record_success(self, ip: str, latency_ms: float,
                       country: Optional[str] = None, city: Optional[str] = None) -> None:
        self.status = ProxyStatus.ACTIVE.value
        self.last_checked_at = _utc_now_iso()
        self.latency_ms = round(latency_ms, 1)
        self.observed_ip = ip
        if country:
            self.observed_country = country
        if city:
            self.observed_city = city
        self.success_count += 1
        self.consecutive_failures = 0
        self.total_checks += 1

    def record_failure(self, dead_after: int = 3) -> None:
        self.last_checked_at = _utc_now_iso()
        self.fail_count += 1
        self.consecutive_failures += 1
        self.total_checks += 1
        if self.consecutive_failures >= dead_after:
            self.status = ProxyStatus.DEAD.value
        else:
            self.status = ProxyStatus.FLAGGED.value

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Proxy":
        return cls(**json.loads(raw))

    def is_healthy(self) -> bool:
        return self.status == ProxyStatus.ACTIVE.value

    def is_usable(self) -> bool:
        """Any status except DEAD is usable (untested proxies get a chance)."""
        return self.status != ProxyStatus.DEAD.value
