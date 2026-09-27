#!/usr/bin/env python3
"""Validity on the expert exam (D2a): LLM judge totals vs the reference grades.

Reads the d2-judge rows (git-ignored, <data root>/interim/human/pilot/d2-judge.jsonl)
and the D2 pack (<data root>/interim/human/heidebach_scripts.json). Only rows of
the pinned judge code version count (d2_labels.D2_CODE_VERSION, override with
--code-version), and per judge x arm x script x pass only the newest row.

Per judge x arm, every statistic is computed per pass and averaged over the
passes that cover every script, so a judge with two passes and a judge with
one pass are compared on single-pass performance:

- n scripts, passes per script;
- MAE and mean bias (judge - reference), with script-bootstrap 95 % CIs;
- Pearson r and Spearman rho (average ranks for ties);
- pass/fail agreement at the exam's pass mark (40 BE) and Cohen's kappa;
- repeat SD (mean within-script SD over passes) and the mean absolute
  difference between two passes, for scripts with >= 2 passes;
- the MAE of the per-script pass means, for reference;
- for the expert-sheet arms: per-step mean absolute difference, over the
  steps both graded, as a share of the step maximum.

Paired contrasts between arms (same scripts) report the mean difference in
absolute error and in signed error with a paired script-bootstrap CI, the SD
of the per-script differences and the t-based minimum detectable effect at
n scripts (alpha .05 two-sided, power .8).

For a generator with two or more sheets, the sheet-sample block separates
sheet-to-sheet from pass-to-pass variance: the pooled within-sheet pass
variance, and the sheet component = variance of the per-script sheet means
minus pass variance / passes per sheet.

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

from scipy.stats import t as student_t

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]
import local_config  # noqa: E402
from d2_labels import D2_CODE_VERSION, arm_label, is_numbered_sheet, rubric_labels  # noqa: E402

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
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


def boot_ci(n: int, stat, rng: random.Random) -> list[float] | None:
    """Percentile CI of stat(indices) over script resamples."""
    if n < 3:
        return None
    vals = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(N_BOOT))
    return [round(vals[int(0.025 * N_BOOT)], 2), round(vals[int(0.975 * N_BOOT) - 1], 2)]


def mde(sd_d: float, n: int, alpha: float = 0.05, power: float = 0.8) -> float | None:
    if n < 3 or sd_d is None:
        return None
    return float((student_t.ppf(1 - alpha / 2, n - 1) + student_t.ppf(power, n - 1)) * sd_d / math.sqrt(n))


def newest_rows(rows: list[dict]) -> list[dict]:
    """One row per judge x arm x script x pass: the newest."""
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["judge"], r["arm"], r.get("script_id"), r.get("pass"))
        if key not in best or str(r.get("ts") or "") >= str(best[key].get("ts") or ""):
            best[key] = r
    return list(best.values())


class Cell:
    """One judge x arm: per script the reference and the totals per pass."""

    def __init__(self, by_script: dict[str, list[dict]], pack: dict):
        self.sids = sorted(by_script)
        self.ref = [float(pack[s]["human"]["total"]) for s in self.sids]
        self.by_pass = []
        passes = sorted({r.get("pass") for rs in by_script.values() for r in rs})
        for k in passes:
            per = {r["script_id"]: float(r["total"]) for rs in by_script.values() for r in rs if r.get("pass") == k}
            if all(s in per for s in self.sids):  # only passes that cover every script
                self.by_pass.append([per[s] for s in self.sids])
        self.totals = {s: [float(r["total"]) for r in by_script[s]] for s in self.sids}

    def per_pass(self, stat, idx=None) -> float | None:
        idx = range(len(self.sids)) if idx is None else idx
        vals = [stat([p[i] for i in idx], [self.ref[i] for i in idx]) for p in self.by_pass]
        vals = [v for v in vals if v is not None]
        return statistics.fmean(vals) if vals else None

    def abs_err(self) -> list[float]:
        """Per script: absolute error, averaged over the complete passes."""
        return [statistics.fmean(abs(p[i] - self.ref[i]) for p in self.by_pass) for i in range(len(self.sids))]

    def signed_err(self) -> list[float]:
        return [statistics.fmean(p[i] - self.ref[i] for p in self.by_pass) for i in range(len(self.sids))]


def _mae(j, r):
    return statistics.fmean(abs(a - b) for a, b in zip(j, r))


def _bias(j, r):
    return statistics.fmean(a - b for a, b in zip(j, r))


def _agree(j, r):
    return statistics.fmean((a >= PASS_MARK) == (b >= PASS_MARK) for a, b in zip(j, r))


def _kappa(j, r):
    return kappa([a >= PASS_MARK for a in j], [b >= PASS_MARK for b in r])


def _spearman(j, r):
    return pearson(ranks(j), ranks(r)) if len(j) >= 3 else None


def _rate(j, r):
    return statistics.fmean(a >= PASS_MARK for a in j)


# Paired contrasts on the same scripts: (judge, arm label) A minus B.
LUNA, MINI, DS = "gpt-5.6-luna", "gpt-5.4-mini", "deepseek-ai/DeepSeek-V4-Pro"
EXPERT = "expert sheet:step"
CONTRASTS = [
    ("judge on the expert sheet", (MINI, EXPERT), (LUNA, EXPERT)),
    ("judge on the expert sheet", (DS, EXPERT), (LUNA, EXPERT)),
    ("sheet for Luna", (LUNA, "gpt-5.4 sheet 1:bullet"), (LUNA, EXPERT)),
    ("sheet for Luna", (LUNA, "gpt-5.4-mini sheet 1:bullet"), (LUNA, EXPERT)),
    ("sheet for Luna", (LUNA, "gpt-5.4-mini sheet 2:bullet"), (LUNA, EXPERT)),
    ("sheet for DeepSeek", (DS, "gpt-5.4 sheet 1:bullet"), (DS, EXPERT)),
    ("sheet for GPT-5.4 Mini", (MINI, "gpt-5.4 sheet 1:bullet"), (MINI, EXPERT)),
    ("weak judge vs generated sheet", (MINI, EXPERT), (LUNA, "gpt-5.4 sheet 1:bullet")),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rows", type=Path, default=ROWS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--code-version", default=D2_CODE_VERSION,
                        help="keep only rows of this provenance code version ('' keeps all)")
    args = parser.parse_args()

    pack = {s["script_id"]: s for s in json.loads(PACK.read_text(encoding="utf-8"))}
    rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not (r.get("provenance") or {}).get("dry_run") and r.get("total") is not None]
    if args.code_version:
        rows = [r for r in rows if (r.get("provenance") or {}).get("code_version") == args.code_version]
    rows = newest_rows(rows)

    grouped: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sid = r.get("script_id")
        script = pack.get(sid) or {}
        if script.get("exclude_reason") or script.get("duplicate_of") or not script.get("human"):
            continue
        grouped[(r["judge"], arm_label(r["arm"], LABELS))][sid].append(r)

    rng = random.Random(SEED)
    result: dict[str, dict] = {}
    cells: dict[tuple[str, str], Cell] = {}
    for (judge, label), by_script in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        cell = Cell(by_script, pack)
        if not cell.by_pass:
            continue
        cells[(judge, label)] = cell
        n = len(cell.sids)
        repeat_sds, pass_diffs, step_diffs, years = [], [], [], defaultdict(int)
        for sid in cell.sids:
            totals = cell.totals[sid]
            if len(totals) >= 2:
                repeat_sds.append(statistics.stdev(totals))
                pass_diffs.append(abs(totals[0] - totals[1]))
            years[str(pack[sid].get("case_year"))] += 1
            if label.startswith(EXPERT.split(":")[0] + ":step"):
                ref = pack[sid]["human"]
                maxima = ref.get("step_maxima") or {}
                for r in by_script[sid]:
                    scores = (r.get("result") or {}).get("scores") or {}
                    for key, human in (ref.get("steps") or {}).items():
                        judged, mx = scores.get(key), maxima.get(key)
                        if isinstance(judged, dict) and judged.get("score") is not None and mx:
                            step_diffs.append(abs(float(judged["score"]) - float(human)) / float(mx))
        means = [statistics.fmean(cell.totals[s]) for s in cell.sids]
        rnd = lambda v, d=2: None if v is None else round(v, d)
        result.setdefault(label, {})[judge] = {
            "n_scripts": n,
            "passes_per_script": sorted({len(v) for v in cell.totals.values()}),
            "complete_passes": len(cell.by_pass),
            "case_years": dict(sorted(years.items())),
            "mae": rnd(cell.per_pass(_mae)),
            "mae_ci95": boot_ci(n, lambda idx: cell.per_pass(_mae, idx), rng),
            "bias": rnd(cell.per_pass(_bias)),
            "bias_ci95": boot_ci(n, lambda idx: cell.per_pass(_bias, idx), rng),
            "pearson": rnd(cell.per_pass(pearson), 3),
            "spearman": rnd(cell.per_pass(_spearman), 3),
            "pass_agreement": rnd(cell.per_pass(_agree), 3),
            "pass_kappa": rnd(cell.per_pass(_kappa), 3),
            "judge_pass_rate": rnd(cell.per_pass(_rate), 3),
            "reference_pass_rate": round(statistics.fmean(v >= PASS_MARK for v in cell.ref), 3),
            "judge_mean_total": round(statistics.fmean(means), 2),
            "reference_mean_total": round(statistics.fmean(cell.ref), 2),
            "mae_of_pass_means": round(_mae(means, cell.ref), 2),
            "repeat_sd": round(statistics.fmean(repeat_sds), 2) if repeat_sds else None,
            "mean_abs_pass_diff": round(statistics.fmean(pass_diffs), 2) if pass_diffs else None,
            "step_abs_diff_share": round(statistics.fmean(step_diffs), 3) if step_diffs else None,
            "n_step_comparisons": len(step_diffs),
        }

    contrasts = []
    for family, a, b in CONTRASTS:
        if a not in cells or b not in cells or cells[a].sids != cells[b].sids:
            continue
        ca, cb = cells[a], cells[b]
        n = len(ca.sids)
        entry = {"family": family, "a": {"judge": a[0], "arm": a[1]}, "b": {"judge": b[0], "arm": b[1]}, "n_scripts": n}
        for name, fa, fb in (("abs_error", ca.abs_err(), cb.abs_err()), ("signed_error", ca.signed_err(), cb.signed_err())):
            d = [x - y for x, y in zip(fa, fb)]
            sd_d = statistics.stdev(d) if n >= 2 else None
            entry[name] = {
                "mean_diff": round(statistics.fmean(d), 2),
                "ci95": boot_ci(n, lambda idx, d=d: statistics.fmean(d[i] for i in idx), rng),
                "sd_diff": None if sd_d is None else round(sd_d, 2),
                "mde": None if sd_d is None else round(mde(sd_d, n), 2),
            }
        contrasts.append(entry)

    # Sheet-sample variance: a generator's independently generated sheets,
    # the same judge and scripts, with the pass noise taken out.
    groups: dict[tuple[str, str, str], dict[str, Cell]] = defaultdict(dict)
    for (judge, label), cell in cells.items():
        if not is_numbered_sheet(label):
            continue
        sheet_part, unit = label.split(":", 1)
        gen, sheet = sheet_part.rsplit(" sheet ", 1)
        groups[(gen, unit, judge)][sheet] = cell
    sheet_sample = {}
    for (gen, unit, judge), sheets in sorted(groups.items()):
        if len(sheets) < 2:
            continue
        common = sorted(set.intersection(*(set(c.sids) for c in sheets.values())))
        within, sheet_vars, sheet_diffs, n_pass = [], [], [], []
        for sid in common:
            sheet_means = []
            for c in sheets.values():
                t = c.totals[sid]
                sheet_means.append(statistics.fmean(t))
                n_pass.append(len(t))
                if len(t) >= 2:
                    within.append(statistics.variance(t))
            sheet_vars.append(statistics.variance(sheet_means))
            if len(sheet_means) == 2:
                sheet_diffs.append(abs(sheet_means[0] - sheet_means[1]))
        pass_var = statistics.fmean(within) if within else None
        k = statistics.harmonic_mean(n_pass) if n_pass else 1
        sheet_var = statistics.fmean(sheet_vars) - (pass_var or 0.0) / k
        sheet_sample.setdefault(f"{gen}:{unit}", {})[judge] = {
            "n_sheets": len(sheets), "n_scripts": len(common), "passes_per_sheet": round(k, 2),
            "sd_of_sheet_means": round(math.sqrt(statistics.fmean(sheet_vars)), 2),
            "pass_sd_pooled": None if pass_var is None else round(math.sqrt(pass_var), 2),
            "sheet_sd_component": round(math.sqrt(max(0.0, sheet_var)), 2),
            "mean_abs_sheet_diff": round(statistics.fmean(sheet_diffs), 2) if sheet_diffs else None,
        }

    out = {
        "note": ("D2a expert exam: LLM judge totals vs reference grades. Statistics are per pass, averaged "
                 "over complete passes. Reference grades of 9 of 15 scripts await the exam author's "
                 "confirmation of the grader. Aggregates only."),
        "pass_mark_be": PASS_MARK,
        "seed": SEED,
        "n_boot": N_BOOT,
        "code_version": args.code_version or None,
        "code_versions_seen": sorted({(r.get("provenance") or {}).get("code_version") for r in rows} - {None}),
        "per_arm": result,
        "contrasts": contrasts,
        "sheet_sample": sheet_sample,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm, per in result.items():
        for judge, x in per.items():
            print(f"{arm:34.34s} {judge:28.28s} n={x['n_scripts']:2d} p={x['complete_passes']} MAE {x['mae']:5.2f} "
                  f"{x['mae_ci95']} bias {x['bias']:+6.2f} r {x['pearson']} agree {x['pass_agreement']} "
                  f"k {x['pass_kappa']} rep {x['repeat_sd']} |dp| {x['mean_abs_pass_diff']}")
    for c in contrasts:
        print(f"{c['a']['judge'][:12]}/{c['a']['arm'][:24]} - {c['b']['judge'][:12]}/{c['b']['arm'][:24]}: "
              f"abs {c['abs_error']} signed {c['signed_error']}")
    for key, per in sheet_sample.items():
        for judge, x in per.items():
            print(f"sheet-sample {key} {judge}: {x}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
