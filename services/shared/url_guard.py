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

DNS-rebinding immunity: validating at save time AND at call time is
not enough on its own — a malicious DNS server can answer the
validation lookup with a public address and the subsequent connection
lookup with a private one (TTL-0 rebinding). This module closes that
window in two pieces that callers use together before every outbound
request:

  * ``resolve_and_validate`` runs all of the checks above AND returns
    the exact IPs that passed, and
  * ``pinned_connector`` builds an ``aiohttp.TCPConnector`` whose
    resolver ignores live DNS and hands aiohttp ONLY those pre-validated
    IPs — so the socket connects to exactly the address the guard
    approved, never one a second (hostile) resolution introduces.

TLS stays correct: the connection targets the pinned IP, but SNI and
certificate verification still use the original hostname (aiohttp
derives ``server_hostname`` from the request URL, and each pinned
resolver record carries ``hostname=<original host>``). Certificate
verification is never disabled. When ``allow_private`` is in effect the
pinned IP list is empty, meaning "no pinning" — self-hosters keep their
LAN endpoints.
"""

import ipaddress
import logging
import os
import socket
from typing import List, Optional, Tuple
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


def _resolve_and_check_addresses(host: str, port: int) -> List[str]:
    """Resolve host, require every A/AAAA answer to be globally routable,
    and return the validated IP strings (deduped, order-preserving).

    The returned list is what the outbound connection is pinned to — the
    exact addresses whose ``.is_global`` we checked. IPv4-mapped IPv6
    answers are unwrapped to their inner IPv4 form both for the check and
    for pinning, so we connect to the same address we validated.
    """
    try:
        addrinfos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError) as exc:
        raise ValueError(f"Custom model URL host '{host}' could not be resolved") from exc
    if not addrinfos:
        raise ValueError(f"Custom model URL host '{host}' could not be resolved")

    validated: List[str] = []
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

        addr_str = str(ip)
        if addr_str not in validated:
            validated.append(addr_str)

    return validated


def resolve_and_validate(
    url: str, *, allow_private: Optional[bool] = None
) -> Tuple[str, List[str]]:
    """Validate + normalize a custom-model base_url AND resolve its IPs.

    This is the single validation implementation. It runs, in order: the
    structural checks (http/https scheme, hostname required, no userinfo,
    no query/fragment, no completions-route suffix), the DNS-independent
    hostname deny-list, and the per-IP ``.is_global`` check on every
    A/AAAA answer. Raises ValueError with a human-readable reason on any
    rejection.

    Returns ``(normalized_url, validated_ips)`` where ``normalized_url`` is
    ``scheme+host[:port]+path`` (no trailing slash) and ``validated_ips``
    are the exact resolved addresses that passed ``.is_global`` — the set
    ``pinned_connector`` pins the outbound socket to.

    ``allow_private=None`` (the default) defers to the
    ``CUSTOM_MODEL_ALLOW_PRIVATE_URLS`` env var; pass True/False to
    override explicitly. When private URLs are allowed the hostname
    deny-list and DNS checks are skipped, the structural checks still
    apply, and ``validated_ips`` is ``[]`` — an empty list means "no
    pinning" so self-hosters keep their LAN endpoints.
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

    validated_ips: List[str] = []
    if not allow_private:
        # Deny-list check runs before (and regardless of) DNS, so these names
        # are rejected even when resolution is unavailable or spoofed.
        # A trailing dot ("localhost.") is the absolute-FQDN spelling of the
        # same name, so strip it for comparison.
        bare_host = host.lower().rstrip(".")
        if bare_host in _DENIED_HOSTNAMES or bare_host.endswith(_DENIED_HOST_SUFFIXES):
            raise ValueError(f"Custom model URL host '{host}' is not allowed")

        validated_ips = _resolve_and_check_addresses(host, port or _DEFAULT_PORTS[scheme])

    # Normalize: lowercase scheme+host (urlsplit already lowercases
    # .hostname), drop default ports, strip trailing slashes.
    host_part = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        host_part = f"{host_part}:{port}"
    normalized = f"{scheme}://{host_part}{path}"
    return normalized, validated_ips


def validate_custom_model_url(url: str, *, allow_private: Optional[bool] = None) -> str:
    """Validate and normalize a custom-model base_url.

    Thin wrapper over :func:`resolve_and_validate` for callers that only
    need the normalized URL (e.g. save-time validation). Raises ValueError
    with a human-readable reason on rejection; returns the normalized URL
    (scheme+host[:port]+path, no trailing slash).

    Call-time outbound paths should use :func:`resolve_and_validate` +
    :func:`pinned_connector` instead so the connection is pinned to the
    validated IPs (DNS-rebinding immunity).
    """
    normalized, _validated_ips = resolve_and_validate(url, allow_private=allow_private)
    return normalized


# ---------------------------------------------------------------------------
# Connection pinning (DNS-rebinding immunity)
# ---------------------------------------------------------------------------

# The AbstractResolver subclass is built lazily so importing url_guard for the
# pure-validation path never requires aiohttp. Both the api and workers
# containers have aiohttp at the point pinned_connector is called.
_PINNED_RESOLVER_CLS = None


def _pinned_resolver_cls():
    """Lazily build (and cache) the aiohttp resolver that pins to fixed IPs."""
    global _PINNED_RESOLVER_CLS
    if _PINNED_RESOLVER_CLS is not None:
        return _PINNED_RESOLVER_CLS

    from aiohttp.abc import AbstractResolver

    class _PinnedResolver(AbstractResolver):
        """Resolver that ignores live DNS and returns ONLY pre-validated IPs.

        aiohttp calls ``resolve(host, port, family)`` for the connection;
        we answer with the addresses ``resolve_and_validate`` already
        approved, so a hostile second (TTL-0) resolution can never
        introduce a new IP. Each record carries ``hostname=host`` so
        aiohttp uses the original hostname for TLS SNI and certificate
        verification while the socket connects to the pinned ``host`` IP.
        """

        def __init__(self, validated_ips: List[str]):
            self._validated_ips = list(validated_ips)

        async def resolve(
            self, host: str, port: int = 0, family: int = socket.AF_INET
        ) -> List[dict]:
            records: List[dict] = []
            for ip in self._validated_ips:
                ip_family = socket.AF_INET6 if ":" in ip else socket.AF_INET
                # Honour the family aiohttp asked for (AF_UNSPEC == any).
                if family not in (socket.AF_UNSPEC, ip_family):
                    continue
                records.append(
                    {
                        "hostname": host,  # SNI + cert verification host
                        "host": ip,  # socket connects here (pinned)
                        "port": port,
                        "family": ip_family,
                        "proto": socket.IPPROTO_TCP,
                        "flags": 0,
                    }
                )
            if not records:
                raise OSError(
                    f"pinned resolver has no validated address for '{host}' "
                    f"in family {family}"
                )
            return records

        async def close(self) -> None:
            return None

    _PINNED_RESOLVER_CLS = _PinnedResolver
    return _PinnedResolver


def pinned_connector(validated_ips: List[str]):
    """Build an ``aiohttp.TCPConnector`` pinned to ``validated_ips``.

    Given the IPs returned by :func:`resolve_and_validate`, returns a
    connector whose resolver hands aiohttp ONLY those addresses, closing
    the TTL-0 DNS-rebinding window between validation and connection. TLS
    SNI and certificate verification still use the original hostname
    (verification is never disabled).

    When ``validated_ips`` is empty (the ``allow_private`` self-hoster
    bypass), returns a default connector — no pinning.
    """
    import aiohttp

    if not validated_ips:
        return aiohttp.TCPConnector()
    resolver = _pinned_resolver_cls()(validated_ips)
    return aiohttp.TCPConnector(resolver=resolver)
