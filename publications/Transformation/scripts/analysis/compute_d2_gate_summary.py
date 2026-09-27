#!/usr/bin/env python3
"""Compact, path-free summary of the D2 probe gate for the manuscript.

Reads the D2 gate output of compute_pilot_probe_gate.py (git-ignored,
<data root>/interim/pilot/gate_d2-probes.json, written with --phase
d2-probes) and writes data/processed/cslaw/gate_v2.json: per judge and
instrument the passes that are complete, the battery verdict over those
passes, the positive control, the largest score on any battery probe, and
the descriptive drops (negation flip, section ablation with its expected
drop, misplacement). A pass that a deliberate interruption left incomplete
is not counted, and only the errors on such a pass are discounted: an error
on a complete pass fails the battery. The summary says how many passes each
battery has.

The gate file must say "phase": "d2-probes"; a D1 gate file is refused. A
legacy gate.json (written before the per-phase files) is read only when its
input was the D2 probe rows and its batteries are D2 arms; it has no per-pass
error record, so none of its errors is discounted.

  compute_d2_gate_summary.py [--gate FILE] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]
import local_config  # noqa: E402
from d2_labels import arm_label, rubric_labels  # noqa: E402

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
GATE = DATA / "interim" / "pilot" / "gate_d2-probes.json"
LEGACY_GATE = DATA / "interim" / "pilot" / "gate.json"
OUT = HERE / "data" / "processed" / "cslaw" / "gate_v2.json"
LABELS = rubric_labels(DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl")
BATTERY = ("empty", "repetition", "offtopic", "keyword_salad", "injection", "same_area_offtopic")
D2_ARM_PREFIXES = ("martin:", "rubric:")


def gate_phase(gate: dict) -> str | None:
    """The phase a gate file scored; inferred for legacy files without the field."""
    if gate.get("phase"):
        return gate["phase"]
    labels = list((gate.get("per_battery") or {}).keys())
    d2_input = Path(str(gate.get("input") or "")).name == "d2-probes.jsonl"
    d2_labels = bool(labels) and all(" [" in lab and lab.split(" [", 1)[1].startswith(D2_ARM_PREFIXES)
                                     for lab in labels)
    return "d2-probes" if d2_input and d2_labels else None


def load_gate(path: Path | None) -> tuple[dict, Path]:
    candidates = [path] if path else [GATE, LEGACY_GATE]
    for candidate in candidates:
        if not candidate.exists():
            continue
        gate = json.loads(candidate.read_text(encoding="utf-8"))
        phase = gate_phase(gate)
        if phase == "d2-probes":
            return gate, candidate
        if path or candidate == GATE:
            raise SystemExit(f"{candidate} scored phase {phase or 'unknown'}, not d2-probes: refusing to "
                             "summarise it as D2")
    raise SystemExit(f"no D2 gate file: run compute_pilot_probe_gate.py --phase d2-probes (writes {GATE})")


def battery_entry(b: dict) -> dict:
    probes = b.get("probes") or {}
    over = b.get("over_complete_passes")
    if over is not None:  # gate schema 2: the gate discounted errors per pass
        complete_passes = list(over.get("passes") or [])
        battery = over.get("battery")
        positive = over.get("positive_control", b.get("positive_control"))
    else:  # legacy gate: no per-pass error record, so no error is discounted
        missing_passes = sorted({m["pass"] for m in b.get("missing") or []})
        complete_passes = [k for k in range(b.get("passes") or 0) if k not in missing_passes]
        fails = sum(int(probes.get(p, {}).get("fails") or 0) for p in BATTERY)
        errors = sum(int(probes.get(p, {}).get("errors") or 0) for p in BATTERY)
        battery = "pass" if fails == 0 and errors == 0 and complete_passes else "fail"
        positive = b.get("positive_control")
    return {
        "complete_passes": len(complete_passes),
        "battery": battery,
        "battery_max_score": max((probes.get(p, {}).get("max") or 0.0) for p in BATTERY),
        "model_proposed_median_on_negatives": max(
            (probes.get(p, {}).get("median_model_total") or 0.0) for p in BATTERY),
        "positive_control": positive,
        "musterloesung_median": probes.get("musterloesung", {}).get("median"),
        "negation_flip_drop": probes.get("negation_flip", {}).get("median_drop"),
        "section_ablation_drop": probes.get("section_ablation", {}).get("median_drop"),
        "section_ablation_expected": probes.get("section_ablation", {}).get("expected_drop"),
        "misplacement_drop": probes.get("misplacement", {}).get("median_drop"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gate", type=Path, default=None, help=f"D2 gate file (default: {GATE.name})")
    parser.add_argument("--out", type=Path, default=OUT, help="summary file (default: the tracked gate_v2.json)")
    args = parser.parse_args()
    gate, source = load_gate(args.gate)
    if source == LEGACY_GATE:
        print(f"note: reading the legacy {source.name}; rerun the gate for {GATE.name} (per-pass error record)")
    out = {"code_version": gate.get("code_version"), "criteria": gate.get("criteria"), "batteries": {}}
    for label, b in gate["per_battery"].items():
        judge, rest = label.split(" [", 1)
        arm = rest.split("]", 1)[0]
        out["batteries"].setdefault(arm_label(arm, LABELS), {})[judge] = battery_entry(b)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm, per in out["batteries"].items():
        for judge, x in per.items():
            print(f"{arm[:40]:40s} {judge[:28]:28s} passes {x['complete_passes']} battery {x['battery']} "
                  f"ML {x['musterloesung_median']} ablation {x['section_ablation_drop']}/{x['section_ablation_expected']} "
                  f"misplace {x['misplacement_drop']} negflip {x['negation_flip_drop']} proposed-neg {x['model_proposed_median_on_negatives']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
