#!/usr/bin/env python3
"""Matched same-judge instrument contrasts (reviewer-required baseline).

The published repeat contrast (control 3.03 vs tailored Luna 1.97) spans a
judge change: the control repeats ran on GPT-5 Mini. The matched holistic
arms re-grade the identical 45 cells with the SAME judges under the
holistic Falllösung rubric — Luna ×3 and GPT-5.4-Mini ×3 — completing a
2×2 (judge × instrument) in which every repeat contrast is within-judge
and within-version.

Conventions mirror analyze_luna_primary.py: first pass for validity and
panels, population SD over 3 passes per cell, blind-human pool mean as the
agreement anchor (annotation picks), panel = 5 flagship first passes + the
primary's first pass.

Inputs: holistic_results_{luna,mini}.jsonl (matched arms),
        judge_results_temp0.jsonl (tailored panel incl. Mini ×3),
        judge_results_luna.jsonl (tailored Luna ×3),
        control_results_temp0.jsonl (control panel + GPT-5 Mini ×3),
        picks_temp0.json, Dataset_ARR human pool.
Output: data/processed/matched_stats.json (incl. per-pick arrays for the
        significance/bootstrap script) + console summary.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DATASET_ARR = HERE.parent / "Dataset_ARR"
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "matched_stats.json"

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

    tail_panel = load_results(INTERIM / "judge_results_temp0.jsonl")   # incl. Mini ×3
    tail_luna = load_results(INTERIM / "judge_results_luna.jsonl")
    hol_luna = load_results(INTERIM / "holistic_results_luna.jsonl")
    hol_mini = load_results(INTERIM / "holistic_results_mini.jsonl")

    ctrl_single, ctrl_rep = defaultdict(dict), defaultdict(dict)
    for line in (INTERIM / "control_results_temp0.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["repeat_run"]:
            ctrl_rep[r["pick_id"]][int(r["run_index"] or 0)] = float(r["score"])
        else:
            ctrl_single[r["pick_id"]][r["judge"]] = float(r["score"])

    sample = json.loads((DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in json.loads((DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json").read_text()):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    hmean = {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}
    ann = [p for p in picks if picks[p]["target_type"] == "annotation" and p in hmean]

    def first(cells, pid, j):
        runs = cells[pid].get(j) or {}
        return runs[min(runs)] if runs else None

    def mean_runs(cells, pid, j):
        runs = cells[pid].get(j) or {}
        return statistics.mean(runs.values()) if runs else None

    def rep_sd(cells, pid, j):
        runs = cells[pid].get(j) or {}
        return statistics.pstdev(list(runs.values())) if len(runs) > 1 else None

    def validity(score_fn):
        pairs = [(score_fn(p), hmean[p]) for p in ann if score_fn(p) is not None]
        xs = [a for a, _ in pairs]; ys = [b for _, b in pairs]
        return {"n": len(xs), "pearson": pearson(xs, ys),
                "mae": statistics.mean(abs(a - b) for a, b in pairs) if pairs else None}

    arms = {
        (LUNA, "tailored"): tail_luna, (LUNA, "holistic"): hol_luna,
        (MINI, "tailored"): tail_panel, (MINI, "holistic"): hol_mini,
    }

    # ---- per-pick table (drives sign tests + cluster bootstrap downstream) ----
    per_pick = []
    for pid in sorted(picks):
        p = picks[pid]
        ctrl_runs = ctrl_rep.get(pid) or {}
        row = {
            "pick_id": pid, "task_id": p["task_id"], "provenance": p["provenance"],
            "target_type": p["target_type"], "human_mean": hmean.get(pid),
            "control_gpt5mini_rep_sd": statistics.pstdev(list(ctrl_runs.values())) if len(ctrl_runs) > 1 else None,
        }
        for (judge, instr), cells in arms.items():
            key = f"{'luna' if judge == LUNA else 'mini'}_{instr[:4]}"
            row[f"{key}_rep_sd"] = rep_sd(cells, pid, judge)
            row[f"{key}_first"] = first(cells, pid, judge)
            row[f"{key}_mean3"] = mean_runs(cells, pid, judge)
        # Panels: tailored flagships + primary (first passes); holistic = control
        # flagship single passes + the matched primary's holistic first pass.
        tail_flag = [first(tail_panel, pid, j) for j in PANEL_BASE]
        hol_flag = [ctrl_single.get(pid, {}).get(j) for j in PANEL_BASE]
        for name, flags, pv in (
            ("panel_tail_luna", tail_flag, first(tail_luna, pid, LUNA)),
            ("panel_tail_mini", tail_flag, first(tail_panel, pid, MINI)),
            ("panel_hol_luna", hol_flag, first(hol_luna, pid, LUNA)),
            ("panel_hol_mini", hol_flag, first(hol_mini, pid, MINI)),
            ("panel_ctrl_mini", hol_flag, ctrl_single.get(pid, {}).get(MINI)),
        ):
            row[name] = (statistics.pstdev([v for v in flags] + [pv])
                         if pv is not None and all(v is not None for v in flags) else None)
        per_pick.append(row)

    def mean_of(key, rows=None):
        vals = [r[key] for r in (rows or per_pick) if r.get(key) is not None]
        return {"n": len(vals), "mean": statistics.mean(vals) if vals else None}

    def paired(key_a, key_b):
        pairs = [(r[key_a], r[key_b]) for r in per_pick
                 if r.get(key_a) is not None and r.get(key_b) is not None]
        diffs = [a - b for a, b in pairs]
        return {
            "n": len(pairs),
            "mean_a": statistics.mean(a for a, _ in pairs) if pairs else None,
            "mean_b": statistics.mean(b for _, b in pairs) if pairs else None,
            "mean_diff": statistics.mean(diffs) if diffs else None,
            "a_lower_n": sum(1 for d in diffs if d < 0),
            "a_higher_n": sum(1 for d in diffs if d > 0),
            "ties": sum(1 for d in diffs if d == 0),
        }

    payload = {
        "note": "matched same-judge instrument contrasts; conventions as analyze_luna_primary.py; "
                "holistic arms = llm_judge_falloesung-{luna3,mini3}-matched on the temp0 clone, "
                "T=1 (provider-forced, both judges), max_tokens 16000",
        "per_judge": {
            "gpt-5.6-luna": {
                "repeats": {
                    "tailored": mean_of("luna_tail_rep_sd"),
                    "holistic": mean_of("luna_holi_rep_sd"),
                    "paired_tailored_vs_holistic": paired("luna_tail_rep_sd", "luna_holi_rep_sd"),
                },
                "validity": {
                    "tailored_first_pass": validity(lambda p: first(tail_luna, p, LUNA)),
                    "tailored_mean3": validity(lambda p: mean_runs(tail_luna, p, LUNA)),
                    "holistic_first_pass": validity(lambda p: first(hol_luna, p, LUNA)),
                    "holistic_mean3": validity(lambda p: mean_runs(hol_luna, p, LUNA)),
                },
                "p01": {"tailored": tail_luna.get("P01", {}).get(LUNA),
                        "holistic": hol_luna.get("P01", {}).get(LUNA)},
            },
            "gpt-5.4-mini": {
                "repeats": {
                    "tailored": mean_of("mini_tail_rep_sd"),
                    "holistic": mean_of("mini_holi_rep_sd"),
                    "paired_tailored_vs_holistic": paired("mini_tail_rep_sd", "mini_holi_rep_sd"),
                },
                "validity": {
                    "tailored_first_pass": validity(lambda p: first(tail_panel, p, MINI)),
                    "tailored_mean3": validity(lambda p: mean_runs(tail_panel, p, MINI)),
                    "holistic_first_pass": validity(lambda p: first(hol_mini, p, MINI)),
                    "holistic_mean3": validity(lambda p: mean_runs(hol_mini, p, MINI)),
                },
                "p01": {"tailored": tail_panel.get("P01", {}).get(MINI),
                        "holistic": hol_mini.get("P01", {}).get(MINI)},
            },
        },
        "legacy_control": {
            "gpt5mini_repeat": mean_of("control_gpt5mini_rep_sd"),
            "caveat": "control repeats ran on GPT-5 Mini (deprecated predecessor); "
                      "kept for continuity — the matched contrasts above replace it",
            "luna_holistic_vs_gpt5mini_control": paired("luna_holi_rep_sd", "control_gpt5mini_rep_sd"),
            "mini_holistic_vs_gpt5mini_control": paired("mini_holi_rep_sd", "control_gpt5mini_rep_sd"),
        },
        "panels": {
            "tailored_luna": mean_of("panel_tail_luna"),
            "tailored_mini": mean_of("panel_tail_mini"),
            "holistic_luna": mean_of("panel_hol_luna"),
            "holistic_mini": mean_of("panel_hol_mini"),
            "control_mini": mean_of("panel_ctrl_mini"),
            "paired_tail_vs_hol_luna": paired("panel_tail_luna", "panel_hol_luna"),
        },
        "per_pick": per_pick,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    print("=== MATCHED 2x2: mean within-cell repeat SD (n cells) ===")
    for jname, jkey in (("Luna", "gpt-5.6-luna"), ("Mini", "gpt-5.4-mini")):
        r = payload["per_judge"][jkey]["repeats"]
        pd = r["paired_tailored_vs_holistic"]
        print(f"{jname}: tailored {r['tailored']['mean']:.3f} (n={r['tailored']['n']})  "
              f"holistic {r['holistic']['mean']:.3f} (n={r['holistic']['n']})  "
              f"diff {pd['mean_diff']:+.3f}, tailored lower on {pd['a_lower_n']}/{pd['n']}")
    lc = payload["legacy_control"]["gpt5mini_repeat"]
    print(f"legacy control (GPT-5 Mini): {lc['mean']:.3f} (n={lc['n']})")
    print("=== agreement with human pool (first pass) ===")
    for jname, jkey in (("Luna", "gpt-5.6-luna"), ("Mini", "gpt-5.4-mini")):
        v = payload["per_judge"][jkey]["validity"]
        t, h = v["tailored_first_pass"], v["holistic_first_pass"]
        print(f"{jname}: tailored r={t['pearson']:.3f} MAE={t['mae']:.1f}  "
              f"holistic r={h['pearson']:.3f} MAE={h['mae']:.1f} (n={t['n']})")
    print("=== panels (mean within-cell SD) ===")
    for k in ("control_mini", "tailored_mini", "tailored_luna", "holistic_luna", "holistic_mini"):
        m = payload["panels"][k]
        print(f"{k}: {m['mean']:.3f} (n={m['n']})")
    print("=== P01 ===")
    for jkey in ("gpt-5.6-luna", "gpt-5.4-mini"):
        p = payload["per_judge"][jkey]["p01"]
        print(f"{jkey}: tailored {p['tailored']} holistic {p['holistic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
