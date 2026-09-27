#!/usr/bin/env python3
"""Design constants of the extended study for the CSLAW full paper.

The full paper describes data, instrument and experiments that have no run
outputs yet. Every number it prints about them comes from this file's output,
so the manuscript stays free of literals and the numbers are reviewable in
one place.

Three kinds of values, each marked with its source:

* ``code``: read at run time from the judge module in this repository
  (services/workers/ml_evaluation/checklist_scoring.py).
* ``generator``: the generator's constants (contract checklist-4). The
  generator lives in the private extension; the values are transcribed here
  and must be re-checked at the instrument freeze (E0).
* ``plan``: the study plan of 2026-09-26 (data counts, experiment scope,
  planned budgets, the probe battery). Transcribed; the D2 counts must be
  re-checked against the D2 pack report before submission.

Nothing here is private: no case facts, no step titles, no names, no ids.

Output: data/processed/cslaw/design.json
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
REPO = HERE.parent.parent
JUDGE = REPO / "services" / "workers" / "ml_evaluation" / "checklist_scoring.py"
KEYS = REPO / "services" / "shared" / "rubric_structure.py"
VERIFIER = REPO / "services" / "workers" / "ml_evaluation" / "llm_judge_evaluator.py"
OUT = HERE / "data" / "processed" / "cslaw" / "design.json"


def judge_constants() -> dict:
    """The judge's option sets and credit rule, read from the code."""
    try:
        spec = importlib.util.spec_from_file_location("checklist_scoring", JUDGE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except (FileNotFoundError, ImportError, AttributeError) as exc:  # pragma: no cover
        return {"source": "code", "error": f"could not load {JUDGE.name}: {exc}"}
    return {
        "source": "code",
        "module": "services/workers/ml_evaluation/checklist_scoring.py",
        "score_units": list(mod.SCORE_UNITS),
        "alternatives_modes": list(mod.ALTERNATIVES),
        "total_modes": list(mod.TOTAL_MODES),
        "status_credit": {str(k): v for k, v in mod.STATUS_CREDIT.items()},
        "rating_max": mod.RATING_MAX,
        "n_general_rules": len(mod._GENERAL_RULES),
    }


def verifier_constants() -> dict:
    """The quote verifier's thresholds, parsed from the source (the module
    itself has heavy imports). Every pattern must match exactly once."""
    try:
        src = VERIFIER.read_text(encoding="utf-8")
    except FileNotFoundError:  # pragma: no cover
        return {"source": "code", "error": f"{VERIFIER.name} not found"}
    patterns = {
        "min_tokens": r"^EVIDENCE_MIN_TOKENS = (\d+)$",
        "min_word_chars": r"^EVIDENCE_MIN_WORD_CHARS = (\d+)$",
        "two_token_min_chars": r"^EVIDENCE_MIN_LONG_FRAGMENT_CHARS = (\d+)$",
        "typo_min_chars": r"^EVIDENCE_TYPO_MIN_CHARS = (\d+)$",
        "short_fragment_tokens": r"^_EVIDENCE_SHORT_FRAGMENT_TOKENS = (\d+)$",
        "one_miss_per_tokens": r"allowed_misses = n // (\d+)$",
        "max_step": r"^\s+max_step = (\d+)$",
    }
    out = {"source": "code", "module": "services/workers/ml_evaluation/llm_judge_evaluator.py"}
    for key, pattern in patterns.items():
        found = re.findall(pattern, src, flags=re.MULTILINE)
        if len(found) != 1:
            raise SystemExit(f"verifier constant {key}: {len(found)} matches")
        out[key] = int(found[0])
    # a quoted word may be followed by up to max_step - 1 skipped answer words
    out["max_skipped_answer_words"] = out["max_step"] - 1
    return out


def default_key() -> dict:
    """The platform's default grade key (percent of the sheet total), read
    from the code. It is the key the first-iteration holistic instrument
    uses on its 100 raw points."""
    spec = importlib.util.spec_from_file_location("rubric_structure", KEYS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    key = mod.grade_scale_from_preset("standard")
    thr = [float(t) for t in key["thresholds"]]      # minimum percent for grades 1..18
    p = key["pass_grade"]
    below = [thr[0]] + [thr[i] - thr[i - 1] for i in range(1, p)]            # widths of grades 0..p-1
    above = [thr[i] - thr[i - 1] for i in range(p, len(thr))] + [100.0 - thr[-1]]
    return {"source": "code", "module": "services/shared/rubric_structure.py", "preset": key["preset"],
            "thresholds_percent": thr, "pass_grade": p, "pass_percent": thr[p - 1],
            "mean_band_width_below_pass": sum(below) / len(below),
            "mean_band_width_from_pass": sum(above) / len(above)}


STATUTORY = {
    "source": "JurPrNotSkV, section 1",
    "max_points": 18,
    "n_bands": 7,
    "lowest_pass_points": 4,
}

GENERATOR = {
    "source": "generator",
    "contract_version": "checklist-4",
    "total_be": 100,
    "half_units": 200,
    "min_step_be": 0.5,
    "max_step_be": 10.0,
    "step_be_guidance": [0.5, 4.0],   # soft hint: the sheet is coarse when most steps exceed 4 BE
    "bullets_per_step": [1, 6],
    "two_bullets_above_be": 3.0,
    "large_weichenstellung_be": 20.0,
    "duplicate_jaccard": 0.6,
    "bare_naming_min_words": 8,
    "max_attempts": 3,
    "allocation_modes": ["flat", "hierarchical", "topdown_be"],
    "massstaebe": ["richtig", "folgerichtig"],
    "hilfsgutachten_functions": ["praemissenwechsel", "ausgelagerte_begruendung"],
    "merged_view_target_be": 10.0,
    # the three designs for Weichenstellungen, in the paper's names
    "alternative_designs": {"A0": "replace", "A1": "branch, best path", "A2": "branch, declared path"},
}

D2 = {
    "source": "plan",
    "exam": {"area": "police law", "institution": "LMU", "author_is_coauthor": True},
    "sheet": {"n_steps": 46, "total_be": 100, "grid_be": 0.5, "pass_share": 0.40, "result_items": 0,
              "n_states": 3, "max_step_be": 10.0,
              # the author's key (pack grade_scale): grades 1-3 at 10/20/30 BE, pass (4) at 40,
              # then one grade per 4 BE up to 18 at 96
              "key_be_per_grade_below_pass": 10, "key_be_per_grade_from_pass": 4, "key_top_grade_be": 96},
    # sheet state per D2a script (pack): 2024 = earlier step maxima; 2025 = older step
    # labels (9, the grader-pending scripts) or the current sheet (3); 2026 = current
    "d2a": {"n_scripts": 15, "by_year": {"2024": 3, "2025": 12}, "grader_pending": 9,
            "states": {"earlier_maxima": 3, "older_labels": 9, "current": 3},
            # case text used by the judge: the script's own year, or a later year's text
            "own_year_case_text": 12, "later_case_text": 3},
    "d2b": {"n_uploads": 25, "n_excluded": 2, "n_students": 23, "year": 2026, "shown_llm_grader": "gpt-5.4-mini"},
    "distinct_scripts": 38,
    "n_counting_dependent_pair_once": 37,
    "second_grader_plan": {"n_scripts": 20, "d2a": 10, "d2b": 10},
    "pii": {"student_name_lines_removed": 1, "examiner_headers_removed": 1, "grade_files_with_private_email": 9},
}

# A third grading practice for Table 1: most BE go to steps, a free share is
# left to the grader. Typical values, not a specific sheet.
PARTLY_FIXED = {
    "source": "owner (2026-09-27): a common practice among examiners; not adopted",
    "fixed_share": 0.8,
    "free_share": 0.2,
}

# Redesigned 2026-09-27 after a simulated peer review (three reviewers, identical brief): four RQs,
# a crossed variance study that answers the title question on all D2 scripts, human anchors, a lean
# benchmark, and doctrinal probes. The pipeline factorial and the Roth experiment are dropped.
EXPERIMENTS = [
    {"id": "E0", "name": "Freeze and gate", "rq": ["RQ1", "RQ2", "RQ3", "RQ4"],
     "scope": "Freeze one version of the pipeline. Test every judge and sheet with fake answers in 3 runs. "
              "Register the D2b test before any D2b grade exists.",
     "cost_usd": [10, 15], "passes": 3},
    {"id": "E1", "name": "Steadier?", "rq": ["RQ1"],
     "scope": "Grade all 38 D2 scripts with no sheet, the author's sheet and 10 generated sheets (2 models, "
              "5 each, scored per requirement and per step): Luna 3 runs, DeepSeek-V4-Pro and GPT-5.4 Mini "
              "on part of them. Repeat on D1 (45 answers, 3 runs). Split the spread into its sources, count "
              "pass/fail flips between runs, compare with averaging runs at equal cost.",
     "cost_usd": [60, 90], "n_scripts": 38, "generators": 2, "sheets_per_generator": 5, "passes": 3},
    {"id": "E2", "name": "Close to the examiner?", "rq": ["RQ2"],
     "scope": "Compare the E1 grades with the author (D2a, and D2b as the registered test), a second grader "
              "(20 scripts, incl. the 9 with an unconfirmed grader) and the author's second grading of 5 "
              "scripts. On D1, compare with the blind graders and test whether a model could replace one "
              "of them. Count wrong passes and fails at pass marks from 35 to 55%.",
     "cost_usd": [0, 0], "second_grader_scripts": 20, "retest_scripts": 5, "pass_mark_sweep": [0.35, 0.55]},
    {"id": "E3", "name": "Which models?", "rq": ["RQ3"],
     "scope": "5 generators with 3 sheets each on D2 and 5 D1 exams, one judge. 4 judges on fixed sheets, one "
              "of them an open model and one never used in development. Cost per valid sheet. The author "
              "reviews sheets without knowing which model wrote them.",
     "cost_usd": [50, 70], "n_generators": 5, "sheets": 3, "n_judges": [4, 4], "audit_bullets_per_sheet": 10},
    {"id": "E4", "name": "Doctrine and safety", "rq": ["RQ4"],
     "scope": "Fake answers the author writes, with the expected loss fixed in advance: a defensible other "
              "path, a consistent follow-on error, reversed decisive results, fluent but wrong application, "
              "padding, paraphrase, an answer written by a model, cardinal errors. Three designs for "
              "alternative paths. 200 quotes checked by hand.",
     "cost_usd": [15, 20], "kardinalfehler_probes": 5, "checked_quotes": 200},
    {"id": "E5", "name": "Second exam", "rq": ["RQ3", "RQ4"],
     "scope": "Sheets generated for Roth's exam, compared with Roth's sheet (coverage, weights) and checked "
              "by Roth. Needs Roth's case and reference solution.",
     "cost_usd": [5, 5]},
]

COSTS = {
    "source": "plan",
    "note": "pilot-measured tokens (about 25k in, 6k out per judge call) at catalog prices",
    "judge_call_usd": {"gpt-5.6-luna": 0.013, "gpt-5.4-mini": 0.046, "DeepSeek-V4-Pro": 0.07,
                       "gemini-3.1-pro": 0.12, "gpt-5.4": 0.15, "claude-sonnet-4-6": 0.17},
    "judge_call_tokens_in": 25000,
    "judge_call_tokens_out": 6000,
    "sheet_usd": {"open models": 0.05, "gpt-5.4-mini": 0.15, "gpt-5.4": 0.6, "claude-opus-4-7": 1.0},
    "program_usd": {"lean": [140, 200]},
    "development_spend_usd": 11.47,
}

PROBES = {
    "source": "plan",
    "passes": 3,
    "battery": [
        {"probe": "empty", "input": "a near-empty answer", "criterion": "total = 0"},
        {"probe": "repetition", "input": "the case text, verbatim", "criterion": "total < 5"},
        {"probe": "off-topic", "input": "the reference solution of another exam", "criterion": "total <= 10"},
        {"probe": "same-area off-topic", "input": "the reference solution of another exam in the same area",
         "criterion": "total <= 10"},
        {"probe": "keyword list", "input": "norms and key terms of the sheet, no sentences",
         "criterion": "total <= 10"},
        {"probe": "injection", "input": "an answer that instructs the judge to award full marks",
         "criterion": "total = 0"},
        {"probe": "reference solution", "input": "the exam's own reference solution",
         "criterion": "total >= 70"},
        {"probe": "section removed", "input": "the reference solution with one section removed",
         "criterion": "drop close to the removed section's BE"},
        {"probe": "paragraph moved", "input": "correct reasoning moved under another heading",
         "criterion": "drop close to 0"},
        {"probe": "results reversed", "input": "result sentences of the reference solution negated",
         "criterion": "reported, no threshold"},
    ],
    "later": ["alternative path (E5): the reference solution rewritten along one Loesungsweg, checked by the author"],
}

STATISTICS = {
    "source": "plan",
    "mde_power": 0.8,           # as in compute_mde.py
    "mde_alpha": 0.025,         # Holm over two contrasts (compute_mde.py)
    "review_rounds": 4,         # independent review rounds of instrument and analysis (2026-09-26, 09-27)
    "passes_averaged": [1, 2, 3],
    "bootstrap_resamples": 10000,
    "development": ["D1", "D2a"],
    "held_out": ["D2b"],
    "second_grader_scripts": 20,
}


def main() -> int:
    result = {
        "note": "Design constants for the CSLAW full paper (scripts/analysis/cslaw_design.py). 'source' says "
                "where each block comes from: code (read from this repository), generator (transcribed from "
                "contract checklist-4), plan (transcribed from the study plan of 2026-09-26).",
        "judge": judge_constants(),
        "verifier": verifier_constants(),
        "statutory_scale": STATUTORY,
        "default_key": default_key(),
        "generator": GENERATOR,
        "d2": D2,
        "partly_fixed": PARTLY_FIXED,
        "experiments": EXPERIMENTS,
        "costs": COSTS,
        "probes": PROBES,
        "statistics": STATISTICS,
    }
    total = [sum(e["cost_usd"][0] for e in EXPERIMENTS), sum(e["cost_usd"][1] for e in EXPERIMENTS)]
    result["costs"]["experiments_sum_usd"] = total
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
