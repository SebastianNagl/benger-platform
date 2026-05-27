"""Pull human korrektur grades on the Benchathon validation subset from prod.

The standard Benchathon-tasks-YYYY-MM-DD.json export carries human korrektur
grades inline (`field_name='loesung'` with `metrics.korrektur_falloesung`), but
without the assignment metadata (`pick_id`, `role`, `pass`, `source` tag) that
the agreement pipeline needs. This script INNER-JOINs `task_evaluations` against
`task_assignments` tagged `source=arr_dataset_2026-05-11`, so only grades that
correspond to an ARR pick assignment are emitted. Stray grades on unassigned
annotation rows (e.g. one grader's 4 extras on task `dfdea348`) are dropped.

Usage
-----
    uv run python scripts/pull_korrektur_sidecar.py

Output
------
    data/raw/benchathon/korrektur_grades_sidecar.json

    {
      "project_id": "...",
      "exported_at": "...",
      "n_rows": 180,
      "rows": [{"evaluation_row_id": "...", "task_id": "...", ...}, ...]
    }

Requires SSH access to root@178.105.26.90 with kubectl in PATH.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "raw" / "benchathon" / "korrektur_grades_sidecar.json"

BENCHATHON_PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
SOURCE_TAG = "source=arr_dataset_2026-05-11"

REMOTE_SCRIPT = r"""
import json, sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/shared")
from database import SessionLocal
from sqlalchemy import text

SQL = '''
SELECT te.id::text                  AS evaluation_row_id,
       te.task_id::text             AS task_id,
       te.annotation_id::text       AS annotation_id,
       te.generation_id::text       AS generation_id,
       ta.target_type               AS target_type,
       te.evaluation_id::text       AS evaluation_run_id,
       te.created_by::text          AS user_id,
       u.email                      AS created_by_email,
       te.created_at::text          AS created_at,
       ta.id::text                  AS assignment_id,
       ta.notes                     AS assignment_notes,
       te.metrics                   AS metrics
  FROM task_evaluations te
  JOIN tasks t ON t.id = te.task_id
  JOIN task_assignments ta
    ON ta.user_id  = te.created_by
   AND ta.task_id  = te.task_id
   AND (ta.target_id = te.annotation_id OR ta.target_id = te.generation_id)
   AND ta.notes LIKE :tag
  LEFT JOIN users u ON u.id = te.created_by
 WHERE t.project_id = :pid
   AND te.field_name = 'loesung'
'''

db = SessionLocal()
rows = db.execute(text(SQL), {"pid": "__PID__", "tag": "%__TAG__%"}).mappings().all()

def parse_notes(notes: str) -> dict:
    out = {}
    for part in (notes or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out

emitted = []
for r in rows:
    notes_kv = parse_notes(r["assignment_notes"])
    metrics = r["metrics"]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    emitted.append({
        "evaluation_row_id":     r["evaluation_row_id"],
        "task_id":               r["task_id"],
        "annotation_id":         r["annotation_id"],
        "generation_id":         r["generation_id"],
        "target_type":           r["target_type"],
        "evaluation_run_id":     r["evaluation_run_id"],
        "user_id":               r["user_id"],
        "created_by_email":      r["created_by_email"],
        "created_at":            r["created_at"],
        "role_from_assignment":  notes_kv.get("evaluator_type"),
        "pick_id":               notes_kv.get("pick_id"),
        "pass":                  notes_kv.get("pass"),
        "assignment_id":         r["assignment_id"],
        "assignment_notes":      r["assignment_notes"],
        "metrics":               metrics,
        "role_inferred":         False,
    })

print(json.dumps(emitted, ensure_ascii=False))
""".replace("__PID__", BENCHATHON_PROJECT_ID).replace("__TAG__", SOURCE_TAG)


def fetch_via_kubectl() -> list[dict]:
    cmd = [
        "ssh", "-o", "ConnectTimeout=15", "root@178.105.26.90",
        "kubectl -n benger exec -i deployment/benger-api -- python3 -",
    ]
    proc = subprocess.run(
        cmd, input=REMOTE_SCRIPT, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"Remote pull failed (rc={proc.returncode}):\n{proc.stderr}"
        )
    body = proc.stdout.strip()
    if not body:
        raise SystemExit("Remote pull returned empty payload.")
    return json.loads(body)


def main() -> None:
    rows = fetch_via_kubectl()

    n = len(rows)
    n_creator = sum(1 for r in rows if r["role_from_assignment"] == "creator")
    n_blind   = sum(1 for r in rows if r["role_from_assignment"] == "blind")
    n_missing = sum(1 for r in rows if not r["assignment_notes"])

    if n_missing:
        raise SystemExit(f"{n_missing} row(s) lack assignment_notes — strict filter regression")
    if n != n_creator + n_blind:
        raise SystemExit(f"role split mismatch: total={n} creator={n_creator} blind={n_blind}")

    payload = {
        "project_id":  BENCHATHON_PROJECT_ID,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_tag":  SOURCE_TAG,
        "n_rows":      n,
        "rows":        rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    print(f"Wrote {n} rows to {OUT}")
    print(f"  creator: {n_creator}  blind: {n_blind}")
    by_grader: dict[str, int] = {}
    for r in rows:
        key = r["created_by_email"] or "(unknown)"
        by_grader[key] = by_grader.get(key, 0) + 1
    for g, k in sorted(by_grader.items(), key=lambda kv: -kv[1]):
        print(f"  {g:50s} {k:3d}")


if __name__ == "__main__":
    main()
