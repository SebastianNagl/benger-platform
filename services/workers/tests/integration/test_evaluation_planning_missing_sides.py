"""Missing-only planning per side (services/shared/evaluation_planning.py).

A subject counts as fully graded when it carries the keys of ITS side: a
generation the model-side keys, an answer the human-side keys. Checking every
subject against the keys of both sides never matched for a config that grades
both (``["__all_model__", "human:loesung"]``), so every graded answer was
dispatched again on each missing-only run.
"""

import uuid

import pytest

from evaluation_planning import plan_evaluation
from models import EvaluationJudgeRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _cfg(cid, preds):
    return {
        "id": cid,
        "metric": "llm_judge_falloesung",
        "prediction_fields": preds,
        "reference_fields": ["musterloesung"],
        "metric_parameters": {"judge_model": "gpt-5.4-mini"},
        "enabled": True,
    }


@pytest.fixture()
def graded(db_conn, make_evaluation_run):
    def _grade(project_id, user_id, task_id, field_name, generation_id=None,
               annotation_id=None, config_id="c1"):
        run = make_evaluation_run(project_id, user_id, status="completed")
        judge_run = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id,
                                  judge_model_id="gpt-5.4-mini", status="completed")
        db_conn.add(judge_run)
        db_conn.commit()
        db_conn.add(TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            judge_run_id=judge_run.id,
            task_id=task_id,
            generation_id=generation_id,
            annotation_id=annotation_id,
            field_name=field_name,
            answer_type="long_text",
            ground_truth={},
            prediction={},
            metrics={"llm_judge_falloesung": 0.8},
            passed=True,
            evaluation_config_id=config_id,
        ))
        db_conn.commit()

    return _grade


@pytest.fixture()
def subjects(make_user, make_project, make_task, make_generation, make_annotation):
    user = make_user()
    other = make_user(name="Second Answerer")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "M"}, created_by=user.id)
    _, gen = make_generation(project.id, task.id, "gpt-4o-mini", user.id, "Antwort")
    graded_ann = make_annotation(project.id, task.id, user.id, [{"value": "a"}])
    open_ann = make_annotation(project.id, task.id, other.id, [{"value": "b"}])
    return user, project, task, gen, graded_ann, open_ann


def test_graded_subjects_of_a_two_sided_config_are_skipped(db_conn, subjects, graded):
    user, project, task, gen, graded_ann, open_ann = subjects
    graded(project.id, user.id, task.id, "c1|__all_model__|musterloesung", generation_id=gen.id)
    graded(project.id, user.id, task.id, "c1|human:loesung|musterloesung", annotation_id=graded_ann.id)

    plan = plan_evaluation(
        db_conn, project.id, [_cfg("c1", ["__all_model__", "human:loesung"])],
        missing_only=True,
    )

    assert plan.gen_cells == []
    assert [a for _t, a, _done in plan.ann_cells] == [open_ann.id]


def test_plain_answer_field_rows_count_as_graded(db_conn, subjects, graded):
    # A Falllösung config's plain field grades answers; stored rows carry no
    # human: prefix and still count.
    user, project, task, _gen, graded_ann, open_ann = subjects
    graded(project.id, user.id, task.id, "c2|loesung|musterloesung",
           annotation_id=graded_ann.id, config_id="c2")

    plan = plan_evaluation(
        db_conn, project.id, [_cfg("c2", ["loesung"])], missing_only=True,
    )

    assert [a for _t, a, _done in plan.ann_cells] == [open_ann.id]


def test_without_missing_only_every_subject_is_planned(db_conn, subjects, graded):
    user, project, task, gen, graded_ann, open_ann = subjects
    graded(project.id, user.id, task.id, "c1|human:loesung|musterloesung", annotation_id=graded_ann.id)

    plan = plan_evaluation(
        db_conn, project.id, [_cfg("c1", ["__all_model__", "human:loesung"])],
        missing_only=False,
    )

    assert [g for _t, g, _d in plan.gen_cells] == [gen.id]
    assert {a for _t, a, _d in plan.ann_cells} == {graded_ann.id, open_ann.id}
