"""Requirements of a step (core 2.51).

A step of a Bewertungsbogen outline may list the single performances it is
made of, each with its own Bewertungseinheiten on the half-point grid. The
key is optional: a sheet without requirements validates, normalizes, renders
and grades exactly as before.
"""

import copy
from types import SimpleNamespace

import pytest

from rubric_structure import (
    MAX_HINT_LEN,
    MAX_REQUIREMENTS_PER_STEP,
    REQUIREMENT_DEFINITION_RULE,
    REQUIREMENT_STANDARD_RULE,
    checklist_spec_from_structure,
    criteria_from_structure,
    has_requirements,
    normalize_structure,
    render_structure_text,
    requirement_lines,
    rubric_checklist_spec,
    rubric_prompt_text,
    step_requirements,
    structure_without_guidance,
    validate_structure,
)
from task_rubric_service import structure_equal


def _req(text, points, standard=None, element=None):
    return {"text": text, "points": points, "standard": standard, "element": element}


def _structure():
    """One section, a step with three requirements (4 BE) and one with one."""
    return {
        "version": 1,
        "nodes": [
            {"id": "a", "level": 0, "kind": "section", "label": "A.", "title": "Zulässigkeit"},
            {
                "id": "s1", "level": 1, "kind": "step", "label": "I.", "title": "Gefahr",
                "max_score": 4, "emphasis": "schwerpunkt", "hints": ["Erwartete Leistung"],
                "requirements": [
                    _req("Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit", 1, element="definition"),
                    _req("Subsumiert die Tatsachen unter jedes Merkmal", 2.5, standard="folgerichtig"),
                    _req("Begründet das Ergebnis", 0.5),
                ],
            },
            {
                "id": "s2", "level": 1, "kind": "step", "label": "II.", "title": "Zuständigkeit",
                "max_score": 0.5, "requirements": [_req("Stellt die Zuständigkeit fest", 0.5)],
            },
        ],
    }


class TestValidation:
    def test_a_sheet_with_requirements_is_valid(self):
        assert validate_structure(_structure()) == []

    def test_a_sheet_without_the_key_is_what_it_always_was(self):
        plain = _structure()
        for node in plain["nodes"]:
            node.pop("requirements", None)
        assert validate_structure(plain) == []
        assert all("requirements" not in n for n in normalize_structure(plain)["nodes"])
        assert has_requirements(plain) is False
        assert checklist_spec_from_structure(plain) is None

    @pytest.mark.parametrize("empty", [None, []])
    def test_an_empty_list_is_no_requirement(self, empty):
        structure = _structure()
        structure["nodes"][1]["requirements"] = empty
        assert validate_structure(structure) == []
        assert "requirements" not in normalize_structure(structure)["nodes"][1]
        # One step without requirements: the sheet is graded as one number per step.
        assert has_requirements(structure) is False

    def test_the_requirements_must_add_up_to_the_step(self):
        structure = _structure()
        structure["nodes"][1]["max_score"] = 5
        assert validate_structure(structure) == [
            "node 2: the requirements add up to 4 BE, the step carries 5 BE"
        ]
        structure["nodes"][1]["requirements"][2]["points"] = 1.5
        assert validate_structure(structure) == []

    @pytest.mark.parametrize(
        "change, message",
        [
            ({"text": ""}, "node 2, requirement 1: text must be a non-empty string"),
            ({"text": "   "}, "node 2, requirement 1: text must be a non-empty string"),
            ({"text": 7}, "node 2, requirement 1: text must be a non-empty string"),
            ({"text": "x" * (MAX_HINT_LEN + 1)}, f"node 2, requirement 1: text exceeds {MAX_HINT_LEN} characters"),
            ({"points": 0}, "node 2, requirement 1: points must be a number > 0"),
            ({"points": -1}, "node 2, requirement 1: points must be a number > 0"),
            ({"points": "1"}, "node 2, requirement 1: points must be a number > 0"),
            ({"points": True}, "node 2, requirement 1: points must be a number > 0"),
            ({"points": float("nan")}, "node 2, requirement 1: points must be a number > 0"),
            ({"points": 0.75}, "node 2, requirement 1: points must be a multiple of 0.5"),
            ({"standard": "richtig"}, "node 2, requirement 1: standard must be null or one of folgerichtig"),
            ({"element": "argument"}, "node 2, requirement 1: element must be null or one of definition"),
        ],
    )
    def test_a_broken_requirement_is_named(self, change, message):
        structure = _structure()
        structure["nodes"][1]["requirements"][0].update(change)
        assert validate_structure(structure) == [message]

    def test_other_shapes(self):
        structure = _structure()
        structure["nodes"][1]["requirements"] = "Subsumtion"
        assert validate_structure(structure) == ["node 2: requirements must be a list"]
        structure["nodes"][1]["requirements"] = ["Subsumtion", _req("x", 4)]
        assert validate_structure(structure) == ["node 2, requirement 1: must be an object"]
        structure["nodes"][1]["max_score"] = 6.5
        structure["nodes"][1]["requirements"] = [_req(f"Teil {i}", 0.5) for i in range(MAX_REQUIREMENTS_PER_STEP + 1)]
        assert validate_structure(structure) == [f"node 2: more than {MAX_REQUIREMENTS_PER_STEP} requirements"]

    def test_a_section_carries_none(self):
        structure = _structure()
        structure["nodes"][0]["requirements"] = [_req("x", 1)]
        assert validate_structure(structure) == ["node 1: section nodes carry no requirements"]
        structure["nodes"][0]["requirements"] = []
        assert validate_structure(structure) == []


class TestNormalization:
    def test_requirements_are_cleaned_and_kept_in_order(self):
        structure = _structure()
        structure["nodes"][1]["requirements"][1].update(text="  Subsumiert  ", points=2.50, extra="weg")
        nodes = normalize_structure(structure)["nodes"]
        assert nodes[1]["requirements"] == [
            _req("Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit", 1, element="definition"),
            _req("Subsumiert", 2.5, standard="folgerichtig"),
            _req("Begründet das Ergebnis", 0.5),
        ]
        assert isinstance(nodes[1]["requirements"][0]["points"], int)
        assert nodes[2]["requirements"] == [_req("Stellt die Zuständigkeit fest", 0.5)]

    def test_normalizing_twice_changes_nothing(self):
        once = normalize_structure(_structure())
        assert normalize_structure(once) == once

    def test_a_requirement_edit_is_a_content_change(self):
        base = _structure()
        assert structure_equal(base, copy.deepcopy(base))
        for change in ({"text": "Anders"}, {"points": 1.5}, {"standard": "folgerichtig"}, {"element": None}):
            other = copy.deepcopy(base)
            other["nodes"][1]["requirements"][0].update(change)
            assert not structure_equal(base, other), change
        without = copy.deepcopy(base)
        without["nodes"][2].pop("requirements")
        assert not structure_equal(base, without)

    def test_step_requirements_reads_any_shape(self):
        assert step_requirements(None) == [] and step_requirements({"requirements": "x"}) == []
        assert step_requirements({"requirements": [_req("a", 1), "b"]}) == [_req("a", 1)]


class TestRendering:
    def test_one_line_per_requirement_with_its_worth_and_marks(self):
        assert requirement_lines(_structure()["nodes"][1]["requirements"]) == [
            "- [1] Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit (1 BE; Definition)",
            "- [2] Subsumiert die Tatsachen unter jedes Merkmal (2.5 BE; folgerichtig)",
            "- [3] Begründet das Ergebnis (0.5 BE)",
        ]
        assert requirement_lines(None) == [] and requirement_lines([]) == []

    def test_the_outline_text_lists_them_and_explains_the_marks(self):
        text = render_structure_text(normalize_structure(_structure()), 4.5)
        assert text.splitlines() == [
            "BEWERTUNGSBOGEN (insgesamt 4.5 BE; halbe BE zulässig)",
            "A. Zulässigkeit",
            "  I. Gefahr (4 BE) SCHWERPUNKT [Schlüssel: s01_gefahr]",
            "    – Hinweis: Erwartete Leistung",
            "    Anforderungen:",
            "    - [1] Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit (1 BE; Definition)",
            "    - [2] Subsumiert die Tatsachen unter jedes Merkmal (2.5 BE; folgerichtig)",
            "    - [3] Begründet das Ergebnis (0.5 BE)",
            "  II. Zuständigkeit (0.5 BE) [Schlüssel: s02_zustaendigkeit]",
            "    Anforderungen:",
            "    - [1] Stellt die Zuständigkeit fest (0.5 BE)",
            "",
            REQUIREMENT_STANDARD_RULE,
            REQUIREMENT_DEFINITION_RULE,
        ]

    def test_a_mark_is_explained_only_where_it_occurs(self):
        structure = _structure()
        structure["nodes"][1]["requirements"][0]["element"] = None
        text = render_structure_text(normalize_structure(structure), 4.5)
        assert REQUIREMENT_STANDARD_RULE in text and REQUIREMENT_DEFINITION_RULE not in text
        structure["nodes"][1]["requirements"][1]["standard"] = None
        text = render_structure_text(normalize_structure(structure), 4.5)
        assert "Vermerk" not in text and not text.endswith("\n")

    def test_the_two_rules(self):
        # The extended generator's own rendering ends with the same sentences.
        assert REQUIREMENT_STANDARD_RULE == (
            'Anforderungen mit dem Vermerk "folgerichtig" werden auf der Grundlage der eigenen früheren '
            "Entscheidungen der Bearbeitung beurteilt, alle übrigen nach der zutreffenden Rechtslage."
        )
        assert REQUIREMENT_DEFINITION_RULE == (
            'Anforderungen mit dem Vermerk "Definition" sind erfüllt, wenn die Bearbeitung alle nummerierten '
            "Kernelemente wiedergibt, gleich in welcher Formulierung. Der Wortlaut der Musterlösung wird nicht "
            "verlangt, und eine anerkannte andere Fassung genügt."
        )

    def test_the_key_block_still_closes_the_mirror(self):
        text = render_structure_text(normalize_structure(_structure()), 4.5, include_grade_scale=True)
        assert text.index(REQUIREMENT_DEFINITION_RULE) < text.index("NOTENSCHLÜSSEL")

    def test_the_step_judge_reads_them_in_the_criteria(self):
        criteria = criteria_from_structure(normalize_structure(_structure()))
        rubric = criteria["s01_gefahr"]["rubric"].splitlines()
        assert rubric[-4:] == [
            "Anforderungen (volle 4 BE, wenn alle erfüllt):",
            "- [1] Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit (1 BE; Definition)",
            "- [2] Subsumiert die Tatsachen unter jedes Merkmal (2.5 BE; folgerichtig)",
            "- [3] Begründet das Ergebnis (0.5 BE)",
        ]
        # The hint list a grader sees stays the hints.
        assert criteria["s01_gefahr"]["description"] == "Erwartete Leistung"
        assert criteria["s01_gefahr"]["max_score"] == 4

    def test_a_solver_without_the_reference_keeps_worth_and_marks_but_no_text(self):
        bare = structure_without_guidance(normalize_structure(_structure()))
        assert bare["nodes"][1]["hints"] == []
        assert bare["nodes"][1]["requirements"] == [
            _req("", 1, element="definition"), _req("", 2.5, standard="folgerichtig"), _req("", 0.5),
        ]
        assert "Subsumiert" not in repr(bare) and "Definiert" not in repr(bare)
        # A sheet without requirements gains no key.
        plain = _structure()
        for node in plain["nodes"]:
            node.pop("requirements", None)
        assert all("requirements" not in n for n in structure_without_guidance(plain)["nodes"])


class TestScoringData:
    def test_the_outline_yields_what_the_requirement_judge_grades_against(self):
        spec = checklist_spec_from_structure(normalize_structure(_structure()))
        assert set(spec) == {"version", "source", "total_points", "order", "steps", "loesungsweg_steps",
                             "weichenstellungen", "arbeitsergebnisse", "hilfsgutachten"}
        assert spec["source"] == "structure" and spec["total_points"] == 4.5
        assert spec["order"] == ["s01_gefahr", "s02_zustaendigkeit"]
        first = spec["steps"]["s01_gefahr"]
        assert (first["name"], first["max_score"], first["step_id"]) == ("Gefahr", 4.0, "n2")
        assert first["anforderungen"] == [
            {"key": "s01_gefahr__b1", "id": None,
             "text": "Definiert die konkrete Gefahr: (1) Sachlage, (2) Wahrscheinlichkeit", "share": 0.25,
             "punkte": 1, "massstab": "richtig", "element": "definition"},
            {"key": "s01_gefahr__b2", "id": None, "text": "Subsumiert die Tatsachen unter jedes Merkmal",
             "share": 0.625, "punkte": 2.5, "massstab": "folgerichtig", "element": None},
            {"key": "s01_gefahr__b3", "id": None, "text": "Begründet das Ergebnis", "share": 0.125,
             "punkte": 0.5, "massstab": "richtig", "element": None},
        ]
        assert sum(b["share"] for b in first["anforderungen"]) == 1.0
        # An outline knows no alternative paths and no auxiliary parts.
        assert spec["weichenstellungen"] == [] and spec["loesungsweg_steps"] == {}
        assert spec["hilfsgutachten"] == {"verlangt": False, "wortlaut": None}
        assert spec["arbeitsergebnisse"][0]["step_keys"] == spec["order"]

    @pytest.mark.parametrize("structure", [None, "x", {}, {"version": 1, "nodes": []}])
    def test_no_spec_for_what_is_not_a_valid_outline(self, structure):
        assert checklist_spec_from_structure(structure) is None

    def test_no_spec_for_an_invalid_outline_with_requirements(self):
        structure = _structure()
        structure["nodes"][1]["max_score"] = 9  # the requirements no longer add up
        assert checklist_spec_from_structure(structure) is None


def _row(**metadata):
    structure = normalize_structure(_structure())
    return SimpleNamespace(
        id="r1", structure=structure, criteria=criteria_from_structure(structure), total_points=4.5,
        title=None, grade_scale=None, generation_metadata=metadata or None,
    )


class TestRowScoringData:
    STORED = {"version": 1, "total_points": 100.0, "order": ["x"], "steps": {}, "weichenstellungen": [{"id": "W1"}]}

    def test_a_generated_row_brings_its_own_spec(self):
        row = _row(checklist_spec=self.STORED, rendered_text="BEWERTUNGSBOGEN …")
        assert rubric_checklist_spec(row) is self.STORED

    @pytest.mark.parametrize(
        "metadata",
        [
            # An edit dropped the text the spec was written with.
            {"checklist_spec": STORED},
            {"checklist_spec": STORED, "rendered_text": "   "},
            # A row edited before the edit also dropped the spec.
            {"checklist_spec": STORED, "rendered_text": "alt", "rendered_text_invalidated_by_edit": True},
            {"checklist_spec": "kaputt", "rendered_text": "BEWERTUNGSBOGEN"},
            {},
        ],
    )
    def test_any_other_row_is_graded_by_its_outline(self, metadata):
        spec = rubric_checklist_spec(_row(**metadata))
        assert spec["source"] == "structure" and spec["order"] == ["s01_gefahr", "s02_zustaendigkeit"]

    def test_a_row_without_requirements_has_none(self):
        row = _row()
        for node in row.structure["nodes"]:
            node.pop("requirements", None)
        assert rubric_checklist_spec(row) is None
        assert rubric_checklist_spec(SimpleNamespace(structure=None, generation_metadata=None)) is None


class TestJudgeText:
    def test_a_generated_sheet_has_one_text_per_judge_lane(self):
        row = _row(rendered_text="Jeder Lösungsweg hat eigene Schlüssel", rendered_text_replace="auf die ersetzten Schritte")
        assert rubric_prompt_text(row) == "Jeder Lösungsweg hat eigene Schlüssel"
        assert rubric_prompt_text(row, alternatives="branch") == "Jeder Lösungsweg hat eigene Schlüssel"
        assert rubric_prompt_text(row, alternatives="replace") == "auf die ersetzten Schritte"

    def test_a_row_with_one_text_reads_it_in_both_lanes(self):
        row = _row(rendered_text="ein Text")
        assert rubric_prompt_text(row, alternatives="replace") == "ein Text"
        blank = _row(rendered_text="ein Text", rendered_text_replace="  ")
        assert rubric_prompt_text(blank, alternatives="replace") == "ein Text"

    def test_without_a_stored_text_the_outline_is_rendered_with_its_requirements(self):
        # The second text alone never stands in: both are dropped together on an edit.
        row = _row(rendered_text_replace="veraltet")
        for alternatives in ("branch", "replace"):
            text = rubric_prompt_text(row, alternatives=alternatives)
            assert text.startswith("BEWERTUNGSBOGEN (insgesamt 4.5 BE")
            assert "- [2] Subsumiert die Tatsachen unter jedes Merkmal (2.5 BE; folgerichtig)" in text
