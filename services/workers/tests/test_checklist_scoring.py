"""Checklist scoring for the Bewertungsbogen judge.

The judge marks requirement bullets (or scores / rates steps) and declares
the path it followed at each Weichenstellung; code computes every point, verifies
every quote, and sums unrounded values before one half-up rounding.
"""

import json
from unittest.mock import MagicMock

import pytest

from ml_evaluation import checklist_scoring as cs
from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

ANSWER = (
    "Der Verwaltungsrechtsweg ist nach § 40 I 1 VwGO eröffnet. "
    "H ist als Zweckveranlasser Störer, weil er die Gefahr bezweckt. "
    "Die Kunstfreiheit ist betroffen, der Eingriff aber gerechtfertigt."
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
        "order": ["s01_rechtsweg", "s02_klageart", "s03_stoerer"],
        "steps": {
            "s01_rechtsweg": step("S1", "Rechtsweg", 20.0, [0.5, 0.5]),
            "s02_klageart": step("S2", "Klageart", 30.0, [1.0]),
            "s03_stoerer": step("S3", "Störer", 50.0, [0.6, 0.4], {"id": "W1", "loesungsweg": "musterloesung"}),
        },
        "loesungsweg_steps": {
            "s04_nichtstoerer": step("W1-L1-S1", "Nichtstörer", 50.0, [1.0], {"id": "W1", "loesungsweg": "W1-L1"}),
        },
        "weichenstellungen": [{
            "id": "W1", "bezeichnung": "Zweckveranlasser", "budget": 50.0,
            "loesungswege": [{"id": "musterloesung", "step_keys": ["s03_stoerer"]},
                       {"id": "W1-L1", "step_keys": ["s04_nichtstoerer"]}],
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
            "s01_rechtsweg": _bullets((2, "Verwaltungsrechtsweg ist nach § 40 I 1 VwGO eröffnet"),
                                      (1, "nach § 40 I 1 VwGO")),
            "s02_klageart": _bullets((0, "")),
            "s03_stoerer": _bullets((2, "H ist als Zweckveranlasser Störer"), (2, "erfunden, steht nicht da")),
            "s04_nichtstoerer": _bullets((1, "Die Kunstfreiheit ist betroffen")),
        },
        "weichenstellungen": {"W1": {"gefolgter_loesungsweg": declared, "evidence": "als Zweckveranlasser Störer", "reason": "r"}},
        "overall_assessment": "ok",
    }


class TestSchema:
    def test_bullet_schema_scores_every_path_and_declares_the_weiche(self):
        schema = cs.build_schema(_spec(), "bullet", "branch")
        steps = schema["properties"]["scores"]["properties"]
        assert list(steps) == ["s01_rechtsweg", "s02_klageart", "s03_stoerer", "s04_nichtstoerer"]
        b1 = steps["s01_rechtsweg"]["properties"]["anforderungen"]["properties"]["b1"]
        assert b1["properties"]["status"] == {"type": "integer", "enum": [0, 1, 2]}
        assert schema["properties"]["weichenstellungen"]["properties"]["W1"]["properties"]["gefolgter_loesungsweg"]["enum"] == [
            "musterloesung", "W1-L1"]
        assert "total_score" not in schema["properties"]  # code sums

    def test_replace_schema_has_only_the_primary_path(self):
        schema = cs.build_schema(_spec(), "bullet", "replace")
        assert list(schema["properties"]["scores"]["properties"]) == ["s01_rechtsweg", "s02_klageart", "s03_stoerer"]
        assert "weichenstellungen" not in schema["properties"]

    def test_step_and_rating_units(self):
        step = cs.build_schema(_spec(), "step", "replace")["properties"]["scores"]["properties"]["s01_rechtsweg"]
        assert step["properties"]["score"]["enum"][-1] == 20.0
        rating = cs.build_schema(_spec(), "rating", "replace")["properties"]["scores"]["properties"]["s01_rechtsweg"]
        assert rating["properties"]["note"]["enum"] == list(range(19))

    def test_large_sheets_fall_back_to_ranges(self):
        spec = _spec()
        for k in list(spec["steps"]):
            spec["steps"][k]["anforderungen"] = spec["steps"][k]["anforderungen"] * 200
        status = cs.build_schema(spec, "bullet", "replace")["properties"]["scores"]["properties"]["s01_rechtsweg"][
            "properties"]["anforderungen"]["properties"]["b1"]["properties"]["status"]
        assert status == {"type": "integer", "minimum": 0, "maximum": 2}


class TestPlacement:
    def test_rules_credit_misplaced_work_once_and_ask_for_the_flag(self):
        prompt = cs.system_prompt("bullet", "branch")
        assert "an anderer Stelle steht" in prompt and "nur für einen Schritt" in prompt
        assert "Suche es nur in dem Teil" not in prompt
        assert "fehlplatziert" in cs.closing_rules("step", "replace")

    def test_flag_is_in_the_schema_and_counted(self):
        step = cs.build_schema(_spec(), "step", "replace")["properties"]["scores"]["properties"]["s01_rechtsweg"]
        assert step["properties"]["fehlplatziert"] == {"type": "boolean"}
        judgment = _judgment()
        judgment["scores"]["s03_stoerer"]["fehlplatziert"] = True
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert out["checklist"]["fehlplatziert_steps"] == 1
        assert out["scores"]["s03_stoerer"]["fehlplatziert"] is True
        # A misplacement is recorded, not punished.
        assert out["scores"]["s03_stoerer"]["raw_points"] == pytest.approx(50 * 0.6)


class TestFinalize:
    def test_bullet_points_evidence_and_both_totals(self):
        out = cs.finalize(_judgment(), _spec(), "bullet", "branch", "declared", _verify)
        s1 = out["scores"]["s01_rechtsweg"]
        assert s1["raw_points"] == pytest.approx(20 * (0.5 * 1 + 0.5 * 0.5))  # 15.0
        s3 = out["scores"]["s03_stoerer"]
        assert s3["anforderungen"]["b2"] == {"status": 0, "model_status": 2,
                                             "evidence": "erfunden, steht nicht da", "evidence_verified": False}
        assert s3["raw_points"] == pytest.approx(50 * 0.6)
        branch = out["scores"]["s04_nichtstoerer"]["raw_points"]
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

    def test_replace_mode_counts_the_primary_steps(self):
        judgment = _judgment()
        del judgment["scores"]["s04_nichtstoerer"]
        del judgment["weichenstellungen"]
        out = cs.finalize(judgment, _spec(), "bullet", "replace", "declared", _verify)
        assert out["checklist"]["totals"] == {"declared": 45.0, "best": 45.0}

    def test_missing_items_are_reported_for_a_retry(self):
        judgment = _judgment()
        del judgment["scores"]["s02_klageart"]
        del judgment["scores"]["s01_rechtsweg"]["anforderungen"]["b2"]
        del judgment["weichenstellungen"]
        out = cs.finalize(judgment, _spec(), "bullet", "branch", "declared", _verify)
        assert set(out["missing"]) == {"s02_klageart", "s01_rechtsweg.b2", "weichenstellungen.W1"}

    def test_totals_round_half_up_once(self):
        spec = _spec()
        spec["steps"]["s01_rechtsweg"]["max_score"] = 0.5
        judgment = _judgment()
        judgment["scores"]["s01_rechtsweg"] = _bullets((2, "nach § 40 I 1 VwGO"), (0, ""))
        out = cs.finalize(judgment, spec, "bullet", "replace", "declared", _verify)
        assert out["scores"]["s01_rechtsweg"]["raw_points"] == 0.25
        assert out["scores"]["s01_rechtsweg"]["score"] == 0.5    # half up, not banker's
        assert cs.round_half_up(0.25) == 0.5 and cs.round_half_up(0.75) == 1.0

    def test_rating_unit_weights_notes_by_step_maximum(self):
        judgment = {
            "scores": {
                "s01_rechtsweg": {"note": 18, "evidence": "nach § 40 I 1 VwGO", "abweichender_weg": False, "reason": ""},
                "s02_klageart": {"note": 9, "evidence": "erfunden", "abweichender_weg": False, "reason": ""},
                "s03_stoerer": {"note": 9, "evidence": "als Zweckveranlasser Störer", "abweichender_weg": True, "reason": ""},
            },
            "overall_assessment": "",
        }
        out = cs.finalize(judgment, _spec(), "rating", "replace", "declared", _verify)
        assert out["scores"]["s02_klageart"]["note"] == 0  # unverified quote
        assert out["checklist"]["totals"]["declared"] == 45.0   # 20 + 0 + 25
        assert out["checklist"]["rating_grade"] == pytest.approx((18 * 20 + 0 * 30 + 9 * 50) / 100)
        assert out["checklist"]["abweichender_weg_steps"] == 1


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
        del incomplete["scores"]["s02_klageart"]
        self._respond(ev, incomplete, _judgment())
        result = ev._evaluate_multidim_single_call(context="SV", ground_truth="ML", prediction=ANSWER)
        assert not result.get("error") and ev.ai_service.generate_structured.call_count == 2

    def test_spec_without_bound_rubric_supplies_the_criteria(self):
        ev = self._evaluator()
        assert list(ev.custom_criteria) == ["s01_rechtsweg", "s02_klageart", "s03_stoerer"]
        assert ev.is_multidim_mode() and ev.rubric_mode

    def test_bad_options_rejected(self):
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="m", custom_prompt_template="x")
        with pytest.raises(ValueError):
            ev.configure_checklist(_spec(), "points", "branch")
