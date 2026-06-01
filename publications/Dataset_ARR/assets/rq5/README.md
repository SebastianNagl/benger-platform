# RQ5 data trace

One CSV per RQ5 test/analysis. Open in Excel / Numbers / any csv viewer.

| File | RQ5 paragraph | What it contains |
|---|---|---|
| `01_per_solution_agreement.csv` | Per-solution agreement | Judge vs. mean blind reviewer Pearson r, Spearman ρ, Cohen's κ, MAE (raw and bias-corrected), calibration offset — one row per corpus. |
| `02_blind_reviewer_irr.csv` | Per-solution agreement | Blind-reviewer ICC(2,1) / ICC(2,k) (raw and grade points) and within-annotation max–min spread — pooled and per solution type. |
| `03_calderon_alttest_summary.csv` | Calderon alt-test | Per-judge × corpus headline: Pearson r vs blind mean, ω (winning rate), ρ (avg advantage), rejection count, pass/fail, binomial CI on ω. |
| `04_calderon_per_annotator.csv` | Calderon alt-test (detail) | Per-blind-reviewer detail behind each ω: n_j, ρ^f_j, ρ^h_j, d̄_j, test name, one-sided p-value, BY-FDR rejection flag. |
| `05_calderon_single_expert.csv` | Calderon §D.2 variant | Single-expert variant against the un-blind creator at ε ∈ {0.15, 0.20}. |
| `06_judge_calibration.csv` | Judge calibration | Per-judge × per-corpus calibration: Δ_dir (judge − pool mean), Δ_sub (pool-substitution shift), paired t-test, Shapiro–Wilk p. Includes baseline single-pass GPT-5-mini, Config B (3 judges × 1 pass), Config A (GPT-5-mini × 3 passes). |
| `07_dimension_agreement.csv` | Dimension-level pattern | Per-rubric-dimension Pearson r and MAE between judge and mean blind reviewer, separately on human-authored and LLM-generated picks. |
| `08_intrajudge_stability.csv` | Judge stability | GPT-5-mini self-consistency: within-cell stdev across 3 re-runs on Benchathon LLM generations, plus per-pass calibration offsets. |
| `09_interjudge_agreement.csv` | Inter-judge agreement | Config B 259-cell subset: per-judge mean/stdev/min/max, pairwise Pearson r / Spearman ρ / MAE, median within-cell spread across the 3 judges. |

Regenerate with `uv run python scripts/rq5_data_trace.py`.
