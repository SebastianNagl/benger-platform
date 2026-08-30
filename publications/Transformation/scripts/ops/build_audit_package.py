#!/usr/bin/env python3
"""Build the BLINDED expert-audit package (RQ1 audit → D6 activation).

Reads ``data/raw/local/task_rubrics.json`` (run ``make pull`` first) and
``data/interim/exams.json``, and writes one Markdown file per exam to
``data/interim/audit/`` containing every contract-valid rubric with the
generator identity replaced by a per-exam letter code (deterministic
seeded shuffle per exam, so codes do NOT correspond across exams and no
generator can be tracked exam-to-exam). The unblinding key goes to
``data/interim/audit/KEY.json`` — auditors must not open it.

Each rubric section shows the derived document rendering (what a grader
sees) plus provenance-audit aids: per-step Herkunft label and the
Fundstelle anchor (to verify against the Musterlösung), and the soft-tier
hinweise recorded at generation time.

Audit sheet columns (fill per rubric in AUDIT_SHEET.csv): missing_steps,
hallucinated_steps, unjustified_external, weight_misallocation,
mishandled_alternatives, overall_1to5, activate (exactly one per exam,
or 'merge' with notes).
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
RUBRICS = HERE / "data" / "raw" / "local" / "task_rubrics.json"
EXAMS = HERE / "data" / "interim" / "exams.json"
# exams.json is keyed by PROD task ids; rubrics carry LOCAL ids.
TASK_MAP = HERE / "data" / "interim" / "benchathon_local_task_map.json"
OUT = HERE / "data" / "interim" / "audit"

SEED = "benger-transformation-audit-2026"


def main() -> int:
    rubrics = [
        r
        for r in json.loads(RUBRICS.read_text(encoding="utf-8"))
        if r.get("status") != "archived"
        and (r.get("generation_metadata") or {}).get("contract_version") == 3
    ]
    exams_prod = (
        {e["task_id"]: e for e in json.loads(EXAMS.read_text(encoding="utf-8"))}
        if EXAMS.exists()
        else {}
    )
    prod_to_local = json.loads(TASK_MAP.read_text(encoding="utf-8"))["task_id_map"]
    exams = {
        local_id: exams_prod[prod_id]
        for prod_id, local_id in prod_to_local.items()
        if prod_id in exams_prod
    }

    by_task: dict = {}
    for r in rubrics:
        by_task.setdefault(r["task_id"], []).append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    key = {}
    sheet_rows = []
    for i, (task_id, rows) in enumerate(sorted(by_task.items()), start=1):
        rng = random.Random(f"{SEED}:{task_id}")
        rows = sorted(rows, key=lambda r: r.get("generator_model_id") or "")
        rng.shuffle(rows)
        exam = exams.get(task_id) or {}
        title = (
            exam.get("name")
            or exam.get("titel")
            or (exam.get("sachverhalt") or "")[:60].strip()
            or task_id[:8]
        )
        lines = [
            f"# Exam {i:02d}: {title}",
            "",
            f"Task: `{task_id}` — Bereich: {exam.get('bereich', '?')} — "
            f"{len(rows)} Kandidaten-Bewertungsbögen (blind codiert)",
            "",
        ]
        for j, r in enumerate(rows):
            code = f"R{chr(ord('A') + j)}"
            key.setdefault(task_id, {})[code] = {
                "rubric_id": r["id"],
                "generator_model_id": r.get("generator_model_id"),
            }
            meta = r.get("generation_metadata") or {}
            hinweise = meta.get("hinweise") or []
            lines.append(f"\n---\n\n## {code} ({len(r.get('criteria') or {})} Schritte)\n")
            if hinweise:
                lines.append(
                    "*Automatische Hinweise (soft-tier):* "
                    + "; ".join(hinweise)
                    + "\n"
                )
            rendered = meta.get("rendered_text")
            if rendered:
                lines.append("```")
                lines.append(rendered)
                lines.append("```")
            sheet_rows.append(
                {
                    "exam": f"{i:02d}",
                    "task_id": task_id,
                    "code": code,
                    "missing_steps": "",
                    "hallucinated_steps": "",
                    "unjustified_external": "",
                    "weight_misallocation": "",
                    "mishandled_alternatives": "",
                    "overall_1to5": "",
                    "activate": "",
                    "notes": "",
                }
            )
        (OUT / f"exam_{i:02d}.md").write_text("\n".join(lines), encoding="utf-8")

    (OUT / "KEY.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (OUT / "AUDIT_SHEET.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sheet_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sheet_rows)

    n = sum(len(v) for v in key.values())
    print(
        f"wrote {len(by_task)} exam files, AUDIT_SHEET.csv ({n} rubrics), "
        f"KEY.json (do not open before the audit) -> {OUT.relative_to(HERE)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
