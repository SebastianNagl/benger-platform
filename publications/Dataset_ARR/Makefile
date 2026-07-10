.PHONY: derive render arxiv clean

derive:
	uv run python scripts/derive_zjs_summary.py
	uv run python scripts/derive_paper_exports.py
	uv run python scripts/rq5_judge_calibration.py
	uv run python scripts/rq5_calderon_per_judge.py
	uv run python scripts/derive_error_analysis.py
	uv run python scripts/derive_inter_judge_agreement.py
	uv run python scripts/derive_grundprinzipien_summary.py
	uv run python scripts/derive_leaderboard_csvs.py
	uv run python scripts/compute_agreement.py
	uv run python scripts/derive_metric_vs_human.py
	uv run python scripts/derive_reasoning_core.py
	uv run python scripts/derive_operational_metadata.py
	uv run python scripts/derive_reasoning_ablation.py

render:
	# Don't pass --to pdf: that resolves to Quarto's built-in pdf format and
	# bypasses the acl-pdf format declared in _quarto.yml (no ACL template,
	# no keep-tex). Letting Quarto pick the default format here keeps the
	# manuscript on the ACL extension and preserves manuscript.tex.
	# `uv run` puts the project venv's python (ipykernel) on PATH so Quarto
	# can discover the `benger-dataset-arr` jupyter kernel on any machine.
	uv run quarto render manuscript.qmd

# Self-contained arXiv source bundle (requires a fresh `make render` so
# manuscript.tex and manuscript_files/ exist). Output is gitignored.
arxiv:
	bash scripts/build_arxiv_bundle.sh

clean:
	rm -rf .quarto manuscript_files manuscript_executed_files \
	       manuscript.tex manuscript.fdb_latexmk manuscript.quarto_ipynb*
