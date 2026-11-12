.PHONY: render docx slides-pdf clean

# PDF, Chicago notes and bibliography (footnote citations, CSL in this folder).
render:
	quarto render manuscript.qmd --to pdf

# Word manuscript in the St.Gallen Publishing template. The template is the
# publisher's file and stays out of the public repo: copy it to
# publisher/St.Gallen_Publishing_Template.docx (gitignored) first. Quarto
# renders against it as reference-doc, then scripts/apply_publisher_styles.py
# maps Quarto's paragraph styles (title, author, abstract, headings, body,
# lists, table captions, references) onto the template's own styles.
# Without the template the target still produces a plain manuscript.docx.
TEMPLATE = publisher/St.Gallen_Publishing_Template.docx
docx:
	@if [ -f "$(TEMPLATE)" ]; then \
	  quarto render manuscript.qmd --to docx -M reference-doc:$(TEMPLATE) && \
	  python3 scripts/apply_publisher_styles.py manuscript.docx; \
	else \
	  echo "note: $(TEMPLATE) not found, rendering a plain manuscript.docx without the publisher's styles"; \
	  quarto render manuscript.qmd --to docx; \
	fi

# Print the HTML deck to presentation/slides.pdf (one 16:9 page per slide).
slides-pdf:
	python3 presentation/build_pdf.py

clean:
	rm -rf .quarto manuscript_files manuscript.tex manuscript.log \
	       manuscript.fdb_latexmk manuscript.quarto_ipynb*
