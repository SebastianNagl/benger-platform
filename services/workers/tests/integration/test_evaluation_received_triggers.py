"""Grading notifications from the worker triggers, against the real DB.

``_notify_batch_grading_received`` finds its recipients with SQL over
task_evaluations and annotations and stores a marker on the run;
``_notify_immediate_grading_received`` checks that the run wrote rows. Both
hand their recipients to the platform helper, which ends in
``NotificationService.create_notification``. A recorder stands in for that
last call (as the conftest stub does for the other db_conn tests), so these
tests assert who would be notified without writing Notification rows the
cleanup does not track.
"""

import uuid

import pytest

import tasks
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    def _record(db, user_ids, notification_type, title, message, data=None,
                organization_id=None):
        calls.append(
            {
                "user_ids": list(user_ids),
                "type": getattr(notification_type, "value", notification_type),
                "data": data,
            }
        )
        return []

    monkeypatch.setattr(
        tasks.NotificationService, "create_notification", staticmethod(_record)
    )
    return calls


def _judge_run(db, run):
    judge_run = (
        db.query(EvaluationJudgeRun).filter(EvaluationJudgeRun.evaluation_id == run.id).first()
    )
    if judge_run is None:
        judge_run = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id,
                                       status="completed")
        db.add(judge_run)
        db.commit()
    return judge_run


def _grade(db, run, task_id, annotation_id=None, generation_id=None):
    row = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=run.id,
        judge_run_id=_judge_run(db, run).id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=generation_id,
        field_name="answer",
        answer_type="text",
        ground_truth={"value": "Ja"},
        prediction={"value": "Ja"},
        metrics={"exact_match": 1.0},
        passed=True,
    )
    db.add(row)
    db.commit()
    return row


def _stored_metadata(db, run_id):
    db.expire_all()
    return db.query(EvaluationRun).filter(EvaluationRun.id == run_id).one().eval_metadata


class TestBatchTrigger:
    def test_notifies_every_annotator_once_and_marks_the_run(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run, make_llm_model, make_generation,
    ):
        starter, alice, bob = make_user("Starter"), make_user("Alice"), make_user("Bob")
        project = make_project(created_by=starter.id, title="Klausur Zivilrecht")
        first = make_task(project.id, {"text": "Fall 1"})
        second = make_task(project.id, {"text": "Fall 2"})
        run = make_evaluation_run(project.id, starter.id, status="completed")

        for task, user in ((first, alice), (second, alice), (first, bob), (first, starter)):
            annotation = make_annotation(project.id, task.id, user.id, result=[])
            _grade(db_conn, run, task.id, annotation_id=annotation.id)
        model = make_llm_model()
        _, generation = make_generation(project.id, first.id, model.id, starter.id, "Antwort")
        _grade(db_conn, run, first.id, generation_id=generation.id)

        tasks._notify_batch_grading_received(db_conn, run)

        assert len(recorded) == 1
        assert recorded[0]["user_ids"] == sorted([alice.id, bob.id])
        assert recorded[0]["type"] == "evaluation_received_batch"
        assert recorded[0]["data"]["evaluation_id"] == run.id
        assert recorded[0]["data"]["project_title"] == "Klausur Zivilrecht"

        stored = _stored_metadata(db_conn, run.id)
        assert stored["annotators_notified"] is True
        assert stored["triggered_by"] == starter.id

        # A re-finalized run reads the stored marker and stays silent.
        tasks._notify_batch_grading_received(
            db_conn, db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()
        )
        assert len(recorded) == 1

    def test_run_that_only_graded_its_starter_stays_unmarked(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        starter = make_user("Starter")
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Fall"})
        run = make_evaluation_run(project.id, starter.id, status="completed")
        annotation = make_annotation(project.id, task.id, starter.id, result=[])
        _grade(db_conn, run, task.id, annotation_id=annotation.id)

        tasks._notify_batch_grading_received(db_conn, run)

        assert recorded == []
        assert "annotators_notified" not in _stored_metadata(db_conn, run.id)

    def test_run_creator_is_left_out_when_triggered_by_is_missing(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        owner, student = make_user("Owner"), make_user("Student")
        project = make_project(created_by=owner.id)
        task = make_task(project.id, {"text": "Fall"})
        run = make_evaluation_run(project.id, owner.id, status="completed", eval_metadata={})
        for user in (owner, student):
            annotation = make_annotation(project.id, task.id, user.id, result=[])
            _grade(db_conn, run, task.id, annotation_id=annotation.id)

        tasks._notify_batch_grading_received(db_conn, run)

        assert [call["user_ids"] for call in recorded] == [[student.id]]


class TestImmediateTrigger:
    def test_run_with_rows_notifies_the_annotator(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        student = make_user("Student")
        project = make_project()
        task = make_task(project.id, {"text": "Fall"})
        annotation = make_annotation(project.id, task.id, student.id, result=[])
        run = make_evaluation_run(project.id, student.id, model_id="immediate", status="completed")
        _grade(db_conn, run, task.id, annotation_id=annotation.id)

        tasks._notify_immediate_grading_received(
            db_conn, run.id, project.id, task.id, annotation.id
        )

        assert [call["user_ids"] for call in recorded] == [[student.id]]
        assert recorded[0]["type"] == "evaluation_received_immediate"
        assert recorded[0]["data"]["task_id"] == task.id

    def test_run_without_rows_notifies_nobody(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        student = make_user("Student")
        project = make_project()
        task = make_task(project.id, {"text": "Fall"})
        annotation = make_annotation(project.id, task.id, student.id, result=[])
        run = make_evaluation_run(project.id, student.id, model_id="immediate", status="completed")

        tasks._notify_immediate_grading_received(
            db_conn, run.id, project.id, task.id, annotation.id
        )

        assert recorded == []
