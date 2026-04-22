"""
Profile dataclass.

A Profile is the persistent, user-visible identity. One Profile = one
coherent fingerprint + metadata (name, tags, proxy binding, usage stats).

Profiles serialize to/from JSON; see store.py for on-disk layout. The
Camoufox config dict is derived from a Profile by adapter.py.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Profile:
    id: str
    name: str
    archetype_id: str
    created_at: str = field(default_factory=_utc_now_iso)
    last_used_at: Optional[str] = None
    use_count: int = 0
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    proxy_id: Optional[str] = None

    os: str = "windows"
    os_version: str = "11"
    platform: str = "Win32"
    oscpu: str = "Windows NT 10.0; Win64; x64"
    firefox_version: str = "142.0.1"
    build_id: str = "20240826000000"
    product_sub: str = "20100101"
    user_agent: str = ""
    app_version: str = ""

    cpu_cores: int = 8
    max_touch_points: int = 0

    screen_width: int = 1920
    screen_height: int = 1080
    avail_width: int = 1920
    avail_height: int = 1032
    color_depth: int = 24
    device_pixel_ratio: float = 1.0

    outer_width: int = 1280
    outer_height: int = 800
    inner_width: int = 1280
    inner_height: int = 720
    screen_x: int = 0
    screen_y: int = 0

    webgl_vendor: str = ""
    webgl_renderer: str = ""

    locale: str = "en-US"
    language: str = "en"
    region: str = "US"
    languages: List[str] = field(default_factory=lambda: ["en-US", "en"])
    accept_language: str = "en-US,en;q=0.5"
    timezone: str = "America/New_York"
    latitude: float = 40.7128
    longitude: float = -74.0060
    geo_accuracy: float = 120.0

    audio_sample_rate: int = 48000
    audio_output_latency: float = 0.02
    audio_max_channel_count: int = 2

    fonts: List[str] = field(default_factory=list)
    fonts_spacing_seed: int = 0

    media_webcams: int = 0
    media_micros: int = 0
    media_speakers: int = 0
    media_enabled: bool = True

    battery_charging: bool = True
    battery_level: float = 0.95
    battery_charging_time: float = 0.0
    battery_discharging_time: float = 0.0

    dnt: str = "unspecified"
    global_privacy_control: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Profile":
        return cls(**json.loads(raw))

    def touch(self) -> None:
        self.last_used_at = _utc_now_iso()
        self.use_count += 1
