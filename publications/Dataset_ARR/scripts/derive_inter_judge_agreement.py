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

Correlation / MAE helpers come from scripts/_stats.py (scipy-backed).
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import mae, pearson, spearman  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
REAL_EXPORT = HERE / "data" / "raw" / "benchathon" / "Benchathon_export.json"
OUT_PATH    = HERE / "data" / "processed" / "benchathon_inter_judge_agreement.json"

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


def main() -> None:
    with REAL_EXPORT.open(encoding="utf-8") as f:
        real = json.load(f)

    by_cell: dict[str, dict[str, float]] = defaultdict(dict)
    for task in real["tasks"]:
        for gen in task.get("generations") or []:
            gid = gen["id"]
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


if __name__ == "__main__":
    main()
