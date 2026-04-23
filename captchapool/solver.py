"""
Multi-provider captcha solver.

A Solver wraps a list of CaptchaProvider instances and drives them
according to a strategy:

    "first"         — try providers in list order, first success wins.
                      On error, fall through to the next one unless it's
                      a fatal credential error (CaptchaInvalidKey /
                      CaptchaInsufficientFunds), which we still propagate
                      after trying everyone else.
    "fastest"       — snapshot the fastest-observed provider by avg latency
                      and try it first. Falls back to others on failure.
                      Behaves like "first" until enough samples accrue.
    "round-robin"   — rotate the starting provider each call so load is
                      spread evenly across accounts. Still falls through
                      on errors.

Stats (SolverStats) are tracked per provider so users can observe
success rate / average latency after a run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from captchapool.providers.base import (
    CaptchaError,
    CaptchaInsufficientFunds,
    CaptchaInvalidKey,
    CaptchaProvider,
    CaptchaTask,
)

log = logging.getLogger("captchapool.solver")


_STRATEGIES = ("first", "fastest", "round-robin")


@dataclass
class SolverStats:
    """Per-provider success/failure counters + rolling latency."""

    successes: int = 0
    failures: int = 0
    total_latency_s: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def attempts(self) -> int:
        return self.successes + self.failures

    @property
    def avg_latency_s(self) -> Optional[float]:
        if self.successes == 0:
            return None
        return self.total_latency_s / self.successes

    @property
    def success_rate(self) -> Optional[float]:
        if self.attempts == 0:
            return None
        return self.successes / self.attempts


class Solver:
    """Drive multiple captcha providers according to a strategy."""

    def __init__(
        self,
        providers: List[CaptchaProvider],
        strategy: str = "first",
    ) -> None:
        if not providers:
            raise ValueError("Solver needs at least one provider")
        if strategy not in _STRATEGIES:
            raise ValueError(
                f"unknown strategy {strategy!r}; must be one of {_STRATEGIES}"
            )
        self.providers = list(providers)
        self.strategy = strategy
        self.stats: Dict[str, SolverStats] = {p.name: SolverStats() for p in providers}
        self._rr_cursor = 0

    # --- ordering ---

    def _order_for_attempt(self) -> List[CaptchaProvider]:
        if self.strategy == "first":
            return list(self.providers)
        if self.strategy == "round-robin":
            n = len(self.providers)
            start = self._rr_cursor % n
            self._rr_cursor += 1
            return self.providers[start:] + self.providers[:start]
        # fastest: sort by avg_latency (seen providers first, unseen after)
        def sort_key(p: CaptchaProvider):
            avg = self.stats[p.name].avg_latency_s
            return (avg is None, avg if avg is not None else 0.0)
        return sorted(self.providers, key=sort_key)

    # --- dispatch ---

    def solve(self, challenge_type: str, **kwargs: Any) -> str:
        """Solve via the first provider that succeeds.

        Keyword arguments mirror CaptchaTask fields (site_key, url, action,
        min_score, invisible, ...). Raises the last error seen if every
        provider fails.
        """
        task = CaptchaTask(
            challenge_type=challenge_type,
            site_key=kwargs.pop("site_key"),
            url=kwargs.pop("url"),
            action=kwargs.pop("action", None),
            min_score=kwargs.pop("min_score", 0.3),
            invisible=kwargs.pop("invisible", False),
            extra=kwargs,
        )
        return self.solve_task(task)

    def solve_task(self, task: CaptchaTask) -> str:
        order = self._order_for_attempt()
        last_exc: Optional[Exception] = None
        for provider in order:
            st = self.stats[provider.name]
            start = time.perf_counter()
            try:
                token = provider.solve(task)
            except (CaptchaInvalidKey, CaptchaInsufficientFunds) as e:
                # Fatal per-provider but not fatal overall — keep trying others.
                st.failures += 1
                st.errors.append(f"{type(e).__name__}: {e}")
                last_exc = e
                log.warning("provider %s fatal credential error: %s", provider.name, e)
                continue
            except CaptchaError as e:
                st.failures += 1
                st.errors.append(f"{type(e).__name__}: {e}")
                last_exc = e
                log.info("provider %s soft-failed: %s", provider.name, e)
                continue
            except Exception as e:  # pragma: no cover — unexpected
                st.failures += 1
                st.errors.append(f"{type(e).__name__}: {e}")
                last_exc = e
                log.exception("provider %s raised unexpected error", provider.name)
                continue

            elapsed = time.perf_counter() - start
            st.successes += 1
            st.total_latency_s += elapsed
            return token

        assert last_exc is not None, "unreachable: providers non-empty but no attempts"
        raise last_exc


def solve(
    providers: List[CaptchaProvider],
    challenge_type: str,
    strategy: str = "first",
    **kwargs: Any,
) -> str:
    """Module-level one-shot helper: build a throwaway Solver and solve.

    Useful for scripts that don't care about stats across calls. Equivalent
    to `Solver(providers, strategy).solve(challenge_type, **kwargs)`.
    """
    return Solver(providers, strategy=strategy).solve(challenge_type, **kwargs)
