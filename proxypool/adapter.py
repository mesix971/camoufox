"""
Proxy -> Camoufox launch_options proxy kwarg.

Camoufox (and the underlying Playwright Firefox launcher) expect:

    {
        "server": "http://host:port",
        "username": "...",
        "password": "...",
    }

This module produces that exact dict, plus a helper that binds a Proxy to a
fpgen Profile (by writing proxy_id onto the profile).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from proxypool.proxy import Proxy


def to_camoufox_proxy(proxy: Proxy, include_scheme: bool = True) -> Dict[str, Any]:
    """Render the Proxy as a dict suitable for camoufox.launch_options(proxy=...)."""
    if include_scheme:
        server = f"{proxy.scheme}://{proxy.host}:{proxy.port}"
    else:
        server = f"{proxy.host}:{proxy.port}"
    result: Dict[str, Any] = {"server": server}
    if proxy.username:
        result["username"] = proxy.username
    if proxy.password:
        result["password"] = proxy.password
    return result


def bind_to_profile(proxy: Proxy, profile: Any) -> None:
    """
    Stamp the profile.proxy_id field.

    `profile` is typed as Any to avoid importing fpgen (optional dependency);
    it must expose a `proxy_id` attribute. Duck-typing keeps proxypool and
    fpgen independent.
    """
    if not hasattr(profile, "proxy_id"):
        raise AttributeError(
            "profile object has no 'proxy_id' attribute; "
            "did you pass an fpgen.Profile?"
        )
    profile.proxy_id = proxy.id


def unbind_from_profile(profile: Any) -> Optional[str]:
    """Clear profile.proxy_id. Returns the previous binding, if any."""
    if not hasattr(profile, "proxy_id"):
        raise AttributeError("profile object has no 'proxy_id' attribute")
    previous = profile.proxy_id
    profile.proxy_id = None
    return previous
