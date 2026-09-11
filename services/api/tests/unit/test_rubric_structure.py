"""Unit tests for ``services/shared/rubric_structure.py`` (pure, pydantic-free).

Pins the Bewertungsbogen structure contract: validation rules, normalization
(ids + keys regenerated), the derived flat criteria, the legacy lift, the
prompt/mirror renderings and the Notenpunkte math — including the byte
equivalence with the old Falllösung grade table on a 100-point total.
"""

from __future__ import annotations

import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from rubric_structure import (  # noqa: E402
    DEFAULT_GRADE_THRESHOLDS,
    MAX_NODES,
    STEP_KEY_PATTERN,
    criteria_from_structure,
    effective_grade_scale,
    format_points,
    grade_for_rubric,
    grade_from_points,
    iter_steps,
    mirror_rubric_into_task_data,
    normalize_grade_scale,
    normalize_structure,
    render_flat_criteria_text,
    render_grade_scale_text,
    render_structure_text,
    rubric_prompt_text,
    slugify_step_key,
    structure_from_flat_criteria,
    total_points_from_structure,
    validate_grade_scale,
    validate_structure,
)

SAMPLE = {
    "version": 1,
    "nodes": [
        {"id": "a", "level": 0, "kind": "section", "label": "A.", "title": "Zulässigkeit", "note": "insgesamt 21 BE"},
        {"id": "b", "level": 1, "kind": "step", "label": "I.", "title": "Eröffnung des Verwaltungsrechtswegs", "max_score": 1},
        {"id": "c", "level": 1, "kind": "section", "label": "II.", "title": "Statthafte Klageart"},
        {"id": "d", "level": 2, "kind": "step", "label": "1.", "title": "Anfechtungsklage", "max_score": 0.5, "hints": ["Regelung (+)", ""]},
        {"id": "e", "level": 0, "kind": "section", "label": "B.", "title": "Begründetheit"},
        {
            "id": "f", "level": 1, "kind": "step", "label": "b)", "title": "Maßnahmerichtung",
            "max_score": 10.0, "emphasis": "schwerpunkt", "hints": ["H1", " H2 "], "key": "client_key_ignored",
        },
    ],
}
COLLEAGUE_SCALE = {
    "unit": "BE",
    "thresholds": [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
    "rounding": "floor",
    "pass_grade": 4,
}
# The pre-existing Falllösung table (upper bounds) — the default scale must
# reproduce it exactly on a 100-point total.
FALLOESUNG_GRADE_TABLE = [
    (12, 0), (25, 1), (38, 2), (49, 3), (53, 4), (56, 5), (59, 6), (63, 7), (66, 8), (69, 9),
    (73, 10), (76, 11), (79, 12), (83, 13), (86, 14), (89, 15), (93, 16), (96, 17), (100, 18),
]


def _legacy_grade(total: float) -> int:
    for upper, grade in FALLOESUNG_GRADE_TABLE:
        if total <= upper:
            return grade
    return 18


def _step(title="Schritt", max_score=1, **extra):
    return {"id": extra.pop("id", "s"), "level": extra.pop("level", 0), "kind": "step", "label": "", "title": title, "max_score": max_score, **extra}


def _structure(*nodes):
    return {"version": 1, "nodes": list(nodes)}


# ---------------------------------------------------------------------------
# slugify_step_key
# ---------------------------------------------------------------------------


class TestSlugifyStepKey:
    def test_matches_extended_format(self):
        assert slugify_step_key("Anspruch entstanden (§ 433 II BGB)", 3) == "s03_anspruch_entstanden_433_ii_bgb"

    def test_umlauts_transliterated_before_ascii_strip(self):
        assert slugify_step_key("Eröffnung Größe Übung", 1) == "s01_eroeffnung_groesse_uebung"

    def test_empty_title_falls_back_to_schritt(self):
        assert slugify_step_key("", 7) == "s07_schritt"
        assert slugify_step_key("§§§", 12) == "s12_schritt"

    def test_capped_at_60_and_pattern(self):
        key = slugify_step_key("x" * 200, 100)
        assert len(key) <= 60
        assert STEP_KEY_PATTERN.match(key)
        assert key.startswith("s100_")


# ---------------------------------------------------------------------------
# validate_structure
# ---------------------------------------------------------------------------


class TestValidateStructure:
    def test_sample_is_valid(self):
        assert validate_structure(SAMPLE) == []

    @pytest.mark.parametrize(
        "structure, fragment",
        [
            ("nope", "must be an object"),
            ({"version": 2, "nodes": [_step()]}, "version"),
            ({"version": 1, "nodes": []}, "non-empty"),
            ({"version": 1}, "non-empty"),
            ({"version": 1, "nodes": [_step()] * (MAX_NODES + 1)}, "max 500"),
        ],
    )
    def test_top_level_errors(self, structure, fragment):
        errors = validate_structure(structure)
        assert any(fragment in e for e in errors), errors

    def test_first_node_must_be_level_zero_and_levels_may_not_skip(self):
        assert any("level 0" in e for e in validate_structure(_structure(_step(level=1))))
        errors = validate_structure(_structure(_step(id="a"), _step(id="b", level=2)))
        assert any("skips a depth" in e for e in errors)

    def test_duplicate_and_missing_ids(self):
        assert any("duplicate id" in e for e in validate_structure(_structure(_step(id="x"), _step(id="x"))))
        assert any("id must be" in e for e in validate_structure(_structure({**_step(), "id": ""})))

    def test_kind_label_title_note_rules(self):
        assert any("kind" in e for e in validate_structure(_structure({**_step(), "kind": "hint"})))
        assert any("label" in e for e in validate_structure(_structure(_step(label="x" * 21))))
        assert any("title" in e for e in validate_structure(_structure(_step(title="   "))))
        assert any("title exceeds" in e for e in validate_structure(_structure(_step(title="t" * 501))))
        assert any("note" in e for e in validate_structure(_structure(_step(note="n" * 501))))

    @pytest.mark.parametrize("score, fragment", [
        (None, "must be a number"), ("1", "must be a number"), (True, "must be a number"),
        (0, "> 0"), (-1, "> 0"), (0.25, "multiple of 0.5"), (1000.5, "exceeds 1000"),
        (float("nan"), "> 0"),
    ])
    def test_step_max_score_rules(self, score, fragment):
        errors = validate_structure(_structure(_step(max_score=score)))
        assert any(fragment in e for e in errors), errors

    def test_step_emphasis_and_hints_rules(self):
        assert any("emphasis" in e for e in validate_structure(_structure(_step(emphasis="wichtig"))))
        assert validate_structure(_structure(_step(emphasis=None))) == []
        assert any("hints must be a list" in e for e in validate_structure(_structure(_step(hints="h"))))
        assert any("more than 20" in e for e in validate_structure(_structure(_step(hints=["h"] * 21))))
        assert any("strings" in e for e in validate_structure(_structure(_step(hints=[1]))))
        assert any("exceeds 1000" in e for e in validate_structure(_structure(_step(hints=["h" * 1001]))))
        assert any("key must be a string" in e for e in validate_structure(_structure(_step(key=3))))

    def test_sections_carry_no_scores_keys_hints_or_emphasis(self):
        section = {"id": "s", "level": 0, "kind": "section", "label": "A.", "title": "T"}
        errors = validate_structure(_structure({**section, "max_score": 1}, _step(id="x")))
        assert any("no max_score" in e for e in errors)
        errors = validate_structure(_structure({**section, "key": "k"}, _step(id="x")))
        assert any("no key" in e for e in errors)
        errors = validate_structure(_structure({**section, "hints": ["h"]}, _step(id="x")))
        assert any("no hints" in e for e in errors)
        errors = validate_structure(_structure({**section, "emphasis": "schwerpunkt"}, _step(id="x")))
        assert any("no emphasis" in e for e in errors)

    def test_needs_at_least_one_step_but_leaf_sections_are_allowed(self):
        section = {"id": "s", "level": 0, "kind": "section", "label": "A.", "title": "T"}
        assert any("at least one step" in e for e in validate_structure(_structure(section)))
        assert validate_structure(_structure(_step(id="x"), {**section, "id": "leaf"})) == []

    def test_non_dict_node_reported(self):
        assert any("must be an object" in e for e in validate_structure(_structure("x", _step())))


# ---------------------------------------------------------------------------
# validate_grade_scale
# ---------------------------------------------------------------------------


class TestValidateGradeScale:
    def test_colleague_scale_valid(self):
        assert validate_grade_scale(COLLEAGUE_SCALE, 100) == []
        assert validate_grade_scale({"thresholds": COLLEAGUE_SCALE["thresholds"]}) == []

    def test_errors(self):
        assert validate_grade_scale("x") == ["grade_scale must be an object"]
        assert any("exactly 18" in e for e in validate_grade_scale({"thresholds": [1, 2]}))
        bad = {**COLLEAGUE_SCALE, "thresholds": [10, "x"] + COLLEAGUE_SCALE["thresholds"][2:]}
        assert any("[1] must be a number" in e for e in validate_grade_scale(bad))
        bad = {**COLLEAGUE_SCALE, "thresholds": [-1] + COLLEAGUE_SCALE["thresholds"][1:]}
        assert any(">= 0" in e for e in validate_grade_scale(bad))
        bad = {**COLLEAGUE_SCALE, "thresholds": [10, 5] + COLLEAGUE_SCALE["thresholds"][2:]}
        assert any("lower than its predecessor" in e for e in validate_grade_scale(bad))
        assert any("exceeds the total" in e for e in validate_grade_scale(COLLEAGUE_SCALE, 72.5))
        assert any("rounding" in e for e in validate_grade_scale({**COLLEAGUE_SCALE, "rounding": "up"}))
        assert any("pass_grade" in e for e in validate_grade_scale({**COLLEAGUE_SCALE, "pass_grade": 19}))
        assert any("pass_grade" in e for e in validate_grade_scale({**COLLEAGUE_SCALE, "pass_grade": True}))
        assert any("max_points" in e for e in validate_grade_scale({**COLLEAGUE_SCALE, "max_points": 0}))
        assert any("unit" in e for e in validate_grade_scale({**COLLEAGUE_SCALE, "unit": "u" * 21}))


# ---------------------------------------------------------------------------
# normalize / derive
# ---------------------------------------------------------------------------


class TestNormalizeStructure:
    def test_ids_keys_and_coercions(self):
        normalized = normalize_structure(SAMPLE)
        nodes = normalized["nodes"]
        assert [n["id"] for n in nodes] == ["n1", "n2", "n3", "n4", "n5", "n6"]
        steps = [n for n in nodes if n["kind"] == "step"]
        # Keys ALWAYS regenerated from (title, step ordinal): the client key is ignored.
        assert [s["key"] for s in steps] == [
            "s01_eroeffnung_des_verwaltungsrechtswegs",
            "s02_anfechtungsklage",
            "s03_massnahmerichtung",
        ]
        assert steps[2]["max_score"] == 10 and isinstance(steps[2]["max_score"], int)
        assert steps[1]["max_score"] == 0.5
        assert steps[1]["hints"] == ["Regelung (+)"]  # empty hint dropped
        assert steps[2]["hints"] == ["H1", "H2"]  # trimmed
        assert steps[0]["emphasis"] is None and steps[2]["emphasis"] == "schwerpunkt"
        assert nodes[0]["note"] == "insgesamt 21 BE" and nodes[2]["note"] is None
        assert "max_score" not in nodes[0] and "hints" not in nodes[0]
        assert validate_structure(normalized) == []

    def test_normalize_is_idempotent(self):
        once = normalize_structure(SAMPLE)
        assert normalize_structure(once) == once

    def test_total_and_iter_steps(self):
        assert total_points_from_structure(SAMPLE) == 11.5
        assert total_points_from_structure(_structure(_step(max_score=0.5), _step(id="b", max_score=0.5), _step(id="c", max_score=0.5))) == 1.5
        assert total_points_from_structure(_structure(_step(max_score=2), _step(id="b", max_score=3))) == 5
        assert isinstance(total_points_from_structure(_structure(_step(max_score=2))), int)
        assert [s["title"] for s in iter_steps(SAMPLE)] == ["Eröffnung des Verwaltungsrechtswegs", "Anfechtungsklage", "Maßnahmerichtung"]
        assert list(iter_steps(None)) == []

    def test_normalize_grade_scale_fills_defaults(self):
        assert normalize_grade_scale({"thresholds": [10.0, 20] + list(range(30, 46))}) == {
            "unit": "BE",
            "thresholds": [10, 20] + list(range(30, 46)),
            "rounding": "floor",
            "pass_grade": 4,
        }
        assert normalize_grade_scale({**COLLEAGUE_SCALE, "max_points": 100.0})["max_points"] == 100


class TestCriteriaFromStructure:
    def test_shape_and_prose(self):
        criteria = criteria_from_structure(normalize_structure(SAMPLE))
        assert list(criteria) == [
            "s01_eroeffnung_des_verwaltungsrechtswegs",
            "s02_anfechtungsklage",
            "s03_massnahmerichtung",
        ]
        first = criteria["s01_eroeffnung_des_verwaltungsrechtswegs"]
        assert first["name"] == "Eröffnung des Verwaltungsrechtswegs"
        assert first["description"] == ""
        assert first["max_score"] == 1
        assert first["rubric"] == (
            "Kontext: A. Zulässigkeit (insgesamt 21 BE)\n"
            "Gliederungspunkt: I. Eröffnung des Verwaltungsrechtswegs — max. 1 BE (halbe BE zulässig)"
        )
        nested = criteria["s02_anfechtungsklage"]
        assert nested["rubric"].startswith("Kontext: A. Zulässigkeit (insgesamt 21 BE) › II. Statthafte Klageart\n")
        assert "max. 0.5 BE" in nested["rubric"]
        assert nested["description"] == "Regelung (+)"
        assert "Hinweise:\n- Regelung (+)" in nested["rubric"]
        emphasised = criteria["s03_massnahmerichtung"]
        assert "Schwerpunkt der Klausur: ausführliche Prüfung erwartet." in emphasised["rubric"]
        assert emphasised["rubric"].endswith("Hinweise:\n- H1\n- H2")
        assert emphasised["description"] == "H1\nH2"
        assert emphasised["max_score"] == 10

    def test_keys_derived_when_missing(self):
        criteria = criteria_from_structure(_structure(_step(title="Kläger", max_score=0.5)))
        assert list(criteria) == ["s01_klaeger"]


class TestStructureFromFlatCriteria:
    def test_orders_by_prefix_and_lifts_hints(self):
        flat = {
            "s02_b": {"name": "B", "description": "d", "rubric": "r1\nr2", "max_score": 60},
            "s01_a": {"name": "A", "rubric": "x", "max_score": 40},
            "unscored": {"name": "U", "rubric": "no max"},
            "broken": "not-a-dict",
        }
        structure = structure_from_flat_criteria(flat)
        assert validate_structure(structure) == []
        nodes = structure["nodes"]
        assert [n["title"] for n in nodes] == ["A", "B"]
        assert all(n["level"] == 0 and n["kind"] == "step" and n["label"] == "" for n in nodes)
        assert nodes[1]["hints"] == ["d", "r1", "r2"]
        assert nodes[0]["key"] == "s01_a" and nodes[0]["max_score"] == 40
        # Round trip: the lifted structure regenerates equivalent criteria.
        regenerated = criteria_from_structure(normalize_structure(structure))
        assert [v["max_score"] for v in regenerated.values()] == [40, 60]

    def test_title_falls_back_to_key_and_insertion_order_without_prefixes(self):
        structure = structure_from_flat_criteria({"zeta": {"max_score": 1}, "alpha": {"max_score": 2}})
        assert [n["title"] for n in structure["nodes"]] == ["zeta", "alpha"]

    def test_empty_inputs(self):
        assert structure_from_flat_criteria(None) == {"version": 1, "nodes": []}
        assert structure_from_flat_criteria("x") == {"version": 1, "nodes": []}


# ---------------------------------------------------------------------------
# renderings
# ---------------------------------------------------------------------------


class TestRenderings:
    FLAT = {
        "s01_anspruch_entstanden": {
            "name": "Anspruch entstanden (§ 433 II BGB)",
            "description": "Prüfung der Anspruchsgrundlage",
            "rubric": "Volle Punkte bei vollständiger Herleitung",
            "max_score": 40,
        },
        "broken": "x",
    }

    def test_flat_rendering_is_the_legacy_shape(self):
        text = render_flat_criteria_text(self.FLAT)
        assert text == (
            "1. Anspruch entstanden (§ 433 II BGB) (40 Punkte) [Schlüssel: s01_anspruch_entstanden]\n"
            "   Prüfung der Anspruchsgrundlage\n"
            "   Volle Punkte bei vollständiger Herleitung"
        )
        assert render_flat_criteria_text(None) == ""

    def test_structure_rendering(self):
        normalized = normalize_structure(SAMPLE)
        text = render_structure_text(normalized, 11.5, None, title="Polizeirecht")
        lines = text.splitlines()
        assert lines[0] == "BEWERTUNGSBOGEN: Polizeirecht (insgesamt 11.5 BE; halbe BE zulässig)"
        assert lines[1] == "A. Zulässigkeit (insgesamt 21 BE)"
        assert lines[2] == "  I. Eröffnung des Verwaltungsrechtswegs (1 BE) [Schlüssel: s01_eroeffnung_des_verwaltungsrechtswegs]"
        assert lines[4] == "    1. Anfechtungsklage (0.5 BE) [Schlüssel: s02_anfechtungsklage]"
        assert lines[5] == "      – Hinweis: Regelung (+)"
        assert lines[7] == "  b) Maßnahmerichtung (10 BE) SCHWERPUNKT [Schlüssel: s03_massnahmerichtung]"
        assert "NOTENSCHLÜSSEL" not in text
        untitled = render_structure_text(normalized, None)
        assert untitled.startswith("BEWERTUNGSBOGEN (insgesamt 11.5 BE; halbe BE zulässig)")

    def test_structure_rendering_with_scale_block(self):
        text = render_structure_text(normalize_structure(SAMPLE), 100, COLLEAGUE_SCALE, include_grade_scale=True)
        assert "\nNOTENSCHLÜSSEL (BE → Notenpunkte): 0 NP unter 10 BE; 1 NP ab 10 BE; " in text
        assert "18 NP ab 96 BE" in text
        assert "Rundung: halbe BE werden abgerundet." in text
        assert text.endswith("Bestanden ab 4 Notenpunkten.")
        nearest = render_grade_scale_text(effective_grade_scale({**COLLEAGUE_SCALE, "rounding": "nearest"}, 100))
        assert "kaufmännisch" in nearest

    def test_rubric_prompt_text_precedence(self):
        structure = normalize_structure(SAMPLE)
        row = SimpleNamespace(
            generation_metadata={"rendered_text": "BEWERTUNGSBOGEN (100 Rohpunkte)"},
            structure=structure, criteria=self.FLAT, total_points=11.5, grade_scale=None, title="T",
        )
        assert rubric_prompt_text(row) == "BEWERTUNGSBOGEN (100 Rohpunkte)"
        row.generation_metadata = {"rendered_text": "  "}
        assert rubric_prompt_text(row).startswith("BEWERTUNGSBOGEN: T (insgesamt 11.5 BE")
        assert "NOTENSCHLÜSSEL" not in rubric_prompt_text(row)
        assert "NOTENSCHLÜSSEL" in rubric_prompt_text(row, include_grade_scale=True)
        row.structure = {"version": 1, "nodes": [{"kind": "step"}]}  # malformed → flat
        assert rubric_prompt_text(row).startswith("1. Anspruch entstanden")
        assert rubric_prompt_text(SimpleNamespace(criteria=None, generation_metadata=None)) == ""

    def test_mirror_into_task_data(self):
        from project_models import Task

        task = Task(id="t", project_id="p", data={"sachverhalt": "S"}, inner_id=1)
        row = SimpleNamespace(
            generation_metadata=None, structure=normalize_structure(SAMPLE), criteria={},
            total_points=11.5, grade_scale=COLLEAGUE_SCALE, title="T",
        )
        mirror_rubric_into_task_data(task, row)
        assert task.data["sachverhalt"] == "S"
        assert task.data["bewertungsbogen"].startswith("BEWERTUNGSBOGEN: T")
        assert "NOTENSCHLÜSSEL" in task.data["bewertungsbogen"]
        mirror_rubric_into_task_data(task, None)
        assert "bewertungsbogen" not in task.data
        mirror_rubric_into_task_data(task, None)  # no-op when absent
        assert task.data == {"sachverhalt": "S"}


# ---------------------------------------------------------------------------
# grades
# ---------------------------------------------------------------------------


class TestGrades:
    def test_default_scale_matches_falloesung_table_on_integers(self):
        for points in range(0, 101):
            grade, passed = grade_from_points(points, 100)
            assert grade == _legacy_grade(points), points
            assert passed is (grade >= 4)

    @pytest.mark.parametrize("points, expected", [(12, 0), (13, 1), (49, 3), (50, 4), (97, 18), (49.5, 3), (100, 18), (150, 18)])
    def test_default_pins(self, points, expected):
        assert grade_from_points(points, 100)[0] == expected

    @pytest.mark.parametrize("points, expected", [(39.5, (3, False)), (40, (4, True)), (72.5, (12, True)), (9.9, (0, False)), (96, (18, True))])
    def test_colleague_scale(self, points, expected):
        assert grade_from_points(points, 100, COLLEAGUE_SCALE) == expected

    def test_rounding_modes(self):
        assert grade_from_points(39.5, 100, {**COLLEAGUE_SCALE, "rounding": "ceil"}) == (4, True)
        assert grade_from_points(39.5, 100, {**COLLEAGUE_SCALE, "rounding": "nearest"}) == (4, True)
        assert grade_from_points(39.4, 100, {**COLLEAGUE_SCALE, "rounding": "nearest"}) == (3, False)
        assert grade_from_points(39.5, 100, {**COLLEAGUE_SCALE, "rounding": "none"}) == (3, False)
        assert grade_from_points(40.0, 100, {**COLLEAGUE_SCALE, "rounding": "none"}) == (4, True)

    def test_invalid_points(self):
        assert grade_from_points(None, 100) == (0, False)
        assert grade_from_points(float("nan"), 100) == (0, False)
        assert grade_from_points(float("inf"), 100) == (0, False)
        assert grade_from_points(-5, 100) == (0, False)
        assert grade_from_points("80", 100) == (0, False)

    def test_scaled_default_for_other_totals(self):
        scale = effective_grade_scale(None, 72.5)
        assert scale["source"] == "default"
        assert scale["thresholds"][3] == pytest.approx(36.25)
        assert scale["max_points"] == 72.5
        assert grade_from_points(72.5, 72.5) == (18, True)
        assert grade_from_points(36, 72.5) == (3, False)
        assert grade_from_points(37, 72.5) == (4, True)
        assert effective_grade_scale(None, None)["thresholds"] == DEFAULT_GRADE_THRESHOLDS
        assert effective_grade_scale(COLLEAGUE_SCALE, 100)["source"] == "rubric"
        assert effective_grade_scale({"thresholds": COLLEAGUE_SCALE["thresholds"]}, 100)["pass_grade"] == 4

    def test_grade_for_rubric_prefers_rubric_total_and_scale(self):
        row = SimpleNamespace(total_points=100, grade_scale=COLLEAGUE_SCALE)
        assert grade_for_rubric(row, 39.5, 80) == (3, False, "rubric")
        legacy = SimpleNamespace(total_points=100, grade_scale=None)
        assert grade_for_rubric(legacy, 80, 100) == (13, True, "default")
        no_total = SimpleNamespace()  # rows without the new columns
        assert grade_for_rubric(no_total, 40, 80) == (4, True, "default")
        assert grade_for_rubric(SimpleNamespace(total_points=0, grade_scale=None), 50, 100) == (4, True, "default")

    def test_format_points(self):
        assert format_points(1) == "1"
        assert format_points(0.5) == "0.5"
        assert format_points(72.5) == "72.5"
        assert format_points(9.425) == "9.425"
        assert format_points(None) == ""
        assert format_points("x") == "x"
        assert format_points(math.inf) == "inf"
