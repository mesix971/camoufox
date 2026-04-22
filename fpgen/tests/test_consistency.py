"""Unit tests for the consistency engine.

Each test constructs a known-bad profile variant and asserts the specific
invariant fires. This guards against silent weakening of the checks.
"""

from __future__ import annotations

import pytest

from fpgen import generate
from fpgen.consistency import validate


def _clone_and_break(**overrides) -> list:
    """Generate a valid profile, then mutate it to break an invariant."""
    p = generate(archetype="windows-11-mainstream", seed=0)
    for k, v in overrides.items():
        setattr(p, k, v)
    return validate(p)


def test_r1_ua_mismatch_with_os() -> None:
    errs = _clone_and_break(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:142.0.1) Gecko/20100101 Firefox/142.0.1")
    assert any("R1" in e for e in errs)


def test_r1_ua_firefox_version_mismatch() -> None:
    errs = _clone_and_break(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:999.0) Gecko/20100101 Firefox/999.0")
    assert any("R1" in e and "Firefox version" in e for e in errs)


def test_r2_wrong_platform() -> None:
    errs = _clone_and_break(platform="MacIntel")
    assert any("R2" in e for e in errs)


def test_r3_fonts_foreign_os() -> None:
    from fpgen.archetypes import FONTS
    p = generate(archetype="windows-11-mainstream", seed=0)
    p.fonts = FONTS["macos"][:30]
    errs = validate(p)
    assert any("R3" in e for e in errs)


def test_r4_apple_gpu_on_windows() -> None:
    errs = _clone_and_break(webgl_vendor="Apple", webgl_renderer="Apple M2 Pro")
    assert any("R4" in e for e in errs)


def test_r4_direct3d_on_macos() -> None:
    p = generate(archetype="macos-14-retina", seed=0)
    p.webgl_vendor = "Google Inc. (NVIDIA)"
    p.webgl_renderer = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11, D3D11)"
    errs = validate(p)
    assert any("R4" in e for e in errs)


def test_r5_mac_dpr_nonstandard() -> None:
    p = generate(archetype="macos-14-retina", seed=0)
    p.device_pixel_ratio = 1.75
    errs = validate(p)
    assert any("R5" in e for e in errs)


def test_r6_inner_bigger_than_outer() -> None:
    errs = _clone_and_break(inner_width=9999, outer_width=800)
    assert any("R6" in e for e in errs)


def test_r7_avail_exceeds_screen() -> None:
    errs = _clone_and_break(avail_height=99999)
    assert any("R7" in e for e in errs)


def test_r8_timezone_not_in_locale_pool() -> None:
    errs = _clone_and_break(locale="en-US", timezone="Asia/Tokyo")
    assert any("R8" in e for e in errs)


def test_r9_geo_too_far() -> None:
    errs = _clone_and_break(locale="en-US", timezone="America/New_York", latitude=0.0, longitude=0.0)
    assert any("R9" in e for e in errs)


def test_r10_accept_language_mismatch() -> None:
    errs = _clone_and_break(accept_language="ja-JP,ja;q=0.5")
    assert any("R10" in e for e in errs)


def test_r11_languages_head_mismatch() -> None:
    errs = _clone_and_break(languages=["ja-JP", "ja"])
    assert any("R11" in e for e in errs)


def test_r12_weird_core_count() -> None:
    errs = _clone_and_break(cpu_cores=7)
    assert any("R12" in e for e in errs)


def test_r13_battery_charging_contradiction() -> None:
    errs = _clone_and_break(battery_charging=True, battery_discharging_time=5000.0)
    assert any("R13" in e for e in errs)


def test_r13_battery_level_out_of_range() -> None:
    errs = _clone_and_break(battery_level=1.5)
    assert any("R13" in e for e in errs)


def test_r14_oddball_sample_rate() -> None:
    errs = _clone_and_break(audio_sample_rate=12345)
    assert any("R14" in e for e in errs)


def test_r15_build_id_malformed() -> None:
    errs = _clone_and_break(build_id="nope")
    assert any("R15" in e for e in errs)


def test_r16_color_depth_weird() -> None:
    errs = _clone_and_break(color_depth=16)
    assert any("R16" in e for e in errs)


def test_happy_path_zero_errors() -> None:
    p = generate(seed=42)
    errs = validate(p)
    assert errs == []


@pytest.mark.parametrize("seed", range(100))
def test_fuzz_generator_always_valid(seed: int) -> None:
    p = generate(seed=seed)
    errs = validate(p)
    assert errs == [], f"seed={seed}: {errs}"
