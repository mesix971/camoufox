"""QueueMonitor tests: state transitions, front-of-queue firing, sync/async."""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pytest

from queuepool import QueueKind, QueueMonitor, QueueState


# ---------------------------------------------------------------------------
# Fake Page objects (duck-typed)
# ---------------------------------------------------------------------------

class FakeSyncPage:
    """Mimics camoufox sync_api page: .url is a property, .content() is sync."""

    def __init__(self, pages):
        # pages = list of (url, html) tuples; last one is sticky.
        self._pages = list(pages)
        self._i = 0

    @property
    def url(self) -> str:
        return self._pages[self._i][0]

    def content(self) -> str:
        return self._pages[self._i][1]

    def advance(self) -> None:
        if self._i < len(self._pages) - 1:
            self._i += 1


class FakeAsyncPage:
    """Mimics camoufox async_api page: .url is property, .content() is async."""

    def __init__(self, pages):
        self._pages = list(pages)
        self._i = 0

    @property
    def url(self) -> str:
        return self._pages[self._i][0]

    async def content(self) -> str:
        return self._pages[self._i][1]

    def advance(self) -> None:
        if self._i < len(self._pages) - 1:
            self._i += 1


def _queue_html(pos: int) -> str:
    return (
        "<html><body>"
        f"<span class='queue-position'>Your position: {pos}</span>"
        "</body></html>"
    )


def _queue_url() -> str:
    return "https://brand.queue-it.net/?c=brand&e=e1"


# ---------------------------------------------------------------------------
# check_once
# ---------------------------------------------------------------------------

def test_check_once_sync_returns_state_and_records_history() -> None:
    page = FakeSyncPage([(_queue_url(), _queue_html(500))])
    m = QueueMonitor()
    state = m.check_once_sync(page)
    assert state is not None
    assert state.kind == QueueKind.QUEUE_IT
    assert state.position == 500
    assert len(m.history) == 1


def test_check_once_sync_non_queue_returns_none_and_no_history() -> None:
    page = FakeSyncPage([("https://www.example.com/", "<html>hi</html>")])
    m = QueueMonitor()
    assert m.check_once_sync(page) is None
    assert m.history == []


def test_check_once_async_with_async_page() -> None:
    page = FakeAsyncPage([(_queue_url(), _queue_html(100))])
    m = QueueMonitor()
    state = asyncio.run(m.check_once(page))
    assert state is not None
    assert state.position == 100


def test_check_once_sync_raises_on_async_page() -> None:
    page = FakeAsyncPage([(_queue_url(), _queue_html(100))])
    m = QueueMonitor()
    with pytest.raises(TypeError):
        m.check_once_sync(page)


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def _state(pos: Optional[int], kind: QueueKind = QueueKind.QUEUE_IT) -> QueueState:
    return QueueState(kind=kind, position=pos, raw_url="https://x/")


def test_is_significant_change_first_time() -> None:
    m = QueueMonitor()
    assert m._is_significant_change(_state(100))


def test_is_significant_change_kind_transition() -> None:
    m = QueueMonitor()
    m._last_notified = _state(100, QueueKind.QUEUE_IT)
    assert m._is_significant_change(_state(100, QueueKind.CLOUDFLARE_WAITING))


def test_is_significant_change_small_delta_ignored() -> None:
    m = QueueMonitor(change_ratio=0.20)
    m._last_notified = _state(1000)
    # 1000 -> 900 = 10% delta, NOT significant at 20% threshold.
    assert not m._is_significant_change(_state(900))


def test_is_significant_change_large_delta_fires() -> None:
    m = QueueMonitor(change_ratio=0.20)
    m._last_notified = _state(1000)
    # 1000 -> 500 = 50% delta, significant.
    assert m._is_significant_change(_state(500))


def test_is_significant_change_none_positions() -> None:
    m = QueueMonitor()
    m._last_notified = _state(None)
    assert not m._is_significant_change(_state(None))
    # Going from None -> int is a change.
    assert m._is_significant_change(_state(100))


# ---------------------------------------------------------------------------
# sync_monitor end-to-end
# ---------------------------------------------------------------------------

def test_sync_monitor_fires_state_change_and_front_callbacks() -> None:
    pages = [
        (_queue_url(), _queue_html(1000)),
        (_queue_url(), _queue_html(500)),   # 50% delta -> state change
        (_queue_url(), _queue_html(5)),     # at front
    ]
    page = FakeSyncPage(pages)

    state_changes: List[QueueState] = []
    front_calls: List[QueueState] = []

    def on_state_change(s: QueueState) -> None:
        state_changes.append(s)

    def on_front(s: QueueState) -> None:
        front_calls.append(s)

    def fake_sleep(_: float) -> None:
        # Advance the fake page on each tick.
        page.advance()

    m = QueueMonitor(poll_interval=0.01, front_threshold=10)
    m.sync_monitor(
        page,
        on_state_change=on_state_change,
        on_front_of_queue=on_front,
        sleep=fake_sleep,
    )

    # First reading fires a state change (first-time rule), then pos 500 is
    # a 50% move so another fires. pos 5 is well below threshold but the
    # kind didn't change AND 500 -> 5 is also a large change, so a third
    # state change may or may not fire. We only assert a lower bound.
    assert len(state_changes) >= 2
    assert len(front_calls) == 1
    assert front_calls[0].position == 5
    assert m._front_fired is True
    assert len(m.history) >= 3


def test_sync_monitor_fires_front_only_once() -> None:
    pages = [(_queue_url(), _queue_html(5))]  # immediately at front
    page = FakeSyncPage(pages)
    front_calls: List[QueueState] = []

    m = QueueMonitor(poll_interval=0.01, front_threshold=10)
    m.sync_monitor(
        page,
        on_front_of_queue=lambda s: front_calls.append(s),
        sleep=lambda _: None,
        max_iterations=5,
        stop_when_front=False,
    )
    assert len(front_calls) == 1


def test_sync_monitor_stops_when_page_leaves_queue() -> None:
    pages = [
        (_queue_url(), _queue_html(500)),
        ("https://example.com/done", "<html>thanks!</html>"),
    ]
    page = FakeSyncPage(pages)

    calls = {"n": 0}

    def fake_sleep(_: float) -> None:
        calls["n"] += 1
        page.advance()

    m = QueueMonitor(poll_interval=0.01)
    m.sync_monitor(page, sleep=fake_sleep, max_iterations=10)

    # We iterated at most a couple of times before the loop exited.
    assert calls["n"] <= 2


def test_sync_monitor_max_iterations_stops() -> None:
    pages = [(_queue_url(), _queue_html(500))]  # never changes, never at front
    page = FakeSyncPage(pages)

    m = QueueMonitor(poll_interval=0.01, front_threshold=10)
    m.sync_monitor(
        page,
        sleep=lambda _: None,
        max_iterations=3,
    )
    assert len(m.history) == 3


# ---------------------------------------------------------------------------
# async monitor
# ---------------------------------------------------------------------------

def test_async_monitor_fires_callbacks() -> None:
    pages = [
        (_queue_url(), _queue_html(1000)),
        (_queue_url(), _queue_html(8)),
    ]
    page = FakeAsyncPage(pages)
    state_changes: List[QueueState] = []
    front_calls: List[QueueState] = []

    async def on_state_change(s: QueueState) -> None:
        state_changes.append(s)
        # Advance after first callback so next iter sees updated HTML.
        page.advance()

    async def on_front(s: QueueState) -> None:
        front_calls.append(s)

    async def run() -> None:
        m = QueueMonitor(poll_interval=0.001, front_threshold=10)
        await m.monitor(
            page,
            on_state_change=on_state_change,
            on_front_of_queue=on_front,
            max_iterations=5,
        )

    asyncio.run(run())
    assert len(state_changes) >= 1
    assert len(front_calls) == 1
    assert front_calls[0].position == 8


def test_async_monitor_accepts_sync_callback() -> None:
    page = FakeAsyncPage([(_queue_url(), _queue_html(3))])
    front_calls: List[QueueState] = []

    def sync_front(s: QueueState) -> None:
        front_calls.append(s)

    async def run() -> None:
        m = QueueMonitor(poll_interval=0.001, front_threshold=10)
        await m.monitor(page, on_front_of_queue=sync_front, max_iterations=3)

    asyncio.run(run())
    assert len(front_calls) == 1


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

def test_invalid_poll_interval() -> None:
    with pytest.raises(ValueError):
        QueueMonitor(poll_interval=0)


def test_invalid_front_threshold() -> None:
    with pytest.raises(ValueError):
        QueueMonitor(front_threshold=-1)


def test_invalid_change_ratio() -> None:
    with pytest.raises(ValueError):
        QueueMonitor(change_ratio=1.5)


def test_max_history_trims() -> None:
    m = QueueMonitor(max_history=3)
    for i in range(10):
        m._append_history(_state(i))
    assert len(m.history) == 3
    # Oldest discarded; last three kept.
    assert [s.position for s in m.history] == [7, 8, 9]
