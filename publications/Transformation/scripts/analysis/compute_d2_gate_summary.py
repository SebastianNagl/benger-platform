#!/usr/bin/env python3
"""Compact, path-free summary of the D2 probe gate for the manuscript.

Reads the gate output of compute_pilot_probe_gate.py (git-ignored,
<data root>/interim/pilot/gate.json, written with --phase d2-probes) and
writes data/processed/cslaw/gate_v2.json: per judge and instrument the
passes that are complete, the battery verdict over those passes, the
positive control, the largest score on any battery probe, and the
descriptive drops (negation flip, section ablation with its expected drop,
misplacement). A pass that a deliberate interruption left incomplete is
not counted; the summary says how many passes each battery has.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]
import local_config  # noqa: E402
from d2_labels import arm_label, rubric_labels  # noqa: E402

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
GATE = DATA / "interim" / "pilot" / "gate.json"
OUT = HERE / "data" / "processed" / "cslaw" / "gate_v2.json"
LABELS = rubric_labels(DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl")
BATTERY = ("empty", "repetition", "offtopic", "keyword_salad", "injection", "same_area_offtopic")


def main() -> int:
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    out = {"code_version": gate.get("code_version"), "criteria": gate.get("criteria"), "batteries": {}}
    for label, b in gate["per_battery"].items():
        judge, rest = label.split(" [", 1)
        arm = rest.split("]", 1)[0]
        missing_passes = sorted({m["pass"] for m in b.get("missing") or []})
        complete_passes = [k for k in range(b.get("passes") or 0) if k not in missing_passes]
        probes = b.get("probes") or {}
        battery_fails = sum(int(probes.get(p, {}).get("fails") or 0) for p in BATTERY)
        # errors on an incomplete pass come from the interruption, not from the judge
        errors = sum(int(probes.get(p, {}).get("errors") or 0) for p in BATTERY) if not missing_passes else 0
        out["batteries"].setdefault(arm_label(arm, LABELS), {})[judge] = {
            "complete_passes": len(complete_passes),
            "battery": "pass" if battery_fails == 0 and errors == 0 and complete_passes else "fail",
            "battery_max_score": max((probes.get(p, {}).get("max") or 0.0) for p in BATTERY),
            "model_proposed_median_on_negatives": max(
                (probes.get(p, {}).get("median_model_total") or 0.0) for p in BATTERY),
            "positive_control": b.get("positive_control"),
            "musterloesung_median": probes.get("musterloesung", {}).get("median"),
            "negation_flip_drop": probes.get("negation_flip", {}).get("median_drop"),
            "section_ablation_drop": probes.get("section_ablation", {}).get("median_drop"),
            "section_ablation_expected": probes.get("section_ablation", {}).get("expected_drop"),
            "misplacement_drop": probes.get("misplacement", {}).get("median_drop"),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm, per in out["batteries"].items():
        for judge, x in per.items():
            print(f"{arm[:40]:40s} {judge[:28]:28s} passes {x['complete_passes']} battery {x['battery']} "
                  f"ML {x['musterloesung_median']} ablation {x['section_ablation_drop']}/{x['section_ablation_expected']} "
                  f"misplace {x['misplacement_drop']} negflip {x['negation_flip_drop']} proposed-neg {x['model_proposed_median_on_negatives']}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
