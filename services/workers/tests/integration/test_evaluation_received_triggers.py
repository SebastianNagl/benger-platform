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


def _grade(db, run, task_id, annotation_id=None, generation_id=None, metrics=None):
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
        metrics=metrics or {"exact_match": 1.0},
        passed=True,
    )
    db.add(row)
    db.commit()
    return row


def _feedback(released, released_by=None):
    """A score-less feedback judge row (core 2.41), held back or released
    (``released_by`` is "judge" or "teacher", absent on legacy rows)."""
    details = {"feedback_only": True}
    if released:
        details["review"] = {"status": "released"}
        if released_by:
            details["review"]["released_by"] = released_by
    return {
        "llm_judge_feedback": {
            "value": 0.6 if released else None,
            "method": "llm_judge_feedback",
            "details": details,
            "error": None,
        }
    }


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


class TestBatchFeedbackDrafts:
    def test_score_less_feedback_rows_notify_nobody(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        """A feedback-only judge row (core 2.41) is the teacher's draft: the
        student hears about it when it is released, not when the run ends."""
        starter = make_user("Teacher")
        draft_owner = make_user("Draft")
        graded = make_user("Graded")
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Cas"})
        run = make_evaluation_run(project.id, starter.id, status="completed")
        feedback = {
            "llm_judge_feedback": {
                "value": None,
                "method": "llm_judge_feedback",
                "details": {"feedback_only": True},
                "error": None,
            }
        }
        draft_ann = make_annotation(project.id, task.id, draft_owner.id, result=[])
        _grade(db_conn, run, task.id, annotation_id=draft_ann.id, metrics=feedback)
        graded_ann = make_annotation(project.id, task.id, graded.id, result=[])
        _grade(db_conn, run, task.id, annotation_id=graded_ann.id)

        tasks._notify_batch_grading_received(db_conn, run)

        assert [call["user_ids"] for call in recorded] == [[graded.id]]

    def test_a_run_of_only_feedback_stays_unmarked(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        starter = make_user("Teacher")
        student = make_user("Student")
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Cas"})
        run = make_evaluation_run(project.id, starter.id, status="completed")
        annotation = make_annotation(project.id, task.id, student.id, result=[])
        _grade(
            db_conn, run, task.id, annotation_id=annotation.id,
            metrics={"llm_judge_feedback": {"value": None, "details": {"feedback_only": True}}},
        )

        tasks._notify_batch_grading_received(db_conn, run)

        assert recorded == []
        assert not (_stored_metadata(db_conn, run.id) or {}).get("annotators_notified")

    def test_only_a_row_the_judge_released_notifies(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        """A row the judge released at write time is visible to the student,
        so the batch notice goes out (opt-in). A draft, a row a teacher
        released (the overlay's release announced it) and a legacy released
        row without ``released_by`` tell nobody here."""
        starter = make_user("Teacher")
        owners = {
            "judge": (make_user("Judge"), _feedback(True, "judge")),
            "teacher": (make_user("TeacherReleased"), _feedback(True, "teacher")),
            "legacy": (make_user("Legacy"), _feedback(True)),
            "draft": (make_user("Draft"), _feedback(False)),
        }
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Cas"})
        run = make_evaluation_run(project.id, starter.id, status="completed")
        for owner, metrics in owners.values():
            annotation = make_annotation(project.id, task.id, owner.id, result=[])
            _grade(db_conn, run, task.id, annotation_id=annotation.id, metrics=metrics)

        tasks._notify_batch_grading_received(db_conn, run)

        assert [call["user_ids"] for call in recorded] == [[owners["judge"][0].id]]

    def test_regraded_score_drafts_notify_nobody(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        """A re-grade writes every answer's new row as a draft (core 2.83),
        for score judges too: in a metric blob or the flat ``<metric>_details``
        sibling. A row with only a fingerprint, or an empty review, is a
        plain grading and still notifies."""
        draft = {"status": "draft", "reason": "regrade"}
        starter = make_user("Teacher")
        owners = {
            "unified": (make_user("Unified"), {"llm_judge_rubric": {
                "value": 0.6, "details": {"review": draft}, "error": None}}),
            "flat": (make_user("Flat"), {"llm_judge_custom": 0.6,
                                         "llm_judge_custom_details": {"review": draft}}),
            "stamped": (make_user("Stamped"), {"llm_judge_custom": 0.6,
                                               "llm_judge_custom_details": {
                                                   "scheme_fingerprint": "x", "review": {}}}),
        }
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Cas"})
        run = make_evaluation_run(project.id, starter.id, status="completed")
        for owner, metrics in owners.values():
            annotation = make_annotation(project.id, task.id, owner.id, result=[])
            _grade(db_conn, run, task.id, annotation_id=annotation.id, metrics=metrics)

        tasks._notify_batch_grading_received(db_conn, run)

        assert [call["user_ids"] for call in recorded] == [[owners["stamped"][0].id]]

    def test_a_run_resumed_after_a_teacher_release_notifies_nobody_again(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        """Pause, teacher release, resume: the paused run wrote drafts and was
        never finalized, the teacher released some of them (announced by the
        overlay), and the resumed run's finalize must not announce them a
        second time."""
        starter = make_user("Teacher")
        released_student = make_user("Released")
        draft_student = make_user("Draft")
        project = make_project(created_by=starter.id)
        task = make_task(project.id, {"text": "Cas"})
        run = make_evaluation_run(project.id, starter.id, status="paused")
        rows = {}
        for student in (released_student, draft_student):
            annotation = make_annotation(project.id, task.id, student.id, result=[])
            rows[student.id] = _grade(
                db_conn, run, task.id, annotation_id=annotation.id, metrics=_feedback(False)
            )
        assert not (_stored_metadata(db_conn, run.id) or {}).get("annotators_notified")

        released = rows[released_student.id]
        released.metrics = _feedback(True, "teacher")
        run.status = "completed"
        db_conn.commit()

        tasks._notify_batch_grading_received(db_conn, run)

        assert recorded == []
        assert not (_stored_metadata(db_conn, run.id) or {}).get("annotators_notified")


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

    def test_a_feedback_draft_notifies_nobody(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        """A feedback judge that holds its result back for the teacher wrote a
        row, but the student cannot see anything yet: no "AI grading ready"
        notice (the teacher's release notifies later)."""
        student = make_user("Student")
        project = make_project()
        task = make_task(project.id, {"text": "Cas"})
        annotation = make_annotation(project.id, task.id, student.id, result=[])
        run = make_evaluation_run(project.id, student.id, model_id="immediate", status="completed")
        _grade(db_conn, run, task.id, annotation_id=annotation.id, metrics=_feedback(False))

        tasks._notify_immediate_grading_received(
            db_conn, run.id, project.id, task.id, annotation.id
        )

        assert recorded == []

    def test_a_feedback_released_on_writing_notifies(
        self, db_conn, recorded, make_user, make_project, make_task,
        make_annotation, make_evaluation_run,
    ):
        student = make_user("Student")
        project = make_project()
        task = make_task(project.id, {"text": "Cas"})
        annotation = make_annotation(project.id, task.id, student.id, result=[])
        run = make_evaluation_run(project.id, student.id, model_id="immediate", status="completed")
        _grade(
            db_conn, run, task.id, annotation_id=annotation.id,
            metrics=_feedback(True, "judge"),
        )

        tasks._notify_immediate_grading_received(
            db_conn, run.id, project.id, task.id, annotation.id
        )

        assert [call["user_ids"] for call in recorded] == [[student.id]]
        assert recorded[0]["type"] == "evaluation_received_immediate"


class TestImmediateStamp:
    def test_immediate_rows_record_the_scheme_of_their_config(self):
        """The immediate lane stamps its rows once every config job wrote
        them (``tasks._stamp_immediate_grading_basis``)."""
        from types import SimpleNamespace

        from grading_basis import metric_details, scheme_fingerprint

        config = {"id": "c1", "metric": "llm_judge_custom",
                  "metric_parameters": {"custom_prompt_template": "t"}}
        judged = SimpleNamespace(evaluation_config_id="c1", metrics={"llm_judge_custom": 0.5})
        other = SimpleNamespace(evaluation_config_id="gone", metrics={"bleu": {"value": 0.2}})
        untouched = other.metrics

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("sqlalchemy.orm.attributes.flag_modified", lambda *a, **k: None)
            tasks._stamp_immediate_grading_basis([judged, other], [config])

        assert metric_details(judged.metrics, "llm_judge_custom") == {
            "scheme_fingerprint": scheme_fingerprint(config)
        }
        assert "review" not in judged.metrics["llm_judge_custom_details"]
        assert other.metrics is untouched
