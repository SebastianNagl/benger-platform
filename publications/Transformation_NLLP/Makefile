.PHONY: derive analyze pull render clean

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
	uv run python scripts/figures/make_trend_figure.py

# Pulls from the LOCAL dev stack (requires docker + running benger-db-1).
pull:
	uv run python scripts/pull_local_sidecar.py

render:
	# Don't pass --to pdf: that resolves to Quarto's built-in pdf format and
	# bypasses the acl-pdf format declared in _quarto.yml (no ACL template,
	# no keep-tex). `uv run` puts the project venv's python (ipykernel) on
	# PATH so Quarto can discover the `benger-transformation` jupyter kernel.
	uv run quarto render manuscript.qmd

clean:
	rm -rf .quarto manuscript_files manuscript_executed_files \
	       manuscript.tex manuscript.fdb_latexmk manuscript.quarto_ipynb*
