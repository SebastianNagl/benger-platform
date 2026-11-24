"""Total rows, column blocks and worksheets in the Korrekturbogen importer.

A total row ("Summe", also with a few words after it, "Gesamt", "Total",
"Σ") used to end the outline for good: every row below it was dropped
without a word, and "Summe <x>" or "Total" rows were read as steps. The
importer also reads one text column and the first worksheet only, so a
second column block or a second worksheet vanished silently.

The sheet below is a synthetic 23-point sheet in the layout that showed
it: items with their points, the section names in rows without points
after (or before) their items, a "Kriterium | Punkte" header, and three
further sections (5.5 points) that follow a total row, sit in a second
column block or on a second worksheet. Before the fix each of those
layouts gave a 17.5-point sheet of 25 steps.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.rubric_import import parse_rubric_file  # noqa: E402
from tests.fixtures.rubric_files import make_docx, make_xlsx  # noqa: E402

HEADER = [("Kriterium", "Punkte")]

# 25 items, 17.5 points: five sections, each name in a row without points.
FIRST = [
    ("Juridiction et date de la décision", 1),
    ("Nature de la décision", 0.5),
    ("Visa", 0.5),
    ("Bonus", None),
    ("Juridiction", None),
    ("Qualification juridique", 1),
    ("Les parties", 0.5),
    ("L'objet du litige", 0.5),
    ("Le premier fait", 0.5),
    ("Le deuxième fait", 0.5),
    ("Le troisième fait", 0.5),
    ("La vente sans accord", 1),
    ("Les acquéreurs", 0.5),
    ("La demande", 1),
    ("Bonus/malus", None),
    ("Faits", None),
    ("Demandeur", 0.5),
    ("Défendeurs", 1),
    ("Décision des juges du fond", 0.5),
    ("Compétence retenue", 0.5),
    ("Demandeur au pourvoi", 0.5),
    ("Défendeur au pourvoi", 0.5),
    ("Procédure", None),
    ("Position du pourvoi", None),
    ("Premier moyen", 0.5),
    ("Deuxième moyen", 1),
    ("Troisième moyen", 1),
    ("Position des juges du fond", None),
    ("Premier motif", 1),
    ("Deuxième motif", 1),
    ("Troisième motif", 1),
    ("Compétence", 0.5),
    ("Bonus/malus", None),
]
# Three more sections, 10 items, 5.5 points.
REST = [
    ("Premier élément de la question", 0.5),
    ("Deuxième élément de la question", 0.5),
    ("Troisième élément de la question", 0.5),
    ("Question de droit", None),
    ("Premier élément de la réponse", 0.5),
    ("Deuxième élément de la réponse", 0.5),
    ("Troisième élément de la réponse", 0.5),
    ("Règle de compétence", 1),
    ("Réponse de la Cour", None),
    ("Cassation", 0.5),
    ("Incompétence", 0.5),
    ("Visa du dispositif", 0.5),
    ("Dispositif", None),
]


def _rows(pairs, col_text="A", col_points="B"):
    out = []
    for text, points in pairs:
        row = {col_text: text}
        if points is not None:
            row[col_points] = points
        out.append(row)
    return out


def _parse(rows, **kwargs):
    return parse_rubric_file("bareme.xlsx", make_xlsx(rows, **kwargs))


def _steps(result):
    return [n for n in result["structure"]["nodes"] if n["kind"] == "step"]


def _titles(result):
    return [n["title"] for n in result["structure"]["nodes"]]


def _codes(result):
    return [w["code"] for w in result["warnings"]]


def _warning(result, code):
    return next(w for w in result["warnings"] if w["code"] == code)


class TestTotalRowDoesNotEndTheSheet:
    @pytest.mark.parametrize(
        "total_row",
        [("Summe", 17.5), ("Summe fiche", 17.5), ("Gesamt", 23), ("Total", 17.5), ("Σ", 17.5)],
    )
    def test_rows_after_a_total_row_are_read(self, total_row):
        result = _parse(_rows(HEADER + FIRST + [total_row] + REST))
        assert result["total_points"] == 23
        assert len(_steps(result)) == 35
        assert total_row[0] not in _titles(result)
        # The total row was a subtotal: the sheet states no final total.
        assert result["declared_total"] is None
        assert "total_mismatch" not in _codes(result)

    def test_control_without_a_total_row(self):
        result = _parse(_rows(HEADER + FIRST + REST))
        assert result["total_points"] == 23
        assert len(_steps(result)) == 35

    def test_the_last_three_sections_keep_their_items(self):
        result = _parse(_rows(HEADER + FIRST + [("Summe", 17.5)] + REST))
        titles = _titles(result)
        for title in ("Premier élément de la question", "Règle de compétence", "Visa du dispositif"):
            assert title in titles


class TestTotalRowsAreNeverSteps:
    @pytest.mark.parametrize(
        "text",
        [
            "Summe",
            "Summe fiche",
            "Summe Teil A:",
            "Gesamt",
            "Gesamt-BE",
            "Gesamtpunkte",
            "Gesamtpunktzahl",
            "Gesamtsumme",
            "Total",
            "Total:",
            "Σ",
        ],
    )
    def test_total_row_variants(self, text):
        result = _parse(
            [{"A": "I. Erster Punkt", "B": 2}, {"A": "II. Zweiter Punkt", "B": 3}, {"A": text, "B": 5}]
        )
        assert [s["title"] for s in _steps(result)] == ["Erster Punkt", "Zweiter Punkt"]
        assert result["declared_total"] == 5
        assert "total_mismatch" not in _codes(result)

    @pytest.mark.parametrize("text", ["Gesamtwürdigung", "Summenbildung", "Totalschaden"])
    def test_words_that_only_start_like_a_total_stay_steps(self, text):
        result = _parse(
            [{"A": "I. Erster Punkt", "B": 2}, {"A": "II. Zweiter Punkt", "B": 1}, {"A": text, "B": 3}]
        )
        assert text in [s["title"] for s in _steps(result)]

    @pytest.mark.parametrize(
        "text, points",
        [
            ("Total des préjudices", 2),
            ("Total ou partiel", 1),
            ("Zwischensumme", 1),
            ("Sous-total", 1),
            ("Σ Teil A", 1),
        ],
    )
    def test_only_the_listed_total_forms_are_totals(self, text, points):
        result = _parse(
            [{"A": "I. Erster Punkt", "B": 2}, {"A": text, "B": points}, {"A": "III. Dritter", "B": 1}]
        )
        steps = {s["title"]: s["max_score"] for s in _steps(result)}
        assert steps[text] == points
        assert result["total_points"] == 3 + points

    def test_a_final_total_that_differs_is_reported_with_its_values(self):
        result = _parse([{"A": "I. a", "B": 1}, {"A": "II. b", "B": 2}, {"A": "Summe fiche", "B": 4}])
        warning = _warning(result, "total_mismatch")
        assert warning["declared"] == 4
        assert warning["computed"] == 3
        assert result["declared_total"] == 4

    def test_text_below_the_final_total_is_not_a_hint(self):
        result = _parse(
            [
                {"A": "I. a", "B": 1},
                {"A": "II. b", "B": 2},
                {"A": "Summe", "B": 3},
                {"A": "Bearbeitungszeit fünf Stunden"},
            ]
        )
        assert result["declared_total"] == 3
        assert all(not n.get("hints") for n in result["structure"]["nodes"])

    def test_held_rows_are_read_in_order_when_the_outline_goes_on(self):
        result = _parse(
            [
                {"A": "I. a", "B": 1},
                {"A": "Summe", "B": 1},
                {"A": "ein Hinweis zum nächsten Punkt"},
                {"A": "II. b", "B": 2},
            ]
        )
        assert [s["title"] for s in _steps(result)] == ["a", "b"]
        assert result["declared_total"] is None

    def test_a_grade_key_after_the_total_ends_the_outline(self):
        result = _parse(
            [
                {"A": "I. a", "B": 1},
                {"A": "II. b", "B": 2},
                {"A": "Gesamt", "B": 3},
                {"A": "sehr gut", "B": 3},
                {"A": "ausreichend", "B": 1.5},
            ]
        )
        assert [s["title"] for s in _steps(result)] == ["a", "b"]
        assert result["declared_total"] == 3

    def test_a_range_after_the_total_ends_the_outline(self):
        result = _parse(
            [
                {"A": "I. a", "B": 1},
                {"A": "Gesamt", "B": 1},
                {"A": "18 Punkte", "B": "0-1"},
                {"A": "17 Punkte", "B": 1},
            ]
        )
        assert [s["title"] for s in _steps(result)] == ["a"]
        assert "points_invalid" not in _codes(result)

    @pytest.mark.parametrize("trailer", ["Note", "Gesamtnote", "Ergibt"])
    def test_a_trailer_with_a_value_after_the_final_total_ends_the_outline(self, trailer):
        result = _parse(
            [
                {"A": "1. a", "B": 10},
                {"A": "2. b", "B": 13},
                {"A": "Gesamt", "B": 23},
                {"A": trailer, "B": 12},
            ]
        )
        assert [s["title"] for s in _steps(result)] == ["a", "b"]
        assert result["total_points"] == 23
        assert result["declared_total"] == 23

    def test_a_trailer_after_a_mismatching_total_keeps_the_warning(self):
        result = _parse(
            [
                {"A": "1. a", "B": 10},
                {"A": "2. b", "B": 13},
                {"A": "Gesamt", "B": 25},
                {"A": "Note", "B": 12},
            ]
        )
        assert result["declared_total"] == 25
        warning = _warning(result, "total_mismatch")
        assert warning["declared"] == 25
        assert warning["computed"] == 23

    def test_a_range_in_the_text_column_after_the_total_ends_the_outline(self):
        result = _parse(
            [
                {"A": "I. a", "B": 15},
                {"A": "II. b", "B": 8},
                {"A": "Gesamt", "B": 23},
                {"A": "95-100", "B": 18},
                {"A": "89-94", "B": 17},
            ]
        )
        assert [s["title"] for s in _steps(result)] == ["a", "b"]
        assert result["total_points"] == 23
        assert result["declared_total"] == 23


class TestIgnoredColumnBlocks:
    def test_a_second_column_block_is_reported(self):
        rows = []
        first, rest = HEADER + FIRST, REST
        for i in range(len(first)):
            row = {}
            text, points = first[i]
            row["A"] = text
            if points is not None:
                row["B"] = points
            if i < len(rest):
                text, points = rest[i]
                row["D"] = text
                if points is not None:
                    row["E"] = points
            rows.append(row)
        result = _parse(rows)
        # Still only the first block is read, but no longer silently.
        assert result["total_points"] == 17.5
        warning = _warning(result, "columns_ignored")
        assert warning["column"] == "D"
        assert warning["read_column"] == "A"
        assert warning["rows"] == 10

    def test_a_remarks_column_is_not_a_block(self):
        result = _parse(
            [
                {"A": "I. a", "B": 1, "C": "nur kurz"},
                {"A": "II. b", "B": 2, "C": "ausführlich"},
                {"A": "III. c", "B": 3, "C": "Schwerpunkt"},
            ]
        )
        assert "columns_ignored" not in _codes(result)

    def test_a_graded_copy_column_is_not_a_block(self):
        result = _parse(
            [
                {"A": "Gliederung", "B": "max. BE", "C": "Ihre BE"},
                {"A": "I. a", "B": 1, "C": 1},
                {"A": "II. b", "B": 2, "C": 1.5},
                {"A": "III. c", "B": 3, "C": 0.5},
            ]
        )
        assert "columns_ignored" not in _codes(result)

    def test_docx_second_column_block_is_reported(self):
        table = [[[a], [b], [c], [d]] for a, b, c, d in (
            ("I. a", "1", "IV. d", "1"),
            ("II. b", "2", "V. e", "2"),
            ("III. c", "3", "VI. f", "3"),
        )]
        result = parse_rubric_file("bogen.docx", make_docx([table]))
        warning = _warning(result, "columns_ignored")
        assert warning["column"] == "3"


class TestIgnoredWorksheets:
    def test_a_second_worksheet_is_reported(self):
        result = _parse(_rows(HEADER + FIRST), extra_sheets=[("Teil 2", _rows(REST))])
        assert result["total_points"] == 17.5
        warning = _warning(result, "sheets_ignored")
        assert warning["sheets"] == ["Teil 2"]
        assert warning["read_sheet"] == "Tabelle1"

    def test_a_worksheet_without_points_is_not_reported(self):
        result = _parse(
            _rows(HEADER + FIRST),
            extra_sheets=[("Notizen", [{"A": "nur eine Notiz"}, {"A": "noch eine"}])],
        )
        assert "sheets_ignored" not in _codes(result)
