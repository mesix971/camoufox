"""
creepjsscore — CreepJS trust/fingerprint scoring for Camoufox profiles.

Drives a Playwright-style page against creepjs.com, waits for the async
scoring to finish, scrapes Trust Score + Fingerprint Score, and rejects
profiles that fall below configured thresholds.

Public API:
    CreepJSScore(dataclass)  — scraped result + pass/fail
    Scorer(thresholds, url, timeout)  — runs scoring against a given page
    score_profile(page, profile_id, thresholds=None)  — one-shot helper
"""

from creepjsscore.score import CreepJSScore, Scorer

__all__ = [
    "CreepJSScore",
    "Scorer",
    "score_profile",
]

__version__ = "0.1.0"


def score_profile(page, profile_id, thresholds=None):
    """One-shot helper: build a throwaway Scorer and score a profile.

    `thresholds` may be a tuple `(fp, trust)` or a dict
    `{"fp": ..., "trust": ...}`. Pass None to accept defaults
    (fp=75.0, trust=70.0).
    """
    kwargs = {}
    if thresholds is None:
        pass
    elif isinstance(thresholds, dict):
        if "fp" in thresholds:
            kwargs["pass_fp_threshold"] = float(thresholds["fp"])
        if "trust" in thresholds:
            kwargs["pass_trust_threshold"] = float(thresholds["trust"])
    elif isinstance(thresholds, (tuple, list)) and len(thresholds) == 2:
        kwargs["pass_fp_threshold"] = float(thresholds[0])
        kwargs["pass_trust_threshold"] = float(thresholds[1])
    else:
        raise TypeError(
            "thresholds must be None, a (fp, trust) tuple, or a dict with "
            "'fp'/'trust' keys"
        )
    return Scorer(**kwargs).score(page, profile_id)
