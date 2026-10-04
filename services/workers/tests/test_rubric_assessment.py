"""Rubric judge prompt profiles and the structured assessment block.

The status and grade expectations mirror the reference post-processor of the
second-exam assessor proposal (``benger_assessor_v1``, Benchmark v2), which
the platform implements instead of shipping: same statuses, same
provisional/unavailable semantics, same lower-threshold grade mapping.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation import rubric_assessment
from ml_evaluation.llm_judge_evaluator import (
    RUBRIC_JUDGE_CLOSING_RULES,
    RUBRIC_JUDGE_SYSTEM_PROMPT,
    LLMJudgeEvaluator,
    _build_rubric_json_schema,
)
from ml_evaluation.rubric_assessment import (
    normalize_assessment,
    register_rubric_prompt_profile,
)

# The ten v1 dimensions with their maxima (BenGER v1 App. L.1) — the
# standard second-exam sheet keeps them for comparability.
MAXIMA = {
    "ergebnisrichtigkeit": 20,
    "vollstaendigkeit": 10,
    "rechtsgrundlagen": 10,
    "rechtskenntnis": 15,
    "subsumtion": 15,
    "schwerpunktsetzung": 10,
    "methodischer_stil": 10,
    "gliederung": 5,
    "sprache": 3,
    "formalia": 2,
}
CRITERIA = {k: {"name": k, "description": k, "max_score": v} for k, v in MAXIMA.items()}
ANSWER = "Die Klage ist zulässig und begründet. Der Beklagte wird verurteilt, an den Kläger 500 Euro zu zahlen."
EVIDENCE = "Die Klage ist zulässig und begründet."


def _assessment(**overrides):
    body = {
        "assessment_status": "scored",
        "work_products": [
            {
                "product": "Urteil",
                "requirement_basis": "Bearbeitervermerk: Entscheidung des Gerichts",
                "status": "fulfilled",
                "reason": "Tenor und Entscheidungsgründe liegen vor.",
            }
        ],
        "supplementary_reviews": [
            {
                "subject": "Hilfsgutachten",
                "requirement_basis": "Kein Auftrag",
                "status": "not_required",
                "assumption": None,
                "reason": "Die Hauptlösung schneidet keine Frage ab.",
            }
        ],
        "error_chains": [],
        "review_reasons": [],
        "improvements": [],
    }
    body.update(overrides)
    return body


def _judge_body(score_fraction=1.0, **assessment):
    return {
        "scores": {
            k: {"evidence": EVIDENCE, "score": v * score_fraction, "max": v, "reason": "ok"}
            for k, v in MAXIMA.items()
        },
        "total_score": 100 * score_fraction,
        "overall_assessment": "solide",
        **_assessment(**assessment),
    }


@pytest.fixture(autouse=True)
def _isolated_profiles(monkeypatch):
    monkeypatch.setattr(rubric_assessment, "_PROFILES", {})


def _evaluator(body, params=None):
    ev = LLMJudgeEvaluator(
        ai_service=MagicMock(),
        judge_model="gpt-5.4-mini",
        custom_prompt_template="SV {context}\nML {ground_truth}\nBB {bewertungsbogen}\nB {prediction}",
    )
    ev.bind_task_rubric(SimpleNamespace(id="rub-1", criteria=CRITERIA), params)
    ev.ai_service.generate_structured.return_value = {
        "success": True,
        "content": json.dumps(body, ensure_ascii=False),
        "usage": {},
        "metadata": {"finish_reason": "stop"},
    }
    return ev


def _call(ev):
    return ev._evaluate_multidim_single_call(
        context="Akte", ground_truth="Prüfervermerk", prediction=ANSWER,
        task_data={"bewertungsbogen": "Standardbogen"},
    )


class TestNormalizeAssessment:
    def test_scored_is_eligible(self):
        out = normalize_assessment(_assessment())
        assert out["assessment_status"] == "scored"
        assert out["score_status"] == "scored"
        assert out["aggregation_eligible"] is True
        assert out["work_products"][0]["status"] == "fulfilled"
        assert out["supplementary_reviews"][0]["assumption"] is None
        assert out["validation_warnings"] == []

    def test_review_required_is_provisional(self):
        out = normalize_assessment(
            _assessment(assessment_status="review_required", review_reasons=["Konflikt mit Referenz."])
        )
        assert out["score_status"] == "provisional"
        assert out["aggregation_eligible"] is False
        assert out["review_reasons"] == ["Konflikt mit Referenz."]

    def test_not_evaluable_is_unavailable(self):
        out = normalize_assessment(
            _assessment(assessment_status="not_evaluable", review_reasons=["Akte fehlt."])
        )
        assert out["score_status"] == "unavailable"
        assert out["aggregation_eligible"] is False

    def test_not_evaluable_without_reason_downgrades_to_review(self):
        out = normalize_assessment(_assessment(assessment_status="not_evaluable"))
        assert out["assessment_status"] == "review_required"
        assert out["review_reasons"]
        assert out["validation_warnings"]

    @pytest.mark.parametrize("status", [None, "passed", 3])
    def test_unknown_status_becomes_review_required(self, status):
        out = normalize_assessment(_assessment(assessment_status=status))
        assert out["assessment_status"] == "review_required"
        assert out["aggregation_eligible"] is False

    def test_malformed_entries_are_dropped_not_fatal(self):
        out = normalize_assessment(
            _assessment(
                work_products=[
                    {"product": "Urteil", "requirement_basis": "BV", "status": "done", "reason": "x"},
                    "kein Objekt",
                    {"product": "", "requirement_basis": "BV", "status": "missing", "reason": "x"},
                    {"product": "Klage", "requirement_basis": "BV", "status": "missing", "reason": "fehlt"},
                ]
            )
        )
        assert [w["product"] for w in out["work_products"]] == ["Klage"]
        assert len(out["validation_warnings"]) == 3

    def test_improvements_capped_at_three(self):
        out = normalize_assessment(_assessment(improvements=["a", "b", "c", "d"]))
        assert out["improvements"] == ["a", "b", "c"]

    def test_input_is_not_mutated(self):
        body = _assessment(improvements=["a", "b", "c", "d"])
        snapshot = json.dumps(body, sort_keys=True)
        normalize_assessment(body)
        assert json.dumps(body, sort_keys=True) == snapshot


class TestSchema:
    def test_default_schema_is_unchanged(self):
        schema = _build_rubric_json_schema(CRITERIA, require_evidence=True)
        assert schema["required"] == ["scores", "total_score", "overall_assessment"]

    def test_structured_schema_is_closed_and_complete(self):
        schema = _build_rubric_json_schema(CRITERIA, require_evidence=True, structured_assessment=True)
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for key in ("assessment_status", "work_products", "supplementary_reviews",
                    "error_chains", "review_reasons", "improvements"):
            assert key in schema["required"]
        item = schema["properties"]["supplementary_reviews"]["items"]
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"])
        # Strict-mode subset only.
        text = json.dumps(schema)
        for keyword in ("multipleOf", '"if"', "maxItems", "oneOf"):
            assert keyword not in text


class TestPromptProfile:
    def test_default_profile_keeps_the_bewertungsbogen_wording(self):
        ev = _evaluator(_judge_body())
        result = _call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert kwargs["system_prompt"] == RUBRIC_JUDGE_SYSTEM_PROMPT
        assert kwargs["prompt"].endswith(RUBRIC_JUDGE_CLOSING_RULES)
        assert result["_judge_prompts_used"]["prompt_profile"] == "default"
        assert "assessment" not in result

    def test_registered_profile_replaces_system_prompt_and_closing_rules(self):
        register_rubric_prompt_profile("zweites_examen", "SYS-2", "CLOSE-2")
        ev = _evaluator(_judge_body(), {"prompt_profile": "zweites_examen"})
        result = _call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert kwargs["system_prompt"] == "SYS-2"
        assert kwargs["prompt"].endswith("CLOSE-2")
        assert RUBRIC_JUDGE_CLOSING_RULES not in kwargs["prompt"]
        assert result["_judge_prompts_used"]["prompt_profile"] == "zweites_examen"

    def test_unknown_profile_fails_loudly_without_calling_the_judge(self):
        ev = _evaluator(_judge_body(), {"prompt_profile": "zweites_examen"})
        result = _call(ev)
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "config_error"
        assert "zweites_examen" in result["error_message"]
        ev.ai_service.generate_structured.assert_not_called()

    def test_profile_needs_all_parts(self):
        with pytest.raises(ValueError):
            register_rubric_prompt_profile("x", "", "close")


class TestStructuredAssessmentCall:
    def test_assessment_rides_along_and_never_changes_scores(self):
        ev = _evaluator(_judge_body(0.5, improvements=["a"]), {"structured_assessment": True})
        result = _call(ev)
        schema = ev.ai_service.generate_structured.call_args.kwargs["json_schema"]
        assert "work_products" in schema["properties"]
        assert result["total_score"] == 50.0
        assert result["assessment"]["assessment_status"] == "scored"
        assert result["assessment"]["work_products"][0]["product"] == "Urteil"

    def test_review_required_keeps_provisional_scores(self):
        body = _judge_body(assessment_status="review_required", review_reasons=["Referenz strittig."])
        result = _call(_evaluator(body, {"structured_assessment": True}))
        assert result["total_score"] == 100.0
        assert result["assessment"]["score_status"] == "provisional"

    def test_not_evaluable_is_a_terminal_error_carrying_the_diagnosis(self):
        body = _judge_body(assessment_status="not_evaluable", review_reasons=["Aktenauszug fehlt."])
        result = _call(_evaluator(body, {"structured_assessment": True}))
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "not_evaluable"
        assert "Aktenauszug fehlt." in result["error_message"]
        assert result["assessment"]["score_status"] == "unavailable"

    def test_flag_is_ignored_outside_rubric_mode(self):
        ev = LLMJudgeEvaluator(
            ai_service=MagicMock(),
            judge_model="gpt-5.4-mini",
            custom_criteria=CRITERIA,
            custom_prompt_template="{prediction}",
        )
        ev.structured_assessment = True
        ev.ai_service.generate_structured.return_value = {
            "success": True, "content": json.dumps(_judge_body()), "usage": {}, "metadata": {},
        }
        result = _call(ev)
        assert "assessment" not in result
        schema = ev.ai_service.generate_structured.call_args.kwargs["json_schema"]
        assert "work_products" not in schema["properties"]

    def test_e2e_mock_emits_a_scored_assessment(self, monkeypatch):
        monkeypatch.setenv("E2E_TEST_MODE", "true")
        ev = _evaluator(_judge_body(), {"structured_assessment": True})
        result = _call(ev)
        assert result["assessment"]["assessment_status"] == "scored"
        ev.ai_service.generate_structured.assert_not_called()


class TestRowShape:
    def _row(self, result):
        import tasks

        return tasks._build_multidim_judge_row_metrics(result, "llm_judge_rubric", None)

    def test_scored_row_carries_assessment_and_status(self):
        result = _call(_evaluator(_judge_body(), {"structured_assessment": True}))
        metrics, normalized = self._row(result)
        details = metrics["llm_judge_rubric"]["details"]
        assert normalized == 1.0
        assert details["assessment"]["work_products"][0]["status"] == "fulfilled"
        assert details["score_status"] == "scored"
        assert details["aggregation_eligible"] is True

    def test_not_evaluable_row_is_an_error_row_with_diagnosis(self):
        import tasks

        body = _judge_body(assessment_status="not_evaluable", review_reasons=["Akte fehlt."])
        result = _call(_evaluator(body, {"structured_assessment": True}))
        metrics, normalized = self._row(result)
        blob = metrics["llm_judge_rubric"]
        assert normalized is None
        assert blob["value"] is None
        assert "Akte fehlt." in blob["error"]
        assert blob["details"]["assessment"]["score_status"] == "unavailable"
        assert tasks._row_is_terminal_error(metrics) is True

    def test_rows_without_the_flag_have_no_assessment(self):
        metrics, _ = self._row(_call(_evaluator(_judge_body())))
        assert "assessment" not in metrics["llm_judge_rubric"]["details"]


class TestGradeMapping:
    """The rubric lane's default Notenschlüssel on a 100-point sheet equals
    the proposal's lower-threshold mapping: inclusive thresholds, no rounding
    of half points (49.5 -> 3, 50 -> 4)."""

    THRESHOLDS = (13, 26, 39, 50, 54, 57, 60, 64, 67, 70, 74, 77, 80, 84, 87, 90, 94, 97)

    def _grade(self, points):
        from rubric_structure import grade_for_rubric

        rubric = SimpleNamespace(total_points=100, grade_scale=None)
        return grade_for_rubric(rubric, points, 100, None)

    def test_every_threshold_and_the_half_point_below(self):
        for i, threshold in enumerate(self.THRESHOLDS):
            assert self._grade(threshold - 0.5)[0] == i
            assert self._grade(threshold)[0] == i + 1

    def test_monotone_over_all_half_points_and_pass_at_four(self):
        grades = [self._grade(i / 2) for i in range(201)]
        assert [g for g, _p, _s in grades] == sorted(g for g, _p, _s in grades)
        assert self._grade(49.5)[:2] == (3, False)
        assert self._grade(50)[:2] == (4, True)
        assert self._grade(100)[0] == 18
