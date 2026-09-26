"""Readable instrument labels for the D2 summaries (no database ids).

An arm is "martin:<unit>" (the expert sheet) or "rubric:<id>:<unit>" (a
generated sheet). The generated sheet's generator and chain come from the
d2-generate rows, so the tracked summaries name "gpt-5.4 sheet 1" instead of
a dev-database id.
"""

from __future__ import annotations

import json
from pathlib import Path


def rubric_labels(generate_rows: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    counts: dict[str, int] = {}
    if not generate_rows.exists():
        return labels
    rows = [json.loads(line) for line in generate_rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    # Number the sheets of the current validator only; older contracts are marked.
    current = next(((r.get("provenance") or {}).get("validator_sha256") for r in reversed(rows)
                    if (r.get("provenance") or {}).get("validator_sha256")), None)
    for row in rows:
        rid = row.get("rubric_id")
        if not rid or row.get("status") != "completed" or rid in labels:
            continue
        gen = row.get("generator") or "unknown"
        if (row.get("provenance") or {}).get("validator_sha256") != current:
            labels[rid] = f"{gen} sheet (older contract)"
            continue
        counts[gen] = counts.get(gen, 0) + 1
        labels[rid] = f"{gen} sheet {counts[gen]}"
    return labels


def arm_label(arm: str, labels: dict[str, str]) -> str:
    parts = arm.split(":")
    if parts[0] == "martin":
        return "expert sheet:" + ":".join(parts[1:])
    if parts[0] == "rubric" and len(parts) >= 3:
        return labels.get(parts[1], "generated sheet") + ":" + ":".join(parts[2:])
    return arm
