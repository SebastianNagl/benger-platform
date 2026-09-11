"""Immediate-eval path of ``llm_judge_rubric`` (judge_evaluator impl).

The immediate path resolves the task's Bewertungsbogen exactly like the
bulk cell path: metric ``llm_judge_rubric`` looks up the task row and its
active rubric BEFORE any judge call, and a missing/unusable rubric raises
the shared ``_NO_RUBRIC_ERROR`` so the caller persists a clear config
error instead of silently grading without an instrument.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# `evaluation.judge_evaluator` does `import tasks` at module top while
# tasks.py imports it back near its bottom — importing tasks FIRST resolves
# the cycle (same order the worker runtime uses). Without this the file only
# collects when an earlier test module happens to have imported tasks.
import tasks  # noqa: F401  isort: skip

from evaluation.cell_evaluator import _NO_RUBRIC_ERROR
from evaluation.judge_evaluator import _evaluate_llm_judge_single_impl


def _impl_kwargs(db):
    return dict(
        db=db,
        record_id="rec-1",
        immediate_eval_id="imm-1",
        project_id="proj-1",
        task_id="task-1",
        annotation_id=None,
        user_id="user-1",
        field_name="cfg|pred|ref",
        metric_type="llm_judge_rubric",
        prediction="Bearbeitung …",
        reference="Musterlösung …",
        metric_params={"judge_model": "gpt-5.4-mini"},
        organization_id=None,
    )


def _judge_factory_mock():
    judge = MagicMock()
    judge.ai_service = object()  # truthy → passes the availability gate
    return judge


def test_missing_task_row_raises_no_rubric_error():
    db = MagicMock()
    # DBLLMModel lookup and ProjectTask lookup both go through db.query();
    # returning None everywhere makes the task row None → rubric None.
    db.query.return_value.filter.return_value.first.return_value = None
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=_judge_factory_mock(),
    ):
        with pytest.raises(RuntimeError) as exc:
            _evaluate_llm_judge_single_impl(**_impl_kwargs(db))
    assert str(exc.value) == _NO_RUBRIC_ERROR.format(task_id="task-1")


def test_rubric_multidim_path_binds_rendering_and_stamps_provenance():
    """Happy path: active rubric found → criteria injected, the rendered
    document bound as {bewertungsbogen}, Musterlösung swapped in as
    reference, and rubric id + generator stamped into details and
    judge_prompts_used."""
    db = MagicMock()
    task_row = SimpleNamespace(
        id="task-1", data={"musterlösung": "Die echte Musterlösung"}
    )
    db.query.return_value.filter.return_value.first.return_value = task_row

    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id="gpt-5.4",
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata={"rendered_text": "BEWERTUNGSBOGEN (100 Rohpunkte)"},
    )

    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = {
        "scores": {"s01_x": {"score": 80, "max": 100, "reason": "ok"}},
        "total_score": 80.0,
        "total_max": 100.0,
        "overall_assessment": "solide",
        "_call_metadata": {},
        "_raw_output": "",
        "_judge_prompts_used": {"system": "…"},
    }

    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        result = _evaluate_llm_judge_single_impl(**_impl_kwargs(db))

    assert result["status"] == "completed"
    assert result["score"] == pytest.approx(0.8)
    # criteria were injected from the rubric, not from config
    assert judge.custom_criteria == rubric.criteria
    call = judge._evaluate_multidim_single_call.call_args.kwargs
    # rendered document bound for the {bewertungsbogen} placeholder
    assert call["task_data"]["bewertungsbogen"].startswith("BEWERTUNGSBOGEN")
    # Musterlösung from task data replaced the passed-in reference
    assert call["ground_truth"] == "Die echte Musterlösung"
    # provenance stamped
    persisted = db.add.call_args.args[0]
    details = persisted.metrics["llm_judge_rubric"]["details"]
    assert details["rubric_id"] == "rub-9"
    assert persisted.judge_prompts_used["task_rubric_id"] == "rub-9"
    assert persisted.judge_prompts_used["task_rubric_generator"] == "gpt-5.4"


def test_multidim_path_feeds_exam_parts_into_judge_context():
    """Case-side exam parts + author grading hints from task.data
    (bearbeitervermerk / zusatzmaterial / korrekturhinweise) are composed
    into the judge's {context} block, in the standard German exam order."""
    db = MagicMock()
    task_row = SimpleNamespace(
        id="task-1",
        data={
            "musterlösung": "ML",
            "bearbeitervermerk": "Nur Strafrecht prüfen.",
            "zusatzmaterial": "§ 242 StGB Auszug",
            "korrekturhinweise": "Schwerpunkt Zueignungsabsicht",
        },
    )
    db.query.return_value.filter.return_value.first.return_value = task_row

    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id="gpt-5.4",
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata={"rendered_text": "BEWERTUNGSBOGEN"},
    )

    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = {
        "scores": {"s01_x": {"score": 80, "max": 100, "reason": "ok"}},
        "total_score": 80.0,
        "total_max": 100.0,
        "overall_assessment": "solide",
        "_call_metadata": {},
        "_raw_output": "",
        "_judge_prompts_used": {"system": "…"},
    }

    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        result = _evaluate_llm_judge_single_impl(**_impl_kwargs(db))

    assert result["status"] == "completed"
    context = judge._evaluate_multidim_single_call.call_args.kwargs["context"]
    assert "## Bearbeitervermerk\n\nNur Strafrecht prüfen." in context
    assert "## Zusatzmaterial\n\n§ 242 StGB Auszug" in context
    assert "Schwerpunkt Zueignungsabsicht" in context
    # Standard exam order: Bearbeitervermerk → Zusatzmaterial → Hinweise.
    assert (
        context.index("Bearbeitervermerk")
        < context.index("Zusatzmaterial")
        < context.index("Schwerpunkt")
    )


def test_unusable_rubric_raises_no_rubric_error():
    db = MagicMock()
    task_row = SimpleNamespace(id="task-1", data={})
    db.query.return_value.filter.return_value.first.return_value = task_row
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=_judge_factory_mock(),
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=None
    ) as resolver:
        with pytest.raises(RuntimeError) as exc:
            _evaluate_llm_judge_single_impl(**_impl_kwargs(db))
    assert resolver.called
    assert "task-1" in str(exc.value)
    assert "Bewertungsbogen" in str(exc.value)


# --- Notenpunkte (migration 100: per-rubric Notenschlüssel) ----------------

COLLEAGUE_SCALE = {
    "thresholds": [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
    "rounding": "floor",
    "pass_grade": 4,
}


# The exam-level key (contract v2): percent thresholds, resolved BEFORE the
# sheet's own scale by rubric_structure.resolve_grade_scale.
EXAM_PERCENT_SCALE = {
    "unit": "percent",
    "preset": "standard",
    "thresholds": [13, 26, 39, 50, 54, 57, 60, 64, 67, 70, 74, 77, 80, 84, 87, 90, 94, 97],
    "rounding": "floor",
    "pass_grade": 4,
}


def _db_for(task_row, project):
    """A db double that answers the Project lookup separately from the task
    lookup (both go through ``db.query(...).filter(...).first()``)."""
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = (
            project if getattr(model, "__name__", "") == "Project" else task_row
        )
        return q

    db.query.side_effect = _query
    return db


def _run_graded(
    db_total,
    total_max=100.0,
    *,
    grade_scale=None,
    total_points=100,
    metric_params=None,
    project_config=None,
):
    task_row = SimpleNamespace(id="task-1", data={"musterloesung": "ML"})
    db = _db_for(
        task_row,
        SimpleNamespace(id="proj-1", evaluation_config=project_config)
        if project_config is not None
        else None,
    )
    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id=None,
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": total_max}},
        generation_metadata=None,
        structure=None,
        total_points=total_points,
        grade_scale=grade_scale,
        title=None,
    )
    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = {
        "scores": {"s01_x": {"score": db_total, "max": total_max, "reason": "ok"}},
        "total_score": float(db_total),
        "total_max": float(total_max),
        "overall_assessment": "solide",
        "_call_metadata": {},
        "_raw_output": "",
        "_judge_prompts_used": {},
    }
    kwargs = _impl_kwargs(db)
    if metric_params is not None:
        kwargs["metric_params"] = metric_params
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user", return_value=judge
    ) as factory, patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        result = _evaluate_llm_judge_single_impl(**kwargs)
    return result, db.add.call_args.args[0], factory


def test_default_scale_grades_80_of_100_as_np_13_with_siblings():
    result, row, _ = _run_graded(80)
    details = row.metrics["llm_judge_rubric"]["details"]
    assert details["grade_points"] == 13
    assert details["passed"] is True
    assert details["grade_scale_source"] == "default"
    assert row.metrics["llm_judge_rubric_grade_points"] == 13.0
    assert row.metrics["llm_judge_rubric_passed"] == 1.0
    assert row.passed is True
    assert result["grade_points"] == 13 and result["passed"] is True
    assert result["score"] == pytest.approx(0.8)


def test_colleague_scale_grades_39_5_as_np_3_fail():
    """39.5 BE → floor → 39 → NP 3 on the colleague's Notenschlüssel (pass from 40),
    even though 0.395 < 0.5 would also fail on the legacy boundary; and 40 BE
    passes although 0.4 < 0.5 — the rubric's scale decides, not value >= 0.5."""
    _, row, _ = _run_graded(39.5, grade_scale=COLLEAGUE_SCALE)
    details = row.metrics["llm_judge_rubric"]["details"]
    assert details["grade_points"] == 3 and details["passed"] is False
    assert details["grade_scale_source"] == "rubric"
    assert row.metrics["llm_judge_rubric_passed"] == 0.0
    assert row.passed is False

    _, row, _ = _run_graded(40, grade_scale=COLLEAGUE_SCALE)
    assert row.metrics["llm_judge_rubric"]["details"]["grade_points"] == 4
    assert row.passed is True


def test_rubric_metric_lifts_default_max_tokens_to_the_floor():
    """No explicit max_tokens → system default (1500) → floored to 32000 for
    llm_judge_rubric; an explicit metric_parameters.max_tokens wins."""
    _, _, factory = _run_graded(80)
    assert factory.call_args.kwargs["max_tokens"] == 32000
    _, _, factory = _run_graded(80, metric_params={"judge_model": "gpt-5.4-mini", "max_tokens": 3000})
    assert factory.call_args.kwargs["max_tokens"] == 3000


def test_exam_percent_key_beats_the_sheets_absolute_scale():
    """The exam's Notenschlüssel (project.evaluation_config.grade_scale) is
    assessment policy and wins over anything the sheet carries: 40 BE passes
    on the sheet's own 40-BE key, but the exam's standard key (50 %) grades
    the same 40 BE as NP 3 — fail."""
    _, row, _ = _run_graded(40, grade_scale=COLLEAGUE_SCALE)
    assert row.metrics["llm_judge_rubric"]["details"]["grade_points"] == 4
    assert row.passed is True

    _, row, _ = _run_graded(
        40,
        grade_scale=COLLEAGUE_SCALE,
        project_config={"grade_scale": EXAM_PERCENT_SCALE},
    )
    details = row.metrics["llm_judge_rubric"]["details"]
    assert details["grade_points"] == 3
    assert details["passed"] is False
    assert details["grade_scale_source"] == "project"
    assert row.metrics["llm_judge_rubric_grade_points"] == 3.0
    assert row.metrics["llm_judge_rubric_passed"] == 0.0
    assert row.passed is False


def test_exam_percent_key_projects_onto_the_sheet_total():
    """A percent key is total-agnostic: on a 50 BE sheet, 25 BE is 50 % → NP 4."""
    _, row, _ = _run_graded(
        25,
        total_max=50.0,
        total_points=50,
        project_config={"grade_scale": EXAM_PERCENT_SCALE},
    )
    details = row.metrics["llm_judge_rubric"]["details"]
    assert details["grade_points"] == 4 and details["passed"] is True
    assert details["grade_scale_source"] == "project"


def test_project_without_a_key_still_uses_the_sheet_scale():
    _, row, _ = _run_graded(
        40, grade_scale=COLLEAGUE_SCALE, project_config={"evaluation_configs": []}
    )
    details = row.metrics["llm_judge_rubric"]["details"]
    assert details["grade_points"] == 4
    assert details["grade_scale_source"] == "rubric"
