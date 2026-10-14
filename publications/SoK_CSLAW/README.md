# SoK: Grading Open-Text Legal Answers (ACM CSLAW '27)

Systematization of knowledge on evaluating open-text legal answers (law exam
case solutions, essays, memos): eight paradigms from human grading to LLM
judges, compared against desiderata from educational measurement and from the
law that governs grading (German examination law, GDPR, EU AI Act). It argues
for an instance-specific rubric applied by a trustworthy LLM judge and lays the
conceptual ground for the BenGER Transformation paper (in preparation).

Status: submitted on 2026-10-14 to the 6th ACM Symposium on Computer Science
and Law (CSLAW '27) as a full archival paper, topic "educational methods
combining CS and law" (15 pages ACM small excluding references and
appendices, single-blind review), and submitted to arXiv as a preprint the
same day (identifier follows the announcement). `manuscript.pdf` is the
submitted named version, `manuscript_blind.pdf` the anonymised one.

## Building

```bash
make render      # make tables + quarto render -> manuscript.pdf (xelatex, TinyTeX with acmart)
make blind       # the same with the BLIND-REVIEW SWAPS applied -> manuscript_blind.pdf
make arxiv       # self-contained XeLaTeX source bundle of the named version for arXiv -> sok_arxiv_source_<date>.zip
```

No Jupyter kernel is needed: `scripts/build_tables.py` writes the tables to
`assets/` from the coding in `data/`, and the manuscript `\input`s them.

## Blind version

`manuscript.qmd` carries BLIND-REVIEW SWAP blocks: a `<<NAMED ... NAMED>>`
block holds the named text, and the commented-out `<<BLIND ... BLIND>>` block
next to it the anonymous text (the author block, the acmart `anonymous`
option, and the self-references in the body). `make blind` applies the swaps
to a temporary copy and renders `manuscript_blind.pdf`; `manuscript.qmd` is
not changed. To switch by hand instead, comment out the NAMED blocks and
uncomment the BLIND blocks. The `anonymous` option prints "Anonymous
Author(s)" and drops the acknowledgments by itself. Published own work stays
cited in the third person, as the double-blind rules of ACL and ACM ask; the
unpublished companion study is cited as `anon2027companion`.

## Layout

```
manuscript.qmd          the paper
data/paradigms.yaml     paradigm x desideratum ratings (Table 2)
data/legal_studies.yaml coded legal evaluations with agreement figures (Table 3)
data/requirements.yaml  legal requirements L1-L7 (Table 1)
data/design.yaml        design space of legal rubrics (Table 4)
scripts/build_tables.py data/*.yaml -> assets/*.tex
scripts/blind.py        manuscript.qmd with the swaps applied -> manuscript_blind.pdf (make blind)
scripts/build_arxiv_bundle.sh  arXiv source bundle of the named version, acmart nonacm option (make arxiv)
figures/judge.pdf       Figure 1, exported from Figma (source stays in Figma); assets/ is git-ignored, figures/ is not
references.bib          bibliography (superset; only cited entries are printed)
```
