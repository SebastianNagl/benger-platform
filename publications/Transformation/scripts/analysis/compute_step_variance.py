#!/usr/bin/env python3
"""Where does repeat variance live inside a tailored rubric?

For every judge with at least three passes on a cell, the per-step score
variance across passes is summed by step size (the step's apportioned
maximum) and compared with the share of points in that size class, and
with the share of SQUARED maxima: if every step had the same relative noise
(SD proportional to its maximum), a size class would hold exactly that share
of the variance, so only a share above it means big steps are noisier per
point. The mean relative SD (SD / maximum) per class tests this directly. Also
reported: the partial-credit rate (score strictly between 0 and max) and,
for steps of at least 6 points, the SD relative to the maximum split by the
widest partial-credit band of the step (< 4 vs >= 4 points), which tests
whether wide bands, rather than big steps, drive the variance.

Inputs: judge_results_luna.jsonl, tailored_repeats_flagships.jsonl,
        judge_results_temp0.jsonl, clone_d6_actives.json,
        data/raw/local/task_rubrics.json (all withheld).
Output: data/processed/step_variance.json
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
RAW = HERE / "data" / "raw" / "local" / "task_rubrics.json"
OUT = HERE / "data" / "processed" / "step_variance.json"
FILES = ("judge_results_luna.jsonl", "tailored_repeats_flagships.jsonl",
         "judge_results_temp0.jsonl")
BUCKETS = ((2, "1-2"), (5, "3-5"), (9, "6-9"), (14, "10-14"), (10 ** 6, "15+"))


def bucket(points):
    return next(label for upper, label in BUCKETS if points <= upper)


def band_widths():
    """criteria key set -> {key: widest band width in points}."""
    out = {}
    for r in json.loads(RAW.read_text()):
        gm = r.get("generation_metadata") or {}
        if not gm.get("derived_document"):
            continue
        derived = {s["id"]: s for a in gm["derived_document"]["abschnitte"] for s in a["schritte"]}
        widths = {}
        for sid, key in gm["key_by_step_id"].items():
            bands = (derived.get(sid) or {}).get("bewertungshinweise", {}).get("teilpunktstufen") or []
            widths[key] = max([b["bis"] - b["von"] + 1 for b in bands] or [0])
        out[frozenset(r["criteria"])] = widths
    return out


def main() -> int:
    actives = json.loads((INTERIM / "clone_d6_actives.json").read_text())
    widths = band_widths()
    cells = defaultdict(dict)
    for name in FILES:
        for line in (INTERIM / name).read_text().splitlines():
            row = json.loads(line)
            if not row.get("scores") or row.get("error") or actives.get(row["task_id"]) != row["rubric_id"]:
                continue
            key = (row["judge_model_id"], row["pick_id"])
            run = int(row.get("judge_run_index") or 0)
            if key not in cells or run not in cells[key] or row["created_at"] > cells[key][run]["created_at"]:
                cells[key][run] = row

    result = {}
    for judge in sorted({j for j, _ in cells}):
        var, pts, n_steps, partial, n_scores = Counter(), Counter(), Counter(), Counter(), Counter()
        sq_pts = Counter()
        rel_by_bucket = defaultdict(list)
        rel_sd = defaultdict(list)
        n_cells = 0
        for (j, _pick), runs in cells.items():
            if j != judge or len(runs) < 3:
                continue
            n_cells += 1
            rows = list(runs.values())
            bw = widths.get(frozenset(rows[0]["scores"]), {})
            for key, first in rows[0]["scores"].items():
                vals = [float(r["scores"][key]["score"]) for r in rows if key in r["scores"]]
                if len(vals) < 3:
                    continue
                mx = float(first["max"])
                b = bucket(mx)
                var[b] += statistics.pvariance(vals)
                pts[b] += mx
                sq_pts[b] += mx * mx
                rel_by_bucket[b].append(statistics.pstdev(vals) / mx)
                n_steps[b] += 1
                n_scores[b] += len(vals)
                partial[b] += sum(1 for v in vals if 0 < v < mx)
                if mx >= 6:
                    rel_sd["widest_band_ge4" if bw.get(key, 0) >= 4 else "widest_band_lt4"].append(
                        statistics.pstdev(vals) / mx)
        if not n_cells:
            continue
        tv, tp, tsq = sum(var.values()), sum(pts.values()), sum(sq_pts.values())
        result[judge] = {
            "n_cells": n_cells,
            "by_step_size": {
                label: {"share_of_points": round(pts[label] / tp, 4),
                        "share_of_variance": round(var[label] / tv, 4) if tv else None,
                        "share_of_squared_maxima": round(sq_pts[label] / tsq, 4),
                        "mean_relative_sd": round(statistics.mean(rel_by_bucket[label]), 4),
                        "partial_credit_rate": round(partial[label] / n_scores[label], 4),
                        "n_step_cells": n_steps[label]}
                for _, label in BUCKETS if n_steps[label]},
            "relative_sd_steps_ge6": {k: {"mean": round(statistics.mean(v), 4), "n": len(v)}
                                      for k, v in sorted(rel_sd.items())},
        }

    OUT.write_text(json.dumps({"note": "Per-step repeat variance by step size (>=3 passes per cell).",
                               "per_judge": result}, indent=1) + "\n")
    for judge, res in result.items():
        print(f"== {judge} ({res['n_cells']} cells)")
        for label, m in res["by_step_size"].items():
            print(f"  max {label:5s} points {m['share_of_points']:6.1%}  squared {m['share_of_squared_maxima']:6.1%}  "
                  f"variance {m['share_of_variance']:6.1%}  rel SD {m['mean_relative_sd']:.3f}  "
                  f"partial credit {m['partial_credit_rate']:6.1%}")
        for k, m in res["relative_sd_steps_ge6"].items():
            print(f"  steps >= 6 pts, {k}: SD/max {m['mean']:.3f} (n={m['n']})")
    print(f"-> {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
