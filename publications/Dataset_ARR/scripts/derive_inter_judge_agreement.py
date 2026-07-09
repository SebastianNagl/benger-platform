"""Inter-judge agreement across 7 judges on the Benchathon LLM generations.

The 2026-05-21 Config B run scored each generation with three judges
(gpt-5-mini, claude-opus-4-7, gemini-3.1-pro-preview); 2026-05-31 follow-ups
added four standalone judges (DeepSeek-V4-Pro, Qwen3.5-397B-A17B,
claude-sonnet-4-6, gpt-5.4-mini) under their own field-name prefixes. This
script reads each generation's evaluations, joins scores by
(generation_id, judge_model) across all judges, and emits per-cell stats +
pairwise correlations.

Output: data/processed/benchathon_inter_judge_agreement.json
{
  "n_cells_with_all_judges": int,    # intersection across all 7
  "n_cells_with_triplets":   int,    # intersection across original 3 (Config B)
  "judges": ["gpt-5-mini", "claude-opus-4-7", "gemini-3.1-pro-preview",
             "claude-sonnet-4-6", "gpt-5.4-mini",
             "deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.5-397B-A17B"],
  "per_judge_stats": {judge: {mean, stdev, n}},
  "pairwise": {"<j1>__<j2>": {pearson_r, spearman_rho, mae, n}},
  "within_cell_spread": {mean, median, min, max},
  "within_cell_stdev":  {mean, median, min, max},
}

Additionally writes the judge-swapped leaderboard view of the same subset:
data/processed/benchathon_judge_swap.json
{
  "coverage": {system_id: n_generations_in_cross_judge_subset},
  "per_judge_per_system": {judge: {system_id: {n, mean_raw, pass_rate}}},
  "system_rank_agreement": {judge: {spearman_rho, kendall_tau, n_systems}},
  "pass_rate_offset_corrected": {judge: {system_id: pass_rate}},
  "_meta": {description, primary_judge, offset_source, notes},
}
All judges (the primary included) are restricted to the identical cell subset,
so per-system comparisons are like-for-like. Rank agreement compares each
judge's per-system mean_raw ordering against the primary judge's. The
offset-corrected pass rates shift each judge's per-generation scores by that
judge's direct judge-minus-pool mean offset vs the blind human pool
(judge_calibration.json) before applying the pass threshold.

Correlation / MAE helpers come from scripts/_stats.py (scipy-backed).
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import kendall_tau, mae, pearson, spearman  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
REAL_EXPORT = HERE / "data" / "raw" / "benchathon" / "Benchathon_export.json"
OUT_PATH    = HERE / "data" / "processed" / "benchathon_inter_judge_agreement.json"
SYSTEMS_PATH     = HERE / "data" / "processed" / "systems.json"
CALIBRATION_PATH = HERE / "data" / "processed" / "judge_calibration.json"
SWAP_OUT_PATH    = HERE / "data" / "processed" / "benchathon_judge_swap.json"

CONFIG_B_FIELD_PREFIX  = "llm_judge_falloesung-mpe7o02k-yrio"
DEEPSEEK_FIELD_PREFIX  = "llm_judge_falloesung-mpss5bx5-tt9n"
QWEN_FIELD_PREFIX      = "llm_judge_falloesung-mpss68ie-xip5"
SONNET_FIELD_PREFIX    = "llm_judge_falloesung-mptmf5x5-iynm"
GPT54MINI_FIELD_PREFIX = "llm_judge_falloesung-mptmfvee-sqyx"
ACCEPTED_PREFIXES = (CONFIG_B_FIELD_PREFIX, DEEPSEEK_FIELD_PREFIX, QWEN_FIELD_PREFIX,
                     SONNET_FIELD_PREFIX, GPT54MINI_FIELD_PREFIX)

# Stable display order: primary judge first, then closed cross-validation
# judges, open-weight last. The legacy GPT-5-mini scoring is excluded from
# this six-judge inter-judge analysis.
JUDGES = (
    "gpt-5.4-mini",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "gemini-3.1-pro-preview",
    "deepseek-ai/DeepSeek-V4-Pro",
    "Qwen/Qwen3.5-397B-A17B",
)
ORIGINAL_TRIPLET = ("gpt-5.4-mini", "claude-opus-4-7", "gemini-3.1-pro-preview")

# --- Judge-swapped leaderboard (benchathon_judge_swap.json) -----------------
PRIMARY_JUDGE = "gpt-5.4-mini"
PASS_THRESHOLD = 50.0  # raw >= 50 counts as a pass ("ausreichend")

# judge_model -> label of the matching row in judge_calibration.json. The
# "(LLM)" rows carry the direct judge-minus-pool offset measured on LLM
# generations, which is what the swap subset consists of; the "(human)" rows
# (offsets measured on human-written solutions) are the deliberately unused
# alternative.
CALIBRATION_LABELS = {
    "gpt-5.4-mini":                "Baseline single-pass GPT-5.4-mini  (LLM)",
    "claude-opus-4-7":             "Config B Opus-4.7  (LLM)",
    "claude-sonnet-4-6":           "Sonnet-4.6  (LLM)",
    "gemini-3.1-pro-preview":      "Config B Gemini-3.1-Pro  (LLM)",
    "deepseek-ai/DeepSeek-V4-Pro": "DeepSeek-V4-Pro  (LLM)",
    "Qwen/Qwen3.5-397B-A17B":      "Qwen3.5-397B-A17B  (LLM)",
}


def write_judge_swap(all_judge_cells: dict[str, dict[str, float]],
                     gid_model: dict[str, str]) -> None:
    """Emit the judge-swapped leaderboard view of the all-judges subset.

    Every judge (primary included) is evaluated on the identical set of
    generations, grouped by the canonical system id from systems.json.
    Generations from off-leaderboard models (raw model_ids without a
    systems.json entry) are excluded and reported in _meta.
    """
    with SYSTEMS_PATH.open(encoding="utf-8") as f:
        systems = json.load(f)
    raw_to_system = {raw: s["model_id"] for s in systems
                     for raw in s["raw_model_ids"]}

    with CALIBRATION_PATH.open(encoding="utf-8") as f:
        calibration = json.load(f)
    cal_by_label = {row["label"]: row for row in calibration}
    offsets = {j: float(cal_by_label[lbl]["judge_minus_pool_mean"])
               for j, lbl in CALIBRATION_LABELS.items()}

    by_system: dict[str, list[str]] = defaultdict(list)
    excluded: Counter[str] = Counter()
    for gid in all_judge_cells:
        system = raw_to_system.get(gid_model.get(gid))
        if system is None:
            excluded[str(gid_model.get(gid))] += 1
            continue
        by_system[system].append(gid)

    system_ids = sorted(by_system)
    coverage = {s: len(by_system[s]) for s in system_ids}

    per_judge_per_system: dict[str, dict] = {}
    pass_rate_corrected: dict[str, dict] = {}
    for j in JUDGES:
        per_sys, corrected = {}, {}
        for s in system_ids:
            vals = [all_judge_cells[g][j] for g in by_system[s]]
            per_sys[s] = {
                "n": len(vals),
                "mean_raw": statistics.mean(vals),
                "pass_rate": sum(v >= PASS_THRESHOLD for v in vals) / len(vals),
            }
            corrected[s] = (sum(v - offsets[j] >= PASS_THRESHOLD for v in vals)
                            / len(vals))
        per_judge_per_system[j] = per_sys
        pass_rate_corrected[j] = corrected

    primary_means = [per_judge_per_system[PRIMARY_JUDGE][s]["mean_raw"]
                     for s in system_ids]
    rank_agreement = {}
    for j in JUDGES:
        means = [per_judge_per_system[j][s]["mean_raw"] for s in system_ids]
        rank_agreement[j] = {
            "spearman_rho": spearman(means, primary_means),
            "kendall_tau": kendall_tau(means, primary_means),
            "n_systems": len(system_ids),
        }

    payload = {
        "coverage": coverage,
        "per_judge_per_system": per_judge_per_system,
        "system_rank_agreement": rank_agreement,
        "pass_rate_offset_corrected": pass_rate_corrected,
        "_meta": {
            "description": (
                "Judge-swapped Benchathon leaderboard: per-judge per-system "
                "stats on the subset of generations scored by ALL six judges, "
                "so every judge (the primary gpt-5.4-mini included) is "
                "compared on identical cells. pass = raw_score >= "
                f"{PASS_THRESHOLD:g}. system_rank_agreement correlates each "
                "judge's per-system mean_raw with the primary judge's on the "
                "same subset (scipy spearmanr / kendalltau tau-b; the primary "
                "judge's row is the trivial self-comparison). "
                "pass_rate_offset_corrected applies "
                "corrected = raw - judge_minus_pool_mean before the threshold."
            ),
            "primary_judge": PRIMARY_JUDGE,
            "offset_source": {
                "file": "data/processed/judge_calibration.json",
                "field": "judge_minus_pool_mean",
                "calibration_labels": dict(CALIBRATION_LABELS),
                "offsets": offsets,
                "choice": (
                    "Direct judge-minus-blind-human-pool mean offset (judge "
                    "minus mean of 3 blind raters), from the '(LLM)' "
                    "calibration rows (n=15 LLM generations) rather than the "
                    "'(human)' rows, because the swap subset consists of LLM "
                    "generations."
                ),
            },
            "notes": [
                "Subset = the n_cells_with_all_judges intersection from "
                "benchathon_inter_judge_agreement.json (258 generations).",
                "Excluded off-leaderboard generations (raw model_id not in "
                f"systems.json): {dict(sorted(excluded.items()))}.",
                "Per-judge n equals coverage for every judge by construction "
                "(the subset requires all six judges per cell).",
                "Kendall tau is tau-b, which handles tied per-system means.",
            ],
        },
    }

    SWAP_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SWAP_OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    n_covered = sum(coverage.values())
    print(f"wrote {SWAP_OUT_PATH.name} "
          f"(systems={len(system_ids)}, cells={n_covered}, "
          f"excluded={sum(excluded.values())})")

    print()
    print(f"system rank agreement vs {PRIMARY_JUDGE} "
          f"(per-system mean_raw, n_systems={len(system_ids)}):")
    for j in JUDGES:
        if j == PRIMARY_JUDGE:
            continue
        ra = rank_agreement[j]
        print(f"  {j:35s}  ρ={ra['spearman_rho']:.3f}  "
              f"τ={ra['kendall_tau']:.3f}")


def main() -> None:
    with REAL_EXPORT.open(encoding="utf-8") as f:
        real = json.load(f)

    by_cell: dict[str, dict[str, float]] = defaultdict(dict)
    gid_model: dict[str, str] = {}
    for task in real["tasks"]:
        for gen in task.get("generations") or []:
            gid = gen["id"]
            gid_model[gid] = gen.get("model_id")
            for ev in gen.get("evaluations") or []:
                fn = str(ev.get("field_name") or "")
                if not fn.startswith(ACCEPTED_PREFIXES):
                    continue
                judge = ev.get("judge_model")
                if judge not in JUDGES:
                    continue
                kf = (ev.get("metrics") or {}).get("llm_judge_falloesung")
                if not isinstance(kf, dict):
                    continue
                raw = (kf.get("details") or {}).get("raw_score", kf.get("value"))
                if raw is None:
                    continue
                by_cell[gid][judge] = float(raw)

    all_judge_cells = {gid: scores for gid, scores in by_cell.items()
                   if all(j in scores for j in JUDGES)}
    triplets    = {gid: scores for gid, scores in by_cell.items()
                   if all(j in scores for j in ORIGINAL_TRIPLET)}

    per_judge: dict[str, dict] = {}
    for j in JUDGES:
        vals = [s[j] for s in all_judge_cells.values()]
        per_judge[j] = {
            "n": len(vals),
            "mean": statistics.mean(vals) if vals else None,
            "stdev": statistics.pstdev(vals) if len(vals) > 1 else None,
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
        }

    pairwise: dict[str, dict] = {}
    for i, j1 in enumerate(JUDGES):
        for j2 in JUDGES[i + 1:]:
            xs = [s[j1] for s in all_judge_cells.values()]
            ys = [s[j2] for s in all_judge_cells.values()]
            pairwise[f"{j1}__{j2}"] = {
                "n": len(xs),
                "pearson_r": pearson(xs, ys),
                "spearman_rho": spearman(xs, ys),
                "mae": mae(xs, ys),
            }

    spreads, stdevs = [], []
    for s in all_judge_cells.values():
        vs = [s[j] for j in JUDGES]
        spreads.append(max(vs) - min(vs))
        stdevs.append(statistics.pstdev(vs))

    def _agg(xs):
        return {
            "n": len(xs),
            "mean": statistics.mean(xs) if xs else None,
            "median": statistics.median(xs) if xs else None,
            "min": min(xs) if xs else None,
            "max": max(xs) if xs else None,
        }

    payload = {
        "n_cells_with_all_judges": len(all_judge_cells),
        "n_cells_with_triplets":   len(triplets),
        "judges": list(JUDGES),
        "per_judge_stats": per_judge,
        "pairwise": pairwise,
        "within_cell_spread": _agg(spreads),
        "within_cell_stdev": _agg(stdevs),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT_PATH.name} "
          f"(all_judge_cells={len(all_judge_cells)}, triplets={len(triplets)})")

    # Compact console summary so the operator can read off Spearman ρ.
    print()
    print(f"per-judge means (n={len(all_judge_cells)}):")
    for j in JUDGES:
        s = per_judge[j]
        print(f"  {j:35s}  mean={s['mean']:6.2f}  sd={s['stdev']:5.2f}")
    print()
    print("pairwise Spearman ρ:")
    for key, p in pairwise.items():
        j1, j2 = key.split("__")
        print(f"  {j1[:25]:25s} ↔ {j2[:25]:25s}  ρ={p['spearman_rho']:.3f}  "
              f"r={p['pearson_r']:.3f}  MAE={p['mae']:.2f}")

    print()
    write_judge_swap(all_judge_cells, gid_model)


if __name__ == "__main__":
    main()
