"""
QueueMonitor — poll a page for queue position and fire callbacks.

The monitor is Playwright-agnostic: it accepts any object that quacks like a
Playwright page, i.e. exposes:

    * .url                        -> str (property OR callable)
    * .content()                  -> str (sync or coroutine returning str)
    * .evaluate(js_expr: str)     -> any (optional; used when available)

Both async and sync loops are provided because Camoufox users routinely mix
sync_api (camoufox.launch()) and async_api (camoufox.async_api.launch()).

Callbacks:
    on_state_change(state): fired when the position changes by more than
        `change_ratio` (default 20%) or the queue kind itself changes.
    on_front_of_queue(state): fired exactly once, the first time position
        is known and <= front_threshold.

A history of QueueStates is retained in `monitor.history`.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Awaitable, Callable, List, Optional

from queuepool.detectors import QueueState, detect_queue


log = logging.getLogger("queuepool.monitor")


# Callback signatures.
AsyncCallback = Callable[[QueueState], Awaitable[None]]
SyncCallback = Callable[[QueueState], None]


class QueueMonitor:
    def __init__(
        self,
        poll_interval: float = 10.0,
        front_threshold: int = 10,
        change_ratio: float = 0.20,
        max_history: int = 512,
    ):
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        if front_threshold < 0:
            raise ValueError("front_threshold must be >= 0")
        if not 0.0 <= change_ratio <= 1.0:
            raise ValueError("change_ratio must be in [0.0, 1.0]")
        self.poll_interval = poll_interval
        self.front_threshold = front_threshold
        self.change_ratio = change_ratio
        self.max_history = max_history

        self.history: List[QueueState] = []
        self._last_notified: Optional[QueueState] = None
        self._front_fired: bool = False

    # ------------------------------------------------------------------
    # One-shot check (async-friendly; handles sync page transparently).
    # ------------------------------------------------------------------

    async def check_once(self, page: Any) -> Optional[QueueState]:
        """Get url + content from `page`, run detect_queue, return result."""
        url = await _maybe_await(_get_url(page))
        html = await _maybe_await(_get_content(page))
        state = detect_queue(url or "", html)
        if state is not None:
            self._append_history(state)
        return state

    def check_once_sync(self, page: Any) -> Optional[QueueState]:
        """Synchronous variant: assumes page.url/page.content() are sync."""
        url = _get_url(page)
        if inspect.iscoroutine(url):
            url.close()
            raise TypeError(
                "page.url returned a coroutine; use check_once() instead of "
                "check_once_sync() for async pages."
            )
        html = _get_content(page)
        if inspect.iscoroutine(html):
            html.close()
            raise TypeError(
                "page.content() returned a coroutine; use check_once() instead."
            )
        state = detect_queue(url or "", html)
        if state is not None:
            self._append_history(state)
        return state

    # ------------------------------------------------------------------
    # Change detection.
    # ------------------------------------------------------------------

    def _append_history(self, state: QueueState) -> None:
        self.history.append(state)
        if len(self.history) > self.max_history:
            # Trim from the left; oldest first.
            self.history = self.history[-self.max_history:]

    def _is_significant_change(self, new: QueueState) -> bool:
        """True if the new state is worth notifying about."""
        prev = self._last_notified
        if prev is None:
            return True  # first real reading
        if prev.kind != new.kind:
            return True
        # Kind is the same; compare positions.
        if new.position is None and prev.position is None:
            return False
        if new.position is None or prev.position is None:
            return True
        if prev.position == 0:
            return new.position != 0
        delta = abs(new.position - prev.position)
        return (delta / prev.position) > self.change_ratio

    def _at_front(self, state: QueueState) -> bool:
        return state.position is not None and state.position <= self.front_threshold

    # ------------------------------------------------------------------
    # Async loop.
    # ------------------------------------------------------------------

    async def monitor(
        self,
        page: Any,
        on_state_change: Optional[AsyncCallback] = None,
        on_front_of_queue: Optional[AsyncCallback] = None,
        stop_when_front: bool = True,
        max_iterations: Optional[int] = None,
    ) -> None:
        """
        Poll `page` every `poll_interval` seconds. Fire callbacks on change.

        Stops when:
          - the front-of-queue callback has fired AND stop_when_front=True
          - the page no longer looks like a queue (detect returns None)
          - max_iterations reached (useful in tests)
          - asyncio.CancelledError is raised
        """
        count = 0
        while True:
            try:
                state = await self.check_once(page)
            except Exception as e:  # noqa: BLE001
                log.warning("check_once failed: %s", e)
                state = None

            if state is None:
                log.debug("page no longer matches a known queue; exiting loop")
                return

            if self._is_significant_change(state):
                self._last_notified = state
                if on_state_change is not None:
                    await _invoke(on_state_change, state)

            if not self._front_fired and self._at_front(state):
                self._front_fired = True
                if on_front_of_queue is not None:
                    await _invoke(on_front_of_queue, state)
                if stop_when_front:
                    return

            count += 1
            if max_iterations is not None and count >= max_iterations:
                return

            await asyncio.sleep(self.poll_interval)

    # ------------------------------------------------------------------
    # Sync loop. time.sleep based, for camoufox.sync_api users.
    # ------------------------------------------------------------------

    def sync_monitor(
        self,
        page: Any,
        on_state_change: Optional[SyncCallback] = None,
        on_front_of_queue: Optional[SyncCallback] = None,
        stop_when_front: bool = True,
        max_iterations: Optional[int] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Synchronous version of monitor(). `sleep` is overridable for tests."""
        count = 0
        while True:
            try:
                state = self.check_once_sync(page)
            except Exception as e:  # noqa: BLE001
                log.warning("check_once_sync failed: %s", e)
                state = None

            if state is None:
                log.debug("page no longer matches a known queue; exiting loop")
                return

            if self._is_significant_change(state):
                self._last_notified = state
                if on_state_change is not None:
                    on_state_change(state)

            if not self._front_fired and self._at_front(state):
                self._front_fired = True
                if on_front_of_queue is not None:
                    on_front_of_queue(state)
                if stop_when_front:
                    return

            count += 1
            if max_iterations is not None and count >= max_iterations:
                return

            sleep(self.poll_interval)


# ---------------------------------------------------------------------------
# Duck-typing helpers
# ---------------------------------------------------------------------------

def _get_url(page: Any) -> Any:
    """Extract URL, tolerating both property and method forms."""
    u = getattr(page, "url", None)
    if callable(u):
        return u()
    return u


def _get_content(page: Any) -> Any:
    fn = getattr(page, "content", None)
    if fn is None:
        return None
    if callable(fn):
        return fn()
    return fn


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _invoke(cb: AsyncCallback, state: QueueState) -> None:
    result = cb(state)
    if inspect.isawaitable(result):
        await result
