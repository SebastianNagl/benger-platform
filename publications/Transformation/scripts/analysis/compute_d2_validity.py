#!/usr/bin/env python3
"""Validity on the expert exam (D2a): LLM judge totals vs the reference grades.

Reads the d2-judge rows (git-ignored, data/interim/human/pilot/d2-judge.jsonl)
and the D2 pack (data/interim/human/heidebach_scripts.json). Per judge x arm:

- n scripts, passes per script;
- MAE and mean bias (judge - reference) of the per-script mean total, with
  script-bootstrap 95 % CIs;
- Pearson r and Spearman rho;
- pass/fail agreement at the exam's pass mark (40 BE) and Cohen's kappa;
- repeat SD (mean within-script SD over passes, scripts with >= 2 passes);
- for the expert-sheet arms: per-step mean absolute difference, over the
  steps both graded, as a share of the step maximum.

Only aggregates are written (data/processed/cslaw/d2_validity.json): no
script ids, no per-script scores, no text. Excluded scripts (duplicates,
test uploads) never count. The reference grades of 9 of the 15 D2a scripts
await the exam author's confirmation of who graded them; the output says so.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts" / "analysis")]
from d2_labels import arm_label, rubric_labels  # noqa: E402
DATA = Path(os.environ.get("PILOT_DATA_ROOT") or (HERE / "data"))
ROWS = DATA / "interim" / "human" / "pilot" / "d2-judge.jsonl"
PACK = DATA / "interim" / "human" / "heidebach_scripts.json"
OUT = HERE / "data" / "processed" / "cslaw" / "d2_validity.json"
PASS_MARK = 40.0
LABELS = rubric_labels(DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl")
SEED = 20260926
N_BOOT = 4000


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if not sx or not sy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def boot_ci(pairs: list[tuple[float, float]], stat, rng: random.Random) -> list[float] | None:
    if len(pairs) < 3:
        return None
    vals = []
    for _ in range(N_BOOT):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        vals.append(stat(sample))
    vals.sort()
    return [round(vals[int(0.025 * N_BOOT)], 2), round(vals[int(0.975 * N_BOOT) - 1], 2)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rows", type=Path, default=ROWS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--code-version", default=None, help="keep only rows of this provenance code version")
    args = parser.parse_args()

    pack = {s["script_id"]: s for s in json.loads(PACK.read_text(encoding="utf-8"))}
    rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not (r.get("provenance") or {}).get("dry_run") and r.get("total") is not None]
    if args.code_version:
        rows = [r for r in rows if (r.get("provenance") or {}).get("code_version") == args.code_version]

    cells: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sid = r.get("script_id")
        script = pack.get(sid) or {}
        if script.get("exclude_reason") or script.get("duplicate_of") or not script.get("human"):
            continue
        cells[(r["judge"], r["arm"])][sid].append(r)

    rng = random.Random(SEED)
    result = {}
    for (judge, arm), by_script in sorted(cells.items()):
        pairs, repeat_sds, step_diffs, years = [], [], [], defaultdict(int)
        for sid, rs in sorted(by_script.items()):
            ref = pack[sid]["human"]
            totals = [float(r["total"]) for r in rs]
            pairs.append((statistics.fmean(totals), float(ref["total"])))
            if len(totals) >= 2:
                repeat_sds.append(statistics.stdev(totals))
            years[str(pack[sid].get("case_year"))] += 1
            if arm.startswith("martin:step"):
                ref_steps = ref.get("steps") or {}
                maxima = ref.get("step_maxima") or {}
                for r in rs:
                    scores = (r.get("result") or {}).get("scores") or {}
                    for key, human in ref_steps.items():
                        judged = scores.get(key)
                        mx = maxima.get(key)
                        if isinstance(judged, dict) and judged.get("score") is not None and mx:
                            step_diffs.append(abs(float(judged["score"]) - float(human)) / float(mx))
        judge_v = [p[0] for p in pairs]
        ref_v = [p[1] for p in pairs]
        mae = lambda ps: statistics.fmean(abs(a - b) for a, b in ps)
        bias = lambda ps: statistics.fmean(a - b for a, b in ps)
        pf_j = [v >= PASS_MARK for v in judge_v]
        pf_r = [v >= PASS_MARK for v in ref_v]
        r_p = pearson(judge_v, ref_v)
        r_s = pearson(ranks(judge_v), ranks(ref_v)) if len(pairs) >= 3 else None
        result.setdefault(arm_label(arm, LABELS), {})[judge] = {
            "n_scripts": len(pairs),
            "passes_per_script": sorted({len(v) for v in by_script.values()}),
            "case_years": dict(years),
            "mae": round(mae(pairs), 2),
            "mae_ci95": boot_ci(pairs, mae, rng),
            "bias": round(bias(pairs), 2),
            "bias_ci95": boot_ci(pairs, bias, rng),
            "pearson": None if r_p is None else round(r_p, 3),
            "spearman": None if r_s is None else round(r_s, 3),
            "pass_agreement": round(sum(a == b for a, b in zip(pf_j, pf_r)) / len(pairs), 3),
            "pass_kappa": None if kappa(pf_j, pf_r) is None else round(kappa(pf_j, pf_r), 3),
            "judge_pass_rate": round(sum(pf_j) / len(pairs), 3),
            "reference_pass_rate": round(sum(pf_r) / len(pairs), 3),
            "judge_mean_total": round(statistics.fmean(judge_v), 2),
            "reference_mean_total": round(statistics.fmean(ref_v), 2),
            "repeat_sd": round(statistics.fmean(repeat_sds), 2) if repeat_sds else None,
            "step_abs_diff_share": round(statistics.fmean(step_diffs), 3) if step_diffs else None,
            "n_step_comparisons": len(step_diffs),
        }
    # Sheet-sample variance: the same generator's independently generated
    # sheets, the same judge and scripts. Per script, the SD of the
    # sheet means (each the mean over passes), averaged over scripts.
    sheet_means: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for (judge, arm), by_script in cells.items():
        label = arm_label(arm, LABELS)
        if " sheet " not in label or label.startswith("expert"):
            continue
        gen, rest = label.split(" sheet ", 1)
        sheet, unit = rest.split(":", 1)
        for sid, rs in by_script.items():
            sheet_means[(gen, unit, judge)].setdefault(sid, {})
            sheet_means[(gen, unit, judge)][sid][sheet] = statistics.fmean(float(r["total"]) for r in rs)
    sheet_sample = {}
    for (gen, unit, judge), per_script in sorted(sheet_means.items()):
        sds = [statistics.stdev(v.values()) for v in per_script.values() if len(v) >= 2]
        n_sheets = max((len(v) for v in per_script.values()), default=0)
        if not sds:
            continue
        sheet_sample.setdefault(f"{gen}:{unit}", {})[judge] = {
            "n_sheets": n_sheets, "n_scripts": len(sds),
            "sheet_sample_sd": round(statistics.fmean(sds), 2),
            "max_script_sd": round(max(sds), 2),
        }
    out = {
        "note": ("D2a expert exam: LLM judge totals vs reference grades (per-script mean over passes). "
                 "Reference grades of 9 of 15 scripts await the exam author's confirmation of the grader. "
                 "Aggregates only."),
        "pass_mark_be": PASS_MARK,
        "seed": SEED,
        "n_boot": N_BOOT,
        "code_versions": sorted({(r.get("provenance") or {}).get("code_version") for r in rows} - {None}),
        "per_arm": result,
        "sheet_sample": sheet_sample,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm, per in result.items():
        for judge, x in per.items():
            print(f"{arm:60.60s} {judge:28.28s} n={x['n_scripts']:2d} MAE {x['mae']:5.1f} {x['mae_ci95']} "
                  f"bias {x['bias']:+5.1f} r {x['pearson']} pass-agree {x['pass_agreement']} "
                  f"repeatSD {x['repeat_sd']} step {x['step_abs_diff_share']}")
    for key, per in sheet_sample.items():
        for judge, x in per.items():
            print(f"sheet-sample {key} {judge}: {x}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
