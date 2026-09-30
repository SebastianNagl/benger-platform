#!/usr/bin/env python3
"""The crossed variance study on the expert exam (E1, RQ1).

Reads the d2-judge rows (git-ignored) of the pinned judge code versions and
the D2 pack, and writes aggregates only to data/processed/cslaw/d2_variance.json.
Every script counts, graded or not: variance needs no human grade.

Per judge and instrument (no sheet, the expert sheet, each generated sheet)
on the scripts that have at least two passes:

- pass variance: the pooled within-script variance over passes;
- for a generator with two or more sheets on the same scripts: the sheet
  variance (between-sheet variance of the per-script sheet means minus the
  pass variance over the passes per sheet), i.e. what a freshly generated
  sheet adds for a given script;
- script variance (the spread of the true scores between scripts);
- dependability for an absolute decision at the pass mark (phi = script
  variance / (script variance + error variance), where the error of one
  judgment is the pass variance for a fixed instrument and pass + sheet
  variance for a freshly generated sheet);
- how often a second judgment falls on the other side of the pass mark:
  over pairs of passes on one instrument, and over pairs of sheets from one
  generator;
- the equal-cost comparison: the SD of one judgment with a generated sheet
  against the SD of the mean of k passes without a sheet, with the cost of
  each from the metered calls.

Per-script values stay in memory; the output holds aggregates only.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]
import local_config
from d2_labels import (
    D2_CODE_VERSIONS,
    arm_label,
    is_numbered_sheet,
    rubric_labels,
)

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
ROWS = DATA / "interim" / "human" / "pilot" / "d2-judge.jsonl"
PACK = DATA / "interim" / "human" / "heidebach_scripts.json"
OUT = HERE / "data" / "processed" / "cslaw" / "d2_variance.json"
LABELS = rubric_labels(DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl")
PASS_MARK = 40.0
MAX_K = 5


def usd(row: dict) -> float:
    return sum(float(c.get("usd") or 0) for c in row.get("calls") or [])


def load(versions: list[str]) -> dict:
    """judge -> label -> version -> script -> {pass: (total, usd)}; newest row per cell."""
    pack = {s["script_id"]: s for s in json.loads(PACK.read_text(encoding="utf-8"))}
    cells: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
    stamp: dict = {}
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        prov = r.get("provenance") or {}
        if prov.get("dry_run") or r.get("total") is None or prov.get("code_version") not in versions:
            continue
        script = pack.get(r.get("script_id")) or {}
        if script.get("exclude_reason") or script.get("duplicate_of"):
            continue
        key = (r["judge"], arm_label(r["arm"], LABELS), prov["code_version"], r["script_id"], r.get("pass"))
        if key in stamp and str(r.get("ts") or "") < stamp[key]:
            continue
        stamp[key] = str(r.get("ts") or "")
        cells[key[0]][key[1]][key[2]][key[3]][key[4]] = (float(r["total"]), usd(r))
    return cells


def newest(by_version: dict, versions: list[str]) -> tuple[str, dict] | tuple[None, None]:
    for v in versions:
        if by_version.get(v):
            return v, by_version[v]
    return None, None


def repeated(scripts: dict) -> dict[str, list[float]]:
    """Scripts with >= 2 passes -> their totals."""
    return {s: [t for t, _ in passes.values()] for s, passes in scripts.items() if len(passes) >= 2}


def flip_rate(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return statistics.fmean((a >= PASS_MARK) != (b >= PASS_MARK) for a, b in pairs)


def instrument_block(scripts: dict) -> dict | None:
    rep = repeated(scripts)
    if len(rep) < 3:
        return None
    pass_var = statistics.fmean(statistics.variance(v) for v in rep.values())
    k = statistics.harmonic_mean([len(v) for v in rep.values()])
    means = [statistics.fmean(v) for v in rep.values()]
    script_var = max(0.0, statistics.variance(means) - pass_var / k)
    pairs = [(a, b) for v in rep.values() for a, b in itertools.combinations(v, 2)]
    calls = [c for passes in scripts.values() for _, c in passes.values()]
    return {
        "n_scripts": len(rep), "passes": round(k, 2),
        "pass_sd": round(math.sqrt(pass_var), 2),
        "script_sd": round(math.sqrt(script_var), 2),
        "phi_one_pass": round(script_var / (script_var + pass_var), 3) if script_var + pass_var else None,
        "pass_flip_rate": round(flip_rate(pairs), 3) if pairs else None,
        "mean_total": round(statistics.fmean(means), 2),
        "usd_per_call": round(statistics.fmean(calls), 4) if calls else None,
        "_pass_var": pass_var, "_script_var": script_var,
    }


def sheet_block(sheets: dict[str, dict]) -> dict | None:
    """Two or more sheets of one generator on the same scripts."""
    reps = {name: repeated(s) for name, s in sheets.items()}
    common = sorted(set.intersection(*(set(r) for r in reps.values()))) if reps else []
    if len(reps) < 2 or len(common) < 3:
        return None
    pass_var = statistics.fmean(statistics.variance(reps[n][s]) for n in reps for s in common)
    k = statistics.harmonic_mean([len(reps[n][s]) for n in reps for s in common])
    sheet_means = {s: [statistics.fmean(reps[n][s]) for n in reps] for s in common}
    within = statistics.fmean(statistics.variance(v) for v in sheet_means.values())
    sheet_var = max(0.0, within - pass_var / k)
    grand = [statistics.fmean(v) for v in sheet_means.values()]
    script_var = max(0.0, statistics.variance(grand) - within / len(reps))
    # a sheet's mean shift across all scripts (level) vs its script-specific part
    level = [statistics.fmean(statistics.fmean(reps[n][s]) for s in common) for n in reps]
    level_var = max(0.0, statistics.variance(level) - within / len(common))
    cross = [(a, b) for s in common for n1, n2 in itertools.combinations(reps, 2)
             for a in reps[n1][s] for b in reps[n2][s]]
    error = sheet_var + pass_var
    return {
        "n_sheets": len(reps), "n_scripts": len(common),
        "pass_sd": round(math.sqrt(pass_var), 2),
        "sheet_sd": round(math.sqrt(sheet_var), 2),
        "sheet_level_sd": round(math.sqrt(level_var), 2),
        "script_sd": round(math.sqrt(script_var), 2),
        "sd_one_judgment_fresh_sheet": round(math.sqrt(error), 2),
        "phi_fresh_sheet_one_pass": round(script_var / (script_var + error), 3) if script_var + error else None,
        "sheet_flip_rate": round(flip_rate(cross), 3) if cross else None,
        "_error_var": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--code-versions", default=",".join(D2_CODE_VERSIONS))
    args = parser.parse_args()
    versions = [v for v in args.code_versions.split(",") if v]
    cells = load(versions)
    out: dict = {"note": ("Crossed variance study on the expert exam (all scripts with >= 2 passes; no human "
                          "grades needed). Aggregates only."),
                 "pass_mark_be": PASS_MARK, "code_versions": versions, "per_judge": {}}
    for judge, labels in sorted(cells.items()):
        per: dict = {"instruments": {}, "generators": {}, "equal_cost": {}}
        chosen: dict[str, dict] = {}
        for label, by_version in sorted(labels.items()):
            version, scripts = newest(by_version, versions)
            block = instrument_block(scripts) if scripts else None
            if block:
                chosen[label] = scripts
                per["instruments"][label] = {"code_version": version,
                                             **{k: v for k, v in block.items() if not k.startswith("_")}}
        groups: dict[tuple[str, str], dict] = defaultdict(dict)
        for label, scripts in chosen.items():
            if is_numbered_sheet(label):
                sheet_part, unit = label.split(":", 1)
                gen, sheet = sheet_part.rsplit(" sheet ", 1)
                groups[(gen, unit)][sheet] = scripts
        for (gen, unit), sheets in sorted(groups.items()):
            block = sheet_block(sheets)
            if block:
                per["generators"][f"{gen}:{unit}"] = {k: v for k, v in block.items() if not k.startswith("_")}
        # equal cost: mean of k no-sheet passes vs one judgment with a fresh generated sheet
        hol = per["instruments"].get("no sheet:holistic")
        if hol:
            hol_var = hol["pass_sd"] ** 2
            per["equal_cost"]["no_sheet_mean_of_k"] = {
                str(k): {"sd": round(math.sqrt(hol_var / k), 2),
                         "usd": round(k * hol["usd_per_call"], 4) if hol["usd_per_call"] is not None else None}
                for k in range(1, MAX_K + 1)}
        out["per_judge"][judge] = per
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for judge, per in out["per_judge"].items():
        print(f"== {judge}")
        for label, b in per["instruments"].items():
            print(f"  {label:34.34s} n={b['n_scripts']:2d} k={b['passes']} pass SD {b['pass_sd']:5.2f} "
                  f"script SD {b['script_sd']:5.2f} phi {b['phi_one_pass']} flips {b['pass_flip_rate']} "
                  f"${b['usd_per_call']}")
        for gen, b in per["generators"].items():
            print(f"  sheets {gen}: {b}")
        if per["equal_cost"]:
            print(f"  equal cost (no sheet, mean of k): {per['equal_cost']['no_sheet_mean_of_k']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
