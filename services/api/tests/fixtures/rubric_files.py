"""In-test builders for minimal XLSX / DOCX packages (stdlib zipfile only).

Used by the rubric importer unit tests and the task-rubrics router tests so
no binary fixture files live in the repo. The packages carry exactly the
parts the importer reads (plus the content-types boilerplate real files
have): ``xl/workbook.xml`` + rels + one worksheet + shared strings for XLSX;
``word/document.xml`` (+ optional ``numbering.xml`` / ``styles.xml``) for
DOCX.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from xml.sax.saxutils import escape

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class RichText:
    """A shared string made of several ``<r>`` runs."""

    def __init__(self, parts: Sequence[str]):
        self.parts = list(parts)


class Formula:
    """A formula cell with its cached value (``<f>`` + ``<v>``)."""

    def __init__(self, formula: str, cached: Union[int, float]):
        self.formula = formula
        self.cached = cached


def _content_types(parts: Iterable[Tuple[str, str]]) -> str:
    overrides = "".join(
        f'<Override PartName="/{name}" ContentType="{ctype}"/>' for name, ctype in parts
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{overrides}</Types>"
    )


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def make_xlsx(
    rows: Sequence[Optional[Dict[str, Any]]],
    *,
    shared_strings: bool = True,
    sheet_file: str = "sheet1.xml",
    absolute_target: bool = False,
) -> bytes:
    """Build a one-sheet workbook.

    ``rows[i]`` is row ``i + 1``: a mapping ``{"A": "text", "B": 1.5, ...}``
    (``None`` for an empty row). Strings become shared strings (or inline
    strings when ``shared_strings=False``), ``RichText`` becomes a rich
    shared string, ``Formula`` a formula cell with a cached value.
    """
    sst: List[Any] = []

    def sst_index(value: Any) -> int:
        sst.append(value)
        return len(sst) - 1

    row_xml: List[str] = []
    for index, row in enumerate(rows, start=1):
        if not row:
            continue
        cells: List[str] = []
        for col, value in row.items():
            ref = f"{col}{index}"
            if isinstance(value, Formula):
                cells.append(f'<c r="{ref}"><f>{escape(value.formula)}</f><v>{value.cached}</v></c>')
            elif isinstance(value, RichText):
                cells.append(f'<c r="{ref}" t="s"><v>{sst_index(value)}</v></c>')
            elif isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>')
            elif isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif value is None:
                continue
            elif shared_strings:
                cells.append(f'<c r="{ref}" t="s"><v>{sst_index(str(value))}</v></c>')
            else:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'
                )
        row_xml.append(f'<row r="{index}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{XLSX_NS}" xmlns:r="{REL_NS}"><sheetData>'
        f'{"".join(row_xml)}</sheetData></worksheet>'
    )
    si_xml: List[str] = []
    for value in sst:
        if isinstance(value, RichText):
            runs = "".join(
                f'<r><rPr><b/></rPr><t xml:space="preserve">{escape(p)}</t></r>' for p in value.parts
            )
            si_xml.append(f"<si>{runs}</si>")
        else:
            si_xml.append(f'<si><t xml:space="preserve">{escape(value)}</t></si>')
    sst_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{XLSX_NS}" count="{len(sst)}" uniqueCount="{len(sst)}">'
        f'{"".join(si_xml)}</sst>'
    )
    target = f"/xl/worksheets/{sheet_file}" if absolute_target else f"worksheets/{sheet_file}"
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{XLSX_NS}" xmlns:r="{REL_NS}"><sheets>'
        '<sheet name="Tabelle1" sheetId="1" r:id="rId7"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        f'<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{target}"/>'
        '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            _content_types(
                [
                    ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
                    (f"xl/worksheets/{sheet_file}", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
                    ("xl/sharedStrings.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"),
                ]
            ),
        )
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr(f"xl/worksheets/{sheet_file}", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", sst_xml)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

ParagraphSpec = Union[str, Dict[str, Any]]


def _paragraph_xml(spec: ParagraphSpec) -> str:
    """``"text"`` | ``{"text", "bullet"?: bool, "num"?: (numId, ilvl), "style"?: str}``."""
    if isinstance(spec, str):
        spec = {"text": spec}
    text = spec.get("text", "")
    ppr_parts: List[str] = []
    if spec.get("style"):
        ppr_parts.append(f'<w:pStyle w:val="{spec["style"]}"/>')
    num = spec.get("num")
    if spec.get("bullet"):
        num = (1, 0)
    if num is not None:
        num_id, ilvl = num
        ppr_parts.append(f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>')
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""
    runs = ""
    if text:
        chunks = text.split("\t")
        run_parts = []
        for i, chunk in enumerate(chunks):
            if i:
                run_parts.append("<w:tab/>")
            if chunk:
                run_parts.append(f'<w:t xml:space="preserve">{escape(chunk)}</w:t>')
        runs = f"<w:r>{''.join(run_parts)}</w:r>"
    return f"<w:p>{ppr}{runs}</w:p>"


def _table_xml(table: Sequence[Sequence[Sequence[ParagraphSpec]]]) -> str:
    rows = []
    for row in table:
        cells = "".join(
            "<w:tc><w:tcPr><w:tcW w:w=\"4000\" w:type=\"dxa\"/></w:tcPr>"
            + ("".join(_paragraph_xml(p) for p in cell) or "<w:p/>")
            + "</w:tc>"
            for cell in row
        )
        rows.append(f"<w:tr>{cells}</w:tr>")
    return f"<w:tbl><w:tblPr/><w:tblGrid/>{''.join(rows)}</w:tbl>"


# numId 1 = bullets; numId 2 = a multilevel outline list (A. / I. / 1. / a) / aa) / (1))
_NUMBERING_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:numbering xmlns:w="{W_NS}">'
    '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#xF0B7;"/></w:lvl>'
    '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="o"/></w:lvl>'
    "</w:abstractNum>"
    '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="multilevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperLetter"/><w:lvlText w:val="%1."/></w:lvl>'
    '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:lvlText w:val="%2."/></w:lvl>'
    '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%3."/></w:lvl>'
    '<w:lvl w:ilvl="3"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%4)"/></w:lvl>'
    '<w:lvl w:ilvl="4"><w:start w:val="27"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%5)"/></w:lvl>'
    '<w:lvl w:ilvl="5"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="(%6)"/></w:lvl>'
    "</w:abstractNum>"
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
    "</w:numbering>"
)

# Style-linked numbering: "H1" carries the outline list, "H2"/"H3" inherit the
# numId from H1 and only set their level (the way Word's Überschrift styles do).
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="H1"><w:name w:val="heading 1"/>'
    '<w:pPr><w:numPr><w:numId w:val="2"/></w:numPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="H2"><w:name w:val="heading 2"/><w:basedOn w:val="H1"/>'
    '<w:pPr><w:numPr><w:ilvl w:val="1"/></w:numPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="H3"><w:name w:val="heading 3"/><w:basedOn w:val="H1"/>'
    '<w:pPr><w:numPr><w:ilvl w:val="2"/></w:numPr><w:outlineLvl w:val="2"/></w:pPr></w:style>'
    "</w:styles>"
)


def make_docx(
    tables: Sequence[Sequence[Sequence[Sequence[ParagraphSpec]]]],
    *,
    paragraphs_before: Sequence[ParagraphSpec] = (),
    paragraphs_after: Sequence[ParagraphSpec] = (),
    paragraphs_between: Sequence[ParagraphSpec] = (),
    bullet_numbering: bool = False,
    styles: bool = False,
) -> bytes:
    """Build a document: paragraphs, then each table (with ``paragraphs_between``
    before every table after the first), then trailing paragraphs.

    Tables are ``rows → cells → paragraphs``; a paragraph spec is a string or
    ``{"text", "bullet": True}`` (numId 1, needs ``bullet_numbering``),
    ``{"text", "num": (2, ilvl)}`` (outline list) or ``{"text", "style": "H2"}``
    (style-linked numbering, needs ``styles``).
    """
    body: List[str] = [_paragraph_xml(p) for p in paragraphs_before]
    for index, table in enumerate(tables):
        if index:
            body.extend(_paragraph_xml(p) for p in paragraphs_between)
        body.append(_table_xml(table))
    body.extend(_paragraph_xml(p) for p in paragraphs_after)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}<w:sectPr/></w:body></w:document>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    parts = [("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", document_xml)
        if bullet_numbering or styles:
            zf.writestr("word/numbering.xml", _NUMBERING_XML)
            parts.append(("word/numbering.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"))
        if styles:
            zf.writestr("word/styles.xml", _STYLES_XML)
            parts.append(("word/styles.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"))
        zf.writestr("[Content_Types].xml", _content_types(parts))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The colleague's sheet, reduced (points re-balanced to sum to 100 so the
# Notenschlüssel still fits; every real-world quirk of the original kept).
# ---------------------------------------------------------------------------

SCALE_RANGES = [
    "0-9", "10~19", "20-29", "30-39", "40-43", "44-47", "48-51", "52-55", "56-59",
    "60-63", "64-67", "68-71", "72-75", "76-79", "80-83", "84-87", "88-91", "92-95", "96-100",
]
COLLEAGUE_THRESHOLDS = [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96]
_COLS = "BCDEFGHIJKLMNOPQRST"


def colleague_sample_rows(*, grades: Optional[List[int]] = None) -> List[Optional[Dict[str, Any]]]:
    grades = list(range(19)) if grades is None else grades
    scale_row = {"A": "BE", **{_COLS[i]: r for i, r in enumerate(SCALE_RANGES)}}
    grade_row = {"A": "Note in Punkten", **{_COLS[i]: g for i, g in enumerate(grades)}}
    return [
        {"A": "Frage 1:", "B": "max. BE", "C": "Ihre BE"},  # 1
        {"A": "A.    Zulässigkeit  (insgesamt 21 BE)"},  # 2 (declared 21, steps sum to 6 → subtotal warning)
        {"A": "I.                Eröffnung des Verwaltungsrechtswegs nach § 40 I 1 VwGO", "B": 1},  # 3
        {"A": "·        Abdrängende Sonderzuweisung eindeutig zu verneinen", "B": 2},  # 4
        {"A": "II.              Statthafte Klageart"},  # 5
        {"A": "1.               Anfechtungsklage"},  # 6
        {"A": "a)               Verwaltungsakt i.S.d. Art. 35 S. 1 VwVfG"},  # 7
        {"A": "·        Regelung (+)", "B": 1},  # 8
        {"A": "·        Allgemeinverfügung irrelevant", "B": 0.5},  # 9
        {"A": "b)              Erledigung des VA", "B": 1},  # 10
        {"A": "IV.            Klagebefugnis, § 42 II VwGO analog", "B": 0.5},  # 11
        {"A": RichText(["B.    ", "Begründetheit", " (insgesamt 21,5 BE)"])},  # 12
        {"A": "Obersatz (Vergangenheitsform!)", "B": 1},  # 13
        {"A": "b)              Maßnahmerichtung (Schwerpunkt!)", "B": 10},  # 14
        {"A": "·        Ausführliche Diskussion: H als Zweckveranlasser? (+)"},  # 15
        {"A": "·        A. A. vertr., wichtig ist die Diskussion der Frage!"},  # 16
        {"A": "bb)           Unverhältnismäßiger Grundrechtseingriff (weiterer Schwerpunkt!)"},  # 17
        {"A": "(1)            Schutzbereich", "B": 4},  # 18
        {"A": "(3)            Rechtfertigung", "B": 6},  # 19
        {"A": "III.            Rechtsverletzung des H", "B": 0.5},  # 20
        {"A": "IV.            Zwischenergebnis"},  # 21
        {"A": "C.    Ergebnis"},  # 22
        None,  # 23
        {"A": "Frage 2: Insgesamt 72,5 BE"},  # 24
        {"A": "I.            Rechtsgrundlage"},  # 25
        {"A": "1.           Art. 16 Abs. 2 S. 1 Nr. 2 lit. a PAG", "B": 2},  # 26
        {"A": "·        Auftrittsverbot kein Aufenthaltsverbot"},  # 27
        {"A": "2.           Generalklausel (Schwerpunkt!)", "B": 1},  # 28
        {"A": "a)           Sperrwirkung der Standardbefugnisse", "B": "1,5"},  # 29 (text cell with comma)
        {"A": "II.          Formelle Rechtmäßigkeit des Auftrittsverbots"},  # 30
        {"A": "aa)        Aufgabeneröffnung nach Art. 2 Abs. 1 PAG (Schwerpunkt!)", "B": 68},  # 31
        {"A": "Gesamt-BE", "B": Formula("SUM(B1:B31)", 100), "C": Formula("SUM(C2:C31)", 0)},  # 32
        {"A": "Ergibt Gesamtnote:"},  # 33
        None,  # 34
        {"A": "Notenschlüssel:"},  # 35
        scale_row,  # 36
        grade_row,  # 37
        None,  # 38
        {"A": "Die Note errechnet sich aus den zusammengezählten BE der rechten Spalte; bei 0,5 BE wird abgerundet."},  # 39
        {"A": "Korrektor: Dr. Martin Heidebach martin.heidebach@jura.uni-muenchen.de"},  # 40
    ]


def colleague_sample_xlsx(**kwargs) -> bytes:
    return make_xlsx(colleague_sample_rows(), **kwargs)
