"""
Size-capped reads of upstream HTTP response bodies.

Single canonical implementation shared by api and workers via /shared.
Used on every outbound call to a user-registered (BYOM) endpoint, where the
remote server is not trusted: aiohttp's ``response.json()`` / ``.text()`` /
``.read()`` accumulate the whole (transparently decompressed) body in
memory, so a hostile endpoint could answer with a very large body or a
small compressed payload that inflates to gigabytes and take the api or
worker process down.

``read_capped`` reads ``response.content`` chunk by chunk and stops as soon
as the DECOMPRESSED byte count exceeds the cap, raising
``ResponseTooLargeError``. ``read_capped_json`` / ``read_capped_text``
decode the capped bytes.

The error message is deliberately generic (no URL, host, or body excerpt),
so it is safe to persist or surface after the usual sanitizing.
"""

import json
from typing import Any

# Connectivity probes (/models listing, 1-message chat ping). A real
# /models list is a few KB; 1 MiB leaves generous headroom.
PROBE_MAX_BODY_BYTES = 1 * 1024 * 1024

# Error bodies of failed completions. Only the head (~500 chars) is ever
# kept, so these are read with ``truncate=True``: the first 64 KiB are
# kept and the rest is never read. Truncating (instead of raising) keeps
# the HTTP status as the thing that decides retry vs. fail-fast.
ERROR_BODY_MAX_BYTES = 64 * 1024

# Successful chat completions. A 32k-token answer is well under 1 MiB of
# JSON, even with reasoning traces; 8 MiB is a comfortable ceiling.
COMPLETION_MAX_BODY_BYTES = 8 * 1024 * 1024

_CHUNK_SIZE = 64 * 1024


class ResponseTooLargeError(Exception):
    """The upstream response body exceeded the configured byte cap."""

    def __init__(self, limit: int):
        super().__init__(
            f"Upstream response too large (limit {limit // 1024} KiB)"
        )
        self.limit = limit


async def read_capped(
    response: Any, max_bytes: int, *, truncate: bool = False
) -> bytes:
    """Read an aiohttp response body, failing once it exceeds ``max_bytes``.

    Counts decompressed bytes (what ``response.content`` yields), so a
    compressed body that inflates past the cap is rejected mid-stream
    instead of being buffered in full. A declared ``Content-Length`` above
    the cap is rejected before reading anything.

    With ``truncate=True`` an oversized body is not an error: the first
    ``max_bytes`` are returned and the rest is left unread (the connection
    is released by the caller's ``async with``).
    """
    declared = getattr(response, "content_length", None)
    if not truncate and isinstance(declared, int) and declared > max_bytes:
        raise ResponseTooLargeError(max_bytes)

    buf = bytearray()
    async for chunk in response.content.iter_chunked(_CHUNK_SIZE):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            if truncate:
                return bytes(buf[:max_bytes])
            raise ResponseTooLargeError(max_bytes)
    return bytes(buf)


async def read_capped_text(
    response: Any, max_bytes: int, *, truncate: bool = False
) -> str:
    """``read_capped`` decoded as text (UTF-8 fallback, never raises on
    bad bytes)."""
    raw = await read_capped(response, max_bytes, truncate=truncate)
    encoding = None
    get_encoding = getattr(response, "get_encoding", None)
    if callable(get_encoding):
        try:
            encoding = get_encoding()
        except Exception:
            encoding = None
    try:
        return raw.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


async def read_capped_json(response: Any, max_bytes: int) -> Any:
    """``read_capped`` parsed as JSON. Raises ``ResponseTooLargeError`` when
    over the cap and ``ValueError`` (json.JSONDecodeError) on bad JSON."""
    raw = await read_capped(response, max_bytes)
    return json.loads(raw)
