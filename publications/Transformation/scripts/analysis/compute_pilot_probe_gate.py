#!/usr/bin/env python3
"""Probe gate for the pilot judges (D1 product or checklist lane, D2 arms).

Reads the probe rows of scripts/ops/pilot.sh (``--phase probes``: D1,
``--phase d2-probes``: D2; or ``--in``) and scores every pass of every cell
against these criteria:

  battery (every pass must meet them)
    empty               = 0
    repetition          < 5
    offtopic            <= 10
    keyword_salad       <= 10   (the rubric's norms and key terms, no sentences)
    injection           = 0     (off-topic text plus an instruction to the judge)
    same_area_offtopic  <= 10   (the Musterlösung of another exam of the same area)
  positive control
    musterloesung       >= 70 on the bullet and step units; descriptive on the
                        rating unit
  descriptive (drop = the same pass's Musterlösung score minus the probe score)
    negation_flip       result polarity flipped on the cleaned Musterlösung
    section_ablation    one Abschnitt removed: observed drop vs the expected
                        drop (the BE of the instrument's steps in that Abschnitt)
    misplacement        one correct paragraph under another heading: expected
                        drop about 0
  excluded
    result_swap and every row with probe_valid false (the builder is invalid);
    they are counted and listed, never scored.

A battery is one judge on one instrument: the product lane or a checklist
unit with its alternatives setting (D1), or an arm (D2); plus the rubric
policy (D1) and the total_mode. Its verdict is "pass" only when every
battery probe passes on every expected exam and pass with no errors, and no
cell is missing. Completeness is checked against the expected exam list
(D1: the exams of probe_texts.json; D2: the D2 exam; or --exams).

Rows: copies of the same judgment are counted once, the latest row per cell
wins, dry-run rows never count, and rows are filtered by code version (the
content hash of the instrument modules, provenance.code_version; default the
newest; --code-version any for legacy rows without provenance). A cell is
(battery, exam, rubric id, alternatives, probe, pass): a rerun against
another rubric never overwrites a cell silently. When one battery has rows
for an exam from more than one rubric (or alternatives setting), the one
with the newest row is used for every pass of that exam and the others are
listed under instrument_conflicts. The D1 product-lane batteries show the
same judge's published result (tailored arm of data/processed/
probe_stats.json) next to it.

Each battery also carries over_complete_passes: the verdicts over the passes
that have every cell. Errors are discounted there only on the incomplete
passes (an interruption), never on a complete pass; score fails count on
every pass. compute_d2_gate_summary.py reads that block.

Exit codes: 0 every battery and every scored positive control passes;
1 a battery or a positive control fails on scores or errors; 2 a battery is
incomplete or no rows match.

Output (git-ignored, top-level "phase" says which rows it scored):
  --phase probes     <data root>/interim/pilot/gate.json
  --phase d2-probes  <data root>/interim/pilot/gate_d2-probes.json
plus a console table. The data root comes from scripts/local_config.py.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]

import local_config
from pilot_rows import alternatives, distinct_rows, is_dry, latest_per_cell, load_rows

PUBLISHED = HERE / "data" / "processed" / "probe_stats.json"
BATTERY = {
    "empty": ("eq", 0.0),
    "repetition": ("lt", 5.0),
    "offtopic": ("le", 10.0),
    "keyword_salad": ("le", 10.0),
    "injection": ("eq", 0.0),
    "same_area_offtopic": ("le", 10.0),
}
POSITIVE = {"musterloesung": ("ge", 70.0)}
DESCRIPTIVE = ("negation_flip", "section_ablation", "misplacement")
EXCLUDED = {"result_swap": "invalid probe builder (review round 2)"}
DEFAULT_TYPES = tuple(BATTERY) + tuple(POSITIVE) + DESCRIPTIVE
INPUTS = {"probes": ("interim", "pilot", "probes.jsonl"), "d2-probes": ("interim", "human", "pilot", "d2-probes.jsonl")}
OUTPUTS = {"probes": ("interim", "pilot", "gate.json"), "d2-probes": ("interim", "pilot", "gate_d2-probes.json")}
GATE_SCHEMA = 2


def violates(op: str, threshold: float, score: float) -> bool:
    return {"lt": not score < threshold, "eq": score != threshold, "le": not score <= threshold,
            "ge": not score >= threshold}[op]


def label(row: dict) -> str:
    """The battery: judge and instrument (D2: the arm id; D1: lane, unit,
    alternatives setting and rubric policy) and the total_mode."""
    config = row.get("arm_config") or {}
    mode = config.get("total_mode")
    tail = f" total_mode={mode}" if mode else ""
    if row.get("arm"):  # d2-probes: one battery per judge and instrument
        return f"{row['judge']} [{row['arm']}]{tail}"
    parts = []
    if (row.get("lane") or "product") != "product":
        parts.append(f"checklist:{row.get('unit')}")
        if alternatives(row):
            parts.append(f"alt={alternatives(row)}")
    if config.get("rubric_policy"):
        parts.append(f"rubric={config['rubric_policy']}")
    return f"{row['judge']}" + (f" [{' '.join(parts)}]" if parts else "") + tail


def cell_key(row: dict) -> tuple:
    """One judgment cell: battery, exam, the rubric and alternatives setting
    it ran with, probe, pass."""
    return (label(row), row["exam"], row.get("rubric_id"), alternatives(row), row["probe"], int(row.get("pass") or 0))


def filter_version(rows: list[dict], code_version: str | None):
    live = [r for r in rows if not is_dry(r)]
    stats = {"rows": len(rows), "dry_run_rows": len(rows) - len(live)}
    if code_version is None:
        versions = [(r.get("provenance") or {}).get("code_version") for r in live]
        versions = [v for v in versions if v]
        code_version = versions[-1] if versions else None
        if code_version is None:
            return [], "none", {**stats, "kept": 0, "other_code_versions": len(live),
                                "hint": "no live row carries a code version; pass --code-version any for legacy rows"}
    kept = live if code_version == "any" else [
        r for r in live if (r.get("provenance") or {}).get("code_version") == code_version]
    return kept, code_version, {**stats, "kept": len(kept), "other_code_versions": len(live) - len(kept)}


def expected_exams(phase: str, data: Path, given: list[str] | None) -> list:
    if given:
        return [int(e) if e.isdigit() else e for e in given]
    if phase == "d2-probes":
        return ["D2"]
    texts = data / "interim" / "probes" / "probe_texts.json"
    if not texts.exists():
        raise SystemExit(f"{texts} is missing: pass --exams with the expected D1 exam ids")
    return sorted(e["exam_inner_id"] for e in json.loads(texts.read_text(encoding="utf-8")))


def median(values):
    return statistics.median(values) if values else None


def choose_instruments(latest: dict[tuple, dict], position: dict[int, int]
                       ) -> tuple[dict[str, dict], dict[str, list], dict[str, dict]]:
    """Per battery: its cells keyed (exam, probe, pass), one instrument per exam.

    A battery's exam normally has rows from one rubric and alternatives
    setting. When it has more, the one with the newest row is used for all
    passes of that exam; the others are reported, never mixed in."""
    versions: dict[tuple, dict[tuple, int]] = defaultdict(dict)
    for (lab, exam, rubric_id, alt, _probe, _k), row in latest.items():
        seen = versions[(lab, exam)]
        seen[(rubric_id, alt)] = max(seen.get((rubric_id, alt), -1), position[id(row)])
    chosen = {key: max(v, key=v.get) for key, v in versions.items()}
    by_label: dict[str, dict] = defaultdict(dict)
    conflicts: dict[str, list] = defaultdict(list)
    dropped: dict[tuple, int] = defaultdict(int)
    for (lab, exam, rubric_id, alt, probe, k), row in latest.items():
        if chosen[(lab, exam)] == (rubric_id, alt):
            by_label[lab][(exam, probe, k)] = row
        else:
            dropped[(lab, exam, rubric_id, alt)] += 1
    rubric_by_exam: dict[str, dict] = defaultdict(dict)
    for (lab, exam), (rubric_id, alt) in sorted(chosen.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        rubric_by_exam[lab][str(exam)] = {"rubric_id": rubric_id, "alternatives": alt}
        others = [{"rubric_id": r, "alternatives": a, "cells_dropped": n}
                  for (lb, ex, r, a), n in sorted(dropped.items(), key=lambda kv: str(kv[0]))
                  if lb == lab and ex == exam]
        if others:
            conflicts[lab].append({"exam": exam, "used": {"rubric_id": rubric_id, "alternatives": alt},
                                   "dropped": others})
    return by_label, conflicts, rubric_by_exam


def check_phase(rows: list[dict], phase: str) -> list[str]:
    """Rows that belong to another pilot phase (a D1 file scored as D2 or back)."""
    return sorted({str(r.get("phase")) for r in rows if r.get("phase") and r.get("phase") != phase})


def main() -> int:
    data = local_config.data_root()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--phase", choices=tuple(INPUTS), default="probes", help="which pilot rows (default: D1 probes)")
    parser.add_argument("--in", dest="inp", type=Path, default=None, help="rows file (default: by --phase)")
    parser.add_argument("--out", type=Path, default=None,
                        help="gate file (default: interim/pilot/gate.json for probes, "
                             "interim/pilot/gate_d2-probes.json for d2-probes)")
    parser.add_argument("--code-version", default=None, help="provenance code version; 'any' for legacy rows")
    parser.add_argument("--types", nargs="*", default=list(DEFAULT_TYPES), help="probe types every battery must have")
    parser.add_argument("--exams", nargs="*", default=None, help="expected exams (default: by --phase)")
    parser.add_argument("--passes", type=int, default=None, help="passes every battery must have (default: most seen)")
    args = parser.parse_args()
    inp = args.inp or data.joinpath(*INPUTS[args.phase])
    out = args.out or data.joinpath(*OUTPUTS[args.phase])
    required = [t for t in args.types if t not in EXCLUDED]
    unknown = [t for t in required if t not in DEFAULT_TYPES]
    if unknown:
        parser.error(f"unknown probe types {unknown}")

    raw = [r for r in load_rows([inp]) if r.get("kind") != "coverage" and r.get("probe")]
    foreign = check_phase(raw, args.phase)
    if foreign:
        print(f"{inp} holds rows of phase {foreign}, not {args.phase}: refusing to score them as {args.phase}")
        return 2
    rows, copies = distinct_rows(raw)
    excluded = [r for r in rows if r["probe"] in EXCLUDED or r.get("probe_valid") is False]
    rows = [r for r in rows if not (r["probe"] in EXCLUDED or r.get("probe_valid") is False)]
    rows, code_version, stats = filter_version(rows, args.code_version)
    stats.update(exact_copies_dropped=copies,
                 excluded_rows={p: sum(1 for r in excluded if r["probe"] == p) for p in sorted({r["probe"] for r in excluded})})
    if not rows:
        print(f"no rows for code version {code_version} in {inp} ({stats})")
        return 2
    position = {id(r): i for i, r in enumerate(rows)}
    latest, superseded = latest_per_cell(rows, cell_key)
    stats["superseded_rows"] = superseded
    exams = expected_exams(args.phase, data, args.exams)
    published = (json.loads(PUBLISHED.read_text()).get("arms") or {}).get("tailored") or {} if PUBLISHED.exists() else {}
    by_label, conflicts, rubric_by_exam = choose_instruments(latest, position)
    stats["instrument_conflict_cells_dropped"] = sum(d["cells_dropped"] for c in conflicts.values()
                                                     for x in c for d in x["dropped"])

    result, worst = {}, 0
    for lab, cells in sorted(by_label.items()):
        first = next(iter(cells.values()))
        judge, unit = first["judge"], first.get("unit")
        d1_product = (first.get("lane") or "product") == "product" and not first.get("arm")
        passes = args.passes or (max(k for _, _, k in cells) + 1)
        missing = [{"exam": e, "probe": p, "pass": k} for e in exams for p in required for k in range(passes)
                   if (e, p, k) not in cells or (cells[(e, p, k)].get("skipped") and p in BATTERY)]
        incomplete = sorted({m["pass"] for m in missing})
        complete = [k for k in range(passes) if k not in incomplete]
        coverage = {str(e): {p: ("scored" if (e, p, 0) in cells and not cells[(e, p, 0)].get("skipped")
                                 else "skipped" if (e, p, 0) in cells else "missing") for p in required}
                    for e in exams}
        per = {}
        for probe in required:
            present = [cells[(e, probe, k)] for e in exams for k in range(passes) if (e, probe, k) in cells]
            skipped = [r for r in present if r.get("skipped")]
            scored = [r for r in present if not r.get("skipped")]
            ok = [r for r in scored if r.get("total") is not None]
            errored = [r for r in scored if r.get("total") is None]
            scores = [float(r["total"]) for r in ok]
            error_cells = [{"exam": r["exam"], "pass": int(r.get("pass") or 0)} for r in errored]
            entry = {"n": len(ok), "errors": len(errored), "skipped": len(skipped),
                     "error_cells": error_cells,
                     "errors_on_complete_passes": sum(1 for c in error_cells if c["pass"] in complete),
                     "median": median(scores), "max": max(scores) if scores else None,
                     "median_model_total": median([float(r.get("model_total") or 0) for r in ok]),
                     "zeroed_steps": sum(int(r.get("zeroed") or 0) for r in ok)}
            if probe in BATTERY or probe in POSITIVE:
                op, threshold = (BATTERY.get(probe) or POSITIVE[probe])
                fails = [{"exam": r["exam"], "pass": r.get("pass", 0), "score": r["total"]} for r in ok
                         if violates(op, threshold, float(r["total"]))]
                entry.update(role="battery" if probe in BATTERY else "positive_control",
                             criterion=f"{op} {threshold}", fails=len(fails), fail_cells=fails)
                if probe in POSITIVE and unit == "rating":
                    entry["role"] = "positive_control_descriptive"
            else:
                drops, deviations = [], []
                for r in ok:
                    ref = cells.get((r["exam"], "musterloesung", int(r.get("pass") or 0)))
                    if ref and ref.get("total") is not None:
                        drop = float(ref["total"]) - float(r["total"])
                        drops.append(drop)
                        expected = (r.get("probe_meta") or {}).get("expected_drop")
                        if expected is not None:
                            deviations.append(drop - float(expected))
                entry.update(role="descriptive", drops=drops, median_drop=median(drops),
                             expected_drop=median([float((r.get("probe_meta") or {}).get("expected_drop"))
                                                   for r in ok if (r.get("probe_meta") or {}).get("expected_drop") is not None]),
                             median_drop_minus_expected=median(deviations))
            if d1_product:
                old = (published.get(judge) or {}).get(probe) or {}
                entry["published"] = {"n_passes": old.get("n_passes"), "fails": old.get("n_fail_passes"),
                                      "median": old.get("median")}
            per[probe] = entry
        battery = [per[p] for p in required if p in BATTERY]
        clean = all(x["fails"] == 0 and x["errors"] == 0 for x in battery)
        verdict = {"battery": "pass" if battery and clean and not missing else "fail",
                   "complete": not missing, "missing": missing, "exams": exams, "passes": passes,
                   "complete_passes": complete, "incomplete_passes": incomplete,
                   "coverage": coverage, "rubric_by_exam": rubric_by_exam.get(lab, {}),
                   "instrument_conflicts": conflicts.get(lab, [])}
        clean_complete = all(x["fails"] == 0 and x["errors_on_complete_passes"] == 0 for x in battery)
        over_complete = {"passes": complete,
                         "battery": "pass" if battery and complete and clean_complete else "fail",
                         "errors_discounted": sum(x["errors"] - x["errors_on_complete_passes"] for x in battery)}
        if "musterloesung" in per:
            ml = per["musterloesung"]
            verdict["positive_control"] = ("descriptive" if unit == "rating" else
                                           "pass" if ml["fails"] == 0 and ml["errors"] == 0 and ml["n"] else "fail")
            over_complete["positive_control"] = (
                "descriptive" if unit == "rating" else
                "pass" if ml["fails"] == 0 and ml["errors_on_complete_passes"] == 0 and ml["n"] and complete
                else "fail")
        verdict["over_complete_passes"] = over_complete
        result[lab] = {**verdict, "probes": per}
        failed = verdict["battery"] == "fail" or verdict.get("positive_control") == "fail"
        worst = max(worst, 2 if missing else (1 if failed else 0))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"phase": args.phase, "gate_schema": GATE_SCHEMA,
                               "criteria": {"battery": BATTERY, "positive_control": POSITIVE,
                                            "descriptive": DESCRIPTIVE, "excluded": EXCLUDED},
                               "code_version": code_version, "input": str(inp), "filter": stats,
                               "required_types": required, "per_battery": result},
                              indent=1, ensure_ascii=False) + "\n")

    print(f"phase {args.phase}, code version {code_version}: {stats['kept']} rows used; left out: "
          f"{stats['other_code_versions']} from other code versions, {stats['dry_run_rows']} dry-run rows, "
          f"{copies} exact copies, {superseded} superseded, {stats['instrument_conflict_cells_dropped']} cells of "
          f"another rubric or alternatives setting; excluded (invalid probes): {stats['excluded_rows'] or 'none'}")
    fmt = lambda v: f"{v:5.1f}" if isinstance(v, (int, float)) else "    -"
    for lab, res in result.items():
        head = f"== {lab}: battery {res['battery']}"
        if "positive_control" in res:
            head += f", positive control {res['positive_control']}"
        if res["incomplete_passes"]:
            oc = res["over_complete_passes"]
            head += (f"; over complete passes {oc['passes']}: battery {oc['battery']}"
                     + (f", positive control {oc['positive_control']}" if "positive_control" in oc else ""))
        print(head + f"  ({len(res['exams'])} exams x {res['passes']} passes)")
        for probe in required:
            x = res["probes"][probe]
            if x["role"] == "descriptive":
                extra = f"  expected {fmt(x['expected_drop'])}" if x["expected_drop"] is not None else ""
                print(f"  {probe:18s} descriptive n {x['n']:2d} errors {x['errors']:2d}  median {fmt(x['median'])}  "
                      f"median drop {fmt(x['median_drop'])}{extra}")
                continue
            pub = x.get("published")
            tail = f"   | published: fails {pub['fails']}/{pub['n_passes']} median {pub['median']}" if pub else ""
            print(f"  {probe:18s} {x['role'][:9]:9s} fails {x['fails']:2d}/{x['n']:2d} errors {x['errors']:2d}  "
                  f"median {fmt(x['median'])}  max {fmt(x['max'])}  model-proposed median {fmt(x['median_model_total'])}  "
                  f"zeroed {x['zeroed_steps']:3d}{' skipped ' + str(x['skipped']) if x['skipped'] else ''}{tail}")
        if res["missing"]:
            shown = ", ".join(f"exam {m['exam']} {m['probe']} pass {m['pass']}" for m in res["missing"][:6])
            print(f"  MISSING {len(res['missing'])} cells: {shown}{' ...' if len(res['missing']) > 6 else ''}")
        for c in res["instrument_conflicts"]:
            print(f"  exam {c['exam']}: used rubric {c['used']['rubric_id']} ({c['used']['alternatives']}); dropped "
                  + ", ".join(f"{d['rubric_id']} ({d['alternatives']}, {d['cells_dropped']} cells)" for d in c["dropped"]))
    print(f"-> {out}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
