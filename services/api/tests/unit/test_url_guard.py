"""
Unit tests for the shared SSRF url_guard (services/shared/url_guard.py).

Pure-unit: socket.getaddrinfo is always monkeypatched — no test performs
real DNS resolution. No DB fixtures are used, so this file also runs
outside the dockerized suite.
"""

import socket

import pytest

import url_guard
from url_guard import validate_custom_model_url

PUBLIC_V4 = "93.184.216.34"


def _addrinfo(*addresses):
    """Build getaddrinfo-shaped result entries for the given IP strings."""
    entries = []
    for addr in addresses:
        if ":" in addr:
            family, sockaddr = socket.AF_INET6, (addr, 443, 0, 0)
        else:
            family, sockaddr = socket.AF_INET, (addr, 443)
        entries.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))
    return entries


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Keep the host environment's flag from leaking into tests."""
    monkeypatch.delenv("CUSTOM_MODEL_ALLOW_PRIVATE_URLS", raising=False)


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every hostname to a single public IPv4 address."""
    monkeypatch.setattr(
        url_guard.socket, "getaddrinfo", lambda *a, **kw: _addrinfo(PUBLIC_V4)
    )


@pytest.fixture
def no_dns(monkeypatch):
    """Fail the test if any DNS resolution is attempted."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("getaddrinfo must not be called")

    monkeypatch.setattr(url_guard.socket, "getaddrinfo", _forbidden)


@pytest.mark.unit
class TestAcceptAndNormalize:
    def test_accepts_public_url(self, public_dns):
        assert (
            validate_custom_model_url("https://api.example.com/v1")
            == "https://api.example.com/v1"
        )

    def test_normalizes_case_default_port_trailing_slash(self, public_dns):
        assert (
            validate_custom_model_url("HTTPS://Api.Example.COM:443/v1/")
            == "https://api.example.com/v1"
        )

    def test_keeps_non_default_port(self, public_dns):
        assert (
            validate_custom_model_url("https://api.example.com:8443/v1")
            == "https://api.example.com:8443/v1"
        )

    def test_strips_trailing_slash_without_path(self, public_dns):
        assert (
            validate_custom_model_url("http://api.example.com/")
            == "http://api.example.com"
        )


@pytest.mark.unit
class TestStructuralRejections:
    """Structural checks run before DNS, so no resolver call may happen."""

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://api.example.com/v1",
            "api.example.com/v1",  # no scheme
            "https://user:pw@api.example.com/",
            "https://api.example.com/v1?key=abc",
            "https://api.example.com/v1#frag",
            "https://api.example.com/v1/chat/completions",
            "https://api.example.com/v1/completions",
            "",
        ],
    )
    def test_rejects(self, no_dns, url):
        with pytest.raises(ValueError):
            validate_custom_model_url(url)


@pytest.mark.unit
class TestResolvedAddressRejections:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",  # loopback
            "10.1.2.3",  # RFC1918
            "172.16.0.1",  # RFC1918
            "192.168.1.1",  # RFC1918
            "169.254.169.254",  # link-local / cloud metadata
            "100.64.0.1",  # CGNAT
            "::1",  # v6 loopback
            "fe80::1",  # v6 link-local
            "fc00::1",  # ULA
            "::ffff:10.0.0.1",  # IPv4-mapped private
        ],
    )
    def test_rejects_non_global_resolution(self, monkeypatch, address):
        monkeypatch.setattr(
            url_guard.socket, "getaddrinfo", lambda *a, **kw: _addrinfo(address)
        )
        with pytest.raises(ValueError):
            validate_custom_model_url("https://api.example.com/v1")

    def test_rejects_when_one_of_many_addresses_is_private(self, monkeypatch):
        monkeypatch.setattr(
            url_guard.socket,
            "getaddrinfo",
            lambda *a, **kw: _addrinfo(PUBLIC_V4, "10.0.0.5"),
        )
        with pytest.raises(ValueError, match="10.0.0.5"):
            validate_custom_model_url("https://api.example.com/v1")

    def test_rejects_unresolvable_host(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        monkeypatch.setattr(url_guard.socket, "getaddrinfo", _fail)
        with pytest.raises(ValueError, match="could not be resolved"):
            validate_custom_model_url("https://does-not-exist.example.com/v1")


@pytest.mark.unit
class TestHostnameDenyList:
    """Deny-listed names are rejected before any DNS resolution."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",
            "http://metadata.google.internal/",
            "http://vllm.svc.cluster.internal/v1",
            "http://ollama.local:11434/v1",
        ],
    )
    def test_rejects_denied_hostnames(self, no_dns, url):
        with pytest.raises(ValueError, match="not allowed"):
            validate_custom_model_url(url)


@pytest.mark.unit
class TestAllowPrivate:
    def test_param_allows_localhost_without_dns(self, no_dns):
        assert (
            validate_custom_model_url("http://localhost:11434", allow_private=True)
            == "http://localhost:11434"
        )

    def test_param_allows_lan_address_without_dns(self, no_dns):
        assert (
            validate_custom_model_url("http://192.168.1.5:8000/v1", allow_private=True)
            == "http://192.168.1.5:8000/v1"
        )

    def test_env_flag_allows_private(self, no_dns, monkeypatch):
        monkeypatch.setenv("CUSTOM_MODEL_ALLOW_PRIVATE_URLS", "true")
        assert (
            validate_custom_model_url("http://localhost:11434")
            == "http://localhost:11434"
        )

    def test_structural_checks_still_apply(self, no_dns):
        with pytest.raises(ValueError):
            validate_custom_model_url(
                "http://localhost:11434/v1/chat/completions", allow_private=True
            )
        with pytest.raises(ValueError):
            validate_custom_model_url(
                "http://user:pw@localhost:11434", allow_private=True
            )

    def test_explicit_false_overrides_env(self, no_dns, monkeypatch):
        monkeypatch.setenv("CUSTOM_MODEL_ALLOW_PRIVATE_URLS", "true")
        with pytest.raises(ValueError, match="not allowed"):
            validate_custom_model_url("http://localhost:11434", allow_private=False)
