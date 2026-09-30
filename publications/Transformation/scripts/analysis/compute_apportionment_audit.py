#!/usr/bin/env python3
"""Audit the weight -> point apportionment of the 170 generated rubrics.

The generator states relative step weights; code apportions exactly 100
points with a floor of 1 per step. The as-run routine floored first and then
ranked the remainders of the UNFLOORED quotas, so a step pinned to the floor
(quota < 1) could win a second point and outrank a heavier step. This script
quantifies that defect on the rubrics the study used and compares the
as-run result with three alternatives:

  as_run            the stored derived points (reproduced here by
                    ``legacy_apportion`` as a guard)
  hamilton_floor    floor-constrained largest remainder (pin, re-quota,
                    repeat), integer points  -- the corrected routine
  webster_floor     Sainte-Lague/Webster divisor method with the same floor
  hamilton_half     floor-constrained largest remainder on the half-point
                    grid (200 half-units, floor 0.5 points)

Per method: steps outside their fair range (quota rule), order-inversion
pairs (lighter step gets more points), pairs of distinct weights that
collapse to equal points, relative rounding error, and steps whose points
differ from the as-run result. Also reports which of the D6-drawn (judged)
rubrics are affected and the stated weight sums.

Inputs: data/raw/local/task_rubrics.json (withheld), data/interim/
        active_rubric_selection.json.
Output: data/processed/apportionment_audit.json
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
RAW = HERE / "data" / "raw" / "local" / "task_rubrics.json"
SELECTION = HERE / "data" / "interim" / "active_rubric_selection.json"
OUT = HERE / "data" / "processed" / "apportionment_audit.json"
TOTAL = 100


def legacy_apportion(weights, total, floor=1):
    """The as-run routine, kept verbatim to prove it reproduces the data."""
    n = len(weights)
    w = [max(float(x), 0.0) for x in weights]
    if sum(w) <= 0:
        w = [1.0] * n
    s = sum(w)
    scaled = [x * total / s for x in w]
    pts = [max(int(x), floor) for x in scaled]
    remainders = [(scaled[i] - int(scaled[i]), -i) for i in range(n)]
    delta = total - sum(pts)
    order = sorted(range(n), key=lambda i: remainders[i], reverse=(delta > 0))
    guard = 0
    while delta != 0 and guard < 10 * n * max(total, 1):
        idx = order[guard % n]
        step = 1 if delta > 0 else -1
        if pts[idx] + step >= floor:
            pts[idx] += step
            delta -= step
        guard += 1
    return pts


def hamilton_floor(weights, total, floor=1):
    """Floor-constrained largest remainder (mirrors the corrected generator)."""
    n = len(weights)
    w = [max(float(x), 0.0) for x in weights]
    if sum(w) <= 0:
        w = [1.0] * n
    pinned = set()
    while True:
        free = [i for i in range(n) if i not in pinned]
        rest = total - floor * len(pinned)
        s = sum(w[i] for i in free)
        below = [i for i in free if w[i] * rest / s < floor]
        if not below:
            break
        pinned.update(below)
    quota = {i: w[i] * rest / s for i in free}
    pts = [floor] * n
    for i in free:
        pts[i] = int(quota[i])
    leftover = rest - sum(pts[i] for i in free)
    for i in sorted(free, key=lambda i: (-(quota[i] - int(quota[i])), i))[:leftover]:
        pts[i] += 1
    return pts


def webster_floor(weights, total, floor=1):
    lo, hi = 1e-9, float(sum(weights))
    pts = None
    for _ in range(200):
        d = (lo + hi) / 2
        pts = [max(floor, math.floor(x / d + 0.5)) for x in weights]
        s = sum(pts)
        if s > total:
            lo = d
        elif s < total:
            hi = d
        else:
            break
    while sum(pts) < total:
        i = max(range(len(weights)), key=lambda i: weights[i] / (pts[i] + 0.5))
        pts[i] += 1
    while sum(pts) > total:
        i = min((i for i in range(len(weights)) if pts[i] > floor),
                key=lambda i: weights[i] / (pts[i] - 0.5))
        pts[i] -= 1
    return pts


def hamilton_half(weights, total, floor=1):
    return [u / 2 for u in hamilton_floor(weights, 2 * total, floor)]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main() -> int:
    rubrics = [r for r in json.loads(RAW.read_text())
               if (r.get("generation_metadata") or {}).get("derived_document")]
    drawn_text = SELECTION.read_text() if SELECTION.exists() else ""

    docs = []
    for r in rubrics:
        gm = r["generation_metadata"]
        full = [s for a in gm["full_document"]["abschnitte"] for s in a["schritte"]]
        derived = [s for a in gm["derived_document"]["abschnitte"] for s in a["schritte"]]
        weights = [float(s["gewicht"]) for s in full]
        stored = [s["max_punkte"] for s in derived]
        if legacy_apportion(weights, TOTAL) != stored:
            raise SystemExit(f"legacy routine does not reproduce rubric {r['id']}")
        docs.append({"id": r["id"], "generator": r.get("generator_model_id"),
                     "weights": weights, "stored": stored, "drawn": r["id"] in drawn_text})

    methods = {
        "as_run": lambda w: legacy_apportion(w, TOTAL),
        "hamilton_floor": lambda w: hamilton_floor(w, TOTAL),
        "webster_floor": lambda w: webster_floor(w, TOTAL),
        "hamilton_half": lambda w: hamilton_half(w, TOTAL),
    }
    result = {}
    affected = {}
    for name, fn in methods.items():
        outside = inversions = collapsed = changed = 0
        inversion_rubrics, outside_rubrics = set(), set()
        rel = []
        for d in docs:
            w, pts = d["weights"], fn(d["weights"])
            assert abs(sum(pts) - TOTAL) < 1e-9
            s = sum(w)
            quota = [x * TOTAL / s for x in w]
            # The configured floor, NOT min(pts): in 8 rubrics the as-run
            # routine lifted every small step to 2, so min(pts) hides them.
            grid = 0.5 if name == "hamilton_half" else 1.0
            floor_pts = 0.5 if name == "hamilton_half" else 1.0
            for i in range(len(w)):
                lo = math.floor(quota[i] / grid) * grid
                hi = math.ceil(quota[i] / grid) * grid
                pinned_ok = quota[i] < floor_pts and pts[i] == floor_pts
                if not (lo - 1e-9 <= pts[i] <= hi + 1e-9) and not pinned_ok:
                    outside += 1
                    outside_rubrics.add(d["id"])
                rel.append(abs(pts[i] - quota[i]) / quota[i])
            inv = sum(1 for i in range(len(w)) for j in range(len(w))
                      if w[i] < w[j] and pts[i] > pts[j])
            if inv:
                inversions += inv
                inversion_rubrics.add(d["id"])
            collapsed += sum(1 for i in range(len(w)) for j in range(i + 1, len(w))
                             if w[i] != w[j] and pts[i] == pts[j])
            changed += sum(1 for a, b in zip(pts, d["stored"]) if a != b)
        result[name] = {
            "steps_outside_fair_range": outside,
            "rubrics_outside_fair_range": len(outside_rubrics),
            "order_inversion_pairs": inversions,
            "rubrics_with_inversion": len(inversion_rubrics),
            "collapsed_distinct_weight_pairs": collapsed,
            "rel_error_median": round(statistics.median(rel), 4),
            "rel_error_p95": round(pct(rel, 0.95), 4),
            "rel_error_max": round(max(rel), 4),
            "steps_changed_vs_as_run": changed,
        }
        if name == "as_run":
            affected = {"rubrics": sorted(outside_rubrics | inversion_rubrics)}

    by_id = {d["id"]: d for d in docs}
    per_gen = defaultdict(Counter)
    for d in docs:
        per_gen[d["generator"]]["rubrics"] += 1
        per_gen[d["generator"]]["sum_exactly_100"] += sum(d["weights"]) == TOTAL
        per_gen[d["generator"]]["affected"] += d["id"] in affected["rubrics"]
    sums = [sum(d["weights"]) for d in docs]
    out = {
        "note": "Apportionment audit over the generated rubrics; as_run = stored points, "
                "reproduced exactly by the legacy routine.",
        "n_rubrics": len(docs),
        "n_steps": sum(len(d["weights"]) for d in docs),
        "methods": result,
        "affected_rubrics": len(affected["rubrics"]),
        "affected_drawn_rubrics": [i for i in affected["rubrics"] if by_id[i]["drawn"]],
        "weight_sums": {"min": min(sums), "median": statistics.median(sums), "max": max(sums),
                        "exactly_100": sum(1 for s in sums if s == TOTAL)},
        "per_generator": {g: dict(c) for g, c in sorted(per_gen.items())},
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print(f"{out['n_rubrics']} rubrics, {out['n_steps']} steps; weight sums "
          f"{out['weight_sums']['min']:.0f}-{out['weight_sums']['max']:.0f}, "
          f"{out['weight_sums']['exactly_100']} exactly 100")
    for name, m in result.items():
        print(f"  {name:15s} outside {m['steps_outside_fair_range']:3d} steps "
              f"({m['rubrics_outside_fair_range']} rubrics), inversions "
              f"{m['order_inversion_pairs']:3d} ({m['rubrics_with_inversion']} rubrics), "
              f"collapsed {m['collapsed_distinct_weight_pairs']:4d}, rel.err p95 "
              f"{m['rel_error_p95']:.3f} max {m['rel_error_max']:.2f}, changed "
              f"{m['steps_changed_vs_as_run']}")
    print(f"  affected rubrics: {out['affected_rubrics']}, of them drawn/judged: "
          f"{len(out['affected_drawn_rubrics'])}")
    print(f"-> {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
