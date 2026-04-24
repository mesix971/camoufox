"""
Primary monitor size detection, cross-platform.

Returns (width, height) in pixels. Falls back to (1920, 1080) if all
detection methods fail.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Tuple


DEFAULT_SIZE = (1920, 1080)


def primary_monitor_size() -> Tuple[int, int]:
    if sys.platform == "win32":
        return _windows_size()
    if sys.platform == "darwin":
        return _macos_size()
    return _linux_size()


def _windows_size() -> Tuple[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # SM_CXSCREEN = 0, SM_CYSCREEN = 1 — primary monitor, unscaled DPI
        user32.SetProcessDPIAware()  # so we get real pixels, not scaled
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except Exception:  # noqa: BLE001
        return DEFAULT_SIZE


def _macos_size() -> Tuple[int, int]:
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType"],
            timeout=5, text=True,
        )
        # Look for "Resolution: 2560 x 1440" first hit
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Resolution:"):
                parts = line.replace("Resolution:", "").split("x")
                if len(parts) >= 2:
                    w = int(parts[0].strip())
                    h = int(parts[1].split()[0].strip())
                    return (w, h)
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_SIZE


def _linux_size() -> Tuple[int, int]:
    # Try xrandr first (X11), then swaymsg (Wayland sway), then fallback.
    for cmd in (
        ["xrandr", "--query"],
        ["sh", "-c", "swaymsg -t get_outputs | head -c 4096"],
    ):
        try:
            out = subprocess.check_output(cmd, timeout=3, text=True)
        except Exception:  # noqa: BLE001
            continue
        # xrandr: line like "Screen 0: ... current 1920 x 1080, ..."
        for line in out.splitlines():
            if "current" in line and "x" in line:
                parts = line.split("current", 1)[1].split(",")[0]
                nums = parts.replace("x", " ").split()
                if len(nums) >= 2:
                    try:
                        return (int(nums[0]), int(nums[1]))
                    except ValueError:
                        continue
    return DEFAULT_SIZE
