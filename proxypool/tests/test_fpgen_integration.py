"""End-to-end: bind a proxy to an fpgen.Profile."""

from __future__ import annotations

import pytest

try:
    import fpgen
    _HAS_FPGEN = True
except ImportError:
    _HAS_FPGEN = False

from proxypool import Proxy, to_camoufox_proxy
from proxypool.adapter import bind_to_profile, unbind_from_profile


pytestmark = pytest.mark.skipif(not _HAS_FPGEN, reason="fpgen not importable in this environment")


def _proxy() -> Proxy:
    return Proxy(
        id=Proxy.new_id(), label="t", scheme="http",
        host="198.51.100.1", port=8080, username="u", password="p",
    )


def test_bind_real_fpgen_profile() -> None:
    profile = fpgen.generate(seed=1)
    assert profile.proxy_id is None
    proxy = _proxy()
    bind_to_profile(proxy, profile)
    assert profile.proxy_id == proxy.id

    previous = unbind_from_profile(profile)
    assert previous == proxy.id
    assert profile.proxy_id is None


def test_combined_camoufox_launch_kwargs() -> None:
    """What the launcher will actually pass to camoufox.launch_options()."""
    profile = fpgen.generate(seed=2)
    proxy = _proxy()
    bind_to_profile(proxy, profile)

    cfg = fpgen.to_camoufox_config(profile)
    proxy_kwarg = to_camoufox_proxy(proxy)

    # Simulate the launcher call
    launch_kwargs = {"config": cfg, "proxy": proxy_kwarg}
    assert "navigator.userAgent" in launch_kwargs["config"]
    assert launch_kwargs["proxy"]["server"] == "http://198.51.100.1:8080"
