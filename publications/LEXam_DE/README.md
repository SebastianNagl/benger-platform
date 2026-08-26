# LEXam_DE: full paper behind the accepted anonymous abstract

**Work in progress.** Tracked in the public repo since 2026-08; build
artifacts and the `analysis/data/` result dumps stay out via the repo-root
`.gitignore` (the dumps ship to Zenodo instead).

Full paper (~3,000 words, plain language for a mixed legal/NLP audience) for
the accepted conference abstract "Replicating LEXam on German First State
Exam-Style Essay Cases to Probe the 'Statistical' Face of Legal Reasoning"
(`Replicating_LEXam_on_German_Exams_Abstract.pdf`).

## Contents

- `manuscript.qmd` → `make render` → `manuscript.pdf` (one-column article
  layout like the abstract, xelatex, fonts loaded from `fonts/`). Narrative
  v2 (2026-08-14): BenGER vs the faithful LEXam replication — why German
  data needed its own instrument, benevolent toward LEXam. Numbers are
  currently hardcoded in the qmd; wire them to the analysis outputs before
  submission.
- `REPRODUCTION.md` — full methodology, headline results, and the deviations
  register of the LEXam-DE reproduction runs (2026-08-12→14, prod).
- `prompts/`, `configs/`, `snapshots/` — the Germanized LEXam templates, the
  exact structure/eval-config payload builder, and the pre-run prod config
  snapshots (everything needed for a rerun).
- `analysis/` — dump + report scripts, `report.md` (full result tables),
  `similarity_vs_rubric.py` (the similarity-vs-rubric correlation analysis
  behind the paper's Finding 4), `human_split_lexam_judge.py` (the
  traditional/co-creation split of the human baseline — the § 5 numbers),
  `pipeline_rank_comparison.py` (the 11-model rank-agreement claim of § 6)
  and their `data/`. The `data/` dumps are gitignored — they go to Zenodo
  as a dataset; regenerate locally via `dump_results.sh` (prod access).
- `presentation/slides.html` — English conference deck (18 slides, 16:9,
  arrow-key navigation, TUM corporate design, same narrative as the paper).
  `presentation/slides.pdf` is the printed version (`make slides-pdf`,
  needs chromium).
