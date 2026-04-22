"""
Proxy format parsers.

Accepts every format that actually shows up in the wild when users paste
lines from iproyal, brightdata, smartproxy or raw lists:

  http://user:pass@host:port       (URL with auth)
  socks5://user:pass@host:port
  host:port:user:pass              (flat, colon-separated)
  host:port@user:pass              (flat, @-separated)
  user:pass@host:port              (reverse flat)
  host:port                        (no auth)

After parsing, the provider is auto-detected from the host and any
provider-specific metadata (country, city, session id, lifetime) is
extracted from the username/password payload.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

from proxypool.proxy import Proxy, ProxyScheme


class ParseError(ValueError):
    """Raised when a line can't be interpreted as a proxy."""


_SCHEME_RE = re.compile(r"^(?P<scheme>https?|socks5)://", re.IGNORECASE)
_HOSTPORT_RE = re.compile(r"^(?P<host>[\w.\-]+):(?P<port>\d{1,5})$")


def _detect_provider(host: str) -> str:
    h = host.lower()
    if "iproyal.com" in h:
        return "iproyal"
    if "brightdata" in h or "superproxy.io" in h or "luminati" in h:
        return "brightdata"
    if "smartproxy.com" in h:
        return "smartproxy"
    if "oxylabs" in h:
        return "oxylabs"
    if "packetstream" in h:
        return "packetstream"
    if "soax.com" in h:
        return "soax"
    if "proxyempire" in h:
        return "proxyempire"
    return "custom"


# Common modifier patterns used by rotating-proxy providers to encode
# stickiness and geo into the auth string: "_country-US", "-country-us",
# "_session-abc123", "-lifetime-10m", "-city-newyork", etc.
_MOD_RE = re.compile(
    r"[-_](?P<kind>country|city|state|session|sess|lifetime|ttl)[-_](?P<value>[A-Za-z0-9]+)",
    re.IGNORECASE,
)


def _extract_modifiers(payload: str) -> dict:
    """Extract country/city/session/lifetime from an auth payload."""
    out: dict = {}
    for m in _MOD_RE.finditer(payload):
        kind = m.group("kind").lower()
        value = m.group("value")
        if kind in ("sess", "session"):
            out["session"] = value
        elif kind in ("ttl", "lifetime"):
            out["lifetime"] = value
        else:
            out[kind] = value
    return out


def _parse_url_form(line: str) -> Optional[Proxy]:
    m = _SCHEME_RE.match(line)
    if not m:
        return None
    parsed = urlparse(line)
    if not parsed.hostname or not parsed.port:
        raise ParseError(f"URL form missing host or port: {line!r}")
    scheme = parsed.scheme.lower()
    if scheme == "socks5h":
        scheme = "socks5"
    return Proxy(
        id=Proxy.new_id(),
        label=f"{parsed.hostname}:{parsed.port}",
        scheme=scheme,
        host=parsed.hostname,
        port=parsed.port,
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
    )


def _parse_flat(line: str) -> Optional[Proxy]:
    """Flat formats: host:port[:user:pass] OR host:port[@user:pass] OR user:pass@host:port."""
    # user:pass@host:port
    if "@" in line:
        left, right = line.rsplit("@", 1)
        hp = _HOSTPORT_RE.match(right)
        if hp:
            if ":" in left:
                user, pw = left.split(":", 1)
            else:
                user, pw = left, None
            return Proxy(
                id=Proxy.new_id(),
                label=f"{hp.group('host')}:{hp.group('port')}",
                host=hp.group("host"),
                port=int(hp.group("port")),
                username=user or None,
                password=pw,
            )
        # host:port@user:pass
        left_hp = _HOSTPORT_RE.match(left)
        if left_hp and ":" in right:
            user, pw = right.split(":", 1)
            return Proxy(
                id=Proxy.new_id(),
                label=f"{left_hp.group('host')}:{left_hp.group('port')}",
                host=left_hp.group("host"),
                port=int(left_hp.group("port")),
                username=user or None,
                password=pw,
            )
        raise ParseError(f"@-form but neither side is host:port: {line!r}")

    # colon-flat: host:port or host:port:user:pass
    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        if not port.isdigit():
            raise ParseError(f"port is not numeric: {line!r}")
        return Proxy(
            id=Proxy.new_id(),
            label=f"{host}:{port}",
            host=host, port=int(port),
        )
    if len(parts) == 4:
        host, port, user, pw = parts
        if not port.isdigit():
            raise ParseError(f"port is not numeric: {line!r}")
        return Proxy(
            id=Proxy.new_id(),
            label=f"{host}:{port}",
            host=host, port=int(port),
            username=user or None, password=pw or None,
        )
    # Special case: 3 parts could be host:port:user (no password). Uncommon.
    if len(parts) == 3 and parts[1].isdigit():
        host, port, user = parts
        return Proxy(
            id=Proxy.new_id(),
            label=f"{host}:{port}",
            host=host, port=int(port),
            username=user or None,
        )
    return None


def _enrich(p: Proxy) -> Proxy:
    """Fill in provider, country/city/session/lifetime from user/pass payload."""
    p.provider = _detect_provider(p.host)
    payload = " ".join(filter(None, [p.username, p.password]))
    if not payload:
        return p
    mods = _extract_modifiers(payload)
    if "country" in mods:
        p.country = mods["country"].upper() if len(mods["country"]) == 2 else mods["country"]
    if "city" in mods:
        p.city = mods["city"]
    if "session" in mods:
        p.sticky_session_id = mods["session"]
    if "lifetime" in mods:
        p.sticky_session_lifetime = mods["lifetime"]
    return p


def parse(line: str, label: Optional[str] = None, tags: Optional[List[str]] = None) -> Proxy:
    """Parse one proxy line. Raises ParseError on failure."""
    line = line.strip()
    if not line or line.startswith("#"):
        raise ParseError("empty or comment line")

    if "://" in line and not _SCHEME_RE.match(line):
        raise ParseError(f"unsupported scheme in: {line!r}")

    p = _parse_url_form(line)
    if p is None:
        p = _parse_flat(line)
    if p is None:
        raise ParseError(f"unrecognized proxy format: {line!r}")

    # Validate scheme
    try:
        ProxyScheme(p.scheme)
    except ValueError:
        raise ParseError(f"unsupported scheme: {p.scheme!r}")

    if not 1 <= p.port <= 65535:
        raise ParseError(f"port out of range: {p.port}")

    p = _enrich(p)
    if label:
        p.label = label
    if tags:
        p.tags = list(tags)
    return p


def parse_many(text: str, label_prefix: Optional[str] = None) -> Tuple[List[Proxy], List[Tuple[int, str, str]]]:
    """
    Parse a block of text, one proxy per line. Blank lines and lines starting
    with '#' are skipped. Returns (parsed, errors) where errors is a list of
    (line_number, raw_line, error_message).
    """
    parsed: List[Proxy] = []
    errors: List[Tuple[int, str, str]] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        raw_s = raw.strip()
        if not raw_s or raw_s.startswith("#"):
            continue
        try:
            p = parse(raw_s)
        except ParseError as e:
            errors.append((n, raw_s, str(e)))
            continue
        if label_prefix:
            p.label = f"{label_prefix}{n:04d}"
        parsed.append(p)
    return parsed, errors
