#!/usr/bin/env python3
"""RQ2 baseline: abstract-rubric (control-arm) variance from the dataset paper.

The control arm already exists — the dataset paper's Benchathon data. This
script LIFTS the relevant reliability numbers from Benchmark_EMNLP's processed
artifacts (single source of truth; nothing is recomputed here) into
``data/processed/variance_stats.json``:

  control_arm.inter_judge   — within-cell spread across the 6-judge panel
                              (benchathon_inter_judge_agreement.json)
  control_arm.judge_repeats — same-judge 3-pass stability
                              (agreement_stats.rq5_judge_repeats)
  control_arm.human_irr     — blind 3-rater pool reliability
                              (agreement_stats.rq5_human_irr)
  control_arm.judge_vs_human— validity anchor under the abstract rubric
                              (agreement_stats.rq5_judge_vs_human)

``tailored_arm`` stays null until the re-grading runs land; the manuscript's
RQ2 section renders whatever halves exist.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ARR = HERE.parent / "Benchmark_EMNLP" / "data" / "processed"
OUT = HERE / "data" / "processed" / "variance_stats.json"


def load(name: str):
    path = ARR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> int:
    agreement = load("agreement_stats.json") or {}
    inter_judge = load("benchathon_inter_judge_agreement.json") or {}

    control = {
        "_sources": {
            "agreement_stats": str((ARR / "agreement_stats.json")),
            "inter_judge": str((ARR / "benchathon_inter_judge_agreement.json")),
        },
        "inter_judge": {
            "judges": inter_judge.get("judges"),
            "n_cells": inter_judge.get("n_cells_with_all_judges"),
            "within_cell_stdev": inter_judge.get("within_cell_stdev"),
            "within_cell_spread": inter_judge.get("within_cell_spread"),
        },
        "judge_repeats": agreement.get("rq5_judge_repeats"),
        "human_irr": {
            k: v
            for k, v in (agreement.get("rq5_human_irr") or {}).items()
            if not isinstance(v, dict)  # drop the nested balanced_subset block
        },
        "judge_vs_human": agreement.get("rq5_judge_vs_human"),
    }

    # MERGE, don't overwrite. The paired_contrast / paired_contrast_temp0 /
    # tailored_arm* blocks in this file come from compute_paired_contrast.py,
    # which needs the local DB and is therefore not part of `make analyze`.
    # A wholesale write here silently dropped them, and manuscript.qmd reads
    # variance_stats["paired_contrast_temp0"] — with it gone the whole RQ2
    # section degrades to "(pending: re-grading runs)" and the paper loses a
    # page. Only own the keys this script actually derives.
    doc = {}
    if OUT.exists():
        try:
            doc = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {}
    doc["control_arm"] = control
    doc.setdefault("tailored_arm", None)
    doc.setdefault("note", "tailored_arm populates after the re-grading runs")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)} "
          f"({len(doc)} blocks: {', '.join(sorted(doc))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
