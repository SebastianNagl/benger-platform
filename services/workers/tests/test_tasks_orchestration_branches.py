"""Behavioral branch coverage for orchestration/persistence helpers in
``tasks.py`` that the existing green suites declared-but-never-actually-tested
(``test_tasks_more_coverage.py`` defines ``_patch_aggregate_module`` /
``_patch_report_service`` helpers but ends without writing the test methods
that use them — so ``recompute_aggregates`` and
``update_report_annotations_async`` were left fully uncovered), plus two
helpers no suite touches at all (``_fail_import_job``,
``_run_immediate_config_job``) and the multi-dim arm of
``_evaluate_llm_judge_single``.

Every test calls the REAL function and asserts on its return value, the
mutated DB/Redis state, or the raised exception — no surface/import/registry
assertions. Idioms mirror the existing worker suites exactly:

  * ``bind=True`` Celery tasks are called directly; the registered task
    object's ``__call__`` already injects ``self``, so we pass only the
    business args (no explicit ``self``).
  * ``SessionLocal`` is patched on the module so the task opens a fake session.
  * ``tasks_module.redis.from_url`` is patched for the coalescing-lock paths.
  * Local ``from aggregate_summaries import …`` / ``from report_service import …``
    are satisfied with injected stub modules via ``patch.dict(sys.modules, …)``.
  * The lazy module-level progress-redis client is reset between tests
    (idiom from ``test_progress_pubsub.py`` / ``test_tasks_more_coverage.py``).

Targets (tasks.py):
  - recompute_aggregates            6191-6239 (lock-skip / success / error /
                                    redis-unavailable proceed-without-lock /
                                    lock-release best-effort)
  - update_report_annotations_async 6266-6320 (follower-skip+pending /
                                    leader-success / compute-exception /
                                    tail re-enqueue when pending /
                                    redis-unavailable proceed)
  - _fail_import_job                6700-6718 (job found→failed+publish /
                                    job missing no-op / inner-exception swallow)
  - _run_immediate_config_job       3966-4017 deterministic success,
                                    3908-3920+4019-4107 falloesung-without-
                                    extended error + error-row persistence,
                                    4019-4097 generic deterministic error row.
  - _evaluate_llm_judge_single      4194-4275 multi-dim single-call arm
                                    (success row + no-scores raise).
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
    _fail_import_job,
    _run_immediate_config_job,
    recompute_aggregates,
    update_report_annotations_async,
)


@pytest.fixture(autouse=True)
def _reset_progress_client():
    """Reset the lazily-cached progress redis client so a mock from one test
    can't leak into the next (idiom from test_progress_pubsub.py)."""
    tasks_module._progress_redis_client = None
    yield
    tasks_module._progress_redis_client = None


def _patch_aggregate_module(ps_return=4, lls_return=7, ps_side=None, lls_side=None):
    """Inject a fake `aggregate_summaries` module so the task's local import
    resolves without pulling the real (DB-heavy) recompute functions."""
    fake = types.ModuleType("aggregate_summaries")
    fake.recompute_project_summaries = MagicMock(
        return_value=ps_return, side_effect=ps_side
    )
    fake.recompute_llm_leaderboard_scores = MagicMock(
        return_value=lls_return, side_effect=lls_side
    )
    return patch.dict(sys.modules, {"aggregate_summaries": fake})


def _patch_report_service(side_effect=None):
    fake = types.ModuleType("report_service")
    fake.update_report_annotations_section = MagicMock(side_effect=side_effect)
    return patch.dict(sys.modules, {"report_service": fake})


# ===========================================================================
# recompute_aggregates  (bind=True; self injected by the task object)
# ===========================================================================


class TestRecomputeAggregates:
    def test_lock_not_acquired_skips_without_touching_db(self):
        """Another run holds the coalescing lock (SET NX returns falsy) → the
        task returns the skip dict and never opens a DB session / runs SQL."""
        rc = MagicMock()
        rc.set.return_value = False  # NX failed → lock held by another run
        session_factory = MagicMock()

        with _patch_aggregate_module():
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = recompute_aggregates()

        assert result == {"status": "skipped", "reason": "another_run_in_progress"}
        # NX lock attempted, but no session opened and no lock released.
        rc.set.assert_called_once()
        session_factory.assert_not_called()
        rc.delete.assert_not_called()

    def test_success_runs_recomputes_and_releases_lock(self):
        rc = MagicMock()
        rc.set.return_value = True  # acquired the lock
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_aggregate_module(ps_return=4, lls_return=7) as _:
            agg = sys.modules["aggregate_summaries"]
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = recompute_aggregates()

        assert result["status"] == "success"
        assert result["project_summaries_upserted"] == 4
        assert result["llm_leaderboard_scores_upserted"] == 7
        assert "elapsed_seconds" in result
        # Both recompute functions ran against the opened session.
        agg.recompute_project_summaries.assert_called_once_with(db)
        agg.recompute_llm_leaderboard_scores.assert_called_once_with(db)
        # Session closed and lock released on the way out.
        db.close.assert_called_once()
        rc.delete.assert_called_once_with("lock:recompute_aggregates")

    def test_inner_exception_returns_error_and_rolls_back(self):
        rc = MagicMock()
        rc.set.return_value = True
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_aggregate_module(ps_side=RuntimeError("recompute boom")):
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = recompute_aggregates()

        assert result["status"] == "error"
        assert "recompute boom" in result["error"]
        db.rollback.assert_called_once()
        db.close.assert_called_once()
        # The lock is still released in the finally even on error.
        rc.delete.assert_called_once_with("lock:recompute_aggregates")

    def test_redis_unavailable_proceeds_without_dedup(self):
        """redis.from_url raises → rc is None → no lock taken, the recompute
        runs anyway, and no delete is attempted on the way out."""
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_aggregate_module(ps_return=1, lls_return=2):
            agg = sys.modules["aggregate_summaries"]
            with patch.object(
                tasks_module.redis, "from_url", side_effect=OSError("no redis")
            ):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = recompute_aggregates()

        assert result["status"] == "success"
        assert result["project_summaries_upserted"] == 1
        assert result["llm_leaderboard_scores_upserted"] == 2
        agg.recompute_project_summaries.assert_called_once_with(db)
        db.close.assert_called_once()

    def test_error_path_swallows_rollback_and_lock_release_failures(self):
        """Both best-effort cleanups can themselves blow up: the inner
        rollback (6230-6231) and the lock-delete in the finally (6238-6239).
        The task must still return the error dict, not propagate either."""
        rc = MagicMock()
        rc.set.return_value = True  # acquired the lock
        rc.delete.side_effect = RuntimeError("delete blew up")
        db = MagicMock()
        db.rollback.side_effect = RuntimeError("rollback blew up")
        session_factory = MagicMock(return_value=db)

        with _patch_aggregate_module(ps_side=RuntimeError("recompute boom")):
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = recompute_aggregates()

        assert result["status"] == "error"
        assert "recompute boom" in result["error"]
        # Both cleanups were attempted (and their exceptions swallowed).
        db.rollback.assert_called_once()
        rc.delete.assert_called_once_with("lock:recompute_aggregates")
        db.close.assert_called_once()


# ===========================================================================
# update_report_annotations_async  (bind=True; self injected by the task object)
# ===========================================================================


class TestUpdateReportAnnotationsAsync:
    def test_follower_skips_and_sets_pending(self):
        """Can't get the lock → follower path: mark the project dirty via the
        pending key and return the skip dict without opening a session."""
        rc = MagicMock()
        rc.set.side_effect = [False]  # NX on the lock fails
        session_factory = MagicMock()

        with _patch_report_service():
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    result = update_report_annotations_async("proj-1")

        assert result == {"status": "skipped", "project_id": "proj-1"}
        session_factory.assert_not_called()
        # Lock NX + pending-set were both attempted.
        assert rc.set.call_count == 2
        rc.set.assert_any_call("pending:report_annotations:proj-1", "1", ex=120)

    def test_leader_success_no_pending_no_reenqueue(self):
        rc = MagicMock()
        rc.set.return_value = True  # acquired the lock
        rc.delete.return_value = 0  # pending flag absent → no re-enqueue
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service() as _:
            svc = sys.modules["report_service"]
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(tasks_module.app, "send_task") as send_task:
                        result = update_report_annotations_async("p9")

        assert result == {"status": "ok", "project_id": "p9"}
        svc.update_report_annotations_section.assert_called_once_with(db, "p9")
        db.close.assert_called_once()
        # pending was 0 → must NOT re-enqueue a tail run.
        send_task.assert_not_called()
        rc.delete.assert_any_call("lock:report_annotations:p9")

    def test_leader_compute_exception_returns_error(self):
        rc = MagicMock()
        rc.set.return_value = True
        rc.delete.return_value = 0
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service(side_effect=ValueError("compute failed")):
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(tasks_module.app, "send_task"):
                        result = update_report_annotations_async("pErr")

        assert result["status"] == "error"
        assert result["project_id"] == "pErr"
        assert "compute failed" in result["error"]
        # Session still closed even when the compute raised.
        db.close.assert_called_once()

    def test_tail_reenqueue_when_pending_flag_set(self):
        """A follower marked the project dirty while the leader ran → the
        leader sees `delete(pending)` return truthy and re-enqueues exactly
        one more pass so the latest submit is reflected."""
        rc = MagicMock()
        rc.set.return_value = True  # leader acquires the lock
        rc.delete.return_value = 1  # pending flag WAS set
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service():
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(tasks_module.app, "send_task") as send_task:
                        result = update_report_annotations_async("pTail")

        assert result == {"status": "ok", "project_id": "pTail"}
        send_task.assert_called_once_with(
            "tasks.update_report_annotations_async",
            args=["pTail"],
            queue="default",
        )

    def test_redis_unavailable_runs_without_coalescing(self):
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service() as _:
            svc = sys.modules["report_service"]
            with patch.object(
                tasks_module.redis, "from_url", side_effect=ConnectionError("down")
            ):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(tasks_module.app, "send_task") as send_task:
                        result = update_report_annotations_async("pNoRedis")

        assert result == {"status": "ok", "project_id": "pNoRedis"}
        svc.update_report_annotations_section.assert_called_once_with(db, "pNoRedis")
        db.close.assert_called_once()
        # rc is None → no tail-check / re-enqueue.
        send_task.assert_not_called()

    def test_leader_swallows_redis_and_reenqueue_failures(self):
        """Every best-effort cleanup on the leader's way out can blow up: the
        pending-delete (6302-6303), the lock-delete (6306-6307), and the
        re-enqueue send_task (6315-6316). The task must still return its
        success dict regardless."""
        rc = MagicMock()
        rc.set.return_value = True  # leader acquires the lock
        # First delete (pending) raises → had_pending falls back to False...
        # so to also exercise the re-enqueue arm we instead make delete return
        # truthy for pending and raise on the lock delete, and make send_task
        # raise. Sequence the two delete calls explicitly:
        rc.delete.side_effect = [1, RuntimeError("lock delete blew up")]
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service():
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(
                        tasks_module.app,
                        "send_task",
                        side_effect=RuntimeError("enqueue blew up"),
                    ) as send_task:
                        result = update_report_annotations_async("pSwallow")

        # pending delete returned 1 → re-enqueue attempted (and its failure
        # swallowed); lock delete raised (swallowed). Result still ok.
        assert result == {"status": "ok", "project_id": "pSwallow"}
        send_task.assert_called_once()
        assert rc.delete.call_count == 2

    def test_leader_pending_delete_failure_falls_back_to_no_reenqueue(self):
        """The tail-check pending delete itself raises (6302-6303) →
        had_pending falls back to False, so no re-enqueue fires; the lock
        delete still runs and the success dict is returned."""
        rc = MagicMock()
        rc.set.return_value = True
        # First delete (pending) raises; second (lock) succeeds.
        rc.delete.side_effect = [RuntimeError("pending delete blew up"), 1]
        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        with _patch_report_service():
            with patch.object(tasks_module.redis, "from_url", return_value=rc):
                with patch.object(tasks_module, "SessionLocal", session_factory):
                    with patch.object(tasks_module.app, "send_task") as send_task:
                        result = update_report_annotations_async("pPendingErr")

        assert result == {"status": "ok", "project_id": "pPendingErr"}
        # had_pending defaulted to False → no tail re-enqueue.
        send_task.assert_not_called()
        assert rc.delete.call_count == 2


# ===========================================================================
# _fail_import_job  (fake session + ImportJob row)
# ===========================================================================


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, job=None, raise_on=None):
        self._job = job
        self._raise_on = raise_on  # e.g. "rollback" / "commit"
        self.committed = False
        self.rolled_back = False

    def rollback(self):
        if self._raise_on == "rollback":
            raise RuntimeError("rollback exploded")
        self.rolled_back = True

    def query(self, model):
        if self._raise_on == "query":
            raise RuntimeError("query exploded")
        return _FakeQuery(self._job)

    def commit(self):
        if self._raise_on == "commit":
            raise RuntimeError("commit exploded")
        self.committed = True


class TestFailImportJob:
    def test_marks_job_failed_and_publishes(self):
        """Happy path: rollback, look up the job, flip it to FAILED with the
        truncated message, commit, and publish a final progress event."""
        from models import JobStatus

        job = types.SimpleNamespace(
            id="ijob-1",
            project_id="proj-1",
            status="running",
            error_message=None,
            progress=42,
        )
        db = _FakeSession(job=job)

        published = []

        def fake_publish(channel, payload):
            published.append((channel, payload))

        with patch.object(tasks_module, "_publish_progress", fake_publish):
            _fail_import_job(db, "ijob-1", "boom: something broke")

        assert db.rolled_back is True
        assert db.committed is True
        assert job.status == JobStatus.FAILED.value
        assert job.error_message == "boom: something broke"
        # Progress event published on the project-scoped import channel.
        assert published == [
            (
                "import:progress:proj-1",
                {"job_id": "ijob-1", "status": "failed", "progress": 42},
            )
        ]

    def test_truncates_long_message_to_2000_chars(self):
        job = types.SimpleNamespace(
            id="ijob-2",
            project_id="proj-2",
            status="running",
            error_message=None,
            progress=0,
        )
        db = _FakeSession(job=job)
        long_msg = "x" * 5000

        with patch.object(tasks_module, "_publish_progress", lambda *a, **k: None):
            _fail_import_job(db, "ijob-2", long_msg)

        assert len(job.error_message) == 2000
        assert db.committed is True

    def test_missing_job_is_noop_no_publish(self):
        """No ImportJob row for the id → roll back, but never commit or
        publish (the `if job is not None` guard)."""
        db = _FakeSession(job=None)
        published = []

        with patch.object(
            tasks_module, "_publish_progress", lambda c, p: published.append((c, p))
        ):
            _fail_import_job(db, "missing", "irrelevant")

        assert db.rolled_back is True
        assert db.committed is False
        assert published == []

    def test_inner_exception_is_swallowed(self):
        """If the rollback/query path raises, _fail_import_job logs and
        returns rather than propagating (it's the error handler of last
        resort and must not mask the original failure)."""
        db = _FakeSession(job=None, raise_on="query")

        # Must not raise despite the query blowing up after rollback.
        with patch.object(tasks_module, "_publish_progress", lambda *a, **k: None):
            _fail_import_job(db, "ijob-3", "msg")

        assert db.rolled_back is True  # rollback ran before query raised


# ===========================================================================
# _run_immediate_config_job  (own-session helper; SessionLocal patched)
# ===========================================================================


class TestRunImmediateConfigJob:
    def _job(self, **overrides):
        job = {
            "metric_type": "exact_match",
            "metric_params": None,
            "field_name": "answer",
            "prediction_value": "hello",
            "reference_value": "hello",
            "judge_run_id": "jr-1",
            "evaluation_config_id": "cfg-1",
            "record_id": "rec-1",
        }
        job.update(overrides)
        return job

    def test_deterministic_metric_success_persists_row(self):
        """exact_match prediction == reference → score 1.0, a TaskEvaluation
        row is added + committed, and the returned dict carries the score and
        details from the real registry handler."""
        db = MagicMock()
        with patch.object(tasks_module, "SessionLocal", return_value=db):
            result = _run_immediate_config_job(
                job=self._job(),
                dispatch_eval_id="eval-1",
                project_id="proj-1",
                task_id="task-1",
                annotation_id="ann-1",
                organization_id=None,
                user_id="user-1",
                task_data={},
            )

        assert result["status"] == "completed"
        assert result["metric"] == "exact_match"
        assert result["score"] == 1.0
        assert isinstance(result["details"], dict)
        # Persisted a row and committed in its own session, then closed it.
        db.add.assert_called_once()
        added_row = db.add.call_args.args[0]
        assert added_row.id == "rec-1"
        assert added_row.evaluation_id == "eval-1"
        assert added_row.judge_run_id == "jr-1"
        assert added_row.evaluation_config_id == "cfg-1"
        assert added_row.passed is True
        db.commit.assert_called_once()
        db.close.assert_called_once()

    def test_deterministic_metric_mismatch_not_passed(self):
        """exact_match with differing values → score 0.0 and passed=False."""
        db = MagicMock()
        with patch.object(tasks_module, "SessionLocal", return_value=db):
            result = _run_immediate_config_job(
                job=self._job(prediction_value="hello", reference_value="world"),
                dispatch_eval_id="eval-2",
                project_id="proj-1",
                task_id="task-1",
                annotation_id="ann-1",
                organization_id=None,
                user_id="user-1",
                task_data={},
            )

        assert result["status"] == "completed"
        assert result["score"] == 0.0
        added_row = db.add.call_args.args[0]
        assert added_row.passed is False

    def test_deterministic_error_persists_error_row(self):
        """The deterministic compute raising mid-job lands in the except arm:
        the first session is rolled back and a minimal error TaskEvaluation
        row (value=None, error=<msg>, passed=False) is committed so the
        method shows as failed and the run still reaches a terminal state."""
        db = MagicMock()
        boom = RuntimeError("compute exploded")

        with patch.object(tasks_module, "SessionLocal", return_value=db):
            # Force the deterministic branch's compute to raise.
            with patch(
                "ml_evaluation.sample_evaluator.SampleEvaluator._compute_metric_with_details",
                side_effect=boom,
            ):
                result = _run_immediate_config_job(
                    job=self._job(metric_type="rouge"),
                    dispatch_eval_id="eval-3",
                    project_id="proj-1",
                    task_id="task-1",
                    annotation_id="ann-1",
                    organization_id=None,
                    user_id="user-1",
                    task_data={},
                )

        assert result["status"] == "error"
        assert result["metric"] == "rouge"
        assert "compute exploded" in result["error"]
        db.rollback.assert_called_once()
        # An error row was persisted in the except arm.
        error_row = db.add.call_args.args[0]
        assert error_row.error_message == "compute exploded"
        assert error_row.passed is False
        assert error_row.metrics["rouge"]["value"] is None
        assert error_row.metrics["rouge"]["error"] == "compute exploded"
        db.close.assert_called_once()

    def test_falloesung_without_extended_returns_error(self):
        """llm_judge_falloesung in the community worker (no benger_extended)
        raises the informative RuntimeError, which is caught and turned into
        the error result dict; the falloesung error-persistence import also
        ImportErrors and is skipped without crashing."""
        db = MagicMock()

        # Ensure the in-body `from benger_extended.workers import ...` fails
        # by masking the package in sys.modules.
        with patch.dict(sys.modules, {"benger_extended": None, "benger_extended.workers": None}):
            with patch.object(tasks_module, "SessionLocal", return_value=db):
                result = _run_immediate_config_job(
                    job=self._job(metric_type="llm_judge_falloesung"),
                    dispatch_eval_id="eval-4",
                    project_id="proj-1",
                    task_id="task-1",
                    annotation_id="ann-1",
                    organization_id=None,
                    user_id="user-1",
                    task_data={},
                )

        assert result["status"] == "error"
        assert result["metric"] == "llm_judge_falloesung"
        assert "benger_extended" in result["error"]
        db.close.assert_called_once()


# ===========================================================================
# _evaluate_llm_judge_single — multi-dim single-call arm
# ===========================================================================


class TestEvaluateLLMJudgeSingleMultidim:
    def _mock_judge(self, multidim_return):
        judge = MagicMock()
        judge.ai_service = MagicMock()
        judge.is_multidim_mode.return_value = True
        judge._evaluate_multidim_single_call.return_value = multidim_return
        return judge

    def test_multidim_success_persists_normalized_row(self):
        """Multi-dim mode returns per-dimension scores; the helper normalizes
        total/total_max into [0,1], persists a TaskEvaluation row carrying the
        per-dim scores under metrics[<metric>].details.scores, and returns the
        normalized score + totals."""
        db = MagicMock()
        # No annotation_id / generation_id → field_outputs stays empty; the
        # task lookup returns a row with empty data.
        db.query.return_value.filter.return_value.first.return_value = None

        multidim = {
            "scores": {"clarity": 3, "depth": 4},
            "total_score": 7.0,
            "total_max": 10.0,
            "overall_assessment": "solid",
            "_call_metadata": {"input_tokens": 11},
            "_raw_output": "raw judge text",
            "_judge_prompts_used": {"system": "..."},
        }
        judge = self._mock_judge(multidim)

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                result = _evaluate_llm_judge_single(
                    db=db,
                    record_id="r-md",
                    immediate_eval_id="i-md",
                    project_id="p1",
                    task_id="t1",
                    annotation_id=None,
                    user_id="u1",
                    field_name="loesung",
                    metric_type="llm_judge_grundprinzipien",
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o"},
                    organization_id=None,
                    judge_run_id="jr-md",
                    evaluation_config_id="cfg-md",
                )

        assert result["status"] == "completed"
        assert result["score"] == pytest.approx(0.7)
        assert result["total_score"] == 7.0
        assert result["total_max"] == 10.0
        # Row persisted with the normalized value + per-dim scores in details.
        row = db.add.call_args.args[0]
        assert row.id == "r-md"
        assert row.judge_run_id == "jr-md"
        assert row.evaluation_config_id == "cfg-md"
        assert row.passed is True  # 0.7 >= 0.5
        metric_blob = row.metrics["llm_judge_grundprinzipien"]
        assert metric_blob["value"] == pytest.approx(0.7)
        assert metric_blob["details"]["scores"] == {"clarity": 3, "depth": 4}
        assert metric_blob["details"]["overall_assessment"] == "solid"
        db.commit.assert_called_once()

    def test_multidim_zero_max_normalizes_to_zero_and_not_passed(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        multidim = {
            "scores": {"x": 0},
            "total_score": 0.0,
            "total_max": 0.0,  # guarded divide → normalized 0.0
            "_call_metadata": {},
            "_raw_output": "",
        }
        judge = self._mock_judge(multidim)

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                result = _evaluate_llm_judge_single(
                    db=db,
                    record_id="r-z",
                    immediate_eval_id="i-z",
                    project_id="p1",
                    task_id="t1",
                    annotation_id=None,
                    user_id="u1",
                    field_name="loesung",
                    metric_type="llm_judge_grundprinzipien",
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o"},
                    organization_id=None,
                )

        assert result["status"] == "completed"
        assert result["score"] == 0.0
        row = db.add.call_args.args[0]
        assert row.passed is False

    def test_multidim_no_scores_raises_runtime_error(self):
        """Multi-dim call returns an error payload (no `scores`) → the helper
        raises RuntimeError with the carried message instead of persisting a
        bogus row."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        judge = self._mock_judge({"error": True, "error_message": "judge refused"})

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                with pytest.raises(RuntimeError, match="judge refused"):
                    _evaluate_llm_judge_single(
                        db=db,
                        record_id="r-e",
                        immediate_eval_id="i-e",
                        project_id="p1",
                        task_id="t1",
                        annotation_id=None,
                        user_id="u1",
                        field_name="loesung",
                        metric_type="llm_judge_grundprinzipien",
                        prediction="pred",
                        reference="ref",
                        metric_params={"judge_model": "gpt-4o"},
                        organization_id=None,
                    )

        # No row committed when the multi-dim call produced no scores.
        db.commit.assert_not_called()

    @staticmethod
    def _dispatching_db(*, annotation_row=None, generation_row=None, task_row=None):
        """A MagicMock db whose query(model).filter(...).first() returns a
        per-model-class row, so we can drive the annotation-fetch and
        generation-fetch branches of the multi-dim path independently of the
        judge-model lookup (which must still return None)."""
        db = MagicMock()

        def query(model):
            name = getattr(model, "__name__", "")
            q = MagicMock()
            if name == "Annotation":
                q.filter.return_value.first.return_value = annotation_row
            elif name == "Generation":  # DBLLMResponse alias → Generation
                q.filter.return_value.first.return_value = generation_row
            elif name == "Task":
                q.filter.return_value.first.return_value = task_row
            else:  # LLMModel judge lookup, etc.
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = query
        return db

    def test_multidim_flattens_annotation_field_outputs(self):
        """annotation_id set + the Annotation row carries a label-studio
        result → the flattener extracts field_outputs from `ann_row.result`
        (4206-4208) and passes them into the multi-dim call."""
        ann_row = types.SimpleNamespace(
            result=[
                {
                    "from_name": "kurzantwort",
                    "type": "textarea",
                    "value": {"text": ["meine antwort"]},
                }
            ]
        )
        task_row = types.SimpleNamespace(data={"frage": "?"})
        db = self._dispatching_db(annotation_row=ann_row, task_row=task_row)

        multidim = {
            "scores": {"a": 5},
            "total_score": 5.0,
            "total_max": 5.0,
            "_call_metadata": {},
            "_raw_output": "",
        }
        judge = self._mock_judge(multidim)

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                result = _evaluate_llm_judge_single(
                    db=db,
                    record_id="r-ann",
                    immediate_eval_id="i-ann",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="ann-99",
                    user_id="u1",
                    field_name="loesung",
                    metric_type="llm_judge_grundprinzipien",
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o"},
                    organization_id=None,
                )

        assert result["status"] == "completed"
        assert result["score"] == pytest.approx(1.0)
        # The flattened annotation field_outputs reached the multi-dim call.
        _, kwargs = judge._evaluate_multidim_single_call.call_args
        assert kwargs["field_outputs"] == {"kurzantwort": "meine antwort"}
        assert kwargs["task_data"] == {"frage": "?"}

    def test_multidim_flattens_generation_parsed_annotation(self):
        """No annotation_id but metric_params carries a generation_id and the
        generation row has a parsed_annotation → the same flattener pulls
        field_outputs off the generation (4213-4216)."""
        gen_row = types.SimpleNamespace(
            parsed_annotation=[
                {
                    "from_name": "begruendung",
                    "type": "textarea",
                    "value": {"text": ["weil"]},
                }
            ]
        )
        db = self._dispatching_db(generation_row=gen_row, task_row=None)

        multidim = {
            "scores": {"a": 2},
            "total_score": 2.0,
            "total_max": 4.0,
            "_call_metadata": {},
            "_raw_output": "",
        }
        judge = self._mock_judge(multidim)

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                result = _evaluate_llm_judge_single(
                    db=db,
                    record_id="r-gen",
                    immediate_eval_id="i-gen",
                    project_id="p1",
                    task_id="t1",
                    annotation_id=None,
                    user_id="u1",
                    field_name="loesung",
                    metric_type="llm_judge_grundprinzipien",
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o", "generation_id": "gen-7"},
                    organization_id=None,
                )

        assert result["status"] == "completed"
        assert result["score"] == pytest.approx(0.5)  # 2 / 4
        _, kwargs = judge._evaluate_multidim_single_call.call_args
        assert kwargs["field_outputs"] == {"begruendung": "weil"}

    def test_multidim_rows_present_but_empty_yield_no_field_outputs(self):
        """Both source rows exist but carry no usable payload: the annotation
        row has `result=None` (falls through the `ann_row and ann_row.result`
        guard, 4207->4211) and the generation row has no parsed_annotation
        (4215->4218). field_outputs ends up empty."""
        ann_row = types.SimpleNamespace(result=None)
        gen_row = types.SimpleNamespace(parsed_annotation=None)
        db = self._dispatching_db(
            annotation_row=ann_row, generation_row=gen_row, task_row=None
        )

        multidim = {
            "scores": {"a": 3},
            "total_score": 3.0,
            "total_max": 6.0,
            "_call_metadata": {},
            "_raw_output": "",
        }
        judge = self._mock_judge(multidim)

        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                result = _evaluate_llm_judge_single(
                    db=db,
                    record_id="r-empty",
                    immediate_eval_id="i-empty",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="ann-empty",
                    user_id="u1",
                    field_name="loesung",
                    metric_type="llm_judge_grundprinzipien",
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o", "generation_id": "gen-empty"},
                    organization_id=None,
                )

        assert result["status"] == "completed"
        assert result["score"] == pytest.approx(0.5)
        _, kwargs = judge._evaluate_multidim_single_call.call_args
        assert kwargs["field_outputs"] == {}
