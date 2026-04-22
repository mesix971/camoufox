"""
CLI entrypoint.

    python -m proxypool add <line>            # one proxy, any supported format
    python -m proxypool import <file>         # one proxy per line, "-" for stdin
    python -m proxypool list [--status active] [--provider iproyal] [--country US] [--tag X]
    python -m proxypool show <id>
    python -m proxypool delete <id>
    python -m proxypool check <id>
    python -m proxypool check-all [--workers 10] [--no-geo]
    python -m proxypool rotate-session <id> [--session-id X] [--lifetime 10m] [--country US]
    python -m proxypool pick [--strategy lru|rr|random|fixed] [--fixed-id X] \\
                             [--provider ...] [--country ...] [--tag ...]
    python -m proxypool prune [--status dead]
    python -m proxypool rebuild-index
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from proxypool import (
    Fixed,
    HealthChecker,
    LeastRecentlyUsed,
    NoHealthyProxy,
    Proxy,
    ProxyStatus,
    ProxyStore,
    Random,
    RoundRobin,
    iproyal,
    parse,
    parse_many,
    to_camoufox_proxy,
)


_DEFAULT_STORE = Path(os.environ.get("PROXYPOOL_STORE", str(Path.home() / ".camoufox" / "proxypool")))


def _store(args: argparse.Namespace) -> ProxyStore:
    return ProxyStore(args.store)


def _print_proxy(p: Proxy) -> None:
    print(f"id:                {p.id}")
    print(f"label:             {p.label}")
    print(f"url:               {p.to_url(include_auth=False)}")
    print(f"provider:          {p.provider}")
    print(f"auth:              {'yes' if p.username else 'no'}")
    print(f"status:            {p.status}")
    print(f"country/city:      {p.country or '-'} / {p.city or '-'}")
    print(f"sticky session:    {p.sticky_session_id or '-'} "
          f"(lifetime: {p.sticky_session_lifetime or '-'})")
    print(f"observed ip:       {p.observed_ip or '-'}")
    print(f"observed country:  {p.observed_country or '-'} / {p.observed_city or '-'}")
    print(f"latency:           {p.latency_ms} ms" if p.latency_ms is not None else "latency:           -")
    print(f"checks:            {p.success_count}/{p.total_checks} ok "
          f"(consec fail: {p.consecutive_failures})")
    print(f"usage:             count={p.use_count}  last={p.last_used_at or '-'}")
    print(f"tags:              {', '.join(p.tags) if p.tags else '-'}")


def cmd_add(args: argparse.Namespace) -> int:
    tags = args.tags.split(",") if args.tags else []
    p = parse(args.line, label=args.label, tags=tags)
    store = _store(args)
    existing = store.find_by_host_port(p.host, p.port)
    if existing and not args.allow_duplicate:
        print(f"duplicate host:port: already exists as id={existing.id} "
              f"(pass --allow-duplicate to save anyway)", file=sys.stderr)
        return 2
    store.save(p)
    _print_proxy(p)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
    proxies, errors = parse_many(text, label_prefix=args.label_prefix)
    store = _store(args)
    saved = 0
    duplicates = 0
    for p in proxies:
        if args.tag:
            p.tags = list({*p.tags, *args.tag.split(",")})
        if not args.allow_duplicate:
            existing = store.find_by_host_port(p.host, p.port)
            if existing:
                duplicates += 1
                continue
        store.save(p)
        saved += 1
    print(f"parsed: {len(proxies)}   saved: {saved}   skipped(dup): {duplicates}   errors: {len(errors)}")
    for n, line, err in errors[:10]:
        print(f"  line {n}: {err}  ({line!r})", file=sys.stderr)
    if len(errors) > 10:
        print(f"  ... ({len(errors) - 10} more errors)", file=sys.stderr)
    return 0 if not errors else 1


def cmd_list(args: argparse.Namespace) -> int:
    entries = _store(args).list(
        status=args.status, provider=args.provider, tag=args.tag, country=args.country,
    )
    if not entries:
        print("(no proxies)")
        return 0
    print(f"{'ID':14} {'STATUS':9} {'PROV':12} {'CC':3} {'LAT':>6}  {'USES':>5}  HOST:PORT              LABEL")
    for e in entries:
        lat = f"{e.get('latency_ms')}" if e.get("latency_ms") is not None else "-"
        cc = (e.get("observed_country") or e.get("country") or "-")[:3]
        host_port = f"{e.get('host','?')}:{e.get('port','?')}"
        print(f"{e['id']:14} {e.get('status','?'):9} {e.get('provider','?'):12} "
              f"{cc:3} {lat:>6}  {e.get('use_count',0):>5}  {host_port:22} {e.get('label','')}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    p = _store(args).load(args.id)
    _print_proxy(p)
    if args.camoufox:
        print("\n--- camoufox proxy dict ---")
        print(json.dumps(to_camoufox_proxy(p), indent=2))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    _store(args).delete(args.id)
    print(f"deleted {args.id}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    store = _store(args)
    p = store.load(args.id)
    checker = HealthChecker(workers=1, timeout=args.timeout, geo_lookup=not args.no_geo)
    results = checker.check([p])
    store.save(p)
    r = results[0]
    if r.ok:
        print(f"OK  {p.id}  ip={r.ip}  latency={r.latency_ms:.0f}ms  geo={r.country}/{r.city}")
        return 0
    print(f"FAIL {p.id}  error={r.error}")
    return 1


def cmd_check_all(args: argparse.Namespace) -> int:
    store = _store(args)
    proxies = list(store.load_all(provider=args.provider, country=args.country))
    if not proxies:
        print("(no proxies to check)")
        return 0
    print(f"checking {len(proxies)} proxies with {args.workers} workers ...")
    checker = HealthChecker(workers=args.workers, timeout=args.timeout, geo_lookup=not args.no_geo)
    results = checker.check(proxies)
    store.save_many(proxies)
    ok = sum(1 for r in results if r.ok)
    print(f"done: {ok}/{len(results)} ok")
    return 0 if ok == len(results) else 1


def cmd_rotate_session(args: argparse.Namespace) -> int:
    store = _store(args)
    p = store.load(args.id)
    new_p = iproyal.rotate_session(
        p,
        new_session_id=args.session_id,
        lifetime=args.lifetime,
        country=args.country,
        city=args.city,
    )
    if args.save_as_new:
        store.save(new_p)
        print(f"new proxy saved: {new_p.id}")
    else:
        store.delete(p.id)
        new_p.id = p.id
        store.save(new_p)
    _print_proxy(new_p)
    return 0


def _build_strategy(args: argparse.Namespace):
    if args.strategy == "fixed":
        if not args.fixed_id:
            print("fixed strategy needs --fixed-id", file=sys.stderr)
            sys.exit(2)
        return Fixed(args.fixed_id)
    if args.strategy == "rr":
        return RoundRobin()
    if args.strategy == "random":
        return Random()
    return LeastRecentlyUsed()


def cmd_pick(args: argparse.Namespace) -> int:
    store = _store(args)
    pool = list(store.load_all(provider=args.provider, tag=args.tag, country=args.country))
    if not pool:
        print("(no proxies in filtered pool)", file=sys.stderr)
        return 1
    strat = _build_strategy(args)
    try:
        p = strat.pick(pool)
    except NoHealthyProxy as e:
        print(f"no healthy proxy: {e}", file=sys.stderr)
        return 1
    if args.touch:
        p = store.touch(p.id)
    _print_proxy(p)
    if args.camoufox:
        print("\n--- camoufox proxy dict ---")
        print(json.dumps(to_camoufox_proxy(p), indent=2))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    n = _store(args).prune(status=args.status)
    print(f"pruned {n} proxies with status={args.status}")
    return 0


def cmd_rebuild_index(args: argparse.Namespace) -> int:
    n = _store(args).rebuild_index()
    print(f"indexed {n} proxies")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="proxypool", description="Camoufox proxy pool")
    ap.add_argument("--store", default=_DEFAULT_STORE, type=Path,
                    help=f"store dir (default: {_DEFAULT_STORE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add one proxy")
    p_add.add_argument("line", help="proxy line (URL form, host:port:u:p, etc.)")
    p_add.add_argument("--label")
    p_add.add_argument("--tags", help="comma-separated")
    p_add.add_argument("--allow-duplicate", action="store_true")
    p_add.set_defaults(func=cmd_add)

    p_imp = sub.add_parser("import", help="import a list file")
    p_imp.add_argument("file", help='file path (or "-" for stdin)')
    p_imp.add_argument("--label-prefix")
    p_imp.add_argument("--tag", help="comma-separated tags to attach to all")
    p_imp.add_argument("--allow-duplicate", action="store_true")
    p_imp.set_defaults(func=cmd_import)

    p_list = sub.add_parser("list", help="list proxies")
    p_list.add_argument("--status", choices=[s.value for s in ProxyStatus])
    p_list.add_argument("--provider")
    p_list.add_argument("--tag")
    p_list.add_argument("--country")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show one proxy")
    p_show.add_argument("id")
    p_show.add_argument("--camoufox", action="store_true", help="also print camoufox launch_options proxy dict")
    p_show.set_defaults(func=cmd_show)

    p_del = sub.add_parser("delete", help="delete a proxy")
    p_del.add_argument("id")
    p_del.set_defaults(func=cmd_delete)

    p_chk = sub.add_parser("check", help="health-check one proxy")
    p_chk.add_argument("id")
    p_chk.add_argument("--timeout", type=float, default=15.0)
    p_chk.add_argument("--no-geo", action="store_true")
    p_chk.set_defaults(func=cmd_check)

    p_chka = sub.add_parser("check-all", help="health-check every proxy in parallel")
    p_chka.add_argument("--workers", type=int, default=10)
    p_chka.add_argument("--timeout", type=float, default=15.0)
    p_chka.add_argument("--no-geo", action="store_true")
    p_chka.add_argument("--provider")
    p_chka.add_argument("--country")
    p_chka.set_defaults(func=cmd_check_all)

    p_rot = sub.add_parser("rotate-session", help="rotate iproyal sticky session")
    p_rot.add_argument("id")
    p_rot.add_argument("--session-id")
    p_rot.add_argument("--lifetime")
    p_rot.add_argument("--country")
    p_rot.add_argument("--city")
    p_rot.add_argument("--save-as-new", action="store_true",
                       help="save rotated proxy under a new id (default: overwrite)")
    p_rot.set_defaults(func=cmd_rotate_session)

    p_pick = sub.add_parser("pick", help="pick a proxy via a rotation strategy")
    p_pick.add_argument("--strategy", choices=["lru", "rr", "random", "fixed"], default="lru")
    p_pick.add_argument("--fixed-id")
    p_pick.add_argument("--provider")
    p_pick.add_argument("--tag")
    p_pick.add_argument("--country")
    p_pick.add_argument("--touch", action="store_true", help="mark proxy as used")
    p_pick.add_argument("--camoufox", action="store_true")
    p_pick.set_defaults(func=cmd_pick)

    p_prune = sub.add_parser("prune", help="delete proxies with a given status")
    p_prune.add_argument("--status", default=ProxyStatus.DEAD.value,
                         choices=[s.value for s in ProxyStatus])
    p_prune.set_defaults(func=cmd_prune)

    p_reb = sub.add_parser("rebuild-index", help="rebuild index.json from proxy files")
    p_reb.set_defaults(func=cmd_rebuild_index)

    return ap


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
