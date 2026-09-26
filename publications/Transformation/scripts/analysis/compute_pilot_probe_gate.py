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

A battery is one judge on one instrument: the product lane, a checklist unit
(D1) or an arm (D2), and the total_mode. Its verdict is "pass" only when
every battery probe passes on every expected exam and pass with no errors,
and no cell is missing. Completeness is checked against the expected exam
list (D1: the exams of probe_texts.json; D2: the D2 exam; or --exams).

Rows: copies of the same judgment are counted once, the latest row per cell
wins, dry-run rows never count, and rows are filtered by code version (the
content hash of the instrument modules, provenance.code_version; default the
newest; --code-version any for legacy rows without provenance). The D1
product-lane batteries show the same judge's published result (tailored arm
of data/processed/probe_stats.json) next to it.

Exit codes: 0 every battery passes; 1 a battery fails on scores or errors;
2 a battery is incomplete or no rows match.

Output: <data root>/interim/pilot/gate.json (git-ignored) + console table.
The data root comes from scripts/local_config.py.
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
from pilot_rows import distinct_rows, is_dry, latest_per_cell, load_rows

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


def violates(op: str, threshold: float, score: float) -> bool:
    return {"lt": not score < threshold, "eq": score != threshold, "le": not score <= threshold,
            "ge": not score >= threshold}[op]


def label(row: dict) -> str:
    config = row.get("arm_config") or {}
    mode = config.get("total_mode")
    tail = f" total_mode={mode}" if mode else ""
    if row.get("arm"):  # d2-probes: one battery per judge and instrument
        return f"{row['judge']} [{row['arm']}]{tail}"
    if (row.get("lane") or "product") == "product":
        return f"{row['judge']}{tail}"
    return f"{row['judge']} [checklist:{row.get('unit')}]{tail}"


def cell_key(row: dict) -> tuple:
    return (label(row), row["exam"], row["probe"], int(row.get("pass") or 0))


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


def main() -> int:
    data = local_config.data_root()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--phase", choices=tuple(INPUTS), default="probes", help="which pilot rows (default: D1 probes)")
    parser.add_argument("--in", dest="inp", type=Path, default=None, help="rows file (default: by --phase)")
    parser.add_argument("--out", type=Path, default=data / "interim" / "pilot" / "gate.json")
    parser.add_argument("--code-version", default=None, help="provenance code version; 'any' for legacy rows")
    parser.add_argument("--types", nargs="*", default=list(DEFAULT_TYPES), help="probe types every battery must have")
    parser.add_argument("--exams", nargs="*", default=None, help="expected exams (default: by --phase)")
    parser.add_argument("--passes", type=int, default=None, help="passes every battery must have (default: most seen)")
    args = parser.parse_args()
    inp = args.inp or data.joinpath(*INPUTS[args.phase])
    required = [t for t in args.types if t not in EXCLUDED]
    unknown = [t for t in required if t not in DEFAULT_TYPES]
    if unknown:
        parser.error(f"unknown probe types {unknown}")

    raw = [r for r in load_rows([inp]) if r.get("kind") != "coverage" and r.get("probe")]
    rows, copies = distinct_rows(raw)
    excluded = [r for r in rows if r["probe"] in EXCLUDED or r.get("probe_valid") is False]
    rows = [r for r in rows if not (r["probe"] in EXCLUDED or r.get("probe_valid") is False)]
    rows, code_version, stats = filter_version(rows, args.code_version)
    stats.update(exact_copies_dropped=copies,
                 excluded_rows={p: sum(1 for r in excluded if r["probe"] == p) for p in sorted({r["probe"] for r in excluded})})
    if not rows:
        print(f"no rows for code version {code_version} in {inp} ({stats})")
        return 2
    latest, superseded = latest_per_cell(rows, cell_key)
    stats["superseded_rows"] = superseded
    exams = expected_exams(args.phase, data, args.exams)
    published = (json.loads(PUBLISHED.read_text()).get("arms") or {}).get("tailored") or {} if PUBLISHED.exists() else {}

    by_label: dict[str, dict] = defaultdict(dict)
    for (lab, exam, probe, k), row in latest.items():
        by_label[lab][(exam, probe, k)] = row

    result, worst = {}, 0
    for lab, cells in sorted(by_label.items()):
        first = next(iter(cells.values()))
        judge, unit = first["judge"], first.get("unit")
        d1_product = (first.get("lane") or "product") == "product" and not first.get("arm")
        passes = args.passes or (max(k for _, _, k in cells) + 1)
        missing = [{"exam": e, "probe": p, "pass": k} for e in exams for p in required for k in range(passes)
                   if (e, p, k) not in cells or (cells[(e, p, k)].get("skipped") and p in BATTERY)]
        coverage = {str(e): {p: ("scored" if (e, p, 0) in cells and not cells[(e, p, 0)].get("skipped")
                                 else "skipped" if (e, p, 0) in cells else "missing") for p in required}
                    for e in exams}
        per = {}
        for probe in required:
            present = [cells[(e, probe, k)] for e in exams for k in range(passes) if (e, probe, k) in cells]
            skipped = [r for r in present if r.get("skipped")]
            scored = [r for r in present if not r.get("skipped")]
            ok = [r for r in scored if r.get("total") is not None]
            scores = [float(r["total"]) for r in ok]
            entry = {"n": len(ok), "errors": len(scored) - len(ok), "skipped": len(skipped),
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
                   "coverage": coverage}
        if "musterloesung" in per:
            ml = per["musterloesung"]
            verdict["positive_control"] = ("descriptive" if unit == "rating" else
                                           "pass" if ml["fails"] == 0 and ml["errors"] == 0 and ml["n"] else "fail")
        result[lab] = {**verdict, "probes": per}
        worst = max(worst, 2 if missing else (1 if verdict["battery"] == "fail" else 0))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"criteria": {"battery": BATTERY, "positive_control": POSITIVE,
                                                 "descriptive": DESCRIPTIVE, "excluded": EXCLUDED},
                                    "code_version": code_version, "input": str(inp), "filter": stats,
                                    "required_types": required, "per_battery": result},
                                   indent=1, ensure_ascii=False) + "\n")

    print(f"code version {code_version}: {stats['kept']} rows used; left out: {stats['other_code_versions']} from other "
          f"code versions, {stats['dry_run_rows']} dry-run rows, {copies} exact copies, {superseded} superseded; "
          f"excluded (invalid probes): {stats['excluded_rows'] or 'none'}")
    fmt = lambda v: f"{v:5.1f}" if isinstance(v, (int, float)) else "    -"
    for lab, res in result.items():
        head = f"== {lab}: battery {res['battery']}"
        if "positive_control" in res:
            head += f", positive control {res['positive_control']}"
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
    print(f"-> {args.out}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
