"""
Abstract captcha provider.

All concrete providers (CapSolver, 2Captcha, ...) implement the same
five solve_* methods plus get_balance(). The Solver orchestrator only
talks to this interface, so providers can be swapped or raced without
the caller knowing which API was used.

Error hierarchy:
    CaptchaError
        CaptchaInvalidKey           — bad/expired API key
        CaptchaInsufficientFunds    — account balance too low
        CaptchaUnsolvable           — provider returned ERROR_CAPTCHA_UNSOLVABLE
        CaptchaTimeout              — exceeded self.timeout while polling
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class CaptchaError(Exception):
    """Base exception for all captchapool errors."""


class CaptchaTimeout(CaptchaError):
    """Raised when polling exceeds the provider's timeout budget."""


class CaptchaInvalidKey(CaptchaError):
    """Raised when the provider rejects our API key (bad, expired, banned)."""


class CaptchaInsufficientFunds(CaptchaError):
    """Raised when the provider says balance/credits are too low to solve."""


class CaptchaUnsolvable(CaptchaError):
    """Raised when the provider attempted but couldn't solve the challenge."""


@dataclass
class CaptchaTask:
    """Descriptor for a single captcha challenge to solve.

    `challenge_type` is one of:
        "recaptcha_v2", "recaptcha_v3", "hcaptcha", "turnstile".
    Other fields mirror the solve_* kwargs.
    """

    challenge_type: str
    site_key: str
    url: str
    action: Optional[str] = None        # recaptcha_v3, turnstile
    min_score: float = 0.3              # recaptcha_v3
    invisible: bool = False             # recaptcha_v2
    extra: Dict[str, Any] = field(default_factory=dict)


class CaptchaProvider(ABC):
    """
    Abstract base class for captcha-solving providers.

    Subclasses must implement the five solve_* methods plus get_balance().
    The constructor stores api_key + polling/timeout knobs common to all
    providers; subclasses can add their own kwargs.
    """

    #: Short human-readable provider name, e.g. "capsolver" / "twocaptcha".
    name: str = "base"

    def __init__(
        self,
        api_key: str,
        timeout: float = 180.0,
        poll_interval: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must be non-empty")
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    # --- captcha solvers ---

    @abstractmethod
    def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
        **kwargs: Any,
    ) -> str:
        """Solve a reCAPTCHA v2 challenge. Returns the g-recaptcha-response token."""

    @abstractmethod
    def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str,
        min_score: float = 0.3,
    ) -> str:
        """Solve a reCAPTCHA v3 challenge. Returns the g-recaptcha-response token."""

    @abstractmethod
    def solve_hcaptcha(self, site_key: str, url: str) -> str:
        """Solve an hCaptcha challenge. Returns the h-captcha-response token."""

    @abstractmethod
    def solve_turnstile(
        self,
        site_key: str,
        url: str,
        action: Optional[str] = None,
    ) -> str:
        """Solve a Cloudflare Turnstile challenge. Returns the cf-turnstile-response token."""

    @abstractmethod
    def get_balance(self) -> float:
        """Return the account's current balance (provider-native units)."""

    # --- dispatch ---

    def solve(self, task: CaptchaTask) -> str:
        """Dispatch a CaptchaTask to the matching solve_* method."""
        t = task.challenge_type
        if t == "recaptcha_v2":
            return self.solve_recaptcha_v2(
                task.site_key, task.url, invisible=task.invisible, **task.extra
            )
        if t == "recaptcha_v3":
            if not task.action:
                raise ValueError("recaptcha_v3 requires a non-empty action")
            return self.solve_recaptcha_v3(
                task.site_key, task.url, action=task.action, min_score=task.min_score
            )
        if t == "hcaptcha":
            return self.solve_hcaptcha(task.site_key, task.url)
        if t == "turnstile":
            return self.solve_turnstile(task.site_key, task.url, action=task.action)
        raise ValueError(f"unknown challenge_type: {t!r}")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
