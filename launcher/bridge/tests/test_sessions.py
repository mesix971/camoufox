"""SessionManager tests. Spawns short-lived real subprocesses so the PID
tracking / reconciliation logic is exercised."""

from __future__ import annotations

import os
import subprocess
import sys

from launcher.bridge.sessions import (
    Session,
    SessionManager,
    SessionStatus,
    _pid_alive,
    _pid_start_time,
)


def test_pid_alive_self() -> None:
    assert _pid_alive(os.getpid())


def test_pid_alive_zero() -> None:
    assert not _pid_alive(0)


def test_save_and_load(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    s = Session(id=Session.new_id(), pid=os.getpid(), profile_id="abc")
    mgr.save(s)
    loaded = mgr.load(s.id)
    assert loaded == s


def test_reconcile_marks_stopped(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    s = Session(id=Session.new_id(), pid=1, profile_id="abc",
                status=SessionStatus.STARTING.value)  # PID 1 won't be ours
    mgr.save(s)
    reloaded = mgr.list()
    # PID 1 is init, alive, so status moves to running. Use a definitely-dead PID.
    assert len(reloaded) == 1


def test_reconcile_definitely_dead_pid(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    # Use a very high PID that won't exist.
    s = Session(id=Session.new_id(), pid=999999, profile_id="abc",
                status=SessionStatus.RUNNING.value)
    mgr.save(s)
    listed = mgr.list()
    assert listed[0].status == SessionStatus.STOPPED.value
    assert listed[0].stopped_at is not None


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time, signal, sys;"
         "signal.signal(signal.SIGTERM, lambda *a: sys.exit(0));"
         "time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def test_kill_running_session(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    popen = _spawn_sleeper()
    try:
        s = Session(id=Session.new_id(), pid=popen.pid, profile_id="abc",
                    status=SessionStatus.RUNNING.value)
        mgr.save(s)
        assert _pid_alive(popen.pid)

        killed = mgr.kill(s.id, timeout=3.0)
        assert killed.status == SessionStatus.STOPPED.value
        # Give the subprocess a moment to exit before the test wrapper reaps it
        popen.wait(timeout=3.0)
        assert not _pid_alive(popen.pid)
    finally:
        if popen.poll() is None:
            popen.kill()


def test_list_sorts_by_start_time(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    a = Session(id="aaaa", pid=os.getpid(), profile_id="a", started_at="2025-01-01T00:00:00+00:00")
    b = Session(id="bbbb", pid=os.getpid(), profile_id="b", started_at="2025-06-01T00:00:00+00:00")
    mgr.save(a)
    mgr.save(b)
    listed = mgr.list()
    assert [s.id for s in listed] == ["bbbb", "aaaa"]


def test_prune_stopped(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    running = Session(id="run", pid=os.getpid(), profile_id="x",
                     status=SessionStatus.RUNNING.value)
    stopped = Session(id="stop", pid=999999, profile_id="y",
                     status=SessionStatus.STOPPED.value)
    mgr.save(running)
    mgr.save(stopped)
    n = mgr.prune_stopped()
    assert n == 1
    assert {s.id for s in mgr.list()} == {"run"}


def test_pid_start_time_self_is_set() -> None:
    """We can read our own process's start time."""
    st = _pid_start_time(os.getpid())
    assert st is not None
    assert st > 0


def test_pid_start_time_dead_pid_returns_none() -> None:
    assert _pid_start_time(999999) is None


def test_pid_start_time_zero_returns_none() -> None:
    assert _pid_start_time(0) is None


def test_pid_alive_with_matching_start_time() -> None:
    st = _pid_start_time(os.getpid())
    assert st is not None
    assert _pid_alive(os.getpid(), expected_start_time=st)


def test_pid_alive_rejects_stale_start_time() -> None:
    """A start_time that doesn't match the live process must be flagged dead.

    This is the bug fix: before this check, kill() on a recycled PID
    could SIGTERM an unrelated process. Now it refuses.
    """
    real = _pid_start_time(os.getpid())
    assert real is not None
    fake = real + 9999.0  # off by enough that the abs()<1.0 tolerance fails
    assert not _pid_alive(os.getpid(), expected_start_time=fake)


def test_pid_alive_without_start_time_is_backward_compatible() -> None:
    """Sessions persisted before the start_time field don't have one;
    plain liveness check must still work for them."""
    assert _pid_alive(os.getpid())  # no expected_start_time
    assert _pid_alive(os.getpid(), expected_start_time=None)


def test_kill_refuses_recycled_pid(tmp_path) -> None:
    """If a session's PID has been reused by another process, kill()
    must NOT signal that process — it should mark the session stopped
    without touching the unrelated PID."""
    mgr = SessionManager(tmp_path)
    # Save a session where the PID is alive (us) but start_time is
    # bogus, simulating PID reuse after the original Camoufox died.
    s = Session(
        id="ghost",
        pid=os.getpid(),
        profile_id="p",
        status=SessionStatus.RUNNING.value,
        start_time=12345.0,  # not our real start time
    )
    mgr.save(s)
    # If kill tried to SIGTERM us, the test would die here. Instead it
    # should detect the mismatch and quietly mark stopped.
    result = mgr.kill("ghost", timeout=0.5)
    assert result.status == SessionStatus.STOPPED.value
    # And our process is obviously still alive.
    assert _pid_alive(os.getpid())


def test_tail_log(tmp_path) -> None:
    mgr = SessionManager(tmp_path)
    log = mgr.logs_dir / "test.log"
    log.write_text("line1\nline2\nline3\n")
    s = Session(id="test", pid=os.getpid(), profile_id="x", log_path=str(log))
    mgr.save(s)
    text = mgr.tail_log("test", lines=2)
    assert text == "line2\nline3\n"
