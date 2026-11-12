# LEXam_DE: full paper behind the accepted anonymous abstract

**Work in progress.** Tracked in the public repo since 2026-08; build
artifacts and the `analysis/data/` result dumps stay out via the repo-root
`.gitignore` (the dumps ship to Zenodo instead).

Full paper (~3,000 words, plain language for a mixed legal/NLP audience) for
the accepted conference abstract "Replicating LEXam on German First State
Exam-Style Essay Cases to Probe the 'Statistical' Face of Legal Reasoning"
(`Replicating_LEXam_on_German_Exams_Abstract.pdf`), to appear in the open
access conference volume of "Legal Reasoning in the Age of AI: Law, Language
and Computation" (St.Gallen Publishing; final manuscripts due 2026-12-31,
Chicago notes and bibliography, publisher's Word template).

## Contents

- `manuscript.qmd` → `make render` → `manuscript.pdf` (one-column article
  layout like the abstract, xelatex, fonts loaded from `fonts/`). Narrative
  v3 (2026-11-12): the faithful LEXam replication, what it showed, where a
  single-reference correctness score stops matching German correction
  (alternative solutions, step-by-step grading of the subsumption), why that
  led to BenGER and on to instance-specific grading sheets; respectful toward
  LEXam throughout. Citations are footnotes in Chicago style
  (`chicago-notes-bibliography.csl`); court decisions are cited in the
  footnotes in German form. Numbers are hardcoded in the qmd and trace to
  `REPRODUCTION.md`, `analysis/` and the BenGER paper.
- `make docx` → `manuscript.docx` for the publisher. Copy the publisher's
  Word template to `publisher/St.Gallen_Publishing_Template.docx` (both
  gitignored) first; Quarto renders against it and
  `scripts/apply_publisher_styles.py` maps the paragraph styles onto the
  template's own styles. Without the template the target renders a plain
  docx.
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
