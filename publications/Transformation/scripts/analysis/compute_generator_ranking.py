#!/usr/bin/env python3
"""Formalize the generator ranking blocks of generator_outcomes.json (WP3.4).

The paired_dmae, sonnet_lens.luna_sonnet_spread and lens_ranking_spearman
values were produced ad hoc (no committed script — commit d0336c6 touched
only the JSON). This script recomputes all three from the tidy cell dumps,
asserts equality with the stored values, and adds what the reviewer asked
for: a rank-stability bootstrap (exam-level clusters) and a split ranking —
full-coverage generators (15/15 schema-conformant rubrics) vs the
conditional-coverage ones (gpt-5.4-mini 8/15, Llama-4 12/15), whose
quality-when-valid is a survivorship-conditional observation.

Inputs: data/interim/crossed_cells.{luna,sonnet}.jsonl (analyze_crossed.py),
        picks_temp0.json, Benchmark_EMNLP human pool,
        data/processed/generator_outcomes.json (assert + read-modify-write)
Output: generator_outcomes.json (adds "ranking", refreshes formalized blocks)
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "generator_outcomes.json"

SEED = 20260806
N_BOOT = 10_000


def load_cells(lens):
    cells = []
    for line in (INTERIM / f"crossed_cells.{lens}.jsonl").read_text().splitlines():
        r = json.loads(line)
        runs = {int(k): v for k, v in r["runs"].items()}
        r["first"] = runs[min(runs)]
        cells.append(r)
    return cells


def main() -> int:
    picks = {p["pick_id"]: p for p in json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]}
    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}

    luna = load_cells("luna")
    sonnet = load_cells("sonnet")

    def ann_err_cells(cells):
        out = []
        for c in cells:
            p = picks.get(c["pick_id"])
            if p and p["target_type"] == "annotation" and c["pick_id"] in hmean:
                out.append({**c, "err": abs(c["first"] - hmean[c["pick_id"]])})
        return out

    luna_err = ann_err_cells(luna)

    def compute_paired_dmae(err_cells):
        by_pick = defaultdict(list)
        for c in err_cells:
            by_pick[c["pick_id"]].append(c["err"])
        pick_mean = {pid: statistics.mean(v) for pid, v in by_pick.items()}
        contrib = defaultdict(list)
        for c in err_cells:
            contrib[c["generator_model_id"]].append(c["err"] - pick_mean[c["pick_id"]])
        return {g: statistics.mean(v) for g, v in contrib.items()}

    paired_dmae = compute_paired_dmae(luna_err)

    stored = json.loads(OUT.read_text())
    for g, want in (stored.get("paired_dmae") or {}).items():
        got = paired_dmae[g]
        assert abs(got - want) < 0.011, f"paired_dmae mismatch {g}: stored {want} vs {got}"
    print(f"paired_dmae reproduces for {len(paired_dmae)} generators (±0.01)")

    # luna_sonnet_spread: mean |luna first − sonnet first| on identical cells.
    s_first = {(c["rubric_id"], c["pick_id"]): c["first"] for c in sonnet}
    spread_pairs = defaultdict(list)
    for c in luna:
        key = (c["rubric_id"], c["pick_id"])
        if key in s_first:
            spread_pairs[c["generator_model_id"]].append(abs(c["first"] - s_first[key]))
    spreads = {g: statistics.mean(v) for g, v in spread_pairs.items()}
    for g, entry in (stored.get("sonnet_lens") or {}).items():
        want = entry.get("luna_sonnet_spread")
        if want is not None:
            assert abs(spreads[g] - want) < 0.051, f"spread mismatch {g}: {want} vs {spreads[g]}"
    print("luna_sonnet_spread reproduces (±0.05)")

    # lens_ranking_spearman: spearman of the UNROUNDED per-generator MAE
    # under both lenses (identified against the stored ad-hoc value — the
    # rounded stored MAEs give .522 via rank ties, the unrounded means .503).
    gens = sorted(paired_dmae)
    per_gen = stored.get("per_generator") or {}
    sonnet_err = ann_err_cells(sonnet)

    def mae_per_gen(err_cells):
        by_gen = defaultdict(list)
        for c in err_cells:
            by_gen[c["generator_model_id"]].append(c["err"])
        return {g: statistics.mean(v) for g, v in by_gen.items()}

    luna_mae, sonnet_mae = mae_per_gen(luna_err), mae_per_gen(sonnet_err)
    rho_all = round(float(sps.spearmanr([luna_mae[g] for g in gens],
                                        [sonnet_mae[g] for g in gens]).statistic), 3)
    full_cov = [g for g in gens if per_gen[g]["n_rubrics"] == 15]
    rho_full = round(float(sps.spearmanr([luna_mae[g] for g in full_cov],
                                         [sonnet_mae[g] for g in full_cov]).statistic), 3)
    rho_stored = stored.get("lens_ranking_spearman")
    assert rho_stored is None or abs(rho_all - rho_stored) < 0.0011, (
        f"lens_ranking_spearman mismatch: stored {rho_stored} vs {rho_all}")
    print(f"lens_ranking_spearman reproduces: {rho_all} "
          f"(full-coverage generators only: {rho_full})")

    # Rank-stability bootstrap on paired_dmae (exam clusters).
    by_exam = defaultdict(list)
    for c in luna_err:
        by_exam[c["task_id"]].append(c)
    exams = sorted(by_exam)
    rng = np.random.default_rng(SEED)
    ranks = defaultdict(list)
    tops = defaultdict(lambda: [0, 0])  # [top1, top3]
    for _ in range(N_BOOT):
        draw = rng.integers(0, len(exams), size=len(exams))
        cells = [c for e in draw for c in by_exam[exams[e]]]
        dm = compute_paired_dmae(cells)
        order = sorted(dm, key=lambda g: dm[g])
        for i, g in enumerate(order):
            ranks[g].append(i + 1)
            if i == 0:
                tops[g][0] += 1
            if i < 3:
                tops[g][1] += 1
    stability = {}
    for g in gens:
        r = ranks[g]
        stability[g] = {
            "n_boot_present": len(r),
            "median_rank": float(np.median(r)),
            "rank_ci95": [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))],
            "p_top1": tops[g][0] / N_BOOT,
            "p_top3": tops[g][1] / N_BOOT,
        }

    n_rubrics = {g: per_gen[g]["n_rubrics"] for g in gens}
    main_rank = sorted((g for g in gens if n_rubrics[g] == 15), key=lambda g: paired_dmae[g])
    cond_rank = sorted((g for g in gens if n_rubrics[g] < 15), key=lambda g: paired_dmae[g])

    stored["paired_dmae"] = {g: round(v, 3) for g, v in paired_dmae.items()}
    stored["lens_ranking_spearman"] = rho_all
    stored["lens_ranking_spearman_basis"] = "spearman of unrounded per-generator MAE, both lenses"
    stored["lens_ranking_spearman_full_coverage"] = rho_full
    for g in spreads:
        stored["sonnet_lens"].setdefault(g, {})["luna_sonnet_spread"] = round(spreads[g], 1)
    stored["ranking"] = {
        "note": "paired_dmae = per-(rubric,pick) |Luna first pass − human mean| minus the "
                "pick's cross-source mean, averaged per generator; main = full-coverage "
                "generators (15/15 schema-conformant rubrics); conditional = incomplete "
                "coverage, quality-when-valid only (survivorship-conditional)",
        "seed": SEED, "n_boot": N_BOOT,
        "main": [{"generator": g, "paired_dmae": round(paired_dmae[g], 2), **stability[g]}
                 for g in main_rank],
        "conditional": [{"generator": g, "n_rubrics": n_rubrics[g],
                         "paired_dmae": round(paired_dmae[g], 2), **stability[g]}
                        for g in cond_rank],
    }
    OUT.write_text(json.dumps(stored, indent=1, ensure_ascii=False), encoding="utf-8")

    print("\nmain ranking (15/15 coverage):")
    for row in stored["ranking"]["main"]:
        print(f"  {row['generator']:45s} dMAE {row['paired_dmae']:+5.2f} "
              f"median rank {row['median_rank']:4.1f} CI {row['rank_ci95']} "
              f"p_top3 {row['p_top3']:.2f}")
    print("conditional (incomplete coverage):")
    for row in stored["ranking"]["conditional"]:
        print(f"  {row['generator']:45s} ({row['n_rubrics']}/15) dMAE {row['paired_dmae']:+5.2f} "
              f"median rank {row['median_rank']:4.1f} CI {row['rank_ci95']} "
              f"p_top1 {row['p_top1']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
