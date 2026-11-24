"""Read an uploaded spreadsheet into rows of cells: XLSX, CSV and TSV.

Every table a person uploads (a grading sheet, a points table, a list of
people) arrives as one of these formats, and every reader needs the same
things: all worksheets of a workbook, Excel's BOM and ``;`` delimiter in a
CSV, the row numbers a person sees in their program (so a message can point
at cell ``C7``), and bounded work on a hostile file. This module does that
once; what the cells mean is up to the caller.

The workbook is read with the stdlib only (``zipfile`` and ``xml.etree``,
see :mod:`ooxml`): there is no XLSX library in the images, and a new
dependency could silently be missing from a long-lived test image.

Shape of the result (:func:`read_table`):

- ``TableFile.sheets``: the readable worksheets in workbook order (a CSV or
  TSV file is one sheet named after the file). The first worksheet must be
  readable, otherwise the file is refused.
- ``TableFile.skipped_sheets``: further worksheets that could not be read,
  with the reason (:data:`ERROR_CODES`), so a caller can warn about them.
- ``Sheet.rows``: one :class:`Row` per row, in order, ``Row.number`` being
  the 1-based row number (the XLSX row reference, or the CSV record number).
  ``Row.cells`` maps the 0-based column index to the value; blank cells are
  left out. Values are strings as written, except that an XLSX number cell
  is a ``float`` (dates and times are numbers in XLSX too) and an XLSX
  boolean is ``"1"`` or ``"0"``. CSV cells are always strings.

Errors are :class:`TableReadError` with a ``code`` from :data:`ERROR_CODES`;
the English ``message`` is for logs, callers map the code to their own copy.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from ooxml import MemberTooLarge, attr, children, first, local, read_member

#: File extensions :func:`read_table` accepts, with the format each one is.
TABLE_FORMATS = {".xlsx": "xlsx", ".csv": "csv", ".tsv": "tsv"}

#: Default cap on the rows of one worksheet (XLSX row elements, CSV records).
DEFAULT_MAX_ROWS = 10_000

#: Text files are decoded through this list in order. ``utf-8-sig`` first so a
#: BOM (Excel's "CSV UTF-8" export always writes one) does not end up in the
#: first cell; cp1252 last for files saved by older Western European Office
#: builds.
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")

#: Delimiters a CSV file is sniffed for (German and French exports use ";").
CSV_DELIMITERS = ",;\t"

ERROR_CODES = (
    "unsupported_type",  # not one of TABLE_FORMATS
    "empty_file",  # zero bytes
    "unreadable",  # not a valid workbook / CSV at all
    "member_too_large",  # a part of the workbook exceeds ooxml.MAX_MEMBER_BYTES
    "no_worksheet",  # the workbook lists no worksheet
    "worksheet_missing",  # a listed worksheet is not in the file
    "too_many_rows",  # a worksheet has more rows than the cap
)


class TableReadError(Exception):
    """A file that cannot be read as a table (``code`` in :data:`ERROR_CODES`)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class Row(NamedTuple):
    """One row: its 1-based number and its non-blank cells by column index."""

    number: int
    cells: Dict[int, Any]


@dataclass(frozen=True)
class Sheet:
    name: str
    rows: List[Row]


@dataclass(frozen=True)
class SkippedSheet:
    name: str
    code: str


@dataclass(frozen=True)
class TableFile:
    format: str
    sheets: List[Sheet]
    skipped_sheets: List[SkippedSheet] = field(default_factory=list)


def table_format(filename: str) -> Optional[str]:
    """The format :func:`read_table` would read ``filename`` as, or None."""
    return TABLE_FORMATS.get(os.path.splitext(filename or "")[1].lower())


def read_table(filename: str, data: bytes, *, max_rows: int = DEFAULT_MAX_ROWS) -> TableFile:
    """Read ``data`` as the table format its ``filename`` extension names."""
    fmt = table_format(filename)
    if fmt is None:
        raise TableReadError(
            "unsupported_type",
            "expected one of " + ", ".join(sorted(TABLE_FORMATS)),
        )
    if not data:
        raise TableReadError("empty_file", "the file is empty")
    if fmt == "xlsx":
        sheets, skipped = read_xlsx_sheets(data, max_rows=max_rows)
        return TableFile(format=fmt, sheets=sheets, skipped_sheets=skipped)
    name = os.path.splitext(os.path.basename(filename))[0] or fmt
    rows = read_delimited(data, delimiter="\t" if fmt == "tsv" else None, max_rows=max_rows)
    return TableFile(format=fmt, sheets=[Sheet(name=name, rows=rows)])


# ---------------------------------------------------------------------------
# Cell references
# ---------------------------------------------------------------------------


def column_letter(index: int) -> str:
    """``0`` -> ``A``, ``26`` -> ``AA``."""
    letters, n = "", index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def column_index(ref: str) -> int:
    """The 0-based column of a cell reference or column name (``C7`` -> 2)."""
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(index - 1, 0)


def cell_ref(row_number: int, col: int) -> str:
    """The reference a person sees for a cell (row 7, column 2 -> ``C7``)."""
    return f"{column_letter(col)}{row_number}"


# ---------------------------------------------------------------------------
# Text: CSV and TSV
# ---------------------------------------------------------------------------


def decode_text(data: bytes) -> str:
    """Decode an uploaded text file through :data:`TEXT_ENCODINGS`.

    Never fails: a stray byte that no encoding takes is replaced.
    """
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def sniff_delimiter(sample: str) -> str:
    """The delimiter of a CSV sample, one of :data:`CSV_DELIMITERS`."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        # Sniffing fails on a single-column file; count instead.
        delimiter = max(CSV_DELIMITERS, key=lambda d: sample.count(d))
        return delimiter if sample.count(delimiter) else ","


def read_delimited(
    data: bytes, *, delimiter: Optional[str] = None, max_rows: int = DEFAULT_MAX_ROWS
) -> List[Row]:
    """CSV or TSV bytes -> rows. ``delimiter=None`` sniffs it."""
    text = decode_text(data)
    if delimiter is None:
        delimiter = sniff_delimiter(text[:4096])
    rows: List[Row] = []
    try:
        for number, record in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
            if number > max_rows:
                raise TableReadError("too_many_rows", f"more than {max_rows} rows")
            rows.append(
                Row(number, {col: value for col, value in enumerate(record) if value.strip()})
            )
    except csv.Error as exc:
        raise TableReadError("unreadable", f"not a readable CSV file: {exc}") from exc
    return rows


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def read_xlsx_sheets(
    data: bytes, *, max_rows: int = DEFAULT_MAX_ROWS
) -> Tuple[List[Sheet], List[SkippedSheet]]:
    """Every worksheet of a workbook, the first one first.

    The first worksheet must be readable; a further one that is not (missing
    part, too large, too many rows, broken XML) is returned as skipped, so
    one bad extra sheet never refuses the file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            shared = _shared_strings(zf)
            paths = _sheet_paths(zf)
            names = set(zf.namelist())
            first_name, first_path = paths[0]
            if first_path not in names:
                raise TableReadError("worksheet_missing", f"worksheet {first_name!r} is missing")
            sheets = [Sheet(first_name, _sheet_rows(zf, first_path, shared, max_rows))]
            skipped: List[SkippedSheet] = []
            for name, path in paths[1:]:
                if path not in names:
                    skipped.append(SkippedSheet(name, "worksheet_missing"))
                    continue
                try:
                    sheets.append(Sheet(name, _sheet_rows(zf, path, shared, max_rows)))
                except TableReadError as exc:
                    skipped.append(SkippedSheet(name, exc.code))
                except MemberTooLarge:
                    skipped.append(SkippedSheet(name, "member_too_large"))
                except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError):
                    skipped.append(SkippedSheet(name, "unreadable"))
            return sheets, skipped
    except TableReadError:
        raise
    except MemberTooLarge as exc:
        raise TableReadError("member_too_large", str(exc)) from exc
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        raise TableReadError("unreadable", "not a readable XLSX workbook") from exc


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(read_member(zf, "xl/sharedStrings.xml"))
    out: List[str] = []
    for si in root.iter():
        if local(si.tag) != "si":
            continue
        parts: List[str] = []
        for el in si.iter():
            # Phonetic guide runs (``rPh``) are not part of the cell text.
            if local(el.tag) == "rPh":
                continue
            if local(el.tag) == "t":
                parts.append(el.text or "")
        out.append("".join(parts))
    return out


def _sheet_paths(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    """``[(sheet name, member path)]`` of every listed worksheet, in workbook order."""
    workbook = ET.fromstring(read_member(zf, "xl/workbook.xml"))
    sheets = [el for el in workbook.iter() if local(el.tag) == "sheet"]
    if not sheets:
        raise TableReadError("no_worksheet", "the workbook lists no worksheet")
    rels: Dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        root = ET.fromstring(read_member(zf, "xl/_rels/workbook.xml.rels"))
        for rel in root.iter():
            if local(rel.tag) == "Relationship" and rel.attrib.get("Id"):
                rels[rel.attrib["Id"]] = rel.attrib.get("Target") or ""
    out: List[Tuple[str, str]] = []
    for index, sheet in enumerate(sheets, start=1):
        rid = attr(sheet, "id")
        target = rels.get(rid or "") or f"worksheets/sheet{index}.xml"
        path = target.lstrip("/") if target.startswith("/") else os.path.normpath(f"xl/{target}")
        out.append((sheet.attrib.get("name") or f"#{index}", path.replace("\\", "/")))
    return out


def _sheet_rows(zf: zipfile.ZipFile, path: str, shared: List[str], max_rows: int) -> List[Row]:
    """The rows of one worksheet part."""
    sheet = ET.fromstring(read_member(zf, path))
    rows: List[Row] = []
    next_row = 1
    for row_el in sheet.iter():
        if local(row_el.tag) != "row":
            continue
        try:
            row_no = int(row_el.attrib.get("r") or next_row)
        except ValueError:
            row_no = next_row
        next_row = row_no + 1
        cells: Dict[int, Any] = {}
        next_col = 0
        for cell in children(row_el, "c"):
            ref = cell.attrib.get("r")
            col = column_index(ref) if ref else next_col
            next_col = col + 1
            value = _cell_value(cell, shared)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            cells[col] = value
        rows.append(Row(row_no, cells))
        if len(rows) > max_rows:
            raise TableReadError("too_many_rows", f"more than {max_rows} rows")
    return rows


def _cell_value(cell: ET.Element, shared: List[str]) -> Any:
    kind = cell.attrib.get("t")
    v_el = first(cell, "v")
    if kind == "s":
        try:
            return shared[int(v_el.text)] if v_el is not None and v_el.text else ""
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        is_el = first(cell, "is")
        return "".join(
            (t.text or "") for t in (is_el.iter() if is_el is not None else []) if local(t.tag) == "t"
        )
    if kind == "str":
        return v_el.text or "" if v_el is not None else ""
    if kind == "b":
        return "1" if v_el is not None and v_el.text == "1" else "0"
    if kind == "e":
        # An error value (#DIV/0!, #REF!) is no value.
        return None
    if v_el is not None and v_el.text not in (None, ""):
        try:
            return float(v_el.text)
        except ValueError:
            return v_el.text
    return None
