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

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        return cls(**json.loads(raw))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


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

    def _reconcile(self, s: Session) -> None:
        """Update status/exit_code in the pidfile based on whether PID is alive."""
        if s.status in (SessionStatus.STOPPED.value, SessionStatus.CRASHED.value):
            return
        if _pid_alive(s.pid):
            if s.status == SessionStatus.STARTING.value:
                s.status = SessionStatus.RUNNING.value
                self.save(s)
            return
        # PID is gone — mark stopped.
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
        runner_argv_extra: Optional[List[str]] = None,
    ) -> Session:
        """Start a detached session_runner subprocess. Returns the persisted Session."""
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
        )
        self.save(s)
        return s

    def kill(self, session_id: str, timeout: float = 5.0) -> Session:
        s = self.load(session_id)
        if not _pid_alive(s.pid):
            self._reconcile(s)
            return s
        try:
            os.kill(s.pid, signal.SIGTERM)
        except ProcessLookupError:
            self._reconcile(s)
            return s
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _pid_alive(s.pid):
                break
            time.sleep(0.1)
        if _pid_alive(s.pid):
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
            if _pid_alive(s.pid):
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
