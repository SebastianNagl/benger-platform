#!/usr/bin/env python3
"""Probe gate on the current rubric judge (extended-version pilot P1).

Scores data/interim/pilot/probes.jsonl (from scripts/ops/run_checklist_pilot.py)
against the probe criteria registered for the paper: repetition < 5,
empty = 0, offtopic <= 10 on every pass; the Musterlösung positive control
>= 70. The judge ran each exam's D6-drawn rubric on the CURRENT product lane
(fixed system prompt, tagged inputs, per-step evidence quotes verified in
code). The same judge's result on the published run (tailored arm of
data/processed/probe_stats.json) is shown next to it.

Also reported: how many steps the evidence check zeroed per probe type, and
the total the model itself proposed before verification ("model_total").

Output: data/processed/pilot_probe_gate.json + console table.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
IN = HERE / "data" / "interim" / "pilot" / "probes.jsonl"
PUBLISHED = HERE / "data" / "processed" / "probe_stats.json"
OUT = HERE / "data" / "processed" / "pilot_probe_gate.json"
CRITERIA = {"repetition": ("lt", 5.0), "empty": ("eq", 0.0), "offtopic": ("le", 10.0), "musterloesung": ("ge", 70.0)}


def violates(ptype: str, score: float) -> bool:
    op, thr = CRITERIA[ptype]
    return {"lt": not score < thr, "eq": score != thr, "le": not score <= thr, "ge": not score >= thr}[op]


def main() -> int:
    latest = {}
    for line in IN.read_text().splitlines():
        row = json.loads(line)
        latest[(row["judge"], row["exam"], row["probe"])] = row  # later rows win
    published = (json.loads(PUBLISHED.read_text()).get("arms") or {}).get("tailored") or {}

    cells = defaultdict(list)
    for (judge, _exam, probe), row in sorted(latest.items()):
        cells[(judge, probe)].append(row)

    result = {}
    for (judge, probe), rows in sorted(cells.items()):
        ok = [r for r in rows if r.get("total") is not None]
        scores = [float(r["total"]) for r in ok]
        fails = [r["exam"] for r in ok if violates(probe, float(r["total"]))]
        old = (published.get(judge) or {}).get(probe) or {}
        result.setdefault(judge, {})[probe] = {
            "n": len(ok),
            "errors": len(rows) - len(ok),
            "fails": len(fails),
            "fail_exams": fails,
            "median": statistics.median(scores) if scores else None,
            "max": max(scores) if scores else None,
            "median_model_total": statistics.median([float(r.get("model_total") or 0) for r in ok]) if ok else None,
            "zeroed_steps": sum(int(r.get("zeroed") or 0) for r in ok),
            "published": {"n_passes": old.get("n_passes"), "fails": old.get("n_fail_passes"), "median": old.get("median")},
        }
    for judge, per in result.items():
        negatives = [per[p] for p in ("repetition", "empty", "offtopic") if p in per]
        per["battery"] = "pass" if negatives and all(x["fails"] == 0 and x["errors"] == 0 for x in negatives) else "fail"
        if "musterloesung" in per:
            per["positive_control"] = "pass" if per["musterloesung"]["fails"] == 0 else "fail"
    OUT.write_text(json.dumps({"criteria": CRITERIA, "per_judge": result}, indent=1) + "\n")

    for judge, per in result.items():
        print(f"== {judge}: battery {per['battery']}" + (f", positive control {per.get('positive_control')}" if "positive_control" in per else ""))
        for probe in ("empty", "repetition", "offtopic", "musterloesung"):
            if probe not in per:
                continue
            x = per[probe]
            pub = x["published"]
            print(f"  {probe:13s} fails {x['fails']:2d}/{x['n']:2d}  median {x['median']:5.1f}  max {x['max']:5.1f}  "
                  f"model-proposed median {x['median_model_total']:5.1f}  zeroed steps {x['zeroed_steps']:3d}   "
                  f"| published: fails {pub['fails']}/{pub['n_passes']} median {pub['median']}")
    print(f"-> {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
