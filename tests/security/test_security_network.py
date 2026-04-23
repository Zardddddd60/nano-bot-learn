"""Tests for network SSRF protection and URL safety checks."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from nanobot_learn.security.network import (
    configure_ssrf_whitelist,
    contains_internal_url,
    validate_resolved_url,
    validate_url_target,
)


def _fake_resolve(host: str, results: list[str]):
    """Return a getaddrinfo mock that maps one host to fake IP results."""

    def _resolver(hostname, port, family=0, type_=0):
        if hostname == host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0)) for ip in results]
        raise socket.gaierror(f"cannot resolve {hostname}")

    return _resolver


@pytest.fixture(autouse=True)
def _reset_ssrf_whitelist() -> None:
    configure_ssrf_whitelist([])
    yield
    configure_ssrf_whitelist([])


def test_validate_url_target_rejects_non_http_scheme() -> None:
    ok, err = validate_url_target("ftp://example.com/file")

    assert not ok
    assert "http" in err.lower()


def test_validate_url_target_rejects_missing_domain() -> None:
    ok, err = validate_url_target("http://")

    assert not ok
    assert "domain" in err.lower()


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.0.0.2",
        "10.0.0.1",
        "172.16.5.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
    ],
)
def test_validate_url_target_blocks_private_ipv4(ip: str) -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("evil.com", [ip]),
    ):
        ok, err = validate_url_target("http://evil.com/path")

    assert not ok
    assert "private" in err.lower() or "blocked" in err.lower()


def test_validate_url_target_blocks_ipv6_loopback() -> None:
    def _resolver(hostname, port, family=0, type_=0):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 0, 0, 0))]

    with patch("nanobot_learn.security.network.socket.getaddrinfo", _resolver):
        ok, _ = validate_url_target("http://evil.com/")

    assert not ok


def test_validate_url_target_allows_public_ip() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("example.com", ["93.184.216.34"]),
    ):
        ok, err = validate_url_target("http://example.com/page")

    assert ok, err


def test_validate_url_target_allows_normal_https() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("github.com", ["140.82.121.3"]),
    ):
        ok, err = validate_url_target("https://github.com/HKUDS/nanobot")

    assert ok, err


def test_configure_ssrf_whitelist_blocks_cgnat_by_default() -> None:
    """100.64.0.0/10 is blocked unless explicitly whitelisted."""
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("ts.local", ["100.100.1.1"]),
    ):
        ok, _ = validate_url_target("http://ts.local/api")

    assert not ok


def test_configure_ssrf_whitelist_allows_matching_cidr() -> None:
    configure_ssrf_whitelist(["100.64.0.0/10"])

    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("ts.local", ["100.100.1.1"]),
    ):
        ok, err = validate_url_target("http://ts.local/api")

    assert ok, err


def test_configure_ssrf_whitelist_does_not_unblock_other_private_ranges() -> None:
    configure_ssrf_whitelist(["100.64.0.0/10"])

    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("internal.local", ["10.0.0.1"]),
    ):
        ok, _ = validate_url_target("http://internal.local/secret")

    assert not ok


def test_configure_ssrf_whitelist_ignores_invalid_cidr_entries() -> None:
    configure_ssrf_whitelist(["not-a-cidr", "100.64.0.0/10"])

    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("ts.local", ["100.100.1.1"]),
    ):
        ok, err = validate_url_target("http://ts.local/api")

    assert ok, err


def test_contains_internal_url_detects_metadata_endpoint() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("169.254.169.254", ["169.254.169.254"]),
    ):
        result = contains_internal_url("curl http://169.254.169.254/latest/meta-data/")

    assert result is True


def test_contains_internal_url_detects_localhost() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("localhost", ["127.0.0.1"]),
    ):
        result = contains_internal_url("wget http://localhost:8080/secret")

    assert result is True


def test_contains_internal_url_allows_public_url() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("example.com", ["93.184.216.34"]),
    ):
        result = contains_internal_url("curl https://example.com/api/data")

    assert result is False


def test_contains_internal_url_returns_false_when_no_url_present() -> None:
    assert contains_internal_url("echo hello && ls -la") is False


def test_validate_resolved_url_blocks_private_literal_ip() -> None:
    ok, err = validate_resolved_url("http://127.0.0.1/admin")

    assert not ok
    assert "private" in err.lower()


def test_validate_resolved_url_blocks_private_domain_after_resolution() -> None:
    with patch(
        "nanobot_learn.security.network.socket.getaddrinfo",
        _fake_resolve("redirect.local", ["127.0.0.1"]),
    ):
        ok, err = validate_resolved_url("http://redirect.local/admin")

    assert not ok
    assert "private" in err.lower()


def test_validate_resolved_url_allows_public_literal_ip() -> None:
    ok, err = validate_resolved_url("https://93.184.216.34/docs")

    assert ok, err
