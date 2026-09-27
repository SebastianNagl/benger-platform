.PHONY: derive analyze analyze-cslaw analyze-local analyze-d2 pull render clean

# File-based derivation only — works without the dev stack.
derive:
	uv run python scripts/extract_exam_pack.py
	uv run python scripts/derive_contract_snapshot.py
	uv run python scripts/rubric_stats.py
	uv run python scripts/derive_control_arm_variance.py

# File-based analysis (2026-08-06 revision): regenerates every published
# statistic from the interim files — no DB needed. Order matters: the
# matched contrasts feed the significance/bootstrap package. The two
# DB-dependent steps (analyze_crossed --lens luna/sonnet, which also
# regression-check the stored per-generator block) are NOT here; run them
# manually with the dev stack up.
analyze:
	uv run python scripts/analysis/compute_matched_contrasts.py
	uv run python scripts/analysis/compute_significance.py
	uv run python scripts/analysis/compute_matched_multijudge.py
	uv run python scripts/analysis/compute_audit_outcome_link.py
	uv run python scripts/analysis/compute_generator_ranking.py
	uv run python scripts/analysis/screen_rubric_language.py
	uv run python scripts/analysis/compute_probe_stats.py
	uv run python scripts/analysis/compute_fewshot_contrasts.py
	uv run python scripts/analysis/compute_band_mapping_stats.py
	uv run python scripts/analysis/compute_apportionment_audit.py
	uv run python scripts/analysis/compute_weight_sensitivity.py --check
	uv run python scripts/analysis/compute_step_variance.py
	uv run python scripts/analysis/compute_mde.py
	uv run python scripts/figures/make_trend_figure.py

# The paper's first-iteration numbers (on step-sum totals) and the extended
# study's design constants. Reads only tracked files (the outputs of
# `make analyze` and a few tracked data/interim files), writes
# data/processed/cslaw/. --check fails on a broken consistency anchor.
analyze-cslaw:
	uv run python scripts/analysis/cslaw_first_iteration.py --check
	uv run python scripts/analysis/cslaw_design.py

# The first-iteration numbers that analyze-cslaw lists as pending: they need
# the git-ignored run outputs and rubrics (local data root,
# scripts/local_config.py) and write aggregates only to
# data/processed/cslaw/first_iteration_local.json. --check fails when a
# stored-total recompute no longer reproduces its tracked value.
analyze-local:
	uv run python scripts/analysis/cslaw_first_iteration_local.py --check

# Pulls from the LOCAL dev stack (requires docker + running benger-db-1).
pull:
	uv run python scripts/pull_local_sidecar.py

# The paper: ACM acmsmall (CSLAW '27), xelatex. Needs the benger-transformation
# jupyter kernel (see README) and TinyTeX with acmart. Don't pass --to pdf:
# that resolves to Quarto's built-in pdf format and bypasses the acm-pdf
# format declared in _quarto.yml. `uv run` puts the project venv's python
# (ipykernel) on PATH so Quarto can discover the kernel.
render: analyze-cslaw
	uv run quarto render manuscript.qmd
	$(MAKE) clean

# Build intermediates only; manuscript.pdf stays.

# D2 summaries and the structure of Roth's sheet: need the git-ignored
# pilot rows, D2 pack and Z2 workbook (local data root,
# scripts/local_config.py); they write aggregates only.
# The D2 runs' judge code version; the same pin as scripts/analysis/d2_labels.py.
D2_CODE_VERSION = 7fc295f3b81f

D2_GATE = $(shell uv run python scripts/local_config.py get data_root)/interim/pilot/gate_d2-probes.json

analyze-d2:
	uv run python scripts/analysis/extract_z2_structure.py
	# The gate's exit code is its verdict (1 a battery failed, 2 a pass is incomplete
	# or the input is bad); the summary records the verdict, so the build only
	# requires that this run wrote a fresh gate file.
	rm -f $(D2_GATE)
	-uv run python scripts/analysis/compute_pilot_probe_gate.py --phase d2-probes --code-version $(D2_CODE_VERSION) --out $(D2_GATE)
	test -s $(D2_GATE)
	uv run python scripts/analysis/compute_d2_gate_summary.py --gate $(D2_GATE)
	uv run python scripts/analysis/compute_d2_generation_summary.py
	uv run python scripts/analysis/compute_d2_validity.py

clean:
	rm -rf .quarto assets manuscript_files manuscript_executed_files \
	       manuscript.tex manuscript.fdb_latexmk manuscript.quarto_ipynb* comment.cut
	find scripts -name __pycache__ -type d -prune -exec rm -rf {} +
