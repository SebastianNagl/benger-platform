"""
SSRF guard for user-supplied custom-model (BYOM) base URLs.

Single canonical implementation shared by api and workers via /shared.
Validates that a bring-your-own-model ``base_url`` points at a public
HTTP(S) endpoint before the platform ever connects to it, so a user
cannot aim the outbound OpenAI-compatible client at cloud metadata
services, cluster-internal services, or the loopback interface.

Checks (in order):
  1. Structural: http/https scheme only, hostname required, no userinfo
     (credential smuggling), no query/fragment in a base URL, and the
     path must not already end in the completions route the client
     appends (``/chat/completions`` / ``/completions``).
  2. Hostname deny-list independent of DNS: ``localhost``,
     ``metadata.google.internal``, and any ``*.internal`` / ``*.local``
     name.
  3. DNS resolution via ``socket.getaddrinfo`` (A and AAAA): EVERY
     resolved address must be globally routable
     (``ipaddress.ip_address(...).is_global``). This rejects loopback,
     RFC1918, link-local (incl. 169.254.169.254 and fe80::/10), CGNAT
     (100.64/10), ULA (fc00::/7), unspecified and reserved ranges.
     IPv4-mapped IPv6 addresses (``::ffff:10.0.0.1``) are unwrapped and
     the inner IPv4 address validated.

Self-hosters pointing at LAN inference servers (vLLM, Ollama, ...) can
opt out of checks 2-3 via the ``CUSTOM_MODEL_ALLOW_PRIVATE_URLS`` env
var (or the explicit ``allow_private`` parameter). The flag is read
from the environment directly — not from API settings — so api and
workers share one switch without the workers importing API config.

DNS-rebinding caveat: this guard validates at save time AND at call
time (callers re-invoke it before each outbound request), but a
malicious DNS server could still answer the validation lookup with a
public address and the subsequent connection lookup with a private one
(TTL-0 rebinding). Full immunity requires pinning the connection to
the validated IP inside the HTTP client (custom connector) — a
documented follow-up, not covered here.
"""

import ipaddress
import logging
import os
import socket
from typing import Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_PORTS = {"http": 80, "https": 443}

# Names rejected regardless of what (if anything) they resolve to.
_DENIED_HOSTNAMES = ("localhost", "metadata.google.internal")
_DENIED_HOST_SUFFIXES = (".internal", ".local")

# The OpenAI-compatible client appends the route itself; a base_url
# already ending in one of these means the user pasted the full
# endpoint and every request would hit .../completions/completions.
_DENIED_PATH_SUFFIXES = ("/chat/completions", "/completions")

_ENV_ALLOW_PRIVATE = "CUSTOM_MODEL_ALLOW_PRIVATE_URLS"
_TRUTHY = ("1", "true", "yes", "on")


def _allow_private_from_env() -> bool:
    """Read the shared allow-private flag from the environment."""
    return os.getenv(_ENV_ALLOW_PRIVATE, "false").strip().lower() in _TRUTHY


def _describe_non_global(ip) -> str:
    """Name the address class that made an IP non-global, for error text."""
    if ip.is_loopback:
        return "a loopback address"
    if ip.is_link_local:
        return "a link-local address"
    if ip.is_private:
        return "a private-network address"
    if ip.is_multicast:
        return "a multicast address"
    if ip.is_unspecified:
        return "the unspecified address"
    if ip.is_reserved:
        return "a reserved address"
    # e.g. CGNAT 100.64/10: not is_private, not is_global.
    return "a non-globally-routable address"


def _check_resolved_addresses(host: str, port: int) -> None:
    """Resolve host and require every A/AAAA answer to be globally routable."""
    try:
        addrinfos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError) as exc:
        raise ValueError(f"Custom model URL host '{host}' could not be resolved") from exc
    if not addrinfos:
        raise ValueError(f"Custom model URL host '{host}' could not be resolved")

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        raw_addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_addr.split("%")[0])
        except ValueError as exc:
            raise ValueError(
                f"Custom model URL host '{host}' resolved to an unparseable address ({raw_addr})"
            ) from exc

        # Unwrap IPv4-mapped IPv6 (::ffff:10.0.0.1) and validate the inner v4 —
        # otherwise a mapped private address could slip past the v6 checks on
        # older Python versions.
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped

        if not ip.is_global:
            raise ValueError(
                f"Custom model URL host '{host}' resolves to {ip}, "
                f"which is {_describe_non_global(ip)} and not allowed"
            )


def validate_custom_model_url(url: str, *, allow_private: Optional[bool] = None) -> str:
    """Validate and normalize a custom-model base_url.

    Raises ValueError with a human-readable reason on rejection.
    Returns the normalized URL (scheme+host[:port]+path, no trailing slash).

    ``allow_private=None`` (the default) defers to the
    ``CUSTOM_MODEL_ALLOW_PRIVATE_URLS`` env var; pass True/False to
    override explicitly. When private URLs are allowed, the hostname
    deny-list and DNS checks are skipped but the structural checks
    (scheme, userinfo, query/fragment, path suffix) still apply.
    """
    if not url or not url.strip():
        raise ValueError("Custom model URL must not be empty")

    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port  # raises ValueError on non-numeric / out-of-range ports
    except ValueError as exc:
        raise ValueError(f"Custom model URL could not be parsed: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("Custom model URL must use http:// or https://")
    if not host:
        raise ValueError("Custom model URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Custom model URL must not contain credentials (user:pass@host)")
    if parts.query:
        raise ValueError("Custom model URL must not contain a query string")
    if parts.fragment:
        raise ValueError("Custom model URL must not contain a fragment")

    path = parts.path.rstrip("/")
    for suffix in _DENIED_PATH_SUFFIXES:
        if path.lower().endswith(suffix):
            raise ValueError(
                f"Custom model URL must be a base URL without the '{suffix}' route — "
                "the client appends it automatically"
            )

    if allow_private is None:
        allow_private = _allow_private_from_env()

    if not allow_private:
        # Deny-list check runs before (and regardless of) DNS, so these names
        # are rejected even when resolution is unavailable or spoofed.
        # A trailing dot ("localhost.") is the absolute-FQDN spelling of the
        # same name, so strip it for comparison.
        bare_host = host.lower().rstrip(".")
        if bare_host in _DENIED_HOSTNAMES or bare_host.endswith(_DENIED_HOST_SUFFIXES):
            raise ValueError(f"Custom model URL host '{host}' is not allowed")

        _check_resolved_addresses(host, port or _DEFAULT_PORTS[scheme])

    # Normalize: lowercase scheme+host (urlsplit already lowercases
    # .hostname), drop default ports, strip trailing slashes.
    host_part = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        host_part = f"{host_part}:{port}"
    return f"{scheme}://{host_part}{path}"
