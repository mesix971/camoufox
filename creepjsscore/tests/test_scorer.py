"""Scorer tests using an in-memory FakePage — no network, no Playwright."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from creepjsscore import CreepJSScore, Scorer, score_profile


class FakePage:
    """Duck-typed Playwright sync page for tests.

    Pass `scrape` (a dict, or Exception, or callable returning a dict) to
    control what the evaluated JS reports. `wait_exc` / `goto_exc` force
    failure at the navigation/ready stages respectively.
    """

    def __init__(
        self,
        scrape: Any = None,
        *,
        wait_exc: Optional[Exception] = None,
        goto_exc: Optional[Exception] = None,
    ) -> None:
        self.scrape = scrape
        self.wait_exc = wait_exc
        self.goto_exc = goto_exc
        self.goto_calls = []
        self.wait_calls = []
        self.evaluate_calls = []

    def goto(self, url: str, timeout: int = 0) -> None:
        self.goto_calls.append((url, timeout))
        if self.goto_exc is not None:
            raise self.goto_exc

    def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
        self.wait_calls.append((selector, timeout))
        if self.wait_exc is not None:
            raise self.wait_exc

    def evaluate(self, js: str) -> Any:
        self.evaluate_calls.append(js)
        s = self.scrape
        if callable(s):
            s = s()
        if isinstance(s, Exception):
            raise s
        return s


def _ok_scrape(**overrides: Any) -> Dict[str, Any]:
    base = {
        "fingerprint_score": 85.0,
        "trust_score": 80.0,
        "lies_count": 0,
        "bot_signals": 0,
        "has_webdriver": False,
        "consistent": True,
        "errors": [],
    }
    base.update(overrides)
    return base


# --- happy path ---

def test_happy_path_passes() -> None:
    page = FakePage(scrape=_ok_scrape())
    s = Scorer()
    r = s.score(page, profile_id="p1")
    assert isinstance(r, CreepJSScore)
    assert r.profile_id == "p1"
    assert r.fingerprint_score == 85.0
    assert r.trust_score == 80.0
    assert r.has_webdriver is False
    assert r.consistent is True
    assert r.error is None
    assert r.passed is True
    # page was driven in the expected order
    assert len(page.goto_calls) == 1
    assert page.goto_calls[0][0].startswith("https://abrahamjuliot.github.io/creepjs")
    assert len(page.wait_calls) == 1
    assert len(page.evaluate_calls) == 1


# --- threshold failures ---

def test_low_fingerprint_score_fails() -> None:
    page = FakePage(scrape=_ok_scrape(fingerprint_score=50.0))
    r = Scorer().score(page, profile_id="low-fp")
    assert r.fingerprint_score == 50.0
    assert r.passed is False


def test_low_trust_score_fails() -> None:
    page = FakePage(scrape=_ok_scrape(trust_score=40.0))
    r = Scorer().score(page, profile_id="low-trust")
    assert r.trust_score == 40.0
    assert r.passed is False


def test_webdriver_true_fails_even_with_good_scores() -> None:
    page = FakePage(scrape=_ok_scrape(
        fingerprint_score=99.0, trust_score=99.0, has_webdriver=True,
    ))
    r = Scorer().score(page, profile_id="wd")
    assert r.has_webdriver is True
    assert r.fingerprint_score == 99.0
    assert r.passed is False


# --- error paths ---

def test_timeout_returns_error_and_fails() -> None:
    page = FakePage(
        scrape=_ok_scrape(),
        wait_exc=TimeoutError("selector never appeared"),
    )
    r = Scorer(timeout=1.0).score(page, profile_id="timeout")
    assert r.error is not None
    assert "creepjs never loaded" in r.error
    assert r.passed is False
    # evaluate was never called because wait_for_selector threw
    assert page.evaluate_calls == []


def test_goto_failure_returns_error() -> None:
    page = FakePage(scrape=_ok_scrape(), goto_exc=RuntimeError("net down"))
    r = Scorer().score(page, profile_id="net")
    assert r.error is not None
    assert "goto failed" in r.error
    assert r.passed is False
    # wait_for_selector was never called because goto threw
    assert page.wait_calls == []


def test_scrape_exception_graceful() -> None:
    page = FakePage(scrape=RuntimeError("page context destroyed"))
    r = Scorer().score(page, profile_id="oops")
    assert r.error is not None
    assert "scrape failed" in r.error
    assert r.passed is False


def test_scrape_non_dict_return_graceful() -> None:
    page = FakePage(scrape="not-a-dict")
    r = Scorer().score(page, profile_id="weird")
    assert r.error is not None
    assert "expected dict" in r.error
    assert r.passed is False
    assert r.raw == {"scraped": "not-a-dict"}


def test_partial_scrape_records_error_keeps_defaults() -> None:
    # Missing fingerprint_score + trust_score — scorer should note the
    # unparseable state without crashing. Defaults (0.0) cause fail.
    page = FakePage(scrape={
        "fingerprint_score": "not-a-number",
        "trust_score": None,
        "lies_count": None,
        "bot_signals": None,
        "has_webdriver": False,
        "consistent": False,
        "errors": ["fp_score: bad selector"],
    })
    r = Scorer().score(page, profile_id="partial")
    assert r.error is not None
    assert "fingerprint_score unparseable" in r.error
    assert "js: fp_score: bad selector" in r.error
    # trust_score None -> 0.0; lies/bot None -> 0.
    assert r.trust_score == 0.0
    assert r.lies_count == 0
    assert r.bot_signals == 0
    assert r.passed is False


# --- helper + config ---

def test_score_profile_helper_with_tuple_thresholds() -> None:
    page = FakePage(scrape=_ok_scrape(fingerprint_score=60.0, trust_score=55.0))
    # With default thresholds this would fail; loosen them via the helper.
    r = score_profile(page, profile_id="h1", thresholds=(50.0, 50.0))
    assert r.passed is True
    assert r.pass_fp_threshold == 50.0
    assert r.pass_trust_threshold == 50.0


def test_score_profile_helper_with_dict_thresholds() -> None:
    page = FakePage(scrape=_ok_scrape())
    r = score_profile(page, profile_id="h2", thresholds={"fp": 90.0, "trust": 90.0})
    # fp=85 < 90 -> fails
    assert r.passed is False
    assert r.pass_fp_threshold == 90.0


def test_score_profile_helper_rejects_bad_thresholds() -> None:
    page = FakePage(scrape=_ok_scrape())
    with pytest.raises(TypeError):
        score_profile(page, profile_id="bad", thresholds=[1, 2, 3])


def test_scorer_rejects_bad_init_args() -> None:
    with pytest.raises(ValueError):
        Scorer(pass_fp_threshold=-1)
    with pytest.raises(ValueError):
        Scorer(pass_trust_threshold=101)
    with pytest.raises(ValueError):
        Scorer(timeout=0)


def test_scorer_custom_url_is_used() -> None:
    page = FakePage(scrape=_ok_scrape())
    Scorer(url="https://example.invalid/creep").score(page, profile_id="u")
    assert page.goto_calls[0][0] == "https://example.invalid/creep"


def test_result_is_json_serializable() -> None:
    import json
    page = FakePage(scrape=_ok_scrape())
    r = Scorer().score(page, profile_id="json")
    blob = json.dumps(r.to_dict())
    assert '"profile_id": "json"' in blob
    assert '"passed": true' in blob


# --- CLI-like integration mock ---

def test_cli_like_integration_batch_rejects_low_scores() -> None:
    """Simulate a batch runner that scores several profiles and filters."""

    # Three profiles with varying results; only p-good should pass.
    profiles = {
        "p-good": _ok_scrape(fingerprint_score=90.0, trust_score=85.0),
        "p-lowfp": _ok_scrape(fingerprint_score=40.0, trust_score=85.0),
        "p-wd": _ok_scrape(fingerprint_score=90.0, trust_score=85.0, has_webdriver=True),
    }

    results = []
    scorer = Scorer()
    for pid, scrape in profiles.items():
        page = FakePage(scrape=scrape)
        results.append(scorer.score(page, profile_id=pid))

    passed = [r for r in results if r.passed]
    rejected = [r for r in results if not r.passed]
    assert [r.profile_id for r in passed] == ["p-good"]
    assert sorted(r.profile_id for r in rejected) == ["p-lowfp", "p-wd"]
