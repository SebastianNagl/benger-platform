#!/usr/bin/env python3
"""Split the Benchathon human baseline under the LEXam judge by working mode.

The pooled human mean (57.1) mixes two arms of the grading event. This script
derives the traditional (unaided) vs co-creation (AI-assisted) split by joining
the LEXam judge cells against the Benchathon export's per-annotation
`ai_assisted` flag. The flag agrees with the canonical `solution_type` labels
in Benchmark_EMNLP/data/processed/benchathon_human_grades.json on every matched
graded solution (validated 2026-08-14: 120/120 grader-rows, 0 disagreements).

Inputs (one of them private):
  - data/judge_cells.tsv (this folder's dump; human cells carry annotation_id)
  - ../../Benchmark_EMNLP/data/raw/benchathon/Benchathon_export.json (PRIVATE
    raw export - present in the local working copy, never in the public repo)

Reference output (2026-08-14, judge gpt-5.4-mini, scores x100):
  co-creation  n=156  mean 61.60  se 1.48
  traditional  n=63   mean 46.67  se 2.77
  uplift       +14.94   (rubric-side uplift in the BenGER paper: +15.7)
  1 judged annotation absent from the export's task annotations (excluded).
"""

import json
import statistics as st
import collections
from pathlib import Path

HERE = Path(__file__).parent
EXPORT = HERE / ".." / ".." / "Benchmark_EMNLP" / "data" / "raw" / "benchathon" / "Benchathon_export.json"


def main() -> None:
    exp = json.load(open(EXPORT))
    amap = {}
    for tk in exp["tasks"]:
        for a in tk.get("annotations", []):
            amap[a["id"]] = {"ai": a.get("ai_assisted"), "cancelled": a.get("was_cancelled")}

    rows = []
    with open(HERE / "data" / "judge_cells.tsv") as f:
        hdr = f.readline().strip().split("\\t")  # dump uses literal backslash-t separators
        idx = {c: i for i, c in enumerate(hdr)}
        for line in f:
            p = line.rstrip("\n").split("\\t")
            if len(p) >= len(hdr) and p[idx["annotation_id"]]:
                rows.append((p[idx["annotation_id"]], float(p[idx["score"]])))

    groups = collections.defaultdict(list)
    unmatched = cancelled = 0
    for aid, sc in rows:
        a = amap.get(aid)
        if a is None:
            unmatched += 1
            continue
        if a["cancelled"]:
            cancelled += 1
            continue
        groups["co-creation" if a["ai"] else "traditional"].append(sc * 100)

    print(f"judged human cells: {len(rows)} (unmatched: {unmatched}, cancelled: {cancelled})")
    for k, v in sorted(groups.items()):
        print(f"{k}: n={len(v)} mean={st.mean(v):.2f} se={st.stdev(v)/len(v)**0.5:.2f}")
    print(f"uplift co-creation - traditional: "
          f"{st.mean(groups['co-creation']) - st.mean(groups['traditional']):.2f}")
    pooled = [s for v in groups.values() for s in v]
    print(f"pooled: n={len(pooled)} mean={st.mean(pooled):.2f}")


if __name__ == "__main__":
    main()
