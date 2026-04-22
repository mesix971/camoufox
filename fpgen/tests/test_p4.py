"""P4 (HTTP/2 + TLS + creepjs) integration tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from fpgen import apply_preset, generate, list_presets, to_camoufox_config

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "jsonvv"))


def test_default_profile_emits_no_p4_keys() -> None:
    """Absent P4 fields => absent in output. Firefox uses its defaults."""
    p = generate(seed=1)
    cfg = to_camoufox_config(p)
    p4_keys = [k for k in cfg if k.startswith(("http2:", "tls:", "creepjs:"))]
    assert p4_keys == []


def test_manual_http2_settings_are_emitted() -> None:
    p = generate(seed=1)
    p.http2_settings = {
        "headerTableSize": 65536,
        "enablePush": False,
        "initialWindowSize": 131072,
    }
    cfg = to_camoufox_config(p)
    assert cfg["http2:settings:headerTableSize"] == 65536
    assert cfg["http2:settings:enablePush"] is False
    assert cfg["http2:settings:initialWindowSize"] == 131072
    assert "http2:settings:maxFrameSize" not in cfg


def test_manual_tls_config_is_emitted() -> None:
    p = generate(seed=1)
    p.tls_extensions_order = ["0", "23", "10"]
    p.tls_grease_enabled = False
    cfg = to_camoufox_config(p)
    assert cfg["tls:extensions:order"] == ["0", "23", "10"]
    assert cfg["tls:grease:enabled"] is False


def test_creepjs_bypass_emitted() -> None:
    p = generate(seed=1)
    p.creepjs_bypass_enabled = True
    p.creepjs_bypass_fake_score = 72.5
    p.creepjs_bypass_host_patterns = [r".*creepjs.*", r"fingerprint\.js"]
    cfg = to_camoufox_config(p)
    assert cfg["creepjs:bypass:enabled"] is True
    assert cfg["creepjs:bypass:fakeScore"] == 72.5
    assert cfg["creepjs:bypass:hostPatterns"] == [r".*creepjs.*", r"fingerprint\.js"]


def test_all_presets_apply_without_error() -> None:
    for name in list_presets():
        p = generate(seed=1)
        apply_preset(p, name)
        cfg = to_camoufox_config(p)
        # Every preset must emit at least one P4 key, otherwise it's a no-op.
        p4_keys = [k for k in cfg if k.startswith(("http2:", "tls:", "creepjs:"))]
        assert p4_keys, f"preset {name!r} emitted nothing"


def test_unknown_preset_raises() -> None:
    p = generate(seed=1)
    with pytest.raises(KeyError):
        apply_preset(p, "nonexistent-preset")


def test_preset_stamps_coherent_values() -> None:
    p = generate(seed=1)
    apply_preset(p, "firefox-142-stock")
    assert p.http2_settings is not None
    assert p.tls_extensions_order is not None
    assert p.tls_grease_enabled is True


def test_pre_grease_preset_disables_grease() -> None:
    p = generate(seed=1)
    apply_preset(p, "firefox-pre-grease")
    cfg = to_camoufox_config(p)
    assert cfg["tls:grease:enabled"] is False


def test_shuffle_preset_is_minimal() -> None:
    p = generate(seed=1)
    apply_preset(p, "shuffle-extensions")
    cfg = to_camoufox_config(p)
    assert cfg["tls:extensions:shuffle"] is True
    # Shouldn't force a specific order — only shuffle the default.
    assert "tls:extensions:order" not in cfg


def test_roundtrip_profile_with_p4() -> None:
    from fpgen.profile import Profile
    p = generate(seed=2)
    apply_preset(p, "firefox-142-stock")
    p.creepjs_bypass_enabled = True
    p.creepjs_bypass_host_patterns = ["abc"]
    restored = Profile.from_json(p.to_json())
    assert restored == p


def test_emitted_config_passes_jvv_schema() -> None:
    try:
        from jsonvv import JsonValidator
    except ImportError:
        pytest.skip("jsonvv not importable")
    with (REPO_ROOT / "settings" / "camoucfg.jvv").open() as f:
        schema = json.load(f)
    v = JsonValidator(schema)
    for preset in list_presets():
        p = generate(seed=0)
        apply_preset(p, preset)
        p.creepjs_bypass_enabled = True
        p.creepjs_bypass_fake_score = 88.0
        p.creepjs_bypass_host_patterns = [r"detector\.example\.com"]
        v.validate(to_camoufox_config(p))  # raises on failure


def test_properties_json_lists_all_new_keys() -> None:
    """Every emitted P4 key MUST appear in settings/properties.json."""
    with (REPO_ROOT / "settings" / "properties.json").open() as f:
        known = {e["property"] for e in json.load(f)}
    p = generate(seed=0)
    apply_preset(p, "firefox-142-stock")
    p.creepjs_bypass_enabled = True
    p.creepjs_bypass_fake_score = 50.0
    p.creepjs_bypass_host_patterns = ["x"]
    p.tls_cipher_suites_order = ["4866"]
    p.tls_alpn_order = ["h2", "http/1.1"]
    p.http2_priority_weight = 42
    cfg = to_camoufox_config(p)
    for key in cfg:
        assert key in known, f"emitted key {key!r} missing from properties.json"
