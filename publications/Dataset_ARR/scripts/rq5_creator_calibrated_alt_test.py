"""Creator-anchored leave-one-out calibration of each judge, then re-run the
§3 Calderon blind-pool alt-test on the calibrated scores.

The question: after stripping each judge's per-instance calibration offset
using the creator grade (independent of the blind pool by design — creators
are excluded from IRR because they wrote the reference solution), does the
bias-cleaned judge clear the ω ≥ 0.5 bar against a typical blind reviewer?

Two correction tiers reported side-by-side:
  scalar : y' = y - mean_loo(y - y_creator)            (1 parameter)
  affine : y' = a_loo + b_loo * y                      (2 parameters)

LOO discipline: for the i-th pick, fit on the other n-1 anchors and predict
the calibrated score for i. Calibration anchors pool human + LLM picks
(n ≈ 45 per judge); pool-specific refit reported as a sensitivity.

Bootstrap: with calibrated scores fixed, resample the alt-test test set
(picks within pool) with replacement 500× and recompute ω, yielding a
percentile-based 95% CI on ω.

Outputs:
  data/processed/calderon_per_judge_creator_calibrated.json
  data/processed/csv/creator_calibration_anchors.csv
  data/processed/csv/creator_calibration_params_loo.csv
  data/processed/csv/creator_calibrated_judge_scores.csv
  data/processed/csv/creator_calibrated_omega_results.csv
  data/processed/csv/creator_calibrated_per_annotator.csv
  data/processed/csv/creator_calibrated_omega_pool_specific.csv

  uv run python scripts/rq5_creator_calibrated_alt_test.py
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
CSV_DIR = PROCESSED / "csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import (  # noqa: E402
    REAL,
    _alt_test_blind_pool,
    _build_blind_pool_inputs,
    _expert_grades_by_solution,
    humans_by_solution,
    index_judge_on_humans,
    load_json,
    pearson,
)
from derive_paper_exports import (  # noqa: E402
    CONFIG_B_FIELD_PREFIX,
    CONFIG_DEEPSEEK_FIELD_PREFIX,
    CONFIG_GPT54MINI_FIELD_PREFIX,
    CONFIG_QWEN_FIELD_PREFIX,
    CONFIG_SONNET_FIELD_PREFIX,
)
from rq5_judge_calibration import index_judge_per_config  # noqa: E402

EPS = 0.15
BOOTSTRAP_REPS = 500
RNG_SEED = 12345
JUDGE_NAMES = {
    "baseline_gpt5": "Baseline GPT-5-mini",
    "cfgB_gpt5":     "Config B GPT-5-mini",
    "cfgB_opus":     "Config B Opus-4.7",
    "cfgB_gemini":   "Config B Gemini-3.1-Pro",
    "deepseek":      "DeepSeek-V4-Pro",
    "qwen":          "Qwen3.5-397B-A17B",
    "sonnet":        "Sonnet-4.6",
    "gpt54mini":     "GPT-5.4-mini",
}


# ----- linear-algebra helpers -------------------------------------------------

def ols_fit(xs, ys):
    """OLS y = a + b*x. Returns (a, b). Degenerate variance -> b=0, a=mean(y)."""
    n = len(xs)
    if n < 2:
        return (statistics.mean(ys) if ys else 0.0), 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return my, 0.0
    b = sxy / sxx
    a = my - b * mx
    return a, b


def clip01_100(v):
    if v < 0.0:
        return 0.0, True
    if v > 100.0:
        return 100.0, True
    return v, False


# ----- judge-score extraction -------------------------------------------------

def build_judge_score_maps(real, model_evals):
    """Return per-judge {pool: {solution_id: raw_score}} for all six judges.

    Mirrors rq5_calderon_per_judge.py:88-123 exactly so uncalibrated parity holds.
    """
    inter_h = index_judge_per_config(
        real, prefix=CONFIG_B_FIELD_PREFIX, group_by_judge=True, target="human")
    inter_l = index_judge_per_config(
        real, prefix=CONFIG_B_FIELD_PREFIX, group_by_judge=True, target="llm")
    ds_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_DEEPSEEK_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    ds_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_DEEPSEEK_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})
    qw_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_QWEN_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    qw_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_QWEN_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})
    sn_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    sn_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})
    g54_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_GPT54MINI_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    g54_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_GPT54MINI_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})

    baseline_idx_h = index_judge_on_humans(real)
    baseline_h = {k: float(v["raw_score"]) for k, v in baseline_idx_h.items()
                  if v.get("raw_score") is not None}
    baseline_l = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                  if r.get("raw_score") is not None}

    return {
        "baseline_gpt5": {"human": baseline_h, "llm": baseline_l},
        "cfgB_gpt5":     {"human": inter_h.get("gpt-5-mini", {}),
                          "llm":   inter_l.get("gpt-5-mini", {})},
        "cfgB_opus":     {"human": inter_h.get("claude-opus-4-7", {}),
                          "llm":   inter_l.get("claude-opus-4-7", {})},
        "cfgB_gemini":   {"human": inter_h.get("gemini-3.1-pro-preview", {}),
                          "llm":   inter_l.get("gemini-3.1-pro-preview", {})},
        "deepseek":      {"human": ds_h, "llm": ds_l},
        "qwen":          {"human": qw_h, "llm": qw_l},
        "sonnet":        {"human": sn_h, "llm": sn_l},
        "gpt54mini":     {"human": g54_h, "llm": g54_l},
    }


# ----- LOO calibration --------------------------------------------------------

def loo_calibrate(anchor_pairs):
    """Given list of (sid, pool, y_judge, y_creator), return per-pick LOO scalar
    and affine calibrated scores plus per-pick fit parameters.

    Pooled fit: each held-out pick is calibrated using all other anchors
    (human + LLM combined).
    """
    n = len(anchor_pairs)
    out = []  # one dict per pick
    for i, (sid, pool, y_j, y_c) in enumerate(anchor_pairs):
        train = [(p[2], p[3]) for k, p in enumerate(anchor_pairs) if k != i]
        # Scalar: mean offset of train.
        deltas = [yj - yc for yj, yc in train]
        a_scalar = -statistics.mean(deltas)  # so y' = y + a_scalar = y - mean(δ)
        # Affine: OLS y_creator = a + b * y_judge on train.
        xs = [yj for yj, _ in train]
        ys = [yc for _, yc in train]
        a_aff, b_aff = ols_fit(xs, ys)
        y_scalar_uncl = y_j + a_scalar
        y_affine_uncl = a_aff + b_aff * y_j
        y_scalar, clip_s = clip01_100(y_scalar_uncl)
        y_affine, clip_a = clip01_100(y_affine_uncl)
        out.append({
            "solution_id": sid,
            "pool": pool,
            "y_raw": y_j,
            "y_creator": y_c,
            "a_scalar": a_scalar,
            "a_affine": a_aff,
            "b_affine": b_aff,
            "n_train": n - 1,
            "y_scalar_uncl": y_scalar_uncl,
            "y_scalar": y_scalar,
            "y_affine_uncl": y_affine_uncl,
            "y_affine": y_affine,
            "clip_scalar": clip_s,
            "clip_affine": clip_a,
        })
    return out


def loo_calibrate_pool_specific(anchor_pairs):
    """Same as loo_calibrate but fits only on anchors of the held-out pick's pool."""
    out = []
    for i, (sid, pool, y_j, y_c) in enumerate(anchor_pairs):
        train = [p for k, p in enumerate(anchor_pairs) if k != i and p[1] == pool]
        if len(train) < 2:  # too few same-pool anchors to fit
            out.append(None)
            continue
        deltas = [p[2] - p[3] for p in train]
        a_scalar = -statistics.mean(deltas)
        xs = [p[2] for p in train]
        ys = [p[3] for p in train]
        a_aff, b_aff = ols_fit(xs, ys)
        y_scalar = clip01_100(y_j + a_scalar)[0]
        y_affine = clip01_100(a_aff + b_aff * y_j)[0]
        out.append({
            "solution_id": sid,
            "pool": pool,
            "y_raw": y_j,
            "y_creator": y_c,
            "a_scalar": a_scalar,
            "a_affine": a_aff,
            "b_affine": b_aff,
            "n_train": len(train),
            "y_scalar": y_scalar,
            "y_affine": y_affine,
        })
    return out


# ----- alt-test wrappers ------------------------------------------------------

def run_alt(judge_by_sol, humans, *, eps=EPS):
    inputs, n_total = _build_blind_pool_inputs(judge_by_sol, humans)
    payload = _alt_test_blind_pool(inputs, eps=eps)
    payload["n_instances_total"] = n_total
    # Pearson vs mean blind, on the same restricted instance set.
    j_vals, m_vals = [], []
    for sid, graders in humans.items():
        rated = [g["raw_score"] for g in graders if g["raw_score"] is not None]
        if len(rated) < 3:
            continue
        j = judge_by_sol.get(sid)
        if j is None:
            continue
        j_vals.append(float(j))
        m_vals.append(sum(rated) / len(rated))
    payload["pearson_judge_vs_mean_blind"] = pearson(j_vals, m_vals)
    payload["n_pearson"] = len(j_vals)
    return payload


def bootstrap_omega(judge_by_sol, humans, *, reps, rng):
    """Resample picks (solution_ids that have both judge score AND ≥3 blind
    raters) with replacement; recompute ω on each resample. Returns the list
    of ω values (percentile CI computed by caller).
    """
    eligible = [sid for sid in humans
                if len([g for g in humans[sid] if g["raw_score"] is not None]) >= 3
                and sid in judge_by_sol]
    n = len(eligible)
    if n == 0:
        return []
    omegas = []
    for _ in range(reps):
        sample = [eligible[rng.randrange(n)] for _ in range(n)]
        # Build bootstrap_humans / bootstrap_judge_by_sol with unique synthetic keys
        b_humans = {}
        b_judge = {}
        for k, sid in enumerate(sample):
            key = f"{sid}__{k}"
            b_humans[key] = humans[sid]
            b_judge[key] = judge_by_sol[sid]
        inputs, _ = _build_blind_pool_inputs(b_judge, b_humans)
        payload = _alt_test_blind_pool(inputs, eps=EPS)
        if payload.get("winning_rate") is not None:
            omegas.append(payload["winning_rate"])
    return omegas


def pct_ci(vals, *, lo=2.5, hi=97.5):
    if not vals:
        return None, None
    s = sorted(vals)
    n = len(s)
    def q(p):
        idx = (p / 100.0) * (n - 1)
        i = int(idx)
        f = idx - i
        if i + 1 < n:
            return s[i] * (1 - f) + s[i + 1] * f
        return s[i]
    return q(lo), q(hi)


# ----- main pipeline ----------------------------------------------------------

def main():
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")

    humans_h = humans_by_solution(canonical, role_filter="blind")
    humans_l = humans_by_solution(canonical, role_filter="blind",
                                  solution_type_filter="llm_system")
    # We want humans_h to be ONLY the human-authored solutions (matching the
    # existing rq5_calderon_per_judge.py "human picks" semantics, which passes
    # the full blind-by-solution dict but the LLM-pool judge scores naturally
    # restrict it to human solutions in practice). The original script does
    # not filter humans_h; we follow it verbatim.

    creator_by_sol = _expert_grades_by_solution(canonical)
    judges = build_judge_score_maps(real, model_evals)

    # ---- 1. Build anchor pairs per judge (pooled across human+LLM picks) ----
    anchors_by_judge = {}
    for jkey, by_pool in judges.items():
        rows = []
        for pool in ("human", "llm"):
            for sid, y_j in by_pool[pool].items():
                y_c = creator_by_sol.get(sid)
                if y_c is None:
                    continue
                rows.append((sid, pool, float(y_j), float(y_c)))
        anchors_by_judge[jkey] = rows

    # ---- 2. LOO calibration (pooled) ---------------------------------------
    calib_pooled = {jkey: loo_calibrate(rows)
                    for jkey, rows in anchors_by_judge.items()}
    calib_poolspec = {jkey: loo_calibrate_pool_specific(rows)
                      for jkey, rows in anchors_by_judge.items()}

    # ---- 3. CSVs: anchors, calibration params, calibrated scores -----------
    with (CSV_DIR / "creator_calibration_anchors.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["judge", "judge_label", "solution_id", "pool", "y_judge", "y_creator"])
        for jkey, rows in anchors_by_judge.items():
            for sid, pool, y_j, y_c in rows:
                w.writerow([jkey, JUDGE_NAMES[jkey], sid, pool, f"{y_j:.4f}", f"{y_c:.4f}"])

    with (CSV_DIR / "creator_calibration_params_loo.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["judge", "judge_label", "solution_id", "pool",
                    "a_scalar", "a_affine", "b_affine", "n_train"])
        for jkey, recs in calib_pooled.items():
            for r in recs:
                w.writerow([jkey, JUDGE_NAMES[jkey], r["solution_id"], r["pool"],
                            f"{r['a_scalar']:.6f}", f"{r['a_affine']:.6f}",
                            f"{r['b_affine']:.6f}", r["n_train"]])

    with (CSV_DIR / "creator_calibrated_judge_scores.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["judge", "judge_label", "solution_id", "pool",
                    "y_raw", "y_scalar_uncl", "y_scalar",
                    "y_affine_uncl", "y_affine",
                    "clip_scalar", "clip_affine"])
        for jkey, recs in calib_pooled.items():
            for r in recs:
                w.writerow([jkey, JUDGE_NAMES[jkey], r["solution_id"], r["pool"],
                            f"{r['y_raw']:.4f}",
                            f"{r['y_scalar_uncl']:.4f}", f"{r['y_scalar']:.4f}",
                            f"{r['y_affine_uncl']:.4f}", f"{r['y_affine']:.4f}",
                            int(r["clip_scalar"]), int(r["clip_affine"])])

    # ---- 4. Run alt-test: raw + scalar + affine, for each (judge, pool) ----
    # Each judge's by_pool dicts only contain solutions IDs from its own pool,
    # so passing humans_h / humans_l unmodified is correct (the alt-test only
    # uses solutions present in BOTH dicts via _build_blind_pool_inputs).
    rng = random.Random(RNG_SEED)
    results = {}
    per_annot_rows = []
    omega_rows = []

    for jkey, recs in calib_pooled.items():
        # Index calibrated scores by (pool, solution_id).
        scalar_by_pool = {"human": {}, "llm": {}}
        affine_by_pool = {"human": {}, "llm": {}}
        raw_by_pool = {"human": {}, "llm": {}}
        for r in recs:
            raw_by_pool[r["pool"]][r["solution_id"]] = r["y_raw"]
            scalar_by_pool[r["pool"]][r["solution_id"]] = r["y_scalar"]
            affine_by_pool[r["pool"]][r["solution_id"]] = r["y_affine"]

        for pool in ("human", "llm"):
            humans = humans_h if pool == "human" else humans_l
            for tier, by_sid in (("raw", raw_by_pool[pool]),
                                 ("scalar", scalar_by_pool[pool]),
                                 ("affine", affine_by_pool[pool])):
                payload = run_alt(by_sid, humans, eps=EPS)
                boot = bootstrap_omega(by_sid, humans,
                                       reps=BOOTSTRAP_REPS, rng=rng)
                boot_lo, boot_hi = pct_ci(boot)
                key = f"{jkey}_{pool}_{tier}"
                payload["calib"] = {
                    "tier": tier,
                    "pool": pool,
                    "n_anchor": len(recs),
                }
                payload["omega_bootstrap_ci95"] = [boot_lo, boot_hi]
                payload["omega_bootstrap_n"] = len(boot)
                results[key] = {
                    "label": f"{JUDGE_NAMES[jkey]} ({pool} picks, {tier})",
                    "payload": payload,
                }
                omega_rows.append({
                    "judge": jkey,
                    "judge_label": JUDGE_NAMES[jkey],
                    "pool": pool,
                    "tier": tier,
                    "omega": payload["winning_rate"],
                    "omega_lo_clopper": payload["winning_rate_ci95_lo_clopper"],
                    "omega_hi_clopper": payload["winning_rate_ci95_hi_clopper"],
                    "omega_lo_boot": boot_lo,
                    "omega_hi_boot": boot_hi,
                    "passes_point": bool(payload.get("passes_alt_test")),
                    "passes_boot_lo": (boot_lo is not None and boot_lo >= 0.5),
                    "n_instances": payload["n_instances_total"],
                    "pearson_vs_mean_blind": payload["pearson_judge_vs_mean_blind"],
                    "n_anchor": len(recs),
                })
                for entry in payload["per_annotator"]:
                    per_annot_rows.append({
                        "judge": jkey,
                        "judge_label": JUDGE_NAMES[jkey],
                        "pool": pool,
                        "tier": tier,
                        **entry,
                    })

    # ---- 5. Pool-specific sensitivity ω -----------------------------------
    omega_rows_pool_specific = []
    for jkey, recs in calib_poolspec.items():
        scalar_by_pool = {"human": {}, "llm": {}}
        affine_by_pool = {"human": {}, "llm": {}}
        for r in recs:
            if r is None:
                continue
            scalar_by_pool[r["pool"]][r["solution_id"]] = r["y_scalar"]
            affine_by_pool[r["pool"]][r["solution_id"]] = r["y_affine"]
        for pool in ("human", "llm"):
            humans = humans_h if pool == "human" else humans_l
            for tier, by_sid in (("scalar", scalar_by_pool[pool]),
                                 ("affine", affine_by_pool[pool])):
                if not by_sid:
                    continue
                payload = run_alt(by_sid, humans, eps=EPS)
                boot = bootstrap_omega(by_sid, humans,
                                       reps=BOOTSTRAP_REPS, rng=rng)
                boot_lo, boot_hi = pct_ci(boot)
                omega_rows_pool_specific.append({
                    "judge": jkey,
                    "judge_label": JUDGE_NAMES[jkey],
                    "pool": pool,
                    "tier": tier,
                    "omega": payload["winning_rate"],
                    "omega_lo_clopper": payload["winning_rate_ci95_lo_clopper"],
                    "omega_hi_clopper": payload["winning_rate_ci95_hi_clopper"],
                    "omega_lo_boot": boot_lo,
                    "omega_hi_boot": boot_hi,
                    "passes_point": bool(payload.get("passes_alt_test")),
                    "passes_boot_lo": (boot_lo is not None and boot_lo >= 0.5),
                    "n_instances": payload["n_instances_total"],
                    "n_anchor_same_pool": sum(1 for r in recs if r is not None and r["pool"] == pool),
                })
                payload["omega_bootstrap_ci95"] = [boot_lo, boot_hi]
                results[f"{jkey}_{pool}_{tier}_poolspecific"] = {
                    "label": f"{JUDGE_NAMES[jkey]} ({pool} picks, {tier}, pool-specific)",
                    "payload": payload,
                }

    # ---- 6. Persist results -----------------------------------------------
    with (CSV_DIR / "creator_calibrated_omega_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(omega_rows[0].keys()))
        w.writeheader()
        for row in omega_rows:
            w.writerow({k: ("" if v is None else (f"{v:.4f}" if isinstance(v, float) else v))
                        for k, v in row.items()})

    with (CSV_DIR / "creator_calibrated_omega_pool_specific.csv").open("w", newline="") as f:
        if omega_rows_pool_specific:
            w = csv.DictWriter(f, fieldnames=list(omega_rows_pool_specific[0].keys()))
            w.writeheader()
            for row in omega_rows_pool_specific:
                w.writerow({k: ("" if v is None else (f"{v:.4f}" if isinstance(v, float) else v))
                            for k, v in row.items()})

    with (CSV_DIR / "creator_calibrated_per_annotator.csv").open("w", newline="") as f:
        cols = ["judge", "judge_label", "pool", "tier", "grader_id",
                "n_j", "rho_f", "rho_h", "d_bar", "test", "statistic",
                "p_value", "rejected_BY_FDR"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in per_annot_rows:
            w.writerow({k: ("" if row.get(k) is None
                            else (f"{row[k]:.6f}" if isinstance(row.get(k), float) else row.get(k)))
                        for k in cols})

    with (PROCESSED / "calderon_per_judge_creator_calibrated.json").open("w") as f:
        json.dump(results, f, indent=2, default=float)

    # ---- 7. Stdout summary -------------------------------------------------
    print()
    print("=" * 130)
    print(f"Creator-anchored LOO calibration + §3 alt-test, ε={EPS}, BY-FDR q=0.05, "
          f"bootstrap reps={BOOTSTRAP_REPS}")
    print("=" * 130)
    print(f"{'judge':28s} {'pool':6s} {'tier':7s} "
          f"{'ω':>5s} {'CI95_clopper':>14s} {'CI95_boot':>14s} "
          f"{'n_inst':>6s} {'pearson':>8s}  pass(pt/boot)")
    print("-" * 130)
    for row in omega_rows:
        ci_c = (f"[{row['omega_lo_clopper']:.2f},{row['omega_hi_clopper']:.2f}]"
                if row['omega_lo_clopper'] is not None else "[--,--]")
        ci_b = (f"[{row['omega_lo_boot']:.2f},{row['omega_hi_boot']:.2f}]"
                if row['omega_lo_boot'] is not None else "[--,--]")
        ome = (f"{row['omega']:.2f}" if row['omega'] is not None else "--")
        pe = (f"{row['pearson_vs_mean_blind']:.2f}"
              if row['pearson_vs_mean_blind'] is not None else "--")
        flag_pt = "PASS" if row['passes_point'] else "fail"
        flag_b = "PASS" if row['passes_boot_lo'] else "fail"
        print(f"{JUDGE_NAMES[row['judge']]:28s} {row['pool']:6s} {row['tier']:7s} "
              f"{ome:>5s} {ci_c:>14s} {ci_b:>14s} "
              f"{row['n_instances']:>6d} {pe:>8s}  {flag_pt}/{flag_b}")

    print()
    print("CSVs written:")
    for p in sorted(CSV_DIR.glob("creator_calib*.csv")):
        print(f"  {p.relative_to(HERE)}")
    print(f"  {(PROCESSED / 'calderon_per_judge_creator_calibrated.json').relative_to(HERE)}")


if __name__ == "__main__":
    main()
