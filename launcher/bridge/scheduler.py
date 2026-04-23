"""
Background scheduler daemon.

Jobs run periodically while the process is alive:
  - proxy_health_check:   every 10 min — run check-proxies-all, flag dead
  - session_crash_watch:  every 60 s   — detect sessions that crashed >N
                          times for the same profile_id and freeze the
                          profile (add tag "frozen") + webhook alert
  - ratelimit_escalation: every 60 s   — if a host is > 90% of its cap
                          for 5 consecutive checks, escalate via webhook

Run with:
    python -m launcher.bridge.scheduler

Writes state to ~/.camoufox/launcher/scheduler.json so crash/escalation
counters survive restarts. Kill with SIGTERM / Ctrl+C.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from launcher.bridge import webhook as webhook_mod


def _state_path() -> Path:
    return Path(
        os.environ.get(
            "LAUNCHER_SCHEDULER_STATE",
            str(Path.home() / ".camoufox" / "launcher" / "scheduler.json"),
        )
    )


def _log(level: str, msg: str, **extra) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {"t": ts, "level": level, "msg": msg, **extra}
    print(json.dumps(payload), flush=True)


def _load_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"crash_counters": {}, "ratelimit_streaks": {}, "last_runs": {}}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {"crash_counters": {}, "ratelimit_streaks": {}, "last_runs": {}}


def _save_state(s: Dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2, sort_keys=True))
    os.replace(tmp, p)


_STOP = False


def _handle_signal(signum, _frame):
    global _STOP
    _STOP = True
    _log("info", f"received signal {signum}, shutting down...")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def proxy_health_check(state: Dict[str, Any]) -> None:
    """Run a health check pass on all stored proxies, flag dead ones."""
    try:
        import proxypool
    except ImportError:
        _log("warn", "proxypool not importable, skipping health check")
        return

    from launcher.bridge.commands import proxy_store_path
    store = proxypool.ProxyStore(proxy_store_path())
    proxies = list(store.load_all(status=None))
    if not proxies:
        return
    checker = proxypool.HealthChecker(workers=10, timeout=15.0, geo_lookup=False)
    results = checker.check(proxies)
    store.save_many(proxies)
    ok = sum(1 for r in results if r.ok)
    flagged = [r.proxy_id for r in results if not r.ok]
    _log("info", "proxy health check done",
         checked=len(results), ok=ok, flagged=len(flagged))
    if len(flagged) > len(results) // 2 and len(results) > 4:
        webhook_mod.notify(
            f"⚠️ Plus de la moitié du pool de proxies est en échec "
            f"({len(flagged)}/{len(results)})",
            level="warn",
        )


def session_crash_watch(state: Dict[str, Any]) -> None:
    """Track crash counts per profile. Freeze profile after N recent crashes."""
    from launcher.bridge.commands import _session_mgr, _profile_store

    mgr = _session_mgr()
    sessions = mgr.list()
    counters = state.setdefault("crash_counters", {})

    # Reset counters older than 1h.
    now = time.time()
    to_drop = [k for k, v in counters.items() if now - v.get("updated", 0) > 3600]
    for k in to_drop:
        counters.pop(k, None)

    # Tally fresh crashes.
    newly_crashed = [
        s for s in sessions
        if s.status == "crashed" and s.stopped_at
        and _iso_to_ts(s.stopped_at) > now - 120.0  # last 2 min
    ]

    alerted_profiles: List[str] = []
    for s in newly_crashed:
        entry = counters.setdefault(s.profile_id, {"count": 0, "updated": now})
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["updated"] = now
        if entry["count"] >= 3 and s.profile_id not in alerted_profiles:
            alerted_profiles.append(s.profile_id)
            _freeze_profile(s.profile_id)
            webhook_mod.notify(
                f"❄️ Profil **{s.profile_id}** gelé — {entry['count']} crashes en <1h",
                level="error",
            )


def ratelimit_escalation(state: Dict[str, Any]) -> None:
    """Alert if a host is sustainedly near its rate cap."""
    from launcher.bridge.commands import ratelimit_stats
    streaks = state.setdefault("ratelimit_streaks", {})
    try:
        data = ratelimit_stats({}).get("hosts", {})
    except Exception:  # noqa: BLE001
        return
    for host, s in data.items():
        events = int(s.get("events_last_minute", 0) or 0)
        cap = int(s.get("max_per_minute", 0) or 0)
        if cap == 0:
            continue
        streak = streaks.setdefault(host, 0)
        if events / cap >= 0.9:
            streak += 1
        else:
            streak = 0
        streaks[host] = streak
        if streak == 5:
            webhook_mod.notify(
                f"🚦 Rate limit saturé sur **{host}** "
                f"({events}/{cap} req/min depuis 5 min) — "
                f"envisagez un backoff ou plus de proxies.",
                level="warn",
            )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iso_to_ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _freeze_profile(profile_id: str) -> None:
    try:
        from launcher.bridge.commands import _profile_store
        store = _profile_store()
        p = store.load(profile_id)
        if p.tags is None:
            p.tags = []
        if "frozen" not in p.tags:
            p.tags.append("frozen")
            store.save(p)
    except (KeyError, OSError) as e:
        _log("warn", f"could not freeze profile {profile_id}: {e}")


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------

JOBS: List[tuple] = [
    # (name, interval_seconds, fn)
    ("proxy_health_check", 600, proxy_health_check),
    ("session_crash_watch", 60, session_crash_watch),
    ("ratelimit_escalation", 60, ratelimit_escalation),
]


def run_forever() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _log("info", "scheduler started", jobs=[j[0] for j in JOBS])

    state = _load_state()
    last_runs: Dict[str, float] = state.setdefault("last_runs", {})

    while not _STOP:
        now = time.time()
        for name, interval, fn in JOBS:
            last = float(last_runs.get(name, 0))
            if now - last >= interval:
                last_runs[name] = now
                try:
                    fn(state)
                except Exception as e:  # noqa: BLE001
                    _log("error", f"{name} failed: {type(e).__name__}: {e}")
        _save_state(state)
        time.sleep(1.0)

    _log("info", "scheduler stopped")


if __name__ == "__main__":
    run_forever()
