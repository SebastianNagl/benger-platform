.PHONY: derive analyze analyze-cslaw analyze-d2 pull render render-cslaw clean

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

# CSLAW full paper (cslaw/): the corrected first-iteration numbers and the
# extended study's design constants. Reads only tracked files (the outputs of
# `make analyze` and a few tracked data/interim files), writes
# data/processed/cslaw/. --check fails on a broken consistency anchor.
analyze-cslaw:
	uv run python scripts/analysis/cslaw_first_iteration.py --check
	uv run python scripts/analysis/cslaw_design.py

# Pulls from the LOCAL dev stack (requires docker + running benger-db-1).
pull:
	uv run python scripts/pull_local_sidecar.py

render:
	# Don't pass --to pdf: that resolves to Quarto's built-in pdf format and
	# bypasses the acl-pdf format declared in _quarto.yml (no ACL template,
	# no keep-tex). `uv run` puts the project venv's python (ipykernel) on
	# PATH so Quarto can discover the `benger-transformation` jupyter kernel.
	uv run quarto render manuscript.qmd

# The CSLAW draft (ACM acmsmall, xelatex). Needs the benger-transformation
# jupyter kernel (see README) and TinyTeX with acmart.
# D2 summaries: need the git-ignored pilot rows and D2 pack (local data
# root, scripts/local_config.py); they write aggregates only.
analyze-d2:
	uv run python scripts/analysis/compute_pilot_probe_gate.py --phase d2-probes || true
	uv run python scripts/analysis/compute_d2_gate_summary.py
	uv run python scripts/analysis/compute_d2_generation_summary.py
	uv run python scripts/analysis/compute_d2_validity.py

render-cslaw: analyze-cslaw
	cd cslaw && uv run quarto render manuscript.qmd

clean:
	rm -rf .quarto manuscript_files manuscript_executed_files \
	       manuscript.tex manuscript.fdb_latexmk manuscript.quarto_ipynb*
