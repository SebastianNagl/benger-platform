"""Readable instrument labels for the D2 summaries (no database ids).

An arm is "martin:<unit>" (the expert sheet) or "rubric:<id>:<unit>" (a
generated sheet). The generated sheet's generator and chain come from the
d2-generate rows, so the tracked summaries name "gpt-5.4 sheet 1" instead of
a dev-database id.

The paper's D2 results are pinned to one generator contract and one judge
code version (the constants below). Sheets are numbered within the pinned
validator only, so a later generation run cannot renumber them; a sheet of
another validator, or an id without a generation row, gets a label that
names it as such and never counts as a numbered sheet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# checklist-3 as run on D2 (extended f13c3b1) and the judge code of the D2 runs
D2_VALIDATOR = "e06a1695309ed6e81f9d6706c175b8f5c956843d3adff0ea7935947a1a6eb069"
D2_CODE_VERSION = "7fc295f3b81f"
NUMBERED = re.compile(r" sheet \d+$")


def rubric_labels(generate_rows: Path, validator: str = D2_VALIDATOR) -> dict[str, str]:
    labels: dict[str, str] = {}
    counts: dict[str, int] = {}
    if not generate_rows.exists():
        return labels
    rows = [json.loads(line) for line in generate_rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    for row in rows:
        rid = row.get("rubric_id")
        if not rid or row.get("status") != "completed" or rid in labels:
            continue
        gen = row.get("generator") or "unknown"
        if (row.get("provenance") or {}).get("validator_sha256") != validator:
            labels[rid] = f"{gen} sheet {rid[:8]} (other contract)"
            continue
        counts[gen] = counts.get(gen, 0) + 1
        labels[rid] = f"{gen} sheet {counts[gen]}"
    return labels


def arm_label(arm: str, labels: dict[str, str]) -> str:
    parts = arm.split(":")
    if parts[0] == "martin":
        return "expert sheet:" + ":".join(parts[1:])
    if parts[0] == "rubric" and len(parts) >= 3:
        name = labels.get(parts[1]) or f"generated sheet {parts[1][:8]} (no generation row)"
        return name + ":" + ":".join(parts[2:])
    return arm


def is_numbered_sheet(label: str) -> bool:
    """A generated sheet of the pinned contract ("gpt-5.4 sheet 2:bullet")."""
    return bool(NUMBERED.search(label.split(":", 1)[0]))
