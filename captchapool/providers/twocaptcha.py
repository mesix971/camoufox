"""
2Captcha (2captcha.com) provider.

API docs: https://2captcha.com/api-docs

2Captcha's "v2" JSON API is intentionally shaped almost identically to
CapSolver's so we can share the same create/poll/balance skeleton with
slightly different URLs + task-type names.

Flow:
    1. POST /createTask  with {clientKey, task: {type, websiteURL, websiteKey, ...}}
    2. Poll /getTaskResult every `poll_interval`s until status == "ready"
    3. Extract solution.token / .gRecaptchaResponse
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

try:
    import requests
    from requests.exceptions import RequestException
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from captchapool.providers.base import (
    CaptchaError,
    CaptchaInsufficientFunds,
    CaptchaInvalidKey,
    CaptchaProvider,
    CaptchaTimeout,
    CaptchaUnsolvable,
)

log = logging.getLogger("captchapool.twocaptcha")


CREATE_TASK_URL = "https://api.2captcha.com/createTask"
GET_RESULT_URL = "https://api.2captcha.com/getTaskResult"
GET_BALANCE_URL = "https://api.2captcha.com/getBalance"


_TASK_TYPE_MAP = {
    "recaptcha_v2": "RecaptchaV2TaskProxyless",
    "recaptcha_v3": "RecaptchaV3TaskProxyless",
    "hcaptcha": "HCaptchaTaskProxyless",
    "turnstile": "TurnstileTaskProxyless",
}


def _raise_for_error(error_code: str, error_description: str) -> None:
    ec = (error_code or "").upper()
    msg = f"{error_code}: {error_description}" if error_description else error_code
    if ec in ("ERROR_KEY_DOES_NOT_EXIST", "ERROR_WRONG_USER_KEY"):
        raise CaptchaInvalidKey(msg)
    if ec in ("ERROR_ZERO_BALANCE", "ERROR_NO_SLOT_AVAILABLE"):
        raise CaptchaInsufficientFunds(msg)
    if ec in ("ERROR_CAPTCHA_UNSOLVABLE", "ERROR_UNSOLVABLE"):
        raise CaptchaUnsolvable(msg)
    raise CaptchaError(msg)


class TwoCaptchaProvider(CaptchaProvider):
    """2Captcha.com implementation of CaptchaProvider."""

    name = "twocaptcha"

    def __init__(
        self,
        api_key: str,
        timeout: float = 180.0,
        poll_interval: float = 5.0,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if not _HAS_REQUESTS:
            raise RuntimeError(
                "captchapool.twocaptcha requires the `requests` library."
            )
        super().__init__(api_key=api_key, timeout=timeout, poll_interval=poll_interval)
        self._session = session or requests.Session()

    # --- HTTP helpers ---

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self._session.post(url, json=payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except RequestException as e:
            raise CaptchaError(f"HTTP error talking to {url}: {e}") from e
        except ValueError as e:
            raise CaptchaError(f"invalid JSON from {url}: {e}") from e

        if data.get("errorId"):
            _raise_for_error(data.get("errorCode", ""), data.get("errorDescription", ""))
        return data

    def _create_task(self, task: Dict[str, Any]) -> str:
        data = self._post(CREATE_TASK_URL, {"clientKey": self.api_key, "task": task})
        task_id = data.get("taskId")
        if not task_id:
            raise CaptchaError(f"createTask returned no taskId: {data!r}")
        return str(task_id)

    def _poll_result(self, task_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            data = self._post(
                GET_RESULT_URL, {"clientKey": self.api_key, "taskId": task_id}
            )
            status = data.get("status")
            if status == "ready":
                return data.get("solution", {}) or {}
            if status == "processing":
                time.sleep(self.poll_interval)
                continue
            log.debug("twocaptcha unknown status %r for task %s", status, task_id)
            time.sleep(self.poll_interval)
        raise CaptchaTimeout(f"twocaptcha task {task_id} did not finish in {self.timeout}s")

    def _solve(self, challenge_type: str, extra_task: Dict[str, Any]) -> Dict[str, Any]:
        task = {"type": _TASK_TYPE_MAP[challenge_type], **extra_task}
        task_id = self._create_task(task)
        return self._poll_result(task_id)

    # --- solve_* methods ---

    def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
        **kwargs: Any,
    ) -> str:
        solution = self._solve(
            "recaptcha_v2",
            {
                "websiteURL": url,
                "websiteKey": site_key,
                "isInvisible": invisible,
                **kwargs,
            },
        )
        token = solution.get("gRecaptchaResponse") or solution.get("token")
        if not token:
            raise CaptchaError(f"no token in solution: {solution!r}")
        return token

    def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str,
        min_score: float = 0.3,
    ) -> str:
        solution = self._solve(
            "recaptcha_v3",
            {
                "websiteURL": url,
                "websiteKey": site_key,
                "pageAction": action,
                "minScore": min_score,
            },
        )
        token = solution.get("gRecaptchaResponse") or solution.get("token")
        if not token:
            raise CaptchaError(f"no token in solution: {solution!r}")
        return token

    def solve_hcaptcha(self, site_key: str, url: str) -> str:
        solution = self._solve(
            "hcaptcha",
            {"websiteURL": url, "websiteKey": site_key},
        )
        token = solution.get("token") or solution.get("gRecaptchaResponse")
        if not token:
            raise CaptchaError(f"no token in hcaptcha solution: {solution!r}")
        return token

    def solve_turnstile(
        self,
        site_key: str,
        url: str,
        action: Optional[str] = None,
    ) -> str:
        task: Dict[str, Any] = {"websiteURL": url, "websiteKey": site_key}
        if action:
            task["action"] = action
        solution = self._solve("turnstile", task)
        token = solution.get("token") or solution.get("gRecaptchaResponse")
        if not token:
            raise CaptchaError(f"no token in turnstile solution: {solution!r}")
        return token

    def get_balance(self) -> float:
        data = self._post(GET_BALANCE_URL, {"clientKey": self.api_key})
        balance = data.get("balance")
        if balance is None:
            raise CaptchaError(f"getBalance returned no balance field: {data!r}")
        return float(balance)
