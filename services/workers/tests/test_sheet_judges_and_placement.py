"""Sheet judges beyond ``llm_judge_rubric`` and sheets graded by argument (core 2.81).

* ``task_rubric_resolution.is_rubric_judge`` is true for any config whose
  ``metric_parameters`` say ``use_task_rubric: true``, so such a config is
  held like the Bewertungsbogen judge while its task has no usable sheet.
* ``structure.placement == "anywhere"`` survives validation, normalization
  and the equality check, and switches the Bewertungsbogen judge's
  placement rule to the argument wording in both lanes. A sheet without it
  grades with exactly the texts it always had.
"""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ml_evaluation import checklist_scoring
from ml_evaluation.llm_judge_evaluator import (
    RUBRIC_JUDGE_CLOSING_RULES,
    RUBRIC_JUDGE_SYSTEM_PROMPT,
    LLMJudgeEvaluator,
    rubric_judge_prompts,
)
from rubric_structure import (
    PLACEMENT_ANYWHERE,
    criteria_from_structure,
    normalize_structure,
    sheet_placement,
    structure_without_guidance,
    validate_structure,
)
from task_rubric_resolution import (
    USE_TASK_RUBRIC_PARAM,
    is_rubric_judge,
    split_held_rubric_judges,
)
from task_rubric_service import structure_equal


def _structure(placement=None, with_requirements=False):
    nodes = [
        {"id": "a", "level": 0, "kind": "section", "label": "I.", "title": "Fond"},
        {"id": "s1", "level": 1, "kind": "step", "label": "", "title": "First criterion", "max_score": 1},
        {"id": "s2", "level": 1, "kind": "step", "label": "", "title": "Argumentation", "max_score": 1.5},
    ]
    if with_requirements:
        nodes[1]["requirements"] = [{"text": "first requirement", "points": 0.5}, {"text": "second requirement", "points": 0.5}]
        nodes[2]["requirements"] = [{"text": "premier argument", "points": 1}, {"text": "second argument", "points": 0.5}]
    structure = {"version": 1, "nodes": nodes}
    if placement is not None:
        structure["placement"] = placement
    return structure


class TestSheetJudges:
    def test_the_bewertungsbogen_judge_always_is_one(self):
        assert is_rubric_judge({"metric": "llm_judge_rubric"}) is True

    def test_any_config_with_use_task_rubric_is_one(self):
        cfg = {"metric": "llm_judge_feedback", "metric_parameters": {USE_TASK_RUBRIC_PARAM: True}}
        assert USE_TASK_RUBRIC_PARAM == "use_task_rubric"
        assert is_rubric_judge(cfg) is True

    @pytest.mark.parametrize(
        "params", [None, {}, {"use_task_rubric": False}, {"use_task_rubric": "yes"}, "x"]
    )
    def test_other_configs_are_not(self, params):
        assert is_rubric_judge({"metric": "llm_judge_feedback", "metric_parameters": params}) is False
        assert is_rubric_judge(None) is False

    def test_a_sheet_judge_without_a_sheet_is_held_the_others_kept(self):
        sheet = {"id": "sheet", "metric": "llm_judge_feedback", "metric_parameters": {"use_task_rubric": True}}
        own = {"id": "own", "metric": "llm_judge_feedback", "metric_parameters": {}}
        with patch("task_rubric_resolution.resolve_grading_rubric", return_value=None) as resolve:
            kept, held = split_held_rubric_judges(MagicMock(), SimpleNamespace(id="t"), [sheet, own])
        assert kept == [own] and held == [sheet]
        resolve.assert_called_once()

    def test_a_sheet_judge_with_a_sheet_is_kept(self):
        sheet = {"id": "sheet", "metric": "llm_judge_feedback", "metric_parameters": {"use_task_rubric": True}}
        with patch("task_rubric_resolution.resolve_grading_rubric", return_value=object()):
            kept, held = split_held_rubric_judges(MagicMock(), SimpleNamespace(id="t"), [sheet])
        assert kept == [sheet] and held == []


class TestPlacementContract:
    def test_absent_is_the_default_and_valid(self):
        structure = _structure()
        assert validate_structure(structure) == []
        assert "placement" not in normalize_structure(structure)
        assert sheet_placement(structure) is None
        assert sheet_placement(None) is None

    def test_anywhere_validates_and_survives_normalization(self):
        structure = _structure(PLACEMENT_ANYWHERE)
        assert PLACEMENT_ANYWHERE == "anywhere"
        assert validate_structure(structure) == []
        normalized = normalize_structure(structure)
        assert normalized["placement"] == "anywhere"
        assert sheet_placement(normalized) == "anywhere"
        assert structure_without_guidance(normalized)["placement"] == "anywhere"
        # The derived criteria are the same either way.
        assert criteria_from_structure(normalized) == criteria_from_structure(normalize_structure(_structure()))

    @pytest.mark.parametrize("value", ["everywhere", "", 1, True])
    def test_other_values_are_refused(self, value):
        errors = validate_structure(_structure(value))
        assert any("structure.placement" in e for e in errors)

    def test_a_placement_change_is_a_change(self):
        assert structure_equal(_structure(), _structure()) is True
        assert structure_equal(_structure(), _structure(PLACEMENT_ANYWHERE)) is False
        assert structure_equal(_structure(PLACEMENT_ANYWHERE), _structure(PLACEMENT_ANYWHERE)) is True


def _row(placement=None, with_requirements=False):
    structure = normalize_structure(_structure(placement, with_requirements))
    return SimpleNamespace(
        id="rubric-1", structure=structure, criteria=criteria_from_structure(structure),
        total_points=2.5, title=None, grade_scale=None, generation_metadata=None, generator_model_id=None,
    )


def _judge():
    return LLMJudgeEvaluator(ai_service=MagicMock(), judge_model="gpt-5.4-mini", custom_prompt_template="{prediction}")


class TestJudgeWording:
    def test_default_texts_are_unchanged(self):
        assert rubric_judge_prompts(None) == (RUBRIC_JUDGE_SYSTEM_PROMPT, RUBRIC_JUDGE_CLOSING_RULES)

    def test_anywhere_swaps_only_the_placement_rule_of_the_step_lane(self):
        system, closing = rubric_judge_prompts("anywhere")
        assert system != RUBRIC_JUDGE_SYSTEM_PROMPT and closing != RUBRIC_JUDGE_CLOSING_RULES
        assert "bewertet nach Argumenten" in system and "bewertet nach Argumenten" in closing
        assert "suche das Zitat nur in dem Teil der Bearbeitung" not in system
        assert "aus dem Teil der Bearbeitung stammen, der die Aufgabe" not in closing
        # The other rules stay.
        assert "Gibt es keine solche Stelle, bleibt \"evidence\" leer" in system
        assert closing.startswith("VERBINDLICHE REGELN FÜR DIE BEWERTUNG")

    def test_the_requirement_lane_switches_too(self):
        default = checklist_scoring.system_prompt("binary", "branch")
        anywhere = checklist_scoring.system_prompt("binary", "branch", True, "anywhere")
        assert checklist_scoring.placement_rule() in default
        assert checklist_scoring.placement_rule("anywhere") in anywhere
        assert checklist_scoring.placement_rule() not in anywhere
        assert checklist_scoring.placement_rule("anywhere") in checklist_scoring.closing_rules(
            "binary", "branch", True, "anywhere"
        )
        assert checklist_scoring.closing_rules("binary", "branch") == checklist_scoring.closing_rules(
            "binary", "branch", True, None
        )

    def test_binding_reads_the_sheets_placement(self):
        ev = _judge()
        ev.bind_task_rubric(_row("anywhere"), margin_notes=False)
        assert ev.rubric_placement == "anywhere"
        ev.bind_task_rubric(_row(), margin_notes=False)
        assert ev.rubric_placement is None
        ev.bind_task_rubric(SimpleNamespace(id="legacy", criteria=copy.deepcopy(_row().criteria)))
        assert ev.rubric_placement is None

    def test_a_requirement_sheet_by_argument_gets_the_argument_rule(self):
        ev = _judge()
        ev.bind_task_rubric(_row("anywhere", with_requirements=True), margin_notes=False)
        if ev.checklist is None:  # pragma: no cover - the sheet must take the requirement lane
            pytest.fail("expected the requirement lane")
        assert checklist_scoring.placement_rule("anywhere") in ev.checklist["system_prompt"]
        assert checklist_scoring.placement_rule("anywhere") in ev.checklist["closing_rules"]

    def test_the_step_lane_call_sends_the_argument_wording(self):
        ev = _judge()
        ev.bind_task_rubric(_row("anywhere"), margin_notes=False)
        assert ev.checklist is None
        ev.ai_service.generate_structured.return_value = {
            "success": True, "content": '{"scores": {}}', "usage": {}, "metadata": {},
        }
        ev._evaluate_multidim_single_call(context="", ground_truth="", prediction="answer text")
        kwargs = ev.ai_service.generate_structured.call_args.kwargs
        system, closing = rubric_judge_prompts("anywhere")
        assert kwargs["system_prompt"] == system
        assert kwargs["prompt"].rstrip().endswith(closing)
