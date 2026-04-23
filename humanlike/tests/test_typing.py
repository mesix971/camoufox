"""Typing behavior — per-char calls, delay cadence, typos, punctuation."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from humanlike.typing import fill, type_text
from humanlike import cursor


class MockMouse:
    def __init__(self) -> None:
        self.moves: List[Tuple[float, float]] = []
        self.downs: int = 0
        self.ups: int = 0

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def down(self) -> None:
        self.downs += 1

    def up(self) -> None:
        self.ups += 1


class MockKeyboard:
    def __init__(self) -> None:
        self.typed: List[str] = []
        self.pressed: List[str] = []

    def type(self, s: str) -> None:
        self.typed.append(s)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class MockLocator:
    def __init__(self, bbox: Optional[Dict[str, float]]) -> None:
        self._bbox = bbox

    def bounding_box(self) -> Optional[Dict[str, float]]:
        return self._bbox


class MockPage:
    def __init__(self, bboxes: Dict[str, Dict[str, float]]) -> None:
        self.mouse = MockMouse()
        self.keyboard = MockKeyboard()
        self._bboxes = bboxes

    def locator(self, selector: str) -> MockLocator:
        return MockLocator(self._bboxes.get(selector))

    def query_selector(self, selector: str):
        return MockLocator(self._bboxes.get(selector))


INPUT_BBOX = {"#inp": {"x": 0.0, "y": 0.0, "width": 200.0, "height": 30.0}}


@pytest.fixture(autouse=True)
def _fast_sleeps():
    """Stub sleep in both cursor and typing so tests run instantly."""
    with patch("humanlike.cursor.time.sleep"), patch(
        "humanlike.typing.time.sleep"
    ):
        yield


@pytest.fixture(autouse=True)
def _clear_cursor_state():
    cursor.reset_tracked_position()
    yield
    cursor.reset_tracked_position()


def test_type_text_calls_keyboard_type_once_per_char() -> None:
    page = MockPage(INPUT_BBOX)
    text = "hello"
    type_text(page, "#inp", text, wpm=250.0, typo_rate=0.0, rng=random.Random(0))
    assert page.keyboard.typed == list(text)
    assert page.keyboard.pressed == []


def test_fill_does_not_call_backspace() -> None:
    page = MockPage(INPUT_BBOX)
    fill(page, "#inp", "hello world", wpm=250.0, rng=random.Random(0))
    assert "Backspace" not in page.keyboard.pressed
    # And still typed every character exactly once.
    assert page.keyboard.typed == list("hello world")


def test_typo_rate_one_causes_backspaces_and_extra_chars() -> None:
    page = MockPage(INPUT_BBOX)
    text = "abcd"
    type_text(
        page, "#inp", text, wpm=250.0, typo_rate=1.0, rng=random.Random(1)
    )
    # Every character triggers: wrong-key, Backspace, correct-key.
    # So typed count ~ 2 * len(text).
    assert len(page.keyboard.typed) == 2 * len(text)
    assert page.keyboard.pressed.count("Backspace") == len(text)
    # Every second typed entry is the real character, in order.
    real_chars = page.keyboard.typed[1::2]
    assert real_chars == list(text)


def test_typo_rate_zero_has_no_backspaces() -> None:
    page = MockPage(INPUT_BBOX)
    type_text(
        page, "#inp", "abcdef", wpm=250.0, typo_rate=0.0, rng=random.Random(5)
    )
    assert page.keyboard.pressed == []


def test_per_char_delay_within_expected_range() -> None:
    """At 250 wpm base per-char delay ~48ms, +/-40% jitter => [28.8, 67.2]."""
    from humanlike.typing import _per_char_delay

    rng = random.Random(0)
    samples = [_per_char_delay(250.0, rng) for _ in range(500)]
    base = 60.0 / 250.0 / 5.0  # 0.048s
    lo, hi = base * 0.6, base * 1.4
    assert all(lo - 1e-9 <= d <= hi + 1e-9 for d in samples)
    # Mean should be near base (within 10%).
    avg = sum(samples) / len(samples)
    assert abs(avg - base) / base < 0.1


def test_punctuation_has_extra_delay() -> None:
    """Punctuation chars sleep 1.5x the base delay."""
    page = MockPage(INPUT_BBOX)
    recorded: List[float] = []

    def record_sleep(d: float) -> None:
        recorded.append(d)

    # Replace the sleep inside typing.py specifically.
    with patch("humanlike.typing.time.sleep", side_effect=record_sleep):
        with patch("humanlike.cursor.time.sleep"):
            type_text(
                page,
                "#inp",
                "ab.",
                wpm=250.0,
                typo_rate=0.0,
                rng=random.Random(42),
            )
    # The last delay corresponds to the "." character and should be larger
    # than the prior (letter) delays on average. Just assert it's > 1.2x
    # the average of the two preceding ones (guards against jitter noise).
    # There's also a post-click settle sleep at the start, so filter those
    # out — per-char delays are at indices -3, -2, -1 (one per char).
    per_char = recorded[-3:]
    letters = per_char[:2]
    punct = per_char[2]
    assert punct > max(letters)


def test_type_text_clicks_selector_first() -> None:
    page = MockPage(INPUT_BBOX)
    type_text(
        page, "#inp", "x", wpm=250.0, typo_rate=0.0, rng=random.Random(0)
    )
    # Click fired a down/up pair before any typing.
    assert page.mouse.downs == 1
    assert page.mouse.ups == 1


def test_adjacent_key_uses_known_map() -> None:
    from humanlike.typing import _ADJACENT, _adjacent_key

    rng = random.Random(0)
    # 'a' is in the map — result should be one of its neighbors.
    result = _adjacent_key("a", rng)
    assert result is not None
    assert result.lower() in _ADJACENT["a"]


def test_adjacent_key_preserves_case() -> None:
    from humanlike.typing import _adjacent_key

    rng = random.Random(0)
    result = _adjacent_key("A", rng)
    assert result is not None
    assert result.isupper()


def test_adjacent_key_returns_none_for_unmapped() -> None:
    from humanlike.typing import _adjacent_key

    # A character not in the adjacency map.
    assert _adjacent_key("~", random.Random(0)) is None
