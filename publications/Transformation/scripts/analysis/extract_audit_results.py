#!/usr/bin/env python3
"""Unblind the automated audit (D10b) and aggregate per generator.

Join chain: audit task_evaluation row -> annotation.completed_by ->
audit-kandidat-<x> username -> blind code R<X> -> KEY.json[benchathon_task]
[code] -> (generator_model_id, rubric_id). Audit tasks are titled
"Exam NN" where NN indexes sorted(KEY task_ids) 1-based (build_audit_import).

The auditor (gpt-5.4-mini) is a roster generator, so aggregates carry a
self-vs-other split. Screening only — never feeds selection (D10).

Output: data/interim/audit_results.jsonl (one row per audited Bogen)
        data/processed/audit_stats.json  (per-generator dimension means)
"""

from __future__ import annotations

import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
KEY = HERE / "data" / "interim" / "audit" / "KEY.json"
RUNS = HERE / "data" / "interim" / "automated_audit_runs.jsonl"
OUT_ROWS = HERE / "data" / "interim" / "audit_results.jsonl"
OUT_STATS = HERE / "data" / "processed" / "audit_stats.json"

AUDITOR = "gpt-5.4-mini"
DIMS = ("vollstaendigkeit", "treue", "externe_ergaenzungen", "gewichtung",
        "alternativen", "teilpunkte", "gesamturteil")


def _psql_json(query: str):
    out = subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-tAc", f"select coalesce(json_agg(t), '[]') from ({query}) t;"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return json.loads(out)


def main() -> int:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    exam_tasks = sorted(key)  # Exam NN = exam_tasks[NN-1]

    eval_ids = sorted({
        json.loads(l)["evaluation_id"]
        for l in RUNS.read_text(encoding="utf-8").splitlines()
        if json.loads(l).get("evaluation_id")
    })
    id_list = "','".join(eval_ids)
    rows = _psql_json(
        "select te.annotation_id, t.data->>'name' as exam_name, u.username, "
        "te.metrics->'llm_judge_custom'->'details' as details "
        "from task_evaluations te "
        "join tasks t on te.task_id = t.id "
        "join annotations a on te.annotation_id = a.id "
        "join users u on a.completed_by = u.id "
        f"where te.evaluation_id in ('{id_list}')"
    )

    out_rows = []
    for r in rows:
        code = "R" + r["username"].rsplit("-", 1)[-1].upper()
        exam_idx = int(r["exam_name"].split()[-1]) - 1
        task_id = exam_tasks[exam_idx]
        entry = (key.get(task_id) or {}).get(code)
        if entry is None:
            raise SystemExit(f"unblinding miss: task {task_id} code {code}")
        details = r.get("details") or {}
        scores = details.get("scores") or {}
        out_rows.append({
            "task_id": task_id,
            "exam": r["exam_name"],
            "blind_code": code,
            "generator_model_id": entry["generator_model_id"],
            "rubric_id": entry["rubric_id"],
            "self_audit": entry["generator_model_id"] == AUDITOR,
            "total_score": details.get("total_score"),
            "scores": {d: (scores.get(d) or {}).get("score") for d in DIMS},
        })

    with OUT_ROWS.open("w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def aggregate(rows_):
        agg = {}
        for d in DIMS:
            vals = [r["scores"][d] for r in rows_ if r["scores"].get(d) is not None]
            agg[d] = round(statistics.mean(vals), 3) if vals else None
        totals = [r["total_score"] for r in rows_ if r["total_score"] is not None]
        agg["total_mean"] = round(statistics.mean(totals), 2) if totals else None
        agg["n"] = len(rows_)
        return agg

    by_gen = defaultdict(list)
    for r in out_rows:
        by_gen[r["generator_model_id"]].append(r)

    stats = {
        "auditor": AUDITOR,
        "n_audited": len(out_rows),
        "overall": aggregate(out_rows),
        "self": aggregate([r for r in out_rows if r["self_audit"]]),
        "other": aggregate([r for r in out_rows if not r["self_audit"]]),
        "per_generator": {
            g: aggregate(v)
            for g, v in sorted(by_gen.items(), key=lambda kv: -(aggregate(kv[1])["total_mean"] or 0))
        },
    }
    OUT_STATS.write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("n_audited", "overall", "self", "other")}, indent=1))
    print("\nper-generator total means:")
    for g, a in stats["per_generator"].items():
        print(f"  {g:45s} n={a['n']:3d} total={a['total_mean']} gesamturteil={a['gesamturteil']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
