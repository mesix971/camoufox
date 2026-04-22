"""Smoke tests on the generator — every archetype must produce a valid profile."""

from __future__ import annotations

import pytest

from fpgen import ARCHETYPES, generate
from fpgen.consistency import validate


@pytest.mark.parametrize("arch", [a.id for a in ARCHETYPES])
def test_every_archetype_generates_valid_profile(arch: str) -> None:
    for seed in range(10):
        p = generate(archetype=arch, seed=seed)
        errs = validate(p)
        assert not errs, f"archetype={arch} seed={seed}: {errs}"


@pytest.mark.parametrize("os", ["windows", "macos", "linux"])
def test_os_filter(os: str) -> None:
    for seed in range(20):
        p = generate(os=os, seed=seed)
        assert p.os == os, f"seed={seed} wrong os"


@pytest.mark.parametrize("locale", ["en-US", "fr-FR", "de-DE", "ja-JP", "pt-BR"])
def test_locale_filter(locale: str) -> None:
    for seed in range(10):
        p = generate(locale=locale, seed=seed)
        assert p.locale == locale


def test_seed_determinism() -> None:
    a = generate(seed=42)
    b = generate(seed=42)
    # Everything except id (which is seeded from rng too actually), should match
    assert a.user_agent == b.user_agent
    assert a.webgl_renderer == b.webgl_renderer
    assert a.fonts == b.fonts
    assert a.id == b.id  # seeded rng also seeds the uuid int


def test_overrides_still_validated() -> None:
    # Setting a deliberately broken value must be caught by assert_valid
    from fpgen.consistency import ConsistencyError

    with pytest.raises(ConsistencyError):
        generate(os="windows", seed=1, webgl_renderer="Apple M2", webgl_vendor="Apple")


def test_profile_roundtrip_json() -> None:
    from fpgen.profile import Profile

    p = generate(seed=7)
    p2 = Profile.from_json(p.to_json())
    assert p == p2


def test_bulk_diversity() -> None:
    """Generating 50 profiles should yield decent diversity — not all identical."""
    profiles = [generate(seed=i) for i in range(50)]
    assert len({p.archetype_id for p in profiles}) >= 3
    assert len({p.webgl_renderer for p in profiles}) >= 5
    assert len({p.user_agent for p in profiles}) >= 2
    assert len({p.locale for p in profiles}) >= 3
