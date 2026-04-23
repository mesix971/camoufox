"""
Humanlike text typing.

`page.fill(selector, text)` pastes the entire string at once, which every
detection pipeline flags immediately (InputEvent timing, no keydown
cadence). Real humans:
  - type at bounded WPM with per-key jitter,
  - pause slightly longer on spaces and punctuation,
  - occasionally hit an adjacent key and correct with Backspace.

This module emits one keystroke at a time via `page.keyboard.type()` and
`page.keyboard.press("Backspace")` with `time.sleep` between them.

Convention: 5 characters per word (standard WPM definition), so
characters-per-minute = wpm * 5, seconds-per-char = 60 / (wpm * 5).
At 250 wpm that's ~48ms per char, matching the task spec.
"""

from __future__ import annotations

import random
import time
from typing import Optional

from humanlike.cursor import click

# Rough QWERTY adjacency — not exhaustive, just enough to make typos look
# like real fat-finger errors. Letters listed here map to nearby keys on
# the same row or one row up/down.
_ADJACENT: dict = {
    "a": "sqwz",
    "b": "vghn",
    "c": "xdfv",
    "d": "serfcx",
    "e": "wsdr",
    "f": "drtgvc",
    "g": "ftyhbv",
    "h": "gyujnb",
    "i": "ujko",
    "j": "huiknm",
    "k": "jiolm",
    "l": "kop",
    "m": "njk",
    "n": "bhjm",
    "o": "iklp",
    "p": "ol",
    "q": "wa",
    "r": "edft",
    "s": "awedxz",
    "t": "rfgy",
    "u": "yhji",
    "v": "cfgb",
    "w": "qase",
    "x": "zsdc",
    "y": "tghu",
    "z": "asx",
    "1": "2q",
    "2": "13qw",
    "3": "24we",
    "4": "35er",
    "5": "46rt",
    "6": "57ty",
    "7": "68yu",
    "8": "79ui",
    "9": "80io",
    "0": "9op",
}

_PUNCT = set(".,;:!?'\"-_()[]{}")


def _per_char_delay(wpm: float, rng: random.Random) -> float:
    """Base per-keystroke delay in seconds with +/-40% jitter."""
    base = 60.0 / max(1.0, wpm) / 5.0  # 5 chars per word convention
    jitter = 1.0 + rng.uniform(-0.4, 0.4)
    return max(0.005, base * jitter)


def _adjacent_key(ch: str, rng: random.Random) -> Optional[str]:
    """Return a random adjacent key for a typo, or None if unavailable."""
    key = ch.lower()
    neighbors = _ADJACENT.get(key)
    if not neighbors:
        return None
    pick = rng.choice(neighbors)
    # Preserve case of the original character.
    return pick.upper() if ch.isupper() else pick


def type_text(
    page,
    selector: str,
    text: str,
    wpm: float = 250.0,
    typo_rate: float = 0.0,
    rng: Optional[random.Random] = None,
) -> None:
    """Click the target then type `text` character-by-character.

    - `wpm`: words per minute. 250 is fast-but-plausible; 60-80 is casual.
    - `typo_rate`: probability per char of hitting an adjacent key first,
      noticing the mistake, and correcting with Backspace.
    """
    if rng is None:
        rng = random.Random()

    click(page, selector, rng=rng)
    # Brief settle after clicking into a focused input.
    time.sleep(rng.uniform(0.05, 0.12))

    for ch in text:
        # Decide if this character will be preceded by a typo.
        if typo_rate > 0 and rng.random() < typo_rate:
            wrong = _adjacent_key(ch, rng)
            if wrong is not None and wrong != ch:
                page.keyboard.type(wrong)
                time.sleep(_per_char_delay(wpm, rng))
                page.keyboard.press("Backspace")
                time.sleep(_per_char_delay(wpm, rng))

        page.keyboard.type(ch)

        delay = _per_char_delay(wpm, rng)
        if ch == " " or ch in _PUNCT:
            delay *= 1.5
        time.sleep(delay)


def fill(
    page,
    selector: str,
    text: str,
    wpm: float = 250.0,
    rng: Optional[random.Random] = None,
) -> None:
    """Convenience wrapper: click + type with no typos."""
    type_text(page, selector, text, wpm=wpm, typo_rate=0.0, rng=rng)
