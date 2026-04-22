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

import fpgen
import proxypool

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
        existing = store.find_by_host_port(p.host, p.port)
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
            if store.find_by_host_port(p.host, p.port):
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
    return {"sessions": [mgr.as_dict(s) for s in mgr.list()]}


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
    )
    return {"session": mgr.as_dict(s)}


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
    "launch-session": launch_session,
    "kill-session": kill_session,
    "kill-all-sessions": kill_all_sessions,
    "prune-sessions": prune_sessions,
    "session-log": session_log,
}
