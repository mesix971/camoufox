"""
Queue detection heuristics.

Each known queue system has:
  - URL regex patterns (fast path: URL alone is enough to classify)
  - DOM selectors for the position number
  - DOM selectors for the total queue size
  - DOM selectors for the estimated wait
  - Text markers used when selectors don't fire (body-text fallback)

`detect_queue(url, html=None)` returns a QueueState when any signal matches.
When `html` is None we do URL-only classification (position unknown).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class QueueKind(str, Enum):
    QUEUE_IT = "queue_it"
    AKAMAI = "akamai"
    FASTLY_SHOPIFY = "fastly_shopify"
    NIKE_SNKRS = "nike_snkrs"
    CLOUDFLARE_WAITING = "cloudflare_waiting"
    DATADOME_CHALLENGE = "datadome_challenge"
    UNKNOWN = "unknown"


@dataclass
class QueueState:
    kind: QueueKind
    position: Optional[int] = None
    queue_size: Optional[int] = None
    estimated_wait_seconds: Optional[int] = None
    detected_at: str = field(default_factory=_utc_now_iso)
    raw_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value if isinstance(self.kind, QueueKind) else self.kind
        return d


# ---------------------------------------------------------------------------
# Per-queue configuration
# ---------------------------------------------------------------------------
#
# Each entry:
#   url_patterns:    list of regex patterns (IGNORECASE) applied to the URL
#   body_markers:    list of case-insensitive substrings identifying the page
#                    by content (used when the URL alone is ambiguous)
#   position_selectors:   CSS selectors whose text contains the user's position
#   queue_size_selectors: CSS selectors whose text contains the total queue
#   wait_selectors:       CSS selectors for the estimated wait label
#   position_regex:  regex to pull an integer out of the body as fallback
#   wait_regex:      regex to pull a human duration ("5 minutes") from body
#
KNOWN_QUEUES: Dict[QueueKind, Dict[str, Any]] = {
    QueueKind.QUEUE_IT: {
        "url_patterns": [
            r"queue-it\.net",
            r"[?&]c=[^&]+&e=[^&]+",          # c=customer & e=eventid
        ],
        "body_markers": [
            "queue-it",
            "You are now in line",
            "You are in line",
            "waiting room",
        ],
        "position_selectors": [
            ".queue-position",
            "#position",
            "[data-qit-position]",
            ".qit-position",
            ".queueit-position",
            "span.position",
        ],
        "queue_size_selectors": [
            ".queue-size",
            "#queue-size",
            "[data-qit-queue-size]",
        ],
        "wait_selectors": [
            ".queue-expected-wait",
            "#expected-wait",
            "[data-qit-expected-wait]",
            ".qit-expected-wait",
        ],
        "position_regex": r"(?:position|number)\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
    QueueKind.AKAMAI: {
        "url_patterns": [
            r"queue\.akamai",
            r"_Incapsula_Resource",
            r"akamai[^/]*\.com/.*queue",
        ],
        "body_markers": [
            "_Incapsula_Resource",
            "Request unsuccessful. Incapsula",
            "Akamai Queue",
            "You are in the queue",
        ],
        "position_selectors": [
            "#position",
            ".akamai-position",
            "[data-queue-position]",
        ],
        "queue_size_selectors": [
            ".akamai-queue-size",
            "[data-queue-size]",
        ],
        "wait_selectors": [
            ".akamai-wait",
            "[data-queue-wait]",
        ],
        "position_regex": r"position\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
    QueueKind.FASTLY_SHOPIFY: {
        "url_patterns": [
            r"checkout\.shopify\.com/queue",
            r"throttle[._-]?queue",
            r"shoppay",
            r"\.myshopify\.com/.*throttle",
        ],
        "body_markers": [
            "You're in line",
            "You are in line for",
            "Shopify",
            "throttle_queue",
            "shop_pay",
        ],
        "position_selectors": [
            ".throttle__queue-position",
            ".queue__position",
            "[data-throttle-position]",
            "#queue-position",
        ],
        "queue_size_selectors": [
            ".throttle__queue-size",
            "[data-throttle-size]",
        ],
        "wait_selectors": [
            ".throttle__estimated-wait",
            "[data-throttle-wait]",
        ],
        "position_regex": r"(?:you(?:'re)?\s+(?:in\s+line\s+)?(?:at\s+)?(?:number|#|position))\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
    QueueKind.NIKE_SNKRS: {
        "url_patterns": [
            r"nike\.com/.*(?:launch|snkrs|queue|waitingroom)",
            r"snkrs\.com",
        ],
        "body_markers": [
            "We've got you in line",
            "We have got you in line",
            "SNKRS",
            "You're in the queue",
            "hang tight",
        ],
        "position_selectors": [
            ".queue-position",
            "[data-qa='queue-position']",
            "#nike-queue-position",
        ],
        "queue_size_selectors": [
            ".queue-total",
            "[data-qa='queue-total']",
        ],
        "wait_selectors": [
            ".queue-wait",
            "[data-qa='queue-wait']",
        ],
        "position_regex": r"(?:position|#)\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
    QueueKind.CLOUDFLARE_WAITING: {
        "url_patterns": [
            r"__cf_chl_",
            r"cdn-cgi/challenge-platform",
            r"cdn-cgi/l/chk_jschl",
            r"waitingroom\.cloudflare",
        ],
        "body_markers": [
            "Please wait while we verify",
            "Checking your browser before accessing",
            "cf-browser-verification",
            "Cloudflare Waiting Room",
            "You are now in line",
        ],
        "position_selectors": [
            "#waiting-room-position",
            ".cf-waitingroom-position",
            "[data-cf-position]",
        ],
        "queue_size_selectors": [
            "#waiting-room-total",
            ".cf-waitingroom-total",
        ],
        "wait_selectors": [
            "#waiting-room-wait",
            ".cf-waitingroom-wait",
        ],
        "position_regex": r"position\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
    QueueKind.DATADOME_CHALLENGE: {
        "url_patterns": [
            r"geo\.captcha-delivery\.com",
            r"datadome",
        ],
        "body_markers": [
            "datadome",
            "dd_cookie",
            "Please complete the security check",
            "geo.captcha-delivery.com",
        ],
        "position_selectors": [
            "#dd-position",
            ".datadome-position",
        ],
        "queue_size_selectors": [
            "#dd-total",
            ".datadome-total",
        ],
        "wait_selectors": [
            "#dd-wait",
            ".datadome-wait",
        ],
        "position_regex": r"position\D{0,10}(\d{1,8})",
        "wait_regex": r"(\d+)\s*(second|minute|hour)s?",
    },
}


# Compiled pattern cache to keep hot-path cheap.
_COMPILED_URL: Dict[QueueKind, List[Pattern[str]]] = {
    kind: [re.compile(p, re.IGNORECASE) for p in cfg.get("url_patterns", [])]
    for kind, cfg in KNOWN_QUEUES.items()
}


# ---------------------------------------------------------------------------
# DOM scraping helpers (no BeautifulSoup dep).
# ---------------------------------------------------------------------------

# Extremely small CSS-selector -> regex translator. We only support:
#   * "#id"            -> id="id"
#   * ".class"         -> class contains class
#   * "tag"            -> that element
#   * "[attr]"         -> has attribute
#   * "[attr='val']"   -> has attribute == val (quoted or bare)
# Compound selectors ("tag.class", "tag[attr]") are supported by folding the
# extra constraint into the attribute match. This is best-effort only;
# callers should prefer page.evaluate() when available.
_ID_RE = re.compile(r"^#([\w-]+)$")
_CLASS_RE = re.compile(r"^\.([\w-]+)$")
_ATTR_RE = re.compile(r"^\[([\w-]+)(?:=['\"]?([^\]'\"]+)['\"]?)?\]$")
_TAG_ATTR_RE = re.compile(r"^([\w-]+)\[([\w-]+)(?:=['\"]?([^\]'\"]+)['\"]?)?\]$")
_TAG_CLASS_RE = re.compile(r"^([\w-]+)\.([\w-]+)$")
_TAG_ONLY_RE = re.compile(r"^([\w-]+)$")


def _text_from_match(html: str, start: int, end_tag_pos: int) -> str:
    """Return inner text (stripped of tags) from html[start:end_tag_pos]."""
    inner = html[start:end_tag_pos]
    # Strip nested tags.
    inner = re.sub(r"<[^>]+>", " ", inner)
    return re.sub(r"\s+", " ", inner).strip()


def _find_by_id(html: str, ident: str) -> Optional[str]:
    pat = re.compile(
        r"<([\w-]+)[^>]*\bid\s*=\s*['\"]" + re.escape(ident) + r"['\"][^>]*>(.*?)</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(html)
    if not m:
        return None
    inner = re.sub(r"<[^>]+>", " ", m.group(2))
    return re.sub(r"\s+", " ", inner).strip() or None


def _find_by_class(html: str, cls: str) -> Optional[str]:
    pat = re.compile(
        r"<([\w-]+)[^>]*\bclass\s*=\s*['\"][^'\"]*\b"
        + re.escape(cls)
        + r"\b[^'\"]*['\"][^>]*>(.*?)</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(html)
    if not m:
        return None
    inner = re.sub(r"<[^>]+>", " ", m.group(2))
    return re.sub(r"\s+", " ", inner).strip() or None


def _find_by_attr(html: str, attr: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        attr_part = r"\b" + re.escape(attr) + r"\b[^>]*"
    else:
        attr_part = (
            r"\b" + re.escape(attr) + r"\s*=\s*['\"]" + re.escape(value) + r"['\"][^>]*"
        )
    pat = re.compile(
        r"<([\w-]+)[^>]*" + attr_part + r">(.*?)</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(html)
    if not m:
        return None
    inner = re.sub(r"<[^>]+>", " ", m.group(2))
    return re.sub(r"\s+", " ", inner).strip() or None


def _query_selector_text(html: str, selector: str) -> Optional[str]:
    """Best-effort stdlib implementation of querySelector(...).textContent."""
    s = selector.strip()
    if not s:
        return None
    if m := _ID_RE.match(s):
        return _find_by_id(html, m.group(1))
    if m := _CLASS_RE.match(s):
        return _find_by_class(html, m.group(1))
    if m := _ATTR_RE.match(s):
        return _find_by_attr(html, m.group(1), m.group(2))
    if m := _TAG_ATTR_RE.match(s):
        return _find_by_attr(html, m.group(2), m.group(3))
    if m := _TAG_CLASS_RE.match(s):
        return _find_by_class(html, m.group(2))
    if m := _TAG_ONLY_RE.match(s):
        tag = m.group(1)
        pat = re.compile(
            r"<" + re.escape(tag) + r"\b[^>]*>(.*?)</" + re.escape(tag) + r">",
            re.IGNORECASE | re.DOTALL,
        )
        mm = pat.search(html)
        if not mm:
            return None
        inner = re.sub(r"<[^>]+>", " ", mm.group(1))
        return re.sub(r"\s+", " ", inner).strip() or None
    # Unknown selector grammar; we do NOT raise, we just give up.
    return None


def _extract_first_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    # Accept common thousands separators.
    cleaned = text.replace(",", "").replace(".", "")
    m = re.search(r"(\d{1,9})", cleaned)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (ValueError, OverflowError):
        return None


_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


def _parse_duration_seconds(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    total = 0
    found = False
    for m in re.finditer(r"(\d+)\s*(second|minute|hour)s?", text, re.IGNORECASE):
        n = int(m.group(1))
        unit = m.group(2).lower()
        total += n * _UNIT_SECONDS[unit]
        found = True
    return total if found else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _url_matches(url: str) -> Optional[QueueKind]:
    for kind, patterns in _COMPILED_URL.items():
        for pat in patterns:
            if pat.search(url):
                return kind
    return None


def _body_matches(html: str) -> Optional[QueueKind]:
    lowered = html.lower()
    for kind, cfg in KNOWN_QUEUES.items():
        for marker in cfg.get("body_markers", []):
            if marker.lower() in lowered:
                return kind
    return None


def _scrape_fields(kind: QueueKind, html: str) -> Dict[str, Optional[int]]:
    cfg = KNOWN_QUEUES[kind]
    out: Dict[str, Optional[int]] = {
        "position": None,
        "queue_size": None,
        "estimated_wait_seconds": None,
    }

    for sel in cfg.get("position_selectors", []):
        val = _query_selector_text(html, sel)
        if val is not None:
            n = _extract_first_int(val)
            if n is not None:
                out["position"] = n
                break

    for sel in cfg.get("queue_size_selectors", []):
        val = _query_selector_text(html, sel)
        if val is not None:
            n = _extract_first_int(val)
            if n is not None:
                out["queue_size"] = n
                break

    for sel in cfg.get("wait_selectors", []):
        val = _query_selector_text(html, sel)
        if val is not None:
            secs = _parse_duration_seconds(val)
            if secs is not None:
                out["estimated_wait_seconds"] = secs
                break

    # Body-regex fallbacks.
    if out["position"] is None and cfg.get("position_regex"):
        m = re.search(cfg["position_regex"], html, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                out["position"] = int(m.group(1))
            except (ValueError, IndexError):
                pass

    if out["estimated_wait_seconds"] is None and cfg.get("wait_regex"):
        secs = _parse_duration_seconds(html)
        if secs is not None:
            out["estimated_wait_seconds"] = secs

    return out


def detect_queue(url: str, html: Optional[str] = None) -> Optional[QueueState]:
    """
    Classify a page as a known queue.

    URL alone is the fast path — if it matches, we return a QueueState even
    without html (position will be None). If html is provided we additionally
    attempt to scrape the position, queue size and estimated wait.

    Returns None if nothing matches.
    """
    kind = _url_matches(url or "")
    if kind is None and html:
        kind = _body_matches(html)
    if kind is None:
        return None

    state = QueueState(kind=kind, raw_url=url or "")
    if html:
        fields = _scrape_fields(kind, html)
        state.position = fields["position"]
        state.queue_size = fields["queue_size"]
        state.estimated_wait_seconds = fields["estimated_wait_seconds"]
    return state
