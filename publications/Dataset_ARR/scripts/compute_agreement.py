"""Compute all agreement / correlation / reliability statistics for the paper.

Inputs (read-only):
  data/raw/benchathon/Benchathon-tasks-2026-05-31.json   LLM-judge grades on human annotations
                                                         + on LLM generations (the real export)
  data/processed/benchathon_model_evaluations.json
  data/processed/benchathon_automatic_metrics.json
  data/processed/benchathon_instruction_variants.json
  data/processed/benchathon_human_grades.json   (real grades from the sidecar)

Output:
  data/processed/agreement_stats.json   single bundle of computed numbers
  consumed by manuscript chunks tbl-agreement, fig-rubric-dim,
  fig-metric-correlation, and RQ4 co-creation prose.

Stats produced (all reported as floats, None where not estimable):
  rq3_metric_correlation:    per auto-metric Pearson + Spearman vs LLM-judge raw,
                             computed over LLM generations on Benchathon
  rq4_cocreation:            mean judge raw for traditional / co-creation human
                             solutions, mean difference + 95% bootstrap CI
  rq5_judge_vs_human:        per-annotation judge raw vs mean-blind-human raw
                             across the expert-graded subset, with Pearson/
                             Spearman, MAE on raw + grade points, pass/fail
                             Cohen's kappa
  rq5_human_irr:             ICC(2,1) and ICC(2,k) on the expert-graded subset
                             at the most-common k of blind raters; also mean
                             within-annotation max-min spread on raw + grade points
  rq5_dim:                   per-rubric-dimension Pearson(judge, mean_human)
                             and mean |judge - mean_human| in dimension points
  rq5_calderon:              Calderon-style alternative-annotator test —
                             system-level Spearman between two grader pools,
                             one substituting the LLM judge for one human grader
  rq5_judge_repeats:         judge stability (between-run stdev) if any
                             generation has >1 judge run; otherwise None

Correlation, Cohen's kappa, ICC and bootstrap helpers come from scipy /
sklearn / pingouin via scripts/_stats.py — see that module for the shared
contracts. Cluster / paired bootstraps and the TOST equivalence test stay
local because they encode domain-specific resampling logic.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pingouin as pg
from scipy import stats as sp_stats
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).resolve().parent.parent
RAW       = HERE / "data" / "raw"
INTERIM   = HERE / "data" / "interim"
PROCESSED = HERE / "data" / "processed"
OUT = PROCESSED / "agreement_stats.json"

REAL = RAW / "benchathon" / "Benchathon_export.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import mae, pearson, spearman  # noqa: E402
from derive_paper_exports import BASELINE_JUDGE_FIELD_PREFIX  # noqa: E402

# Isolated bootstrap RNG: reproducible regardless of how many or in what order
# other np.random.* calls run in this module.
_BOOTSTRAP_RNG = np.random.default_rng(7)

DIMENSIONS = (
    "ergebnisrichtigkeit", "vollstaendigkeit", "rechtsgrundlagen",
    "rechtskenntnis", "subsumtion", "schwerpunktsetzung",
    "methodischer_stil", "gliederung", "sprache", "formalia",
)


# ----------------------------- statistical wrappers -----------------------------

def cohen_kappa(xs, ys):
    """Cohen's kappa for two binary raters (sklearn-backed)."""
    pairs = [(bool(x), bool(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    a = np.fromiter((p[0] for p in pairs), dtype=bool)
    b = np.fromiter((p[1] for p in pairs), dtype=bool)
    k = cohen_kappa_score(a, b)
    return None if not np.isfinite(k) else float(k)


def icc21_and_2k_long(triples):
    """ICC(2,1) and ICC(2,k) from long-format ratings (pingouin-backed).

    `triples` is an iterable of (target_id, rater_id, rating). Two-way
    random, absolute agreement — Shrout & Fleiss 1979 ICC(2,1) / ICC(2,k);
    pingouin labels these `ICC(A,1)` and `ICC(A,k)`. The long form lets
    callers preserve true rater identity across targets (the n×k matrix
    form silently aligns columns by position, which only encodes rater
    identity in fully-balanced designs).

    Returns (icc_2_1, icc_2_k), or (None, None) if the design is unbalanced
    (pingouin requires every rater to rate every target), too small, or
    pingouin produces NaN (e.g. zero MSE). For unbalanced (partially-crossed)
    designs there is no single closed-form ICC(2,*) — the strict number is
    only defined on a fully-balanced subset; see `_balanced_icc_long` in
    `rq5_human_irr` for the largest-balanced-subset path used in this paper.
    """
    rows = [(t, r, float(v)) for (t, r, v) in triples if v is not None]
    if not rows:
        return None, None
    long_df = pd.DataFrame(rows, columns=["target", "rater", "rating"])
    if long_df["target"].nunique() < 2 or long_df["rater"].nunique() < 2:
        return None, None
    try:
        icc = pg.intraclass_corr(
            data=long_df, targets="target", raters="rater", ratings="rating",
            nan_policy="raise",
        ).set_index("Type")
    except (AssertionError, ValueError):
        return None, None

    def _get(label):
        if label not in icc.index:
            return None
        v = icc.loc[label, "ICC"]
        return None if pd.isna(v) else float(v)

    return _get("ICC(A,1)"), _get("ICC(A,k)")


def icc21_and_2k(matrix):
    """ICC(2,1) and ICC(2,k) on an n×k ratings matrix (positional entry point).

    The matrix form assigns rater identity *by column position*, which is
    only meaningful when each column is consistently the same rater across
    rows. Prefer `icc21_and_2k_long` when true rater IDs are available.
    """
    n = len(matrix)
    if n < 2:
        return None, None
    k = len(matrix[0]) if matrix else 0
    if k < 2 or any(len(row) != k for row in matrix):
        return None, None
    if any(v is None for row in matrix for v in row):
        return None, None
    triples = [(i, j, float(matrix[i][j])) for i in range(n) for j in range(k)]
    return icc21_and_2k_long(triples)


def _percentile_ci(values, n=2000):
    """Percentile bootstrap CI on the mean of `values`. Returns (lo, hi)."""
    arr = np.asarray(values, dtype=float)
    res = sp_stats.bootstrap(
        (arr,), np.mean, n_resamples=n, method="percentile",
        random_state=_BOOTSTRAP_RNG,
    )
    return float(res.confidence_interval.low), float(res.confidence_interval.high)


def bootstrap_mean_diff(a, b, n=2000):
    """Bootstrap CI on mean(a) - mean(b). Returns (point, lo95, hi95)."""
    a = np.asarray([float(x) for x in a if x is not None], dtype=float)
    b = np.asarray([float(x) for x in b if x is not None], dtype=float)
    if len(a) < 3 or len(b) < 3:
        return None, None, None
    point = float(a.mean() - b.mean())
    res = sp_stats.bootstrap(
        (a, b), lambda x, y, axis=-1: x.mean(axis=axis) - y.mean(axis=axis),
        n_resamples=n, method="percentile", random_state=_BOOTSTRAP_RNG,
        vectorized=True, paired=False,
    )
    return point, float(res.confidence_interval.low), float(res.confidence_interval.high)


def cluster_bootstrap_mean_diff(samples_a, samples_b, n=2000):
    """Cluster bootstrap on mean(a) - mean(b).

    Inputs are dicts cluster_id -> list[float] of that cluster's scores in
    arm a / arm b. We resample cluster ids with replacement (separately on
    each arm), then take all of the resampled cluster's observations.
    Clusters with no observation in an arm contribute nothing in that arm.

    Kept custom: scipy.stats.bootstrap operates on a flat sample array; it
    cannot resample cluster keys and expand to the cluster's variable-length
    observation lists.
    """
    cids_a = [c for c, xs in samples_a.items() if xs]
    cids_b = [c for c, xs in samples_b.items() if xs]
    if len(cids_a) < 3 or len(cids_b) < 3:
        return None, None, None
    flat_a = [v for xs in samples_a.values() for v in xs]
    flat_b = [v for xs in samples_b.values() for v in xs]
    if not flat_a or not flat_b:
        return None, None, None
    point = statistics.mean(flat_a) - statistics.mean(flat_b)
    diffs = []
    idx_a = _BOOTSTRAP_RNG.integers(0, len(cids_a), size=(n, len(cids_a)))
    idx_b = _BOOTSTRAP_RNG.integers(0, len(cids_b), size=(n, len(cids_b)))
    for r in range(n):
        sa = [v for i in idx_a[r] for v in samples_a[cids_a[i]]]
        sb = [v for i in idx_b[r] for v in samples_b[cids_b[i]]]
        if not sa or not sb:
            continue
        diffs.append(statistics.mean(sa) - statistics.mean(sb))
    if len(diffs) < 3:
        return point, None, None
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return point, float(lo), float(hi)


def paired_within_cluster_bootstrap(samples_a, samples_b, n=2000):
    """Bootstrap mean of within-cluster Δ = mean(a_c) - mean(b_c) over the
    subset of clusters that contributed to both arms. Returns
    (point, lo, hi, n_clusters_paired).
    """
    deltas = []
    for cid in set(samples_a) & set(samples_b):
        a, b = samples_a[cid], samples_b[cid]
        if not a or not b:
            continue
        deltas.append(statistics.mean(a) - statistics.mean(b))
    if len(deltas) < 3:
        return None, None, None, len(deltas)
    point = statistics.mean(deltas)
    lo, hi = _percentile_ci(deltas, n=n)
    return point, lo, hi, len(deltas)


def tost_mean_diff(a, b, eq_low=-5.0, eq_high=5.0, n=2000):
    """Bootstrap two-one-sided-tests (TOST) for equivalence of mean(a) and
    mean(b) within a band [eq_low, eq_high]. Equivalence claim requires
    both one-sided 95% bounds to fall inside the band.

    Returns dict with the one-sided bounds and per-hypothesis flags, or
    None if either arm is too small to bootstrap.
    """
    a_arr = np.asarray([float(x) for x in a if x is not None], dtype=float)
    b_arr = np.asarray([float(x) for x in b if x is not None], dtype=float)
    if len(a_arr) < 3 or len(b_arr) < 3:
        return None
    # One-sided 95% bounds = 5th and 95th percentiles of the bootstrapped diffs.
    idx_a = _BOOTSTRAP_RNG.integers(0, len(a_arr), size=(n, len(a_arr)))
    idx_b = _BOOTSTRAP_RNG.integers(0, len(b_arr), size=(n, len(b_arr)))
    diffs = a_arr[idx_a].mean(axis=1) - b_arr[idx_b].mean(axis=1)
    lo_one_sided = float(np.percentile(diffs, 5))
    hi_one_sided = float(np.percentile(diffs, 95))
    point = float(a_arr.mean() - b_arr.mean())
    return {
        "point_estimate": point,
        "eq_low": eq_low,
        "eq_high": eq_high,
        "one_sided_lower_95": lo_one_sided,
        "one_sided_upper_95": hi_one_sided,
        "reject_h0_low":  lo_one_sided > eq_low,
        "reject_h0_high": hi_one_sided < eq_high,
        "equivalent": (lo_one_sided > eq_low) and (hi_one_sided < eq_high),
    }


def clopper_pearson_ci(k, n, alpha=0.05):
    """Exact (Clopper--Pearson) two-sided binomial CI on k/n at 1-alpha.

    Returns (lo, hi); endpoints pinned to 0/1 when k=0 / k=n. Returns
    (None, None) when n=0. Used for the Calderon alt-test winning rate
    omega = #rejected / m on the small (m=5) reviewer roster.
    """
    if not n:
        return None, None
    lo, hi = sp_stats.binomtest(int(k), int(n)).proportion_ci(
        confidence_level=1 - alpha, method="exact",
    )
    return float(lo), float(hi)


# ----------------------------- data joins -----------------------------

def load_json(p: Path):
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def index_judge_on_humans(real):
    """annotation_id -> {raw, grade_points, passed, dimensions{...}}.

    Pulls LLM-judge evaluations that target human annotations from
    task-level `evaluations[]` whose field_name targets `human:loesung`.
    Handles both flat-key (Benchathon shape) and nested-dict (ZJS-style)
    metric encodings.
    """
    out = {}
    for task in real["tasks"]:
        for ev in task.get("evaluations") or []:
            fn = ev.get("field_name") or ""
            # Restrict to the baseline single-pass judge that anchors the RQ1/2/3
            # leaderboards. The 2026-05-21 export also carries Config A/B passes
            # (mpe7mkzx-2zp6, mpe7o02k-yrio); without this filter, whichever
            # config appears last per annotation silently wins via out[ann_id]
            # overwrite, contaminating every RQ5 / rq4_cocreation number.
            if not fn.startswith(BASELINE_JUDGE_FIELD_PREFIX):
                continue
            if "human:loesung" not in fn:
                continue
            m = ev.get("metrics") or {}
            judge = m.get("llm_judge_falloesung")

            # Shape A: nested `llm_judge_falloesung.details.raw_score` on 0-100.
            # Shape B: top-level `raw_score` plus `llm_judge_falloesung_response`.
            # Backfilled rows wear the Shape A envelope but the `details` blob
            # is a stub (just `{backfilled_legacy: true}` — the DB-side key
            # name pre-dates this rename and stays). `judge.get("value")` is
            # then a 0-1 ratio, the same scale trap fixed in
            # `_baseline_judge_score`. Gate Shape A on `details.raw_score is
            # not None` and otherwise fall through to the Shape B branch.
            details = {}
            raw = gp = passed = None
            dims_src = {}
            if isinstance(judge, dict):
                details = judge.get("details") or {}
                if details.get("raw_score") is not None:
                    dims_src = (
                        (details.get("judge_response") or {}).get("dimensions")
                        or (judge.get("judge_response") or {}).get("dimensions")
                        or details.get("dimensions")
                        or {}
                    )
                    raw = details["raw_score"]
                    gp = details.get("grade_points")
                    passed = details.get("passed")
            if raw is None:
                # Legacy Shape B: top-level keys on the metrics dict.
                response_blob = m.get("llm_judge_falloesung_response") or {}
                details_blob = m.get("llm_judge_falloesung_details") or {}
                if not dims_src:
                    dims_src = response_blob.get("dimensions") or details_blob.get("dimensions") or {}
                raw = m.get("raw_score") or m.get("llm_judge_falloesung_raw")
                if raw is None and isinstance(response_blob, dict):
                    raw = response_blob.get("score")
                gp = m.get("llm_judge_falloesung_grade_points") or response_blob.get("grade_points")
                passed_v = m.get("llm_judge_falloesung_passed")
                passed = bool(passed_v) if passed_v is not None else response_blob.get("passed")

            dims = {}
            for name, info in dims_src.items():
                if isinstance(info, dict):
                    s = info.get("score")
                    if s is not None:
                        dims[name] = float(s)

            out[ev["annotation_id"]] = {
                "raw_score": float(raw) if raw is not None else None,
                "grade_points": gp,
                "passed": bool(passed) if passed is not None else None,
                "dimensions": dims,
            }
    return out


def humans_by_solution(canonical_grades, *,
                       role_filter: str | None = None,
                       solution_type_filter: str | None = None):
    """Canonical-grades fold: solution_id -> list[grader_dict].

    `canonical_grades` is the schema produced by `derive_paper_exports.py::derive_human_grades`
    in `benchathon_human_grades.json` (`role`, `solution_type`, `bereich`,
    `system_or_user`, ... per row).

    Filters return only rows matching the requested role and/or solution
    type. This is the single entry point that downstream RQ4-human and RQ5
    analyses use, so swapping in the real expert grading export — once roles
    are populated — automatically restricts IRR to blind reviewers, surfaces
    creators separately, and exposes the LLM-solution rows.
    """
    by_sol: dict[str, list[dict]] = defaultdict(list)
    for r in canonical_grades:
        if role_filter is not None and r.get("role") != role_filter:
            continue
        if solution_type_filter is not None and r.get("solution_type") != solution_type_filter:
            continue
        by_sol[r["solution_id"]].append({
            "grader_id": r.get("grader_id"),
            "role": r.get("role"),
            "raw_score": r.get("raw_score"),
            "grade_points": r.get("grade_points"),
            "passed": r.get("passed"),
            "dimensions": r.get("dimensions") or {},
            "solution_type": r.get("solution_type"),
            "system_or_user": r.get("system_or_user"),
            "task_id": r.get("task_id"),
            "bereich": r.get("bereich"),
        })
    return by_sol


def annotation_to_task(real):
    out = {}
    for task in real["tasks"]:
        for ann in task.get("annotations") or []:
            out[ann["id"]] = task["id"]
    return out


def annotation_to_user(real):
    """annotation_id -> completed_by (participant id), for clustered RQ4
    resampling. Missing completed_by stays unmapped."""
    out = {}
    for task in real["tasks"]:
        for ann in task.get("annotations") or []:
            uid = ann.get("completed_by")
            if uid is not None:
                out[ann["id"]] = uid
    return out


# ----------------------------- analyses -----------------------------

def rq3_metric_correlations(model_evals, auto_metrics):
    """For each automatic metric, Pearson + Spearman vs LLM-judge raw_score
    over all LLM generations on Benchathon."""
    judge_by_gen = {r["generation_id"]: r["raw_score"] for r in model_evals}
    metric_pairs = defaultdict(lambda: ([], []))
    for r in auto_metrics:
        gid = r["generation_id"]
        if gid not in judge_by_gen:
            continue
        metric_pairs[r["metric"]][0].append(r["value"])
        metric_pairs[r["metric"]][1].append(judge_by_gen[gid])
    out = {}
    for m, (vals, judges) in metric_pairs.items():
        out[m] = {
            "n": len(vals),
            "pearson_vs_judge_raw": pearson(vals, judges),
            "spearman_vs_judge_raw": spearman(vals, judges),
        }
    return out


# Canonical order shared with manuscript.qmd's tbl-metric-correlation and the
# Appendix-H bar figures. Keep in sync with CANONICAL_METRIC_ORDER there.
CANONICAL_METRIC_ORDER = (
    "bleu", "rouge", "meteor", "chrf",
    "bertscore", "moverscore", "semantic_similarity", "coherence",
)

METRIC_LABELS_CSV = {
    "bleu": "BLEU", "rouge": "ROUGE", "meteor": "METEOR", "chrf": "chrF",
    "bertscore": "BERTScore", "moverscore": "MoverScore",
    "semantic_similarity": "Semantic similarity", "coherence": "Coherence",
}


def write_metric_correlation_csv(out_path, *, bench_llm, zjs_llm,
                                 grundprinzipien_llm, humans):
    """Emit one CSV mirroring manuscript.qmd's tbl-metric-correlation.

    Columns: metric, then one (pearson, spearman, n) triple per data source
    in the order Benchathon-LLM / ZJS-LLM / Grundprinzipien-LLM /
    Benchathon-human-traditional / Benchathon-human-cocreation. Empty cells
    are written as empty strings.
    """
    import csv

    sources = [
        ("benchathon_llm",          bench_llm),
        ("zjs_llm",                 zjs_llm),
        ("grundprinzipien_llm",     grundprinzipien_llm),
        ("benchathon_human_trad",   (humans or {}).get("classic") or {}),
        ("benchathon_human_cocreat",(humans or {}).get("cocreation") or {}),
    ]

    header = ["metric", "metric_label"]
    for col, _ in sources:
        header += [f"{col}__pearson", f"{col}__spearman", f"{col}__n"]

    rows = []
    for m in CANONICAL_METRIC_ORDER:
        row = [m, METRIC_LABELS_CSV.get(m, m)]
        for _, d in sources:
            v = (d.get(m) or {})
            r = v.get("pearson_vs_judge_raw")
            s = v.get("spearman_vs_judge_raw")
            n = v.get("n")
            row += [
                "" if r is None else f"{r:.6f}",
                "" if s is None else f"{s:.6f}",
                "" if n in (None, 0) else str(n),
            ]
        rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {out_path}")


def rq3_metric_correlations_humans(human_auto_metrics, judge_on_humans):
    """Same shape as rq3_metric_correlations(), but restricted to human-written
    annotations and split by working condition (classic / co-creation).

    `human_auto_metrics` is the list emitted by
    derive_paper_exports.derive_human_automatic_metrics — rows already carry
    the `variant` ('ai' / 'no_ai' / None) joined in from the instruction-variant
    map.
    """
    pairs: dict[str, dict[str, tuple[list, list]]] = {
        "classic":    defaultdict(lambda: ([], [])),
        "cocreation": defaultdict(lambda: ([], [])),
    }
    for r in human_auto_metrics:
        j = judge_on_humans.get(r["annotation_id"])
        if not j or j.get("raw_score") is None:
            continue
        v = r.get("variant")
        bucket = "cocreation" if v == "ai" else "classic" if v == "no_ai" else None
        if bucket is None:
            continue
        vals, judges = pairs[bucket][r["metric"]]
        vals.append(r["value"])
        judges.append(j["raw_score"])

    out: dict[str, dict] = {}
    for bucket, by_metric in pairs.items():
        out[bucket] = {
            m: {
                "n": len(vs),
                "pearson_vs_judge_raw": pearson(vs, js),
                "spearman_vs_judge_raw": spearman(vs, js),
            }
            for m, (vs, js) in by_metric.items()
        }
    return out


def rq4_cocreation(judge_on_humans, ann_to_task, variants, ann_to_user):
    """Mean judge raw on traditional vs co-creation human solutions.

    Headline CI is the participant-cluster bootstrap; the i.i.d. bootstrap
    and a task-cluster variant are also reported as Appendix diagnostics,
    and the within-participant paired Δ provides a strict robustness check
    on the subset of participants who appear in both arms.
    """
    trad, ai = [], []
    by_user_trad: dict[str, list[float]] = defaultdict(list)
    by_user_ai:   dict[str, list[float]] = defaultdict(list)
    by_task_trad: dict[str, list[float]] = defaultdict(list)
    by_task_ai:   dict[str, list[float]] = defaultdict(list)
    for ann_id, j in judge_on_humans.items():
        v = variants.get(ann_id)
        raw = j.get("raw_score")
        if raw is None:
            continue
        uid = ann_to_user.get(ann_id)
        tid = ann_to_task.get(ann_id)
        if v == "ai":
            ai.append(raw)
            if uid: by_user_ai[uid].append(raw)
            if tid: by_task_ai[tid].append(raw)
        elif v == "no_ai":
            trad.append(raw)
            if uid: by_user_trad[uid].append(raw)
            if tid: by_task_trad[tid].append(raw)

    point_iid, lo_iid, hi_iid = bootstrap_mean_diff(ai, trad)
    point_pc,  lo_pc,  hi_pc  = cluster_bootstrap_mean_diff(by_user_ai, by_user_trad)
    point_tc,  lo_tc,  hi_tc  = cluster_bootstrap_mean_diff(by_task_ai, by_task_trad)
    point_pp,  lo_pp,  hi_pp,  n_paired = paired_within_cluster_bootstrap(
        by_user_ai, by_user_trad)

    return {
        "n_traditional": len(trad),
        "n_co_creation": len(ai),
        "n_participants_paired": n_paired,
        "n_participants_trad": len(by_user_trad),
        "n_participants_ai":   len(by_user_ai),
        "mean_traditional": statistics.mean(trad) if trad else None,
        "mean_co_creation": statistics.mean(ai) if ai else None,
        # Headline = participant cluster bootstrap. Manuscript prose
        # already inlines `mean_diff_ai_minus_trad`, `ci95_lo`, `ci95_hi`,
        # so the names stay; only the resampling unit changes.
        "mean_diff_ai_minus_trad": point_pc,
        "ci95_lo": lo_pc,
        "ci95_hi": hi_pc,
        # Diagnostics for the methods appendix.
        "mean_diff_ai_minus_trad_iid": point_iid,
        "ci95_lo_iid": lo_iid,
        "ci95_hi_iid": hi_iid,
        "ci95_lo_cluster_task": lo_tc,
        "ci95_hi_cluster_task": hi_tc,
        "mean_diff_cluster_task": point_tc,
        "mean_diff_paired_within_participant": point_pp,
        "ci95_lo_paired_within_participant": lo_pp,
        "ci95_hi_paired_within_participant": hi_pp,
    }


def rq5_judge_vs_human(judge_on_humans, humans):
    """Per-solution judge vs mean-human; pairs across the expert-graded subset.

    `humans` is keyed by solution_id (per humans_by_solution). For human-
    written Benchathon entries the solution_id and annotation_id coincide,
    so `judge_on_humans[solution_id]` resolves; on LLM solutions (whose
    annotation_id is null and whose judge scores live in model_evals via
    generation_id) the lookup misses and the loop skips them, restricting
    this function to human-authored solutions. The LLM-side equivalent is
    rq5_judge_on_llm_solutions.
    """
    j_raw, h_raw, j_gp, h_gp, j_pass, h_pass = [], [], [], [], [], []
    for solution_id, graders in humans.items():
        j = judge_on_humans.get(solution_id)
        if not j:
            continue
        mean_h_raw = statistics.mean(g["raw_score"] for g in graders if g["raw_score"] is not None)
        mean_h_gp = statistics.mean(g["grade_points"] for g in graders if g["grade_points"] is not None)
        # Majority pass
        passed = [g["passed"] for g in graders if g["passed"] is not None]
        mean_h_pass = sum(passed) > len(passed) / 2 if passed else None
        if j["raw_score"] is None:
            continue
        j_raw.append(j["raw_score"]); h_raw.append(mean_h_raw)
        if j["grade_points"] is not None and mean_h_gp is not None:
            j_gp.append(j["grade_points"]); h_gp.append(mean_h_gp)
        if j["passed"] is not None and mean_h_pass is not None:
            j_pass.append(j["passed"]); h_pass.append(mean_h_pass)
    # Bias-corrected residual MAE: subtract the mean systematic offset
    # before taking |·|, so the calibration shift the judge-calibration
    # audit documents (~+11.7 raw / ~+27 raw on LLM picks) doesn't
    # silently dominate what we present as "disagreement".
    def _bias_corrected_mae(js, hs):
        if not js or not hs:
            return None
        delta = statistics.mean(js) - statistics.mean(hs)
        return statistics.mean(abs((j - h) - delta) for j, h in zip(js, hs))
    return {
        "n_annotations": len(j_raw),
        "pearson_raw": pearson(j_raw, h_raw),
        "spearman_raw": spearman(j_raw, h_raw),
        "mae_raw": mae(j_raw, h_raw),
        "mae_grade_points": mae(j_gp, h_gp),
        "mae_raw_bias_corrected": _bias_corrected_mae(j_raw, h_raw),
        "mae_grade_points_bias_corrected": _bias_corrected_mae(j_gp, h_gp),
        "judge_minus_pool_mean_raw": (
            statistics.mean(j_raw) - statistics.mean(h_raw) if j_raw and h_raw else None),
        "judge_minus_pool_mean_grade_points": (
            statistics.mean(j_gp) - statistics.mean(h_gp) if j_gp and h_gp else None),
        "passfail_cohen_kappa": cohen_kappa(j_pass, h_pass),
        "mean_judge_raw": statistics.mean(j_raw) if j_raw else None,
        "mean_human_raw_mean": statistics.mean(h_raw) if h_raw else None,
    }


def rq5_human_irr(humans):
    """ICC(2,1) and ICC(2,k) across solutions graded by k blind raters.
    Also within-solution spread on raw and grade points.

    Real grading coverage is partially crossed (k=3 blind raters per
    solution, drawn from a roster of m=5 — so different solutions see
    different rater triplets). We report two numbers:

    * **Pooled positional ICC** (`icc_2_1_raw` etc.) — the Shrout-Fleiss
      formula on an n×k matrix where column j is the j-th rater *in source-
      file order*, so column identity isn't a stable rater identity. The
      number is well-defined and matches what the manuscript was written
      against, but it's a conservative approximation: random column-position
      noise inflates MSC and pulls ICC down relative to the strict version.

    * **Balanced-subset ICC** (`balanced_subset.icc_2_1_raw` etc.) — the
      strict ICC(2,*) on the largest subset of solutions sharing the same
      rater triplet, computed in long format with real grader IDs. Smaller
      n, but the only number that carries a clean ICC(2,*) interpretation.

    The `max_k_subset` field uses the same modal-k logic (modal k among
    k>=3) as before.
    """
    from collections import Counter as _Counter
    rows_raw_all, rows_gp_all = [], []
    rows_raw_with_ids, rows_gp_with_ids = [], []   # parallel: (sol_id, [(gid, v), ...])
    spreads_raw, spreads_gp = [], []
    for solution_id, graders in humans.items():
        if len(graders) < 2:
            continue
        raw_pairs = [(g["grader_id"], g["raw_score"]) for g in graders]
        gp_pairs  = [(g["grader_id"], g["grade_points"]) for g in graders]
        if all(v is not None for _, v in raw_pairs):
            rows_raw_all.append([v for _, v in raw_pairs])
            rows_raw_with_ids.append((solution_id, raw_pairs))
            spreads_raw.append(max(v for _, v in raw_pairs) - min(v for _, v in raw_pairs))
        if all(v is not None for _, v in gp_pairs):
            rows_gp_all.append([v for _, v in gp_pairs])
            rows_gp_with_ids.append((solution_id, gp_pairs))
            spreads_gp.append(max(v for _, v in gp_pairs) - min(v for _, v in gp_pairs))

    def _icc_at_k(rows, k):
        sub = [r for r in rows if len(r) == k]
        return sub, icc21_and_2k(sub)

    def _balanced_icc_long(rows_with_ids):
        """ICC(2,*) on the largest subset of solutions sharing one rater set."""
        if not rows_with_ids:
            return None, None, [], None
        triplet_counts = _Counter(
            frozenset(gid for gid, _ in pairs) for _, pairs in rows_with_ids
        )
        if not triplet_counts:
            return None, None, [], None
        modal_set, _ = triplet_counts.most_common(1)[0]
        subset = [(sid, pairs) for sid, pairs in rows_with_ids
                  if frozenset(gid for gid, _ in pairs) == modal_set]
        if len(subset) < 2:
            return None, None, subset, sorted(modal_set)
        triples = [(sid, gid, v) for sid, pairs in subset for gid, v in pairs]
        icc_1, icc_k = icc21_and_2k_long(triples)
        return icc_1, icc_k, subset, sorted(modal_set)

    # Pooled positional ICC (matrix on all multi-graded solutions; column j
    # is the j-th rater in source-file order, not a stable rater identity).
    if rows_raw_all:
        k_modal_raw = _Counter(len(r) for r in rows_raw_all).most_common(1)[0][0]
    else:
        k_modal_raw = None
    if rows_gp_all:
        k_modal_gp = _Counter(len(r) for r in rows_gp_all).most_common(1)[0][0]
    else:
        k_modal_gp = None
    rows_modal_raw, (icc1_raw, iccK_raw) = _icc_at_k(rows_raw_all, k_modal_raw) if k_modal_raw else ([], (None, None))
    rows_modal_gp, (icc1_gp, iccK_gp) = _icc_at_k(rows_gp_all, k_modal_gp) if k_modal_gp else ([], (None, None))

    # Balanced-subset ICC (rater-identity-aware)
    bal_icc1_raw, bal_iccK_raw, bal_subset_raw, bal_raters_raw = _balanced_icc_long(rows_raw_with_ids)
    bal_icc1_gp,  bal_iccK_gp,  bal_subset_gp,  bal_raters_gp  = _balanced_icc_long(rows_gp_with_ids)

    # k>=3: the tightest-IRR subset that modal-k filtering drops when the mode
    # is k=2. icc21_and_2k requires balanced rows; pick the modal k among k>=3.
    rows_raw_ge3 = [r for r in rows_raw_all if len(r) >= 3]
    rows_gp_ge3  = [r for r in rows_gp_all  if len(r) >= 3]
    if rows_raw_ge3:
        k_max_balanced_raw = _Counter(len(r) for r in rows_raw_ge3).most_common(1)[0][0]
        rows_maxk_raw, (icc1_raw_max, iccK_raw_max) = _icc_at_k(rows_raw_ge3, k_max_balanced_raw)
    else:
        k_max_balanced_raw, rows_maxk_raw, icc1_raw_max, iccK_raw_max = None, [], None, None
    if rows_gp_ge3:
        k_max_balanced_gp = _Counter(len(r) for r in rows_gp_ge3).most_common(1)[0][0]
        rows_maxk_gp, (icc1_gp_max, iccK_gp_max) = _icc_at_k(rows_gp_ge3, k_max_balanced_gp)
    else:
        k_max_balanced_gp, rows_maxk_gp, icc1_gp_max, iccK_gp_max = None, [], None, None

    return {
        "n_annotations": len(rows_modal_raw),
        "k_raters": len(rows_modal_raw[0]) if rows_modal_raw else None,
        "icc_2_1_raw": icc1_raw,
        "icc_2_k_raw": iccK_raw,
        "icc_2_1_grade_points": icc1_gp,
        "icc_2_k_grade_points": iccK_gp,
        "mean_within_ann_spread_raw": statistics.mean(spreads_raw) if spreads_raw else None,
        "mean_within_ann_spread_grade_points": statistics.mean(spreads_gp) if spreads_gp else None,
        "mean_judge_human_dev_vs_human_human_dev_ratio": None,  # filled in main
        # Strict ICC(2,*) on the largest rater-triplet-balanced subset.
        # Smaller n; preserves true rater identity instead of column-position
        # alignment. Reported alongside the pooled positional value above so
        # the difference between the two is auditable.
        "balanced_subset": {
            "raw": {
                "n_solutions": len(bal_subset_raw),
                "rater_ids": bal_raters_raw,
                "icc_2_1": bal_icc1_raw,
                "icc_2_k": bal_iccK_raw,
            },
            "grade_points": {
                "n_solutions": len(bal_subset_gp),
                "rater_ids": bal_raters_gp,
                "icc_2_1": bal_icc1_gp,
                "icc_2_k": bal_iccK_gp,
            },
        },
        # Tightest-IRR subset (k>=3); reported alongside the modal-k ICC so the
        # reader can see whether agreement holds on the more heavily-graded
        # annotations (which modal-k=2 filtering otherwise drops).
        "max_k_subset": {
            "n_annotations": len(rows_maxk_raw),
            "k_raters": k_max_balanced_raw,
            "icc_2_1_raw": icc1_raw_max,
            "icc_2_k_raw": iccK_raw_max,
            "icc_2_1_grade_points": icc1_gp_max,
            "icc_2_k_grade_points": iccK_gp_max,
        },
    }


def rq5_dim_agreement(judge_on_humans, humans):
    """Per-dimension Pearson(judge, mean_human) + MAE."""
    out = {}
    for d in DIMENSIONS:
        j_vals, h_vals = [], []
        for solution_id, graders in humans.items():
            j = judge_on_humans.get(solution_id)
            if not j:
                continue
            jv = j["dimensions"].get(d)
            human_dims = [g["dimensions"].get(d) for g in graders if g["dimensions"].get(d) is not None]
            if jv is None or not human_dims:
                continue
            j_vals.append(jv)
            h_vals.append(statistics.mean(human_dims))
        out[d] = {
            "n": len(j_vals),
            "pearson_judge_vs_mean_human": pearson(j_vals, h_vals),
            "mae_dim_points": mae(j_vals, h_vals),
        }
    return out


# ----------------------------- Calderon alt-test -----------------------------

# Implementation of the Alternative Annotator Test (alt-test) of
# Calderon, Reichart & Dror, ACL 2025 (arXiv:2501.10970). The §3 procedure
# tests whether the LLM judge can stand in for a randomly drawn human
# annotator from the blind-reviewer pool; the §D.2 variant compares against
# a single expert reference (here: the un-blind creator grade). Both share
# the per-annotator paired test, Benjamini–Yekutieli FDR, and winning-rate
# decision rule. See `publications/Dataset_ARR/scripts/test_rq5_calderon.py`
# for hand-traced regression toys.

# Minimum per-annotator instance count before we run a test. Paper §3.3 uses
# Wilcoxon as the small-n fallback (n<30) but does not give a hard floor;
# below ~5 the Wilcoxon p-value is too coarse to matter. We drop annotators
# below this cutoff and surface the count in `m_dropped_low_n`.
_ALTTEST_MIN_N_J = 5


def _by_fdr(pvals, q=0.05):
    """Benjamini–Yekutieli FDR controller (Calderon Alg. 1, paper p. 24).

    BY (not Benjamini–Hochberg) is required because the m hypotheses are
    dependent: they all share the per-instance `H_i\\{j}` reference pool.
    Returns a list of bool — True iff the corresponding p-value is rejected
    at the BY-adjusted threshold.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    cm = sum(1.0 / k for k in range(1, m + 1))
    rejected = [False] * m
    for rank, idx in enumerate(order, start=1):
        threshold = (rank / m) * (q / cm)
        if pvals[idx] <= threshold:
            # Reject p_(1)..p_(rank); later passes only re-mark the same set
            # or extend it, so the final state reflects the largest rank that
            # met its threshold.
            for r in range(rank):
                rejected[order[r]] = True
    return rejected


def _advantage_test(d, eps):
    """One-sided paired test of d̄ > ε on the per-instance difference series.

    `d` is the list of W^h_{i,j} - W^f_{i,j} indicators across the instances
    annotator h_j graded (each entry in {-1, 0, 1}). Paper §3.3:
      t_j = (d̄_j - ε) / (s_j / sqrt(n_j)), α = 0.05, one-sided.
    Falls back to Wilcoxon signed-rank when n_j < 30 (paper §3.3).
    Returns (n_j, test_name, statistic, p_value, d_bar).
    """
    from scipy import stats  # local: keeps stdlib-only smoke tests cheap

    n = len(d)
    if n == 0:
        return n, "none", None, 1.0, None
    d_bar = sum(d) / n
    # H_0j: ρ^f_j ≤ ρ^h_j - ε  <=>  d̄ ≥ ε   (since d = W^h - W^f).
    # H_1j: ρ^f_j > ρ^h_j - ε   <=>  d̄ < ε.
    # We reject H_0j when d̄ is significantly LESS than ε (judge wins by more
    # than the cost-benefit penalty allows for the human alternative).
    if n >= 30:
        s = math.sqrt(sum((x - d_bar) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
        if s == 0.0:
            # Degenerate: all d_i identical. Reject iff d̄ < ε.
            return n, "t", float("-inf") if d_bar < eps else float("inf"), \
                   (0.0 if d_bar < eps else 1.0), d_bar
        t_stat = (d_bar - eps) / (s / math.sqrt(n))
        # Lower-tail p: P(T <= t_stat) under H_0.
        p = float(stats.t.cdf(t_stat, df=n - 1))
        return n, "t", float(t_stat), p, d_bar

    # Wilcoxon signed-rank fallback. We test whether d - ε is significantly
    # LESS than zero (one-sided). scipy.wilcoxon's `alternative='less'` does
    # exactly this. zero_method='wilcox' drops zero differences (paper's
    # default convention).
    shifted = [x - eps for x in d]
    nonzero = [x for x in shifted if x != 0]
    if not nonzero:
        # All instances are ties at d_i = ε; cannot reject.
        return n, "wilcoxon", None, 1.0, d_bar
    try:
        # method="exact" pins the small-n permutation distribution; scipy's
        # default `method="auto"` switched behaviour between scipy 1.13 and
        # 1.17 for n in the 7–25 range we hit here, which silently moved
        # FDR-corrected p-values across the rejection boundary.
        res = stats.wilcoxon(shifted, alternative="less", zero_method="wilcox",
                             method="exact")
        return n, "wilcoxon", float(res.statistic), float(res.pvalue), d_bar
    except ValueError:
        # scipy raises if all values are zero or n is too small.
        return n, "wilcoxon", None, 1.0, d_bar


def _alt_test_blind_pool(annotators_with_others, *, eps):
    """Run the §3 alt-test on the per-annotator instance lists.

    `annotators_with_others` maps grader_id -> list of (judge_score,
    h_j_score, [other_scores]) tuples — one entry per instance h_j graded
    where the judge also graded and ≥2 other humans graded (i.e.
    |H_i| ≥ 3 after excluding h_j).
    """
    per_annotator = []
    p_values = []
    for grader_id, rows in sorted(annotators_with_others.items()):
        if len(rows) < _ALTTEST_MIN_N_J:
            continue
        w_f, w_h, d = [], [], []
        for judge_score, hj, others in rows:
            # -RMSE alignment (paper §3.1, continuous-task variant).
            s_f = -math.sqrt(sum((judge_score - h_k) ** 2 for h_k in others) / len(others))
            s_h = -math.sqrt(sum((hj - h_k) ** 2 for h_k in others) / len(others))
            w_f_i = 1 if s_f >= s_h else 0
            w_h_i = 1 if s_h >= s_f else 0
            w_f.append(w_f_i)
            w_h.append(w_h_i)
            d.append(w_h_i - w_f_i)
        rho_f = sum(w_f) / len(w_f)
        rho_h = sum(w_h) / len(w_h)
        n_j, test, stat, p, d_bar = _advantage_test(d, eps)
        per_annotator.append({
            "grader_id": grader_id,
            "n_j": n_j,
            "rho_f": rho_f,
            "rho_h": rho_h,
            "d_bar": d_bar,
            "test": test,
            "statistic": stat,
            "p_value": p,
        })
        p_values.append(p)

    rejected = _by_fdr(p_values, q=0.05)
    for entry, rj in zip(per_annotator, rejected):
        entry["rejected_BY_FDR"] = bool(rj)
    m = len(per_annotator)
    n_rej = sum(rejected) if m else None
    omega = (n_rej / m) if m else None
    omega_lo, omega_hi = clopper_pearson_ci(n_rej, m) if m else (None, None)
    rho = (sum(e["rho_f"] for e in per_annotator) / m) if m else None
    return {
        "epsilon": eps,
        "m_annotators": m,
        "per_annotator": per_annotator,
        "n_rejected": n_rej,
        "winning_rate": omega,
        "winning_rate_ci95_lo_clopper": omega_lo,
        "winning_rate_ci95_hi_clopper": omega_hi,
        "avg_advantage_probability": rho,
        "passes_alt_test": (omega is not None and omega >= 0.5),
    }


def _alt_test_single_expert(annotators_with_expert, *, eps):
    """Run the §D.2 single-expert variant.

    `annotators_with_expert` maps grader_id -> list of (judge_score,
    h_j_score, expert_score) tuples — one entry per instance h_j graded
    where the judge also graded and the expert reference exists.
    Alignment score is point-wise distance to the expert (paper §D.2).
    """
    per_annotator = []
    p_values = []
    for grader_id, rows in sorted(annotators_with_expert.items()):
        if len(rows) < _ALTTEST_MIN_N_J:
            continue
        w_f, w_h, d = [], [], []
        for judge_score, hj, exp in rows:
            s_f = -abs(judge_score - exp)
            s_h = -abs(hj - exp)
            w_f_i = 1 if s_f >= s_h else 0
            w_h_i = 1 if s_h >= s_f else 0
            w_f.append(w_f_i)
            w_h.append(w_h_i)
            d.append(w_h_i - w_f_i)
        rho_f = sum(w_f) / len(w_f)
        rho_h = sum(w_h) / len(w_h)
        n_j, test, stat, p, d_bar = _advantage_test(d, eps)
        per_annotator.append({
            "grader_id": grader_id,
            "n_j": n_j,
            "rho_f": rho_f,
            "rho_h": rho_h,
            "d_bar": d_bar,
            "test": test,
            "statistic": stat,
            "p_value": p,
        })
        p_values.append(p)

    rejected = _by_fdr(p_values, q=0.05)
    for entry, rj in zip(per_annotator, rejected):
        entry["rejected_BY_FDR"] = bool(rj)
    m = len(per_annotator)
    n_rej = sum(rejected) if m else None
    omega = (n_rej / m) if m else None
    omega_lo, omega_hi = clopper_pearson_ci(n_rej, m) if m else (None, None)
    rho = (sum(e["rho_f"] for e in per_annotator) / m) if m else None
    return {
        "epsilon": eps,
        "m_annotators": m,
        "per_annotator": per_annotator,
        "n_rejected": n_rej,
        "winning_rate": omega,
        "winning_rate_ci95_lo_clopper": omega_lo,
        "winning_rate_ci95_hi_clopper": omega_hi,
        "avg_advantage_probability": rho,
        "passes_alt_test": (omega is not None and omega >= 0.5),
    }


def _build_blind_pool_inputs(judge_scores_by_solution, humans):
    """Build per-annotator instance lists for the §3 blind-pool test.

    `judge_scores_by_solution` is a dict solution_id -> float (the LLM
    judge's raw_score, already filtered to entries that have a score).
    `humans` is the blind-rater map solution_id -> list[grader_dict].
    Each instance must have ≥ 3 blind raters AND a judge score (so that
    excluding h_j still leaves ≥ 2 references for -RMSE).
    """
    per_annot = defaultdict(list)
    total_instances = 0
    for solution_id, graders in humans.items():
        rated = [(g.get("grader_id") or "", g["raw_score"])
                 for g in graders if g["raw_score"] is not None]
        if len(rated) < 3:
            continue
        judge = judge_scores_by_solution.get(solution_id)
        if judge is None:
            continue
        total_instances += 1
        for k, (gid, hj) in enumerate(rated):
            others = [r for i, (_, r) in enumerate(rated) if i != k]
            per_annot[gid].append((float(judge), float(hj), [float(x) for x in others]))
    return per_annot, total_instances


def _build_single_expert_inputs(judge_scores_by_solution, humans, expert_by_solution):
    """Build per-annotator instance lists for the §D.2 single-expert variant.

    `expert_by_solution` maps solution_id -> float expert reference grade
    (mean of creator-role grades). Each instance must have the expert grade,
    the judge grade, and a blind-rater grade.
    """
    per_annot = defaultdict(list)
    total_instances = 0
    for solution_id, graders in humans.items():
        exp = expert_by_solution.get(solution_id)
        if exp is None:
            continue
        judge = judge_scores_by_solution.get(solution_id)
        if judge is None:
            continue
        rated = [(g.get("grader_id") or "", g["raw_score"])
                 for g in graders if g["raw_score"] is not None]
        if not rated:
            continue
        total_instances += 1
        for gid, hj in rated:
            per_annot[gid].append((float(judge), float(hj), float(exp)))
    return per_annot, total_instances


def _expert_grades_by_solution(canonical_grades):
    """Mean creator-role grade per solution. Returns {} if no creator rows."""
    by_sol = defaultdict(list)
    for r in canonical_grades:
        if r.get("role") != "creator":
            continue
        if r.get("raw_score") is None:
            continue
        by_sol[r["solution_id"]].append(float(r["raw_score"]))
    return {s: statistics.mean(vs) for s, vs in by_sol.items() if vs}


def rq5_calderon(judge_on_humans, humans, canonical_grades=None, *,
                 eps_blind_pool=0.15, eps_single_expert_values=(0.15, 0.20)):
    """Calderon alt-test on human-authored solutions.

    Returns a dict with two sub-payloads:
      - `blind_pool` : §3 procedure against the m blind reviewers, ε=0.15.
      - `single_expert` : §D.2 variant against the un-blind creator grade,
        keyed by ε ∈ {0.15, 0.20} so the headline (user-set ε=0.20) and the
        Calderon "cost-of-alternative" sensitivity check (ε=0.15) are both
        visible to the manuscript.

    `canonical_grades` is the schema produced by derive_paper_exports.derive_
    human_grades. Used to extract the creator reference for §D.2; if missing
    or empty, the §D.2 payload is None.
    """
    judge_by_sol = {sid: float(j["raw_score"]) for sid, j in judge_on_humans.items()
                    if j.get("raw_score") is not None}

    # §3 — blind-reviewer pool.
    blind_inputs, n_blind = _build_blind_pool_inputs(judge_by_sol, humans)
    blind_payload = _alt_test_blind_pool(blind_inputs, eps=eps_blind_pool)
    blind_payload["variant"] = "calderon_section_3"
    blind_payload["reference"] = "blind_reviewer_pool"
    blind_payload["n_instances_total"] = n_blind

    # §D.2 — single expert (creator).
    single_expert_payload = None
    if canonical_grades:
        expert_by_sol = _expert_grades_by_solution(canonical_grades)
        if expert_by_sol:
            se_inputs, n_se = _build_single_expert_inputs(
                judge_by_sol, humans, expert_by_sol)
            se_by_eps = {}
            for eps in eps_single_expert_values:
                payload = _alt_test_single_expert(se_inputs, eps=eps)
                payload["variant"] = "calderon_section_D2_single_expert"
                payload["reference"] = "creator_unblind"
                payload["n_instances_total"] = n_se
                se_by_eps[f"{eps:.2f}"] = payload
            single_expert_payload = {
                "variant": "calderon_section_D2_single_expert",
                "reference": "creator_unblind",
                "n_instances_with_creator_and_judge": n_se,
                "epsilon_results": se_by_eps,
            }

    return {
        "blind_pool": blind_payload,
        "single_expert": single_expert_payload,
    }


def rq3_rank_correlation(model_evals, auto_metrics, zjs_summary):
    """System-level rank correlation: for each automatic metric, do per-system
    means rank the systems the same way the LLM judge does?

    Benchathon: aggregate per-(system, metric) means from auto_metrics and
    per-system judge means from model_evals; Spearman ρ on system ordering.
    ZJS: read per-system per-metric means directly from zjs_summary.

    Reviewer-friendly version of RQ3 — answers "would a metric-only leaderboard
    rank systems the same way as the judge?" without ambiguous per-generation
    averaging.
    """
    out = {"benchathon": {}, "zjs": {}}

    # Benchathon: build per-system means.
    judge_by_sys: dict[str, list[float]] = defaultdict(list)
    for r in model_evals:
        if r.get("raw_score") is not None:
            judge_by_sys[r["system"]].append(float(r["raw_score"]))

    metric_by_sys: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in auto_metrics:
        v = r.get("value")
        if v is None:
            continue
        metric_by_sys[r["metric"]][r["system"]].append(float(v))

    judge_mean_by_sys = {s: statistics.mean(vs) for s, vs in judge_by_sys.items() if vs}

    for metric, by_sys in metric_by_sys.items():
        common = [s for s in by_sys if s in judge_mean_by_sys and by_sys[s]]
        if len(common) < 3:
            out["benchathon"][metric] = {
                "n_systems": len(common),
                "spearman_metric_vs_judge": None,
                "pearson_metric_vs_judge": None,
            }
            continue
        metric_means = [statistics.mean(by_sys[s]) for s in common]
        judge_means = [judge_mean_by_sys[s] for s in common]
        out["benchathon"][metric] = {
            "n_systems": len(common),
            "spearman_metric_vs_judge": spearman(metric_means, judge_means),
            "pearson_metric_vs_judge": pearson(metric_means, judge_means),
        }

    # ZJS: per-system per-metric means are in zjs_summary already.
    if zjs_summary:
        # Identify which metric keys exist across systems.
        metric_keys = set()
        for r in zjs_summary:
            for k in (r.get("metrics") or {}):
                if k.endswith("_mean") and k != "grade_points_mean" and k != "llm_judge_falloesung_raw_mean":
                    metric_keys.add(k)
        judge_key = "llm_judge_falloesung_raw_mean"

        for k in sorted(metric_keys):
            pairs = []
            for r in zjs_summary:
                m = r.get("metrics") or {}
                if k in m and judge_key in m and m[k] is not None and m[judge_key] is not None:
                    pairs.append((m[k], m[judge_key]))
            if len(pairs) < 3:
                out["zjs"][k.removesuffix("_mean")] = {
                    "n_systems": len(pairs),
                    "spearman_metric_vs_judge": None,
                    "pearson_metric_vs_judge": None,
                }
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            out["zjs"][k.removesuffix("_mean")] = {
                "n_systems": len(pairs),
                "spearman_metric_vs_judge": spearman(xs, ys),
                "pearson_metric_vs_judge": pearson(xs, ys),
            }
    return out


def tier_provider_aggregates(model_evals, zjs_summary, systems_meta):
    """Per-tier, per-provider, and open-vs-closed-weight aggregates of judge
    raw scores on each corpus. RQ2 evidence: directly answers how performance
    varies across deployed system tiers and provider families.

    Benchathon: bootstrap 95% CI over per-generation raw scores.
    ZJS: per-system means averaged within the group (no per-generation
    bootstrap because the ZJS summary file only carries per-system means).
    """
    meta_by_sys = {s["model_id"]: s for s in systems_meta}

    def _group_bench(group_key):
        by_group: dict[str, list[float]] = defaultdict(list)
        sys_by_group: dict[str, set[str]] = defaultdict(set)
        for r in model_evals:
            m = meta_by_sys.get(r["system"])
            if not m:
                continue
            raw = r.get("raw_score")
            if raw is None:
                continue
            key = m.get(group_key)
            if not key:
                continue
            by_group[key].append(float(raw))
            sys_by_group[key].add(r["system"])
        out = {}
        for key, vals in by_group.items():
            mean = statistics.mean(vals)
            lo, hi = _percentile_ci(vals, n=2000)
            out[key] = {
                "n_systems": len(sys_by_group[key]),
                "n_generations": len(vals),
                "mean_raw": mean,
                "ci95_lo": lo,
                "ci95_hi": hi,
            }
        return out

    def _group_zjs(group_key):
        per_system_means: dict[str, list[float]] = defaultdict(list)
        sys_by_group: dict[str, set[str]] = defaultdict(set)
        for r in (zjs_summary or []):
            m = meta_by_sys.get(r["system"])
            if not m:
                continue
            mean_raw = (r.get("metrics") or {}).get("llm_judge_falloesung_raw_mean")
            if mean_raw is None:
                continue
            key = m.get(group_key)
            if not key:
                continue
            per_system_means[key].append(float(mean_raw))
            sys_by_group[key].add(r["system"])
        out = {}
        for key, means in per_system_means.items():
            if not means:
                continue
            out[key] = {
                "n_systems": len(sys_by_group[key]),
                "mean_raw": statistics.mean(means),
                "min": min(means),
                "max": max(means),
            }
        return out

    return {
        "benchathon": {
            "by_tier":     _group_bench("tier"),
            "by_provider": _group_bench("provider"),
            "by_weights":  _group_bench("weights"),
        },
        "zjs": {
            "by_tier":     _group_zjs("tier"),
            "by_provider": _group_zjs("provider"),
            "by_weights":  _group_zjs("weights"),
        },
    }


def rq5_judge_repeats(judge_repeats):
    if not judge_repeats:
        return None
    stds = [r["stdev"] for r in judge_repeats if r.get("stdev") is not None]
    return {
        "n_generations_with_repeats": len(judge_repeats),
        "mean_within_gen_stdev": statistics.mean(stds) if stds else None,
    }


# --------- forward-compatible blocks for the real human-grading layer ---------

def rq4_cocreation_by_bereich(judge_on_humans, variants, real):
    """RQ4 trad vs co-creation, split by legal domain (Zivilrecht / Strafrecht
    / Öffentliches Recht). Uses judge-on-human scores, same source as the
    main rq4_cocreation block."""
    # Annotation -> bereich lookup.
    ann_bereich: dict[str, str] = {}
    for task in real["tasks"]:
        b = (task.get("data") or {}).get("bereich")
        for ann in task.get("annotations") or []:
            ann_bereich[ann["id"]] = b

    by_bereich: dict[str, dict] = defaultdict(lambda: {"trad": [], "ai": []})
    for ann_id, j in judge_on_humans.items():
        raw = j.get("raw_score")
        if raw is None:
            continue
        b = ann_bereich.get(ann_id)
        if not b:
            continue
        v = variants.get(ann_id)
        if v == "ai":
            by_bereich[b]["ai"].append(raw)
        elif v == "no_ai":
            by_bereich[b]["trad"].append(raw)

    out = {}
    for b, pools in by_bereich.items():
        if not pools["trad"] or not pools["ai"]:
            out[b] = None
            continue
        point, lo, hi = bootstrap_mean_diff(pools["ai"], pools["trad"])
        out[b] = {
            "n_traditional": len(pools["trad"]),
            "n_co_creation": len(pools["ai"]),
            "mean_traditional": statistics.mean(pools["trad"]),
            "mean_co_creation": statistics.mean(pools["ai"]),
            "mean_diff_ai_minus_trad": point,
            "ci95_lo": lo,
            "ci95_hi": hi,
        }
    return out


def rq4_cocreation_blind_human(canonical_grades):
    """RQ4 trad vs co-creation, but on mean-blind-human raw score instead of
    the LLM judge. Needs canonical grades with `role` populated and
    `solution_type` ∈ {human_traditional, human_co_creation}.

    Returns None when no rows match (e.g. the export covers only LLM
    generations, or roles aren't yet labelled). Bootstrap CI is clustered
    on participant (`system_or_user`) — at n=15 per arm this matters less
    than for the judge-based RQ4 but keeps the inference model consistent.
    """
    blind = humans_by_solution(canonical_grades, role_filter="blind")
    trad, ai = [], []
    by_user_trad: dict[str, list[float]] = defaultdict(list)
    by_user_ai:   dict[str, list[float]] = defaultdict(list)
    for sol_id, raters in blind.items():
        raws = [r["raw_score"] for r in raters if r["raw_score"] is not None]
        if not raws:
            continue
        mean_raw = statistics.mean(raws)
        stype = raters[0].get("solution_type")
        uid = raters[0].get("system_or_user")
        if stype == "human_traditional":
            trad.append(mean_raw)
            if uid: by_user_trad[uid].append(mean_raw)
        elif stype == "human_co_creation":
            ai.append(mean_raw)
            if uid: by_user_ai[uid].append(mean_raw)
    if not trad or not ai:
        return None
    point_iid, lo_iid, hi_iid = bootstrap_mean_diff(ai, trad)
    point_pc,  lo_pc,  hi_pc  = cluster_bootstrap_mean_diff(by_user_ai, by_user_trad)
    return {
        "n_traditional": len(trad),
        "n_co_creation": len(ai),
        "n_participants_trad": len(by_user_trad),
        "n_participants_ai":   len(by_user_ai),
        "mean_traditional": statistics.mean(trad),
        "mean_co_creation": statistics.mean(ai),
        # Headline = participant cluster bootstrap, like rq4_cocreation.
        "mean_diff_ai_minus_trad": point_pc if point_pc is not None else point_iid,
        "ci95_lo": lo_pc if lo_pc is not None else lo_iid,
        "ci95_hi": hi_pc if hi_pc is not None else hi_iid,
        "mean_diff_ai_minus_trad_iid": point_iid,
        "ci95_lo_iid": lo_iid,
        "ci95_hi_iid": hi_iid,
    }


def rq5_creator_vs_blind(canonical_grades):
    """Per-solution comparison between the creator review and the mean of
    blind reviews. Returns the systematic offset (creator − mean_blind),
    correlation, and MAE.

    Mock data has no `role="creator"` rows, so this returns None until the
    real grading export populates the creator role via grader_roles.json.
    """
    by_sol = defaultdict(lambda: {"blind": [], "creator": []})
    for r in canonical_grades:
        role = r.get("role")
        if role not in ("blind", "creator"):
            continue
        if r.get("raw_score") is None:
            continue
        by_sol[r["solution_id"]][role].append(r["raw_score"])

    pairs_c, pairs_b = [], []
    diffs_raw, diffs_gp = [], []
    pairs_c_gp, pairs_b_gp = [], []
    by_sol_gp = defaultdict(lambda: {"blind": [], "creator": []})
    for r in canonical_grades:
        if r.get("role") not in ("blind", "creator"):
            continue
        if r.get("grade_points") is None:
            continue
        by_sol_gp[r["solution_id"]][r["role"]].append(r["grade_points"])

    for sol_id, pools in by_sol.items():
        if not pools["creator"] or not pools["blind"]:
            continue
        c_raw = statistics.mean(pools["creator"])
        b_raw = statistics.mean(pools["blind"])
        pairs_c.append(c_raw)
        pairs_b.append(b_raw)
        diffs_raw.append(c_raw - b_raw)
    for sol_id, pools in by_sol_gp.items():
        if not pools["creator"] or not pools["blind"]:
            continue
        c_gp = statistics.mean(pools["creator"])
        b_gp = statistics.mean(pools["blind"])
        pairs_c_gp.append(c_gp)
        pairs_b_gp.append(b_gp)
        diffs_gp.append(c_gp - b_gp)

    if not pairs_c:
        return None
    return {
        "n_solutions": len(pairs_c),
        "pearson_creator_vs_mean_blind_raw": pearson(pairs_c, pairs_b),
        "spearman_creator_vs_mean_blind_raw": spearman(pairs_c, pairs_b),
        "mae_raw": mae(pairs_c, pairs_b),
        "mae_grade_points": mae(pairs_c_gp, pairs_b_gp) if pairs_c_gp else None,
        "mean_creator_minus_blind_raw": statistics.mean(diffs_raw),
        "mean_creator_minus_blind_grade_points": statistics.mean(diffs_gp) if diffs_gp else None,
    }


def rq5_judge_on_llm_solutions(canonical_grades, model_evals):
    """Judge-vs-blind agreement on LLM-generated solutions in the validation set.

    Returns None when no LLM solutions are blind-graded in canonical_grades.
    """
    judge_by_gen = {r["generation_id"]: r for r in model_evals}
    blind_llm = humans_by_solution(canonical_grades,
                                   role_filter="blind",
                                   solution_type_filter="llm_system")
    if not blind_llm:
        return None

    j_raw, h_raw, j_gp, h_gp, j_pass, h_pass = [], [], [], [], [], []
    for gen_id, raters in blind_llm.items():
        j = judge_by_gen.get(gen_id)
        if not j or j.get("raw_score") is None:
            continue
        h_raws = [r["raw_score"] for r in raters if r["raw_score"] is not None]
        if not h_raws:
            continue
        h_gps = [r["grade_points"] for r in raters if r["grade_points"] is not None]
        h_passes = [r["passed"] for r in raters if r["passed"] is not None]
        j_raw.append(j["raw_score"])
        h_raw.append(statistics.mean(h_raws))
        if j.get("grade_points") is not None and h_gps:
            j_gp.append(j["grade_points"])
            h_gp.append(statistics.mean(h_gps))
        if j.get("passed") is not None and h_passes:
            j_pass.append(bool(j["passed"]))
            h_pass.append(sum(h_passes) > len(h_passes) / 2)
    if not j_raw:
        return None
    def _bias_corrected_mae(js, hs):
        if not js or not hs:
            return None
        delta = statistics.mean(js) - statistics.mean(hs)
        return statistics.mean(abs((j - h) - delta) for j, h in zip(js, hs))
    return {
        "n_generations": len(j_raw),
        "pearson_raw": pearson(j_raw, h_raw),
        "spearman_raw": spearman(j_raw, h_raw),
        "mae_raw": mae(j_raw, h_raw),
        "mae_grade_points": mae(j_gp, h_gp) if j_gp else None,
        "mae_raw_bias_corrected": _bias_corrected_mae(j_raw, h_raw),
        "mae_grade_points_bias_corrected": _bias_corrected_mae(j_gp, h_gp) if j_gp else None,
        "judge_minus_pool_mean_raw": (
            statistics.mean(j_raw) - statistics.mean(h_raw) if j_raw and h_raw else None),
        "judge_minus_pool_mean_grade_points": (
            statistics.mean(j_gp) - statistics.mean(h_gp) if j_gp and h_gp else None),
        "passfail_cohen_kappa": cohen_kappa(j_pass, h_pass) if j_pass else None,
        "mean_judge_raw": statistics.mean(j_raw) if j_raw else None,
        "mean_human_raw_mean": statistics.mean(h_raw) if h_raw else None,
    }


def rq5_dim_on_llm_solutions(canonical_grades, model_evals):
    """Per-rubric-dimension judge-vs-blind on LLM-generated solutions.

    Mirror of rq5_dim_agreement but keyed by generation_id, since LLM
    solutions are generations (not annotations). Requires that model_evals
    rows carry a `dimensions` dict; derive_paper_exports._baseline_judge_score
    extracts these alongside raw_score / grade_points / passed.
    """
    judge_by_gen = {r["generation_id"]: r for r in model_evals}
    blind_llm = humans_by_solution(canonical_grades,
                                   role_filter="blind",
                                   solution_type_filter="llm_system")
    if not blind_llm:
        return None
    out = {}
    for d in DIMENSIONS:
        j_vals, h_vals = [], []
        for gen_id, raters in blind_llm.items():
            j = judge_by_gen.get(gen_id)
            if not j:
                continue
            jv = (j.get("dimensions") or {}).get(d)
            human_dims = [g["dimensions"].get(d) for g in raters
                          if g.get("dimensions") and g["dimensions"].get(d) is not None]
            if jv is None or not human_dims:
                continue
            j_vals.append(jv)
            h_vals.append(statistics.mean(human_dims))
        out[d] = {
            "n": len(j_vals),
            "pearson_judge_vs_mean_human": pearson(j_vals, h_vals),
            "mae_dim_points": mae(j_vals, h_vals),
        }
    return out


def rq5_calderon_on_llm_solutions(canonical_grades, model_evals,
                                  *, eps_blind_pool=0.15,
                                  eps_single_expert_values=(0.15, 0.20)):
    """Calderon alt-test on LLM-generated solutions.

    Mirrors `rq5_calderon` but is keyed by generation_id rather than
    annotation_id, because LLM solutions are generations. Returns the same
    `{"blind_pool": …, "single_expert": …}` shape. `single_expert` is None
    when the canonical grades carry no creator-role rows on LLM solutions.
    """
    judge_by_sol = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                    if r.get("raw_score") is not None}
    blind_llm = humans_by_solution(canonical_grades,
                                   role_filter="blind",
                                   solution_type_filter="llm_system")
    if not blind_llm:
        return None

    # §3 — blind-reviewer pool.
    blind_inputs, n_blind = _build_blind_pool_inputs(judge_by_sol, blind_llm)
    blind_payload = _alt_test_blind_pool(blind_inputs, eps=eps_blind_pool)
    blind_payload["variant"] = "calderon_section_3"
    blind_payload["reference"] = "blind_reviewer_pool"
    blind_payload["n_instances_total"] = n_blind

    # §D.2 — single-expert variant, restricted to LLM-system solutions.
    single_expert_payload = None
    expert_by_sol = {sid: v for sid, v in _expert_grades_by_solution(
        [r for r in canonical_grades
         if r.get("solution_type") == "llm_system"]).items()}
    if expert_by_sol:
        se_inputs, n_se = _build_single_expert_inputs(
            judge_by_sol, blind_llm, expert_by_sol)
        se_by_eps = {}
        for eps in eps_single_expert_values:
            payload = _alt_test_single_expert(se_inputs, eps=eps)
            payload["variant"] = "calderon_section_D2_single_expert"
            payload["reference"] = "creator_unblind"
            se_by_eps[f"{eps:.2f}"] = payload
        single_expert_payload = {
            "variant": "calderon_section_D2_single_expert",
            "reference": "creator_unblind",
            "n_instances_with_creator_and_judge": n_se,
            "epsilon_results": se_by_eps,
        }

    return {
        "blind_pool": blind_payload,
        "single_expert": single_expert_payload,
    }


def rq5_human_irr_by_solution_type(canonical_grades):
    """Per-solution-type ICC(2,1) / ICC(2,k) breakdown of the blind-rater pool.

    Calls rq5_human_irr three times — once with solution_type filtered to
    each of human_traditional / human_co_creation / llm_system. Returns a
    dict keyed by solution_type with the same payload shape as the pooled
    rq5_human_irr.

    Per-type matrices are small (~15 solutions × 3 raters); the underlying
    icc21_and_2k returns None for cells where the design isn't balanced
    enough, so a sparse type just yields None ICCs without crashing.
    """
    out = {}
    for stype in ("human_traditional", "human_co_creation", "llm_system"):
        humans_type = humans_by_solution(canonical_grades,
                                         role_filter="blind",
                                         solution_type_filter=stype)
        out[stype] = rq5_human_irr(humans_type) if humans_type else None
    return out


# ----------------------------- entry point -----------------------------

def main() -> None:
    real = load_json(REAL)
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    auto_metrics = load_json(PROCESSED / "benchathon_automatic_metrics.json")
    human_auto_metrics_path = PROCESSED / "benchathon_human_automatic_metrics.json"
    human_auto_metrics = load_json(human_auto_metrics_path) if human_auto_metrics_path.exists() else []
    variants = load_json(PROCESSED / "benchathon_instruction_variants.json")
    judge_repeats = load_json(PROCESSED / "benchathon_human_judge_repeats.json")
    canonical_grades = load_json(PROCESSED / "benchathon_human_grades.json")
    systems_meta = load_json(PROCESSED / "systems.json")
    zjs_summary_path = PROCESSED / "zjs_model_summary.json"
    zjs_summary = load_json(zjs_summary_path) if zjs_summary_path.exists() else []

    judge_on_humans = index_judge_on_humans(real)
    # IRR / judge-vs-human / dim / Calderon use the blind raters only, drawn
    # from the canonical grade file. Creator self-grades are kept out of the
    # inter-rater statistics (they're used separately in rq5_creator_vs_blind).
    humans = humans_by_solution(canonical_grades, role_filter="blind")
    ann_to_task = annotation_to_task(real)
    ann_to_user = annotation_to_user(real)

    # Co-creation vs flagship-tier TOST: per-generation flagship raws come from
    # model_evals, co-creation human raws from the judge-on-humans index.
    # Equivalence band ±5 raw points (≈ 0.9 grade points, ~half the inter-
    # human within-solution spread reported in RQ5).
    _flagship_ids = {s["model_id"] for s in systems_meta if s.get("tier") == "flagship"}
    _flagship_raws = [r["raw_score"] for r in model_evals
                      if r.get("raw_score") is not None and r.get("system") in _flagship_ids]
    _cocreation_raws = [j["raw_score"] for ann_id, j in judge_on_humans.items()
                        if variants.get(ann_id) == "ai" and j.get("raw_score") is not None]
    rq4_vs_flagship_tost = tost_mean_diff(_cocreation_raws, _flagship_raws,
                                          eq_low=-5.0, eq_high=5.0)

    payload = {
        "_sources": {
            "real_export": REAL.name,
            "korrektur_sidecar": "korrektur_grades_sidecar.json",
            "n_annotations_with_judge": len(judge_on_humans),
            "n_solutions_with_blind_human_grades": len(humans),
            "n_canonical_grade_rows": len(canonical_grades),
        },
        "rq3_metric_correlation": rq3_metric_correlations(model_evals, auto_metrics),
        # Per-condition (classic vs. co-creation) metric-vs-judge correlations
        # over human-written Benchathon annotations.
        "rq3_metric_correlation_humans": rq3_metric_correlations_humans(
            human_auto_metrics, judge_on_humans),
        "rq4_cocreation": rq4_cocreation(judge_on_humans, ann_to_task, variants, ann_to_user),
        "rq4_cocreation_by_bereich": rq4_cocreation_by_bereich(judge_on_humans, variants, real),
        "rq4_cocreation_vs_flagship_tost": rq4_vs_flagship_tost,
        # Forward-compatible: same comparison computed against the mean of
        # blind human reviewers. Returns null until canonical grades carry
        # blind-graded human solutions in both variants.
        "rq4_cocreation_blind_human": rq4_cocreation_blind_human(canonical_grades),
        "rq5_judge_vs_human": rq5_judge_vs_human(judge_on_humans, humans),
        "rq5_human_irr": rq5_human_irr(humans),
        "rq5_dim": rq5_dim_agreement(judge_on_humans, humans),
        "rq5_calderon": rq5_calderon(judge_on_humans, humans, canonical_grades),
        "rq5_judge_repeats": rq5_judge_repeats(judge_repeats),
        # Activates when the real grading export populates role="creator" via
        # data/processed/grader_roles.json (or its export-native equivalent).
        "rq5_creator_vs_blind": rq5_creator_vs_blind(canonical_grades),
        # Activates when the real grading export covers LLM-generated solutions
        # in the 45-solution validation set (solution_type="llm_system").
        "rq5_judge_on_llm_solutions": rq5_judge_on_llm_solutions(canonical_grades, model_evals),
        "rq5_dim_on_llm_solutions": rq5_dim_on_llm_solutions(canonical_grades, model_evals),
        "rq5_calderon_on_llm_solutions": rq5_calderon_on_llm_solutions(canonical_grades, model_evals),
        # Per-solution-type breakdown of the blind-rater IRR — answers "do
        # reviewers agree more on LLM output than on human-written essays?"
        "rq5_human_irr_by_solution_type": rq5_human_irr_by_solution_type(canonical_grades),
        # RQ2 quantitative aggregates by tier / provider / weights, on both corpora.
        "tier_aggregates": tier_provider_aggregates(model_evals, zjs_summary, systems_meta),
        # RQ3 system-level rank correlation: do metric-only leaderboards rank systems
        # the same way as the judge?
        "rq3_rank_correlation": rq3_rank_correlation(model_evals, auto_metrics, zjs_summary),
    }

    # Derived ratio: judge_vs_human MAE / human_within-annotation spread.
    jh_mae = payload["rq5_judge_vs_human"].get("mae_raw")
    hh_spread = payload["rq5_human_irr"].get("mean_within_ann_spread_raw")
    if jh_mae is not None and hh_spread:
        payload["rq5_human_irr"]["mean_judge_human_dev_vs_human_human_dev_ratio"] = jh_mae / (hh_spread / 2)
    # (Spread/2 approximates a typical |grader - mean| for k≈4.)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=float)
    print(f"wrote {OUT}")

    # Side-by-side CSV mirror of manuscript tbl-metric-correlation. Kept in
    # sync with the canonical metric order and column set used by the manuscript
    # rendering chunk so reviewers / downstream tooling can consume the same
    # numbers without parsing the larger JSON.
    write_metric_correlation_csv(
        PROCESSED / "metric_correlation_table.csv",
        bench_llm=payload["rq3_metric_correlation"],
        zjs_llm=(load_json(PROCESSED / "zjs_metric_correlation.json")
                 if (PROCESSED / "zjs_metric_correlation.json").exists() else {}),
        grundprinzipien_llm=(load_json(PROCESSED / "grundprinzipien_metric_correlation.json")
                             if (PROCESSED / "grundprinzipien_metric_correlation.json").exists() else {}),
        humans=payload["rq3_metric_correlation_humans"],
    )

    print(json.dumps(payload, indent=2, default=lambda v: round(v, 4) if isinstance(v, float) else str(v))[:4000])


if __name__ == "__main__":
    main()
