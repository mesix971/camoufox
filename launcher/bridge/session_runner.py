"""
session_runner — the long-lived subprocess that actually holds one Camoufox
browser open for a Session.

Spawned by SessionManager.spawn(). Reads profile + proxy from the fpgen and
proxypool stores, launches Camoufox with the combined config, navigates to
the target URL, then waits for SIGTERM to close cleanly.

Running:
    python -m launcher.bridge.session_runner \\
        --session-id <id> --profile-id <id> [--proxy-id <id>] [--url <url>] [--headless]

stdout/stderr are captured by SessionManager into <sessions_root>/logs/<id>.log.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Defer heavy imports so import-time errors are reported cleanly in the log.
def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] {msg}", flush=True)


def _profile_store_path() -> str:
    return os.environ.get("FPGEN_STORE", str(Path.home() / ".camoufox" / "fpgen"))


def _proxy_store_path() -> str:
    return os.environ.get("PROXYPOOL_STORE", str(Path.home() / ".camoufox" / "proxypool"))


def _session_store_path() -> str:
    return os.environ.get("LAUNCHER_SESSIONS", str(Path.home() / ".camoufox" / "launcher" / "sessions"))


_STOP = False


def _handle_signal(signum, _frame):
    global _STOP
    _STOP = True
    _log(f"received signal {signum}, shutting down...")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--proxy-id")
    ap.add_argument("--url")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        import fpgen
        import proxypool
    except ImportError as e:
        _log(f"FATAL: fpgen/proxypool not importable: {e}")
        return 2

    try:
        profile = fpgen.ProfileStore(_profile_store_path()).load(args.profile_id)
    except KeyError:
        _log(f"FATAL: profile {args.profile_id} not found")
        return 2

    proxy = None
    if args.proxy_id:
        try:
            proxy = proxypool.ProxyStore(_proxy_store_path()).load(args.proxy_id)
        except KeyError:
            _log(f"FATAL: proxy {args.proxy_id} not found")
            return 2

    _log(f"session={args.session_id} profile={profile.name} "
         f"proxy={proxy.label if proxy else '-'} url={args.url or '-'} headless={args.headless}")

    config = fpgen.to_camoufox_config(profile)
    proxy_kwarg = proxypool.to_camoufox_proxy(proxy) if proxy else None

    # Update the pidfile early so the launcher sees "running".
    _mark_running(args.session_id)

    try:
        from camoufox.sync_api import Camoufox
    except ImportError as e:
        _log(f"FATAL: camoufox not importable (run in Camoufox env): {e}")
        return 2

    launch_kwargs = {"config": config, "headless": args.headless}
    if proxy_kwarg is not None:
        launch_kwargs["proxy"] = proxy_kwarg

    try:
        with Camoufox(**launch_kwargs) as browser:
            page = browser.new_page()
            if args.url:
                page.goto(args.url)
            _log("browser ready; waiting for stop signal")
            while not _STOP:
                time.sleep(0.25)
            _log("stop signal received; closing browser")
    except Exception as e:  # noqa: BLE001 — runner must log everything
        _log(f"FATAL: {type(e).__name__}: {e}")
        _log(traceback.format_exc())
        return 1

    _log("session exited cleanly")
    return 0


def _mark_running(session_id: str) -> None:
    path = Path(_session_store_path()) / f"{session_id}.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        data["status"] = "running"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, path)
    except (OSError, json.JSONDecodeError) as e:
        _log(f"could not mark running: {e}")


if __name__ == "__main__":
    sys.exit(main())
