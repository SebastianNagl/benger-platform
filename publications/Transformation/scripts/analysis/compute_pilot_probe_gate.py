#!/usr/bin/env python3
"""Probe gate for the pilot judges (P1 product lane, P2 checklist lane).

Scores data/interim/pilot/probes.jsonl (from scripts/ops/pilot.sh probes)
against the probe criteria registered for the paper, on every pass:

  empty          = 0
  repetition     < 5
  offtopic       <= 10
  keyword_salad  <= 10   (the rubric's norms and key terms, no sentences)
  negation_flip  below the same pass's Musterlösung score for that exam
  musterloesung  >= 70   (positive control, reported separately)

A judge's battery passes only when every negative probe passes on every exam
and pass with no errors, and no cell is missing. A cell is (exam, probe type,
pass); a negation_flip cell that the runner skipped (fewer than 3 flipped
sentences) counts as present. Judges on the checklist lane are reported per
unit, e.g. "gpt-5.6-luna [checklist:bullet]".

Rows are filtered by code version (the content hash of the judge, verifier,
generator and prompt files; see provenance.code_version) so stale rows do
not mix in. The default is the code version of the newest row; pass
--code-version any to read legacy rows without provenance. Dry-run rows never
count. For each cell the latest row wins.

The same judge's result on the published run (tailored arm of
data/processed/probe_stats.json) is shown next to it.

Exit codes: 0 every battery passes; 1 a battery fails on scores or errors;
2 a battery is incomplete (a probe type, pass or exam cell is missing) or no
rows match.

Output: data/processed/pilot_probe_gate.json + console table.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
MAIN_DATA = Path("/home/pschorr95/Code/BenGER/benger-platform/publications/Transformation/data")
PUBLISHED = HERE / "data" / "processed" / "probe_stats.json"
OUT = HERE / "data" / "processed" / "pilot_probe_gate.json"
PROBE_TYPES = ("empty", "repetition", "offtopic", "musterloesung", "negation_flip", "keyword_salad")
NEGATIVE = ("empty", "repetition", "offtopic", "keyword_salad", "negation_flip")
CRITERIA = {
    "repetition": ("lt", 5.0),
    "empty": ("eq", 0.0),
    "offtopic": ("le", 10.0),
    "musterloesung": ("ge", 70.0),
    "keyword_salad": ("le", 10.0),
    "negation_flip": ("lt_paired", "musterloesung"),
}


def violates(ptype: str, score: float) -> bool:
    op, thr = CRITERIA[ptype]
    return {"lt": not score < thr, "eq": score != thr, "le": not score <= thr, "ge": not score >= thr}[op]


def default_input() -> Path:
    root = os.environ.get("PILOT_DATA_ROOT")
    if root:
        return Path(root) / "interim" / "pilot" / "probes.jsonl"
    local = HERE / "data" / "interim" / "pilot" / "probes.jsonl"
    return local if local.exists() else MAIN_DATA / "interim" / "pilot" / "probes.jsonl"


def label(row: dict) -> str:
    if (row.get("lane") or "product") == "product":
        return row["judge"]
    if row.get("arm"):  # d2-probes: one battery per judge and instrument
        return f"{row['judge']} [{row['arm']}]"
    return f"{row['judge']} [checklist:{row.get('unit')}]"


def load(path: Path, code_version: str | None):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    live = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    if code_version is None:
        versions = [(r.get("provenance") or {}).get("code_version") for r in live]
        versions = [v for v in versions if v]
        code_version = versions[-1] if versions else None
        if code_version is None:
            return [], "none", {"rows": len(rows), "dry_run_rows": len(rows) - len(live), "kept": 0,
                                "other_code_versions": len(live),
                                "hint": "no live row carries a code version; pass --code-version any for legacy rows"}
    kept = live if code_version == "any" else [
        r for r in live if (r.get("provenance") or {}).get("code_version") == code_version]
    stats = {"rows": len(rows), "dry_run_rows": len(rows) - len(live), "kept": len(kept),
             "other_code_versions": len(live) - len(kept)}
    return kept, code_version, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--in", dest="inp", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--code-version", default=None, help="provenance code version; 'any' for legacy rows")
    parser.add_argument("--types", nargs="*", default=list(PROBE_TYPES), help="probe types every judge must have")
    parser.add_argument("--passes", type=int, default=None, help="passes every judge must have (default: most seen)")
    args = parser.parse_args()
    inp = args.inp or default_input()

    rows, code_version, stats = load(inp, args.code_version)
    if not rows:
        print(f"no rows for code version {code_version} in {inp} ({stats})")
        return 2
    latest = {}
    for row in rows:  # later rows win
        latest[(label(row), row["exam"], row["probe"], int(row.get("pass") or 0))] = row
    published = (json.loads(PUBLISHED.read_text()).get("arms") or {}).get("tailored") or {} if PUBLISHED.exists() else {}

    by_label = defaultdict(dict)
    for (lab, exam, probe, k), row in latest.items():
        by_label[lab][(exam, probe, k)] = row

    result = {}
    worst = 0
    for lab, cells in sorted(by_label.items()):
        judge = next(iter(cells.values()))["judge"]
        exams = sorted({exam for exam, _, _ in cells})
        passes = args.passes or (max(k for _, _, k in cells) + 1)
        missing = [{"exam": e, "probe": p, "pass": k} for e in exams for p in args.types for k in range(passes)
                   if (e, p, k) not in cells or (cells[(e, p, k)].get("skipped") and p != "negation_flip")]
        per = {}
        for probe in args.types:
            present = [cells[(e, probe, k)] for e in exams for k in range(passes) if (e, probe, k) in cells]
            skipped = [r for r in present if r.get("skipped")]
            scored = [r for r in present if not r.get("skipped")]
            ok = [r for r in scored if r.get("total") is not None]
            fails, unpaired = [], []
            for r in ok:
                if probe == "negation_flip":
                    ref = cells.get((r["exam"], "musterloesung", int(r.get("pass") or 0)))
                    if not ref or ref.get("total") is None:
                        unpaired.append({"exam": r["exam"], "pass": r.get("pass", 0)})
                    elif not float(r["total"]) < float(ref["total"]):
                        fails.append({"exam": r["exam"], "pass": r.get("pass", 0),
                                      "score": r["total"], "musterloesung": ref["total"]})
                elif violates(probe, float(r["total"])):
                    fails.append({"exam": r["exam"], "pass": r.get("pass", 0), "score": r["total"]})
            scores = [float(r["total"]) for r in ok]
            old = (published.get(judge) or {}).get(probe) or {}
            per[probe] = {
                "n": len(ok),
                "errors": len(scored) - len(ok),
                "fails": len(fails),
                "fail_exams": sorted({f["exam"] for f in fails}),
                "fail_cells": fails,
                "skipped": len(skipped),
                "unpaired": len(unpaired),
                "median": statistics.median(scores) if scores else None,
                "max": max(scores) if scores else None,
                "median_model_total": statistics.median([float(r.get("model_total") or 0) for r in ok]) if ok else None,
                "zeroed_steps": sum(int(r.get("zeroed") or 0) for r in ok),
                "published": {"n_passes": old.get("n_passes"), "fails": old.get("n_fail_passes"), "median": old.get("median")},
            }
        negatives = [per[p] for p in NEGATIVE if p in per]
        clean = all(x["fails"] == 0 and x["errors"] == 0 and x["unpaired"] == 0 for x in negatives)
        per["battery"] = "pass" if negatives and clean and not missing else "fail"
        if "musterloesung" in per:
            ml = per["musterloesung"]
            per["positive_control"] = "pass" if ml["fails"] == 0 and ml["errors"] == 0 and ml["n"] else "fail"
        per["complete"] = not missing
        per["missing"] = missing
        per["exams"] = exams
        per["passes"] = passes
        result[lab] = per
        worst = max(worst, 2 if missing else (1 if per["battery"] == "fail" else 0))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"criteria": CRITERIA, "code_version": code_version, "input": str(inp),
                                    "filter": stats, "required_types": args.types, "per_judge": result},
                                   indent=1, ensure_ascii=False) + "\n")

    print(f"code version {code_version}: {stats['kept']} rows used, {stats['other_code_versions']} from other "
          f"code versions and {stats['dry_run_rows']} dry-run rows left out")
    fmt = lambda v: f"{v:5.1f}" if isinstance(v, (int, float)) else "    -"
    for lab, per in result.items():
        head = f"== {lab}: battery {per['battery']}"
        if "positive_control" in per:
            head += f", positive control {per['positive_control']}"
        head += f"  ({len(per['exams'])} exams x {per['passes']} passes)"
        print(head)
        for probe in args.types:
            x = per[probe]
            pub = x["published"]
            extra = f" unpaired {x['unpaired']}" if x["unpaired"] else ""
            extra += f" skipped {x['skipped']}" if x["skipped"] else ""
            print(f"  {probe:13s} fails {x['fails']:2d}/{x['n']:2d} errors {x['errors']:2d}  median {fmt(x['median'])}  "
                  f"max {fmt(x['max'])}  model-proposed median {fmt(x['median_model_total'])}  "
                  f"zeroed {x['zeroed_steps']:3d}{extra}   | published: fails {pub['fails']}/{pub['n_passes']} median {pub['median']}")
        if per["missing"]:
            shown = ", ".join(f"exam {m['exam']} {m['probe']} pass {m['pass']}" for m in per["missing"][:8])
            print(f"  MISSING {len(per['missing'])} cells: {shown}{' ...' if len(per['missing']) > 8 else ''}")
    try:
        shown_out = args.out.relative_to(HERE)
    except ValueError:
        shown_out = args.out
    print(f"-> {shown_out}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
