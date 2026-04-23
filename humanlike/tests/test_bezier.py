"""Bezier curve math — endpoints, sample count, velocity profile, shape."""

from __future__ import annotations

import math
import random

import pytest

from humanlike.bezier import Bezier


def test_humanize_endpoints_match_without_overshoot() -> None:
    curve = Bezier.humanize(
        (10.0, 20.0), (300.0, 400.0), overshoot=0.0, rng=random.Random(1)
    )
    assert curve.p0 == pytest.approx((10.0, 20.0))
    assert curve.p3 == pytest.approx((300.0, 400.0))


def test_humanize_overshoot_pushes_p3_past_end() -> None:
    start = (0.0, 0.0)
    end = (100.0, 0.0)
    curve = Bezier.humanize(
        start, end, overshoot=0.2, rng=random.Random(2)
    )
    # With overshoot=0.2, p3 lands 20% past the end in the direction of travel.
    assert curve.p3[0] > end[0]
    assert curve.p3[0] == pytest.approx(120.0, rel=1e-6)


def test_points_returns_steps_plus_one_samples() -> None:
    curve = Bezier.humanize(
        (0.0, 0.0), (100.0, 50.0), overshoot=0.0, rng=random.Random(3)
    )
    pts = curve.points(steps=40)
    assert len(pts) == 41
    # First and last sample land on p0/p3 exactly.
    assert pts[0] == pytest.approx(curve.p0)
    assert pts[-1] == pytest.approx(curve.p3)


def test_points_rejects_invalid_steps() -> None:
    curve = Bezier.humanize(
        (0.0, 0.0), (10.0, 10.0), rng=random.Random(0)
    )
    with pytest.raises(ValueError):
        curve.points(steps=0)


def test_with_velocity_sums_close_to_target_duration() -> None:
    curve = Bezier.humanize(
        (0.0, 0.0), (500.0, 300.0), overshoot=0.0, rng=random.Random(4)
    )
    wp = curve.with_velocity(steps=40, total_duration=0.3)
    assert len(wp) == 41
    total = sum(d for _, _, d in wp)
    # Within 5% of target (last entry has zero trailing delay by design).
    assert total == pytest.approx(0.3, rel=0.05)
    # Last point carries no further delay.
    assert wp[-1][2] == 0.0
    # All individual delays are non-negative.
    assert all(d >= 0 for _, _, d in wp)


def test_with_velocity_is_ease_in_ease_out() -> None:
    """Middle samples should be faster (smaller delay) than edges."""
    curve = Bezier.humanize(
        (0.0, 0.0), (500.0, 0.0), overshoot=0.0, rng=random.Random(5)
    )
    wp = curve.with_velocity(steps=40, total_duration=0.3)
    delays = [d for _, _, d in wp[:-1]]  # exclude terminal zero
    mid = delays[len(delays) // 2]
    # Compare middle to average of the first and last active delays.
    edges_avg = (delays[0] + delays[-1]) / 2.0
    assert mid < edges_avg, (
        f"middle delay {mid} should be faster than edges avg {edges_avg}"
    )


def test_deviation_changes_curve_shape() -> None:
    """Bigger deviation = control points farther from straight line."""
    start = (0.0, 0.0)
    end = (200.0, 0.0)

    def max_offset(curve: Bezier) -> float:
        # Max perpendicular distance of a sampled point from the straight
        # line y=0. For a horizontal start->end, that's just |y|.
        return max(abs(y) for _, y in curve.points(steps=20))

    low = Bezier.humanize(
        start, end, deviation=10.0, overshoot=0.0, rng=random.Random(42)
    )
    high = Bezier.humanize(
        start, end, deviation=200.0, overshoot=0.0, rng=random.Random(42)
    )
    assert max_offset(high) > max_offset(low) * 2


def test_degenerate_zero_length_curve() -> None:
    """start == end must not blow up (division by zero guard)."""
    curve = Bezier.humanize(
        (50.0, 50.0), (50.0, 50.0), rng=random.Random(0)
    )
    pts = curve.points(steps=5)
    assert all(p == pytest.approx((50.0, 50.0)) for p in pts)


def test_sample_formula_matches_explicit_cubic() -> None:
    """Spot-check the cubic polynomial against a hand-computed t=0.5."""
    curve = Bezier(
        p0=(0.0, 0.0),
        p1=(0.0, 100.0),
        p2=(100.0, 100.0),
        p3=(100.0, 0.0),
    )
    # B(0.5) for this symmetric curve = (50, 75).
    # (1/8)*0 + 3*(1/4)*(1/2)*0 + 3*(1/2)*(1/4)*100 + (1/8)*100 = 37.5 + 12.5 = 50 (x)
    # (1/8)*0 + 3*(1/4)*(1/2)*100 + 3*(1/2)*(1/4)*100 + (1/8)*0 = 37.5 + 37.5 = 75 (y)
    pts = curve.points(steps=2)
    assert pts[1] == pytest.approx((50.0, 75.0))


def test_seeded_rng_is_deterministic() -> None:
    a = Bezier.humanize(
        (0.0, 0.0), (100.0, 100.0), rng=random.Random(1234)
    )
    b = Bezier.humanize(
        (0.0, 0.0), (100.0, 100.0), rng=random.Random(1234)
    )
    assert a == b


def test_with_velocity_rejects_invalid_steps() -> None:
    curve = Bezier.humanize(
        (0.0, 0.0), (1.0, 1.0), rng=random.Random(0)
    )
    with pytest.raises(ValueError):
        curve.with_velocity(steps=0)
