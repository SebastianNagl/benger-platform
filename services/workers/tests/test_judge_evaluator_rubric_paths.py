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
    """Case-side exam parts from task.data (bearbeitervermerk /
    zusatzmaterial) are composed into the rubric judge's {context} block in
    the standard German exam order. The author's grading hints
    (korrekturhinweise) stay OUT of the case text: the evaluator renders
    them as their own <korrekturhinweise> block from the task data it is
    handed (see LLMJudgeEvaluator._evaluate_multidim_single_call)."""
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
    call = judge._evaluate_multidim_single_call.call_args.kwargs
    context = call["context"]
    assert "## Bearbeitervermerk\n\nNur Strafrecht prüfen." in context
    assert "## Zusatzmaterial\n\n§ 242 StGB Auszug" in context
    # Standard exam order: Bearbeitervermerk → Zusatzmaterial.
    assert context.index("Bearbeitervermerk") < context.index("Zusatzmaterial")
    # The hints reach the evaluator through task_data, not the case text.
    assert "Schwerpunkt Zueignungsabsicht" not in context
    assert call["task_data"]["korrekturhinweise"] == "Schwerpunkt Zueignungsabsicht"


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


# The exam-level key: percent thresholds, resolved BEFORE the
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


@pytest.mark.parametrize("stored", [None, ""])
def test_a_stored_null_judge_model_resolves_to_the_shared_default(stored):
    """Writers store the key with a null or empty value (the Bewertungsbogen
    setup does when neither a judge nor a generator is given). The old
    ``.get("judge_model", "gpt-4o")`` default did not cover that, so None
    reached the provider lookup. It must resolve to the shared default, the
    model every picker shows."""
    from model_defaults import DEFAULT_JUDGE_MODEL_ID

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    kwargs = _impl_kwargs(db)
    kwargs["metric_params"] = {"judge_model": stored}
    providers_asked = []

    def _provider(model_id):
        providers_asked.append(model_id)
        return "openai"

    with patch("tasks._get_provider_from_model", side_effect=_provider), patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=_judge_factory_mock(),
    ) as create_judge:
        # No task row, so the run stops at the rubric lookup, after the judge
        # was built.
        with pytest.raises(RuntimeError) as exc:
            _evaluate_llm_judge_single_impl(**kwargs)

    assert str(exc.value) == _NO_RUBRIC_ERROR.format(task_id="task-1")
    assert providers_asked == [DEFAULT_JUDGE_MODEL_ID]
    assert create_judge.call_args.kwargs["judge_model"] == DEFAULT_JUDGE_MODEL_ID


_EVIDENCE_STEP = {
    "score": 0.0,
    "max": 100.0,
    "reason": "nur in der Musterlösung [Punkte nicht vergeben]",
    "evidence": "",
    "evidence_verified": False,
    "model_score": 20.0,
}


def _multidim_with_evidence():
    return {
        "scores": {
            "s01_x": dict(_EVIDENCE_STEP),
        },
        "total_score": 0.0,
        "total_max": 100.0,
        "overall_assessment": "",
        "_call_metadata": {},
        "_raw_output": "",
        "_judge_prompts_used": {"system": "…"},
    }


def _run_immediate(task_data, metric_type="llm_judge_rubric"):
    db = MagicMock()
    task_row = SimpleNamespace(id="task-1", data=task_data)
    db.query.return_value.filter.return_value.first.return_value = task_row
    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id=None,
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata={"rendered_text": "BEWERTUNGSBOGEN"},
    )
    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = _multidim_with_evidence()
    kwargs = _impl_kwargs(db)
    kwargs["metric_type"] = metric_type
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        result = _evaluate_llm_judge_single_impl(**kwargs)
    return result, judge, db


def test_rubric_path_turns_on_rubric_mode_and_leads_context_with_the_sachverhalt():
    """The immediate lane hands the judge the same inputs as the bulk cell
    path: the Sachverhalt first, then the exam parts, and the evaluator in
    rubric mode (tags, fixed rules, verified evidence)."""
    result, judge, _db = _run_immediate(
        {
            "sachverhalt": "Der Fall.",
            "musterlösung": "ML",
            "bearbeitervermerk": "Nur Polizeirecht prüfen.",
        }
    )
    assert result["status"] == "completed"
    assert judge.rubric_mode is True
    context = judge._evaluate_multidim_single_call.call_args.kwargs["context"]
    assert context == "Der Fall.\n\n## Bearbeitervermerk\n\nNur Polizeirecht prüfen."


def test_rubric_path_context_is_the_sachverhalt_alone_without_exam_parts():
    _result, judge, _db = _run_immediate({"sachverhalt": "Der Fall.", "musterlösung": "ML"})
    assert judge._evaluate_multidim_single_call.call_args.kwargs["context"] == "Der Fall."


def test_rubric_path_persists_per_step_evidence_fields():
    result, _judge, db = _run_immediate({"sachverhalt": "Der Fall.", "musterlösung": "ML"})
    persisted = db.add.call_args.args[0]
    details = persisted.metrics["llm_judge_rubric"]["details"]
    assert details["scores"]["s01_x"] == _EVIDENCE_STEP
    assert details["total_score"] == 0.0
    assert set(details) == {
        "scores", "total_score", "total_max", "overall_assessment",
        "call_metadata", "raw_output", "rubric_id", "grade_points", "passed",
        "grade_scale_source",
    }
    assert result["total_score"] == 0.0


def test_other_multidim_metrics_stay_out_of_rubric_mode():
    """A generic multi-dim judge (llm_judge_custom with max_score criteria)
    never switches on the rubric rules. It sees the same context as the
    bulk cell path: the case text (the immediate lane used to drop it for
    every metric but the rubric judge)."""
    _result, judge, _db = _run_immediate(
        {"sachverhalt": "Der Fall.", "musterlösung": "ML"}, metric_type="llm_judge_custom"
    )
    assert judge.rubric_mode is not True
    assert judge._evaluate_multidim_single_call.call_args.kwargs["context"] == "Der Fall."


def test_other_multidim_metrics_keep_the_hints_inside_the_context():
    """Outside rubric mode there is no <korrekturhinweise> tag, so the hints
    stay in the context block as before."""
    _result, judge, _db = _run_immediate(
        {"sachverhalt": "Der Fall.", "korrekturhinweise": "Schwerpunkt A"},
        metric_type="llm_judge_custom",
    )
    assert judge._evaluate_multidim_single_call.call_args.kwargs["context"] == (
        "Der Fall.\n\nZusätzliche Hinweise für die Korrektur (vom Aufgabensteller):\n"
        "Schwerpunkt A"
    )


def test_rubric_path_keeps_the_hints_out_of_the_context():
    _result, judge, _db = _run_immediate(
        {"sachverhalt": "Der Fall.", "musterlösung": "ML", "korrekturhinweise": "Schwerpunkt A"}
    )
    call = judge._evaluate_multidim_single_call.call_args.kwargs
    assert call["context"] == "Der Fall."
    assert call["task_data"]["korrekturhinweise"] == "Schwerpunkt A"


@pytest.mark.parametrize("configured", [None, "minimal"])
def test_immediate_lane_forwards_the_configured_reasoning_effort(configured):
    """The immediate lane hands metric_parameters.reasoning_effort to the
    judge factory like the bulk path does (None lets the rubric default
    apply inside the evaluator)."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id="task-1", data={"sachverhalt": "Der Fall.", "musterlösung": "ML"}
    )
    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id=None,
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata={"rendered_text": "BEWERTUNGSBOGEN"},
    )
    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = _multidim_with_evidence()
    kwargs = _impl_kwargs(db)
    kwargs["metric_params"] = {"judge_model": "gpt-5-mini", "reasoning_effort": configured}
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ) as factory, patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        _evaluate_llm_judge_single_impl(**kwargs)
    assert factory.call_args.kwargs["reasoning_effort"] == configured


# ---------------------------------------------------------------------------
# _build_judge_context: the one context builder every judge lane uses
# ---------------------------------------------------------------------------

_FULL_TASK = {
    "sachverhalt": "Der Fall.",
    "bearbeitervermerk": " Nur Strafrecht prüfen. ",
    "zusatzmaterial": "§ 242 StGB Auszug",
    "korrekturhinweise": "Schwerpunkt Zueignungsabsicht",
}


def test_build_judge_context_composes_case_parts_and_hints_in_order():
    from evaluation.cell_evaluator import _build_judge_context

    assert _build_judge_context(_FULL_TASK) == (
        "Der Fall.\n\n"
        "## Bearbeitervermerk\n\nNur Strafrecht prüfen.\n\n"
        "## Zusatzmaterial\n\n§ 242 StGB Auszug\n\n"
        "Zusätzliche Hinweise für die Korrektur (vom Aufgabensteller):\n"
        "Schwerpunkt Zueignungsabsicht"
    )


def test_build_judge_context_can_leave_out_the_hints():
    from evaluation.cell_evaluator import _build_judge_context

    context = _build_judge_context(_FULL_TASK, include_korrekturhinweise=False)
    assert context.endswith("## Zusatzmaterial\n\n§ 242 StGB Auszug")
    assert "Schwerpunkt" not in context


def test_build_judge_context_can_leave_out_the_case():
    from evaluation.cell_evaluator import _build_judge_context

    context = _build_judge_context(_FULL_TASK, include_case=False)
    assert context.startswith("## Bearbeitervermerk\n\nNur Strafrecht prüfen.")
    assert "Der Fall." not in context


@pytest.mark.parametrize("data", [None, {}, {"other": "x"}, {"bearbeitervermerk": "  "}])
def test_build_judge_context_is_empty_without_any_key(data):
    from evaluation.cell_evaluator import _build_judge_context

    assert _build_judge_context(data) == ""


def test_build_judge_context_case_text_precedence_and_case_insensitive_keys():
    from evaluation.cell_evaluator import _build_judge_context

    # text | input | sachverhalt, first hit wins; keys match case-insensitively
    assert _build_judge_context({"Text": "T", "input": "I", "sachverhalt": "S"}) == "T"
    assert _build_judge_context({"Input": "I", "Sachverhalt": "S"}) == "I"
    assert _build_judge_context({"Sachverhalt": "S"}) == "S"
    # a task with parts but no case text starts with the first part
    assert _build_judge_context({"Zusatzmaterial": "Z"}) == "## Zusatzmaterial\n\nZ"
