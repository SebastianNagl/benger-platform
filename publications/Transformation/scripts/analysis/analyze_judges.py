#!/usr/bin/env python3
"""Per-judge rubric-use profile (narrative question 3).

For every judge that graded the tailored cells — the six control-arm panel
judges, Luna, and the current-generation additions (Opus 5, Terra) — three
axes:

- validity: first-pass r / MAE vs the blind-human pool mean (30 annotation
  picks)
- stability: 3-pass repeat SD (where a 3-pass execution exists)
- integrity: the P01 degenerate-submission probe (a restated Sachverhalt;
  an honest judge scores 0)

Sources: judge_run_log_temp0.jsonl (panel first passes + mini x3),
judge_run_log_luna.jsonl (luna x3), judge_run_log_repair.jsonl +
judge_run_log_repeats.jsonl (repeats x3 for the other judges + Opus5/Terra).
Rows are guarded to the exam's D6-active rubric via details.rubric_id.

Output: data/processed/judge_outcomes.json + console table.
"""

from __future__ import annotations

import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "judge_outcomes.json"

LOGS = ("judge_run_log_temp0.jsonl", "judge_run_log_luna.jsonl",
        "judge_run_log_repeats.jsonl", "judge_run_log_repair.jsonl",
        "judge_run_log_repair2.jsonl",
        "judge_run_log_o5gap.jsonl")


def _psql_json(query: str):
    out = subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-tAc", f"select coalesce(json_agg(t), '[]') from ({query}) t;"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return json.loads(out)


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def main() -> int:
    picks = json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]
    by_target = {p["target_id"]: p for p in picks}

    # D6-active rubric per clone task from the STABLE criteria-hash snapshot
    # (clone_d6_actives.json) — NOT the live DB actives, which the crossed
    # sweeps mutate mid-round; reading them live silently invalidates the
    # guard while a sweep runs.
    active_by_task = json.loads((INTERIM / "clone_d6_actives.json").read_text())

    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}

    eval_ids = []
    for log in LOGS:
        p = INTERIM / log
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r.get("evaluation_id"):
                eval_ids.append(r["evaluation_id"])
    id_list = "','".join(sorted(set(eval_ids)))
    rows = _psql_json(
        "select te.task_id, te.generation_id, te.annotation_id, te.field_name, "
        "te.evaluation_id, ejr.judge_model_id, ejr.run_index, "
        "te.metrics->'llm_judge_rubric'->'details'->>'rubric_id' as rid, "
        "te.metrics->'llm_judge_rubric'->'details'->>'total_score' as total "
        "from task_evaluations te "
        "left join evaluation_judge_runs ejr on te.judge_run_id = ejr.id "
        f"where te.evaluation_id in ('{id_list}')"
    )

    # cells[judge][(pick, eval_id)] -> {run_index: score}; keep executions
    # separate so first-pass and repeat sets don't mix across fleets.
    per_judge = defaultdict(lambda: defaultdict(dict))
    guard_dropped = 0
    for r in rows:
        if r.get("total") is None or not r.get("judge_model_id"):
            continue
        fname = r.get("field_name") or ""
        if not ("|__all_model__|" in fname or "|human:loesung|" in fname):
            continue
        target = r.get("generation_id") or r.get("annotation_id")
        pick = by_target.get(target)
        if pick is None:
            continue
        if r.get("rid") != active_by_task.get(r["task_id"]):
            guard_dropped += 1
            continue
        per_judge[r["judge_model_id"]][(pick["pick_id"], r["evaluation_id"])][
            int(r.get("run_index") or 0)] = float(r["total"])

    result = {}
    for judge, cells in per_judge.items():
        # first pass per pick: prefer the execution with the LOWEST run count
        # spread? Simply: for each pick take run_index 0 of the earliest
        # execution that has one (stable across fleets).
        first_by_pick, runs_by_pick = {}, defaultdict(list)
        for (pid, eid), runs in sorted(cells.items()):
            if 0 in runs and pid not in first_by_pick:
                first_by_pick[pid] = runs[0]
            if len(runs) > 1:
                runs_by_pick[pid].append(statistics.pstdev(list(runs.values())))
        ann = [(first_by_pick[p], hmean[p]) for p in first_by_pick
               if p in hmean and by_target and
               next(x for x in picks if x["pick_id"] == p)["target_type"] == "annotation"]
        xs = [a for a, _ in ann]; ys = [b for _, b in ann]
        rep = [statistics.mean(v) for v in runs_by_pick.values()]
        result[judge] = {
            "n_picks": len(first_by_pick),
            "validity_r": round(pearson(xs, ys), 3) if pearson(xs, ys) is not None else None,
            "mae": round(statistics.mean(abs(a - b) for a, b in ann), 1) if ann else None,
            "repeat_sd": round(statistics.mean(rep), 2) if rep else None,
            "n_repeat_cells": len(rep),
            "p01": first_by_pick.get("P01"),
        }

    payload = {"per_judge": result, "guard_dropped_rows": guard_dropped}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"guard-dropped rows: {guard_dropped}")
    print(f"{'judge':30s} picks    r    MAE  repSD (n)   P01")
    for j, r in sorted(result.items(), key=lambda kv: kv[1]["mae"] or 99):
        print(f"{j.split('/')[-1]:30s} {r['n_picks']:4d} {r['validity_r'] or '—':>5} "
              f"{r['mae'] or '—':>6} {r['repeat_sd'] or '—':>6} ({r['n_repeat_cells']:3d}) "
              f"{r['p01'] if r['p01'] is not None else '—':>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
