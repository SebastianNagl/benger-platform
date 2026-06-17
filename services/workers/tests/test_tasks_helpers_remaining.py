"""Behavioral branch coverage for the remaining testable, DB-less / fake-session
helper paths in ``tasks.py`` that the existing green suites left uncovered.

Every test calls the REAL function and asserts on its return value, the mutated
session/row state, or the raised exception — no surface/import/registry checks.
Idioms mirror the existing worker suites exactly:

  * ``SessionLocal`` is patched on the module so the task opens a fake session.
  * Model-class-keyed fake query dispatch (idiom from
    ``test_tasks_handlers_coverage.py``'s ``auto_submit`` fakes and
    ``test_tasks_orchestration_branches.py``'s ``_dispatching_db``) drives the
    different ``db.query(Model)`` lookups inside a single task body.
  * ``bind=True`` Celery tasks are invoked via ``.run(...)`` so ``self`` is
    injected by the registered task object (idiom from
    ``test_tasks_deep_coverage.py``).
  * The lazy module-level progress-redis client is reset between tests.

Targets (tasks.py), all genuinely uncovered before this file:

  - _evaluate_llm_judge_single — single-criterion (non-multidim) arm:
        4277-4336.  Existing ``TestEvaluateLLMJudgeSingle.test_success`` only
        covered the ``score_scale="0-1"`` + named-metric-criterion + passed
        path. This file adds:
          * the ``1-5`` scale ``(raw - 1) / 4`` normalization branch (4307),
          * the ``llm_judge_classic`` / ``llm_judge_custom`` criterion fallback
            to ``llm_judge.criteria[0]`` (4283-4285),
          * the criteria-empty ``"helpfulness"`` fallback,
          * the no-score ``RuntimeError`` raise (4299-4303),
          * the ``passed=False`` (score < 0.5) branch (4326).

  - run_single_sample_evaluation — the create-NEW-EvaluationRun path
        (eval_run is None, 3551-3568) including the run-provenance snapshot
        (3506-3518), the per-config judge_run create with judge_model
        resolution (3639-3676), and the aggregation arm that runs when the
        re-query returns TaskEvaluation rows (3791-3850). The existing
        ``TestRunSingleSampleEvaluation`` tests always returned a pre-existing
        run and an empty ``task_evals`` list, so none of that ran.

  - export_project — the ``project is None`` → mark-failed branch (6392-6396),
        uncovered by ``test_export_task.py``.

  - auto_submit_expired_timer — the partial branches where the task row exists
        but the drafted ``result`` is empty (so the counter bump is skipped,
        861->876) and where the project row is missing (864->876).
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module  # noqa: E402
from tasks import (  # noqa: E402
    _evaluate_llm_judge_single,
    auto_submit_expired_timer,
    export_project,
    run_single_sample_evaluation,
)


@pytest.fixture(autouse=True)
def _reset_progress_client():
    """Reset the lazily-cached progress redis client so a mock from one test
    can't leak into the next (idiom from test_progress_pubsub.py)."""
    tasks_module._progress_redis_client = None
    yield
    tasks_module._progress_redis_client = None


# ===========================================================================
# _evaluate_llm_judge_single — single-criterion (non-multidim) arm
# ===========================================================================


def _single_criterion_judge(*, score, score_scale="0-1", criteria=None):
    """A judge mock pinned to the per-criterion path (is_multidim_mode False)
    so the helper takes the 4277-4336 arm instead of the multidim block."""
    judge = MagicMock()
    judge.ai_service = MagicMock()
    judge.is_multidim_mode.return_value = False
    judge.score_scale = score_scale
    judge.criteria = criteria if criteria is not None else ["correctness"]
    judge._evaluate_single_criterion.return_value = {
        "score": score,
        "justification": "because",
    }
    return judge


def _call_single(db, judge, *, metric_type, **overrides):
    kwargs = dict(
        db=db,
        record_id="r1",
        immediate_eval_id="i1",
        project_id="p1",
        task_id="t1",
        annotation_id="a1",
        user_id="u1",
        field_name="answer",
        metric_type=metric_type,
        prediction="pred",
        reference="ref",
        metric_params={"judge_model": "gpt-4o"},
        organization_id=None,
    )
    kwargs.update(overrides)
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ):
        with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
            return _evaluate_llm_judge_single(**kwargs)


class TestEvaluateLLMJudgeSingleCriterionArm:
    def test_one_to_five_scale_is_normalized(self):
        """score_scale='1-5' → the raw score is mapped to [0,1] via
        ``(raw - 1) / 4`` (4307). A raw 5 → 1.0, persisted + passed."""
        db = MagicMock()
        judge = _single_criterion_judge(score=5, score_scale="1-5")

        result = _call_single(db, judge, metric_type="llm_judge_correctness")

        assert result["status"] == "completed"
        assert result["score"] == pytest.approx(1.0)
        # Derived criterion from the metric name (not the classic/custom fallback).
        _, ckwargs = judge._evaluate_single_criterion.call_args
        assert ckwargs["criterion"] == "correctness"
        row = db.add.call_args.args[0]
        assert row.metrics["llm_judge_correctness"] == pytest.approx(1.0)
        assert row.passed is True
        db.commit.assert_called_once()

    def test_one_to_five_scale_midpoint_below_threshold_not_passed(self):
        """Raw 2 on the 1-5 scale → (2-1)/4 = 0.25 < 0.5 → passed=False (4326)."""
        db = MagicMock()
        judge = _single_criterion_judge(score=2, score_scale="1-5")

        result = _call_single(db, judge, metric_type="llm_judge_correctness")

        assert result["score"] == pytest.approx(0.25)
        row = db.add.call_args.args[0]
        assert row.passed is False

    def test_classic_metric_falls_back_to_first_configured_criterion(self):
        """``llm_judge_classic`` carries no single criterion in its name, so the
        helper falls back to ``llm_judge.criteria[0]`` (4283-4285)."""
        db = MagicMock()
        judge = _single_criterion_judge(
            score=0.9, score_scale="0-1", criteria=["depth", "clarity"]
        )

        result = _call_single(db, judge, metric_type="llm_judge_classic")

        assert result["status"] == "completed"
        _, ckwargs = judge._evaluate_single_criterion.call_args
        assert ckwargs["criterion"] == "depth"  # criteria[0]

    def test_custom_metric_with_empty_criteria_uses_helpfulness_default(self):
        """``llm_judge_custom`` + no configured criteria → the final
        ``"helpfulness"`` literal default (4285)."""
        db = MagicMock()
        judge = _single_criterion_judge(score=0.8, score_scale="0-1", criteria=[])

        result = _call_single(db, judge, metric_type="llm_judge_custom")

        assert result["status"] == "completed"
        _, ckwargs = judge._evaluate_single_criterion.call_args
        assert ckwargs["criterion"] == "helpfulness"

    def test_no_score_in_result_raises_runtime_error(self):
        """The single-criterion call returns a payload without a ``score`` key
        → the helper raises RuntimeError carrying the error_message (4299-4303)
        instead of persisting a bogus row."""
        db = MagicMock()
        judge = MagicMock()
        judge.ai_service = MagicMock()
        judge.is_multidim_mode.return_value = False
        judge.score_scale = "0-1"
        judge.criteria = ["correctness"]
        judge._evaluate_single_criterion.return_value = {
            "error": True,
            "error_message": "judge refused to score",
        }

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                with pytest.raises(RuntimeError, match="judge refused to score"):
                    _evaluate_llm_judge_single(
                        db=db,
                        record_id="r1",
                        immediate_eval_id="i1",
                        project_id="p1",
                        task_id="t1",
                        annotation_id="a1",
                        user_id="u1",
                        field_name="answer",
                        metric_type="llm_judge_correctness",
                        prediction="pred",
                        reference="ref",
                        metric_params={"judge_model": "gpt-4o"},
                        organization_id=None,
                    )

        db.commit.assert_not_called()

    def test_none_result_raises_with_default_message(self):
        """``_evaluate_single_criterion`` returns None → RuntimeError with the
        synthesized ``"produced no score for <criterion>"`` message (4299-4303,
        the ``raw is None`` arm of the guard)."""
        db = MagicMock()
        judge = MagicMock()
        judge.ai_service = MagicMock()
        judge.is_multidim_mode.return_value = False
        judge.score_scale = "0-1"
        judge.criteria = ["correctness"]
        judge._evaluate_single_criterion.return_value = None

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                with pytest.raises(RuntimeError, match="no score for correctness"):
                    _call_single(db, judge, metric_type="llm_judge_correctness")

        db.commit.assert_not_called()


# ===========================================================================
# run_single_sample_evaluation — create-new-run + judge_run + aggregation arms
# ===========================================================================


class _RSSEDispatchDB:
    """A fake session whose ``query(Model)`` returns per-model-class results,
    so we can independently drive the Project snapshot lookup, the
    get-or-create EvaluationRun path, the per-config EvaluationJudgeRun
    create, the judge LLMModel lookup, and the final TaskEvaluation
    aggregation re-query inside one ``run_single_sample_evaluation`` body.

    ``eval_run_first`` is a list consumed FIFO across the two
    ``query(EvaluationRun).first()`` calls (initial get-or-create, then the
    completion re-query)."""

    def __init__(self, *, project_row, eval_run_first, judge_run_existing,
                 judge_model_row, task_evals):
        self._project_row = project_row
        self._eval_run_first = list(eval_run_first)
        self._judge_run_existing = judge_run_existing
        self._judge_model_row = judge_model_row
        self._task_evals = task_evals
        self.added = []
        self.commits = 0
        self.flushes = 0
        self.rolled_back = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        q = MagicMock()
        if name == "Project":
            q.filter.return_value.first.return_value = self._project_row
        elif name == "EvaluationRun":
            nxt = self._eval_run_first.pop(0) if self._eval_run_first else None
            q.filter.return_value.first.return_value = nxt
        elif name == "EvaluationJudgeRun":
            q.filter.return_value.first.return_value = self._judge_run_existing
        elif name == "LLMModel":
            q.filter.return_value.first.return_value = self._judge_model_row
        elif name == "TaskEvaluation":
            q.filter.return_value.all.return_value = self._task_evals
            q.filter.return_value.first.return_value = None
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _project_snapshot_row():
    return types.SimpleNamespace(
        id="p1",
        label_config_version=3,
        evaluation_config={"cfg": "snap"},
    )


class TestRunSingleSampleEvaluationCreatePath:
    def test_creates_run_resolves_judge_and_aggregates(self):
        """eval_run is None at start → the worker CREATEs the EvaluationRun
        (3551-3568) with the project snapshot provenance (3510-3518), creates a
        per-config judge_run resolving the judge LLMModel (3639-3676), runs the
        deterministic job, then the completion re-query returns a TaskEvaluation
        row so the aggregation arm runs and writes EvaluationRun.metrics
        (3791-3850)."""
        # A persisted TaskEvaluation row the completion re-query will aggregate.
        te_row = types.SimpleNamespace(
            field_name="answer",
            metrics={
                "exact_match": {"value": 1.0, "method": "exact_match", "details": {}},
                "raw_score": 1.0,
                "exact_match_details": {"ignore": "me"},  # skipped by suffix filter
            },
        )
        eval_run_after = MagicMock()
        eval_run_after.eval_metadata = {
            "configs": [{"metric": "exact_match", "display_name": "Exact"}]
        }
        eval_run_after.metrics = {}
        eval_run_after.status = "running"

        judge_model_row = types.SimpleNamespace(
            id="gpt-4o", recommended_parameters={"temperature": 0.0}
        )

        db = _RSSEDispatchDB(
            project_row=_project_snapshot_row(),
            # 1st .first() (get-or-create) → None → CREATE; 2nd (completion) → run.
            eval_run_first=[None, eval_run_after],
            judge_run_existing=None,
            judge_model_row=judge_model_row,
            task_evals=[te_row],
        )

        configs = [{
            "id": "cfg-em",
            "metric": "exact_match",
            "display_name": "Exact",
            "prediction_fields": ["answer"],
            "reference_fields": ["task.ref"],
            "metric_parameters": {"judge_model": "gpt-4o"},
        }]

        # The per-job compute runs on a worker thread via _run_immediate_config_job;
        # stub it so this test stays focused on the orchestration body and the
        # deterministic compute's heavy registry isn't exercised here.
        def fake_job(**kwargs):
            return {
                "status": "completed",
                "metric": kwargs["job"]["metric_type"],
                "score": 1.0,
            }

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            with patch.object(tasks_module, "_run_immediate_config_job", side_effect=fake_job):
                result = run_single_sample_evaluation.run(
                    evaluation_record_id="eval-new-1",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="a1",
                    evaluation_configs=configs,
                    annotation_results={"answer": "my answer"},
                    task_data={"ref": "my answer"},
                    organization_id=None,
                    user_id="u1",
                )

        assert result["status"] == "completed"
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "completed"

        # A new EvaluationRun was constructed and added (create-path), and a
        # per-config EvaluationJudgeRun was created (judge_model resolution).
        added_names = [type(o).__name__ for o in db.added]
        assert "EvaluationRun" in added_names
        assert "EvaluationJudgeRun" in added_names

        # The created run carries the worker-only provenance snapshot.
        created_run = next(o for o in db.added if type(o).__name__ == "EvaluationRun")
        assert created_run.eval_metadata["label_config_version"] == 3
        assert created_run.eval_metadata["evaluation_config_snapshot"] == {"cfg": "snap"}
        assert created_run.eval_metadata["expected_config_count"] == 1

        # The created judge_run resolved the judge model id from metric_parameters.
        judge_run = next(o for o in db.added if type(o).__name__ == "EvaluationJudgeRun")
        assert judge_run.judge_model_id == "gpt-4o"
        assert judge_run.run_index == 0
        # The provenance snapshot was stamped from the resolved param chain.
        assert "_param_provenance" in judge_run.metric_parameters_snapshot

        # The aggregation arm ran: the re-queried run is completed and its
        # metrics dict was rebuilt from the TaskEvaluation row under the
        # ``{field}|{metric}`` key shape (the *_details key was suffix-filtered).
        assert eval_run_after.status == "completed"
        assert eval_run_after.metrics == {"answer|exact_match": 1.0}
        assert eval_run_after.samples_evaluated == 1

    def test_revives_terminal_judge_run_on_resume(self):
        """A prior cancel left this config's EvaluationJudgeRun terminal; on a
        resume the get-or-create finds it and flips it back to 'running'
        (3626-3631) rather than re-inserting (which would violate the UQ)."""
        existing_jr = types.SimpleNamespace(
            id="jr-existing",
            status="cancelled",
            error_message="prior cancel",
            completed_at="2026-01-01",
            started_at=None,
        )
        eval_run_after = MagicMock()
        eval_run_after.eval_metadata = {"configs": []}
        eval_run_after.metrics = {}
        eval_run_after.status = "running"

        db = _RSSEDispatchDB(
            project_row=None,  # no snapshot → run_provenance stays {}
            eval_run_first=[None, eval_run_after],
            judge_run_existing=existing_jr,
            judge_model_row=types.SimpleNamespace(id="gpt-4o", recommended_parameters=None),
            task_evals=[],  # no rows → aggregation arm short-circuits
        )

        configs = [{
            "id": "cfg-j",
            "metric": "llm_judge_correctness",
            "display_name": "Judge",
            "prediction_fields": ["answer"],
            "reference_fields": ["task.ref"],
            "metric_parameters": {"judge_model": "gpt-4o"},
        }]

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            with patch.object(
                tasks_module,
                "_run_immediate_config_job",
                side_effect=lambda **k: {"status": "completed", "metric": "x", "score": 1.0},
            ):
                result = run_single_sample_evaluation.run(
                    evaluation_record_id="eval-revive-1",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="a1",
                    evaluation_configs=configs,
                    annotation_results={"answer": "ans"},
                    task_data={"ref": "r"},
                    user_id="u1",
                )

        assert result["status"] == "completed"
        # The terminal judge_run was revived in place, not re-inserted.
        assert existing_jr.status == "running"
        assert existing_jr.error_message is None
        assert existing_jr.completed_at is None
        assert "EvaluationJudgeRun" not in [type(o).__name__ for o in db.added]

    def test_outer_exception_rolls_back_and_returns_error(self):
        """A failure inside the body (here: the Project snapshot query blowing
        up) lands in the outer except → rollback + error dict (3858-3861)."""
        db = MagicMock()
        db.query.side_effect = RuntimeError("snapshot query exploded")

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            result = run_single_sample_evaluation.run(
                evaluation_record_id="eval-err-1",
                project_id="p1",
                task_id="t1",
                annotation_id="a1",
                evaluation_configs=[{
                    "metric": "exact_match",
                    "prediction_fields": ["answer"],
                    "reference_fields": ["task.ref"],
                }],
                annotation_results={"answer": "a"},
                task_data={"ref": "a"},
                user_id="u1",
            )

        assert result["status"] == "error"
        assert "snapshot query exploded" in result["message"]
        db.rollback.assert_called_once()
        db.close.assert_called_once()


# ===========================================================================
# export_project — project-not-found arm
# ===========================================================================


class TestExportProjectProjectNotFound:
    def test_missing_project_marks_job_failed(self):
        """The ExportJob is pending but its project row is gone → the job is
        flipped to FAILED with 'project_not_found' and committed (6392-6396),
        and no multipart upload is ever started."""
        from models import JobStatus

        job = types.SimpleNamespace(
            id="ejob-np",
            project_id="gone",
            status=JobStatus.PENDING.value,
            error_message=None,
        )

        def query(model):
            name = getattr(model, "__name__", "")
            q = MagicMock()
            if name == "ExportJob":
                q.filter.return_value.first.return_value = job
            elif name == "Project":
                q.filter.return_value.first.return_value = None  # missing project
            else:
                q.filter.return_value.first.return_value = None
            return q

        db = MagicMock()
        db.query.side_effect = query

        fake_storage = MagicMock()

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            with patch.dict(
                sys.modules,
                {"storage.object_storage": types.SimpleNamespace(object_storage=fake_storage)},
            ):
                result = export_project.run("ejob-np")

        assert result["status"] == "error"
        assert result["error"] == "project_not_found"
        assert job.status == JobStatus.FAILED.value
        assert job.error_message == "project_not_found"
        db.commit.assert_called_once()
        # Never reached the upload machinery.
        fake_storage.create_multipart_upload.assert_not_called()
        db.close.assert_called_once()


# ===========================================================================
# auto_submit_expired_timer — task-counter partial branches
# ===========================================================================


class _AutoSubmitDB:
    """Model-class-keyed fake session for auto_submit_expired_timer (idiom from
    test_tasks_handlers_coverage.py). Drives the timer-session lookup, the
    'annotation already exists' check (here: None → proceed), the task-counter
    lookup, and the project lookup independently."""

    def __init__(self, *, session_row, task_row, project_row):
        self._session = session_row
        self._task = task_row
        self._project = project_row
        self.committed = False
        self.rolled_back = False
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", "")
        q = MagicMock()
        if name == "TimerSession":
            q.filter.return_value.first.return_value = self._session
        elif name == "Annotation":
            # 'existing annotation' check → None so we proceed to auto-submit;
            # the non-cancelled count uses .count(), kept at 0.
            q.filter.return_value.first.return_value = None
            q.filter.return_value.count.return_value = 0
        elif name == "TaskDraft":
            q.filter.return_value.first.return_value = None
        elif name == "Task":
            q.filter.return_value.first.return_value = self._task
        elif name == "Project":
            q.filter.return_value.first.return_value = self._project
        else:
            q.filter.return_value.first.return_value = None
        return q

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _timer_session(**overrides):
    s = types.SimpleNamespace(
        id="ts-1",
        completed_at=None,
        target_type="task",
        task_id="t1",
        project_id="p1",
        user_id="u1",
        draft_result=None,
        time_limit_seconds=600,
        auto_submitted=False,
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class TestAutoSubmitExpiredTimerCounterBranches:
    def test_empty_draft_result_skips_counter_bump(self):
        """The drafted result is empty, so the annotation is still created but
        the ``task.total_annotations`` / ``is_labeled`` counter block is skipped
        (the ``result and len(result) > 0`` guard, 861->876). The session is
        completed + auto_submitted and 'submitted' is returned."""
        session = _timer_session(draft_result=[])  # empty draft → empty result
        task = types.SimpleNamespace(total_annotations=5, is_labeled=False)
        db = _AutoSubmitDB(session_row=session, task_row=task, project_row=None)

        with patch.object(tasks_module, "HAS_DATABASE", True):
            with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
                out = auto_submit_expired_timer("ts-1")

        assert out["status"] == "submitted"
        # Counter block skipped → task counters untouched.
        assert task.total_annotations == 5
        assert task.is_labeled is False
        assert session.completed_at is not None
        assert session.auto_submitted is True
        assert db.committed is True

    def test_nonempty_result_but_missing_project_bumps_count_only(self):
        """Result is non-empty so ``total_annotations`` bumps, but the project
        row is missing so the ``is_labeled`` recompute is skipped (864->876).
        """
        session = _timer_session(draft_result=[{"value": {"text": ["x"]}}])
        task = types.SimpleNamespace(total_annotations=2, is_labeled=False)
        db = _AutoSubmitDB(session_row=session, task_row=task, project_row=None)

        with patch.object(tasks_module, "HAS_DATABASE", True):
            with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
                out = auto_submit_expired_timer("ts-1")

        assert out["status"] == "submitted"
        # Count bumped (result non-empty), but is_labeled untouched (no project).
        assert task.total_annotations == 3
        assert task.is_labeled is False
        assert db.committed is True
