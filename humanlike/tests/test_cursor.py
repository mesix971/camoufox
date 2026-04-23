"""Cursor move/click/drag using a MockPage that records all calls."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from humanlike import cursor
from humanlike.cursor import click, drag, move, reset_tracked_position


class MockMouse:
    def __init__(self) -> None:
        self.moves: List[Tuple[float, float]] = []
        self.downs: int = 0
        self.ups: int = 0

    def move(self, x: float, y: float) -> None:
        self.moves.append((float(x), float(y)))

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
    def __init__(
        self, bboxes: Optional[Dict[str, Dict[str, float]]] = None
    ) -> None:
        self.mouse = MockMouse()
        self.keyboard = MockKeyboard()
        self._bboxes = bboxes or {}

    def locator(self, selector: str) -> MockLocator:
        return MockLocator(self._bboxes.get(selector))

    def query_selector(self, selector: str) -> Any:
        return MockLocator(self._bboxes.get(selector))


@pytest.fixture(autouse=True)
def _fast_sleep():
    """time.sleep in cursor.py is real — stub it so tests aren't slow."""
    with patch("humanlike.cursor.time.sleep"):
        yield


@pytest.fixture(autouse=True)
def _clear_state():
    reset_tracked_position()
    yield
    reset_tracked_position()


def test_move_records_steps_plus_one_or_two_points() -> None:
    page = MockPage()
    move(
        page, (400.0, 300.0),
        from_=(0.0, 0.0),
        steps=40,
        overshoot=False,
        rng=random.Random(1),
    )
    # Without overshoot: exactly steps+1 = 41 move() calls.
    assert len(page.mouse.moves) == 41
    # First point is the start, last is the end.
    assert page.mouse.moves[0] == pytest.approx((0.0, 0.0))
    assert page.mouse.moves[-1] == pytest.approx((400.0, 300.0))


def test_move_with_overshoot_adds_correction_point() -> None:
    page = MockPage()
    move(
        page, (400.0, 300.0),
        from_=(0.0, 0.0),
        steps=30,
        overshoot=True,
        rng=random.Random(2),
    )
    # Overshoot appends one correction move back to the exact target.
    assert len(page.mouse.moves) == 32
    assert page.mouse.moves[-1] == pytest.approx((400.0, 300.0))


def test_move_path_stays_near_straight_line_for_low_deviation() -> None:
    """All waypoints should lie within a reasonable envelope of the path."""
    page = MockPage()
    move(
        page, (500.0, 0.0),
        from_=(0.0, 0.0),
        steps=40,
        overshoot=False,
        rng=random.Random(7),
    )
    # Every y-coordinate should be within ~|x-range| * deviation of zero.
    max_y = max(abs(y) for _, y in page.mouse.moves)
    assert max_y < 500.0  # Sanity: not wildly off-path.


def test_move_tracks_last_position() -> None:
    page = MockPage()
    move(page, (100.0, 100.0), from_=(0.0, 0.0), steps=10, rng=random.Random(1))
    # Second move with no `from_` should start where the previous ended.
    page.mouse.moves.clear()
    move(page, (200.0, 200.0), steps=10, overshoot=False, rng=random.Random(1))
    assert page.mouse.moves[0] == pytest.approx((100.0, 100.0))


def test_click_resolves_selector_and_issues_down_up() -> None:
    page = MockPage(
        bboxes={"#btn": {"x": 100.0, "y": 200.0, "width": 50.0, "height": 20.0}}
    )
    click(page, "#btn", steps=20, rng=random.Random(3))

    assert page.mouse.downs == 1
    assert page.mouse.ups == 1
    # Final target lies inside the element's bounding box.
    x, y = page.mouse.moves[-1]
    assert 100.0 <= x <= 150.0
    assert 200.0 <= y <= 220.0


def test_click_target_near_center() -> None:
    page = MockPage(
        bboxes={"#x": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 100.0}}
    )
    click(page, "#x", steps=10, rng=random.Random(11))
    x, y = page.mouse.moves[-1]
    # Offset is within 30% of half-width/height => within 15 px of center.
    assert abs(x - 50.0) <= 15.0 + 1e-6
    assert abs(y - 50.0) <= 15.0 + 1e-6


def test_click_raises_on_missing_selector() -> None:
    page = MockPage(bboxes={})
    with pytest.raises(ValueError):
        click(page, "#nope")


def test_drag_presses_moves_and_releases() -> None:
    page = MockPage(
        bboxes={
            "#a": {"x": 0.0, "y": 0.0, "width": 20.0, "height": 20.0},
            "#b": {"x": 200.0, "y": 200.0, "width": 20.0, "height": 20.0},
        }
    )
    drag(page, "#a", "#b", steps=15, rng=random.Random(9))
    assert page.mouse.downs == 1
    assert page.mouse.ups == 1
    # At least two segments of moves recorded (one per move() call).
    assert len(page.mouse.moves) > 20
