"""Tests for the async webhook dispatcher."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from launcher.bridge import webhook


@pytest.fixture(autouse=True)
def _isolate_queue(monkeypatch):
    """Each test gets a fresh empty queue and an unflagged worker so we
    can deterministically observe enqueue behaviour."""
    import queue as _queue_mod
    import threading
    monkeypatch.setattr(webhook, "_queue", _queue_mod.Queue(maxsize=10))
    monkeypatch.setattr(webhook, "_worker_started", threading.Event())
    monkeypatch.setattr(webhook, "_worker_lock", threading.Lock())
    yield


def test_notify_returns_false_without_webhook(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_webhook", lambda: None)
    assert webhook.notify("hello") is False


def test_notify_returns_immediately_even_when_post_is_slow(monkeypatch) -> None:
    """The whole point of the fix: the caller must not block waiting on HTTP."""
    monkeypatch.setattr(webhook, "get_webhook", lambda: "https://hook.test/x")

    slow_calls = []

    def _slow_post(*args, **kwargs):
        slow_calls.append(time.monotonic())
        time.sleep(2.0)
        raise RuntimeError("never reached because we don't wait")

    with patch.object(webhook.requests, "post", side_effect=_slow_post):
        start = time.monotonic()
        ok = webhook.notify("payload")
        elapsed = time.monotonic() - start

    assert ok is True
    # Caller should return well under the 2s post latency.
    assert elapsed < 0.2, f"notify blocked for {elapsed}s"


def test_notify_dispatches_to_worker(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_webhook", lambda: "https://hook.test/x")
    posted = []

    def _record_post(url, json=None, timeout=None):
        posted.append({"url": url, "payload": json})
        return type("R", (), {"status_code": 204})()

    with patch.object(webhook.requests, "post", side_effect=_record_post):
        webhook.notify("hello", level="warn")
        # Wait briefly for the worker to drain.
        webhook._queue.join()

    assert len(posted) == 1
    assert posted[0]["url"] == "https://hook.test/x"
    assert posted[0]["payload"]["username"] == "Camoufox"


def test_notify_drops_old_when_queue_is_full(monkeypatch) -> None:
    """Flooding webhooks during a Discord outage must not OOM the process."""
    monkeypatch.setattr(webhook, "get_webhook", lambda: "https://hook.test/x")
    # Block the worker so the queue can fill up.
    block = lambda *a, **kw: time.sleep(60)  # noqa: E731
    with patch.object(webhook.requests, "post", side_effect=block):
        # Fill capacity (10) + push more.
        for i in range(15):
            webhook.notify(f"msg-{i}")
    # Bounded queue keeps memory usage finite.
    assert webhook._queue.qsize() <= 10


def test_notify_sync_returns_post_success(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_webhook", lambda: "https://hook.test/x")
    with patch.object(
        webhook.requests, "post",
        return_value=type("R", (), {"status_code": 204})(),
    ):
        assert webhook.notify_sync("hi") is True


def test_notify_sync_returns_false_on_network_error(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_webhook", lambda: "https://hook.test/x")
    with patch.object(
        webhook.requests, "post",
        side_effect=webhook.requests.RequestException("boom"),
    ):
        assert webhook.notify_sync("hi") is False


def test_payload_color_per_level() -> None:
    p = webhook._build_payload("x", "error", None)
    assert p["embeds"][0]["color"] == 0xE74C3C
    p = webhook._build_payload("x", "info", None)
    assert p["embeds"][0]["color"] == 0x3498DB
