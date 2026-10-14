.PHONY: tables render blind arxiv clean

# The systematization tables are generated from data/*.yaml, so the coding of
# every surveyed work lives in one reviewable place.
tables:
	uv run python scripts/build_tables.py

# Don't pass --to pdf: that resolves to Quarto's built-in pdf format and
# bypasses the acm-pdf format declared in _quarto.yml.
render: tables
	quarto render manuscript.qmd
	$(MAKE) clean

# Blind version for review: the BLIND-REVIEW SWAP blocks of manuscript.qmd
# applied to a temporary copy, rendered to manuscript_blind.pdf.
blind: tables
	uv run python scripts/blind.py
	$(MAKE) clean

# Self-contained arXiv source bundle of the named version (needs the
# manuscript.tex of a fresh `make render`). Output is gitignored.
arxiv:
	bash scripts/build_arxiv_bundle.sh

# Build intermediates only; manuscript.pdf stays.
clean:
	rm -rf .quarto manuscript_files manuscript.fdb_latexmk comment.cut
	find scripts -name __pycache__ -type d -prune -exec rm -rf {} +
