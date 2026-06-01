"""Run the formal Calderon alt-test (compute_agreement.rq5_calderon_blind_pool)
separately for each judge model in Config B (GPT-5-mini / Opus / Gemini), on
human-authored and LLM-generated picks.

Reviewer follow-up: GPT-5-mini fails the alt-test with ω=0.20 on human picks
and ω=0.00 on LLM picks; the per-judge calibration audit showed Opus is
near-perfectly calibrated to the blind-reviewer pool while GPT-5-mini sits
+4.82 / +9.16 above it. Does a calibrated judge (Opus) actually clear the
ω≥0.5 substitution bar?

Outputs:
  data/processed/calderon_per_judge.json    per-judge alt-test payloads
  printed table to stdout

  uv run python scripts/rq5_calderon_per_judge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import (  # noqa: E402
    REAL,
    _alt_test_blind_pool,
    _build_blind_pool_inputs,
    humans_by_solution,
    index_judge_on_humans,
    load_json,
)
from derive_paper_exports import (  # noqa: E402
    CONFIG_B_FIELD_PREFIX,
    CONFIG_DEEPSEEK_FIELD_PREFIX,
    CONFIG_QWEN_FIELD_PREFIX,
    CONFIG_SONNET_FIELD_PREFIX,
)
from rq5_judge_calibration import index_judge_per_config  # noqa: E402


def run_alt_test_for_judge(judge_by_sol, humans, *, eps=0.15):
    """Run §3 blind-pool alt-test with this judge's scores. Also computes
    the per-solution Pearson r between the judge and the mean of the blind
    reviewers (the traditional LLM-human alignment metric in Calderon
    Table 2's "Pears" column), restricted to the same instances the
    alt-test uses.
    """
    inputs, n_total = _build_blind_pool_inputs(judge_by_sol, humans)
    payload = _alt_test_blind_pool(inputs, eps=eps)
    payload["n_instances_total"] = n_total

    # Per-solution Pearson r against mean blind reviewer
    judge_vals, mean_blind_vals = [], []
    for sol_id, graders in humans.items():
        rated = [g["raw_score"] for g in graders if g["raw_score"] is not None]
        if len(rated) < 3:
            continue
        j = judge_by_sol.get(sol_id)
        if j is None:
            continue
        judge_vals.append(float(j))
        mean_blind_vals.append(sum(rated) / len(rated))
    from compute_agreement import pearson  # local import keeps top-of-file lean
    payload["pearson_judge_vs_mean_blind"] = pearson(judge_vals, mean_blind_vals)
    payload["n_pearson"] = len(judge_vals)
    return payload


def fmt_row(label, payload, col_w=46):
    label = (label + " " * col_w)[:col_w]
    if not payload or payload.get("m_annotators", 0) == 0:
        return f"{label}  (no data)"
    m = payload["m_annotators"]
    n = payload["n_instances_total"]
    omega = payload["winning_rate"]
    rho = payload["avg_advantage_probability"]
    passes = payload["passes_alt_test"]
    rejected = sum(1 for e in payload["per_annotator"] if e["rejected_BY_FDR"])
    return (f"{label}  m={m}  n={n:3d}  "
            f"ω={omega:.2f} (rejects {rejected}/{m})  "
            f"ρ={rho:.2f}  "
            f"{'PASS' if passes else 'fail'}")


def main():
    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")
    humans_h = humans_by_solution(canonical, role_filter="blind")
    humans_llm = humans_by_solution(canonical, role_filter="blind",
                                    solution_type_filter="llm_system")

    # Three per-judge configs to compare against the baseline GPT-5-mini.
    inter_h = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="human")
    inter_l = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="llm")

    # Single-judge follow-up runs (2026-05-31): DeepSeek-V4-Pro and Qwen3.5-397B-A17B
    # were re-run as standalone judges on the same Benchathon picks. Each config
    # carries exactly one judge_model, so unwrap the singleton.
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

    # Sonnet-4.6 standalone single-judge run. Same singleton-unwrap as
    # DeepSeek/Qwen above.
    sn_h = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="human").values()), {})
    sn_l = next(iter(index_judge_per_config(
        real, prefix=CONFIG_SONNET_FIELD_PREFIX,
        group_by_judge=True, target="llm").values()), {})
    # GPT-5.4-mini is now the *primary* baseline judge. Five additional
    # cross-validation judges (Opus, Gemini, DeepSeek, Qwen, Sonnet) round
    # out the six-judge ensemble. The legacy GPT-5-mini scoring is no
    # longer surfaced.

    # Baseline single-pass = GPT-5.4-mini (new primary).
    baseline_idx_h = index_judge_on_humans(real)
    baseline_h = {k: float(v["raw_score"]) for k, v in baseline_idx_h.items()
                  if v.get("raw_score") is not None}
    baseline_l = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                  if r.get("raw_score") is not None}

    results = {}
    rows = []

    for label, by_sol, humans, key in (
        ("Baseline GPT-5.4-mini  (human picks, ε=0.15)", baseline_h, humans_h, "baseline_human"),
        ("Config B Opus-4.7  (human picks)",             inter_h.get("claude-opus-4-7", {}), humans_h, "cfgB_opus_human"),
        ("Config B Gemini-3.1-Pro  (human picks)",       inter_h.get("gemini-3.1-pro-preview", {}), humans_h, "cfgB_gemini_human"),
        ("DeepSeek-V4-Pro  (human picks)",               ds_h, humans_h, "deepseek_human"),
        ("Qwen3.5-397B-A17B  (human picks)",             qw_h, humans_h, "qwen_human"),
        ("Sonnet-4.6  (human picks)",                    sn_h, humans_h, "sonnet_human"),
        ("Baseline GPT-5.4-mini  (LLM picks, ε=0.15)",   baseline_l, humans_llm, "baseline_llm"),
        ("Config B Opus-4.7  (LLM picks)",               inter_l.get("claude-opus-4-7", {}), humans_llm, "cfgB_opus_llm"),
        ("Config B Gemini-3.1-Pro  (LLM picks)",         inter_l.get("gemini-3.1-pro-preview", {}), humans_llm, "cfgB_gemini_llm"),
        ("DeepSeek-V4-Pro  (LLM picks)",                 ds_l, humans_llm, "deepseek_llm"),
        ("Qwen3.5-397B-A17B  (LLM picks)",               qw_l, humans_llm, "qwen_llm"),
        ("Sonnet-4.6  (LLM picks)",                      sn_l, humans_llm, "sonnet_llm"),
    ):
        payload = run_alt_test_for_judge(by_sol or {}, humans, eps=0.15)
        results[key] = {"label": label, "payload": payload}
        rows.append((label, payload))

    print()
    print("=" * 120)
    print("Calderon alt-test ω (§3 blind-pool), per judge model, ε=0.15, BY-FDR q=0.05")
    print("=" * 120)
    for label, payload in rows:
        print(fmt_row(label, payload))
    print("=" * 120)
    print("PASS = ω ≥ 0.5  (judge can replace a randomly drawn blind reviewer)")
    print("rejects N/m = number of blind reviewers significantly beaten by the judge after BY-FDR")
    print("=" * 120)

    # Per-annotator breakdown for the most interesting rows: the two judges
    # that clear ω ≥ 0.5 on human picks (baseline GPT-5.4-mini, Opus-4.7)
    # plus the four others that fail.
    print()
    print("=" * 120)
    print("Per-annotator p-values (one-sided, after BY-FDR)")
    print("=" * 120)
    for key in ("baseline_human", "cfgB_opus_human", "sonnet_human",
                "cfgB_gemini_human", "deepseek_human", "qwen_human"):
        r = results[key]
        print(f"\n{r['label']}:")
        for entry in r["payload"]["per_annotator"]:
            mark = "***" if entry["rejected_BY_FDR"] else ""
            print(f"  {entry['grader_id'][:22]:22s}  "
                  f"n_j={entry['n_j']:3d}  "
                  f"ρ^f={entry['rho_f']:.2f}  ρ^h={entry['rho_h']:.2f}  "
                  f"d̄={entry['d_bar']:+.3f}  "
                  f"{entry['test']:8s}  p={entry['p_value']:.4f}  {mark}")
    print("=" * 120)

    out = PROCESSED / "calderon_per_judge.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({k: {"label": v["label"], "payload": v["payload"]}
                   for k, v in results.items()},
                  f, indent=2, default=float)
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
