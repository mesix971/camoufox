"""
Generator core.

generate() picks an archetype, samples consistent values from it, and returns
a Profile that is guaranteed to pass the consistency engine. A seed makes
generation deterministic (useful for tests and for reproducing profiles).
"""

from __future__ import annotations

import uuid
from random import Random
from typing import Any, Dict, List, Optional

from fpgen.archetypes import (
    FIREFOX,
    Archetype,
    font_set,
    gpu_pool,
    pick_archetype,
    pick_locale,
)
from fpgen.consistency import assert_valid
from fpgen.profile import Profile


_DEFAULT_FONT_SAMPLE_SIZE = 55


def _pick_firefox(rng: Random, version: Optional[str]) -> Dict[str, str]:
    if version:
        for v in FIREFOX["versions"]:
            if v["version"] == version:
                return v
        raise ValueError(f"unknown firefox version: {version}")
    return rng.choice(FIREFOX["versions"])


def _pick_screen(rng: Random, arch: Archetype) -> Dict[str, int]:
    width, height = rng.choice(arch.screen_presets)
    avail_width = width
    avail_height = max(height - arch.taskbar_height, height - 100)
    return {
        "screen_width": width,
        "screen_height": height,
        "avail_width": avail_width,
        "avail_height": avail_height,
    }


def _pick_window(rng: Random, screen_w: int, screen_h: int, dpr: float) -> Dict[str, int]:
    # Window sizes users commonly run: 1280x800, 1440x900, 1536x864 (1920×dpr=1.25),
    # 1600x900, full screen. Bias toward "windowed but not tiny".
    candidates = [
        (1280, 800), (1366, 768), (1440, 900), (1536, 864),
        (1600, 900), (1680, 1050),
    ]
    if screen_w >= 1920:
        candidates.extend([(1920, 1080), (1728, 1080), (1600, 1000)])
    if screen_w >= 2560:
        candidates.append((2560, 1440))

    candidates = [(w, h) for (w, h) in candidates if w <= screen_w and h <= screen_h]
    if not candidates:
        candidates = [(screen_w, screen_h)]
    outer_w, outer_h = rng.choice(candidates)

    # Inner = outer minus chrome. Firefox chrome ≈ 74px top + 0px sides when a
    # single tab is open. Clamp at 0.
    inner_w = outer_w
    inner_h = max(outer_h - 74, 100)

    # screenX/Y: where the window sits on the desktop.
    screen_x = rng.randint(0, max(screen_w - outer_w, 0))
    screen_y = rng.randint(0, max(screen_h - outer_h, 0))

    return {
        "outer_width": outer_w,
        "outer_height": outer_h,
        "inner_width": inner_w,
        "inner_height": inner_h,
        "screen_x": screen_x,
        "screen_y": screen_y,
    }


def _pick_fonts(rng: Random, set_id: str, k: int = _DEFAULT_FONT_SAMPLE_SIZE) -> List[str]:
    pool = font_set(set_id)
    k = min(k, len(pool))
    fonts = rng.sample(pool, k)
    fonts.sort()
    return fonts


def _pick_geo(rng: Random, loc: Dict) -> Dict[str, Any]:
    centroid = rng.choice(loc["geo_centroids"])
    lat = centroid["lat"] + rng.uniform(-0.5, 0.5)
    lon = centroid["lon"] + rng.uniform(-0.5, 0.5)
    # round to 4 decimals ≈ 11m precision, matches browser geolocation output
    return {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "geo_accuracy": round(rng.uniform(20, 200), 1),
        "timezone": centroid["tz"],
    }


def _pick_battery(rng: Random) -> Dict[str, Any]:
    charging = rng.random() < 0.55
    level = round(rng.uniform(0.15, 1.0), 2)
    if charging:
        charging_time = rng.choice([0.0, 1200.0, 2400.0, 3600.0]) if level < 1.0 else 0.0
        discharging_time = 0.0
    else:
        charging_time = 0.0
        discharging_time = round(rng.uniform(3600, 28800), 0)
    return {
        "battery_charging": charging,
        "battery_level": level,
        "battery_charging_time": charging_time,
        "battery_discharging_time": discharging_time,
    }


def _pick_media(rng: Random, os: str) -> Dict[str, int]:
    has_webcam = rng.random() < 0.85
    has_mic = rng.random() < 0.9
    speakers = rng.choice([1, 1, 2])
    return {
        "media_webcams": 1 if has_webcam else 0,
        "media_micros": 1 if has_mic else 0,
        "media_speakers": speakers,
    }


def _build_ua(arch: Archetype, ffver: str) -> str:
    return arch.ua_template.format(ffver=ffver)


def _build_app_version(ua: str) -> str:
    # navigator.appVersion = UA without "Mozilla/"
    return ua.removeprefix("Mozilla/")


def generate(
    archetype: Optional[str] = None,
    os: Optional[str] = None,
    locale: Optional[str] = None,
    firefox_version: Optional[str] = None,
    name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    seed: Optional[int] = None,
    **overrides: Any,
) -> Profile:
    """
    Generate a coherent Profile.

    Args:
        archetype: archetype id (e.g. "windows-11-mainstream"). Mutually exclusive with `os`.
        os: filter archetypes by OS ("windows", "macos", "linux").
        locale: force a locale (e.g. "fr-FR"). Weighted random if None.
        firefox_version: force Firefox version. Random from FIREFOX data if None.
        name: human label for the profile. Defaults to "<archetype_id>-<short_id>".
        tags: list of user tags.
        seed: deterministic seed for reproducibility.
        **overrides: any Profile attribute to hard-set after generation (bypasses
            consistency; use with care — validated afterward).

    Returns:
        A validated Profile.

    Raises:
        ConsistencyError: if overrides break invariants.
    """
    rng = Random(seed)
    arch = pick_archetype(rng, os=os, archetype_id=archetype)
    ff = _pick_firefox(rng, firefox_version)
    loc = pick_locale(rng, locale=locale)

    screen = _pick_screen(rng, arch)
    dpr = rng.choice(arch.dpr_choices)
    window = _pick_window(rng, screen["screen_width"], screen["screen_height"], dpr)
    geo = _pick_geo(rng, loc)
    battery = _pick_battery(rng)
    media = _pick_media(rng, arch.os)
    gpu = rng.choice(gpu_pool(arch.gpu_tier))
    fonts = _pick_fonts(rng, arch.font_set_id)

    ua = _build_ua(arch, ff["version"])
    app_version = _build_app_version(ua)

    profile_id = uuid.UUID(int=rng.getrandbits(128), version=4).hex[:12]
    default_name = name or f"{arch.id}-{profile_id[:6]}"

    p = Profile(
        id=profile_id,
        name=default_name,
        archetype_id=arch.id,
        tags=list(tags or []),
        os=arch.os,
        os_version=arch.os_version,
        platform=arch.platform,
        oscpu=arch.oscpu,
        firefox_version=ff["version"],
        build_id=ff["build_id"],
        product_sub=ff["product_sub"],
        user_agent=ua,
        app_version=app_version,
        cpu_cores=rng.choice(arch.cpu_cores_choices),
        max_touch_points=rng.choice(arch.max_touch_points_choices),
        color_depth=rng.choice(arch.color_depth_choices),
        device_pixel_ratio=dpr,
        webgl_vendor=gpu["vendor"],
        webgl_renderer=gpu["renderer"],
        locale=loc["locale"],
        language=loc["language"],
        region=loc["region"],
        languages=list(loc["languages"]),
        accept_language=loc["accept_language"],
        audio_sample_rate=rng.choice(arch.audio_sample_rate_choices),
        audio_output_latency=round(rng.uniform(0.005, 0.04), 4),
        audio_max_channel_count=rng.choice(arch.audio_max_channel_count_choices),
        fonts=fonts,
        fonts_spacing_seed=rng.randint(1, 2**31 - 1),
        media_enabled=True,
        dnt=rng.choices(["unspecified", "1", "0"], weights=[80, 15, 5], k=1)[0],
        global_privacy_control=rng.random() < 0.05,
        **screen,
        **window,
        **geo,
        **battery,
        **media,
    )

    for key, value in overrides.items():
        if not hasattr(p, key):
            raise AttributeError(f"Profile has no attribute {key!r}")
        setattr(p, key, value)

    assert_valid(p)
    return p
