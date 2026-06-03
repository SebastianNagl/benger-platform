"""RQ4 data trace — one CSV per analytic step that goes into the
manuscript's RQ4 prose.

Mirrors the layout of `assets/rq5/` (built by `rq5_data_trace.py`):
each step gets its own numbered CSV plus a README.md explaining how each
file maps to the RQ4 narrative.

Reads (all read-only):
  data/processed/agreement_stats.json     headline RQ4 stats (computed by compute_agreement.py)
  data/raw/benchathon/Benchathon-tasks-2026-05-31.json   raw annotations + judge evaluations
  data/processed/benchathon_instruction_variants.json    annotation_id -> "ai" / "no_ai"

Writes:
  assets/rq4/01_cohort.csv
  assets/rq4/02_per_condition_means.csv
  assets/rq4/03_mean_difference_bootstraps.csv
  assets/rq4/04_per_participant_paired.csv
  assets/rq4/05_by_bereich.csv
  assets/rq4/06_tost_vs_flagship.csv
  assets/rq4/07_blind_human_cross_check.csv
  assets/rq4/08_judge_vs_human_gap.csv
  assets/rq4/README.md

Re-run after any pipeline change:
  python scripts/rq4_data_trace.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
RAW = HERE / "data" / "raw"
ASSETS = HERE / "assets" / "rq4"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_paper_exports import BASELINE_JUDGE_FIELD_PREFIX  # noqa: E402


def index_judge_on_humans(real):
    """annotation_id -> {"raw_score": float | None} for judge evaluations on
    human:loesung annotations under the baseline single-pass judge prefix.

    Inlined here (rather than imported from compute_agreement) so this script
    stays lightweight — compute_agreement carries heavy stats deps (pandas,
    pingouin, sklearn) that we don't need for the data trace.
    """
    out = {}
    for task in real["tasks"]:
        for ev in task.get("evaluations") or []:
            fn = ev.get("field_name") or ""
            if not fn.startswith(BASELINE_JUDGE_FIELD_PREFIX):
                continue
            if "human:loesung" not in fn:
                continue
            ann_id = ev.get("annotation_id")
            if not ann_id:
                continue
            m = ev.get("metrics") or {}
            raw = None
            # Flat-key shape (what the Benchathon export actually uses):
            # llm_judge_falloesung_raw on 0-100.
            if m.get("llm_judge_falloesung_raw") is not None:
                raw = float(m["llm_judge_falloesung_raw"])
            else:
                # Fallbacks for nested shapes used by other corpora / vintages.
                judge = m.get("llm_judge_falloesung")
                if isinstance(judge, dict):
                    details = judge.get("details") or {}
                    if details.get("raw_score") is not None:
                        raw = float(details["raw_score"])
                    elif judge.get("value") is not None:
                        v = float(judge["value"])
                        raw = v * 100.0 if v <= 1.0 else v
                elif isinstance(judge, (int, float)):
                    v = float(judge)
                    raw = v * 100.0 if v <= 1.0 else v
                if raw is None and m.get("raw_score") is not None:
                    raw = float(m["raw_score"])
            if raw is not None:
                out[ann_id] = {"raw_score": raw}
    return out


def _gp(raw_points):
    return None if raw_points is None else raw_points * 18 / 100


def _r(v, w=3):
    return None if v is None else round(v, w)


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    ag = json.loads((PROCESSED / "agreement_stats.json").read_text())
    real = json.loads((RAW / "benchathon" / "Benchathon-tasks-2026-05-31.json").read_text())
    variants = json.loads((PROCESSED / "benchathon_instruction_variants.json").read_text())

    r4 = ag.get("rq4_cocreation") or {}
    r4b = ag.get("rq4_cocreation_by_bereich") or {}
    r4h = ag.get("rq4_cocreation_blind_human") or {}
    r4_tost = ag.get("rq4_cocreation_vs_flagship_tost") or {}
    flagship = (((ag.get("tier_aggregates") or {}).get("benchathon") or {}).get("by_tier") or {}).get("flagship") or {}

    # Raw per-annotation join: annotation_id -> dict
    judge_by_ann = index_judge_on_humans(real)
    ann_to_user, ann_to_task, ann_to_bereich = {}, {}, {}
    for task in real["tasks"]:
        bereich = (task.get("data") or {}).get("bereich")
        for ann in (task.get("annotations") or []):
            ann_to_user[ann["id"]] = ann.get("completed_by")
            ann_to_task[ann["id"]] = task["id"]
            ann_to_bereich[ann["id"]] = bereich

    # Per-participant raw-score lists, split by arm
    by_user_trad = defaultdict(list)
    by_user_ai = defaultdict(list)
    for ann_id, j in judge_by_ann.items():
        raw = j.get("raw_score")
        if raw is None:
            continue
        v = variants.get(ann_id)
        uid = ann_to_user.get(ann_id)
        if uid is None or v not in ("ai", "no_ai"):
            continue
        (by_user_ai if v == "ai" else by_user_trad)[uid].append(float(raw))

    # ----------------------------- 01 cohort -----------------------------
    n_trad_only = sum(1 for u in by_user_trad if u not in by_user_ai)
    n_ai_only = sum(1 for u in by_user_ai if u not in by_user_trad)
    n_both = sum(1 for u in by_user_ai if u in by_user_trad)
    _write_csv(
        ASSETS / "01_cohort.csv",
        ["pool", "n_annotations", "n_participants", "note"],
        [
            {"pool": "traditional",
             "n_annotations": r4.get("n_traditional"),
             "n_participants": r4.get("n_participants_trad"),
             "note": "participants who contributed at least one traditional annotation"},
            {"pool": "co_creation",
             "n_annotations": r4.get("n_co_creation"),
             "n_participants": r4.get("n_participants_ai"),
             "note": "participants who contributed at least one co-creation annotation"},
            {"pool": "participants_in_both_arms",
             "n_annotations": "",
             "n_participants": n_both,
             "note": "unit for the within-participant paired test (Step 3, paired row)"},
            {"pool": "participants_traditional_only",
             "n_annotations": "",
             "n_participants": n_trad_only,
             "note": "did trad but skipped co-creation (rare)"},
            {"pool": "participants_co_creation_only",
             "n_annotations": "",
             "n_participants": n_ai_only,
             "note": "did co-creation but skipped trad — drives the 155 vs 65 imbalance"},
        ],
    )

    # ----------------------- 02 per-condition means ----------------------
    def _arm_stats(by_user, n_total):
        vals = [v for vs in by_user.values() for v in vs]
        return {
            "mean_raw": statistics.mean(vals) if vals else None,
            "stdev_raw": statistics.stdev(vals) if len(vals) > 1 else None,
            "n_annotations": len(vals),
            "n_participants": len(by_user),
        }
    trad_stats = _arm_stats(by_user_trad, r4.get("n_traditional"))
    ai_stats = _arm_stats(by_user_ai, r4.get("n_co_creation"))
    _write_csv(
        ASSETS / "02_per_condition_means.csv",
        ["condition", "mean_raw_0_100", "mean_grade_points_0_18",
         "stdev_raw", "n_annotations", "n_participants", "note"],
        [
            {"condition": "traditional",
             "mean_raw_0_100": _r(trad_stats["mean_raw"]),
             "mean_grade_points_0_18": _r(_gp(trad_stats["mean_raw"])),
             "stdev_raw": _r(trad_stats["stdev_raw"]),
             "n_annotations": trad_stats["n_annotations"],
             "n_participants": trad_stats["n_participants"],
             "note": "no AI tools allowed; books and statutes only"},
            {"condition": "co_creation",
             "mean_raw_0_100": _r(ai_stats["mean_raw"]),
             "mean_grade_points_0_18": _r(_gp(ai_stats["mean_raw"])),
             "stdev_raw": _r(ai_stats["stdev_raw"]),
             "n_annotations": ai_stats["n_annotations"],
             "n_participants": ai_stats["n_participants"],
             "note": "any LLM(s) of participant's choosing"},
        ],
    )

    # ------------------ 03 mean-difference bootstraps --------------------
    rows = []
    rows.append({
        "method": "iid_annotation_bootstrap",
        "delta_raw": _r(r4.get("mean_diff_ai_minus_trad_iid")),
        "delta_grade_points": _r(_gp(r4.get("mean_diff_ai_minus_trad_iid"))),
        "ci95_lo_raw": _r(r4.get("ci95_lo_iid")),
        "ci95_hi_raw": _r(r4.get("ci95_hi_iid")),
        "ci95_lo_grade_points": _r(_gp(r4.get("ci95_lo_iid"))),
        "ci95_hi_grade_points": _r(_gp(r4.get("ci95_hi_iid"))),
        "n_resample_units": (r4.get("n_traditional") or 0) + (r4.get("n_co_creation") or 0),
        "resample_unit": "annotation",
        "role": "diagnostic_only_assumes_independence",
        "note": "naive bootstrap; fools itself about effective n because same participant contributes many annotations",
    })
    rows.append({
        "method": "participant_cluster_bootstrap",
        "delta_raw": _r(r4.get("mean_diff_ai_minus_trad")),
        "delta_grade_points": _r(_gp(r4.get("mean_diff_ai_minus_trad"))),
        "ci95_lo_raw": _r(r4.get("ci95_lo")),
        "ci95_hi_raw": _r(r4.get("ci95_hi")),
        "ci95_lo_grade_points": _r(_gp(r4.get("ci95_lo"))),
        "ci95_hi_grade_points": _r(_gp(r4.get("ci95_hi"))),
        "n_resample_units": (r4.get("n_participants_trad") or 0) + (r4.get("n_participants_ai") or 0),
        "resample_unit": "participant",
        "role": "HEADLINE",
        "note": "resamples participants with replacement; honest about the per-participant clustering of annotations",
    })
    rows.append({
        "method": "task_cluster_bootstrap",
        "delta_raw": _r(r4.get("mean_diff_cluster_task")),
        "delta_grade_points": _r(_gp(r4.get("mean_diff_cluster_task"))),
        "ci95_lo_raw": _r(r4.get("ci95_lo_cluster_task")),
        "ci95_hi_raw": _r(r4.get("ci95_hi_cluster_task")),
        "ci95_lo_grade_points": _r(_gp(r4.get("ci95_lo_cluster_task"))),
        "ci95_hi_grade_points": _r(_gp(r4.get("ci95_hi_cluster_task"))),
        "n_resample_units": 15,
        "resample_unit": "task",
        "role": "robustness_check",
        "note": "resamples Benchathon tasks; rules out a particular hard task driving the effect",
    })
    rows.append({
        "method": "paired_within_participant",
        "delta_raw": _r(r4.get("mean_diff_paired_within_participant")),
        "delta_grade_points": _r(_gp(r4.get("mean_diff_paired_within_participant"))),
        "ci95_lo_raw": _r(r4.get("ci95_lo_paired_within_participant")),
        "ci95_hi_raw": _r(r4.get("ci95_hi_paired_within_participant")),
        "ci95_lo_grade_points": _r(_gp(r4.get("ci95_lo_paired_within_participant"))),
        "ci95_hi_grade_points": _r(_gp(r4.get("ci95_hi_paired_within_participant"))),
        "n_resample_units": r4.get("n_participants_paired"),
        "resample_unit": "participant_in_both_arms",
        "role": "cleanest_within_subject_test",
        "note": "compares each participant to themselves; eliminates between-participant covariates (expertise, motivation, etc.)",
    })
    _write_csv(
        ASSETS / "03_mean_difference_bootstraps.csv",
        ["method", "delta_raw", "delta_grade_points",
         "ci95_lo_raw", "ci95_hi_raw",
         "ci95_lo_grade_points", "ci95_hi_grade_points",
         "n_resample_units", "resample_unit", "role", "note"],
        rows,
    )

    # ----------------- 04 per-participant paired deltas ------------------
    paired_rows = []
    for uid in sorted(set(by_user_trad) & set(by_user_ai)):
        trad_vals = by_user_trad[uid]
        ai_vals = by_user_ai[uid]
        paired_rows.append({
            "participant_id": uid,
            "n_traditional": len(trad_vals),
            "n_co_creation": len(ai_vals),
            "mean_traditional_raw": _r(statistics.mean(trad_vals)),
            "mean_co_creation_raw": _r(statistics.mean(ai_vals)),
            "delta_ai_minus_trad_raw": round(
                statistics.mean(ai_vals) - statistics.mean(trad_vals), 3),
            "delta_ai_minus_trad_grade_points": round(
                _gp(statistics.mean(ai_vals) - statistics.mean(trad_vals)), 3),
        })
    paired_rows.sort(key=lambda r: r["delta_ai_minus_trad_raw"], reverse=True)
    _write_csv(
        ASSETS / "04_per_participant_paired.csv",
        ["participant_id", "n_traditional", "n_co_creation",
         "mean_traditional_raw", "mean_co_creation_raw",
         "delta_ai_minus_trad_raw", "delta_ai_minus_trad_grade_points"],
        paired_rows,
    )

    # --------------------------- 05 by Bereich ---------------------------
    bereich_rows = []
    for name in ("Zivilrecht", "Strafrecht", "Öffentliches Recht"):
        b = (r4b or {}).get(name)
        if not b:
            continue
        bereich_rows.append({
            "bereich": name,
            "mean_traditional_raw": _r(b.get("mean_traditional")),
            "mean_co_creation_raw": _r(b.get("mean_co_creation")),
            "delta_raw": _r(b.get("mean_diff_ai_minus_trad")),
            "delta_grade_points": _r(_gp(b.get("mean_diff_ai_minus_trad"))),
            "ci95_lo_raw_iid": _r(b.get("ci95_lo")),
            "ci95_hi_raw_iid": _r(b.get("ci95_hi")),
            "n_traditional": b.get("n_traditional"),
            "n_co_creation": b.get("n_co_creation"),
            "note": "descriptive only — no inferential per-domain test",
        })
    _write_csv(
        ASSETS / "05_by_bereich.csv",
        ["bereich", "mean_traditional_raw", "mean_co_creation_raw",
         "delta_raw", "delta_grade_points",
         "ci95_lo_raw_iid", "ci95_hi_raw_iid",
         "n_traditional", "n_co_creation", "note"],
        bereich_rows,
    )

    # ----------------------- 06 TOST vs flagship -------------------------
    _write_csv(
        ASSETS / "06_tost_vs_flagship.csv",
        ["quantity", "value", "note"],
        [
            {"quantity": "mean_co_creation_raw",
             "value": _r(r4.get("mean_co_creation")),
             "note": "n=155 co-creation annotations"},
            {"quantity": "mean_flagship_tier_raw",
             "value": _r(flagship.get("mean_raw")),
             "note": f"flagship pool, n_gen={flagship.get('n_generations')}"},
            {"quantity": "flagship_ci95_lo_raw",
             "value": _r(flagship.get("ci95_lo")), "note": ""},
            {"quantity": "flagship_ci95_hi_raw",
             "value": _r(flagship.get("ci95_hi")), "note": ""},
            {"quantity": "delta_co_creation_minus_flagship_raw",
             "value": _r(r4_tost.get("point_estimate")),
             "note": "point estimate; negative means co-creation slightly below flagship"},
            {"quantity": "equivalence_band_lo_raw",
             "value": r4_tost.get("eq_low"),
             "note": "we'd call any difference within [-5,+5] practically equivalent"},
            {"quantity": "equivalence_band_hi_raw",
             "value": r4_tost.get("eq_high"), "note": ""},
            {"quantity": "tost_one_sided_95_lower_raw",
             "value": _r(r4_tost.get("one_sided_lower_95")),
             "note": "must be > eq_lo to reject 'co-creation is meaningfully worse'"},
            {"quantity": "tost_one_sided_95_upper_raw",
             "value": _r(r4_tost.get("one_sided_upper_95")),
             "note": "must be < eq_hi to reject 'co-creation is meaningfully better'"},
            {"quantity": "reject_h0_co_creation_meaningfully_worse",
             "value": r4_tost.get("reject_h0_low"), "note": ""},
            {"quantity": "reject_h0_co_creation_meaningfully_better",
             "value": r4_tost.get("reject_h0_high"), "note": ""},
            {"quantity": "equivalent_within_5_raw_points",
             "value": r4_tost.get("equivalent"),
             "note": "HEADLINE: both rejections fire => statistically equivalent within the band"},
        ],
    )

    # --------------- 07 blind-human cross-check (n=15+15) ---------------
    _write_csv(
        ASSETS / "07_blind_human_cross_check.csv",
        ["quantity", "value", "note"],
        [
            {"quantity": "n_traditional",
             "value": r4h.get("n_traditional"),
             "note": "validation subset solutions written traditional-style"},
            {"quantity": "n_co_creation",
             "value": r4h.get("n_co_creation"),
             "note": "validation subset solutions written co-creation-style"},
            {"quantity": "n_participants_traditional",
             "value": r4h.get("n_participants_trad"),
             "note": ""},
            {"quantity": "n_participants_co_creation",
             "value": r4h.get("n_participants_ai"),
             "note": ""},
            {"quantity": "mean_traditional_raw_blind_human",
             "value": _r(r4h.get("mean_traditional")),
             "note": "blind-reviewer pool average"},
            {"quantity": "mean_co_creation_raw_blind_human",
             "value": _r(r4h.get("mean_co_creation")),
             "note": ""},
            {"quantity": "delta_ai_minus_trad_raw_blind_human",
             "value": _r(r4h.get("mean_diff_ai_minus_trad")),
             "note": "HEADLINE: sign matches the judge result, but the CI spans zero at this n"},
            {"quantity": "delta_grade_points_blind_human",
             "value": _r(_gp(r4h.get("mean_diff_ai_minus_trad"))),
             "note": ""},
            {"quantity": "ci95_lo_raw_participant_cluster",
             "value": _r(r4h.get("ci95_lo")),
             "note": "HEADLINE CI — crosses zero at n=15 per arm"},
            {"quantity": "ci95_hi_raw_participant_cluster",
             "value": _r(r4h.get("ci95_hi")),
             "note": ""},
            {"quantity": "ci95_lo_raw_iid_diagnostic",
             "value": _r(r4h.get("ci95_lo_iid")),
             "note": "diagnostic only"},
            {"quantity": "ci95_hi_raw_iid_diagnostic",
             "value": _r(r4h.get("ci95_hi_iid")),
             "note": ""},
        ],
    )

    # ------------- 08 judge vs blind-human gap (calibration) -------------
    judge_delta = r4.get("mean_diff_ai_minus_trad")
    human_delta = r4h.get("mean_diff_ai_minus_trad")
    gap = (judge_delta - human_delta) if (judge_delta is not None and human_delta is not None) else None
    # Pull content-dependent calibration offsets from judge_calibration.json
    jc_path = PROCESSED / "judge_calibration.json"
    jc = json.loads(jc_path.read_text()) if jc_path.exists() else []
    def _by_label(needle):
        for r in jc:
            if needle in r.get("label", ""):
                return r
        return {}
    gpt_human = _by_label("Config B gpt-5-mini  (human)").get("judge_minus_pool_mean")
    gpt_llm = _by_label("Config B gpt-5-mini  (LLM)").get("judge_minus_pool_mean")
    content_diff = (gpt_llm - gpt_human) if (gpt_human is not None and gpt_llm is not None) else None
    inferred_llm_share = (gap / content_diff) if (gap is not None and content_diff) else None
    _write_csv(
        ASSETS / "08_judge_vs_human_gap.csv",
        ["quantity", "value", "note"],
        [
            {"quantity": "judge_delta_raw",
             "value": _r(judge_delta),
             "note": "Step 3 headline (participant-clustered)"},
            {"quantity": "blind_human_delta_raw",
             "value": _r(human_delta),
             "note": "Step 7 headline"},
            {"quantity": "gap_judge_minus_human_raw",
             "value": _r(gap),
             "note": "empirical bound on how much of the headline is judge-style premium on AI-assisted writing"},
            {"quantity": "judge_offset_on_human_content_raw",
             "value": _r(gpt_human),
             "note": "from RQ5 calibration audit (Config B GPT-5-mini, human picks)"},
            {"quantity": "judge_offset_on_llm_content_raw",
             "value": _r(gpt_llm),
             "note": "from RQ5 calibration audit (Config B GPT-5-mini, LLM picks)"},
            {"quantity": "content_dependent_differential_raw",
             "value": _r(content_diff),
             "note": "judge gives this much extra credit to LLM-styled vs human-styled content"},
            {"quantity": "implied_llm_styled_share_of_co_creation",
             "value": _r(inferred_llm_share) if inferred_llm_share is not None else None,
             "note": "the gap (~6.3) divided by the differential (~10.7) ≈ 0.6 — judge sees co-creation as ~60% LLM-styled"},
        ],
    )

    # ----------------------------- README --------------------------------
    readme = ASSETS / "README.md"
    readme.write_text(
        "# RQ4 data trace\n\n"
        "One CSV per RQ4 analytic step. Open in Excel / Numbers / any csv viewer.\n\n"
        "| File | RQ4 step | What it contains |\n"
        "|---|---|---|\n"
        "| `01_cohort.csv` | Cohort and per-condition pools | Annotation counts and participant counts per arm; the imbalance that drives the skip-mechanism story. |\n"
        "| `02_per_condition_means.csv` | Per-condition mean LLM-judge scores | Mean raw 0–100 and grade-point 0–18 per condition, plus stdev and n. |\n"
        "| `03_mean_difference_bootstraps.csv` | Mean difference Δ under four resampling units | Δ and 95% CI under i.i.d. bootstrap, participant-cluster bootstrap (HEADLINE), task-cluster bootstrap, and within-participant paired delta. |\n"
        "| `04_per_participant_paired.csv` | Within-participant paired test (underlying data) | One row per participant who did both arms — their per-arm mean and personal Δ. This is the data behind the paired row in CSV 03. |\n"
        "| `05_by_bereich.csv` | Per legal area (Zivil / Straf / Öffentlich) | Descriptive per-domain Δ values with i.i.d. CIs. No inferential test. |\n"
        "| `06_tost_vs_flagship.csv` | TOST equivalence vs closed-flagship LLM tier | Per-arm means, equivalence band, one-sided 95% bounds, equivalence decision. |\n"
        "| `07_blind_human_cross_check.csv` | Blind-human cross-check (RQ5 validation subset, n=15+15) | Same contrast scored by the blind human pool; both participant-cluster and i.i.d. CIs. |\n"
        "| `08_judge_vs_human_gap.csv` | Judge vs blind-human gap explained by content-dependent calibration | The ~6-raw-point gap between judge and human Δ, and the ~10-raw-point content-dependent calibration offset from RQ5 that explains it. |\n"
        "\n"
        "Regenerate with `python scripts/rq4_data_trace.py`.\n",
        encoding="utf-8",
    )

    print(f"wrote 8 CSVs + README to {ASSETS}")


if __name__ == "__main__":
    main()
