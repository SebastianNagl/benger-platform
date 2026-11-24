"""The shared table reader: XLSX (every worksheet), CSV and TSV into rows.

Workbooks are built in-test with the stdlib zip builder of the grading sheet
importer's fixtures, so the reader is checked against the same files that
importer reads.
"""

from __future__ import annotations

import io
import zipfile

import pytest

import ooxml
from table_grid import (
    ERROR_CODES,
    Row,
    SkippedSheet,
    TableReadError,
    cell_ref,
    column_index,
    column_letter,
    decode_text,
    read_table,
    sniff_delimiter,
    table_format,
)
from tests.fixtures.rubric_files import Formula, make_xlsx


def _cells(sheet):
    return [(row.number, row.cells) for row in sheet.rows]


class TestXlsx:
    def test_reads_every_worksheet_in_order_with_row_numbers(self):
        data = make_xlsx(
            [{"A": "Name", "B": "Punkte"}, None, {"A": "Ada", "B": 7.5}],
            extra_sheets=[("Aufgabe 2", [{"A": "Name"}, {"A": "Bea", "C": 3}])],
        )
        table = read_table("punkte.xlsx", data)
        assert table.format == "xlsx"
        assert [s.name for s in table.sheets] == ["Tabelle1", "Aufgabe 2"]
        # Row 2 is empty in the file and therefore not written: the numbers
        # are the ones the person sees, not positions in a list.
        assert _cells(table.sheets[0]) == [(1, {0: "Name", 1: "Punkte"}), (3, {0: "Ada", 1: 7.5})]
        assert _cells(table.sheets[1]) == [(1, {0: "Name"}), (2, {0: "Bea", 2: 3.0})]
        assert table.skipped_sheets == []

    def test_rows_unpack_as_number_and_cells(self):
        table = read_table("a.xlsx", make_xlsx([{"A": "x"}]))
        row = table.sheets[0].rows[0]
        assert isinstance(row, Row)
        number, cells = row
        assert (number, cells) == (1, {0: "x"})

    def test_cell_kinds(self):
        data = make_xlsx(
            [{"A": "  ", "B": True, "C": False, "D": Formula("1+1", "2"), "E": 0}],
            shared_strings=False,
        )
        cells = read_table("a.xlsx", data).sheets[0].rows[0].cells
        # A whitespace-only cell is blank; booleans read "1"/"0"; a formula
        # reads its cached value; a zero is a value, not a blank.
        assert cells == {1: "1", 2: "0", 3: 2.0, 4: 0.0}

    def test_values_keep_their_spacing(self):
        cells = read_table("a.xlsx", make_xlsx([{"A": " Ada "}])).sheets[0].rows[0].cells
        assert cells == {0: " Ada "}

    def test_a_broken_further_sheet_is_skipped_not_fatal(self):
        data = make_xlsx([{"A": "ok"}], extra_sheets=[("Kaputt", [{"A": "x"}])])
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buffer, "w") as dst:
            for item in src.infolist():
                body = src.read(item.filename)
                if item.filename == "xl/worksheets/sheet2.xml":
                    body = b"<worksheet><sheetData><row>"
                dst.writestr(item, body)
        table = read_table("a.xlsx", buffer.getvalue())
        assert [s.name for s in table.sheets] == ["Tabelle1"]
        assert table.skipped_sheets == [SkippedSheet("Kaputt", "unreadable")]

    def test_an_oversized_further_sheet_is_skipped(self):
        data = make_xlsx([{"A": "ok"}], extra_sheets=[("Riesig", [{"A": "x"}])])
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                body = src.read(item.filename)
                if item.filename == "xl/worksheets/sheet2.xml":
                    body = b"\0" * (ooxml.MAX_MEMBER_BYTES + 1)
                dst.writestr(item.filename, body)
        table = read_table("a.xlsx", buffer.getvalue())
        assert [s.name for s in table.sheets] == ["Tabelle1"]
        assert table.skipped_sheets == [SkippedSheet("Riesig", "member_too_large")]

    def test_a_further_sheet_over_the_row_cap_is_skipped(self):
        data = make_xlsx(
            [{"A": "a"}], extra_sheets=[("Lang", [{"A": str(i)} for i in range(5)])]
        )
        table = read_table("a.xlsx", data, max_rows=3)
        assert table.skipped_sheets == [SkippedSheet("Lang", "too_many_rows")]

    def test_the_first_sheet_over_the_row_cap_refuses_the_file(self):
        data = make_xlsx([{"A": str(i)} for i in range(5)])
        with pytest.raises(TableReadError) as exc:
            read_table("a.xlsx", data, max_rows=4)
        assert exc.value.code == "too_many_rows"
        assert read_table("a.xlsx", data, max_rows=5).sheets[0].rows[-1].number == 5

    def test_absolute_relationship_targets_resolve(self):
        data = make_xlsx([{"A": "x"}], absolute_target=True, sheet_file="blatt.xml")
        assert _cells(read_table("a.xlsx", data).sheets[0]) == [(1, {0: "x"})]

    def test_not_a_zip_is_unreadable(self):
        with pytest.raises(TableReadError) as exc:
            read_table("a.xlsx", b"not a zip at all")
        assert exc.value.code == "unreadable"

    def test_workbook_without_sheets(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/workbook.xml", "<workbook><sheets/></workbook>")
        with pytest.raises(TableReadError) as exc:
            read_table("a.xlsx", buffer.getvalue())
        assert exc.value.code == "no_worksheet"

    def test_first_sheet_part_missing(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/workbook.xml", '<workbook><sheets><sheet name="A"/></sheets></workbook>')
        with pytest.raises(TableReadError) as exc:
            read_table("a.xlsx", buffer.getvalue())
        assert exc.value.code == "worksheet_missing"

    def test_zip_bomb_member_is_refused_before_decompressing(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/workbook.xml", '<workbook><sheets><sheet name="A"/></sheets></workbook>')
            zf.writestr("xl/worksheets/sheet1.xml", b"\0" * (ooxml.MAX_MEMBER_BYTES + 1024))
        payload = buffer.getvalue()
        assert len(payload) < 1024 * 1024
        with pytest.raises(TableReadError) as exc:
            read_table("a.xlsx", payload)
        assert exc.value.code == "member_too_large"


class TestDelimited:
    def test_excel_csv_with_bom_and_semicolons(self):
        data = "﻿Name;Punkte;Kommentar\nAda;7,5;\n\nBea;3;gut\n".encode("utf-8")
        table = read_table("liste.csv", data)
        assert table.format == "csv"
        assert [s.name for s in table.sheets] == ["liste"]
        # Every record keeps its number, the blank line included; cells stay
        # strings ("7,5" is the caller's to read as a number).
        assert _cells(table.sheets[0]) == [
            (1, {0: "Name", 1: "Punkte", 2: "Kommentar"}),
            (2, {0: "Ada", 1: "7,5"}),
            (3, {}),
            (4, {0: "Bea", 1: "3", 2: "gut"}),
        ]

    def test_comma_csv_with_quoted_delimiters(self):
        data = b'a,b\n"x, y",2\n'
        assert _cells(read_table("a.csv", data).sheets[0]) == [(1, {0: "a", 1: "b"}), (2, {0: "x, y", 1: "2"})]

    def test_tsv_is_always_tab_separated(self):
        data = b"a;b\tc\n1;2\t3\n"
        assert _cells(read_table("a.tsv", data).sheets[0]) == [
            (1, {0: "a;b", 1: "c"}),
            (2, {0: "1;2", 1: "3"}),
        ]

    def test_cp1252_file(self):
        data = "Name;Prüfer\nZoë;Müller\n".encode("cp1252")
        rows = read_table("a.csv", data).sheets[0].rows
        assert rows[1].cells == {0: "Zoë", 1: "Müller"}

    def test_row_cap(self):
        data = b"\n".join(b"x" for _ in range(6))
        with pytest.raises(TableReadError) as exc:
            read_table("a.csv", data, max_rows=5)
        assert exc.value.code == "too_many_rows"

    def test_an_unreadable_csv_is_a_read_error(self):
        data = b'"' + b"x" * (200 * 1024)
        with pytest.raises(TableReadError) as exc:
            read_table("a.csv", data)
        assert exc.value.code == "unreadable"

    def test_sniff_single_column(self):
        assert sniff_delimiter("Name\nAda\n") == ","
        assert sniff_delimiter("a;b\n1;2\n") == ";"


class TestDispatchAndHelpers:
    @pytest.mark.parametrize(
        "name,fmt", [("a.xlsx", "xlsx"), ("A.CSV", "csv"), ("a.tsv", "tsv"), ("a.docx", None), ("", None)]
    )
    def test_table_format(self, name, fmt):
        assert table_format(name) == fmt

    def test_unsupported_and_empty(self):
        with pytest.raises(TableReadError) as exc:
            read_table("a.docx", b"x")
        assert exc.value.code == "unsupported_type"
        with pytest.raises(TableReadError) as exc:
            read_table("a.csv", b"")
        assert exc.value.code == "empty_file"

    def test_every_raised_code_is_declared(self):
        assert set(ERROR_CODES) == {
            "unsupported_type",
            "empty_file",
            "unreadable",
            "member_too_large",
            "no_worksheet",
            "worksheet_missing",
            "too_many_rows",
        }

    def test_cell_references(self):
        assert [column_letter(i) for i in (0, 25, 26, 701, 702)] == ["A", "Z", "AA", "ZZ", "AAA"]
        assert [column_index(r) for r in ("A1", "c7", "AA10", "ZZ")] == [0, 2, 26, 701]
        assert cell_ref(7, 2) == "C7"

    def test_decode_text_never_fails(self):
        assert decode_text("﻿ä".encode("utf-8")) == "ä"
        assert decode_text(b"\x81") == "�"
