"""Grading notifications to the annotator, against the real DB.

- ``create_notification`` with stored preference rows and the per-type
  defaults: the human grading type is in-app and email by default, the AI
  grading types are opt-in, and an email-only choice queues the email without
  an in-app row (for every type).
- ``notify_evaluation_received``: recipients from real annotations, the
  notification data, and one pending notice per project per type until read.
- The preferences API round trip for the three grading types.

Celery is replaced by a mock that records the queued email payloads.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

import mailer.notification_service as ns_module
from models import Notification, NotificationType, UserNotificationPreference
from project_models import Annotation, Project, Task

pytestmark = pytest.mark.integration

HUMAN = NotificationType.EVALUATION_RECEIVED_HUMAN
IMMEDIATE = NotificationType.EVALUATION_RECEIVED_IMMEDIATE
BATCH = NotificationType.EVALUATION_RECEIVED_BATCH


def _uid():
    return str(uuid.uuid4())


@pytest.fixture
def celery():
    app = MagicMock()
    with patch.object(ns_module, "EMAIL_SERVICE_AVAILABLE", True), patch.object(
        ns_module, "get_celery_app", return_value=app
    ):
        yield app


def _queued(celery):
    return [item for call in celery.send_task.call_args_list for item in call.kwargs["args"][0]]


def _prefer(db, user, notification_type, *, in_app, email):
    db.add(
        UserNotificationPreference(
            id=_uid(),
            user_id=user.id,
            notification_type=notification_type.value,
            in_app_enabled=in_app,
            email_enabled=email,
        )
    )
    db.commit()


def _rows(db, user, notification_type):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.type == notification_type)
        .all()
    )


def _create(db, user, notification_type):
    return ns_module.NotificationService.create_notification(
        db=db,
        user_ids=[user.id],
        notification_type=notification_type,
        title="T",
        message="M",
        data={"project_id": "p1"},
    )


@pytest.mark.integration
class TestChannelsWithStoredPreferences:
    def test_human_grading_without_a_row_is_shown_and_queued(self, test_db, test_users, celery):
        annotator = test_users[2]

        created = _create(test_db, annotator, HUMAN)

        assert [n.user_id for n in _rows(test_db, annotator, HUMAN)] == [annotator.id]
        assert [(p["user_id"], p["id"]) for p in _queued(celery)] == [(annotator.id, created[0].id)]
        assert ns_module.NotificationService._user_wants_channel(
            test_db, annotator.id, HUMAN, "email"
        )

    @pytest.mark.parametrize("notification_type", [IMMEDIATE, BATCH])
    def test_ai_grading_without_a_row_stays_silent(
        self, test_db, test_users, celery, notification_type
    ):
        annotator = test_users[2]

        assert _create(test_db, annotator, notification_type) == []

        assert _rows(test_db, annotator, notification_type) == []
        celery.send_task.assert_not_called()

    def test_email_only_ai_grading_is_queued_without_a_row(self, test_db, test_users, celery):
        annotator = test_users[2]
        _prefer(test_db, annotator, IMMEDIATE, in_app=False, email=True)

        assert _create(test_db, annotator, IMMEDIATE) == []

        assert _rows(test_db, annotator, IMMEDIATE) == []
        assert _queued(celery) == [
            {
                "id": None,
                "user_id": annotator.id,
                "type": IMMEDIATE.value,
                "title": "T",
                "message": "M",
                "data": {"project_id": "p1"},
            }
        ]

    def test_email_only_works_for_older_types_too(self, test_db, test_users, celery):
        grader = test_users[1]
        _prefer(test_db, grader, NotificationType.KORREKTUR_ASSIGNED, in_app=False, email=True)

        _create(test_db, grader, NotificationType.KORREKTUR_ASSIGNED)

        assert _rows(test_db, grader, NotificationType.KORREKTUR_ASSIGNED) == []
        assert [p["user_id"] for p in _queued(celery)] == [grader.id]

    def test_stored_row_overrides_the_human_email_default(self, test_db, test_users, celery):
        annotator = test_users[2]
        _prefer(test_db, annotator, HUMAN, in_app=True, email=False)

        _create(test_db, annotator, HUMAN)

        assert len(_rows(test_db, annotator, HUMAN)) == 1
        assert not ns_module.NotificationService._user_wants_channel(
            test_db, annotator.id, HUMAN, "email"
        )


def _exam(db, creator, title="Klausur Zivilrecht", kind="exam"):
    project = Project(
        id=_uid(),
        title=title,
        created_by=creator.id,
        kind=kind,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    task = Task(id=_uid(), project_id=project.id, data={"text": "Fall"}, inner_id=1,
                created_by=creator.id)
    db.add(task)
    db.commit()
    return project, task


def _annotate(db, project, task, user):
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=[],
        was_cancelled=False,
    )
    db.add(annotation)
    db.commit()
    return annotation


def _notify(db, project, source="human", recipients=(), exclude=(), task_id=None):
    return ns_module.notify_evaluation_received(
        db,
        source=source,
        project_id=project.id,
        recipient_ids=list(recipients),
        exclude_user_ids=list(exclude),
        task_id=task_id,
        evaluation_id="run-1",
    )


@pytest.mark.integration
class TestNotifyEvaluationReceived:
    def test_annotators_of_real_annotations_are_notified_with_project_data(
        self, test_db, test_users, celery
    ):
        admin, grader, annotator = test_users[0], test_users[1], test_users[2]
        project, task = _exam(test_db, admin)
        annotations = [_annotate(test_db, project, task, user) for user in (annotator, grader)]

        recipients = ns_module.annotator_ids_for_annotations(
            test_db, [a.id for a in annotations] + ["missing-annotation"]
        )
        assert recipients == sorted([annotator.id, grader.id])

        created = _notify(test_db, project, recipients=recipients, exclude=[grader.id],
                          task_id=task.id)

        assert [n.user_id for n in created] == [annotator.id]
        assert _rows(test_db, grader, HUMAN) == []
        assert created[0].data == {
            "project_id": project.id,
            "project_title": "Klausur Zivilrecht",
            "project_kind": "exam",
            "task_id": task.id,
            "evaluation_id": "run-1",
            "source": "human",
        }

    def test_unknown_annotations_have_no_annotators(self, test_db):
        assert ns_module.annotator_ids_for_annotations(test_db, ["missing-annotation"]) == []

    def test_one_pending_notice_per_project_per_type_until_read(
        self, test_db, test_users, celery
    ):
        admin, annotator = test_users[0], test_users[2]
        project, _ = _exam(test_db, admin)
        other_project, _ = _exam(test_db, admin, title="Klausur Strafrecht")

        assert len(_notify(test_db, project, recipients=[annotator.id])) == 1
        # A second grade on the same project while the first notice is unread.
        assert _notify(test_db, project, recipients=[annotator.id]) == []
        assert len(_rows(test_db, annotator, HUMAN)) == 1

        # Another project is its own notice.
        assert len(_notify(test_db, other_project, recipients=[annotator.id])) == 1

        # Another type on the same project is its own notice.
        _prefer(test_db, annotator, IMMEDIATE, in_app=True, email=False)
        assert len(_notify(test_db, project, source="immediate", recipients=[annotator.id])) == 1

        # Once read, the next grade notifies again.
        first = (
            test_db.query(Notification)
            .filter(Notification.user_id == annotator.id, Notification.type == HUMAN)
            .order_by(Notification.created_at)
            .first()
        )
        first.is_read = True
        test_db.commit()
        assert len(_notify(test_db, project, recipients=[annotator.id])) == 1
        assert len(_rows(test_db, annotator, HUMAN)) == 3


@pytest.mark.integration
class TestGradingPreferencesApi:
    def _get(self, client, headers):
        resp = client.get("/api/notifications/preferences", headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()["preferences"]

    def test_defaults_per_grading_type(self, client, test_users, auth_headers):
        prefs = self._get(client, auth_headers["annotator"])

        assert prefs[HUMAN.value] == {"enabled": True, "in_app": True, "email": True}
        assert prefs[IMMEDIATE.value] == {"enabled": False, "in_app": False, "email": False}
        assert prefs[BATCH.value] == {"enabled": False, "in_app": False, "email": False}

    def test_email_only_choice_persists(self, client, test_db, test_users, auth_headers):
        annotator = test_users[2]
        resp = client.post(
            "/api/notifications/preferences",
            json={
                "preferences": {
                    IMMEDIATE.value: {"enabled": True, "in_app": False, "email": True}
                }
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200, resp.text

        assert self._get(client, auth_headers["annotator"])[IMMEDIATE.value] == {
            "enabled": True,
            "in_app": False,
            "email": True,
        }
        stored = (
            test_db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.user_id == annotator.id,
                UserNotificationPreference.notification_type == IMMEDIATE.value,
            )
            .one()
        )
        assert (stored.in_app_enabled, stored.email_enabled) == (False, True)

    def test_stored_row_overrides_the_human_default(
        self, client, test_db, test_users, auth_headers
    ):
        _prefer(test_db, test_users[2], HUMAN, in_app=True, email=False)

        assert self._get(client, auth_headers["annotator"])[HUMAN.value] == {
            "enabled": True,
            "in_app": True,
            "email": False,
        }
