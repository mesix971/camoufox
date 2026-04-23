"""Solver tests using an in-memory FakeProvider — no network, no mocks."""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from captchapool import (
    CaptchaError,
    CaptchaInsufficientFunds,
    CaptchaInvalidKey,
    CaptchaProvider,
    CaptchaUnsolvable,
    Solver,
    solve,
)


class FakeProvider(CaptchaProvider):
    """In-memory provider that returns/raises whatever you tell it to."""

    def __init__(self, name: str, *, outcomes: Optional[List[Any]] = None) -> None:
        super().__init__(api_key="fake")
        self.name = name
        # Each call consumes one outcome; a string is returned, an Exception raised.
        self.outcomes: List[Any] = list(outcomes or ["TOK-" + name])
        self.calls = 0

    def _next(self) -> str:
        self.calls += 1
        if not self.outcomes:
            outcome: Any = "TOK-" + self.name
        else:
            outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def solve_recaptcha_v2(self, site_key, url, invisible=False, **kwargs):
        return self._next()

    def solve_recaptcha_v3(self, site_key, url, action, min_score=0.3):
        return self._next()

    def solve_hcaptcha(self, site_key, url):
        return self._next()

    def solve_turnstile(self, site_key, url, action=None):
        return self._next()

    def get_balance(self) -> float:
        return 100.0


def test_solver_first_strategy_returns_first_success() -> None:
    a = FakeProvider("a", outcomes=["A-TOK"])
    b = FakeProvider("b", outcomes=["B-TOK"])
    s = Solver([a, b], strategy="first")
    token = s.solve("recaptcha_v2", site_key="sk", url="https://x.com")
    assert token == "A-TOK"
    assert a.calls == 1
    assert b.calls == 0
    assert s.stats["a"].successes == 1
    assert s.stats["b"].attempts == 0


def test_solver_falls_through_on_soft_error() -> None:
    a = FakeProvider("a", outcomes=[CaptchaUnsolvable("nope")])
    b = FakeProvider("b", outcomes=["B-TOK"])
    s = Solver([a, b])
    token = s.solve("hcaptcha", site_key="sk", url="https://x.com")
    assert token == "B-TOK"
    assert s.stats["a"].failures == 1
    assert s.stats["b"].successes == 1


def test_solver_falls_through_on_fatal_credential_error() -> None:
    a = FakeProvider("a", outcomes=[CaptchaInvalidKey("bad")])
    b = FakeProvider("b", outcomes=["B-TOK"])
    s = Solver([a, b])
    token = s.solve("hcaptcha", site_key="sk", url="https://x.com")
    assert token == "B-TOK"


def test_solver_raises_last_error_when_all_fail() -> None:
    a = FakeProvider("a", outcomes=[CaptchaInvalidKey("bad-a")])
    b = FakeProvider("b", outcomes=[CaptchaInsufficientFunds("broke-b")])
    s = Solver([a, b])
    with pytest.raises(CaptchaInsufficientFunds):
        s.solve("hcaptcha", site_key="sk", url="https://x.com")
    assert s.stats["a"].failures == 1
    assert s.stats["b"].failures == 1


def test_solver_round_robin_rotates_starting_provider() -> None:
    a = FakeProvider("a", outcomes=["A1", "A2"])
    b = FakeProvider("b", outcomes=["B1", "B2"])
    s = Solver([a, b], strategy="round-robin")
    t1 = s.solve("hcaptcha", site_key="sk", url="https://x.com")
    t2 = s.solve("hcaptcha", site_key="sk", url="https://x.com")
    # First call starts at index 0 (a), second at index 1 (b).
    assert t1 == "A1"
    assert t2 == "B1"


def test_solver_fastest_prefers_faster_provider_after_samples() -> None:
    # Seed stats so "b" has a lower avg latency than "a".
    a = FakeProvider("a", outcomes=["A-x"])
    b = FakeProvider("b", outcomes=["B-x"])
    s = Solver([a, b], strategy="fastest")
    s.stats["a"].successes = 1
    s.stats["a"].total_latency_s = 5.0
    s.stats["b"].successes = 1
    s.stats["b"].total_latency_s = 0.5
    token = s.solve("hcaptcha", site_key="sk", url="https://x.com")
    assert token == "B-x"
    assert b.calls == 1
    assert a.calls == 0


def test_solver_rejects_empty_providers() -> None:
    with pytest.raises(ValueError):
        Solver([], strategy="first")


def test_solver_rejects_unknown_strategy() -> None:
    with pytest.raises(ValueError):
        Solver([FakeProvider("a")], strategy="bogus")


def test_solver_stats_track_latency() -> None:
    a = FakeProvider("a", outcomes=["tok"])
    s = Solver([a])
    s.solve("hcaptcha", site_key="sk", url="https://x.com")
    st = s.stats["a"]
    assert st.success_rate == 1.0
    assert st.avg_latency_s is not None and st.avg_latency_s >= 0


def test_module_level_solve_helper() -> None:
    a = FakeProvider("a", outcomes=["ONESHOT"])
    token = solve([a], "hcaptcha", site_key="sk", url="https://x.com")
    assert token == "ONESHOT"


def test_solver_dispatch_recaptcha_v3_passes_action() -> None:
    seen: dict = {}

    class Capture(FakeProvider):
        def solve_recaptcha_v3(self, site_key, url, action, min_score=0.3):
            seen.update(site_key=site_key, url=url, action=action, min_score=min_score)
            return "V3"

    s = Solver([Capture("c")])
    token = s.solve(
        "recaptcha_v3",
        site_key="sk",
        url="https://x.com",
        action="login",
        min_score=0.5,
    )
    assert token == "V3"
    assert seen == {"site_key": "sk", "url": "https://x.com", "action": "login", "min_score": 0.5}


def test_solver_unexpected_exception_marks_failure_and_continues() -> None:
    a = FakeProvider("a", outcomes=[RuntimeError("kaboom")])
    b = FakeProvider("b", outcomes=["OK"])
    s = Solver([a, b])
    assert s.solve("hcaptcha", site_key="sk", url="https://x.com") == "OK"
    assert s.stats["a"].failures == 1
