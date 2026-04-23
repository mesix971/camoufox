"""
taskqueue — persistent file-based task queue for Camoufox.

Tasks such as "launch profile X at URL Y and run script Z" can be
enqueued; workers pick them up via pop_due() and execute them. Supports
deferred scheduling, retries with exponential backoff+jitter, and
survives launcher restarts because state is on disk.

IMPORTANT: This queue is designed for a few dozen tasks/sec max. For
higher throughput use a real broker (Redis/SQS/RabbitMQ/Postgres).

Public API:
    Task, TaskStatus, RetryPolicy, TaskQueue

Typical use:
    from taskqueue import TaskQueue, RetryPolicy

    q = TaskQueue("/var/lib/camoufox/tasks")
    q.enqueue({"type": "launch-session", "profile_id": "abc",
               "url": "https://example.com"},
              retry_policy=RetryPolicy(max_retries=5))

    # In a worker loop:
    task = q.pop_due()
    if task:
        try:
            result = run(task.action)
            task.mark_success(result)
            q.save(task)
            q.release_lock(task.id)
        except Exception as e:
            if task.can_retry():
                delay = RetryPolicy(**task.retry_policy).delay_for_attempt(task.attempts)
                task.mark_failed(str(e), retry=True)
                q.reschedule(task, delay)
            else:
                task.mark_failed(str(e), retry=False)
                q.save(task)
                q.release_lock(task.id)
"""

from taskqueue.queue import TaskQueue
from taskqueue.task import RetryPolicy, Task, TaskStatus

__all__ = [
    "RetryPolicy",
    "Task",
    "TaskQueue",
    "TaskStatus",
]

__version__ = "0.1.0"
