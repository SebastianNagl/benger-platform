"""Deterministic Korrekturbogen importer: XLSX / DOCX → rubric structure.

A professor's Korrekturbogen (grading sheet) is typically a two-column table:
the outline of the Musterlösung (``A.`` → ``I.`` → ``1.`` → ``a)`` → ``aa)``
→ ``(1)`` → bullet hints) on the left and the maximum Bewertungseinheiten
(BE, half points allowed) on the right, followed by a total row and a
Notenschlüssel (BE ranges → Notenpunkte 0..18) with a rounding sentence.

This module turns such a file into the canonical ``structure`` /
``grade_scale`` contract of ``services/shared/rubric_structure.py`` WITHOUT
any LLM: pure heuristics over the cell text, so the result is reproducible
and cheap, and a human review step (the outline editor) always follows.
Every guess that a reviewer should double-check is reported as a warning
``{code, message, row?, node_id?}`` — see ``WARNING_CODES``.

Both formats are read with the stdlib only (``zipfile`` + ``xml.etree``):
mammoth flattens tables and there is no XLSX reader in the image, and a new
dependency would silently be missing from the long-lived test image.

Public surface: :func:`parse_rubric_file`, :class:`RubricImportError`.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from rubric_structure import (
    GRADE_COUNT,
    MAX_HINT_LEN,
    MAX_HINTS_PER_STEP,
    MAX_LABEL_LEN,
    MAX_NODES,
    MAX_NOTE_LEN,
    MAX_TITLE_LEN,
    criteria_from_structure,
    format_points,
    normalize_structure,
    total_points_from_structure,
    validate_grade_scale,
    validate_structure,
)

MAX_RUBRIC_FILE_BYTES = 5 * 1024 * 1024
# Cap on the UNCOMPRESSED size of a single zip member. OOXML files are zips,
# so a 5 MB upload can declare a multi-gigabyte sheet/document part ("zip
# bomb") and OOM the api worker inside ``zf.read``. Every member this module
# reads goes through :func:`_read_member`, which refuses oversized entries
# before decompressing. 32 MB is far above any real Korrekturbogen (the
# colleague's 100-BE sheet has a 28 KB worksheet part).
MAX_ZIP_MEMBER_BYTES = 32 * 1024 * 1024
MAX_RAW_ROWS = 2000
SUPPORTED_EXTS = {".xlsx", ".docx"}
MAX_TITLE_CANDIDATE_LEN = 120

WARNING_CODES = (
    "merged_label_cell",
    "auto_numbering",
    "ambiguous_label",
    "alignment_uncertain",
    "note_from_bullet",
    "empty_section",
    "points_rounded",
    "points_invalid",
    "subtotal_mismatch",
    "total_mismatch",
    "grade_scale_unparsed",
    "grade_scale_total_mismatch",
    "rounding_assumed",
    "title_from_filename",
)

ERROR_CODES = (
    "unsupported_type",
    "corrupt_file",
    "no_table_found",
    "no_scored_steps",
    "too_many_rows",
)


class RubricImportError(Exception):
    """A file that cannot be turned into a rubric (``code`` ∈ ERROR_CODES)."""

    def __init__(self, code: str, message: str, warnings: Optional[List[Dict[str, Any]]] = None):
        self.code = code
        self.message = message
        self.warnings = warnings or []
        super().__init__(message)

    def to_detail(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "warnings": self.warnings}


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_FRAGE_RE = re.compile(r"^(Frage|Aufgabe|Teil)\s+(\d{1,2}|[A-Z])\s*[:.]?(?:\s+|$)(.*)$", re.I)
_ROMAN_RE = re.compile(r"^([IVX]{1,6})\.(?:\s+|$)(.*)$")
_CAPITAL_RE = re.compile(r"^([A-Z])\.(?:\s+|$)(.*)$")
_DECIMAL_RE = re.compile(r"^(\d{1,2})\.(?:\s+|$)(.*)$")
_DOUBLE_LOWER_RE = re.compile(r"^([a-z])\1\)\s*(.*)$")
_LOWER_RE = re.compile(r"^([a-z])\)\s*(.*)$")
_PAREN_DECIMAL_RE = re.compile(r"^\((\d{1,2})\)\s*(.*)$")
_PAREN_LOWER_RE = re.compile(r"^\(([a-z]{1,2})\)\s*(.*)$")
_BULLET_RE = re.compile(r"^[·•\-–—*]\s*(.*)$")

_HEADER_CELL_RE = re.compile(r"^(max\.?\s*)?(BE|Punkte|Pkt\.?|P\.?)\s*:?$", re.I)
_IGNORED_COLUMN_RE = re.compile(r"(Ihre\s+BE|Bewertung|erreicht|Korrektor)", re.I)
_TOTAL_ROW_RE = re.compile(
    r"^(Gesamt(?:\s*-?\s*(?:BE|punkte|punktzahl|summe))?|Summe|Gesamtpunkte|Σ)\s*[:.]?\s*$",
    re.I,
)
_TRAILER_RE = re.compile(r"^(Korrektor(?:in)?|Prüfer(?:in)?|Ergibt|Gesamtnote|Note)\b", re.I)
_SCALE_TRIGGER_RE = re.compile(r"^(Noten|Punkte)schl(ü|ue)ssel", re.I)
_ROUNDING_RE = re.compile(r"\b(abgerundet|aufgerundet|kaufmännisch)\b", re.I)
_NOTE_RE = re.compile(
    r"\(?\s*(insgesamt\s*:?\s*\d+(?:[.,]\d+)?\s*BE)\s*\)?", re.I
)
_NOTE_VALUE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_EMPHASIS_RE = re.compile(r"\(\s*(?:weiterer\s+)?Schwerpunkt\s*!?\s*\)", re.I)
_POINTS_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:BE|P\.?|Pkt\.?|Punkte)?\s*$", re.I)
_RANGE_RE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:[-–—~]|bis)\s*(\d+(?:[.,]\d+)?)\s*(?:BE)?\s*$", re.I
)
_GRADE_RE = re.compile(r"^\s*(\d{1,2})\s*(?:NP|Punkte|Notenpunkte)?\s*$", re.I)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_value(text: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(text.upper()):
        value = _ROMAN_VALUES.get(ch, 0)
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def _to_roman(number: int) -> str:
    pairs = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    out = []
    for value, glyph in pairs:
        while number >= value:
            out.append(glyph)
            number -= value
    return "".join(out) or "0"


def _letters(number: int, upper: bool) -> str:
    base = ord("A") if upper else ord("a")
    if number <= 0:
        return ""
    # Word semantics: 27 → "AA", 28 → "BB" (repeat the letter), not base-26.
    repeat, letter = divmod(number - 1, 26)
    return chr(base + letter) * (repeat + 1)


def _parse_number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(el: ET.Element, name: str) -> Iterable[ET.Element]:
    for child in el:
        if _local(child.tag) == name:
            yield child


def _first(el: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if el is None:
        return None
    for child in el:
        if _local(child.tag) == name:
            return child
    return None


def _attr(el: Optional[ET.Element], name: str) -> Optional[str]:
    if el is None:
        return None
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return None


# ---------------------------------------------------------------------------
# Shared row model
# ---------------------------------------------------------------------------


@dataclass
class _RawRow:
    """One outline line: the text and the max points next to it.

    XLSX rows carry the unparsed ``points_raw`` cell and are parsed lazily by
    the outline builder (rows after the total row never get parsed, so the
    Notenschlüssel cells do not raise points warnings); DOCX rows are parsed
    during cell alignment (``points_parsed=True``).
    """

    text: str
    points: Optional[float]
    row: int
    points_text: Optional[str] = None
    bullet: bool = False
    auto_rank: Optional[int] = None
    auto_label: Optional[str] = None
    note: Optional[str] = None
    points_raw: Any = None
    points_parsed: bool = True


@dataclass
class _Node:
    kind: str
    level: int
    label: str
    title: str
    row: int
    rank: float
    parent: Optional["_Node"] = None
    note: Optional[str] = None
    max_score: Optional[float] = None
    emphasis: Optional[str] = None
    hints: List[str] = field(default_factory=list)
    declared_subtotal: Optional[float] = None
    has_children: bool = False


class _Warnings(list):
    def add(self, code: str, message: str, *, row: Optional[int] = None, node_id: Optional[str] = None):
        entry: Dict[str, Any] = {"code": code, "message": message}
        if row is not None:
            entry["row"] = row
        if node_id is not None:
            entry["node_id"] = node_id
        self.append(entry)


def _parse_points_cell(value: Any, row: int, warnings: _Warnings) -> Tuple[Optional[float], Optional[str]]:
    """``(points, raw_text)`` for a points cell; warnings for odd values."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        raw = format_points(number)
    else:
        raw = str(value).strip()
        if not raw:
            return None, None
        if _HEADER_CELL_RE.match(raw) or _NOTE_RE.search(raw):
            return None, raw
        match = _POINTS_RE.match(raw)
        if not match:
            warnings.add(
                "points_invalid",
                f"Zeile {row}: „{raw}“ ist keine gültige Punktzahl und wurde ignoriert.",
                row=row,
            )
            return None, raw
        number = _parse_number(match.group(1)) or 0.0
    if number <= 0:
        warnings.add(
            "points_invalid",
            f"Zeile {row}: Punktzahl {format_points(number)} ist nicht positiv und wurde ignoriert.",
            row=row,
        )
        return None, raw
    snapped = round(number * 2) / 2
    if abs(snapped - number) > 1e-9:
        warnings.add(
            "points_rounded",
            f"Zeile {row}: {format_points(number)} BE auf {format_points(snapped)} BE gerundet (halbe BE).",
            row=row,
        )
        number = snapped
    return number, raw


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def _col_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(index - 1, 0)


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes:
    """``zf.read(name)`` with a declared-size guard (see MAX_ZIP_MEMBER_BYTES).

    ``ZipInfo.file_size`` is the size recorded in the archive; a bomb has to
    declare its payload there, so refusing before the read keeps the
    decompression bounded. A lying header still cannot get past the member
    cap because ``read`` is given ``MAX_ZIP_MEMBER_BYTES + 1`` bytes at most.
    """
    try:
        info = zf.getinfo(name)
    except KeyError:
        raise
    if info.file_size > MAX_ZIP_MEMBER_BYTES:
        raise RubricImportError(
            "corrupt_file",
            "Die Datei enthält einen unerwartet großen Bestandteil und wurde nicht gelesen.",
        )
    with zf.open(name) as handle:
        data = handle.read(MAX_ZIP_MEMBER_BYTES + 1)
    if len(data) > MAX_ZIP_MEMBER_BYTES:
        raise RubricImportError(
            "corrupt_file",
            "Die Datei enthält einen unerwartet großen Bestandteil und wurde nicht gelesen.",
        )
    return data


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(_read_member(zf, "xl/sharedStrings.xml"))
    out: List[str] = []
    for si in root.iter():
        if _local(si.tag) != "si":
            continue
        parts: List[str] = []
        for el in si.iter():
            if _local(el.tag) == "rPh":
                continue
            if _local(el.tag) == "t":
                parts.append(el.text or "")
        out.append("".join(parts))
    return out


def _first_sheet_path(zf: zipfile.ZipFile) -> str:
    names = set(zf.namelist())
    workbook = ET.fromstring(_read_member(zf, "xl/workbook.xml"))
    sheet = next((el for el in workbook.iter() if _local(el.tag) == "sheet"), None)
    if sheet is None:
        raise RubricImportError("no_table_found", "Die Arbeitsmappe enthält kein Tabellenblatt.")
    rid = _attr(sheet, "id")
    target = None
    if rid and "xl/_rels/workbook.xml.rels" in names:
        rels = ET.fromstring(_read_member(zf, "xl/_rels/workbook.xml.rels"))
        for rel in rels.iter():
            if _local(rel.tag) == "Relationship" and rel.attrib.get("Id") == rid:
                target = rel.attrib.get("Target")
                break
    if not target:
        target = "worksheets/sheet1.xml"
    path = target.lstrip("/") if target.startswith("/") else os.path.normpath(f"xl/{target}")
    path = path.replace("\\", "/")
    if path not in names:
        raise RubricImportError("corrupt_file", "Das Tabellenblatt fehlt in der Datei.")
    return path


def _read_xlsx_grid(data: bytes) -> List[Tuple[int, Dict[int, Any]]]:
    """``[(row_no, {col_index: str|float})]`` of the first worksheet."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            shared = _shared_strings(zf)
            sheet = ET.fromstring(_read_member(zf, _first_sheet_path(zf)))
    except RubricImportError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        raise RubricImportError("corrupt_file", "Die XLSX-Datei konnte nicht gelesen werden.") from exc

    grid: List[Tuple[int, Dict[int, Any]]] = []
    next_row = 1
    for row_el in sheet.iter():
        if _local(row_el.tag) != "row":
            continue
        try:
            row_no = int(row_el.attrib.get("r") or next_row)
        except ValueError:
            row_no = next_row
        next_row = row_no + 1
        cells: Dict[int, Any] = {}
        next_col = 0
        for cell in _children(row_el, "c"):
            ref = cell.attrib.get("r")
            col = _col_index(ref) if ref else next_col
            next_col = col + 1
            kind = cell.attrib.get("t")
            v_el = _first(cell, "v")
            value: Any = None
            if kind == "s":
                try:
                    value = shared[int(v_el.text)] if v_el is not None and v_el.text else ""
                except (ValueError, IndexError):
                    value = ""
            elif kind == "inlineStr":
                is_el = _first(cell, "is")
                value = "".join(
                    (t.text or "") for t in (is_el.iter() if is_el is not None else []) if _local(t.tag) == "t"
                )
            elif kind == "str":
                value = v_el.text or "" if v_el is not None else ""
            elif kind == "b":
                value = "1" if v_el is not None and v_el.text == "1" else "0"
            elif kind == "e":
                value = None
            else:
                if v_el is not None and v_el.text not in (None, ""):
                    try:
                        value = float(v_el.text)
                    except ValueError:
                        value = v_el.text
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            cells[col] = value
        grid.append((row_no, cells))
        if len(grid) > MAX_RAW_ROWS:
            raise RubricImportError(
                "too_many_rows", f"Die Tabelle hat mehr als {MAX_RAW_ROWS} Zeilen."
            )
    return grid


def _detect_columns(grid: List[Tuple[int, Dict[int, Any]]]) -> Tuple[int, Optional[int]]:
    """``(text_col, points_col)`` for a grid (points_col None when no numeric column)."""
    text_counts: Dict[int, int] = {}
    numeric_cols: Dict[int, int] = {}
    header_col: Optional[int] = None
    ignored: set = set()
    for _row_no, cells in grid:
        for col, value in cells.items():
            if isinstance(value, str):
                text = value.strip()
                if _HEADER_CELL_RE.match(text) and header_col is None:
                    header_col = col
                elif _IGNORED_COLUMN_RE.search(text) and len(text) <= 30:
                    ignored.add(col)
                text_counts[col] = text_counts.get(col, 0) + 1
            elif isinstance(value, (int, float)):
                numeric_cols[col] = numeric_cols.get(col, 0) + 1
    text_col = next((col for col in sorted(text_counts) if text_counts[col] >= 3), None)
    if text_col is None:
        raise RubricImportError("no_table_found", "Keine Textspalte mit Gliederungspunkten gefunden.")
    if header_col is not None and header_col != text_col:
        return text_col, header_col
    for col in sorted(numeric_cols):
        if col > text_col and col not in ignored:
            return text_col, col
    return text_col, None


def _rows_from_xlsx(grid, warnings: _Warnings) -> Tuple[List[_RawRow], List[Tuple[int, Dict[int, Any]]]]:
    text_col, points_col = _detect_columns(grid)
    rows: List[_RawRow] = []
    for row_no, cells in grid:
        text_value = cells.get(text_col)
        text = format_points(text_value) if isinstance(text_value, (int, float)) else str(text_value or "")
        points_value = cells.get(points_col) if points_col is not None else None
        note = None
        if isinstance(points_value, str) and _NOTE_RE.search(points_value):
            note = _NOTE_RE.search(points_value).group(1).strip()
            points_value = None
        rows.append(
            _RawRow(
                text=text, points=None, row=row_no, note=note,
                points_raw=points_value, points_parsed=points_value is None,
            )
        )
    return rows, grid


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


@dataclass
class _Paragraph:
    text: str
    bullet: bool = False
    auto_rank: Optional[int] = None
    auto_label: Optional[str] = None
    outline_rank: Optional[int] = None


@dataclass
class _DocxDoc:
    blocks: List[Tuple[str, Any]]  # ("p", _Paragraph) | ("tbl", List[List[List[_Paragraph]]])
    auto_numbered: bool = False


class _Numbering:
    """Word list definitions + running counters (to reconstruct visible labels)."""

    def __init__(self, zf: zipfile.ZipFile):
        self.abstract: Dict[str, Dict[int, Tuple[str, str, int]]] = {}
        self.nums: Dict[str, Tuple[str, Dict[int, int]]] = {}
        self.counters: Dict[str, Dict[int, int]] = {}
        self.overrides_applied: set = set()
        if "word/numbering.xml" not in zf.namelist():
            return
        try:
            root = ET.fromstring(_read_member(zf, "word/numbering.xml"))
        except ET.ParseError:
            return
        for an in root.iter():
            if _local(an.tag) != "abstractNum":
                continue
            levels: Dict[int, Tuple[str, str, int]] = {}
            for lvl in _children(an, "lvl"):
                try:
                    ilvl = int(_attr(lvl, "ilvl") or 0)
                except ValueError:
                    continue
                fmt = _attr(_first(lvl, "numFmt"), "val") or "decimal"
                text = _attr(_first(lvl, "lvlText"), "val") or ""
                try:
                    start = int(_attr(_first(lvl, "start"), "val") or 1)
                except ValueError:
                    start = 1
                levels[ilvl] = (fmt, text, start)
            self.abstract[_attr(an, "abstractNumId") or ""] = levels
        for num in root.iter():
            if _local(num.tag) != "num":
                continue
            abstract_id = _attr(_first(num, "abstractNumId"), "val") or ""
            starts: Dict[int, int] = {}
            for override in _children(num, "lvlOverride"):
                so = _first(override, "startOverride")
                try:
                    starts[int(_attr(override, "ilvl") or 0)] = int(_attr(so, "val") or 1)
                except (TypeError, ValueError):
                    continue
            self.nums[_attr(num, "numId") or ""] = (abstract_id, starts)

    def level(self, num_id: str, ilvl: int) -> Optional[Tuple[str, str, int]]:
        entry = self.nums.get(num_id)
        if not entry:
            return None
        return self.abstract.get(entry[0], {}).get(ilvl)

    def advance(self, num_id: str, ilvl: int) -> str:
        """Increment the counter for (list, level) and render the visible label."""
        abstract_id, starts = self.nums[num_id]
        counters = self.counters.setdefault(abstract_id, {})
        levels = self.abstract.get(abstract_id, {})
        if num_id not in self.overrides_applied:
            self.overrides_applied.add(num_id)
            for lvl, start in starts.items():
                counters[lvl] = start - 1
        start = levels.get(ilvl, ("decimal", "", 1))[2]
        counters[ilvl] = counters.get(ilvl, start - 1) + 1
        for deeper in [lvl for lvl in counters if lvl > ilvl]:
            counters[deeper] = levels.get(deeper, ("decimal", "", 1))[2] - 1
        fmt, text, _start = levels.get(ilvl, ("decimal", "%1.", 1))

        def render(match: re.Match) -> str:
            lvl = int(match.group(1)) - 1
            value = counters.get(lvl)
            if value is None or value <= 0:
                value = levels.get(lvl, ("decimal", "", 1))[2]
            lvl_fmt = levels.get(lvl, (fmt, "", 1))[0]
            if lvl_fmt == "upperLetter":
                return _letters(value, True)
            if lvl_fmt == "lowerLetter":
                return _letters(value, False)
            if lvl_fmt == "upperRoman":
                return _to_roman(value)
            if lvl_fmt == "lowerRoman":
                return _to_roman(value).lower()
            return str(value)

        return re.sub(r"%(\d)", render, text).strip()


class _Styles:
    def __init__(self, zf: zipfile.ZipFile):
        self.styles: Dict[str, Tuple[Optional[str], Optional[str], Optional[int], Optional[int]]] = {}
        if "word/styles.xml" not in zf.namelist():
            return
        try:
            root = ET.fromstring(_read_member(zf, "word/styles.xml"))
        except ET.ParseError:
            return
        for style in root.iter():
            if _local(style.tag) != "style":
                continue
            style_id = _attr(style, "styleId") or ""
            based_on = _attr(_first(style, "basedOn"), "val")
            ppr = _first(style, "pPr")
            num_id = None
            ilvl = None
            outline = None
            if ppr is not None:
                numpr = _first(ppr, "numPr")
                if numpr is not None:
                    num_id = _attr(_first(numpr, "numId"), "val")
                    ilvl_val = _attr(_first(numpr, "ilvl"), "val")
                    ilvl = int(ilvl_val) if ilvl_val and ilvl_val.isdigit() else None
                outline_val = _attr(_first(ppr, "outlineLvl"), "val")
                outline = int(outline_val) if outline_val and outline_val.isdigit() else None
            self.styles[style_id] = (based_on, num_id, ilvl, outline)

    def resolve(self, style_id: Optional[str]) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """``(num_id, ilvl, outline_level)`` through the basedOn chain (nearest wins)."""
        num_id = ilvl = outline = None
        seen: set = set()
        while style_id and style_id not in seen and style_id in self.styles:
            seen.add(style_id)
            based_on, s_num, s_ilvl, s_outline = self.styles[style_id]
            if num_id is None and s_num is not None:
                num_id = s_num
            if ilvl is None and s_ilvl is not None:
                ilvl = s_ilvl
            if outline is None and s_outline is not None:
                outline = s_outline
            style_id = based_on
        return num_id, ilvl, outline


def _paragraph_text(p: ET.Element) -> str:
    parts: List[str] = []
    for el in p.iter():
        name = _local(el.tag)
        if name == "t":
            parts.append(el.text or "")
        elif name == "tab":
            parts.append("\t")
        elif name in ("br", "cr"):
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _read_docx(data: bytes) -> _DocxDoc:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise RubricImportError("corrupt_file", "Die DOCX-Datei enthält kein Dokument.")
            root = ET.fromstring(_read_member(zf, "word/document.xml"))
            numbering = _Numbering(zf)
            styles = _Styles(zf)
    except RubricImportError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        raise RubricImportError("corrupt_file", "Die DOCX-Datei konnte nicht gelesen werden.") from exc

    body = next((el for el in root.iter() if _local(el.tag) == "body"), None)
    if body is None:
        raise RubricImportError("corrupt_file", "Die DOCX-Datei enthält keinen Dokumentkörper.")

    doc = _DocxDoc(blocks=[])
    paragraph_count = 0

    def make_paragraph(p: ET.Element) -> _Paragraph:
        nonlocal paragraph_count
        paragraph_count += 1
        if paragraph_count > MAX_RAW_ROWS * 4:
            raise RubricImportError("too_many_rows", f"Das Dokument hat zu viele Absätze (> {MAX_RAW_ROWS * 4}).")
        text = _paragraph_text(p)
        ppr = _first(p, "pPr")
        style_id = _attr(_first(ppr, "pStyle"), "val")
        num_id = None
        ilvl = None
        numpr = _first(ppr, "numPr")
        if numpr is not None:
            num_id = _attr(_first(numpr, "numId"), "val")
            ilvl_val = _attr(_first(numpr, "ilvl"), "val")
            ilvl = int(ilvl_val) if ilvl_val and ilvl_val.isdigit() else None
        s_num, s_ilvl, outline = styles.resolve(style_id)
        if num_id is None:
            num_id = s_num
        if ilvl is None:
            ilvl = s_ilvl if s_ilvl is not None else 0
        para = _Paragraph(text=text)
        if outline is not None:
            para.outline_rank = 1 + outline
        if num_id and num_id != "0":
            level = numbering.level(num_id, ilvl)
            if level is not None:
                if level[0] == "bullet":
                    para.bullet = True
                else:
                    para.auto_label = numbering.advance(num_id, ilvl)
                    para.auto_rank = 1 + ilvl
                    doc.auto_numbered = True
        return para

    def walk_cell(tc: ET.Element) -> List[_Paragraph]:
        return [make_paragraph(p) for p in _children(tc, "p")]

    for block in body:
        name = _local(block.tag)
        if name == "p":
            doc.blocks.append(("p", make_paragraph(block)))
        elif name == "tbl":
            rows: List[List[List[_Paragraph]]] = []
            for tr in _children(block, "tr"):
                rows.append([walk_cell(tc) for tc in _children(tr, "tc")])
                if len(rows) > MAX_RAW_ROWS:
                    raise RubricImportError("too_many_rows", f"Die Tabelle hat mehr als {MAX_RAW_ROWS} Zeilen.")
            doc.blocks.append(("tbl", rows))
        elif name == "sdt":
            content = _first(block, "sdtContent")
            if content is not None:
                for inner in content:
                    if _local(inner.tag) == "p":
                        doc.blocks.append(("p", make_paragraph(inner)))
    return doc


def _table_grid(rows: List[List[List[_Paragraph]]]) -> List[Tuple[int, Dict[int, Any]]]:
    grid: List[Tuple[int, Dict[int, Any]]] = []
    for index, row in enumerate(rows, start=1):
        cells: Dict[int, Any] = {}
        for col, paragraphs in enumerate(row):
            text = " ".join(p.text for p in paragraphs if p.text).strip()
            if text:
                number = _parse_number(text) if _POINTS_RE.match(text) else None
                cells[col] = number if number is not None else text
        grid.append((index, cells))
    return grid


def _is_main_table(rows: List[List[List[_Paragraph]]]) -> bool:
    if len(rows) < 3 or max((len(r) for r in rows), default=0) < 2:
        return False
    for row in rows:
        if len(row) >= 2 and any(_POINTS_RE.match(p.text) for p in row[1] if p.text):
            return True
    return False


def _align_cell(
    text_paras: List[_Paragraph],
    points_paras: List[_Paragraph],
    row_no: int,
    warnings: _Warnings,
) -> List[_RawRow]:
    """Pair the text-cell paragraphs with the BE-cell paragraphs of one table row."""
    values: List[Tuple[Optional[float], Optional[str]]] = []
    for p in points_paras:
        values.append(_parse_points_cell(p.text or None, row_no, warnings))
    notes = [raw for pts, raw in values if pts is None and raw and _NOTE_RE.search(raw)]

    def make_row(p: _Paragraph, points: Optional[float], raw: Optional[str]) -> _RawRow:
        return _RawRow(
            text=p.text,
            points=points,
            row=row_no,
            points_text=raw,
            bullet=p.bullet,
            auto_rank=p.auto_rank if p.auto_rank is not None else p.outline_rank,
            auto_label=p.auto_label if p.auto_rank is not None else ("" if p.outline_rank is not None else None),
        )

    rows: List[_RawRow] = []
    unassigned: List[str] = []

    if len(text_paras) == len(points_paras):
        for p, (pts, raw) in zip(text_paras, values):
            if not p.text:
                if pts is not None:
                    unassigned.append(format_points(pts))
                continue
            rows.append(make_row(p, pts, raw))
    else:
        texts = [p for p in text_paras if p.text]
        vals = [(pts, raw) for pts, raw in values if pts is not None]
        if len(texts) == len(vals):
            for p, (pts, raw) in zip(texts, vals):
                rows.append(make_row(p, pts, raw))
        elif len(vals) == 1 and texts:
            rows.append(make_row(texts[0], *vals[0]))
            rows.extend(make_row(p, None, None) for p in texts[1:])
            # Heading + hint bullets with one value is the normal layout; only
            # flag the guess when a non-bullet sibling could own the value.
            if any(not p.bullet and not _BULLET_RE.match(p.text) for p in texts[1:]):
                warnings.add(
                    "alignment_uncertain",
                    f"Zeile {row_no}: ein Punktwert ({format_points(vals[0][0])} BE) für {len(texts)} Textzeilen; "
                    f"er wurde der Überschrift „{texts[0].text[:40]}“ zugeordnet.",
                    row=row_no,
                )
        elif texts and len(vals) == len(texts) - 1:
            rows.append(make_row(texts[0], None, None))
            for p, (pts, raw) in zip(texts[1:], vals):
                rows.append(make_row(p, pts, raw))
        else:
            for index, p in enumerate(texts):
                pts, raw = vals[index] if index < len(vals) else (None, None)
                rows.append(make_row(p, pts, raw))
            unassigned.extend(format_points(pts) for pts, _raw in vals[len(texts):])
            if texts and vals:
                warnings.add(
                    "alignment_uncertain",
                    f"Zeile {row_no}: {len(vals)} Punktwerte stehen {len(texts)} Textzeilen gegenüber; "
                    "die Zuordnung wurde der Reihe nach geraten.",
                    row=row_no,
                )
    if unassigned:
        warnings.add(
            "alignment_uncertain",
            f"Zeile {row_no}: Punktwerte ohne zugeordnete Textzeile: {', '.join(unassigned)} BE.",
            row=row_no,
        )
    if notes and rows:
        target = next((r for r in reversed(rows) if not r.bullet), rows[0])
        target.note = _NOTE_RE.search(notes[0]).group(1).strip()
    return rows


def _rows_from_docx(doc: _DocxDoc, warnings: _Warnings) -> Tuple[List[_RawRow], List[Tuple[int, Dict[int, Any]]]]:
    main_index = next(
        (i for i, (kind, payload) in enumerate(doc.blocks) if kind == "tbl" and _is_main_table(payload)),
        None,
    )
    if main_index is None:
        raise RubricImportError(
            "no_table_found",
            "Im Dokument wurde keine Tabelle mit Gliederungspunkten und Punktwerten gefunden.",
        )
    table_rows: List[List[List[_Paragraph]]] = doc.blocks[main_index][1]
    text_col, points_col = _detect_columns(_table_grid(table_rows))
    if points_col is None:
        points_col = text_col + 1

    rows: List[_RawRow] = []
    # Paragraphs before the table feed the title candidate.
    for kind, payload in doc.blocks[:main_index]:
        if kind == "p" and payload.text:
            rows.append(_RawRow(text=payload.text, points=None, row=0, bullet=payload.bullet))
    for row_no, cells in enumerate(table_rows, start=1):
        if len(cells) <= text_col:
            continue
        if len(cells) <= points_col:
            text_paras = [p for p in cells[text_col] if p.text]
            if text_paras:
                warnings.add(
                    "merged_label_cell",
                    f"Zeile {row_no}: verbundene Zelle ohne Punktespalte; als Überschrift übernommen.",
                    row=row_no,
                )
                rows.extend(
                    _RawRow(text=p.text, points=None, row=row_no, bullet=p.bullet,
                            auto_rank=p.auto_rank if p.auto_rank is not None else p.outline_rank,
                            auto_label=p.auto_label)
                    for p in text_paras
                )
            continue
        rows.extend(_align_cell(cells[text_col], cells[points_col], row_no, warnings))
    # Paragraphs and tables after the main table: scale trigger, scale table,
    # rounding sentence, trailer.
    scale_grid: List[Tuple[int, Dict[int, Any]]] = []
    for kind, payload in doc.blocks[main_index + 1:]:
        if kind == "p":
            if payload.text:
                scale_grid.append((len(scale_grid) + 1, {0: payload.text}))
                rows.append(_RawRow(text=payload.text, points=None, row=0, bullet=payload.bullet))
        else:
            for _row_no, cells in _table_grid(payload):
                scale_grid.append((len(scale_grid) + 1, cells))
    if doc.auto_numbered:
        warnings.add(
            "auto_numbering",
            "Die Gliederungsbezeichnungen (A., I., 1., a) …) wurden aus der automatischen "
            "Word-Nummerierung rekonstruiert; bitte prüfen.",
        )
    return rows, scale_grid


# ---------------------------------------------------------------------------
# Row classification → outline
# ---------------------------------------------------------------------------


class _LabelContext:
    def __init__(self):
        self.last_capital: Optional[str] = None
        self.last_roman: Optional[int] = None

    def note(self, rank: int, label: str) -> None:
        if rank == 0:
            self.last_capital = None
            self.last_roman = None
        elif rank == 1:
            self.last_capital = label.rstrip(".")
            self.last_roman = None
        elif rank == 2:
            self.last_roman = _roman_value(label.rstrip("."))


def _classify_label(text: str, ctx: _LabelContext, row: int, warnings: _Warnings) -> Optional[Tuple[int, str, str]]:
    """``(rank, label, rest)`` when ``text`` starts with an outline label."""
    match = _FRAGE_RE.match(text)
    if match:
        label = f"{match.group(1)} {match.group(2)}"
        return 0, "", (label if not match.group(3).strip() else f"{label}: {match.group(3).strip()}")
    match = _ROMAN_RE.match(text)
    if match:
        letters = match.group(1)
        if len(letters) > 1 or letters == "I":
            return 2, f"{letters}.", match.group(2)
        # Single V or X: roman iff it continues the roman sequence, capital
        # iff it continues the capital sequence, else roman.
        value = _roman_value(letters)
        if ctx.last_roman is not None and ctx.last_roman + 1 == value:
            return 2, f"{letters}.", match.group(2)
        if ctx.last_capital is not None and len(ctx.last_capital) == 1 and ord(ctx.last_capital) + 1 == ord(letters):
            return 1, f"{letters}.", match.group(2)
        warnings.add(
            "ambiguous_label",
            f"Zeile {row}: „{letters}.“ wurde als römische Ziffer gelesen (könnte auch ein Abschnittsbuchstabe sein).",
            row=row,
        )
        return 2, f"{letters}.", match.group(2)
    for rank, pattern in (
        (1, _CAPITAL_RE),
        (3, _DECIMAL_RE),
        (5, _DOUBLE_LOWER_RE),
        (4, _LOWER_RE),
        (6, _PAREN_DECIMAL_RE),
        (7, _PAREN_LOWER_RE),
    ):
        match = pattern.match(text)
        if match:
            if rank == 5:
                label = f"{match.group(1)}{match.group(1)})"
            elif rank == 1 or rank == 3:
                label = f"{match.group(1)}."
            elif rank in (6, 7):
                label = f"({match.group(1)})"
            else:
                label = f"{match.group(1)})"
            return rank, label, match.group(2)
    return None


def _extract_note(text: str) -> Tuple[str, Optional[str], Optional[float]]:
    match = _NOTE_RE.search(text)
    if not match:
        return text, None, None
    note = match.group(1).strip()
    value_match = _NOTE_VALUE_RE.search(note)
    declared = _parse_number(value_match.group(1)) if value_match else None
    cleaned = (text[: match.start()] + " " + text[match.end():]).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-–")
    return cleaned, note, declared


def _extract_emphasis(text: str) -> Tuple[str, Optional[str]]:
    match = _EMPHASIS_RE.search(text)
    if not match:
        return text, None
    cleaned = re.sub(r"\s+", " ", text[: match.start()] + " " + text[match.end():]).strip()
    return cleaned, match.group(0).strip("() ").strip()


def _subtree_points(nodes: List[_Node], index: int) -> float:
    node = nodes[index]
    doubled = int(round((node.max_score or 0) * 2))
    for later in nodes[index + 1:]:
        if later.level <= node.level:
            break
        doubled += int(round((later.max_score or 0) * 2))
    return doubled / 2


def _build_outline(rows: List[_RawRow], warnings: _Warnings) -> Tuple[List[_Node], Optional[float], Optional[str], Optional[str]]:
    """``(nodes, declared_total, title_candidate, rounding)``."""
    nodes: List[_Node] = []
    stack: List[_Node] = []
    last_node: Optional[_Node] = None
    ctx = _LabelContext()
    declared_total: Optional[float] = None
    title_candidate: Optional[str] = None
    rounding: Optional[str] = None
    stopped = False

    for raw in rows:
        text = raw.text.strip()
        rounding_match = _ROUNDING_RE.search(text)
        if rounding_match:
            word = rounding_match.group(1).lower()
            rounding = {"abgerundet": "floor", "aufgerundet": "ceil"}.get(word, "nearest")
            continue
        if _SCALE_TRIGGER_RE.match(text):
            stopped = True
            continue
        if stopped:
            continue
        if not raw.points_parsed:
            raw.points, raw.points_text = _parse_points_cell(raw.points_raw, raw.row, warnings)
            raw.points_parsed = True
        if not text and raw.points is None:
            continue
        if not text:
            warnings.add(
                "points_invalid",
                f"Zeile {raw.row}: Punktwert {format_points(raw.points)} ohne Text wurde ignoriert.",
                row=raw.row,
            )
            continue
        if _HEADER_CELL_RE.match(text):
            continue
        if _TOTAL_ROW_RE.match(text):
            declared_total = raw.points
            stopped = True
            continue

        rank: Optional[int] = None
        label = ""
        bullet = raw.bullet
        body = text
        if not bullet:
            marker = _BULLET_RE.match(text)
            if marker:
                bullet = True
                body = marker.group(1).strip()
        if not bullet:
            frage = _FRAGE_RE.match(text)
            if frage:
                rank, label, body = _classify_label(text, ctx, raw.row, warnings)
            elif raw.auto_rank is not None:
                rank, label, body = raw.auto_rank, (raw.auto_label or ""), text
            else:
                classified = _classify_label(text, ctx, raw.row, warnings)
                if classified:
                    rank, label, body = classified
        if rank is None and not bullet and _TRAILER_RE.match(text) and raw.points is None:
            continue

        body, note, declared_subtotal = _extract_note(body)
        body, emphasis_text = _extract_emphasis(body)
        title = body.strip().rstrip(":").strip() or label.strip(".) ") or text
        if raw.note:
            note = raw.note if note is None else f"{note}; {raw.note}"
            if declared_subtotal is None:
                value_match = _NOTE_VALUE_RE.search(raw.note)
                declared_subtotal = _parse_number(value_match.group(1)) if value_match else None

        if rank is not None:
            ctx.note(rank, label)
            while stack and stack[-1].rank >= rank:
                stack.pop()
            parent = stack[-1] if stack else None
            node = _Node(
                kind="step" if raw.points is not None else "section",
                level=parent.level + 1 if parent else 0,
                label=label,
                title=title,
                row=raw.row,
                rank=rank,
                parent=parent,
                note=note,
                max_score=raw.points,
                declared_subtotal=declared_subtotal,
            )
            if parent is not None:
                parent.has_children = True
            nodes.append(node)
            stack.append(node)
            last_node = node
        elif raw.points is not None:
            if bullet or last_node is None or last_node.kind == "section" or last_node.parent is None and not stack:
                parent = stack[-1] if stack else None
                level = parent.level + 1 if parent else 0
            else:
                parent = last_node.parent
                level = last_node.level
            node = _Node(
                kind="step",
                level=level,
                label="",
                title=title,
                row=raw.row,
                rank=(parent.rank + 0.5) if parent else -0.5,
                parent=parent,
                note=note,
                max_score=raw.points,
                declared_subtotal=declared_subtotal,
            )
            if parent is not None:
                parent.has_children = True
            nodes.append(node)
            last_node = node
        else:
            if last_node is None:
                if title_candidate is None and len(text) <= MAX_TITLE_CANDIDATE_LEN and not bullet:
                    title_candidate = text
                continue
            extra = body.strip()
            if last_node.kind == "step":
                if extra:
                    last_node.hints.append(extra)
                if note:
                    # A note-only line ("Insgesamt 4 BE") under a step is kept
                    # as the step's note, not as an empty hint.
                    last_node.note = note if not last_node.note else f"{last_node.note}; {note}"
            else:
                for part in (extra, note):
                    if part:
                        last_node.note = part if not last_node.note else f"{last_node.note}; {part}"
                warnings.add(
                    "note_from_bullet",
                    f"Zeile {raw.row}: „{(extra or note or '')[:60]}“ wurde als Anmerkung zu „{last_node.title[:40]}“ übernommen.",
                    row=raw.row,
                )
        if emphasis_text and nodes:
            target = nodes[-1]
            if target.kind == "step":
                target.emphasis = "schwerpunkt"
            else:
                target.note = emphasis_text if not target.note else f"{target.note}; {emphasis_text}"
    return nodes, declared_total, title_candidate, rounding


def _nodes_to_structure(nodes: List[_Node], warnings: _Warnings) -> Dict[str, Any]:
    if len(nodes) > MAX_NODES:
        raise RubricImportError(
            "too_many_rows", f"Der Bogen hat {len(nodes)} Gliederungspunkte, erlaubt sind {MAX_NODES}."
        )
    out: List[Dict[str, Any]] = []
    for index, node in enumerate(nodes):
        node_id = f"n{index + 1}"
        if node.kind == "section" and not node.has_children:
            warnings.add(
                "empty_section",
                f"„{(node.label + ' ' + node.title).strip()[:60]}“ hat weder Punkte noch Unterpunkte.",
                row=node.row,
                node_id=node_id,
            )
        if node.declared_subtotal is not None:
            actual = _subtree_points(nodes, index)
            if abs(actual - node.declared_subtotal) > 1e-9:
                warnings.add(
                    "subtotal_mismatch",
                    f"„{(node.label + ' ' + node.title).strip()[:60]}“: angegeben {format_points(node.declared_subtotal)} BE, "
                    f"Summe der Schritte {format_points(actual)} BE.",
                    row=node.row,
                    node_id=node_id,
                )
        entry: Dict[str, Any] = {
            "id": node_id,
            "level": node.level,
            "kind": node.kind,
            "label": node.label[:MAX_LABEL_LEN],
            "title": node.title[:MAX_TITLE_LEN],
            "note": (node.note or None) and node.note[:MAX_NOTE_LEN],
        }
        if node.kind == "step":
            hints = [h[:MAX_HINT_LEN] for h in node.hints if h]
            if len(hints) > MAX_HINTS_PER_STEP:
                hints = hints[: MAX_HINTS_PER_STEP - 1] + ["; ".join(hints[MAX_HINTS_PER_STEP - 1:])[:MAX_HINT_LEN]]
            entry.update(
                {
                    "key": None,
                    "max_score": node.max_score,
                    "emphasis": node.emphasis,
                    "hints": hints,
                }
            )
        out.append(entry)
    return {"version": 1, "nodes": out}


# ---------------------------------------------------------------------------
# Notenschlüssel
# ---------------------------------------------------------------------------


def _detect_grade_scale(
    grid: List[Tuple[int, Dict[int, Any]]],
    rounding: Optional[str],
    computed_total: float,
    warnings: _Warnings,
) -> Optional[Dict[str, Any]]:
    ranges: List[Tuple[int, int, float, float]] = []  # (row, col, low, high)
    grades: Dict[Tuple[int, int], int] = {}
    seen_trigger = False
    for row_no, cells in grid:
        texts = [str(v) for v in cells.values() if isinstance(v, str)]
        if any(_SCALE_TRIGGER_RE.match(t.strip()) for t in texts):
            seen_trigger = True
            continue
        for col, value in cells.items():
            if isinstance(value, str):
                match = _RANGE_RE.match(value)
                if match:
                    low = _parse_number(match.group(1))
                    high = _parse_number(match.group(2))
                    if low is not None and high is not None:
                        ranges.append((row_no, col, low, high))
                    continue
                gmatch = _GRADE_RE.match(value)
                if gmatch and 0 <= int(gmatch.group(1)) <= GRADE_COUNT:
                    grades[(row_no, col)] = int(gmatch.group(1))
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if float(value).is_integer() and 0 <= int(value) <= GRADE_COUNT:
                    grades[(row_no, col)] = int(value)
    if not ranges:
        if seen_trigger:
            warnings.add(
                "grade_scale_unparsed",
                "Ein Notenschlüssel wurde angekündigt, aber keine BE-Bereiche gefunden; es gilt der Standardschlüssel.",
            )
        return None

    pairs: Dict[int, List[Tuple[float, float]]] = {}

    def pair_up(find_grade) -> Dict[int, List[Tuple[float, float]]]:
        found: Dict[int, List[Tuple[float, float]]] = {}
        for row_no, col, low, high in ranges:
            grade = find_grade(row_no, col)
            if grade is not None:
                found.setdefault(grade, []).append((low, high))
        return found

    grade_rows = sorted({r for r, _c in grades})
    grade_cols = sorted({c for _r, c in grades})

    def by_column(row_no, col):
        for r in grade_rows:
            if r > row_no and (r, col) in grades:
                return grades[(r, col)]
        return None

    def by_row(row_no, col):
        for c in grade_cols:
            if c > col and (row_no, c) in grades:
                return grades[(row_no, c)]
        return None

    pairs = pair_up(by_column)
    if len(pairs) < GRADE_COUNT + 1:
        alt = pair_up(by_row)
        if len(alt) > len(pairs):
            pairs = alt

    complete = all(g in pairs and len(pairs[g]) == 1 for g in range(GRADE_COUNT + 1))
    lows = [pairs[g][0][0] for g in range(GRADE_COUNT + 1)] if complete else []
    if not complete or any(lows[i] >= lows[i + 1] for i in range(len(lows) - 1)):
        warnings.add(
            "grade_scale_unparsed",
            "Der Notenschlüssel konnte nicht vollständig gelesen werden (0 bis 18 Notenpunkte mit "
            "aufsteigenden BE-Bereichen erwartet); es gilt der Standardschlüssel.",
        )
        return None
    max_points = pairs[GRADE_COUNT][0][1]
    scale: Dict[str, Any] = {
        "unit": "BE",
        "thresholds": [int(v) if float(v).is_integer() else v for v in lows[1:]],
        "rounding": rounding or "floor",
        "pass_grade": 4,
        "max_points": int(max_points) if float(max_points).is_integer() else max_points,
    }
    if rounding is None:
        warnings.add(
            "rounding_assumed",
            "Keine Rundungsregel gefunden; halbe BE werden abgerundet (Standard).",
        )
    if abs(max_points - computed_total) > 1e-9:
        warnings.add(
            "grade_scale_total_mismatch",
            f"Der Notenschlüssel endet bei {format_points(max_points)} BE, die Schritte summieren sich "
            f"auf {format_points(computed_total)} BE.",
        )
    return scale


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _grade_scale_as_percent(
    scale: Optional[Dict[str, Any]], total_points: Any
) -> Optional[Dict[str, Any]]:
    """A ``unit: "percent"`` twin of an absolute (BE) Notenschlüssel.

    Each threshold becomes ``round(t / total_points * 100, 4)``. Returns
    ``None`` when there is no scale or no usable total — the caller then
    simply has nothing to offer as the exam key and the default applies.
    """
    if not isinstance(scale, dict):
        return None
    thresholds = scale.get("thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        return None
    try:
        total = float(total_points)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    out: Dict[str, Any] = {
        "unit": "percent",
        "preset": "custom",
        "thresholds": [round(float(t) / total * 100, 4) for t in thresholds],
        "rounding": scale.get("rounding") or "floor",
        "pass_grade": scale.get("pass_grade", 4),
    }
    return out


def parse_rubric_file(filename: str, data: bytes) -> Dict[str, Any]:
    """Parse an XLSX or DOCX Korrekturbogen into the rubric contract.

    Returns ``{"title", "structure", "criteria", "total_points", "grade_scale",
    "warnings", "source_format"}``; raises :class:`RubricImportError` for files
    that cannot be used at all.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise RubricImportError(
            "unsupported_type",
            "Bitte eine Excel-Datei (.xlsx) oder ein Word-Dokument (.docx) hochladen.",
        )
    if not data:
        raise RubricImportError("corrupt_file", "Die Datei ist leer.")

    warnings = _Warnings()
    if ext == ".xlsx":
        rows, scale_grid = _rows_from_xlsx(_read_xlsx_grid(data), warnings)
        source_format = "xlsx"
    else:
        rows, scale_grid = _rows_from_docx(_read_docx(data), warnings)
        source_format = "docx"

    nodes, declared_total, title_candidate, rounding = _build_outline(rows, warnings)
    if not any(n.kind == "step" for n in nodes):
        raise RubricImportError(
            "no_scored_steps",
            "Keine Prüfungsschritte mit Punktwerten gefunden. Der Bogen braucht eine Spalte mit den maximalen BE je Schritt.",
            warnings=list(warnings),
        )
    structure = normalize_structure(_nodes_to_structure(nodes, warnings))
    errors = validate_structure(structure)
    if errors:
        raise RubricImportError(
            "no_scored_steps",
            "Der Bogen konnte nicht in eine gültige Gliederung überführt werden: " + "; ".join(errors[:3]),
            warnings=list(warnings),
        )
    total = total_points_from_structure(structure)
    if declared_total is not None and abs(float(total) - declared_total) > 1e-9:
        warnings.add(
            "total_mismatch",
            f"Gesamtsumme laut Bogen {format_points(declared_total)} BE, Summe der Schritte {format_points(total)} BE.",
        )

    grade_scale = _detect_grade_scale(scale_grid, rounding, float(total), warnings)
    if grade_scale is not None and validate_grade_scale(grade_scale, total):
        # Thresholds above the computed total etc. — keep the default instead.
        warnings.add(
            "grade_scale_unparsed",
            "Der gelesene Notenschlüssel passt nicht zur Gesamtsumme des Bogens; es gilt der Standardschlüssel.",
        )
        grade_scale = None

    title = (title_candidate or "").strip()
    if not title:
        title = os.path.splitext(os.path.basename(filename))[0].strip() or "Bewertungsbogen"
        warnings.add(
            "title_from_filename",
            "Kein Titel im Dokument gefunden; der Dateiname wurde als Titel übernommen.",
        )

    return {
        "title": title[:255],
        "structure": structure,
        "criteria": criteria_from_structure(structure),
        "total_points": total,
        "grade_scale": grade_scale,
        # The same key expressed in PERCENT of the sheet total, so the client
        # can offer it as the EXAM's Notenschlüssel (the key is
        # assessment policy on the exam, not content on the sheet, and a
        # percent key survives a later change of the sheet's point total).
        # ``None`` when the file carried no readable key.
        "grade_scale_percent": _grade_scale_as_percent(grade_scale, total),
        "warnings": list(warnings),
        "source_format": source_format,
    }
