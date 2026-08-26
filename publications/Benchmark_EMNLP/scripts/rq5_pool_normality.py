"""Reviewer-requested pool normality check (n=30 supplementary).

For each human-authored Benchathon pick (n=30) and LLM-generated pick (n=15):
  - `full` = mean over k blind raters
  - `sub`  = mean over (k-1 blind raters + LLM judge), judge takes the
            alphabetically-last seat (deterministic, matches the pre-Phase-1
            substitution convention in compute_agreement.rq5_calderon)
Plot histograms, run Shapiro-Wilk on each series, run paired t-test on
(sub - full) differences, also report Wilcoxon paired for comparison.

This is a supplementary analysis. Calderon §1 critiques pool-aggregation
IAA measures as inadequate for *replacing* human annotators — the formal
Calderon alt-test (in `compute_agreement.rq5_calderon`) is the substitution
test, with ω=0.20 on human picks and ω=0.00 on LLM picks. This script
addresses the separate descriptive question: does swapping the judge into
the pool measurably shift the pool mean?

  uv run python scripts/rq5_pool_normality.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from scipy import stats

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
ASSETS = HERE / "assets"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import (  # noqa: E402
    REAL,
    humans_by_solution,
    index_judge_on_humans,
    load_json,
)


def build_pool_series(judge_by_sol, humans):
    """For each solution with k>=2 blind raters and a judge score:
       full = mean(k raters), sub = mean((k-1) raters + judge).
    Drops alphabetically-last rater to take the judge seat (deterministic).
    Returns two parallel lists across solutions.
    """
    full_series, sub_series = [], []
    for sol_id, graders in humans.items():
        rated = [(g.get("grader_id") or "", g["raw_score"])
                 for g in graders if g["raw_score"] is not None]
        if len(rated) < 2:
            continue
        judge = judge_by_sol.get(sol_id)
        if judge is None:
            continue
        rated.sort()
        raws = [r for _, r in rated]
        full_series.append(statistics.mean(raws))
        sub_series.append((sum(raws[:-1]) + judge) / len(raws))
    return full_series, sub_series


def report(label, full, sub):
    n = len(full)
    out = {"label": label, "n": n}
    print(f"\n=== {label} (n={n}) ===")
    if n < 3:
        print("  too few points for SW")
        return out
    sw_full = stats.shapiro(full)
    sw_sub = stats.shapiro(sub)
    diffs = [s - f for s, f in zip(sub, full)]
    sw_diff = stats.shapiro(diffs)
    print(f"  Shapiro-Wilk full:        W={sw_full.statistic:.4f}, p={sw_full.pvalue:.4f}")
    print(f"  Shapiro-Wilk sub:         W={sw_sub.statistic:.4f}, p={sw_sub.pvalue:.4f}")
    print(f"  Shapiro-Wilk (sub-full):  W={sw_diff.statistic:.4f}, p={sw_diff.pvalue:.4f}  <- the assumption that matters for paired t-test")
    print(f"  Mean(sub - full):   {statistics.mean(diffs):+.3f} pts (sd={statistics.stdev(diffs):.3f}, range=[{min(diffs):+.2f}, {max(diffs):+.2f}])")
    ttest = stats.ttest_rel(sub, full)
    print(f"  Paired t-test:      t={ttest.statistic:.3f}, p={ttest.pvalue:.4f}")
    try:
        wilcoxon = stats.wilcoxon(sub, full)
        print(f"  Wilcoxon (paired):  W={wilcoxon.statistic:.3f}, p={wilcoxon.pvalue:.4f}")
    except ValueError:
        print(f"  Wilcoxon (paired):  undefined (all differences zero)")
    out.update({
        "sw_full": {"W": float(sw_full.statistic), "p": float(sw_full.pvalue)},
        "sw_sub":  {"W": float(sw_sub.statistic),  "p": float(sw_sub.pvalue)},
        "sw_diff": {"W": float(sw_diff.statistic), "p": float(sw_diff.pvalue)},
        "diff_mean": statistics.mean(diffs),
        "diff_sd": statistics.stdev(diffs),
        "ttest_paired": {"t": float(ttest.statistic), "p": float(ttest.pvalue)},
    })
    return out


def plot_histograms(label, full, sub, out_path):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    diffs = [s - f for s, f in zip(sub, full)]

    axes[0].hist(full, bins=10, edgecolor='black', alpha=0.7, color='steelblue')
    axes[0].set_title(f"{label}: full pool (3 humans)")
    axes[0].set_xlabel("Pool mean (raw 0–100 scale)")
    axes[0].set_ylabel("Count")

    axes[1].hist(sub, bins=10, edgecolor='black', alpha=0.7, color='coral')
    axes[1].set_title(f"{label}: substituted (2 humans + judge)")
    axes[1].set_xlabel("Pool mean (raw 0–100 scale)")
    axes[1].set_ylabel("Count")

    axes[2].hist(diffs, bins=10, edgecolor='black', alpha=0.7, color='seagreen')
    axes[2].axvline(0, color='black', linewidth=1, linestyle='--')
    axes[2].set_title(f"{label}: sub - full (paired diff)")
    axes[2].set_xlabel("Difference (raw points)")
    axes[2].set_ylabel("Count")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  saved {out_path}")


def main():
    real = load_json(REAL)
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")

    judge_on_humans = index_judge_on_humans(real)
    judge_by_sol_human = {k: float(v["raw_score"]) for k, v in judge_on_humans.items()
                          if v.get("raw_score") is not None}
    humans = humans_by_solution(canonical, role_filter="blind")
    full_h, sub_h = build_pool_series(judge_by_sol_human, humans)

    judge_by_gen = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                    if r.get("raw_score") is not None}
    blind_llm = humans_by_solution(canonical, role_filter="blind",
                                   solution_type_filter="llm_system")
    full_l, sub_l = build_pool_series(judge_by_gen, blind_llm)

    print(f"Loaded {len(full_h)} human-authored picks, {len(full_l)} LLM-generated picks")

    ASSETS.mkdir(parents=True, exist_ok=True)

    r_h = report("Human-authored picks", full_h, sub_h)
    plot_histograms("Human-authored", full_h, sub_h, ASSETS / "pool_normality_human.png")

    r_l = report("LLM-generated picks", full_l, sub_l)
    plot_histograms("LLM-generated", full_l, sub_l, ASSETS / "pool_normality_llm.png")

    # Persist the numeric results so the manuscript chunk (if added) can read them.
    out_json = PROCESSED / "pool_normality.json"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump({"human_authored": r_h, "llm_generated": r_l}, f, indent=2)
    print(f"\nsaved {out_json}")

    print()
    print("=== Interpretation guide ===")
    print("Shapiro-Wilk H0: data drawn from a normal distribution.")
    print("  High p-value (> 0.05): fail to reject normality → parametric paired t-test is defensible.")
    print("  Low p-value (≤ 0.05): reject normality → prefer Wilcoxon signed-rank.")
    print()
    print("Paired t-test / Wilcoxon H0: sub and full have equal means.")
    print("  High p-value (> 0.05): no detectable shift from substituting the judge.")
    print("  Low p-value (≤ 0.05): judge substitution shifts the pool mean significantly.")
    print()
    print("Note: Calderon §1 explicitly critiques pool-aggregation correlation/")
    print("equivalence measures. This script reports a descriptive supplementary")
    print("check; the formal Calderon alt-test in compute_agreement.rq5_calderon")
    print("is the substitution test of record.")


if __name__ == "__main__":
    main()
