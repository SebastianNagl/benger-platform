#!/usr/bin/env python3
"""Few-shot instrument contrasts (lever A, WP A6).

Primary endpoint: few-shot Luna repeat SD vs the matched holistic-Luna
baseline (2.25) — does an outcome-informed few-shot instrument move the
within-judge repeat variance the zero-shot random draw could not? Also vs
the zero-shot drawn instrument (1.97). Secondaries: Luna/Mini human-score
agreement (r, MAE) vs holistic and zero-shot; Mini floor check (repeat SD,
r under few-shot). Exam-cluster bootstrap CIs + paired sign tests.

Inputs (few-shot judgments extracted by extract_judge_results with the
fewshot run log):
  data/interim/fewshot_results_luna.jsonl, fewshot_results_mini.jsonl
Baselines (existing):
  matched holistic: data/processed/matched_stats.json (per_pick)
  zero-shot drawn:  data/interim/judge_results_luna.jsonl (Luna),
                    judge_results_temp0.jsonl (Mini)
Output: data/processed/fewshot_stats.json + significance keys.
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
DATASET_ARR = HERE.parent / "Dataset_ARR"
OUT = HERE / "data" / "processed" / "fewshot_stats.json"
SIG = HERE / "data" / "processed" / "significance.json"
SEED = 20260806
N_BOOT = 10_000
LUNA, MINI = "gpt-5.6-luna", "gpt-5.4-mini"


def load(path, judge):
    cells = defaultdict(dict)
    for line in (INTERIM / path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("judge_model_id") != judge or r.get("total_score") is None:
            continue
        cells[r["pick_id"]][int(r.get("judge_run_index") or 0)] = float(r["total_score"])
    return cells


def rep_sd(runs):
    return statistics.pstdev(list(runs.values())) if len(runs) > 1 else None


def first(runs):
    return runs[min(runs)] if runs else None


def main() -> int:
    picks = {p["pick_id"]: p for p in json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]}
    # human pool
    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}
    ann = [p for p in picks if picks[p]["target_type"] == "annotation" and p in hmean]

    fs_luna = load("fewshot_results_luna.jsonl", LUNA)
    fs_mini = load("fewshot_results_mini.jsonl", MINI)
    zs_luna = load("judge_results_luna.jsonl", LUNA)
    zs_mini = load("judge_results_temp0.jsonl", MINI)
    # holistic-luna repeat SD per pick from matched_stats per_pick
    matched = {r["pick_id"]: r for r in json.loads((HERE / "data" / "processed" / "matched_stats.json").read_text())["per_pick"]}

    def pearson(xs, ys):
        if len(xs) < 3:
            return None
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5; dy = sum((y - my) ** 2 for y in ys) ** 0.5
        return num / (dx * dy) if dx and dy else None

    def validity(cells):
        pairs = [(first(cells[p]), hmean[p]) for p in ann if cells.get(p)]
        pairs = [(a, b) for a, b in pairs if a is not None]
        return {"n": len(pairs), "r": pearson([a for a, _ in pairs], [b for _, b in pairs]),
                "mae": statistics.mean(abs(a - b) for a, b in pairs) if pairs else None}

    # per-pick repeat SD table for the contrasts
    rows = []
    for pid in sorted(picks):
        rows.append({
            "pick_id": pid, "task_id": picks[pid]["task_id"],
            "fs_luna_sd": rep_sd(fs_luna.get(pid) or {}),
            "fs_mini_sd": rep_sd(fs_mini.get(pid) or {}),
            "zs_luna_sd": rep_sd(zs_luna.get(pid) or {}),
            "zs_mini_sd": rep_sd(zs_mini.get(pid) or {}),
            "hol_luna_sd": (matched.get(pid) or {}).get("luna_holi_rep_sd"),
            "hol_mini_sd": (matched.get(pid) or {}).get("mini_holi_rep_sd"),
        })
    by_exam = defaultdict(list)
    for r in rows:
        by_exam[r["task_id"]].append(r)
    exams = sorted(by_exam)

    def diffs(a, b, subset=None):
        rs = subset if subset is not None else rows
        return [r[a] - r[b] for r in rs if r.get(a) is not None and r.get(b) is not None]

    def sign(d):
        lo = sum(1 for x in d if x < 0); hi = sum(1 for x in d if x > 0); n = lo + hi
        return {"n": n, "a_lower": lo, "a_higher": hi,
                "p": sps.binomtest(lo, n, 0.5).pvalue if n else None,
                "mean_diff": statistics.mean(d) if d else None}

    def boot(a, b):
        rng = np.random.default_rng(SEED)
        vals = []
        for _ in range(N_BOOT):
            draw = rng.integers(0, len(exams), size=len(exams))
            dd = [x for e in draw for x in diffs(a, b, by_exam[exams[e]])]
            if dd:
                vals.append(statistics.mean(dd))
        return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else [None, None]

    contrasts = {}
    for name, a, b in [
        ("luna_fewshot_vs_holistic", "fs_luna_sd", "hol_luna_sd"),
        ("luna_fewshot_vs_zeroshot", "fs_luna_sd", "zs_luna_sd"),
        ("mini_fewshot_vs_holistic", "fs_mini_sd", "hol_mini_sd"),
        ("mini_fewshot_vs_zeroshot", "fs_mini_sd", "zs_mini_sd"),
    ]:
        d = diffs(a, b)
        contrasts[name] = {**sign(d), "ci95": boot(a, b),
                           "mean_a": statistics.mean(r[a] for r in rows if r.get(a) is not None),
                           "mean_b": statistics.mean(r[b] for r in rows if r.get(b) is not None)}

    # per-generator few-shot Luna repeat SD (which sources yield stable
    # few-shot instruments — the best-generator headroom)
    sel = {s["task_id"]: s for s in json.loads((INTERIM / "fewshot" / "selection.json").read_text())["selection"]}
    per_gen = defaultdict(list)
    for pid, runs in fs_luna.items():
        if len(runs) > 1 and picks[pid]["task_id"] in sel:
            g = sel[picks[pid]["task_id"]]["generator_model_id"]
            per_gen[g].append(statistics.pstdev(list(runs.values())))
    per_generator = {g.split("/")[-1]: round(statistics.mean(v), 2)
                     for g, v in sorted(per_gen.items(), key=lambda kv: statistics.mean(kv[1]))}

    # compliance recovery vs zero-shot (from the two sweep logs)
    def compliance(log):
        c = defaultdict(lambda: [0, 0])
        for line in (INTERIM / log).read_text().splitlines():
            r = json.loads(line)
            c[r["generator_model_id"].split("/")[-1]][0] += 1
            if r["outcome"] == "completed":
                c[r["generator_model_id"].split("/")[-1]][1] += 1
        return {g: {"valid": ok, "total": n} for g, (n, ok) in c.items()}
    fs_comp = compliance("rubric_sweep_log.fewshot.jsonl")

    payload = {
        "note": "few-shot repeat SD contrasts; negative diff = few-shot more stable. "
                "exam-cluster bootstrap 95% CI (seed 20260806, 10k), paired sign tests.",
        "repeat_sd_contrasts": contrasts,
        "validity": {
            "fewshot_luna": validity(fs_luna), "fewshot_mini": validity(fs_mini),
            "zeroshot_luna": validity(zs_luna), "zeroshot_mini": validity(zs_mini),
        },
        "means": {"fewshot_luna_repeat_sd": statistics.mean(r["fs_luna_sd"] for r in rows if r["fs_luna_sd"] is not None),
                  "fewshot_mini_repeat_sd": statistics.mean(r["fs_mini_sd"] for r in rows if r["fs_mini_sd"] is not None)},
        "per_generator_repeat_sd": per_generator,
        "compliance_fewshot": fs_comp,
        "compliance_zeroshot": {"gpt-5.4-mini": {"valid": 8, "total": 15}},
        "p01": {"fewshot_luna": {k: fs_luna.get("P01", {}).get(k) for k in (0, 1, 2)},
                "fewshot_mini": {k: fs_mini.get("P01", {}).get(k) for k in (0, 1, 2)}},
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    sig = json.loads(SIG.read_text()) if SIG.exists() else {}
    for name, c in contrasts.items():
        sig[f"fewshot_{name}"] = {k: c[k] for k in ("n", "a_lower", "a_higher", "p", "mean_diff", "ci95")}
    SIG.write_text(json.dumps(sig, indent=1, ensure_ascii=False), encoding="utf-8")

    print("repeat-SD contrasts (few-shot vs baseline):")
    for name, c in contrasts.items():
        print(f"  {name:32s} {c['mean_a']:.2f} vs {c['mean_b']:.2f}  "
              f"diff {c['mean_diff']:+.2f} CI[{c['ci95'][0]:+.2f},{c['ci95'][1]:+.2f}] p={c['p']:.3f}")
    print("agreement (first pass vs human pool):")
    for k, v in payload["validity"].items():
        print(f"  {k:16s} r={v['r']:.3f} MAE={v['mae']:.1f} (n={v['n']})")
    print(f"-> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
