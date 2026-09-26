"""Reading pilot rows (scripts/ops/pilot.sh output) for any analysis.

The pilot files overlap: early runs were copied into several files
(probes.jsonl holds every row of probes_gate.jsonl and
probes_luna_fixed.jsonl), and reruns of a cell append a newer row. Every
analysis therefore reads rows through :func:`distinct_rows` (one row per
physical judgment) and, where it wants one verdict per cell,
:func:`latest_per_cell`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


def load_rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
            if line.strip():
                row = json.loads(line)
                row["_source"] = f"{Path(path).name}:{n + 1}"
                rows.append(row)
    return rows


def call_fingerprint(call: dict[str, Any]) -> tuple:
    """One provider call: model, tokens, cost, latency and prompt hash."""
    return (call.get("model"), call.get("in"), call.get("out"), call.get("usd"), call.get("s"),
            call.get("prompt_sha256"), call.get("system_sha256"))


def row_fingerprint(row: dict[str, Any]) -> tuple:
    """One physical judgment or generation: its calls, else its identity fields."""
    calls = tuple(call_fingerprint(c) for c in row.get("calls") or [])
    ident = tuple(row.get(k) for k in ("run_id", "ts", "phase", "judge", "generator", "exam", "pick", "script_id",
                                       "arm", "probe", "unit", "pass", "sample", "total"))
    return (ident, calls) if not calls or all(c[1] is None for c in calls) else calls


def distinct_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Rows with exact copies (same calls) dropped; the first copy stays."""
    seen, out = set(), []
    for row in rows:
        fp = row_fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(row)
    return out, len(rows) - len(out)


def latest_per_cell(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], tuple]
                    ) -> tuple[dict[tuple, dict[str, Any]], int]:
    """The latest row per cell (file order; later rows win) and how many rows it superseded."""
    cells: dict[tuple, dict[str, Any]] = {}
    superseded = 0
    for row in rows:
        k = key(row)
        if k in cells:
            superseded += 1
        cells[k] = row
    return cells, superseded


def is_dry(row: dict[str, Any]) -> bool:
    return bool((row.get("provenance") or {}).get("dry_run")) or any(c.get("dry_run") for c in row.get("calls") or [])
