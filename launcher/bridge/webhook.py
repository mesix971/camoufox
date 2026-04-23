"""
Minimal Discord webhook posting.

Used by the session_runner and scheduler to notify about:
  - session crashed
  - queue position reached front
  - proxy mass-death
  - health check anomalies

Config: a single webhook URL stored in ~/.camoufox/launcher/webhook.json
or overridden via CAMOUFOX_DISCORD_WEBHOOK env var. One URL only; if you
want multiple channels, use Discord's Channel Webhooks forwarding.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests


def _config_path() -> Path:
    return Path(
        os.environ.get(
            "CAMOUFOX_WEBHOOK_CONFIG",
            str(Path.home() / ".camoufox" / "launcher" / "webhook.json"),
        )
    )


def set_webhook(url: str) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"url": url}))


def get_webhook() -> Optional[str]:
    env = os.environ.get("CAMOUFOX_DISCORD_WEBHOOK")
    if env:
        return env
    p = _config_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("url")
    except (OSError, json.JSONDecodeError):
        return None


def notify(
    content: str,
    level: str = "info",
    url: Optional[str] = None,
    embeds: Optional[list] = None,
) -> bool:
    """Post a message to the configured Discord webhook. Returns True on success.

    Best-effort: swallows network errors, returns False on failure so callers
    can keep going.
    """
    hook = url or get_webhook()
    if not hook:
        return False
    color = {
        "info": 0x3498DB,
        "success": 0x2ECC71,
        "warn": 0xF39C12,
        "error": 0xE74C3C,
    }.get(level, 0x95A5A6)
    payload = {
        "username": "Camoufox",
        "embeds": embeds or [{
            "description": content,
            "color": color,
        }],
    }
    try:
        r = requests.post(hook, json=payload, timeout=5.0)
        return 200 <= r.status_code < 300
    except requests.RequestException:
        return False
