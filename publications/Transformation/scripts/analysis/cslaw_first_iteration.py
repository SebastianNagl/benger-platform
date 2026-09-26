#!/usr/bin/env python3
"""First-iteration numbers for the CSLAW full paper, with the corrections applied.

The full paper reports the published first iteration (D1: 12 generators,
15 exams, 45 answers) as "First iteration". Review round 3 (2026-09-26) found
errors in the published text (corrections B1-B27). This script collects every
first-iteration number the full paper prints, applies the corrections that the
tracked data allow, and records the rest as pending with the reason.

It reads ONLY tracked files (data/processed/*.json and a few tracked
data/interim/*.json). It never writes to the published outputs.

Corrections applied here (ids from the change list):
  B1   apportionment audit (as-run routine vs floor-constrained Hamilton)
  B2   totals defined as the step sum. The step-sum re-aggregation of the
       zero-shot arm is the "actual" scheme of weight_sensitivity.json
       (score / max re-weighted by the apportioned points, which is the sum
       of the clipped step scores). The few-shot arm has no step-sum file.
  B5   audit link: absolute bias named as such, Pearson and Spearman both
  B10  panel SD range over all panel definitions
  B11  Mini's tailored MAE level next to the MAE difference
  B13  few-shot vs zero-shot CI and sign test ("directionally consistent")
  B14  every per-judge CI, pooled estimate unweighted
  B15  first-attempt compliance over all series, not only over successes
  B16  Llama-4 audit total (lowest), so it does not fail "invisibly"
  B18  probe severity among failing passes (empty probe: exact from means)
       and the off-topic maxima
  B19  rubric-pick cells of the crossed sweep (510, not 170)
  B20  prior judge MAE on the grade-point scale, computed, not converted
  B22  one source for the judge table (file-based step sums)
  B23  step-variance shares for the 15+ bucket, all judges
  B24  weight sensitivity per judge
  B25  t-based MDE with the real D2 counts (mde.json)

Inputs (tracked): data/processed/{reliability_conditions, weight_sensitivity,
  matched_stats, matched_multijudge, bootstrap_cis, significance,
  fewshot_stats, probe_stats, judge_outcomes, generator_outcomes,
  rubric_outcomes, audit_stats, audit_outcome_link, rubric_run_summary,
  rubric_stats, rubric_screen, apportionment_audit, band_mapping_stats,
  step_variance, variance_stats, trend_figure_data, agreement_bias,
  luna_primary_stats, mde}.json and data/interim/{picks_temp0,
  active_rubric_selection}.json.
Output: data/processed/cslaw/first_iteration.json

``--check`` fails when an internal consistency anchor breaks.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
PROCESSED = HERE / "data" / "processed"
INTERIM = HERE / "data" / "interim"
OUT_DIR = PROCESSED / "cslaw"
OUT = OUT_DIR / "first_iteration.json"

LUNA = "gpt-5.6-luna"
MINI = "gpt-5.4-mini"
ROSTER = (  # the seven tailored-arm judges with a step-sum file
    LUNA, "Qwen/Qwen3.5-397B-A17B", "gemini-3.1-pro-preview", "claude-sonnet-4-6",
    "claude-opus-4-7", "deepseek-ai/DeepSeek-V4-Pro", MINI,
)
EXTRA_JUDGES = ("claude-opus-5", "gpt-5.6-terra")  # single pass, DB extraction only
BIG_BUCKET = "15+"
# A size class is "disproportionate" when its share of summed step variance
# exceeds its share of points by more than 30 %.
RATIO_THRESHOLD = 1.3
AUDIT_SCALE_MAX = 5  # each audit dimension is rated 1-5 (audit prompt, published appendix)


def _load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def load(name: str, base: Path = PROCESSED):
    return json.loads((base / name).read_text(encoding="utf-8"))


def ranks(values):
    """Average ranks (1-based), ties share the mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return num / den


def spearman(xs, ys):
    return pearson(ranks(xs), ranks(ys))


def main() -> int:
    check = "--check" in sys.argv
    problems: list[str] = []

    def anchor(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    cond = {r["condition"]: r for r in load("reliability_conditions.json")["rows"]}
    ws = load("weight_sensitivity.json")["per_judge"]
    matched = load("matched_stats.json")
    multi = load("matched_multijudge.json")
    boots = load("bootstrap_cis.json")["contrasts"]
    sig = load("significance.json")
    fewshot = load("fewshot_stats.json")
    probes = load("probe_stats.json")
    judges_db = load("judge_outcomes.json")["per_judge"]
    gen_out = load("generator_outcomes.json")
    rub_out = load("rubric_outcomes.json")
    audit = load("audit_stats.json")
    audit_link = load("audit_outcome_link.json")
    run_summary = load("rubric_run_summary.json")
    rubric_stats = load("rubric_stats.json")
    screen = load("rubric_screen.json")
    appo = load("apportionment_audit.json")
    bands = load("band_mapping_stats.json")
    stepvar = load("step_variance.json")["per_judge"]
    varstats = load("variance_stats.json")
    trend = load("trend_figure_data.json")
    agree = load("agreement_bias.json")
    mde = load("mde.json")
    picks = load("picks_temp0.json", INTERIM)["resolved"]
    selection = load("active_rubric_selection.json", INTERIM)["selection"]
    holistic = load("falloesung_prompt_snapshot.json", INTERIM)

    pending: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Corpus and the prior study (control arm)
    # ------------------------------------------------------------------
    ctrl = varstats["control_arm"]
    n_exams = len({p["task_id"] for p in picks})
    corpus = {
        "n_exams": n_exams,
        "n_answers": len(picks),
        "n_annotation_answers": sum(1 for p in picks if p["target_type"] == "annotation"),
        "n_generated_answers": sum(1 for p in picks if p["target_type"] == "generation"),
        "provenances": sorted({p["provenance"] for p in picks}),
        "n_blind_raters": ctrl["human_irr"]["k_raters"],
        # the human pool: three blind raters plus the answer's creator (published design)
        "pool_graders": ctrl["human_irr"]["k_raters"] + 1,
        "n_irr_answers": ctrl["human_irr"]["n_annotations"],
        "holistic_dimensions": len(holistic["dimensions"]),
        "holistic_dimension_max": [d["max_score"] for d in holistic["dimensions"].values()],
        "human_icc_2_1_raw": ctrl["human_irr"]["icc_2_1_raw"],
        "human_spread_raw": ctrl["human_irr"]["mean_within_ann_spread_raw"],
        "human_spread_grade_points": ctrl["human_irr"]["mean_within_ann_spread_grade_points"],
        "prior_judge_r": ctrl["judge_vs_human"]["pearson_raw"],
        "prior_judge_mae_raw": ctrl["judge_vs_human"]["mae_raw"],
        # B20: computed on the grade-point scale in the Benchmark data, not a
        # conversion of the raw MAE.
        "prior_judge_mae_grade_points": ctrl["judge_vs_human"]["mae_grade_points"],
        "legacy_control": {k: cond["holistic_control"][k] for k in ("repeat_sd", "r", "mae", "bias")},
    }

    # ------------------------------------------------------------------
    # RQ1 generation (B15 first-attempt compliance over all series)
    # ------------------------------------------------------------------
    gens = run_summary["generators"]
    per_gen = {}
    for g, s in gens.items():
        successes = s["rubrics"]
        first_ok = round(s["first_attempt_rate"] * successes)
        anchor(abs(first_ok - s["first_attempt_rate"] * successes) < 1e-6, f"first-attempt count not integral for {g}")
        provider = (s.get("failure_stages") or {}).get("provider", 0)
        model_series = s["series"] - provider
        per_gen[g] = {
            "valid": successes,
            "series": s["series"],
            "provider_aborts": provider,
            "model_series": model_series,
            "failed_series": s["failed_series"],
            "failure_stages": s.get("failure_stages") or {},
            "failure_categories": s.get("failure_contract_categories") or {},
            "first_attempt_successes": first_ok,
            "first_attempt_rate_published": s["first_attempt_rate"],
            "first_attempt_rate_all_series": first_ok / s["series"],
            "first_attempt_rate_model_series": first_ok / model_series,
            "attempts_per_success": s["attempts_per_success"]["mean"],
            "step_count_mean": rubric_stats["per_generator"][g]["step_count"]["mean"],
            "heaviest_step_mean": rubric_stats["per_generator"][g]["heaviest_step_points"]["mean"],
            "audit_total": audit["per_generator"][g]["total_mean"],
        }
    stages: dict[str, int] = {}
    for s in gens.values():
        for k, v in (s.get("failure_stages") or {}).items():
            stages[k] = stages.get(k, 0) + v
    provider_gens = sorted(g for g, s in gens.items() if (s.get("failure_stages") or {}).get("provider"))
    n_cells = n_exams * len(gens)
    generation = {
        "n_generators": len(gens),
        "n_cells": n_cells,
        "n_valid": run_summary["n_rubrics"],
        "n_full_coverage": sum(1 for s in gens.values() if s["rubrics"] == n_exams),
        "series_total": sum(s["series"] for s in gens.values()),
        "series_failed": sum(s["failed_series"] for s in gens.values()),
        "failed_by_stage": stages,
        "provider_abort_generators": provider_gens,
        "first_attempt_range_published": [min(v["first_attempt_rate_published"] for v in per_gen.values()),
                                          max(v["first_attempt_rate_published"] for v in per_gen.values())],
        "first_attempt_range_model_series": [min(v["first_attempt_rate_model_series"] for v in per_gen.values()),
                                             max(v["first_attempt_rate_model_series"] for v in per_gen.values())],
        "first_attempt_range_all_series": [min(v["first_attempt_rate_all_series"] for v in per_gen.values()),
                                           max(v["first_attempt_rate_all_series"] for v in per_gen.values())],
        "step_count_mean_range": [min(v["step_count_mean"] for v in per_gen.values()),
                                  max(v["step_count_mean"] for v in per_gen.values())],
        "weight_sums": appo["weight_sums"],
        "lexical_screen": {"n_rubrics": screen["n_rubrics"], "listed": screen["listed"]["n_rubrics_hit"],
                           "any": screen["any"]["n_rubrics_hit"]},
        "fewshot_compliance": fewshot["compliance_fewshot"],
        "zeroshot_compliance_mini": fewshot["compliance_zeroshot"][MINI],
        "per_generator": per_gen,
    }
    anchor(generation["series_total"] == 220, "series total is not 220")
    anchor(generation["series_failed"] == 50, "failed series is not 50")
    pending["strict_first_full_series_coverage"] = (
        "coverage under a strict first-full-series rule (published 167/180) needs the per-series sweep log "
        "(data/interim/rubric_sweep_log.jsonl, withheld)")

    # ------------------------------------------------------------------
    # B1 apportionment, band mapping
    # ------------------------------------------------------------------
    drawn_gen = {e["rubric_id"]: e["generator_model_id"] for e in selection}
    affected_drawn = appo["affected_drawn_rubrics"]
    apportionment = {
        "n_rubrics": appo["n_rubrics"],
        "n_steps": appo["n_steps"],
        "as_run": appo["methods"]["as_run"],
        "hamilton_floor": appo["methods"]["hamilton_floor"],
        "hamilton_half": appo["methods"]["hamilton_half"],
        "affected_rubrics": appo["affected_rubrics"],
        "affected_by_generator": {g: v["affected"] for g, v in appo["per_generator"].items() if v["affected"]},
        "affected_drawn_rubrics": len(affected_drawn),
        "affected_drawn_generators": sorted(drawn_gen.get(r, "unknown") for r in affected_drawn),
        "n_drawn": len(selection),
        # every generated rubric was outcome-measured in the crossed sweep
        "affected_in_ranking": appo["affected_rubrics"],
    }
    pending["apportionment_steps_off_in_drawn_rubric"] = (
        "steps changed in the one affected drawn rubric (review notes: 8 of 24) need the withheld rubric documents")
    band_mapping = bands

    # ------------------------------------------------------------------
    # Reliability table (B2, B10, B11)
    # ------------------------------------------------------------------
    def ws_actual(judge):
        return ws[judge]["actual"]

    table = []
    for key in ("holistic_luna", "tailored_luna", "fewshot_luna", "holistic_mini", "tailored_mini", "fewshot_mini"):
        row = cond[key]
        judge = LUNA if key.endswith("luna") else MINI
        out = {"condition": key, "instrument": row["instrument"], "judge": judge,
               "repeat_sd_stored": row["repeat_sd"], "r_stored": row["r"], "mae_stored": row["mae"],
               "bias_stored": row["bias"]}
        if row["instrument"] == "tailored":
            a = ws_actual(judge)
            out.update(repeat_sd=a["repeat_sd"], r=a["r"], mae=a["mae"], bias=None, basis="step_sum",
                       n_repeat_cells=a["n_repeat_cells"])
        elif row["instrument"] == "fewshot":
            out.update(repeat_sd=None, r=None, mae=None, bias=None, basis="stored_pending")
        else:
            out.update(repeat_sd=row["repeat_sd"], r=row["r"], mae=row["mae"], bias=row["bias"],
                       basis="holistic")
        table.append(out)
    pending["fewshot_step_sum"] = (
        "few-shot rows (Luna, Mini): repeat SD, r, MAE and bias recomputed from step sums need the withheld "
        "few-shot run outputs; the review notes report 1.80 -> 1.78 (Luna) and 5.22 -> 5.21 (Mini)")
    pending["tailored_bias_step_sum"] = (
        "signed bias of the zero-shot rows on step sums needs the withheld run outputs "
        "(weight_sensitivity.json stores r, MAE and repeat SD only); the stored values are shown")
    pending["stored_total_rows_per_judge"] = (
        "number of rows per judge whose stored total differs from the step sum (review notes: Luna 6/135 "
        "zero-shot, 9/135 few-shot; Mini 7/135; Opus 8/108; Sonnet 10/135; Qwen 3/135; DeepSeek, Gemini 0) "
        "needs the withheld run outputs")
    panels = {k: cond[k]["interjudge_sd"] for k in cond if cond[k]["interjudge_sd"] is not None}
    reliability = {
        "table": table,
        "panel_sd": panels,
        "panel_sd_range": [min(panels.values()), max(panels.values())],
        "panel_size": len(varstats["tailored_arm_temp0"]["judges"]),
        "panel_n": load("reliability_conditions.json")["basis"]["panel_n"],
        "repeat_n": load("reliability_conditions.json")["basis"]["repeat_n"],
        "agreement_n": load("reliability_conditions.json")["basis"]["agreement_n"],
    }
    anchor(abs(ws_actual(LUNA)["r"] - cond["tailored_luna"]["r"]) < 0.001, "Luna step-sum r drifted")
    anchor(round(ws_actual(LUNA)["repeat_sd"], 2) == 1.96, "Luna step-sum repeat SD is not 1.96")
    anchor(round(ws_actual(MINI)["repeat_sd"], 2) == 5.51, "Mini step-sum repeat SD is not 5.51")

    # ------------------------------------------------------------------
    # Repeat contrasts (B13, B14)
    # ------------------------------------------------------------------
    fs = fewshot["repeat_sd_contrasts"]
    contrasts = {
        "luna_zs_vs_hol": {**boots["repeat_sd_luna_tailored_minus_holistic"],
                           "sign_p": sig["luna_matched_repeats_sign"]["p"],
                           "wilcoxon_p": sig["luna_matched_repeats_sign"]["wilcoxon"]["p"]},
        "mini_zs_vs_hol": {**boots["repeat_sd_mini_tailored_minus_holistic"],
                           "sign_p": sig["mini_matched_repeats_sign"]["p"],
                           "wilcoxon_p": sig["mini_matched_repeats_sign"]["wilcoxon"]["p"]},
        "luna_fs_vs_hol": {"point": fs["luna_fewshot_vs_holistic"]["mean_diff"],
                           "ci95": fs["luna_fewshot_vs_holistic"]["ci95"],
                           "sign_p": fs["luna_fewshot_vs_holistic"]["p"],
                           "wilcoxon_p": sig["luna_fewshot_repeats"]["wilcoxon"]["p"]},
        "luna_fs_vs_zs": {"point": fs["luna_fewshot_vs_zeroshot"]["mean_diff"],
                          "ci95": fs["luna_fewshot_vs_zeroshot"]["ci95"],
                          "sign_p": fs["luna_fewshot_vs_zeroshot"]["p"]},
        "mini_fs_vs_hol": {"point": fs["mini_fewshot_vs_holistic"]["mean_diff"],
                           "ci95": fs["mini_fewshot_vs_holistic"]["ci95"],
                           "sign_p": fs["mini_fewshot_vs_holistic"]["p"]},
        "mini_fs_vs_zs": {"point": fs["mini_fewshot_vs_zeroshot"]["mean_diff"],
                          "ci95": fs["mini_fewshot_vs_zeroshot"]["ci95"],
                          "sign_p": fs["mini_fewshot_vs_zeroshot"]["p"]},
        "pooled_five": multi["pooled"],
        "per_judge": [{**f, "sign_p": (multi["per_judge"].get(f["judge"]) or {}).get("sign", {}).get("p"),
                       "tailored_mean": (multi["per_judge"].get(f["judge"]) or {}).get("tailored_mean"),
                       "holistic_mean": (multi["per_judge"].get(f["judge"]) or {}).get("holistic_mean")}
                      for f in multi["forest"]],
        "basis": "stored totals (matched_multijudge.json, fewshot_stats.json, bootstrap_cis.json)",
        "trend_luna": {"holistic": trend["holistic"], "zeroshot": trend["zeroshot"], "fewshot": trend["fewshot"],
                       "in_sample_floor": trend["oracle"]},
        "fewshot_per_generator_repeat_sd": fewshot["per_generator_repeat_sd"],
    }
    excl = [f["label"] for f in multi["forest"] if f["in_pooled"] and (f["ci95"][0] > 0 or f["ci95"][1] < 0)]
    contrasts["judges_ci_excluding_zero"] = excl
    pending["contrast_cis_step_sum"] = (
        "the repeat-SD contrasts and their CIs use stored totals; their step-sum recompute needs the withheld "
        "per-pass rows (the step-sum shift of the tailored means is at most "
        "a few hundredths where it can be checked)")
    shift = {j: ws[j]["actual"]["repeat_sd"] - (multi["per_judge"].get(j) or {}).get("tailored_mean", float("nan"))
             for j in multi["judges"]}
    contrasts["step_sum_minus_stored_tailored_mean"] = shift

    # ------------------------------------------------------------------
    # Agreement (B11)
    # ------------------------------------------------------------------
    agreement = {
        "luna": {"hol": {"r": cond["holistic_luna"]["r"], "mae": cond["holistic_luna"]["mae"],
                         "bias": cond["holistic_luna"]["bias"]},
                 "zs_step_sum": {"r": ws_actual(LUNA)["r"], "mae": ws_actual(LUNA)["mae"]},
                 "zs_bias_stored": cond["tailored_luna"]["bias"],
                 "fs_stored": {"r": cond["fewshot_luna"]["r"], "mae": cond["fewshot_luna"]["mae"],
                               "bias": cond["fewshot_luna"]["bias"]},
                 "mae_zs_minus_hol": boots["mae_luna_tailored_minus_holistic"],
                 "r_zs_minus_hol": boots["r_luna_tailored_minus_holistic"],
                 "mae_fs_minus_hol": boots["mae_luna_fewshot_minus_holistic"]},
        "mini": {"hol": {"r": cond["holistic_mini"]["r"], "mae": cond["holistic_mini"]["mae"],
                         "bias": cond["holistic_mini"]["bias"]},
                 "zs_step_sum": {"r": ws_actual(MINI)["r"], "mae": ws_actual(MINI)["mae"]},
                 "zs_bias_stored": cond["tailored_mini"]["bias"],
                 "fs_stored": {"r": cond["fewshot_mini"]["r"], "mae": cond["fewshot_mini"]["mae"],
                               "bias": cond["fewshot_mini"]["bias"]},
                 # B11: +8.2 is a difference; the level is the zero-shot MAE.
                 "mae_zs_minus_hol": boots["mae_mini_tailored_minus_holistic"],
                 "r_zs_minus_hol": boots["r_mini_tailored_minus_holistic"]},
        "loeo_calibrated_mae": {k: v["mae_loeo_calibrated"] for k, v in agree["per_condition"].items()},
        "blind_only_r": {k: v["pearson"] for k, v in agree["blind_only_sensitivity"].items()},
        "p01": {"luna_zs": matched["per_judge"][LUNA]["p01"]["tailored"],
                "luna_hol": matched["per_judge"][LUNA]["p01"]["holistic"],
                "mini_zs": matched["per_judge"][MINI]["p01"]["tailored"],
                "mini_hol": matched["per_judge"][MINI]["p01"]["holistic"],
                "legacy_control": cond["holistic_control"]["p01_runs"]},
    }

    # ------------------------------------------------------------------
    # Judges (B22) and probes (B18)
    # ------------------------------------------------------------------
    pb = probes["per_judge"]
    arms = probes["arms"]
    judge_rows = []
    for j in ROSTER:
        a = ws[j]["actual"]
        judge_rows.append({
            "judge": j, "r": a["r"], "mae": a["mae"], "repeat_sd": a["repeat_sd"],
            "n_repeat_cells": a["n_repeat_cells"], "n_agreement": a["n"],
            "battery": (pb.get(j) or {}).get("battery"),
            "positive_control": ((arms.get("tailored") or {}).get(j) or {}).get("positive_control"),
            "p01": (judges_db.get(j) or {}).get("p01"),
        })
    extra = [{"judge": j, "r": judges_db[j]["validity_r"], "mae": judges_db[j]["mae"], "p01": judges_db[j]["p01"]}
             for j in EXTRA_JUDGES]
    capable = [r for r in judge_rows if r["judge"] != MINI]

    def fail_mean(arm, judge, probe):
        """Mean score over failing passes of the empty probe. Passing passes
        score exactly 0 there, so mean * n / n_fail is exact."""
        e = ((arms.get(arm) or {}).get(judge) or {}).get(probe) or {}
        if not e.get("n_fail_passes"):
            return None
        return e["mean"] * e["n_passes"] / e["n_fail_passes"]

    def entry(arm, judge, probe):
        return ((arms.get(arm) or {}).get(judge) or {}).get(probe) or {}

    probe_out = {
        "n_probes_per_type": probes["n_probes"],
        "criteria": probes["criteria"],
        "clean_battery": sorted(j for j, e in pb.items() if e.get("battery") == "pass"),
        "fail_counts": {arm: {j: {t: e.get(t, {}).get("n_fail_passes") for t in ("repetition", "empty", "offtopic")}
                              for j, e in arms[arm].items()} for arm in arms},
        "n_passes": {arm: {j: {t: e.get(t, {}).get("n_passes") for t in ("repetition", "empty", "offtopic")}
                           for j, e in arms[arm].items()} for arm in arms},
        "battery": {arm: {j: e.get("battery") for j, e in arms[arm].items()} for arm in arms},
        "positive_control": {arm: {j: e.get("positive_control") for j, e in arms[arm].items()} for arm in arms},
        "positive_control_fails": {arm: {j: [e.get("musterloesung", {}).get("n_fail_passes"),
                                             e.get("musterloesung", {}).get("n_passes")]
                                         for j, e in arms[arm].items()} for arm in arms},
        "severity": {arm: {j: {t: {k: e[t][k] for k in ("median", "p95", "max")}
                               for t in ("repetition", "empty", "offtopic", "musterloesung") if t in e}
                           for j, e in arms[arm].items()} for arm in arms},
        # B18: the published "median 89-90 when failing" was over ALL passes.
        "luna_empty_median_all_passes": {"tailored": entry("tailored", LUNA, "empty").get("median"),
                                         "fewshot": entry("fewshot", LUNA, "empty").get("median")},
        "luna_empty_mean_failing": {"tailored": fail_mean("tailored", LUNA, "empty"),
                                    "fewshot": fail_mean("fewshot", LUNA, "empty")},
        "mini_empty_mean_failing": {"tailored": fail_mean("tailored", MINI, "empty"),
                                    "holistic": fail_mean("holistic", MINI, "empty")},
        "offtopic_max_tailored": {j: e.get("offtopic", {}).get("max") for j, e in arms["tailored"].items()},
    }
    pending["luna_empty_median_failing"] = (
        "median over failing passes only (review notes: 99.5-100) needs per-pass probe rows (withheld); "
        "the exact mean over failing passes is reported instead")
    probe_out["mini_negative_fails"] = {
        arm: sum(v for v in probe_out["fail_counts"][arm][MINI].values() if v) for arm in ("tailored", "holistic")}
    probe_out["mini_negative_passes"] = {
        arm: sum(v for v in probe_out["n_passes"][arm][MINI].values() if v) for arm in ("tailored", "holistic")}
    judges = {"roster": judge_rows, "extra_single_pass": extra, "n_judges": len(judge_rows) + len(extra),
              "n_matched_judges": len(multi["judges"]), "n_fewshot_generators": len(fewshot["compliance_fewshot"]),
              "capable_r_range": [min(r["r"] for r in capable), max(r["r"] for r in capable)],
              "basis": "weight_sensitivity.json 'actual' (step sums, file-based) for the roster; "
                       "judge_outcomes.json (DB extraction) only for the two single-pass extras",
              "guard_dropped_rows": load("judge_outcomes.json")["guard_dropped_rows"]}

    # ------------------------------------------------------------------
    # RQ4 generators, audit link (B5, B16, B19)
    # ------------------------------------------------------------------
    pg = gen_out["per_generator"]
    rank = gen_out["ranking"]
    names = sorted(pg)
    audit_tot = [audit["per_generator"][g]["total_mean"] for g in names]
    luna_bias = [pg[g]["bias"] for g in names]
    son_bias = [gen_out["sonnet_lens"][g]["bias"] for g in names]
    link = audit_link["audit_total_vs"]
    generators = {
        "per_generator": {g: {**pg[g], "paired_dmae": gen_out["paired_dmae"][g],
                              "sonnet": gen_out["sonnet_lens"][g],
                              "audit_total": audit["per_generator"][g]["total_mean"]} for g in names},
        "ranking": rank,
        "n_rubrics": sum(v["n_rubrics"] for v in pg.values()),
        "n_rubric_pick_cells": sum(r["n_cells"] for r in rub_out["luna"]["per_rubric"]),
        "passes": len(matched["per_judge"][LUNA]["p01"]["tailored"]),
        "dropped_rows": gen_out["dropped_rows"],
        "granularity": gen_out["granularity"],
        "lens_spearman": gen_out["lens_ranking_spearman"],
        "lens_spearman_full_coverage": gen_out["lens_ranking_spearman_full_coverage"],
        "audit_lowest": min(names, key=lambda g: audit["per_generator"][g]["total_mean"]),
        "audit_highest": max(names, key=lambda g: audit["per_generator"][g]["total_mean"]),
        "highest_repeat_sd": max(names, key=lambda g: pg[g]["repeat_sd_mean"]),
        "lowest_r": min(names, key=lambda g: pg[g]["validity_r"]),
        # generator level (n = 12, descriptive): does a higher audit total go
        # with a more negative (harsher) signed bias?
        "generator_level_spearman_audit_vs_bias": {"luna": spearman(audit_tot, luna_bias),
                                                   "sonnet": spearman(audit_tot, son_bias), "n": len(names)},
        "audit": {"auditor": audit["auditor"], "n": audit["n_audited"], "overall_total": audit["overall"]["total_mean"],
                  "n_dimensions": len([k for k in audit["overall"] if k not in ("total_mean", "n")]),
                  "scale_max": AUDIT_SCALE_MAX,
                  "self_total": audit["self"]["total_mean"], "self_n": audit["self"]["n"],
                  "other_total": audit["other"]["total_mean"]},
        "audit_link": {
            "mae_centered": link["mae"]["within_exam_centered"],
            "repeat_sd_centered": link["repeat_sd"]["within_exam_centered"],
            "abs_bias_centered": link["abs_bias"]["within_exam_centered"],
            "note": "B5: the published 'harshness'/'signed bias' wording referred to ABSOLUTE bias",
        },
    }
    anchor(generators["n_rubric_pick_cells"] == 510, "crossed-sweep cells are not 510")
    anchor(generators["audit_lowest"].startswith("meta-llama"), "Llama-4 is no longer the lowest-audited source")
    pending["audit_signed_bias_link"] = (
        "within-exam correlation of the audit total with SIGNED bias (review notes: r = -0.33, CI -0.46 to "
        "-0.18) needs audit_results.jsonl (withheld)")

    # ------------------------------------------------------------------
    # Weights (B24) and step size (B23)
    # ------------------------------------------------------------------
    weights = {}
    for j in ROSTER:
        w = ws[j]
        weights[j] = {s: {"r": w[s]["r"], "mae": w[s]["mae"], "repeat_sd": w[s]["repeat_sd"]}
                      for s in ("actual", "model_weights", "class_only", "uniform", "sqrt_points")}
        weights[j]["permuted"] = w["permuted"]
    ws_mod = _load_module("compute_weight_sensitivity", HERE / "scripts" / "analysis" / "compute_weight_sensitivity.py")
    weight_summary = {
        "class_weights": dict(ws_mod.CLASS_WEIGHT),
        "uniform_lowers_repeat_sd": sorted(j for j in ROSTER if ws[j]["uniform"]["repeat_sd"] < ws[j]["actual"]["repeat_sd"]),
        "class_only_below_uniform_r": sorted(j for j in ROSTER if ws[j]["class_only"]["r"] < ws[j]["uniform"]["r"]),
        "perm_share_range": [min(ws[j]["permuted"]["share_of_permutations_below_actual_r"] for j in ROSTER),
                             max(ws[j]["permuted"]["share_of_permutations_below_actual_r"] for j in ROSTER)],
        "n_judges": len(ROSTER),
    }
    steps = {}
    for j in ROSTER:
        b = stepvar[j]["by_step_size"][BIG_BUCKET]
        steps[j] = {"share_points": b["share_of_points"], "share_variance": b["share_of_variance"],
                    "n_step_cells": b["n_step_cells"], "n_cells": stepvar[j]["n_cells"],
                    "ratio": b["share_of_variance"] / b["share_of_points"]}
    step_summary = {
        "disproportionate": sorted(j for j in ROSTER if steps[j]["ratio"] > RATIO_THRESHOLD),
        "near_proportional": sorted(j for j in ROSTER if steps[j]["ratio"] <= RATIO_THRESHOLD),
        "ratio_threshold": RATIO_THRESHOLD,
        "bucket": BIG_BUCKET,
        "note": "share = share of SUMMED per-step variance (covariance ignored), bucket = step maximum >= 15",
    }

    result = {
        "note": "First-iteration numbers for the CSLAW full paper, corrections B1-B27 applied where the tracked "
                "data allow. Generated by scripts/analysis/cslaw_first_iteration.py. 'pending' lists what needs "
                "withheld inputs.",
        "corpus": corpus,
        "generation": generation,
        "apportionment": apportionment,
        "band_mapping": band_mapping,
        "reliability": reliability,
        "contrasts": contrasts,
        "agreement": agreement,
        "judges": judges,
        "probes": probe_out,
        "generators": generators,
        "weights": {"per_judge": weights, "summary": weight_summary},
        "step_size": {"per_judge": steps, "summary": step_summary},
        "mde": mde,
        "pending": pending,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}; {len(pending)} pending items")
    for p in problems:
        print("ANCHOR FAILED:", p)
    return 1 if (check and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
