"""
Retry helper with exponential backoff + jitter.

Used by session_runner for navigation + by the bridge for flaky operations.
Not a general-purpose lib — keeps things simple so we don't need tenacity.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Type, TypeVar

T = TypeVar("T")


@dataclass
class RetrySpec:
    max_attempts: int = 3
    initial_delay: float = 2.0
    factor: float = 2.0
    max_delay: float = 30.0
    jitter: float = 0.25  # ±25%

    def delay(self, attempt: int) -> float:
        base = min(self.initial_delay * self.factor ** attempt, self.max_delay)
        j = random.uniform(-self.jitter, self.jitter)
        return max(0.1, base * (1 + j))


def retry(
    func: Callable[[], T],
    spec: Optional[RetrySpec] = None,
    on_error: Optional[Callable[[int, Exception], None]] = None,
    retry_on: Optional[Iterable[Type[BaseException]]] = None,
) -> T:
    """Call `func`. On exception matching `retry_on` (default: Exception),
    sleep with exponential backoff and retry up to `max_attempts` times.
    """
    spec = spec or RetrySpec()
    retry_on = tuple(retry_on or (Exception,))
    last_err: Optional[BaseException] = None
    for attempt in range(spec.max_attempts):
        try:
            return func()
        except retry_on as e:
            last_err = e
            if on_error:
                try:
                    on_error(attempt, e)
                except Exception:  # noqa: BLE001 — callback shouldn't kill retry loop
                    pass
            if attempt + 1 >= spec.max_attempts:
                break
            time.sleep(spec.delay(attempt))
    assert last_err is not None
    raise last_err
