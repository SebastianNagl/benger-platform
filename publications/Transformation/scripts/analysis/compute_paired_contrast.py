#!/usr/bin/env python3
"""Paired RQ2 contrast: control vs tailored arm on the IDENTICAL 45 picks.

The control arm's published within-cell stdev (7.93) averages over all 258
generations; the tailored arm judges only the 45 dataset-paper picks. The
like-for-like contrast restricts BOTH arms to the same cells and pairs them:
per pick, within-cell stdev/spread across the identical 6-judge panel, then
the paired difference (tailored - control) with a sign test.

Control scores come from the imported Benchathon judge rows in the local DB
(field prefixes = the five accepted runs of the dataset paper's
derive_inter_judge_agreement.py; judge attribution via
evaluation_judge_runs). Repeats: the control 3-pass run used gpt-5-mini
(the tailored arm's primary is gpt-5.4-mini) — reported with that caveat.

Inputs: data/interim/picks.json, judge_results.jsonl, local DB.
Output: control_on_picks + paired_contrast blocks in
        data/processed/variance_stats.json; control rows dumped to
        data/interim/control_results.jsonl for reproducibility.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
PICKS = HERE / "data" / "interim" / "picks.json"
TAILORED = HERE / "data" / "interim" / "judge_results.jsonl"
CONTROL_OUT = HERE / "data" / "interim" / "control_results.jsonl"
STATS = HERE / "data" / "processed" / "variance_stats.json"

# Field prefix -> judge attribution rule. Config B (mpe7o02k) carries three
# judges split by judge_run; the standalone runs are single-judge.
ACCEPTED_PREFIXES = (
    "llm_judge_falloesung-mpe7o02k-yrio",   # Config B: gpt-5-mini/opus/gemini
    "llm_judge_falloesung-mpss5bx5-tt9n",   # DeepSeek-V4-Pro
    "llm_judge_falloesung-mpss68ie-xip5",   # Qwen3.5-397B
    "llm_judge_falloesung-mptmf5x5-iynm",   # sonnet
    "llm_judge_falloesung-mptmfvee-sqyx",   # gpt-5.4-mini single pass
)
REPEAT_PREFIX = "llm_judge_falloesung-mpe7mkzx-2zp6"  # gpt-5-mini x3
JUDGES = (
    "gpt-5.4-mini",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "gemini-3.1-pro-preview",
    "deepseek-ai/DeepSeek-V4-Pro",
    "Qwen/Qwen3.5-397B-A17B",
)
PRIMARY = "gpt-5.4-mini"


def _psql_json(query: str):
    out = subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-tAc", f"select coalesce(json_agg(t), '[]') from ({query}) t;"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return json.loads(out)


def _agg(xs):
    return {
        "n": len(xs),
        "mean": statistics.mean(xs) if xs else None,
        "median": statistics.median(xs) if xs else None,
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--picks", default=str(PICKS))
    parser.add_argument("--results", default=str(TAILORED))
    parser.add_argument("--control-out", default=str(CONTROL_OUT))
    parser.add_argument("--block", default="paired_contrast")
    args = parser.parse_args()

    picks = json.loads(Path(args.picks).read_text(encoding="utf-8"))["resolved"]
    by_target = {p["target_id"]: p for p in picks}
    id_list = "','".join(by_target)
    prefix_like = " or ".join(
        f"te.field_name like '{p}%'" for p in ACCEPTED_PREFIXES + (REPEAT_PREFIX,)
    )
    rows = _psql_json(
        "select te.generation_id, te.annotation_id, te.field_name, "
        "ejr.judge_model_id, ejr.run_index, "
        "te.metrics->'llm_judge_falloesung'->'details'->>'raw_score' as raw_score, "
        "te.metrics->'llm_judge_falloesung'->>'value' as value "
        "from task_evaluations te "
        "left join evaluation_judge_runs ejr on te.judge_run_id = ejr.id "
        f"where ({prefix_like}) and (te.generation_id in ('{id_list}') "
        f"or te.annotation_id in ('{id_list}'))"
    )

    control_cells: dict[str, dict[str, float]] = defaultdict(dict)
    control_repeats: dict[str, list[float]] = defaultdict(list)
    with Path(args.control_out).open("w", encoding="utf-8") as fh:
        for r in rows:
            target = r.get("generation_id") or r.get("annotation_id")
            pick = by_target.get(target)
            if pick is None:
                continue
            raw = r.get("raw_score")
            score = float(raw) if raw is not None else (
                float(r["value"]) * 100 if r.get("value") is not None else None
            )
            if score is None:
                continue
            judge = r.get("judge_model_id")
            is_repeat = r["field_name"].startswith(REPEAT_PREFIX)
            fh.write(json.dumps({
                "pick_id": pick["pick_id"], "judge": judge,
                "run_index": r.get("run_index"), "score": score,
                "repeat_run": is_repeat,
            }) + "\n")
            if is_repeat:
                control_repeats[pick["pick_id"]].append(score)
            elif judge in JUDGES:
                control_cells[pick["pick_id"]][judge] = score

    # Tailored per-pick scores (same convention as compute_tailored_variance).
    tailored_cells: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    for line in Path(args.results).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("total_score") is None:
            continue
        tailored_cells[r["pick_id"]][r["judge_model_id"]][int(r.get("judge_run_index") or 0)] = float(r["total_score"])

    def tailored_score(pid, j):
        runs = tailored_cells[pid].get(j) or {}
        if not runs:
            return None
        return runs[min(runs)] if j == PRIMARY else list(runs.values())[0]

    paired = []
    for pid in sorted({p["pick_id"] for p in picks}):
        c = control_cells.get(pid) or {}
        if not all(j in c for j in JUDGES):
            continue
        t = {j: tailored_score(pid, j) for j in JUDGES}
        if any(v is None for v in t.values()):
            continue
        meta = next(p for p in picks if p["pick_id"] == pid)
        paired.append({
            "pick_id": pid,
            "target_type": meta["target_type"],
            "provenance": meta["provenance"],
            "control_stdev": statistics.pstdev(c.values()),
            "control_spread": max(c.values()) - min(c.values()),
            "tailored_stdev": statistics.pstdev(t.values()),
            "tailored_spread": max(t.values()) - min(t.values()),
        })

    diffs = [p["tailored_stdev"] - p["control_stdev"] for p in paired]
    neg = sum(1 for d in diffs if d < 0)  # tailored LOWER variance
    pos = sum(1 for d in diffs if d > 0)

    control_sd = [p["control_stdev"] for p in paired]
    tailored_sd = [p["tailored_stdev"] for p in paired]
    rep_sds = [statistics.pstdev(v) for v in control_repeats.values() if len(v) > 1]

    def by(key, val):
        sub = [p for p in paired if p[key] == val]
        return {
            "n": len(sub),
            "control_stdev_mean": statistics.mean([p["control_stdev"] for p in sub]) if sub else None,
            "tailored_stdev_mean": statistics.mean([p["tailored_stdev"] for p in sub]) if sub else None,
        }

    payload = {
        "n_paired_cells": len(paired),
        "control_on_picks": {
            "within_cell_stdev": _agg(control_sd),
            "within_cell_spread": _agg([p["control_spread"] for p in paired]),
            "repeats_gpt5mini_3pass": {
                "n": len(rep_sds),
                "mean_within_cell_stdev": statistics.mean(rep_sds) if rep_sds else None,
                "caveat": "control repeat judge is gpt-5-mini, tailored primary is gpt-5.4-mini",
            },
        },
        "tailored_on_same_cells": {
            "within_cell_stdev": _agg(tailored_sd),
        },
        "paired_diff_stdev": {
            "mean": statistics.mean(diffs) if diffs else None,
            "median": statistics.median(diffs) if diffs else None,
            "tailored_lower_n": neg,
            "tailored_higher_n": pos,
        },
        "by_target_type": {
            "generation": by("target_type", "generation"),
            "annotation": by("target_type", "annotation"),
        },
        "per_pick": paired,
    }

    doc = json.loads(STATS.read_text(encoding="utf-8"))
    doc[args.block] = payload
    STATS.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {k: v for k, v in payload.items() if k != "per_pick"}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
