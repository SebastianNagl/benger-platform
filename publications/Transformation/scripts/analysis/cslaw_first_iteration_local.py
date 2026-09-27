#!/usr/bin/env python3
"""First-iteration numbers that need the git-ignored run outputs.

cslaw_first_iteration.py reads tracked files only and lists what it cannot
compute under "pending". This script computes those eight items from the
git-ignored run outputs and the generated rubrics, and writes aggregates only
(counts, means, correlations, CIs). It never writes exam, rubric or answer
text, and it never writes to the outputs of `make analyze`.

Items (keys of first_iteration.json "pending"):
  strict_first_full_series_coverage     rubric_sweep_log.jsonl
  apportionment_steps_off_in_drawn_rubric task_rubrics.json
  fewshot_step_sum                      fewshot_results_{luna,mini}.jsonl
  tailored_bias_step_sum                judge_results_{luna,temp0}.jsonl,
                                        tailored_repeats_flagships.jsonl
  stored_total_rows_per_judge           the judge result files
  contrast_cis_step_sum                 judge, few-shot and holistic result files
  luna_empty_median_failing             {,fewshot_,holistic_}probe_results.jsonl
  audit_signed_bias_link                audit_results.jsonl

Step sum: the sum of the clipped step scores, 100 * sum(clip(score, 0, max)) /
sum(max). This is the "actual" scheme of compute_weight_sensitivity.py. Every
row's step maxima are the apportioned points and sum to 100 (checked below
against task_rubrics.json), so it is the plain sum of the clipped scores. The
few-shot rubrics are not in task_rubrics.json, so the row's own maxima carry
the weights there.

Row selection and statistics copy the scripts that produced the stored-total
numbers (compute_matched_contrasts, compute_significance,
compute_matched_multijudge, compute_fewshot_contrasts, compute_probe_stats,
compute_audit_outcome_link, compute_weight_sensitivity), with the same seeds.
Each recompute first reproduces the tracked stored-total value (an "anchor");
``--check`` exits non-zero when an anchor breaks.

Data root: the ignored inputs are read from scripts/local_config.py's
data_root (PILOT_DATA_ROOT or data_root in .pilot.local.json). A worktree has
no ignored data, so point data_root at the main checkout's
publications/Transformation/data. Tracked inputs are read from this checkout.
The extended checkout (extended_repo) is optional: when present, its
`apportion` is checked against the corrected routine used here.

Output: data/processed/cslaw/first_iteration_local.json
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts")]
import local_config  # noqa: E402

DATA = local_config.data_root()
LOCAL_INTERIM = DATA / "interim"
RUBRICS = DATA / "raw" / "local" / "task_rubrics.json"
INTERIM = HERE / "data" / "interim"          # tracked inputs
PROCESSED = HERE / "data" / "processed"      # tracked outputs of `make analyze`
DATASET_ARR = HERE.parent / "Benchmark_EMNLP"
OUT = PROCESSED / "cslaw" / "first_iteration_local.json"

SEED = 20260806
N_BOOT = 10_000
TOL = 1e-6          # a stored total "differs" from the step sum beyond this
ANCHOR_TOL = 1e-9
LUNA, MINI = "gpt-5.6-luna", "gpt-5.4-mini"
ROSTER = (LUNA, "Qwen/Qwen3.5-397B-A17B", "gemini-3.1-pro-preview", "claude-sonnet-4-6",
          "claude-opus-4-7", "deepseek-ai/DeepSeek-V4-Pro", MINI)
MULTI = {  # compute_matched_multijudge.JUDGES: tailored and holistic x3 sources
    LUNA: ("judge_results_luna.jsonl", "holistic_results_luna.jsonl"),
    "claude-sonnet-4-6": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "gemini-3.1-pro-preview": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "deepseek-ai/DeepSeek-V4-Pro": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
    "Qwen/Qwen3.5-397B-A17B": ("tailored_repeats_flagships.jsonl", "holistic_results_flagships.jsonl"),
}
WS_FILES = ("judge_results_luna.jsonl", "tailored_repeats_flagships.jsonl", "judge_results_temp0.jsonl")

LOCAL_INPUTS = (
    "rubric_sweep_log.jsonl", "judge_results_luna.jsonl", "judge_results_temp0.jsonl",
    "judge_results.jsonl", "tailored_repeats_flagships.jsonl", "fewshot_results_luna.jsonl",
    "fewshot_results_mini.jsonl", "holistic_results_luna.jsonl", "holistic_results_flagships.jsonl",
    "probe_results.jsonl", "fewshot_probe_results.jsonl", "holistic_probe_results.jsonl",
    "audit_results.jsonl",
)
TRACKED_INPUTS = (
    INTERIM / "picks.json", INTERIM / "picks_temp0.json", INTERIM / "clone_d6_actives.json",
    INTERIM / "active_rubric_selection.json", INTERIM / "fewshot" / "selection.json",
    PROCESSED / "matched_stats.json", PROCESSED / "bootstrap_cis.json", PROCESSED / "significance.json",
    PROCESSED / "fewshot_stats.json", PROCESSED / "matched_multijudge.json",
    PROCESSED / "reliability_conditions.json", PROCESSED / "agreement_bias.json",
    PROCESSED / "weight_sensitivity.json", PROCESSED / "probe_stats.json",
    PROCESSED / "apportionment_audit.json", PROCESSED / "rubric_run_summary.json",
    PROCESSED / "rubric_outcomes.json", PROCESSED / "audit_outcome_link.json",
    DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json",
    DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json",
    HERE / "scripts" / "analysis" / "compute_apportionment_audit.py",
)

problems: list[str] = []


def anchor(ok: bool, what: str) -> bool:
    if not ok:
        problems.append(what)
    return bool(ok)


def close(a, b, tol=ANCHOR_TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    return abs(float(a) - float(b)) <= tol


def require_inputs() -> None:
    missing = [str(LOCAL_INTERIM / n) for n in LOCAL_INPUTS if not (LOCAL_INTERIM / n).exists()]
    if not RUBRICS.exists():
        missing.append(str(RUBRICS))
    missing += [str(p) for p in TRACKED_INPUTS if not p.exists()]
    if missing:
        raise SystemExit(
            "missing inputs:\n  " + "\n  ".join(missing) + f"\n\ndata root: {DATA}\n"
            "The ignored run outputs live only in the main checkout. Set PILOT_DATA_ROOT, or data_root in "
            "publications/Transformation/.pilot.local.json, to the main checkout's "
            "publications/Transformation/data.")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


_rows_cache: dict[str, list] = {}


def rows_of(name: str) -> list[dict]:
    if name not in _rows_cache:
        _rows_cache[name] = [json.loads(line) for line in
                             (LOCAL_INTERIM / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    return _rows_cache[name]


def stored(row) -> float:
    return float(row["total_score"])


def step_sum(row) -> float:
    """compute_weight_sensitivity 'actual' with the row's own step maxima as weights."""
    num = den = 0.0
    for v in row["scores"].values():
        mx = float(v["max"])
        num += min(max(float(v["score"]), 0.0), mx)
        den += mx
    return 100.0 * num / den


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def rep_sd(runs):
    return statistics.pstdev(list(runs.values())) if len(runs) > 1 else None


def first(runs):
    return runs[min(runs)] if runs else None


def binom_p(k, n):
    return float(sps.binomtest(k, n, 0.5).pvalue) if n else None


def sign_lower(diffs):
    lo = sum(1 for d in diffs if d < 0)
    hi = sum(1 for d in diffs if d > 0)
    return {"n": lo + hi, "lower": lo, "higher": hi, "p": binom_p(lo, lo + hi)}


def wilcoxon_sens(diffs):
    """compute_significance.wilcoxon_sens: exact, approx on a warning."""
    d = [x for x in diffs if x != 0]
    if len(d) < 5:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            res = sps.wilcoxon(d, method="exact")
    except (Warning, ValueError):
        res = sps.wilcoxon(d, method="approx", correction=True)
    return float(res.pvalue)


def cells_last_wins(name: str, judge: str, total) -> dict:
    """pick -> {run: total}; rows without total_score skipped, last row in the
    file wins (compute_matched_contrasts / _multijudge / _fewshot_contrasts)."""
    cells: dict = defaultdict(dict)
    for r in rows_of(name):
        if r.get("judge_model_id") != judge or r.get("total_score") is None:
            continue
        cells[r["pick_id"]][int(r.get("judge_run_index") or 0)] = total(r)
    return cells


def human_pool():
    sample = jload(DATASET_ARR / "data" / "interim" / "benchathon_human_grading_sample.json")
    subj = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    hg = defaultdict(list)
    for g in jload(DATASET_ARR / "data" / "processed" / "benchathon_human_grades.json"):
        if g.get("raw_score") is not None:
            hg[g["solution_id"]].append(float(g["raw_score"]))
    return {pid: statistics.mean(hg[s]) for pid, s in subj.items() if hg.get(s)}


# ---------------------------------------------------------------------------
# 1. strict first-full-series coverage
# ---------------------------------------------------------------------------
MODEL_VERDICT = {"contract", "parse"}


def strict_coverage():
    rows = rows_of("rubric_sweep_log.jsonl")
    cells = defaultdict(list)
    for r in rows:
        cells[(r["generator_model_id"], r["task_id"])].append(r)
    for series in cells.values():
        series.sort(key=lambda r: r["ts"])

    def full_every_attempt(r):
        errs = r.get("attempt_errors") or []
        return len(errs) == r["attempts"] and all(e.get("stage") in MODEL_VERDICT for e in errs)

    def full_final_verdict(r):
        return r.get("error_stage") in MODEL_VERDICT

    def coverage(is_full):
        per = Counter()
        for (gen, _), series in cells.items():
            ok = False
            for r in series:
                if r["outcome"] == "completed":
                    ok = True
                    break
                if is_full(r):
                    break
            per[gen] += ok
        return sum(per.values()), dict(sorted(per.items()))

    lenient = Counter(g for (g, _), s in cells.items() if any(r["outcome"] == "completed" for r in s))
    n_cells = len(cells)
    per_gen_cells = Counter(g for g, _ in cells)
    strict_n, strict_per = coverage(full_every_attempt)
    alt_n, alt_per = coverage(full_final_verdict)
    anchor(len(rows) == 220 and sum(r["outcome"] == "failed" for r in rows) == 50,
           "sweep log is not 220 series / 50 failed")
    anchor(sum(lenient.values()) == 170, "lenient coverage is not 170")
    summary = jload(PROCESSED / "rubric_run_summary.json")["generators"]
    anchor(all(summary[g]["rubrics"] == lenient[g] for g in summary), "lenient coverage != rubric_run_summary")
    return {
        "definition": "cells (generator x exam) with a valid rubric when a cell counts only if no fully executed "
                      "failed series precedes its first valid series; fully executed = every one of the three "
                      "attempts reached a model verdict (contract or parse), none aborted at the provider or "
                      "truncated",
        "sources": ["data/interim/rubric_sweep_log.jsonl (ignored)", "rubric_run_summary.json (anchor)"],
        "value": strict_n,
        "n_cells": n_cells,
        "lenient_any_series": sum(lenient.values()),
        "per_generator_below_full": {g: v for g, v in strict_per.items() if v < per_gen_cells[g]},
        "cells_lost_vs_lenient": {g: lenient[g] - v for g, v in strict_per.items() if lenient[g] != v},
        "variant_final_attempt_verdict": {
            "definition": "stricter reading: a failed series counts as fully executed when its FINAL attempt "
                          "reached a model verdict (then a series with truncated or provider-aborted earlier "
                          "attempts also counts)",
            "value": alt_n,
            "per_generator_below_full": {g: v for g, v in alt_per.items() if v < per_gen_cells[g]},
        },
    }


# ---------------------------------------------------------------------------
# 2. apportionment: steps changed in the affected drawn rubric
# ---------------------------------------------------------------------------
def apportionment_drawn():
    audit_mod = load_module("compute_apportionment_audit", HERE / "scripts" / "analysis" / "compute_apportionment_audit.py")
    appo = jload(PROCESSED / "apportionment_audit.json")
    drawn = {s["rubric_id"] for s in jload(INTERIM / "active_rubric_selection.json")["selection"]}
    rubrics = [r for r in jload(RUBRICS) if (r.get("generation_metadata") or {}).get("derived_document")]

    ext_path = Path(str(local_config.setting("extended_repo"))) / "benger_extended" / "workers" / "bewertungsbogen_constants.py"
    ext = load_module("bewertungsbogen_constants", ext_path) if ext_path.exists() else None

    out = []
    total_changed = 0
    ext_equal = 0
    for r in rubrics:
        gm = r["generation_metadata"]
        full = [s for a in gm["full_document"]["abschnitte"] for s in a["schritte"]]
        derived = [s for a in gm["derived_document"]["abschnitte"] for s in a["schritte"]]
        weights = [float(s["gewicht"]) for s in full]
        as_run = [s["max_punkte"] for s in derived]
        anchor(audit_mod.legacy_apportion(weights, 100) == as_run, "legacy routine does not reproduce a rubric")
        corrected = audit_mod.hamilton_floor(weights, 100)
        if ext is not None:
            ext_equal += ext.apportion(weights, 100, 1) == corrected
        changed = [c - a for c, a in zip(corrected, as_run) if c != a]
        total_changed += len(changed)
        if r["id"] in drawn and changed:
            out.append({"rubric_id": r["id"], "generator": r.get("generator_model_id"), "n_steps": len(weights),
                        "steps_changed": len(changed), "steps_plus_one": sum(1 for d in changed if d == 1),
                        "steps_minus_one": sum(1 for d in changed if d == -1),
                        "max_abs_change": max(abs(d) for d in changed)})
    anchor(total_changed == appo["methods"]["hamilton_floor"]["steps_changed_vs_as_run"],
           "total changed steps != apportionment_audit.json")
    anchor(sorted(o["rubric_id"] for o in out) == sorted(appo["affected_drawn_rubrics"]),
           "affected drawn rubrics != apportionment_audit.json")
    if ext is not None:
        anchor(ext_equal == len(rubrics), "extended apportion differs from hamilton_floor")
    one = out[0] if len(out) == 1 else None
    return {
        "definition": "steps whose points differ between the as-run apportionment (stored) and the corrected "
                      "floor-constrained Hamilton routine, in the drawn (judged) rubric that the as-run defect "
                      "affects",
        "sources": ["data/raw/local/task_rubrics.json (ignored)", "active_rubric_selection.json",
                    "compute_apportionment_audit.py (hamilton_floor, legacy_apportion)"],
        "value": {"steps_changed": one["steps_changed"], "n_steps": one["n_steps"]} if one else None,
        "affected_drawn": out,
        "extended_apportion_check": ({"file": "benger_extended/workers/bewertungsbogen_constants.py",
                                      "identical_on_rubrics": ext_equal, "n_rubrics": len(rubrics)}
                                     if ext is not None else "extended checkout not found; not checked"),
    }


# ---------------------------------------------------------------------------
# 3 + 4. agreement rows on step sums (few-shot and zero-shot)
# ---------------------------------------------------------------------------
def table_row(cells, hmean, ann_rows):
    """compute_significance conventions: repeat SD = mean over picks of the
    population SD over >= 2 passes; r / MAE / bias = first pass vs the human
    pool mean on the 30 annotation cells."""
    sds = [rep_sd(cells[p]) for p in cells if rep_sd(cells[p]) is not None]
    pairs = [(first(cells[p]), hmean[p]) for p in ann_rows if cells.get(p)]
    xs, ys = [a for a, _ in pairs], [b for _, b in pairs]
    return {"repeat_sd": statistics.mean(sds), "n_repeat_cells": len(sds),
            "r": pearson(xs, ys), "mae": statistics.mean(abs(a - b) for a, b in pairs),
            "bias": statistics.mean(a - b for a, b in pairs), "n_agreement": len(pairs)}


def agreement_rows(hmean, picks):
    cond = {r["condition"]: r for r in jload(PROCESSED / "reliability_conditions.json")["rows"]}
    ann_rows = [p for p in sorted(picks) if picks[p]["target_type"] == "annotation" and p in hmean]
    anchor(len(ann_rows) == 30, "expected 30 annotation cells")
    sources = {
        "fewshot_luna": ("fewshot_results_luna.jsonl", LUNA),
        "fewshot_mini": ("fewshot_results_mini.jsonl", MINI),
        "tailored_luna": ("judge_results_luna.jsonl", LUNA),
        "tailored_mini": ("judge_results_temp0.jsonl", MINI),
    }
    rows = {}
    for key, (name, judge) in sources.items():
        st = table_row(cells_last_wins(name, judge, stored), hmean, ann_rows)
        ss = table_row(cells_last_wins(name, judge, step_sum), hmean, ann_rows)
        c = cond[key]
        anchor(all(close(st[k], c[k]) for k in ("repeat_sd", "r", "mae", "bias")),
               f"{key}: stored-total recompute != reliability_conditions.json")
        rows[key] = {"source": name, "stored": st, "step_sum": ss}
    ws = jload(PROCESSED / "weight_sensitivity.json")["per_judge"]
    for key, judge in (("tailored_luna", LUNA), ("tailored_mini", MINI)):
        a, s = ws[judge]["actual"], rows[key]["step_sum"]
        anchor(all(close(round(s[k], 4), a[k], 1e-12) for k in ("repeat_sd", "r", "mae")),
               f"{key}: step-sum recompute != weight_sensitivity.json actual")
    return rows


def roster_bias(hmean, picks):
    """Signed bias for the seven roster judges on the weight-sensitivity row
    basis (D6-active rubric, latest row per pass, all three files)."""
    actives = jload(INTERIM / "clone_d6_actives.json")
    cells = defaultdict(dict)
    for name in WS_FILES:
        for row in rows_of(name):
            if not row.get("scores") or row.get("error"):
                continue
            if actives.get(row["task_id"]) != row["rubric_id"]:
                continue
            run = int(row.get("judge_run_index") or 0)
            key = (row["judge_model_id"], row["pick_id"])
            prev = cells[key].get(run)
            if prev is None or row["created_at"] > prev["created_at"]:
                cells[key][run] = row
    ann = {p for p in picks if picks[p]["target_type"] == "annotation"}
    ws = jload(PROCESSED / "weight_sensitivity.json")["per_judge"]
    out = {}
    for judge in ROSTER:
        jc = {p: runs for (j, p), runs in cells.items() if j == judge}
        res = {}
        for label, fn in (("stored", stored), ("step_sum", step_sum)):
            firsts, sds = [], []
            for p, runs in jc.items():
                totals = {i: fn(r) for i, r in runs.items()}
                if 0 in totals and p in hmean and p in ann:
                    firsts.append((totals[0], hmean[p]))
                if len(totals) >= 3:
                    sds.append(statistics.pstdev(list(totals.values())))
            xs, ys = [a for a, _ in firsts], [b for _, b in firsts]
            res[label] = {"n": len(firsts), "bias": statistics.mean(a - b for a, b in firsts),
                          "r": pearson(xs, ys), "mae": statistics.mean(abs(a - b) for a, b in firsts),
                          "repeat_sd": statistics.mean(sds), "n_repeat_cells": len(sds)}
        a = ws[judge]["actual"]
        anchor(all(close(round(res["step_sum"][k], 4), a[k], 1e-12) for k in ("r", "mae", "repeat_sd"))
               and res["step_sum"]["n_repeat_cells"] == a["n_repeat_cells"],
               f"roster {judge}: step-sum recompute != weight_sensitivity.json actual")
        out[judge] = res
    return out, cells


# ---------------------------------------------------------------------------
# 5. rows whose stored total differs from the step sum
# ---------------------------------------------------------------------------
def stored_vs_step(ws_cells):
    files = {
        "judge_results_luna.jsonl": "zero-shot x3 (Luna)",
        "judge_results_temp0.jsonl": "zero-shot, T=0 clone (Mini x3, flagships first pass)",
        "tailored_repeats_flagships.jsonl": "zero-shot x3 (flagships)",
        "fewshot_results_luna.jsonl": "few-shot x3 (Luna)",
        "fewshot_results_mini.jsonl": "few-shot x3 (Mini)",
        "judge_results.jsonl": "zero-shot, T=1 source project (appendix)",
    }
    per_file = {}
    summax_off = 0
    for name, label in files.items():
        acc = defaultdict(lambda: {"n_rows": 0, "n_differs": 0, "max_abs_diff": 0.0})
        for r in rows_of(name):
            if r.get("total_score") is None or not r.get("scores") or r.get("error"):
                continue
            d = abs(stored(r) - step_sum(r))
            summax_off += abs(sum(float(v["max"]) for v in r["scores"].values()) - 100.0) > 1e-9
            a = acc[r["judge_model_id"]]
            a["n_rows"] += 1
            if d > TOL:
                a["n_differs"] += 1
                a["max_abs_diff"] = max(a["max_abs_diff"], d)
        per_file[name] = {"arm": label, "per_judge": dict(sorted(acc.items()))}
    anchor(summax_off == 0, "some scored rows have step maxima that do not sum to 100")

    basis = defaultdict(lambda: {"n_rows": 0, "n_differs": 0})
    for (judge, _), runs in ws_cells.items():
        for r in runs.values():
            basis[judge]["n_rows"] += 1
            basis[judge]["n_differs"] += abs(stored(r) - step_sum(r)) > TOL

    headline = {
        LUNA: {"zero_shot": per_file["judge_results_luna.jsonl"]["per_judge"][LUNA],
               "few_shot": per_file["fewshot_results_luna.jsonl"]["per_judge"][LUNA]},
        MINI: {"zero_shot": per_file["judge_results_temp0.jsonl"]["per_judge"][MINI],
               "few_shot": per_file["fewshot_results_mini.jsonl"]["per_judge"][MINI]},
    }
    for j in ("claude-opus-4-7", "claude-sonnet-4-6", "Qwen/Qwen3.5-397B-A17B", "deepseek-ai/DeepSeek-V4-Pro",
              "gemini-3.1-pro-preview"):
        headline[j] = {"zero_shot": per_file["tailored_repeats_flagships.jsonl"]["per_judge"][j]}
    return {
        "definition": f"scored rows whose stored total differs from the step sum by more than {TOL:g} "
                      "(the August judge kept the model's own total when it was within 0.5 of the step sum); "
                      "headline = each judge's x3 repeat file",
        "sources": list(files),
        "value": headline,
        "per_file": per_file,
        "analysis_basis": {
            "definition": "rows that enter the judge table (compute_weight_sensitivity: D6-active rubric, "
                          "latest row per pass, zero-shot files merged)",
            "per_judge": dict(sorted(basis.items())),
        },
    }


# ---------------------------------------------------------------------------
# 6. repeat-SD contrasts on step sums
# ---------------------------------------------------------------------------
def pct_ci(vals):
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def zs_vs_hol(total, matched_pp):
    """compute_significance: shared draws, percentile CI, sign test (lower),
    Wilcoxon sensitivity; holistic side from matched_stats per_pick."""
    luna = cells_last_wins("judge_results_luna.jsonl", LUNA, total)
    mini = cells_last_wins("judge_results_temp0.jsonl", MINI, total)
    per_pick = []
    for r in matched_pp:
        per_pick.append({"task_id": r["task_id"],
                         "luna_tail": rep_sd(luna.get(r["pick_id"]) or {}), "luna_hol": r.get("luna_holi_rep_sd"),
                         "mini_tail": rep_sd(mini.get(r["pick_id"]) or {}), "mini_hol": r.get("mini_holi_rep_sd")})
    by_exam = defaultdict(list)
    for r in per_pick:
        by_exam[r["task_id"]].append(r)
    exams = sorted(by_exam)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(exams), size=(N_BOOT, len(exams)))

    def diffs(rows, a, b):
        return [r[a] - r[b] for r in rows if r.get(a) is not None and r.get(b) is not None]

    out = {}
    for name, a, b in (("luna_zs_vs_hol", "luna_tail", "luna_hol"), ("mini_zs_vs_hol", "mini_tail", "mini_hol")):
        d = diffs(per_pick, a, b)
        vals = []
        for i in range(N_BOOT):
            rows = [r for e in draws[i] for r in by_exam[exams[e]]]
            dd = diffs(rows, a, b)
            if dd:
                vals.append(statistics.mean(dd))
        out[name] = {"point": statistics.mean(d), "ci95": pct_ci(vals), "n": len(d),
                     "tailored_mean": statistics.mean(r[a] for r in per_pick if r[a] is not None),
                     "sign_p": sign_lower(d)["p"], "wilcoxon_p": wilcoxon_sens(d)}
    return out


def fewshot_contrasts(total, matched_pp):
    """compute_fewshot_contrasts: fresh rng per contrast, percentile CI, sign test."""
    fs_luna = cells_last_wins("fewshot_results_luna.jsonl", LUNA, total)
    fs_mini = cells_last_wins("fewshot_results_mini.jsonl", MINI, total)
    zs_luna = cells_last_wins("judge_results_luna.jsonl", LUNA, total)
    zs_mini = cells_last_wins("judge_results_temp0.jsonl", MINI, total)
    matched = {r["pick_id"]: r for r in matched_pp}
    picks = {p["pick_id"]: p for p in jload(INTERIM / "picks_temp0.json")["resolved"]}
    rows = [{"task_id": picks[p]["task_id"],
             "fs_luna": rep_sd(fs_luna.get(p) or {}), "fs_mini": rep_sd(fs_mini.get(p) or {}),
             "zs_luna": rep_sd(zs_luna.get(p) or {}), "zs_mini": rep_sd(zs_mini.get(p) or {}),
             "hol_luna": (matched.get(p) or {}).get("luna_holi_rep_sd"),
             "hol_mini": (matched.get(p) or {}).get("mini_holi_rep_sd")} for p in sorted(picks)]
    by_exam = defaultdict(list)
    for r in rows:
        by_exam[r["task_id"]].append(r)
    exams = sorted(by_exam)

    def diffs(a, b, rs):
        return [r[a] - r[b] for r in rs if r.get(a) is not None and r.get(b) is not None]

    out = {}
    for name, a, b in (("luna_fs_vs_hol", "fs_luna", "hol_luna"), ("luna_fs_vs_zs", "fs_luna", "zs_luna"),
                       ("mini_fs_vs_hol", "fs_mini", "hol_mini"), ("mini_fs_vs_zs", "fs_mini", "zs_mini")):
        d = diffs(a, b, rows)
        rng = np.random.default_rng(SEED)
        vals = []
        for _ in range(N_BOOT):
            draw = rng.integers(0, len(exams), size=len(exams))
            dd = [x for e in draw for x in diffs(a, b, by_exam[exams[e]])]
            if dd:
                vals.append(statistics.mean(dd))
        out[name] = {"point": statistics.mean(d), "ci95": pct_ci(vals), "n": len(d),
                     "mean_a": statistics.mean(r[a] for r in rows if r[a] is not None),
                     "mean_b": statistics.mean(r[b] for r in rows if r[b] is not None),
                     "sign_p": sign_lower(d)["p"]}
        if name == "luna_fs_vs_hol":   # compute_significance luna_fewshot_repeats
            out[name]["wilcoxon_p"] = wilcoxon_sens(d)
    return out


def multijudge(total, matched_pp):
    """compute_matched_multijudge: pooled = unweighted mean of the five capable
    judges' mean diffs, one rng for the pooled CI, a fresh rng per judge."""
    picks = {p["pick_id"]: p for p in jload(INTERIM / "picks_temp0.json")["resolved"]}
    per_judge_rows = {}
    for judge, (tp, hp) in MULTI.items():
        tail = cells_last_wins(tp, judge, total)
        hol = cells_last_wins(hp, judge, stored)       # holistic totals are the dimension sums
        rows = []
        for pid in picks:
            ts, hs = rep_sd(tail.get(pid) or {}), rep_sd(hol.get(pid) or {})
            if ts is not None and hs is not None:
                rows.append({"task_id": picks[pid]["task_id"], "t": ts, "h": hs, "diff": ts - hs})
        per_judge_rows[judge] = rows
    mini_tail = cells_last_wins("judge_results_temp0.jsonl", MINI, total)
    per_judge_rows[MINI] = [
        {"task_id": r["task_id"], "t": rep_sd(mini_tail.get(r["pick_id"]) or {}), "h": r["mini_holi_rep_sd"],
         "diff": rep_sd(mini_tail.get(r["pick_id"]) or {}) - r["mini_holi_rep_sd"]}
        for r in matched_pp if rep_sd(mini_tail.get(r["pick_id"]) or {}) is not None
        and r.get("mini_holi_rep_sd") is not None]

    per_judge = {}
    for judge, rows in per_judge_rows.items():
        d = [r["diff"] for r in rows]
        per_judge[judge] = {"delta": statistics.mean(d), "n_cells": len(rows),
                            "tailored_mean": statistics.mean(r["t"] for r in rows),
                            "holistic_mean": statistics.mean(r["h"] for r in rows),
                            "sign_p": sign_lower(d)["p"], "in_pooled": judge in MULTI}
    pooled_point = statistics.mean(per_judge[j]["delta"] for j in MULTI)

    by_exam_judge = defaultdict(lambda: defaultdict(list))
    for judge, rows in per_judge_rows.items():
        for r in rows:
            by_exam_judge[r["task_id"]][judge].append(r["diff"])
    exams = sorted(by_exam_judge)
    rng = np.random.default_rng(SEED)
    pooled = []
    for _ in range(N_BOOT):
        draw = rng.integers(0, len(exams), size=len(exams))
        means = []
        for judge in MULTI:
            vals = [d for e in draw for d in by_exam_judge[exams[e]].get(judge, [])]
            if vals:
                means.append(statistics.mean(vals))
        if means:
            pooled.append(statistics.mean(means))

    for judge, rows in per_judge_rows.items():
        by_exam = defaultdict(list)
        for r in rows:
            by_exam[r["task_id"]].append(r["diff"])
        exs = sorted(by_exam)
        rng_j = np.random.default_rng(SEED)
        vals = []
        for _ in range(N_BOOT):
            draw = rng_j.integers(0, len(exs), size=len(exs))
            pool = [d for e in draw for d in by_exam[exs[e]]]
            if pool:
                vals.append(statistics.mean(pool))
        per_judge[judge]["ci95"] = pct_ci(vals)
    return {"pooled_five": {"point": pooled_point, "ci95": pct_ci(pooled), "n_judges": len(MULTI)},
            "per_judge": per_judge}


def contrasts():
    matched_pp = jload(PROCESSED / "matched_stats.json")["per_pick"]
    boots = jload(PROCESSED / "bootstrap_cis.json")["contrasts"]
    sig = jload(PROCESSED / "significance.json")
    fs_stats = jload(PROCESSED / "fewshot_stats.json")["repeat_sd_contrasts"]
    multi_stored = jload(PROCESSED / "matched_multijudge.json")

    res = {}
    for label, fn in (("stored", stored), ("step_sum", step_sum)):
        res[label] = {**zs_vs_hol(fn, matched_pp), **fewshot_contrasts(fn, matched_pp),
                      **multijudge(fn, matched_pp)}

    st = res["stored"]
    for name, bkey, skey in (("luna_zs_vs_hol", "repeat_sd_luna_tailored_minus_holistic", "luna_matched_repeats_sign"),
                             ("mini_zs_vs_hol", "repeat_sd_mini_tailored_minus_holistic", "mini_matched_repeats_sign")):
        anchor(close(st[name]["point"], boots[bkey]["point"]) and close(st[name]["ci95"], boots[bkey]["ci95"])
               and close(st[name]["sign_p"], sig[skey]["p"]) and close(st[name]["wilcoxon_p"], sig[skey]["wilcoxon"]["p"]),
               f"{name}: stored-total recompute != bootstrap_cis/significance")
    for name, fkey in (("luna_fs_vs_hol", "luna_fewshot_vs_holistic"), ("luna_fs_vs_zs", "luna_fewshot_vs_zeroshot"),
                       ("mini_fs_vs_hol", "mini_fewshot_vs_holistic"), ("mini_fs_vs_zs", "mini_fewshot_vs_zeroshot")):
        anchor(close(st[name]["point"], fs_stats[fkey]["mean_diff"]) and close(st[name]["ci95"], fs_stats[fkey]["ci95"])
               and close(st[name]["sign_p"], fs_stats[fkey]["p"]),
               f"{name}: stored-total recompute != fewshot_stats")
    anchor(close(st["luna_fs_vs_hol"]["wilcoxon_p"], sig["luna_fewshot_repeats"]["wilcoxon"]["p"]),
           "luna_fs_vs_hol Wilcoxon != significance")
    anchor(close(st["pooled_five"]["point"], multi_stored["pooled"]["point"])
           and close(st["pooled_five"]["ci95"], multi_stored["pooled"]["ci95"]), "pooled: stored recompute != multijudge")
    for f in multi_stored["forest"]:
        mine = st["per_judge"][f["judge"]]
        anchor(close(mine["delta"], f["delta"]) and close(mine["ci95"], f["ci95"]) and mine["n_cells"] == f["n_cells"]
               and close(mine["sign_p"], multi_stored["per_judge"][f["judge"]]["sign"]["p"]),
               f"forest {f['judge']}: stored recompute != matched_multijudge")

    ss = res["step_sum"]
    ex_stored = sorted(j for j, v in st["per_judge"].items() if v["in_pooled"] and (v["ci95"][0] > 0 or v["ci95"][1] < 0))
    ex_step = sorted(j for j, v in ss["per_judge"].items() if v["in_pooled"] and (v["ci95"][0] > 0 or v["ci95"][1] < 0))
    return {
        "definition": "repeat-SD contrasts (instrument minus comparison; negative = more stable) with the tailored and "
                      "few-shot passes totalled as step sums; holistic passes unchanged (their stored totals equal "
                      "their dimension sums). Row selection, exam-cluster bootstrap (seed 20260806, 10k, percentile "
                      "95% CI), sign tests and Wilcoxon as in compute_significance / compute_fewshot_contrasts / "
                      "compute_matched_multijudge",
        "sources": ["judge_results_luna.jsonl", "judge_results_temp0.jsonl", "tailored_repeats_flagships.jsonl",
                    "fewshot_results_luna.jsonl", "fewshot_results_mini.jsonl", "holistic_results_luna.jsonl",
                    "holistic_results_flagships.jsonl", "matched_stats.json (holistic Luna/Mini per pick)"],
        "value": ss,
        "stored_recompute": st,
        "judges_ci_excluding_zero": {"stored": ex_stored, "step_sum": ex_step},
    }


# ---------------------------------------------------------------------------
# 7. Luna's empty-answer probe among failing passes
# ---------------------------------------------------------------------------
def luna_empty_failing():
    probes = jload(PROCESSED / "probe_stats.json")["arms"]
    d6 = jload(INTERIM / "clone_d6_actives.json")
    fs_drawn = {s["task_id"]: s["rubric_id"] for s in jload(INTERIM / "fewshot" / "selection.json")["selection"]}
    arms = {"tailored": ("probe_results.jsonl", d6), "fewshot": ("fewshot_probe_results.jsonl", fs_drawn),
            "holistic": ("holistic_probe_results.jsonl", None)}
    out = {}
    for arm, (name, guard) in arms.items():
        rows = [r for r in rows_of(name) if r["judge_model_id"] == LUNA and r["provenance"] == "empty"]
        if guard is not None:
            anchor(all(r.get("rubric_id") == guard.get(r["task_id"]) for r in rows), f"{arm}: probe row off its rubric")
        anchor(all(r.get("total_score") is not None and not r.get("error") for r in rows), f"{arm}: errored probe row")
        entry = {}
        for label, fn in (("stored", stored), ("step_sum", step_sum)):
            if label == "step_sum" and guard is None:
                continue
            scores = [fn(r) for r in rows]
            failing = [s for s in scores if s != 0.0]
            entry[label] = {"n_passes": len(scores), "n_fail_passes": len(failing),
                            "median_failing": statistics.median(failing) if failing else None,
                            "mean_failing": statistics.mean(failing) if failing else None,
                            "min_failing": min(failing) if failing else None,
                            "max_failing": max(failing) if failing else None,
                            "median_all_passes": statistics.median(scores)}
        ref = (probes.get(arm) or {}).get(LUNA, {}).get("empty") or {}
        s = entry["stored"]
        anchor(s["n_passes"] == ref.get("n_passes") and s["n_fail_passes"] == ref.get("n_fail_passes")
               and close(round(s["median_all_passes"], 2), ref.get("median"), 1e-12),
               f"{arm}: empty-probe counts/median != probe_stats.json")
        out[arm] = entry
    return {
        "definition": "median of Luna's score on the empty-answer probe over the failing passes only "
                      "(criterion: empty = 0 on every pass), per arm; stored totals as in compute_probe_stats, "
                      "step sums alongside for the step-score arms",
        "sources": ["probe_results.jsonl", "fewshot_probe_results.jsonl", "holistic_probe_results.jsonl"],
        "value": {arm: e["stored"]["median_failing"] for arm, e in out.items()},
        "per_arm": out,
    }


# ---------------------------------------------------------------------------
# 8. audit total vs SIGNED bias
# ---------------------------------------------------------------------------
def audit_signed_bias():
    src = {p["pick_id"]: p["task_id"] for p in jload(INTERIM / "picks.json")["resolved"]}
    clo = {p["pick_id"]: p["task_id"] for p in jload(INTERIM / "picks_temp0.json")["resolved"]}
    src_to_clone = {s: clo[pid] for pid, s in src.items()}
    per_rubric = jload(PROCESSED / "rubric_outcomes.json")["luna"]["per_rubric"]
    out_by_key = {(r["task_id"], r["generator_model_id"]): r for r in per_rubric}
    rows = []
    for a in rows_of("audit_results.jsonl"):
        o = out_by_key[(src_to_clone[a["task_id"]], a["generator_model_id"])]
        rows.append({"exam": src_to_clone[a["task_id"]], "audit_total": float(a["total_score"]),
                     "bias": o.get("bias"), "abs_bias": abs(o["bias"]) if o.get("bias") is not None else None})
    anchor(len(rows) == 170, "audit join is not 170 rows")

    def centered(vbe):
        out = []
        for pairs in vbe.values():
            if len(pairs) < 2:
                continue
            mx = statistics.mean(x for x, _ in pairs)
            my = statistics.mean(y for _, y in pairs)
            out.extend((x - mx, y - my) for x, y in pairs)
        return out

    def pack(pairs):
        xs, ys = [a for a, _ in pairs], [b for _, b in pairs]
        return {"n": len(pairs), "pearson": float(sps.pearsonr(xs, ys).statistic),
                "spearman": float(sps.spearmanr(xs, ys).statistic)}

    def boot_ci(y_key, kind):
        rng = np.random.default_rng(SEED)
        sub = defaultdict(list)
        for r in rows:
            if r.get(y_key) is not None:
                sub[r["exam"]].append(r)
        ex = sorted(sub)
        vals = []
        for _ in range(N_BOOT):
            draw = rng.integers(0, len(ex), size=len(ex))
            if kind == "raw":
                pairs = [(r["audit_total"], r[y_key]) for e in draw for r in sub[ex[e]]]
            else:
                pairs = []
                for e in draw:
                    grp = [(r["audit_total"], r[y_key]) for r in sub[ex[e]]]
                    if len(grp) < 2:
                        continue
                    mx = statistics.mean(x for x, _ in grp)
                    my = statistics.mean(y for _, y in grp)
                    pairs.extend((x - mx, y - my) for x, y in grp)
            if len(pairs) < 3:
                continue
            xs, ys = [a for a, _ in pairs], [b for _, b in pairs]
            if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
                continue
            vals.append(float(sps.pearsonr(xs, ys).statistic))
        return pct_ci(vals)

    def corr(y_key):
        raw = [(r["audit_total"], r[y_key]) for r in rows if r.get(y_key) is not None]
        vbe = defaultdict(list)
        for r in rows:
            if r.get(y_key) is not None:
                vbe[r["exam"]].append((r["audit_total"], r[y_key]))
        return {"raw": {**pack(raw), "ci95": boot_ci(y_key, "raw")},
                "within_exam_centered": {**pack(centered(vbe)), "ci95": boot_ci(y_key, "centered")}}

    signed, absolute = corr("bias"), corr("abs_bias")
    ref = jload(PROCESSED / "audit_outcome_link.json")["audit_total_vs"]["abs_bias"]
    for k in ("raw", "within_exam_centered"):
        anchor(all(close(absolute[k][f], ref[k][f]) for f in ("pearson", "spearman", "ci95"))
               and absolute[k]["n"] == ref[k]["n"], f"abs-bias {k}: recompute != audit_outcome_link.json")
    return {
        "definition": "Pearson (and Spearman) correlation of the automated audit total with the rubric's SIGNED bias "
                      "(Luna lens, crossed sweep, rubric_outcomes.json; negative = harsher), exam means removed from "
                      "both; exam-cluster bootstrap 95% CI (seed 20260806, 10k), as for the absolute-bias link",
        "sources": ["audit_results.jsonl (ignored)", "rubric_outcomes.json", "picks.json", "picks_temp0.json"],
        "value": signed["within_exam_centered"],
        "raw": signed["raw"],
        "basis_note": "the crossed-sweep bias is on stored totals: crossed_cells.luna.jsonl keeps pass totals only, "
                      "so no step-sum version exists",
    }


def rounded(obj, nd=6):
    if isinstance(obj, float):
        return None if math.isnan(obj) else round(obj, nd)
    if isinstance(obj, dict):
        return {k: rounded(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v, nd) for v in obj]
    return obj


def main() -> int:
    check = "--check" in sys.argv
    require_inputs()
    picks = {p["pick_id"]: p for p in jload(INTERIM / "picks_temp0.json")["resolved"]}
    hmean = human_pool()

    items = {"strict_first_full_series_coverage": strict_coverage(),
             "apportionment_steps_off_in_drawn_rubric": apportionment_drawn()}

    table = agreement_rows(hmean, picks)
    items["fewshot_step_sum"] = {
        "definition": "few-shot rows of the reliability table with totals = step sums: repeat SD (mean over 45 "
                      "picks of the population SD over 3 passes), r / MAE / signed bias (first pass vs the human "
                      "pool mean, 30 annotation cells)",
        "sources": ["fewshot_results_luna.jsonl", "fewshot_results_mini.jsonl", "Benchmark_EMNLP human pool"],
        "value": {k: table[k]["step_sum"] for k in ("fewshot_luna", "fewshot_mini")},
        "stored": {k: table[k]["stored"] for k in ("fewshot_luna", "fewshot_mini")},
    }
    roster, ws_cells = roster_bias(hmean, picks)
    items["tailored_bias_step_sum"] = {
        "definition": "signed bias of the zero-shot (tailored) rows on step sums: mean(first pass - human pool "
                      "mean), 30 annotation cells; negative = harsher than the humans",
        "sources": ["judge_results_luna.jsonl", "judge_results_temp0.jsonl", "tailored_repeats_flagships.jsonl"],
        "value": {k: table[k]["step_sum"]["bias"] for k in ("tailored_luna", "tailored_mini")},
        "stored": {k: table[k]["stored"]["bias"] for k in ("tailored_luna", "tailored_mini")},
        "table_rows": {k: table[k]["step_sum"] for k in ("tailored_luna", "tailored_mini")},
        "roster": {"definition": "the seven roster judges on the judge-table row basis (weight_sensitivity.json)",
                   "per_judge": {j: {"bias_step_sum": v["step_sum"]["bias"], "bias_stored": v["stored"]["bias"],
                                     "n": v["step_sum"]["n"]} for j, v in roster.items()}},
    }
    items["stored_total_rows_per_judge"] = stored_vs_step(ws_cells)
    items["contrast_cis_step_sum"] = contrasts()
    items["luna_empty_median_failing"] = luna_empty_failing()
    items["audit_signed_bias_link"] = audit_signed_bias()

    result = {
        "note": "First-iteration numbers that need the git-ignored run outputs (the 'pending' items of "
                "first_iteration.json). Aggregates only. Generated by "
                "scripts/analysis/cslaw_first_iteration_local.py; every value has a stored-total anchor that "
                "reproduces a tracked number first.",
        "step_sum": "100 * sum(clip(score, 0, max)) / sum(max) over a pass's steps; every scored row's maxima "
                    "sum to 100, so this is the sum of the clipped step scores",
        "items": items,
        "anchors": {"n_failed": len(problems), "failed": problems},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rounded(result), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {OUT.relative_to(HERE)}")
    sc = items["strict_first_full_series_coverage"]
    print(f"1 strict coverage {sc['value']}/{sc['n_cells']} (variant {sc['variant_final_attempt_verdict']['value']})")
    ap = items["apportionment_steps_off_in_drawn_rubric"]["value"]
    print(f"2 drawn rubric: {ap['steps_changed']} of {ap['n_steps']} steps change" if ap else "2 no single drawn rubric")
    for k, v in items["fewshot_step_sum"]["value"].items():
        s = items["fewshot_step_sum"]["stored"][k]
        print(f"3 {k}: SD {s['repeat_sd']:.3f}->{v['repeat_sd']:.3f} r {s['r']:.4f}->{v['r']:.4f} "
              f"MAE {s['mae']:.3f}->{v['mae']:.3f} bias {s['bias']:+.3f}->{v['bias']:+.3f}")
    for k, v in items["tailored_bias_step_sum"]["value"].items():
        print(f"4 {k}: bias {items['tailored_bias_step_sum']['stored'][k]:+.4f} -> {v:+.4f}")
    for j, v in items["stored_total_rows_per_judge"]["value"].items():
        print(f"5 {j}: " + ", ".join(f"{arm} {e['n_differs']}/{e['n_rows']}" for arm, e in v.items()))
    cs = items["contrast_cis_step_sum"]
    for name in ("luna_zs_vs_hol", "mini_zs_vs_hol", "luna_fs_vs_hol", "luna_fs_vs_zs", "mini_fs_vs_hol",
                 "mini_fs_vs_zs", "pooled_five"):
        a, b = cs["stored_recompute"][name], cs["value"][name]
        print(f"6 {name}: {a['point']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}] -> "
              f"{b['point']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}]")
    for j, b in cs["value"]["per_judge"].items():
        a = cs["stored_recompute"]["per_judge"][j]
        print(f"6 forest {j.split('/')[-1]}: {a['delta']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}] -> "
              f"{b['delta']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}] sign p {b['sign_p']:.3f}")
    for arm, e in items["luna_empty_median_failing"]["per_arm"].items():
        s = e["stored"]
        print(f"7 {arm}: median failing {s['median_failing']} (n {s['n_fail_passes']}/{s['n_passes']})")
    ab = items["audit_signed_bias_link"]["value"]
    print(f"8 audit vs signed bias (centered): r {ab['pearson']:+.3f} [{ab['ci95'][0]:+.3f}, {ab['ci95'][1]:+.3f}], "
          f"rho {ab['spearman']:+.3f}")
    for p in problems:
        print("ANCHOR FAILED:", p)
    return 1 if (check and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
