"""Adapter tests — the output must match properties.json types exactly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from fpgen import generate, to_camoufox_config


PROPERTIES_PATH = Path(__file__).resolve().parents[2] / "settings" / "properties.json"


def _load_property_types() -> Dict[str, str]:
    with PROPERTIES_PATH.open() as f:
        data = json.load(f)
    return {entry["property"]: entry["type"] for entry in data}


PROPERTY_TYPES = _load_property_types()


def _check_type(key: str, value) -> None:
    expected = PROPERTY_TYPES[key]
    if expected == "str":
        assert isinstance(value, str), f"{key}: expected str, got {type(value).__name__}"
    elif expected == "uint":
        assert isinstance(value, int) and not isinstance(value, bool), f"{key}: expected int"
        assert value >= 0, f"{key}: uint must be >= 0, got {value}"
    elif expected == "int":
        assert isinstance(value, int) and not isinstance(value, bool), f"{key}: expected int"
    elif expected == "double":
        assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{key}: expected number"
    elif expected == "bool":
        assert isinstance(value, bool), f"{key}: expected bool"
    elif expected == "array":
        assert isinstance(value, list), f"{key}: expected list"
    elif expected == "dict":
        assert isinstance(value, dict), f"{key}: expected dict"
    else:
        raise AssertionError(f"unknown property type in schema: {expected}")


@pytest.mark.parametrize("seed", range(20))
def test_every_emitted_key_is_known_and_typed_correctly(seed: int) -> None:
    p = generate(seed=seed)
    cfg = to_camoufox_config(p)
    for key, value in cfg.items():
        assert key in PROPERTY_TYPES, f"emitted unknown key {key!r} not in properties.json"
        _check_type(key, value)


def test_build_id_opt_in() -> None:
    p = generate(seed=0)
    cfg = to_camoufox_config(p)
    assert "navigator.buildID" not in cfg
    cfg_with = to_camoufox_config(p, include_build_id=True)
    assert cfg_with["navigator.buildID"] == p.build_id


def test_core_keys_present() -> None:
    p = generate(seed=0)
    cfg = to_camoufox_config(p)
    must_have = [
        "navigator.userAgent", "navigator.platform", "navigator.oscpu",
        "navigator.hardwareConcurrency", "navigator.languages",
        "screen.width", "screen.height", "window.outerWidth", "window.devicePixelRatio",
        "timezone", "geolocation:latitude", "geolocation:longitude",
        "webGl:vendor", "webGl:renderer", "fonts",
        "AudioContext:sampleRate",
        "locale:all", "locale:language", "locale:region",
        "battery:charging", "battery:level",
    ]
    for k in must_have:
        assert k in cfg, f"missing core key {k}"
