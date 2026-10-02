"""Safe Exam Browser (SEB) request verification.

An exam project with ``seb_required`` only accepts exam reads and writes that
prove they come from SEB running an accepted configuration. SEB offers two
proofs, and we accept either:

* **Native headers** (SEB for Windows, and the classic WebView on macOS):
  ``X-SafeExamBrowser-ConfigKeyHash`` and ``X-SafeExamBrowser-RequestHash``,
  each ``hex(sha256(request_url_without_fragment + key))``. The key is the
  Config Key (CK) or the Browser Exam Key (BEK) respectively.
* **JavaScript API** (the modern WKWebView on macOS / iOS cannot send custom
  headers): ``SafeExamBrowser.security.configKey`` / ``.browserExamKey`` hold
  the same hashes, computed over the *page* URL. The frontend forwards them
  as ``X-Benger-SEB-CK`` / ``X-Benger-SEB-BEK`` together with the page URL
  (``X-Benger-SEB-URL``) and the URL the document was loaded with
  (``X-Benger-SEB-Load-URL``), since SEB may hash either after client-side
  navigation.

The Config Key proves "this configuration"; the Browser Exam Key also covers
the SEB binary, so pinning it restricts an exam to official SEB builds.

The API does not trust forwarded headers (no ProxyHeadersMiddleware), so the
public request URL is rebuilt from ``X-Forwarded-Host`` / ``Host``. Only hosts
of this deployment (``FRONTEND_URL``, ``VERTRETBAR_FRONTEND_URL`` and their
subdomains) are accepted as hash inputs.

Limits: the hashes can be replayed and the CK can be computed by anyone who
holds the ``.seb`` file. SEB raises the bar; it is not attestation.

Pure module: no FastAPI, no DB.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from public_hosts import main_frontend_url, student_locked_frontend_url

HEADER_CONFIG_KEY_HASH = "x-safeexambrowser-configkeyhash"
HEADER_REQUEST_HASH = "x-safeexambrowser-requesthash"
HEADER_JS_CONFIG_KEY = "x-benger-seb-ck"
HEADER_JS_BROWSER_EXAM_KEY = "x-benger-seb-bek"
HEADER_JS_PAGE_URL = "x-benger-seb-url"
HEADER_JS_LOAD_URL = "x-benger-seb-load-url"

CODE_SEB_REQUIRED = "seb_required"
CODE_SEB_VERSION_NOT_ALLOWED = "seb_version_not_allowed"

VIA_HEADER = "header"
VIA_JS = "js"

_HEX_KEY = re.compile(r"^[0-9a-f]{64}$")


def normalize_key(value: Any) -> Optional[str]:
    """A 64-char lowercase hex key, or ``None`` when ``value`` is not one."""
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if _HEX_KEY.match(value) else None


def strip_fragment(url: str) -> str:
    """Drop the ``#fragment``; SEB hashes the URL without it."""
    return url.split("#", 1)[0]


def key_hash(url: str, key: str) -> str:
    """``hex(sha256(url_without_fragment + key))``, as SEB computes it."""
    return hashlib.sha256((strip_fragment(url) + key).encode("utf-8")).hexdigest()


def accepted_config_keys(seb_config: Optional[Mapping]) -> List[str]:
    """The generated Config Key plus any extra keys, normalized, deduped."""
    if not isinstance(seb_config, Mapping):
        return []
    candidates = [seb_config.get("generated_config_key")]
    extra = seb_config.get("extra_config_keys")
    if isinstance(extra, list):
        candidates.extend(extra)
    return _dedupe(normalize_key(k) for k in candidates)


def accepted_browser_exam_keys(seb_config: Optional[Mapping]) -> List[str]:
    """Pinned Browser Exam Keys. Empty means the BEK is not checked."""
    if not isinstance(seb_config, Mapping):
        return []
    entries = seb_config.get("browser_exam_keys")
    if not isinstance(entries, list):
        return []
    keys = []
    for entry in entries:
        keys.append(normalize_key(entry.get("key") if isinstance(entry, Mapping) else entry))
    return _dedupe(keys)


# seb_config keys that only mean something on the deployment that wrote them:
# the download token is per project, the base URL, generated .seb settings and
# their Config Key name the source host, and the config-file password is
# encrypted with that deployment's key.
HOST_BOUND_CONFIG_KEYS = frozenset(
    {"config_token", "base_url", "settings", "generated_config_key", "config_password_enc"}
)


def portable_seb_config(seb_config: Any) -> Optional[dict]:
    """The part of ``seb_config`` that may leave or enter a deployment.

    Only the organizer's choices travel (extra hosts, pinned keys, the quit
    password hash, ...). Exports drop the host-bound keys so no download token
    or encrypted password ends up in a file, and imports drop them again in
    case the file came from an older export; re-enabling the gate rebuilds
    them for the importing host.
    """
    if not isinstance(seb_config, Mapping):
        return None
    return {k: v for k, v in seb_config.items() if k not in HOST_BOUND_CONFIG_KEYS}


def _dedupe(keys: Iterable[Optional[str]]) -> List[str]:
    out: List[str] = []
    for key in keys:
        if key and key not in out:
            out.append(key)
    return out


def deployment_hosts() -> List[str]:
    """Bare hosts (with port) this deployment serves the frontend on."""
    hosts = []
    for base in (main_frontend_url(), student_locked_frontend_url()):
        if base:
            host = urlsplit(base).netloc.lower()
            if host and host not in hosts:
                hosts.append(host)
    return hosts


def host_allowed(host: Optional[str]) -> bool:
    """Whether ``host`` is a deployment host or one of its subdomains."""
    if not host:
        return False
    host = host.strip().lower()
    for allowed in deployment_hosts():
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def _first(value: Optional[str]) -> Optional[str]:
    """First entry of a possibly comma-joined forwarded header."""
    if not value:
        return None
    return value.split(",", 1)[0].strip() or None


def public_request_urls(headers: Mapping[str, str], path: str, query: str) -> List[str]:
    """Candidate public URLs of the current request, as the browser saw it.

    The host comes from ``X-Forwarded-Host`` (set by the Next proxy), falling
    back to ``Host``, and must pass :func:`host_allowed`. The scheme is not
    trustworthy behind two proxies, so both the forwarded scheme and the
    scheme of ``FRONTEND_URL`` are tried.
    """
    host = _first(headers.get("x-forwarded-host")) or _first(headers.get("host"))
    if not host_allowed(host):
        return []
    schemes = []
    for scheme in (_first(headers.get("x-forwarded-proto")), urlsplit(main_frontend_url()).scheme):
        if scheme in ("http", "https") and scheme not in schemes:
            schemes.append(scheme)
    return [urlunsplit((scheme, host.lower(), path, query, "")) for scheme in schemes]


def exam_page_paths(project_id: str) -> List[str]:
    """Paths of the pages a student writes this project's exam on."""
    return [f"/projects/{project_id}/label", f"/student/exams/{project_id}"]


def page_urls(
    headers: Mapping[str, str], page_paths: Optional[Iterable[str]] = None
) -> List[str]:
    """The page URLs the frontend reported for JS-API hashes, host-checked.

    With ``page_paths`` only URLs of those pages count, so a hash taken on
    any other page of the site is no proof for this exam.
    """
    allowed_paths = {p.rstrip("/") for p in page_paths} if page_paths is not None else None
    urls = []
    for name in (HEADER_JS_PAGE_URL, HEADER_JS_LOAD_URL):
        url = (headers.get(name) or "").strip()
        if not url or url in urls:
            continue
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not host_allowed(parts.netloc):
            continue
        if allowed_paths is not None and parts.path.rstrip("/") not in allowed_paths:
            continue
        urls.append(url)
    return urls


def _matches(presented: Optional[str], urls: List[str], keys: List[str]) -> bool:
    presented = normalize_key(presented)
    if not presented:
        return False
    return any(
        hmac.compare_digest(key_hash(url, key), presented) for url in urls for key in keys
    )


@dataclass(frozen=True)
class SebCheck:
    """Outcome of :func:`verify_seb_request`."""

    ok: bool
    code: Optional[str] = None
    via: Optional[str] = None
    browser_exam_key_checked: bool = False


def verify_seb_request(
    headers: Mapping[str, str],
    path: str,
    query: str,
    seb_config: Optional[Mapping],
    page_paths: Optional[Iterable[str]] = None,
) -> SebCheck:
    """Check the SEB proof on a request against a project's ``seb_config``.

    ``headers`` must be case-insensitive or lower-cased (Starlette's are).
    ``page_paths`` limits JS-API proofs to hashes taken on those pages
    (:func:`exam_page_paths`); ``None`` accepts any page on an allowed host.
    Returns ``ok`` with the proof channel, ``seb_required`` when no accepted
    Config Key proof is present, or ``seb_version_not_allowed`` when the
    Config Key matches but pinned Browser Exam Keys do not.
    """
    config_keys = accepted_config_keys(seb_config)
    exam_keys = accepted_browser_exam_keys(seb_config)
    if not config_keys:
        return SebCheck(ok=False, code=CODE_SEB_REQUIRED)

    channels = (
        (
            VIA_HEADER,
            public_request_urls(headers, path, query),
            headers.get(HEADER_CONFIG_KEY_HASH),
            headers.get(HEADER_REQUEST_HASH),
        ),
        (
            VIA_JS,
            page_urls(headers, page_paths),
            headers.get(HEADER_JS_CONFIG_KEY),
            headers.get(HEADER_JS_BROWSER_EXAM_KEY),
        ),
    )
    config_key_seen = False
    for via, urls, ck_hash, bek_hash in channels:
        if not urls or not _matches(ck_hash, urls, config_keys):
            continue
        config_key_seen = True
        if not exam_keys:
            return SebCheck(ok=True, via=via)
        if _matches(bek_hash, urls, exam_keys):
            return SebCheck(ok=True, via=via, browser_exam_key_checked=True)
    if config_key_seen:
        return SebCheck(ok=False, code=CODE_SEB_VERSION_NOT_ALLOWED)
    return SebCheck(ok=False, code=CODE_SEB_REQUIRED)
