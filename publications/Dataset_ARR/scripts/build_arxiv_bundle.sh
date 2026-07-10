#!/usr/bin/env bash
# Build a self-contained arXiv source bundle from the current render.
#
# Collects manuscript.tex (keep-tex output of `make render`) plus everything
# it references (assets/*.tex tables, figure files, fonts, bib/style files),
# verifies the bundle compiles standalone with xelatex + bibtex in a scratch
# directory, includes the produced .bbl, and tars the result to
# benger_arxiv_source_<date>.tar.gz (gitignored - bundles ship to arXiv,
# never to git).
#
# Usage: make arxiv   (or: bash scripts/build_arxiv_bundle.sh)

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f manuscript.tex ]]; then
    echo "manuscript.tex not found - run 'make render' first." >&2
    exit 1
fi

OUT="benger_arxiv_source_$(date +%F).tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Static bundle members.
cp manuscript.tex references.bib acl.sty acl_natbib.bst "$STAGE/"
mkdir -p "$STAGE/fonts"
cp fonts/*.otf "$STAGE/fonts/"

# Everything manuscript.tex references via \input{...} or \includegraphics.
mapfile -t refs < <(
    { grep -oE '\\input\{[^}]+\}' manuscript.tex \
        | sed -E 's/\\input\{([^}]+)\}/\1/';
      grep -oE '\\includegraphics(\[[^]]*\])?\{[^}]+\}' manuscript.tex \
        | sed -E 's/.*\{([^}]+)\}/\1/'; } | sort -u
)
for f in "${refs[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "referenced file missing: $f (stale render?)" >&2
        exit 1
    fi
    mkdir -p "$STAGE/$(dirname "$f")"
    cp "$f" "$STAGE/$f"
done

# Prove the bundle compiles standalone and produce the .bbl for arXiv.
echo "verifying standalone compile in $STAGE ..."
(
    cd "$STAGE"
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex > compile.log 2>&1 \
        || { tail -30 compile.log >&2; exit 1; }
    bibtex manuscript >> compile.log 2>&1 || { tail -30 compile.log >&2; exit 1; }
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex >> compile.log 2>&1
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex >> compile.log 2>&1
    [[ -s manuscript.pdf ]] || { echo "no PDF produced" >&2; exit 1; }
)
pages=$(grep -oE 'Output written on manuscript.pdf \([0-9]+ pages' \
            "$STAGE/manuscript.log" | tail -1 | grep -oE '[0-9]+' || echo "?")
[[ "$pages" != "?" && "$pages" -gt 10 ]] \
    || { echo "suspicious page count: $pages" >&2; exit 1; }
echo "standalone compile OK ($pages pages)"

# Bundle: sources + .bbl, minus build artifacts.
rm -f "$STAGE"/manuscript.{pdf,aux,log,out,blg,fls,fdb_latexmk} "$STAGE/compile.log"
tar czf "$OUT" -C "$STAGE" $(ls "$STAGE")
echo "wrote $OUT ($(du -h "$OUT" | cut -f1)) with $(tar -tzf "$OUT" | grep -vc '/$') files"
