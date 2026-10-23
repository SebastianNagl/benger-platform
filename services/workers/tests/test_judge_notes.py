"""
Tests for the notes an overlay lets the rubric judge write beside its scores
(``ml_evaluation/judge_notes.py``) and their path through the rubric judge
into the evaluation row. The extended edition's margin notes provide the
real notes; here a fake provider stands in for them.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.judge_notes import (  # noqa: E402
    judge_notes_enabled,
    resolve_judge_notes,
)
from ml_evaluation.llm_judge_evaluator import (  # noqa: E402
    LLMJudgeEvaluator,
    _build_rubric_json_schema,
)

_ANSWER = (
    "A. Zulässigkeit\n\n"
    "Mangels abdrängender Sonderzuweisung richtet sich der Rechtsweg nach **§ 13 GVG**. "
    "Die Streitigkeit ist bürgerlich-rechtlich."
)

_STEPS = {
    "s01_rechtsweg": {"name": "Rechtsweg", "rubric": "r", "max_score": 2},
    "s02_anfechtung": {"name": "Anfechtung", "rubric": "r", "max_score": 1},
}

_TEMPLATE = (
    "SACHVERHALT:\n{context}\n\nMUSTERLÖSUNG:\n{ground_truth}\n\n"
    "BEWERTUNGSBOGEN:\n{bewertungsbogen}\n\nBEARBEITUNG:\n{prediction}"
)

_RULES = "NOTIZEN-REGELN (Feld annotations)"


class FakeNotes:
    """A notes provider as an overlay exposes it (see judge_notes)."""

    def __init__(self, on=True):
        self.on = on
        self.finalized = []

    def enabled(self, metric_parameters):
        if isinstance(metric_parameters, dict) and metric_parameters.get("margin_notes") is False:
            return False
        return self.on

    def schema(self, refs, use_enum=True):
        ref = {"type": "string"}
        if use_enum:
            ref["enum"] = [*refs, "allgemein"]
        return {"type": "array", "items": {"type": "object", "properties": {"ref": ref}}}

    def schema_cost(self, ref_count):
        return 5, ref_count + 4

    def rubric_rules(self):
        return _RULES

    def finalize(self, raw, answer, refs, *, index=None, zeroed_refs=()):
        refs = list(refs)
        zeroed = list(zeroed_refs)
        self.finalized.append({"raw": raw, "answer": answer, "refs": refs, "zeroed": zeroed, "index": index})
        return [
            {"id": f"n{i + 1}", "ref": item["ref"], "zeroed": item["ref"] in zeroed}
            for i, item in enumerate(raw or [])
        ]


@pytest.fixture
def provider():
    """Install a fake provider as the overlay's ``get_judge_notes``."""
    notes = FakeNotes()
    with patch("extension_registry.first_worker_attr", return_value=lambda: notes) as lookup:
        yield notes
    assert all(call.args == ("get_judge_notes",) for call in lookup.call_args_list)


@pytest.fixture
def no_provider():
    with patch("extension_registry.first_worker_attr", return_value=None):
        yield


class TestResolve:
    def test_no_overlay_no_notes(self, no_provider):
        assert resolve_judge_notes() is None
        assert judge_notes_enabled({}) is False

    def test_the_overlay_provider_decides(self, provider):
        assert resolve_judge_notes() is provider
        assert judge_notes_enabled({}) is True
        assert judge_notes_enabled({"margin_notes": False}) is False
        provider.on = False
        assert judge_notes_enabled({}) is False

    def test_a_failing_provider_means_no_notes(self, provider):
        provider.enabled = MagicMock(side_effect=RuntimeError("flag store down"))
        assert judge_notes_enabled({}) is False


class TestSchema:
    def test_annotations_only_with_a_provider(self):
        assert "annotations" not in _build_rubric_json_schema(_STEPS, require_evidence=True)["properties"]
        schema = _build_rubric_json_schema(_STEPS, require_evidence=True, notes=FakeNotes())
        assert schema["required"] == ["scores", "total_score", "overall_assessment", "annotations"]
        ref = schema["properties"]["annotations"]["items"]["properties"]["ref"]
        assert ref["enum"] == [*_STEPS, "allgemein"]

    def test_the_notes_count_against_the_strict_mode_budget(self):
        # Fits without notes, not with their enum values on top.
        steps = {f"s{i:03d}": {"name": "n", "max_score": 9.5} for i in range(48)}
        plain = _build_rubric_json_schema(steps, require_evidence=True)
        assert "enum" in plain["properties"]["scores"]["properties"]["s000"]["properties"]["score"]

        class Costly(FakeNotes):
            def schema_cost(self, ref_count):
                return 5, 500

        schema = _build_rubric_json_schema(steps, require_evidence=True, notes=Costly())
        assert "enum" not in schema["properties"]["scores"]["properties"]["s000"]["properties"]["score"]
        assert "enum" not in schema["properties"]["annotations"]["items"]["properties"]["ref"]


class TestRubricJudgeNotes:
    def _evaluator(self, margin_notes=True, body_notes=None):
        ev = LLMJudgeEvaluator(
            ai_service=MagicMock(), judge_model="gpt-5.4-mini", custom_prompt_template=_TEMPLATE
        )
        ev.bind_task_rubric(SimpleNamespace(id="rub-1", criteria=_STEPS), margin_notes=margin_notes)
        body = {
            "scores": {
                "s01_rechtsweg": {
                    "evidence": "richtet sich der Rechtsweg nach § 13 GVG",
                    "score": 2,
                    "max": 2,
                    "reason": "geprüft",
                },
                "s02_anfechtung": {"evidence": "Eine Anfechtung ist irrelevant", "score": 1, "max": 1, "reason": "x"},
            },
            "total_score": 3,
            "overall_assessment": "solide",
            "annotations": body_notes
            if body_notes is not None
            else [{"ref": "s01_rechtsweg"}, {"ref": "s02_anfechtung"}],
        }
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": json.dumps(body, ensure_ascii=False),
            "usage": {},
            "metadata": {"finish_reason": "stop"},
        }
        return ev

    def _call(self, ev, prediction=_ANSWER):
        return ev._evaluate_multidim_single_call(
            context="Der Sachverhalt.",
            ground_truth="Die Musterlösung.",
            prediction=prediction,
            task_data={"bewertungsbogen": "1. Rechtsweg (2 BE)"},
        )

    def test_binding_turns_notes_on_by_default(self):
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="m", custom_prompt_template=_TEMPLATE)
        assert ev.margin_notes is False
        ev.bind_task_rubric(SimpleNamespace(id="r", criteria=_STEPS))
        assert ev.margin_notes is True

    def test_prompt_and_schema_ask_for_the_notes(self, provider):
        ev = self._evaluator()
        self._call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert kwargs["prompt"].endswith(_RULES)
        assert "annotations" in kwargs["json_schema"]["properties"]

    def test_the_provider_finalizes_against_the_verified_scores(self, provider):
        result = self._call(self._evaluator())
        # s02's evidence is not in the answer: zeroed, and the provider is told.
        assert result["scores"]["s02_anfechtung"]["score"] == 0.0
        [call] = provider.finalized
        assert call["refs"] == list(_STEPS)
        assert call["zeroed"] == ["s02_anfechtung"]
        assert call["answer"] == _ANSWER
        assert call["index"] is not None
        assert result["annotations"] == [
            {"id": "n1", "ref": "s01_rechtsweg", "zeroed": False},
            {"id": "n2", "ref": "s02_anfechtung", "zeroed": True},
        ]

    def test_switched_off_the_judge_is_not_asked(self, provider):
        ev = self._evaluator(margin_notes=False)
        result = self._call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert _RULES not in kwargs["prompt"]
        assert "annotations" not in kwargs["json_schema"]["properties"]
        assert "annotations" not in result
        assert provider.finalized == []

    def test_without_an_overlay_the_judge_is_not_asked(self, no_provider):
        ev = self._evaluator()
        result = self._call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert "annotations" not in kwargs["json_schema"]["properties"]
        assert "annotations" not in result

    def test_e2e_mock_runs_the_note_through_the_provider(self, provider, monkeypatch):
        monkeypatch.setenv("E2E_TEST_MODE", "true")
        ev = self._evaluator()
        ev.ai_service = None
        result = self._call(ev)
        [note] = result["annotations"]
        assert note["ref"] == "s01_rechtsweg"
        # The raw output stays what the "judge" said.
        assert "id" not in json.loads(result["_raw_output"])["annotations"][0]


class TestRowMetrics:
    def test_notes_land_in_the_row_details(self):
        import tasks

        multidim = {
            "scores": {"s01_rechtsweg": {"score": 2.0, "max": 2.0, "reason": "r"}},
            "total_score": 2.0,
            "total_max": 2.0,
            "overall_assessment": "",
            "annotations": [{"id": "n1", "ref": "s01_rechtsweg", "comment": "gut\x07"}],
        }
        metrics, _ = tasks._build_multidim_judge_row_metrics(multidim, "llm_judge_rubric", None)
        assert metrics["llm_judge_rubric"]["details"]["annotations"] == [
            {"id": "n1", "ref": "s01_rechtsweg", "comment": "gut"}
        ]

    def test_rows_without_notes_carry_no_key(self):
        import tasks

        multidim = {"scores": {}, "total_score": 0.0, "total_max": 1.0, "overall_assessment": ""}
        metrics, _ = tasks._build_multidim_judge_row_metrics(multidim, "llm_judge_rubric", None)
        assert "annotations" not in metrics["llm_judge_rubric"]["details"]


class TestFalloesungHookKwargs:
    def test_passed_only_to_a_hook_that_knows_it(self, provider):
        from evaluation.cell_evaluator import _falloesung_margin_notes_kwargs

        def new_hook(*, prediction, margin_notes=False):
            return None

        def old_hook(*, prediction):
            return None

        assert _falloesung_margin_notes_kwargs(new_hook, None) == {"margin_notes": True}
        assert _falloesung_margin_notes_kwargs(new_hook, {"margin_notes": False}) == {"margin_notes": False}
        assert _falloesung_margin_notes_kwargs(old_hook, None) == {}
        # The provider says no: the hook is told so, it is not left to its default.
        provider.on = False
        assert _falloesung_margin_notes_kwargs(new_hook, None) == {"margin_notes": False}

    def test_no_overlay_tells_the_hook_no(self, no_provider):
        from evaluation.cell_evaluator import _falloesung_margin_notes_kwargs

        def new_hook(*, prediction, margin_notes=False):
            return None

        assert _falloesung_margin_notes_kwargs(new_hook, None) == {"margin_notes": False}
