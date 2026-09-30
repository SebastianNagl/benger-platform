#!/usr/bin/env python3
"""D1 against the exam creator's grade: the expert-reference view.

Every D1 answer carries three blind human grades and one un-blind grade by
the exam's creator, the domain expert who wrote the case and the model
solution. The paper measures agreement against the mean of all four grades.
The benchmark paper treats the creator as the single most expert reference
(its Calderon single-expert alt-test, epsilon 0.20). This script takes the
creator's grade as the reference, as D2 takes the exam author's, and reports
for every first-iteration judge x instrument arm with totals on the D1
answers:

  1. MAE, mean bias (judge - creator) and Pearson r, per pass and averaged
     over the complete passes (compute_d2_validity.py), plus the first pass,
     on the 30 human-written answers and on all 45 answers;
  2. the human baseline: each blind grader against the creator on the
     answers they graded, and the mean blind-to-creator MAE;
  3. Calderon's alternative-annotator test with the creator as the single
     expert (epsilon 0.20; 0.15 as sensitivity), run with the benchmark's own
     code (compute_agreement._alt_test_single_expert);
  4. the benchmark's "human cloud" ratio: MAE against the blind mean divided
     by half the mean within-answer max-min spread of the blind grades;
  5. paired differences in absolute error against the creator between each
     sheet arm and the same judge's holistic arm, with an exam-cluster
     bootstrap 95 % CI (15 exams, fixed seed).

Totals: sheet arms (zero-shot and few-shot) use the step sums of
cslaw_first_iteration_local.py (its loaders are reused: roster_bias for the
zero-shot judge-table basis, cells_last_wins + step_sum for few-shot);
holistic arms use the stored totals, which are the dimension sums.

Before switching the reference, the script reproduces two anchors and stops
without writing when either breaks: the benchmark's creator-vs-blind-mean
MAE (agreement_stats.json rq5_creator_vs_blind, 12.47 raw, 45 answers) and
Luna's zero-shot first-pass MAE against the 4-grader pool (12.81, 30
answers). Further anchors (benchmark judge MAE and alt-test, cloud ratio,
the reliability-table rows) fail the run under ``--check``.

Inputs: the git-ignored run outputs under scripts/local_config.py's data
root (point PILOT_DATA_ROOT at the main checkout's
publications/Transformation/data in a worktree), the benchmark's raw export
(Benchmark_EMNLP/data/raw/benchathon/Benchathon_export.json, ignored; looked
up in this checkout, then next to the data root's paper folder) and tracked
files of both papers. Output: data/processed/cslaw/creator_reference.json,
aggregates only (no answer text, no exam content, grader ids only as the
benchmark's anonymized ids).
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
ANALYSIS = HERE / "scripts" / "analysis"
PROCESSED = HERE / "data" / "processed"
INTERIM = HERE / "data" / "interim"
BENCH = HERE.parent / "Benchmark_EMNLP"
OUT = PROCESSED / "cslaw" / "creator_reference.json"

SEED = 20260806        # the D1 bootstrap seed (compute_significance, cslaw_first_iteration_local)
N_BOOT = 10_000
EPS = 0.20             # the benchmark's headline epsilon for the single-expert test
EPS_SENS = 0.15        # the benchmark's sensitivity epsilon
ANCHOR_TOL = 1e-9


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# The first-iteration loaders (step sums, row selection, human pool) and the
# benchmark's alt-test code, reused as they are.
fil = load_module("cslaw_first_iteration_local", ANALYSIS / "cslaw_first_iteration_local.py")
ca = load_module("bench_compute_agreement", BENCH / "scripts" / "compute_agreement.py")

DATA = fil.DATA
LOCAL_INTERIM = fil.LOCAL_INTERIM
LUNA, MINI = fil.LUNA, fil.MINI
ROSTER = fil.ROSTER
HOLISTIC_FLAGSHIPS = ("claude-sonnet-4-6", "gemini-3.1-pro-preview", "deepseek-ai/DeepSeek-V4-Pro",
                      "Qwen/Qwen3.5-397B-A17B")
CONTROL_SINGLE = ("claude-opus-4-7", "claude-sonnet-4-6", "gemini-3.1-pro-preview",
                  "deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3.5-397B-A17B")
BENCH_PRIMARY = "gpt-5.4-mini"   # compute_agreement.BASELINE_JUDGE_FIELD_PREFIX (mptmfvee-sqyx)
CONTROL_REPEAT = "gpt-5-mini"    # the reliability table's holistic_control row

RAW_NAME = Path("Benchmark_EMNLP") / "data" / "raw" / "benchathon" / "Benchathon_export.json"
RAW_CANDIDATES = (HERE.parent / RAW_NAME, DATA.parent.parent / RAW_NAME)

LOCAL_INPUTS = (
    "judge_results_luna.jsonl", "judge_results_temp0.jsonl", "tailored_repeats_flagships.jsonl",
    "fewshot_results_luna.jsonl", "fewshot_results_mini.jsonl", "holistic_results_luna.jsonl",
    "holistic_results_mini.jsonl", "holistic_results_flagships.jsonl", "control_results_temp0.jsonl",
)
TRACKED_INPUTS = (
    INTERIM / "picks_temp0.json", INTERIM / "clone_d6_actives.json",
    PROCESSED / "weight_sensitivity.json", PROCESSED / "reliability_conditions.json",
    PROCESSED / "agreement_bias.json", PROCESSED / "bootstrap_cis.json",
    PROCESSED / "cslaw" / "first_iteration.json", PROCESSED / "cslaw" / "first_iteration_local.json",
    BENCH / "data" / "interim" / "benchathon_human_grading_sample.json",
    BENCH / "data" / "processed" / "benchathon_human_grades.json",
    BENCH / "data" / "processed" / "benchathon_model_evaluations.json",
    BENCH / "data" / "processed" / "benchathon_superseded_evaluations.json",
    BENCH / "data" / "processed" / "agreement_stats.json",
)

problems: list[str] = []


def anchor(ok: bool, what: str) -> bool:
    if not ok:
        problems.append(what)
    return bool(ok)


close = fil.close
jload = fil.jload
pearson = fil.pearson


def raw_export_path() -> Path | None:
    return next((p for p in RAW_CANDIDATES if p.exists()), None)


def require_inputs() -> None:
    missing = [str(LOCAL_INTERIM / n) for n in LOCAL_INPUTS if not (LOCAL_INTERIM / n).exists()]
    missing += [str(p) for p in TRACKED_INPUTS if not p.exists()]
    if raw_export_path() is None:
        missing.append(" or ".join(str(p) for p in RAW_CANDIDATES))
    if missing:
        raise SystemExit(
            "missing inputs:\n  " + "\n  ".join(missing) + f"\n\ndata root: {DATA}\n"
            "The ignored run outputs and the benchmark's raw export live only in the main checkout. "
            "Set PILOT_DATA_ROOT, or data_root in publications/Transformation/.pilot.local.json, to the "
            "main checkout's publications/Transformation/data.")


# ---------------------------------------------------------------------------
# human grades
# ---------------------------------------------------------------------------
def short(grader_id: str) -> str:
    return grader_id.split("@", 1)[0]


class Humans:
    """Per pick: the creator's grade, the blind grades, their mean, the pool."""

    def __init__(self, picks: dict):
        sample = jload(BENCH / "data" / "interim" / "benchathon_human_grading_sample.json")
        self.grades = jload(BENCH / "data" / "processed" / "benchathon_human_grades.json")
        self.sol = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
        self.exam_inner = {p["pick_id"]: p["task_inner_id"] for p in sample["picks"]}
        pick_of = {s: p for p, s in self.sol.items()}
        creator, blind = defaultdict(list), defaultdict(list)
        for g in self.grades:
            if g.get("raw_score") is None:
                continue
            pid = pick_of[g["solution_id"]]
            if g["role"] == "creator":
                creator[pid].append((g["grader_id"], float(g["raw_score"])))
            elif g["role"] == "blind":
                blind[pid].append((g["grader_id"], float(g["raw_score"])))
        anchor(sorted(creator) == sorted(picks) and all(len(v) == 1 for v in creator.values()),
               "not exactly one creator grade per pick")
        anchor(sorted(blind) == sorted(picks) and all(len(v) == 3 for v in blind.values()),
               "not exactly three blind grades per pick")
        creators_of_exam = defaultdict(set)
        for pid, rows in creator.items():
            creators_of_exam[self.exam_inner[pid]].update(g for g, _ in rows)
        own = sum(1 for pid, rows in blind.items() for g, _ in rows if g in creators_of_exam[self.exam_inner[pid]])
        anchor(own == 0, "a blind grade comes from the exam's own creator")
        self.creator = {p: v[0][1] for p, v in creator.items()}
        self.creator_ids = {v[0][0] for v in creator.values()}
        self.blind = dict(blind)
        self.blind_mean = {p: statistics.mean(x for _, x in v) for p, v in blind.items()}
        self.pool = fil.human_pool()   # all four grades, the paper's anchor
        self.n_creators = len(self.creator_ids)
        self.blind_graders = sorted({g for v in blind.values() for g, _ in v})
        self.blind_who_created = sorted(set(self.blind_graders) & self.creator_ids)


# ---------------------------------------------------------------------------
# arms: passes -> {pick: total}
# ---------------------------------------------------------------------------
def by_pass(cells: dict) -> dict[int, dict[str, float]]:
    """pick -> {run: total}  to  run -> {pick: total}."""
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for pid, runs in cells.items():
        for k, v in runs.items():
            out[int(k)][pid] = float(v)
    return dict(sorted(out.items()))


def bench_primary(humans: Humans) -> dict[str, float]:
    """The benchmark paper's primary judge (its RQ5 judge), single pass: its
    own loader on the raw export for the human answers, its pick-level
    model evaluations for the generated answers (compute_agreement.main)."""
    real = ca.load_json(raw_export_path())
    on_humans = ca.index_judge_on_humans(real)
    evals = jload(BENCH / "data" / "processed" / "benchathon_model_evaluations.json")
    evals += jload(BENCH / "data" / "processed" / "benchathon_superseded_evaluations.json")
    on_gens: dict[str, list[float]] = defaultdict(list)
    for r in evals:
        if r.get("raw_score") is not None:
            on_gens[r["generation_id"]].append(float(r["raw_score"]))
    out = {}
    for pid, sid in humans.sol.items():
        j = (on_humans.get(sid) or {}).get("raw_score")
        if j is not None:
            out[pid] = float(j)
        elif len(on_gens.get(sid, [])) == 1:
            out[pid] = on_gens[sid][0]
    anchor(len(out) == 45, "benchmark judge: totals on fewer than 45 picks")
    return out


def control_rows():
    """control_results_temp0.jsonl as compute_matched_contrasts reads it:
    repeat rows by run, single-pass rows by judge; the last row wins."""
    rep, single = defaultdict(dict), defaultdict(dict)
    for r in fil.rows_of("control_results_temp0.jsonl"):
        if r.get("score") is None:
            continue
        if r["repeat_run"]:
            rep[r["pick_id"]][int(r["run_index"] or 0)] = float(r["score"])
        else:
            single[r["judge"]][r["pick_id"]] = float(r["score"])
    return rep, single


def build_arms(humans: Humans, picks: dict):
    arms: dict[str, dict] = {}

    def add(instrument, judge, passes, source, basis):
        arms[f"{instrument}:{judge}"] = {"instrument": instrument, "judge": judge, "passes": passes,
                                         "source": source, "basis": basis}

    # holistic: the matched re-run of the 10-dimension Falllösung instrument
    add("holistic", LUNA, by_pass(fil.cells_last_wins("holistic_results_luna.jsonl", LUNA, fil.stored)),
        "holistic_results_luna.jsonl", "stored total (dimension sum)")
    add("holistic", MINI, by_pass(fil.cells_last_wins("holistic_results_mini.jsonl", MINI, fil.stored)),
        "holistic_results_mini.jsonl", "stored total (dimension sum)")
    for j in HOLISTIC_FLAGSHIPS:
        add("holistic", j, by_pass(fil.cells_last_wins("holistic_results_flagships.jsonl", j, fil.stored)),
            "holistic_results_flagships.jsonl", "stored total (dimension sum)")

    # zero-shot generated sheet: the judge-table basis (weight_sensitivity 'actual')
    _, ws_cells = fil.roster_bias(humans.pool, picks)
    for j in ROSTER:
        cells = {p: {k: fil.step_sum(r) for k, r in runs.items()} for (jj, p), runs in ws_cells.items() if jj == j}
        add("zero_shot_sheet", j, by_pass(cells),
            "judge_results_luna.jsonl, tailored_repeats_flagships.jsonl, judge_results_temp0.jsonl",
            "step sum; D6-active rubric, latest row per pass (compute_weight_sensitivity)")
    # the reliability table's rows (cells_last_wins) must give the same totals
    for j, name in ((LUNA, "judge_results_luna.jsonl"), (MINI, "judge_results_temp0.jsonl")):
        table = by_pass(fil.cells_last_wins(name, j, fil.step_sum))
        mine = arms[f"zero_shot_sheet:{j}"]["passes"]
        anchor(table.keys() == mine.keys()
               and all(table[k].keys() == mine[k].keys() and all(close(table[k][p], mine[k][p]) for p in table[k])
                       for k in table),
               f"zero-shot {j}: judge-table basis != reliability-table basis")

    # few-shot sheet
    for j, name in ((LUNA, "fewshot_results_luna.jsonl"), (MINI, "fewshot_results_mini.jsonl")):
        add("few_shot_sheet", j, by_pass(fil.cells_last_wins(name, j, fil.step_sum)), name,
            "step sum; last row per pass (compute_fewshot_contrasts)")

    # the benchmark paper's own holistic judge runs (imported, unchanged)
    add("holistic_benchmark_run", BENCH_PRIMARY, {0: bench_primary(humans)},
        "Benchathon_export.json, benchathon_model_evaluations.json, benchathon_superseded_evaluations.json",
        "the benchmark's primary (RQ5) judge, single pass, its own loader")
    rep, single = control_rows()
    add("holistic_benchmark_run", CONTROL_REPEAT, by_pass(rep), "control_results_temp0.jsonl",
        "the benchmark's 3-pass repeat run (reliability table row holistic_control)")
    for j in CONTROL_SINGLE:
        add("holistic_benchmark_run", j, {0: dict(single[j])}, "control_results_temp0.jsonl",
            "the benchmark's single-pass panel run")
    n_diff = sum(1 for p, v in single[BENCH_PRIMARY].items()
                 if not close(v, arms[f"holistic_benchmark_run:{BENCH_PRIMARY}"]["passes"][0].get(p)))
    return arms, n_diff


# ---------------------------------------------------------------------------
# 1. agreement with a reference
# ---------------------------------------------------------------------------
def block(xs, ys) -> dict:
    return {"n": len(xs), "mae": statistics.mean(abs(a - b) for a, b in zip(xs, ys)),
            "bias": statistics.mean(a - b for a, b in zip(xs, ys)), "r": pearson(xs, ys)}


def answers_of(passes, subset, ref):
    return [p for p in subset if p in ref and any(p in t for t in passes.values())]


def complete_passes(passes, answers):
    return [k for k in sorted(passes) if all(p in passes[k] for p in answers)]


def first_pass(passes, answers) -> dict[str, float]:
    """Per pick the lowest run index present (compute_significance's first())."""
    return {p: passes[min(k for k in passes if p in passes[k])][p] for p in answers}


def agreement(passes, ref, subset) -> dict:
    answers = answers_of(passes, subset, ref)
    done = complete_passes(passes, answers)
    per = [block([passes[k][p] for p in answers], [ref[p] for p in answers]) for k in done]
    fp = first_pass(passes, answers)

    def avg(key):
        vals = [b[key] for b in per if b[key] is not None]
        return statistics.mean(vals) if vals else None

    return {"n_answers": len(answers), "n_missing": len(subset) - len(answers), "complete_passes": len(done),
            "mae": avg("mae"), "bias": avg("bias"), "r": avg("r"),
            "mae_range_over_passes": [min(b["mae"] for b in per), max(b["mae"] for b in per)] if per else None,
            "first_pass": block([fp[p] for p in answers], [ref[p] for p in answers])}


# ---------------------------------------------------------------------------
# 2. the human baseline: blind graders against the creator
# ---------------------------------------------------------------------------
def human_baseline(humans: Humans, subsets: dict) -> dict:
    out = {}
    for name, subset in subsets.items():
        per_grader = defaultdict(lambda: ([], []))
        pairs = []
        for p in subset:
            for g, x in humans.blind[p]:
                per_grader[g][0].append(x)
                per_grader[g][1].append(humans.creator[p])
                pairs.append((x, humans.creator[p]))
        graders = {short(g): block(xs, ys) for g, (xs, ys) in sorted(per_grader.items())}
        maes = [v["mae"] for v in graders.values()]
        spread = [max(x for _, x in humans.blind[p]) - min(x for _, x in humans.blind[p]) for p in subset]
        out[name] = {
            "per_grader": graders,
            "pair_level": {**block([a for a, _ in pairs], [b for _, b in pairs]), "n_answers": len(subset)},
            "grader_level_mean_mae": statistics.mean(maes),
            "grader_level_mae_range": [min(maes), max(maes)],
            "blind_mean_vs_creator": block([humans.blind_mean[p] for p in subset], [humans.creator[p] for p in subset]),
            "creator_vs_blind_mean_as_rater": block([humans.creator[p] for p in subset],
                                                    [humans.blind_mean[p] for p in subset]),
            "blind_spread_mean": statistics.mean(spread),
        }
    return out


# ---------------------------------------------------------------------------
# 3. Calderon single-expert alt-test (the benchmark's own code)
# ---------------------------------------------------------------------------
def alt_test(totals: dict[str, float], subset, humans: Humans, blind_by_sol, expert_by_sol, eps: float,
             detail: bool = False) -> dict:
    judge_by_sol = {humans.sol[p]: totals[p] for p in subset if p in totals}
    inputs, n_inst = ca._build_single_expert_inputs(judge_by_sol, blind_by_sol, expert_by_sol)
    res = ca._alt_test_single_expert(inputs, eps=eps)
    out = {"epsilon": eps, "n_instances": n_inst, "m_annotators": res["m_annotators"],
           "n_rejected": res["n_rejected"], "winning_rate": res["winning_rate"],
           "winning_rate_ci95_clopper": [res["winning_rate_ci95_lo_clopper"], res["winning_rate_ci95_hi_clopper"]],
           "avg_advantage_probability": res["avg_advantage_probability"],
           "passes_alt_test": res["passes_alt_test"]}
    if detail:
        out["per_annotator"] = [{"grader": short(a["grader_id"]), "n_j": a["n_j"], "rho_f": a["rho_f"],
                                 "rho_h": a["rho_h"], "d_bar": a["d_bar"], "test": a["test"],
                                 "p_value": a["p_value"], "rejected_BY_FDR": a["rejected_BY_FDR"]}
                                for a in res["per_annotator"]]
    return out, res


def alt_block(passes, subset, humans, blind_by_sol, expert_by_sol, detail: bool) -> dict:
    answers = answers_of(passes, subset, humans.creator)
    done = complete_passes(passes, answers)
    fp = first_pass(passes, answers)
    head, _ = alt_test(fp, subset, humans, blind_by_sol, expert_by_sol, EPS, detail=detail)
    sens, _ = alt_test(fp, subset, humans, blind_by_sol, expert_by_sol, EPS_SENS)
    per = {}
    for k in done:
        r, _ = alt_test(passes[k], subset, humans, blind_by_sol, expert_by_sol, EPS)
        per[str(k)] = {f: r[f] for f in ("winning_rate", "n_rejected", "m_annotators", "passes_alt_test",
                                         "avg_advantage_probability")}
    return {"first_pass": head,
            "first_pass_eps_sensitivity": {f: sens[f] for f in ("epsilon", "winning_rate", "n_rejected",
                                                                "passes_alt_test")},
            "per_complete_pass": per,
            "mean_winning_rate_over_complete_passes": statistics.mean(v["winning_rate"] for v in per.values())
            if per else None,
            "complete_passes_passing": sum(v["passes_alt_test"] for v in per.values()),
            "n_complete_passes": len(per)}


# ---------------------------------------------------------------------------
# 4. the human-cloud ratio
# ---------------------------------------------------------------------------
def cloud(passes, humans: Humans, subsets: dict, half_spread: dict) -> dict:
    a30 = agreement(passes, humans.blind_mean, subsets["human_written"])
    a45 = agreement(passes, humans.blind_mean, subsets["all"])

    def ratio(x, d):
        return None if x is None else x / d

    return {
        "mae_vs_blind_mean_human_written": {"first_pass": a30["first_pass"]["mae"], "pass_mean": a30["mae"],
                                            "n": a30["n_answers"]},
        "benchmark_definition": ratio(a30["first_pass"]["mae"], half_spread["all"]),
        "pass_mean": ratio(a30["mae"], half_spread["all"]),
        "matched_30": ratio(a30["first_pass"]["mae"], half_spread["human_written"]),
        "all_45": ratio(a45["first_pass"]["mae"], half_spread["all"]),
        "all_45_pass_mean": ratio(a45["mae"], half_spread["all"]),
    }


# ---------------------------------------------------------------------------
# 5. paired sheet - holistic contrasts
# ---------------------------------------------------------------------------
def abs_err(passes, subset, ref, first_only=False) -> dict[str, float]:
    """Per answer |total - reference|, averaged over the complete passes
    (compute_d2_validity Cell.abs_err); first_only uses the first pass."""
    answers = answers_of(passes, subset, ref)
    if first_only:
        fp = first_pass(passes, answers)
        return {p: abs(fp[p] - ref[p]) for p in answers}
    done = complete_passes(passes, answers)
    if not done:
        return {}
    return {p: statistics.mean(abs(passes[k][p] - ref[p]) for k in done) for p in answers}


def cluster_ci(diffs: dict[str, float], exam_of: dict[str, str]) -> list[float]:
    exams = sorted({exam_of[p] for p in diffs})
    sums = np.array([sum(d for p, d in diffs.items() if exam_of[p] == e) for e in exams])
    cnts = np.array([sum(1 for p in diffs if exam_of[p] == e) for e in exams])
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(exams), size=(N_BOOT, len(exams)))
    means = sums[draws].sum(axis=1) / cnts[draws].sum(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def paired(a_passes, b_passes, subset, ref, exam_of, first_only=False) -> dict | None:
    ea, eb = abs_err(a_passes, subset, ref, first_only), abs_err(b_passes, subset, ref, first_only)
    common = [p for p in subset if p in ea and p in eb]
    if not common:
        return None
    d = {p: ea[p] - eb[p] for p in common}
    return {"n_answers": len(common), "n_exams": len({exam_of[p] for p in common}),
            "mae_sheet": statistics.mean(ea[p] for p in common), "mae_holistic": statistics.mean(eb[p] for p in common),
            "mean_diff": statistics.mean(d.values()), "ci95": cluster_ci(d, exam_of),
            "sheet_closer": sum(1 for v in d.values() if v < 0), "holistic_closer": sum(1 for v in d.values() if v > 0),
            "ties": sum(1 for v in d.values() if v == 0)}


# ---------------------------------------------------------------------------
def main() -> int:
    check = "--check" in sys.argv
    require_inputs()
    picks = {p["pick_id"]: p for p in jload(INTERIM / "picks_temp0.json")["resolved"]}
    exam_of = {p: picks[p]["task_id"] for p in picks}
    subsets = {"human_written": sorted(p for p in picks if picks[p]["target_type"] == "annotation"),
               "all": sorted(picks)}
    anchor(len(subsets["human_written"]) == 30 and len(subsets["all"]) == 45 and len(set(exam_of.values())) == 15,
           "D1 is not 30 human-written of 45 answers in 15 exams")
    humans = Humans(picks)
    anchor(all(len({exam_of[p] for p in picks if humans.exam_inner[p] == e}) == 1
               for e in set(humans.exam_inner.values())), "exam clusters differ between the two papers")
    stats_ref = jload(BENCH / "data" / "processed" / "agreement_stats.json")

    # ---- required anchor 1: the benchmark's creator vs blind mean (45) ----
    cvb = stats_ref["rq5_creator_vs_blind"]
    mine = ca.rq5_creator_vs_blind(humans.grades)
    ok1 = all(close(mine[k], cvb[k]) for k in ("mae_raw", "mean_creator_minus_blind_raw",
                                               "pearson_creator_vs_mean_blind_raw")) and mine["n_solutions"] == 45
    hb45 = block([humans.creator[p] for p in subsets["all"]], [humans.blind_mean[p] for p in subsets["all"]])
    ok1 = ok1 and close(hb45["mae"], cvb["mae_raw"]) and round(hb45["mae"], 2) == 12.47

    # ---- the arms ----
    arms, n_control_primary_diff = build_arms(humans, picks)
    for p in fil.problems:
        anchor(False, f"cslaw_first_iteration_local: {p}")

    # ---- required anchor 2: Luna zero-shot vs the 4-grader pool (30) ----
    luna_zs = agreement(arms[f"zero_shot_sheet:{LUNA}"]["passes"], humans.pool, subsets["human_written"])
    fi = jload(PROCESSED / "cslaw" / "first_iteration.json")["agreement"]["luna"]["zs_step_sum"]
    fil_json = jload(PROCESSED / "cslaw" / "first_iteration_local.json")["items"]
    fil_row = fil_json["tailored_bias_step_sum"]["table_rows"]["tailored_luna"]
    ok2 = (luna_zs["first_pass"]["n"] == 30 and close(round(luna_zs["first_pass"]["mae"], 4), fi["mae"])
           and close(round(luna_zs["first_pass"]["mae"], 6), fil_row["mae"])
           and round(luna_zs["first_pass"]["mae"], 2) == 12.81)
    if not (ok1 and ok2):
        print(f"ANCHOR FAILED (required): creator vs blind mean MAE {hb45['mae']:.4f} (want {cvb['mae_raw']:.4f}); "
              f"Luna zero-shot vs pool MAE {luna_zs['first_pass']['mae']:.4f} (want {fi['mae']})", file=sys.stderr)
        return 2
    print(f"anchor: creator vs blind mean MAE {hb45['mae']:.4f} (benchmark {cvb['mae_raw']:.4f}), n 45")
    print(f"anchor: Luna zero-shot vs 4-grader pool MAE {luna_zs['first_pass']['mae']:.4f} "
          f"(first_iteration {fi['mae']}), n 30")

    # ---- further anchors: the paper's rows against the pool ----
    rc = {r["condition"]: r for r in jload(PROCESSED / "reliability_conditions.json")["rows"]}
    ws = jload(PROCESSED / "weight_sensitivity.json")["per_judge"]
    hw = subsets["human_written"]
    for cond, arm in (("holistic_luna", f"holistic:{LUNA}"), ("holistic_mini", f"holistic:{MINI}"),
                      ("holistic_control", f"holistic_benchmark_run:{CONTROL_REPEAT}")):
        a = agreement(arms[arm]["passes"], humans.pool, hw)["first_pass"]
        anchor(close(a["mae"], rc[cond]["mae"]) and close(a["r"], rc[cond]["r"]) and close(a["bias"], rc[cond]["bias"]),
               f"{arm}: first pass vs pool != reliability_conditions {cond}")
    for key, arm in (("fewshot_luna", f"few_shot_sheet:{LUNA}"), ("fewshot_mini", f"few_shot_sheet:{MINI}")):
        a = agreement(arms[arm]["passes"], humans.pool, hw)["first_pass"]
        ref = fil_json["fewshot_step_sum"]["value"][key]
        anchor(all(close(round(a[k], 6), ref[k]) for k in ("mae", "r", "bias")),
               f"{arm}: first pass vs pool != first_iteration_local fewshot_step_sum")
    for j in ROSTER:
        a = agreement(arms[f"zero_shot_sheet:{j}"]["passes"], humans.pool, hw)["first_pass"]
        bias_ref = fil_json["tailored_bias_step_sum"]["roster"]["per_judge"][j]["bias_step_sum"]
        anchor(close(round(a["mae"], 4), ws[j]["actual"]["mae"]) and close(round(a["r"], 4), ws[j]["actual"]["r"])
               and close(round(a["bias"], 6), bias_ref) and a["n"] == ws[j]["actual"]["n"],
               f"zero-shot {j}: first pass vs pool != weight_sensitivity / first_iteration_local")
    # the blind-mean reference: compute_significance's blind-only sensitivity
    # (stored totals; Luna's zero-shot first passes equal their step sums)
    blind_only = jload(PROCESSED / "agreement_bias.json")["blind_only_sensitivity"]
    for cond, arm in (("holistic_luna", f"holistic:{LUNA}"), ("holistic_mini", f"holistic:{MINI}"),
                      ("holistic_control", f"holistic_benchmark_run:{CONTROL_REPEAT}"),
                      ("tailored_luna", f"zero_shot_sheet:{LUNA}")):
        a = agreement(arms[arm]["passes"], humans.blind_mean, hw)["first_pass"]
        ref = blind_only[cond]
        anchor(close(a["mae"], ref["mae"]) and close(a["r"], ref["pearson"]) and close(a["bias"], ref["bias"])
               and a["n"] == ref["n"], f"{arm}: first pass vs blind mean != agreement_bias {cond}")
    # the bootstrap: Luna's zero-shot - holistic MAE contrast against the pool
    boot_ref = jload(PROCESSED / "bootstrap_cis.json")["contrasts"]["mae_luna_tailored_minus_holistic"]
    luna_pair = paired(arms[f"zero_shot_sheet:{LUNA}"]["passes"], arms[f"holistic:{LUNA}"]["passes"], hw,
                       humans.pool, exam_of, first_only=True)
    anchor(close(luna_pair["mean_diff"], boot_ref["point"]) and close(luna_pair["ci95"], boot_ref["ci95"]),
           "Luna zero-shot - holistic MAE contrast vs pool != bootstrap_cis.json")

    # ---- further anchors: the benchmark's judge, cloud and alt-test ----
    bench = arms[f"holistic_benchmark_run:{BENCH_PRIMARY}"]["passes"]
    jvh = stats_ref["rq5_judge_vs_human"]
    a = agreement(bench, humans.blind_mean, hw)["first_pass"]
    anchor(close(a["mae"], jvh["mae_raw"]) and close(a["r"], jvh["pearson_raw"]) and a["n"] == jvh["n_annotations"],
           "benchmark judge vs blind mean != agreement_stats rq5_judge_vs_human")
    baseline = human_baseline(humans, subsets)
    irr = stats_ref["rq5_human_irr"]
    anchor(close(baseline["all"]["blind_spread_mean"], irr["mean_within_ann_spread_raw"]),
           "blind spread != agreement_stats rq5_human_irr")
    half_spread = {k: v["blind_spread_mean"] / 2 for k, v in baseline.items()}
    anchor(close(a["mae"] / half_spread["all"], irr["mean_judge_human_dev_vs_human_human_dev_ratio"]),
           "benchmark cloud ratio != agreement_stats")
    blind_by_sol = ca.humans_by_solution(humans.grades, role_filter="blind")
    expert_by_sol = ca._expert_grades_by_solution(humans.grades)
    llm = sorted(set(subsets["all"]) - set(hw))
    for subset, key in ((hw, "rq5_calderon"), (llm, "rq5_calderon_on_llm_solutions")):
        for eps in (EPS, EPS_SENS):
            _, res = alt_test(bench[0], subset, humans, blind_by_sol, expert_by_sol, eps)
            want = stats_ref[key]["single_expert"]["epsilon_results"][f"{eps:.2f}"]
            anchor(res["n_rejected"] == want["n_rejected"] and close(res["winning_rate"], want["winning_rate"])
                   and len(res["per_annotator"]) == len(want["per_annotator"])
                   and all(x["grader_id"] == y["grader_id"] and x["n_j"] == y["n_j"]
                           and close(x["p_value"], y["p_value"]) and x["rejected_BY_FDR"] == y["rejected_BY_FDR"]
                           for x, y in zip(res["per_annotator"], want["per_annotator"])),
                   f"benchmark judge alt-test ({key}, eps {eps}) != agreement_stats")

    # ---- per arm ----
    per_arm = {}
    for arm_id, arm in arms.items():
        passes = arm["passes"]
        per_arm[arm_id] = {
            "judge": arm["judge"], "instrument": arm["instrument"], "source": arm["source"], "basis": arm["basis"],
            "passes": len(passes),
            "vs_creator": {name: agreement(passes, humans.creator, s) for name, s in subsets.items()},
            "vs_blind_mean": {name: agreement(passes, humans.blind_mean, s) for name, s in subsets.items()},
            "vs_pool4": {name: agreement(passes, humans.pool, s) for name, s in subsets.items()},
            "alt_test_creator": {name: alt_block(passes, s, humans, blind_by_sol, expert_by_sol,
                                                 detail=name == "human_written")
                                 for name, s in subsets.items()},
            "cloud_ratio": cloud(passes, humans, subsets, half_spread),
        }

    # ---- paired sheet - holistic, same judge ----
    contrasts = []
    for sheet in ("zero_shot_sheet", "few_shot_sheet"):
        for j in (LUNA, MINI, *HOLISTIC_FLAGSHIPS):
            a_id, b_id = f"{sheet}:{j}", f"holistic:{j}"
            if a_id not in arms or b_id not in arms:
                continue
            entry = {"a": a_id, "b": b_id}
            for ref_name, ref in (("creator", humans.creator), ("pool4", humans.pool)):
                entry[f"vs_{ref_name}"] = {
                    name: {"pass_mean": paired(arms[a_id]["passes"], arms[b_id]["passes"], s, ref, exam_of),
                           "first_pass": paired(arms[a_id]["passes"], arms[b_id]["passes"], s, ref, exam_of, True)}
                    for name, s in subsets.items()}
            contrasts.append(entry)

    n_j = [a["n_j"] for a in per_arm[f"holistic_benchmark_run:{BENCH_PRIMARY}"]["alt_test_creator"]["human_written"]
           ["first_pass"]["per_annotator"]]
    result = {
        "note": "D1 against the exam creator's un-blind grade as the expert reference (as D2 uses the exam "
                "author). Aggregates only. Generated by scripts/analysis/cslaw_creator_reference.py.",
        "definitions": {
            "reference": "the creator's grade (one per answer, raw 0-100). The creator wrote the case and the "
                         "model solution and graded un-blind (benchmark role 'creator').",
            "subsets": "human_written = the 30 annotation answers (classic and co-creation), the paper's agreement "
                       "basis; all = the 45 answers incl. the 15 model-generated ones",
            "totals": "sheet arms (zero-shot, few-shot) use the step sum 100 * sum(clip(score, 0, max)) / sum(max) "
                      "as in cslaw_first_iteration_local.py; holistic arms use the stored total (dimension sum)",
            "per_pass": "mae, bias (judge - reference) and Pearson r are computed per pass and averaged over the "
                        "complete passes (passes with a total on every answer of the subset), as in "
                        "compute_d2_validity.py; first_pass = per answer the lowest run index present",
            "vs_blind_mean / vs_pool4": "the same statistics against the mean of the three blind grades and "
                                        "against the mean of all four grades (the paper's pool)",
            "human_baseline": "each blind grader against the creator on the answers they graded; pair_level = "
                              "mean over all blind grades of |blind - creator| (each answer has three), the "
                              "counterpart of one judge pass; grader_level_mean_mae = unweighted mean of the "
                              "per-grader MAEs; blind_mean_vs_creator = the mean of three blind grades",
            "alt_test_creator": f"Calderon et al. (ACL 2025) alternative-annotator test, single-expert variant "
                                f"(section D.2) with the creator as the expert, run with the benchmark's "
                                f"compute_agreement._alt_test_single_expert: per blind annotator j, instance wins "
                                f"by point-wise distance to the creator (ties count for both), d = W_h - W_f, "
                                f"one-sided test of d_bar < epsilon (t for n_j >= 30, else exact Wilcoxon), "
                                f"Benjamini-Yekutieli FDR at q .05, annotators with n_j < 5 dropped, winning rate "
                                f"omega = rejected / m, pass iff omega >= 0.5. epsilon {EPS} (the benchmark's "
                                f"headline), {EPS_SENS} as sensitivity. Run on the first pass and on each complete "
                                f"pass; per_annotator detail for the first pass on the human-written subset",
            "cloud_ratio": "MAE against the blind mean divided by half the mean within-answer max-min spread of "
                           "the three blind grades. benchmark_definition: numerator first pass on the 30 "
                           "human-written answers, spread over all 45 answers (the benchmark's 10.83 / 11.94 = "
                           "0.91); pass_mean: numerator averaged over complete passes; matched_30: spread over the "
                           "same 30 answers; all_45: numerator on all 45 answers",
            "paired": "sheet arm minus the same judge's holistic arm in per-answer absolute error; pass_mean = "
                      "per answer the mean over each arm's complete passes (compute_d2_validity Cell.abs_err), "
                      f"first_pass = first pass only; exam-cluster bootstrap (15 exams resampled with replacement, "
                      f"seed {SEED}, {N_BOOT} draws, percentile 95 % CI); negative = the sheet is closer",
        },
        "caveats": [
            "The creator graded un-blind: they wrote the case and the model solution and knew both while grading.",
            ("The creator graded with the same 10-dimension scheme the holistic instrument uses, so the holistic "
            "arms share the reference's grading frame."),
            ("The generated sheets (zero-shot and few-shot) are built from the same model solution the creator "
            "wrote, so the sheet arms and the reference draw on one source."),
            (f"{humans.n_creators} creators cover the 15 exams. The reference is one grade per answer, so creator "
            "and exam effects are confounded and the reference carries no measured repeat noise."),
            (f"{len(humans.blind_who_created)} of the {len(humans.blind_graders)} blind graders created other exams; "
            "no blind grade comes from the exam's own creator."),
            (f"The alt-test has m = {len(n_j)} blind annotators with {min(n_j)} to {max(n_j)} answers each on the "
            "30 human-written answers, so omega moves in steps of 1/m and its Clopper-Pearson CI is wide."),
        ],
        "notes": {
            "control_primary_rows_differ_from_export": (
                f"control_results_temp0.jsonl carries a different single-pass total for the benchmark's primary "
                f"judge than the benchmark's export on {n_control_primary_diff} of 45 answers; this script takes "
                f"the export (the benchmark's own loader)"),
            "not_included": {
                "claude-opus-5, gpt-5.6-terra": "single zero-shot pass extracted from the DB only "
                                                "(judge_outcomes.json); no per-answer totals in the run outputs",
                "judge_results.jsonl": "the T=1 source-project zero-shot run (appendix), superseded by the T=0 "
                                       "clone that the judge table uses",
                "holistic claude-opus-4-7": "no matched holistic re-run; its benchmark single pass is included",
            },
        },
        "sources": ["benchathon_human_grades.json", "benchathon_human_grading_sample.json",
                    "Benchathon_export.json (ignored)", "benchathon_model_evaluations.json",
                    "benchathon_superseded_evaluations.json", "agreement_stats.json (anchors)",
                    "compute_agreement.py (alt-test code)", "picks_temp0.json", "clone_d6_actives.json",
                    *LOCAL_INPUTS, ("weight_sensitivity.json, reliability_conditions.json, agreement_bias.json, "
                    "bootstrap_cis.json, first_iteration.json, first_iteration_local.json (anchors)")],
        "seed": SEED, "n_boot": N_BOOT, "epsilon": EPS, "epsilon_sensitivity": EPS_SENS,
        "design": {"n_answers": 45, "n_human_written": 30, "n_exams": 15, "n_creators": humans.n_creators,
                   "n_blind_graders": len(humans.blind_graders), "blind_grades_per_answer": 3},
        "human_baseline": baseline,
        "half_blind_spread": half_spread,
        "arms": per_arm,
        "paired_sheet_minus_holistic": contrasts,
        "anchors": {
            "required": {
                "creator_vs_blind_mean_mae_45": {"value": hb45["mae"], "benchmark": cvb["mae_raw"]},
                "luna_zero_shot_vs_pool4_mae_30": {"value": luna_zs["first_pass"]["mae"], "first_iteration": fi["mae"]},
            },
            "n_failed": len(problems), "failed": problems,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fil.rounded(result), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}")

    # ---- console summary ----
    b30, b45 = baseline["human_written"], baseline["all"]
    print(f"human baseline vs creator: one blind grade MAE {b30['pair_level']['mae']:.2f} (30) / "
          f"{b45['pair_level']['mae']:.2f} (45), bias {b30['pair_level']['bias']:+.2f} / {b45['pair_level']['bias']:+.2f}, "
          f"r {b30['pair_level']['r']:.3f} / {b45['pair_level']['r']:.3f}; grader-level mean MAE "
          f"{b30['grader_level_mean_mae']:.2f} / {b45['grader_level_mean_mae']:.2f}; blind mean MAE "
          f"{b30['blind_mean_vs_creator']['mae']:.2f} / {b45['blind_mean_vs_creator']['mae']:.2f}")
    print(f"half blind spread: {half_spread['all']:.2f} (45), {half_spread['human_written']:.2f} (30)")
    hdr = (f"{'arm':44s} {'p':>1s} | {'MAE30':>6s} {'bias30':>7s} {'r30':>6s} | {'MAE45':>6s} {'bias45':>7s} "
           f"{'r45':>6s} | {'fpMAE30':>7s} | {'omega30':>7s} {'pass':>4s} | {'omega45':>7s} | {'cloud':>5s}")
    print(hdr)
    for arm_id, v in per_arm.items():
        c30, c45 = v["vs_creator"]["human_written"], v["vs_creator"]["all"]
        at30, at45 = v["alt_test_creator"]["human_written"]["first_pass"], v["alt_test_creator"]["all"]["first_pass"]

        def f(x, spec):
            return format(x, spec) if x is not None else "-"

        print(f"{arm_id[:44]:44s} {v['passes']:1d} | {f(c30['mae'], '6.2f')} {f(c30['bias'], '+7.2f')} {f(c30['r'], '6.3f')} | "
              f"{f(c45['mae'], '6.2f')} {f(c45['bias'], '+7.2f')} {f(c45['r'], '6.3f')} | {c30['first_pass']['mae']:7.2f} | "
              f"{at30['winning_rate']:7.2f} {'yes' if at30['passes_alt_test'] else 'no':>4s} | {at45['winning_rate']:7.2f} | "
              f"{f(v['cloud_ratio']['benchmark_definition'], '5.2f')}")
    for c in contrasts:
        for ref in ("creator", "pool4"):
            for name in ("human_written", "all"):
                x = c[f"vs_{ref}"][name]["pass_mean"]
                if x:
                    print(f"paired {c['a']} - {c['b'].split(':')[0]} vs {ref} {name}: {x['mean_diff']:+.2f} "
                          f"[{x['ci95'][0]:+.2f}, {x['ci95'][1]:+.2f}] n {x['n_answers']}")
    for p in problems:
        print("ANCHOR FAILED:", p)
    return 1 if (check and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
