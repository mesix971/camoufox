"""
fpgen — coherent fingerprint generator for Camoufox.

Produces Profile objects whose Camoufox config dicts pass the
settings/properties.json schema and maintain OS/GPU/fonts/locale/timezone
coherence that a naive random generator would violate.

Public API:
    generate(archetype=None, seed=None, **overrides) -> Profile
    Profile.to_camoufox_config() -> dict
    ProfileStore(path).save(profile); load(id); list(); rotate(...)
"""

from fpgen.adapter import to_camoufox_config
from fpgen.archetypes import Archetype, ARCHETYPES, pick_archetype
from fpgen.consistency import ConsistencyError, validate
from fpgen.generator import generate
from fpgen.profile import Profile
from fpgen.store import ProfileStore

__all__ = [
    "Archetype",
    "ARCHETYPES",
    "ConsistencyError",
    "Profile",
    "ProfileStore",
    "generate",
    "pick_archetype",
    "to_camoufox_config",
    "validate",
]

__version__ = "0.1.0"
