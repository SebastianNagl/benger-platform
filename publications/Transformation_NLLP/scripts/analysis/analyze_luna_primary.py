#!/usr/bin/env python3
"""Does the judge-capability floor move with GPT-5.6 Luna as primary?

Compares luna (3 passes, T=1 forced — same constraint group as mini) against
gpt-5.4-mini on the identical temp-0 clone cells:

- validity vs the blind-human pool mean (first pass, mean-of-3)
- 3-pass repeat stdev
- P01 behavior (the Sachverhalt-only submission mini confabulated on)
- panel swap: within-cell SD of the 6-judge panel with luna replacing mini,
  paired against the control arm on the same cells

Inputs: judge_results_temp0.jsonl (temp-0 panel), judge_results_luna.jsonl
        (luna runs), picks_temp0.json, control_results_temp0.jsonl.
Output: data/processed/luna_primary_stats.json + console summary.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "luna_primary_stats.json"

PANEL_BASE = ("claude-opus-4-7", "claude-sonnet-4-6", "gemini-3.1-pro-preview",
              "deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.5-397B-A17B")
MINI = "gpt-5.4-mini"
LUNA = "gpt-5.6-luna"


def pearson(xs, ys):
    if len(xs) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def load_results(path):
    cells = defaultdict(lambda: defaultdict(dict))
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("total_score") is None:
            continue
        cells[r["pick_id"]][r["judge_model_id"]][int(r.get("judge_run_index") or 0)] = float(r["total_score"])
    return cells


def main() -> int:
    picks = {p["pick_id"]: p for p in json.loads((INTERIM / "picks_temp0.json").read_text())["resolved"]}
    panel_cells = load_results(INTERIM / "judge_results_temp0.jsonl")
    luna_cells = load_results(INTERIM / "judge_results_luna.jsonl")

    ctrl = defaultdict(dict)
    for line in (INTERIM / "control_results_temp0.jsonl").read_text().splitlines():
        r = json.loads(line)
        if not r["repeat_run"]:
            ctrl[r["pick_id"]][r["judge"]] = r["score"]

    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}

    def first(cells, pid, j):
        runs = cells[pid].get(j) or {}
        return runs[min(runs)] if runs else None

    def mean_runs(cells, pid, j):
        runs = cells[pid].get(j) or {}
        return statistics.mean(runs.values()) if runs else None

    ann = [p for p in picks if picks[p]["target_type"] == "annotation" and p in hmean]

    def validity(score_fn):
        pairs = [(score_fn(p), hmean[p]) for p in ann if score_fn(p) is not None]
        xs = [a for a, _ in pairs]; ys = [b for _, b in pairs]
        return {"n": len(xs), "pearson": pearson(xs, ys),
                "mae": statistics.mean(abs(a - b) for a, b in pairs) if pairs else None}

    # Repeats over all picks with 3 passes.
    def repeats(cells, judge):
        sds = [statistics.pstdev(list(cells[p][judge].values()))
               for p in cells if len(cells[p].get(judge) or {}) > 1]
        return {"n": len(sds), "mean_within_cell_stdev": statistics.mean(sds) if sds else None}

    # Panel swap: base 5 + {primary}, paired vs control (same 6 judges incl. mini
    # on control side — control has no luna, so control keeps mini; the swap
    # isolates the primary's contribution on the tailored side).
    def panel_sd(primary_cells, primary):
        rows = {}
        for pid in picks:
            vals = [first(panel_cells, pid, j) for j in PANEL_BASE]
            pv = first(primary_cells, pid, primary)
            if any(v is None for v in vals) or pv is None:
                continue
            rows[pid] = statistics.pstdev(vals + [pv])
        return rows

    mini_panel = panel_sd(panel_cells, MINI)
    luna_panel = panel_sd(luna_cells, LUNA)
    common = sorted(set(mini_panel) & set(luna_panel) & set(
        pid for pid in ctrl if all(j in ctrl[pid] for j in PANEL_BASE + (MINI,))))
    ctrl_sd = {pid: statistics.pstdev([ctrl[pid][j] for j in PANEL_BASE + (MINI,)]) for pid in common}

    payload = {
        "n_common_cells": len(common),
        "validity_annotations": {
            "mini_first_pass": validity(lambda p: first(panel_cells, p, MINI)),
            "mini_mean3": validity(lambda p: mean_runs(panel_cells, p, MINI)),
            "luna_first_pass": validity(lambda p: first(luna_cells, p, LUNA)),
            "luna_mean3": validity(lambda p: mean_runs(luna_cells, p, LUNA)),
        },
        "repeats": {"mini": repeats(panel_cells, MINI), "luna": repeats(luna_cells, LUNA)},
        "panel_within_cell_sd_mean": {
            "control_mini_panel": statistics.mean([ctrl_sd[p] for p in common]),
            "tailored_mini_panel": statistics.mean([mini_panel[p] for p in common]),
            "tailored_luna_panel": statistics.mean([luna_panel[p] for p in common]),
        },
        "p01": {
            "mini_runs": panel_cells.get("P01", {}).get(MINI),
            "luna_runs": luna_cells.get("P01", {}).get(LUNA),
            "flagships": {j: first(panel_cells, "P01", j) for j in PANEL_BASE},
        },
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
