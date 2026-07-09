"""Anchor the automatic metrics to the MEAN BLIND HUMAN GRADE (reviewer check).

A reviewer hypothesises the LLM judge may be biased toward reference-like
style, which would inflate the lexical-overlap metrics' (BLEU / ROUGE /
METEOR) apparent validity in the RQ3 metric-vs-judge correlations. The direct
test: re-run the per-metric correlations against the per-solution mean
blind-reviewer raw grade (0-100) instead of the judge, on the 45-solution
human-validation subset (30 human-authored picks: 15 traditional + 15
co-creation; 15 LLM-generated picks).

Inputs (read-only):
  data/processed/benchathon_human_grades.json            blind + creator grades, 45 picks
  data/processed/benchathon_human_automatic_metrics.json auto metrics on human annotations
  data/processed/benchathon_automatic_metrics.json       auto metrics on LLM generations
  data/processed/benchathon_model_evaluations.json       baseline judge on LLM generations
  data/raw/benchathon/Benchathon_export.json             baseline judge on human annotations
                                                         + solution texts (length only)

Output:
  data/processed/metric_vs_human.json
    metric_vs_human    per metric x {human_authored, llm_generated, pooled}:
                       Pearson r (+ paired percentile bootstrap 95% CI,
                       B=2000, seed 42 — the paper's leaderboard convention),
                       Spearman rho, actual n
    residual_analysis  per lexical metric: corr((judge_raw - mean_blind_raw),
                       metric). Positive => judge over-scores reference-like
                       solutions relative to humans (reference-style bias);
                       ~0 supports the templatic-writing account.
    length_partial     partial Pearson of judge_raw with each lexical metric
                       controlling for candidate length (tokens / chars)
    _meta              inputs, matching strategy, exclusions

No metric is recomputed from text; the raw export is only consulted for the
judge-on-human scores (same extraction as compute_agreement.py) and for
candidate lengths (loesung markdown / generation response text).

Usage:  uv run python scripts/derive_metric_vs_human.py
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "data" / "raw"
PROCESSED = HERE / "data" / "processed"
OUT = PROCESSED / "metric_vs_human.json"

REAL = RAW / "benchathon" / "Benchathon_export.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import pearson, spearman  # noqa: E402
from compute_agreement import index_judge_on_humans, load_json  # noqa: E402
from derive_paper_exports import _response_text, count_tokens  # noqa: E402

BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 42

# Canonical paper order (manuscript tbl-metric-correlation). chrf is kept so
# its absence on Benchathon is explicit in the output rather than silent.
METRIC_ORDER = (
    "bleu", "rouge", "meteor", "chrf",
    "bertscore", "moverscore", "semantic_similarity", "coherence",
)
LEXICAL_METRICS = ("bleu", "rouge", "meteor")
SPLITS = ("human_authored", "llm_generated", "pooled")


# ----------------------------- statistics -----------------------------

def _paired_bootstrap_pearson_ci(xs, ys, b=BOOTSTRAP_B, seed=BOOTSTRAP_SEED):
    """Percentile bootstrap 95% CI on Pearson r, resampling (x, y) pairs.

    Fresh default_rng(seed) per call so every cell is reproducible in
    isolation (same convention as derive_leaderboard_csvs.bootstrap_ci).
    Non-finite resamples (zero-variance draws) are dropped.
    """
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None, None
    a = np.asarray([p[0] for p in pairs], dtype=float)
    c = np.asarray([p[1] for p in pairs], dtype=float)
    n = len(pairs)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(b, n))
    x_res, y_res = a[idx], c[idx]
    xc = x_res - x_res.mean(axis=1, keepdims=True)
    yc = y_res - y_res.mean(axis=1, keepdims=True)
    num = (xc * yc).sum(axis=1)
    den = np.sqrt((xc ** 2).sum(axis=1) * (yc ** 2).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = num / den
    rs = rs[np.isfinite(rs)]
    if rs.size < 3:
        return None, None
    lo, hi = np.percentile(rs, [2.5, 97.5])
    return float(lo), float(hi)


def corr_cell(xs, ys):
    """{n, pearson_r, pearson_ci95_lo/hi, spearman_rho} on paired lists."""
    n = sum(1 for x, y in zip(xs, ys) if x is not None and y is not None)
    lo, hi = _paired_bootstrap_pearson_ci(xs, ys)
    return {
        "n": n,
        "pearson_r": pearson(xs, ys),
        "pearson_ci95_lo": lo,
        "pearson_ci95_hi": hi,
        "spearman_rho": spearman(xs, ys),
    }


def partial_pearson(xs, ys, zs):
    """First-order partial Pearson r(x, y | z) on complete-case triples.

    Closed form for a single covariate:
      r_xy.z = (r_xy - r_xz * r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))
    Returns (partial_r, n_complete). None when n < 4 or degenerate.
    """
    triples = [(x, y, z) for x, y, z in zip(xs, ys, zs)
               if x is not None and y is not None and z is not None]
    n = len(triples)
    if n < 4:
        return None, n
    a = [t[0] for t in triples]
    b = [t[1] for t in triples]
    c = [t[2] for t in triples]
    r_xy, r_xz, r_yz = pearson(a, b), pearson(a, c), pearson(b, c)
    if r_xy is None or r_xz is None or r_yz is None:
        return None, n
    den = math.sqrt((1.0 - r_xz ** 2) * (1.0 - r_yz ** 2))
    if den == 0.0:
        return None, n
    return (r_xy - r_xz * r_yz) / den, n


# ----------------------------- data joins -----------------------------

def _loesung_markdown(annotation) -> str | None:
    """Solution text of a human annotation (result entry type='loesung')."""
    for entry in annotation.get("result") or []:
        if entry.get("type") == "loesung":
            md = (entry.get("value") or {}).get("markdown")
            if isinstance(md, str) and md.strip():
                return md
    return None


def build_picks():
    """One dict per validation-subset solution, all sources joined.

    Join keys:
      human-authored picks: solution_id == annotation_id
        - blind grades:  benchathon_human_grades.json (role == 'blind')
        - auto metrics:  benchathon_human_automatic_metrics.json (annotation_id)
        - judge raw:     Benchathon_export.json task evaluations via
                         compute_agreement.index_judge_on_humans (baseline
                         judge field prefix, 'human:loesung' targets)
        - length:        annotation result loesung.value.markdown
      LLM-generated picks: solution_id == generation_id
        - blind grades:  benchathon_human_grades.json (role == 'blind')
        - auto metrics:  benchathon_automatic_metrics.json (generation_id)
        - judge raw:     benchathon_model_evaluations.json (generation_id)
        - length:        generation response_content via _response_text
    """
    grades = load_json(PROCESSED / "benchathon_human_grades.json")
    human_auto = load_json(PROCESSED / "benchathon_human_automatic_metrics.json")
    llm_auto = load_json(PROCESSED / "benchathon_automatic_metrics.json")
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    real = load_json(REAL)

    # Per-solution mean blind raw grade (k = 3 blind reviewers per pick).
    blind_raws: dict[str, list[float]] = defaultdict(list)
    solution_type: dict[str, str] = {}
    for r in grades:
        solution_type[r["solution_id"]] = r["solution_type"]
        if r.get("role") == "blind" and r.get("raw_score") is not None:
            blind_raws[r["solution_id"]].append(float(r["raw_score"]))

    # Metric values.
    metrics_by_sol: dict[str, dict[str, float]] = defaultdict(dict)
    dup_metric_rows = 0
    for r in human_auto:
        if r["metric"] in metrics_by_sol[r["annotation_id"]]:
            dup_metric_rows += 1
        metrics_by_sol[r["annotation_id"]][r["metric"]] = float(r["value"])
    for r in llm_auto:
        if r["metric"] in metrics_by_sol[r["generation_id"]]:
            dup_metric_rows += 1
        metrics_by_sol[r["generation_id"]][r["metric"]] = float(r["value"])

    # Judge raw.
    judge_on_humans = index_judge_on_humans(real)
    judge_on_llm = {r["generation_id"]: float(r["raw_score"])
                    for r in model_evals if r.get("raw_score") is not None}
    output_tokens_by_gen = {r["generation_id"]: r.get("output_tokens")
                            for r in model_evals}

    # Candidate texts (length only — never re-scored).
    text_by_sol: dict[str, str] = {}
    for task in real["tasks"]:
        for ann in task.get("annotations") or []:
            if ann["id"] in solution_type:
                md = _loesung_markdown(ann)
                if md is not None:
                    text_by_sol[ann["id"]] = md
        for gen in task.get("generations") or []:
            if gen["id"] in solution_type:
                txt = _response_text(gen)
                if txt:
                    text_by_sol[gen["id"]] = txt

    picks, exclusions = [], []
    token_crosscheck_mismatches = 0
    for sol_id, stype in sorted(solution_type.items()):
        provenance = "llm_generated" if stype == "llm_system" else "human_authored"
        raws = blind_raws.get(sol_id) or []
        if not raws:
            exclusions.append({"solution_id": sol_id, "reason": "no blind grades"})
            continue
        judge_raw = (judge_on_llm.get(sol_id) if provenance == "llm_generated"
                     else (judge_on_humans.get(sol_id) or {}).get("raw_score"))
        text = text_by_sol.get(sol_id)
        n_tokens = count_tokens(text) if text is not None else None
        n_chars = len(text) if text is not None else None
        if provenance == "llm_generated" and n_tokens is not None:
            if output_tokens_by_gen.get(sol_id) not in (None, n_tokens):
                token_crosscheck_mismatches += 1
        picks.append({
            "solution_id": sol_id,
            "solution_type": stype,
            "provenance": provenance,
            "mean_blind_raw": statistics.mean(raws),
            "n_blind_raters": len(raws),
            "judge_raw": float(judge_raw) if judge_raw is not None else None,
            "metrics": metrics_by_sol.get(sol_id, {}),
            "length_tokens": n_tokens,
            "length_chars": n_chars,
        })
    return picks, exclusions, dup_metric_rows, token_crosscheck_mismatches


def split_picks(picks):
    return {
        "human_authored": [p for p in picks if p["provenance"] == "human_authored"],
        "llm_generated": [p for p in picks if p["provenance"] == "llm_generated"],
        "pooled": list(picks),
    }


# ----------------------------- analyses -----------------------------

def metric_vs_human(splits):
    out = {}
    for metric in METRIC_ORDER:
        out[metric] = {}
        for split, rows in splits.items():
            xs = [p["metrics"].get(metric) for p in rows]
            ys = [p["mean_blind_raw"] for p in rows]
            out[metric][split] = corr_cell(xs, ys)
    return out


def residual_analysis(splits):
    """corr(judge_raw - mean_blind_raw, lexical metric).

    Positive r => the judge over-scores (relative to blind humans) exactly
    the solutions with high reference overlap — reference-style bias.
    r ~ 0 => the judge's deviations from humans are unrelated to reference
    overlap, supporting the templatic-writing account.
    """
    out = {}
    for metric in LEXICAL_METRICS:
        out[metric] = {}
        for split, rows in splits.items():
            xs, ys = [], []
            for p in rows:
                if p["judge_raw"] is None:
                    continue
                xs.append(p["metrics"].get(metric))
                ys.append(p["judge_raw"] - p["mean_blind_raw"])
            out[metric][split] = corr_cell(xs, ys)
    return out


def length_partial(splits):
    """Partial Pearson r(judge_raw, lexical metric | candidate length)."""
    out = {}
    for metric in LEXICAL_METRICS:
        out[metric] = {}
        for split, rows in splits.items():
            judge = [p["judge_raw"] for p in rows]
            mvals = [p["metrics"].get(metric) for p in rows]
            toks = [p["length_tokens"] for p in rows]
            chars = [p["length_chars"] for p in rows]
            partial_tok, n_tok = partial_pearson(judge, mvals, toks)
            partial_chr, n_chr = partial_pearson(judge, mvals, chars)
            out[metric][split] = {
                "n": n_tok,
                "zero_order_pearson_judge_metric": pearson(judge, mvals),
                "partial_pearson_given_tokens": partial_tok,
                "partial_pearson_given_chars": partial_chr,
                "n_chars": n_chr,
                "pearson_judge_length_tokens": pearson(judge, toks),
                "pearson_metric_length_tokens": pearson(mvals, toks),
            }
    return out


# ----------------------------- main -----------------------------

def main():
    picks, excluded, dup_rows, tok_mismatch = build_picks()
    splits = split_picks(picks)

    n_by_split = {s: len(rows) for s, rows in splits.items()}
    n_by_type = defaultdict(int)
    for p in picks:
        n_by_type[p["solution_type"]] += 1

    result = {
        "_meta": {
            "description": (
                "Automatic metrics anchored to the mean blind-reviewer raw grade "
                "(0-100) on the 45-solution human-validation subset, plus the "
                "judge-residual and length-partial diagnostics for the "
                "reference-style-bias reviewer hypothesis."
            ),
            "inputs": [
                "data/processed/benchathon_human_grades.json",
                "data/processed/benchathon_human_automatic_metrics.json",
                "data/processed/benchathon_automatic_metrics.json",
                "data/processed/benchathon_model_evaluations.json",
                "data/raw/benchathon/Benchathon_export.json",
            ],
            "matching_strategy": {
                "human_authored_picks": (
                    "solution_id == annotation_id. Blind grades from "
                    "benchathon_human_grades.json (role='blind', k=3 per pick); "
                    "metric values from benchathon_human_automatic_metrics.json "
                    "on annotation_id; judge raw from the raw export's task "
                    "evaluations via compute_agreement.index_judge_on_humans "
                    "(baseline judge field prefix, 'human:loesung' targets); "
                    "candidate text = annotation result loesung.value.markdown."
                ),
                "llm_generated_picks": (
                    "solution_id == generation_id. Blind grades as above; "
                    "metric values from benchathon_automatic_metrics.json on "
                    "generation_id; judge raw from "
                    "benchathon_model_evaluations.json (baseline judge); "
                    "candidate text = generation response_content via "
                    "derive_paper_exports._response_text."
                ),
                "human_anchor": "mean of the k=3 blind-reviewer raw_score per solution",
                "length": (
                    "length_tokens = tiktoken o200k_base count of the candidate "
                    "text (same count_tokens as the paper's output_tokens "
                    "column); length_chars = len() of the same text. Metrics "
                    "are never recomputed from text."
                ),
            },
            "n_picks": {
                "human_authored": n_by_split["human_authored"],
                "llm_generated": n_by_split["llm_generated"],
                "pooled": n_by_split["pooled"],
                "by_solution_type": dict(sorted(n_by_type.items())),
            },
            "bootstrap": {
                "B": BOOTSTRAP_B,
                "seed": BOOTSTRAP_SEED,
                "method": "percentile, paired resampling of (metric, grade) pairs",
                "note": "fresh default_rng(seed) per cell (leaderboard convention)",
            },
            "exclusions": {
                "picks_dropped": excluded,
                "duplicate_metric_rows_last_wins": dup_rows,
                "chrf": (
                    "not computed on Benchathon (neither metrics export carries "
                    "it) — all chrf cells have n=0"
                ),
                "bertscore": (
                    "absent from the human-annotation metric sidecar — "
                    "human_authored n=0; its pooled cell is the 15 LLM picks only"
                ),
                "semantic_similarity_moverscore": (
                    "computed on only 7 of the 30 human-authored picks in the "
                    "prod sidecar — pooled n=22"
                ),
                "coherence": "missing for 1 of the 15 LLM picks (pooled n=44)",
                "length_token_crosscheck_mismatches": tok_mismatch,
            },
            "caveats": [
                "Small n throughout (<= 45); CIs are wide and cells with n <= 7 "
                "(semantic_similarity / moverscore on human picks) are at best "
                "directional.",
                "Pooled cells mix two provenances with different judge "
                "calibration offsets (judge over-scores LLM picks by ~+27 raw); "
                "the split cells are the interpretable ones for the residual "
                "diagnostic.",
                "residual_analysis sign convention: residual = judge_raw - "
                "mean_blind_raw; positive correlation with a lexical metric "
                "indicates judge reference-style bias, ~0 supports the "
                "templatic-writing account.",
            ],
        },
        "metric_vs_human": metric_vs_human(splits),
        "residual_analysis": residual_analysis(splits),
        "length_partial": length_partial(splits),
    }

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"picks: {n_by_split} (excluded: {len(excluded)}, "
          f"dup metric rows: {dup_rows}, token cross-check mismatches: {tok_mismatch})")
    print("\nmetric_vs_human (Pearson r [95% CI] / Spearman rho, n):")
    for metric in METRIC_ORDER:
        cells = result["metric_vs_human"][metric]
        line = f"  {metric:20}"
        for split in SPLITS:
            c = cells[split]
            if c["pearson_r"] is None:
                line += f"  {split[:4]}: n={c['n']:>2}   --  "
            else:
                line += (f"  {split[:4]}: n={c['n']:>2} r={c['pearson_r']:+.3f}"
                         f"[{c['pearson_ci95_lo']:+.2f},{c['pearson_ci95_hi']:+.2f}]"
                         f" rho={c['spearman_rho']:+.3f}")
        print(line)
    print("\nresidual_analysis (judge - mean blind human vs metric):")
    for metric in LEXICAL_METRICS:
        cells = result["residual_analysis"][metric]
        line = f"  {metric:20}"
        for split in SPLITS:
            c = cells[split]
            if c["pearson_r"] is None:
                line += f"  {split[:4]}: n={c['n']:>2}   --  "
            else:
                line += (f"  {split[:4]}: n={c['n']:>2} r={c['pearson_r']:+.3f}"
                         f" rho={c['spearman_rho']:+.3f}")
        print(line)
    print("\nlength_partial (judge~metric | tokens):")
    for metric in LEXICAL_METRICS:
        cells = result["length_partial"][metric]
        line = f"  {metric:20}"
        for split in SPLITS:
            c = cells[split]
            zo = c["zero_order_pearson_judge_metric"]
            pt = c["partial_pearson_given_tokens"]
            line += (f"  {split[:4]}: n={c['n']:>2}"
                     f" r0={'--' if zo is None else format(zo, '+.3f')}"
                     f" rp={'--' if pt is None else format(pt, '+.3f')}")
        print(line)


if __name__ == "__main__":
    main()
