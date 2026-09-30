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
# checklist-4 (extended 5fe4517): its sheets are numbered on their own, "<gen> c4 sheet N"
D2_VALIDATOR_C4 = "28ca3922040ea537147e582daf021519fcb5d3502460225f5b927eceda52983c"
VALIDATOR_TAGS = {D2_VALIDATOR: "", D2_VALIDATOR_C4: " c4"}
# Judge code versions of the D2 runs, newest first: 5768f1f9104b after review
# round 4 (quote verifier and checklist judge fixes; the no-sheet arm),
# 7fc295f3b81f the runs of 09-26. An arm uses its newest version; a paired
# comparison uses the newest version both arms have.
D2_CODE_VERSIONS = ("5768f1f9104b", "7fc295f3b81f")
D2_CODE_VERSION = D2_CODE_VERSIONS[-1]
NUMBERED = re.compile(r" sheet \d+$")


def rubric_labels(generate_rows: Path, validators: dict[str, str] | None = None) -> dict[str, str]:
    """Rubric id -> label. Sheets are numbered per generator within each
    pinned validator (checklist-3 plain, checklist-4 tagged " c4")."""
    tags = VALIDATOR_TAGS if validators is None else validators
    labels: dict[str, str] = {}
    counts: dict[tuple[str, str], int] = {}
    if not generate_rows.exists():
        return labels
    rows = [json.loads(line) for line in generate_rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    for row in rows:
        rid = row.get("rubric_id")
        if not rid or row.get("status") != "completed" or rid in labels:
            continue
        gen = row.get("generator") or "unknown"
        validator = (row.get("provenance") or {}).get("validator_sha256")
        if validator not in tags:
            labels[rid] = f"{gen} sheet {rid[:8]} (other contract)"
            continue
        tagged = gen + tags[validator]
        counts[(tagged, validator)] = counts.get((tagged, validator), 0) + 1
        labels[rid] = f"{tagged} sheet {counts[(tagged, validator)]}"
    return labels


def arm_label(arm: str, labels: dict[str, str]) -> str:
    if arm == "holistic":
        return "no sheet:holistic"
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
