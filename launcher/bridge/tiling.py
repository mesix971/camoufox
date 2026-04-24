"""
Grid layout for tiling N browser windows on a screen.

Given N windows + (screen_w, screen_h), compute a list of (x, y, w, h)
rectangles that tile the workspace. Supports 'auto' (square-ish grid),
or explicit "cols x rows".
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

Rect = Tuple[int, int, int, int]  # x, y, w, h


# Windows/macOS title bars + taskbars eat some space; leave a margin.
MARGIN_TOP = 0
MARGIN_BOTTOM = 40       # taskbar
MARGIN_SIDES = 0
MIN_WINDOW_W = 420
MIN_WINDOW_H = 300


def auto_grid(n: int) -> Tuple[int, int]:
    """Pick a cols×rows that's close to square, favoring wider grids."""
    if n <= 0:
        return (1, 1)
    if n == 1:
        return (1, 1)
    if n == 2:
        return (2, 1)
    if n == 3:
        return (3, 1)
    if n == 4:
        return (2, 2)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return (cols, rows)


def compute_tiles(
    n: int,
    screen_w: int,
    screen_h: int,
    grid: Optional[Tuple[int, int]] = None,
) -> List[Rect]:
    """Return N tile rects. If `grid` is None, auto-select."""
    if n <= 0:
        return []
    cols, rows = grid if grid is not None else auto_grid(n)
    usable_w = max(screen_w - 2 * MARGIN_SIDES, MIN_WINDOW_W)
    usable_h = max(screen_h - MARGIN_TOP - MARGIN_BOTTOM, MIN_WINDOW_H)
    tile_w = max(usable_w // cols, MIN_WINDOW_W)
    tile_h = max(usable_h // rows, MIN_WINDOW_H)

    rects: List[Rect] = []
    for i in range(n):
        r = i // cols
        c = i % cols
        x = MARGIN_SIDES + c * tile_w
        y = MARGIN_TOP + r * tile_h
        rects.append((x, y, tile_w, tile_h))
    return rects


def parse_grid(spec: str) -> Optional[Tuple[int, int]]:
    """Parse 'auto' -> None or 'CxR' -> (C, R). Raises ValueError on bad input."""
    if not spec or spec.lower() == "auto":
        return None
    spec = spec.lower().replace("×", "x")
    parts = spec.split("x")
    if len(parts) != 2:
        raise ValueError(f"bad grid spec: {spec!r} (expected e.g. '2x2')")
    c, r = int(parts[0]), int(parts[1])
    if c < 1 or r < 1:
        raise ValueError(f"grid must be >=1x1, got {c}x{r}")
    return (c, r)
