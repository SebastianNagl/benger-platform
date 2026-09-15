"""Grading notifications to the annotator (the evaluation_received_* types).

Covers the per-type channel defaults, email-only dispatch in
``create_notification``, the input handling of ``notify_evaluation_received``,
the template mapping, the link helper and the rendering of the grading email.
The preference rows, the recipient query and the unread dedupe run against the
real DB in tests/integration/test_evaluation_received_notifications.py.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import mailer.notification_service as ns_module
from email_templates.template_map import template_for
from mailer.branding import resolve_email_brand
from mailer.notification_links import (
    evaluation_received_path,
    is_evaluation_received_type,
)
from models import NotificationType

GRADING_TYPES = (
    "evaluation_received_human",
    "evaluation_received_immediate",
    "evaluation_received_batch",
)


# ---------------------------------------------------------------------------
# Channel defaults
# ---------------------------------------------------------------------------


class TestDefaultChannels:
    def test_human_grading_defaults_to_in_app_and_email(self):
        assert ns_module.default_channels(NotificationType.EVALUATION_RECEIVED_HUMAN) == {
            "in_app": True,
            "email": True,
        }

    @pytest.mark.parametrize(
        "type_value", ["evaluation_received_immediate", "evaluation_received_batch"]
    )
    def test_ai_gradings_are_opt_in_on_both_channels(self, type_value):
        assert ns_module.default_channels(type_value) == {"in_app": False, "email": False}

    def test_other_types_keep_the_general_rule(self):
        assert ns_module.default_channels("project_created") == {
            "in_app": True,
            "email": False,
        }

    def test_returns_a_copy(self):
        channels = ns_module.default_channels("evaluation_received_human")
        channels["email"] = False
        assert ns_module.default_channels("evaluation_received_human")["email"] is True


# ---------------------------------------------------------------------------
# create_notification: email without the in-app row
# ---------------------------------------------------------------------------


def _channel_prefs(mapping):
    def fake(db, user_id, notification_type, channel):
        return mapping.get((user_id, channel), False)

    return fake


class TestEmailOnlyDispatch:
    def _create(self, prefs, celery):
        db = MagicMock()
        with patch.object(
            ns_module.NotificationService,
            "_user_wants_channel",
            side_effect=_channel_prefs(prefs),
        ), patch.object(ns_module, "EMAIL_SERVICE_AVAILABLE", True), patch.object(
            ns_module, "get_celery_app", return_value=celery
        ):
            created = ns_module.NotificationService.create_notification(
                db=db,
                user_ids=["row", "mail", "none"],
                notification_type="evaluation_received_immediate",
                title="T",
                message="M",
                data={"project_id": "p1"},
            )
        return db, created

    def test_email_only_user_gets_email_without_row(self):
        celery = MagicMock()
        db, created = self._create(
            {
                ("row", "in_app"): True,
                ("mail", "in_app"): False,
                ("mail", "email"): True,
            },
            celery,
        )
        assert [n.user_id for n in created] == ["row"]
        assert db.add.call_count == 1

        celery.send_task.assert_called_once()
        assert celery.send_task.call_args.args[0] == "emails.send_notification_batch"
        payload = celery.send_task.call_args.kwargs["args"][0]
        by_user = {p["user_id"]: p for p in payload}
        assert set(by_user) == {"row", "mail"}
        assert by_user["mail"] == {
            "id": None,
            "user_id": "mail",
            "type": "evaluation_received_immediate",
            "title": "T",
            "message": "M",
            "data": {"project_id": "p1"},
        }

    def test_nobody_opted_in_enqueues_nothing(self):
        celery = MagicMock()
        db, created = self._create({}, celery)
        assert created == []
        db.add.assert_not_called()
        celery.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# Producer helpers
# ---------------------------------------------------------------------------


def _db_with_project(project):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


class TestNotifyEvaluationReceived:
    def test_builds_data_and_filters_recipients(self):
        db = _db_with_project(SimpleNamespace(title="Klausur 1", kind="exam"))
        with patch.object(
            ns_module.NotificationService, "create_notification", return_value=["n"]
        ) as create:
            out = ns_module.notify_evaluation_received(
                db,
                source="human",
                project_id="p1",
                recipient_ids=["u1", None, "u2", "u1", "grader"],
                exclude_user_ids=["grader", None],
                task_id="t1",
                evaluation_id="e1",
            )
        assert out == ["n"]
        kwargs = create.call_args.kwargs
        assert kwargs["user_ids"] == ["u1", "u2"]
        assert kwargs["notification_type"] == NotificationType.EVALUATION_RECEIVED_HUMAN
        assert kwargs["title"] == "New grading"
        assert "Klausur 1" in kwargs["message"]
        assert kwargs["data"] == {
            "project_id": "p1",
            "project_title": "Klausur 1",
            "project_kind": "exam",
            "task_id": "t1",
            "evaluation_id": "e1",
            "source": "human",
        }

    @pytest.mark.parametrize(
        "source,expected",
        [
            ("immediate", NotificationType.EVALUATION_RECEIVED_IMMEDIATE),
            ("batch", NotificationType.EVALUATION_RECEIVED_BATCH),
        ],
    )
    def test_source_selects_the_type(self, source, expected):
        db = _db_with_project(SimpleNamespace(title="P", kind=None))
        with patch.object(
            ns_module.NotificationService, "create_notification", return_value=[]
        ) as create:
            ns_module.notify_evaluation_received(
                db, source=source, project_id="p1", recipient_ids=["u1"]
            )
        assert create.call_args.kwargs["notification_type"] == expected
        assert create.call_args.kwargs["data"]["project_kind"] is None

    def test_unknown_source_notifies_nobody(self):
        db = MagicMock()
        with patch.object(ns_module.NotificationService, "create_notification") as create:
            out = ns_module.notify_evaluation_received(
                db, source="telepathy", project_id="p1", recipient_ids=["u1"]
            )
        assert out == []
        create.assert_not_called()

    def test_only_excluded_recipients_skips_everything(self):
        db = MagicMock()
        with patch.object(ns_module.NotificationService, "create_notification") as create:
            out = ns_module.notify_evaluation_received(
                db,
                source="human",
                project_id="p1",
                recipient_ids=["grader"],
                exclude_user_ids=["grader"],
            )
        assert out == []
        create.assert_not_called()
        db.query.assert_not_called()

    def test_missing_project_still_notifies(self):
        db = _db_with_project(None)
        with patch.object(
            ns_module.NotificationService, "create_notification", return_value=[]
        ) as create:
            ns_module.notify_evaluation_received(
                db, source="human", project_id="gone", recipient_ids=["u1"]
            )
        data = create.call_args.kwargs["data"]
        assert data["project_title"] == ""
        assert data["project_kind"] is None

    def test_never_raises(self):
        db = _db_with_project(SimpleNamespace(title="P", kind="exam"))
        with patch.object(
            ns_module.NotificationService,
            "create_notification",
            side_effect=RuntimeError("boom"),
        ):
            out = ns_module.notify_evaluation_received(
                db, source="human", project_id="p1", recipient_ids=["u1"]
            )
        assert out == []
        db.rollback.assert_called_once()


class TestAnnotatorIdsForAnnotations:
    def test_empty_input_skips_the_query(self):
        db = MagicMock()
        assert ns_module.annotator_ids_for_annotations(db, [None, ""]) == []
        assert ns_module.annotator_ids_for_annotations(db, None) == []
        db.query.assert_not_called()


# ---------------------------------------------------------------------------
# Template mapping and links
# ---------------------------------------------------------------------------


class TestTemplateMapping:
    @pytest.mark.parametrize("type_value", GRADING_TYPES)
    def test_grading_types_use_the_grading_template(self, type_value):
        assert template_for(type_value) == "evaluation_received.html"
        assert template_for(NotificationType(type_value)) == "evaluation_received.html"


class TestEvaluationReceivedPath:
    def test_student_exam_opens_the_student_exam_page(self):
        data = {"project_id": "p1", "project_kind": "exam"}
        assert evaluation_received_path(data, student_surface=True) == "/student/exams/p1"

    def test_student_on_a_non_exam_project_opens_my_tasks(self):
        data = {"project_id": "p1", "project_kind": None}
        assert evaluation_received_path(data, student_surface=True) == "/projects/p1/my-tasks"

    def test_expert_opens_my_tasks_even_for_an_exam(self):
        data = {"project_id": "p1", "project_kind": "exam"}
        assert evaluation_received_path(data, student_surface=False) == "/projects/p1/my-tasks"

    def test_no_project_means_no_link(self):
        assert evaluation_received_path({}, student_surface=True) is None
        assert evaluation_received_path(None, student_surface=False) is None

    def test_type_check_accepts_enum_and_value(self):
        assert is_evaluation_received_type(NotificationType.EVALUATION_RECEIVED_BATCH)
        assert is_evaluation_received_type("evaluation_received_human")
        assert not is_evaluation_received_type("evaluation_completed")
        assert not is_evaluation_received_type(None)


# ---------------------------------------------------------------------------
# Branded notification email
# ---------------------------------------------------------------------------


@pytest.fixture
def email_svc():
    with patch("mailer.email_service.SendGridClient") as mock_sg:
        with patch("database.SessionLocal"):
            from email_service import EmailService

            svc = EmailService()
            svc.mail_client = mock_sg.return_value
            svc.mail_client.send_message.return_value = {"status": "success"}
            svc.mail_enabled = True
            return svc


def _grading_notification(source="human", project_title="Klausur 1"):
    return SimpleNamespace(
        type=f"evaluation_received_{source}",
        title="New grading",
        message="m",
        data={
            "project_id": "p1",
            "project_title": project_title,
            "project_kind": "exam",
            "source": source,
        },
    )


def _send(email_svc, notification, brand=None, action_url=None):
    context = {"action_url": action_url} if action_url else None
    ok = asyncio.run(
        email_svc.send_notification_email(
            "user@example.com", notification, context=context, brand=brand
        )
    )
    assert ok is True
    return email_svc.mail_client.send_message.call_args.kwargs


# (subject title, source label, button) per source; German for both brands.
WORDING = {
    "human": ("Neue Korrektur", "Menschliche Korrektur", "Korrektur ansehen"),
    "immediate": ("KI-Korrektur fertig", "KI-Korrektur", "Korrektur ansehen"),
    "batch": ("Neue Evaluierung", "Evaluierungslauf", "Ergebnisse ansehen"),
}
# Vertretbar says "du", BenGER "Sie": (expected footer, the other brand's footer).
VOICE = {
    "vertretbar.net": ("Du kannst E-Mails", "Sie können E-Mails"),
    None: ("Sie können E-Mails", "Du kannst E-Mails"),
}


class TestGradingEmail:
    @pytest.mark.parametrize("host", ["vertretbar.net", None])
    @pytest.mark.parametrize("source", ["human", "immediate", "batch"])
    def test_renders_german_wording_voice_and_link(self, email_svc, host, source):
        brand = resolve_email_brand(host)
        action_url = f"{brand.frontend_url}/student/exams/p1"
        kwargs = _send(email_svc, _grading_notification(source), brand, action_url)

        title, label, button = WORDING[source]
        assert kwargs["subject"] == f"{title}: Klausur 1"
        html = kwargs["html_body"]
        assert f"Quelle: {label}" in html
        assert f'href="{action_url}"' in html
        assert button in html
        own_voice, other_voice = VOICE[host]
        assert own_voice in html
        assert other_voice not in html
        assert f"{brand.frontend_url}/settings/notifications" in html
        assert 'lang="de"' in html

    def test_vertretbar_brand_overrides_the_sender(self, email_svc):
        brand = resolve_email_brand("vertretbar.net")
        kwargs = _send(email_svc, _grading_notification(), brand)
        assert kwargs["from_address"] == brand.from_address
        assert kwargs["from_name"] == brand.from_name

    def test_default_brand_keeps_the_mailer_sender(self, email_svc):
        kwargs = _send(email_svc, _grading_notification())
        assert "from_address" not in kwargs
        assert "from_name" not in kwargs
        assert "Sie können E-Mails" in kwargs["html_body"]

    def test_without_a_link_there_is_no_button(self, email_svc):
        html = _send(email_svc, _grading_notification("batch"))["html_body"]
        assert "Ergebnisse ansehen" not in html
        assert "<a href=\"None\"" not in html

    def test_without_a_project_title_the_subject_has_no_colon(self, email_svc):
        kwargs = _send(email_svc, _grading_notification("immediate", project_title=""))
        assert kwargs["subject"] == "KI-Korrektur fertig"
        assert "Projekt:" not in kwargs["html_body"]

    def test_unknown_source_reads_as_a_human_grading(self, email_svc):
        notification = _grading_notification()
        notification.data["source"] = "oracle"
        kwargs = _send(email_svc, notification)
        assert kwargs["subject"] == "Neue Korrektur: Klausur 1"
        assert "Quelle: Menschliche Korrektur" in kwargs["html_body"]

    def test_existing_types_send_exactly_as_before(self, email_svc):
        notification = SimpleNamespace(
            type=NotificationType.KORREKTUR_ASSIGNED,
            title="Korrektur zugewiesen",
            message="m",
            data={"project_title": "P"},
        )
        asyncio.run(email_svc.send_notification_email("grader@example.com", notification))
        email_svc.mail_client.send_message.assert_called_once()
        assert set(email_svc.mail_client.send_message.call_args.kwargs) == {
            "to",
            "subject",
            "html_body",
        }
