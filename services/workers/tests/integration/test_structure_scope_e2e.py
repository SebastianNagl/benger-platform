"""End-to-end behavioral test for the prompt-structure scope on evaluation runs.

Drives the REAL ``run_evaluation`` chord pipeline (same setup as
``test_orchestration_branches_e2e.py``) against three generations of the SAME
task and model that differ only in their parent ResponseGeneration's
``structure_key``: one under structure A, one under structure B, one legacy
row with ``structure_key IS NULL``.

Asserts the scoped run grades ONLY the structure-A generation — including the
NULL exclusion (SQL ``IN`` never matches NULL, which is the intended
semantics: a scoped run grades only cells produced under the named
structures) — while an unscoped control run on the same data grades all
three. Metric is the deterministic ``exact_match`` (no judge, no network).
"""

import pytest

import tasks
from models import TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _exact_match_config(config_id="cfg-scope"):
    return {
        "id": config_id,
        "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {},
        "enabled": True,
    }


def test_structure_keys_scope_grades_only_named_structures(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run,
):
    user = make_user()
    make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)

    _, gen_a = make_generation(
        project.id, task.id, "gpt-4o", user.id, "ja",
        structure_key="lexam-open",
    )
    make_generation(
        project.id, task.id, "gpt-4o", user.id, "ja",
        structure_key="fallloesung",
    )
    make_generation(  # legacy row: structure_key IS NULL
        project.id, task.id, "gpt-4o", user.id, "ja",
    )

    # Scoped run: only the lexam-open generation is enumerated. The NULL
    # row must be excluded too, not treated as a wildcard match.
    scoped_run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()
    result = tasks.run_evaluation(
        evaluation_id=scoped_run.id,
        project_id=project.id,
        evaluation_configs=[_exact_match_config()],
        structure_keys=["lexam-open"],
    )
    db_conn.expire_all()

    assert result["status"] == "dispatched"
    assert result["gen_cells"] == 1
    scoped_rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == scoped_run.id)
        .all()
    )
    assert {r.generation_id for r in scoped_rows} == {gen_a.id}

    # Unscoped control on the same data: all three generations are graded.
    control_run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()
    control = tasks.run_evaluation(
        evaluation_id=control_run.id,
        project_id=project.id,
        evaluation_configs=[_exact_match_config()],
    )
    db_conn.expire_all()

    assert control["status"] == "dispatched"
    assert control["gen_cells"] == 3
