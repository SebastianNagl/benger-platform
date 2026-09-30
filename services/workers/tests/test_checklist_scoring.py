"""Checklist scoring for the Bewertungsbogen judge.

The judge marks requirement bullets (or scores / rates steps) and declares
the path it followed at each Weichenstellung; code computes every point, verifies
every quote, and sums unrounded values before one half-up rounding.
"""

import json
import re
from unittest.mock import MagicMock

import pytest

from ml_evaluation import checklist_scoring as cs
from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

# A synthetic civil-law case: a used bicycle with a defective brake. The
# fork (Weichenstellung) is whether the brake was defective when the bike was
# handed over (the reference solution's path) or only worn (another
# defensible path).
ANSWER = (
    "Der Anspruch auf Rückzahlung des Kaufpreises folgt aus §§ 437 Nr. 2, 346 I BGB. "
    "Die Bremse des Fahrrads war bei Übergabe defekt, weil sie am ersten Tag versagte. "
    "Die Kette ist verschlissen, der Verschleiß ist aber gewöhnlich."
)


def _spec():
    """Two primary steps outside any Weichenstellung, one replaced step, one branch step."""
    def step(sid, name, mx, shares, weichenstellung=None):
        return {
            "step_id": sid, "name": name, "max_score": mx, "keine_punkte": "nichts",
            "anforderungen": [{"key": f"k_{sid}__b{i}", "id": f"{sid}-{i}", "text": f"A{i}", "share": sh}
                              for i, sh in enumerate(shares, start=1)],
            "weichenstellung": weichenstellung,
        }
    return {
        "version": 1, "total_points": 100.0,
        "order": ["s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel"],
        "steps": {
            "s01_anspruchsgrundlage": step("S1", "Anspruchsgrundlage", 20.0, [0.5, 0.5]),
            "s02_kaufvertrag": step("S2", "Kaufvertrag", 30.0, [1.0]),
            "s03_sachmangel": step("S3", "Sachmangel", 50.0, [0.6, 0.4], {"id": "W1", "loesungsweg": "musterloesung"}),
        },
        "loesungsweg_steps": {
            "s04_verschleiss": step("W1-L1-S1", "Verschleiß", 50.0, [1.0], {"id": "W1", "loesungsweg": "W1-L1"}),
        },
        "weichenstellungen": [{
            "id": "W1", "bezeichnung": "Mangel oder Verschleiß", "budget": 50.0,
            "loesungswege": [{"id": "musterloesung", "step_keys": ["s03_sachmangel"]},
                       {"id": "W1-L1", "step_keys": ["s04_verschleiss"]}],
        }],
    }


def _bullets(*statuses_and_quotes):
    return {"anforderungen": {f"b{i}": {"status": st, "evidence": q}
                              for i, (st, q) in enumerate(statuses_and_quotes, start=1)},
            "abweichender_weg": False, "fehlplatziert": False, "reason": "r"}


def _verify(quote):
    return bool(quote) and quote in ANSWER


def _judgment(declared="musterloesung"):
    return {
        "scores": {
            "s01_anspruchsgrundlage": _bullets((2, "Anspruch auf Rückzahlung des Kaufpreises folgt aus §§ 437 Nr. 2, 346 I BGB"),
                                      (1, "folgt aus §§ 437 Nr. 2, 346 I BGB")),
            "s02_kaufvertrag": _bullets((0, "")),
            "s03_sachmangel": _bullets((2, "Die Bremse des Fahrrads war bei Übergabe defekt"), (2, "erfunden, steht nicht da")),
            "s04_verschleiss": _bullets((1, "Die Kette ist verschlissen")),
        },
        "weichenstellungen": {"W1": {"gefolgter_loesungsweg": declared, "evidence": "bei Übergabe defekt", "reason": "r"}},
        "overall_assessment": "ok",
        **_diagnosis(),
    }


def _diagnosis(status="scored", products=(("P1 Gutachten", "fulfilled"),), reasons=()):
    return {
        "assessment_status": status,
        "work_products": [{"product": p, "requirement_basis": "Aufgabenstellung", "status": st, "reason": "r"}
                          for p, st in products],
        "supplementary_reviews": [{"subject": "Kein Hilfsgutachten verlangt", "requirement_basis": "Bearbeitervermerk",
                                   "status": "not_required", "assumption": None, "reason": "r"}],
        "error_chains": [],
        "review_reasons": list(reasons),
        "improvements": ["Anspruchsgrundlage knapper"],
    }


class TestSchema:
    def test_bullet_schema_scores_every_path_and_declares_the_weiche(self):
        schema = cs.build_schema(_spec(), "bullet", "branch")
        steps = schema["properties"]["scores"]["properties"]
        assert list(steps) == ["s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel", "s04_verschleiss"]
        b1 = steps["s01_anspruchsgrundlage"]["properties"]["anforderungen"]["properties"]["b1"]
        assert b1["properties"]["status"] == {"type": "integer", "enum": [0, 1, 2]}
        assert schema["properties"]["weichenstellungen"]["properties"]["W1"]["properties"]["gefolgter_loesungsweg"]["enum"] == [
            "musterloesung", "W1-L1"]
        assert "total_score" not in schema["properties"]  # code sums

    def test_replace_schema_has_only_the_primary_path(self):
        schema = cs.build_schema(_spec(), "step", "replace")
        assert list(schema["properties"]["scores"]["properties"]) == ["s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel"]
        assert "weichenstellungen" not in schema["properties"]

    def test_step_and_rating_units(self):
        step = cs.build_schema(_spec(), "step", "replace")["properties"]["scores"]["properties"]["s01_anspruchsgrundlage"]
        assert step["properties"]["score"]["enum"][-1] == 20.0
        rating = cs.build_schema(_spec(), "rating", "replace")["properties"]["scores"]["properties"]["s01_anspruchsgrundlage"]
        assert rating["properties"]["note"]["enum"] == list(range(19))

    def test_large_sheets_fall_back_to_ranges(self):
        spec = _spec()
        for k in list(spec["steps"]):
            spec["steps"][k]["anforderungen"] = spec["steps"][k]["anforderungen"] * 200
        status = cs.build_schema(spec, "bullet", "branch")["properties"]["scores"]["properties"]["s01_anspruchsgrundlage"][
            "properties"]["anforderungen"]["properties"]["b1"]["properties"]["status"]
        assert status == {"type": "integer", "minimum": 0, "maximum": 2}

    def test_the_enum_budget_counts_the_fixed_enums(self):
        # 329 bullets (325 here, 4 in the other steps) cost 987 status values:
        # under the cap on their own, over it with the diagnosis block (13) and
        # the Weichenstellung ids (2).
        spec = _spec()
        spec["steps"]["s01_anspruchsgrundlage"]["anforderungen"] = [
            {"key": f"k{i}", "id": f"S1-{i}", "text": "A", "share": 1 / 325} for i in range(325)]
        schema = cs.build_schema(spec, "bullet", "branch")
        enums, _ = cs.schema_budget(schema)
        assert enums == 2 + 5 + 5 + 3  # only the fixed enums remain
        status = schema["properties"]["scores"]["properties"]["s01_anspruchsgrundlage"]["properties"]["anforderungen"][
            "properties"]["b1"]["properties"]["status"]
        assert status == {"type": "integer", "minimum": 0, "maximum": 2}
        spec["steps"]["s01_anspruchsgrundlage"]["anforderungen"] = spec["steps"]["s01_anspruchsgrundlage"]["anforderungen"][:320]
        enums, properties = cs.schema_budget(cs.build_schema(spec, "bullet", "branch"))
        assert enums == 3 * 324 + 15 and properties < 5000  # 987: enums again

    def test_replace_with_bullets_is_rejected(self):
        with pytest.raises(ValueError, match="replace"):
            cs.validate_options("bullet", "replace", "declared")
        for unit in ("step", "rating"):
            cs.validate_options(unit, "replace", "declared")


_COMBINATIONS = [(unit, alt) for unit in cs.SCORE_UNITS for alt in cs.ALTERNATIVES]

# The judge prompts are generic. No term of a concrete case may reach them:
# an example from a case would tell the judge what the answers are about.
# The terms of the fixture case above stand in for any case the instrument
# is used on.
_CASE_TERMS = ("Fahrrad", "Bremse", "Kaufpreis", "Rückzahlung", "Kaufvertrag", "Sachmangel", "Verschleiß")


class TestPromptRules:
    @pytest.mark.parametrize("unit,alternatives", _COMBINATIONS)
    def test_no_case_terms_in_any_judge_prompt(self, unit, alternatives):
        text = (cs.system_prompt(unit, alternatives) + "\n" + cs.closing_rules(unit, alternatives)).casefold()
        assert [t for t in _CASE_TERMS if t.casefold() in text] == []

    @pytest.mark.parametrize("unit,alternatives", _COMBINATIONS)
    def test_general_rules_are_in_the_system_prompt_and_the_closing_rules(self, unit, alternatives):
        system, closing = cs.system_prompt(unit, alternatives), cs.closing_rules(unit, alternatives)
        for rule in cs._GENERAL_RULES:
            assert rule in system and f"- {rule}" in closing
        assert "keinen Vollständigkeitsbonus" in closing
        assert "\"Keine Punkte\" eines Schritts" in closing

    def test_bullet_status_definition(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "1 = im Kern erbracht, aber unvollständig oder mit einem Fehler" in prompt
        assert "Das bloße Nennen eines Stichworts, einer Norm oder eines Ergebnisses ist 0" in prompt
        assert "teilweise erfüllt" not in prompt

    def test_rating_unit_uses_the_jurprnotskv_anchors(self):
        prompt = cs.system_prompt("rating", "replace")
        assert "§ 1 JurPrNotSkV" in prompt
        for anchor in ("16 bis 18 = sehr gut, eine besonders hervorragende Leistung",
                       "10 bis 12 = vollbefriedigend",
                       "1 bis 3 = mangelhaft, eine an erheblichen Mängeln leidende, im Ganzen nicht mehr brauchbare",
                       "0 = ungenügend, eine völlig unbrauchbare Leistung"):
            assert anchor in prompt

    @pytest.mark.parametrize("unit,alternatives", _COMBINATIONS)
    def test_alternatives_wording_only_with_weichenstellungen(self, unit, alternatives):
        spec = _spec()
        with_w = cs.system_prompt(unit, alternatives, cs.has_weichenstellungen(spec))
        assert (cs._BRANCH_RULE if alternatives == "branch" else cs._REPLACE_RULE) in with_w
        spec["weichenstellungen"] = []
        assert not cs.has_weichenstellungen(spec)
        text = (cs.system_prompt(unit, alternatives, False) + cs.closing_rules(unit, alternatives, False)
                + json.dumps(cs.build_schema(spec, unit, alternatives), ensure_ascii=False))
        assert "Weichenstellung" not in text and "weichenstellungen" not in text
        assert "gefolgter_loesungsweg" not in text

    def test_user_template_has_no_score_wording(self):
        for word in ("Punkt", "Bewertungseinheit", "halbe", "Halbe", "Maximal"):
            assert word not in cs.USER_TEMPLATE
        assert re.search(r"\bBE\b", cs.USER_TEMPLATE) is None
        for slot in ("{context}", "{ground_truth}", "{bewertungsbogen}", "{prediction}"):
            assert slot in cs.USER_TEMPLATE

    def test_missing_keys_note_names_the_json_paths(self):
        note = cs.missing_keys_note(["s02_kaufvertrag", "s01_anspruchsgrundlage.b2", "weichenstellungen.W1"])
        assert note.startswith("Deiner letzten Antwort fehlten Pflichtangaben. Es fehlen die Schlüssel ")
        assert "scores.s02_kaufvertrag, scores.s01_anspruchsgrundlage.anforderungen.b2, weichenstellungen.W1." in note
        many = cs.missing_keys_note([f"s{i:02d}" for i in range(50)])
        assert "scores.s39" in many and "scores.s40" not in many and "und 10 weitere" in many

    def test_branch_rule_needs_a_justified_path(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "ein bloß behauptetes anderes Ergebnis ist kein gefolgter Weg" in prompt
        assert "Gezählt wird nur ein Weg" in prompt
        assert "in der Regel 0 Punkte" not in prompt


class TestPlacement:
    def test_rules_credit_misplaced_work_once_and_ask_for_the_flag(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "an anderer Stelle steht" in prompt and "nur für einen Schritt" in prompt
        assert "innerhalb derselben Fallfrage und desselben Arbeitsergebnisses" in prompt
        assert "wenn die Bearbeitung dort ausdrücklich auf sie verweist" in prompt
        assert "Suche es nur in dem Teil" not in prompt
        assert "fehlplatziert" in cs.closing_rules("step", "replace")

    def test_flag_is_in_the_schema_and_counted(self):
        step = cs.build_schema(_spec(), "step", "replace")["properties"]["scores"]["properties"]["s01_anspruchsgrundlage"]
        assert step["properties"]["fehlplatziert"] == {"type": "boolean"}
        judgment = _judgment()
        judgment["scores"]["s03_sachmangel"]["fehlplatziert"] = True
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["fehlplatziert_steps"] == 1
        assert out["scores"]["s03_sachmangel"]["fehlplatziert"] is True
        # A misplacement is recorded, not punished.
        assert out["scores"]["s03_sachmangel"]["raw_points"] == pytest.approx(50 * 0.6)


class TestFinalize:
    def test_bullet_points_evidence_and_both_totals(self):
        out = cs.finalize(_judgment(), _spec(), "bullet", "branch", "declared", _verify)
        s1 = out["scores"]["s01_anspruchsgrundlage"]
        assert s1["raw_points"] == pytest.approx(20 * (0.5 * 1 + 0.5 * 0.5))  # 15.0
        s3 = out["scores"]["s03_sachmangel"]
        assert s3["anforderungen"]["b2"] == {"status": 0, "model_status": 2,
                                             "evidence": "erfunden, steht nicht da", "evidence_verified": False}
        assert s3["raw_points"] == pytest.approx(50 * 0.6)
        branch = out["scores"]["s04_verschleiss"]["raw_points"]
        assert branch == pytest.approx(25.0)
        ck = out["checklist"]
        assert ck["totals"]["declared"] == 45.0          # 15 + 0 + 30
        assert ck["totals"]["best"] == 45.0              # primary 30 beats branch 25
        assert ck["weichenstellungen"]["W1"]["declared"] == "musterloesung"
        assert ck["zeroed_items"] == 1
        assert out["total_score"] == 45.0 and out["total_max"] == 100.0

    def test_declared_branch_counts_that_path_and_best_can_differ(self):
        out = cs.finalize(_judgment("W1-L1"), _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["totals"] == {"declared": 40.0, "best": 45.0}
        best = cs.finalize(_judgment("W1-L1"), _spec(), "bullet", "branch", "best", _verify)
        assert best["total_score"] == 45.0

    def test_unknown_declaration_falls_back_to_primary(self):
        out = cs.finalize(_judgment("W9-L9"), _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["weichenstellungen"]["W1"]["declared"] == "musterloesung"

    def test_declared_other_path_needs_a_verified_quote(self):
        judgment = _judgment("W1-L1")
        judgment["weichenstellungen"]["W1"]["evidence"] = "erfunden, steht nicht da"
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        decision = out["checklist"]["weichenstellungen"]["W1"]
        assert decision["declared"] == "musterloesung" and decision["declared_model"] == "W1-L1"
        assert decision["declared_fallback"] is True and decision["evidence_verified"] is False
        assert out["checklist"]["totals"]["declared"] == 45.0  # the Musterlösung's path counts
        verified = cs.finalize(_judgment("W1-L1"), _spec(), "bullet", "branch", "declared", _verify)
        assert verified["checklist"]["weichenstellungen"]["W1"]["declared_fallback"] is False
        assert verified["checklist"]["totals"]["declared"] == 40.0
        # The Musterlösung's own path needs no verified quote.
        primary = _judgment()
        primary["weichenstellungen"]["W1"]["evidence"] = ""
        out = cs.finalize(primary, _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["weichenstellungen"]["W1"]["declared_fallback"] is False

    def test_best_mode_subtotals_and_rating_grade_follow_the_counted_path(self):
        judgment = _judgment()
        judgment["scores"]["s04_verschleiss"] = _bullets((2, "Die Kette ist verschlissen"))  # 50 > 30
        declared = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        best = cs.finalize(judgment, _spec(), "bullet", "branch", "best", _verify)
        assert declared["checklist"]["arbeitsergebnisse"]["P1"]["points"] == pytest.approx(45.0)
        assert best["total_score"] == 65.0
        assert best["checklist"]["arbeitsergebnisse"]["P1"]["points"] == pytest.approx(65.0)

        def rated(note):
            return {"note": note, "evidence": "folgt aus §§ 437 Nr. 2, 346 I BGB", "abweichender_weg": False,
                    "fehlplatziert": False, "reason": ""}
        ratings = {"scores": {"s01_anspruchsgrundlage": rated(18), "s02_kaufvertrag": rated(0), "s03_sachmangel": rated(4),
                              "s04_verschleiss": rated(16)},
                   "weichenstellungen": {"W1": {"gefolgter_loesungsweg": "musterloesung", "evidence": "", "reason": ""}},
                   **_diagnosis()}
        declared = cs.finalize(ratings, _spec(), "rating", "branch", "declared", _verify)
        best = cs.finalize(ratings, _spec(), "rating", "branch", "best", _verify)
        assert declared["checklist"]["rating_grade"] == pytest.approx((18 * 20 + 4 * 50) / 100)
        assert best["checklist"]["weichenstellungen"]["W1"]["best"] == "W1-L1"
        assert best["checklist"]["rating_grade"] == pytest.approx((18 * 20 + 16 * 50) / 100)

    def test_replace_mode_counts_the_primary_steps(self):
        def scored(score, quote):
            return {"score": score, "evidence": quote, "abweichender_weg": False, "fehlplatziert": False, "reason": ""}
        judgment = {"scores": {"s01_anspruchsgrundlage": scored(15, "folgt aus §§ 437 Nr. 2, 346 I BGB"), "s02_kaufvertrag": scored(0, ""),
                               "s03_sachmangel": scored(30, "bei Übergabe defekt")}, **_diagnosis()}
        out = cs.finalize(judgment, _spec(), "step", "replace", "declared", _verify)
        assert out["checklist"]["totals"] == {"declared": 45.0, "best": 45.0}

    def test_missing_items_are_reported_for_a_retry(self):
        judgment = _judgment()
        del judgment["scores"]["s02_kaufvertrag"]
        del judgment["scores"]["s01_anspruchsgrundlage"]["anforderungen"]["b2"]
        del judgment["weichenstellungen"]
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert set(out["missing"]) == {"s02_kaufvertrag", "s01_anspruchsgrundlage.b2", "weichenstellungen.W1"}

    def test_totals_round_half_up_once(self):
        spec = _spec()
        spec["steps"]["s01_anspruchsgrundlage"]["max_score"] = 0.5
        judgment = _judgment()
        judgment["scores"]["s01_anspruchsgrundlage"] = _bullets((2, "folgt aus §§ 437 Nr. 2, 346 I BGB"), (0, ""))
        out = cs.finalize(judgment, spec, "bullet", "branch", "declared", _verify)
        assert out["scores"]["s01_anspruchsgrundlage"]["raw_points"] == 0.25
        assert out["scores"]["s01_anspruchsgrundlage"]["score"] == 0.5    # half up, not banker's
        assert out["checklist"]["totals_unrounded"]["declared"] == pytest.approx(30.25)
        assert out["checklist"]["totals"]["declared"] == 30.5
        assert cs.round_half_up(0.25) == 0.5 and cs.round_half_up(0.75) == 1.0

    def test_rounding_survives_float_noise(self):
        assert 25 * 0.29 < 7.25  # 7.249999999999999
        assert cs.round_half_up(25 * 0.29) == 7.5
        assert cs.round_half_up(7.2) == 7.0 and cs.round_half_up(7.24) == 7.0

    def test_shown_step_scores_add_up_to_the_total(self):
        # Three steps at 0.25 each: rounding each would show 1.5 against a total of 1.0.
        spec = {"total_points": 3.0, "order": ["a", "b", "c"],
                "steps": {k: {"name": k, "max_score": 1.0, "anforderungen": [{"share": 0.25}, {"share": 0.75}]}
                          for k in ("a", "b", "c")}}
        judgment = {"scores": {k: _bullets((2, "folgt aus §§ 437 Nr. 2, 346 I BGB"), (0, "")) for k in ("a", "b", "c")},
                    **_diagnosis()}
        out = cs.finalize(judgment, spec, "bullet", "branch", "declared", _verify)
        assert out["total_score"] == 1.0
        assert [out["scores"][k]["score"] for k in "abc"] == [0.5, 0.5, 0.0]  # ties: sheet order
        assert [out["scores"][k]["raw_points"] for k in "abc"] == [0.25, 0.25, 0.25]

    def test_distribution_respects_each_step_maximum(self):
        shown = cs.distribute_half_points({"a": 1.0, "b": 0.2, "c": 0.4}, {"a": 1.0, "b": 0.5, "c": 0.5}, 1.5)
        assert shown == {"a": 1.0, "b": 0.0, "c": 0.5}
        shown = cs.distribute_half_points({"a": 2.3, "b": 2.3, "c": 2.3}, {"a": 3, "b": 3, "c": 3}, 7.0)
        assert shown == {"a": 2.5, "b": 2.5, "c": 2.0} and sum(shown.values()) == 7.0
        shown = cs.distribute_half_points({"a": 0.0, "b": 0.0}, {"a": 1, "b": 1}, 0.0)
        assert shown == {"a": 0.0, "b": 0.0}

    def test_best_mode_shows_the_best_path(self):
        out = cs.finalize(_judgment("W1-L1"), _spec(), "bullet", "branch", "best", _verify)
        shown = ["s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel"]
        assert sum(out["scores"][k]["score"] for k in shown) == out["total_score"] == 45.0
        assert out["scores"]["s04_verschleiss"]["score"] == 25.0  # not counted, rounded on its own

    def test_rating_unit_maps_notes_through_the_grade_key(self):
        judgment = {
            "scores": {
                "s01_anspruchsgrundlage": {"note": 18, "evidence": "folgt aus §§ 437 Nr. 2, 346 I BGB", "abweichender_weg": False, "reason": ""},
                "s02_kaufvertrag": {"note": 9, "evidence": "erfunden", "abweichender_weg": False, "reason": ""},
                "s03_sachmangel": {"note": 9, "evidence": "bei Übergabe defekt", "abweichender_weg": True, "reason": ""},
            },
            "overall_assessment": "",
        }
        out = cs.finalize(judgment, _spec(), "rating", "replace", "declared", _verify)
        assert out["scores"]["s02_kaufvertrag"]["note"] == 0  # unverified quote
        # Standard key: grade 18, the top of the scale, is the full step; grade 9
        # is the midpoint of its band [67, 70) -> 68.5 %.
        assert out["scores"]["s01_anspruchsgrundlage"]["raw_points"] == pytest.approx(20.0)
        assert out["scores"]["s03_sachmangel"]["raw_points"] == pytest.approx(50 * 0.685)
        assert out["checklist"]["totals_unrounded"]["declared"] == pytest.approx(54.25)
        assert out["checklist"]["totals"]["declared"] == 54.5
        assert [out["scores"][k]["score"] for k in ("s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel")] == [20.0, 0.0, 34.5]
        # Aggregation (a) is unchanged: the weighted mean of the grades.
        assert out["checklist"]["rating_grade"] == pytest.approx((18 * 20 + 0 * 30 + 9 * 50) / 100)
        assert out["checklist"]["abweichender_weg_steps"] == 1

    def test_rating_key_of_the_exam_changes_the_points(self):
        judgment = {"scores": {k: {"note": 4, "evidence": "folgt aus §§ 437 Nr. 2, 346 I BGB", "abweichender_weg": False, "reason": ""}
                               for k in ("s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel")}}
        study_key = {"thresholds_be": [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
                     "rounding": "floor", "pass_grade": 4}
        out = cs.finalize(judgment, _spec(), "rating", "replace", "declared", _verify, grade_scale=study_key)
        assert out["checklist"]["totals_unrounded"]["declared"] == pytest.approx(42.0)  # [40, 44) -> 42 %
        standard = cs.finalize(judgment, _spec(), "rating", "replace", "declared", _verify)
        assert standard["checklist"]["totals_unrounded"]["declared"] == pytest.approx(52.0)  # [50, 54)


STUDY_THRESHOLDS = [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96]


class TestGradeKey:
    def test_default_is_the_standard_preset(self):
        table = cs.rating_percent_table(None, 100.0)
        assert len(table) == 19 and table[0] == 0.0
        assert table[1] == pytest.approx(19.5)   # [13, 26)
        assert table[4] == pytest.approx(52.0)   # [50, 54)
        assert table[17] == pytest.approx(95.5)  # [94, 97)
        assert table[18] == 100.0                # the top grade is the full step

    def test_study_key_and_its_platform_forms_agree(self):
        study = cs.rating_percent_table({"thresholds_be": STUDY_THRESHOLDS, "rounding": "floor", "pass_grade": 4}, 100)
        assert study[1] == pytest.approx(15.0) and study[4] == pytest.approx(42.0) and study[17] == pytest.approx(94.0)
        assert study[18] == 100.0
        assert cs.rating_percent_table({"unit": "BE", "thresholds": STUDY_THRESHOLDS}, 100) == pytest.approx(study)
        assert cs.rating_percent_table({"unit": "percent", "thresholds": STUDY_THRESHOLDS}, 100) == pytest.approx(study)
        assert cs.grade_key({"thresholds_be": STUDY_THRESHOLDS, "rounding": "floor"}) == {
            "unit": "BE", "thresholds": STUDY_THRESHOLDS, "rounding": "floor"}

    def test_a_points_key_is_read_on_the_sheet_total(self):
        half = [t / 2 for t in STUDY_THRESHOLDS]
        assert cs.rating_percent_table({"unit": "BE", "thresholds": half}, 50) == pytest.approx(
            cs.rating_percent_table({"unit": "percent", "thresholds": STUDY_THRESHOLDS}, 50))

    @pytest.mark.parametrize("bad", [
        {"thresholds_be": [10, 20]},
        {"unit": "percent", "thresholds": list(reversed(STUDY_THRESHOLDS))},
        {"unit": "BE", "thresholds": [t * 2 for t in STUDY_THRESHOLDS]},  # above the 100-BE total
        "standard",
    ])
    def test_bad_keys_are_rejected(self, bad):
        with pytest.raises(ValueError):
            cs.rating_percent_table(bad, 100)


class TestEvaluatorIntegration:
    def _evaluator(self):
        ev = LLMJudgeEvaluator(
            ai_service=MagicMock(),
            judge_model="gpt-5.6-luna",
            custom_prompt_template="{context}\n{bewertungsbogen}\n{prediction}",
        )
        ev.configure_checklist(_spec(), "bullet", "branch", "declared")
        return ev

    def _respond(self, ev, *bodies):
        ev.ai_service.generate_structured.side_effect = [
            {"success": True, "content": json.dumps(b), "usage": {}, "metadata": {"finish_reason": "stop"}}
            for b in bodies
        ]

    def test_checklist_call_uses_its_prompt_schema_and_totals(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        self._respond(ev, _judgment())
        result = ev._evaluate_multidim_single_call(
            context="SV", ground_truth="ML", prediction=ANSWER, task_data={"bewertungsbogen": "BOGEN"}
        )
        assert not result.get("error"), result
        assert result["total_score"] == 45.0
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert "Bewerte jede Anforderung" in kwargs["system_prompt"]
        assert "gefolgter_loesungsweg" in kwargs["prompt"] and "SCHLÜSSEL FÜR DIE ANTWORT" in kwargs["prompt"]
        assert "weichenstellungen" in kwargs["json_schema"]["properties"]
        assert result["_judge_prompts_used"]["mode"] == "checklist"

    def test_incomplete_judgment_is_retried(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        incomplete = _judgment()
        del incomplete["scores"]["s02_kaufvertrag"]
        self._respond(ev, incomplete, _judgment())
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert not result.get("error") and ev.ai_service.generate_structured.call_count == 2

    def test_the_retry_names_the_missing_keys_and_meters_every_attempt(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        incomplete = _judgment()
        del incomplete["scores"]["s02_kaufvertrag"]
        del incomplete["weichenstellungen"]
        ev.ai_service.generate_structured.side_effect = [
            {"success": True, "content": json.dumps(incomplete), "metadata": {"finish_reason": "stop"},
             "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
            {"success": True, "content": json.dumps(_judgment()), "metadata": {"finish_reason": "stop"},
             "usage": {"prompt_tokens": 110, "completion_tokens": 30, "total_tokens": 140}},
        ]
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        first, second = (c.kwargs["prompt"] for c in ev.ai_service.generate_structured.call_args_list)
        assert "Es fehlen die Schlüssel" not in first
        assert second.startswith(first.rstrip())
        assert second.endswith("Es fehlen die Schlüssel scores.s02_kaufvertrag, weichenstellungen.W1. "
                               "Gib die vollständige Antwort erneut aus, mit allen Schlüsseln des Schemas.")
        meta = result["_call_metadata"]
        assert meta["usage_all_attempts"] == {"attempts": 2, "attempts_without_usage": 0, "input_tokens": 210,
                                              "output_tokens": 50, "total_tokens": 260}
        assert meta["input_tokens"] == 110  # the last attempt's own usage stays
        assert meta["judge_retries"] == [{"attempt": 1, "error_type": "missing_keys", "missing": 2}]
        assert result["_judge_prompts_used"]["evaluation_prompt"] == first

    def test_a_failed_retry_series_reports_the_summed_usage(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        incomplete = _judgment()
        del incomplete["scores"]["s02_kaufvertrag"]
        ev.ai_service.generate_structured.side_effect = [
            {"success": True, "content": json.dumps(incomplete), "metadata": {"finish_reason": "stop"},
             "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            RuntimeError("socket closed"),
            {"success": True, "content": json.dumps(incomplete), "metadata": {"finish_reason": "stop"},
             "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125}},
        ]
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert result["error"] is True
        assert result["_call_metadata"]["usage_all_attempts"] == {
            "attempts": 3, "attempts_without_usage": 1, "input_tokens": 200, "output_tokens": 45,
            "total_tokens": 245}

    def test_the_checklist_lane_uses_its_own_template(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        product = ("{context}\n{bewertungsbogen}\n{prediction}\nVergib Punkte je Schritt. "
                   "Halbe Bewertungseinheiten sind zulässig.")
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.6-luna", custom_prompt_template=product)
        ev.configure_checklist(_spec(), "bullet", "branch", "declared")
        self._respond(ev, _judgment())
        ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER,
                                          task_data={"bewertungsbogen": "BOGEN"})
        prompt = ev.ai_service.generate_structured.call_args.kwargs["prompt"]
        assert prompt.startswith("Bewerte die Bearbeitung anhand des Bewertungsbogens nach den festen Regeln.")
        assert "Halbe Bewertungseinheiten" not in prompt and "Vergib Punkte" not in prompt
        assert "<bewertungsbogen>\nBOGEN\n</bewertungsbogen>" in prompt
        assert ev.custom_prompt_template == product  # kept for the product lane
        assert ev.checklist["user_template"] == cs.USER_TEMPLATE
        # No template at all: the checklist lane still has one.
        bare = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.6-luna")
        bare.configure_checklist(_spec(), "bullet", "branch", "declared")
        self._respond(bare, _judgment())
        assert not bare._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER).get("error")

    def test_configure_checklist_owns_the_prompts(self):
        spec = _spec()
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="m", custom_prompt_template="x")
        ev.configure_checklist(spec, "step", "replace", "declared")
        assert ev.checklist["system_prompt"] == cs.system_prompt("step", "replace", True)
        assert ev.checklist["closing_rules"] == cs.closing_rules("step", "replace", True)
        spec["weichenstellungen"] = []
        ev.configure_checklist(spec, "step", "replace", "declared")
        assert cs._REPLACE_RULE not in ev.checklist["system_prompt"]
        assert cs._REPLACE_RULE not in ev.checklist["closing_rules"]

    def test_spec_without_bound_rubric_supplies_the_criteria(self):
        ev = self._evaluator()
        assert list(ev.custom_criteria) == ["s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel"]
        assert ev.is_multidim_mode() and ev.rubric_mode

    def test_bad_options_rejected(self):
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="m", custom_prompt_template="x")
        with pytest.raises(ValueError):
            ev.configure_checklist(_spec(), "points", "branch")
        with pytest.raises(ValueError):
            ev.configure_checklist(_spec(), "bullet", "replace")
        with pytest.raises(ValueError):
            ev.configure_checklist(_spec(), "rating", "replace", grade_scale={"thresholds_be": [1, 2, 3]})

    def test_the_exam_key_reaches_the_rating_totals(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.6-luna",
                               custom_prompt_template="{context}\n{prediction}")
        ev.configure_checklist(_spec(), "rating", "replace", "declared",
                               grade_scale={"thresholds_be": STUDY_THRESHOLDS, "rounding": "floor", "pass_grade": 4})
        assert ev.checklist["grade_scale"]["unit"] == "BE"
        judgment = {"scores": {k: {"note": 18, "evidence": "folgt aus §§ 437 Nr. 2, 346 I BGB", "abweichender_weg": False,
                                   "fehlplatziert": False, "reason": ""}
                               for k in ("s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel")}, **_diagnosis()}
        self._respond(ev, judgment)
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert result["checklist"]["totals_unrounded"]["declared"] == pytest.approx(100.0)
        assert result["_judge_prompts_used"]["checklist"]["grade_scale"]["thresholds"] == STUDY_THRESHOLDS


class TestDiagnosisAndSecondExamAlignment:
    def test_schema_carries_the_second_exam_diagnosis_block(self):
        props = cs.build_schema(_spec(), "bullet", "branch")["properties"]
        for key in ("assessment_status", "work_products", "supplementary_reviews", "error_chains",
                    "review_reasons", "improvements"):
            assert key in props
        assert props["assessment_status"]["enum"] == ["scored", "review_required", "not_evaluable"]

    def test_rules_cover_hilfsgutachten_and_folgerichtig(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "Hilfsgutachten ersetzt nie das Ergebnis der Hauptlösung" in prompt
        assert "eine fehlende Kennzeichnung schließt die Bewertung nicht aus" in prompt
        assert "\"folgerichtig\"" in prompt and "error_chains" in prompt
        assert "rechnest du diesen Fehler nicht ein zweites Mal an" in prompt

    def test_scored_judgment_keeps_status_and_reports_product_totals(self):
        out = cs.finalize(_judgment(), _spec(), "bullet", "branch", "declared", _verify)
        assert out["assessment"]["assessment_status"] == "scored"
        assert out["assessment"]["aggregation_eligible"] is True
        assert out["checklist"]["arbeitsergebnisse"]["P1"]["points"] == pytest.approx(45.0)
        assert out["checklist"]["arbeitsergebnisse"]["P1"]["max"] == 100.0

    def test_unforeseen_path_needs_review(self):
        judgment = _judgment()
        judgment["scores"]["s02_kaufvertrag"]["abweichender_weg"] = True
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["assessment"]["assessment_status"] == "review_required"
        assert out["assessment"]["score_status"] == "provisional"
        assert any("s02_kaufvertrag" in r for r in out["assessment"]["review_reasons"])
        assert out["total_score"] == 45.0  # the value is kept

    def test_missing_product_with_credited_steps_needs_review(self):
        judgment = _judgment()
        judgment.update(_diagnosis(products=(("P1 Gutachten", "missing"),)))
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["assessment"]["assessment_status"] == "review_required"
        assert any("P1" in w for w in out["assessment"]["validation_warnings"])

    def test_two_work_results_with_the_renamed_keys(self):
        # The generator's current spec: arbeitsergebnisse on top, arbeitsergebnis_id
        # per step, and a step-level Hilfsgutachten marker with its "ebene".
        spec = _spec()
        spec["arbeitsergebnisse"] = [
            {"id": "P1", "bezeichnung": "Gutachten", "art": "gutachten", "step_keys": ["s01_anspruchsgrundlage"]},
            {"id": "P2", "bezeichnung": "Urteil", "art": "urteil", "step_keys": ["s02_kaufvertrag", "s03_sachmangel"]}]
        spec["steps"]["s01_anspruchsgrundlage"]["arbeitsergebnis_id"] = "P1"
        for k in ("s02_kaufvertrag", "s03_sachmangel"):
            spec["steps"][k]["arbeitsergebnis_id"] = "P2"
        spec["steps"]["s02_kaufvertrag"]["hilfsgutachten"] = {
            "abschnitt_id": "A2", "ebene": "schritt", "funktion": "praemissenwechsel",
            "ausloeser": "der Kaufvertrag bereits nichtig ist", "ausloeser_step_keys": ["s01_anspruchsgrundlage"]}
        out = cs.finalize(_judgment(), spec, "bullet", "branch", "declared", _verify)
        results = out["checklist"]["arbeitsergebnisse"]
        assert results["P1"] == {"points": pytest.approx(15.0), "max": 20.0}
        # s03 is counted on the declared path; a path's own steps would go to P2 too.
        assert results["P2"] == {"points": pytest.approx(30.0), "max": 80.0}
        assert "s02_kaufvertrag: Kaufvertrag (Anforderungen b1 bis b1; hilfsgutachtlich geschuldet)" in (
            cs.expected_output_note(spec, "bullet", "branch"))
        declared_l1 = cs.finalize(_judgment("W1-L1"), spec, "bullet", "branch", "declared", _verify)
        assert declared_l1["checklist"]["arbeitsergebnisse"]["P2"] == {"points": pytest.approx(25.0), "max": 80.0}

    @pytest.mark.parametrize("key", ["arbeitsergebnis_id", "arbeitsprodukt_id"])
    def test_work_results_match_exactly(self, key):
        spec = _spec()
        spec["steps"]["s02_kaufvertrag"][key] = "P10"
        spec["arbeitsergebnisse" if key == "arbeitsergebnis_id" else "arbeitsprodukte"] = [
            {"id": "P1", "bezeichnung": "Gutachten"}, {"id": "P10", "bezeichnung": "Urteil"}]
        judgment = _judgment()
        judgment.update(_diagnosis(products=(("P1 Gutachten", "fulfilled"), ("P10 Urteil", "missing"))))
        out = cs.finalize(judgment, spec, "bullet", "branch", "declared", _verify)
        assert out["checklist"]["arbeitsergebnisse"]["P10"] == {"points": 0.0, "max": 30.0}
        assert out["assessment"]["assessment_status"] == "scored"  # "P10 …" is not P1, whose steps earned points
        judgment.update(_diagnosis(products=(("Gutachten", "missing"),)))
        out = cs.finalize(judgment, spec, "bullet", "branch", "declared", _verify)
        assert out["assessment"]["assessment_status"] == "review_required"  # the exact name is P1
        assert any("Arbeitsergebnis P1" in r for r in out["assessment"]["review_reasons"])

    def test_missing_status_defaults_to_review(self):
        judgment = _judgment()
        del judgment["assessment_status"]
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["assessment"]["assessment_status"] == "review_required"

    def test_key_map_marks_folgerichtig_and_owed_steps(self):
        spec = _spec()
        spec["steps"]["s02_kaufvertrag"]["anforderungen"][0]["massstab"] = "folgerichtig"
        spec["steps"]["s02_kaufvertrag"]["hilfsgutachten"] = {"funktion": "praemissenwechsel"}
        note = cs.expected_output_note(spec, "bullet", "branch")
        assert "s02_kaufvertrag: Kaufvertrag (Anforderungen b1 bis b1; folgerichtig: b1; hilfsgutachtlich geschuldet)" in note

    def test_not_evaluable_becomes_an_error_row(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.6-luna",
                               custom_prompt_template="{context}\n{prediction}")
        ev.configure_checklist(_spec(), "bullet", "branch", "declared")
        judgment = _judgment()
        judgment.update(_diagnosis(status="not_evaluable", reasons=("Bearbeitung ist unlesbar",)))
        ev.ai_service.generate_structured.return_value = {
            "success": True, "content": json.dumps(judgment), "usage": {}, "metadata": {"finish_reason": "stop"}}
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "not_evaluable"
        assert "unlesbar" in result["error_message"]



# ---------------------------------------------------------------------------
# Robustness: a broken spec fails before any call, a deterministic finalize
# error is not retried, and the sheet total is never assumed.
# ---------------------------------------------------------------------------


def _without(mapping, *path):
    """``mapping`` with the key at ``path`` removed (a fresh spec each time)."""
    node = mapping
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return mapping


def _broken(change):
    spec = _spec()
    change(spec)
    return spec


_BROKEN_SPECS = {
    "no total_points": (lambda s: s.pop("total_points"), "total_points"),
    "zero total_points": (lambda s: s.update(total_points=0), "total_points"),
    "no max_score": (lambda s: _without(s, "steps", "s02_kaufvertrag", "max_score"), "steps.s02_kaufvertrag.max_score"),
    "text max_score": (lambda s: s["steps"]["s01_anspruchsgrundlage"].update(max_score="20"), "max_score"),
    "text share": (lambda s: s["steps"]["s01_anspruchsgrundlage"]["anforderungen"][0].update(share="half"),
                   "anforderungen[b1].share"),
    "bullet not an object": (lambda s: s["steps"]["s02_kaufvertrag"].update(anforderungen=["A1"]),
                             "anforderungen[b1] must be an object"),
    "order key without step": (lambda s: s["order"].append("s09_fehlt"), "s09_fehlt has no entry in steps"),
    "order listed twice": (lambda s: s["order"].append("s02_kaufvertrag"), "listed twice"),
    "no musterloesung path": (lambda s: s["weichenstellungen"][0]["loesungswege"][0].update(id="W1-L0"),
                              "no Lösungsweg with id 'musterloesung'"),
    "branch step without entry": (lambda s: s.update(loesungsweg_steps={}), "s04_verschleiss"),
    "step_keys not a list": (lambda s: s["weichenstellungen"][0]["loesungswege"][1].update(step_keys="s04_verschleiss"),
                             "needs step_keys"),
    "primary step outside order": (lambda s: s["weichenstellungen"][0]["loesungswege"][0].update(
        step_keys=["s09_fehlt"]), "s09_fehlt"),
    "weichenstellung id twice": (lambda s: s["weichenstellungen"].append(dict(s["weichenstellungen"][0])),
                                 "used twice"),
    "work results not objects": (lambda s: s.update(arbeitsergebnisse=["P1"]), "arbeitsergebnisse"),
}


class TestSpecValidation:
    @pytest.mark.parametrize("unit,alternatives", _COMBINATIONS)
    def test_the_fixture_spec_is_valid(self, unit, alternatives):
        cs.validate_spec(_spec(), unit, alternatives)

    @pytest.mark.parametrize("name", list(_BROKEN_SPECS))
    def test_a_broken_spec_is_named(self, name):
        change, fragment = _BROKEN_SPECS[name]
        with pytest.raises(cs.ChecklistSpecError) as exc:
            cs.validate_spec(_broken(change), "bullet", "branch")
        assert str(exc.value).startswith("checklist spec is invalid: ")
        assert fragment in str(exc.value)

    def test_every_problem_is_listed(self):
        spec = _spec()
        del spec["total_points"]
        del spec["steps"]["s02_kaufvertrag"]["max_score"]
        spec["loesungsweg_steps"] = {}
        message = str(pytest.raises(cs.ChecklistSpecError, cs.validate_spec, spec, "bullet", "branch").value)
        for fragment in ("total_points", "s02_kaufvertrag.max_score", "s04_verschleiss"):
            assert fragment in message

    def test_replace_mode_does_not_score_the_other_paths(self):
        """The other paths' steps are only scored in branch mode; replace
        mode needs no entries for them."""
        spec = _spec()
        spec["loesungsweg_steps"] = {}
        cs.validate_spec(spec, "step", "replace")
        with pytest.raises(cs.ChecklistSpecError):
            cs.validate_spec(spec, "step", "branch")

    def test_step_and_rating_units_ignore_the_bullet_shares(self):
        spec = _spec()
        spec["steps"]["s01_anspruchsgrundlage"]["anforderungen"][0]["share"] = "half"
        cs.validate_spec(spec, "step", "branch")
        cs.validate_spec(spec, "rating", "replace")

    @pytest.mark.parametrize("spec", [None, [], "spec", {"order": [], "steps": {}, "total_points": 100}])
    def test_not_a_spec(self, spec):
        with pytest.raises(cs.ChecklistSpecError):
            cs.validate_spec(spec, "bullet", "branch")

    def test_configure_checklist_fails_before_any_call(self):
        ai = MagicMock()
        ev = LLMJudgeEvaluator(ai_service=ai, judge_model="m", custom_prompt_template="x")
        spec = _without(_spec(), "steps", "s02_kaufvertrag", "max_score")
        with pytest.raises(cs.ChecklistSpecError, match="s02_kaufvertrag.max_score"):
            ev.configure_checklist(spec, "bullet", "branch", "declared")
        assert ev.checklist is None
        ai.generate_structured.assert_not_called()


class TestTotalPoints:
    def test_the_spec_total_is_used(self):
        spec = _spec()
        spec["total_points"] = 120.0
        out = cs.finalize(_judgment(), spec, "bullet", "branch", "declared", _verify)
        assert out["total_max"] == 120.0

    @pytest.mark.parametrize("total", [None, 0, -5, "100", float("inf")])
    def test_no_total_is_an_error_not_100(self, total):
        spec = _spec()
        if total is None:
            del spec["total_points"]
        else:
            spec["total_points"] = total
        with pytest.raises(cs.ChecklistSpecError, match="total_points"):
            cs.finalize(_judgment(), spec, "bullet", "branch", "declared", _verify)
        with pytest.raises(cs.ChecklistSpecError, match="total_points"):
            cs.spec_total_points(spec)

    @pytest.mark.parametrize("total", [None, 0, "100"])
    def test_the_rating_table_needs_a_total(self, total):
        with pytest.raises(cs.ChecklistSpecError, match="total_points"):
            cs.rating_percent_table(None, total)


class TestAnswerValuesNeverRaise:
    """finalize coerces every malformed value of the answer, so its errors
    can only come from the spec or the code (see the evaluator tests)."""

    @pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), "zwei", [2], None])
    def test_bullet_status(self, value):
        judgment = _judgment()
        judgment["scores"]["s02_kaufvertrag"]["anforderungen"]["b1"] = {"status": value, "evidence": ""}
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["scores"]["s02_kaufvertrag"]["anforderungen"]["b1"]["status"] == 0

    @pytest.mark.parametrize("value", [float("inf"), float("nan"), "viel", {"a": 1}])
    def test_step_score_and_rating(self, value):
        def entry(key):
            return {key: value, "evidence": "bei Übergabe defekt", "abweichender_weg": False, "reason": ""}
        keys = ("s01_anspruchsgrundlage", "s02_kaufvertrag", "s03_sachmangel")
        scored = cs.finalize({"scores": {k: entry("score") for k in keys}}, _spec(), "step", "replace",
                             "declared", _verify)
        assert scored["total_score"] == 0.0
        rated = cs.finalize({"scores": {k: entry("note") for k in keys}}, _spec(), "rating", "replace",
                            "declared", _verify)
        assert rated["total_score"] == 0.0

    @pytest.mark.parametrize("declared", [["W1-L1"], {"id": "W1-L1"}, 7, None])
    def test_an_unusable_declaration_is_the_musterloesung(self, declared):
        judgment = _judgment()
        judgment["weichenstellungen"]["W1"]["gefolgter_loesungsweg"] = declared
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["weichenstellungen"]["W1"]["declared"] == "musterloesung"


class TestEvaluatorRetries:
    def _evaluator(self, spec=None, unit="bullet", alternatives="branch"):
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.6-luna",
                               custom_prompt_template="{context}\n{prediction}")
        ev.configure_checklist(spec or _spec(), unit, alternatives, "declared")
        ev.ai_service.generate_structured.return_value = {
            "success": True, "content": json.dumps(_judgment()), "metadata": {"finish_reason": "stop"},
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}
        return ev

    def test_a_deterministic_finalize_error_fails_at_once(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        # A spec changed after configure_checklist: finalize trips over it
        # on every attempt, so the call is not repeated.
        del ev.checklist["spec"]["steps"]["s02_kaufvertrag"]["max_score"]
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert ev.ai_service.generate_structured.call_count == 1
        assert result["error"] is True
        meta = result["_call_metadata"]
        assert meta["error_type"] == "checklist_error"
        assert meta["judge_retries"] == []
        assert meta["usage_all_attempts"]["attempts"] == 1
        assert result["error_message"].startswith("checklist scoring failed (KeyError)")
        assert result["_raw_output"]  # the paid answer is kept

    @pytest.mark.parametrize("error", [KeyError("x"), StopIteration(), OverflowError("x"), ZeroDivisionError()])
    def test_no_finalize_error_is_retried(self, monkeypatch, error):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()

        def boom(*_args, **_kwargs):
            raise error

        monkeypatch.setattr(cs, "finalize", boom)
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert ev.ai_service.generate_structured.call_count == 1
        assert result["_call_metadata"]["error_type"] == "checklist_error"
        assert type(error).__name__ in result["error_message"]

    def test_an_unparseable_answer_is_still_retried(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        ok = {"success": True, "content": json.dumps(_judgment()), "metadata": {"finish_reason": "stop"},
              "usage": {}}
        ev.ai_service.generate_structured.return_value = None
        ev.ai_service.generate_structured.side_effect = [
            {"success": True, "content": "kein JSON", "metadata": {"finish_reason": "stop"}, "usage": {}}, ok]
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert ev.ai_service.generate_structured.call_count == 2
        assert not result.get("error") and result["total_score"] == 45.0

    def test_a_non_finite_answer_value_is_scored_not_retried(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        ev = self._evaluator()
        judgment = _judgment()
        judgment["scores"]["s02_kaufvertrag"]["anforderungen"]["b1"]["status"] = 1e999  # json: Infinity
        ev.ai_service.generate_structured.return_value = {
            "success": True, "content": json.dumps(judgment), "metadata": {"finish_reason": "stop"}, "usage": {}}
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert ev.ai_service.generate_structured.call_count == 1
        assert not result.get("error") and result["total_score"] == 45.0
