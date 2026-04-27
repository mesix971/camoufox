"""
Minimal Discord webhook posting.

Used by the session_runner and scheduler to notify about:
  - session crashed
  - queue position reached front
  - proxy mass-death
  - health check anomalies

Config: a single webhook URL stored in ~/.camoufox/launcher/webhook.json
or overridden via CAMOUFOX_DISCORD_WEBHOOK env var. One URL only; if you
want multiple channels, use Discord's Channel Webhooks forwarding.

Async by default
----------------
``notify()`` is fire-and-forget — it enqueues the payload onto an
in-process worker thread and returns immediately. Callers in the hot
path (session_runner main loop, queue position polling) never block on
network IO. If Discord is slow or down, only the worker thread waits;
the caller moves on.

For the rare callsite that needs to know the post succeeded (a final
crash report just before exit, say), use ``notify_sync()`` which keeps
the original synchronous semantics.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import threading
from pathlib import Path
from typing import Optional

import requests


def _config_path() -> Path:
    return Path(
        os.environ.get(
            "CAMOUFOX_WEBHOOK_CONFIG",
            str(Path.home() / ".camoufox" / "launcher" / "webhook.json"),
        )
    )


def set_webhook(url: str) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"url": url}))


def get_webhook() -> Optional[str]:
    env = os.environ.get("CAMOUFOX_DISCORD_WEBHOOK")
    if env:
        return env
    p = _config_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("url")
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Async dispatch
# ---------------------------------------------------------------------------

# Bounded queue so a webhook outage can't grow memory unboundedly. When
# full we drop the oldest message — fresher events matter more than a
# stale backlog of 30-minute-old crash reports.
_MAX_QUEUE_SIZE = 1000

_queue: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
_worker_started = threading.Event()
_worker_lock = threading.Lock()


def _ensure_worker() -> None:
    """Start the daemon worker on first use. Idempotent and thread-safe."""
    if _worker_started.is_set():
        return
    with _worker_lock:
        if _worker_started.is_set():
            return
        thread = threading.Thread(
            target=_worker_loop, name="webhook-dispatcher", daemon=True
        )
        thread.start()
        _worker_started.set()
        atexit.register(_drain, timeout=2.0)


def _worker_loop() -> None:
    """Pop payloads off the queue and POST them. Runs forever as a daemon."""
    while True:
        # Re-read the module-level _queue each iteration so a test fixture
        # that swaps it out mid-test doesn't cross-talk between iterations.
        q = _queue
        item = q.get()
        try:
            if item is not None:  # None is a sentinel that just bumps the counter
                try:
                    requests.post(item["url"], json=item["payload"], timeout=2.0)
                except requests.RequestException:
                    pass  # best-effort; don't retry, just drop
        finally:
            try:
                q.task_done()
            except ValueError:
                # Test isolation: q was replaced after we got() from it.
                pass


def _drain(timeout: float) -> None:
    """Flush the queue at process exit (best-effort, capped by ``timeout``)."""
    try:
        # Wait for queued items to drain, but never block shutdown forever.
        _queue.join_with_timeout(timeout) if hasattr(_queue, "join_with_timeout") \
            else _join_queue(_queue, timeout)
    except Exception:  # noqa: BLE001
        pass


def _join_queue(q: "queue.Queue", timeout: float) -> None:
    """Equivalent to Queue.join() with a timeout."""
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if q.unfinished_tasks == 0:
            return
        time.sleep(0.05)


def _build_payload(content: str, level: str, embeds: Optional[list]) -> dict:
    color = {
        "info": 0x3498DB,
        "success": 0x2ECC71,
        "warn": 0xF39C12,
        "error": 0xE74C3C,
    }.get(level, 0x95A5A6)
    return {
        "username": "Camoufox",
        "embeds": embeds or [{
            "description": content,
            "color": color,
        }],
    }


def notify(
    content: str,
    level: str = "info",
    url: Optional[str] = None,
    embeds: Optional[list] = None,
) -> bool:
    """Enqueue a Discord webhook post for the dispatcher thread to send.

    Returns True if the payload was enqueued (or False if no webhook URL
    is configured / queue is full). **Does not** wait for the HTTP
    response — call ``notify_sync()`` if you need the success status.

    Designed for the runner hot path: a slow or dead webhook host must
    never block session monitoring or rate-limit polling.
    """
    hook = url or get_webhook()
    if not hook:
        return False
    _ensure_worker()
    payload = _build_payload(content, level, embeds)
    try:
        _queue.put_nowait({"url": hook, "payload": payload})
        return True
    except queue.Full:
        # Drop one old entry to make room for the new one. Fresh events
        # matter more than stale ones during an outage.
        try:
            _queue.get_nowait()
            _queue.task_done()
        except queue.Empty:
            pass
        try:
            _queue.put_nowait({"url": hook, "payload": payload})
            return True
        except queue.Full:
            return False


def notify_sync(
    content: str,
    level: str = "info",
    url: Optional[str] = None,
    embeds: Optional[list] = None,
    timeout: float = 5.0,
) -> bool:
    """Synchronous post. Returns True on success, False on failure.

    Use only at clean-exit points where you genuinely need to know the
    message landed (final crash dump, manual test). Anywhere else,
    prefer ``notify()``.
    """
    hook = url or get_webhook()
    if not hook:
        return False
    payload = _build_payload(content, level, embeds)
    try:
        r = requests.post(hook, json=payload, timeout=timeout)
        return 200 <= r.status_code < 300
    except requests.RequestException:
        return False
