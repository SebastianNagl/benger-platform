#!/usr/bin/env python3
"""Significance tests + exam-level cluster bootstrap (WP3.1).

Formalizes the previously script-less significance.json (three exact
two-sided binomial sign tests) and extends it with the matched same-judge
contrasts, Clopper-Pearson CIs on every sign proportion, Wilcoxon
sensitivity checks, and an exam-level cluster bootstrap for the central
differences. The 45 solutions are 15 exams × 3 provenances — cells within
an exam share the rubric, the exam's difficulty, and any judge×exam
interaction, so resampling happens at the exam level (15 clusters drawn
with replacement, all cells of a drawn exam enter together).

Also emits reliability_conditions.json — the body table's source: one row
per (instrument × primary judge) condition with inter-judge panel SD,
repeat SD, human-pool agreement, MAE, and the P01 probe scores. Panel
means use the 43 cells with complete data in every panel definition
(control claude-opus-4-7 is missing on P25/P28); repeat/agreement columns
use their full n.

Inputs: data/processed/matched_stats.json (per_pick; compute_matched_contrasts.py)
        data/processed/significance.json (regression reference, if present)
        data/interim/fewshot_results_{luna,mini}.jsonl (lever A per-pass rows)
        data/processed/rubric_outcomes.json (oracle floor, luna lens)
        ../Benchmark_EMNLP/data/... (blind-only sensitivity pool)
Usage:  uv run python scripts/analysis/compute_significance.py [--check-only]
Output: data/processed/significance.json (superset, legacy keys byte-stable)
        data/processed/bootstrap_cis.json
        data/processed/reliability_conditions.json
        data/processed/agreement_bias.json
        data/processed/trend_figure_data.json (script-written since 2026-08-09;
        previously hand-maintained)

Revision 2026-08-09 (reviewer round 2, DESIGN.md log): agreement contrasts
(stat_mae_diff / stat_r_diff) are now computed on the 30 annotation cells —
the same basis as every table's r/MAE — instead of all 45 cells; the
previously published +6.7 for the Mini MAE contrast was the 45-cell value.
Legacy sign-test keys remain byte-stable.
"""

from __future__ import annotations

import argparse
import json
import statistics
import warnings
from pathlib import Path

import numpy as np
import scipy
from scipy import stats as sps

HERE = Path(__file__).resolve().parent.parent.parent
PROCESSED = HERE / "data" / "processed"
INTERIM = HERE / "data" / "interim"
DATASET = HERE.parent / "Benchmark_EMNLP"
MATCHED = PROCESSED / "matched_stats.json"
SIG_OUT = PROCESSED / "significance.json"
BOOT_OUT = PROCESSED / "bootstrap_cis.json"
COND_OUT = PROCESSED / "reliability_conditions.json"
BIAS_OUT = PROCESSED / "agreement_bias.json"
TREND_OUT = PROCESSED / "trend_figure_data.json"

SEED = 20260806
N_BOOT = 10_000


def sign_test(diffs, direction="lower"):
    """Exact two-sided binomial sign test on paired differences (ties dropped).

    direction='lower' reports k = #(a < b); 'higher' reports k = #(a > b) —
    matching the legacy significance.json key shapes.
    """
    lower = sum(1 for d in diffs if d < 0)
    higher = sum(1 for d in diffs if d > 0)
    n = lower + higher
    k = lower if direction == "lower" else higher
    p = sps.binomtest(k, n, 0.5).pvalue if n else None
    lo, hi = (sps.binomtest(k, n, 0.5).proportion_ci(0.95, method="exact")
              if n else (None, None))
    out = {direction: k, "n": n, "p": p,
           "prop_ci95": [lo, hi] if n else None}
    return out


def wilcoxon_sens(diffs):
    d = [x for x in diffs if x != 0]
    if len(d) < 5:
        return None
    method = "exact"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            res = sps.wilcoxon(d, method="exact")
    except Exception:
        method = "approx"
        res = sps.wilcoxon(d, method="approx", correction=True)
    return {"p": float(res.pvalue), "method": method, "n_nonzero": len(d),
            "scipy": scipy.__version__}


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
    parser.add_argument("--check-only", action="store_true",
                        help="Only verify the legacy sign tests reproduce; write nothing")
    args = parser.parse_args()

    per_pick = json.loads(MATCHED.read_text())["per_pick"]

    # Few-shot (lever A) per-pass rows: augment per_pick in place with the
    # judge-first-pass score and the 3-pass population SD, per primary.
    def _load_fs(path, prefix):
        by_pick = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("total_score") is None:
                continue
            by_pick.setdefault(r["pick_id"], {})[int(r["judge_run_index"] or 0)] = float(r["total_score"])
        for row in per_pick:
            runs = by_pick.get(row["pick_id"])
            if not runs:
                continue
            if 0 in runs:
                row[f"{prefix}_fs_first"] = runs[0]
            if len(runs) >= 2:
                row[f"{prefix}_fs_rep_sd"] = statistics.pstdev(list(runs.values()))
        return by_pick

    fs_luna = _load_fs(INTERIM / "fewshot_results_luna.jsonl", "luna")
    fs_mini = _load_fs(INTERIM / "fewshot_results_mini.jsonl", "mini")
    assert len(fs_luna) == 45 and len(fs_mini) == 45, "few-shot coverage incomplete"

    by_exam = {}
    for r in per_pick:
        by_exam.setdefault(r["task_id"], []).append(r)
    exams = sorted(by_exam)
    assert len(exams) == 15, f"expected 15 exam clusters, got {len(exams)}"

    def pairs(rows, a, b):
        return [(r[a], r[b]) for r in rows if r.get(a) is not None and r.get(b) is not None]

    def diffs(rows, a, b):
        return [x - y for x, y in pairs(rows, a, b)]

    # ---------- legacy sign tests (must reproduce bit-for-bit) ----------
    legacy = {
        "luna_panel_sign": sign_test(diffs(per_pick, "panel_tail_luna", "panel_ctrl_mini"), "lower"),
        "luna_repeats_sign": sign_test(diffs(per_pick, "luna_tail_rep_sd", "control_gpt5mini_rep_sd"), "lower"),
        "mini_panel_sign": sign_test(diffs(per_pick, "panel_tail_mini", "panel_ctrl_mini"), "higher"),
    }
    legacy["luna_repeats_sign"]["mean_diff"] = statistics.mean(
        diffs(per_pick, "luna_tail_rep_sd", "control_gpt5mini_rep_sd"))

    stored = json.loads(SIG_OUT.read_text()) if SIG_OUT.exists() else {}
    problems = []
    for key in ("luna_panel_sign", "luna_repeats_sign", "mini_panel_sign"):
        if key not in stored:
            continue
        for f, want in stored[key].items():
            got = legacy[key].get(f)
            ok = (abs(got - want) < 1e-12) if isinstance(want, float) else (got == want)
            if not ok:
                problems.append(f"{key}.{f}: stored {want} vs regenerated {got}")
    if problems:
        print("LEGACY REGRESSION FAILED:")
        for p in problems:
            print(" ", p)
        return 1
    print("legacy sign tests reproduce bit-for-bit"
          if stored else "no stored significance.json — first run")
    if args.check_only:
        return 0

    # ---------- matched same-judge tests ----------
    matched = {
        "luna_matched_repeats_sign": sign_test(diffs(per_pick, "luna_tail_rep_sd", "luna_holi_rep_sd"), "lower"),
        "mini_matched_repeats_sign": sign_test(diffs(per_pick, "mini_tail_rep_sd", "mini_holi_rep_sd"), "lower"),
        "luna_matched_panel_sign": sign_test(diffs(per_pick, "panel_tail_luna", "panel_hol_luna"), "lower"),
    }
    for key, (a, b) in {
        "luna_matched_repeats_sign": ("luna_tail_rep_sd", "luna_holi_rep_sd"),
        "mini_matched_repeats_sign": ("mini_tail_rep_sd", "mini_holi_rep_sd"),
        "luna_matched_panel_sign": ("panel_tail_luna", "panel_hol_luna"),
    }.items():
        d = diffs(per_pick, a, b)
        matched[key]["mean_diff"] = statistics.mean(d)
        matched[key]["wilcoxon"] = wilcoxon_sens(d)

    # Cluster-robust sensitivity (2026-08-09): the cell-level sign/Wilcoxon
    # treat the 45 solutions as exchangeable, ignoring exam clustering (3
    # cells share rubric, difficulty, and any judge×exam interaction).
    # Aggregate the paired diff to one mean per exam and test the 15 values.
    def exam_level(a, b):
        em = []
        for e in exams:
            d = diffs(by_exam[e], a, b)
            if d:
                em.append(statistics.mean(d))
        return {"n_exams": len(em), "mean": statistics.mean(em),
                "sign": sign_test(em, "lower"), "wilcoxon": wilcoxon_sens(em)}

    for key, (a, b) in {
        "luna_matched_repeats_sign": ("luna_tail_rep_sd", "luna_holi_rep_sd"),
        "mini_matched_repeats_sign": ("mini_tail_rep_sd", "mini_holi_rep_sd"),
    }.items():
        matched[key]["exam_level"] = exam_level(a, b)

    # Few-shot repeat contrast (lever A), formalized here so the body's
    # Wilcoxon is JSON-sourced (it was a hardcoded literal before 2026-08-09).
    fs_d = diffs(per_pick, "luna_fs_rep_sd", "luna_holi_rep_sd")
    matched["luna_fewshot_repeats"] = {
        **sign_test(fs_d, "lower"),
        "mean_diff": statistics.mean(fs_d),
        "wilcoxon": wilcoxon_sens(fs_d),
        "wilcoxon_note": "not pre-registered (sign test + cluster CI were); sensitivity only",
        "exam_level": exam_level("luna_fs_rep_sd", "luna_holi_rep_sd"),
    }

    sig = {**stored, **legacy, **matched,
           "note": "exact two-sided binomial sign tests; prop_ci95 = Clopper-Pearson; "
                   "wilcoxon = sensitivity on nonzero diffs; generated by compute_significance.py"}
    SIG_OUT.write_text(json.dumps(sig, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------- exam-level cluster bootstrap ----------
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(exams), size=(N_BOOT, len(exams)))

    def stat_mean_diff(rows, a, b):
        d = diffs(rows, a, b)
        return statistics.mean(d) if d else None

    def _agree_pairs(rows, key):
        # Agreement basis (2026-08-09): the 30 annotation cells only — the same
        # basis as every reported r/MAE. Model-generated solutions carry human
        # grades too, but tables and the prior study anchor on human-authored
        # submissions; mixing bases produced the published +6.7-vs-8.2 clash.
        return [(r[key], r["human_mean"]) for r in rows
                if r.get(key) is not None and r.get("human_mean") is not None
                and r.get("target_type") == "annotation"]

    def stat_mae_diff(rows, a, b):
        pa, pb = _agree_pairs(rows, a), _agree_pairs(rows, b)
        if not pa or not pb:
            return None
        return (statistics.mean(abs(x - h) for x, h in pa)
                - statistics.mean(abs(x - h) for x, h in pb))

    def stat_r_diff(rows, a, b):
        pa, pb = _agree_pairs(rows, a), _agree_pairs(rows, b)
        ra = pearson([x for x, _ in pa], [h for _, h in pa])
        rb = pearson([x for x, _ in pb], [h for _, h in pb])
        return ra - rb if ra is not None and rb is not None else None

    CONTRASTS = {
        # matched, same judge: tailored − holistic
        "repeat_sd_luna_tailored_minus_holistic": lambda rows: stat_mean_diff(rows, "luna_tail_rep_sd", "luna_holi_rep_sd"),
        "repeat_sd_mini_tailored_minus_holistic": lambda rows: stat_mean_diff(rows, "mini_tail_rep_sd", "mini_holi_rep_sd"),
        "panel_sd_luna_tailored_minus_holistic": lambda rows: stat_mean_diff(rows, "panel_tail_luna", "panel_hol_luna"),
        # legacy cross-judge contrasts (kept for continuity)
        "repeat_sd_luna_tailored_minus_control_gpt5mini": lambda rows: stat_mean_diff(rows, "luna_tail_rep_sd", "control_gpt5mini_rep_sd"),
        "panel_sd_luna_tailored_minus_control": lambda rows: stat_mean_diff(rows, "panel_tail_luna", "panel_ctrl_mini"),
        "panel_sd_mini_tailored_minus_control": lambda rows: stat_mean_diff(rows, "panel_tail_mini", "panel_ctrl_mini"),
        # agreement: tailored − holistic (negative MAE diff = tailored better)
        "mae_luna_tailored_minus_holistic": lambda rows: stat_mae_diff(rows, "luna_tail_first", "luna_holi_first"),
        "mae_mini_tailored_minus_holistic": lambda rows: stat_mae_diff(rows, "mini_tail_first", "mini_holi_first"),
        "r_luna_tailored_minus_holistic": lambda rows: stat_r_diff(rows, "luna_tail_first", "luna_holi_first"),
        "r_mini_tailored_minus_holistic": lambda rows: stat_r_diff(rows, "mini_tail_first", "mini_holi_first"),
        # agreement: few-shot arms (lever A)
        "mae_luna_fewshot_minus_holistic": lambda rows: stat_mae_diff(rows, "luna_fs_first", "luna_holi_first"),
        "mae_luna_fewshot_minus_tailored": lambda rows: stat_mae_diff(rows, "luna_fs_first", "luna_tail_first"),
        "r_luna_fewshot_minus_holistic": lambda rows: stat_r_diff(rows, "luna_fs_first", "luna_holi_first"),
        "r_luna_fewshot_minus_tailored": lambda rows: stat_r_diff(rows, "luna_fs_first", "luna_tail_first"),
        "mae_mini_fewshot_minus_holistic": lambda rows: stat_mae_diff(rows, "mini_fs_first", "mini_holi_first"),
        "r_mini_fewshot_minus_holistic": lambda rows: stat_r_diff(rows, "mini_fs_first", "mini_holi_first"),
    }

    boot = {}
    for name, fn in CONTRASTS.items():
        point = fn(per_pick)
        vals = []
        for i in range(N_BOOT):
            rows = []
            for e in draws[i]:
                rows.extend(by_exam[exams[e]])
            v = fn(rows)
            if v is not None:
                vals.append(v)
        lo, hi = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (None, None)
        boot[name] = {"point": point, "ci95": [lo, hi], "n_boot_valid": len(vals)}
        print(f"boot {name}: {point:+.3f} [{lo:+.3f}, {hi:+.3f}]")

    # SD- vs variance-scale framing of the two headline repeat contrasts.
    def sd_var_framing(a_key, b_key):
        a = [r[a_key] for r in per_pick if r.get(a_key) is not None]
        b = [r[b_key] for r in per_pick if r.get(b_key) is not None]
        ma, mb = statistics.mean(a), statistics.mean(b)
        return {"mean_a": ma, "mean_b": mb,
                "sd_change_pct": (ma - mb) / mb * 100.0,
                "variance_change_pct": (ma ** 2 - mb ** 2) / (mb ** 2) * 100.0}

    framing = {
        "luna_tailored_vs_luna_holistic": sd_var_framing("luna_tail_rep_sd", "luna_holi_rep_sd"),
        "luna_tailored_vs_control_gpt5mini": sd_var_framing("luna_tail_rep_sd", "control_gpt5mini_rep_sd"),
        "mini_tailored_vs_mini_holistic": sd_var_framing("mini_tail_rep_sd", "mini_holi_rep_sd"),
    }

    BOOT_OUT.write_text(json.dumps(
        {"seed": SEED, "n_boot": N_BOOT, "n_clusters": len(exams),
         "method": "exam-level cluster bootstrap, percentile 95% CI",
         "agreement_basis": "30 annotation cells (since 2026-08-09; previously all 45)",
         "contrasts": boot, "sd_vs_variance_framing": framing},
        indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------- signed bias + LOEO-calibrated MAE (2026-08-09) ----------
    ann_rows = [r for r in per_pick if r.get("target_type") == "annotation"
                and r.get("human_mean") is not None]
    assert len(ann_rows) == 30, f"expected 30 annotation cells, got {len(ann_rows)}"

    def bias_block(key):
        cells = [(r["task_id"], r[key] - r["human_mean"]) for r in ann_rows
                 if r.get(key) is not None]
        if not cells:
            return None
        bias = statistics.mean(e for _, e in cells)
        mae = statistics.mean(abs(e) for _, e in cells)
        cal = []
        for e_id in sorted({t for t, _ in cells}):
            others = [err for t, err in cells if t != e_id]
            b_e = statistics.mean(others)
            cal.extend(abs(err - b_e) for t, err in cells if t == e_id)
        return {"n": len(cells), "bias": bias, "mae": mae,
                "mae_loeo_calibrated": statistics.mean(cal)}

    ARM_KEYS = {
        "holistic_luna": "luna_holi_first", "tailored_luna": "luna_tail_first",
        "fewshot_luna": "luna_fs_first", "holistic_mini": "mini_holi_first",
        "tailored_mini": "mini_tail_first", "fewshot_mini": "mini_fs_first",
    }
    bias_per_condition = {cond: bias_block(key) for cond, key in ARM_KEYS.items()}

    # Control primary (GPT-5 Mini, repeat pass 0), same 30-cell basis.
    ctrl_rows = [json.loads(l) for l in
                 (INTERIM / "control_results_temp0.jsonl").read_text().splitlines()]
    ctrl_first = {r["pick_id"]: float(r["score"]) for r in ctrl_rows
                  if r["repeat_run"] and int(r["run_index"] or 0) == 0}
    for r in per_pick:
        if r["pick_id"] in ctrl_first:
            r["ctrl_gpt5mini_first"] = ctrl_first[r["pick_id"]]
    bias_per_condition["holistic_control"] = bias_block("ctrl_gpt5mini_first")

    # Blind-only sensitivity: the paper's human anchor is the 4-grader pool
    # (3 blind + the exam creator); the prior study's agreement protocol was
    # blind-only. Recompute r/MAE per condition against the blind-only mean.
    def blind_pool_means():
        sample = json.loads((DATASET / "data" / "interim" /
                             "benchathon_human_grading_sample.json").read_text())
        grades = json.loads((DATASET / "data" / "processed" /
                             "benchathon_human_grades.json").read_text())
        pick_rows = sample["picks"] if isinstance(sample, dict) else sample
        sol_of = {p["pick_id"]: p["subject_id"] for p in pick_rows}
        by_sol = {}
        for g in grades:
            if g.get("role") == "blind" and g.get("raw_score") is not None:
                by_sol.setdefault(g["solution_id"], []).append(float(g["raw_score"]))
        return {pid: statistics.mean(by_sol[sid]) for pid, sid in sol_of.items()
                if sid in by_sol}

    blind_sensitivity = {}
    try:
        blind_mean = blind_pool_means()
        for cond, key in {**ARM_KEYS, "holistic_control": "ctrl_gpt5mini_first"}.items():
            pairs_b = [(r[key], blind_mean[r["pick_id"]]) for r in ann_rows
                       if r.get(key) is not None and r["pick_id"] in blind_mean]
            if len(pairs_b) < 3:
                continue
            blind_sensitivity[cond] = {
                "n": len(pairs_b),
                "pearson": pearson([x for x, _ in pairs_b], [h for _, h in pairs_b]),
                "mae": statistics.mean(abs(x - h) for x, h in pairs_b),
                "bias": statistics.mean(x - h for x, h in pairs_b),
            }
    except FileNotFoundError as exc:
        blind_sensitivity = {"error": f"dataset repo files not found: {exc}"}

    BIAS_OUT.write_text(json.dumps(
        {"basis": "first pass vs 4-grader pool mean, 30 annotation cells; "
                  "bias = mean(judge - human); mae_loeo_calibrated subtracts a "
                  "leave-one-exam-out bias estimate before |error|",
         "per_condition": bias_per_condition,
         "blind_only_sensitivity": blind_sensitivity},
        indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------- trend figure data (script-written since 2026-08-09) ----------
    def cond_sd_ci(key):
        def stat(rows):
            v = [r[key] for r in rows if r.get(key) is not None]
            return statistics.mean(v) if v else None
        point = stat(per_pick)
        vals = []
        for i in range(N_BOOT):
            rows = []
            for e in draws[i]:
                rows.extend(by_exam[exams[e]])
            v = stat(rows)
            if v is not None:
                vals.append(v)
        return [round(point, 3),
                round(float(np.percentile(vals, 2.5)), 3),
                round(float(np.percentile(vals, 97.5)), 3)]

    outcomes = json.loads((PROCESSED / "rubric_outcomes.json").read_text())
    by_task_min = {}
    for r in outcomes["luna"]["per_rubric"]:
        v = r.get("repeat_sd_mean")
        if v is None:
            continue
        t = r["task_id"]
        by_task_min[t] = v if t not in by_task_min else min(by_task_min[t], v)
    oracle = round(statistics.mean(by_task_min.values()), 2)

    TREND_OUT.write_text(json.dumps(
        {"holistic": cond_sd_ci("luna_holi_rep_sd"),
         "zeroshot": cond_sd_ci("luna_tail_rep_sd"),
         "fewshot": cond_sd_ci("luna_fs_rep_sd"),
         "oracle": oracle,
         "oracle_note": "per-exam retrospective min repeat SD over the crossed sweep's "
                        "170 rubrics — an in-sample, post-hoc selection floor "
                        "(optimistic bound), not demonstrated headroom",
         "generated_by": "compute_significance.py (2026-08-09; previously hand-maintained)"},
        indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------- reliability-conditions table source ----------
    panel_keys = ["panel_ctrl_mini", "panel_tail_mini", "panel_tail_luna",
                  "panel_hol_luna", "panel_hol_mini"]
    common = [r for r in per_pick if all(r.get(k) is not None for k in panel_keys)]

    matched_stats = json.loads(MATCHED.read_text())
    pj = matched_stats["per_judge"]

    def hol_ctrl_validity():
        # Control primary (GPT-5 Mini): first repeat pass vs human pool, on the
        # annotation picks only — the same 30-cell agreement basis as every
        # other row's validity() (matched_stats per_judge).
        rows = [json.loads(l) for l in
                (HERE / "data" / "interim" / "control_results_temp0.jsonl").read_text().splitlines()]
        first = {r["pick_id"]: float(r["score"]) for r in rows
                 if r["repeat_run"] and int(r["run_index"] or 0) == 0}
        pairs = [(first[r["pick_id"]], r["human_mean"]) for r in per_pick
                 if r["pick_id"] in first and r.get("human_mean") is not None
                 and r.get("target_type") == "annotation"]
        return {"n": len(pairs),
                "pearson": pearson([a for a, _ in pairs], [b for _, b in pairs]),
                "mae": statistics.mean(abs(a - b) for a, b in pairs)}

    def cmean(key):
        return statistics.mean(r[key] for r in common)

    ctrl_val = hol_ctrl_validity()
    p01 = {r["pick_id"]: r for r in per_pick}["P01"]
    ctrl_p01_runs = None
    for line in (HERE / "data" / "interim" / "control_results_temp0.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["pick_id"] == "P01" and r["repeat_run"]:
            ctrl_p01_runs = (ctrl_p01_runs or {})
            ctrl_p01_runs[int(r["run_index"] or 0)] = float(r["score"])

    def _bias_of(cond):
        b = bias_per_condition.get(cond)
        return b["bias"] if b else None

    def _fs_validity(key):
        pairs_v = [(r[key], r["human_mean"]) for r in ann_rows if r.get(key) is not None]
        return {"n": len(pairs_v),
                "pearson": pearson([x for x, _ in pairs_v], [h for _, h in pairs_v]),
                "mae": statistics.mean(abs(x - h) for x, h in pairs_v)}

    fsv_luna, fsv_mini = _fs_validity("luna_fs_first"), _fs_validity("mini_fs_first")

    def _fs_rep_mean(key):
        return statistics.mean(r[key] for r in per_pick if r.get(key) is not None)

    conditions = {
        "basis": {"panel_n": len(common),
                  "panel_note": "mean within-cell SD over the cells with complete data in "
                                "every panel definition (control opus-4-7 missing on 2)",
                  "repeat_n": 45, "agreement_n": 30,
                  "bias_note": "bias = mean(first pass - human pool), 30 annotation cells"},
        "rows": [
            {"condition": "holistic_control",
             "instrument": "holistic", "primary": "gpt-5-mini (control)",
             "interjudge_sd": cmean("panel_ctrl_mini"),
             "repeat_sd": statistics.mean(r["control_gpt5mini_rep_sd"] for r in per_pick
                                          if r.get("control_gpt5mini_rep_sd") is not None),
             "r": ctrl_val["pearson"], "mae": ctrl_val["mae"],
             "bias": _bias_of("holistic_control"),
             "p01_runs": ctrl_p01_runs},
            {"condition": "tailored_mini",
             "instrument": "tailored", "primary": "gpt-5.4-mini",
             "interjudge_sd": cmean("panel_tail_mini"),
             "repeat_sd": pj["gpt-5.4-mini"]["repeats"]["tailored"]["mean"],
             "r": pj["gpt-5.4-mini"]["validity"]["tailored_first_pass"]["pearson"],
             "mae": pj["gpt-5.4-mini"]["validity"]["tailored_first_pass"]["mae"],
             "bias": _bias_of("tailored_mini"),
             "p01_runs": pj["gpt-5.4-mini"]["p01"]["tailored"]},
            {"condition": "tailored_luna",
             "instrument": "tailored", "primary": "gpt-5.6-luna",
             "interjudge_sd": cmean("panel_tail_luna"),
             "repeat_sd": pj["gpt-5.6-luna"]["repeats"]["tailored"]["mean"],
             "r": pj["gpt-5.6-luna"]["validity"]["tailored_first_pass"]["pearson"],
             "mae": pj["gpt-5.6-luna"]["validity"]["tailored_first_pass"]["mae"],
             "bias": _bias_of("tailored_luna"),
             "p01_runs": pj["gpt-5.6-luna"]["p01"]["tailored"]},
            {"condition": "fewshot_luna",
             "instrument": "fewshot", "primary": "gpt-5.6-luna",
             "interjudge_sd": None,
             "repeat_sd": _fs_rep_mean("luna_fs_rep_sd"),
             "r": fsv_luna["pearson"], "mae": fsv_luna["mae"],
             "bias": _bias_of("fewshot_luna"),
             "p01_runs": {str(k): v for k, v in (fs_luna.get("P01") or {}).items()}},
            {"condition": "holistic_luna",
             "instrument": "holistic", "primary": "gpt-5.6-luna",
             "interjudge_sd": cmean("panel_hol_luna"),
             "repeat_sd": pj["gpt-5.6-luna"]["repeats"]["holistic"]["mean"],
             "r": pj["gpt-5.6-luna"]["validity"]["holistic_first_pass"]["pearson"],
             "mae": pj["gpt-5.6-luna"]["validity"]["holistic_first_pass"]["mae"],
             "bias": _bias_of("holistic_luna"),
             "p01_runs": pj["gpt-5.6-luna"]["p01"]["holistic"]},
            {"condition": "holistic_mini",
             "instrument": "holistic", "primary": "gpt-5.4-mini",
             "interjudge_sd": cmean("panel_hol_mini"),
             "repeat_sd": pj["gpt-5.4-mini"]["repeats"]["holistic"]["mean"],
             "r": pj["gpt-5.4-mini"]["validity"]["holistic_first_pass"]["pearson"],
             "mae": pj["gpt-5.4-mini"]["validity"]["holistic_first_pass"]["mae"],
             "bias": _bias_of("holistic_mini"),
             "p01_runs": pj["gpt-5.4-mini"]["p01"]["holistic"]},
            {"condition": "fewshot_mini",
             "instrument": "fewshot", "primary": "gpt-5.4-mini",
             "interjudge_sd": None,
             "repeat_sd": _fs_rep_mean("mini_fs_rep_sd"),
             "r": fsv_mini["pearson"], "mae": fsv_mini["mae"],
             "bias": _bias_of("fewshot_mini"),
             "p01_runs": {str(k): v for k, v in (fs_mini.get("P01") or {}).items()}},
        ],
    }
    COND_OUT.write_text(json.dumps(conditions, indent=1, ensure_ascii=False), encoding="utf-8")

    print("\nmatched sign tests:")
    for k, v in matched.items():
        print(f"  {k}: k={v.get('lower', v.get('higher'))}/{v['n']} p={v['p']:.4f} "
              f"mean_diff={v['mean_diff']:+.3f} "
              f"(wilcoxon {v['wilcoxon']['method']} p={v['wilcoxon']['p']:.4f})")
    print("\nconditions table:")
    for row in conditions["rows"]:
        sdj = f"{row['interjudge_sd']:.2f}" if row.get("interjudge_sd") is not None else "-"
        print(f"  {row['condition']:18s} SD_j={sdj} "
              f"SD_rep={row['repeat_sd']:.2f} r={row['r']:.3f} MAE={row['mae']:.1f} "
              f"bias={row['bias']:+.1f} "
              f"P01={sorted((row['p01_runs'] or {}).values())}")
    print(f"\nwrote {SIG_OUT.name}, {BOOT_OUT.name}, {COND_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
