"""Captcha solver provider implementations."""

from captchapool.providers.base import (
    CaptchaError,
    CaptchaInsufficientFunds,
    CaptchaInvalidKey,
    CaptchaProvider,
    CaptchaTask,
    CaptchaTimeout,
    CaptchaUnsolvable,
)
from captchapool.providers.capsolver import CapSolverProvider
from captchapool.providers.twocaptcha import TwoCaptchaProvider

__all__ = [
    "CapSolverProvider",
    "CaptchaError",
    "CaptchaInsufficientFunds",
    "CaptchaInvalidKey",
    "CaptchaProvider",
    "CaptchaTask",
    "CaptchaTimeout",
    "CaptchaUnsolvable",
    "TwoCaptchaProvider",
]
