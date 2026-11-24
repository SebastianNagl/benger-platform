"""Gradings outdated by a sheet change (shared/grading_basis.py).

A sheet that already graded is never edited in place: the edit activates a
clone. A row that records the old sheet (``details.rubric_id``) is outdated
once its task is graded along another one, for a judge and for every human
grader's own row alike; only the current row of a cell is judged.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from grading_basis import grading_basis_by_config, outdated_gradings_summary
from models import EvaluationJudgeRun, TaskEvaluation
from project_models import TaskRubric
import task_rubric_resolution
from task_rubric_resolution import resolve_grading_rubric, resolve_grading_rubric_ids

pytestmark = [pytest.mark.integration, pytest.mark.database]

JUDGE = {
    "id": "sheet-judge",
    "metric": "llm_judge_rubric",
    "prediction_fields": ["human:loesung"],
    "reference_fields": ["task.musterloesung"],
    "metric_parameters": {},
    "enabled": True,
}
HUMAN = {
    "id": "human-lane",
    "metric": "korrektur_custom",
    "prediction_fields": ["loesung"],
    "reference_fields": [],
    "metric_parameters": {},
    "enabled": True,
}


def _rubric(db_conn, project, task, status, *, generator=None, created_at=None):
    row = TaskRubric(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        criteria={"a": {"max_score": 2}},
        total_points=2,
        status=status,
        generator_model_id=generator,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_conn.add(row)
    db_conn.commit()
    return row


@pytest.fixture()
def exam(db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run):
    teacher = make_user(name="Teacher")
    other = make_user(name="Second Grader")
    student = make_user(name="Student")
    project = make_project(created_by=teacher.id)
    task = make_task(project.id, {"musterloesung": "M"}, created_by=teacher.id)
    answer = make_annotation(project.id, task.id, student.id, [{"value": "a"}])
    run = make_evaluation_run(project.id, teacher.id, status="completed")
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id="gpt-4o", status="completed"
    )
    db_conn.add(judge_run)
    db_conn.commit()
    project.evaluation_config = {"evaluation_configs": [JUDGE, HUMAN]}
    db_conn.commit()
    return {
        "teacher": teacher, "other": other, "project": project, "task": task,
        "answer": answer, "run": run, "judge_run": judge_run,
    }


def _row(db_conn, exam, config, metric, rubric_id, *, grader=None, age_minutes=0, run=None):
    created_by = grader.id if grader is not None else None
    run, judge_run = run or (exam["run"], exam["judge_run"])
    row = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=run.id,
        judge_run_id=judge_run.id,
        task_id=exam["task"].id,
        annotation_id=exam["answer"].id,
        field_name=(
            f"{config['id']}|human:loesung|task.musterloesung"
            if grader is None else "loesung"
        ),
        evaluation_config_id=config["id"],
        answer_type="long_text",
        ground_truth={},
        prediction={},
        metrics={metric: {"value": 0.5, "method": metric, "details": {"rubric_id": rubric_id}}},
        passed=True,
        created_by=created_by,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )
    db_conn.add(row)
    db_conn.commit()
    return row


def _switch_sheet(db_conn, exam, old):
    old.status = "archived"
    db_conn.commit()
    return _rubric(db_conn, exam["project"], exam["task"], "active")


def test_a_new_sheet_outdates_judge_and_every_graders_row(db_conn, exam):
    old = _rubric(db_conn, exam["project"], exam["task"], "active")
    _row(db_conn, exam, JUDGE, "llm_judge_rubric", old.id)
    _row(db_conn, exam, HUMAN, "korrektur_custom", old.id, grader=exam["teacher"])
    _row(db_conn, exam, HUMAN, "korrektur_custom", old.id, grader=exam["other"])
    assert outdated_gradings_summary(db_conn, exam["project"])["total"] == 0

    _switch_sheet(db_conn, exam, old)
    summary = outdated_gradings_summary(db_conn, exam["project"])

    assert (summary["ai"], summary["human"], summary["total"]) == (1, 2, 3)
    by_config = {entry["config_id"]: entry for entry in summary["configs"]}
    assert by_config["sheet-judge"]["reasons"] == {"sheet": 1, "scheme": 0}
    assert by_config["human-lane"]["graded"] == 2
    assert by_config["human-lane"]["human"] is True


def test_only_the_current_row_of_a_cell_is_judged(db_conn, exam, make_evaluation_run):
    old = _rubric(db_conn, exam["project"], exam["task"], "active")
    _row(db_conn, exam, JUDGE, "llm_judge_rubric", old.id, age_minutes=10)
    new = _switch_sheet(db_conn, exam, old)
    regrade = make_evaluation_run(exam["project"].id, exam["teacher"].id, status="completed")
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=regrade.id, judge_model_id="gpt-4o",
        status="completed",
    )
    db_conn.add(judge_run)
    db_conn.commit()
    _row(db_conn, exam, JUDGE, "llm_judge_rubric", new.id, run=(regrade, judge_run))

    [basis] = grading_basis_by_config(db_conn, exam["project"].id, [JUDGE])

    assert len(basis.rows) == 1
    assert basis.outdated_rows == []


def test_a_task_without_a_usable_sheet_now_does_not_count(db_conn, exam):
    old = _rubric(db_conn, exam["project"], exam["task"], "active")
    _row(db_conn, exam, JUDGE, "llm_judge_rubric", old.id)
    old.status = "archived"
    db_conn.commit()

    [basis] = grading_basis_by_config(db_conn, exam["project"].id, [JUDGE])

    assert basis.outdated_rows == []


@pytest.mark.parametrize("chunk", [1000, 1])
def test_one_query_lookup_matches_the_per_task_lookup(db_conn, exam, make_task, monkeypatch, chunk):
    monkeypatch.setattr(task_rubric_resolution, "_TASK_ID_CHUNK", chunk)
    project = exam["project"]
    task_two = make_task(project.id, {"musterloesung": "M2"}, created_by=exam["teacher"].id)
    active = _rubric(db_conn, project, exam["task"], "active")
    now = datetime.now(timezone.utc)
    _rubric(db_conn, project, task_two, "candidate", generator="gen-a",
            created_at=now - timedelta(hours=1))
    newest = _rubric(db_conn, project, task_two, "candidate", generator="gen-a", created_at=now)
    selector = {"rubric_selector": {"generator_model_id": "gen-a"}}

    for params in ({}, selector):
        bulk = resolve_grading_rubric_ids(db_conn, [exam["task"].id, task_two.id], params)
        single = {}
        for task in (exam["task"], task_two):
            row = resolve_grading_rubric(db_conn, task, params)
            if row is not None:
                single[task.id] = row.id
        assert bulk == single
    assert resolve_grading_rubric_ids(db_conn, [exam["task"].id], {}) == {exam["task"].id: active.id}
    assert resolve_grading_rubric_ids(db_conn, [task_two.id], selector) == {task_two.id: newest.id}
