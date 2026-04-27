"""
Action DSL — a small, JSON-serialisable scripting language for driving a
Playwright sync ``Page``.

An action is a plain ``dict`` with a ``"type"`` key and action-specific
parameters. A script is an ordered list of such dicts. This keeps macros
trivially serialisable to disk (JSON one-liner per file) while still
expressive enough to cover the common automation primitives: navigation,
waiting, clicking, typing, selecting, scrolling, screenshotting,
cookies, JS eval, conditionals and loops.

The executor (:func:`run_script`) is deliberately duck-typed against the
``Page`` interface — anything that quacks like Playwright's sync
``Page`` works, which is what makes unit-testing with a MagicMock
trivial.

Example:

    script = ActionScript(
        name="login",
        actions=[
            {"type": "goto", "url": "https://example.com/login"},
            {"type": "fill", "selector": "#user", "value": "alice"},
            {"type": "fill", "selector": "#pw",   "value": "hunter2"},
            {"type": "click", "selector": "button[type=submit]"},
            {"type": "wait_for_url", "pattern": "/dashboard"},
        ],
    )
    results = run_script(page, script)
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Action schema
# ---------------------------------------------------------------------------

# type name -> (required keys, optional keys)
_SCHEMA: Dict[str, Dict[str, List[str]]] = {
    "goto":         {"required": ["url"],          "optional": ["wait_until", "timeout_ms"]},
    "wait":         {"required": ["seconds"],      "optional": []},
    "wait_for":     {"required": ["selector"],     "optional": ["timeout_ms", "state"]},
    "wait_for_url": {"required": ["pattern"],      "optional": ["timeout_ms"]},
    "click":        {"required": ["selector"],     "optional": ["humanlike", "button", "timeout_ms"]},
    "fill":         {"required": ["selector", "value"], "optional": ["humanlike", "timeout_ms"]},
    "type":         {"required": ["selector", "text"],  "optional": ["delay_ms", "timeout_ms"]},
    "press":        {"required": ["key"],          "optional": ["selector"]},
    "select":       {"required": ["selector", "value"], "optional": []},
    "check":        {"required": ["selector"],     "optional": []},
    "scroll":       {"required": [],               "optional": ["direction", "pixels"]},
    "screenshot":   {"required": ["path"],         "optional": ["full_page"]},
    "set_cookie":   {"required": ["name", "value", "domain"], "optional": ["path", "secure", "http_only"]},
    "eval_js":      {"required": ["code"],         "optional": []},
    "if":           {"required": ["condition"],    "optional": ["then", "else"]},
    "repeat":       {"required": ["times", "actions"], "optional": []},
    "log":          {"required": ["message"],      "optional": []},
}

ACTION_TYPES = tuple(_SCHEMA.keys())


MAX_ACTIONS_PER_RUN = 10_000
"""Hard cap on the number of actions executed in a single ``run_script`` call.

Protects against runaway loops in user-authored scripts (a typo'd
``repeat`` count, an unbounded condition, or nested loops whose product
explodes). Hitting the cap aborts the run with ``ActionLimitExceeded``
and surfaces a clear error in the result list rather than freezing
the runner indefinitely.
"""


class ActionLimitExceeded(RuntimeError):
    """Raised when a script tries to execute more than MAX_ACTIONS_PER_RUN actions."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """Thin wrapper around an action dict.

    Most of the codebase passes plain dicts around (matches the DSL's
    JSON-native shape); this class exists mainly for readability where a
    typed handle is useful.
    """

    type: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, **self.params}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Action":
        params = {k: v for k, v in d.items() if k != "type"}
        return cls(type=d["type"], params=params)


@dataclass
class ActionResult:
    """Outcome of executing a single action."""

    action: Dict[str, Any]
    ok: bool
    duration_ms: float
    error: Optional[str] = None
    output: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ActionScript:
    """A named, ordered list of action dicts plus optional metadata."""

    def __init__(
        self,
        name: str,
        actions: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.actions: List[Dict[str, Any]] = list(actions)
        self.metadata: Dict[str, Any] = dict(metadata or {})

    # --- serialisation ---

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "actions": self.actions,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionScript":
        return cls(
            name=d.get("name", ""),
            actions=list(d.get("actions", [])),
            metadata=dict(d.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, raw: str) -> "ActionScript":
        return cls.from_dict(json.loads(raw))

    # --- validation ---

    def validate(self) -> List[str]:
        """Return a list of validation errors; empty list means valid."""
        errors: List[str] = []
        if not isinstance(self.name, str) or not self.name:
            errors.append("script name must be a non-empty string")
        if not isinstance(self.actions, list):
            errors.append("actions must be a list")
            return errors
        for i, a in enumerate(self.actions):
            errors.extend(_validate_action(a, path=f"actions[{i}]"))
        return errors


def _validate_action(a: Any, path: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(a, dict):
        errors.append(f"{path}: not a dict")
        return errors
    t = a.get("type")
    if not isinstance(t, str):
        errors.append(f"{path}: missing or non-string 'type'")
        return errors
    schema = _SCHEMA.get(t)
    if schema is None:
        errors.append(f"{path}: unknown action type {t!r}")
        return errors
    for key in schema["required"]:
        if key not in a:
            errors.append(f"{path}: action {t!r} missing required key {key!r}")
    # Recurse into nested action lists.
    if t == "if":
        for branch in ("then", "else"):
            branch_actions = a.get(branch, [])
            if branch_actions and not isinstance(branch_actions, list):
                errors.append(f"{path}.{branch}: must be a list")
                continue
            for j, sub in enumerate(branch_actions or []):
                errors.extend(_validate_action(sub, path=f"{path}.{branch}[{j}]"))
    elif t == "repeat":
        sub_actions = a.get("actions", [])
        if not isinstance(sub_actions, list):
            errors.append(f"{path}.actions: must be a list")
        else:
            for j, sub in enumerate(sub_actions):
                errors.extend(_validate_action(sub, path=f"{path}.actions[{j}]"))
    return errors


# ---------------------------------------------------------------------------
# Humanlike fallback
# ---------------------------------------------------------------------------


def _resolve_humanlike(humanlike_module: Any) -> Any:
    """Return a module-like object exposing click/fill, or None."""
    if humanlike_module is not None:
        return humanlike_module
    try:
        import humanlike  # type: ignore
        return humanlike
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def run_script(
    page: Any,
    script: ActionScript,
    humanlike_module: Any = None,
) -> List[ActionResult]:
    """Execute ``script`` against ``page``.

    Each action is dispatched to its handler and timed. A failure either
    aborts the whole script (``on_error="abort"`` — the default) or is
    recorded and the next action is attempted (``on_error="continue"``).

    The ``humanlike_module`` argument lets callers pass in a specific
    humanlike implementation; when omitted we lazily try to import the
    sibling ``humanlike`` package and fall back to plain Playwright
    calls if unavailable.
    """
    hl = _resolve_humanlike(humanlike_module)
    results: List[ActionResult] = []
    abort_flag = {"abort": False, "count": 0}
    _execute(page, script.actions, results, hl, abort_flag=abort_flag)
    return results


def _execute(
    page: Any,
    actions: List[Dict[str, Any]],
    results: List[ActionResult],
    hl: Any,
    abort_flag: Dict[str, Any],
) -> None:
    for action in actions:
        if abort_flag["abort"]:
            return
        if abort_flag["count"] >= MAX_ACTIONS_PER_RUN:
            results.append(ActionResult(
                action=dict(action) if isinstance(action, dict) else {"type": None},
                ok=False,
                duration_ms=0.0,
                error=(
                    f"ActionLimitExceeded: more than {MAX_ACTIONS_PER_RUN} "
                    f"actions executed; aborting (likely an unbounded loop)"
                ),
            ))
            abort_flag["abort"] = True
            return
        abort_flag["count"] += 1
        result = _run_one(page, action, hl, results, abort_flag)
        results.append(result)
        if not result.ok and action.get("on_error", "abort") == "abort":
            abort_flag["abort"] = True
            return


def _run_one(
    page: Any,
    action: Dict[str, Any],
    hl: Any,
    results: List[ActionResult],
    abort_flag: Dict[str, Any],
) -> ActionResult:
    t = action.get("type") if isinstance(action, dict) else None
    start = time.monotonic()
    try:
        handler = _HANDLERS.get(t)
        if handler is None:
            raise ValueError(f"unknown action type: {t!r}")
        output = handler(page, action, hl, results, abort_flag)
        duration_ms = (time.monotonic() - start) * 1000.0
        return ActionResult(action=dict(action) if isinstance(action, dict) else {"type": None},
                            ok=True, duration_ms=duration_ms, output=output)
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000.0
        return ActionResult(
            action=dict(action) if isinstance(action, dict) else {"type": None},
            ok=False,
            duration_ms=duration_ms,
            error=f"{type(e).__name__}: {e}",
        )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_goto(page, a, hl, results, abort_flag):
    kwargs: Dict[str, Any] = {}
    wait_until = a.get("wait_until", "domcontentloaded")
    if wait_until:
        kwargs["wait_until"] = wait_until
    if "timeout_ms" in a:
        kwargs["timeout"] = a["timeout_ms"]
    page.goto(a["url"], **kwargs)
    return None


def _h_wait(page, a, hl, results, abort_flag):
    time.sleep(float(a["seconds"]))
    return None


def _h_wait_for(page, a, hl, results, abort_flag):
    kwargs: Dict[str, Any] = {}
    if "timeout_ms" in a:
        kwargs["timeout"] = a["timeout_ms"]
    if "state" in a:
        kwargs["state"] = a["state"]
    page.wait_for_selector(a["selector"], **kwargs)
    return None


def _h_wait_for_url(page, a, hl, results, abort_flag):
    kwargs: Dict[str, Any] = {}
    if "timeout_ms" in a:
        kwargs["timeout"] = a["timeout_ms"]
    page.wait_for_url(a["pattern"], **kwargs)
    return None


def _h_click(page, a, hl, results, abort_flag):
    selector = a["selector"]
    if a.get("humanlike") and hl is not None and hasattr(hl, "click"):
        hl.click(page, selector)
    else:
        kwargs: Dict[str, Any] = {}
        if "button" in a:
            kwargs["button"] = a["button"]
        if "timeout_ms" in a:
            kwargs["timeout"] = a["timeout_ms"]
        page.click(selector, **kwargs)
    return None


def _h_fill(page, a, hl, results, abort_flag):
    selector = a["selector"]
    value = a["value"]
    if a.get("humanlike") and hl is not None and hasattr(hl, "fill"):
        hl.fill(page, selector, value)
    else:
        kwargs: Dict[str, Any] = {}
        if "timeout_ms" in a:
            kwargs["timeout"] = a["timeout_ms"]
        page.fill(selector, value, **kwargs)
    return None


def _h_type(page, a, hl, results, abort_flag):
    kwargs: Dict[str, Any] = {}
    if "delay_ms" in a:
        kwargs["delay"] = a["delay_ms"]
    if "timeout_ms" in a:
        kwargs["timeout"] = a["timeout_ms"]
    page.type(a["selector"], a["text"], **kwargs)
    return None


def _h_press(page, a, hl, results, abort_flag):
    if a.get("selector"):
        page.press(a["selector"], a["key"])
    else:
        page.keyboard.press(a["key"])
    return None


def _h_select(page, a, hl, results, abort_flag):
    page.select_option(a["selector"], a["value"])
    return None


def _h_check(page, a, hl, results, abort_flag):
    page.check(a["selector"])
    return None


def _h_scroll(page, a, hl, results, abort_flag):
    direction = a.get("direction", "down")
    pixels = int(a.get("pixels", 500))
    dy = pixels if direction == "down" else -pixels if direction == "up" else 0
    dx = pixels if direction == "right" else -pixels if direction == "left" else 0
    page.mouse.wheel(dx, dy)
    return None


def _h_screenshot(page, a, hl, results, abort_flag):
    kwargs: Dict[str, Any] = {"path": a["path"]}
    if "full_page" in a:
        kwargs["full_page"] = bool(a["full_page"])
    page.screenshot(**kwargs)
    return {"path": a["path"]}


def _h_set_cookie(page, a, hl, results, abort_flag):
    cookie: Dict[str, Any] = {
        "name": a["name"],
        "value": a["value"],
        "domain": a["domain"],
        "path": a.get("path", "/"),
    }
    if "secure" in a:
        cookie["secure"] = bool(a["secure"])
    if "http_only" in a:
        cookie["httpOnly"] = bool(a["http_only"])
    page.context.add_cookies([cookie])
    return None


def _h_eval_js(page, a, hl, results, abort_flag):
    return {"value": page.evaluate(a["code"])}


def _h_if(page, a, hl, results, abort_flag):
    cond = a.get("condition") or {}
    selector = cond.get("selector_exists")
    truthy = False
    if selector:
        try:
            el = page.query_selector(selector)
            truthy = el is not None
        except Exception:
            truthy = False
    elif "js" in cond:
        truthy = bool(page.evaluate(cond["js"]))
    branch = a.get("then", []) if truthy else a.get("else", [])
    if branch:
        _execute(page, list(branch), results, hl, abort_flag)
    return {"branch": "then" if truthy else "else"}


def _h_repeat(page, a, hl, results, abort_flag):
    times = int(a["times"])
    sub = list(a.get("actions", []))
    for _ in range(max(0, times)):
        if abort_flag["abort"]:
            break
        _execute(page, sub, results, hl, abort_flag)
    return {"iterations": times}


def _h_log(page, a, hl, results, abort_flag):
    return {"message": str(a["message"])}


_HANDLERS: Dict[str, Callable[..., Any]] = {
    "goto": _h_goto,
    "wait": _h_wait,
    "wait_for": _h_wait_for,
    "wait_for_url": _h_wait_for_url,
    "click": _h_click,
    "fill": _h_fill,
    "type": _h_type,
    "press": _h_press,
    "select": _h_select,
    "check": _h_check,
    "scroll": _h_scroll,
    "screenshot": _h_screenshot,
    "set_cookie": _h_set_cookie,
    "eval_js": _h_eval_js,
    "if": _h_if,
    "repeat": _h_repeat,
    "log": _h_log,
}
