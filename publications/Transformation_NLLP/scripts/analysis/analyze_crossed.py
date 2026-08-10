#!/usr/bin/env python3
"""Generator outcome ranking from the crossed rubric-source runs (RQ4 proper).

Data: every valid v3 rubric of every exam judged over the exam's picks — the
155 crossed rounds plus the corresponding arm's rows for the D6-active rubrics
(same judge, same cells). Two lenses:

- ``--lens luna`` (default): Luna ×3 crossed rounds (crossed_run_log.luna.jsonl)
  + the Luna arm (judge_run_log_luna.jsonl). Updates the luna-owned keys of
  generator_outcomes.json (judge, per_generator, granularity, dropped_rows).
- ``--lens sonnet``: Sonnet ×1 crossed rounds (crossed_run_log.jsonl) + the
  temp-0 panel arm (judge_run_log_temp0.jsonl, sonnet single pass). Updates
  only the ``sonnet_lens`` block.

NOTE the log-name history: the Luna rounds originally lived in
crossed_run_log.jsonl and were renamed to .luna.jsonl when the Sonnet lens
reused the plain name — the lens flag resolves this explicitly so a re-run
can never read the wrong log again.

Both lenses persist per-rubric outcomes (data/processed/rubric_outcomes.json,
merged across lenses) and a tidy per-cell dump
(data/interim/crossed_cells.<lens>.jsonl) so downstream scripts are DB-free.

generator_outcomes.json is read-modify-written: the ad-hoc blocks
(paired_dmae, paired_dmae_note, lens_ranking_spearman — formalized in
compute_generator_ranking.py) are preserved verbatim. For the luna lens the
regenerated per_generator is asserted equal to the stored block before
writing (regression guard; --no-check to override after intentional changes).

Output: generator_outcomes.json (merged) + rubric_outcomes.json + cells dump.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Dataset_ARR"
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "generator_outcomes.json"
RUBRIC_OUT = HERE / "data" / "processed" / "rubric_outcomes.json"

LENSES = {
    "luna": {
        "judge": "gpt-5.6-luna",
        "crossed_log": "crossed_run_log.luna.jsonl",
        "arm_log": "judge_run_log_luna.jsonl",
    },
    "sonnet": {
        "judge": "claude-sonnet-4-6",
        "crossed_log": "crossed_run_log.jsonl",
        "arm_log": "judge_run_log_temp0.jsonl",
    },
}


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--lens", choices=sorted(LENSES), default="luna")
    parser.add_argument("--no-check", action="store_true",
                        help="Skip the regression assert against the stored per_generator")
    args = parser.parse_args()
    lens = LENSES[args.lens]
    judge = lens["judge"]

    picks = json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]
    by_target = {p["target_id"]: p for p in picks}

    # Human pool means keyed by pick id.
    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}

    # Crossed rounds + the arm runs (active rubrics).
    eval_meta = {}   # evaluation_id -> rubric_id (crossed) or None (arm; resolve per row)
    for line in (INTERIM / lens["crossed_log"]).read_text().splitlines():
        r = json.loads(line)
        if r.get("verified"):
            eval_meta[r["evaluation_id"]] = r["rubric_id"]
    for line in (INTERIM / lens["arm_log"]).read_text().splitlines():
        r = json.loads(line)
        if r.get("evaluation_id"):
            eval_meta[r["evaluation_id"]] = None  # active rubric; resolve per row

    id_list = "','".join(eval_meta)
    rows = _psql_json(
        "select te.evaluation_id, te.generation_id, te.annotation_id, te.field_name, "
        "ejr.judge_model_id, ejr.run_index, "
        "te.metrics->'llm_judge_rubric'->'details'->>'rubric_id' as rubric_id, "
        "te.metrics->'llm_judge_rubric'->'details'->>'total_score' as total "
        "from task_evaluations te "
        "left join evaluation_judge_runs ejr on te.judge_run_id = ejr.id "
        f"where te.evaluation_id in ('{id_list}')"
    )

    # Rubric metadata: task, generator + step count, from the clone's task_rubrics.
    rub_rows = _psql_json(
        "select tr.id, tr.task_id, tr.generator_model_id, "
        "(select count(*) from jsonb_object_keys(tr.criteria::jsonb) k) as nsteps "
        "from task_rubrics tr join tasks t on tr.task_id = t.id "
        "where t.project_id = '81e474b8-d226-4bf8-bc2e-fb744d25cba5'"
    )
    rub_gen = {r["id"]: r["generator_model_id"] for r in rub_rows}
    rub_task = {r["id"]: r["task_id"] for r in rub_rows}
    rub_steps = {r["id"]: int(r["nsteps"]) for r in rub_rows}

    # cells[(rubric_id, pick_id)][run_index] = total
    cells = defaultdict(dict)
    dropped = 0
    for r in rows:
        if r.get("judge_model_id") != judge or r.get("total") is None:
            continue
        fname = r.get("field_name") or ""
        if not ("|__all_model__|" in fname or "|human:loesung|" in fname):
            continue
        target = r.get("generation_id") or r.get("annotation_id")
        pick = by_target.get(target)
        rid = r.get("rubric_id")
        if pick is None or rid is None:
            dropped += 1
            continue
        expected = eval_meta.get(r["evaluation_id"])
        if expected is not None and expected != rid:
            dropped += 1
            continue
        cells[(rid, pick["pick_id"])][int(r.get("run_index") or 0)] = float(r["total"])

    per_gen = defaultdict(lambda: {"val_pairs": [], "rep_sds": [], "errs": [],
                                   "biases": [], "rubrics": set()})
    per_rubric = defaultdict(lambda: {"rep_sds": [], "errs": [], "biases": [], "n_cells": 0})
    cell_dump = []
    for (rid, pid), runs in sorted(cells.items()):
        gen = rub_gen.get(rid)
        if gen is None:
            continue
        first = runs.get(min(runs))
        g = per_gen[gen]
        g["rubrics"].add(rid)
        per_rubric[rid]["n_cells"] += 1
        cell_dump.append({
            "rubric_id": rid, "task_id": rub_task.get(rid), "generator_model_id": gen,
            "pick_id": pid, "runs": {str(k): v for k, v in sorted(runs.items())},
        })
        if len(runs) > 1:
            sd = statistics.pstdev(list(runs.values()))
            g["rep_sds"].append(sd)
            per_rubric[rid]["rep_sds"].append(sd)
        if pid in hmean and by_target and first is not None:
            meta = next(p for p in picks if p["pick_id"] == pid)
            if meta["target_type"] == "annotation":
                g["val_pairs"].append((first, hmean[pid]))
                g["errs"].append(abs(first - hmean[pid]))
                g["biases"].append(first - hmean[pid])
                per_rubric[rid]["errs"].append(abs(first - hmean[pid]))
                per_rubric[rid]["biases"].append(first - hmean[pid])

    result = {}
    for gen, g in per_gen.items():
        xs = [a for a, _ in g["val_pairs"]]; ys = [b for _, b in g["val_pairs"]]
        result[gen] = {
            "n_rubrics": len(g["rubrics"]),
            "n_cells": len(g["rep_sds"]) if args.lens == "luna" else len(g["val_pairs"]),
            "repeat_sd_mean": round(statistics.mean(g["rep_sds"]), 2) if g["rep_sds"] else None,
            "validity_r": round(pearson(xs, ys), 3) if pearson(xs, ys) is not None else None,
            "mae": round(statistics.mean(g["errs"]), 1) if g["errs"] else None,
            "bias": round(statistics.mean(g["biases"]), 1) if g["biases"] else None,
        }

    # Granularity: per-rubric step count vs repeat SD and MAE.
    gr_x, gr_sd, gr_err = [], [], []
    for rid, d in per_rubric.items():
        ns = rub_steps.get(rid)
        if ns is None or not d["rep_sds"]:
            continue
        gr_x.append(ns)
        gr_sd.append(statistics.mean(d["rep_sds"]))
        gr_err.append(statistics.mean(d["errs"]) if d["errs"] else None)
    gr_pairs_err = [(x, e) for x, e in zip(gr_x, gr_err) if e is not None]
    granularity = {
        "n_rubrics": len(gr_x),
        "steps_vs_repeat_sd_r": round(pearson(gr_x, gr_sd), 3) if pearson(gr_x, gr_sd) is not None else None,
        "steps_vs_mae_r": round(pearson([a for a, _ in gr_pairs_err], [b for _, b in gr_pairs_err]), 3)
                          if len(gr_pairs_err) > 2 else None,
    }

    # ---- persist: tidy cells, per-rubric outcomes (merged across lenses) ----
    cells_path = INTERIM / f"crossed_cells.{args.lens}.jsonl"
    with cells_path.open("w", encoding="utf-8") as fh:
        for row in cell_dump:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    rub_payload = json.loads(RUBRIC_OUT.read_text()) if RUBRIC_OUT.exists() else {}
    lens_rows = []
    for rid, d in sorted(per_rubric.items()):
        lens_rows.append({
            "rubric_id": rid,
            "task_id": rub_task.get(rid),
            "generator_model_id": rub_gen.get(rid),
            "steps": rub_steps.get(rid),
            "n_cells": d["n_cells"],
            "repeat_sd_mean": round(statistics.mean(d["rep_sds"]), 3) if d["rep_sds"] else None,
            "mae": round(statistics.mean(d["errs"]), 2) if d["errs"] else None,
            "bias": round(statistics.mean(d["biases"]), 2) if d["biases"] else None,
        })
    rub_payload[args.lens] = {"judge": judge, "n_rubrics": len(lens_rows), "per_rubric": lens_rows}
    RUBRIC_OUT.write_text(json.dumps(rub_payload, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- read-modify-write generator_outcomes.json ----
    stored = json.loads(OUT.read_text()) if OUT.exists() else {}
    if args.lens == "luna":
        if not args.no_check and stored.get("per_generator"):
            mismatches = []
            for gen, want in stored["per_generator"].items():
                got = result.get(gen)
                if got != want:
                    mismatches.append((gen, want, got))
            if stored.get("dropped_rows") is not None and stored["dropped_rows"] != dropped:
                mismatches.append(("dropped_rows", stored["dropped_rows"], dropped))
            if mismatches:
                print("REGRESSION CHECK FAILED — regenerated values differ from stored:")
                for gen, want, got in mismatches:
                    print(f"  {gen}:\n    stored {want}\n    new    {got}")
                print("Re-run with --no-check only if the change is intentional.")
                return 1
        stored.update({"judge": judge, "per_generator": result,
                       "granularity": granularity, "dropped_rows": dropped})
    else:
        # Merge per generator so stored extras (e.g. luna_sonnet_spread,
        # formalized in compute_generator_ranking.py) survive the rewrite.
        prev = stored.get("sonnet_lens") or {}
        stored["sonnet_lens"] = {
            gen: {**(prev.get(gen) or {}),
                  "n": len(per_gen[gen]["val_pairs"]),
                  "mae": result[gen]["mae"], "bias": result[gen]["bias"]}
            for gen in result
        }
    OUT.write_text(json.dumps(stored, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"lens={args.lens} judge={judge} dropped={dropped}")
    print(f"cells -> {cells_path.name}; rubric outcomes -> {RUBRIC_OUT.name} "
          f"({len(lens_rows)} rubrics)")
    print(f"granularity: {granularity}")
    print(f"{'generator':45s} rub  cells  repSD    r    MAE   bias")
    for gen, r in sorted(result.items(), key=lambda kv: kv[1]["mae"] or 99):
        print(f"{gen:45s} {r['n_rubrics']:3d} {r['n_cells']:5d} "
              f"{r['repeat_sd_mean'] or '—':>6} {r['validity_r'] or '—':>5} "
              f"{r['mae'] or '—':>5} {r['bias'] or '—':>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
