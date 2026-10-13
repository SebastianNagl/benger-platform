"""Cursor pagination of the public API.

Lists take ``?limit=50&cursor=<opaque>`` and answer
``{"items": [...], "next_cursor": "..." | null}``. A cursor is base64url
(unpadded) JSON naming the list it belongs to (``k``) and the sort key of
the last item served; clients treat it as opaque. Cursors stay valid across
deployments as long as the list's sort order does not change.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import Query

from routers.v1._errors import V1Error

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def limit_param(default: int = DEFAULT_LIMIT):
    return Query(
        default,
        ge=1,
        le=MAX_LIMIT,
        description=f"Page size (1 to {MAX_LIMIT}).",
    )


def cursor_param():
    return Query(
        None,
        max_length=512,
        description="Opaque cursor from the previous page's `next_cursor`.",
    )


def encode_cursor(kind: str, position: Dict[str, Any]) -> str:
    raw = json.dumps({"k": kind, **position}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).rstrip(b"=").decode("ascii")


def decode_cursor(kind: str, cursor: Optional[str]) -> Optional[Dict[str, Any]]:
    """The position stored in ``cursor`` (None for the first page). A cursor
    that is malformed or belongs to another list answers 400
    ``invalid_cursor``."""
    if cursor is None or cursor == "":
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        raise V1Error(400, "invalid_cursor", "The cursor is malformed")
    if not isinstance(data, dict) or data.pop("k", None) != kind:
        raise V1Error(400, "invalid_cursor", "The cursor belongs to another list")
    return data


def page(
    kind: str,
    rows: Sequence[Any],
    limit: int,
    position_of,
) -> Tuple[List[Any], Optional[str]]:
    """Split ``rows`` (fetched with ``limit + 1``) into the page and the next
    cursor. ``position_of(row)`` returns the sort-key dict of a row."""
    items = list(rows[:limit])
    if len(rows) > limit and items:
        return items, encode_cursor(kind, position_of(items[-1]))
    return items, None
