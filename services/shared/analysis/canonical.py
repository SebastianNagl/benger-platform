"""Canonical JSON and content hashes.

A spec hash and a frame hash must not depend on dictionary key order, on the
JSON library's float formatting or on the Parquet writer's version, so both
are computed over a canonical serialization defined here:

* JSON: keys sorted, no insignificant whitespace, UTF-8, floats in Python's
  shortest round-trip ``repr``; NaN and infinities are refused (the spec
  format has no use for them).
* Frames: see :func:`analysis.frame.frame_hash`, which feeds column names,
  kinds and values to :func:`sha256_hex` in a fixed byte layout.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """``value`` as canonical JSON text."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_hash(value: Any) -> str:
    """SHA-256 of the canonical JSON of ``value``."""
    return sha256_hex(canonical_json(value).encode("utf-8"))
