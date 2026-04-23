"""Detector tests: URL matching, DOM scraping, body-marker fallback."""

from __future__ import annotations

from queuepool import KNOWN_QUEUES, QueueKind, detect_queue
from queuepool.detectors import (
    _extract_first_int,
    _parse_duration_seconds,
    _query_selector_text,
)


# ---------------------------------------------------------------------------
# URL-only detection
# ---------------------------------------------------------------------------

def test_url_only_matches_queue_it() -> None:
    s = detect_queue("https://example.queue-it.net/?c=brand&e=shoe")
    assert s is not None
    assert s.kind == QueueKind.QUEUE_IT
    assert s.position is None
    assert s.raw_url.endswith("e=shoe")


def test_url_only_matches_akamai() -> None:
    s = detect_queue("https://queue.akamai.example.com/waiting")
    assert s is not None
    assert s.kind == QueueKind.AKAMAI


def test_url_only_matches_fastly_shopify() -> None:
    s = detect_queue("https://checkout.shopify.com/queue/foo")
    assert s is not None
    assert s.kind == QueueKind.FASTLY_SHOPIFY


def test_url_only_matches_nike_snkrs() -> None:
    s = detect_queue("https://www.nike.com/launch/queue/abc")
    assert s is not None
    assert s.kind == QueueKind.NIKE_SNKRS


def test_url_only_matches_cloudflare() -> None:
    s = detect_queue("https://example.com/foo?__cf_chl_f_tk=xyz")
    assert s is not None
    assert s.kind == QueueKind.CLOUDFLARE_WAITING


def test_url_only_matches_datadome() -> None:
    s = detect_queue("https://geo.captcha-delivery.com/challenge")
    assert s is not None
    assert s.kind == QueueKind.DATADOME_CHALLENGE


def test_non_queue_url_returns_none() -> None:
    assert detect_queue("https://www.example.com/") is None
    assert detect_queue("") is None


# ---------------------------------------------------------------------------
# Body marker fallback (url is benign but html is a queue)
# ---------------------------------------------------------------------------

def test_body_marker_nike_snkrs() -> None:
    html = "<html><body><h1>We've got you in line</h1></body></html>"
    s = detect_queue("https://some-random-cdn.com/x", html)
    assert s is not None
    assert s.kind == QueueKind.NIKE_SNKRS


def test_body_marker_cloudflare() -> None:
    html = "<html><body>Please wait while we verify your browser.</body></html>"
    s = detect_queue("https://example.org/", html)
    assert s is not None
    assert s.kind == QueueKind.CLOUDFLARE_WAITING


# ---------------------------------------------------------------------------
# Position / size / wait extraction via selectors
# ---------------------------------------------------------------------------

QUEUE_IT_HTML = """
<html><body>
  <div class="queue-it-panel">You are now in line.</div>
  <span class="queue-position">Your position: 1,234</span>
  <span class="queue-size">Queue size: 5000</span>
  <span class="queue-expected-wait">Expected wait: 12 minutes</span>
</body></html>
"""


def test_queue_it_position_extraction() -> None:
    s = detect_queue("https://brand.queue-it.net/?c=brand&e=e1", QUEUE_IT_HTML)
    assert s is not None
    assert s.kind == QueueKind.QUEUE_IT
    assert s.position == 1234
    assert s.queue_size == 5000
    assert s.estimated_wait_seconds == 12 * 60


SHOPIFY_HTML = """
<html><body>
  <div class="throttle__queue-position">Number 42 in line</div>
  <div class="throttle__estimated-wait">About 3 minutes</div>
</body></html>
"""


def test_fastly_shopify_position_extraction() -> None:
    s = detect_queue("https://x.myshopify.com/throttle/queue", SHOPIFY_HTML)
    assert s is not None
    assert s.kind == QueueKind.FASTLY_SHOPIFY
    assert s.position == 42
    assert s.estimated_wait_seconds == 180


NIKE_HTML = """
<html><body>
  <div>We've got you in line</div>
  <span data-qa="queue-position">Position #87</span>
</body></html>
"""


def test_nike_position_via_attr_selector() -> None:
    s = detect_queue("https://www.nike.com/launch/foo", NIKE_HTML)
    assert s is not None
    assert s.kind == QueueKind.NIKE_SNKRS
    assert s.position == 87


def test_position_falls_back_to_regex() -> None:
    # No selectors match, but body regex should.
    html = "<html><body>You are at position 123 of the queue.</body></html>"
    s = detect_queue("https://brand.queue-it.net/?c=b&e=e", html)
    assert s is not None
    assert s.position == 123


def test_missing_selectors_leave_position_none() -> None:
    html = "<html><body>Cloudflare waiting room page here.</body></html>"
    s = detect_queue("https://example.com/foo?__cf_chl_x=1", html)
    assert s is not None
    assert s.kind == QueueKind.CLOUDFLARE_WAITING
    assert s.position is None


# ---------------------------------------------------------------------------
# KNOWN_QUEUES invariants
# ---------------------------------------------------------------------------

def test_known_queues_has_all_kinds_except_unknown() -> None:
    for kind in QueueKind:
        if kind is QueueKind.UNKNOWN:
            continue
        assert kind in KNOWN_QUEUES
        cfg = KNOWN_QUEUES[kind]
        # Each config must have some URL pattern OR body marker.
        assert cfg.get("url_patterns") or cfg.get("body_markers")
        assert "position_selectors" in cfg
        assert "queue_size_selectors" in cfg
        assert "wait_selectors" in cfg


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def test_extract_first_int_strips_separators() -> None:
    assert _extract_first_int("1,234") == 1234
    assert _extract_first_int("Position: 42") == 42
    assert _extract_first_int("") is None
    assert _extract_first_int(None) is None
    assert _extract_first_int("no digits here") is None


def test_parse_duration_seconds() -> None:
    assert _parse_duration_seconds("5 minutes") == 300
    assert _parse_duration_seconds("2 hours and 30 minutes") == 2 * 3600 + 30 * 60
    assert _parse_duration_seconds("45 seconds") == 45
    assert _parse_duration_seconds("") is None
    assert _parse_duration_seconds("nothing useful") is None


def test_query_selector_text_by_id_class_attr() -> None:
    html = (
        "<div id='position'>  42 </div>"
        "<span class='queue-size'>5,000</span>"
        "<em data-qa='x'>hi</em>"
    )
    assert _query_selector_text(html, "#position") == "42"
    assert _query_selector_text(html, ".queue-size") == "5,000"
    assert _query_selector_text(html, "[data-qa='x']") == "hi"
    assert _query_selector_text(html, "#missing") is None


def test_query_selector_text_handles_tag_class_compound() -> None:
    html = "<span class='queue-position big'>10</span>"
    assert _query_selector_text(html, "span.queue-position") == "10"


def test_queue_state_to_dict_round_trip() -> None:
    s = detect_queue("https://brand.queue-it.net/?c=b&e=e", QUEUE_IT_HTML)
    assert s is not None
    d = s.to_dict()
    assert d["kind"] == "queue_it"
    assert d["position"] == 1234
    assert d["queue_size"] == 5000
