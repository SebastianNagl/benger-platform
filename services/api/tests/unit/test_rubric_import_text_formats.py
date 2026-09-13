"""CSV, Markdown and JSON Korrekturbogen imports.

The OOXML pair is what a chair usually produces, but a Word table is the
hardest thing in this importer to read correctly: the structure lives in
paragraph alignment rather than in the data. These three formats exist so a
chair who CAN state the sheet plainly gets an exact import instead of a
heuristic one — and so a sheet curated once in the outline editor can be
exported and brought back without loss.

All of them reduce to the same grid the XLSX reader produces, so column
detection, the outline builder, the Notenschlüssel detector and every warning
are shared rather than reimplemented. JSON is the exception in one direction
only: a file that already carries a valid structure is taken verbatim.
"""

from __future__ import annotations

import json

import pytest

from services.rubric_import import RubricImportError, parse_rubric_file


def _steps(result):
    return [n for n in result["structure"]["nodes"] if n["kind"] == "step"]


CSV_SHEET = (
    "Prüfungsschritt;max. BE\n"
    "Frage 1: Klage des H;\n"
    "A. Zulässigkeit;\n"
    "I. Eröffnung des Verwaltungsrechtswegs;1\n"
    "II. Statthafte Klageart;2,5\n"
    "b) Sperrwirkung (Schwerpunkt!);6\n"
    "Gesamt-BE;9,5\n"
)


class TestCsv:
    def test_it_reads_an_outline_with_half_points(self):
        result = parse_rubric_file("bogen.csv", CSV_SHEET.encode("utf-8"))
        assert result["source_format"] == "csv"
        assert result["total_points"] == 9.5
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5, 6]

    def test_labels_and_schwerpunkt_survive(self):
        steps = _steps(parse_rubric_file("bogen.csv", CSV_SHEET.encode("utf-8")))
        assert [s["label"] for s in steps] == ["I.", "II.", "b)"]
        assert steps[2]["emphasis"] == "schwerpunkt"
        # The marker is stripped from the title, not left in it.
        assert "Schwerpunkt" not in steps[2]["title"]

    @pytest.mark.parametrize("delimiter", [";", "\t"])
    def test_the_delimiter_is_sniffed(self, delimiter):
        # ';' is what German Excel writes, and it is the safe one: a decimal
        # comma needs no quoting next to it.
        body = CSV_SHEET.replace(";", delimiter)
        result = parse_rubric_file("bogen.csv", body.encode("utf-8"))
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5, 6]

    def test_a_comma_delimited_file_needs_its_decimals_quoted(self):
        # With ',' as the delimiter an unquoted "2,5" is two fields, and no
        # parser can tell which was meant. A correct writer quotes it; then
        # the decimal comma survives.
        body = CSV_SHEET.replace(";", ",").replace("2,5", '"2,5"')
        result = parse_rubric_file("bogen.csv", body.encode("utf-8"))
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5, 6]

    def test_a_bom_does_not_end_up_in_the_first_cell(self):
        # Excel's "CSV UTF-8" always writes one.
        result = parse_rubric_file("bogen.csv", CSV_SHEET.encode("utf-8-sig"))
        assert not _steps(result)[0]["title"].startswith("﻿")

    def test_cp1252_is_read(self):
        result = parse_rubric_file("bogen.csv", CSV_SHEET.encode("cp1252"))
        assert "Eröffnung" in _steps(result)[0]["title"]


MD_OUTLINE = (
    "# Korrekturbogen Polizeirecht\n\n"
    "## Frage 1\n\n"
    "### A. Zulässigkeit\n"
    "- I. Eröffnung des Verwaltungsrechtswegs — 1 BE\n"
    "- II. Statthafte Klageart (2,5 BE)\n"
    "- b) Sperrwirkung (Schwerpunkt!) 6 BE\n"
)

MD_TABLE = (
    "| Schritt | max. BE |\n"
    "| --- | --- |\n"
    "| A. Zulässigkeit | |\n"
    "| I. Verwaltungsrechtsweg | 1 |\n"
    "| II. Klageart | 2,5 |\n"
)


class TestMarkdown:
    def test_an_outline_with_trailing_points(self):
        result = parse_rubric_file("bogen.md", MD_OUTLINE.encode("utf-8"))
        assert result["source_format"] == "md"
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5, 6]

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("- I. Schritt — 1 BE", 1),
            ("- I. Schritt (2,5 BE)", 2.5),
            ("- I. Schritt [3 Punkte]", 3),
            ("- I. Schritt 4 P.", 4),
        ],
    )
    def test_the_point_notations_a_chair_actually_writes(self, line, expected):
        body = MD_OUTLINE.rsplit("\n", 4)[0] + "\n" + line + "\n"
        result = parse_rubric_file("bogen.md", body.encode("utf-8"))
        assert _steps(result)[-1]["max_score"] == expected

    def test_a_pipe_table_is_read_as_a_table(self):
        result = parse_rubric_file("tabelle.md", MD_TABLE.encode("utf-8"))
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5]
        # The separator row is not a step.
        assert all("---" not in s["title"] for s in _steps(result))

    def test_a_file_with_no_points_at_all_is_refused_clearly(self):
        body = "# Bogen\n\n- I. Ein Schritt ohne Punkte\n- II. Noch einer\n"
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.md", body.encode("utf-8"))
        assert exc.value.code == "no_scored_steps"


class TestJson:
    def test_a_list_of_steps(self):
        payload = json.dumps(
            {
                "steps": [
                    {"label": "A.", "title": "Zulässigkeit"},
                    {"label": "I.", "title": "Verwaltungsrechtsweg", "max_score": 1},
                    {"label": "II.", "title": "Klageart", "max_score": 2.5},
                ]
            }
        )
        result = parse_rubric_file("bogen.json", payload.encode("utf-8"))
        assert result["source_format"] == "json"
        assert [s["max_score"] for s in _steps(result)] == [1, 2.5]

    def test_a_structure_round_trips_verbatim(self):
        # The export side of this importer coming home: taken as-is, because
        # re-deriving it through the heuristics could only lose fidelity.
        source = parse_rubric_file("bogen.csv", CSV_SHEET.encode("utf-8"))
        exported = json.dumps(
            {
                "title": "Korrekturbogen PolR",
                "structure": source["structure"],
                "grade_scale": source["grade_scale"],
            }
        )
        back = parse_rubric_file("export.json", exported.encode("utf-8"))
        assert back["title"] == "Korrekturbogen PolR"
        assert back["total_points"] == source["total_points"]
        assert [s["key"] for s in _steps(back)] == [s["key"] for s in _steps(source)]
        assert [s["title"] for s in _steps(back)] == [s["title"] for s in _steps(source)]
        assert back["warnings"] == []

    def test_a_bare_nodes_document_is_also_a_structure(self):
        source = parse_rubric_file("bogen.csv", CSV_SHEET.encode("utf-8"))
        back = parse_rubric_file("nodes.json", json.dumps(source["structure"]).encode("utf-8"))
        assert len(_steps(back)) == len(_steps(source))

    def test_an_invalid_structure_is_refused_rather_than_repaired(self):
        payload = json.dumps({"structure": {"version": 1, "nodes": [{"id": "n1"}]}})
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("kaputt.json", payload.encode("utf-8"))
        assert exc.value.code == "no_scored_steps"

    def test_malformed_json_says_so(self):
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("kaputt.json", b"{nicht: json,,}")
        assert exc.value.code == "corrupt_file"


class TestDispatch:
    def test_an_unsupported_extension_names_what_is_accepted(self):
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.pdf", b"%PDF-1.4")
        assert exc.value.code == "unsupported_type"
        for ext in (".xlsx", ".docx", ".csv", ".md", ".json"):
            assert ext in exc.value.message

    @pytest.mark.parametrize("name", ["bogen.csv", "bogen.md", "bogen.json"])
    def test_an_empty_file_is_refused(self, name):
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file(name, b"")
        assert exc.value.code == "corrupt_file"
