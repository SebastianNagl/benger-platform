"""The model label a finished evaluation run carries.

Drives the real ``run_evaluation`` orchestrator, its cells and the
``finalize_evaluation_run`` chord callback against the test Postgres with a
deterministic metric (``exact_match``: no judge, no network), the way a
metric-only run over lexical metrics works.

A run's rows name the model they graded through their generation. The run's
own ``model_id`` names the model when it graded one, and stays "unknown"
when it graded several; ``eval_metadata["evaluated_model_ids"]`` lists the
models it graded. Dispatch only knows the models in scope, so a run over
several requested models of which only one had anything to grade used to
stay "unknown".
"""

import pytest
import tasks
from models import EvaluationRun, Generation, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _run_to_completion(db_conn, run, project, config, **scope):
    tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[config],
        **scope,
    )
    db_conn.expire_all()
    finished = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()
    if finished.status not in ("completed", "failed", "cancelled"):
        tasks.finalize_evaluation_run.apply(args=[[], run.id]).get()
        db_conn.expire_all()
        finished = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()
    return finished


def _row_models(db_conn, run_id):
    return sorted(
        model_id
        for (model_id,) in db_conn.query(Generation.model_id)
        .join(TaskEvaluation, TaskEvaluation.generation_id == Generation.id)
        .filter(TaskEvaluation.evaluation_id == run_id)
    )


@pytest.fixture()
def two_model_project(
    db_conn, make_user, make_llm_model, make_project, make_task, make_generation
):
    """Two tasks; model A answered both, model B only the first."""
    user = make_user()
    model_a = make_llm_model(provider="OpenAI")
    model_b = make_llm_model(provider="Anthropic")
    project = make_project(created_by=user.id)
    task_1 = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    task_2 = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task_1.id, model_a.id, user.id, response_content="ja")
    make_generation(project.id, task_2.id, model_a.id, user.id, response_content="nein")
    make_generation(project.id, task_1.id, model_b.id, user.id, response_content="ja")
    db_conn.flush()
    return user, project, model_a, model_b, task_1, task_2


def test_run_over_several_models_lists_them_and_keeps_the_neutral_label(
    db_conn, make_evaluation_run, exact_match_config, two_model_project
):
    user, project, model_a, model_b, *_ = two_model_project
    run = make_evaluation_run(project.id, user.id, model_id="unknown")

    finished = _run_to_completion(
        db_conn, run, project, exact_match_config(),
        model_ids=[model_a.id, model_b.id],
    )

    assert finished.status == "completed"
    assert _row_models(db_conn, run.id) == sorted([model_a.id, model_a.id, model_b.id])
    assert finished.model_id == "unknown"
    # Most rows first.
    assert finished.eval_metadata["evaluated_model_ids"] == [model_a.id, model_b.id]
    assert finished.eval_metadata["evaluated_model_id"] == "unknown"


def test_run_that_graded_one_of_several_requested_models_is_labelled_with_it(
    db_conn, make_evaluation_run, exact_match_config, two_model_project
):
    """Both models were requested, but only model A answered task 2."""
    user, project, model_a, model_b, _task_1, task_2 = two_model_project
    run = make_evaluation_run(
        project.id,
        user.id,
        model_id="unknown",
        eval_metadata={
            "triggered_by": user.id,
            "evaluated_model_ids": [model_a.id, model_b.id],
            "evaluated_model_id": "unknown",
        },
    )

    finished = _run_to_completion(
        db_conn, run, project, exact_match_config(),
        model_ids=[model_a.id, model_b.id], task_ids=[task_2.id],
    )

    assert finished.status == "completed"
    assert _row_models(db_conn, run.id) == [model_a.id]
    assert finished.model_id == model_a.id
    assert finished.eval_metadata["evaluated_model_ids"] == [model_a.id]
    assert finished.eval_metadata["evaluated_model_id"] == model_a.id


def test_run_over_one_model_keeps_that_model(
    db_conn, make_evaluation_run, exact_match_config, two_model_project
):
    user, project, _model_a, model_b, *_ = two_model_project
    run = make_evaluation_run(project.id, user.id, model_id=model_b.id)

    finished = _run_to_completion(
        db_conn, run, project, exact_match_config(), model_ids=[model_b.id]
    )

    assert finished.status == "completed"
    assert finished.model_id == model_b.id
    assert finished.eval_metadata["evaluated_model_ids"] == [model_b.id]
