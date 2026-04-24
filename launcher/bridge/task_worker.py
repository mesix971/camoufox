"""
Task worker — pulls tasks from taskqueue and executes them.

Runs as a standalone daemon:
    python -m launcher.bridge.task_worker

Action types understood:

  launch-session: spawn a session via SessionManager.spawn. The action
    dict mirrors launch-session command args (profile_id, proxy_id, url,
    warmup, persistent, auto_solve_captcha, run_macro, …).

  warmup: do a multi-site warmup session that builds cookies + history
    for a profile, then closes. Used 24-72h before a drop so the profile
    arrives with a real-looking browsing history.
    Args: { profile_id, target_url?, duration_minutes?=15, persistent=True }

  batch-launch: spawn N sessions by expanding a list of profile_ids
    (same shape as batch-launch-session command).

Each task's retry_policy is honored — on failure, the worker reschedules
with backoff. Non-retriable actions (e.g. unknown type) are marked FAILED.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import taskqueue

from launcher.bridge import webhook as webhook_mod


_STOP = False


def _log(level: str, msg: str, **extra) -> None:
    import json
    payload = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": level, "msg": msg, **extra,
    }
    print(json.dumps(payload), flush=True)


def _handle_signal(signum, _frame):
    global _STOP
    _STOP = True
    _log("info", f"received signal {signum}, stopping worker after current task")


def _task_queue() -> taskqueue.TaskQueue:
    return taskqueue.TaskQueue(
        os.environ.get(
            "TASKQUEUE_STORE",
            str(Path.home() / ".camoufox" / "launcher" / "tasks"),
        )
    )


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _dispatch_launch_session(action: Dict[str, Any]) -> Dict[str, Any]:
    from launcher.bridge.commands import launch_session
    return launch_session({k: v for k, v in action.items() if k != "type"})


def _dispatch_batch_launch(action: Dict[str, Any]) -> Dict[str, Any]:
    from launcher.bridge.commands import batch_launch_session
    return batch_launch_session({k: v for k, v in action.items() if k != "type"})


def _dispatch_warmup(action: Dict[str, Any]) -> Dict[str, Any]:
    """Launch a persistent session that visits mainstream sites + the target,
    then closes after `duration_minutes`. Builds cookies + history that make
    the profile look "aged" when it later enters the real queue."""
    from launcher.bridge.sessions import SessionManager
    from launcher.bridge.commands import sessions_root

    profile_id = action["profile_id"]
    target_url = action.get("target_url")
    duration_min = float(action.get("duration_minutes", 15))

    mgr = SessionManager(sessions_root())
    s = mgr.spawn(
        profile_id=profile_id,
        proxy_id=action.get("proxy_id"),
        url=target_url,
        headless=bool(action.get("headless", True)),
        warmup=True,           # visits mainstream sites first
        persistent=True,       # keep cookies
        auto_refresh=float(action.get("auto_refresh", 90.0)),  # keep page alive
    )
    _log("info", "warmup session launched",
         session_id=s.id, profile_id=profile_id, duration_min=duration_min)

    # Let the session run for the requested duration, then kill it.
    deadline = time.time() + duration_min * 60
    while not _STOP and time.time() < deadline:
        time.sleep(2.0)
    try:
        mgr.kill(s.id, timeout=5.0)
    except Exception:  # noqa: BLE001
        pass
    _log("info", "warmup session ended", session_id=s.id)
    return {"session_id": s.id, "duration_minutes": duration_min}


ACTIONS = {
    "launch-session": _dispatch_launch_session,
    "batch-launch": _dispatch_batch_launch,
    "warmup": _dispatch_warmup,
}


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


def run_once(queue: taskqueue.TaskQueue) -> bool:
    """Pop one due task, execute, save. Returns True if a task was processed."""
    task = queue.pop_due()
    if task is None:
        return False
    _log("info", "task claimed", id=task.id, type=task.action.get("type"))

    action_type = task.action.get("type")
    handler = ACTIONS.get(action_type)
    if handler is None:
        task.mark_failed(f"unknown action type: {action_type}", retry=False)
        queue.save(task)
        webhook_mod.notify(
            f"❌ Tâche `{task.id}` échouée : type inconnu `{action_type}`",
            level="error",
        )
        return True

    task.mark_started()
    queue.save(task)
    try:
        result = handler(task.action)
        task.mark_success(result)
        _log("info", "task done", id=task.id, ok=True)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        will_retry = task.can_retry()
        task.mark_failed(err, retry=will_retry)
        _log("error", "task failed", id=task.id, error=err, will_retry=will_retry)
        if will_retry:
            rp = _retry_policy(task)
            delay = rp.delay_for_attempt(task.attempts)
            queue.reschedule(task, delay)
            return True
        webhook_mod.notify(
            f"❌ Tâche `{task.id}` échouée définitivement : `{err}`",
            level="error",
        )
    queue.save(task)
    return True


def _retry_policy(task) -> "taskqueue.RetryPolicy":
    import taskqueue as tq
    if isinstance(task.retry_policy, dict):
        return tq.RetryPolicy(**task.retry_policy)
    return tq.RetryPolicy()


def run_forever(poll_interval: float = 3.0) -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    queue = _task_queue()
    _log("info", "task worker started", poll_interval=poll_interval)
    while not _STOP:
        did_work = run_once(queue)
        if not did_work:
            time.sleep(poll_interval)
    _log("info", "task worker stopped")


if __name__ == "__main__":
    run_forever()
