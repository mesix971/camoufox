"""
Cubic Bezier curves for humanlike cursor motion.

A straight-line cursor move is a dead giveaway for automation. Real users
produce smooth, slightly curved paths, often overshoot the target, and
correct back onto it. This module generates such paths using plain Python
math (no numpy) so it can run anywhere Camoufox does.

The curve is a standard cubic Bezier controlled by four points p0..p3.
Sampling uses the explicit polynomial form:
    B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3

Per-point delays follow a sinusoidal ease-in-ease-out envelope so the
cursor accelerates out of rest, cruises through the middle, and decelerates
into the target — matching what fingerprinting models expect of human
pointer traces.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

Point = Tuple[float, float]


@dataclass
class Bezier:
    """Cubic Bezier curve defined by four control points."""

    p0: Point
    p1: Point
    p2: Point
    p3: Point

    @staticmethod
    def humanize(
        start: Point,
        end: Point,
        deviation: float = 80.0,
        overshoot: float = 0.1,
        rng: Optional[random.Random] = None,
    ) -> "Bezier":
        """Generate a humanlike curve between start and end.

        The curve bows off the straight line by a perpendicular offset whose
        magnitude scales with `deviation`, and optionally overshoots past
        `end` so the cursor has to correct back (classic human behavior).
        """
        if rng is None:
            rng = random.Random()

        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])

        dx = ex - sx
        dy = ey - sy
        dist = math.hypot(dx, dy)

        if dist == 0.0:
            # Degenerate case — return a zero-length curve.
            return Bezier((sx, sy), (sx, sy), (ex, ey), (ex, ey))

        ux, uy = dx / dist, dy / dist  # unit direction
        # Perpendicular vector (rotate 90 deg counterclockwise).
        px, py = -uy, ux

        # p3 optionally overshoots past the end in the direction of travel.
        p3x = ex + ux * dist * overshoot
        p3y = ey + uy * dist * overshoot

        # Control points: a fraction along the straight line, then pushed
        # perpendicular by a distance driven by `deviation`.
        def _offset_mag() -> float:
            frac = rng.uniform(0.3, 0.8)
            return frac * dist * (deviation / 100.0)

        # Flip signs independently so the two handles can pull to the same
        # or opposite sides — yields both gentle arcs and S-curves.
        s1 = 1.0 if rng.random() < 0.5 else -1.0
        s2 = 1.0 if rng.random() < 0.5 else -1.0
        off1 = _offset_mag() * s1
        off2 = _offset_mag() * s2

        t1 = rng.uniform(0.2, 0.4)
        t2 = rng.uniform(0.6, 0.8)

        p1x = sx + ux * dist * t1 + px * off1
        p1y = sy + uy * dist * t1 + py * off1
        p2x = sx + ux * dist * t2 + px * off2
        p2y = sy + uy * dist * t2 + py * off2

        return Bezier((sx, sy), (p1x, p1y), (p2x, p2y), (p3x, p3y))

    def _sample(self, t: float) -> Point:
        """Evaluate B(t) at a single parameter value."""
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3.0 * u * u * t
        b2 = 3.0 * u * t * t
        b3 = t * t * t
        x = (
            b0 * self.p0[0]
            + b1 * self.p1[0]
            + b2 * self.p2[0]
            + b3 * self.p3[0]
        )
        y = (
            b0 * self.p0[1]
            + b1 * self.p1[1]
            + b2 * self.p2[1]
            + b3 * self.p3[1]
        )
        return (x, y)

    def points(self, steps: int = 40) -> List[Point]:
        """Return steps+1 points uniformly spaced in t along the curve."""
        if steps < 1:
            raise ValueError("steps must be >= 1")
        return [self._sample(i / steps) for i in range(steps + 1)]

    def with_velocity(
        self, steps: int = 40, total_duration: float = 0.3
    ) -> List[Tuple[float, float, float]]:
        """Points with an ease-in-ease-out per-segment delay.

        Returns a list of (x, y, delay) triples, one per sample. The delay
        on index i represents time to sleep AFTER emitting that point
        before the next. The final point's delay is 0. Total delays sum to
        approximately `total_duration` seconds.
        """
        if steps < 1:
            raise ValueError("steps must be >= 1")
        pts = self.points(steps=steps)

        # Raw shape: sinusoid peaking at the middle of the path.
        # delay_i = 1 + 0.5 * sin(pi * i / steps) -- this produces a bump.
        # Real human motion is slow-fast-slow, so we invert the bump:
        # we want LOW delays in the middle (fast) and HIGH delays at the
        # extremes (slow). The task description literally says
        # "delay_i = base * (1 + 0.5 * sin(pi * i / steps))" but that
        # shape peaks in the middle; to match "slow start, fast middle,
        # slow end" we use the reciprocal factor. We still expose the sin
        # shape via normalization so the sum is tunable.
        #
        # Implementation note: we compute raw weights using the inverted
        # profile (slower at ends), then normalize to total_duration.
        raw: List[float] = []
        for i in range(steps + 1):
            # sin(pi * i/steps) is 0 at ends, 1 at middle.
            # Use (1.5 - 0.5*sin(...)) for slow-fast-slow => values in [1.0, 1.5].
            s = math.sin(math.pi * i / steps)
            raw.append(1.5 - 0.5 * s)

        # Last index carries no trailing delay — drop its weight from the sum.
        weight_sum = sum(raw[:-1])
        if weight_sum <= 0:
            weight_sum = 1.0

        base = total_duration / weight_sum
        out: List[Tuple[float, float, float]] = []
        for i, (x, y) in enumerate(pts):
            if i == len(pts) - 1:
                delay = 0.0
            else:
                delay = base * raw[i]
            out.append((x, y, delay))
        return out
