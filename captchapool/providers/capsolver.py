"""
CapSolver (capsolver.com) provider.

API docs: https://docs.capsolver.com/

Flow:
    1. POST /createTask  with {clientKey, task: {...}}
    2. Poll /getTaskResult every `poll_interval`s until status == "ready"
    3. Extract solution.gRecaptchaResponse / .token from the response

Error codes we map:
    ERROR_KEY_DOES_NOT_EXIST      -> CaptchaInvalidKey
    ERROR_ZERO_BALANCE            -> CaptchaInsufficientFunds
    ERROR_CAPTCHA_UNSOLVABLE      -> CaptchaUnsolvable
    everything else               -> CaptchaError
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

log = logging.getLogger("captchapool.capsolver")


CREATE_TASK_URL = "https://api.capsolver.com/createTask"
GET_RESULT_URL = "https://api.capsolver.com/getTaskResult"
GET_BALANCE_URL = "https://api.capsolver.com/getBalance"


_TASK_TYPE_MAP = {
    "recaptcha_v2": "ReCaptchaV2TaskProxyLess",
    "recaptcha_v3": "ReCaptchaV3TaskProxyLess",
    "hcaptcha": "HCaptchaTaskProxyLess",
    "turnstile": "AntiTurnstileTaskProxyLess",
}


def _raise_for_error(error_code: str, error_description: str) -> None:
    """Map CapSolver's errorCode to our exception hierarchy."""
    ec = (error_code or "").upper()
    msg = f"{error_code}: {error_description}" if error_description else error_code
    if ec in ("ERROR_KEY_DOES_NOT_EXIST", "ERROR_KEY_DENIED_ACCESS"):
        raise CaptchaInvalidKey(msg)
    if ec in ("ERROR_ZERO_BALANCE", "ERROR_NO_SLOT_AVAILABLE"):
        raise CaptchaInsufficientFunds(msg)
    if ec in ("ERROR_CAPTCHA_UNSOLVABLE", "ERROR_CAPTCHA_UNRESOLVED"):
        raise CaptchaUnsolvable(msg)
    raise CaptchaError(msg)


class CapSolverProvider(CaptchaProvider):
    """CapSolver.com implementation of CaptchaProvider."""

    name = "capsolver"

    def __init__(
        self,
        api_key: str,
        timeout: float = 180.0,
        poll_interval: float = 5.0,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if not _HAS_REQUESTS:
            raise RuntimeError(
                "captchapool.capsolver requires the `requests` library."
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

    # --- create + poll ---

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
            # Unknown status — log and keep polling; provider may be lagging.
            log.debug("capsolver unknown status %r for task %s", status, task_id)
            time.sleep(self.poll_interval)
        raise CaptchaTimeout(f"capsolver task {task_id} did not finish in {self.timeout}s")

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
        token = solution.get("gRecaptchaResponse")
        if not token:
            raise CaptchaError(f"no gRecaptchaResponse in solution: {solution!r}")
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
        token = solution.get("gRecaptchaResponse")
        if not token:
            raise CaptchaError(f"no gRecaptchaResponse in solution: {solution!r}")
        return token

    def solve_hcaptcha(self, site_key: str, url: str) -> str:
        solution = self._solve(
            "hcaptcha",
            {"websiteURL": url, "websiteKey": site_key},
        )
        token = solution.get("gRecaptchaResponse") or solution.get("token")
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
