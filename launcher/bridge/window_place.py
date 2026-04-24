"""
Move a browser window to a given (x, y, w, h) rect.

Strategy (tried in order):
  1. page.evaluate("window.moveTo/resizeTo") — works when the pref
     dom.allow_scripts_to_close_windows is true OR Camoufox patches
     the restriction (it does, since it spoofs window geometry).
  2. OS-level window management via ctypes on Windows, wmctrl on Linux,
     AppleScript on macOS, filtering by PID.

Silent on failure — tiling is a UX convenience, not a correctness feature.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Optional


def place_window(page, pid: int, x: int, y: int, w: int, h: int) -> bool:
    """Try in-page JS first, then OS-level. Returns True if any worked."""
    if _via_page_eval(page, x, y, w, h):
        return True
    return _via_os(pid, x, y, w, h)


def _via_page_eval(page, x: int, y: int, w: int, h: int) -> bool:
    try:
        page.evaluate(
            "([x,y,w,h]) => { window.moveTo(x,y); window.resizeTo(w,h); }",
            [x, y, w, h],
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _via_os(pid: int, x: int, y: int, w: int, h: int) -> bool:
    if sys.platform == "win32":
        return _windows_place(pid, x, y, w, h)
    if sys.platform == "darwin":
        return _macos_place(pid, x, y, w, h)
    return _linux_place(pid, x, y, w, h)


def _windows_place(pid: int, x: int, y: int, w: int, h: int, wait_sec: float = 3.0) -> bool:
    """Find any top-level HWND owned by (pid OR its children) and SetWindowPos."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
        )
        user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND

        target_pids = _descendants_windows(pid) | {pid}

        deadline = time.time() + wait_sec
        found: Optional[int] = None
        while time.time() < deadline and found is None:
            hwnds = []

            def cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                if user32.GetParent(hwnd):  # skip child windows
                    return True
                owner = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value in target_pids:
                    hwnds.append(hwnd)
                return True

            user32.EnumWindows(EnumWindowsProc(cb), 0)
            if hwnds:
                found = hwnds[0]
            else:
                time.sleep(0.25)
                target_pids = _descendants_windows(pid) | {pid}

        if found is None:
            return False

        HWND_TOP = 0
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(found, HWND_TOP, x, y, w, h, SWP_SHOWWINDOW)
        return True
    except Exception:  # noqa: BLE001
        return False


def _descendants_windows(pid: int) -> set:
    """Return {pid, ...children...} on Windows using toolhelp32."""
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return {pid}
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        children: dict = {}
        if k32.Process32First(snap, ctypes.byref(entry)):
            while True:
                children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
                if not k32.Process32Next(snap, ctypes.byref(entry)):
                    break
        k32.CloseHandle(snap)

        out = {pid}
        stack = [pid]
        while stack:
            p = stack.pop()
            for c in children.get(p, []):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out
    except Exception:  # noqa: BLE001
        return {pid}


def _linux_place(pid: int, x: int, y: int, w: int, h: int) -> bool:
    # wmctrl -l -p tells us which window belongs to which pid.
    try:
        out = subprocess.check_output(
            ["wmctrl", "-l", "-p"], timeout=3, text=True,
        )
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            wid, _desk, wpid, *_ = parts
            if int(wpid) == pid:
                subprocess.run(
                    ["wmctrl", "-i", "-r", wid, "-e", f"0,{x},{y},{w},{h}"],
                    timeout=3, check=False,
                )
                return True
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return False


def _macos_place(pid: int, x: int, y: int, w: int, h: int) -> bool:
    # Best-effort via AppleScript on the frontmost window of our process.
    script = f'''
    tell application "System Events"
      set theProc to first process whose unix id is {pid}
      set position of window 1 of theProc to {{{x}, {y}}}
      set size of window 1 of theProc to {{{w}, {h}}}
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", script], timeout=5, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False
