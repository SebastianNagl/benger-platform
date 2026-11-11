"""Grading a Bewertungsbogen per requirement in the product (core 2.51).

Three parts: the binary unit of ``checklist_scoring`` (one state per
requirement, points from met requirements only), the judge's switch into the
requirement-level lane when the sheet lists requirements
(``LLMJudgeEvaluator.bind_task_rubric``), and what the dispatch helpers hand
on (the sheet text that fits the lane, the row's details).
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation import checklist_scoring as cs  # noqa: E402
from ml_evaluation.llm_judge_evaluator import (  # noqa: E402
    RUBRIC_REQUIREMENT_UNIT,
    LLMJudgeEvaluator,
)
from rubric_structure import (  # noqa: E402
    checklist_spec_from_structure,
    criteria_from_structure,
    normalize_structure,
    rubric_checklist_spec,
    stored_checklist_spec,
)

ANSWER = (
    "Die öffentliche Sicherheit umfasst die Unversehrtheit der Rechtsordnung und die Rechtsgüter des Einzelnen. "
    "Hier droht ein Schaden für die Gesundheit der Anwohner, weil der Lärm die ganze Nacht anhält. "
    "Die Maßnahme ist geeignet und erforderlich."
)
Q_DEFINITION = "Die öffentliche Sicherheit umfasst die Unversehrtheit der Rechtsordnung"
Q_SUBSUMPTION = "Hier droht ein Schaden für die Gesundheit der Anwohner"
Q_PROPORTION = "Die Maßnahme ist geeignet und erforderlich"


def _verify(quote):
    return bool(quote) and quote in ANSWER


def _spec():
    """Two steps outside any fork, one replaced step and one step on another
    path; requirement BE on the half-point grid (20 BE in all)."""
    def step(sid, name, mx, points, fork=None):
        return {
            "step_id": sid, "name": name, "max_score": mx, "keine_punkte": "nichts",
            "anforderungen": [
                {"key": f"k_{sid}__b{i}", "id": None, "text": f"A{i}", "share": p / mx, "punkte": p,
                 "massstab": "richtig", "element": None}
                for i, p in enumerate(points, start=1)
            ],
            "weichenstellung": fork,
        }

    return {
        "version": 1, "total_points": 20.0,
        "order": ["s01_sicherheit", "s02_gefahr", "s03_verhaeltnis"],
        "steps": {
            "s01_sicherheit": step("S1", "Öffentliche Sicherheit", 4.0, [1.0, 2.5, 0.5]),
            "s02_gefahr": step("S2", "Gefahr", 6.0, [2.0, 4.0]),
            "s03_verhaeltnis": step("S3", "Verhältnismäßigkeit", 10.0, [5.0, 5.0], {"id": "W1", "loesungsweg": "musterloesung"}),
        },
        "loesungsweg_steps": {
            "s04_ermessen": step("W1-L1-S1", "Ermessen", 10.0, [10.0], {"id": "W1", "loesungsweg": "W1-L1"}),
        },
        "weichenstellungen": [{
            "id": "W1", "bezeichnung": "Verhältnismäßigkeit oder Ermessen", "budget": 10.0,
            "loesungswege": [{"id": "musterloesung", "step_keys": ["s03_verhaeltnis"]},
                             {"id": "W1-L1", "step_keys": ["s04_ermessen"]}],
        }],
    }


def _marks(*items):
    return {
        "anforderungen": {
            f"b{i}": {"evidence": quote, "status": status, "grund": grund}
            for i, (status, quote, grund) in enumerate(items, start=1)
        },
        "abweichender_weg": False, "fehlplatziert": False, "reason": "r",
    }


def _diagnosis(status="scored"):
    return {
        "assessment_status": status,
        "work_products": [],
        "supplementary_reviews": [{"subject": "Kein Hilfsgutachten", "requirement_basis": "Bearbeitervermerk",
                                   "status": "not_required", "assumption": None, "reason": "r"}],
        "error_chains": [], "review_reasons": [], "improvements": ["Definition vollständig wiedergeben"],
    }


def _judgment(declared="musterloesung", fork_quote=Q_PROPORTION):
    return {
        "scores": {
            "s01_sicherheit": _marks(("erfuellt", Q_DEFINITION, ""), ("erfuellt", Q_SUBSUMPTION, ""),
                                     ("nicht_erfuellt", "", "kein Ergebnis genannt")),
            "s02_gefahr": _marks(("erfuellt", "steht so nicht in der Bearbeitung", ""), ("unsicher", "", "Prognose unklar")),
            "s03_verhaeltnis": _marks(("erfuellt", Q_PROPORTION, ""), ("nicht_erfuellt", "", "Angemessenheit fehlt")),
            "s04_ermessen": _marks(("nicht_einschlaegig", "", "anderer Lösungsweg")),
        },
        "weichenstellungen": {"W1": {"gefolgter_loesungsweg": declared, "evidence": fork_quote, "reason": "r"}},
        "overall_assessment": "ok",
        **_diagnosis(),
    }


class TestBinaryUnit:
    def test_the_unit_is_one_of_the_score_units(self):
        assert "binary" in cs.SCORE_UNITS and cs.REQUIREMENT_UNITS == ("bullet", "binary")
        assert cs.BINARY_STATES == ("erfuellt", "nicht_erfuellt", "nicht_einschlaegig", "unsicher")
        assert cs.STATE_CHECK_FAILED == "zitat_nicht_belegt"
        cs.validate_options("binary", "branch", "declared")
        with pytest.raises(ValueError, match="replace"):
            cs.validate_options("binary", "replace", "declared")

    def test_the_three_step_unit_reads_as_before(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "2 = erfüllt; 1 = im Kern erbracht, aber unvollständig oder mit einem Fehler; 0 = nicht erfüllt" in prompt
        status = cs.build_schema(_spec(), "bullet", "branch")["properties"]["scores"]["properties"]["s01_sicherheit"][
            "properties"]["anforderungen"]["properties"]["b1"]
        assert status["properties"] == {"evidence": {"type": "string"}, "status": {"type": "integer", "enum": [0, 1, 2]}}

    def test_the_judge_is_told_the_four_states_and_that_only_met_earns(self):
        for text in (cs.system_prompt("binary", "branch"), cs.closing_rules("binary", "branch")):
            assert '"erfuellt" = die Bearbeitung erbringt die beschriebene Teilleistung vollständig' in text
            assert '"nicht_erfuellt" = sie erbringt sie nicht oder nur zum Teil' in text
            assert '"nicht_einschlaegig" = die Anforderung entfällt, weil eine vertretbare eigene Entscheidung der ' \
                   "Bearbeitung sie abschneidet" in text
            assert '"unsicher" = die Bearbeitung lässt sich für diese Anforderung nicht sicher beurteilen' in text
            assert "Eine Zwischenstufe gibt es nicht." in text
            assert "Punkte gibt es nur für erfüllte Anforderungen; die Maschine rechnet sie aus." in text
            assert 'Nenne für jeden anderen Status als "erfuellt" im Feld "grund" in wenigen Worten den Grund' in text
            assert "im Kern erbracht" not in text

    def test_the_schema_asks_for_quote_state_and_reason_per_requirement(self):
        schema = cs.build_schema(_spec(), "binary", "branch")
        steps = schema["properties"]["scores"]["properties"]
        assert list(steps) == ["s01_sicherheit", "s02_gefahr", "s03_verhaeltnis", "s04_ermessen"]
        b1 = steps["s01_sicherheit"]["properties"]["anforderungen"]["properties"]["b1"]
        assert b1["properties"] == {
            "evidence": {"type": "string"},
            "status": {"type": "string", "enum": ["erfuellt", "nicht_erfuellt", "nicht_einschlaegig", "unsicher"]},
            "grund": {"type": "string"},
        }
        assert b1["required"] == ["evidence", "status", "grund"] and b1["additionalProperties"] is False
        assert list(steps["s01_sicherheit"]["properties"]["anforderungen"]["properties"]) == ["b1", "b2", "b3"]
        assert "total_score" not in schema["properties"]

    def test_a_sheet_too_large_for_the_enum_budget_gets_plain_strings(self):
        spec = _spec()
        spec["steps"]["s01_sicherheit"]["anforderungen"] = [
            {"key": f"k{i}", "text": "A", "share": 1 / 260, "punkte": 4 / 260} for i in range(260)]
        status = cs.build_schema(spec, "binary", "branch")["properties"]["scores"]["properties"]["s01_sicherheit"][
            "properties"]["anforderungen"]["properties"]["b1"]["properties"]["status"]
        assert status == {"type": "string"}

    def test_points_come_from_met_requirements_with_a_quote_that_stands(self):
        result = cs.finalize(_judgment(), _spec(), "binary", "branch", "declared", _verify)
        scores = result["scores"]
        first = scores["s01_sicherheit"]["anforderungen"]
        assert first["b1"] == {
            "status": "erfuellt", "model_status": "erfuellt", "evidence": Q_DEFINITION, "evidence_verified": True,
            "grund": "", "max": 1.0, "score": 1.0,
        }
        assert (first["b2"]["status"], first["b2"]["score"]) == ("erfuellt", 2.5)
        assert first["b3"] == {
            "status": "nicht_erfuellt", "model_status": "nicht_erfuellt", "evidence": "", "evidence_verified": False,
            "grund": "kein Ergebnis genannt", "max": 0.5, "score": 0.0,
        }
        # Met by the judge, but the quote is not in the answer: a state of its
        # own, no points, and the judge's state stays beside it.
        failed = scores["s02_gefahr"]["anforderungen"]["b1"]
        assert (failed["status"], failed["model_status"], failed["score"], failed["max"]) == (
            "zitat_nicht_belegt", "erfuellt", 0.0, 2.0)
        assert scores["s02_gefahr"]["anforderungen"]["b2"]["status"] == "unsicher"
        assert [scores[k]["score"] for k in ("s01_sicherheit", "s02_gefahr", "s03_verhaeltnis")] == [3.5, 0.0, 5.0]
        assert result["total_score"] == 8.5 and result["total_max"] == 20.0
        # Every step's points are the sum of its met requirements, on the half-point grid.
        for key in ("s01_sicherheit", "s02_gefahr", "s03_verhaeltnis"):
            assert scores[key]["score"] == sum(i["score"] for i in scores[key]["anforderungen"].values())

    def test_the_readings_beside_the_verified_total(self):
        block = cs.finalize(_judgment(), _spec(), "binary", "branch", "declared", _verify)["checklist"]
        assert block["score_unit"] == "binary"
        assert block["totals"] == {"declared": 8.5, "best": 8.5}
        # The judge's own states, before the quote check: 2 BE more.
        assert block["totals_proposed"] == {"declared": 10.5, "best": 10.5}
        assert block["zeroed_items"] == 1
        # What the requirements of each final state are worth on the counted path.
        assert block["states"] == {
            "erfuellt": {"count": 3, "be": 8.5},
            "nicht_erfuellt": {"count": 2, "be": 5.5},
            "zitat_nicht_belegt": {"count": 1, "be": 2.0},
            "unsicher": {"count": 1, "be": 4.0},
        }
        assert block["unsettled_be"] == 6.0
        assert sum(s["be"] for s in block["states"].values()) == 20.0

    def test_much_unsettled_sends_the_script_to_a_person(self):
        result = cs.finalize(_judgment(), _spec(), "binary", "branch", "declared", _verify)
        # 6 of 20 BE are uncertain or without a quote that stands: above a tenth.
        assert result["assessment"]["assessment_status"] == "review_required"
        assert result["assessment"]["score_status"] == "provisional"
        assert result["assessment"]["aggregation_eligible"] is False
        assert result["assessment"]["review_reasons"] == [
            "Unsichere oder nicht belegte Anforderungen tragen zusammen 6 BE."
        ]
        # No point changes for it.
        assert result["total_score"] == 8.5

    def test_little_unsettled_stays_scored(self):
        judgment = _judgment()
        judgment["scores"]["s02_gefahr"] = _marks(("erfuellt", Q_SUBSUMPTION, ""), ("nicht_erfuellt", "", "fehlt"))
        judgment["scores"]["s01_sicherheit"]["anforderungen"]["b3"] = {"evidence": "", "status": "unsicher", "grund": "?"}
        result = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)
        assert result["checklist"]["unsettled_be"] == 0.5
        assert result["assessment"]["assessment_status"] == "scored"
        assert result["assessment"]["review_reasons"] == []

    def test_a_declared_other_path_without_a_quote_falls_back_and_is_flagged(self):
        judgment = _judgment(declared="W1-L1", fork_quote="steht nicht da")
        judgment["scores"]["s02_gefahr"] = _marks(("erfuellt", Q_SUBSUMPTION, ""), ("nicht_erfuellt", "", "fehlt"))
        result = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)
        decision = result["checklist"]["weichenstellungen"]["W1"]
        assert (decision["declared"], decision["declared_model"], decision["declared_fallback"]) == (
            "musterloesung", "W1-L1", True)
        assert result["assessment"]["assessment_status"] == "review_required"
        assert result["assessment"]["review_reasons"] == [
            "Erklärter anderer Lösungsweg ohne belegtes Zitat, gewertet wurde der Lösungsweg der Musterlösung: W1"
        ]

    def test_the_other_path_counts_when_it_is_declared_with_a_quote(self):
        judgment = _judgment(declared="W1-L1")
        judgment["scores"]["s04_ermessen"] = _marks(("erfuellt", Q_PROPORTION, ""))
        judgment["scores"]["s02_gefahr"] = _marks(("erfuellt", Q_SUBSUMPTION, ""), ("nicht_erfuellt", "", "fehlt"))
        result = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)
        assert result["checklist"]["weichenstellungen"]["W1"]["declared"] == "W1-L1"
        # 3.5 + 2 + the other path's 10; the replaced step's 5 do not count.
        assert result["total_score"] == 15.5
        states = result["checklist"]["states"]
        assert states["erfuellt"] == {"count": 4, "be": 15.5}
        # The counted path holds six requirements worth the sheet's 20 BE: the
        # two of the replaced step are not among them.
        assert sum(s["count"] for s in states.values()) == 6
        assert sum(s["be"] for s in states.values()) == 20.0

    @pytest.mark.parametrize("written, state", [
        ("erfüllt", "erfuellt"), ("ERFUELLT", "erfuellt"), (" Erfüllt ", "erfuellt"),
        ("Nicht erfüllt", "nicht_erfuellt"), ("nicht-erfuellt", "nicht_erfuellt"),
        ("nicht einschlägig", "nicht_einschlaegig"), ("Unsicher", "unsicher"),
    ])
    def test_another_spelling_of_a_state_reads_as_that_state(self, written, state):
        # Where the provider does not hold the judge to the four words.
        assert cs.binary_state(written) == (state, state)
        judgment = _judgment()
        judgment["scores"]["s01_sicherheit"]["anforderungen"]["b1"]["status"] = written
        item = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)[
            "scores"]["s01_sicherheit"]["anforderungen"]["b1"]
        assert (item["status"], item["model_status"]) == (state, state)
        assert item["score"] == (1.0 if state == "erfuellt" else 0.0)

    @pytest.mark.parametrize("value, kept, grund", [
        ("teilweise", "teilweise", "Status nicht erkannt: teilweise"),
        (2, "2", "Status nicht erkannt: 2"),
        (True, "True", "Status nicht erkannt: True"),
        (["erfuellt"], "['erfuellt']", "Status nicht erkannt: ['erfuellt']"),
        ({"a": 1}, "{'a': 1}", "Status nicht erkannt: {'a': 1}"),
        (None, "", "Kein Status angegeben"),
        ("   ", "", "Kein Status angegeben"),
    ])
    def test_a_word_that_names_no_state_is_uncertain_and_kept(self, value, kept, grund):
        # Not a judgment the code can count either way: no points, the BE
        # count as unsettled, and the row says what the judge wrote.
        judgment = _judgment()
        judgment["scores"]["s01_sicherheit"]["anforderungen"]["b1"]["status"] = value
        result = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)
        first = result["scores"]["s01_sicherheit"]
        assert first["anforderungen"]["b1"] == {
            "status": "unsicher", "model_status": kept, "evidence": Q_DEFINITION, "evidence_verified": True,
            "grund": grund, "max": 1.0, "score": 0.0,
        }
        assert first["score"] == 2.5
        assert result["checklist"]["unsettled_be"] == 7.0
        # The judge did not propose these points either.
        assert result["checklist"]["totals_proposed"]["declared"] == 9.5

    def test_the_judges_own_reason_stays_beside_an_unknown_word(self):
        judgment = _judgment()
        judgment["scores"]["s01_sicherheit"]["anforderungen"]["b1"].update(status="halb", grund=" nur angedeutet ")
        item = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)[
            "scores"]["s01_sicherheit"]["anforderungen"]["b1"]
        assert (item["status"], item["model_status"], item["grund"]) == ("unsicher", "halb", "nur angedeutet")

    def test_a_long_unknown_word_is_cut(self):
        assert cs.binary_state("x" * 200) == ("unsicher", "x" * 60)
        assert cs.binary_state(10 ** 80) == ("unsicher", str(10 ** 80)[:60])

    def test_a_requirement_is_worth_its_stated_points(self):
        # 7.5 of 11 BE as a share comes back off the half-point grid.
        share = 7.5 / 11
        assert 11 * share != 7.5
        assert cs.requirement_worth({"share": share, "punkte": 7.5}, 11.0) == 7.5
        # A spec without stated points (before checklist-6) keeps the share.
        assert cs.requirement_worth({"share": 0.25}, 4.0) == 1.0
        assert cs.requirement_worth({"share": None}, 4.0) == 0.0
        # Points that are no number, or no usable one, are not stated points.
        for odd in (True, "2", None, float("nan"), float("inf"), -1):
            assert cs.requirement_worth({"share": 0.5, "punkte": odd}, 4.0) == 2.0

    def test_stated_points_keep_a_step_on_the_grid(self):
        spec = _spec()
        step = spec["steps"]["s02_gefahr"]
        step["max_score"] = 11.0
        step["anforderungen"][0].update(share=7.5 / 11, punkte=7.5)
        step["anforderungen"][1].update(share=3.5 / 11, punkte=3.5)
        spec["total_points"] = 25.0
        judgment = _judgment()
        judgment["scores"]["s02_gefahr"] = _marks(("erfuellt", Q_SUBSUMPTION, ""), ("nicht_erfuellt", "", "fehlt"))
        result = cs.finalize(judgment, spec, "binary", "branch", "declared", _verify)
        second = result["scores"]["s02_gefahr"]
        assert (second["anforderungen"]["b1"]["max"], second["anforderungen"]["b1"]["score"]) == (7.5, 7.5)
        assert second["raw_points"] == 7.5 and second["score"] == 7.5
        assert result["checklist"]["states"]["erfuellt"]["be"] == 16.0

    def test_not_applicable_earns_nothing_and_goes_to_a_person(self):
        # The answer's own decision cut the requirement off. It earns no
        # points here; whether that decision holds is the examiner's call.
        judgment = _judgment()
        judgment["scores"]["s02_gefahr"] = _marks(("erfuellt", Q_SUBSUMPTION, ""), ("nicht_erfuellt", "", "fehlt"))
        judgment["scores"]["s01_sicherheit"]["anforderungen"]["b3"] = {
            "evidence": "", "status": "nicht_einschlaegig", "grund": "Prüfung endet vorher"}
        result = cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify)
        block = result["checklist"]
        assert block["states"]["nicht_einschlaegig"] == {"count": 1, "be": 0.5}
        assert (block["not_applicable_be"], block["unsettled_be"]) == (0.5, 0)
        assert result["scores"]["s01_sicherheit"]["anforderungen"]["b3"]["score"] == 0.0
        assert result["assessment"]["assessment_status"] == "review_required"
        assert result["assessment"]["score_status"] == "provisional"
        assert result["assessment"]["review_reasons"] == [
            "Als entfallen eingestufte Anforderungen tragen zusammen 0,5 BE; "
            "sie bringen in dieser Bewertung keine Punkte."
        ]

    def test_not_applicable_on_a_path_that_is_not_counted_raises_no_flag(self):
        # The fixture marks the other path's step not applicable; the
        # counted path is the reference solution's.
        block = cs.finalize(_judgment(), _spec(), "binary", "branch", "declared", _verify)["checklist"]
        assert block["not_applicable_be"] == 0.0 and "nicht_einschlaegig" not in block["states"]

    def test_a_missing_requirement_is_asked_for_again(self):
        judgment = _judgment()
        del judgment["scores"]["s01_sicherheit"]["anforderungen"]["b2"]
        del judgment["scores"]["s02_gefahr"]
        assert cs.finalize(judgment, _spec(), "binary", "branch", "declared", _verify) == {
            "missing": ["s01_sicherheit.b2", "s02_gefahr"]}

    def test_a_step_without_requirements_cannot_be_scored_in_this_unit(self):
        spec = _spec()
        spec["steps"]["s02_gefahr"]["anforderungen"] = []
        with pytest.raises(cs.ChecklistSpecError, match="steps.s02_gefahr.anforderungen must list at least one"):
            cs.validate_spec(spec, "binary", "branch")
        cs.validate_spec(spec, "bullet", "branch")  # the three-step unit is as it was

    def test_the_key_map_names_the_requirements(self):
        note = cs.expected_output_note(_spec(), "binary", "branch")
        assert "- s01_sicherheit: Öffentliche Sicherheit (Anforderungen b1 bis b3)" in note

    def test_the_mock_judgment_has_the_schema_shape_and_scores(self):
        for unit in cs.SCORE_UNITS:
            alternatives = "branch" if unit in cs.REQUIREMENT_UNITS else "replace"
            body = cs.mock_judgment(_spec(), unit, alternatives, evidence=Q_DEFINITION, seed_text="x")
            schema = cs.build_schema(_spec(), unit, alternatives)
            assert set(body) == set(schema["properties"])
            assert set(body["scores"]) == set(schema["properties"]["scores"]["properties"])
            result = cs.finalize(body, _spec(), unit, alternatives, "declared", _verify)
            assert "missing" not in result and 0 <= result["total_score"] <= 20
        again = cs.mock_judgment(_spec(), "binary", "branch", evidence=Q_DEFINITION, seed_text="x")
        assert again == cs.mock_judgment(_spec(), "binary", "branch", evidence=Q_DEFINITION, seed_text="x")

    def test_build_schema_within_counts_the_callers_part(self):
        schema, enums = cs.build_schema_within(_spec(), "binary", "branch")
        assert enums is True and schema == cs.build_schema(_spec(), "binary", "branch")
        _, enums = cs.build_schema_within(_spec(), "binary", "branch", extra_enum_values=1000)
        assert enums is False
        _, enums = cs.build_schema_within(_spec(), "binary", "branch", extra_properties=5000)
        assert enums is False


# ---------------------------------------------------------------------------
# The judge's switch into the requirement-level lane
# ---------------------------------------------------------------------------

_TEMPLATE = "SV:\n{context}\n\nML:\n{ground_truth}\n\nBOGEN:\n{bewertungsbogen}\n\nBEARBEITUNG:\n{prediction}"


def _structure(with_requirements=True):
    nodes = [
        {"id": "a", "level": 0, "kind": "section", "label": "A.", "title": "Rechtmäßigkeit"},
        {"id": "s1", "level": 1, "kind": "step", "label": "I.", "title": "Öffentliche Sicherheit", "max_score": 4,
         "hints": ["Erwartete Leistung"],
         "requirements": [
             {"text": "Definiert die öffentliche Sicherheit: (1) Rechtsordnung, (2) Rechtsgüter", "points": 1,
              "element": "definition"},
             {"text": "Subsumiert die Tatsachen", "points": 2.5, "standard": "folgerichtig"},
             {"text": "Begründet das Ergebnis", "points": 0.5},
         ]},
        {"id": "s2", "level": 1, "kind": "step", "label": "II.", "title": "Gefahr", "max_score": 6,
         "requirements": [{"text": "Prognose", "points": 2}, {"text": "Schaden", "points": 4}]},
    ]
    if not with_requirements:
        for node in nodes:
            node.pop("requirements", None)
    return normalize_structure({"version": 1, "nodes": nodes})


def _row(with_requirements=True, **metadata):
    structure = _structure(with_requirements)
    return SimpleNamespace(
        id="rubric-1", structure=structure, criteria=criteria_from_structure(structure), total_points=10.0,
        title=None, grade_scale=None, generation_metadata=metadata or None, generator_model_id=None,
    )


def _judge():
    return LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.4-mini", custom_prompt_template=_TEMPLATE)


def _answer(ev, body):
    ev.ai_service.generate_structured.return_value = {
        "success": True, "content": json.dumps(body), "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "metadata": {"finish_reason": "stop"},
    }


def _outline_judgment():
    return {
        "scores": {
            "s01_oeffentliche_sicherheit": _marks(("erfuellt", Q_DEFINITION, ""), ("erfuellt", Q_SUBSUMPTION, ""),
                                                  ("nicht_erfuellt", "", "kein Ergebnis")),
            "s02_gefahr": _marks(("nicht_erfuellt", "", "fehlt"), ("erfuellt", Q_SUBSUMPTION, "")),
        },
        "overall_assessment": "ok",
        **_diagnosis(),
    }


class TestBinding:
    def test_a_sheet_with_requirements_is_graded_per_requirement(self):
        ev = _judge()
        row = _row()
        ev.bind_task_rubric(row, margin_notes=False)
        assert RUBRIC_REQUIREMENT_UNIT == "binary"
        assert ev.rubric_mode is True and ev.checklist is not None
        assert (ev.checklist["score_unit"], ev.checklist["alternatives"], ev.checklist["total_mode"]) == (
            "binary", "branch", "declared")
        assert ev.checklist["spec"] == checklist_spec_from_structure(row.structure)
        assert list(ev.custom_criteria) == ev.checklist["spec"]["order"] == ["s01_oeffentliche_sicherheit", "s02_gefahr"]
        assert ev.rubric_text_alternatives() == "branch"

    def test_a_sheet_without_requirements_is_graded_as_one_number_per_step(self):
        ev = _judge()
        ev.bind_task_rubric(_row(with_requirements=False))
        assert ev.rubric_mode is True and ev.checklist is None
        assert ev.rubric_text_alternatives() == "replace"

    def test_the_config_can_keep_one_number_per_step_or_ask_for_three_steps(self):
        ev = _judge()
        ev.bind_task_rubric(_row(), score_unit="step")
        assert ev.checklist is None and ev.rubric_text_alternatives() == "replace"
        ev.bind_task_rubric(_row(), score_unit="bullet")
        assert ev.checklist["score_unit"] == "bullet"

    def test_binding_again_starts_from_the_new_sheet(self):
        ev = _judge()
        ev.bind_task_rubric(_row())
        ev.bind_task_rubric(_row(with_requirements=False))
        assert ev.checklist is None

    @pytest.mark.parametrize("unit", ["rating", "replace", "quatsch"])
    def test_an_unknown_unit_is_logged_and_the_sheet_graded_per_step(self, unit, caplog):
        ev = _judge()
        with caplog.at_level("WARNING"):
            ev.bind_task_rubric(_row(), score_unit=unit)
        assert ev.checklist is None
        assert "requirement-level grading is not possible" in caplog.text and "rubric-1" in caplog.text

    def test_the_generators_own_scoring_data_comes_first(self):
        # It knows more than the outline does (the sheet's other solution
        # paths, the parts owed in an auxiliary opinion).
        stored = checklist_spec_from_structure(_structure())
        stored["steps"]["s02_gefahr"]["keine_punkte"] = "nur aus dem gespeicherten Bogen"
        row = _row(checklist_spec=stored, rendered_text="BEWERTUNGSBOGEN")
        assert stored_checklist_spec(row) is stored
        ev = _judge()
        ev.bind_task_rubric(row)
        assert ev.checklist["spec"]["steps"]["s02_gefahr"]["keine_punkte"] == "nur aus dem gespeicherten Bogen"
        assert rubric_checklist_spec(row) is stored

    @pytest.mark.parametrize("metadata", [
        {"checklist_spec": "x", "rendered_text": "BOGEN"},
        {"checklist_spec": None, "rendered_text": "BOGEN"},
        {"rendered_text": "   "},
        {"rendered_text": None},
        {},
        {"rendered_text": "BOGEN", "rendered_text_invalidated_by_edit": True},
    ])
    def test_scoring_data_counts_only_with_the_text_it_was_rendered_with(self, metadata):
        spec = checklist_spec_from_structure(_structure())
        row = _row(**{"checklist_spec": spec, **metadata})
        assert stored_checklist_spec(row) is None
        # The sheet is graded per requirement all the same, from its outline.
        assert rubric_checklist_spec(row) == checklist_spec_from_structure(row.structure)
        assert stored_checklist_spec(SimpleNamespace(generation_metadata="x")) is None
        assert stored_checklist_spec(SimpleNamespace()) is None

    def test_scoring_data_beside_an_outline_without_requirements_changes_nothing(self, caplog):
        # A sheet of an earlier generator version: requirements as hint
        # lines only, scoring data in the metadata. It was graded as one
        # number per step before core 2.51 and still is.
        stored = checklist_spec_from_structure(_structure())
        row = _row(with_requirements=False, checklist_spec=stored, rendered_text="BEWERTUNGSBOGEN")
        assert stored_checklist_spec(row) is stored and rubric_checklist_spec(row) is None
        ev = _judge()
        with caplog.at_level("WARNING"):
            ev.bind_task_rubric(row)
        assert ev.checklist is None and ev.rubric_mode is True
        assert ev.rubric_text_alternatives() == "replace"
        assert caplog.text == ""

    def test_a_sheet_with_one_step_without_requirements_is_graded_per_step(self):
        structure = _structure()
        del structure["nodes"][2]["requirements"]
        row = _row()
        row.structure = normalize_structure(structure)
        assert rubric_checklist_spec(row) is None
        ev = _judge()
        ev.bind_task_rubric(row)
        assert ev.checklist is None

    def test_scoring_data_that_does_not_match_the_sheet_gives_way_to_the_outline(self, caplog):
        stale = checklist_spec_from_structure(_structure())
        stale["order"] = ["s01_anders", "s02_gefahr"]
        stale["steps"]["s01_anders"] = stale["steps"].pop("s01_oeffentliche_sicherheit")
        row = _row(checklist_spec=stale, rendered_text="BEWERTUNGSBOGEN")
        ev = _judge()
        with caplog.at_level("WARNING"):
            ev.bind_task_rubric(row)
        assert ev.checklist["spec"] == checklist_spec_from_structure(row.structure)
        assert ev.rubric_text_alternatives() == "branch"
        assert "the stored scoring data cannot be used for requirement-level grading" in caplog.text
        assert "the scoring data and the sheet's steps differ" in caplog.text
        assert "grading per step" not in caplog.text

    @pytest.mark.parametrize("damage, logged", [
        (lambda spec: spec.update(total_points=None), "total_points"),
        # A number where the list of steps belongs.
        (lambda spec: spec.update(order=5), "TypeError: 'int' object is not iterable"),
        # Step keys that are no strings.
        (lambda spec: spec.update(order=[["s01_oeffentliche_sicherheit"], {"a": 1}]), "steps differ"),
        (lambda spec: spec.update(steps=7), "steps"),
        (lambda spec: spec["steps"].update(s02_gefahr="kaputt"), "s02_gefahr"),
        (lambda spec: spec["steps"]["s02_gefahr"].update(anforderungen=3), "s02_gefahr"),
        (lambda spec: spec.update(weichenstellungen="W1"), "weichenstellungen"),
    ])
    def test_broken_scoring_data_never_blocks_a_grading(self, damage, logged, caplog):
        broken = checklist_spec_from_structure(_structure())
        damage(broken)
        row = _row(checklist_spec=broken, rendered_text="BEWERTUNGSBOGEN")
        ev = _judge()
        with caplog.at_level("WARNING"):
            ev.bind_task_rubric(row)
        # The outline's own data takes over.
        assert ev.rubric_mode is True
        assert ev.checklist["spec"] == checklist_spec_from_structure(row.structure)
        assert "the stored scoring data cannot be used" in caplog.text and logged in caplog.text

    def test_when_no_scoring_data_can_be_used_the_sheet_is_graded_per_step(self, caplog):
        row = _row()
        ev = _judge()
        with patch.object(ev, "configure_checklist", side_effect=TypeError("kaputt")), caplog.at_level("WARNING"):
            ev.bind_task_rubric(row)
        assert ev.checklist is None and ev.rubric_mode is True
        assert "the outline cannot be used for requirement-level grading (TypeError: kaputt)" in caplog.text
        assert "requirement-level grading is not possible; grading per step" in caplog.text

    def test_an_outline_that_cannot_be_read_is_graded_per_step(self, caplog):
        row = _row()
        ev = _judge()
        with patch("rubric_structure.checklist_spec_from_structure", side_effect=KeyError("nodes")), \
                caplog.at_level("WARNING"):
            ev.bind_task_rubric(row)
        assert ev.checklist is None and ev.rubric_mode is True
        assert "the outline's requirements cannot be read" in caplog.text


class TestRequirementLane:
    def test_one_call_marks_every_requirement_and_code_computes_the_points(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = _judge()
        ev.bind_task_rubric(_row(), margin_notes=False)
        _answer(ev, _outline_judgment())
        result = ev._evaluate_multidim_single_call(
            context="Sachverhalt", ground_truth="Musterlösung", prediction=ANSWER,
            task_data={"bewertungsbogen": "BEWERTUNGSBOGEN (insgesamt 10 BE)"},
        )
        assert not result.get("error"), result
        assert result["total_score"] == 7.5 and result["total_max"] == 10.0
        assert result["scores"]["s01_oeffentliche_sicherheit"]["score"] == 3.5
        assert result["scores"]["s02_gefahr"]["anforderungen"]["b2"]["score"] == 4.0
        assert result["checklist"]["score_unit"] == "binary"
        assert result["assessment"]["improvements"] == ["Definition vollständig wiedergeben"]
        assert "annotations" not in result
        call = ev.ai_service.generate_structured.call_args.kwargs
        assert '"erfuellt" = die Bearbeitung erbringt die beschriebene Teilleistung vollständig' in call["system_prompt"]
        assert "- s01_oeffentliche_sicherheit: Öffentliche Sicherheit (Anforderungen b1 bis b3; folgerichtig: b2)" in call["prompt"]
        assert "<bewertungsbogen>\nBEWERTUNGSBOGEN (insgesamt 10 BE)\n</bewertungsbogen>" in call["prompt"]
        assert "annotations" not in call["json_schema"]["properties"]
        assert result["_judge_prompts_used"]["mode"] == "checklist"
        assert result["_judge_prompts_used"]["checklist"]["score_unit"] == "binary"

    def test_the_notes_of_an_overlay_ride_along(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)

        class Notes:
            finalized = []

            def schema(self, refs, use_enum=True):
                return {"type": "array", "items": {"type": "object", "properties": {
                    "ref": {"type": "string", **({"enum": [*refs, "allgemein"]} if use_enum else {})}}}}

            def schema_cost(self, ref_count):
                return 5, ref_count + 4

            def rubric_rules(self):
                return "NOTIZEN-REGELN (Feld annotations)"

            def finalize(self, raw, answer, refs, *, index=None, zeroed_refs=()):
                self.finalized.append({"refs": list(refs), "zeroed": list(zeroed_refs), "answer": answer})
                return [{"id": "n1", "ref": item["ref"]} for item in raw or []]

        notes = Notes()
        body = _outline_judgment()
        # A step whose only credited requirement lost its quote counts as zeroed for the provider.
        body["scores"]["s02_gefahr"] = _marks(("nicht_erfuellt", "", "fehlt"), ("erfuellt", "nicht in der Bearbeitung", ""))
        body["annotations"] = [{"ref": "s01_oeffentliche_sicherheit", "kind": "positiv", "quote": Q_DEFINITION, "comment": "gut"}]
        ev = _judge()
        ev.bind_task_rubric(_row(), margin_notes=True)
        _answer(ev, body)
        with patch("extension_registry.first_worker_attr", return_value=lambda: notes):
            result = ev._evaluate_multidim_single_call(
                context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"})
        assert not result.get("error"), result
        assert result["annotations"] == [{"id": "n1", "ref": "s01_oeffentliche_sicherheit"}]
        assert notes.finalized == [{
            "refs": ["s01_oeffentliche_sicherheit", "s02_gefahr"], "zeroed": ["s02_gefahr"], "answer": ANSWER}]
        call = ev.ai_service.generate_structured.call_args.kwargs
        assert call["prompt"].rstrip().endswith("NOTIZEN-REGELN (Feld annotations)")
        schema = call["json_schema"]
        assert schema["required"][-1] == "annotations" and schema["required"] == list(schema["properties"])
        assert schema["properties"]["annotations"]["items"]["properties"]["ref"]["enum"] == [
            "s01_oeffentliche_sicherheit", "s02_gefahr", "allgemein"]

    def test_no_notes_when_the_binding_switched_them_off(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = _judge()
        ev.bind_task_rubric(_row(), margin_notes=False)
        _answer(ev, _outline_judgment())
        lookup = MagicMock()
        with patch("extension_registry.first_worker_attr", lookup):
            result = ev._evaluate_multidim_single_call(
                context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"})
        assert "annotations" not in result
        lookup.assert_not_called()

    def test_the_end_to_end_test_mode_fills_the_sheet_without_a_provider(self, monkeypatch):
        monkeypatch.setenv("E2E_TEST_MODE", "true")
        ev = _judge()
        ev.bind_task_rubric(_row(), margin_notes=False)
        result = ev._evaluate_multidim_single_call(
            context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"})
        ev.ai_service.generate_structured.assert_not_called()
        assert result["_call_metadata"]["e2e_test_mode"] is True
        assert set(result["scores"]) == {"s01_oeffentliche_sicherheit", "s02_gefahr"}
        assert result["checklist"]["score_unit"] == "binary" and result["total_max"] == 10.0
        items = [i for step in result["scores"].values() for i in step["anforderungen"].values()]
        assert {i["status"] for i in items} <= {"erfuellt", "nicht_erfuellt"}
        # The mock quotes the start of the answer, so its credits pass the quote check.
        assert all(i["evidence_verified"] for i in items if i["status"] == "erfuellt")
        assert result["total_score"] == sum(i["score"] for i in items)
        again = ev._evaluate_multidim_single_call(
            context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"})
        assert again["scores"] == result["scores"]


class TestDispatchHelpers:
    def test_the_score_unit_of_a_config(self):
        from evaluation.cell_evaluator import _rubric_score_unit_kwargs

        assert _rubric_score_unit_kwargs({"rubric_score_unit": " step "}) == {"score_unit": "step"}
        for params in (None, {}, {"rubric_score_unit": ""}, {"rubric_score_unit": None}, {"rubric_score_unit": 3}, "x"):
            assert _rubric_score_unit_kwargs(params) == {}

    def test_each_lane_reads_the_text_that_fits_it(self):
        from evaluation.cell_evaluator import _render_rubric_text, _rubric_text_for

        row = _row(rendered_text="eigene Schlüssel je Lösungsweg", rendered_text_replace="auf die ersetzten Schritte",
                   checklist_spec=checklist_spec_from_structure(_structure()))
        per_requirement, per_step = _judge(), _judge()
        per_requirement.bind_task_rubric(row)
        per_step.bind_task_rubric(row, score_unit="step")
        assert _rubric_text_for(per_requirement, row) == "eigene Schlüssel je Lösungsweg"
        assert _rubric_text_for(per_step, row) == "auf die ersetzten Schritte"
        # An evaluator that cannot say reads the stored default, as before.
        assert _rubric_text_for(SimpleNamespace(), row) == "eigene Schlüssel je Lösungsweg"
        assert _render_rubric_text(row) == "eigene Schlüssel je Lösungsweg"
        assert _render_rubric_text(row, MagicMock()) == "eigene Schlüssel je Lösungsweg"

    def test_the_row_keeps_the_requirement_level_findings(self):
        import tasks

        ev = _judge()
        ev.bind_task_rubric(_row(), margin_notes=False)
        _answer(ev, _outline_judgment())
        result = ev._evaluate_multidim_single_call(
            context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"})
        metrics, normalized = tasks._build_multidim_judge_row_metrics(result, "llm_judge_rubric", None)
        details = metrics["llm_judge_rubric"]["details"]
        assert normalized == 0.75 and details["total_score"] == 7.5
        assert details["checklist"]["score_unit"] == "binary"
        assert details["checklist"]["states"]["erfuellt"] == {"count": 3, "be": 7.5}
        assert details["assessment"]["assessment_status"] == "scored"
        assert details["scores"]["s01_oeffentliche_sicherheit"]["anforderungen"]["b1"]["status"] == "erfuellt"
        # A grading with one number per step carries neither block.
        plain = {"scores": {"a": {"score": 1, "max": 2, "reason": "r"}}, "total_score": 1, "total_max": 2}
        plain_details = tasks._build_multidim_judge_row_metrics(plain, "llm_judge_rubric", None)[0][
            "llm_judge_rubric"]["details"]
        assert "checklist" not in plain_details and "assessment" not in plain_details

    def test_a_row_without_scores_keeps_what_the_judge_found(self):
        import tasks

        # The judge found the inputs not evaluable: no scores, but the row
        # says why (and control characters never reach the JSONB column).
        found = {"assessment_status": "not_evaluable", "review_reasons": ["Bearbeitung\u0000 leer"]}
        failed = {"error": True, "error_message": "nicht bewertbar", "assessment": found,
                  "_raw_output": "{}", "_call_metadata": {"finish_reason": "stop"}}
        metrics, normalized = tasks._build_multidim_judge_row_metrics(failed, "llm_judge_rubric", None)
        row = metrics["llm_judge_rubric"]
        assert normalized is None and row["value"] is None and row["error"] == "nicht bewertbar"
        assert row["details"] == {
            "raw_output": "{}", "call_metadata": {"finish_reason": "stop"},
            "assessment": {"assessment_status": "not_evaluable", "review_reasons": ["Bearbeitung leer"]},
        }
        # Without findings, or with findings in another shape, the row is as before.
        for other in ({"error": True}, {"error": True, "assessment": "x"}, None):
            details = tasks._build_multidim_judge_row_metrics(other, "llm_judge_rubric", "E")[0][
                "llm_judge_rubric"]["details"]
            assert set(details) == {"raw_output", "call_metadata"}


class TestPromptsForTheUi:
    """The project page shows the prompts of this lane from a file the API
    can read (``shared/rubric_requirement_prompts.json``). The file is
    written from the worker code and must never say anything else."""

    @staticmethod
    def _script():
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "write_rubric_requirement_prompts.py"
        spec = importlib.util.spec_from_file_location("write_rubric_requirement_prompts", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_file_is_what_the_worker_sends(self):
        script = self._script()
        assert script.TARGET.read_text(encoding="utf-8") == script.rendered(), (
            "the prompts of the requirement-level judge changed: run "
            "services/workers/scripts/write_rubric_requirement_prompts.py"
        )

    def test_the_reader_serves_every_requirement_unit_and_the_default(self):
        from rubric_judge_prompts import requirement_judge_prompts

        prompts = requirement_judge_prompts()
        assert "note" not in prompts
        assert prompts["default_unit"] == RUBRIC_REQUIREMENT_UNIT == "binary"
        assert prompts["alternatives"] == "branch"
        assert set(prompts["units"]) == {"binary", "bullet"}
        assert prompts["user_template"] == cs.USER_TEMPLATE
        for unit, texts in prompts["units"].items():
            assert texts["system_prompt"] == cs.system_prompt(unit, "branch", True)
            assert texts["closing_rules"] == cs.closing_rules(unit, "branch", True)
            # The one rule a sheet without other solution paths does not get.
            assert prompts["paths_rule"] in texts["system_prompt"]
            assert prompts["paths_rule"] in texts["closing_rules"]
            assert prompts["paths_rule"] not in cs.system_prompt(unit, "branch", False)
            assert prompts["paths_rule"] not in cs.closing_rules(unit, "branch", False)

    def test_the_file_states_the_prompt_the_judge_gets(self):
        """End to end: the system prompt of a real requirement-level call is
        the text the UI shows for the unit (here a sheet without forks, so
        without the paths rule)."""
        from rubric_judge_prompts import requirement_judge_prompts

        ev = _judge()
        ev.bind_task_rubric(_row())
        assert ev.checklist is not None
        shown = requirement_judge_prompts()["units"][ev.checklist["score_unit"]]
        sent = ev.checklist["system_prompt"]
        assert sent == cs.system_prompt("binary", "branch", False)
        # Apart from the paths rule and the numbering after it, rule by rule the same text.
        strip = lambda text: [line.split(". ", 1)[-1] for line in text.splitlines()]  # noqa: E731
        shown_rules = [r for r in strip(shown["system_prompt"]) if r != requirement_judge_prompts()["paths_rule"]]
        assert strip(sent) == shown_rules

    def test_a_copy_on_every_call(self):
        from rubric_judge_prompts import requirement_judge_prompts

        first = requirement_judge_prompts()
        first["units"]["binary"]["system_prompt"] = "geändert"
        assert requirement_judge_prompts()["units"]["binary"]["system_prompt"] != "geändert"
