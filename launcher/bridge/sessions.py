"""
Session manager.

A Session is a running Camoufox subprocess bound to a (profile_id, proxy_id?,
url?) tuple. Persistence is via one JSON pidfile per session, so that any
bridge invocation can rediscover running sessions.

Layout:
    <sessions_root>/
        <session_id>.json          — pidfile metadata
        logs/
            <session_id>.log       — stdout/stderr captured while running
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"


class ProfileBusyError(RuntimeError):
    """Raised when an operation would launch a second Camoufox process on a
    profile's user_data_dir while another active session already holds it.

    Concurrent processes on the same Firefox profile fight over parent.lock,
    corrupt places.sqlite/cookies.sqlite, and on Windows can both succeed at
    opening the profile, producing silent data loss.
    """


@dataclass
class Session:
    id: str
    pid: int
    profile_id: str
    proxy_id: Optional[str] = None
    url: Optional[str] = None
    headless: bool = False
    log_path: str = ""
    started_at: str = field(default_factory=_utc_now_iso)
    stopped_at: Optional[str] = None
    status: str = SessionStatus.STARTING.value
    exit_code: Optional[int] = None
    error: Optional[str] = None
    # Process start time (POSIX: jiffies since boot from /proc/<pid>/stat
    # field 22; Windows: CreationTime FILETIME from GetProcessTimes).
    # Stored alongside the PID so we can detect PID reuse: if the process
    # at this PID has a different start time than the one we recorded,
    # it's a different process — don't kill it.
    start_time: Optional[float] = None

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        return cls(**json.loads(raw))


def _pid_start_time(pid: int) -> Optional[float]:
    """Return a stable identifier for *this* process at this PID.

    On POSIX: starttime from /proc/<pid>/stat field 22 (jiffies since
    boot). The kernel reuses PIDs but a freshly-spawned process always
    gets a strictly later starttime, so the (pid, starttime) tuple is
    unique within a boot.

    On Windows: CreationTime as a 64-bit FILETIME from GetProcessTimes.

    Returns None if the PID does not exist or the lookup failed.
    """
    if pid <= 0:
        return None
    if sys.platform == "win32":
        return _pid_start_time_windows(pid)
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    # The comm (field 2) can contain spaces and parens, so split after
    # the LAST ')' to be safe.
    rparen = data.rfind(b")")
    if rparen < 0:
        return None
    rest = data[rparen + 1:].split()
    # After the comm, fields are state(3), ppid(4), …, starttime(22).
    # That's index 22 - 3 = 19 in the rest list.
    if len(rest) < 20:
        return None
    try:
        return float(rest[19])
    except ValueError:
        return None


def _pid_start_time_windows(pid: int) -> Optional[float]:
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_ = wintypes.FILETIME()
        kernel_ = wintypes.FILETIME()
        user_ = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                        ctypes.byref(exit_),
                                        ctypes.byref(kernel_),
                                        ctypes.byref(user_)):
            return None
        # Combine high+low 32-bit halves into a single 64-bit value.
        return float((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int, expected_start_time: Optional[float] = None) -> bool:
    """True if PID is alive AND, if expected_start_time is given, it
    matches the start time of the live process.

    Without ``expected_start_time``, this is a plain liveness check —
    backwards-compatible for sessions persisted before the start_time
    field was added. With it, we reject hits where the kernel has
    reused the PID for an unrelated process (a real risk on long-lived
    Linux hosts where the 32 768 default PID range wraps).
    """
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False
    else:
        if not _pid_alive_windows(pid):
            return False
    if expected_start_time is None:
        return True
    actual = _pid_start_time(pid)
    if actual is None:
        return False
    # FILETIME / jiffies are integers; tolerate tiny float rounding.
    return abs(actual - expected_start_time) < 1.0


def _pid_alive_windows(pid: int) -> bool:
    # os.kill(pid, 0) on Windows uses OpenProcess(PROCESS_ALL_ACCESS) which
    # frequently fails with OSError even for same-user processes (especially
    # detached ones). Use PROCESS_QUERY_LIMITED_INFORMATION which is the
    # canonical minimal-permission probe and check the exit code.
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


class SessionManager:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.logs_dir = self.root / "logs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _pidfile(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    # --- CRUD ---

    def save(self, s: Session) -> None:
        path = self._pidfile(s.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(s.to_json())
        os.replace(tmp, path)

    def load(self, session_id: str) -> Session:
        path = self._pidfile(session_id)
        if not path.exists():
            raise KeyError(f"session not found: {session_id}")
        return Session.from_json(path.read_text())

    def exists(self, session_id: str) -> bool:
        return self._pidfile(session_id).exists()

    def list(self) -> List[Session]:
        out: List[Session] = []
        for path in sorted(self.root.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            try:
                s = Session.from_json(path.read_text())
            except (json.JSONDecodeError, TypeError):
                continue
            # Reconcile status against actual PID state.
            self._reconcile(s)
            out.append(s)
        out.sort(key=lambda s: s.started_at, reverse=True)
        return out

    def active_profile_ids(self) -> set[str]:
        """Return the set of profile_ids whose Camoufox process is currently
        live. Reads pidfiles fresh and checks PID liveness so the answer
        reflects reality even after a crash.
        """
        active: set[str] = set()
        for path in self.root.glob("*.json"):
            if path.name.endswith(".tmp"):
                continue
            try:
                s = Session.from_json(path.read_text())
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if s.status in (SessionStatus.STOPPED.value, SessionStatus.CRASHED.value):
                continue
            if _pid_alive(s.pid):
                active.add(s.profile_id)
        return active

    def assert_profile_free(self, profile_id: str) -> None:
        """Raise ProfileBusyError if a live session already owns this profile.

        Call before any operation that would open a second Camoufox process
        on the same user_data_dir (spawn, cookie export, warmup task, …).
        """
        if profile_id in self.active_profile_ids():
            raise ProfileBusyError(
                f"profile {profile_id!r} is already in use by a live session; "
                f"stop it first or wait for it to finish"
            )

    def _reconcile(self, s: Session) -> None:
        """Update status/exit_code in the pidfile based on whether PID is alive.

        Uses the saved start_time (when present) to avoid mistaking a
        recycled PID for our process — important on long-running hosts
        where the kernel reuses PIDs.
        """
        if s.status in (SessionStatus.STOPPED.value, SessionStatus.CRASHED.value):
            return
        if _pid_alive(s.pid, expected_start_time=s.start_time):
            if s.status == SessionStatus.STARTING.value:
                s.status = SessionStatus.RUNNING.value
                self.save(s)
            return
        # PID is gone (or has been reused) — mark stopped.
        s.status = SessionStatus.STOPPED.value
        s.stopped_at = _utc_now_iso()
        self.save(s)

    def delete(self, session_id: str) -> None:
        path = self._pidfile(session_id)
        if path.exists():
            path.unlink()
        log = self.logs_dir / f"{session_id}.log"
        if log.exists():
            log.unlink()

    # --- lifecycle ---

    def spawn(
        self,
        profile_id: str,
        proxy_id: Optional[str] = None,
        url: Optional[str] = None,
        headless: bool = False,
        warmup: bool = False,
        auto_refresh: float = 0.0,
        persistent: bool = False,
        queue_monitor: bool = False,
        rate_limit: int = 0,
        auto_solve_captcha: bool = False,
        humanlike: bool = False,
        run_macro: Optional[str] = None,
        record_macro: Optional[str] = None,
        tile: Optional[tuple] = None,  # (x, y, w, h)
        runner_argv_extra: Optional[List[str]] = None,
    ) -> Session:
        """Start a detached session_runner subprocess. Returns the persisted Session.

        Raises ProfileBusyError if another live session already owns this
        profile_id — concurrent Camoufox processes on the same user_data_dir
        corrupt the Firefox profile.
        """
        self.assert_profile_free(profile_id)
        session_id = Session.new_id()
        log_path = self.logs_dir / f"{session_id}.log"
        log_fh = log_path.open("w")  # closed when this process exits

        argv = [
            sys.executable, "-m", "launcher.bridge.session_runner",
            "--session-id", session_id,
            "--profile-id", profile_id,
        ]
        if proxy_id:
            argv += ["--proxy-id", proxy_id]
        if url:
            argv += ["--url", url]
        if headless:
            argv += ["--headless"]
        if warmup:
            argv += ["--warmup"]
        if auto_refresh > 0:
            argv += ["--auto-refresh", str(auto_refresh)]
        if persistent:
            argv += ["--persistent"]
        if queue_monitor:
            argv += ["--queue-monitor"]
        if rate_limit > 0:
            argv += ["--rate-limit", str(rate_limit)]
        if auto_solve_captcha:
            argv += ["--auto-solve-captcha"]
        if humanlike:
            argv += ["--humanlike"]
        if run_macro:
            argv += ["--run-macro", run_macro]
        if record_macro:
            argv += ["--record-macro", record_macro]
        if tile and len(tile) == 4:
            argv += ["--tile", ",".join(str(int(v)) for v in tile)]
        if runner_argv_extra:
            argv += list(runner_argv_extra)

        popen_kwargs: Dict[str, Any] = {
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # Electron/Node spawns us inside a Windows Job Object with
            # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. When this intermediate Python
            # exits, the job closes and kills session_runner too. Break out of
            # the job and detach from any console so the browser survives.
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            popen_kwargs["creationflags"] = (
                DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
            )
        else:
            popen_kwargs["start_new_session"] = True  # POSIX setsid

        popen = subprocess.Popen(argv, **popen_kwargs)
        # Close in the parent — the child inherited the FD and owns it now.
        log_fh.close()

        s = Session(
            id=session_id,
            pid=popen.pid,
            profile_id=profile_id,
            proxy_id=proxy_id,
            url=url,
            headless=headless,
            log_path=str(log_path),
            status=SessionStatus.STARTING.value,
            start_time=_pid_start_time(popen.pid),
        )
        self.save(s)
        return s

    def kill(self, session_id: str, timeout: float = 5.0) -> Session:
        """Stop the session's process, refusing to signal a recycled PID.

        Compares the live PID's start_time against the one we recorded at
        spawn time. If they don't match, the original process is gone and
        the PID now belongs to something else (sshd, another user's shell,
        anything) — we mark the session stopped without sending SIGTERM.
        """
        s = self.load(session_id)
        if not _pid_alive(s.pid, expected_start_time=s.start_time):
            self._reconcile(s)
            return s
        try:
            os.kill(s.pid, signal.SIGTERM)
        except ProcessLookupError:
            self._reconcile(s)
            return s
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _pid_alive(s.pid, expected_start_time=s.start_time):
                break
            time.sleep(0.1)
        if _pid_alive(s.pid, expected_start_time=s.start_time):
            try:
                os.kill(s.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        s.status = SessionStatus.STOPPED.value
        s.stopped_at = _utc_now_iso()
        self.save(s)
        return s

    def kill_all(self) -> int:
        count = 0
        for s in self.list():
            if _pid_alive(s.pid, expected_start_time=s.start_time):
                self.kill(s.id)
                count += 1
        return count

    def prune_stopped(self) -> int:
        count = 0
        for s in self.list():
            if s.status in (SessionStatus.STOPPED.value, SessionStatus.CRASHED.value):
                self.delete(s.id)
                count += 1
        return count

    def tail_log(self, session_id: str, lines: int = 200) -> str:
        s = self.load(session_id)
        path = Path(s.log_path)
        if not path.exists():
            return ""
        with path.open() as f:
            data = f.readlines()
        return "".join(data[-lines:])

    def as_dict(self, s: Session) -> Dict[str, Any]:
        return asdict(s)
