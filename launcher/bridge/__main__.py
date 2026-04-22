"""
JSON CLI dispatcher.

Invocation:
    python -m launcher.bridge <cmd> [--arg key=value ...] [--json-stdin]
    python -m launcher.bridge <cmd> '{"key": "value", ...}'

Result:
    exactly one JSON object on stdout; exit code 0 on success, non-zero on error.

Error shape: {"error": {"type": "...", "message": "...", "traceback": "..."}}
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Dict, List, Optional

from launcher.bridge.commands import COMMANDS


def _parse_args(argv: List[str]) -> Dict[str, Any]:
    """
    Accepts either a positional JSON blob or a mix of --key=value / --key value /
    --flag args. Values are JSON-parsed when possible (so --seed 42 yields int,
    --headless true yields bool, etc.) and fall back to string otherwise.
    """
    if not argv:
        return {}

    # JSON blob form
    first = argv[0]
    if first.startswith("{"):
        return json.loads(first)

    # --stdin reads one JSON object from stdin
    if first == "--stdin":
        return json.loads(sys.stdin.read())

    # --key=value / --key value / --flag
    args: Dict[str, Any] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            raise SystemExit(f"unexpected token: {tok!r}; expected --key value or a JSON blob")
        key = tok[2:]
        value: Any
        if "=" in key:
            key, raw = key.split("=", 1)
            value = _coerce(raw)
            i += 1
        elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            value = _coerce(argv[i + 1])
            i += 2
        else:
            value = True
            i += 1
        args[key.replace("-", "_")] = value
    return args


def _coerce(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _err(exc: BaseException) -> Dict[str, Any]:
    return {
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(json.dumps({"commands": sorted(COMMANDS.keys())}, indent=2))
        return 0

    cmd = argv[0]
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(json.dumps({"error": {"type": "UnknownCommand",
                                    "message": f"no such command: {cmd}",
                                    "available": sorted(COMMANDS.keys())}}))
        return 2

    try:
        args = _parse_args(argv[1:])
        result = handler(args)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except KeyError as e:
        print(json.dumps(_err(e)))
        return 2
    except Exception as e:  # noqa: BLE001 — bridge exit shape must be uniform
        print(json.dumps(_err(e)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
