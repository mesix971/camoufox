"""
Queue-it HTTP client — polls a queue page without Playwright.

Useful when you have many sessions (100+) monitoring their position in
parallel: scraping the DOM through a Playwright page is expensive and
slow. This module issues a plain HTTPS GET with the session's cookies
and extracts the position + queueId from the returned HTML.

Caveats:
  - Queue-it's challenge token (bmak, _sdf etc.) is usually already in
    the cookies your Playwright session received when it first hit the
    queue page. We reuse those cookies verbatim.
  - The HTML format has changed in the past; the selectors here cover
    the current public pages. If your queue returns JS-rendered content
    only, fall back to queuepool.QueueMonitor (DOM via Playwright).
  - Some customers have a custom theme — this client parses the known
    default selectors (data-queueid, #queue-status, .estimated-wait).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests


QUEUE_HOST_RE = re.compile(r"https?://([a-z0-9-]+)\.queue-it\.net", re.I)

POSITION_PATTERNS = [
    re.compile(r'data-position\s*=\s*"(\d+)"'),
    re.compile(r'id="queuePosition"[^>]*>\s*(\d{1,9})'),
    re.compile(r'"queuePosition"\s*:\s*(\d+)'),
    re.compile(r"Votre position\s*[:\-]?\s*(\d{1,9})", re.I),
    re.compile(r"Your position\s*[:\-]?\s*(\d{1,9})", re.I),
]
QUEUE_SIZE_PATTERNS = [
    re.compile(r'data-total\s*=\s*"(\d+)"'),
    re.compile(r'"queueSize"\s*:\s*(\d+)'),
]
ETA_PATTERNS = [
    re.compile(r'data-expected-wait-minutes\s*=\s*"(\d+)"'),
    re.compile(r'"expectedWaitMinutes"\s*:\s*(\d+)'),
    re.compile(r"(\d+)\s*min[ute]*"),
]
QUEUE_ID_PATTERNS = [
    re.compile(r'data-queueid\s*=\s*"([a-f0-9-]+)"', re.I),
    re.compile(r'"queueId"\s*:\s*"([a-f0-9-]+)"', re.I),
]


@dataclass
class ApiPollResult:
    position: Optional[int] = None
    queue_size: Optional[int] = None
    estimated_wait_minutes: Optional[int] = None
    queue_id: Optional[str] = None
    customer_id: Optional[str] = None
    event_id: Optional[str] = None
    polled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    redirected_to: Optional[str] = None
    error: Optional[str] = None
    raw_url: str = ""


class QueueItClient:
    """HTTP client for polling Queue-it status pages.

    Instantiate with a requests.Session that has the session's cookies,
    optionally a proxy + user-agent matching the Camoufox profile that
    originally entered the queue.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        timeout: float = 8.0,
    ):
        self.session = session or requests.Session()
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
        if user_agent:
            self.session.headers["User-Agent"] = user_agent
        else:
            # Default to a recent Firefox UA so we don't stick out with the
            # python-requests string.
            self.session.headers.setdefault(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
            )
        self.timeout = timeout

    # --- parsing helpers ---

    @staticmethod
    def parse_queue_url(url: str) -> Dict[str, Optional[str]]:
        """Extract customerId / eventId / token from a queue URL."""
        p = urlparse(url)
        m = QUEUE_HOST_RE.match(f"{p.scheme}://{p.netloc}")
        customer_id = m.group(1) if m else None
        q = parse_qs(p.query)
        return {
            "customer_id": customer_id,
            "event_id": (q.get("e") or q.get("eventid") or [None])[0],
            "token": (q.get("t") or q.get("queueittoken") or [None])[0],
            "queue_id": (q.get("q") or [None])[0],
        }

    @staticmethod
    def _first_int(patterns: List[re.Pattern], html: str) -> Optional[int]:
        for p in patterns:
            m = p.search(html)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    @staticmethod
    def _first_str(patterns: List[re.Pattern], html: str) -> Optional[str]:
        for p in patterns:
            m = p.search(html)
            if m:
                return m.group(1)
        return None

    # --- public ---

    def poll(self, queue_url: str) -> ApiPollResult:
        """Fetch the queue page and parse position + metadata."""
        r = ApiPollResult(raw_url=queue_url)
        url_meta = self.parse_queue_url(queue_url)
        r.customer_id = url_meta["customer_id"]
        r.event_id = url_meta["event_id"]
        if url_meta["queue_id"]:
            r.queue_id = url_meta["queue_id"]

        try:
            resp = self.session.get(queue_url, timeout=self.timeout, allow_redirects=True)
            if str(resp.url) != queue_url:
                r.redirected_to = str(resp.url)
            if resp.status_code >= 400:
                r.error = f"HTTP {resp.status_code}"
                return r
            html = resp.text
        except requests.RequestException as e:
            r.error = f"{type(e).__name__}: {e}"
            return r

        r.position = self._first_int(POSITION_PATTERNS, html)
        r.queue_size = self._first_int(QUEUE_SIZE_PATTERNS, html)
        r.estimated_wait_minutes = self._first_int(ETA_PATTERNS, html)
        if not r.queue_id:
            r.queue_id = self._first_str(QUEUE_ID_PATTERNS, html)

        # If the page redirected to the target site, we're through the queue.
        if r.redirected_to and ".queue-it.net" not in r.redirected_to:
            r.position = 0

        return r

    def poll_many(self, queue_urls: List[str]) -> List[ApiPollResult]:
        """Sequential polls — wrap in ThreadPoolExecutor externally for
        parallel fan-out. Kept simple here to avoid thread-safety surprises
        with shared cookies across sessions."""
        return [self.poll(u) for u in queue_urls]

    @staticmethod
    def from_playwright_context(context, queue_url: str) -> "QueueItClient":
        """Build a client with cookies + UA copied from a Playwright BrowserContext."""
        s = requests.Session()
        for c in context.cookies():
            s.cookies.set(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", None),
                path=c.get("path", "/"),
            )
        ua = None
        try:
            page = context.pages[0] if context.pages else None
            if page:
                ua = page.evaluate("() => navigator.userAgent")
        except Exception:  # noqa: BLE001
            pass
        return QueueItClient(session=s, user_agent=ua)
