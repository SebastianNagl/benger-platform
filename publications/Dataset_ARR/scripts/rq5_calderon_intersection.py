"""Sanity check: re-run the per-judge alt-test restricted to the intersection
of picks all three Config B judges scored. This eliminates the n=28 vs n=30
asymmetry caused by Opus failing to parse on 2 picks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import (  # noqa: E402
    REAL,
    _alt_test_blind_pool,
    _build_blind_pool_inputs,
    humans_by_solution,
    load_json,
)
from derive_paper_exports import CONFIG_B_FIELD_PREFIX  # noqa: E402
from rq5_judge_calibration import index_judge_per_config  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"


def main():
    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")
    humans_h = humans_by_solution(canonical, role_filter="blind")

    inter_h = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="human")

    # Intersection of picks with non-None score from all three judges
    judges = ("gpt-5-mini", "claude-opus-4-7", "gemini-3.1-pro-preview")
    sets = [set(inter_h[j].keys()) for j in judges]
    intersection = set.intersection(*sets)
    print(f"Per-judge coverage: " + ", ".join(f"{j}={len(inter_h[j])}" for j in judges))
    print(f"Intersection across all three: {len(intersection)} picks")
    print()

    print("Calderon §3 alt-test on the intersection (same picks, ε=0.15):")
    for j in judges:
        # restrict to intersection
        by_sol = {sid: v for sid, v in inter_h[j].items() if sid in intersection}
        inputs, n_total = _build_blind_pool_inputs(by_sol, humans_h)
        payload = _alt_test_blind_pool(inputs, eps=0.15)
        payload["n_instances_total"] = n_total
        decision = "PASS" if payload["passes_alt_test"] else "fail"
        rej = sum(1 for e in payload["per_annotator"] if e["rejected_BY_FDR"])
        print(f"  {j:30s}  m={payload['m_annotators']}  n={n_total:3d}  "
              f"ω={payload['winning_rate']:.2f}  ρ={payload['avg_advantage_probability']:.2f}  "
              f"rej={rej}/{payload['m_annotators']}  {decision}")


if __name__ == "__main__":
    main()
