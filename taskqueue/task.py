"""
Task dataclass + supporting types for the taskqueue package.

A Task is a serialisable unit of work enqueued for later execution by a
worker process. The queue itself does not know how to run anything; it
only owns the task's lifecycle state (QUEUED -> RUNNING -> SUCCESS /
FAILED / RETRYING / CANCELLED). The `action` dict is opaque to the
queue — the worker inspects `action["type"]` and decides what to do.

Typical action payloads:

    {"type": "launch-session", "profile_id": "...", "url": "...",
     "headless": False, "warmup": True}

Tasks are JSON-serialised one-file-per-task on disk (see queue.py).
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string, tolerating a 'Z' suffix."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    """Exponential backoff with jitter.

    delay_for_attempt(n) returns the backoff for the n-th retry attempt
    (0-indexed: attempt 0 is the first retry after the initial failure).
    """

    max_retries: int = 3
    backoff_seconds: float = 30.0
    backoff_factor: float = 2.0
    max_backoff_seconds: float = 900.0

    def delay_for_attempt(self, n: int) -> float:
        if n < 0:
            n = 0
        raw = self.backoff_seconds * (self.backoff_factor ** n)
        capped = min(raw, self.max_backoff_seconds)
        # +/- 20% jitter to avoid thundering herds.
        jitter = 1.0 + random.uniform(-0.2, 0.2)
        return max(0.0, capped * jitter)


@dataclass
class Task:
    id: str
    action: Dict[str, Any]
    scheduled_at: str = field(default_factory=_utc_now_iso)
    created_at: str = field(default_factory=_utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = TaskStatus.QUEUED.value
    attempts: int = 0
    retry_policy: Dict[str, Any] = field(default_factory=lambda: asdict(RetryPolicy()))
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    # --- serialisation ---

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Task":
        return cls(**json.loads(raw))

    # --- queries ---

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """True if scheduled_at is in the past (or equal to now)."""
        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        try:
            sched = _parse_iso(self.scheduled_at)
        except ValueError:
            # Unparseable scheduled_at -> treat as due now.
            return True
        return sched <= now

    def can_retry(self) -> bool:
        """Whether another retry attempt is allowed under the retry policy."""
        max_retries = int(self.retry_policy.get("max_retries", 0))
        return self.attempts < max_retries

    # --- state transitions ---

    def mark_started(self) -> None:
        self.status = TaskStatus.RUNNING.value
        self.started_at = _utc_now_iso()

    def mark_success(self, result: Optional[Dict[str, Any]] = None) -> None:
        self.status = TaskStatus.SUCCESS.value
        self.finished_at = _utc_now_iso()
        self.result = result
        self.error = None

    def mark_failed(self, error: str, retry: bool = False) -> None:
        """Record a failure.

        If retry=True the task is left in RETRYING status (caller is
        expected to call TaskQueue.reschedule to put it back on the queue).
        Otherwise the task is terminally FAILED.
        """
        self.error = error
        self.finished_at = _utc_now_iso()
        if retry:
            self.status = TaskStatus.RETRYING.value
        else:
            self.status = TaskStatus.FAILED.value
