#!/usr/bin/env bash
# Build a self-contained arXiv source bundle of the NAMED version from the
# current render (the same recipe as the benchmark paper's bundle script).
#
# Collects manuscript.tex (keep-tex output of `make render`) plus everything
# it references (assets/*.tex tables, the figure), the bibliography, and the
# acmart class and bibliography style of the local TeX Live, so the bundle
# does not depend on the acmart version arXiv happens to ship. The staged
# .tex gets the acmart `nonacm` option, which drops the placeholder DOI,
# ISBN and ACM reference block that a conference submission carries; the
# text is otherwise unchanged. The bundle is compiled standalone with
# xelatex + bibtex in a scratch directory (arXiv compiles with XeLaTeX,
# which has to be selected on the submission form), the produced .bbl is
# included, and the result is zipped to sok_arxiv_source_<date>.zip
# (gitignored: bundles ship to arXiv, never to git).
#
# Usage: make arxiv   (or: bash scripts/build_arxiv_bundle.sh)

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f manuscript.tex ]]; then
    echo "manuscript.tex not found - run 'make render' first." >&2
    exit 1
fi
if grep -q "anonymous" <(sed -n '/\\documentclass/p' manuscript.tex); then
    echo "manuscript.tex is the anonymous build - run 'make render' (not 'make blind') first." >&2
    exit 1
fi

TEXBIN="$HOME/.TinyTeX/bin/x86_64-linux"
[[ -x "$TEXBIN/xelatex" ]] || TEXBIN="$(dirname "$(command -v xelatex)")"
KPSE="$TEXBIN/kpsewhich"

OUT="sok_arxiv_source_$(date +%F).zip"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# The main file, with the preprint class option.
sed 's/\\documentclass\[acmsmall,screen\]{acmart}/\\documentclass[acmsmall,screen,nonacm]{acmart}/' \
    manuscript.tex > "$STAGE/manuscript.tex"
grep -q 'acmsmall,screen,nonacm' "$STAGE/manuscript.tex" || { echo "documentclass line not found" >&2; exit 1; }

# Bibliography, class and style files.
cp references.bib "$STAGE/"
cp "$("$KPSE" acmart.cls)" "$("$KPSE" ACM-Reference-Format.bst)" "$STAGE/"

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
    export PATH="$TEXBIN:$PATH"
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex > compile.log 2>&1 \
        || { tail -30 compile.log >&2; exit 1; }
    bibtex manuscript >> compile.log 2>&1 || { tail -30 compile.log >&2; exit 1; }
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex >> compile.log 2>&1
    xelatex -interaction=nonstopmode -halt-on-error manuscript.tex >> compile.log 2>&1
    [[ -s manuscript.pdf ]] || { echo "no PDF produced" >&2; exit 1; }
    if grep -q -E "Citation .* undefined|Reference .* undefined" manuscript.log; then
        echo "undefined citations or references in the standalone compile" >&2; exit 1
    fi
)
pages=$(grep -oE 'Output written on manuscript.pdf \([0-9]+ pages' \
            "$STAGE/manuscript.log" | tail -1 | grep -oE '[0-9]+' || echo "?")
[[ "$pages" != "?" && "$pages" -gt 10 ]] \
    || { echo "suspicious page count: $pages" >&2; exit 1; }
echo "standalone compile OK ($pages pages)"
cp "$STAGE/manuscript.pdf" "sok_arxiv_preview_$(date +%F).pdf"

# arXiv's 00README.json: compile with xelatex (acmart loads the Libertine
# OpenType fonts through fontspec), manuscript.tex is the top-level file.
cat > "$STAGE/00README.json" <<'EOF'
{
  "process": {"compiler": "xelatex"},
  "sources": [{"filename": "manuscript.tex", "usage": "toplevel"}]
}
EOF

# Bundle: sources + .bbl, minus build artifacts.
rm -f "$STAGE"/manuscript.{pdf,aux,log,out,blg,fls,fdb_latexmk,toc} "$STAGE/compile.log" "$STAGE/comment.cut"
rm -f "$OUT"
# python's zipfile, since the zip binary is not installed everywhere.
python3 - "$STAGE" "$OUT" <<'EOF'
import os, sys, zipfile
stage, out = sys.argv[1], sys.argv[2]
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk(stage):
        for f in sorted(files):
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, stage))
            count += 1
print(f"{out}: {count} files")
EOF
echo "wrote $OUT ($(du -h "$OUT" | cut -f1)); preview PDF next to it"
