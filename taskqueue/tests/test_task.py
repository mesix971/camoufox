"""Task dataclass tests: state transitions, retry policy, JSON round-trip."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from taskqueue import RetryPolicy, Task, TaskStatus


def _mk(**kw) -> Task:
    return Task(
        id=Task.new_id(),
        action={"type": "launch-session", "profile_id": "abc", "url": "https://ex.com"},
        **kw,
    )


def test_new_id_is_12_hex_chars() -> None:
    tid = Task.new_id()
    assert len(tid) == 12
    int(tid, 16)  # parses as hex


def test_defaults() -> None:
    t = _mk()
    assert t.status == TaskStatus.QUEUED.value
    assert t.attempts == 0
    assert t.started_at is None
    assert t.finished_at is None
    assert t.error is None
    assert t.result is None
    assert t.tags == []
    # retry_policy default is asdict of RetryPolicy()
    assert t.retry_policy["max_retries"] == 3
    assert t.retry_policy["backoff_seconds"] == 30.0


def test_mark_started() -> None:
    t = _mk()
    t.mark_started()
    assert t.status == TaskStatus.RUNNING.value
    assert t.started_at is not None


def test_mark_success_clears_error() -> None:
    t = _mk(error="prev")
    t.mark_success({"ok": True, "url": "https://x"})
    assert t.status == TaskStatus.SUCCESS.value
    assert t.result == {"ok": True, "url": "https://x"}
    assert t.finished_at is not None
    assert t.error is None


def test_mark_failed_terminal_vs_retrying() -> None:
    t = _mk()
    t.mark_failed("network blip", retry=True)
    assert t.status == TaskStatus.RETRYING.value
    assert t.error == "network blip"

    t2 = _mk()
    t2.mark_failed("hard error", retry=False)
    assert t2.status == TaskStatus.FAILED.value
    assert t2.error == "hard error"


def test_is_due_past_and_future() -> None:
    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=60)).isoformat(timespec="seconds")
    future = (now + timedelta(seconds=60)).isoformat(timespec="seconds")
    t_past = _mk(scheduled_at=past)
    t_future = _mk(scheduled_at=future)
    assert t_past.is_due(now) is True
    assert t_future.is_due(now) is False


def test_can_retry_respects_max_retries() -> None:
    t = _mk(retry_policy=asdict(RetryPolicy(max_retries=2)))
    assert t.can_retry() is True
    t.attempts = 1
    assert t.can_retry() is True
    t.attempts = 2
    assert t.can_retry() is False
    t.attempts = 3
    assert t.can_retry() is False


def test_retry_policy_delay_scales_and_caps() -> None:
    pol = RetryPolicy(
        max_retries=10, backoff_seconds=10.0, backoff_factor=2.0, max_backoff_seconds=60.0
    )
    # Take many samples to cover jitter bounds.
    samples_0 = [pol.delay_for_attempt(0) for _ in range(50)]
    samples_1 = [pol.delay_for_attempt(1) for _ in range(50)]
    samples_big = [pol.delay_for_attempt(10) for _ in range(50)]

    # Attempt 0: raw=10, +/-20% jitter -> [8, 12]
    assert all(8.0 <= s <= 12.0 for s in samples_0)
    # Attempt 1: raw=20, +/-20% jitter -> [16, 24]
    assert all(16.0 <= s <= 24.0 for s in samples_1)
    # Attempt 10: raw way past cap=60; jitter applied to cap -> [48, 72]
    assert all(48.0 <= s <= 72.0 for s in samples_big)


def test_retry_policy_negative_attempt_treated_as_zero() -> None:
    pol = RetryPolicy(backoff_seconds=10.0, backoff_factor=2.0, max_backoff_seconds=1000.0)
    samples = [pol.delay_for_attempt(-5) for _ in range(20)]
    assert all(8.0 <= s <= 12.0 for s in samples)


def test_json_round_trip_preserves_everything() -> None:
    t = _mk(tags=["scrape", "vip"])
    t.mark_started()
    t.mark_success({"status": 200})
    t.attempts = 2
    raw = t.to_json()
    t2 = Task.from_json(raw)
    assert t == t2
