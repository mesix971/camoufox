"""
Warmup: visit a few innocent sites before navigating to the target.

Anti-bot systems (Cloudflare Turnstile, DataDome) score sessions higher when
they see an existing browsing history + third-party cookies accumulated over
the last few minutes. A cold browser with zero cookies going straight to a
ticketing site is a strong bot signal.

This module picks a short random path of mainstream sites and visits each
for a few seconds, scrolling and idling, before returning control.
"""

from __future__ import annotations

import random
import time
from typing import List, Optional


DEFAULT_WARMUP_POOL: List[str] = [
    "https://www.google.com/search?q=weather+today",
    "https://www.google.com/search?q=news",
    "https://www.bing.com/search?q=music+2026",
    "https://duckduckgo.com/?q=recipes",
    "https://www.reddit.com/",
    "https://www.wikipedia.org/",
    "https://news.ycombinator.com/",
    "https://www.bbc.com/news",
    "https://www.youtube.com/",
    "https://www.imdb.com/",
    "https://weather.com/",
    "https://www.amazon.com/",
]


def pick_warmup_urls(
    k: int = 3,
    locale: Optional[str] = None,
    pool: Optional[List[str]] = None,
    seed: Optional[int] = None,
) -> List[str]:
    """Pick `k` random URLs from the pool.

    If `locale` looks like a country-specific code (fr-FR, de-DE, …) we'd add
    a country TLD search; keeping it simple for now with .com mainstream sites
    that work everywhere.
    """
    rng = random.Random(seed)
    src = list(pool or DEFAULT_WARMUP_POOL)
    rng.shuffle(src)
    return src[:k]


def warmup(
    page,
    urls: Optional[List[str]] = None,
    min_dwell: float = 2.0,
    max_dwell: float = 6.0,
    scroll: bool = True,
    seed: Optional[int] = None,
) -> None:
    """Visit each url, wait a random 2-6s, optionally scroll once, then move on.

    `page` is a Playwright sync page. Exceptions are swallowed per-url so that
    one flaky warmup site doesn't kill the whole session.
    """
    rng = random.Random(seed)
    urls = urls or pick_warmup_urls(k=3, seed=seed)
    for url in urls:
        try:
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
        except Exception:  # noqa: BLE001 — best-effort warmup
            continue
        dwell = rng.uniform(min_dwell, max_dwell)
        if scroll:
            try:
                page.mouse.wheel(0, rng.randint(300, 1200))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(dwell)
