"""
session_runner — the long-lived subprocess that actually holds one Camoufox
browser open for a Session.

Spawned by SessionManager.spawn(). Reads profile + proxy from the fpgen and
proxypool stores, launches Camoufox with the combined config, navigates to
the target URL, then waits for SIGTERM to close cleanly.

Running:
    python -m launcher.bridge.session_runner \\
        --session-id <id> --profile-id <id> [--proxy-id <id>] [--url <url>] [--headless] \\
        [--warmup] [--auto-refresh 30] [--persistent] [--queue-monitor]

stdout/stderr are captured by SessionManager into <sessions_root>/logs/<id>.log.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from launcher.bridge import warmup as warmup_mod
from launcher.bridge.ratelimit import RateLimiter, RateLimitExceeded
from launcher.bridge.retry import RetrySpec, retry
from launcher.bridge.webhook import notify as webhook_notify


def _captcha_store_path() -> str:
    return os.environ.get(
        "CAPTCHAPOOL_STORE",
        str(Path.home() / ".camoufox" / "captchapool"),
    )


def _maybe_build_solver():
    """Build a captcha Solver from saved providers, or return None if none configured."""
    try:
        import captchapool  # type: ignore
    except ImportError:
        return None
    try:
        store = captchapool.ProviderStore(_captcha_store_path())
        if not store.list():
            return None
        return store.build_solver()
    except Exception:  # noqa: BLE001 — captcha is opt-in; never crash the session
        return None


def _detect_and_solve_captcha(page, solver, url: str) -> bool:
    """Best-effort: look for a Turnstile / reCAPTCHA / hCaptcha iframe on the
    current page and, if found, ask the solver for a token and inject it.

    Returns True if a captcha was solved, False otherwise. Never raises —
    captcha integration is opt-in.
    """
    if solver is None:
        return False
    try:
        iframe_info = page.evaluate(
            """() => {
              const f = [...document.querySelectorAll('iframe')]
                .map(e => e.src || '').find(s =>
                  s.includes('challenges.cloudflare.com') ||
                  s.includes('recaptcha') ||
                  s.includes('hcaptcha'));
              if (!f) return null;
              const siteKeyMatch = f.match(/[?&]k=([^&]+)/) ||
                                   f.match(/[?&]sitekey=([^&]+)/);
              const kind = f.includes('challenges.cloudflare.com') ? 'turnstile' :
                           f.includes('hcaptcha') ? 'hcaptcha' : 'recaptcha_v2';
              return { kind, sitekey: siteKeyMatch ? siteKeyMatch[1] : null };
            }"""
        )
    except Exception:  # noqa: BLE001
        return False
    if not iframe_info or not iframe_info.get("sitekey"):
        return False
    kind = iframe_info["kind"]
    sitekey = iframe_info["sitekey"]
    _log(f"captcha detected: {kind} sitekey={sitekey[:8]}…")
    try:
        token = solver.solve(kind, site_key=sitekey, url=url)
    except Exception as e:  # noqa: BLE001
        _log(f"captcha solver failed: {type(e).__name__}: {e}")
        return False
    try:
        # Inject the token into the standard response fields so the page's
        # submit handler can use it. Works for most sites.
        page.evaluate(
            """(token) => {
              document.querySelectorAll(
                '[name=g-recaptcha-response], [name=h-captcha-response], [name=cf-turnstile-response]'
              ).forEach(el => { el.value = token; });
              if (window.turnstile && window.turnstile.execute) { /* noop */ }
            }""",
            token,
        )
        _log(f"captcha {kind} solved + token injected")
        return True
    except Exception as e:  # noqa: BLE001
        _log(f"captcha token injection failed: {e}")
        return False


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


def _ratelimit_path() -> str:
    return os.environ.get(
        "LAUNCHER_RATELIMIT",
        str(Path.home() / ".camoufox" / "launcher" / "ratelimit.json"),
    )


def _profile_user_data_dir(profile_id: str) -> Path:
    """Persistent per-profile storage for cookies/localStorage/cache.

    Keeps Cloudflare clearance + logged-in sessions across launches.
    """
    return Path.home() / ".camoufox" / "launcher" / "user_data" / profile_id


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
    ap.add_argument("--warmup", action="store_true",
                    help="visit 2-3 mainstream sites before --url")
    ap.add_argument("--auto-refresh", type=float, default=0.0, metavar="SECONDS",
                    help="reload the target URL every N±20% seconds (0 disables)")
    ap.add_argument("--persistent", action="store_true",
                    help="use a persistent user_data_dir for cookies/storage")
    ap.add_argument("--queue-monitor", action="store_true",
                    help="detect queue pages and notify via webhook when near front")
    ap.add_argument("--rate-limit", type=int, default=0, metavar="PER_MIN",
                    help="per-host rate cap (0 = use global default)")
    ap.add_argument("--auto-solve-captcha", action="store_true",
                    help="auto-solve Turnstile/reCAPTCHA/hCaptcha using configured providers")
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

    _log(
        f"session={args.session_id} profile={profile.name} "
        f"proxy={proxy.label if proxy else '-'} url={args.url or '-'} "
        f"headless={args.headless} warmup={args.warmup} "
        f"auto_refresh={args.auto_refresh} persistent={args.persistent}"
    )

    config = fpgen.to_camoufox_config(profile)
    proxy_kwarg = proxypool.to_camoufox_proxy(proxy) if proxy else None

    _mark_running(args.session_id)

    try:
        from camoufox.sync_api import Camoufox
    except ImportError as e:
        _log(f"FATAL: camoufox not importable (run in Camoufox env): {e}")
        return 2

    launch_kwargs = {"config": config, "headless": args.headless}
    if proxy_kwarg is not None:
        launch_kwargs["proxy"] = proxy_kwarg
    if args.persistent:
        data_dir = _profile_user_data_dir(args.profile_id)
        data_dir.mkdir(parents=True, exist_ok=True)
        launch_kwargs["persistent_context"] = True
        launch_kwargs["user_data_dir"] = str(data_dir)

    limiter = RateLimiter(_ratelimit_path())
    if args.rate_limit and args.url:
        limiter.set_limit(
            RateLimiter._host(args.url), args.rate_limit,  # noqa: SLF001 — internal helper
        )

    exit_code = 0
    try:
        with Camoufox(**launch_kwargs) as browser:
            # persistent_context returns a BrowserContext directly, not Browser.
            if args.persistent:
                page = browser.new_page() if hasattr(browser, "new_page") else browser.pages[0]
            else:
                page = browser.new_page()

            if args.warmup:
                _log("warmup start")
                warmup_mod.warmup(page, seed=hash(args.session_id) & 0xFFFF)
                _log("warmup done")

            solver = _maybe_build_solver() if args.auto_solve_captcha else None
            if args.auto_solve_captcha and solver is None:
                _log("auto-solve-captcha requested but no providers configured; skipping")

            if args.url:
                _goto_with_retry(page, args.url, limiter)
                if solver:
                    _detect_and_solve_captcha(page, solver, args.url)

            _log("browser ready; waiting for stop signal")

            if args.queue_monitor:
                # Lazy import so the runner still works without the module.
                try:
                    from queuepool import detect_queue
                except ImportError:
                    _log("queue-monitor requested but queuepool not installed")
                    detect_queue = None
            else:
                detect_queue = None

            _main_loop(
                page,
                args,
                limiter,
                detect_queue=detect_queue,
            )
            _log("stop signal received; closing browser")
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL: {type(e).__name__}: {e}")
        _log(traceback.format_exc())
        webhook_notify(
            f"Session **{profile.name}** crashed: `{type(e).__name__}: {e}`",
            level="error",
        )
        exit_code = 1

    _log("session exited cleanly" if exit_code == 0 else f"session exited with code {exit_code}")
    return exit_code


def _goto_with_retry(page, url: str, limiter: RateLimiter) -> None:
    """Navigate with rate limit + retry on transient failures."""
    try:
        waited = limiter.check_and_record(url, wait=True, max_wait_seconds=30.0)
        if waited > 0:
            _log(f"rate-limited, waited {waited:.1f}s before {url}")
    except RateLimitExceeded as e:
        _log(f"rate limit giving up: {e}")
        raise

    def _do():
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")

    retry(
        _do,
        spec=RetrySpec(max_attempts=3, initial_delay=3.0, factor=2.0, max_delay=20.0),
        on_error=lambda attempt, e: _log(f"goto attempt {attempt+1} failed: {type(e).__name__}: {e}"),
    )


def _main_loop(page, args, limiter: RateLimiter, detect_queue=None) -> None:
    """Sleep loop with optional auto-refresh + queue monitor."""
    refresh_interval = args.auto_refresh
    next_refresh = time.time() + _jitter(refresh_interval) if refresh_interval > 0 else None
    queue_notified = False
    last_queue_position = None

    while not _STOP:
        time.sleep(0.25)
        now = time.time()

        if next_refresh and now >= next_refresh:
            try:
                limiter.check_and_record(page.url, wait=False)
                page.reload(wait_until="domcontentloaded", timeout=15_000)
                _log(f"auto-refreshed {page.url}")
            except RateLimitExceeded as e:
                _log(f"auto-refresh skipped (rate limit): {e}")
            except Exception as e:  # noqa: BLE001
                _log(f"auto-refresh error: {type(e).__name__}: {e}")
            next_refresh = now + _jitter(refresh_interval)

        if detect_queue and int(now) % 10 == 0:
            try:
                html = page.content()
                state = detect_queue(page.url, html)
                if state and state.position is not None:
                    if last_queue_position != state.position:
                        _log(f"queue: kind={state.kind.value} position={state.position}")
                    last_queue_position = state.position
                    if not queue_notified and state.position <= 10:
                        webhook_notify(
                            f"🎯 Front of queue on {page.url} (position={state.position})",
                            level="success",
                        )
                        queue_notified = True
            except Exception:  # noqa: BLE001
                pass


def _jitter(seconds: float, pct: float = 0.2) -> float:
    if seconds <= 0:
        return seconds
    j = random.uniform(-pct, pct)
    return max(1.0, seconds * (1 + j))


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
