"""
iproyal-specific helpers.

iproyal encodes sticky-session state inside the password payload using
underscore-delimited modifiers:

    actualpassword_country-US_city-NewYork_session-abc123_lifetime-10m

Session rotation = regenerate the `session-<id>` modifier (and optionally
rewrite country/city/lifetime). Calling iproyal's HTTP API isn't needed —
the session ID lives entirely in the password string; iproyal creates/binds
a fresh IP the first time that session id is seen.
"""

from __future__ import annotations

import re
import secrets
from typing import Optional

from proxypool.proxy import Proxy


_SESSION_RE = re.compile(r"(_session-)[A-Za-z0-9]+", re.IGNORECASE)
_LIFETIME_RE = re.compile(r"(_lifetime-)[A-Za-z0-9]+", re.IGNORECASE)
_COUNTRY_RE = re.compile(r"(_country-)[A-Za-z]+", re.IGNORECASE)
_CITY_RE = re.compile(r"(_city-)[A-Za-z0-9]+", re.IGNORECASE)


def _gen_session_id() -> str:
    return secrets.token_hex(6)


def rotate_session(
    proxy: Proxy,
    new_session_id: Optional[str] = None,
    lifetime: Optional[str] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    in_place: bool = False,
) -> Proxy:
    """
    Return a Proxy with a rotated sticky session.

    If `new_session_id` is None, generates a random one. Country/city/lifetime
    can also be overridden. If `in_place=True`, mutates the input Proxy and
    returns it; otherwise returns a shallow copy.

    Requires proxy.provider == "iproyal" and a password containing session
    modifiers. Raises ValueError otherwise — use update_session_in_password()
    for the lower-level string manipulation.
    """
    if proxy.provider != "iproyal":
        raise ValueError(
            f"rotate_session supports iproyal only; got provider={proxy.provider!r}"
        )
    if not proxy.password:
        raise ValueError("proxy has no password to rotate")

    new_session_id = new_session_id or _gen_session_id()
    new_password = update_session_in_password(
        proxy.password,
        session_id=new_session_id,
        lifetime=lifetime,
        country=country,
        city=city,
    )

    target = proxy if in_place else _shallow_copy(proxy)
    target.password = new_password
    target.sticky_session_id = new_session_id
    if lifetime is not None:
        target.sticky_session_lifetime = lifetime
    if country is not None:
        target.country = country.upper() if len(country) == 2 else country
    if city is not None:
        target.city = city
    # A rotated session has never been used, so clear IP observation.
    target.observed_ip = None
    target.observed_country = None
    target.observed_city = None
    target.consecutive_failures = 0
    return target


def update_session_in_password(
    password: str,
    session_id: str,
    lifetime: Optional[str] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
) -> str:
    """Rewrite modifier fragments in an iproyal-style password."""
    def _replace_or_append(pattern: re.Pattern, prefix: str, value: Optional[str], text: str) -> str:
        if value is None:
            return text
        repl = f"{prefix}{value}"
        if pattern.search(text):
            return pattern.sub(repl, text)
        return f"{text}{repl}"

    out = password
    out = _replace_or_append(_SESSION_RE, "_session-", session_id, out)
    out = _replace_or_append(_LIFETIME_RE, "_lifetime-", lifetime, out)
    out = _replace_or_append(_COUNTRY_RE, "_country-", country, out)
    out = _replace_or_append(_CITY_RE, "_city-", city, out)
    return out


def _shallow_copy(p: Proxy) -> Proxy:
    """Return a new Proxy with a fresh id (a rotated session is a new identity)."""
    from dataclasses import replace
    return replace(p, id=Proxy.new_id())
