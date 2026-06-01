"""Streaming helpers for memory-bounded project import (issue #158).

The import endpoints used to ``json.load`` the whole upload, which balloons a
583MB export to 2-4GB resident and OOM-kills the API pod. These helpers parse
the same files incrementally with ijson so peak heap stays O(batch) instead of
O(file):

- ``read_top_object`` does one streaming pass over a top-level JSON object,
  fully materializing only a whitelist of small keys (``meta``, ``project``,
  bounded side-arrays) while parsing-through and discarding the big arrays.
- ``iter_array`` re-seeks the spooled file and yields one element of a top-level
  array at a time (e.g. ``data.item`` / ``tasks.item``), never holding the whole
  array in memory.

Both accept any seekable binary file object (``SpooledTemporaryFile``,
``io.BytesIO``); callers stream the request body into one of those first.
"""

from typing import Any, Dict, Iterator, Set, Tuple

import ijson
from ijson.common import ObjectBuilder

# Opening ijson events that begin a JSON value, used to classify each top-level
# key (so callers can assert e.g. ``data`` is an array → 422 otherwise).
_VALUE_OPENING_EVENTS = frozenset(
    {"start_map", "start_array", "null", "boolean", "number", "string"}
)


def read_top_object(
    fileobj, include_keys: Set[str]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Stream a top-level JSON object once, building only ``include_keys``.

    Returns ``(values, kinds)``:
      - ``values[k]`` is the fully-built Python value for each ``k`` in
        ``include_keys`` that is present in the document.
      - ``kinds[k]`` is the opening ijson event (``"start_array"``,
        ``"start_map"``, ``"string"``, ``"number"``, ``"boolean"``, ``"null"``)
        for *every* top-level key, including ones not in ``include_keys``. This
        lets callers validate structure (e.g. that ``data`` is an array)
        without materializing it.

    Keys outside ``include_keys`` are parsed-through and discarded, so memory
    stays bounded by the size of the included (small) values, not the file.

    Raises ``ijson.JSONError`` (incl. ``IncompleteJSONError``) on malformed
    JSON. A non-object top level (e.g. a bare array) yields empty results — the
    caller can treat a missing required key as the error.
    """
    fileobj.seek(0)
    values: Dict[str, Any] = {}
    kinds: Dict[str, str] = {}
    current_key = None
    builder = None
    awaiting_open = False

    def _flush_current():
        nonlocal current_key, builder
        if current_key is not None and builder is not None:
            values[current_key] = getattr(builder, "value", None)
        current_key = None
        builder = None

    # use_float=True parses JSON numbers as float, matching json.load. Without
    # it ijson yields decimal.Decimal, which psycopg2 cannot serialize into a
    # JSON/JSONB column ("Object of type Decimal is not JSON serializable").
    for prefix, event, value in ijson.parse(fileobj, use_float=True):
        if prefix == "" and event == "map_key":
            # New top-level key: close out the previous one.
            _flush_current()
            current_key = value
            awaiting_open = True
            builder = ObjectBuilder() if value in include_keys else None
            continue
        if prefix == "" and event in ("start_map", "end_map"):
            # The outer object's own braces. end_map closes the last key.
            if event == "end_map":
                _flush_current()
            continue
        # Any other event belongs to the current top-level key's value.
        if awaiting_open and current_key is not None and event in _VALUE_OPENING_EVENTS:
            kinds[current_key] = event
            awaiting_open = False
        if builder is not None:
            builder.event(event, value)

    return values, kinds


def iter_array(fileobj, path: str) -> Iterator[Any]:
    """Yield elements of a top-level array one at a time.

    ``path`` is an ijson item path such as ``"data.item"`` or ``"tasks.item"``.
    Re-seeks to the start so the same spooled file can be streamed in multiple
    independent passes (e.g. a user-id pre-pass then the main insert pass).
    """
    fileobj.seek(0)
    # use_float=True: see read_top_object — keep float semantics so values land
    # in JSON columns without a Decimal serialization error.
    yield from ijson.items(fileobj, path, use_float=True)
