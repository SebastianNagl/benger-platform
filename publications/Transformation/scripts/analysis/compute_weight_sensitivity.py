#!/usr/bin/env python3
"""Do the generated step weights matter? Post-hoc re-weighting.

Every tailored judgment stores a per-step score and maximum. Re-aggregating
the stored fractions (score / max) under other weight schemes shows how much
the generated point allocation contributes to agreement with the blind-human
pool and to repeat stability, without new judge calls:

  actual          the apportioned points (reproduces the published totals)
  model_weights   the model's unrounded relative weights
  class_only      1 / 2 / 3 for routine / tragend / schwerpunkt
  uniform         every step counts the same
  sqrt_points     compressed allocation (square root of the points)
  permuted        the rubric's own points shuffled across its steps
                  (200 permutations, fixed seed)

Caveat: the judge scored each step while seeing its actual maximum, so the
fractions are conditional on the actual allocation.

Anchor: the actual scheme must reproduce Luna's published first-pass r .769,
MAE 12.8 and repeat SD 1.96; ``--check`` exits non-zero otherwise.

Inputs: judge_results_luna.jsonl, tailored_repeats_flagships.jsonl,
        judge_results_temp0.jsonl, clone_d6_actives.json, picks_temp0.json,
        data/raw/local/task_rubrics.json (all withheld), Benchmark_EMNLP
        human pool.
Output: data/processed/weight_sensitivity.json
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
INTERIM = HERE / "data" / "interim"
RAW = HERE / "data" / "raw" / "local" / "task_rubrics.json"
OUT = HERE / "data" / "processed" / "weight_sensitivity.json"
FILES = ("judge_results_luna.jsonl", "tailored_repeats_flagships.jsonl",
         "judge_results_temp0.jsonl")
CLASS_WEIGHT = {"routine": 1.0, "tragend": 2.0, "schwerpunkt": 3.0}
ANCHOR = ("gpt-5.6-luna", 0.769, 12.8, 1.96)
N_PERMUTATIONS = 200


def pearson(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return num / den if den else float("nan")


def step_tables():
    """criteria key set -> {key: {pts, weight, cls}} for every derived rubric."""
    tables = {}
    for r in json.loads(RAW.read_text()):
        gm = r.get("generation_metadata") or {}
        if not gm.get("derived_document"):
            continue
        by_sid = {s["id"]: s for a in gm["full_document"]["abschnitte"] for s in a["schritte"]}
        derived = {s["id"]: s for a in gm["derived_document"]["abschnitte"] for s in a["schritte"]}
        info = {}
        for sid, key in gm["key_by_step_id"].items():
            if sid in by_sid:
                info[key] = {"pts": float(derived[sid]["max_punkte"]),
                             "weight": float(by_sid[sid]["gewicht"]),
                             "cls": by_sid[sid]["gewichtungsklasse"]}
        tables[frozenset(r["criteria"])] = info
    return tables


def human_means():
    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    grades = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            grades[g["solution_id"]].append(float(g["raw_score"]))
    return {pid: statistics.mean(grades[s]) for pid, s in subj.items() if grades.get(s)}


def load_cells(actives):
    """(judge, pick) -> {run_index: row}; D6-active rubric only, latest row wins."""
    cells = defaultdict(dict)
    for name in FILES:
        for line in (INTERIM / name).read_text().splitlines():
            row = json.loads(line)
            if not row.get("scores") or row.get("error"):
                continue
            if actives.get(row["task_id"]) != row["rubric_id"]:
                continue
            run = int(row.get("judge_run_index") or 0)
            key = (row["judge_model_id"], row["pick_id"])
            prev = cells[key].get(run)
            if prev is None or row["created_at"] > prev["created_at"]:
                cells[key][run] = row
    return cells


def total(row, weight_of):
    num = den = 0.0
    for key, v in row["scores"].items():
        mx = float(v["max"]) or 1.0
        wt = weight_of(key)
        num += wt * min(max(float(v["score"]), 0.0), mx) / mx
        den += wt
    return 100.0 * num / den


def evaluate(judge_cells, weight_for_row, hmean, ann):
    firsts, sds = [], []
    for pick, runs in judge_cells.items():
        totals = {i: total(r, weight_for_row(r)) for i, r in runs.items()}
        if 0 in totals and pick in hmean and pick in ann:
            firsts.append((totals[0], hmean[pick]))
        if len(totals) >= 3:
            sds.append(statistics.pstdev(list(totals.values())))
    xs = [a for a, _ in firsts]
    ys = [b for _, b in firsts]
    return {"n": len(xs),
            "r": pearson(xs, ys) if len(xs) > 3 else None,
            "mae": statistics.mean(abs(a - b) for a, b in firsts) if firsts else None,
            "repeat_sd": statistics.mean(sds) if sds else None,
            "n_repeat_cells": len(sds)}


def main() -> int:
    check = "--check" in sys.argv
    tables = step_tables()
    hmean = human_means()
    picks = json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]
    ann = {p["pick_id"] for p in picks if p["target_type"] == "annotation"}
    actives = json.loads((INTERIM / "clone_d6_actives.json").read_text())
    cells = load_cells(actives)

    def info(row):
        found = tables.get(frozenset(row["scores"]))
        if found is None:
            raise SystemExit(f"no rubric matches the step keys of {row['pick_id']}")
        return found

    schemes = {
        "actual": lambda s: s["pts"],
        "model_weights": lambda s: s["weight"],
        "class_only": lambda s: CLASS_WEIGHT[s["cls"]],
        "uniform": lambda s: 1.0,
        "sqrt_points": lambda s: math.sqrt(s["pts"]),
    }
    result = {}
    for judge in sorted({j for j, _ in cells}):
        jc = {p: runs for (j, p), runs in cells.items() if j == judge}
        out = {}
        for name, fn in schemes.items():
            out[name] = evaluate(jc, lambda row, fn=fn: (lambda k, t=info(row): fn(t[k])), hmean, ann)
        rnd = random.Random(20260926)
        perm_r, perm_sd = [], []
        for _ in range(N_PERMUTATIONS):
            shuffled = {}

            def weight_for_row(row):
                t = info(row)
                key = id(t)
                if key not in shuffled:
                    vals = [t[k]["pts"] for k in t]
                    rnd.shuffle(vals)
                    shuffled[key] = dict(zip(t, vals))
                return lambda k, m=shuffled[key]: m[k]

            res = evaluate(jc, weight_for_row, hmean, ann)
            if res["r"] is not None:
                perm_r.append(res["r"])
            if res["repeat_sd"] is not None:
                perm_sd.append(res["repeat_sd"])
        perm_r.sort()
        perm_sd.sort()
        actual_r = out["actual"]["r"]
        out["permuted"] = {
            "r_median": statistics.median(perm_r) if perm_r else None,
            "r_ci95": [perm_r[int(0.025 * len(perm_r))], perm_r[int(0.975 * len(perm_r)) - 1]] if perm_r else None,
            "share_of_permutations_below_actual_r": (sum(1 for x in perm_r if x < actual_r) / len(perm_r))
            if perm_r and actual_r is not None else None,
            "repeat_sd_median": statistics.median(perm_sd) if perm_sd else None,
        }
        result[judge] = out

    rounded = json.loads(json.dumps(result), parse_float=lambda x: round(float(x), 4))
    OUT.write_text(json.dumps({
        "note": "Post-hoc re-weighting of stored per-step tailored scores (D6-active rubrics). "
                "r/MAE: first pass vs blind-human pool mean, annotation picks; repeat_sd: "
                "population SD over >=3 passes, mean over cells.",
        "per_judge": rounded}, indent=1) + "\n")

    for judge, out in result.items():
        print(f"== {judge}")
        for name, m in out.items():
            if name == "permuted":
                print(f"  {'permuted (200x)':15s} r median {m['r_median']:.3f} "
                      f"[{m['r_ci95'][0]:.3f}, {m['r_ci95'][1]:.3f}], actual beats "
                      f"{m['share_of_permutations_below_actual_r']:.0%}")
            else:
                print(f"  {name:15s} n={m['n']:2d} r={m['r']:.3f} MAE={m['mae']:5.1f} "
                      f"repeatSD={m['repeat_sd']:.2f}")
    judge, r0, mae0, sd0 = ANCHOR
    a = result[judge]["actual"]
    ok = round(a["r"], 3) == r0 and round(a["mae"], 1) == mae0 and round(a["repeat_sd"], 2) == sd0
    print(f"anchor {judge}: r {a['r']:.3f} MAE {a['mae']:.1f} SD {a['repeat_sd']:.2f} -> "
          f"{'OK' if ok else 'MISMATCH'}")
    print(f"-> {OUT.relative_to(HERE)}")
    return 1 if (check and not ok) else 0


if __name__ == "__main__":
    raise SystemExit(main())
