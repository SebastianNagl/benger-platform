"""Per-task per-judge deviation table data.

For each of the 15 Benchathon tasks and each of the 3 Config-B judges
(GPT-5-mini, Opus-4.7, Gemini-3.1-Pro), compute the judge's score minus
the mean of the blind reviewers, broken out by solution type
(human_traditional, human_co_creation, llm_system).

Output: data/processed/judge_per_task.json
  {
    "tasks": [
      {"task_id": ..., "bereich": ..., "label": "Z1",
       "judge_devs": {
         "gpt-5-mini": {"trad": ..., "cocre": ..., "llm": ...},
         "gemini-3.1-pro-preview": {...},
         "claude-opus-4-7": {...}
       },
       "mean_blind": {"trad": ..., "cocre": ..., "llm": ...}
      }, ...
    ]
  }

  uv run python scripts/rq5_judge_per_task.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_agreement import REAL, humans_by_solution, load_json  # noqa: E402
from derive_paper_exports import CONFIG_B_FIELD_PREFIX  # noqa: E402
from rq5_judge_calibration import index_judge_per_config  # noqa: E402

JUDGES = ("gpt-5-mini", "claude-opus-4-7", "gemini-3.1-pro-preview")
SOLUTION_TYPES = ("human_traditional", "human_co_creation", "llm_system")
SOL_SHORT = {"human_traditional": "trad",
             "human_co_creation": "cocre",
             "llm_system": "llm"}

BEREICH_PREFIX = {
    "Strafrecht": "S",
    "Zivilrecht": "Z",
    "Öffentliches Recht": "Ö",
}


def main():
    real = load_json(REAL)
    canonical = load_json(PROCESSED / "benchathon_human_grades.json")

    # Index judge scores: solution_id -> {judge -> raw_score}
    # Human-authored picks come from task.evaluations (target="human"),
    # LLM-generated picks come from gen.evaluations (target="llm").
    inter_h = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="human")
    inter_l = index_judge_per_config(real, prefix=CONFIG_B_FIELD_PREFIX,
                                     group_by_judge=True, target="llm")

    # solution_id -> {judge -> raw}; merge both
    judge_by_sol = defaultdict(dict)
    for judge in JUDGES:
        for sid, raw in (inter_h.get(judge) or {}).items():
            judge_by_sol[sid][judge] = raw
        for sid, raw in (inter_l.get(judge) or {}).items():
            judge_by_sol[sid][judge] = raw

    # task_id -> solution_type -> (solution_id, [blind raw scores])
    by_task_soltype = defaultdict(lambda: defaultdict(lambda: (None, [])))
    bereich_by_task = {}
    for r in canonical:
        if r.get("role") != "blind":
            continue
        if r.get("raw_score") is None:
            continue
        tid = r.get("task_id")
        st = r.get("solution_type")
        sid = r.get("solution_id")
        if not (tid and st in SOLUTION_TYPES and sid):
            continue
        prev_sid, raws = by_task_soltype[tid][st]
        raws.append(float(r["raw_score"]))
        by_task_soltype[tid][st] = (sid, raws)
        bereich_by_task[tid] = r.get("bereich")

    # Build per-task label: Z1..Z5, S1..S5, Ö1..Ö5
    tasks_by_bereich = defaultdict(list)
    for tid in by_task_soltype:
        tasks_by_bereich[bereich_by_task[tid]].append(tid)
    label_by_task = {}
    for bereich, tids in tasks_by_bereich.items():
        for i, tid in enumerate(sorted(tids), start=1):
            label_by_task[tid] = f"{BEREICH_PREFIX[bereich]}{i}"

    # Compute deviations
    out_tasks = []
    for tid in sorted(by_task_soltype, key=lambda t: (
            BEREICH_PREFIX[bereich_by_task[t]], label_by_task[t])):
        entry = {
            "task_id": tid,
            "bereich": bereich_by_task[tid],
            "label": label_by_task[tid],
            "judge_devs": defaultdict(dict),
            "mean_blind": {},
        }
        for st in SOLUTION_TYPES:
            sid, raws = by_task_soltype[tid].get(st, (None, []))
            short = SOL_SHORT[st]
            if not (sid and raws):
                for judge in JUDGES:
                    entry["judge_devs"][judge][short] = None
                entry["mean_blind"][short] = None
                continue
            mean_blind = statistics.mean(raws)
            entry["mean_blind"][short] = mean_blind
            for judge in JUDGES:
                j = (judge_by_sol.get(sid) or {}).get(judge)
                entry["judge_devs"][judge][short] = (
                    None if j is None else float(j) - mean_blind)
        # Convert defaultdict to plain
        entry["judge_devs"] = {k: dict(v) for k, v in entry["judge_devs"].items()}
        out_tasks.append(entry)

    out = {"tasks": out_tasks}
    out_path = PROCESSED / "judge_per_task.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    print(f"saved {out_path}")

    # Console summary
    print()
    print(f"{'Task':6s}  {'Bereich':18s}  "
          f"{'GPT-5-mini T':>12s}  {'C':>6s}  {'L':>6s}  "
          f"{'Gemini T':>10s}  {'C':>6s}  {'L':>6s}  "
          f"{'Opus T':>10s}  {'C':>6s}  {'L':>6s}")
    for e in out_tasks:
        cells = [e["label"], e["bereich"]]
        for judge in JUDGES:
            for short in ("trad", "cocre", "llm"):
                v = e["judge_devs"][judge][short]
                cells.append("---" if v is None else f"{v:+.1f}")
        print(f"{cells[0]:6s}  {cells[1]:18s}  "
              f"{cells[2]:>12s}  {cells[3]:>6s}  {cells[4]:>6s}  "
              f"{cells[5]:>10s}  {cells[6]:>6s}  {cells[7]:>6s}  "
              f"{cells[8]:>10s}  {cells[9]:>6s}  {cells[10]:>6s}")


if __name__ == "__main__":
    main()
