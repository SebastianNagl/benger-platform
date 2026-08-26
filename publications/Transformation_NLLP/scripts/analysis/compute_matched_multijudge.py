#!/usr/bin/env python3
"""Multi-judge matched within-judge repeat-SD contrast (lever C, WP C4).

Extends the single-judge matched design to all five capable judges that
have ×3 passes in BOTH instruments: gpt-5.6-luna (existing arms),
claude-sonnet-4-6, gemini-3.1-pro, DeepSeek-V4-Pro, Qwen3.5-397B. Opus-4-7
is excluded (cost). Each judge is paired within itself (tailored − holistic
repeat SD) per cell; the primary endpoint is the pooled mean of per-judge
mean differences with an exam-cluster bootstrap CI, plus per-judge exact
sign tests and Wilcoxon sensitivity.

Tailored ×3 sources:
  luna  -> judge_results_luna.jsonl
  others-> tailored_repeats_flagships.jsonl (rep3/gem3 + sonnet repair)
Holistic ×3 sources:
  luna  -> holistic_results_luna.jsonl
  others-> holistic_results_flagships.jsonl

Each judge pairs at its own tailored-arm temperature (sonnet/DS/Qwen T=0,
gemini+luna T=1); the pairing is within-judge so temperature is held fixed.

Output: data/processed/matched_multijudge.json + significance keys +
console table.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
OUT = HERE / "data" / "processed" / "matched_multijudge.json"
SIG = HERE / "data" / "processed" / "significance.json"

SEED = 20260806
N_BOOT = 10_000

JUDGES = {
    "gpt-5.6-luna": ("judge_results_luna.jsonl", "holistic_results_luna.jsonl"),
    "claude-sonnet-4-6": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "gemini-3.1-pro-preview": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "deepseek-ai/DeepSeek-V4-Pro": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "Qwen/Qwen3.5-397B-A17B": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
}


def load_cells(path, judge):
    """(pick_id) -> {run_index: total} for one judge from a results file."""
    cells = defaultdict(dict)
    for line in (INTERIM / path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("judge_model_id") != judge or r.get("total_score") is None:
            continue
        cells[r["pick_id"]][int(r.get("judge_run_index") or 0)] = float(r["total_score"])
    return cells


def rep_sd(runs):
    return statistics.pstdev(list(runs.values())) if len(runs) > 1 else None


def main() -> int:
    picks = {p["pick_id"]: p for p in json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]}

    # per (judge, pick): tailored & holistic repeat SD
    per_pick = defaultdict(dict)   # pick_id -> {judge: (tail_sd, hol_sd)}
    per_judge_rows = {}
    for judge, (tp, hp) in JUDGES.items():
        tail = load_cells(tp, judge)
        hol = load_cells(hp, judge)
        rows = []
        for pid in picks:
            ts, hs = rep_sd(tail.get(pid) or {}), rep_sd(hol.get(pid) or {})
            if ts is not None and hs is not None:
                per_pick[pid][judge] = (ts, hs)
                rows.append({"pick_id": pid, "task_id": picks[pid]["task_id"],
                             "tailored_sd": ts, "holistic_sd": hs, "diff": ts - hs})
        per_judge_rows[judge] = rows

    # per-judge summary
    def sign_test(diffs):
        lo = sum(1 for d in diffs if d < 0); hi = sum(1 for d in diffs if d > 0)
        n = lo + hi
        p = sps.binomtest(lo, n, 0.5).pvalue if n else None
        return {"n": n, "tailored_lower": lo, "tailored_higher": hi, "p": p}

    def wilcoxon(diffs):
        d = [x for x in diffs if x != 0]
        if len(d) < 5:
            return None
        return {"p": float(sps.wilcoxon(d, method="exact").pvalue), "n_nonzero": len(d)}

    per_judge = {}
    for judge, rows in per_judge_rows.items():
        diffs = [r["diff"] for r in rows]
        per_judge[judge] = {
            "n_cells": len(rows),
            "tailored_mean": statistics.mean(r["tailored_sd"] for r in rows) if rows else None,
            "holistic_mean": statistics.mean(r["holistic_sd"] for r in rows) if rows else None,
            "mean_diff": statistics.mean(diffs) if diffs else None,
            "sign": sign_test(diffs), "wilcoxon": wilcoxon(diffs),
        }

    # Mini (below the execution floor, 2026-08-09): its matched pair comes from
    # matched_stats.json; shown in the forest for completeness but NEVER pooled
    # — the pooled endpoint was pre-registered over the five capable judges.
    mini_rows = []
    matched = json.loads((HERE / "data" / "processed" / "matched_stats.json").read_text())
    for r in matched["per_pick"]:
        ts, hs = r.get("mini_tail_rep_sd"), r.get("mini_holi_rep_sd")
        if ts is not None and hs is not None:
            mini_rows.append({"pick_id": r["pick_id"], "task_id": r["task_id"],
                              "tailored_sd": ts, "holistic_sd": hs, "diff": ts - hs})
    per_judge_rows["gpt-5.4-mini"] = mini_rows
    diffs_m = [r["diff"] for r in mini_rows]
    per_judge["gpt-5.4-mini"] = {
        "n_cells": len(mini_rows),
        "tailored_mean": statistics.mean(r["tailored_sd"] for r in mini_rows),
        "holistic_mean": statistics.mean(r["holistic_sd"] for r in mini_rows),
        "mean_diff": statistics.mean(diffs_m),
        "sign": sign_test(diffs_m), "wilcoxon": wilcoxon(diffs_m),
        "below_floor": True, "excluded_from_pooled": True,
    }

    # pooled: mean of per-judge mean diffs (equal weight per judge),
    # capable judges only (the pre-registered five)
    pooled_point = statistics.mean(v["mean_diff"] for j, v in per_judge.items()
                                   if j in JUDGES)

    # exam-cluster bootstrap: resample exams, recompute per-judge mean diff
    # (over that judge's cells in the drawn exams), then average across judges
    by_exam_judge = defaultdict(lambda: defaultdict(list))
    for judge, rows in per_judge_rows.items():
        for r in rows:
            by_exam_judge[r["task_id"]][judge].append(r["diff"])
    exams = sorted(by_exam_judge)
    rng = np.random.default_rng(SEED)
    pooled_samples = []
    for _ in range(N_BOOT):
        draw = rng.integers(0, len(exams), size=len(exams))
        judge_means = []
        for judge in JUDGES:
            vals = [d for e in draw for d in by_exam_judge[exams[e]].get(judge, [])]
            if vals:
                judge_means.append(statistics.mean(vals))
        if judge_means:
            pooled_samples.append(statistics.mean(judge_means))
    pooled_ci = [float(np.percentile(pooled_samples, 2.5)),
                 float(np.percentile(pooled_samples, 97.5))]

    # Per-judge exam-cluster CIs (2026-08-09, forest panel): same bootstrap,
    # restricted to one judge; a fresh rng per judge keeps the pooled CI above
    # byte-stable and gives every judge the identical exam draws.
    def judge_ci(judge):
        rows = per_judge_rows[judge]
        by_exam = defaultdict(list)
        for r in rows:
            by_exam[r["task_id"]].append(r["diff"])
        exs = sorted(by_exam)
        rng_j = np.random.default_rng(SEED)
        vals = []
        for _ in range(N_BOOT):
            draw = rng_j.integers(0, len(exs), size=len(exs))
            pool = [d for e in draw for d in by_exam[exs[e]]]
            if pool:
                vals.append(statistics.mean(pool))
        return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]

    def exam_level_tests(judge):
        rows = per_judge_rows[judge]
        by_exam = defaultdict(list)
        for r in rows:
            by_exam[r["task_id"]].append(r["diff"])
        em = [statistics.mean(v) for _, v in sorted(by_exam.items())]
        return {"n_exams": len(em), "mean": statistics.mean(em),
                "sign": sign_test(em), "wilcoxon": wilcoxon(em)}

    for judge in per_judge:
        per_judge[judge]["ci95"] = judge_ci(judge)
        per_judge[judge]["exam_level"] = exam_level_tests(judge)

    FOREST_LABELS = {
        "gpt-5.6-luna": "Luna", "claude-sonnet-4-6": "Sonnet",
        "gemini-3.1-pro-preview": "Gemini", "deepseek-ai/DeepSeek-V4-Pro": "DS-Pro",
        "Qwen/Qwen3.5-397B-A17B": "Qwen", "gpt-5.4-mini": "Mini",
    }
    forest = [{"judge": j, "label": FOREST_LABELS[j],
               "delta": per_judge[j]["mean_diff"], "ci95": per_judge[j]["ci95"],
               "n_cells": per_judge[j]["n_cells"], "in_pooled": j in JUDGES}
              for j in ["gpt-5.6-luna", "claude-sonnet-4-6", "gemini-3.1-pro-preview",
                        "deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.5-397B-A17B",
                        "gpt-5.4-mini"]]

    payload = {
        "note": "within-judge tailored-minus-holistic repeat SD; pooled = mean of per-judge "
                "mean diffs, exam-cluster bootstrap 95% CI (seed 20260806, 10k). Negative = "
                "tailored more stable (the pre-registered reduction direction).",
        "judges": list(JUDGES), "opus_excluded_for_cost": True,
        "pooled": {"point": pooled_point, "ci95": pooled_ci,
                   "n_judges": sum(1 for j in per_judge if j in JUDGES)},
        "per_judge": per_judge,
        "forest": forest,
        "forest_note": "per-judge Δ repeat SD (tailored − holistic) with exam-cluster "
                       "bootstrap 95% CIs (seed 20260806, fresh rng per judge, identical "
                       "draws); Mini shown for completeness, excluded from the "
                       "pre-registered pooled endpoint (below the execution floor)",
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    # merge significance keys
    sig = json.loads(SIG.read_text()) if SIG.exists() else {}
    for judge, v in per_judge.items():
        key = "multijudge_" + judge.split("/")[-1].replace("-", "").replace(".", "").lower()
        sig[key + "_matched_repeats"] = {**v["sign"], "mean_diff": v["mean_diff"],
                                         "wilcoxon": v["wilcoxon"]}
    sig["multijudge_pooled"] = payload["pooled"]
    SIG.write_text(json.dumps(sig, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"{'judge':30s} {'n':>3} {'tailored':>9} {'holistic':>9} {'diff':>7} {'sign p':>8} {'wilcox':>7}")
    for judge, v in per_judge.items():
        w = v["wilcoxon"]["p"] if v["wilcoxon"] else float("nan")
        print(f"{judge.split('/')[-1]:30s} {v['n_cells']:>3} {v['tailored_mean']:>9.2f} "
              f"{v['holistic_mean']:>9.2f} {v['mean_diff']:>+7.2f} {v['sign']['p']:>8.3f} {w:>7.3f}")
    print(f"\nPOOLED tailored−holistic repeat SD: {pooled_point:+.3f} "
          f"(95% CI {pooled_ci[0]:+.3f} to {pooled_ci[1]:+.3f}, "
          f"{payload['pooled']['n_judges']} capable judges; Mini shown, not pooled)")
    print(f"-> {OUT.name} + significance keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
