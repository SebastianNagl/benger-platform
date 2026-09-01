"""Pull automatic-metric task_evaluations on human annotations from production.

The standard paper export (Benchathon-tasks-YYYY-MM-DD.json) carries only the
LLM-judge runs on human annotations. The auto-metric runs (BLEU, ROUGE, METEOR,
coherence, semantic_similarity, moverscore) exist in the prod DB but were
filtered out of that export. This script grabs them as a sidecar JSON so the
paper pipeline can compute per-condition metric-vs-judge correlations without
re-running the full export.

Usage
-----
    uv run python scripts/export_human_automatic_metrics.py

Output
------
    data/raw/benchathon/human_automatic_metrics_export.json

    [{"annotation_id": "...", "metric": "bleu", "value": 0.044}, ...]

Requires SSH access to root@178.105.26.90 with kubectl in PATH.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "raw" / "benchathon" / "human_automatic_metrics_export.json"

BENCHATHON_PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"

REMOTE_SCRIPT = """
import json, re, sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/shared")
from database import SessionLocal
from sqlalchemy import text

SQL = (
    "SELECT te.annotation_id, te.field_name, te.metrics "
    "FROM task_evaluations te "
    "JOIN evaluation_runs er ON er.id = te.evaluation_id "
    "WHERE er.project_id = :pid AND te.annotation_id IS NOT NULL"
)

db = SessionLocal()
rows = db.execute(text(SQL), {"pid": "__PID__"}).fetchall()

AUTO = ("bleu", "rouge", "meteor", "bertscore", "moverscore", "semantic_similarity", "coherence")
out = []
for r in rows:
    fn = (r.field_name or "").lower()
    head = re.split(r"[-:|]", fn, maxsplit=1)[0]
    if head not in AUTO:
        continue
    m = r.metrics or {}
    payload = m.get(head)
    if isinstance(payload, dict):
        val = payload.get("value")
        if val is None:
            val = payload.get("score")
    else:
        val = payload
    if val is None:
        continue
    out.append({"annotation_id": str(r.annotation_id), "metric": head, "value": float(val)})

print(json.dumps(out))
""".replace("__PID__", BENCHATHON_PROJECT_ID)


def fetch_via_kubectl() -> list[dict]:
    cmd = [
        "ssh", "-o", "ConnectTimeout=15", "root@178.105.26.90",
        "kubectl -n benger exec -i deployment/benger-api -- python3 -",
    ]
    proc = subprocess.run(
        cmd, input=REMOTE_SCRIPT, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"Remote pull failed (rc={proc.returncode}):\n{proc.stderr}"
        )
    # The pod stdout contains only the JSON payload (the remote script prints
    # exactly one line).
    body = proc.stdout.strip()
    if not body:
        raise SystemExit("Remote pull returned empty payload.")
    return json.loads(body)


def main() -> None:
    rows = fetch_via_kubectl()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    by_metric: dict[str, int] = {}
    for r in rows:
        by_metric[r["metric"]] = by_metric.get(r["metric"], 0) + 1
    print(f"Wrote {len(rows)} rows to {OUT}")
    for m, n in sorted(by_metric.items(), key=lambda kv: -kv[1]):
        print(f"  {m:22} {n:4}")


if __name__ == "__main__":
    main()
