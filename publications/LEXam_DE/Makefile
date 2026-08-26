.PHONY: render slides-pdf clean

render:
	quarto render manuscript.qmd

# Print the HTML deck to presentation/slides.pdf (one 16:9 page per slide).
slides-pdf:
	python3 presentation/build_pdf.py

clean:
	rm -rf .quarto manuscript_files manuscript.tex manuscript.log \
	       manuscript.fdb_latexmk manuscript.quarto_ipynb*
