"""Parser tests: every real-world format must round-trip cleanly."""

from __future__ import annotations

import pytest

from proxypool import parse, parse_many
from proxypool.parsers import ParseError


def test_url_form_http() -> None:
    p = parse("http://user:pass@198.51.100.1:8080")
    assert p.scheme == "http"
    assert p.host == "198.51.100.1"
    assert p.port == 8080
    assert p.username == "user"
    assert p.password == "pass"


def test_url_form_https_noauth() -> None:
    p = parse("https://proxy.example.com:3128")
    assert p.scheme == "https"
    assert p.host == "proxy.example.com"
    assert p.port == 3128
    assert p.username is None
    assert p.password is None


def test_url_form_socks5() -> None:
    p = parse("socks5://u:p@198.51.100.2:1080")
    assert p.scheme == "socks5"


def test_flat_host_port_user_pass() -> None:
    p = parse("198.51.100.3:8888:alice:secret")
    assert p.host == "198.51.100.3"
    assert p.port == 8888
    assert p.username == "alice"
    assert p.password == "secret"


def test_flat_host_port_only() -> None:
    p = parse("198.51.100.4:9999")
    assert p.host == "198.51.100.4"
    assert p.port == 9999
    assert p.username is None


def test_flat_at_form() -> None:
    p = parse("alice:secret@198.51.100.5:7070")
    assert p.host == "198.51.100.5"
    assert p.port == 7070
    assert p.username == "alice"
    assert p.password == "secret"


def test_iproyal_line_detects_provider_and_session() -> None:
    line = "geo.iproyal.com:12321:user123:realpass_country-US_city-NewYork_session-abc123_lifetime-10m"
    p = parse(line)
    assert p.provider == "iproyal"
    assert p.host == "geo.iproyal.com"
    assert p.port == 12321
    assert p.username == "user123"
    assert p.country == "US"
    assert p.city == "NewYork"
    assert p.sticky_session_id == "abc123"
    assert p.sticky_session_lifetime == "10m"


def test_brightdata_url_form() -> None:
    line = "http://brd-customer-hl_xyz-zone-residential-country-us:abcpass@brd.superproxy.io:22225"
    p = parse(line)
    assert p.provider == "brightdata"
    assert p.host == "brd.superproxy.io"
    assert p.port == 22225
    # modifiers are in USERNAME for brightdata; our extractor finds them there too
    assert p.country == "us" or p.country == "US"


def test_smartproxy_at_form() -> None:
    line = "user:pass@gate.smartproxy.com:7000"
    p = parse(line)
    assert p.provider == "smartproxy"
    assert p.port == 7000


def test_reject_empty() -> None:
    with pytest.raises(ParseError):
        parse("")


def test_reject_comment_line() -> None:
    with pytest.raises(ParseError):
        parse("# this is a comment")


def test_reject_bad_port() -> None:
    with pytest.raises(ParseError):
        parse("198.51.100.9:notaport")


def test_reject_port_out_of_range() -> None:
    with pytest.raises(ParseError):
        parse("198.51.100.9:70000")


def test_reject_unknown_scheme() -> None:
    with pytest.raises(ParseError):
        parse("ftp://u:p@198.51.100.1:21")


def test_parse_many_mixed() -> None:
    text = """
    # mixed formats
    http://u:p@198.51.100.1:8080
    198.51.100.2:9000
    198.51.100.3:8888:user:pass
    bad line here
    geo.iproyal.com:12321:x:y_session-abc
    """
    parsed, errors = parse_many(text)
    assert len(parsed) == 4
    assert len(errors) == 1
    assert errors[0][1] == "bad line here"


def test_parse_many_assigns_label_prefix() -> None:
    text = "198.51.100.1:9000\n198.51.100.2:9001\n"
    parsed, _ = parse_many(text, label_prefix="batch-")
    assert parsed[0].label == "batch-0001"
    assert parsed[1].label == "batch-0002"


def test_to_url_round_trip() -> None:
    original = "http://user:pass@198.51.100.1:8080"
    p = parse(original)
    assert p.to_url(include_auth=True) == original
    assert p.to_url(include_auth=False) == "http://198.51.100.1:8080"
