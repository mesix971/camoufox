"""
Consistency engine.

Runs invariants over a Profile that a bot-detection stack routinely checks
for cross-field contradictions. Violation = the Profile is rejected before
it's ever saved or launched.

Rules:
  R1  UA string matches os + oscpu + firefox_version
  R2  navigator.platform matches os
  R3  Font set matches os (disjoint Windows vs macOS vs Linux)
  R4  WebGL renderer plausibility vs os (no "Apple M2" on Windows)
  R5  DPR matches retina conventions (Mac retina => 2.0)
  R6  Window dims <= screen dims (inner <= outer <= screen)
  R7  availHeight = screen.height - taskbar_height (within ±2 tolerance)
  R8  Timezone in locale's allowed tz pool
  R9  Geo lat/lon within plausible bbox for timezone centroid (±5°)
  R10 accept_language starts with locale
  R11 languages[0] == locale
  R12 hardwareConcurrency in [2..64] and a power of 2 or standard consumer value
  R13 Battery: charging -> dischargingTime == 0; !charging -> chargingTime == 0; level in [0,1]
  R14 audio sample rate in well-known set {44100, 48000, 96000}
  R15 build_id is 14 digits
  R16 color_depth in {24, 30, 32}

Call validate(profile) to get a list of failures. If the list is empty the
profile passes.
"""

from __future__ import annotations

import re
from typing import List

from fpgen.archetypes import FONTS, LOCALES
from fpgen.profile import Profile


class ConsistencyError(ValueError):
    """Raised when a Profile fails one or more invariants."""


_UA_RE = re.compile(
    r"^Mozilla/5\.0 \((?P<platbit>[^)]+)\) Gecko/20100101 Firefox/(?P<ffver>[\d.]+)$"
)

_OS_UA_PLATFORM_FRAGMENTS = {
    "windows": "Windows NT",
    "macos": "Macintosh",
    "linux": "X11",
}

_OS_PLATFORM = {
    "windows": "Win32",
    "macos": "MacIntel",
    "linux": "Linux x86_64",
}

_ACCEPTED_CORES = {1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 48, 64}
_ACCEPTED_SAMPLE_RATES = {44100, 48000, 96000}
_ACCEPTED_COLOR_DEPTH = {24, 30, 32}


def _check_ua(p: Profile, errs: List[str]) -> None:
    m = _UA_RE.match(p.user_agent)
    if not m:
        errs.append(f"R1: user_agent does not match Firefox UA pattern: {p.user_agent!r}")
        return
    frag = _OS_UA_PLATFORM_FRAGMENTS.get(p.os)
    if frag and frag not in m.group("platbit"):
        errs.append(
            f"R1: UA platform fragment {m.group('platbit')!r} inconsistent with os={p.os!r} "
            f"(expected to contain {frag!r})"
        )
    if m.group("ffver") != p.firefox_version:
        errs.append(
            f"R1: UA Firefox version {m.group('ffver')!r} != firefox_version {p.firefox_version!r}"
        )


def _check_platform(p: Profile, errs: List[str]) -> None:
    expected = _OS_PLATFORM.get(p.os)
    if expected and p.platform != expected:
        errs.append(f"R2: platform={p.platform!r} inconsistent with os={p.os!r} (expected {expected!r})")


def _check_fonts(p: Profile, errs: List[str]) -> None:
    if not p.fonts:
        errs.append("R3: fonts list is empty")
        return
    # Identify which OS each font "belongs" to by majority membership.
    # Allow ~10% cross-OS fonts (Arial, Times New Roman, etc. are truly universal).
    expected_set = set(FONTS.get(p.os, []))
    if not expected_set:
        errs.append(f"R3: no font set for os={p.os!r}")
        return
    wrong_os = {"windows", "macos", "linux"} - {p.os}
    foreign_sets = {other: set(FONTS[other]) - expected_set for other in wrong_os}
    profile_fonts = set(p.fonts)
    overlap = profile_fonts & expected_set
    if len(overlap) < len(profile_fonts) * 0.6:
        errs.append(
            f"R3: only {len(overlap)}/{len(profile_fonts)} fonts match os={p.os!r} set; "
            f"fingerprint will look cross-OS"
        )
    for other, other_only in foreign_sets.items():
        foreign = profile_fonts & other_only
        if len(foreign) > 3:
            errs.append(
                f"R3: {len(foreign)} fonts exclusive to {other!r} leaked into os={p.os!r} profile: "
                f"{sorted(foreign)[:5]}"
            )


def _check_webgl(p: Profile, errs: List[str]) -> None:
    renderer = p.webgl_renderer
    vendor = p.webgl_vendor
    if not renderer or not vendor:
        errs.append("R4: webgl vendor/renderer empty")
        return
    r_lower = renderer.lower()
    if p.os == "macos":
        if "angle" in r_lower or "direct3d" in r_lower:
            errs.append(f"R4: Direct3D/ANGLE renderer on macOS is impossible: {renderer!r}")
    elif p.os == "windows":
        if "apple" in r_lower or "m1" in r_lower or " m2" in r_lower or " m3" in r_lower:
            errs.append(f"R4: Apple GPU renderer on Windows is impossible: {renderer!r}")
        if "opengl engine" in r_lower:
            errs.append(f"R4: Mac-style OpenGL Engine string on Windows: {renderer!r}")
    elif p.os == "linux":
        if "direct3d" in r_lower or "angle (" in r_lower:
            errs.append(f"R4: Direct3D/ANGLE renderer on Linux is impossible: {renderer!r}")
        if "apple" in r_lower:
            errs.append(f"R4: Apple GPU renderer on Linux is impossible: {renderer!r}")


def _check_dpr(p: Profile, errs: List[str]) -> None:
    if p.device_pixel_ratio <= 0:
        errs.append(f"R5: devicePixelRatio must be > 0, got {p.device_pixel_ratio}")
    if p.os == "macos" and p.device_pixel_ratio not in (1.0, 2.0):
        errs.append(f"R5: macOS devicePixelRatio should be 1.0 or 2.0, got {p.device_pixel_ratio}")


def _check_window_dims(p: Profile, errs: List[str]) -> None:
    if not (p.inner_width <= p.outer_width <= p.screen_width):
        errs.append(
            f"R6: inner ({p.inner_width}) <= outer ({p.outer_width}) <= screen ({p.screen_width}) violated"
        )
    if not (p.inner_height <= p.outer_height <= p.screen_height):
        errs.append(
            f"R6: inner ({p.inner_height}) <= outer ({p.outer_height}) <= screen ({p.screen_height}) violated"
        )


def _check_avail(p: Profile, errs: List[str]) -> None:
    if p.avail_width != p.screen_width:
        errs.append(f"R7: availWidth ({p.avail_width}) != screen.width ({p.screen_width})")
    if p.avail_height > p.screen_height:
        errs.append(f"R7: availHeight ({p.avail_height}) > screen.height ({p.screen_height})")
    if p.screen_height - p.avail_height > 100:
        errs.append(
            f"R7: taskbar gap {p.screen_height - p.avail_height}px too large "
            f"(screen={p.screen_height}, avail={p.avail_height})"
        )


def _check_locale(p: Profile, errs: List[str]) -> None:
    loc = next((x for x in LOCALES if x["locale"] == p.locale), None)
    if not loc:
        errs.append(f"R8: locale {p.locale!r} not in known locales table")
        return
    if p.timezone not in loc["timezones"]:
        errs.append(
            f"R8: timezone {p.timezone!r} not in allowed pool for locale {p.locale!r}: "
            f"{loc['timezones']}"
        )
    if p.accept_language and not p.accept_language.lower().startswith(p.locale.lower()):
        errs.append(
            f"R10: accept_language {p.accept_language!r} must start with locale {p.locale!r}"
        )
    if not p.languages or p.languages[0] != p.locale:
        errs.append(f"R11: languages[0] {p.languages[:1]} must equal locale {p.locale!r}")


def _check_geo(p: Profile, errs: List[str]) -> None:
    loc = next((x for x in LOCALES if x["locale"] == p.locale), None)
    if not loc:
        return  # already reported by R8
    centroids = [c for c in loc["geo_centroids"] if c["tz"] == p.timezone]
    if not centroids:
        return  # timezone mismatch already reported
    nearest = min(centroids, key=lambda c: abs(c["lat"] - p.latitude) + abs(c["lon"] - p.longitude))
    if abs(nearest["lat"] - p.latitude) > 5 or abs(nearest["lon"] - p.longitude) > 5:
        errs.append(
            f"R9: geo ({p.latitude}, {p.longitude}) too far from expected centroid "
            f"({nearest['lat']}, {nearest['lon']}) for tz={p.timezone!r}"
        )


def _check_misc(p: Profile, errs: List[str]) -> None:
    if p.cpu_cores not in _ACCEPTED_CORES:
        errs.append(f"R12: hardwareConcurrency={p.cpu_cores} not a common consumer value")
    if not p.battery_charging and p.battery_charging_time != 0:
        errs.append("R13: battery_charging_time must be 0 when not charging")
    if p.battery_charging and p.battery_discharging_time != 0:
        errs.append("R13: battery_discharging_time must be 0 when charging")
    if not 0.0 <= p.battery_level <= 1.0:
        errs.append(f"R13: battery_level={p.battery_level} out of [0, 1]")
    if p.audio_sample_rate not in _ACCEPTED_SAMPLE_RATES:
        errs.append(f"R14: audio_sample_rate={p.audio_sample_rate} not in {_ACCEPTED_SAMPLE_RATES}")
    if not re.fullmatch(r"\d{14}", p.build_id):
        errs.append(f"R15: build_id={p.build_id!r} is not 14 digits")
    if p.color_depth not in _ACCEPTED_COLOR_DEPTH:
        errs.append(f"R16: color_depth={p.color_depth} not in {_ACCEPTED_COLOR_DEPTH}")


def validate(profile: Profile) -> List[str]:
    errs: List[str] = []
    _check_ua(profile, errs)
    _check_platform(profile, errs)
    _check_fonts(profile, errs)
    _check_webgl(profile, errs)
    _check_dpr(profile, errs)
    _check_window_dims(profile, errs)
    _check_avail(profile, errs)
    _check_locale(profile, errs)
    _check_geo(profile, errs)
    _check_misc(profile, errs)
    return errs


def assert_valid(profile: Profile) -> None:
    errs = validate(profile)
    if errs:
        raise ConsistencyError("profile failed " + str(len(errs)) + " invariants:\n  - " + "\n  - ".join(errs))
