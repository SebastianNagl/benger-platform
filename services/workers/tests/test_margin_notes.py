"""
Tests for the margin notes (Randbemerkungen) of the LLM judges
(``ml_evaluation/margin_notes.py``) and their path through the rubric judge
into the evaluation row.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import (  # noqa: E402
    RUBRIC_JUDGE_MARGIN_NOTES_RULES,
    LLMJudgeEvaluator,
    _build_rubric_json_schema,
)
from ml_evaluation.margin_notes import (  # noqa: E402
    MARGIN_NOTE_GENERAL_REF,
    MARGIN_NOTES_MAX,
    MARGIN_NOTES_MAX_TOKENS_HEADROOM,
    finalize_margin_notes,
    locate_quote,
    margin_notes_enabled,
    margin_notes_max_tokens,
    margin_notes_schema,
)

_ANSWER = (
    "A. Zulässigkeit\n\n"
    "I\\. Eröffnung des Zivilrechtswegs\n\n"
    "Mangels abdrängender Sonderzuweisung richtet sich der Rechtsweg nach **§ 13 GVG**. "
    "Die Streitigkeit ist bürgerlich-rechtlich.\n\n"
    "1\\. Die Bestellung ist eine „Willenserklärung“ im Sinne des § 130 Abs. 1 S. 1 BGB, "
    "denn K hat gegenüber V verbindlich erklärt, das Fahrrad zu kaufen."
)

_STEPS = {
    "s01_rechtsweg": {"name": "Rechtsweg", "rubric": "r", "max_score": 2},
    "s02_anfechtung": {"name": "Anfechtung", "rubric": "r", "max_score": 1},
}

_TEMPLATE = (
    "SACHVERHALT:\n{context}\n\nMUSTERLÖSUNG:\n{ground_truth}\n\n"
    "BEWERTUNGSBOGEN:\n{bewertungsbogen}\n\nBEARBEITUNG:\n{prediction}"
)


def _note(ref="s01_rechtsweg", kind="mangel", quote="Die Streitigkeit ist bürgerlich-rechtlich", comment="Begründen."):
    return {"ref": ref, "kind": kind, "quote": quote, "comment": comment}


class TestLocateQuote:
    def test_exact_quote_spans_the_passage(self):
        start, end = locate_quote("Die Streitigkeit ist bürgerlich-rechtlich", _ANSWER)
        assert _ANSWER[start:end] == "Die Streitigkeit ist bürgerlich-rechtlich"

    def test_markdown_markers_inside_the_passage_stay_in_the_anchor(self):
        start, end = locate_quote("richtet sich der Rechtsweg nach § 13 GVG", _ANSWER)
        assert _ANSWER[start:end] == "richtet sich der Rechtsweg nach **§ 13 GVG"

    def test_a_typo_and_a_left_out_word_keep_the_anchor(self):
        start, end = locate_quote("Die Bestelung ist eine Willenserklärung im Sinne des § 130 BGB", _ANSWER)
        assert _ANSWER[start:end].startswith("Die Bestellung ist eine")
        assert _ANSWER[start:end].endswith("BGB")

    def test_an_ellipsis_quote_anchors_its_longest_fragment(self):
        start, end = locate_quote("Mangels … K hat gegenüber V verbindlich erklärt", _ANSWER)
        assert _ANSWER[start:end] == "K hat gegenüber V verbindlich erklärt"

    def test_a_stray_word_far_off_does_not_stretch_the_anchor(self):
        answer = "die Lage ist klar. " + "x " * 8 + "Der Anspruch des K gegen V ist entstanden."
        start, end = locate_quote("die Der Anspruch des K gegen V ist entstanden", answer)
        assert answer[start:end] == "Der Anspruch des K gegen V ist entstanden"

    def test_quote_not_in_the_answer(self):
        assert locate_quote("Der Verwaltungsakt ist rechtswidrig und aufzuheben", _ANSWER) is None

    @pytest.mark.parametrize("quote", ["", "GVG", "… …"])
    def test_too_short_to_anchor(self, quote):
        assert locate_quote(quote, _ANSWER) is None

    def test_empty_answer(self):
        assert locate_quote("Die Streitigkeit ist bürgerlich-rechtlich", "") is None


class TestFinalizeMarginNotes:
    def test_verified_note_carries_the_anchor(self):
        [note] = finalize_margin_notes([_note()], _ANSWER, _STEPS)
        assert note == {
            "id": "n1",
            "ref": "s01_rechtsweg",
            "kind": "mangel",
            "comment": "Begründen.",
            "quote": "Die Streitigkeit ist bürgerlich-rechtlich",
            "verified": True,
            "anchor_text": "Die Streitigkeit ist bürgerlich-rechtlich",
        }

    def test_a_made_up_quote_keeps_its_comment_but_no_anchor(self):
        [note] = finalize_margin_notes(
            [_note(quote="Die Streitigkeit ist öffentlich-rechtlich")], _ANSWER, _STEPS
        )
        assert note["verified"] is False
        assert note["anchor_text"] is None
        assert note["comment"] == "Begründen."

    def test_unknown_ref_and_empty_comment_are_dropped(self):
        notes = finalize_margin_notes(
            [_note(ref="s99_fantasie"), _note(comment="  "), _note(comment=None), "kein dict"],
            _ANSWER,
            _STEPS,
        )
        assert notes == []

    def test_general_ref_and_unknown_kind(self):
        [note] = finalize_margin_notes([_note(ref=MARGIN_NOTE_GENERAL_REF, kind="lob")], _ANSWER, _STEPS)
        assert note["ref"] == MARGIN_NOTE_GENERAL_REF
        assert note["kind"] == "hinweis"

    def test_praise_on_a_zeroed_step_is_dropped(self):
        notes = finalize_margin_notes(
            [_note(kind="positiv"), _note(kind="mangel")], _ANSWER, _STEPS, zeroed_refs=["s01_rechtsweg"]
        )
        assert [n["kind"] for n in notes] == ["mangel"]
        assert notes[0]["id"] == "n1"

    def test_at_most_the_cap_is_kept(self):
        notes = finalize_margin_notes([_note()] * (MARGIN_NOTES_MAX + 5), _ANSWER, _STEPS)
        assert len(notes) == MARGIN_NOTES_MAX
        assert notes[-1]["id"] == f"n{MARGIN_NOTES_MAX}"

    @pytest.mark.parametrize("raw", [None, {}, "x"])
    def test_no_list_no_notes(self, raw):
        assert finalize_margin_notes(raw, _ANSWER, _STEPS) == []


class TestSchemaAndFlag:
    def test_schema_limits_ref_to_the_steps(self):
        schema = margin_notes_schema(["a", "b"])
        item = schema["items"]
        assert item["properties"]["ref"]["enum"] == ["a", "b", MARGIN_NOTE_GENERAL_REF]
        assert item["required"] == ["ref", "kind", "quote", "comment"]
        assert item["additionalProperties"] is False
        assert "enum" not in margin_notes_schema(["a"], use_enum=False)["items"]["properties"]["ref"]

    def test_rubric_schema_adds_annotations_only_when_asked(self):
        assert "annotations" not in _build_rubric_json_schema(_STEPS, require_evidence=True)["properties"]
        schema = _build_rubric_json_schema(_STEPS, require_evidence=True, margin_notes=True)
        assert schema["required"] == ["scores", "total_score", "overall_assessment", "annotations"]
        ref = schema["properties"]["annotations"]["items"]["properties"]["ref"]
        assert ref["enum"] == [*_STEPS, MARGIN_NOTE_GENERAL_REF]

    def test_oversized_rubric_drops_the_ref_enum_with_the_score_enums(self):
        steps = {f"s{i:03d}": {"name": "n", "max_score": 10} for i in range(60)}
        schema = _build_rubric_json_schema(steps, require_evidence=True, margin_notes=True)
        assert "enum" not in schema["properties"]["scores"]["properties"]["s000"]["properties"]["score"]
        assert "enum" not in schema["properties"]["annotations"]["items"]["properties"]["ref"]

    @pytest.mark.parametrize(
        "params, expected",
        [(None, True), ({}, True), ({"margin_notes": True}, True), ({"margin_notes": False}, False)],
    )
    def test_enabled_unless_switched_off(self, params, expected):
        assert margin_notes_enabled(params) is expected

    def test_notes_get_token_room_on_top_of_the_budget(self):
        assert margin_notes_max_tokens(4096) == 4096 + MARGIN_NOTES_MAX_TOKENS_HEADROOM
        assert margin_notes_max_tokens("4096") == 4096 + MARGIN_NOTES_MAX_TOKENS_HEADROOM
        assert margin_notes_max_tokens(None) is None


class TestRubricJudgeMarginNotes:
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
            "annotations": body_notes if body_notes is not None else [
                _note(kind="positiv", quote="richtet sich der Rechtsweg nach § 13 GVG", comment="Gut."),
                _note(ref="s02_anfechtung", kind="positiv", quote="Eine Anfechtung ist irrelevant", comment="Gut."),
                _note(ref="s02_anfechtung", comment="Anfechtung fehlt."),
            ],
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

    def test_binding_turns_margin_notes_on_by_default(self):
        ev = LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="m", custom_prompt_template=_TEMPLATE)
        assert ev.margin_notes is False
        ev.bind_task_rubric(SimpleNamespace(id="r", criteria=_STEPS))
        assert ev.margin_notes is True

    def test_prompt_and_schema_ask_for_the_notes(self):
        ev = self._evaluator()
        self._call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert kwargs["prompt"].endswith(RUBRIC_JUDGE_MARGIN_NOTES_RULES)
        assert "annotations" in kwargs["json_schema"]["properties"]

    def test_notes_are_checked_and_follow_the_verified_scores(self):
        result = self._call(self._evaluator())
        # s02's evidence is not in the answer: its points and its praise go.
        assert result["scores"]["s02_anfechtung"]["score"] == 0.0
        assert [(n["ref"], n["kind"]) for n in result["annotations"]] == [
            ("s01_rechtsweg", "positiv"),
            ("s02_anfechtung", "mangel"),
        ]
        assert result["annotations"][0]["anchor_text"] == "richtet sich der Rechtsweg nach **§ 13 GVG"

    def test_switched_off_the_judge_is_not_asked(self):
        ev = self._evaluator(margin_notes=False)
        result = self._call(ev)
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        assert RUBRIC_JUDGE_MARGIN_NOTES_RULES not in kwargs["prompt"]
        assert "annotations" not in kwargs["json_schema"]["properties"]
        assert "annotations" not in result

    def test_e2e_mock_sets_an_anchored_note(self, monkeypatch):
        monkeypatch.setenv("E2E_TEST_MODE", "true")
        ev = self._evaluator()
        ev.ai_service = None
        result = self._call(ev)
        [note] = result["annotations"]
        assert note["verified"] is True
        assert note["anchor_text"] and note["anchor_text"] in _ANSWER
        # The raw output stays what the "judge" said.
        assert "verified" not in json.loads(result["_raw_output"])["annotations"][0]


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
    def test_passed_only_to_a_hook_that_knows_it(self):
        from evaluation.cell_evaluator import _falloesung_margin_notes_kwargs

        def new_hook(*, prediction, margin_notes=False):
            return None

        def old_hook(*, prediction):
            return None

        assert _falloesung_margin_notes_kwargs(new_hook, None) == {"margin_notes": True}
        assert _falloesung_margin_notes_kwargs(new_hook, {"margin_notes": False}) == {"margin_notes": False}
        assert _falloesung_margin_notes_kwargs(old_hook, None) == {}
