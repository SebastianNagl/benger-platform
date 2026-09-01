"""V2 of the creator-anchored alt-test: addresses methodological issues found
in the first run.

Four additions over v1 (rq5_creator_calibrated_alt_test.py):

1. **Grader-leave-one-out (GLOO).** For each blind reviewer g tested in the
   alt-test, the calibration fit additionally excludes every anchor pick
   where g was the creator. This neutralises the dual-role leak in v1, where
   graders 01 and 04 acted as creators on some picks and blind reviewers on
   others — v1 silently style-trained the judge on those graders. The
   alt-test now receives per-(annotator, pick) calibrated scores via a
   custom input builder.

2. **Pure-creator anchor sensitivity.** Restrict the anchor set to picks
   whose creator is in {grader_03, grader_06} — the two pure-creator graders
   who never appear in the blind pool. Stricter discipline but smaller n.

3. **Stacked bootstrap (anchor + test).** Per bootstrap rep, resample the
   anchor set with replacement, refit (a, b) globally, apply to all test
   picks, resample the test set, run alt-test. Propagates both calibration
   variance and test-set variance.

4. **ε sensitivity.** Re-run every tier at ε ∈ {0.15, 0.20}.

Outputs:
  data/processed/calderon_per_judge_creator_calibrated_v2.json
  data/processed/csv/v2_gloo_omega_results.csv
  data/processed/csv/v2_gloo_calibration_params.csv
  data/processed/csv/v2_pure_creator_omega_results.csv
  data/processed/csv/v2_stacked_bootstrap_omega.csv
  data/processed/csv/v2_epsilon_sweep_omega.csv

  uv run python scripts/rq5_creator_calibrated_alt_test_v2.py
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from collections import defaultdict
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

EPS_VALUES = (0.15, 0.20)
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

PURE_CREATORS = {
    "grader_03@anonymized.benger.invalid",
    "grader_06@anonymized.benger.invalid",
}
# Dual-role graders — needed for diagnostics
DUAL_GRADERS = {
    "grader_01@anonymized.benger.invalid",
    "grader_04@anonymized.benger.invalid",
}


# ----- linear-algebra helpers -------------------------------------------------

def ols_fit(xs, ys):
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
    return max(0.0, min(100.0, v))


# ----- judge-score extraction (reused from v1) -------------------------------

def build_judge_score_maps(real, model_evals):
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


def build_creator_of_map(canonical):
    """sid -> grader_id of the creator."""
    out = {}
    for r in canonical:
        if r.get("role") == "creator":
            out[r["solution_id"]] = r.get("grader_id")
    return out


# ----- calibration helpers ---------------------------------------------------

def fit_calibration(anchor_subset):
    """anchor_subset: iterable of (y_judge, y_creator). Returns (a_scalar,
    a_affine, b_affine)."""
    pairs = list(anchor_subset)
    if not pairs:
        return 0.0, 0.0, 1.0
    deltas = [yj - yc for yj, yc in pairs]
    a_scalar = -statistics.mean(deltas)
    xs = [yj for yj, _ in pairs]
    ys = [yc for _, yc in pairs]
    a_aff, b_aff = ols_fit(xs, ys)
    return a_scalar, a_aff, b_aff


def apply_calibration(y, a_scalar, a_affine, b_affine):
    return (clip01_100(y + a_scalar),
            clip01_100(a_affine + b_affine * y))


# ----- GLOO: per-(annotator g, pick i) calibrated scores ---------------------

def gloo_calibrated_scores(judge_scores, anchor_pairs_full, creator_of, *,
                           humans_pool, blind_graders):
    """For each (annotator g, pick i) needed by the alt-test, compute
    LOO-calibrated y' using anchors that exclude:
      - pick i itself (standard LOO)
      - every pick where g was the creator (closes the dual-role leak)

    Returns {(sid, grader_id): (y_scalar, y_affine, n_train)}.

    `anchor_pairs_full`: list of (sid, pool, y_judge, y_creator, creator_grader)
    `humans_pool`: solution_id -> [grader dicts] (the blind pool for this pool)
    `blind_graders`: set of grader_ids that appear as blind reviewers
    """
    # Pre-compute, per g, the subset of anchors excluding g's creator picks.
    anchors_excl_g = {}
    for g in blind_graders:
        anchors_excl_g[g] = [(s, p, yj, yc, cg) for (s, p, yj, yc, cg) in anchor_pairs_full
                             if cg != g]

    cache = {}
    for sid, graders in humans_pool.items():
        if sid not in judge_scores:
            continue
        y_judge = judge_scores[sid]
        for g_dict in graders:
            gid = g_dict.get("grader_id")
            if gid is None or gid not in blind_graders:
                continue
            # Anchor training set for this (sid, gid): excl g's creator picks AND pick sid itself
            train = [(yj, yc) for (s, _, yj, yc, _) in anchors_excl_g[gid] if s != sid]
            a_s, a_a, b_a = fit_calibration(train)
            y_scalar, y_affine = apply_calibration(y_judge, a_s, a_a, b_a)
            cache[(sid, gid)] = {
                "y_raw": y_judge,
                "y_scalar": y_scalar,
                "y_affine": y_affine,
                "a_scalar": a_s,
                "a_affine": a_a,
                "b_affine": b_a,
                "n_train": len(train),
            }
    return cache


def build_per_annot_inputs_gloo(gloo_cache, humans_pool, tier):
    """Same shape as _build_blind_pool_inputs but the judge_score per
    (annotator, pick) comes from gloo_cache[(sid, gid)][tier_key].
    """
    tier_key = {"raw": "y_raw", "scalar": "y_scalar", "affine": "y_affine"}[tier]
    per_annot = defaultdict(list)
    n_total = 0
    for sid, graders in humans_pool.items():
        rated = [(g.get("grader_id") or "", g["raw_score"])
                 for g in graders if g["raw_score"] is not None]
        if len(rated) < 3:
            continue
        # Need GLOO entries for every grader on this pick.
        if not all((sid, gid) in gloo_cache for gid, _ in rated):
            continue
        n_total += 1
        for k, (gid, hj) in enumerate(rated):
            others = [r for i, (_, r) in enumerate(rated) if i != k]
            y_judge_for_this_pair = gloo_cache[(sid, gid)][tier_key]
            per_annot[gid].append((float(y_judge_for_this_pair), float(hj),
                                   [float(x) for x in others]))
    return per_annot, n_total


# ----- pooled LOO calibration (for the pure-creator sensitivity) ------------

def loo_calibrate_pooled(anchor_pairs):
    """Same pooled LOO as v1 but reads creator_grader-bearing anchor tuples."""
    out = {}
    for i, (sid, pool, y_j, y_c, _cg) in enumerate(anchor_pairs):
        train = [(p[2], p[3]) for k, p in enumerate(anchor_pairs) if k != i]
        a_s, a_a, b_a = fit_calibration(train)
        y_scalar, y_affine = apply_calibration(y_j, a_s, a_a, b_a)
        out[sid] = {
            "pool": pool, "y_raw": y_j, "y_creator": y_c,
            "a_scalar": a_s, "a_affine": a_a, "b_affine": b_a,
            "y_scalar": y_scalar, "y_affine": y_affine,
            "n_train": len(train),
        }
    return out


# ----- alt-test wrappers -----------------------------------------------------

def run_alt(judge_by_sol, humans, *, eps):
    inputs, n_total = _build_blind_pool_inputs(judge_by_sol, humans)
    payload = _alt_test_blind_pool(inputs, eps=eps)
    payload["n_instances_total"] = n_total
    return payload


def run_alt_gloo(gloo_cache, humans, tier, *, eps):
    inputs, n_total = build_per_annot_inputs_gloo(gloo_cache, humans, tier)
    payload = _alt_test_blind_pool(inputs, eps=eps)
    payload["n_instances_total"] = n_total
    return payload


# ----- bootstrap helpers ----------------------------------------------------

def stacked_bootstrap_omega(anchor_pairs, judge_scores, humans, *,
                            tier, eps, reps, rng):
    """Per rep: resample anchors (with replacement) → fit global (a, b) →
    apply to test picks → resample test picks (with replacement) → alt-test.
    Returns list of omegas."""
    n_anchor = len(anchor_pairs)
    eligible = [sid for sid in humans
                if len([g for g in humans[sid] if g["raw_score"] is not None]) >= 3
                and sid in judge_scores]
    n_test = len(eligible)
    if n_anchor == 0 or n_test == 0:
        return []
    omegas = []
    for _ in range(reps):
        # ---- anchor resample ----
        anchor_samp = [anchor_pairs[rng.randrange(n_anchor)] for _ in range(n_anchor)]
        a_s, a_a, b_a = fit_calibration([(yj, yc) for (_, _, yj, yc, _) in anchor_samp])
        if tier == "scalar":
            apply_one = lambda y: clip01_100(y + a_s)
        elif tier == "affine":
            apply_one = lambda y: clip01_100(a_a + b_a * y)
        else:  # raw
            apply_one = lambda y: y
        cal = {sid: apply_one(y) for sid, y in judge_scores.items()}
        # ---- test resample ----
        sample_t = [eligible[rng.randrange(n_test)] for _ in range(n_test)]
        b_humans = {}
        b_judge = {}
        for k, sid in enumerate(sample_t):
            key = f"{sid}__{k}"
            b_humans[key] = humans[sid]
            b_judge[key] = cal[sid]
        inputs, _ = _build_blind_pool_inputs(b_judge, b_humans)
        payload = _alt_test_blind_pool(inputs, eps=eps)
        if payload.get("winning_rate") is not None:
            omegas.append(payload["winning_rate"])
    return omegas


def stacked_bootstrap_omega_gloo(anchor_pairs, judge_scores, humans,
                                 creator_of, blind_graders, *,
                                 tier, eps, reps, rng):
    """Same as stacked_bootstrap_omega but the calibration is GLOO per (sid, g)."""
    eligible = [sid for sid in humans
                if len([g for g in humans[sid] if g["raw_score"] is not None]) >= 3
                and sid in judge_scores]
    if not eligible or not anchor_pairs:
        return []
    n_anchor = len(anchor_pairs)
    n_test = len(eligible)
    omegas = []
    for _ in range(reps):
        anchor_samp = [anchor_pairs[rng.randrange(n_anchor)] for _ in range(n_anchor)]
        # GLOO: per-grader fit on the resampled anchors, excluding g's creator picks.
        # No LOO inside the bootstrap (resample provides the calibration noise).
        fit_by_g = {}
        for g in blind_graders:
            train = [(yj, yc) for (_, _, yj, yc, cg) in anchor_samp if cg != g]
            fit_by_g[g] = fit_calibration(train)
        # Apply per (sid, g) for sid in resampled test set.
        sample_t = [eligible[rng.randrange(n_test)] for _ in range(n_test)]
        per_annot = defaultdict(list)
        for k, sid in enumerate(sample_t):
            graders = humans[sid]
            rated = [(g.get("grader_id") or "", g["raw_score"])
                     for g in graders if g["raw_score"] is not None]
            if len(rated) < 3:
                continue
            y_judge = judge_scores[sid]
            for j, (gid, hj) in enumerate(rated):
                if gid not in fit_by_g:
                    continue
                a_s, a_a, b_a = fit_by_g[gid]
                if tier == "scalar":
                    y_cal = clip01_100(y_judge + a_s)
                elif tier == "affine":
                    y_cal = clip01_100(a_a + b_a * y_judge)
                else:
                    y_cal = y_judge
                others = [r for i_, (_, r) in enumerate(rated) if i_ != j]
                per_annot[gid].append((float(y_cal), float(hj),
                                       [float(x) for x in others]))
        payload = _alt_test_blind_pool(per_annot, eps=eps)
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
        i = int(idx); f = idx - i
        return s[i] * (1 - f) + s[i + 1] * f if i + 1 < n else s[i]
    return q(lo), q(hi)


# ----- main pipeline --------------------------------------------------------

def main():
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RNG_SEED)

    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    humans_h = humans_by_solution(canonical, role_filter="blind")
    humans_l = humans_by_solution(canonical, role_filter="blind",
                                  solution_type_filter="llm_system")
    creator_by_sol = _expert_grades_by_solution(canonical)
    creator_of = build_creator_of_map(canonical)
    judges = build_judge_score_maps(real, model_evals)

    # Blind-pool grader identities (across both pools)
    blind_graders = set()
    for hp in (humans_h, humans_l):
        for graders in hp.values():
            for g in graders:
                if g.get("grader_id"):
                    blind_graders.add(g["grader_id"])

    # ---- Build anchor sets per judge (pooled across pools) ----
    anchors_by_judge_full = {}     # all 45 picks per judge
    anchors_by_judge_pure = {}     # only picks whose creator is in PURE_CREATORS
    for jkey, by_pool in judges.items():
        full, pure = [], []
        for pool in ("human", "llm"):
            for sid, y_j in by_pool[pool].items():
                y_c = creator_by_sol.get(sid)
                cg = creator_of.get(sid)
                if y_c is None or cg is None:
                    continue
                rec = (sid, pool, float(y_j), float(y_c), cg)
                full.append(rec)
                if cg in PURE_CREATORS:
                    pure.append(rec)
        anchors_by_judge_full[jkey] = full
        anchors_by_judge_pure[jkey] = pure

    # ====================================================================
    # 1. GLOO calibration + alt-test, both ε
    # ====================================================================
    gloo_omega_rows = []
    gloo_params_rows = []
    json_results = {}

    for jkey, by_pool in judges.items():
        full = anchors_by_judge_full[jkey]
        for pool, humans in (("human", humans_h), ("llm", humans_l)):
            scores = by_pool[pool]
            gloo = gloo_calibrated_scores(
                scores, full, creator_of,
                humans_pool=humans, blind_graders=blind_graders)
            # Dump params for diagnostics: average (a, b) per grader
            per_g_agg = defaultdict(lambda: {"a_scalar": [], "a_affine": [], "b_affine": []})
            for (sid, gid), rec in gloo.items():
                per_g_agg[gid]["a_scalar"].append(rec["a_scalar"])
                per_g_agg[gid]["a_affine"].append(rec["a_affine"])
                per_g_agg[gid]["b_affine"].append(rec["b_affine"])
            for gid, vs in per_g_agg.items():
                gloo_params_rows.append({
                    "judge": jkey, "judge_label": JUDGE_NAMES[jkey],
                    "pool": pool, "annotator": gid,
                    "n_picks": len(vs["a_scalar"]),
                    "mean_a_scalar": statistics.mean(vs["a_scalar"]),
                    "mean_a_affine": statistics.mean(vs["a_affine"]),
                    "mean_b_affine": statistics.mean(vs["b_affine"]),
                })
            for tier in ("raw", "scalar", "affine"):
                for eps in EPS_VALUES:
                    payload = run_alt_gloo(gloo, humans, tier, eps=eps)
                    boot = stacked_bootstrap_omega_gloo(
                        full, scores, humans, creator_of, blind_graders,
                        tier=tier, eps=eps, reps=BOOTSTRAP_REPS, rng=rng)
                    boot_lo, boot_hi = pct_ci(boot)
                    gloo_omega_rows.append({
                        "judge": jkey, "judge_label": JUDGE_NAMES[jkey],
                        "pool": pool, "tier": tier, "epsilon": eps,
                        "omega": payload["winning_rate"],
                        "omega_lo_clopper": payload["winning_rate_ci95_lo_clopper"],
                        "omega_hi_clopper": payload["winning_rate_ci95_hi_clopper"],
                        "omega_lo_boot": boot_lo,
                        "omega_hi_boot": boot_hi,
                        "passes_point": bool(payload.get("passes_alt_test")),
                        "passes_boot_lo": (boot_lo is not None and boot_lo >= 0.5),
                        "n_instances": payload["n_instances_total"],
                        "n_anchor_full": len(full),
                    })
                    payload["omega_bootstrap_ci95"] = [boot_lo, boot_hi]
                    json_results[f"gloo_{jkey}_{pool}_{tier}_eps{eps}"] = {
                        "label": f"GLOO {JUDGE_NAMES[jkey]} ({pool} picks, {tier}, ε={eps})",
                        "payload": payload,
                    }

    # ====================================================================
    # 2. Pure-creator anchor (pooled LOO), both ε
    # ====================================================================
    pure_omega_rows = []
    for jkey, by_pool in judges.items():
        pure = anchors_by_judge_pure[jkey]
        n_pure_h = sum(1 for (_, p, _, _, _) in pure if p == "human")
        n_pure_l = sum(1 for (_, p, _, _, _) in pure if p == "llm")
        cal = loo_calibrate_pooled(pure) if pure else {}
        for pool, humans in (("human", humans_h), ("llm", humans_l)):
            # Test set: original judge scores on this pool's solutions.
            # Calibration: use cal[sid] if sid is in pure-anchor set; otherwise
            # apply the pure-anchor-mean calibration (i.e., fit on all pure
            # anchors → apply to picks outside the anchor set).
            if pure:
                a_s_full, a_a_full, b_a_full = fit_calibration(
                    [(yj, yc) for (_, _, yj, yc, _) in pure])
            else:
                a_s_full, a_a_full, b_a_full = 0.0, 0.0, 1.0
            scalar_by_sid, affine_by_sid, raw_by_sid = {}, {}, {}
            for sid, y in by_pool[pool].items():
                if sid in cal:
                    raw_by_sid[sid] = cal[sid]["y_raw"]
                    scalar_by_sid[sid] = cal[sid]["y_scalar"]
                    affine_by_sid[sid] = cal[sid]["y_affine"]
                else:
                    raw_by_sid[sid] = float(y)
                    scalar_by_sid[sid] = clip01_100(float(y) + a_s_full)
                    affine_by_sid[sid] = clip01_100(a_a_full + b_a_full * float(y))
            for tier, by_sid in (("raw", raw_by_sid),
                                 ("scalar", scalar_by_sid),
                                 ("affine", affine_by_sid)):
                for eps in EPS_VALUES:
                    payload = run_alt(by_sid, humans, eps=eps)
                    pure_omega_rows.append({
                        "judge": jkey, "judge_label": JUDGE_NAMES[jkey],
                        "pool": pool, "tier": tier, "epsilon": eps,
                        "omega": payload["winning_rate"],
                        "omega_lo_clopper": payload["winning_rate_ci95_lo_clopper"],
                        "omega_hi_clopper": payload["winning_rate_ci95_hi_clopper"],
                        "passes_point": bool(payload.get("passes_alt_test")),
                        "n_instances": payload["n_instances_total"],
                        "n_anchor_pure": len(pure),
                        "n_anchor_pure_human": n_pure_h,
                        "n_anchor_pure_llm": n_pure_l,
                    })
                    json_results[f"pure_{jkey}_{pool}_{tier}_eps{eps}"] = {
                        "label": f"Pure-creator {JUDGE_NAMES[jkey]} ({pool} picks, {tier}, ε={eps})",
                        "payload": payload,
                    }

    # ====================================================================
    # 3. Stacked bootstrap on the pooled (non-GLOO) v1 calibration, both ε
    # ====================================================================
    stacked_rows = []
    for jkey, by_pool in judges.items():
        full = anchors_by_judge_full[jkey]
        for pool, humans in (("human", humans_h), ("llm", humans_l)):
            scores = by_pool[pool]
            for tier in ("raw", "scalar", "affine"):
                for eps in EPS_VALUES:
                    # Point estimate: use v1-style pooled LOO calibration.
                    cal = loo_calibrate_pooled(full)
                    by_sid = {sid: cal[sid][f"y_{tier}"] if tier != "raw" else cal[sid]["y_raw"]
                              for sid, _ in scores.items() if sid in cal}
                    point = run_alt(by_sid, humans, eps=eps)
                    boot = stacked_bootstrap_omega(
                        full, scores, humans,
                        tier=tier, eps=eps, reps=BOOTSTRAP_REPS, rng=rng)
                    boot_lo, boot_hi = pct_ci(boot)
                    stacked_rows.append({
                        "judge": jkey, "judge_label": JUDGE_NAMES[jkey],
                        "pool": pool, "tier": tier, "epsilon": eps,
                        "omega": point["winning_rate"],
                        "omega_lo_stacked_boot": boot_lo,
                        "omega_hi_stacked_boot": boot_hi,
                        "passes_point": bool(point.get("passes_alt_test")),
                        "passes_stacked_boot_lo": (boot_lo is not None and boot_lo >= 0.5),
                        "n_instances": point["n_instances_total"],
                    })

    # ====================================================================
    # 4. ε sweep summary: collect GLOO + pure + stacked into one wide table
    # ====================================================================
    eps_rows = []
    for src_name, rows in (("gloo", gloo_omega_rows),
                           ("pure_creator", pure_omega_rows),
                           ("stacked", stacked_rows)):
        for r in rows:
            eps_rows.append({
                "source": src_name,
                "judge": r["judge"], "judge_label": r["judge_label"],
                "pool": r["pool"], "tier": r["tier"], "epsilon": r["epsilon"],
                "omega": r["omega"],
                "passes_point": r["passes_point"],
                "n_instances": r["n_instances"],
            })

    # ====================================================================
    # Write CSVs
    # ====================================================================
    def write_csv(path, rows, cols=None):
        if not rows:
            return
        if cols is None:
            cols = list(rows[0].keys())
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                w.writerow({k: ("" if row.get(k) is None
                                else (f"{row[k]:.4f}" if isinstance(row.get(k), float)
                                      else row.get(k))) for k in cols})

    write_csv(CSV_DIR / "v2_gloo_omega_results.csv", gloo_omega_rows)
    write_csv(CSV_DIR / "v2_gloo_calibration_params.csv", gloo_params_rows)
    write_csv(CSV_DIR / "v2_pure_creator_omega_results.csv", pure_omega_rows)
    write_csv(CSV_DIR / "v2_stacked_bootstrap_omega.csv", stacked_rows)
    write_csv(CSV_DIR / "v2_epsilon_sweep_omega.csv", eps_rows)

    with (PROCESSED / "calderon_per_judge_creator_calibrated_v2.json").open("w") as f:
        json.dump(json_results, f, indent=2, default=float)

    # ====================================================================
    # Stdout summary
    # ====================================================================
    print()
    print("=" * 140)
    print(f"V2 — GLOO + pure-creator + stacked bootstrap, ε ∈ {EPS_VALUES}, reps={BOOTSTRAP_REPS}")
    print("=" * 140)
    print(f"\n[1/4] GLOO (grader-leave-one-out) — leak-clean. ε=0.15.")
    print(f"{'judge':28s} {'pool':6s} {'tier':7s} "
          f"{'ω':>5s} {'CI_clopper':>14s} {'CI_stacked':>14s} {'n_inst':>6s}  pass(pt/boot)")
    for r in gloo_omega_rows:
        if r["epsilon"] != 0.15:
            continue
        ci_c = (f"[{r['omega_lo_clopper']:.2f},{r['omega_hi_clopper']:.2f}]"
                if r['omega_lo_clopper'] is not None else "[--,--]")
        ci_b = (f"[{r['omega_lo_boot']:.2f},{r['omega_hi_boot']:.2f}]"
                if r['omega_lo_boot'] is not None else "[--,--]")
        ome = f"{r['omega']:.2f}" if r['omega'] is not None else "--"
        print(f"  {r['judge_label']:26s} {r['pool']:6s} {r['tier']:7s} "
              f"{ome:>5s} {ci_c:>14s} {ci_b:>14s} "
              f"{r['n_instances']:>6d}  "
              f"{'PASS' if r['passes_point'] else 'fail'}/"
              f"{'PASS' if r['passes_boot_lo'] else 'fail'}")

    print(f"\n[2/4] Pure-creator anchors only (graders 03, 06). ε=0.15.")
    print(f"{'judge':28s} {'pool':6s} {'tier':7s} {'ω':>5s} "
          f"{'CI_clopper':>14s} {'n_inst':>6s} {'n_anc(h/l)':>10s}  pass")
    for r in pure_omega_rows:
        if r["epsilon"] != 0.15:
            continue
        ci = (f"[{r['omega_lo_clopper']:.2f},{r['omega_hi_clopper']:.2f}]"
              if r['omega_lo_clopper'] is not None else "[--,--]")
        ome = f"{r['omega']:.2f}" if r['omega'] is not None else "--"
        anc = f"{r['n_anchor_pure_human']}/{r['n_anchor_pure_llm']}"
        print(f"  {r['judge_label']:26s} {r['pool']:6s} {r['tier']:7s} "
              f"{ome:>5s} {ci:>14s} {r['n_instances']:>6d} {anc:>10s}  "
              f"{'PASS' if r['passes_point'] else 'fail'}")

    print(f"\n[3/4] Stacked bootstrap (anchor + test) on v1 pooled LOO. ε=0.15.")
    print(f"{'judge':28s} {'pool':6s} {'tier':7s} {'ω':>5s} {'stacked_CI95':>14s} pass(pt/boot)")
    for r in stacked_rows:
        if r["epsilon"] != 0.15:
            continue
        ci = (f"[{r['omega_lo_stacked_boot']:.2f},{r['omega_hi_stacked_boot']:.2f}]"
              if r['omega_lo_stacked_boot'] is not None else "[--,--]")
        ome = f"{r['omega']:.2f}" if r['omega'] is not None else "--"
        print(f"  {r['judge_label']:26s} {r['pool']:6s} {r['tier']:7s} "
              f"{ome:>5s} {ci:>14s} "
              f"{'PASS' if r['passes_point'] else 'fail'}/"
              f"{'PASS' if r['passes_stacked_boot_lo'] else 'fail'}")

    print(f"\n[4/4] ε=0.20 sensitivity (GLOO only).")
    print(f"{'judge':28s} {'pool':6s} {'tier':7s} {'ω(0.15)':>8s} {'ω(0.20)':>8s}")
    omega_by = {(r['judge'], r['pool'], r['tier'], r['epsilon']): r['omega']
                for r in gloo_omega_rows}
    for jkey in JUDGE_NAMES:
        for pool in ("human", "llm"):
            for tier in ("raw", "scalar", "affine"):
                w15 = omega_by.get((jkey, pool, tier, 0.15))
                w20 = omega_by.get((jkey, pool, tier, 0.20))
                if w15 is None:
                    continue
                print(f"  {JUDGE_NAMES[jkey]:26s} {pool:6s} {tier:7s} "
                      f"{w15:>8.2f} {w20:>8.2f}")

    print()
    print("CSVs written:")
    for p in sorted(CSV_DIR.glob("v2_*.csv")):
        print(f"  {p.relative_to(HERE)}")
    print(f"  {(PROCESSED / 'calderon_per_judge_creator_calibrated_v2.json').relative_to(HERE)}")


if __name__ == "__main__":
    main()
