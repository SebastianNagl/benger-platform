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
