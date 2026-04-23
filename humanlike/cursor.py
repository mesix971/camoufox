"""
Humanlike cursor movement and clicks.

Bot detectors flag pointer traces that are straight lines, teleport-style
instant moves, or click events with no preceding mousemove history. This
module produces Bezier-path mouse moves with realistic per-waypoint
delays, then wraps mouse.down/up with a short dwell time for clicks.

Page objects are duck-typed — we only depend on Playwright-like surface:
    page.mouse.move(x, y)
    page.mouse.down() / page.mouse.up()
    page.locator(selector).bounding_box() -> {"x", "y", "width", "height"}
    page.query_selector(selector).bounding_box()
    page.keyboard.* (used by typing.py)

Playwright sync does not expose the current mouse position, so we track
last known positions ourselves in a module-level dict keyed by id(page).
"""

from __future__ import annotations

import random
import time
from typing import Dict, Optional, Tuple

from humanlike.bezier import Bezier

Point = Tuple[float, float]

# Per-page last known cursor position. Keyed by id(page) because page
# objects aren't required to be hashable. Entries live for the lifetime
# of the process — acceptable for automation scripts.
_last_pos: Dict[int, Point] = {}


def _get_last(page) -> Point:
    return _last_pos.get(id(page), (0.0, 0.0))


def _set_last(page, pos: Point) -> None:
    _last_pos[id(page)] = pos


def _resolve_bbox(page, selector: str) -> dict:
    """Return bounding box dict for selector, preferring locator API."""
    # Try the modern locator API first; fall back to query_selector.
    try:
        locator = page.locator(selector)
        bbox = locator.bounding_box()
    except AttributeError:
        bbox = None
    if bbox is None:
        handle = page.query_selector(selector)
        if handle is None:
            raise ValueError(f"selector not found: {selector!r}")
        bbox = handle.bounding_box()
    if bbox is None:
        raise ValueError(f"selector has no bounding box: {selector!r}")
    return bbox


def move(
    page,
    to: Point,
    from_: Optional[Point] = None,
    steps: int = 40,
    overshoot: bool = True,
    total_duration: float = 0.35,
    rng: Optional[random.Random] = None,
) -> None:
    """Move the cursor from `from_` to `to` along a humanlike curve.

    If `from_` is None, uses the last tracked position for this page
    (defaulting to (0, 0) on first move).

    Total travel time is `total_duration` +/- 20% jitter. If `overshoot`
    is True, the curve overshoots the target slightly and then corrects.
    """
    if rng is None:
        rng = random.Random()

    start = from_ if from_ is not None else _get_last(page)
    end = (float(to[0]), float(to[1]))

    jitter = 1.0 + rng.uniform(-0.2, 0.2)
    duration = max(0.01, total_duration * jitter)
    overshoot_amt = 0.08 if overshoot else 0.0

    curve = Bezier.humanize(
        start=start, end=end, overshoot=overshoot_amt, rng=rng
    )
    waypoints = curve.with_velocity(steps=steps, total_duration=duration)

    for x, y, delay in waypoints:
        page.mouse.move(x, y)
        if delay > 0:
            time.sleep(delay)

    if overshoot:
        # Final correction back onto the exact target (the overshot p3
        # placed us slightly past `end`). A tiny settle pause mimics the
        # micro-adjustment humans make when landing on a click target.
        page.mouse.move(end[0], end[1])
        time.sleep(rng.uniform(0.01, 0.04))

    _set_last(page, end)


def click(
    page,
    selector: str,
    steps: int = 40,
    rng: Optional[random.Random] = None,
) -> None:
    """Move to a random point inside the element and click it.

    Target is the element's center plus a small offset — within 30% of
    half the element's width/height. This avoids always hitting the exact
    pixel center, which is itself a detectable pattern.
    """
    if rng is None:
        rng = random.Random()

    bbox = _resolve_bbox(page, selector)
    cx = bbox["x"] + bbox["width"] / 2.0
    cy = bbox["y"] + bbox["height"] / 2.0
    ox = rng.uniform(-0.3, 0.3) * bbox["width"] / 2.0
    oy = rng.uniform(-0.3, 0.3) * bbox["height"] / 2.0
    target = (cx + ox, cy + oy)

    move(page, target, steps=steps, rng=rng)
    page.mouse.down()
    time.sleep(rng.uniform(0.04, 0.12))
    page.mouse.up()


def drag(
    page,
    from_selector: str,
    to_selector: str,
    steps: int = 40,
    rng: Optional[random.Random] = None,
) -> None:
    """Mouse-down on one element, drag along a curve to another, release."""
    if rng is None:
        rng = random.Random()

    from_bbox = _resolve_bbox(page, from_selector)
    to_bbox = _resolve_bbox(page, to_selector)

    from_pt = (
        from_bbox["x"] + from_bbox["width"] / 2.0,
        from_bbox["y"] + from_bbox["height"] / 2.0,
    )
    to_pt = (
        to_bbox["x"] + to_bbox["width"] / 2.0,
        to_bbox["y"] + to_bbox["height"] / 2.0,
    )

    move(page, from_pt, steps=steps, rng=rng)
    page.mouse.down()
    time.sleep(rng.uniform(0.04, 0.12))
    move(page, to_pt, steps=steps, rng=rng)
    time.sleep(rng.uniform(0.04, 0.12))
    page.mouse.up()


def reset_tracked_position(page=None) -> None:
    """Clear tracked cursor state (test helper)."""
    if page is None:
        _last_pos.clear()
    else:
        _last_pos.pop(id(page), None)
