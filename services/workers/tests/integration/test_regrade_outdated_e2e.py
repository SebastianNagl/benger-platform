"""Outdated gradings and re-grade runs, end to end (shared/grading_basis.py).

A batch run stamps every row with the grading scheme of its config. Once the
teacher changes the scheme, the rows graded on the old one count as
outdated; a re-grade run (``outdated_only``) grades exactly those, writes
the answers' new rows as drafts a teacher releases, notifies nobody, and
leaves the subjects that are already current alone. The judge runs in its
built-in E2E mock (no network); assertions are on the persisted rows.
"""

import pytest
from sqlalchemy.orm.attributes import flag_modified

import tasks
from evaluation_planning import judge_call_counts, plan_evaluation
from grading_basis import (
    FINGERPRINT_KEY,
    grading_basis_by_config,
    metric_details,
    outdated_gradings_summary,
    scheme_fingerprint,
    stamp_grading_basis,
)
from metric_filters import row_awaits_release
from models import EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

METRIC = "llm_judge_correctness"


@pytest.fixture()
def mock_judge_mode(monkeypatch):
    monkeypatch.setenv("E2E_TEST_MODE", "true")
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: None
    )


def _config(template):
    return {
        "id": "judge",
        "metric": METRIC,
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {
            "judges": [{"judge_model_id": "gpt-4o", "runs": 1}],
            "score_scale": "0-1",
            "custom_prompt_template": template,
        },
        "enabled": True,
    }


def _answer(make_annotation, project, task, user, text):
    return make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": [text]}}],
    )


def _rows(db_conn, run_id):
    db_conn.expire_all()
    return (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run_id)
        .order_by(TaskEvaluation.annotation_id)
        .all()
    )


@pytest.fixture()
def graded_exam(
    mock_judge_mode, db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    teacher = make_user(name="Teacher")
    first, second = make_user(name="First Student"), make_user(name="Second Student")
    project = make_project(created_by=teacher.id)
    task = make_task(project.id, {"musterloesung": "M"}, created_by=teacher.id)
    ann_first = _answer(make_annotation, project, task, first, "Antwort eins")
    ann_second = _answer(make_annotation, project, task, second, "Antwort zwei")
    old = _config("Prüfe die Subsumtion.\n{ground_truth}\n{prediction}")
    project.evaluation_config = {"evaluation_configs": [old]}
    flag_modified(project, "evaluation_config")
    db_conn.commit()

    run = make_evaluation_run(project.id, teacher.id, status="pending")
    tasks.run_evaluation(evaluation_id=run.id, project_id=project.id, evaluation_configs=[old])
    return {
        "teacher": teacher,
        "project": project,
        "task": task,
        "ann_first": ann_first,
        "ann_second": ann_second,
        "old": old,
        "first_run": run,
    }


def _change_scheme(db_conn, project):
    new = _config("Prüfe Subsumtion und Gutachtenstil.\n{ground_truth}\n{prediction}")
    project.evaluation_config = {"evaluation_configs": [new]}
    flag_modified(project, "evaluation_config")
    db_conn.commit()
    return new


def test_every_batch_row_records_its_grading_scheme(db_conn, graded_exam):
    rows = _rows(db_conn, graded_exam["first_run"].id)

    assert len(rows) == 2
    expected = scheme_fingerprint(graded_exam["old"])
    for row in rows:
        # The per-criterion judge writes a flat row: the stamp sits in the
        # <metric>_details sibling, and a plain run writes no draft.
        assert metric_details(row.metrics, METRIC)[FINGERPRINT_KEY] == expected
        assert "review" not in metric_details(row.metrics, METRIC)
        assert not row_awaits_release(row.metrics)
    db_conn.expire_all()
    first_meta = db_conn.get(EvaluationRun, graded_exam["first_run"].id).eval_metadata
    assert first_meta.get("annotators_notified") is True


def test_a_scheme_change_makes_the_rows_outdated(db_conn, graded_exam):
    project = graded_exam["project"]
    assert outdated_gradings_summary(db_conn, project)["total"] == 0

    _change_scheme(db_conn, project)
    summary = outdated_gradings_summary(db_conn, project)

    assert summary["ai"] == 2 and summary["human"] == 0
    [entry] = summary["configs"]
    assert entry["graded"] == 2
    assert entry["outdated"] == 2
    assert entry["reasons"] == {"sheet": 0, "scheme": 2}


def test_regrade_grades_only_outdated_answers_as_unannounced_drafts(
    db_conn, graded_exam, make_evaluation_run,
):
    project = graded_exam["project"]
    new = _change_scheme(db_conn, project)
    # The second answer was already graded on the new scheme: it is current.
    [second_row] = [
        r for r in _rows(db_conn, graded_exam["first_run"].id)
        if r.annotation_id == graded_exam["ann_second"].id
    ]
    second_row.metrics = stamp_grading_basis(
        {k: v for k, v in second_row.metrics.items() if k != f"{METRIC}_details"}, new
    )
    flag_modified(second_row, "metrics")
    db_conn.commit()

    plan = plan_evaluation(db_conn, project.id, [new], outdated_only=True)
    assert [a for _t, a, _d in plan.ann_cells] == [graded_exam["ann_first"].id]
    assert plan.gen_cells == []
    assert plan.cell_config_ids == {graded_exam["ann_first"].id: ["judge"]}
    # The cost estimate prices exactly the planned cells.
    assert judge_call_counts(plan, [new]) == {"gpt-4o": 1}

    regrade = make_evaluation_run(
        project.id, graded_exam["teacher"].id, status="pending",
        eval_metadata={"triggered_by": graded_exam["teacher"].id, "outdated_only": True,
                       "regrade": True},
    )
    tasks.run_evaluation(
        evaluation_id=regrade.id, project_id=project.id, evaluation_configs=[new],
        evaluate_missing_only=True, outdated_only=True,
    )

    rows = _rows(db_conn, regrade.id)
    assert [r.annotation_id for r in rows] == [graded_exam["ann_first"].id]
    details = metric_details(rows[0].metrics, METRIC)
    assert details[FINGERPRINT_KEY] == scheme_fingerprint(new)
    assert details["review"] == {"status": "draft", "reason": "regrade"}
    assert row_awaits_release(rows[0].metrics)

    db_conn.expire_all()
    meta = db_conn.get(EvaluationRun, regrade.id).eval_metadata
    assert meta["cells_dispatched"] == 1
    # Drafts are announced by their release, never by the run.
    assert "annotators_notified" not in meta

    # Nothing is outdated any more: the re-graded draft is the current row.
    assert outdated_gradings_summary(db_conn, project)["total"] == 0
    again = plan_evaluation(db_conn, project.id, [new], outdated_only=True)
    assert again.ann_cells == [] and again.gen_cells == []


def test_rows_written_before_fingerprints_count_as_current(db_conn, graded_exam):
    project = graded_exam["project"]
    for row in _rows(db_conn, graded_exam["first_run"].id):
        row.metrics = {k: v for k, v in row.metrics.items() if k != f"{METRIC}_details"}
        flag_modified(row, "metrics")
    db_conn.commit()
    new = _change_scheme(db_conn, project)

    [basis] = grading_basis_by_config(db_conn, project.id, [new])

    assert len(basis.rows) == 2
    assert basis.outdated_rows == []
