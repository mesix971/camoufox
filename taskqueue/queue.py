"""
File-based persistent task queue.

Design
------
One JSON file per task:

    <root>/<task_id>.json

Pop atomicity uses a side lockfile per task:

    <root>/.lock.<task_id>

Claiming a task is a two-step atomic rename dance:

    1. Candidate task is chosen by listing *.json files, filtering to
       QUEUED tasks whose scheduled_at is in the past.
    2. To claim it, the worker writes a unique temp file and
       os.renames() it to `<root>/.lock.<task_id>`. `os.rename` is
       atomic on POSIX within the same filesystem, and fails if the
       destination already exists (when using os.link + unlink, or on
       Windows). We use Path.hardlink_to + unlink semantics via
       os.link, which fails atomically if the link already exists.

This is sufficient for a handful of cooperating workers on the same
machine. Multiple worker *processes* can safely call pop_due() without
double-claiming a task.

IMPORTANT: This queue is designed for a few dozen tasks/sec max. For
higher throughput or distributed workers across machines, use a real
broker (Redis/SQS/RabbitMQ/Postgres LISTEN-NOTIFY).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from taskqueue.task import RetryPolicy, Task, TaskStatus


LOCK_PREFIX = ".lock."
TMP_PREFIX = ".tmp."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


class TaskQueue:
    """File-based persistent task queue.

    Not a distributed broker. Safe for multiple worker *processes* on a
    single host sharing the same root directory (POSIX atomic renames).
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths ---

    def _task_path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def _lock_path(self, task_id: str) -> Path:
        return self.root / f"{LOCK_PREFIX}{task_id}"

    # --- low-level IO ---

    def _atomic_write(self, path: Path, data: str) -> None:
        tmp = path.with_name(f"{TMP_PREFIX}{path.name}.{os.getpid()}")
        with tmp.open("w") as f:
            f.write(data)
        os.replace(tmp, path)

    def _read_task(self, path: Path) -> Task:
        with path.open() as f:
            return Task.from_json(f.read())

    # --- CRUD ---

    def save(self, task: Task) -> None:
        """Atomic write (tmp + replace)."""
        self._atomic_write(self._task_path(task.id), task.to_json())

    def get(self, task_id: str) -> Task:
        path = self._task_path(task_id)
        if not path.exists():
            raise KeyError(f"task not found: {task_id}")
        return self._read_task(path)

    def delete(self, task_id: str) -> None:
        path = self._task_path(task_id)
        if path.exists():
            path.unlink()
        lock = self._lock_path(task_id)
        if lock.exists():
            try:
                lock.unlink()
            except FileNotFoundError:
                pass

    def exists(self, task_id: str) -> bool:
        return self._task_path(task_id).exists()

    # --- enqueue ---

    def enqueue(
        self,
        action: Dict,
        scheduled_at: Optional[datetime] = None,
        retry_policy: Optional[RetryPolicy] = None,
        tags: Iterable[str] = (),
    ) -> Task:
        policy = retry_policy or RetryPolicy()
        sched = scheduled_at or _utc_now()
        task = Task(
            id=Task.new_id(),
            action=dict(action),
            scheduled_at=_iso(sched),
            retry_policy={
                "max_retries": policy.max_retries,
                "backoff_seconds": policy.backoff_seconds,
                "backoff_factor": policy.backoff_factor,
                "max_backoff_seconds": policy.max_backoff_seconds,
            },
            tags=list(tags),
        )
        self.save(task)
        return task

    # --- listing ---

    def _iter_task_files(self) -> Iterable[Path]:
        for path in sorted(self.root.glob("*.json")):
            name = path.name
            if name.startswith(LOCK_PREFIX) or name.startswith(TMP_PREFIX):
                continue
            yield path

    def list(self, status: Optional[str] = None, tag: Optional[str] = None) -> List[Task]:
        out: List[Task] = []
        for path in self._iter_task_files():
            try:
                t = self._read_task(path)
            except (OSError, json.JSONDecodeError):
                continue
            if status is not None and t.status != status:
                continue
            if tag is not None and tag not in t.tags:
                continue
            out.append(t)
        out.sort(key=lambda t: t.created_at)
        return out

    # --- atomic pop ---

    def _try_claim(self, task_id: str) -> bool:
        """Try to atomically create a lockfile for task_id.

        Returns True iff we won the race. Uses os.link() which fails
        atomically with FileExistsError if the destination already
        exists — safe across processes on the same POSIX filesystem.
        """
        lock = self._lock_path(task_id)
        tmp = self.root / f"{TMP_PREFIX}claim.{task_id}.{os.getpid()}"
        try:
            with tmp.open("w") as f:
                f.write(str(os.getpid()))
            try:
                os.link(tmp, lock)
                return True
            except FileExistsError:
                return False
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def pop_due(self, now: Optional[datetime] = None) -> Optional[Task]:
        """Atomically claim the oldest due QUEUED task.

        Returns the claimed Task with status=RUNNING, or None if
        nothing is due. Safe against concurrent workers: only one will
        succeed at claiming any given task.
        """
        if now is None:
            now = _utc_now()

        # Collect candidates: QUEUED, due, no lockfile yet.
        candidates: List[Task] = []
        for path in self._iter_task_files():
            try:
                t = self._read_task(path)
            except (OSError, json.JSONDecodeError):
                continue
            if t.status != TaskStatus.QUEUED.value:
                continue
            if not t.is_due(now):
                continue
            if self._lock_path(t.id).exists():
                continue
            candidates.append(t)

        # Oldest-scheduled first, tiebreak by created_at.
        candidates.sort(key=lambda t: (t.scheduled_at, t.created_at))

        for task in candidates:
            if not self._try_claim(task.id):
                continue
            # Re-read under the lock to avoid a TOCTOU on status.
            try:
                fresh = self.get(task.id)
            except KeyError:
                self._lock_path(task.id).unlink(missing_ok=True)
                continue
            if fresh.status != TaskStatus.QUEUED.value:
                # Someone transitioned it between our listing and claim.
                self._lock_path(task.id).unlink(missing_ok=True)
                continue
            fresh.mark_started()
            self.save(fresh)
            return fresh

        return None

    def release_lock(self, task_id: str) -> None:
        """Release the claim lock for a task (typically on completion)."""
        lock = self._lock_path(task_id)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass

    # --- retry ---

    def reschedule(self, task: Task, delay_seconds: float) -> Task:
        """Put a task back on the queue after a delay.

        Clears the lock (if any), sets status=QUEUED, bumps attempts,
        and sets scheduled_at to now + delay.
        """
        task.status = TaskStatus.QUEUED.value
        task.attempts += 1
        task.started_at = None
        task.finished_at = None
        task.scheduled_at = _iso(_utc_now() + timedelta(seconds=max(0.0, delay_seconds)))
        self.save(task)
        self.release_lock(task.id)
        return task

    # --- stats ---

    def stats(self) -> Dict[str, int]:
        """Counts of tasks by status. Missing statuses report 0."""
        counts: Counter = Counter()
        for t in self.list():
            counts[t.status] += 1
        out = {s.value: 0 for s in TaskStatus}
        out.update(counts)
        return out
