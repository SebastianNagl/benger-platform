"""What the missing-only skip set reads (services/shared/evaluation_planning.py).

The cost estimate of a ZJS Fälle evaluation (581 tasks, 88k graded rows with
336 MB of judge prose in their metrics) failed with a statement timeout: the
skip set read the metrics blob of every graded row in the project, even for
a run scoped to one model. It now reads only the run's subjects, decides the
scored rows in SQL and fetches the blobs of the other rows alone. These tests
pin that the skip decisions did not change and that the reads stay scoped.
"""

import uuid

import pytest
from sqlalchemy import event

from evaluation_planning import plan_evaluation
from models import EvaluationJudgeRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

CFG = {
    "id": "c1",
    "metric": "llm_judge_falloesung",
    "prediction_fields": ["__all_model__"],
    "reference_fields": ["musterloesung"],
    "metric_parameters": {"judge_model": "gpt-5.4-mini"},
    "enabled": True,
}
KEY = "c1|__all_model__|musterloesung"


@pytest.fixture()
def grade(db_conn, make_evaluation_run):
    def _grade(project_id, user_id, task_id, generation_id, metrics):
        run = make_evaluation_run(project_id, user_id, status="completed")
        judge_run = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id,
                                       judge_model_id="gpt-5.4-mini", status="completed")
        db_conn.add(judge_run)
        db_conn.commit()
        row = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            judge_run_id=judge_run.id,
            task_id=task_id,
            generation_id=generation_id,
            field_name=KEY,
            answer_type="long_text",
            ground_truth={},
            prediction={},
            metrics=metrics,
            passed=False,
            evaluation_config_id="c1",
        )
        db_conn.add(row)
        db_conn.commit()
        return row

    return _grade


@pytest.fixture()
def statements(db_conn):
    """Every statement the session runs, with its bound parameters."""
    seen = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, parameters))

    engine = db_conn.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    yield seen
    event.remove(engine, "before_cursor_execute", _record)


# (metrics blob, counts as graded): the shapes _row_has_score and
# _row_is_terminal_error tell apart.
ROW_SHAPES = {
    "bare_float": ({"llm_judge_falloesung": 0.8}, True),
    "unified_value": ({"llm_judge_falloesung": {"value": 0.4, "details": {"why": "x" * 500}}}, True),
    "feedback_only": ({"llm_judge_falloesung": {"value": None, "details": {"feedback_only": True}}}, True),
    "terminal_error": ({"llm_judge_falloesung": {"value": None, "error": "schema mismatch"}}, True),
    "retryable_error": ({"llm_judge_falloesung": {"value": None, "error": "Error code: 429 rate limit"}}, False),
    "retryable_by_type": ({"llm_judge_falloesung": {
        "value": None, "error": "boom", "details": {"call_metadata": {"error_type": "rate_limit"}}}}, False),
    "boolean_only": ({"passed": True}, False),
    "error_key_number": ({"error": 1}, False),
    "valueless_dict": ({"llm_judge_falloesung": {"value": None}}, False),
    "json_null": (None, False),
}


def test_skip_set_keeps_its_decision_for_every_row_shape(
    db_conn, make_user, make_project, make_task, make_generation, grade
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "M"}, created_by=user.id)
    gens = {}
    for shape, (metrics, _graded) in ROW_SHAPES.items():
        _, gen = make_generation(project.id, task.id, "gpt-4o-mini", user.id, shape)
        grade(project.id, user.id, task.id, gen.id, metrics)
        gens[shape] = gen.id

    plan = plan_evaluation(db_conn, project.id, [CFG], missing_only=True)

    planned = {g for _t, g, _done in plan.gen_cells}
    expected = {gens[s] for s, (_m, graded) in ROW_SHAPES.items() if not graded}
    assert planned == expected


def test_skip_set_reads_only_the_unscored_blobs_of_the_runs_subjects(
    db_conn, make_user, make_project, make_task, make_generation, grade, statements
):
    user = make_user()
    project = make_project(created_by=user.id)
    in_scope_unscored = []
    in_scope_scored = []
    out_of_scope = []
    for _ in range(30):
        task = make_task(project.id, {"musterloesung": "M"}, created_by=user.id)
        _, scoped = make_generation(project.id, task.id, "qwen", user.id, "a")
        _, other = make_generation(project.id, task.id, "gpt-4o-mini", user.id, "b")
        in_scope_scored.append(
            grade(project.id, user.id, task.id, scoped.id, {"llm_judge_falloesung": 0.5}).id
        )
        out_of_scope.append(
            grade(project.id, user.id, task.id, other.id,
                  {"llm_judge_falloesung": {"value": None, "error": "429 rate limit"}}).id
        )
        in_scope_unscored.append(
            grade(project.id, user.id, task.id, scoped.id,
                  {"llm_judge_falloesung": {"value": None, "error": "429 rate limit"}}).id
        )
    statements.clear()

    plan = plan_evaluation(
        db_conn, project.id, [CFG], model_ids=["qwen"], missing_only=True,
    )

    assert len(plan.gen_cells) == 0  # every scoped generation has a score
    blob_reads = [
        (sql, params) for sql, params in statements
        if "task_evaluations.metrics AS" in sql
    ]
    read_ids = {v for _sql, params in blob_reads for v in params.values()}
    assert read_ids == set(in_scope_unscored)
    assert not read_ids & set(in_scope_scored)
    assert not read_ids & set(out_of_scope)
    # No other statement binds an id per task: the task and subject scope go
    # in as subqueries, so a large project cannot outgrow the driver's limit
    # (the blob reads bind ids in bounded chunks).
    assert max(
        len(params) for sql, params in statements if (sql, params) not in blob_reads
    ) < 30
