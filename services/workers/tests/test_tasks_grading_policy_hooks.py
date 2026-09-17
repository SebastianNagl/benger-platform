"""Behavioral coverage for the grading dispatch-policy + finalize extension
hooks in ``run_single_sample_evaluation`` (tasks.py).

The hooks are soft-looked-up from ``benger_extended.workers`` so the community
edition no-ops. These tests inject a fake ``benger_extended.workers`` module
via ``sys.modules`` (the platform test image has no real extended package) and
assert on REAL task behavior: which organization_id reaches the per-config
jobs, which judge model the created EvaluationJudgeRun records, and what the
finalize hook is called with on success / job-error / task-crash.

Idioms mirror ``test_tasks_helpers_remaining.py``: SessionLocal patched to a
model-class-keyed fake session; the bind=True task invoked via ``.run(...)``;
``_run_immediate_config_job`` stubbed so no heavy metric registry loads.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module  # noqa: E402
from tasks import run_single_sample_evaluation  # noqa: E402


class _HookDispatchDB:
    """Fake session with per-model-class query dispatch (see
    test_tasks_helpers_remaining._RSSEDispatchDB for the idiom)."""

    def __init__(self, *, project_row, eval_run_first, judge_model_row):
        self._project_row = project_row
        self._eval_run_first = list(eval_run_first)
        self._judge_model_row = judge_model_row
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", "")
        q = MagicMock()
        if name == "Project":
            q.filter.return_value.first.return_value = self._project_row
        elif name == "EvaluationRun":
            nxt = self._eval_run_first.pop(0) if self._eval_run_first else None
            q.filter.return_value.first.return_value = nxt
        elif name == "EvaluationJudgeRun":
            q.filter.return_value.first.return_value = None
        elif name == "LLMModel":
            q.filter.return_value.first.return_value = self._judge_model_row
        elif name == "TaskEvaluation":
            q.filter.return_value.all.return_value = []
            q.filter.return_value.first.return_value = None
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _fresh_db():
    project_row = types.SimpleNamespace(
        id="p1", label_config_version=1, evaluation_config={}
    )
    eval_run_after = MagicMock()
    eval_run_after.eval_metadata = {"configs": [{"metric": "llm_judge_custom"}]}
    eval_run_after.metrics = {}
    return _HookDispatchDB(
        project_row=project_row,
        eval_run_first=[None, eval_run_after],
        judge_model_row=types.SimpleNamespace(
            id="gpt-5-mini", recommended_parameters=None
        ),
    )


def _configs(judge_model="gpt-5.4-mini"):
    return [
        {
            "id": "cfg-judge",
            "metric": "llm_judge_custom",
            "display_name": "Judge",
            "prediction_fields": ["loesung"],
            "reference_fields": ["task.musterloesung"],
            "metric_parameters": {"judge_model": judge_model},
        }
    ]


def _fake_extended(policy_fn=None, finalize_fn=None):
    """Build fake benger_extended / benger_extended.workers modules."""
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    if policy_fn is not None:
        workers.get_grading_dispatch_policy_fn = lambda: policy_fn
    if finalize_fn is not None:
        workers.get_grading_finalize_fn = lambda: finalize_fn
    pkg.workers = workers
    return {"benger_extended": pkg, "benger_extended.workers": workers}


def _run(db, configs, captured_jobs=None):
    def fake_job(**kwargs):
        if captured_jobs is not None:
            captured_jobs.append(kwargs)
        return {"status": "completed", "metric": kwargs["job"]["metric_type"], "score": 1.0}

    with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
        with patch.object(tasks_module, "_run_immediate_config_job", side_effect=fake_job):
            return run_single_sample_evaluation.run(
                evaluation_record_id="eval-hook-1",
                project_id="p1",
                task_id="t1",
                annotation_id="a1",
                evaluation_configs=configs,
                annotation_results={"loesung": "meine lösung"},
                task_data={"musterloesung": "referenz"},
                organization_id=None,
                user_id="u1",
            )


class TestPolicyHook:
    def test_no_extended_module_passes_through_unchanged(self):
        """Fake module WITHOUT the hook attrs → soft lookup degrades to no-op:
        original org (None) reaches the jobs, judge model stays as dispatched."""
        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended()):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert captured[0]["organization_id"] is None
        judge_run = next(o for o in db.added if type(o).__name__ == "EvaluationJudgeRun")
        assert judge_run.judge_model_id == "gpt-5.4-mini"

    def test_policy_overrides_org_and_judge_model(self):
        """The policy's returned (org, configs) drive key resolution AND the
        judge_run's recorded model — the override must land BEFORE judge runs
        are created so provenance stays truthful."""
        seen = {}

        def policy(db, *, project, user_id, organization_id, configs, evaluation_run_id, eval_metadata):
            seen["project_id"] = getattr(project, "id", None)
            seen["user_id"] = user_id
            seen["evaluation_run_id"] = evaluation_run_id
            new_configs = [dict(c) for c in configs]
            for c in new_configs:
                params = dict(c.get("metric_parameters") or {})
                params["judge_model"] = "gpt-5-mini"
                c["metric_parameters"] = params
            return "org-vertretbar", new_configs

        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert seen == {
            "project_id": "p1",
            "user_id": "u1",
            "evaluation_run_id": "eval-hook-1",
        }
        # Overridden org reached the fanned-out job (→ key resolution).
        assert captured[0]["organization_id"] == "org-vertretbar"
        # Overridden judge model reached both the judge_run row and the job.
        judge_run = next(o for o in db.added if type(o).__name__ == "EvaluationJudgeRun")
        assert judge_run.judge_model_id == "gpt-5-mini"
        assert captured[0]["job"]["metric_params"]["judge_model"] == "gpt-5-mini"

    def test_policy_crash_keeps_dispatched_values(self):
        """A raising policy is logged and ignored — the task proceeds with the
        originally dispatched org/configs (fails loud downstream on key
        resolution rather than silently misrouting)."""

        def policy(*args, **kwargs):
            raise RuntimeError("extension bug")

        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert captured[0]["organization_id"] is None
        judge_run = next(o for o in db.added if type(o).__name__ == "EvaluationJudgeRun")
        assert judge_run.judge_model_id == "gpt-5.4-mini"


class TestFinalizeHook:
    def test_finalize_called_with_success_true_on_clean_run(self):
        calls = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(finalize_fn=lambda rid, ok: calls.append((rid, ok)))):
            result = _run(db, _configs())

        assert result["status"] == "completed"
        assert calls == [("eval-hook-1", True)]

    def test_finalize_called_with_success_false_when_a_job_errors(self):
        calls = []
        db = _fresh_db()

        def failing_job(**kwargs):
            return {"status": "error", "error": "judge exploded"}

        with patch.dict(sys.modules, _fake_extended(finalize_fn=lambda rid, ok: calls.append((rid, ok)))):
            with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
                with patch.object(
                    tasks_module, "_run_immediate_config_job", side_effect=failing_job
                ):
                    result = run_single_sample_evaluation.run(
                        evaluation_record_id="eval-hook-1",
                        project_id="p1",
                        task_id="t1",
                        annotation_id="a1",
                        evaluation_configs=_configs(),
                        annotation_results={"loesung": "meine lösung"},
                        task_data={"musterloesung": "referenz"},
                        organization_id=None,
                        user_id="u1",
                    )

        assert result["status"] == "completed"
        assert calls == [("eval-hook-1", False)]

    def test_finalize_called_with_false_when_task_crashes(self):
        """The outer except path voids the grading (success=False) so a failed
        run releases a claimed weekly free slot instead of eating it."""
        calls = []

        class _ExplodingDB(_HookDispatchDB):
            def query(self, model):
                raise RuntimeError("db down")

        db = _ExplodingDB(project_row=None, eval_run_first=[], judge_model_row=None)
        with patch.dict(sys.modules, _fake_extended(finalize_fn=lambda rid, ok: calls.append((rid, ok)))):
            with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
                result = run_single_sample_evaluation.run(
                    evaluation_record_id="eval-hook-1",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="a1",
                    evaluation_configs=_configs(),
                    annotation_results={},
                    task_data={},
                    organization_id=None,
                    user_id="u1",
                )

        assert result["status"] == "error"
        assert calls == [("eval-hook-1", False)]

    def test_finalize_crash_does_not_kill_the_run(self):
        def bad_finalize(rid, ok):
            raise RuntimeError("billing down")

        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(finalize_fn=bad_finalize)):
            result = _run(db, _configs())

        assert result["status"] == "completed"


class _AddedRunDB(_HookDispatchDB):
    """After the pre-created lookups are used up, EvaluationRun queries
    return the run the task added, so the failure path sees the real row."""

    def query(self, model):
        if getattr(model, "__name__", "") == "EvaluationRun" and not self._eval_run_first:
            q = MagicMock()
            added = [o for o in self.added if type(o).__name__ == "EvaluationRun"]
            q.filter.return_value.first.return_value = added[-1] if added else None
            return q
        return super().query(model)


def _blocking_db():
    return _AddedRunDB(
        project_row=types.SimpleNamespace(
            id="p1", label_config_version=1, evaluation_config={}
        ),
        eval_run_first=[None],
        judge_model_row=types.SimpleNamespace(
            id="gpt-5-mini", recommended_parameters=None
        ),
    )


class TestPolicyBlock:
    def test_four_tuple_without_block_proceeds_with_policy_values(self):
        """A 4-tuple whose block is None grades normally: the policy's org and
        consumer-billing authorization reach the job."""

        def policy(db, **kwargs):
            return "org-lms", kwargs["configs"], True, None

        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert len(captured) == 1
        assert captured[0]["organization_id"] == "org-lms"
        assert captured[0]["org_billing_authorized"] is True

    def test_three_tuple_still_carries_the_authorization(self):
        def policy(db, **kwargs):
            return "org-pays", kwargs["configs"], 1

        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert captured[0]["organization_id"] == "org-pays"
        assert captured[0]["org_billing_authorized"] is True

    def test_block_marks_run_failed_and_runs_no_judge(self):
        """A block fails the run with the reason in its metadata, builds no
        judge run and no job, and settles the grading as unsuccessful."""
        block = {
            "code": "lti_org_unfunded",
            "reason": "org_key_missing",
            "org_id": "org-lms",
            "missing_providers": ["openai"],
        }

        def policy(db, **kwargs):
            return "org-lms", kwargs["configs"], False, block

        captured, finalized = [], []
        db = _blocking_db()
        with patch.dict(
            sys.modules,
            _fake_extended(
                policy_fn=policy,
                finalize_fn=lambda rid, ok: finalized.append((rid, ok)),
            ),
        ):
            result = _run(db, _configs(), captured)

        assert result == {
            "status": "blocked",
            "evaluation_record_id": "eval-hook-1",
            "block": block,
        }
        assert captured == []
        assert not [o for o in db.added if type(o).__name__ == "EvaluationJudgeRun"]
        run = next(o for o in db.added if type(o).__name__ == "EvaluationRun")
        assert run.status == "failed"
        assert run.eval_metadata["error"] == "billing_blocked:org_key_missing"
        stamped = run.eval_metadata["billing_block"]
        assert {k: stamped[k] for k in block} == block
        assert stamped["checked_at"]
        # The expected-config list written before the policy ran is kept.
        assert run.eval_metadata["evaluation_type"] == "immediate"
        assert finalized == [("eval-hook-1", False)]

    def test_block_given_as_reason_string_is_normalized(self):
        def policy(db, **kwargs):
            return None, kwargs["configs"], False, "org_not_paying"

        captured = []
        db = _blocking_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "blocked"
        assert result["block"] == {"reason": "org_not_paying"}
        assert captured == []
        run = next(o for o in db.added if type(o).__name__ == "EvaluationRun")
        assert run.status == "failed"
        assert run.eval_metadata["billing_block"]["reason"] == "org_not_paying"

    def test_unexpected_policy_shape_keeps_dispatched_values(self):
        """A 5-tuple is not a contract shape: it is logged and ignored, like a
        crashing policy, and the grading runs as dispatched."""

        def policy(db, **kwargs):
            return "org-x", [], True, {"reason": "x"}, "extra"

        captured = []
        db = _fresh_db()
        with patch.dict(sys.modules, _fake_extended(policy_fn=policy)):
            result = _run(db, _configs(), captured)

        assert result["status"] == "completed"
        assert captured[0]["organization_id"] is None
        assert captured[0]["org_billing_authorized"] is False


class _AbortingDB(_HookDispatchDB):
    """A session with the transaction semantics a failed query leaves behind:
    once ``aborted``, every statement fails until ``rollback()``, and the
    rollback discards whatever was only flushed, not committed."""

    def __init__(self, *, committed_run=None):
        super().__init__(
            project_row=types.SimpleNamespace(
                id="p1", label_config_version=7, evaluation_config={}
            ),
            eval_run_first=[],
            judge_model_row=types.SimpleNamespace(
                id="gpt-5-mini", recommended_parameters=None
            ),
        )
        self.aborted = False
        self.committed = [committed_run] if committed_run is not None else []
        self.pending = []
        self.rollbacks = 0

    def _check(self):
        if self.aborted:
            raise RuntimeError("InFailedSqlTransaction: transaction is aborted")

    def query(self, model):
        self._check()
        if getattr(model, "__name__", "") == "EvaluationRun":
            runs = [
                o
                for o in self.committed + self.pending
                if type(o).__name__ == "EvaluationRun"
            ]
            q = MagicMock()
            q.filter.return_value.first.return_value = runs[-1] if runs else None
            return q
        return super().query(model)

    def add(self, obj):
        self._check()
        super().add(obj)
        self.pending.append(obj)

    def flush(self):
        self._check()

    def commit(self):
        self._check()
        self.committed.extend(self.pending)
        self.pending = []

    def rollback(self):
        self.rollbacks += 1
        self.aborted = False
        for obj in self.pending:
            self.added.remove(obj)
        self.pending = []


def _failed_check_policy(db, **kwargs):
    db.aborted = True  # one of the policy's queries failed
    return "org-lms", kwargs["configs"], False, {"reason": "billing_check_failed"}


class TestBlockAfterFailedPolicyQuery:
    """A DB error inside the policy still yields a fail-closed block. The
    run must end ``failed``; before the fix it stayed ``running`` (the write
    hit the aborted transaction), so no retry path ever graded it again."""

    def test_pre_created_run_is_marked_failed(self):
        from models import EvaluationRun

        run = EvaluationRun(
            id="eval-hook-1",
            project_id="p1",
            model_id="immediate",
            evaluation_type_ids=["llm_judge_custom"],
            status="running",
            created_by="u1",
            eval_metadata={"evaluation_type": "immediate", "configs": [{"id": "x"}]},
            metrics={},
        )
        db = _AbortingDB(committed_run=run)
        captured, finalized = [], []
        with patch.dict(
            sys.modules,
            _fake_extended(
                policy_fn=_failed_check_policy,
                finalize_fn=lambda rid, ok: finalized.append((rid, ok)),
            ),
        ):
            result = _run(db, _configs(), captured)

        assert result["status"] == "blocked"
        assert db.rollbacks >= 1
        assert run.status == "failed"
        assert run.eval_metadata["error"] == "billing_blocked:billing_check_failed"
        assert run.eval_metadata["billing_block"]["reason"] == "billing_check_failed"
        assert run.eval_metadata["label_config_version"] == 7
        assert captured == []
        assert finalized == [("eval-hook-1", False)]

    def test_run_only_flushed_by_the_task_is_written_again_failed(self):
        db = _AbortingDB()
        finalized = []
        with patch.dict(
            sys.modules,
            _fake_extended(
                policy_fn=_failed_check_policy,
                finalize_fn=lambda rid, ok: finalized.append((rid, ok)),
            ),
        ):
            result = _run(db, _configs(), [])

        assert result["status"] == "blocked"
        runs = [o for o in db.added if type(o).__name__ == "EvaluationRun"]
        assert len(runs) == 1
        run = runs[0]
        assert run in db.committed
        assert run.id == "eval-hook-1"
        assert run.status == "failed"
        assert run.model_id == "immediate"
        assert run.project_id == "p1"
        assert run.created_by == "u1"
        meta = run.eval_metadata
        assert meta["error"] == "billing_blocked:billing_check_failed"
        assert meta["billing_block"]["reason"] == "billing_check_failed"
        assert meta["evaluation_type"] == "immediate"
        assert meta["expected_config_count"] == 1
        assert meta["label_config_version"] == 7
        assert not [o for o in db.added if type(o).__name__ == "EvaluationJudgeRun"]
        assert finalized == [("eval-hook-1", False)]
