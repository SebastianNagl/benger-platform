# RQ4 data trace

One CSV per RQ4 analytic step. Open in Excel / Numbers / any csv viewer.

| File | RQ4 step | What it contains |
|---|---|---|
| `01_cohort.csv` | Cohort and per-condition pools | Annotation counts and participant counts per arm; the imbalance that drives the skip-mechanism story. |
| `02_per_condition_means.csv` | Per-condition mean LLM-judge scores | Mean raw 0–100 and grade-point 0–18 per condition, plus stdev and n. |
| `03_mean_difference_bootstraps.csv` | Mean difference Δ under four resampling units | Δ and 95% CI under i.i.d. bootstrap, participant-cluster bootstrap (HEADLINE), task-cluster bootstrap, and within-participant paired delta. |
| `04_per_participant_paired.csv` | Within-participant paired test (underlying data) | One row per participant who did both arms — their per-arm mean and personal Δ. This is the data behind the paired row in CSV 03. |
| `05_by_bereich.csv` | Per legal area (Zivil / Straf / Öffentlich) | Descriptive per-domain Δ values with i.i.d. CIs. No inferential test. |
| `06_tost_vs_flagship.csv` | TOST equivalence vs closed-flagship LLM tier | Per-arm means, equivalence band, one-sided 95% bounds, equivalence decision. |
| `07_blind_human_cross_check.csv` | Blind-human cross-check (RQ5 validation subset, n=15+15) | Same contrast scored by the blind human pool; both participant-cluster and i.i.d. CIs. |
| `08_judge_vs_human_gap.csv` | Judge vs blind-human gap explained by content-dependent calibration | The ~6-raw-point gap between judge and human Δ, and the ~10-raw-point content-dependent calibration offset from RQ5 that explains it. |

Regenerate with `python scripts/rq4_data_trace.py`.
