"""TaskQueue tests: enqueue, pop atomicity, scheduling, retry, stats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from taskqueue import RetryPolicy, Task, TaskQueue, TaskStatus


ACTION = {"type": "launch-session", "profile_id": "p1", "url": "https://ex.com"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_enqueue_creates_queued_task(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION, tags=["vip"])
    assert t.status == TaskStatus.QUEUED.value
    assert t.action == ACTION
    assert t.tags == ["vip"]
    # File exists on disk.
    assert (tmp_path / f"{t.id}.json").exists()


def test_get_missing_raises(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    with pytest.raises(KeyError):
        q.get("nonexistent")


def test_get_returns_same_task(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    reloaded = q.get(t.id)
    assert reloaded == t


def test_list_filters_by_status_and_tag(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    a = q.enqueue(ACTION, tags=["vip"])
    b = q.enqueue(ACTION, tags=["bulk"])
    c = q.enqueue(ACTION, tags=["vip", "bulk"])

    # Mark one as SUCCESS to test status filter.
    b.mark_success({"ok": True})
    q.save(b)

    all_ids = {t.id for t in q.list()}
    assert all_ids == {a.id, b.id, c.id}

    queued_ids = {t.id for t in q.list(status=TaskStatus.QUEUED.value)}
    assert queued_ids == {a.id, c.id}

    vip_ids = {t.id for t in q.list(tag="vip")}
    assert vip_ids == {a.id, c.id}


def test_pop_due_returns_running_task(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    popped = q.pop_due()
    assert popped is not None
    assert popped.id == t.id
    assert popped.status == TaskStatus.RUNNING.value
    assert popped.started_at is not None

    # Persisted running on disk.
    assert q.get(t.id).status == TaskStatus.RUNNING.value


def test_pop_due_returns_none_when_empty(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    assert q.pop_due() is None


def test_pop_skips_future_scheduled_tasks(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    future = _now() + timedelta(hours=1)
    t_future = q.enqueue(ACTION, scheduled_at=future)
    t_now = q.enqueue(ACTION)

    popped = q.pop_due()
    assert popped is not None
    assert popped.id == t_now.id

    # Second pop finds nothing because only the future task remains queued.
    assert q.pop_due() is None

    # But passing a now-arg far in the future would release it.
    popped2 = q.pop_due(now=_now() + timedelta(hours=2))
    assert popped2 is not None
    assert popped2.id == t_future.id


def test_pop_is_atomic_single_task_single_claim(tmp_path) -> None:
    """Two consecutive pops against a single task -> only one succeeds.

    This simulates two workers racing: the winner gets the task, the
    loser gets None. We don't release the lock between calls.
    """
    q = TaskQueue(tmp_path)
    q.enqueue(ACTION)

    first = q.pop_due()
    second = q.pop_due()

    assert first is not None
    assert second is None
    assert first.status == TaskStatus.RUNNING.value


def test_pop_picks_oldest_scheduled_first(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    now = _now()
    # Enqueue in reverse scheduled order to verify sort is by scheduled_at.
    newer = q.enqueue(ACTION, scheduled_at=now - timedelta(seconds=10))
    older = q.enqueue(ACTION, scheduled_at=now - timedelta(seconds=100))
    popped = q.pop_due()
    assert popped is not None
    assert popped.id == older.id
    popped2 = q.pop_due()
    assert popped2 is not None
    assert popped2.id == newer.id


def test_reschedule_puts_task_back_queued_with_delay(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    claimed = q.pop_due()
    assert claimed is not None

    claimed.mark_failed("boom", retry=True)
    q.reschedule(claimed, delay_seconds=60)

    fresh = q.get(t.id)
    assert fresh.status == TaskStatus.QUEUED.value
    assert fresh.attempts == 1
    # scheduled_at should be roughly 60s in the future.
    from taskqueue.task import _parse_iso
    sched = _parse_iso(fresh.scheduled_at)
    delta = (sched - _now()).total_seconds()
    assert 30 <= delta <= 120  # generous window

    # Not due right now.
    assert q.pop_due() is None
    # Due in 2 minutes.
    future = _now() + timedelta(minutes=2)
    popped = q.pop_due(now=future)
    assert popped is not None
    assert popped.id == t.id


def test_reschedule_releases_lock_so_next_pop_can_claim(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    q.enqueue(ACTION)

    first = q.pop_due()
    assert first is not None
    # Before reschedule, a second pop gets nothing (lock held, running).
    assert q.pop_due() is None

    q.reschedule(first, delay_seconds=0)
    # Now another worker can claim it again.
    second = q.pop_due()
    assert second is not None
    assert second.id == first.id
    assert second.attempts == 1


def test_retry_policy_delay_increases_with_attempts(tmp_path) -> None:
    pol = RetryPolicy(backoff_seconds=10.0, backoff_factor=2.0, max_backoff_seconds=1000.0)
    # delay_for_attempt(0) ~ 10s, (1) ~ 20s, (2) ~ 40s.
    d0 = min(pol.delay_for_attempt(0) for _ in range(20))
    d2 = max(pol.delay_for_attempt(2) for _ in range(20))
    # Worst case d0 with +20% = 12, best case d2 with -20% = 32.
    # So d2 should always exceed d0.
    assert d0 < d2


def test_stats_counts_by_status(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    a = q.enqueue(ACTION)
    b = q.enqueue(ACTION)
    c = q.enqueue(ACTION)
    d = q.enqueue(ACTION)

    # a: success. b: failed. c: running via pop. d: stays queued.
    a.mark_success({"ok": True})
    q.save(a)
    b.mark_failed("err", retry=False)
    q.save(b)
    popped = q.pop_due()
    assert popped is not None and popped.id in {c.id, d.id}

    stats = q.stats()
    assert stats["success"] == 1
    assert stats["failed"] == 1
    assert stats["running"] == 1
    assert stats["queued"] == 1
    # Unused statuses are present with 0.
    assert stats["retrying"] == 0
    assert stats["cancelled"] == 0


def test_delete_removes_task_and_lock(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    q.pop_due()  # creates lockfile
    assert (tmp_path / f".lock.{t.id}").exists()
    q.delete(t.id)
    assert not (tmp_path / f"{t.id}.json").exists()
    assert not (tmp_path / f".lock.{t.id}").exists()
    with pytest.raises(KeyError):
        q.get(t.id)


def test_save_is_atomic_tmp_file_cleaned_up(tmp_path) -> None:
    """After a save, no .tmp files remain in the queue dir."""
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    t.mark_started()
    q.save(t)
    # No .tmp.* files should be left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp.")]
    assert leftovers == []


def test_enqueue_with_custom_retry_policy(tmp_path) -> None:
    q = TaskQueue(tmp_path)
    pol = RetryPolicy(max_retries=7, backoff_seconds=5.0, backoff_factor=3.0,
                     max_backoff_seconds=500.0)
    t = q.enqueue(ACTION, retry_policy=pol)
    assert t.retry_policy["max_retries"] == 7
    assert t.retry_policy["backoff_seconds"] == 5.0
    assert t.retry_policy["backoff_factor"] == 3.0
    assert t.retry_policy["max_backoff_seconds"] == 500.0

    # Round-trips through disk.
    reloaded = q.get(t.id)
    assert reloaded.retry_policy == t.retry_policy


def test_pop_skips_already_running_tasks(tmp_path) -> None:
    """A RUNNING task is not eligible for pop_due even if no lockfile exists."""
    q = TaskQueue(tmp_path)
    t = q.enqueue(ACTION)
    # Manually mark it running and save, without going through pop.
    t.mark_started()
    q.save(t)
    assert q.pop_due() is None
