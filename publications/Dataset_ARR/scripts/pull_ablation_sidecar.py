"""Pull the Qwen3-235B Thinking-vs-Instruct ablation sidecar from prod.

Extracts every generation of the ablation model
(`Qwen/Qwen3-235B-A22B-Instruct-2507`) on the Benchathon and Grundprinzipien
projects, together with the primary-judge evaluations attached to those
generations, into:

    data/raw/ablation/qwen_instruct_ablation.json

The canonical task exports stay untouched: the ablation model is not part of
the 12-system leaderboard, so its rows live in a dedicated sidecar file that
`derive_reasoning_ablation.py` pairs against the Thinking-2507 rows of the
canonical exports.

Same SSH + kubectl exec pattern as pull_korrektur_sidecar.py.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "raw" / "ablation" / "qwen_instruct_ablation.json"

ABLATION_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"
PROJECTS = {
    "benchathon": "e529779b-300f-48c0-89cb-90f3f4b72a51",
    "grundprinzipien": "7995bf7a-24e8-405c-9769-bb1024cf2afb",
}
# Primary-judge evaluation-config prefixes (same runs that score the paper).
JUDGE_PREFIXES = {
    "benchathon": "llm_judge_falloesung-mptmfvee",
    "grundprinzipien": "llm_judge_custom-mpu1cuad",
}

REMOTE_SCRIPT = r"""
import json, sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/shared")
from database import SessionLocal
from sqlalchemy import text

MODEL = "__MODEL__"
PROJECTS = json.loads('__PROJECTS__')
PREFIXES = json.loads('__PREFIXES__')

def _scrub(obj):
    """Recursively drop account/billing identifiers from nested payloads
    (judge evaluations embed their own call metadata)."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()
                if k not in ("billed_user_id", "billed_organization_id")}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj

db = SessionLocal()
out = {"model_id": MODEL, "corpora": {}}
for corpus, pid in PROJECTS.items():
    gens = db.execute(text('''
        SELECT g.id::text AS generation_id, g.task_id::text AS task_id,
               g.model_id, g.response_content, g.response_metadata,
               g.created_at::text AS created_at
          FROM generations g
          JOIN tasks t ON t.id = g.task_id
         WHERE t.project_id = :pid AND g.model_id = :model
           AND g.status = 'completed'
    '''), {"pid": pid, "model": MODEL}).mappings().all()
    gen_rows = []
    gen_ids = []
    for g in gens:
        md = g["response_metadata"]
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:
                md = {"_raw": md}
        # Drop the bulky prompt copies and account/billing identifiers;
        # keep operational + provenance keys.
        _DROP_KEYS = ("system_prompt", "instruction_prompt",
                      "billed_user_id", "billed_organization_id")
        slim = {k: v for k, v in (md or {}).items() if k not in _DROP_KEYS}
        gen_rows.append({
            "generation_id": g["generation_id"],
            "task_id": g["task_id"],
            "model_id": g["model_id"],
            "response_content": g["response_content"],
            "response_metadata": slim,
            "created_at": g["created_at"],
        })
        gen_ids.append(g["generation_id"])
    evals = []
    if gen_ids:
        evals = db.execute(text('''
            SELECT te.generation_id::text AS generation_id,
                   te.field_name, te.metrics, te.created_at::text AS created_at
              FROM task_evaluations te
             WHERE te.generation_id::text = ANY(:gids)
               AND te.field_name LIKE :prefix
        '''), {"gids": gen_ids, "prefix": PREFIXES[corpus] + "%"}).mappings().all()
    eval_rows = []
    for e in evals:
        m = e["metrics"]
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except Exception:
                m = {"_raw": m}
        eval_rows.append({
            "generation_id": e["generation_id"],
            "field_name": e["field_name"],
            "metrics": _scrub(m),
            "created_at": e["created_at"],
        })
    out["corpora"][corpus] = {"generations": gen_rows, "evaluations": eval_rows}
db.close()
print(json.dumps(out, ensure_ascii=False, default=str))
"""


def main():
    script = (REMOTE_SCRIPT
              .replace("__MODEL__", ABLATION_MODEL)
              .replace("__PROJECTS__", json.dumps(PROJECTS))
              .replace("__PREFIXES__", json.dumps(JUDGE_PREFIXES)))
    proc = subprocess.run(
        ["ssh", "root@178.105.26.90",
         "kubectl -n benger exec -i deployment/benger-api -- python3 -"],
        input=script.encode(), capture_output=True, check=True)
    payload = json.loads(proc.stdout.decode().strip().splitlines()[-1])
    payload["_pulled_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for corpus, blob in payload["corpora"].items():
        print(f"{corpus}: {len(blob['generations'])} generations, "
              f"{len(blob['evaluations'])} judge evaluations")
    print(f"wrote {OUT.relative_to(HERE)}")


if __name__ == "__main__":
    main()
