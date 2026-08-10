#!/usr/bin/env python3
"""RQ2/RQ3 tailored-arm statistics, method-mirrored to the control arm.

Conventions copied from Dataset_ARR/scripts/derive_inter_judge_agreement.py
and derive_paper_exports.derive_judge_repeats so the two arms are comparable:

- One score per (cell, judge); the primary judge (gpt-5.4-mini) enters the
  inter-judge panel with its FIRST pass only (the control arm's mini score
  was a single-pass run). Scores are raw 0-100 (details.total_score).
- within_cell_stdev/spread: population stdev / max-min over the 6 judge
  scores, aggregated as mean/median/min/max over cells with ALL 6 judges.
- judge_repeats: population stdev over the primary judge's 3 passes per
  cell, averaged.
- judge_vs_human: per-pick blind-human pool mean (4 reviews each, from
  Dataset_ARR benchathon_human_grades.json joined via the pick's
  subject_id) vs the judge score; Pearson/Spearman/MAE. Reported for the
  30 annotation picks (control-arm convention) and for all 45.

Inputs: data/interim/judge_results.jsonl (extract_judge_results.py),
        data/interim/picks.json, Dataset_ARR human-grade artifacts.
Output: data/processed/variance_stats.json — fills the "tailored_arm" block
        next to the existing "control_arm" block.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Dataset_ARR"
RESULTS = HERE / "data" / "interim" / "judge_results.jsonl"
PICKS = HERE / "data" / "interim" / "picks.json"
SAMPLE = DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json"
HUMAN_GRADES = DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json"
OUT = HERE / "data" / "processed" / "variance_stats.json"

JUDGES = (
    "gpt-5.4-mini",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "gemini-3.1-pro-preview",
    "deepseek-ai/DeepSeek-V4-Pro",
    "Qwen/Qwen3.5-397B-A17B",
)
PRIMARY = "gpt-5.4-mini"


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def _ranks(vs):
    order = sorted(range(len(vs)), key=lambda i: vs[i])
    ranks = [0.0] * len(vs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(xs, ys):
    return pearson(_ranks(xs), _ranks(ys))


def mae(xs, ys):
    return statistics.mean(abs(x - y) for x, y in zip(xs, ys))


def _agg(xs):
    return {
        "n": len(xs),
        "mean": statistics.mean(xs) if xs else None,
        "median": statistics.median(xs) if xs else None,
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--picks", default=str(PICKS))
    parser.add_argument("--results", default=str(RESULTS))
    parser.add_argument("--block", default="tailored_arm",
                        help="key to write in variance_stats.json")
    args = parser.parse_args()

    picks = json.loads(Path(args.picks).read_text(encoding="utf-8"))["resolved"]
    pick_meta = {p["pick_id"]: p for p in picks}

    # pick_id -> blind-human pool mean (raw 0-100).
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    subject_by_pick = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    grades = json.loads(HUMAN_GRADES.read_text(encoding="utf-8"))
    by_solution = defaultdict(list)
    for g in grades:
        if g.get("raw_score") is not None:
            by_solution[g["solution_id"]].append(float(g["raw_score"]))
    human_mean = {
        pid: statistics.mean(by_solution[sid])
        for pid, sid in subject_by_pick.items()
        if by_solution.get(sid)
    }

    # (pick_id, judge, run_index) -> total_score
    cells: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    errors = []
    for line in Path(args.results).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("total_score") is None:
            errors.append({"pick_id": r.get("pick_id"), "judge": r.get("judge_model_id"),
                           "error": r.get("error")})
            continue
        cells[r["pick_id"]][r["judge_model_id"]][int(r.get("judge_run_index") or 0)] = float(
            r["total_score"]
        )

    # Inter-judge: one score per judge, primary = first pass.
    def judge_score(pid, j):
        runs = cells[pid].get(j) or {}
        if not runs:
            return None
        return runs[min(runs)] if j == PRIMARY else list(runs.values())[0]

    complete = {
        pid: {j: judge_score(pid, j) for j in JUDGES}
        for pid in cells
        if all(judge_score(pid, j) is not None for j in JUDGES)
    }
    stdevs = [statistics.pstdev(list(s.values())) for s in complete.values()]
    spreads = [max(s.values()) - min(s.values()) for s in complete.values()]

    def split(target_type=None, provenance=None):
        pids = [
            pid for pid in complete
            if (target_type is None or pick_meta[pid]["target_type"] == target_type)
            and (provenance is None or pick_meta[pid]["provenance"] == provenance)
        ]
        return {
            "within_cell_stdev": _agg([statistics.pstdev(list(complete[p].values())) for p in pids]),
            "within_cell_spread": _agg([max(complete[p].values()) - min(complete[p].values()) for p in pids]),
        }

    # Repeats: primary judge, 3 passes.
    repeat_stdevs = []
    for pid in cells:
        runs = cells[pid].get(PRIMARY) or {}
        if len(runs) > 1:
            repeat_stdevs.append(statistics.pstdev(list(runs.values())))

    # Validity: judge vs blind human pool mean.
    def validity(pids, score_fn):
        pairs = [(score_fn(p), human_mean[p]) for p in pids if p in human_mean and score_fn(p) is not None]
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        if len(xs) < 2:
            return {"n": len(xs)}
        return {
            "n": len(xs),
            "pearson_raw": pearson(xs, ys),
            "spearman_raw": spearman(xs, ys),
            "mae_raw": mae(xs, ys),
            "judge_mean": statistics.mean(xs),
            "human_mean": statistics.mean(ys),
            "judge_stdev": statistics.pstdev(xs),
            "human_stdev": statistics.pstdev(ys),
        }

    ann_pids = [p for p in complete if pick_meta[p]["target_type"] == "annotation"]
    all_pids = list(complete)

    def primary_first(p):
        return judge_score(p, PRIMARY)

    def primary_mean3(p):
        runs = cells[p].get(PRIMARY) or {}
        return statistics.mean(runs.values()) if runs else None

    def panel_mean(p):
        return statistics.mean(complete[p].values())

    per_judge = {
        j: _agg([complete[p][j] for p in complete]) for j in JUDGES
    }

    tailored = {
        "n_picks_with_all_judges": len(complete),
        "n_picks_total": len(cells),
        "judges": list(JUDGES),
        "primary_judge": PRIMARY,
        "inter_judge": {
            "within_cell_stdev": _agg(stdevs),
            "within_cell_spread": _agg(spreads),
            "by_target_type": {
                "generation": split(target_type="generation"),
                "annotation": split(target_type="annotation"),
            },
        },
        "judge_repeats": {
            "n_cells_with_repeats": len(repeat_stdevs),
            "mean_within_cell_stdev": statistics.mean(repeat_stdevs) if repeat_stdevs else None,
        },
        "judge_vs_human": {
            "annotations_primary_first_pass": validity(ann_pids, primary_first),
            "annotations_primary_mean3": validity(ann_pids, primary_mean3),
            "annotations_panel_mean": validity(ann_pids, panel_mean),
            "all_picks_panel_mean": validity(all_pids, panel_mean),
        },
        "per_judge_stats": per_judge,
        "errors": errors,
    }

    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    doc[args.block] = tailored
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "cells_complete": len(complete),
        "inter_judge_stdev_mean": tailored["inter_judge"]["within_cell_stdev"]["mean"],
        "repeat_stdev_mean": tailored["judge_repeats"]["mean_within_cell_stdev"],
        "validity_ann_panel": tailored["judge_vs_human"]["annotations_panel_mean"],
        "errors": len(errors),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
