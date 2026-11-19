"""Lookup tables: validation and content hash (pure Python).

A lookup table is a small named table of a project (``analysis_lookup_tables``,
one row per version) that specs join onto their frames by key columns
(``lookups`` in the spec; the join itself is
:func:`analysis.frame.join_lookups`). A table is ``columns`` (identifiers,
unique) and ``rows``, each a list of values in column order or an object by
column name; values are text (at most 1000 characters), finite numbers,
booleans or null.

:func:`validate_table` checks a payload and returns it with rows as lists;
:func:`lookup_hash` is the content hash a version records and a spec can pin
(``table.content_hash``). The API imports this module without the numeric
stack.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Mapping, Sequence

from analysis.canonical import json_hash

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
MAX_COLUMNS = 50
MAX_ROWS = 100_000
MAX_TEXT = 1000


class LookupTableError(ValueError):
    """An invalid lookup table. ``errors`` lists every problem found (at most
    50)."""

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "invalid lookup table")


def lookup_hash(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """SHA-256 of the canonical JSON of ``{"columns": [...], "rows": [[...]]}``."""
    return json_hash({"columns": list(columns), "rows": [list(r) for r in rows]})


def _value_error(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return "" if math.isfinite(value) else "a number must be finite"
    if isinstance(value, str):
        return "" if len(value) <= MAX_TEXT else f"text longer than {MAX_TEXT} characters"
    return "a value must be text, a number, a boolean or null"


def validate_table(payload: Any) -> Dict[str, Any]:
    """``{"name", "description", "columns", "rows", "row_count",
    "content_hash"}`` of a valid payload ``{"name", "columns", "rows",
    "description"?}``; raises :class:`LookupTableError` otherwise."""
    errors: List[str] = []
    if not isinstance(payload, Mapping):
        raise LookupTableError(["/: the body must be an object"])
    name = payload.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        errors.append("/name: an identifier of at most 100 characters (letters, digits, _)")
    description = payload.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 5000):
        errors.append("/description: text of at most 5000 characters")
    columns = payload.get("columns")
    if not isinstance(columns, list) or not columns or len(columns) > MAX_COLUMNS:
        errors.append(f"/columns: a list of 1 to {MAX_COLUMNS} column names")
        columns = []
    else:
        for i, col in enumerate(columns):
            if not isinstance(col, str) or not NAME.match(col):
                errors.append(f"/columns/{i}: {col!r} is not an identifier")
        if len(set(map(str, columns))) != len(columns):
            errors.append("/columns: column names repeat")
    rows = payload.get("rows")
    out_rows: List[List[Any]] = []
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        errors.append(f"/rows: a list of 1 to {MAX_ROWS} rows")
        rows = []
    for i, row in enumerate(rows):
        if len(errors) >= 50:
            break
        if isinstance(row, Mapping):
            unknown = sorted(str(k) for k in row if k not in columns)
            if unknown:
                errors.append(f"/rows/{i}: unknown column(s) {', '.join(unknown)}")
                continue
            values = [row.get(col) for col in columns]
        elif isinstance(row, list):
            if len(row) != len(columns):
                errors.append(f"/rows/{i}: {len(row)} values for {len(columns)} columns")
                continue
            values = list(row)
        else:
            errors.append(f"/rows/{i}: a row is a list of values or an object")
            continue
        for col, value in zip(columns, values):
            problem = _value_error(value)
            if problem:
                errors.append(f"/rows/{i}/{col}: {problem}")
        out_rows.append(values)
    if errors:
        raise LookupTableError(errors[:50])
    return {
        "name": name,
        "description": description,
        "columns": list(columns),
        "rows": out_rows,
        "row_count": len(out_rows),
        "content_hash": lookup_hash(columns, out_rows),
    }


__all__ = ["LookupTableError", "MAX_COLUMNS", "MAX_ROWS", "lookup_hash", "validate_table"]
