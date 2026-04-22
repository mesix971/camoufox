"""
CLI entrypoint.

    python -m fpgen new [--os windows] [--archetype <id>] [--locale fr-FR] \\
                       [--name myprofile] [--tags tag1,tag2] [--seed N] \\
                       [--no-save] [--store ~/.camoufox/fpgen]

    python -m fpgen list [--os windows] [--tag <tag>] [--store ...]
    python -m fpgen show <id> [--store ...] [--config]
    python -m fpgen delete <id> [--store ...]
    python -m fpgen rotate [--os windows] [--tag <tag>] [--exclude id1,id2]
    python -m fpgen prune --days 30
    python -m fpgen archetypes
    python -m fpgen validate <id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from fpgen import (
    ARCHETYPES,
    Profile,
    ProfileStore,
    generate,
    to_camoufox_config,
    validate,
)

_DEFAULT_STORE = Path(os.environ.get("FPGEN_STORE", str(Path.home() / ".camoufox" / "fpgen")))


def _store(args: argparse.Namespace) -> ProfileStore:
    return ProfileStore(args.store)


def _print_profile_summary(p: Profile) -> None:
    print(f"id:            {p.id}")
    print(f"name:          {p.name}")
    print(f"archetype:     {p.archetype_id}")
    print(f"os:            {p.os} {p.os_version}")
    print(f"firefox:       {p.firefox_version}")
    print(f"cpu_cores:     {p.cpu_cores}")
    print(f"screen:        {p.screen_width}x{p.screen_height} @ dpr={p.device_pixel_ratio}")
    print(f"window:        {p.outer_width}x{p.outer_height}")
    print(f"webgl:         {p.webgl_vendor} / {p.webgl_renderer}")
    print(f"locale:        {p.locale}")
    print(f"timezone:      {p.timezone}")
    print(f"geo:           {p.latitude}, {p.longitude} (±{p.geo_accuracy}m)")
    print(f"audio:         {p.audio_sample_rate}Hz / {p.audio_max_channel_count}ch")
    print(f"fonts:         {len(p.fonts)} fonts")
    print(f"battery:       {'charging' if p.battery_charging else 'discharging'} @ {p.battery_level:.0%}")
    print(f"tags:          {', '.join(p.tags) if p.tags else '(none)'}")
    print(f"proxy_id:      {p.proxy_id or '(unbound)'}")
    print(f"created_at:    {p.created_at}")
    print(f"last_used_at:  {p.last_used_at or '(never)'}")
    print(f"use_count:     {p.use_count}")


def cmd_new(args: argparse.Namespace) -> int:
    tags = args.tags.split(",") if args.tags else []
    p = generate(
        archetype=args.archetype,
        os=args.os,
        locale=args.locale,
        firefox_version=args.firefox_version,
        name=args.name,
        tags=tags,
        seed=args.seed,
    )
    if not args.no_save:
        _store(args).save(p)
    _print_profile_summary(p)
    if args.config:
        print("\n--- camoufox config ---")
        print(json.dumps(to_camoufox_config(p), indent=2, sort_keys=True))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = _store(args).list(tag=args.tag, os=args.os)
    if not entries:
        print("(no profiles)")
        return 0
    print(f"{'ID':14} {'OS':8} {'LOCALE':8} {'ARCHETYPE':28} {'LAST USED':20} {'USES':>5}  NAME")
    for e in entries:
        last = e.get("last_used_at") or "-"
        print(
            f"{e['id']:14} {e.get('os','?'):8} {e.get('locale','?'):8} "
            f"{e.get('archetype_id','?'):28} {last:20} {e.get('use_count',0):>5}  {e.get('name','')}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = _store(args)
    p = store.load(args.id)
    _print_profile_summary(p)
    if args.config:
        print("\n--- camoufox config ---")
        print(json.dumps(to_camoufox_config(p), indent=2, sort_keys=True))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    _store(args).delete(args.id)
    print(f"deleted {args.id}")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    exclude = args.exclude.split(",") if args.exclude else []
    entry = _store(args).pick_least_recently_used(os=args.os, tag=args.tag, exclude=exclude)
    if not entry:
        print("(no candidate profile)", file=sys.stderr)
        return 1
    p = _store(args).touch(entry["id"])
    _print_profile_summary(p)
    if args.config:
        print("\n--- camoufox config ---")
        print(json.dumps(to_camoufox_config(p), indent=2, sort_keys=True))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    cutoff = ProfileStore.utc_days_ago(args.days)
    n = _store(args).prune_older_than(cutoff)
    print(f"pruned {n} profiles older than {cutoff}")
    return 0


def cmd_archetypes(args: argparse.Namespace) -> int:
    for a in ARCHETYPES:
        print(f"{a.id:28} weight={a.weight:>3}  os={a.os:<8} fonts={a.font_set_id} gpu={a.gpu_tier}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    store = _store(args)
    p = store.load(args.id)
    errs = validate(p)
    if not errs:
        print(f"{args.id}: OK")
        return 0
    print(f"{args.id}: {len(errs)} invariant failures:")
    for e in errs:
        print(f"  - {e}")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fpgen", description="Camoufox fingerprint profile generator")
    ap.add_argument("--store", default=_DEFAULT_STORE, type=Path, help=f"profile store directory (default: {_DEFAULT_STORE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="generate a new profile")
    p_new.add_argument("--os", choices=["windows", "macos", "linux"])
    p_new.add_argument("--archetype")
    p_new.add_argument("--locale")
    p_new.add_argument("--firefox-version", dest="firefox_version")
    p_new.add_argument("--name")
    p_new.add_argument("--tags", help="comma-separated")
    p_new.add_argument("--seed", type=int)
    p_new.add_argument("--no-save", action="store_true")
    p_new.add_argument("--config", action="store_true", help="also print Camoufox config JSON")
    p_new.set_defaults(func=cmd_new)

    p_list = sub.add_parser("list", help="list saved profiles")
    p_list.add_argument("--os", choices=["windows", "macos", "linux"])
    p_list.add_argument("--tag")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show a profile")
    p_show.add_argument("id")
    p_show.add_argument("--config", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_del = sub.add_parser("delete", help="delete a profile")
    p_del.add_argument("id")
    p_del.set_defaults(func=cmd_delete)

    p_rot = sub.add_parser("rotate", help="pick LRU profile and mark it used")
    p_rot.add_argument("--os", choices=["windows", "macos", "linux"])
    p_rot.add_argument("--tag")
    p_rot.add_argument("--exclude", help="comma-separated ids to skip")
    p_rot.add_argument("--config", action="store_true")
    p_rot.set_defaults(func=cmd_rotate)

    p_prune = sub.add_parser("prune", help="delete profiles older than N days")
    p_prune.add_argument("--days", type=int, default=30)
    p_prune.set_defaults(func=cmd_prune)

    p_arch = sub.add_parser("archetypes", help="list known archetypes")
    p_arch.set_defaults(func=cmd_archetypes)

    p_val = sub.add_parser("validate", help="re-run consistency checks on a saved profile")
    p_val.add_argument("id")
    p_val.set_defaults(func=cmd_validate)

    return ap


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
