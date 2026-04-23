"""Provider-level tests. Everything mocks requests.post — zero network."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from captchapool import (
    CapSolverProvider,
    CaptchaError,
    CaptchaInsufficientFunds,
    CaptchaInvalidKey,
    CaptchaTask,
    CaptchaTimeout,
    CaptchaUnsolvable,
    TwoCaptchaProvider,
)


def _json_response(payload):
    """Build a MagicMock that behaves like a requests.Response with JSON body."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


# ------------------------------------------------------------------ CapSolver


def test_capsolver_solve_recaptcha_v2_happy_path() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T1"}),
        _json_response({"errorId": 0, "status": "processing"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"gRecaptchaResponse": "TOKEN-123"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses) as mock_post:
        token = p.solve_recaptcha_v2("sk", "https://example.com")
    assert token == "TOKEN-123"
    # createTask + 2 getTaskResult calls
    assert mock_post.call_count == 3
    first_payload = mock_post.call_args_list[0].kwargs["json"]
    assert first_payload["task"]["type"] == "ReCaptchaV2TaskProxyLess"
    assert first_payload["task"]["websiteKey"] == "sk"


def test_capsolver_solve_recaptcha_v3_sends_action_and_min_score() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T2"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"gRecaptchaResponse": "v3-TOK"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses) as mock_post:
        token = p.solve_recaptcha_v3("sk", "https://x.com", action="login", min_score=0.7)
    assert token == "v3-TOK"
    sent_task = mock_post.call_args_list[0].kwargs["json"]["task"]
    assert sent_task["type"] == "ReCaptchaV3TaskProxyLess"
    assert sent_task["pageAction"] == "login"
    assert sent_task["minScore"] == 0.7


def test_capsolver_solve_turnstile() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T3"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"token": "TS-TOK"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses):
        token = p.solve_turnstile("sk", "https://x.com", action="submit")
    assert token == "TS-TOK"


def test_capsolver_solve_hcaptcha() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T4"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"gRecaptchaResponse": "HC-TOK"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses):
        token = p.solve_hcaptcha("sk", "https://x.com")
    assert token == "HC-TOK"


def test_capsolver_invalid_key() -> None:
    p = CapSolverProvider(api_key="bad", poll_interval=0)
    err = _json_response({
        "errorId": 1,
        "errorCode": "ERROR_KEY_DOES_NOT_EXIST",
        "errorDescription": "bad key",
    })
    with patch.object(p._session, "post", return_value=err):
        with pytest.raises(CaptchaInvalidKey):
            p.solve_recaptcha_v2("sk", "https://x.com")


def test_capsolver_insufficient_funds() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    err = _json_response({
        "errorId": 1,
        "errorCode": "ERROR_ZERO_BALANCE",
        "errorDescription": "topup",
    })
    with patch.object(p._session, "post", return_value=err):
        with pytest.raises(CaptchaInsufficientFunds):
            p.solve_hcaptcha("sk", "https://x.com")


def test_capsolver_unsolvable() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T5"}),
        _json_response({
            "errorId": 1, "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
            "errorDescription": "nope",
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses):
        with pytest.raises(CaptchaUnsolvable):
            p.solve_recaptcha_v2("sk", "https://x.com")


def test_capsolver_timeout() -> None:
    # timeout=0 so the while-loop condition fails on the very first iteration.
    p = CapSolverProvider(api_key="k", timeout=0.0, poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T6"}),
    ]
    with patch.object(p._session, "post", side_effect=responses):
        with pytest.raises(CaptchaTimeout):
            p.solve_recaptcha_v2("sk", "https://x.com")


def test_capsolver_generic_api_error() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    err = _json_response({
        "errorId": 1,
        "errorCode": "ERROR_SOMETHING_WEIRD",
        "errorDescription": "weird",
    })
    with patch.object(p._session, "post", return_value=err):
        with pytest.raises(CaptchaError) as ei:
            p.solve_recaptcha_v2("sk", "https://x.com")
        # Specifically NOT one of the subclasses.
        assert type(ei.value) is CaptchaError


def test_capsolver_get_balance() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    with patch.object(p._session, "post", return_value=_json_response({"errorId": 0, "balance": 42.5})):
        assert p.get_balance() == 42.5


def test_capsolver_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError):
        CapSolverProvider(api_key="")


def test_capsolver_solve_via_task_dispatcher() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "T7"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"gRecaptchaResponse": "DISPATCHED"},
        }),
    ]
    task = CaptchaTask(
        challenge_type="recaptcha_v2",
        site_key="sk",
        url="https://x.com",
        invisible=True,
    )
    with patch.object(p._session, "post", side_effect=responses):
        assert p.solve(task) == "DISPATCHED"


def test_captcha_task_recaptcha_v3_requires_action() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    task = CaptchaTask(challenge_type="recaptcha_v3", site_key="sk", url="https://x.com")
    with pytest.raises(ValueError):
        p.solve(task)


def test_captcha_task_unknown_type() -> None:
    p = CapSolverProvider(api_key="k", poll_interval=0)
    task = CaptchaTask(challenge_type="funcaptcha", site_key="sk", url="https://x.com")
    with pytest.raises(ValueError):
        p.solve(task)


# ----------------------------------------------------------------- 2Captcha


def test_twocaptcha_solve_recaptcha_v2_happy_path() -> None:
    p = TwoCaptchaProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "Q1"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"gRecaptchaResponse": "2C-TOK"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses) as mock_post:
        token = p.solve_recaptcha_v2("sk", "https://x.com")
    assert token == "2C-TOK"
    first_payload = mock_post.call_args_list[0].kwargs["json"]
    assert first_payload["task"]["type"] == "RecaptchaV2TaskProxyless"


def test_twocaptcha_invalid_key() -> None:
    p = TwoCaptchaProvider(api_key="bad", poll_interval=0)
    err = _json_response({
        "errorId": 1, "errorCode": "ERROR_WRONG_USER_KEY",
        "errorDescription": "bad",
    })
    with patch.object(p._session, "post", return_value=err):
        with pytest.raises(CaptchaInvalidKey):
            p.solve_hcaptcha("sk", "https://x.com")


def test_twocaptcha_get_balance() -> None:
    p = TwoCaptchaProvider(api_key="k", poll_interval=0)
    with patch.object(p._session, "post", return_value=_json_response({"errorId": 0, "balance": 9.99})):
        assert p.get_balance() == 9.99


def test_twocaptcha_turnstile_type_mapping() -> None:
    p = TwoCaptchaProvider(api_key="k", poll_interval=0)
    responses = [
        _json_response({"errorId": 0, "taskId": "Q2"}),
        _json_response({
            "errorId": 0, "status": "ready",
            "solution": {"token": "2C-TS"},
        }),
    ]
    with patch.object(p._session, "post", side_effect=responses) as mock_post:
        token = p.solve_turnstile("sk", "https://x.com")
    assert token == "2C-TS"
    assert mock_post.call_args_list[0].kwargs["json"]["task"]["type"] == "TurnstileTaskProxyless"
