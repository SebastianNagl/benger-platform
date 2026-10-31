"""Evaluation cells must not hold a DB transaction across judge calls.

A cell reads its inputs, then spends minutes in LLM judge calls. When the
session stayed in its read transaction for that time, the backend sat idle in
transaction holding AccessShareLocks, which blocked the 2026-10-15 migration
on ``users``. The cell now ends the read transaction before the fan-out,
releases the short reads it makes inside the loop (rubric, project config)
right away, and writes everything in one transaction at the end.

The fake session below tracks whether a transaction is open the way a real
Session does: any query or execute begins one, commit/rollback ends it.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module  # noqa: E402
from evaluation import cell_evaluator  # noqa: E402


class _FakeQuery:
    def __init__(self, db, result):
        self._db = db
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def scalar(self):
        return self._result


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.in_tx = False
        self.events = []
        self.expire_on_commit = True

    def query(self, entity):
        self.in_tx = True
        self.events.append("query")
        name = getattr(entity, "__name__", None)
        return _FakeQuery(self, self.rows.get(name))

    def commit(self):
        self.in_tx = False
        self.events.append("commit")

    def rollback(self):
        self.in_tx = False
        self.events.append("rollback")

    def close(self):
        self.events.append("close")


class _RecordingJudge:
    """Stands in for an LLMJudgeEvaluator; records the session state."""

    score_scale = "0-1"

    def __init__(self, db, multidim=False):
        self._db = db
        self._multidim = multidim
        self.tx_open_during_call = []

    def is_multidim_mode(self):
        return self._multidim

    def bind_task_rubric(self, rubric, margin_notes=False):
        pass

    def _record(self):
        self.tx_open_during_call.append(self._db.in_tx)
        self._db.events.append("llm")

    def _evaluate_single_criterion(self, **kwargs):
        self._record()
        return {"score": 0.8}

    def _evaluate_multidim_single_call(self, **kwargs):
        self._record()
        return {"scores": {"a": 1}, "total_score": 1.0, "total_max": 1.0}


def _run_cell(db, judges_by_config, configs):
    def _upsert(session, rows):
        session.in_tx = True
        session.events.append("upsert")
        return len(rows), len(rows), 0

    def _bump(session, **kwargs):
        session.in_tx = True
        session.events.append("bump")

    judge_runs = {
        cid: [
            {
                "evaluator": judge,
                "judge_run_id": f"jr-{cid}",
                "judge_model_id": "judge-model",
                "run_index": 0,
            }
        ]
        for cid, judge in judges_by_config.items()
    }

    with patch.object(tasks_module, "SessionLocal", return_value=db), \
            patch.object(tasks_module, "_record_cell_attempt", return_value=1), \
            patch.object(
                tasks_module,
                "_reconstruct_judge_evaluators_for_cell",
                return_value=(judge_runs, dict(judges_by_config)),
            ), \
            patch.object(tasks_module, "_build_sample_evaluator_for_cell", return_value=MagicMock()), \
            patch.object(tasks_module, "_bulk_upsert_task_evaluations", side_effect=_upsert), \
            patch.object(tasks_module, "_bump_evaluation_counters", side_effect=_bump), \
            patch.object(tasks_module, "_publish_progress"), \
            patch.object(cell_evaluator, "resolve_inline_judge", return_value=None):
        return cell_evaluator.evaluate_generation_cell_impl(
            None,
            evaluation_id="eval-1",
            task_id="t1",
            generation_id="g1",
            project_id="p1",
            configs_for_cell=configs,
            judge_run_ids_by_config={},
            default_judge_run_id="jr-default",
            organization_id=None,
            triggered_by_user_id="u1",
        )


def _rows():
    gen = types.SimpleNamespace(
        id="g1",
        response_content="the prediction",
        parsed_annotation=None,
        model_id="m1",
        parse_status="success",
    )
    task = types.SimpleNamespace(id="t1", data={"answer": "the reference"})
    return {"Generation": gen, "Task": task}


def _config(cid, metric):
    return {
        "id": cid,
        "metric": metric,
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.answer"],
    }


def test_judge_call_runs_outside_a_transaction():
    db = _FakeSession(_rows())
    judge = _RecordingJudge(db)

    result = _run_cell(db, {"c1": judge}, [_config("c1", "llm_judge_custom")])

    assert result["status"] == "ok", result
    assert judge.tx_open_during_call == [False]
    assert db.expire_on_commit is False
    # Read phase, release, judge call, then one write transaction.
    llm_at = db.events.index("llm")
    assert db.events[llm_at - 1] == "commit"
    assert db.events[llm_at + 1:] == ["upsert", "bump", "commit", "close"]


def test_in_loop_reads_are_released_before_the_next_judge_call():
    """The rubric lookup and the project config read inside the loop open a
    short transaction each; neither may still be open when a judge runs."""
    db = _FakeSession(_rows())
    rubric_judge = _RecordingJudge(db, multidim=True)
    second_judge = _RecordingJudge(db)

    def _fake_rubric(session, task, params):
        session.in_tx = True
        session.events.append("rubric_read")
        return types.SimpleNamespace(criteria={"a": {"max_score": 1}})

    def _fake_project_config(session, project_id):
        session.in_tx = True
        session.events.append("project_read")
        return None

    with patch.object(cell_evaluator, "_resolve_task_rubric", side_effect=_fake_rubric), \
            patch.object(cell_evaluator, "_project_eval_config", side_effect=_fake_project_config), \
            patch.object(cell_evaluator, "_stamp_rubric_result"), \
            patch.object(cell_evaluator, "_render_rubric_text", return_value="rubric"), \
            patch.object(
                tasks_module,
                "_build_multidim_judge_row_metrics",
                return_value=({"llm_judge_rubric": {"value": 1.0}}, 1.0),
            ):
        result = _run_cell(
            db,
            {"c1": rubric_judge, "c2": second_judge},
            [_config("c1", "llm_judge_rubric"), _config("c2", "llm_judge_custom")],
        )

    assert result["status"] == "ok", result
    assert rubric_judge.tx_open_during_call == [False]
    assert second_judge.tx_open_during_call == [False]
    for marker in ("rubric_read", "project_read"):
        at = db.events.index(marker)
        assert db.events[at + 1] == "commit", (marker, db.events)
