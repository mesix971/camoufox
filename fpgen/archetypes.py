"""
Archetype loader.

An archetype is a curated bundle of realistic OS + hardware + display + audio
choices. The generator picks one archetype, then samples within it — this is
what keeps values coherent (no Windows UA with macOS fonts, no Mac without
a 2x DPR display, etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Dict, List, Optional, Tuple

_DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Archetype:
    id: str
    weight: int
    os: str
    os_version: str
    platform: str
    oscpu: str
    ua_template: str
    cpu_cores_choices: List[int]
    screen_presets: List[Tuple[int, int]]
    dpr_choices: List[float]
    color_depth_choices: List[int]
    audio_sample_rate_choices: List[int]
    audio_max_channel_count_choices: List[int]
    font_set_id: str
    gpu_tier: str
    taskbar_height: int
    max_touch_points_choices: List[int] = field(default_factory=lambda: [0])

    @classmethod
    def from_json(cls, raw: Dict) -> "Archetype":
        return cls(
            id=raw["id"],
            weight=raw["weight"],
            os=raw["os"],
            os_version=raw["os_version"],
            platform=raw["platform"],
            oscpu=raw["oscpu"],
            ua_template=raw["ua_template"],
            cpu_cores_choices=list(raw["cpu_cores_choices"]),
            screen_presets=[tuple(p) for p in raw["screen_presets"]],
            dpr_choices=list(raw["dpr_choices"]),
            color_depth_choices=list(raw["color_depth_choices"]),
            audio_sample_rate_choices=list(raw["audio_sample_rate_choices"]),
            audio_max_channel_count_choices=list(raw["audio_max_channel_count_choices"]),
            font_set_id=raw["font_set_id"],
            gpu_tier=raw["gpu_tier"],
            taskbar_height=raw["taskbar_height"],
            max_touch_points_choices=list(raw.get("max_touch_points_choices", [0])),
        )


def _load_archetypes() -> List[Archetype]:
    with (_DATA_DIR / "archetypes.json").open() as f:
        data = json.load(f)
    return [Archetype.from_json(a) for a in data["archetypes"]]


def _load_gpus() -> Dict[str, List[Dict[str, str]]]:
    with (_DATA_DIR / "gpus.json").open() as f:
        return json.load(f)["tiers"]


def _load_fonts() -> Dict[str, List[str]]:
    with (_DATA_DIR / "fonts.json").open() as f:
        return json.load(f)["sets"]


def _load_locales() -> List[Dict]:
    with (_DATA_DIR / "locales.json").open() as f:
        return json.load(f)["locales"]


def _load_firefox() -> Dict:
    with (_DATA_DIR / "firefox.json").open() as f:
        return json.load(f)


ARCHETYPES: List[Archetype] = _load_archetypes()
GPUS: Dict[str, List[Dict[str, str]]] = _load_gpus()
FONTS: Dict[str, List[str]] = _load_fonts()
LOCALES: List[Dict] = _load_locales()
FIREFOX: Dict = _load_firefox()


def pick_archetype(
    rng: Random,
    os: Optional[str] = None,
    archetype_id: Optional[str] = None,
) -> Archetype:
    """Pick an archetype. Filter by os or pick exact by id. Weighted random otherwise."""
    if archetype_id:
        for a in ARCHETYPES:
            if a.id == archetype_id:
                return a
        raise ValueError(f"unknown archetype_id: {archetype_id}")

    pool = ARCHETYPES
    if os:
        pool = [a for a in ARCHETYPES if a.os == os]
        if not pool:
            raise ValueError(f"no archetype for os={os!r}")

    weights = [a.weight for a in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def gpu_pool(tier: str) -> List[Dict[str, str]]:
    if tier not in GPUS:
        raise ValueError(f"unknown gpu tier: {tier}")
    return GPUS[tier]


def font_set(set_id: str) -> List[str]:
    if set_id not in FONTS:
        raise ValueError(f"unknown font set: {set_id}")
    return FONTS[set_id]


def pick_locale(rng: Random, locale: Optional[str] = None) -> Dict:
    if locale:
        for loc in LOCALES:
            if loc["locale"] == locale:
                return loc
        raise ValueError(f"unknown locale: {locale}")
    weights = [loc["weight"] for loc in LOCALES]
    return rng.choices(LOCALES, weights=weights, k=1)[0]
