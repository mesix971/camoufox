"""
Command handlers. Each function takes a dict of already-validated args and
returns a JSON-serializable dict. They are called by __main__.py.

Kept as plain functions (no OOP) so the JSON CLI maps 1:1 to callable names
and each command can be unit-tested in isolation.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import json

import fpgen
import proxypool

from launcher.bridge import metrics as metrics_mod
from launcher.bridge import webhook as webhook_mod
from launcher.bridge.ratelimit import RateLimiter
from launcher.bridge.sessions import SessionManager


# --- path helpers (env-overridable for tests and multi-tenant setups) ---

def profile_store_path() -> str:
    return os.environ.get("FPGEN_STORE", str(Path.home() / ".camoufox" / "fpgen"))


def proxy_store_path() -> str:
    return os.environ.get("PROXYPOOL_STORE", str(Path.home() / ".camoufox" / "proxypool"))


def sessions_root() -> str:
    return os.environ.get("LAUNCHER_SESSIONS", str(Path.home() / ".camoufox" / "launcher" / "sessions"))


def _profile_store() -> fpgen.ProfileStore:
    return fpgen.ProfileStore(profile_store_path())


def _proxy_store() -> proxypool.ProxyStore:
    return proxypool.ProxyStore(proxy_store_path())


def _session_mgr() -> SessionManager:
    return SessionManager(sessions_root())


# --- profile commands ---

def list_profiles(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _profile_store()
    items = store.list(tag=args.get("tag"), os=args.get("os"))
    return {"profiles": items}


def show_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _profile_store()
    p = store.load(args["id"])
    return {
        "profile": _profile_to_dict(p),
        "config": fpgen.to_camoufox_config(p),
    }


def new_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    tags = args.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split(",") if t]
    p = fpgen.generate(
        archetype=args.get("archetype"),
        os=args.get("os"),
        locale=args.get("locale"),
        firefox_version=args.get("firefox_version"),
        name=args.get("name"),
        tags=tags,
        seed=args.get("seed"),
    )
    if args.get("save", True):
        _profile_store().save(p)
    return {"profile": _profile_to_dict(p)}


def delete_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    _profile_store().delete(args["id"])
    return {"deleted": args["id"]}


def clone_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    """Duplicate a profile, optionally overriding a few fields.

    args: id (required), name (optional new name), reseed (bool, re-roll random
    sub-fields like tls session_id), tags (list of extra tags).
    """
    from dataclasses import asdict as _asdict
    import uuid
    store = _profile_store()
    src = store.load(args["id"])
    data = _asdict(src)
    data["id"] = uuid.uuid4().hex[:12]
    data["name"] = args.get("name") or f"{src.name}-clone"
    from datetime import datetime, timezone
    data["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["last_used_at"] = None
    data["use_count"] = 0
    if args.get("tags"):
        extras = args["tags"] if isinstance(args["tags"], list) else [args["tags"]]
        data["tags"] = list({*(data.get("tags") or []), *extras})
    cloned = fpgen.Profile.from_json(json.dumps(data))
    store.save(cloned)
    return {"profile": _profile_to_dict(cloned)}


def update_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    """Patch a profile with a dict of field updates. Only allows fields that
    exist on Profile; unknown keys raise KeyError.
    """
    from dataclasses import fields as _fields
    store = _profile_store()
    p = store.load(args["id"])
    allowed = {f.name for f in _fields(fpgen.Profile)} - {"id", "created_at"}
    updates = args.get("updates") or {}
    if not isinstance(updates, dict):
        raise ValueError("updates must be an object")
    for k, v in updates.items():
        if k not in allowed:
            raise KeyError(f"cannot update field: {k}")
        setattr(p, k, v)
    store.save(p)
    return {"profile": _profile_to_dict(p)}


def export_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return the full profile as JSON — user pipes/copies to disk."""
    from dataclasses import asdict as _asdict
    p = _profile_store().load(args["id"])
    return {"profile": _asdict(p), "export_version": 1}


def import_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    """Import a profile from a JSON dict (as produced by export-profile).

    args: profile (required, dict), rename (bool: generate a fresh id+name to
    avoid clashing with the source).
    """
    import uuid
    data = args["profile"]
    if not isinstance(data, dict):
        raise ValueError("profile must be an object")
    if args.get("rename", True):
        data = dict(data)
        data["id"] = uuid.uuid4().hex[:12]
        if "name" in data:
            data["name"] = f"{data['name']}-imported"
    p = fpgen.Profile.from_json(json.dumps(data))
    _profile_store().save(p)
    return {"profile": _profile_to_dict(p)}


def list_archetypes(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "archetypes": [
            {"id": a.id, "os": a.os, "os_version": a.os_version,
             "weight": a.weight, "font_set_id": a.font_set_id, "gpu_tier": a.gpu_tier}
            for a in fpgen.ARCHETYPES
        ]
    }


# --- proxy commands ---

def list_proxies(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _proxy_store()
    items = store.list(
        status=args.get("status"),
        provider=args.get("provider"),
        tag=args.get("tag"),
        country=args.get("country"),
    )
    return {"proxies": items}


def show_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    p = _proxy_store().load(args["id"])
    return {
        "proxy": asdict(p),
        "camoufox": proxypool.to_camoufox_proxy(p),
    }


def add_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    line = args["line"]
    label = args.get("label")
    tags = args.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split(",") if t]
    p = proxypool.parse(line, label=label, tags=tags)
    store = _proxy_store()
    if not args.get("allow_duplicate"):
        existing = store.find_by_signature(p.host, p.port, p.username, p.password)
        if existing:
            return {"proxy": asdict(existing), "duplicate": True}
    store.save(p)
    return {"proxy": asdict(p), "duplicate": False}


def import_proxies(args: Dict[str, Any]) -> Dict[str, Any]:
    text = args["text"]
    store = _proxy_store()
    parsed, errors = proxypool.parse_many(text, label_prefix=args.get("label_prefix"))
    saved, duplicates = 0, 0
    for p in parsed:
        if args.get("tag"):
            p.tags = list({*p.tags, *args["tag"].split(",")})
        if not args.get("allow_duplicate"):
            if store.find_by_signature(p.host, p.port, p.username, p.password):
                duplicates += 1
                continue
        store.save(p)
        saved += 1
    return {
        "parsed": len(parsed),
        "saved": saved,
        "duplicates": duplicates,
        "errors": [{"line": n, "raw": raw, "error": err} for n, raw, err in errors],
    }


def delete_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    _proxy_store().delete(args["id"])
    return {"deleted": args["id"]}


def check_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _proxy_store()
    p = store.load(args["id"])
    checker = proxypool.HealthChecker(
        workers=1,
        timeout=args.get("timeout", 15.0),
        geo_lookup=args.get("geo", True),
    )
    results = checker.check([p])
    store.save(p)
    r = results[0]
    return {"proxy": asdict(p), "result": asdict(r)}


def check_proxies_all(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _proxy_store()
    proxies = list(store.load_all(
        status=args.get("status"),
        provider=args.get("provider"),
        country=args.get("country"),
    ))
    if not proxies:
        return {"checked": 0, "ok": 0, "results": []}
    checker = proxypool.HealthChecker(
        workers=args.get("workers", 10),
        timeout=args.get("timeout", 15.0),
        geo_lookup=args.get("geo", True),
    )
    results = checker.check(proxies)
    store.save_many(proxies)
    ok = sum(1 for r in results if r.ok)
    return {
        "checked": len(results),
        "ok": ok,
        "results": [asdict(r) for r in results],
    }


def rotate_proxy_session(args: Dict[str, Any]) -> Dict[str, Any]:
    store = _proxy_store()
    p = store.load(args["id"])
    new_p = proxypool.iproyal.rotate_session(
        p,
        new_session_id=args.get("session_id"),
        lifetime=args.get("lifetime"),
        country=args.get("country"),
        city=args.get("city"),
    )
    if args.get("save_as_new"):
        store.save(new_p)
    else:
        store.delete(p.id)
        new_p.id = p.id
        store.save(new_p)
    return {"proxy": asdict(new_p)}


# --- session commands ---

def list_sessions(args: Dict[str, Any]) -> Dict[str, Any]:
    mgr = _session_mgr()
    include_metrics = bool(args.get("metrics", False))
    items = []
    for s in mgr.list():
        d = mgr.as_dict(s)
        if include_metrics and s.pid > 0:
            d["metrics"] = metrics_mod.process_metrics(s.pid)
        items.append(d)
    out = {"sessions": items}
    if include_metrics:
        out["system"] = metrics_mod.system_metrics()
        out["psutil_available"] = metrics_mod.has_psutil()
    return out


def session_metrics(args: Dict[str, Any]) -> Dict[str, Any]:
    """Live CPU/RAM per session (requires psutil)."""
    mgr = _session_mgr()
    sessions = mgr.list()
    pids = [s.pid for s in sessions if s.pid > 0]
    by_pid = metrics_mod.metrics_for_sessions(pids)
    return {
        "psutil_available": metrics_mod.has_psutil(),
        "system": metrics_mod.system_metrics(),
        "sessions": [
            {"id": s.id, "pid": s.pid, "status": s.status, **by_pid.get(s.pid, {})}
            for s in sessions
        ],
    }


def launch_session(args: Dict[str, Any]) -> Dict[str, Any]:
    mgr = _session_mgr()
    # Validate referenced profile + proxy exist before spawning.
    _profile_store().load(args["profile_id"])
    if args.get("proxy_id"):
        _proxy_store().load(args["proxy_id"])
    s = mgr.spawn(
        profile_id=args["profile_id"],
        proxy_id=args.get("proxy_id"),
        url=args.get("url"),
        headless=bool(args.get("headless", False)),
        warmup=bool(args.get("warmup", False)),
        auto_refresh=float(args.get("auto_refresh", 0) or 0),
        persistent=bool(args.get("persistent", False)),
        queue_monitor=bool(args.get("queue_monitor", False)),
        rate_limit=int(args.get("rate_limit", 0) or 0),
        auto_solve_captcha=bool(args.get("auto_solve_captcha", False)),
        humanlike=bool(args.get("humanlike", False)),
        run_macro=args.get("run_macro"),
        record_macro=args.get("record_macro"),
    )
    return {"session": mgr.as_dict(s)}


def reopen_session(args: Dict[str, Any]) -> Dict[str, Any]:
    """Relaunch a session using the old session's profile/proxy/url + persistent=True.

    The persistent flag makes the new session pick up the previous session's
    cookies/storage (saved under ~/.camoufox/launcher/user_data/<profile_id>/),
    so the user sees "their" tabs, logged-in sites, etc. — within the limits
    of what Firefox persists in a user profile.
    """
    mgr = _session_mgr()
    old = mgr.load(args["id"])
    s = mgr.spawn(
        profile_id=old.profile_id,
        proxy_id=old.proxy_id,
        url=args.get("url") or old.url,
        headless=bool(args.get("headless", old.headless)),
        warmup=bool(args.get("warmup", False)),
        auto_refresh=float(args.get("auto_refresh", 0) or 0),
        persistent=True,  # key: restore the user's cookies
        queue_monitor=bool(args.get("queue_monitor", False)),
        rate_limit=int(args.get("rate_limit", 0) or 0),
        auto_solve_captcha=bool(args.get("auto_solve_captcha", False)),
        humanlike=bool(args.get("humanlike", False)),
    )
    return {"session": mgr.as_dict(s), "previous_id": args["id"]}


def kill_session(args: Dict[str, Any]) -> Dict[str, Any]:
    mgr = _session_mgr()
    s = mgr.kill(args["id"], timeout=args.get("timeout", 5.0))
    return {"session": mgr.as_dict(s)}


def kill_all_sessions(args: Dict[str, Any]) -> Dict[str, Any]:
    n = _session_mgr().kill_all()
    return {"killed": n}


def prune_sessions(args: Dict[str, Any]) -> Dict[str, Any]:
    n = _session_mgr().prune_stopped()
    return {"pruned": n}


def session_log(args: Dict[str, Any]) -> Dict[str, Any]:
    mgr = _session_mgr()
    text = mgr.tail_log(args["id"], lines=args.get("lines", 200))
    return {"id": args["id"], "log": text}


# --- profile <-> proxy binding ---

def bind_profile_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    """Write profile.proxy_id = proxy_id (or None to unbind). Validates both exist."""
    pstore = _profile_store()
    profile = pstore.load(args["profile_id"])
    proxy_id = args.get("proxy_id")
    if proxy_id:
        _proxy_store().load(proxy_id)  # validate existence
        profile.proxy_id = proxy_id
    else:
        profile.proxy_id = None
    pstore.save(profile)
    return {"profile_id": profile.id, "proxy_id": profile.proxy_id}


# --- batch launch ---

def batch_launch_session(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Launch N sessions at once. Each profile can be paired with a proxy via
    one of three strategies:
      - 'bound'     : use each profile's profile.proxy_id (skip if unset)
      - 'round-robin': cycle through the proxy pool
      - 'fixed'     : all sessions get the same proxy_id
      - 'none'      : no proxy

    args:
      profile_ids: list[str]
      strategy: 'bound'|'round-robin'|'fixed'|'none'  (default: 'bound')
      proxy_id: str  (required if strategy=='fixed')
      proxy_filter: dict (optional: {provider, country, tag, status} passed to proxypool.list)
      url: str
      headless: bool
    """
    mgr = _session_mgr()
    pstore = _profile_store()
    xstore = _proxy_store()

    profile_ids = args.get("profile_ids") or []
    if not profile_ids:
        raise ValueError("profile_ids must be a non-empty list")
    strategy = args.get("strategy", "bound")
    url = args.get("url")
    headless = bool(args.get("headless", False))

    tile_rects = None
    if args.get("tile"):
        from launcher.bridge.screen import primary_monitor_size
        from launcher.bridge.tiling import compute_tiles, parse_grid
        grid = parse_grid(args.get("grid") or "auto")
        sw, sh = primary_monitor_size()
        tile_rects = compute_tiles(len(profile_ids), sw, sh, grid=grid)

    proxy_pool: list = []
    if strategy == "round-robin":
        filt = args.get("proxy_filter") or {}
        proxy_pool = xstore.list(
            status=filt.get("status", "active"),
            provider=filt.get("provider"),
            tag=filt.get("tag"),
            country=filt.get("country"),
        )
        if not proxy_pool:
            raise ValueError("round-robin needs at least one matching proxy")
    elif strategy == "fixed":
        xstore.load(args["proxy_id"])  # validate

    spawned = []
    failures = []
    for idx, pid in enumerate(profile_ids):
        try:
            profile = pstore.load(pid)
        except KeyError as e:
            failures.append({"profile_id": pid, "error": str(e)})
            continue

        proxy_id = None
        if strategy == "bound":
            proxy_id = profile.proxy_id
        elif strategy == "round-robin":
            proxy_id = proxy_pool[idx % len(proxy_pool)]["id"]
        elif strategy == "fixed":
            proxy_id = args.get("proxy_id")

        try:
            s = mgr.spawn(
                profile_id=pid,
                proxy_id=proxy_id,
                url=url,
                headless=headless,
                warmup=bool(args.get("warmup", False)),
                auto_refresh=float(args.get("auto_refresh", 0) or 0),
                persistent=bool(args.get("persistent", False)),
                queue_monitor=bool(args.get("queue_monitor", False)),
                rate_limit=int(args.get("rate_limit", 0) or 0),
                auto_solve_captcha=bool(args.get("auto_solve_captcha", False)),
                humanlike=bool(args.get("humanlike", False)),
                run_macro=args.get("run_macro"),
                tile=tile_rects[idx] if tile_rects and idx < len(tile_rects) else None,
            )
            spawned.append(mgr.as_dict(s))
        except Exception as e:  # noqa: BLE001 — batch must not bail on one failure
            failures.append({"profile_id": pid, "error": f"{type(e).__name__}: {e}"})

    return {"spawned": spawned, "failures": failures, "count": len(spawned)}


# --- dashboard summary ---

def dashboard_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate metrics for the dashboard tab."""
    pstore = _profile_store()
    xstore = _proxy_store()
    mgr = _session_mgr()

    profiles = pstore.list()
    proxies = xstore.list()
    sessions = mgr.list()

    proxies_by_status: Dict[str, int] = {}
    for p in proxies:
        proxies_by_status[p["status"]] = proxies_by_status.get(p["status"], 0) + 1

    sessions_by_status: Dict[str, int] = {}
    for s in sessions:
        sessions_by_status[s.status] = sessions_by_status.get(s.status, 0) + 1

    profiles_by_os: Dict[str, int] = {}
    for p in profiles:
        profiles_by_os[p.get("os", "?")] = profiles_by_os.get(p.get("os", "?"), 0) + 1

    bound_profiles = sum(1 for p in profiles if p.get("proxy_id"))

    return {
        "profiles": {
            "total": len(profiles),
            "by_os": profiles_by_os,
            "bound_to_proxy": bound_profiles,
        },
        "proxies": {
            "total": len(proxies),
            "by_status": proxies_by_status,
        },
        "sessions": {
            "total": len(sessions),
            "by_status": sessions_by_status,
            "running": sessions_by_status.get("running", 0) + sessions_by_status.get("starting", 0),
        },
    }


# --- webhook / settings ---

def set_webhook(args: Dict[str, Any]) -> Dict[str, Any]:
    url = args["url"]
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)://")
    webhook_mod.set_webhook(url)
    return {"ok": True}


def get_webhook(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"url": webhook_mod.get_webhook()}


def test_webhook(args: Dict[str, Any]) -> Dict[str, Any]:
    ok = webhook_mod.notify(
        args.get("content", "Camoufox webhook test — it works."),
        level=args.get("level", "info"),
    )
    return {"delivered": ok}


def ratelimit_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    path = os.environ.get(
        "LAUNCHER_RATELIMIT",
        str(Path.home() / ".camoufox" / "launcher" / "ratelimit.json"),
    )
    return {"hosts": RateLimiter(path).stats(args.get("host"))}


def ratelimit_set(args: Dict[str, Any]) -> Dict[str, Any]:
    path = os.environ.get(
        "LAUNCHER_RATELIMIT",
        str(Path.home() / ".camoufox" / "launcher" / "ratelimit.json"),
    )
    RateLimiter(path).set_limit(args["host"], int(args["max_per_minute"]))
    return {"ok": True, "host": args["host"], "max_per_minute": int(args["max_per_minute"])}


# --- macros ---

def _macros_store():
    import actions
    return actions.ScriptStore(
        os.environ.get(
            "ACTIONS_STORE",
            str(Path.home() / ".camoufox" / "macros"),
        )
    )


def list_macros(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"macros": _macros_store().list()}


def show_macro(args: Dict[str, Any]) -> Dict[str, Any]:
    script = _macros_store().load(args["name"])
    return {
        "name": script.name,
        "actions": script.actions,
        "metadata": getattr(script, "metadata", {}),
    }


def save_macro(args: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a macro from a JSON blob. Args: name, actions (list), metadata (dict)."""
    import actions as actions_mod
    script = actions_mod.ActionScript(
        name=args["name"],
        actions=args.get("actions") or [],
        metadata=args.get("metadata") or {},
    )
    errors = script.validate()
    if errors:
        raise ValueError(f"invalid script: {'; '.join(errors)}")
    _macros_store().save(script)
    return {"saved": args["name"], "action_count": len(script.actions)}


def delete_macro(args: Dict[str, Any]) -> Dict[str, Any]:
    _macros_store().delete(args["name"])
    return {"deleted": args["name"]}


# --- creepjs scoring ---

def score_profile_creepjs(args: Dict[str, Any]) -> Dict[str, Any]:
    """Launch a short-lived Camoufox session to score a profile on creepjs.com.

    Runs in-process (not via session_runner) since we need to use the scored
    page synchronously and close it; don't pollute the sessions list.
    """
    import creepjsscore
    from dataclasses import asdict as _asdict
    profile_id = args["profile_id"]
    profile = _profile_store().load(profile_id)
    try:
        from camoufox.sync_api import Camoufox
    except ImportError as e:
        raise RuntimeError(f"camoufox not importable: {e}")
    config = fpgen.to_camoufox_config(profile)
    scorer = creepjsscore.Scorer(
        pass_fp_threshold=float(args.get("pass_fp_threshold", 75.0)),
        pass_trust_threshold=float(args.get("pass_trust_threshold", 70.0)),
    )
    with Camoufox(config=config, headless=bool(args.get("headless", True))) as browser:
        page = browser.new_page()
        result = scorer.score(page, profile_id)
    score_dict = _asdict(result)
    # Attach to profile metadata if accepted.
    if args.get("save_to_profile") and result.passed:
        if not profile.tags:
            profile.tags = []
        if "creepjs-passed" not in profile.tags:
            profile.tags.append("creepjs-passed")
        _profile_store().save(profile)
    return {"score": score_dict}


# --- task queue ---

def _task_queue():
    import taskqueue as tq
    return tq.TaskQueue(
        os.environ.get(
            "TASKQUEUE_STORE",
            str(Path.home() / ".camoufox" / "launcher" / "tasks"),
        )
    )


def enqueue_task(args: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime, timezone, timedelta
    q = _task_queue()
    action = args["action"]
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    scheduled_at = None
    if args.get("delay_seconds"):
        scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=float(args["delay_seconds"]))
    elif args.get("run_at"):
        scheduled_at = datetime.fromisoformat(args["run_at"])
    task = q.enqueue(action=action, scheduled_at=scheduled_at, tags=args.get("tags") or [])
    return {"task": asdict(task)}


def list_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
    q = _task_queue()
    items = [asdict(t) for t in q.list(status=args.get("status"), tag=args.get("tag"))]
    return {"tasks": items, "stats": q.stats()}


def delete_task(args: Dict[str, Any]) -> Dict[str, Any]:
    _task_queue().delete(args["id"])
    return {"deleted": args["id"]}


# --- helpers ---

def _profile_to_dict(p: fpgen.Profile) -> Dict[str, Any]:
    from dataclasses import asdict as _asdict
    return _asdict(p)


# --- command registry ---

COMMANDS = {
    "list-profiles": list_profiles,
    "show-profile": show_profile,
    "new-profile": new_profile,
    "delete-profile": delete_profile,
    "clone-profile": clone_profile,
    "update-profile": update_profile,
    "export-profile": export_profile,
    "import-profile": import_profile,
    "list-archetypes": list_archetypes,

    "list-proxies": list_proxies,
    "show-proxy": show_proxy,
    "add-proxy": add_proxy,
    "import-proxies": import_proxies,
    "delete-proxy": delete_proxy,
    "check-proxy": check_proxy,
    "check-proxies-all": check_proxies_all,
    "rotate-proxy-session": rotate_proxy_session,

    "list-sessions": list_sessions,
    "session-metrics": session_metrics,
    "launch-session": launch_session,
    "reopen-session": reopen_session,
    "kill-session": kill_session,
    "kill-all-sessions": kill_all_sessions,
    "prune-sessions": prune_sessions,
    "session-log": session_log,
    "batch-launch-session": batch_launch_session,

    "bind-profile-proxy": bind_profile_proxy,

    "dashboard-summary": dashboard_summary,

    "set-webhook": set_webhook,
    "get-webhook": get_webhook,
    "test-webhook": test_webhook,
    "ratelimit-stats": ratelimit_stats,
    "ratelimit-set": ratelimit_set,

    "enqueue-task": enqueue_task,
    "list-tasks": list_tasks,
    "delete-task": delete_task,

    "score-profile-creepjs": score_profile_creepjs,

    "list-macros": list_macros,
    "show-macro": show_macro,
    "save-macro": save_macro,
    "delete-macro": delete_macro,
}
