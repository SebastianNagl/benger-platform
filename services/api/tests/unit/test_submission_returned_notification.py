"""The author's notice when a project editor returns a submission (core 2.80).

Covers the channel defaults, the template mapping, the link helpers (the
notice opens the submission's page like a grading notice), the input
handling of ``notify_submission_returned`` and the rendered email. The real
row is written in tests/integration/test_annotation_withdrawal.py.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import mailer.notification_service as ns_module
from email_templates.template_map import template_for
from mailer.branding import resolve_email_brand
from mailer.notification_links import (
    SUBMISSION_NOTICE_TYPES,
    evaluation_received_path,
    is_evaluation_received_type,
    is_submission_notice_type,
)
from models import NotificationType

TYPE = NotificationType.SUBMISSION_RETURNED


def _db_with_project(project):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


class TestTypeAndDefaults:
    def test_value(self):
        assert TYPE.value == "submission_returned"

    def test_in_app_and_email_by_default(self):
        assert ns_module.default_channels(TYPE) == {"in_app": True, "email": True}
        assert ns_module.default_channels(TYPE.value) == {"in_app": True, "email": True}

    def test_own_template(self):
        assert template_for(TYPE) == "submission_returned.html"
        assert template_for(TYPE.value) == "submission_returned.html"


class TestLinks:
    def test_is_a_submission_notice_but_not_a_grading(self):
        assert is_submission_notice_type(TYPE)
        assert is_submission_notice_type("submission_returned")
        assert not is_evaluation_received_type(TYPE)

    def test_the_grading_notices_are_submission_notices(self):
        for value in (
            "evaluation_received_human",
            "evaluation_received_immediate",
            "evaluation_received_batch",
        ):
            assert is_submission_notice_type(value)
        assert SUBMISSION_NOTICE_TYPES >= {"submission_returned"}

    def test_other_types_are_not(self):
        assert not is_submission_notice_type("project_created")
        assert not is_submission_notice_type(None)

    def test_opens_the_submission_page(self):
        data = {"project_id": "p1", "project_kind": "exam"}
        assert evaluation_received_path(data, True) == "/student/exams/p1"
        assert evaluation_received_path(data, False) == "/projects/p1/my-tasks"


class TestNotifySubmissionReturned:
    def test_builds_the_notice(self):
        db = _db_with_project(SimpleNamespace(title="Klausur 1", kind="exam"))
        with patch.object(
            ns_module.NotificationService, "create_notification", return_value=["n"]
        ) as create:
            out = ns_module.notify_submission_returned(
                db,
                project_id="p1",
                task_id="t1",
                annotation_id="a1",
                author_id="author",
                actor_id="editor",
                reason="Wrong file",
            )
        assert out == ["n"]
        kwargs = create.call_args.kwargs
        assert kwargs["user_ids"] == ["author"]
        assert kwargs["notification_type"] == TYPE
        assert kwargs["title"] == "Submission returned"
        assert "Klausur 1" in kwargs["message"]
        assert "Wrong file" in kwargs["message"]
        assert kwargs["data"] == {
            "project_id": "p1",
            "project_title": "Klausur 1",
            "project_kind": "exam",
            "task_id": "t1",
            "annotation_id": "a1",
            "reason": "Wrong file",
        }

    def test_an_editor_returning_their_own_submission_is_not_notified(self):
        db = _db_with_project(SimpleNamespace(title="P", kind=None))
        with patch.object(ns_module.NotificationService, "create_notification") as create:
            out = ns_module.notify_submission_returned(
                db,
                project_id="p1",
                task_id=None,
                annotation_id="a1",
                author_id="same",
                actor_id="same",
                reason="r",
            )
        assert out == []
        create.assert_not_called()

    def test_never_raises(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db gone")
        out = ns_module.notify_submission_returned(
            db,
            project_id="p1",
            task_id=None,
            annotation_id="a1",
            author_id="author",
            actor_id="editor",
            reason="r",
        )
        assert out == []
        db.rollback.assert_called_once()


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


class TestEmail:
    @pytest.mark.parametrize("host", ["vertretbar.net", None])
    def test_renders_reason_link_and_voice(self, email_svc, host):
        brand = resolve_email_brand(host)
        action_url = f"{brand.frontend_url}/student/exams/p1"
        notification = SimpleNamespace(
            type="submission_returned",
            title="Submission returned",
            message="m",
            data={
                "project_id": "p1",
                "project_title": "Klausur 1",
                "project_kind": "exam",
                "reason": "Bitte <b>vollständig</b> abgeben",
            },
        )
        ok = asyncio.run(
            email_svc.send_notification_email(
                "user@example.com",
                notification,
                context={"action_url": action_url},
                brand=brand,
            )
        )
        assert ok is True
        kwargs = email_svc.mail_client.send_message.call_args.kwargs
        assert kwargs["subject"] == "Abgabe zurückgegeben: Klausur 1"
        html = kwargs["html_body"]
        assert f'href="{action_url}"' in html
        assert "Abgabe ansehen" in html
        # The reason is the editor's text: escaped, never markup.
        assert "Grund: Bitte &lt;b&gt;vollständig&lt;/b&gt; abgeben" in html
        assert "Du kannst E-Mails" in html
        assert 'lang="de"' in html
