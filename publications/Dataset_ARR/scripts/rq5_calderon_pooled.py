"""Reference-only: Calderon §3 alt-test on the pooled subset (30 human-authored
+ 15 LLM-generated = 45 picks). Not used in the manuscript — the headline
analysis splits by corpus because the judge's calibration bias differs across
content types (+14 raw points above pool on human picks vs +24 on LLM picks
for GPT-5-mini), and pooling would mix those regimes.

Useful as a sanity check: with the corpora combined, per-reviewer n_j can
exceed 30, which lets some tests use the parametric t-test branch.

Outputs:
    assets/rq5/10_calderon_pooled.csv          per-judge summary
    assets/rq5/11_calderon_pooled_per_annotator.csv  per-reviewer detail
    prints summary tables to stdout

    uv run python scripts/rq5_calderon_pooled.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
OUT_DIR = HERE / "assets" / "rq5"

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
    CONFIG_GPT54MINI_FIELD_PREFIX,
    CONFIG_QWEN_FIELD_PREFIX,
    CONFIG_SONNET_FIELD_PREFIX,
)
from rq5_judge_calibration import index_judge_per_config  # noqa: E402


JUDGES = (
    ("baseline", "GPT-5-mini (baseline)"),
    ("gpt5",     "GPT-5-mini (Config B)"),
    ("gemini",   "Gemini-3.1-Pro (Config B)"),
    ("opus",     "Opus-4.7 (Config B)"),
    ("deepseek", "DeepSeek-V4-Pro"),
    ("qwen",     "Qwen3.5-397B-A17B"),
    ("sonnet",   "Sonnet-4.6"),
    ("gpt54mini", "GPT-5.4-mini"),
)


def main():
    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    model_evals = load_json(PROCESSED / "benchathon_model_evaluations.json")

    humans_h = humans_by_solution(canonical, role_filter="blind")
    humans_llm = humans_by_solution(canonical, role_filter="blind",
                                    solution_type_filter="llm_system")
    humans_pooled = {**humans_h, **humans_llm}

    # Judge scores keyed by solution_id (human picks) and generation_id (LLM picks)
    baseline_idx_h = index_judge_on_humans(real)
    baseline_h = {k: float(v["raw_score"]) for k, v in baseline_idx_h.items()
                  if v.get("raw_score") is not None}
    baseline_l = {r["generation_id"]: float(r["raw_score"]) for r in model_evals
                  if r.get("raw_score") is not None}
    baseline_pooled = {**baseline_h, **baseline_l}

    inter_h = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="human")
    inter_l = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="llm")

    def cfgb_pooled(judge_model):
        return {**(inter_h.get(judge_model) or {}),
                **(inter_l.get(judge_model) or {})}

    def singleton_pooled(prefix):
        h = next(iter(index_judge_per_config(
            real, prefix=prefix, group_by_judge=True, target="human").values()), {})
        l = next(iter(index_judge_per_config(
            real, prefix=prefix, group_by_judge=True, target="llm").values()), {})
        return {**h, **l}

    judge_scores = {
        "baseline": baseline_pooled,
        "gpt5":     cfgb_pooled("gpt-5-mini"),
        "gemini":   cfgb_pooled("gemini-3.1-pro-preview"),
        "opus":     cfgb_pooled("claude-opus-4-7"),
        "deepseek": singleton_pooled(CONFIG_DEEPSEEK_FIELD_PREFIX),
        "qwen":     singleton_pooled(CONFIG_QWEN_FIELD_PREFIX),
        "sonnet":   singleton_pooled(CONFIG_SONNET_FIELD_PREFIX),
        "gpt54mini": singleton_pooled(CONFIG_GPT54MINI_FIELD_PREFIX),
    }

    summary_rows = []
    per_ann_rows = []

    for slug, name in JUDGES:
        inputs, n_total = _build_blind_pool_inputs(judge_scores[slug], humans_pooled)
        payload = _alt_test_blind_pool(inputs, eps=0.15)
        payload["n_instances_total"] = n_total

        rej = sum(1 for e in payload["per_annotator"] if e.get("rejected_BY_FDR"))
        summary_rows.append({
            "judge": name,
            "corpus": "pooled (human + LLM)",
            "epsilon": payload.get("epsilon"),
            "m_annotators": payload.get("m_annotators"),
            "n_instances": n_total,
            "winning_rate_omega": payload.get("winning_rate"),
            "avg_advantage_rho": payload.get("avg_advantage_probability"),
            "n_rejected_BY_FDR": rej,
            "passes_alt_test": payload.get("passes_alt_test"),
            "omega_ci95_lo_clopper": payload.get("winning_rate_ci95_lo_clopper"),
            "omega_ci95_hi_clopper": payload.get("winning_rate_ci95_hi_clopper"),
        })

        for e in payload["per_annotator"]:
            gid = (e.get("grader_id") or "").split("@")[0]
            per_ann_rows.append({
                "judge": name,
                "corpus": "pooled (human + LLM)",
                "grader_id": gid,
                "n_j": e.get("n_j"),
                "rho_f_judge_wins": e.get("rho_f"),
                "rho_h_reviewer_wins": e.get("rho_h"),
                "d_bar": e.get("d_bar"),
                "test": e.get("test"),
                "p_value_one_sided": e.get("p_value"),
                "rejected_BY_FDR": e.get("rejected_BY_FDR"),
            })

    # Write CSVs alongside the existing per-test trace
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "10_calderon_pooled.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "judge", "corpus", "epsilon", "m_annotators", "n_instances",
            "winning_rate_omega", "avg_advantage_rho",
            "n_rejected_BY_FDR", "passes_alt_test",
            "omega_ci95_lo_clopper", "omega_ci95_hi_clopper"])
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)
    with (OUT_DIR / "11_calderon_pooled_per_annotator.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "judge", "corpus", "grader_id", "n_j",
            "rho_f_judge_wins", "rho_h_reviewer_wins", "d_bar",
            "test", "p_value_one_sided", "rejected_BY_FDR"])
        w.writeheader()
        for r in per_ann_rows:
            w.writerow(r)

    # Console summary
    print()
    print("=" * 110)
    print("Calderon §3 alt-test on POOLED picks (30 human + 15 LLM = 45 total), ε=0.15")
    print("=" * 110)
    print(f"{'Judge':30s}  {'n':>3s}  {'ω':>5s}  {'ρ':>5s}  {'rej.':>5s}  Decision   Per-reviewer test/p")
    print("-" * 110)
    for slug, name in JUDGES:
        s = next(r for r in summary_rows if r["judge"] == name)
        s_per_ann = [r for r in per_ann_rows if r["judge"] == name]
        decision = "PASS" if s["passes_alt_test"] else "fail"
        tests = ", ".join(f"{r['test']}@n={r['n_j']}"
                          for r in s_per_ann[:2]) + ("..." if len(s_per_ann) > 2 else "")
        print(f"{name:30s}  {s['n_instances']:>3d}  "
              f"{s['winning_rate_omega']:.2f}  {s['avg_advantage_rho']:.2f}  "
              f"{s['n_rejected_BY_FDR']:>5d}  {decision:8s}   {tests}")
    print("=" * 110)
    print()
    print("Per-reviewer detail:")
    for slug, name in JUDGES:
        rows = [r for r in per_ann_rows if r["judge"] == name]
        if not rows:
            continue
        print(f"\n  {name}")
        print(f"    {'grader':10s}  {'n_j':>4s}  {'ρ^f':>5s}  {'ρ^h':>5s}  "
              f"{'d̄':>7s}  {'test':10s}  {'p':>7s}  rej?")
        for r in rows:
            star = "★" if r["rejected_BY_FDR"] else ""
            print(f"    {r['grader_id']:10s}  {r['n_j']:>4d}  "
                  f"{r['rho_f_judge_wins']:.2f}   {r['rho_h_reviewer_wins']:.2f}   "
                  f"{r['d_bar']:+.3f}  {r['test']:10s}  {r['p_value_one_sided']:.4f}  {star}")
    print()
    print(f"Saved {OUT_DIR / '10_calderon_pooled.csv'}")
    print(f"Saved {OUT_DIR / '11_calderon_pooled_per_annotator.csv'}")


if __name__ == "__main__":
    main()
