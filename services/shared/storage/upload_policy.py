"""Upload and download policy for client-driven object storage access.

The bucket is served publicly (``storage.<domain>``) through presigned URLs,
so anything a client can store there under a renderable type (HTML, SVG, XML,
JavaScript) becomes a page on a same-site host. This module holds the rules
the ``/storage`` router applies to client input and the defaults the shared
``ObjectStorageService`` applies to every presigned URL:

* a content-type allowlist; scripting-capable types are never accepted,
* magic-byte checks for the binary types when the bytes pass through the API,
* the prefixes a client may choose and a size ceiling per prefix,
* a clamp for presigned GET lifetimes and the Content-Disposition to send.

Kept dependency-free so the api, the workers and the unit tests (which put
``/shared/storage`` itself on ``sys.path``) can all import it.
"""

import os
import re
from typing import Dict, Optional, Tuple

MB = 1024 * 1024

# Default ceiling for a presigned POST when a caller passes no (or a
# non-positive) max_size: a size condition is always part of the policy.
DEFAULT_MAX_UPLOAD_BYTES = 100 * MB

# Prefixes (``file_type``) a client may pick on the /storage endpoints, with
# the size ceiling for each. Server-side writers (exports, imports, handed-in
# submissions, static assets, backups) choose their prefix themselves and
# never go through this map.
CLIENT_PREFIX_MAX_BYTES: Dict[str, int] = {
    "uploads": 100 * MB,
    "temp": 100 * MB,
}

# Content types a client may store, keyed by the normalized type.
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/csv",
        "text/plain",
        "text/markdown",
        "application/json",
        "application/zip",
    }
)

# Types a presigned GET may render in the browser. Everything else is sent
# with ``Content-Disposition: attachment``.
INLINE_SAFE_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
)

# Aliases browsers and tools send for allowed types.
_CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "application/x-zip-compressed": "application/zip",
    "application/x-zip": "application/zip",
    "text/x-markdown": "text/markdown",
    "application/csv": "text/csv",
    "text/comma-separated-values": "text/csv",
}

# Extension fallback when the client sends no type or a generic one.
# ``.apkg`` (Anki deck) is a zip archive.
_EXTENSION_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".zip": "application/zip",
    ".apkg": "application/zip",
}

_GENERIC_TYPES = frozenset({"", "application/octet-stream", "binary/octet-stream"})

# Types (or families) that can run script or be rendered as a document when a
# browser opens them. Never stored from client input, never sent as a
# response type.
_SCRIPTABLE_PATTERN = re.compile(
    r"(html|xml|svg|javascript|ecmascript|x-shockwave|xhtml|text/css|multipart/)"
)

# Leading bytes for the binary types. A zip signature also covers docx.
_MAGIC = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "application/pdf": (b"%PDF-",),
    "application/zip": (b"PK\x03\x04", b"PK\x05\x06"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        b"PK\x03\x04",
    ),
}

DOWNLOAD_URL_MIN_SECONDS = 60
DOWNLOAD_URL_MAX_SECONDS = 3600


class UploadPolicyError(ValueError):
    """A client upload request breaks the policy; ``status_code`` maps to HTTP."""

    def __init__(self, message: str, status_code: int = 415):
        super().__init__(message)
        self.status_code = status_code


def normalize_content_type(content_type: Optional[str]) -> str:
    """Lowercase, strip parameters (``; charset=...``) and map aliases."""
    base = (content_type or "").split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_ALIASES.get(base, base)


def is_scriptable_content_type(content_type: Optional[str]) -> bool:
    """True for HTML, XML, SVG, JavaScript and similar renderable types.

    Allowlisted types are never scriptable (docx's ``openxmlformats`` name
    contains "xml" but is a zip archive browsers do not render).
    """
    normalized = normalize_content_type(content_type)
    if normalized in ALLOWED_CONTENT_TYPES:
        return False
    return bool(_SCRIPTABLE_PATTERN.search(normalized))


def content_type_for_filename(filename: Optional[str]) -> Optional[str]:
    """Allowed type implied by the file extension, or None."""
    _, ext = os.path.splitext((filename or "").lower())
    return _EXTENSION_TYPES.get(ext)


def resolve_client_content_type(content_type: Optional[str], filename: Optional[str]) -> str:
    """Validated content type for a client upload, or raise 415.

    A missing or generic type (octet-stream) falls back to the extension.
    """
    normalized = normalize_content_type(content_type)
    if is_scriptable_content_type(normalized):
        raise UploadPolicyError(f"Content type not allowed: {normalized}")
    if normalized in _GENERIC_TYPES:
        normalized = content_type_for_filename(filename) or ""
    if normalized not in ALLOWED_CONTENT_TYPES:
        raise UploadPolicyError(
            f"Content type not allowed: {normalized or 'unknown'}"
        )
    return normalized


def verify_magic_bytes(content_type: str, data: bytes) -> None:
    """Reject bytes whose signature does not match a binary ``content_type``."""
    if content_type == "image/webp":
        if not (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
            raise UploadPolicyError("File content does not match image/webp")
        return
    signatures = _MAGIC.get(content_type)
    if signatures is None:
        return
    if not any(data.startswith(sig) for sig in signatures):
        raise UploadPolicyError(f"File content does not match {content_type}")


def resolve_client_prefix(file_type: Optional[str]) -> Tuple[str, int]:
    """(prefix, size ceiling) for a client-chosen ``file_type``, or raise 400."""
    prefix = (file_type or "uploads").strip()
    if prefix not in CLIENT_PREFIX_MAX_BYTES:
        raise UploadPolicyError(f"File type not allowed: {prefix}", status_code=400)
    return prefix, CLIENT_PREFIX_MAX_BYTES[prefix]


def clamp_max_size(max_size: Optional[int], ceiling: int) -> int:
    """A positive size limit no larger than ``ceiling``; 0/None mean the ceiling."""
    if not max_size or max_size <= 0:
        return ceiling
    return min(int(max_size), ceiling)


def clamp_download_expiry(expires_in: Optional[int]) -> int:
    """Presigned GET lifetime in [60, 3600] seconds, default 3600."""
    if expires_in is None:
        return DOWNLOAD_URL_MAX_SECONDS
    return max(DOWNLOAD_URL_MIN_SECONDS, min(int(expires_in), DOWNLOAD_URL_MAX_SECONDS))


def safe_response_content_type(content_type: Optional[str]) -> str:
    """The stored type if it is on the allowlist, else application/octet-stream."""
    normalized = normalize_content_type(content_type)
    if normalized in ALLOWED_CONTENT_TYPES:
        return normalized
    return "application/octet-stream"


def _ascii_filename(filename: str) -> str:
    cleaned = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in filename or ""
    )
    return cleaned or "download"


def content_disposition_for(
    filename: Optional[str], content_type: Optional[str], allow_inline: bool = False
) -> str:
    """``attachment`` unless ``allow_inline`` and the type is inline-safe.

    ``allow_inline`` exists for a consumer that renders the file in the page
    (an ``<img>`` or a PDF preview); only png/jpeg/gif/webp/pdf qualify.

    The filename is reduced to printable ASCII without quotes or backslashes
    and the UTF-8 original rides in ``filename*`` (RFC 6266 / 5987), so no
    stored name can break out of the header value.
    """
    from urllib.parse import quote

    disposition = (
        "inline"
        if allow_inline and normalize_content_type(content_type) in INLINE_SAFE_CONTENT_TYPES
        else "attachment"
    )
    name = filename or "download"
    header = f'{disposition}; filename="{_ascii_filename(name)}"'
    if _ascii_filename(name) != name:
        header += f"; filename*=UTF-8''{quote(name, safe='')}"
    return header
