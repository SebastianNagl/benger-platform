"""Unit tests for the deterministic Korrekturbogen importer
(``services/api/services/rubric_import.py``).

Every fixture is built in-test with the stdlib zip builders in
``tests/fixtures/rubric_files.py`` — no binary files in the repo. The
colleague's sheet (Polizeirecht Übungsklausur) is reproduced in reduced form
with all of its real-world quirks: the ``Frage 1:`` header row shared with the
column header, ``insgesamt N BE`` notes, half points, ``0,5`` comma decimals,
Schwerpunkt markers with hint bullets, a scored node with scored children,
the ``Gesamt-BE`` formula row, a ``10~19`` range, the Notenschlüssel rows and
the rounding sentence, and a ``Korrektor:`` trailer.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from rubric_structure import criteria_from_structure, validate_structure  # noqa: E402
from services.rubric_import import (  # noqa: E402
    MAX_RAW_ROWS,
    MAX_RUBRIC_FILE_BYTES,
    MAX_ZIP_MEMBER_BYTES,
    RubricImportError,
    parse_rubric_file,
)
from tests.fixtures.rubric_files import (  # noqa: E402
    COLLEAGUE_THRESHOLDS,
    SCALE_RANGES,
    Formula,
    colleague_sample_rows,
    colleague_sample_xlsx,
    make_docx,
    make_xlsx,
)


def _codes(result):
    return [w["code"] for w in result["warnings"]]


def _steps(result):
    return [n for n in result["structure"]["nodes"] if n["kind"] == "step"]


def _by_title(result):
    return {n["title"]: n for n in result["structure"]["nodes"]}


def _xlsx(rows, **kwargs):
    return parse_rubric_file("bogen.xlsx", make_xlsx(rows, **kwargs))


def _scale_rows():
    cols = "BCDEFGHIJKLMNOPQRST"
    return [
        {"A": "Notenschlüssel:"},
        {"A": "BE", **{cols[i]: r for i, r in enumerate(SCALE_RANGES)}},
        {"A": "Note", **{cols[i]: g for i, g in enumerate(range(19))}},
    ]


# ---------------------------------------------------------------------------
# The colleague's sheet
# ---------------------------------------------------------------------------


class TestColleagueSample:
    @pytest.fixture(scope="class")
    def result(self):
        return parse_rubric_file("Korrekturbogen mit Bewertungseinheiten.xlsx", colleague_sample_xlsx())

    def test_totals_scale_and_contract(self, result):
        assert result["source_format"] == "xlsx"
        assert result["total_points"] == 100
        assert len(result["structure"]["nodes"]) == 27
        assert len(_steps(result)) == 15
        assert result["grade_scale"] == {
            "unit": "BE",
            "thresholds": COLLEAGUE_THRESHOLDS,
            "rounding": "floor",
            "pass_grade": 4,
            "max_points": 100,
        }
        # The same key in percent, offered as the EXAM's Notenschlüssel
        # This sheet totals 100 BE, so the numbers coincide.
        assert result["grade_scale_percent"] == {
            "unit": "percent",
            "preset": "custom",
            "thresholds": [float(t) for t in COLLEAGUE_THRESHOLDS],
            "rounding": "floor",
            "pass_grade": 4,
        }
        assert validate_structure(result["structure"]) == []
        assert criteria_from_structure(result["structure"]) == result["criteria"]
        assert list(result["criteria"])[:2] == [
            "s01_eroeffnung_des_verwaltungsrechtswegs_nach_40_i_1_vwgo",
            "s02_abdraengende_sonderzuweisung_eindeutig_zu_verneinen",
        ]
        assert result["title"] == "Korrekturbogen mit Bewertungseinheiten"

    def test_levels_kinds_and_labels(self, result):
        nodes = result["structure"]["nodes"]
        by = _by_title(result)
        assert nodes[0] == {"id": "n1", "level": 0, "kind": "section", "label": "", "title": "Frage 1", "note": None}
        assert by["Zulässigkeit"]["level"] == 1 and by["Zulässigkeit"]["label"] == "A."
        assert by["Zulässigkeit"]["note"] == "insgesamt 21 BE"
        eroeffnung = by["Eröffnung des Verwaltungsrechtswegs nach § 40 I 1 VwGO"]
        assert (eroeffnung["level"], eroeffnung["label"], eroeffnung["max_score"]) == (2, "I.", 1)
        # a scored bullet under a scored step → child step (rows 3/4)
        child = by["Abdrängende Sonderzuweisung eindeutig zu verneinen"]
        assert (child["level"], child["label"], child["max_score"]) == (3, "", 2)
        assert by["Statthafte Klageart"]["level"] == 2 and by["Anfechtungsklage"]["level"] == 3
        va = by["Verwaltungsakt i.S.d. Art. 35 S. 1 VwVfG"]
        assert va["kind"] == "section" and va["level"] == 4 and va["label"] == "a)"
        assert (by["Regelung (+)"]["level"], by["Regelung (+)"]["max_score"]) == (5, 1)
        assert by["Allgemeinverfügung irrelevant"]["max_score"] == 0.5
        assert by["Erledigung des VA"]["label"] == "b)" and by["Erledigung des VA"]["level"] == 4
        assert by["Klagebefugnis, § 42 II VwGO analog"]["level"] == 2  # roman continues after a subtree
        # rich-text shared string joined; comma decimal note kept verbatim
        assert by["Begründetheit"]["note"] == "insgesamt 21,5 BE"
        obersatz = by["Obersatz (Vergangenheitsform!)"]
        assert (obersatz["level"], obersatz["label"], obersatz["max_score"]) == (2, "", 1)
        emphasised = by["Maßnahmerichtung"]
        assert emphasised["emphasis"] == "schwerpunkt" and emphasised["max_score"] == 10
        assert emphasised["hints"] == [
            "Ausführliche Diskussion: H als Zweckveranlasser? (+)",
            "A. A. vertr., wichtig ist die Diskussion der Frage!",
        ]
        bb = by["Unverhältnismäßiger Grundrechtseingriff"]
        assert bb["kind"] == "section" and bb["note"] == "weiterer Schwerpunkt!"
        assert by["Schutzbereich"]["label"] == "(1)" and by["Schutzbereich"]["level"] == 4
        assert by["Zwischenergebnis"]["kind"] == "section" and by["Ergebnis"]["label"] == "C."
        frage2 = by["Frage 2"]
        assert frage2["level"] == 0 and frage2["note"] == "Insgesamt 72,5 BE"
        assert by["Sperrwirkung der Standardbefugnisse"]["max_score"] == 1.5  # "1,5" text cell
        assert by["Generalklausel"]["emphasis"] == "schwerpunkt"
        aa = by["Aufgabeneröffnung nach Art. 2 Abs. 1 PAG"]
        assert aa["label"] == "aa)" and aa["max_score"] == 68 and aa["emphasis"] == "schwerpunkt"

    def test_warnings(self, result):
        codes = _codes(result)
        assert sorted(codes) == ["empty_section", "empty_section", "subtotal_mismatch", "title_from_filename"]
        mismatch = next(w for w in result["warnings"] if w["code"] == "subtotal_mismatch")
        assert mismatch["node_id"] == "n2" and mismatch["row"] == 2
        assert "21 BE" in mismatch["message"] and "6 BE" in mismatch["message"]
        empties = [w for w in result["warnings"] if w["code"] == "empty_section"]
        assert {w["node_id"] for w in empties} == {"n19", "n20"}

    def test_trailer_and_scale_rows_are_not_nodes(self, result):
        titles = " | ".join(n["title"] for n in result["structure"]["nodes"])
        for forbidden in ("Korrektor", "Ergibt", "Note in Punkten", "Gesamt", "Notenschlüssel", "abgerundet"):
            assert forbidden not in titles

    def test_inline_strings_and_non_default_sheet_name(self):
        result = parse_rubric_file(
            "bogen.xlsx",
            make_xlsx(colleague_sample_rows(), shared_strings=False, sheet_file="sheet3.xml", absolute_target=True),
        )
        assert result["total_points"] == 100
        assert len(_steps(result)) == 15


# ---------------------------------------------------------------------------
# XLSX heuristics
# ---------------------------------------------------------------------------


class TestXlsxHeuristics:
    def test_v_continues_the_roman_sequence(self):
        result = _xlsx([{"A": "A. Abschnitt"}, {"A": "IV. Vier", "B": 1}, {"A": "V. Fünf", "B": 1}])
        by = _by_title(result)
        assert by["Vier"]["level"] == 1 and by["Fünf"]["level"] == 1 and by["Fünf"]["label"] == "V."
        assert "ambiguous_label" not in _codes(result)

    def test_v_continues_the_capital_sequence(self):
        result = _xlsx([{"A": "U. Abschnitt"}, {"A": "I. Eins", "B": 1}, {"A": "V. Nächster", "B": 1}])
        by = _by_title(result)
        assert by["Nächster"]["level"] == 0 and by["Nächster"]["label"] == "V."
        assert "ambiguous_label" not in _codes(result)

    def test_v_without_context_is_roman_with_warning(self):
        result = _xlsx([{"A": "A. Abschnitt"}, {"A": "V. Fünf", "B": 1}, {"A": "VI. Sechs", "B": 1}])
        assert _by_title(result)["Fünf"]["level"] == 1
        assert _by_title(result)["Sechs"]["level"] == 1
        assert "ambiguous_label" in _codes(result)

    def test_multi_letter_roman_and_c_capital(self):
        result = _xlsx([{"A": "C. Abschnitt"}, {"A": "III. Drei", "B": 1}, {"A": "L. Elf"}, {"A": "I. x", "B": 1}])
        by = _by_title(result)
        assert by["Abschnitt"]["level"] == 0 and by["Drei"]["level"] == 1
        assert by["Elf"]["level"] == 0 and by["Elf"]["label"] == "L."

    def test_label_less_scored_rows_sibling_after_step_child_after_section(self):
        result = _xlsx([
            {"A": "A. Abschnitt"},
            {"A": "Erster", "B": 1},
            {"A": "I. Zweiter", "B": 1},
            {"A": "Dritter", "B": 1},
            {"A": "1. Vierter", "B": 1},
            {"A": "Fünfter", "B": 1},
        ])
        by = _by_title(result)
        assert by["Erster"]["level"] == 1  # child of the section
        assert by["Zweiter"]["level"] == 1
        assert by["Dritter"]["level"] == 1  # sibling of the previous step
        assert by["Vierter"]["level"] == 2
        assert by["Fünfter"]["level"] == 2
        assert all(n["label"] == "" for n in (by["Erster"], by["Dritter"], by["Fünfter"]))

    def test_leaf_section_never_becomes_a_zero_point_step(self):
        result = _xlsx([{"A": "A. Abschnitt"}, {"A": "I. Leer"}, {"A": "II. Voll", "B": 1}])
        leer = _by_title(result)["Leer"]
        assert leer["kind"] == "section" and "max_score" not in leer
        assert [w["node_id"] for w in result["warnings"] if w["code"] == "empty_section"] == ["n2"]

    def test_points_rounding_invalid_and_units(self):
        result = _xlsx([
            {"A": "I. a", "B": 0.3},
            {"A": "II. b", "B": 0},
            {"A": "III. c", "B": "abc"},
            {"A": "IV. d", "B": "2 BE"},
            {"A": "V. e", "B": "1,5 Punkte"},
            {"A": "VI. f", "B": -1},
        ])
        by = _by_title(result)
        assert by["a"]["max_score"] == 0.5
        assert by["b"]["kind"] == "section" and by["c"]["kind"] == "section" and by["f"]["kind"] == "section"
        assert by["d"]["max_score"] == 2 and by["e"]["max_score"] == 1.5
        codes = _codes(result)
        assert codes.count("points_invalid") == 3 and "points_rounded" in codes
        rounded = next(w for w in result["warnings"] if w["code"] == "points_rounded")
        assert rounded["row"] == 1

    def test_total_mismatch(self):
        result = _xlsx([{"A": "I. a", "B": 1}, {"A": "II. b", "B": 2}, {"A": "Gesamt", "B": 50}])
        assert result["total_points"] == 3
        assert "total_mismatch" in _codes(result)
        assert len(result["structure"]["nodes"]) == 2

    def test_notes_emphasis_and_bullet_note(self):
        result = _xlsx([
            {"A": "A. Zulässigkeit (insgesamt 4 BE)"},
            {"A": "· Hinweis zum Abschnitt"},
            {"A": "I. x (Schwerpunkt!)", "B": 3},
            {"A": "II. y (weiterer Schwerpunkt!)"},
            {"A": "1. z", "B": 1},
            {"A": "Insgesamt 1 BE"},
        ])
        by = _by_title(result)
        assert by["Zulässigkeit"]["note"] == "insgesamt 4 BE; Hinweis zum Abschnitt"
        assert by["x"]["emphasis"] == "schwerpunkt" and by["x"]["max_score"] == 3
        assert by["y"]["kind"] == "section" and by["y"]["note"] == "weiterer Schwerpunkt!"
        assert "note_from_bullet" in _codes(result)
        assert "subtotal_mismatch" not in _codes(result)
        # a label-less note-only row after a step is kept as the step's note, not an empty hint
        assert by["z"]["hints"] == []
        assert by["z"]["note"] == "Insgesamt 1 BE"

    def test_hints_attach_to_the_last_step(self):
        result = _xlsx([
            {"A": "I. Schritt", "B": 2},
            {"A": "· Erster Hinweis"},
            {"A": "Zweiter Hinweis ohne Marker"},
            {"A": "II. Nächster", "B": 1},
        ])
        assert _by_title(result)["Schritt"]["hints"] == ["Erster Hinweis", "Zweiter Hinweis ohne Marker"]

    def test_more_than_twenty_hints_are_merged(self):
        rows = [{"A": "I. Schritt", "B": 2}] + [{"A": f"· Hinweis {i}"} for i in range(25)]
        hints = _by_title(_xlsx(rows))["Schritt"]["hints"]
        assert len(hints) == 20 and "Hinweis 24" in hints[-1]

    def test_unparsed_scale_with_17_grades_falls_back_to_default(self):
        result = parse_rubric_file("b.xlsx", make_xlsx(colleague_sample_rows(grades=list(range(17)) + [None, None])))
        assert result["grade_scale"] is None
        assert "grade_scale_unparsed" in _codes(result)

    def test_rounding_assumed_when_sentence_missing(self):
        rows = [r for r in colleague_sample_rows() if not (r and "abgerundet" in str(r.get("A", "")))]
        result = parse_rubric_file("b.xlsx", make_xlsx(rows))
        assert result["grade_scale"]["rounding"] == "floor"
        assert "rounding_assumed" in _codes(result)

    def test_rounding_sentence_variants(self):
        base = [{"A": "I. a", "B": 100}] + _scale_rows()
        assert _xlsx(base + [{"A": "halbe BE werden aufgerundet"}])["grade_scale"]["rounding"] == "ceil"
        assert _xlsx(base + [{"A": "es wird kaufmännisch gerundet"}])["grade_scale"]["rounding"] == "nearest"

    def test_vertical_scale_layout(self):
        rows = [{"A": "I. a", "B": 100}, {"A": "Punkteschlüssel"}]
        rows += [{"A": rng, "B": grade} for grade, rng in enumerate(SCALE_RANGES)]
        result = _xlsx(rows)
        assert result["grade_scale"]["thresholds"] == COLLEAGUE_THRESHOLDS

    def test_scale_not_fitting_the_total_is_dropped(self):
        result = _xlsx([{"A": "I. a", "B": 10}] + _scale_rows())
        assert result["grade_scale"] is None
        assert "grade_scale_total_mismatch" in _codes(result)
        assert "grade_scale_unparsed" in _codes(result)
        assert result["grade_scale_percent"] is None

    def test_percent_twin_on_a_non_100_total(self):
        """A 50 BE sheet: the absolute key stays absolute, the percent twin
        rescales it so the exam key survives a later change of the total."""
        lows = [5, 10, 15, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48]
        bounds = [(0, lows[0] - 1)] + [
            (low, (lows[i + 1] - 1) if i + 1 < len(lows) else 50)
            for i, low in enumerate(lows)
        ]
        rows = [{"A": "I. a", "B": 50}, {"A": "Notenschlüssel:"}]
        rows += [
            {"A": f"{low}-{high} BE", "B": grade}
            for grade, (low, high) in enumerate(bounds)
        ]
        result = _xlsx(rows)
        assert result["total_points"] == 50
        assert result["grade_scale"]["unit"] == "BE"
        percent = result["grade_scale_percent"]
        assert percent["unit"] == "percent" and percent["preset"] == "custom"
        assert percent["rounding"] == result["grade_scale"]["rounding"]
        assert percent["pass_grade"] == 4
        assert "max_points" not in percent
        assert percent["thresholds"] == [
            round(t / 50 * 100, 4) for t in result["grade_scale"]["thresholds"]
        ]
        assert percent["thresholds"][0] == 10.0  # 5 BE of 50 = 10 %

    def test_title_from_first_free_row(self):
        result = _xlsx([{"A": "Korrekturbogen Übungsklausur"}, {"A": "I. a", "B": 1}, {"A": "II. b", "B": 1}])
        assert result["title"] == "Korrekturbogen Übungsklausur"
        assert "title_from_filename" not in _codes(result)

    def test_points_column_from_header_ignores_ihre_be(self):
        result = _xlsx([
            {"A": "Text", "B": "Ihre BE", "C": "max. BE"},
            {"A": "I. a", "B": 0, "C": 2},
            {"A": "II. b", "B": 1, "C": 3},
            {"A": "III. c", "B": 0, "C": 1},
        ])
        assert [s["max_score"] for s in _steps(result)] == [2, 3, 1]

    def test_points_column_first_numeric_right_of_text(self):
        result = _xlsx([{"A": "I. a", "C": 2}, {"A": "II. b", "C": 3}, {"A": "III. c", "C": 1}])
        assert [s["max_score"] for s in _steps(result)] == [2, 3, 1]

    def test_formula_cells_use_cached_values(self):
        result = _xlsx([{"A": "I. a", "B": Formula("1+1", 2)}, {"A": "II. b", "B": 1}, {"A": "Summe", "B": Formula("SUM(B1:B2)", 3)}])
        assert result["total_points"] == 3 and "total_mismatch" not in _codes(result)

    def test_no_scored_steps(self):
        with pytest.raises(RubricImportError) as exc:
            _xlsx([{"A": "A. Nur"}, {"A": "I. Überschriften"}, {"A": "II. ohne Punkte"}])
        assert exc.value.code == "no_scored_steps"
        assert exc.value.to_detail()["code"] == "no_scored_steps"

    def test_no_text_column(self):
        with pytest.raises(RubricImportError) as exc:
            _xlsx([{"A": 1}, {"A": 2}, {"A": 3}])
        assert exc.value.code == "no_table_found"

    def test_too_many_rows(self):
        with pytest.raises(RubricImportError) as exc:
            _xlsx([{"A": f"I. r{i}", "B": 1} for i in range(MAX_RAW_ROWS + 1)])
        assert exc.value.code == "too_many_rows"

    def test_unsupported_and_corrupt(self):
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.pdf", b"%PDF")
        assert exc.value.code == "unsupported_type"
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.xlsx", b"not a zip at all")
        assert exc.value.code == "corrupt_file"
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.xlsx", b"")
        assert exc.value.code == "corrupt_file"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("hello.txt", "no workbook here")
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bogen.xlsx", buffer.getvalue())
        assert exc.value.code == "corrupt_file"

    def test_zip_bomb_member_is_refused_before_decompressing(self):
        """A small upload whose worksheet part DECLARES a huge size is refused.

        OOXML files are zips, so the 5 MB endpoint cap says nothing about
        what a member expands to: 600 MB of zeros compress to well under a
        megabyte. Without the guard ``zf.read`` would materialize all of it
        in the api worker (1 GiB container limit in dev).
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                '2006/main"><sheets><sheet name="S" sheetId="1"/></sheets></workbook>',
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml", b"\0" * (MAX_ZIP_MEMBER_BYTES + 1024)
            )
        payload = buffer.getvalue()
        assert len(payload) < MAX_RUBRIC_FILE_BYTES  # passes the endpoint cap
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("bombe.xlsx", payload)
        assert exc.value.code == "corrupt_file"


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _scale_table():
    return [
        [["BE"]] + [[r] for r in SCALE_RANGES],
        [["Note"]] + [[str(g)] for g in range(19)],
    ]


class TestDocx:
    def test_happy_path_with_typed_labels(self):
        data = make_docx(
            [
                [
                    [[""], ["max. BE"], ["erreicht"]],
                    [["A. Zulässigkeit (insgesamt 3 BE)"], [""], [""]],
                    [["I. Eröffnung des Verwaltungsrechtswegs"], ["1"], [""]],
                    [["II. Klagebefugnis (Schwerpunkt!)"], ["2"], [""]],
                    [["B. Begründetheit"], [""], [""]],
                    [["I. Anspruch"], ["97"], [""]],
                    [["Gesamt-BE"], ["100"], [""]],
                ],
                _scale_table(),
            ],
            paragraphs_before=["Korrekturbogen Polizeirecht"],
            paragraphs_between=["Notenschlüssel:"],
            paragraphs_after=["Die Note errechnet sich aus den BE; bei 0,5 BE wird abgerundet.", "Korrektor: X"],
        )
        result = parse_rubric_file("Übungsklausur Korrekturbogen.docx", data)
        assert result["source_format"] == "docx"
        assert result["title"] == "Korrekturbogen Polizeirecht"
        assert result["total_points"] == 100
        assert result["grade_scale"]["thresholds"] == COLLEAGUE_THRESHOLDS
        assert result["grade_scale"]["rounding"] == "floor"
        by = _by_title(result)
        assert by["Zulässigkeit"]["note"] == "insgesamt 3 BE"
        assert by["Klagebefugnis"]["emphasis"] == "schwerpunkt" and by["Klagebefugnis"]["level"] == 1
        assert by["Anspruch"]["max_score"] == 97
        assert "title_from_filename" not in _codes(result)
        assert "total_mismatch" not in _codes(result)
        assert validate_structure(result["structure"]) == []
        assert criteria_from_structure(result["structure"]) == result["criteria"]

    def test_messy_cell_alignment(self):
        data = make_docx([[
            [["Text"], ["BE"]],
            [["b) Maßnahmerichtung (Schwerpunkt!)", "· H1", "· H2"], ["10", "", ""]],
            [["a) VA", "· Regelung", "· AV"], ["1", "", "2"]],
            [["Gefahr", "Konkrete Gefahr"], ["3"]],
            [["Nur eine Zeile"], ["1", "2"]],
        ]])
        result = parse_rubric_file("b.docx", data)
        by = _by_title(result)
        assert by["Maßnahmerichtung"]["max_score"] == 10 and by["Maßnahmerichtung"]["emphasis"] == "schwerpunkt"
        assert by["Maßnahmerichtung"]["hints"] == ["H1", "H2"]
        assert by["VA"]["max_score"] == 1 and by["VA"]["hints"] == ["Regelung"]
        assert by["AV"]["max_score"] == 2 and by["AV"]["level"] == by["VA"]["level"] + 1
        # one value, two non-bullet lines → heading gets it, reviewer warned
        assert by["Gefahr"]["max_score"] == 3 and by["Gefahr"]["hints"] == ["Konkrete Gefahr"]
        assert by["Nur eine Zeile"]["max_score"] == 1
        alignment = [w for w in result["warnings"] if w["code"] == "alignment_uncertain"]
        assert {w["row"] for w in alignment} == {4, 5}
        assert any("2 BE" in w["message"] for w in alignment if w["row"] == 5)

    def test_bullets_via_numbering_xml(self):
        data = make_docx(
            [[
                [["Text"], ["BE"]],
                [["I. Schritt", {"text": "Erster Hinweis", "bullet": True}, {"text": "Zweiter", "bullet": True}], ["4"]],
                [["II. Anderer"], ["1"]],
            ]],
            bullet_numbering=True,
        )
        result = parse_rubric_file("b.docx", data)
        by = _by_title(result)
        assert by["Schritt"]["max_score"] == 4 and by["Schritt"]["hints"] == ["Erster Hinweis", "Zweiter"]
        assert "alignment_uncertain" not in _codes(result)
        assert "auto_numbering" not in _codes(result)

    def test_style_linked_numbering_reconstructs_labels(self):
        data = make_docx(
            [[
                [[""], ["BE"]],
                [["Frage 1:", {"text": "Zulässigkeit", "style": "H1"}], ["Insgesamt: 3,5 BE"]],
                [[{"text": "Eröffnung", "style": "H2"}, {"text": "Abdrängend", "bullet": True}], ["1", "", "2"]],
                [[{"text": "Statthafte Klageart", "style": "H2"}], [""]],
                [[{"text": "Anfechtungsklage", "style": "H3"}], ["0,5"]],
                [[{"text": "Begründetheit", "style": "H1"}], [""]],
                [[{"text": "Anspruch", "style": "H2"}], ["1"]],
            ]],
            styles=True,
        )
        result = parse_rubric_file("b.docx", data)
        by = _by_title(result)
        assert by["Frage 1"]["level"] == 0
        assert (by["Zulässigkeit"]["label"], by["Zulässigkeit"]["level"]) == ("A.", 1)
        assert by["Zulässigkeit"]["note"] == "Insgesamt: 3,5 BE"  # BE-cell note → last heading of the cell
        assert (by["Eröffnung"]["label"], by["Eröffnung"]["level"], by["Eröffnung"]["max_score"]) == ("I.", 2, 1)
        assert by["Abdrängend"]["max_score"] == 2 and by["Abdrängend"]["level"] == 3
        assert by["Statthafte Klageart"]["label"] == "II."
        assert (by["Anfechtungsklage"]["label"], by["Anfechtungsklage"]["max_score"]) == ("1.", 0.5)
        assert by["Begründetheit"]["label"] == "B."
        assert by["Anspruch"]["label"] == "I."  # roman restarts under the new section
        assert "auto_numbering" in _codes(result)
        assert "subtotal_mismatch" not in _codes(result)

    def test_direct_outline_numbering_with_word_start_value(self):
        data = make_docx(
            [[
                [["Text"], ["BE"]],
                [[{"text": "Abschnitt", "num": (2, 0)}], [""]],
                [[{"text": "Formell", "num": (2, 3)}], [""]],
                [[{"text": "Polizei", "num": (2, 4)}], ["2"]],
                [[{"text": "Sachlich", "num": (2, 4)}], ["1"]],
                [[{"text": "Aufgabe", "num": (2, 5)}], ["3"]],
            ]],
            bullet_numbering=True,
        )
        result = parse_rubric_file("b.docx", data)
        by = _by_title(result)
        assert by["Abschnitt"]["label"] == "A."
        assert by["Formell"]["label"] == "a)"
        assert by["Polizei"]["label"] == "aa)" and by["Sachlich"]["label"] == "bb)"  # w:start=27
        assert by["Aufgabe"]["label"] == "(1)" and by["Aufgabe"]["level"] == by["Sachlich"]["level"] + 1

    def test_scale_table_without_trigger_paragraph(self):
        data = make_docx([[[["Text"], ["BE"]], [["I. a"], ["99"]], [["II. b"], ["1"]]], _scale_table()])
        result = parse_rubric_file("b.docx", data)
        assert result["grade_scale"]["thresholds"] == COLLEAGUE_THRESHOLDS
        assert "rounding_assumed" in _codes(result)

    def test_merged_cell_row(self):
        data = make_docx([[
            [["Text"], ["BE"]],
            [["A. Nur eine Zelle"]],
            [["I. Schritt"], ["2"]],
        ]])
        result = parse_rubric_file("b.docx", data)
        by = _by_title(result)
        assert by["Nur eine Zelle"]["kind"] == "section" and by["Schritt"]["level"] == 1
        assert "merged_label_cell" in _codes(result)

    def test_no_table_and_no_scored_table(self):
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("b.docx", make_docx([], paragraphs_before=["Nur Text"]))
        assert exc.value.code == "no_table_found"
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("b.docx", make_docx([[[["a"], ["b"]], [["c"], ["d"]], [["e"], ["f"]]]]))
        assert exc.value.code == "no_table_found"

    def test_corrupt_docx(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("word/other.xml", "<x/>")
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("b.docx", buffer.getvalue())
        assert exc.value.code == "corrupt_file"
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("b.docx", b"garbage")
        assert exc.value.code == "corrupt_file"

    def test_too_many_table_rows(self):
        rows = [[["Text"], ["BE"]]] + [[[f"I. r{i}"], ["1"]] for i in range(MAX_RAW_ROWS + 1)]
        with pytest.raises(RubricImportError) as exc:
            parse_rubric_file("b.docx", make_docx([rows]))
        assert exc.value.code == "too_many_rows"
