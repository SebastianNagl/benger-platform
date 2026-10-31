"""Org storage connections: read-only S3 access to customer buckets.

Service half of the ``org_storage_connections`` table (migration 095): an org
admin stores read-only credentials for an S3-compatible bucket (AWS S3,
self-hosted MinIO, ...) once, then org members browse it server-side and the
import worker pulls selected files straight from it (cloud imports). Lives
under /shared so BOTH the API router and the Celery import worker call the
exact same code, the way ``shared_org_api_key_service`` is shared for org API
keys.

It deliberately avoids any FastAPI / Pydantic import: the workers container
carries sqlalchemy + ijson + boto3 only (no fastapi, no pydantic), so a
/shared module that pulled those in would fail to import there. Validation
problems are raised as plain ``ValueError``; the API layer maps them to HTTP
errors.

Deliberately NOT built on ``storage.object_storage.ObjectStorageService`` /
``S3StorageBackend``: both run ``_ensure_bucket_exists`` at init, which
CREATES the bucket when missing — unacceptable against customer
infrastructure. The client built here is read-only by construction: only
``head_bucket`` / ``head_object`` / ``list_objects_v2`` / ``get_object``
are ever issued, and the stored credentials should be scoped read-only on
the customer side too.

Security posture (SSRF): ``validate_endpoint_url`` always enforces the
http(s) scheme whitelist and the structural rules, and by DEFAULT also
rejects endpoints whose host is on the ``url_guard`` deny-list or resolves
to a private / loopback / link-local / otherwise non-global address
(``url_guard.validate_public_host``, the same check BYOM base URLs get).
Org admins are tenant users (LTI self-service included), so they must not be
able to aim the server at cloud metadata, the K8s API or cluster services.
Self-hosters whose MinIO lives on a LAN / in-cluster address opt in with
``ORG_STORAGE_ALLOW_PRIVATE_ENDPOINTS=true`` (the dev compose sets it). The
check runs when a connection is saved AND every time a client is built, so
rows saved under an earlier, more permissive setting stop working once the
deployment denies private endpoints. Residual gap: boto3 re-resolves DNS
per request, so a TTL-0 rebinding between the check and the request is not
pinned yet.

Prefix jail: every listing and download enforces that the requested key /
prefix starts with the connection's stored ``prefix``, so members can never
browse outside the sub-tree the admin scoped the connection to.
"""

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import url_guard
from encryption_service import encryption_service

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_PORTS = {"http": 80, "https": 443}

_ENV_ALLOW_PRIVATE = "ORG_STORAGE_ALLOW_PRIVATE_ENDPOINTS"
_TRUTHY = ("1", "true", "yes", "on")

# Sanity ceiling for one browse page; the router clamps user input to this.
MAX_LIST_KEYS = 1000


def _allow_private_endpoints() -> bool:
    """Default DENY; only an explicitly truthy env value allows private hosts.

    See the module docstring for the SSRF posture.
    """
    return os.getenv(_ENV_ALLOW_PRIVATE, "false").strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    """Fernet-encrypt a credential for storage (same path as org API keys).

    Returns None for empty/unencryptable input — callers must treat that as
    a validation failure, never store None.
    """
    return encryption_service.encrypt_api_key(value)


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    """Decrypt a stored credential; None on missing/corrupted ciphertext."""
    return encryption_service.decrypt_api_key(value)


def access_key_hint(encrypted_access_key: Optional[str]) -> Optional[str]:
    """Last 4 characters of the access key id, for display ("...F4K3").

    The access key ID is the non-secret half of an S3 credential pair, so a
    4-char suffix is safe to show to org members; the secret key never leaves
    the server in any form.
    """
    plain = decrypt_secret(encrypted_access_key)
    if not plain:
        return None
    return plain[-4:]


# ---------------------------------------------------------------------------
# Endpoint validation
# ---------------------------------------------------------------------------


def validate_endpoint_url(url: Optional[str]) -> None:
    """Validate a connection endpoint URL; raise ``ValueError`` on rejection.

    ``None`` / empty is valid (means the AWS default endpoint). Always
    enforced: http/https scheme, a hostname, no userinfo (credential
    smuggling), no query/fragment. Unless ``ORG_STORAGE_ALLOW_PRIVATE_ENDPOINTS``
    is explicitly truthy, the host must also pass
    ``url_guard.validate_public_host``: not on the deny-list (localhost,
    ``*.internal``, ``*.local``, GCE metadata) and every resolved address
    globally routable (rejects loopback, RFC1918, link-local incl.
    169.254.169.254, CGNAT, ULA, NAT64, ...). Network-state rejections all
    share one generic message so the check cannot be used to map internal
    DNS. See the module docstring.
    """
    if url is None or not url.strip():
        return

    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port  # raises ValueError on a malformed port
    except ValueError as exc:
        raise ValueError(f"Endpoint URL could not be parsed: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("Endpoint URL must use http:// or https://")
    if not host:
        raise ValueError("Endpoint URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Endpoint URL must not contain credentials (user:pass@host)")
    if parts.query or parts.fragment:
        raise ValueError("Endpoint URL must not contain a query string or fragment")

    if _allow_private_endpoints():
        return

    url_guard.validate_public_host(host, port or _DEFAULT_PORTS[scheme])


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def _resolve_credentials(
    conn, access_key: Optional[str] = None, secret_key: Optional[str] = None
):
    """Return (access_key, secret_key), decrypting from ``conn`` when not given."""
    if access_key is None:
        access_key = decrypt_secret(getattr(conn, "encrypted_access_key", None))
    if secret_key is None:
        secret_key = decrypt_secret(getattr(conn, "encrypted_secret_key", None))
    if not access_key or not secret_key:
        raise ValueError(
            "Storage connection credentials could not be decrypted; re-enter them"
        )
    return access_key, secret_key


def build_client(
    conn, access_key: Optional[str] = None, secret_key: Optional[str] = None
):
    """Build a READ-ONLY boto3 S3 client for a connection (or unsaved params).

    ``conn`` needs ``endpoint_url`` / ``region`` / ``use_ssl`` attributes plus
    either the encrypted credential columns or explicit ``access_key`` /
    ``secret_key`` overrides (the unsaved-params test path). Deliberately NOT
    ``S3StorageBackend`` — its ``_ensure_bucket_exists`` creates buckets in
    customer infrastructure. Tight timeouts + bounded retries so a dead
    endpoint fails a request in seconds, not minutes.
    """
    import boto3
    from botocore.client import Config

    access_key, secret_key = _resolve_credentials(conn, access_key, secret_key)

    endpoint_url = getattr(conn, "endpoint_url", None) or None
    # Re-check on every client build, not only at save time: DNS can change
    # after the save, and rows saved under a permissive setting must not keep
    # reaching private addresses once the deployment denies them.
    validate_endpoint_url(endpoint_url)
    config = Config(
        connect_timeout=10,
        read_timeout=60,
        retries={"max_attempts": 3},
        signature_version="s3v4",
        # Custom endpoints (MinIO et al.) need path-style addressing; AWS
        # keeps its default virtual-host style.
        s3={"addressing_style": ("path" if endpoint_url else "auto")},
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=getattr(conn, "region", None) or None,
        use_ssl=bool(getattr(conn, "use_ssl", True)),
        config=config,
    )


# ---------------------------------------------------------------------------
# Prefix jail
# ---------------------------------------------------------------------------


def resolve_jailed_prefix(conn, requested_prefix: Optional[str]) -> str:
    """Return the effective listing prefix, enforcing the connection jail.

    Empty/None request → the connection's own prefix. Anything else must
    start with the connection's prefix; raise ``ValueError`` otherwise so a
    member can never browse outside the admin-scoped sub-tree.
    """
    jail = getattr(conn, "prefix", "") or ""
    if requested_prefix is None or requested_prefix == "":
        return jail
    if not requested_prefix.startswith(jail):
        raise ValueError("Prefix is outside this connection's configured prefix")
    return requested_prefix


def key_in_jail(conn, key: Optional[str]) -> bool:
    """Whether an object key is inside the connection's prefix jail."""
    if not isinstance(key, str) or not key:
        return False
    jail = getattr(conn, "prefix", "") or ""
    return key.startswith(jail)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def list_objects(
    conn,
    prefix: Optional[str] = None,
    continuation_token: Optional[str] = None,
    max_keys: int = 100,
) -> Dict[str, Any]:
    """One delimiter-collapsed listing page under the (jailed) prefix.

    ``Delimiter='/'`` folds sub-"directories" into ``prefixes`` so the UI can
    browse level by level. Raises ``ValueError`` when the requested prefix
    escapes the connection's prefix jail. Returns::

        {"objects": [{"key", "size", "last_modified"}, ...],
         "prefixes": ["a/b/", ...],
         "next_token": "..." | None}
    """
    effective_prefix = resolve_jailed_prefix(conn, prefix)
    max_keys = max(1, min(int(max_keys), MAX_LIST_KEYS))

    client = build_client(conn)
    kwargs: Dict[str, Any] = {
        "Bucket": conn.bucket,
        "Prefix": effective_prefix,
        "Delimiter": "/",
        "MaxKeys": max_keys,
    }
    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token

    response = client.list_objects_v2(**kwargs)

    objects = [
        {
            "key": item["Key"],
            "size": item.get("Size"),
            "last_modified": (
                item["LastModified"].isoformat() if item.get("LastModified") else None
            ),
        }
        for item in response.get("Contents", [])
        # A key identical to the prefix is the "directory" placeholder object
        # some tools create; hide it from the browse listing.
        if item.get("Key") != effective_prefix
    ]
    prefixes = [p["Prefix"] for p in response.get("CommonPrefixes", [])]
    next_token = (
        response.get("NextContinuationToken") if response.get("IsTruncated") else None
    )
    return {"objects": objects, "prefixes": prefixes, "next_token": next_token}


def _generic_error_message(exc: Exception) -> str:
    """Map a botocore failure to a short generic message.

    Never echoes raw exception text — it can carry internal hostnames,
    request IDs, or the endpoint URL.
    """
    try:
        from botocore.exceptions import (
            ClientError,
            ConnectTimeoutError,
            EndpointConnectionError,
            NoCredentialsError,
            ReadTimeoutError,
            SSLError,
        )
    except ImportError:  # pragma: no cover — boto3 is a hard dep in both images
        return "Connection test failed"

    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchBucket") or status == 404:
            return "Bucket not found"
        if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch") or status == 403:
            return "Access denied — check the credentials and bucket permissions"
        if code in ("301", "PermanentRedirect") or status == 301:
            return "Bucket is in a different region — set the correct region"
        return "The storage service rejected the request"
    if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError)):
        return "Could not connect to the storage endpoint"
    if isinstance(exc, ReadTimeoutError):
        return "The storage endpoint timed out"
    if isinstance(exc, SSLError):
        return "TLS handshake with the storage endpoint failed"
    if isinstance(exc, NoCredentialsError):
        return "Credentials are missing or invalid"
    if isinstance(exc, ValueError):
        return str(exc)
    return "Connection test failed"


def test_connection(
    conn, access_key: Optional[str] = None, secret_key: Optional[str] = None
) -> Dict[str, Any]:
    """head_bucket + a 1-key list under the prefix; never raises.

    Works for a saved row (credentials decrypted from the row) or unsaved
    params (explicit ``access_key`` / ``secret_key``). Returns
    ``{"ok": bool, "message": str}`` with short generic messages only — no
    internal hostnames, no raw botocore error text.
    """
    try:
        client = build_client(conn, access_key=access_key, secret_key=secret_key)
        client.head_bucket(Bucket=conn.bucket)
        client.list_objects_v2(
            Bucket=conn.bucket,
            Prefix=(getattr(conn, "prefix", "") or ""),
            MaxKeys=1,
        )
    except Exception as exc:
        logger.info("Org storage connection test failed: %s", type(exc).__name__)
        return {"ok": False, "message": _generic_error_message(exc)}
    return {"ok": True, "message": "Connection successful"}


def head_object_size(conn, key: str) -> int:
    """Object size in bytes via ``head_object`` (for the pre-download cap check).

    Raises ``FileNotFoundError`` when the key doesn't exist.
    """
    from botocore.exceptions import ClientError

    client = build_client(conn)
    try:
        response = client.head_object(Bucket=conn.bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            raise FileNotFoundError(f"Object not found: {key}")
        raise
    return int(response["ContentLength"])


def download_to_fileobj(conn, key: str, fileobj) -> None:
    """Stream an object from the customer bucket into a seekable file object.

    Chunked ``get_object`` body read so the download stays O(buffer), not
    O(file) — same shape as ``ObjectStorageService.download_to_fileobj``.
    Raises ``FileNotFoundError`` when the key doesn't exist so the import
    worker can mark the job failed.
    """
    from botocore.exceptions import ClientError

    client = build_client(conn)
    try:
        response = client.get_object(Bucket=conn.bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            raise FileNotFoundError(f"Object not found: {key}")
        logger.error("Cloud-import download failed: %s", type(exc).__name__)
        raise
    body = response["Body"]
    try:
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            fileobj.write(chunk)
    finally:
        body.close()
