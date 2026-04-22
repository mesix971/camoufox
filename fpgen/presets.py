"""
Known-good P4 presets (H2 SETTINGS, TLS extension order, GREASE, etc.).

Applying a preset to a Profile stamps all the P4-related fields at once so
they stay coherent. Use a preset that matches the Profile's firefox_version
or UA — mismatching them (e.g. Firefox 142 UA + "chrome-120" H2 values) is
a fingerprinting inconsistency.

Only use these if you know why you're overriding TLS/H2 defaults; for 99%
of cases Firefox's built-in defaults are the right answer.
"""

from __future__ import annotations

from typing import Any, Dict

from fpgen.profile import Profile


# Extension IDs as decimal strings, in ClientHello order. Sourced from
# captured Wireshark traces of the matching browser release on Linux/x86.
# Comments show the conventional name.
_FF142_EXT_ORDER = [
    "0",   # server_name
    "23",  # session_ticket
    "65281",  # renegotiation_info
    "10",  # supported_groups
    "11",  # ec_point_formats
    "35",  # session_ticket (alt)
    "16",  # application_layer_protocol_negotiation
    "5",   # status_request
    "34",  # delegated_credentials
    "51",  # key_share
    "43",  # supported_versions
    "13",  # signature_algorithms
    "28",  # record_size_limit
    "65037",  # encrypted_client_hello
    "21",  # padding
]

_FF_OLD_EXT_ORDER = [
    "0", "23", "65281", "10", "11", "35", "16", "5", "34",
    "51", "43", "13", "28", "21",
]

PRESETS: Dict[str, Dict[str, Any]] = {
    "firefox-142-stock": {
        "http2_settings": {
            "headerTableSize": 65536,
            "enablePush": False,
            "initialWindowSize": 131072,
            "maxFrameSize": 16384,
        },
        "http2_window_initial": 12517377,
        "tls_extensions_order": list(_FF142_EXT_ORDER),
        "tls_grease_enabled": True,
    },
    "firefox-140-stock": {
        "http2_settings": {
            "headerTableSize": 65536,
            "enablePush": False,
            "initialWindowSize": 131072,
        },
        "http2_window_initial": 12517377,
        "tls_extensions_order": list(_FF_OLD_EXT_ORDER),
        "tls_grease_enabled": True,
    },
    "firefox-pre-grease": {
        # Older Firefox versions (<110) didn't emit GREASE. Pair with a UA
        # in that range for consistency.
        "http2_settings": {
            "headerTableSize": 65536,
            "enablePush": False,
            "initialWindowSize": 131072,
        },
        "tls_extensions_order": list(_FF_OLD_EXT_ORDER),
        "tls_grease_enabled": False,
    },
    "shuffle-extensions": {
        # Low-risk tweak: keep everything Firefox-accurate but shuffle
        # non-mandatory extensions per-connection. Breaks exact JA4 match
        # without making the handshake invalid.
        "tls_extensions_shuffle": True,
        "tls_grease_enabled": True,
    },
}


def apply_preset(profile: Profile, preset_name: str) -> Profile:
    """Stamp P4 fields on profile from a named preset. Mutates + returns."""
    if preset_name not in PRESETS:
        raise KeyError(f"unknown P4 preset: {preset_name}. Known: {sorted(PRESETS)}")
    for key, value in PRESETS[preset_name].items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    return profile


def list_presets() -> list:
    return sorted(PRESETS.keys())
