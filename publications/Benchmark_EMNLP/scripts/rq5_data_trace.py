"""Generate one CSV per RQ5 test/analysis in `assets/rq5/`. Each file is a
flat table with named columns so it can be opened in Excel or any CSV tool
and tied back to a specific RQ5 paragraph or table in the manuscript.

Files produced:
    assets/rq5/01_per_solution_agreement.csv
    assets/rq5/02_blind_reviewer_irr.csv
    assets/rq5/03_calderon_alttest_summary.csv
    assets/rq5/04_calderon_per_annotator.csv
    assets/rq5/05_calderon_single_expert.csv
    assets/rq5/06_judge_calibration.csv
    assets/rq5/07_dimension_agreement.csv
    assets/rq5/08_intrajudge_stability.csv
    assets/rq5/09_interjudge_agreement.csv
    assets/rq5/README.md

    uv run python scripts/rq5_data_trace.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
OUT_DIR = HERE / "assets" / "rq5"


def load(name):
    p = PROCESSED / name
    return json.loads(p.read_text()) if p.exists() else {}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in fieldnames})


def main():
    agreement = load("agreement_stats.json")
    cpj = load("calderon_per_judge.json")
    calib_rows = load("judge_calibration.json") or []
    inter = load("benchathon_inter_judge_agreement.json")

    # =========================================================================
    # 01 — Per-solution judge vs. mean blind reviewer
    # =========================================================================
    jvh_h = agreement.get("rq5_judge_vs_human") or {}
    jvh_l = agreement.get("rq5_judge_on_llm_solutions") or {}

    def per_sol_row(corpus, src, d, n_key):
        return {
            "corpus": corpus,
            "n": d.get(n_key),
            "pearson_raw": d.get("pearson_raw"),
            "spearman_raw": d.get("spearman_raw"),
            "cohen_kappa_passfail": d.get("passfail_cohen_kappa"),
            "mae_raw": d.get("mae_raw"),
            "mae_grade_points": d.get("mae_grade_points"),
            "calibration_offset_raw": d.get("judge_minus_pool_mean_raw"),
            "calibration_offset_grade_points": d.get("judge_minus_pool_mean_grade_points"),
            "mae_raw_bias_corrected": d.get("mae_raw_bias_corrected"),
            "mae_grade_points_bias_corrected": d.get("mae_grade_points_bias_corrected"),
            "source": src,
        }
    write_csv(
        OUT_DIR / "01_per_solution_agreement.csv",
        ["corpus", "n", "pearson_raw", "spearman_raw", "cohen_kappa_passfail",
         "mae_raw", "mae_grade_points", "calibration_offset_raw",
         "calibration_offset_grade_points", "mae_raw_bias_corrected",
         "mae_grade_points_bias_corrected", "source"],
        [
            per_sol_row("human-authored", "rq5_judge_vs_human",         jvh_h, "n_annotations"),
            per_sol_row("LLM-generated",  "rq5_judge_on_llm_solutions", jvh_l, "n_generations"),
        ],
    )

    # =========================================================================
    # 02 — Blind-reviewer inter-rater reliability (ICC + within-annotation spread)
    # =========================================================================
    irr = agreement.get("rq5_human_irr") or {}
    irr_type = agreement.get("rq5_human_irr_by_solution_type") or {}

    def irr_row(name, d):
        return {
            "subset": name,
            "n_annotations": d.get("n_annotations"),
            "k_raters": d.get("k_raters"),
            "icc_2_1_raw": d.get("icc_2_1_raw"),
            "icc_2_k_raw": d.get("icc_2_k_raw"),
            "icc_2_1_grade_points": d.get("icc_2_1_grade_points"),
            "icc_2_k_grade_points": d.get("icc_2_k_grade_points"),
            "mean_within_ann_spread_raw": d.get("mean_within_ann_spread_raw"),
            "mean_within_ann_spread_grade_points": d.get("mean_within_ann_spread_grade_points"),
        }
    irr_csv_rows = [irr_row("All blind picks (pooled)", irr)]
    for stype in ("human_traditional", "human_co_creation", "llm_system"):
        st = irr_type.get(stype) or {}
        if st:
            irr_csv_rows.append(irr_row(stype, st))
    write_csv(
        OUT_DIR / "02_blind_reviewer_irr.csv",
        ["subset", "n_annotations", "k_raters",
         "icc_2_1_raw", "icc_2_k_raw",
         "icc_2_1_grade_points", "icc_2_k_grade_points",
         "mean_within_ann_spread_raw", "mean_within_ann_spread_grade_points"],
        irr_csv_rows,
    )

    # =========================================================================
    # 03 — Calderon §3 alt-test, per-judge summary
    # =========================================================================
    JUDGE_DISPLAY = {
        "gpt5":   "GPT-5-mini (Config B)",
        "gemini": "Gemini-3.1-Pro (Config B)",
        "opus":   "Opus-4.7 (Config B)",
    }
    alt_summary_rows = []
    # Primary (baseline single-pass GPT-5-mini)
    for label, key, corpus in (
        ("GPT-5-mini (baseline)", "blind_pool",                 "human-authored"),
    ):
        d = (agreement.get("rq5_calderon") or {}).get(key) or {}
        if d:
            alt_summary_rows.append({
                "judge": label, "corpus": corpus,
                "epsilon": d.get("epsilon"),
                "m_annotators": d.get("m_annotators"),
                "n_instances": d.get("n_instances_total"),
                "pearson_judge_vs_mean_blind": "",
                "winning_rate_omega": d.get("winning_rate"),
                "avg_advantage_rho": d.get("avg_advantage_probability"),
                "n_rejected_BY_FDR": d.get("n_rejected"),
                "passes_alt_test": d.get("passes_alt_test"),
                "omega_ci95_lo_clopper": d.get("winning_rate_ci95_lo_clopper"),
                "omega_ci95_hi_clopper": d.get("winning_rate_ci95_hi_clopper"),
            })
    # Primary on LLM picks
    d_llm = (agreement.get("rq5_calderon_on_llm_solutions") or {}).get("blind_pool") or {}
    if d_llm:
        alt_summary_rows.append({
            "judge": "GPT-5-mini (baseline)", "corpus": "LLM-generated",
            "epsilon": d_llm.get("epsilon"),
            "m_annotators": d_llm.get("m_annotators"),
            "n_instances": d_llm.get("n_instances_total"),
            "pearson_judge_vs_mean_blind": "",
            "winning_rate_omega": d_llm.get("winning_rate"),
            "avg_advantage_rho": d_llm.get("avg_advantage_probability"),
            "n_rejected_BY_FDR": d_llm.get("n_rejected"),
            "passes_alt_test": d_llm.get("passes_alt_test"),
            "omega_ci95_lo_clopper": d_llm.get("winning_rate_ci95_lo_clopper"),
            "omega_ci95_hi_clopper": d_llm.get("winning_rate_ci95_hi_clopper"),
        })
    # Config B re-runs and the two 2026-05-31 open-weight follow-up judges.
    # The Config B trio shares one JSON key prefix; DeepSeek and Qwen each
    # have their own bare key.
    cfgB_judges = (("cfgB_gpt5", "GPT-5-mini (Config B)"),
                   ("cfgB_gemini", "Gemini-3.1-Pro (Config B)"),
                   ("cfgB_opus", "Opus-4.7 (Config B)"))
    followup_judges = (("deepseek", "DeepSeek-V4-Pro"),
                       ("qwen", "Qwen3.5-397B-A17B"),
                       ("sonnet", "Sonnet-4.6"),
                       ("gpt54mini", "GPT-5.4-mini"))
    for prefix, name in (*cfgB_judges, *followup_judges):
        for suffix, corpus in (("human", "human-authored"), ("llm", "LLM-generated")):
            p = ((cpj.get(f"{prefix}_{suffix}") or {}).get("payload") or {})
            if not p:
                continue
            alt_summary_rows.append({
                "judge": name, "corpus": corpus,
                "epsilon": p.get("epsilon"),
                "m_annotators": p.get("m_annotators"),
                "n_instances": p.get("n_instances_total"),
                "pearson_judge_vs_mean_blind": p.get("pearson_judge_vs_mean_blind"),
                "winning_rate_omega": p.get("winning_rate"),
                "avg_advantage_rho": p.get("avg_advantage_probability"),
                "n_rejected_BY_FDR": p.get("n_rejected"),
                "passes_alt_test": p.get("passes_alt_test"),
                "omega_ci95_lo_clopper": p.get("winning_rate_ci95_lo_clopper"),
                "omega_ci95_hi_clopper": p.get("winning_rate_ci95_hi_clopper"),
            })
    write_csv(
        OUT_DIR / "03_calderon_alttest_summary.csv",
        ["judge", "corpus", "epsilon", "m_annotators", "n_instances",
         "pearson_judge_vs_mean_blind",
         "winning_rate_omega", "avg_advantage_rho",
         "n_rejected_BY_FDR", "passes_alt_test",
         "omega_ci95_lo_clopper", "omega_ci95_hi_clopper"],
        alt_summary_rows,
    )

    # =========================================================================
    # 04 — Calderon alt-test, per-blind-reviewer detail
    # =========================================================================
    per_ann_rows = []

    def push_block(judge, corpus, payload):
        if not payload:
            return
        for e in payload.get("per_annotator") or []:
            gid = (e.get("grader_id") or "").split("@")[0]
            per_ann_rows.append({
                "judge": judge,
                "corpus": corpus,
                "grader_id": gid,
                "n_j": e.get("n_j"),
                "rho_f_judge_wins": e.get("rho_f"),
                "rho_h_reviewer_wins": e.get("rho_h"),
                "d_bar": e.get("d_bar"),
                "test": e.get("test"),
                "p_value_one_sided": e.get("p_value"),
                "rejected_BY_FDR": e.get("rejected_BY_FDR"),
            })

    push_block("GPT-5-mini (baseline)", "human-authored",
               (agreement.get("rq5_calderon") or {}).get("blind_pool") or {})
    push_block("GPT-5-mini (baseline)", "LLM-generated",
               (agreement.get("rq5_calderon_on_llm_solutions") or {}).get("blind_pool") or {})
    for prefix, name in (("cfgB_gpt5", "GPT-5-mini (Config B)"),
                         ("cfgB_gemini", "Gemini-3.1-Pro (Config B)"),
                         ("cfgB_opus", "Opus-4.7 (Config B)"),
                         ("deepseek", "DeepSeek-V4-Pro"),
                         ("qwen", "Qwen3.5-397B-A17B"),
                         ("sonnet", "Sonnet-4.6"),
                         ("gpt54mini", "GPT-5.4-mini")):
        for suffix, corpus in (("human", "human-authored"), ("llm", "LLM-generated")):
            push_block(name, corpus,
                       (cpj.get(f"{prefix}_{suffix}") or {}).get("payload") or {})

    write_csv(
        OUT_DIR / "04_calderon_per_annotator.csv",
        ["judge", "corpus", "grader_id", "n_j",
         "rho_f_judge_wins", "rho_h_reviewer_wins", "d_bar",
         "test", "p_value_one_sided", "rejected_BY_FDR"],
        per_ann_rows,
    )

    # =========================================================================
    # 05 — Calderon §D.2 single-expert variant
    # =========================================================================
    se_rows = []
    for corpus_label, src_key in (("human-authored", "rq5_calderon"),
                                   ("LLM-generated", "rq5_calderon_on_llm_solutions")):
        se = ((agreement.get(src_key) or {}).get("single_expert")) or {}
        eps_results = se.get("epsilon_results") or {}
        for eps_str, payload in eps_results.items():
            se_rows.append({
                "corpus": corpus_label,
                "epsilon": eps_str,
                "n_picks_with_creator_and_judge": se.get("n_instances_with_creator_and_judge"),
                "m_annotators": payload.get("m_annotators"),
                "winning_rate_omega": payload.get("winning_rate"),
                "avg_advantage_rho": payload.get("avg_advantage_probability"),
                "passes_alt_test": payload.get("passes_alt_test"),
            })
    write_csv(
        OUT_DIR / "05_calderon_single_expert.csv",
        ["corpus", "epsilon", "n_picks_with_creator_and_judge",
         "m_annotators", "winning_rate_omega", "avg_advantage_rho",
         "passes_alt_test"],
        se_rows,
    )

    # =========================================================================
    # 06 — Judge calibration audit (Δ_dir, Δ_sub, t-tests, Shapiro-Wilk)
    # =========================================================================
    calib_csv_rows = []
    for r in calib_rows:
        if not isinstance(r, dict):
            continue
        label = r.get("label", "")
        # Parse corpus
        if "(human)" in label:
            corpus = "human-authored"
        elif "(LLM)" in label:
            corpus = "LLM-generated"
        else:
            corpus = "?"
        # Configuration name (strip the trailing "(human)" / "(LLM)")
        config = label.replace("  (human)", "").replace("  (LLM)", "").strip()
        calib_csv_rows.append({
            "configuration": config,
            "corpus": corpus,
            "n": r.get("n"),
            "judge_minus_pool_mean": r.get("judge_minus_pool_mean"),
            "judge_minus_pool_sd": r.get("judge_minus_pool_sd"),
            "judge_pool_ttest_t": r.get("judge_pool_ttest_t"),
            "judge_pool_ttest_p": r.get("judge_pool_ttest_p"),
            "sub_minus_full_mean": r.get("diff_mean"),
            "sub_minus_full_sd": r.get("diff_sd"),
            "shapiro_wilk_p_on_diff": r.get("sw_diff_p"),
            "sub_ttest_t": r.get("ttest_t"),
            "sub_ttest_p": r.get("ttest_p"),
        })
    write_csv(
        OUT_DIR / "06_judge_calibration.csv",
        ["configuration", "corpus", "n",
         "judge_minus_pool_mean", "judge_minus_pool_sd",
         "judge_pool_ttest_t", "judge_pool_ttest_p",
         "sub_minus_full_mean", "sub_minus_full_sd",
         "shapiro_wilk_p_on_diff",
         "sub_ttest_t", "sub_ttest_p"],
        calib_csv_rows,
    )

    # =========================================================================
    # 07 — Per-dimension judge–blind agreement
    # =========================================================================
    dim_h = agreement.get("rq5_dim") or {}
    dim_l = agreement.get("rq5_dim_on_llm_solutions") or {}
    dim_rows = []
    for corpus_label, dim_data in (("human-authored", dim_h),
                                    ("LLM-generated",  dim_l)):
        for dim_name, d in dim_data.items():
            dim_rows.append({
                "corpus": corpus_label,
                "dimension": dim_name,
                "n": d.get("n"),
                "pearson_judge_vs_mean_blind": d.get("pearson_judge_vs_mean_human"),
                "mae_dimension_points": d.get("mae_dim_points"),
            })
    write_csv(
        OUT_DIR / "07_dimension_agreement.csv",
        ["corpus", "dimension", "n",
         "pearson_judge_vs_mean_blind", "mae_dimension_points"],
        dim_rows,
    )

    # =========================================================================
    # 08 — Intra-judge stability (Config A passes + ×3 within-cell stdev)
    # =========================================================================
    intra_rows = []
    # Within-cell stdev summary
    jr = agreement.get("rq5_judge_repeats") or {}
    if jr:
        intra_rows.append({
            "metric": "Mean within-cell stdev across GPT-5-mini ×3",
            "scope": "Benchathon LLM generations",
            "n_generations": jr.get("n_generations_with_repeats"),
            "value": jr.get("mean_within_gen_stdev"),
            "notes": "raw points; judge self-consistency",
        })
    # Per-pass calibration offsets vs mean (drift of Δ_dir across passes)
    def find_calib(label):
        for r in calib_rows:
            if isinstance(r, dict) and label in r.get("label", ""):
                return r
        return {}
    for corpus_label, sfx in (("human-authored", "(human)"), ("LLM-generated", "(LLM)")):
        mean_r = find_calib(f"Config A GPT-5-mini × 3 (mean)  {sfx}")
        for pi in (1, 2, 3):
            r = find_calib(f"Config A GPT-5-mini pass {pi}  {sfx}")
            if r:
                intra_rows.append({
                    "metric": f"Δ_dir pass {pi} (judge − pool mean)",
                    "scope": f"Config A GPT-5-mini, {corpus_label}",
                    "n_generations": r.get("n"),
                    "value": r.get("judge_minus_pool_mean"),
                    "notes": (f"mean of 3 passes = "
                              f"{mean_r.get('judge_minus_pool_mean')}"),
                })
    write_csv(
        OUT_DIR / "08_intrajudge_stability.csv",
        ["metric", "scope", "n_generations", "value", "notes"],
        intra_rows,
    )

    # =========================================================================
    # 09 — Inter-judge agreement (Config B 259-cell subset)
    # =========================================================================
    inter_rows = []
    n_triplets = inter.get("n_cells_with_triplets")
    pjs = inter.get("per_judge_stats") or {}
    for j, d in pjs.items():
        inter_rows.append({
            "comparison": "per-judge mean",
            "judge_or_pair": j,
            "n_cells": d.get("n"),
            "mean": d.get("mean"),
            "stdev": d.get("stdev"),
            "min": d.get("min"),
            "max": d.get("max"),
            "pearson_r": "",
            "spearman_rho": "",
            "mae": "",
        })
    pairwise = inter.get("pairwise") or {}
    for pair_key, d in pairwise.items():
        inter_rows.append({
            "comparison": "pairwise",
            "judge_or_pair": pair_key,
            "n_cells": d.get("n"),
            "mean": "",
            "stdev": "",
            "min": "",
            "max": "",
            "pearson_r": d.get("pearson_r"),
            "spearman_rho": d.get("spearman_rho"),
            "mae": d.get("mae"),
        })
    wcs = inter.get("within_cell_stdev") or {}
    inter_rows.append({
        "comparison": "within-cell spread (median across cells)",
        "judge_or_pair": "GPT-5-mini ∪ Opus ∪ Gemini",
        "n_cells": n_triplets,
        "mean": wcs.get("mean"),
        "stdev": "",
        "min": wcs.get("min"),
        "max": wcs.get("max"),
        "pearson_r": "",
        "spearman_rho": "",
        "mae": "",
    })
    write_csv(
        OUT_DIR / "09_interjudge_agreement.csv",
        ["comparison", "judge_or_pair", "n_cells",
         "mean", "stdev", "min", "max",
         "pearson_r", "spearman_rho", "mae"],
        inter_rows,
    )

    # =========================================================================
    # README
    # =========================================================================
    readme = (OUT_DIR / "README.md")
    readme.write_text(
        "# RQ5 data trace\n\n"
        "One CSV per RQ5 test/analysis. Open in Excel / Numbers / any csv viewer.\n\n"
        "| File | RQ5 paragraph | What it contains |\n"
        "|---|---|---|\n"
        "| `01_per_solution_agreement.csv` | Per-solution agreement | "
        "Judge vs. mean blind reviewer Pearson r, Spearman ρ, Cohen's κ, MAE "
        "(raw and bias-corrected), calibration offset — one row per corpus. |\n"
        "| `02_blind_reviewer_irr.csv` | Per-solution agreement | "
        "Blind-reviewer ICC(2,1) / ICC(2,k) (raw and grade points) and "
        "within-annotation max–min spread — pooled and per solution type. |\n"
        "| `03_calderon_alttest_summary.csv` | Calderon alt-test | "
        "Per-judge × corpus headline: Pearson r vs blind mean, ω (winning rate), "
        "ρ (avg advantage), rejection count, pass/fail, binomial CI on ω. |\n"
        "| `04_calderon_per_annotator.csv` | Calderon alt-test (detail) | "
        "Per-blind-reviewer detail behind each ω: n_j, ρ^f_j, ρ^h_j, d̄_j, "
        "test name, one-sided p-value, BY-FDR rejection flag. |\n"
        "| `05_calderon_single_expert.csv` | Calderon §D.2 variant | "
        "Single-expert variant against the un-blind creator at ε ∈ {0.15, 0.20}. |\n"
        "| `06_judge_calibration.csv` | Judge calibration | "
        "Per-judge × per-corpus calibration: Δ_dir (judge − pool mean), Δ_sub "
        "(pool-substitution shift), paired t-test, Shapiro–Wilk p. Includes "
        "baseline single-pass GPT-5-mini, Config B (3 judges × 1 pass), Config A "
        "(GPT-5-mini × 3 passes). |\n"
        "| `07_dimension_agreement.csv` | Dimension-level pattern | "
        "Per-rubric-dimension Pearson r and MAE between judge and mean blind "
        "reviewer, separately on human-authored and LLM-generated picks. |\n"
        "| `08_intrajudge_stability.csv` | Judge stability | "
        "GPT-5-mini self-consistency: within-cell stdev across 3 re-runs on "
        "Benchathon LLM generations, plus per-pass calibration offsets. |\n"
        "| `09_interjudge_agreement.csv` | Inter-judge agreement | "
        "Config B 259-cell subset: per-judge mean/stdev/min/max, pairwise "
        "Pearson r / Spearman ρ / MAE, median within-cell spread across the 3 judges. |\n"
        "\n"
        "Regenerate with `uv run python scripts/rq5_data_trace.py`.\n"
    )

    print(f"Wrote {len(list(OUT_DIR.glob('*.csv')))} CSVs + README to {OUT_DIR}")


if __name__ == "__main__":
    main()
