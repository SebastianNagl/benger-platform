#!/usr/bin/env python3
"""Does the automated audit score predict downstream grading utility? (WP3.3)

The manuscript asserts qualitatively that audit plausibility does not
predict grading outcome — this script puts numbers on it: per-rubric
correlations between the 7-dimension automated audit total (auditor
gpt-5.4-mini, audit_results.jsonl, 170 rubrics) and the crossed-sweep
outcomes (rubric_outcomes.json: per-rubric MAE, repeat SD, bias under the
Luna lens), raw and within-exam centered, with exam-level cluster
bootstrap CIs. Audit rubric ids live in the SOURCE project, outcome ids
in the clone — the join runs on (task, generator), which is unique and
covers 170/170 (re-asserted here).

Inputs: data/interim/audit_results.jsonl, data/processed/rubric_outcomes.json,
        picks.json + picks_temp0.json (source->clone task map)
Output: data/processed/audit_outcome_link.json
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
OUT = HERE / "data" / "processed" / "audit_outcome_link.json"

SEED = 20260806
N_BOOT = 10_000


def main() -> int:
    src = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks.json"))["resolved"]}
    clo = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks_temp0.json"))["resolved"]}
    src_to_clone = {}
    for pid, s in src.items():
        src_to_clone[s] = clo[pid]

    audits = [json.loads(l) for l in (INTERIM / "audit_results.jsonl").read_text().splitlines()]
    outcomes = json.loads((HERE / "data" / "processed" / "rubric_outcomes.json").read_text())
    per_rubric = outcomes["luna"]["per_rubric"]

    out_by_key = {}
    for r in per_rubric:
        key = (r["task_id"], r["generator_model_id"])
        assert key not in out_by_key, f"non-unique outcome key {key}"
        out_by_key[key] = r

    rows = []
    for a in audits:
        clone_task = src_to_clone[a["task_id"]]
        key = (clone_task, a["generator_model_id"])
        o = out_by_key.get(key)
        assert o is not None, f"no outcome for audit key {key}"
        rows.append({
            "exam": clone_task,
            "generator_model_id": a["generator_model_id"],
            "self_audit": a.get("self_audit", False),
            "audit_total": float(a["total_score"]),
            "audit_scores": a.get("scores") or {},
            "mae": o.get("mae"),
            "repeat_sd": o.get("repeat_sd_mean"),
            "abs_bias": abs(o["bias"]) if o.get("bias") is not None else None,
            "steps": o.get("steps"),
        })
    assert len(rows) == 170, f"joined {len(rows)}/170"
    print(f"joined {len(rows)}/170 audit rows to outcomes")

    dims = sorted({d for r in rows for d in r["audit_scores"]})
    by_exam = defaultdict(list)
    for r in rows:
        by_exam[r["exam"]].append(r)
    exams = sorted(by_exam)

    def centered(vals_by_exam):
        out = []
        for exam, pairs in vals_by_exam.items():
            if len(pairs) < 2:
                continue
            mx = statistics.mean(x for x, _ in pairs)
            my = statistics.mean(y for _, y in pairs)
            out.extend((x - mx, y - my) for x, y in pairs)
        return out

    def corr_pack(subset, x_fn, y_key):
        raw = [(x_fn(r), r[y_key]) for r in subset
               if x_fn(r) is not None and r.get(y_key) is not None]
        vbe = defaultdict(list)
        for r in subset:
            if x_fn(r) is not None and r.get(y_key) is not None:
                vbe[r["exam"]].append((x_fn(r), r[y_key]))
        cen = centered(vbe)

        def pack(pairs):
            if len(pairs) < 3:
                return None
            xs = [a for a, _ in pairs]; ys = [b for _, b in pairs]
            return {"n": len(pairs),
                    "pearson": float(sps.pearsonr(xs, ys).statistic),
                    "spearman": float(sps.spearmanr(xs, ys).statistic)}

        return {"raw": pack(raw), "within_exam_centered": pack(cen)}

    def boot_ci(subset, x_fn, y_key, kind):
        rng = np.random.default_rng(SEED)
        sub_by_exam = defaultdict(list)
        for r in subset:
            if x_fn(r) is not None and r.get(y_key) is not None:
                sub_by_exam[r["exam"]].append(r)
        ex = sorted(sub_by_exam)
        vals = []
        for _ in range(N_BOOT):
            draw = rng.integers(0, len(ex), size=len(ex))
            rs = [r for e in draw for r in sub_by_exam[ex[e]]]
            if kind == "raw":
                pairs = [(x_fn(r), r[y_key]) for r in rs]
            else:
                vbe = defaultdict(list)
                for r in rs:
                    vbe[id(r)] = None  # placeholder, not used
                # rebuild exam grouping within the resample (repeated exams
                # count as separate pseudo-clusters, standard cluster bootstrap)
                pairs = []
                for e in draw:
                    grp = [(x_fn(r), r[y_key]) for r in sub_by_exam[ex[e]]]
                    if len(grp) < 2:
                        continue
                    mx = statistics.mean(x for x, _ in grp)
                    my = statistics.mean(y for _, y in grp)
                    pairs.extend((x - mx, y - my) for x, y in grp)
            if len(pairs) < 3:
                continue
            xs = [a for a, _ in pairs]; ys = [b for _, b in pairs]
            if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
                continue
            vals.append(float(sps.pearsonr(xs, ys).statistic))
        return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]

    audit_total = lambda r: r["audit_total"]
    payload = {
        "seed": SEED, "n_boot": N_BOOT,
        "note": "per-rubric join on (exam task, generator); outcomes = Luna lens "
                "(rubric_outcomes.json); centered = exam means removed from both "
                "variables; CIs = exam-level cluster bootstrap on the pearson r",
        "n_rubrics": len(rows),
        "audit_total_vs": {},
        "per_dimension_vs_mae": {},
        "sensitivity_excluding_self_audit": {},
    }
    for y_key in ("mae", "repeat_sd", "abs_bias"):
        pack = corr_pack(rows, audit_total, y_key)
        pack["raw"]["ci95"] = boot_ci(rows, audit_total, y_key, "raw")
        pack["within_exam_centered"]["ci95"] = boot_ci(rows, audit_total, y_key, "centered")
        payload["audit_total_vs"][y_key] = pack
    for d in dims:
        fn = lambda r, d=d: (float(r["audit_scores"][d]) if d in r["audit_scores"] else None)
        payload["per_dimension_vs_mae"][d] = corr_pack(rows, fn, "mae")
    other = [r for r in rows if not r["self_audit"]]
    for y_key in ("mae", "repeat_sd"):
        payload["sensitivity_excluding_self_audit"][y_key] = corr_pack(other, audit_total, y_key)
    payload["sensitivity_excluding_self_audit"]["n"] = len(other)

    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k in ("audit_total_vs",)}, indent=1)[:1500])
    print(f"-> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
