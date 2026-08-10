#!/usr/bin/env python3
"""Score the probe battery against its pre-registered criteria (WP2.4).

Negative criteria (DESIGN.md 2026-08-06, fixed before dispatch): repetition
< 5 on every pass, empty = 0 on every pass, offtopic ≤ 10 on every pass.
Positive control (DESIGN.md 2026-08-09, fixed before dispatch):
musterloesung ≥ 70 on every pass. A judge passes the (negative) battery iff
all three negative criteria hold on all 15 exams on all its passes; the
positive control is reported separately per judge × arm. Severity
distributions (median / p95 / max) accompany every fail count so `fail(N)`
is interpretable (reviewer round 2).

Arms (2026-08-09, arm-aware):
  tailored  probe_results.jsonl (+ probe_results_musterloesung.jsonl),
            guarded against clone_d6_actives.json
  fewshot   fewshot_probe_results.jsonl, guarded against
            fewshot/selection.json (the seeded few-shot draw)
  holistic  holistic_probe_results.jsonl (falloesung metric, no rubric)

Missing arm files are skipped with a note so the script runs before the
holistic extraction lands.

Output: data/processed/probe_stats.json + console summary. Backward-compat:
top-level `per_judge` remains the TAILORED arm's negative battery (the
manuscript's Table 3 column); the full arm-aware picture lives under `arms`.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "probe_stats.json"

CRITERIA = {"repetition": ("lt", 5.0), "empty": ("eq", 0.0),
            "offtopic": ("le", 10.0), "musterloesung": ("ge", 70.0)}
NEGATIVE_TYPES = ("repetition", "empty", "offtopic")


def violates(ptype, score):
    op, thr = CRITERIA[ptype]
    if op == "lt":
        return not (score < thr)
    if op == "eq":
        return score != thr
    if op == "ge":
        return not (score >= thr)
    return not (score <= thr)


def p95(scores):
    s = sorted(scores)
    if len(s) == 1:
        return s[0]
    k = 0.95 * (len(s) - 1)
    lo = int(k)
    frac = k - lo
    return s[lo] if lo + 1 >= len(s) else s[lo] + frac * (s[lo + 1] - s[lo])


def load_rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def guard_d6(rows):
    d6 = json.loads((INTERIM / "clone_d6_actives.json").read_text())
    bad = [r for r in rows if r.get("rubric_id") != d6.get(r["task_id"])]
    assert not bad, f"{len(bad)} rows judged under a non-D6 rubric"
    return rows


def guard_fewshot(rows):
    sel = json.loads((INTERIM / "fewshot" / "selection.json").read_text())
    drawn = {s["task_id"]: s["rubric_id"] for s in sel["selection"]}
    bad = [r for r in rows if r.get("rubric_id") != drawn.get(r["task_id"])]
    assert not bad, f"{len(bad)} rows judged under a non-drawn few-shot rubric"
    return rows


def summarize(rows):
    """per judge: per probe-type severity + negative-battery verdict +
    positive-control verdict."""
    per_judge = defaultdict(lambda: defaultdict(lambda: {
        "scores": [], "n_fail_passes": 0, "fail_exams": set()}))
    for r in rows:
        if r.get("error") or r.get("total_score") is None:
            raise SystemExit(f"errored/scoreless probe row: {r['pick_id']} {r['judge_model_id']}")
        ptype = r["provenance"]
        s = float(r["total_score"])
        d = per_judge[r["judge_model_id"]][ptype]
        d["scores"].append(s)
        if violates(ptype, s):
            d["n_fail_passes"] += 1
            d["fail_exams"].add(r["pick_id"])

    out = {}
    for judge in sorted(per_judge):
        entry = {}
        neg_fail = 0
        for ptype in CRITERIA:
            d = per_judge[judge].get(ptype)
            if d is None:
                continue
            entry[ptype] = {
                "n_passes": len(d["scores"]),
                "mean": round(statistics.mean(d["scores"]), 2),
                "median": round(statistics.median(d["scores"]), 2),
                "p95": round(p95(d["scores"]), 2),
                "max": max(d["scores"]),
                "min": min(d["scores"]),
                "n_fail_passes": d["n_fail_passes"],
                "fail_probes": sorted(d["fail_exams"]),
            }
            if ptype in NEGATIVE_TYPES:
                neg_fail += d["n_fail_passes"]
        if any(t in entry for t in NEGATIVE_TYPES):
            entry["battery"] = "pass" if neg_fail == 0 else f"fail({neg_fail})"
        if "musterloesung" in entry:
            m = entry["musterloesung"]
            entry["positive_control"] = ("pass" if m["n_fail_passes"] == 0
                                         else f"fail({m['n_fail_passes']})")
        out[judge] = entry
    return out


def main() -> int:
    arms = {}

    tail_rows = guard_d6(load_rows(INTERIM / "probe_results.jsonl"))
    tail_pos = INTERIM / "probe_results_musterloesung.jsonl"
    if tail_pos.exists():
        tail_rows = tail_rows + guard_d6(load_rows(tail_pos))
    else:
        print(f"note: {tail_pos.name} not found — tailored arm scored without positive control")
    arms["tailored"] = summarize(tail_rows)

    fs_path = INTERIM / "fewshot_probe_results.jsonl"
    if fs_path.exists():
        arms["fewshot"] = summarize(guard_fewshot(load_rows(fs_path)))
    else:
        print(f"note: {fs_path.name} not found — few-shot arm skipped")

    hol_path = INTERIM / "holistic_probe_results.jsonl"
    if hol_path.exists():
        arms["holistic"] = summarize(load_rows(hol_path))
    else:
        print(f"note: {hol_path.name} not found — holistic arm skipped")

    payload = {
        "criteria": {"repetition": "< 5 on every pass", "empty": "= 0 on every pass",
                     "offtopic": "<= 10 on every pass",
                     "musterloesung": ">= 70 on every pass (positive control)",
                     "preregistered": "negatives: DESIGN.md 2026-08-06; positive control "
                                      "+ holistic arm: DESIGN.md 2026-08-09 — both before dispatch",
                     "battery_verdict": "negative probes only (comparable to the published "
                                        "fail counts); positive_control reported separately"},
        "n_probes": 45,
        "per_judge": {j: {k: v for k, v in e.items() if k in
                          (*NEGATIVE_TYPES, "battery")}
                      for j, e in arms["tailored"].items()},
        "arms": arms,
    }

    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.name}")
    for arm, judges in arms.items():
        print(f"\n[{arm}]")
        print(f"{'judge':30s} {'battery':10s} {'pos.ctrl':10s} "
              f"{'rep med/p95/max':>16s} {'empty med/p95/max':>18s} {'offt med/p95/max':>17s}")
        for judge, e in judges.items():
            def fmt(t):
                d = e.get(t)
                return f"{d['median']:.0f}/{d['p95']:.0f}/{d['max']:.0f}" if d else "-"
            print(f"{judge.split('/')[-1]:30s} {e.get('battery', '-'):10s} "
                  f"{e.get('positive_control', '-'):10s} "
                  f"{fmt('repetition'):>16s} {fmt('empty'):>18s} {fmt('offtopic'):>17s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
