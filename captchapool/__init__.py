"""
captchapool — captcha-solving provider management for Camoufox.

Wraps third-party captcha solver APIs (CapSolver, 2Captcha) behind one
uniform interface and lets a Solver race/fall-back across them when a
site is picky.

Public API:
    CaptchaProvider                — abstract base class
    CapSolverProvider              — CapSolver.com concrete impl
    TwoCaptchaProvider             — 2Captcha.com concrete impl
    CaptchaTask(dataclass)         — request descriptor
    Solver(providers, strategy)    — multi-provider orchestrator
    solve(providers, challenge, ...)  — module-level one-shot helper
    ProviderStore(root)            — on-disk provider credential store
    Errors: CaptchaError, CaptchaTimeout, CaptchaInvalidKey,
            CaptchaInsufficientFunds, CaptchaUnsolvable
"""

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
from captchapool.solver import Solver, SolverStats, solve
from captchapool.store import ProviderStore

__all__ = [
    "CapSolverProvider",
    "CaptchaError",
    "CaptchaInsufficientFunds",
    "CaptchaInvalidKey",
    "CaptchaProvider",
    "CaptchaTask",
    "CaptchaTimeout",
    "CaptchaUnsolvable",
    "ProviderStore",
    "Solver",
    "SolverStats",
    "TwoCaptchaProvider",
    "solve",
]

__version__ = "0.1.0"
