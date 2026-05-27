"""Inter-judge agreement on Config B (gpt-5-mini + opus + gemini × 1 pass each).

Reads the 2026-05-23 Benchathon export, filters to Config B
(`llm_judge_falloesung-mpe7o02k-yrio`), groups by (generation_id, judge_model),
and emits per-cell triplet stats + pairwise correlations.

Output: data/processed/benchathon_inter_judge_agreement.json
{
  "n_cells_with_triplets": int,
  "judges": ["gpt-5-mini", "claude-opus-4-7", "gemini-3.1-pro-preview"],
  "per_judge_stats": {judge: {mean, stdev, n}},
  "pairwise": {"<j1>__<j2>": {pearson_r, spearman_rho, mae, n}},
  "within_cell_spread": {mean, median, min, max},
  "within_cell_stdev":  {mean, median, min, max},
}

Stdlib only.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REAL_EXPORT = HERE / "data" / "raw" / "benchathon" / "Benchathon-tasks-2026-05-23.json"
OUT_PATH    = HERE / "data" / "processed" / "benchathon_inter_judge_agreement.json"

CONFIG_B_FIELD_PREFIX = "llm_judge_falloesung-mpe7o02k-yrio"
JUDGES = ("gpt-5-mini", "claude-opus-4-7", "gemini-3.1-pro-preview")


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx2 = sum((x - mx) ** 2 for x in xs)
    dy2 = sum((y - my) ** 2 for y in ys)
    den = math.sqrt(dx2 * dy2)
    return num / den if den else None


def spearman(xs, ys):
    def _ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        ranks = [0.0] * len(vs)
        i = 0
        while i < len(vs):
            j = i
            while j + 1 < len(vs) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks
    return pearson(_ranks(xs), _ranks(ys))


def main() -> None:
    with REAL_EXPORT.open(encoding="utf-8") as f:
        real = json.load(f)

    by_cell: dict[str, dict[str, float]] = defaultdict(dict)
    for task in real["tasks"]:
        for gen in task.get("generations") or []:
            gid = gen["id"]
            for ev in gen.get("evaluations") or []:
                fn = str(ev.get("field_name") or "")
                if not fn.startswith(CONFIG_B_FIELD_PREFIX):
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

    triplets = {gid: scores for gid, scores in by_cell.items()
                if all(j in scores for j in JUDGES)}

    per_judge: dict[str, dict] = {}
    for j in JUDGES:
        vals = [s[j] for s in triplets.values()]
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
            xs = [s[j1] for s in triplets.values()]
            ys = [s[j2] for s in triplets.values()]
            mae = (sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)) if xs else None
            pairwise[f"{j1}__{j2}"] = {
                "n": len(xs),
                "pearson_r": pearson(xs, ys),
                "spearman_rho": spearman(xs, ys),
                "mae": mae,
            }

    spreads = []
    stdevs = []
    for s in triplets.values():
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
        "n_cells_with_triplets": len(triplets),
        "judges": list(JUDGES),
        "per_judge_stats": per_judge,
        "pairwise": pairwise,
        "within_cell_spread": _agg(spreads),
        "within_cell_stdev": _agg(stdevs),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT_PATH.name} (n_cells={len(triplets)}, judges={list(JUDGES)})")


if __name__ == "__main__":
    main()
