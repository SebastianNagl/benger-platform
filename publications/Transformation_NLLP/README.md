# BenGER Transformation

Second BenGER publication: exam-specific, auto-generated 100-point step
rubrics (*Bewertungsbogen*) for LLM-as-judge grading of German legal exams,
replacing the dataset paper's abstract 10-dimension rubric. The study asks
whether heterogeneous generators can produce schema-conformant exam-specific
schemes, whether grading against them stabilises a judge across repeated
passes, at what cost in human-score agreement, and which generators write the
best instruments.

Companion to the BenGER dataset paper in `../Dataset_ARR`, and built on the
BenGER platform (this repo).

## Building the paper

```bash
uv sync                                  # hydrate the venv
uv run python -m ipykernel install --user --name benger-transformation
make derive                              # file-based data prep, no dev stack
make analyze                             # regenerate every published statistic
make render                              # -> manuscript.pdf (ACL, xelatex)
```

`make render` rebuilds `manuscript.pdf` from `manuscript.qmd` and the tracked
data. Every number in the paper is computed at render time from
`data/processed/`; nothing is hardcoded.

`make render` works from a clean clone. `make derive` and `make analyze` do
not — they re-derive `data/processed/` from the run outputs and the exam
corpus, neither of which is in this repo (see below).

## Layout

```
manuscript.qmd      the paper (Quarto, ACL format)
manuscript.pdf      the built paper
_quarto.yml         format config (xelatex; do not "simplify", see comments)
_extensions/acl/    ACL Quarto format
fonts/              STIX Two Math + TeX Gyre Termes (self-contained build)
references.bib      bibliography
assets/             figures and generated LaTeX tables
data/raw/local/     generated rubrics (task_rubrics.json) — not in git
data/interim/       run inputs (tracked) + judge/probe/audit run outputs (not in git)
data/processed/     derived statistics the manuscript loads
scripts/            extraction, validation, dispatch drivers
scripts/analysis/   the statistics behind every reported number
scripts/ops/        one-shot dispatch + audit-setup drivers
```

## What is not in this repo

Some inputs are withheld and ship with the dataset release instead:

- **Exam corpus text** (*Sachverhalt* and *Musterlösung* for the 15 exams).
  These are third-party materials used under the permissions documented for
  the underlying corpus; we do not hold redistribution rights, so the audit
  import files and probe texts that embed them are not published here. The
  same applies to the ZJS sources in `../Dataset_ARR`.
- **The generated rubrics** (`data/raw/local/task_rubrics.json`, 193 documents).
  Their step criteria enumerate the expected solution of each exam, which makes
  them a close derivative of the *Musterlösungen* — so they fall under the same
  redistribution call as the corpus text itself.
- **Run outputs** (`data/interim/**/*.jsonl`, 23 MB of per-cell judge, probe and
  audit score rows). Withheld for bulk rather than for rights: git is not a data
  store. They are the input to `make analyze`, and the statistics they produce
  are tracked in `data/processed/`.
- **The audit blind-code key** (`data/interim/audit/KEY.json`), which maps each
  blind code to its rubric and generator. Publishing it next to the blind-coded
  `AUDIT_SHEET.csv` would undo the blinding. The de-blinded outcome the paper
  reports is in `data/processed/audit_stats.json`.
- **Audit and probe account fixtures**, which carry platform credentials.

None of these is an input to `make render`: every load in `manuscript.qmd` goes
through `load_optional()`, so the paper rebuilds from the tracked data alone.
Reproducing `data/processed/` from scratch needs the withheld inputs restored
from the dataset release.

## Citing

Nagl, S. and Grabmair, M. *BenGER Transformation: Exploring Automated Rubric
Generation to Reduce LLM Grading Variance in German Legal Exams.*
