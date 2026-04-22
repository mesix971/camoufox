"""CLI parsing + dispatch smoke tests."""

from __future__ import annotations

import json
import subprocess
import sys

from launcher.bridge.__main__ import _coerce, _parse_args, main


def test_coerce_int() -> None:
    assert _coerce("42") == 42


def test_coerce_bool() -> None:
    assert _coerce("true") is True
    assert _coerce("false") is False


def test_coerce_string_fallback() -> None:
    assert _coerce("hello") == "hello"


def test_parse_args_kv_form() -> None:
    args = _parse_args(["--os", "windows", "--seed", "42"])
    assert args == {"os": "windows", "seed": 42}


def test_parse_args_equals_form() -> None:
    args = _parse_args(["--os=windows", "--seed=42"])
    assert args == {"os": "windows", "seed": 42}


def test_parse_args_flag() -> None:
    args = _parse_args(["--headless"])
    assert args == {"headless": True}


def test_parse_args_dashes_become_underscores() -> None:
    args = _parse_args(["--profile-id", "abc"])
    assert args == {"profile_id": "abc"}


def test_parse_args_json_blob() -> None:
    args = _parse_args(['{"os": "windows", "seed": 42}'])
    assert args == {"os": "windows", "seed": 42}


def test_main_unknown_command_exits_nonzero(capsys) -> None:
    rc = main(["bogus-command"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["type"] == "UnknownCommand"


def test_main_help_lists_commands(capsys) -> None:
    rc = main(["--help"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "list-profiles" in out["commands"]
    assert "launch-session" in out["commands"]


def test_subprocess_invocation(tmp_path) -> None:
    """Full subprocess round-trip — the form Electron will actually use."""
    env = {
        "FPGEN_STORE": str(tmp_path / "fpgen"),
        "PROXYPOOL_STORE": str(tmp_path / "proxypool"),
        "LAUNCHER_SESSIONS": str(tmp_path / "sessions"),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": "/home/user/camoufox",
    }
    # list-profiles on empty store
    res = subprocess.run(
        [sys.executable, "-m", "launcher.bridge", "list-profiles"],
        capture_output=True, text=True, env=env, check=True,
    )
    assert json.loads(res.stdout) == {"profiles": []}

    # new-profile via JSON blob
    res = subprocess.run(
        [sys.executable, "-m", "launcher.bridge", "new-profile",
         '{"os": "windows", "seed": 1}'],
        capture_output=True, text=True, env=env, check=True,
    )
    created = json.loads(res.stdout)
    assert created["profile"]["os"] == "windows"

    # list again; should see 1
    res = subprocess.run(
        [sys.executable, "-m", "launcher.bridge", "list-profiles"],
        capture_output=True, text=True, env=env, check=True,
    )
    listed = json.loads(res.stdout)
    assert len(listed["profiles"]) == 1
