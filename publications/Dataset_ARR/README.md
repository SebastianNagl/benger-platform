# Dataset_ARR — BenGER paper sources

Quarto manuscript for the BenGER dataset paper (ACL/ARR target). The dataset is **BenGER**, a single benchmark with three thematic subsets: Benchathon, ZJS, and Grundprinzipien. 12 LLM systems, rubric-aligned LLM-as-a-Judge with a human-grading validation layer.

## Public release

- **Paper (preprint)**: [arXiv:2605.28183](https://arxiv.org/abs/2605.28183)
- **Zenodo (canonical dataset distribution)**: [10.5281/zenodo.20409635](https://doi.org/10.5281/zenodo.20409635) — `benger-v1.0.zip` with the full anonymised `benchathon/`, `zjs/`, `grundprinzipien/`, and `processed/` subtrees.
- **GitHub** (this folder): ships the manuscript source, the derived `data/processed/` and `data/interim/` JSONs the paper loads, and the scripts that produced everything. The raw platform exports and the unredacted ZJS source stay out of git.

### Grader anonymisation

The seven human graders of the Benchathon subset are referred to by stable codes `grader_01..grader_07` across every file in `data/`. The real-name↔code↔email↔uuid mapping lives in `data/.grader_map.json`, which is gitignored and **must not be published**. Run `scripts/anonymize_graders.py --dry-run` for a preview and `scripts/anonymize_graders.py` to apply. The script is idempotent.

### ZJS IP-clearance

The ZJS subset reproduces case texts from *Zeitschrift für das Juristische Studium*. Each case has an author whose IP-clearance status is recorded in `data/raw/zjs/ip_clearance.csv` (the roster) and normalised in `data/raw/zjs/ip_clearance.json` (the lookup). Two redacted variants are produced:

- `data/raw/zjs/source_strict/` — only cases with status `Genehmigt` keep their full text; all others have `Aufgabe` and `Musterlösung` replaced with the ZJS search URL.
- `data/raw/zjs/source_optimistic/` — only cases with status `Abgelehnt` are redacted.

Pick a variant for public release at upload time (`ZJS_RELEASE_VARIANT=strict` or `optimistic`). Default recommendation pending legal review: strict. Both variants also exist as `data/raw/zjs/zjs_merged_<variant>.json`, `data/interim/zjs_<variant>.json`, and `data/raw/zjs/ZJS Fälle-tasks-<variant>.json` (the streamed platform export). Reproduce with:

```bash
python scripts/zjs_build_ip_map.py
python scripts/zjs_apply_ip_clearance.py --mode strict
python scripts/zjs_apply_ip_clearance.py --mode optimistic
```

## Render

```bash
make render
```

## Re-derive the small JSONs the manuscript loads

```bash
make derive       # runs each script under `uv run` against this project's pyproject
```

The four scripts run in dependency order:

1. `scripts/derive_zjs_summary.py`             → `data/processed/zjs_{model_summary,metric_correlation}.json`
2. `scripts/derive_paper_exports.py`           → `data/processed/{systems,benchathon_*}.json`  *(needs zjs_model_summary.json for the system whitelist)*
3. `scripts/derive_grundprinzipien_summary.py` → `data/processed/grundprinzipien_{model_summary,metric_correlation,tier_aggregates}.json`  *(needs systems.json)*
4. `scripts/compute_agreement.py`              → `data/processed/agreement_stats.json`

`derive_zjs_summary.py` streams a 3.6 GB file and takes a few minutes; the others run in seconds.

## Python environment

This project uses **uv** (`pyproject.toml` + `uv.lock`). Run anything from the project root:

```bash
uv sync                                          # hydrate .venv from uv.lock
uv run python scripts/<script>.py                # any of the derive / compute scripts
```

The Makefile prefixes every script call with `uv run` so deps like `ijson` and `tiktoken` resolve correctly.

## Data layout

```
data/
├── raw/          immutable platform exports + corpus source material
│   ├── benchathon/        Benchathon-tasks-*.json, benchathon_users.json
│   ├── grundprinzipien/   Grundprinzipien-tasks-*.json + source/
│   ├── zjs/               ZJS Fälle-tasks-*.json + source/
│   ├── mock/              benchathon_mock.json
│   └── archive/           superseded raw exports kept for provenance
│
├── interim/      normalised per-corpus task lists + human-grading working files
│   ├── benchathon.json, grundprinzipien.json, zjs.json
│   └── benchathon_human_grading_{sample,assignments,todo_*}.{csv,json}
│
└── processed/    small derived JSONs the manuscript loads (one source of truth per stat)
```

Convention: nothing in `data/raw/` is ever overwritten; `data/interim/` and `data/processed/` are produced by `scripts/` and safe to regenerate.

## Known model-version drift

The Google efficiency-tier slot was generated under two different ids. Benchathon ran `gemini-3-flash-preview`; ZJS and Grundprinzipien ran the successor `gemini-3.1-flash-lite-preview`. The paper exports (`data/processed/systems.json`, leaderboards, model-evaluation rows) collapse both ids into one row keyed by the canonical id `gemini-3.1-flash-lite-preview`; the raw per-row id is preserved on each generation in `data/raw/benchathon/` so downstream consumers can disambiguate if needed. The aliasing is driven by `MODEL_ID_ALIASES` in `scripts/derive_paper_exports.py`. Manuscript discloses the drift in @tbl-system-overview and §Limitations.
