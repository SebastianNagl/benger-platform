"""Compute all agreement / correlation / reliability statistics for the paper.

Inputs (read-only):
  data/raw/benchathon/Benchathon-tasks-2026-05-23.json   LLM-judge grades on human annotations
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

Pure stdlib (statistics.correlation is Pearson in py3.10+, Spearman is
rank→Pearson). ICC implemented from Shrout & Fleiss 1979.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Isolated bootstrap RNG: reproducible regardless of how many or in what order
# other random.* calls run in this module.
_BOOTSTRAP_RNG = random.Random(7)

HERE = Path(__file__).resolve().parent.parent
RAW       = HERE / "data" / "raw"
INTERIM   = HERE / "data" / "interim"
PROCESSED = HERE / "data" / "processed"
OUT = PROCESSED / "agreement_stats.json"

REAL = RAW / "benchathon" / "Benchathon-tasks-2026-05-23.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_paper_exports import LEGACY_JUDGE_FIELD_PREFIX  # noqa: E402

DIMENSIONS = (
    "ergebnisrichtigkeit", "vollstaendigkeit", "rechtsgrundlagen",
    "rechtskenntnis", "subsumtion", "schwerpunktsetzung",
    "methodischer_stil", "gliederung", "sprache", "formalia",
)


# ----------------------------- correlation helpers -----------------------------

def _to_floats(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return [], []
    return [float(x) for x, _ in pairs], [float(y) for _, y in pairs]


def pearson(xs, ys):
    xs, ys = _to_floats(xs, ys)
    if not xs:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return None


def _rank(xs):
    # Average rank for ties.
    indexed = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[indexed[j + 1]] == xs[indexed[i]]:
            j += 1
        avg = (i + j) / 2 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    xs, ys = _to_floats(xs, ys)
    if not xs:
        return None
    return pearson(_rank(xs), _rank(ys))


def mae(xs, ys):
    xs, ys = _to_floats(xs, ys)
    if not xs:
        return None
    return statistics.mean(abs(a - b) for a, b in zip(xs, ys))


def cohen_kappa(xs, ys):
    """Cohen's kappa for two binary raters."""
    pairs = [(bool(x), bool(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    po = agree / n
    pa1 = sum(1 for a, _ in pairs if a) / n
    pb1 = sum(1 for _, b in pairs if b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return None if pe == 1 else (po - pe) / (1 - pe)


def icc21_and_2k(matrix):
    """Shrout & Fleiss (1979) ICC(2,1) and ICC(2,k) on n×k ratings matrix.

    Two-way random, single-rater (consistency-of-mean-rating not strict
    absolute-agreement variant). Returns (icc_2_1, icc_2_k) or (None, None)
    if any cell is missing or n<2 / k<2.
    """
    n = len(matrix)
    if n < 2:
        return None, None
    k = len(matrix[0]) if matrix else 0
    if k < 2 or any(len(row) != k for row in matrix):
        return None, None
    if any(v is None for row in matrix for v in row):
        return None, None

    grand = sum(sum(row) for row in matrix) / (n * k)
    row_means = [sum(row) / k for row in matrix]
    col_means = [sum(matrix[i][j] for i in range(n)) / n for j in range(k)]

    ssr = k * sum((rm - grand) ** 2 for rm in row_means)
    ssc = n * sum((cm - grand) ** 2 for cm in col_means)
    sst = sum((matrix[i][j] - grand) ** 2 for i in range(n) for j in range(k))
    sse = sst - ssr - ssc
    msr = ssr / (n - 1)
    msc = ssc / (k - 1)
    mse = sse / ((n - 1) * (k - 1))

    denom_1 = msr + (k - 1) * mse + k * (msc - mse) / n
    if denom_1 <= 0:
        return None, None
    icc_2_1 = (msr - mse) / denom_1

    denom_k = msr + (msc - mse) / n
    if denom_k <= 0:
        icc_2_k = None
    else:
        icc_2_k = (msr - mse) / denom_k
    return icc_2_1, icc_2_k


def bootstrap_mean_diff(a, b, n=2000):
    """Bootstrap CI on mean(a) - mean(b). Returns (point, lo95, hi95)."""
    a = [float(x) for x in a if x is not None]
    b = [float(x) for x in b if x is not None]
    if len(a) < 3 or len(b) < 3:
        return None, None, None
    point = statistics.mean(a) - statistics.mean(b)
    diffs = []
    for _ in range(n):
        sa = [_BOOTSTRAP_RNG.choice(a) for _ in a]
        sb = [_BOOTSTRAP_RNG.choice(b) for _ in b]
        diffs.append(statistics.mean(sa) - statistics.mean(sb))
    diffs.sort()
    lo = diffs[int(0.025 * n)]
    hi = diffs[min(int(0.975 * n), n - 1)]
    return point, lo, hi


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
            # Restrict to the legacy single-pass judge that anchors the RQ1/2/3
            # leaderboards. The 2026-05-21 export also carries Config A/B passes
            # (mpe7mkzx-2zp6, mpe7o02k-yrio); without this filter, whichever
            # config appears last per annotation silently wins via out[ann_id]
            # overwrite, contaminating every RQ5 / rq4_cocreation number.
            if not fn.startswith(LEGACY_JUDGE_FIELD_PREFIX):
                continue
            if "human:loesung" not in fn:
                continue
            m = ev.get("metrics") or {}
            judge = m.get("llm_judge_falloesung")

            # Shape A: nested `llm_judge_falloesung.details.raw_score` on 0-100.
            # Shape B: top-level `raw_score` plus `llm_judge_falloesung_response`.
            # Backfilled legacy rows wear the Shape A envelope but the `details`
            # blob is a stub (just `backfilled_legacy: true`) — `judge.get("value")`
            # is then a 0-1 ratio, the same scale trap fixed in `_legacy_judge_score`.
            # Gate Shape A on `details.raw_score is not None` and otherwise fall
            # through to the Shape B branch.
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


def rq4_cocreation(judge_on_humans, ann_to_task, variants):
    """Mean judge raw on traditional vs co-creation human solutions; bootstrap CI."""
    trad, ai = [], []
    for ann_id, j in judge_on_humans.items():
        v = variants.get(ann_id)
        raw = j.get("raw_score")
        if raw is None:
            continue
        if v == "ai":
            ai.append(raw)
        elif v == "no_ai":
            trad.append(raw)
    point, lo, hi = bootstrap_mean_diff(ai, trad)
    return {
        "n_traditional": len(trad),
        "n_co_creation": len(ai),
        "mean_traditional": statistics.mean(trad) if trad else None,
        "mean_co_creation": statistics.mean(ai) if ai else None,
        "mean_diff_ai_minus_trad": point,
        "ci95_lo": lo,
        "ci95_hi": hi,
    }


def rq5_judge_vs_human(judge_on_humans, humans):
    """Per-annotation judge vs mean-human; pairs across the expert-graded subset."""
    j_raw, h_raw, j_gp, h_gp, j_pass, h_pass = [], [], [], [], [], []
    for ann_id, graders in humans.items():
        j = judge_on_humans.get(ann_id)
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
    return {
        "n_annotations": len(j_raw),
        "pearson_raw": pearson(j_raw, h_raw),
        "spearman_raw": spearman(j_raw, h_raw),
        "mae_raw": mae(j_raw, h_raw),
        "mae_grade_points": mae(j_gp, h_gp),
        "passfail_cohen_kappa": cohen_kappa(j_pass, h_pass),
        "mean_judge_raw": statistics.mean(j_raw) if j_raw else None,
        "mean_human_raw_mean": statistics.mean(h_raw) if h_raw else None,
    }


def rq5_human_irr(humans):
    """ICC(2,1) and ICC(2,k) across solutions graded by k blind raters.
    Also within-solution spread on raw and grade points.

    Real grading coverage is unbalanced (most solutions have 2 or 3 blind
    raters, a few have 4). We pick the *most common* k for the ICC, which
    keeps the largest balanced subset rather than the max (which would
    keep only the handful of solutions with the rare k=4 coverage).
    """
    from collections import Counter as _Counter
    rows_raw_all, rows_gp_all = [], []
    spreads_raw, spreads_gp = [], []
    for ann_id, graders in humans.items():
        if len(graders) < 2:
            continue
        raws = [g["raw_score"] for g in graders]
        gps = [g["grade_points"] for g in graders]
        if None not in raws:
            rows_raw_all.append(raws); spreads_raw.append(max(raws) - min(raws))
        if None not in gps:
            rows_gp_all.append(gps); spreads_gp.append(max(gps) - min(gps))

    def _icc_at_k(rows, k):
        sub = [r for r in rows if len(r) == k]
        return sub, icc21_and_2k(sub)

    # Modal-k: the dominant rater-count in the data (current behavior).
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
        for ann_id, graders in humans.items():
            j = judge_on_humans.get(ann_id)
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


def rq5_calderon(judge_on_humans, humans):
    """Alternative-annotator test (Calderon 2025-style).

    Treat each annotation as an item. Compute two scoring rows per annotation:
      - mean over k human graders                   (full-human pool)
      - mean over (k-1 human graders + LLM judge)   (judge-substituted pool)
    Report (a) Pearson + Spearman between the two pooled scores across items,
    and (b) the analogous "human-only" leave-one-out check where we drop one
    human at a time from the pool of k and compare against the full mean.

    A judge that scores like an additional human grader should show
    judge-substituted correlation ≈ human-only correlation.
    """
    # Matched sample: both the judge-substituted and the human-LOO comparison
    # run on the same annotations (those where the legacy judge has data and
    # k>=2 humans), and both drop the SAME position from the human pool. This
    # fixes two issues with the prior implementation: (a) the LOO loop also
    # ran on annotations the judge never graded, mixing pools; (b) the LOO
    # dropped raws[0] while the judge swap dropped raws[-1], so they weren't
    # symmetric. With a stable grader_id sort, the chosen position is
    # deterministic and reproducible across re-runs.
    full_matched, sub_matched, loh_matched = [], [], []
    # Rigorous subset: k>=3 only. For k=2, the human-LOO is one rater scored
    # against the mean of the same two raters; that's a high-correlation
    # comparison by construction (the LOO is 50% of the full sum). The k>=3
    # subset breaks that direct overlap so the gap to judge_substituted is
    # interpretable.
    full_k3, sub_k3, loh_k3 = [], [], []
    for ann_id, graders in humans.items():
        rated = [(g.get("grader_id") or "", g["raw_score"])
                 for g in graders if g["raw_score"] is not None]
        if len(rated) < 2:
            continue
        j = judge_on_humans.get(ann_id)
        if not (j and j.get("raw_score") is not None):
            continue
        rated.sort()
        raws = [r for _, r in rated]
        full = statistics.mean(raws)
        # Drop the last (alphabetically-sorted-by-grader_id) human in both
        # branches, so the judge takes a fixed seat and the human-LOO drops a
        # fixed seat.
        sub = (sum(raws[:-1]) + j["raw_score"]) / len(raws)
        loh = statistics.mean(raws[:-1])
        full_matched.append(full); sub_matched.append(sub); loh_matched.append(loh)
        if len(raws) >= 3:
            full_k3.append(full); sub_k3.append(sub); loh_k3.append(loh)
    return {
        # Matched-sample (k>=2)
        "n_pairs_judge_substituted": len(full_matched),
        "n_pairs_human_leave_one_out": len(loh_matched),
        "pearson_judge_substituted_vs_full_human": pearson(sub_matched, full_matched),
        "spearman_judge_substituted_vs_full_human": spearman(sub_matched, full_matched),
        "pearson_human_LOO_vs_full_human": pearson(loh_matched, full_matched),
        "spearman_human_LOO_vs_full_human": spearman(loh_matched, full_matched),
        # Rigorous subset (k>=3) — included so the reader can see whether the
        # judge-substituted vs human-LOO gap survives outside the k=2 regime
        # where the LOO and full means share 50% of their components.
        "k_ge_3_subset": {
            "n_pairs": len(full_k3),
            "pearson_judge_substituted_vs_full_human": pearson(sub_k3, full_k3),
            "spearman_judge_substituted_vs_full_human": spearman(sub_k3, full_k3),
            "pearson_human_LOO_vs_full_human": pearson(loh_k3, full_k3),
            "spearman_human_LOO_vs_full_human": spearman(loh_k3, full_k3),
        },
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
            point, lo, hi = bootstrap_mean_diff(vals, [0.0] * len(vals))
            # bootstrap_mean_diff returns mean(a)−mean(b); with b=0s we get mean(a).
            # Re-derive a proper CI on mean(a) directly:
            mean = statistics.mean(vals)
            samples = sorted(
                statistics.mean(_BOOTSTRAP_RNG.choices(vals, k=len(vals))) for _ in range(2000)
            )
            out[key] = {
                "n_systems": len(sys_by_group[key]),
                "n_generations": len(vals),
                "mean_raw": mean,
                "ci95_lo": samples[int(0.025 * 2000)],
                "ci95_hi": samples[min(int(0.975 * 2000), 2000 - 1)],
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
    generations, or roles aren't yet labelled).
    """
    blind = humans_by_solution(canonical_grades, role_filter="blind")
    trad, ai = [], []
    for sol_id, raters in blind.items():
        raws = [r["raw_score"] for r in raters if r["raw_score"] is not None]
        if not raws:
            continue
        mean_raw = statistics.mean(raws)
        stype = raters[0].get("solution_type")
        if stype == "human_traditional":
            trad.append(mean_raw)
        elif stype == "human_co_creation":
            ai.append(mean_raw)
    if not trad or not ai:
        return None
    point, lo, hi = bootstrap_mean_diff(ai, trad)
    return {
        "n_traditional": len(trad),
        "n_co_creation": len(ai),
        "mean_traditional": statistics.mean(trad),
        "mean_co_creation": statistics.mean(ai),
        "mean_diff_ai_minus_trad": point,
        "ci95_lo": lo,
        "ci95_hi": hi,
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
    return {
        "n_generations": len(j_raw),
        "pearson_raw": pearson(j_raw, h_raw),
        "spearman_raw": spearman(j_raw, h_raw),
        "mae_raw": mae(j_raw, h_raw),
        "mae_grade_points": mae(j_gp, h_gp) if j_gp else None,
        "passfail_cohen_kappa": cohen_kappa(j_pass, h_pass) if j_pass else None,
    }


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
        "rq4_cocreation": rq4_cocreation(judge_on_humans, ann_to_task, variants),
        "rq4_cocreation_by_bereich": rq4_cocreation_by_bereich(judge_on_humans, variants, real),
        # Forward-compatible: same comparison computed against the mean of
        # blind human reviewers. Returns null until canonical grades carry
        # blind-graded human solutions in both variants.
        "rq4_cocreation_blind_human": rq4_cocreation_blind_human(canonical_grades),
        "rq5_judge_vs_human": rq5_judge_vs_human(judge_on_humans, humans),
        "rq5_human_irr": rq5_human_irr(humans),
        "rq5_dim": rq5_dim_agreement(judge_on_humans, humans),
        "rq5_calderon": rq5_calderon(judge_on_humans, humans),
        "rq5_judge_repeats": rq5_judge_repeats(judge_repeats),
        # Activates when the real grading export populates role="creator" via
        # data/processed/grader_roles.json (or its export-native equivalent).
        "rq5_creator_vs_blind": rq5_creator_vs_blind(canonical_grades),
        # Activates when the real grading export covers LLM-generated solutions
        # in the 45-solution validation set (solution_type="llm_system").
        "rq5_judge_on_llm_solutions": rq5_judge_on_llm_solutions(canonical_grades, model_evals),
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
