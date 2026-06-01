"""Per-judge calibration check: is the +4 to +8 lenient bias GPT-5-mini-specific
or shared by Opus and Gemini? And is it stable across intra-judge runs?

Inter-judge: Config B (mpe7o02k-yrio) — gpt-5-mini + claude-opus-4-7 +
gemini-3.1-pro-preview each scored every human-authored pick once. We run the
pool-substitution pipeline (full = mean of 3 blind raters; sub = mean of 2
blind raters + judge) per judge and report Shapiro-Wilk normality of the
paired (sub - full) differences plus paired t-test on the shift.

Intra-judge: Config A (mpe7mkzx-2zp6) — gpt-5-mini × 3 passes per pick.
We run the same pipeline per pass and check whether the bias is stable.

Outputs:
  data/processed/judge_calibration.json   per-judge / per-pass stats
  assets/pool_normality_per_judge.png     side-by-side histograms
  printed table to stdout

Calderon §1 critiques pool-aggregation as a substitution metric; this is the
descriptive supplementary check the reviewer requested, NOT the formal
alt-test. The alt-test of record stays in compute_agreement.rq5_calderon.

  uv run python scripts/rq5_judge_calibration.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from scipy import stats

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
ASSETS = HERE / "assets"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import REAL, humans_by_solution, load_json  # noqa: E402
from derive_paper_exports import (  # noqa: E402
    CONFIG_A_GPT54MINI_FIELD_PREFIX,
    CONFIG_B_FIELD_PREFIX,
    CONFIG_DEEPSEEK_FIELD_PREFIX,
    CONFIG_QWEN_FIELD_PREFIX,
    CONFIG_SONNET_FIELD_PREFIX,
)


def _raw_from_eval(ev):
    kf = (ev.get("metrics") or {}).get("llm_judge_falloesung")
    if isinstance(kf, dict):
        d = kf.get("details") or {}
        if d.get("raw_score") is not None:
            return float(d["raw_score"])
        v = kf.get("value")
        if v is not None:
            return float(v)
    m = ev.get("metrics") or {}
    if m.get("raw_score") is not None:
        return float(m["raw_score"])
    return None


def index_judge_per_config(real, *, prefix, group_by_judge=True,
                           target="human"):
    """Index evaluations matching `prefix`.

    target="human": pull task.evaluations whose field_name contains "human:loesung",
                    key by annotation_id.
    target="llm":   pull gen.evaluations under each task.generations[],
                    key by generation_id.
    """
    out = defaultdict(dict) if group_by_judge else defaultdict(list)
    if target == "human":
        for task in real["tasks"]:
            for ev in task.get("evaluations") or []:
                fn = str(ev.get("field_name") or "")
                if not fn.startswith(prefix) or "human:loesung" not in fn:
                    continue
                raw = _raw_from_eval(ev)
                if raw is None:
                    continue
                ann_id = ev.get("annotation_id")
                if not ann_id:
                    continue
                if group_by_judge:
                    judge = ev.get("judge_model") or "?"
                    out[judge][ann_id] = raw
                else:
                    out[ann_id].append(raw)
    elif target == "llm":
        for task in real["tasks"]:
            for gen in task.get("generations") or []:
                gid = gen.get("id")
                if not gid:
                    continue
                for ev in gen.get("evaluations") or []:
                    fn = str(ev.get("field_name") or "")
                    if not fn.startswith(prefix):
                        continue
                    raw = _raw_from_eval(ev)
                    if raw is None:
                        continue
                    if group_by_judge:
                        judge = ev.get("judge_model") or "?"
                        out[judge][gid] = raw
                    else:
                        out[gid].append(raw)
    return out


def build_pool_series(judge_by_sol, humans):
    """For each solution with >=2 blind raters AND a judge score:
       full = mean(k raters), sub = mean((k-1) raters + judge),
       judge = the per-solution judge score itself.
    Alphabetically-last rater drops to take the judge seat in `sub`.
    Returns parallel full, sub, judge series across solutions so callers
    can separate the *substitution* shift (sub − full, attenuated by 1/k
    relative to a direct comparison) from the *direct* judge-vs-pool
    offset (judge − full), which is what readers usually want when the
    text says "the judge sits X points above the pool".
    """
    full_s, sub_s, judge_s = [], [], []
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
        full_s.append(statistics.mean(raws))
        sub_s.append((sum(raws[:-1]) + judge) / len(raws))
        judge_s.append(float(judge))
    return full_s, sub_s, judge_s


def analyse(label, full, sub, judge=None):
    """Per-judge calibration summary.

    Reports two paired comparisons:

    * `diff_mean` etc. — the *substitution* shift Δ_sub = sub − full.
      This is the Calderon §1 pool-substitution quantity; at k blind
      raters it equals (judge − dropped_rater)/k, so its magnitude is
      attenuated by 1/k relative to a direct judge-vs-pool comparison.
      Kept for the supplementary table the manuscript already cites.

    * `judge_minus_pool_*` — the *direct* offset Δ_dir = judge − full,
      which is what readers expect when the prose says "the judge sits
      X raw points above the blind-reviewer pool". This is the number
      to quote for absolute calibration claims and for any RQ1/RQ2
      leaderboard discount; `Δ_sub × k` is a reasonable approximation
      when the dropped rater is near the pool mean, but the direct
      number is exact.
    """
    n = len(full)
    if n < 3:
        return {"label": label, "n": n}
    diffs = [s - f for s, f in zip(sub, full)]
    sw_diff = stats.shapiro(diffs)
    ttest = stats.ttest_rel(sub, full)
    try:
        wlx = stats.wilcoxon(sub, full)
        wlx_p = float(wlx.pvalue)
    except ValueError:
        wlx_p = None
    out = {
        "label": label,
        "n": n,
        "full_mean": statistics.mean(full),
        "sub_mean": statistics.mean(sub),
        "diff_mean": statistics.mean(diffs),
        "diff_sd": statistics.stdev(diffs),
        "diff_min": min(diffs),
        "diff_max": max(diffs),
        "sw_diff_W": float(sw_diff.statistic),
        "sw_diff_p": float(sw_diff.pvalue),
        "ttest_t": float(ttest.statistic),
        "ttest_p": float(ttest.pvalue),
        "wilcoxon_p": wlx_p,
    }
    if judge is not None and len(judge) == n:
        direct = [j - f for j, f in zip(judge, full)]
        ttest_dir = stats.ttest_rel(judge, full)
        try:
            wlx_dir = stats.wilcoxon(judge, full)
            wlx_dir_p = float(wlx_dir.pvalue)
        except ValueError:
            wlx_dir_p = None
        out.update({
            "judge_mean": statistics.mean(judge),
            "judge_minus_pool_mean": statistics.mean(direct),
            "judge_minus_pool_sd": statistics.stdev(direct),
            "judge_minus_pool_min": min(direct),
            "judge_minus_pool_max": max(direct),
            "judge_pool_ttest_t": float(ttest_dir.statistic),
            "judge_pool_ttest_p": float(ttest_dir.pvalue),
            "judge_pool_wilcoxon_p": wlx_dir_p,
        })
    return out


def fmt_row(r, label_w=44):
    label = (r["label"] + " " * label_w)[:label_w]
    if r.get("n", 0) < 3:
        return f"{label}  (n={r.get('n','?')}, too few)"
    n = r["n"]
    direct = r.get("judge_minus_pool_mean")
    direct_str = f"  J−pool̄={direct:+6.2f}" if direct is not None else ""
    return (f"{label}  n={n:3d}  "
            f"full̄={r['full_mean']:6.2f}  sub̄={r['sub_mean']:6.2f}  "
            f"Δsub={r['diff_mean']:+6.2f} (sd={r['diff_sd']:5.2f})"
            f"{direct_str}  "
            f"SW p={r['sw_diff_p']:.3f}  "
            f"t={r['ttest_t']:+6.2f}  p={r['ttest_p']:.4f}")


def main():
    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    humans_h = humans_by_solution(canonical, role_filter="blind")
    humans_llm = humans_by_solution(canonical, role_filter="blind",
                                    solution_type_filter="llm_system")

    # ---- Inter-judge (Config B): three judges scored each pick once.
    inter_h = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="human")
    inter_l = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="llm")

    # ---- Single-judge follow-up runs (2026-05-31): DeepSeek-V4-Pro and
    # Qwen3.5-397B-A17B as standalone Config-B-style judges, each under its
    # own field-name prefix with a single judge_model.
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

    # ---- Standalone judge follow-up runs (DeepSeek-V4-Pro, Qwen3.5-397B,
    # Sonnet-4.6); each scored every Benchathon pick once under its own
    # field-name prefix with a single judge_model.
    sn_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    sn_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})
    # GPT-5.4-mini is now the *primary* judge (BASELINE_JUDGE_FIELD_PREFIX)
    # so its standalone row is identical to the Baseline single-pass row and
    # we drop it from this table to avoid duplication. The legacy GPT-5-mini
    # single-pass run is retained as a continuity comparator under its
    # original prefix.

    # ---- Baseline single-pass: one *GPT-5.4-mini* score per pick (NEW
    # primary as of 2026-06-01). For human picks, use index_judge_on_humans
    # (handles the baseline Shape-A/Shape-B envelope, now keyed against the
    # GPT-5.4-mini run via BASELINE_JUDGE_FIELD_PREFIX). For LLM picks, use
    # benchathon_model_evaluations.json which is regenerated against the new
    # baseline by derive_paper_exports.py.
    from compute_agreement import index_judge_on_humans  # noqa: E402
    baseline_idx_h = index_judge_on_humans(real)
    baseline_by_sol_h = {k: float(v["raw_score"]) for k, v in baseline_idx_h.items()
                         if v.get("raw_score") is not None}
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    baseline_by_sol_l = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                         if r.get("raw_score") is not None}

    # ---- Intra-judge (Config A) for GPT-5.4-mini × 3, landed 2026-06-01.
    # Returns {sol_id: [score_pass1, score_pass2, score_pass3]}.
    intra_h = index_judge_per_config(real, prefix=CONFIG_A_GPT54MINI_FIELD_PREFIX,
                                     group_by_judge=False, target="human")
    intra_l = index_judge_per_config(real, prefix=CONFIG_A_GPT54MINI_FIELD_PREFIX,
                                     group_by_judge=False, target="llm")

    rows = []

    def add(label, by_sol, humans):
        full_s, sub_s, judge_s = build_pool_series(by_sol, humans)
        rows.append(analyse(label, full_s, sub_s, judge_s))

    # === HUMAN-AUTHORED PICKS ===
    # Six judges: GPT-5.4-mini (primary) + five cross-validation judges.
    # Opus and Gemini are surfaced from the Config B trio; DeepSeek, Qwen,
    # Sonnet are standalone single-judge runs.
    add("Baseline single-pass GPT-5.4-mini  (human)", baseline_by_sol_h, humans_h)
    add("Config B Opus-4.7  (human)", inter_h.get("claude-opus-4-7", {}), humans_h)
    add("Config B Gemini-3.1-Pro  (human)", inter_h.get("gemini-3.1-pro-preview", {}), humans_h)
    add("DeepSeek-V4-Pro  (human)", ds_h, humans_h)
    add("Qwen3.5-397B-A17B  (human)", qw_h, humans_h)
    add("Sonnet-4.6  (human)", sn_h, humans_h)
    # Config A GPT-5.4-mini × 3 intra-judge rows: mean + per-pass breakdown.
    avg_h = {sid: statistics.mean(vs) for sid, vs in intra_h.items() if vs}
    add("Config A GPT-5.4-mini × 3 (mean)  (human)", avg_h, humans_h)
    for p in range(3):
        per_pass = {sid: vs[p] for sid, vs in intra_h.items() if len(vs) > p}
        add(f"Config A GPT-5.4-mini pass {p+1}  (human)", per_pass, humans_h)

    # === LLM-GENERATED PICKS ===
    add("Baseline single-pass GPT-5.4-mini  (LLM)", baseline_by_sol_l, humans_llm)
    add("Config B Opus-4.7  (LLM)", inter_l.get("claude-opus-4-7", {}), humans_llm)
    add("Config B Gemini-3.1-Pro  (LLM)", inter_l.get("gemini-3.1-pro-preview", {}), humans_llm)
    add("DeepSeek-V4-Pro  (LLM)", ds_l, humans_llm)
    add("Qwen3.5-397B-A17B  (LLM)", qw_l, humans_llm)
    add("Sonnet-4.6  (LLM)", sn_l, humans_llm)
    avg_l = {sid: statistics.mean(vs) for sid, vs in intra_l.items() if vs}
    add("Config A GPT-5.4-mini × 3 (mean)  (LLM)", avg_l, humans_llm)
    for p in range(3):
        per_pass = {sid: vs[p] for sid, vs in intra_l.items() if len(vs) > p}
        add(f"Config A GPT-5.4-mini pass {p+1}  (LLM)", per_pass, humans_llm)

    # Print table
    print()
    print("=" * 150)
    print("Per-judge pool comparison: substitution shift Δsub = sub − full  AND  direct offset Δdir = judge − full")
    print("=" * 150)
    print(f"{'Configuration':44s}  {'n':>3s}   full̄    sub̄        Δsub  (sd)    J−pool̄   SW p     t            p")
    print("-" * 150)
    for r in rows:
        print(fmt_row(r))
    print("=" * 150)
    print("Δsub equals (judge − dropped_rater)/k by construction (Calderon §1 pool-substitution metric).")
    print("J−pool̄ is the direct judge-vs-pool offset; use this number when the prose says 'judge sits X above pool'.")
    print("SW p > 0.05 ⇒ paired-difference series is consistent with normality (t-test defensible).")
    print("=" * 150)

    # Save JSON for the manuscript table chunk
    out = PROCESSED / "judge_calibration.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print(f"\nsaved {out}")

    # Plot 6-judge × 2-corpus comparison histograms of Δ = sub − full.
    # Layout: 2 rows (human / LLM picks) × 6 columns (judges, ordered by
    # strictness against the blind pool: GPT-5.4-mini, Opus-4.7, Sonnet-4.6,
    # DeepSeek-V4-Pro, Gemini-3.1-Pro, Qwen3.5-397B-A17B).
    # figsize is tuned so that the rendered PNG, included at
    # \includegraphics[width=0.85\textwidth] in the figure* environment,
    # fits within the ACL two-column text width (\textwidth = 17.78 cm
    # ≈ 7 in) without horizontal overflow. Aspect ratio kept ≈ 2:1 so
    # the per-panel bars stay legible after scaling.
    ASSETS.mkdir(parents=True, exist_ok=True)
    # figsize tuned for ACL two-column \textwidth ≈ 7.0 in. We disable
    # bbox_inches='tight' below (which would expand the saved PNG beyond
    # figsize whenever titles/labels overflow) and pair the include in the
    # manuscript with width=\textwidth so the PNG renders at 1:1.
    fig, axes = plt.subplots(2, 6, figsize=(14, 6), sharey='row',
                             gridspec_kw={"wspace": 0.25, "hspace": 0.55})
    judge_panels = [
        ("GPT-5.4-mini",        "tab:purple",  baseline_by_sol_h, baseline_by_sol_l),
        ("Opus-4.7",            "tab:orange",  inter_h.get("claude-opus-4-7", {}),
                                               inter_l.get("claude-opus-4-7", {})),
        ("Sonnet-4.6",          "tab:red",     sn_h, sn_l),
        ("DeepSeek-V4-Pro",     "tab:brown",   ds_h, ds_l),
        ("Gemini-3.1-Pro",      "tab:green",   inter_h.get("gemini-3.1-pro-preview", {}),
                                               inter_l.get("gemini-3.1-pro-preview", {})),
        ("Qwen3.5-A17B",        "tab:olive",   qw_h, qw_l),
    ]
    for col, (label, colour, by_sol_h, by_sol_l) in enumerate(judge_panels):
        for row, (by_sol, humans, ctitle) in enumerate(
                ((by_sol_h, humans_h, "human-authored"),
                 (by_sol_l, humans_llm, "LLM-generated"))):
            ax = axes[row][col]
            full_s, sub_s, _ = build_pool_series(by_sol, humans)
            diffs = [s - f for s, f in zip(sub_s, full_s)]
            if diffs:
                ax.hist(diffs, bins=10, color=colour, edgecolor='black',
                        alpha=0.85, linewidth=0.5)
                ax.axvline(0, color='black', linewidth=0.8, linestyle='--')
                ax.set_title(
                    f"{label}, {ctitle}\n$\\bar\\Delta={statistics.mean(diffs):+.2f}$"
                    f" ($n$={len(diffs)})",
                    fontsize=9)
                ax.set_xlabel(r"$\Delta_{\rm sub}$ (raw)", fontsize=8)
                ax.tick_params(axis='both', labelsize=7)
            else:
                ax.set_title(f"{label}, {ctitle}\n(no data)", fontsize=9)
        axes[row][0].set_ylabel("Count", fontsize=8)
    fig.suptitle("Pool-substitution shift by judge $\\times$ corpus "
                 "(primary GPT-5.4-mini + five cross-validation judges)",
                 y=0.99, fontsize=10)
    # Explicit margins to keep the figure exactly within figsize.
    fig.subplots_adjust(top=0.86, bottom=0.12, left=0.05, right=0.995)
    out_png = ASSETS / "pool_normality_per_judge.png"
    # IMPORTANT: do NOT use bbox_inches='tight' here. Matplotlib's tight
    # bbox calculation re-frames the saved image to include any element
    # extending past the figure boundary (suptitle, tick labels), which
    # makes the PNG wider than figsize and breaks LaTeX's width-based
    # scaling. We rely on subplots_adjust above to keep everything in box.
    fig.savefig(out_png, dpi=300)
    plt.close(fig)
    print(f"saved {out_png}")


if __name__ == "__main__":
    main()
