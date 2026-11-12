#!/usr/bin/env python3
"""Map Quarto's docx paragraph styles onto the St.Gallen Publishing template.

Quarto renders manuscript.docx with the publisher's template as reference-doc,
which brings the template's styles, page setup and header into the file but
leaves every paragraph in Pandoc's own styles (Body Text, Heading 1, ...).
This script rewrites those paragraph styles to the template's styles so the
manuscript opens in Word exactly as the publisher's sample document does:

    Title / Subtitle / Author  -> 01 Haupttitel / 01a Untertitel / 08 Autor
    Abstract                   -> 06a_Abstract_primär (abstract heading removed)
    Heading 1..4               -> 06 Zw'titel 1 .. 06d Zw'titel 4
    Body Text, First Paragraph -> 05 Grundschrift de
    bullet / numbered lists    -> 05a Grundschrift Aufz / 05c ... Nummeriert
    block quote                -> 05a Grundschrift Einz_Ohne Aufz
    table caption              -> 14a Grafiktitel
    table cells                -> 12 Beispieltexte (the template's small text)
    references heading / list  -> 13a Literatur / 13a Literatur Grundtext

Footnotes keep Pandoc's "Footnote Text", which the template defines itself
(Arial 9 pt), and the author legend paragraph (03 Legende, written as raw
OpenXML in manuscript.qmd) is moved directly under the author line, where the
template places it. Usage: apply_publisher_styles.py manuscript.docx
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

PARAGRAPH_STYLES = {
    "Title": "01Haupttitel",
    "Subtitle": "01aUntertitel",
    "Author": "08Autor",
    "Abstract": "06aAbstractprimr",
    "Heading1": "06Zwtitel1",
    "berschrift1": "06Zwtitel1",
    "Heading2": "06bZwtitel2225mm",
    "berschrift2": "06bZwtitel2225mm",
    "Heading3": "06cZwtitel3225mm",
    "Heading4": "06dZwtitel4225mm",
    "BodyText": "05Grundschriftde",
    "FirstParagraph": "05Grundschriftde",
    "BlockText": "05aGrundschriftEinzOhneAufz",
    "Bibliography": "13aLiteraturGrundtext",
    "Caption": "14aGrafiktitel",
}
CAPTION_STYLES = {"Caption", "TableCaption", "ImageCaption"}
DROP_PARAGRAPH_STYLES = {"AbstractTitle", "Date"}
LIST_STYLE_BULLET = "05aGrundschriftAufz"
LIST_STYLE_NUMBERED = "05cGrundschriftAufzNummeriert"
TABLE_CELL_STYLE = "12Beispieltexte"
REFERENCES_HEADING = "13aLiteratur"
LEGEND_STYLE = "03Legende"
AUTHOR_STYLE = "08Autor"

# Self-closing paragraphs (<w:p/>) are matched first and the opening tag may not
# contain a slash, or an empty cell paragraph would swallow everything up to the
# next closing paragraph.
P_RE = re.compile(r"<w:p\b[^>]*/>|<w:p\b[^>/]*>.*?</w:p>", re.S)
PSTYLE_RE = re.compile(r'<w:pStyle w:val="([^"]+)"\s*/>')
NUMFMT_BULLET_RE = re.compile(r'<w:numFmt w:val="bullet"')


def style_of(p: str) -> str | None:
    m = PSTYLE_RE.search(p)
    return m.group(1) if m else None


def set_style(p: str, new: str) -> str:
    if PSTYLE_RE.search(p):
        return PSTYLE_RE.sub(f'<w:pStyle w:val="{new}"/>', p, count=1)
    if "<w:pPr>" in p:
        return p.replace("<w:pPr>", f'<w:pPr><w:pStyle w:val="{new}"/>', 1)
    return re.sub(r"(<w:p\b[^>]*>)", rf'\1<w:pPr><w:pStyle w:val="{new}"/></w:pPr>', p, count=1)


def bullet_num_ids(numbering_xml: str) -> set[str]:
    """numId values whose abstract numbering is a bullet list."""
    abstract_bullets = set()
    for m in re.finditer(r'<w:abstractNum\b[^>]*w:abstractNumId="(\d+)".*?</w:abstractNum>', numbering_xml, re.S):
        if NUMFMT_BULLET_RE.search(m.group(0)):
            abstract_bullets.add(m.group(1))
    ids = set()
    for m in re.finditer(r'<w:num\b[^>]*w:numId="(\d+)".*?<w:abstractNumId w:val="(\d+)"', numbering_xml, re.S):
        if m.group(2) in abstract_bullets:
            ids.add(m.group(1))
    return ids


TOKEN_RE = re.compile(r"<w:tbl>|</w:tbl>|<w:p\b[^>]*/>|<w:p\b[^>/]*>.*?</w:p>", re.S)


def restyle_document(doc: str, bullets: set[str]) -> str:
    depth = 0

    def repl(m: re.Match) -> str:
        nonlocal depth
        tok = m.group(0)
        if tok == "<w:tbl>":
            depth += 1
            return tok
        if tok == "</w:tbl>":
            depth -= 1
            return tok
        return restyle_paragraph(tok, bullets, in_table=depth > 0)

    doc = TOKEN_RE.sub(repl, doc)
    doc = drop_abstract_title(doc)
    doc = mark_references_heading(doc)
    doc = move_legend_under_author(doc)
    return doc


DOUBLE_PPR_RE = re.compile(r"<w:pPr>(?:(?!</w:pPr>).)*?</w:pPr>(\s*<w:pPr>)", re.S)


def restyle_paragraph(p: str, bullets: set[str], in_table: bool) -> str:
    # Quarto emits a table caption with two w:pPr elements (an empty centring
    # one before the real one); Word accepts only the first, so drop it.
    p = DOUBLE_PPR_RE.sub(r"\1", p, count=1)
    st = style_of(p)
    if st in CAPTION_STYLES:
        return set_style(p, PARAGRAPH_STYLES["Caption"])
    if in_table:
        if st in (None, "Compact", "BodyText", "FirstParagraph", "Normal"):
            return set_style(p, TABLE_CELL_STYLE)
        return p
    if st == "Compact" or (st in (None, "BodyText", "FirstParagraph") and "<w:numPr>" in p):
        num = re.search(r'<w:numId w:val="(\d+)"', p)
        return set_style(p, LIST_STYLE_BULLET if num and num.group(1) in bullets else LIST_STYLE_NUMBERED)
    if st in PARAGRAPH_STYLES:
        p = set_style(p, PARAGRAPH_STYLES[st])
        if PARAGRAPH_STYLES[st].startswith("06"):
            p = use_template_heading_numbers(p)
        return p
    return p


HEADING_NUMBER_RE = re.compile(r'(<w:t(?: xml:space="preserve")?>)\d+(?:\.\d+)*\.?\s+')
NO_NUMBERING = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr>'


def use_template_heading_numbers(p: str) -> str:
    """The template's heading styles number themselves (one list, levels 1 to 4).
    Quarto also writes the section number as text, so strip that text from numbered
    headings and switch the style's numbering off on headings Quarto left unnumbered
    (AI usage disclosure), which otherwise would be numbered by the style."""
    if HEADING_NUMBER_RE.search(p):
        return HEADING_NUMBER_RE.sub(r"\1", p, count=1)
    return p.replace("</w:pPr>", NO_NUMBERING + "</w:pPr>", 1)


def drop_abstract_title(doc: str) -> str:
    def repl(m: re.Match) -> str:
        return "" if style_of(m.group(0)) in DROP_PARAGRAPH_STYLES else m.group(0)
    return P_RE.sub(repl, doc)


def mark_references_heading(doc: str) -> str:
    """The heading right before the first bibliography entry becomes 13a Literatur."""
    paras = list(P_RE.finditer(doc))
    first_bib = next((i for i, m in enumerate(paras) if style_of(m.group(0)) == "13aLiteraturGrundtext"), None)
    if first_bib is None:
        return doc
    for i in range(first_bib - 1, -1, -1):
        st = style_of(paras[i].group(0))
        if st and st.startswith("06"):
            m = paras[i]
            return doc[:m.start()] + set_style(m.group(0), REFERENCES_HEADING) + doc[m.end():]
        if st is not None:
            break
    return doc


def move_legend_under_author(doc: str) -> str:
    paras = list(P_RE.finditer(doc))
    legends = [m for m in paras if style_of(m.group(0)) == LEGEND_STYLE]
    authors = [m for m in paras if style_of(m.group(0)) == AUTHOR_STYLE]
    if not legends or not authors:
        return doc
    legend_xml = "".join(m.group(0) for m in legends)
    for m in reversed(legends):
        doc = doc[:m.start()] + doc[m.end():]
    last_author = [m for m in P_RE.finditer(doc) if style_of(m.group(0)) == AUTHOR_STYLE][-1]
    return doc[:last_author.end()] + legend_xml + doc[last_author.end():]


def main(path: str) -> None:
    src = Path(path)
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        numbering = zin.read("word/numbering.xml").decode("utf-8") if "word/numbering.xml" in names else ""
        document = zin.read("word/document.xml").decode("utf-8")
        new_document = restyle_document(document, bullet_num_ids(numbering))
        tmp = Path(tempfile.mkstemp(suffix=".docx", dir=src.parent)[1])
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = new_document.encode("utf-8") if item.filename == "word/document.xml" else zin.read(item.filename)
                zout.writestr(item, data)
    shutil.move(tmp, src)
    counts = {}
    for m in P_RE.finditer(new_document):
        st = style_of(m.group(0)) or "(none)"
        counts[st] = counts.get(st, 0) + 1
    print("paragraph styles in", src.name + ":")
    for st, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {st}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
