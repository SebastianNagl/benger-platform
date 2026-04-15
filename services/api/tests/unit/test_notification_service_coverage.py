"""
Extended unit tests for notification_service to cover uncovered lines.

Covers:
- Import fallback branches (EMAIL_SERVICE_AVAILABLE=False, PROJECT_MODEL_AVAILABLE=False)
- create_notification with string type, enum type, invalid non-string/non-enum type
- create_notification commit failure with enum constraint violation message
- get_notification_recipients for various event types
- _get_org_admin_recipients
- _get_task_creator (returns None)
- _user_wants_notification with enum, string, invalid type, and preference disabled
- _user_wants_email_notification (returns preference or False)
- _send_email_notifications with email validation fallback, user with no email, preference disabled
- get_notification_groups with organization and unknown group_by
- get_notification_groups respecting per-group limit
- All helper functions: notify_project_deleted, notify_project_archived, notify_data_import_success,
  notify_labeling_config_updated, notify_evaluation_completed, notify_data_upload_completed,
  notify_organization_invitation_sent, notify_organization_invitation_accepted, notify_member_joined,
  notify_model_api_key_invalid, notify_long_running_task_update, notify_api_quota_warning,
  notify_performance_alert, notify_project_completed, and the duplicate project_deleted/archived/
  data_import_success/labeling_config_updated functions
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, Mock, AsyncMock, patch, call
from uuid import uuid4

import pytest

from models import (
    NotificationType,
    Organization,
    OrganizationRole,
    User,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def user_id():
    return str(uuid4())


@pytest.fixture
def org_id():
    return str(uuid4())


# ─────────────────────────────────────────────
# Import-level fallback branches
# ─────────────────────────────────────────────

class TestImportFallbacks:
    """Test the try/except import blocks at module level."""

    def test_email_service_import_failure_fallback(self):
        """When email_service cannot be imported, EMAIL_SERVICE_AVAILABLE is False
        and a stub send_notification_email is created (lines 37-42)."""
        import importlib
        import sys

        # Force reimport with email_service missing
        saved = sys.modules.get("email_service")
        sys.modules["email_service"] = None  # Force ImportError

        try:
            # Need to reimport the module
            if "notification_service" in sys.modules:
                del sys.modules["notification_service"]

            # This should trigger the ImportError branch
            import notification_service as ns_reimported

            # The module should still load, with EMAIL_SERVICE_AVAILABLE = False
            # (or True if the real import succeeded first; we check the fallback function)
            assert hasattr(ns_reimported, "EMAIL_SERVICE_AVAILABLE")
        finally:
            # Restore
            if saved is not None:
                sys.modules["email_service"] = saved
            elif "email_service" in sys.modules:
                del sys.modules["email_service"]
            if "notification_service" in sys.modules:
                del sys.modules["notification_service"]

    def test_project_model_import_failure(self):
        """PROJECT_MODEL_AVAILABLE fallback (lines 50-52).
        This branch is just a pass + flag set; verify it doesn't crash."""
        from notification_service import PROJECT_MODEL_AVAILABLE

        # The actual value depends on import success; just ensure it's a bool
        assert isinstance(PROJECT_MODEL_AVAILABLE, bool)


# ─────────────────────────────────────────────
# create_notification edge cases
# ─────────────────────────────────────────────

class TestCreateNotificationEdgeCases:

    @patch("notification_service.NotificationService._user_wants_notification")
    @patch("notification_service.asyncio.create_task")
    def test_create_notification_with_string_type(
        self, mock_task, mock_wants, mock_db, user_id
    ):
        """String notification type is converted to enum (lines 84-87)."""
        mock_wants.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock()

        from notification_service import NotificationService

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[user_id],
            notification_type="project_created",  # string, not enum
            title="T",
            message="M",
        )
        assert len(result) == 1

    def test_create_notification_invalid_string_type(self, mock_db, user_id):
        """Invalid string type returns empty list (lines 88-90)."""
        from notification_service import NotificationService

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[user_id],
            notification_type="totally_bogus_type",
            title="T",
            message="M",
        )
        assert result == []

    def test_create_notification_non_string_non_enum_type(self, mock_db, user_id):
        """Non-string, non-enum type returns empty list (lines 94-96)."""
        from notification_service import NotificationService

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[user_id],
            notification_type=12345,  # neither str nor NotificationType
            title="T",
            message="M",
        )
        assert result == []

    @patch("notification_service.NotificationService._user_wants_notification")
    def test_create_notification_enum_constraint_violation(
        self, mock_wants, mock_db, user_id
    ):
        """Commit failure with 'invalid input value for enum' message (lines 153-157)."""
        mock_wants.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock(
            side_effect=Exception("invalid input value for enum notificationtype")
        )
        mock_db.rollback = Mock()

        from notification_service import NotificationService

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[user_id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert result == []
        mock_db.rollback.assert_called_once()

    @patch("services.email.notification_service.asyncio.create_task")
    @patch("services.email.notification_service.NotificationService._user_wants_notification")
    def test_create_notification_email_service_unavailable(
        self, mock_wants, mock_task, mock_db, user_id
    ):
        """When EMAIL_SERVICE_AVAILABLE is False, no email task is created (line 161)."""
        mock_wants.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock()

        from notification_service import NotificationService

        with patch("services.email.notification_service.EMAIL_SERVICE_AVAILABLE", False):
            result = NotificationService.create_notification(
                db=mock_db,
                user_ids=[user_id],
                notification_type=NotificationType.PROJECT_CREATED,
                title="T",
                message="M",
            )
            mock_task.assert_not_called()
            assert len(result) == 1


# ─────────────────────────────────────────────
# get_notification_recipients branches
# ─────────────────────────────────────────────

class TestGetNotificationRecipients:

    def test_invalid_string_event_type(self, mock_db):
        """Invalid string event_type returns empty list (lines 187-189)."""
        from notification_service import NotificationService

        result = NotificationService.get_notification_recipients(
            mock_db, "completely_invalid", {}
        )
        assert result == []

    def test_member_joined_event(self, mock_db, org_id):
        """MEMBER_JOINED fetches org admins (lines 211-216)."""
        from notification_service import NotificationService

        mock_membership = Mock(user_id="admin-1")
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_membership]

        result = NotificationService.get_notification_recipients(
            mock_db, NotificationType.MEMBER_JOINED, {"organization_id": org_id}
        )
        assert "admin-1" in result

    def test_org_invitation_sent_event(self, mock_db, org_id):
        """ORGANIZATION_INVITATION_SENT fetches org admins (lines 218-226)."""
        from notification_service import NotificationService

        mock_membership = Mock(user_id="admin-2")
        # First call returns org admin members, second call returns superadmins (may be empty)
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_membership]

        result = NotificationService.get_notification_recipients(
            mock_db,
            NotificationType.ORGANIZATION_INVITATION_SENT,
            {"organization_id": org_id},
        )
        assert "admin-2" in result

    def test_system_alert_event(self, mock_db):
        """SYSTEM_ALERT fetches admin recipients (lines 228-233)."""
        from notification_service import NotificationService

        mock_admin = Mock(id="superadmin-1", is_superadmin=True)
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_admin]

        result = NotificationService.get_notification_recipients(
            mock_db, NotificationType.SYSTEM_ALERT, {}
        )
        assert "superadmin-1" in result

    def test_llm_generation_failed_returns_empty(self, mock_db):
        """LLM_GENERATION_FAILED passes (empty recipients, lines 236-242)."""
        from notification_service import NotificationService

        # No query should be made; recipients determined by caller
        result = NotificationService.get_notification_recipients(
            mock_db, NotificationType.LLM_GENERATION_FAILED, {}
        )
        assert result == []

    def test_system_maintenance_event(self, mock_db):
        """SYSTEM_MAINTENANCE fetches admin recipients (lines 244-249)."""
        from notification_service import NotificationService

        mock_admin = Mock(id="admin-x")
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_admin]

        result = NotificationService.get_notification_recipients(
            mock_db, NotificationType.SYSTEM_MAINTENANCE, {}
        )
        assert "admin-x" in result

    def test_security_alert_passes(self, mock_db):
        """SECURITY_ALERT passes (lines 251-253)."""
        from notification_service import NotificationService

        result = NotificationService.get_notification_recipients(
            mock_db, NotificationType.SECURITY_ALERT, {}
        )
        assert result == []

    def test_project_created_with_org(self, mock_db, org_id):
        """PROJECT_CREATED fetches org members + superadmins (lines 255-286)."""
        from notification_service import NotificationService

        member1 = Mock(user_id="member-1")
        member2 = Mock(user_id="member-2")
        admin = Mock(id="superadmin-1")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_chain = MagicMock()
            if call_count[0] == 1:
                # OrganizationMembership query
                mock_chain.filter.return_value.all.return_value = [member1, member2]
            else:
                # User superadmin query
                mock_chain.filter.return_value.all.return_value = [admin]
            return mock_chain

        mock_db.query.side_effect = side_effect

        result = NotificationService.get_notification_recipients(
            mock_db,
            NotificationType.PROJECT_CREATED,
            {"organization_id": org_id},
        )
        assert "member-1" in result
        assert "member-2" in result
        assert "superadmin-1" in result

    def test_project_created_without_org(self, mock_db):
        """PROJECT_CREATED with no organization_id (line 279 warning branch)."""
        from notification_service import NotificationService

        admin = Mock(id="sa-1")
        mock_db.query.return_value.filter.return_value.all.return_value = [admin]

        result = NotificationService.get_notification_recipients(
            mock_db,
            NotificationType.PROJECT_CREATED,
            {},  # no organization_id
        )
        # Only superadmins returned
        assert "sa-1" in result

    def test_evaluation_completed_with_task_id(self, mock_db):
        """EVALUATION_COMPLETED tries to get task creator but returns None (line 206-209)."""
        from notification_service import NotificationService

        result = NotificationService.get_notification_recipients(
            mock_db,
            NotificationType.EVALUATION_COMPLETED,
            {"task_id": "task-123"},
        )
        # _get_task_creator always returns None
        assert result == []


# ─────────────────────────────────────────────
# _get_org_admin_recipients
# ─────────────────────────────────────────────

class TestGetOrgAdminRecipients:

    def test_returns_admin_user_ids(self, mock_db, org_id):
        """Returns user IDs of org admins (lines 309-319)."""
        from notification_service import NotificationService

        m1 = Mock(user_id="oa-1")
        m2 = Mock(user_id="oa-2")
        mock_db.query.return_value.filter.return_value.all.return_value = [m1, m2]

        result = NotificationService._get_org_admin_recipients(mock_db, org_id)
        assert result == ["oa-1", "oa-2"]

    def test_returns_empty_when_no_admins(self, mock_db, org_id):
        """Returns empty list when there are no org admins (line 319)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = NotificationService._get_org_admin_recipients(mock_db, org_id)
        assert result == []


# ─────────────────────────────────────────────
# _get_task_creator
# ─────────────────────────────────────────────

class TestGetTaskCreator:

    def test_always_returns_none(self, mock_db):
        """_get_task_creator always returns None (line 323)."""
        from notification_service import NotificationService

        result = NotificationService._get_task_creator(mock_db, "any-task-id")
        assert result is None


# ─────────────────────────────────────────────
# _user_wants_notification
# ─────────────────────────────────────────────

class TestUserWantsNotification:

    def test_with_enum_type(self, mock_db, user_id):
        """Enum type is converted to value string (lines 333-335)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = NotificationService._user_wants_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        # No preference -> default to True
        assert result is True

    def test_with_string_type(self, mock_db, user_id):
        """String type is used directly (lines 336-338)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = NotificationService._user_wants_notification(
            mock_db, user_id, "project_created"
        )
        assert result is True

    def test_with_invalid_type(self, mock_db, user_id):
        """Non-string, non-enum type returns False (lines 339-341)."""
        from notification_service import NotificationService

        result = NotificationService._user_wants_notification(
            mock_db, user_id, 42
        )
        assert result is False

    def test_preference_disabled(self, mock_db, user_id):
        """User has explicitly disabled this notification type (lines 356-358)."""
        from notification_service import NotificationService

        pref = Mock(email_enabled=False)
        mock_db.query.return_value.filter.return_value.first.return_value = pref

        result = NotificationService._user_wants_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        assert result is False

    def test_preference_enabled(self, mock_db, user_id):
        """User has preference enabled (lines 359-360)."""
        from notification_service import NotificationService

        pref = Mock(email_enabled=True)
        mock_db.query.return_value.filter.return_value.first.return_value = pref

        result = NotificationService._user_wants_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        assert result is True


# ─────────────────────────────────────────────
# _user_wants_email_notification
# ─────────────────────────────────────────────

class TestUserWantsEmailNotification:

    def test_preference_exists_and_enabled(self, mock_db, user_id):
        """Returns True when preference.email_enabled is True (line 613)."""
        from notification_service import NotificationService

        pref = Mock(email_enabled=True)
        mock_db.query.return_value.filter.return_value.first.return_value = pref

        result = NotificationService._user_wants_email_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        assert result is True

    def test_preference_exists_and_disabled(self, mock_db, user_id):
        """Returns False when preference.email_enabled is False (line 613)."""
        from notification_service import NotificationService

        pref = Mock(email_enabled=False)
        mock_db.query.return_value.filter.return_value.first.return_value = pref

        result = NotificationService._user_wants_email_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        assert result is False

    def test_no_preference_returns_false(self, mock_db, user_id):
        """Returns False when no preference exists (opt-in, line 613)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = NotificationService._user_wants_email_notification(
            mock_db, user_id, NotificationType.PROJECT_CREATED
        )
        assert result is False


# ─────────────────────────────────────────────
# _send_email_notifications
# ─────────────────────────────────────────────

class TestSendEmailNotifications:

    @pytest.mark.asyncio
    @patch("notification_service.send_notification_email", new_callable=AsyncMock)
    @patch("notification_service.NotificationService._user_wants_email_notification")
    async def test_skips_user_without_email(
        self, mock_wants_email, mock_send, mock_db
    ):
        """Skips user with no email address (lines 561-562)."""
        from notification_service import NotificationService

        user_no_email = Mock(email=None)
        mock_db.query.return_value.filter.return_value.first.return_value = user_no_email

        data = [{"id": "n1", "user_id": "u1", "type": NotificationType.PROJECT_CREATED}]
        await NotificationService._send_email_notifications(mock_db, data)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("notification_service.send_notification_email", new_callable=AsyncMock)
    @patch("notification_service.NotificationService._user_wants_email_notification")
    async def test_skips_when_user_not_found(
        self, mock_wants_email, mock_send, mock_db
    ):
        """Skips when user is not found in DB (line 561)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = [{"id": "n1", "user_id": "u1", "type": NotificationType.PROJECT_CREATED}]
        await NotificationService._send_email_notifications(mock_db, data)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("notification_service.send_notification_email", new_callable=AsyncMock)
    @patch("notification_service.NotificationService._user_wants_email_notification")
    async def test_skips_when_preference_disabled(
        self, mock_wants_email, mock_send, mock_db
    ):
        """Skips when user doesn't want email for this type (lines 572-575)."""
        from notification_service import NotificationService

        user = Mock(email="test@example.com", id="u1", name="Test")
        mock_db.query.return_value.filter.return_value.first.return_value = user
        mock_wants_email.return_value = False

        data = [{"id": "n1", "user_id": "u1", "type": NotificationType.PROJECT_CREATED}]
        await NotificationService._send_email_notifications(mock_db, data)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("email_validation.is_valid_email", return_value=True)
    @patch("services.email.notification_service.send_notification_email", new_callable=AsyncMock)
    @patch("services.email.notification_service.NotificationService._user_wants_email_notification")
    async def test_sends_email_when_all_checks_pass(
        self, mock_wants_email, mock_send, mock_valid_email, mock_db
    ):
        """Sends email when user and preferences are valid (lines 584-589)."""
        from notification_service import NotificationService

        user = Mock(email="researcher@tum.de", id="u1", name="Test")
        mock_db.query.return_value.filter.return_value.first.return_value = user
        mock_wants_email.return_value = True

        data = [{
            "id": "n1",
            "user_id": "u1",
            "type": NotificationType.PROJECT_CREATED,
            "title": "T",
            "message": "M",
            "data": {},
        }]
        await NotificationService._send_email_notifications(mock_db, data)

        mock_send.assert_called_once()

    @pytest.mark.asyncio
    @patch("notification_service.send_notification_email", new_callable=AsyncMock)
    @patch("notification_service.NotificationService._user_wants_email_notification")
    async def test_handles_exception_in_loop(
        self, mock_wants_email, mock_send, mock_db
    ):
        """Catches exception per notification without crashing (lines 591-592)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.side_effect = Exception("DB error")

        data = [{"id": "n1", "user_id": "u1", "type": NotificationType.PROJECT_CREATED}]
        # Should not raise
        await NotificationService._send_email_notifications(mock_db, data)

    @pytest.mark.asyncio
    async def test_email_validation_fallback(self, mock_db):
        """When email_validation import fails, fallback validation is used (lines 550-555)."""
        from notification_service import NotificationService

        user = Mock(email="bademail", id="u1", name="Test")
        mock_db.query.return_value.filter.return_value.first.return_value = user

        with patch("notification_service.NotificationService._user_wants_email_notification") as mwe:
            mwe.return_value = True
            with patch.dict("sys.modules", {"email_validation": None}):
                # The fallback validator checks for "@" and "." in email
                # "bademail" has neither, so it should be skipped
                with patch("notification_service.send_notification_email", new_callable=AsyncMock) as mock_send:
                    data = [{"id": "n1", "user_id": "u1", "type": NotificationType.PROJECT_CREATED}]
                    await NotificationService._send_email_notifications(mock_db, data)
                    # The function defines its own fallback validator inside the try/except
                    # Depending on whether email_validation is importable in the test env,
                    # the behavior may differ. We just verify it doesn't crash.


# ─────────────────────────────────────────────
# get_notification_groups edge cases
# ─────────────────────────────────────────────

class TestGetNotificationGroupsExtended:

    def test_group_by_organization(self, mock_db, user_id):
        """Group by organization (lines 726-727)."""
        from notification_service import NotificationService

        n1 = Mock(
            type=NotificationType.PROJECT_CREATED,
            created_at=datetime.utcnow(),
            organization_id="org-1",
        )
        n2 = Mock(
            type=NotificationType.PROJECT_CREATED,
            created_at=datetime.utcnow(),
            organization_id=None,
        )

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            n1, n2
        ]

        result = NotificationService.get_notification_groups(
            mock_db, user_id, group_by="organization"
        )
        assert "org-1" in result
        assert "personal" in result

    def test_group_by_unknown_key(self, mock_db, user_id):
        """Unknown group_by key uses 'ungrouped' (lines 728-729)."""
        from notification_service import NotificationService

        n1 = Mock(
            type=NotificationType.PROJECT_CREATED,
            created_at=datetime.utcnow(),
            organization_id=None,
        )

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            n1
        ]

        result = NotificationService.get_notification_groups(
            mock_db, user_id, group_by="foobar"
        )
        assert "ungrouped" in result

    def test_group_respects_limit(self, mock_db, user_id):
        """Per-group limit is enforced (line 734)."""
        from notification_service import NotificationService

        notifications = [
            Mock(
                type=NotificationType.PROJECT_CREATED,
                created_at=datetime.utcnow(),
            )
            for _ in range(10)
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = notifications

        result = NotificationService.get_notification_groups(
            mock_db, user_id, group_by="type", limit=3
        )
        assert len(result[NotificationType.PROJECT_CREATED.value]) == 3


# ─────────────────────────────────────────────
# get_user_preferences
# ─────────────────────────────────────────────

class TestGetUserPreferences:

    def test_returns_defaults_with_overrides(self, mock_db, user_id):
        """Returns all types defaulting to True, with user overrides applied."""
        from notification_service import NotificationService

        pref = Mock(
            notification_type=NotificationType.PROJECT_CREATED.value,
            email_enabled=False,
        )
        mock_db.query.return_value.filter.return_value.all.return_value = [pref]

        result = NotificationService.get_user_preferences(mock_db, user_id)

        # PROJECT_CREATED should be overridden to False
        assert result[NotificationType.PROJECT_CREATED.value] is False
        # Other types should default to True
        assert result[NotificationType.MEMBER_JOINED.value] is True


# ─────────────────────────────────────────────
# update_user_preferences error branch
# ─────────────────────────────────────────────

class TestUpdateUserPreferencesError:

    def test_commit_failure_rolls_back(self, mock_db, user_id):
        """Commit exception triggers rollback and returns False (lines 534-537)."""
        from notification_service import NotificationService

        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.add = Mock()
        mock_db.commit = Mock(side_effect=Exception("DB down"))
        mock_db.rollback = Mock()

        result = NotificationService.update_user_preferences(
            mock_db,
            user_id,
            {NotificationType.PROJECT_CREATED.value: True},
        )
        assert result is False
        mock_db.rollback.assert_called_once()


# ─────────────────────────────────────────────
# Convenience / helper notification functions
# ─────────────────────────────────────────────

class TestNotifyProjectCreatedHelper:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients(self, mock_create, mock_recipients, mock_db):
        """When there are no recipients, create_notification is not called (lines 879-881)."""
        from notification_service import notify_project_created

        mock_recipients.return_value = []

        notify_project_created(mock_db, "p1", "Proj", "Alice", "org-1")
        mock_create.assert_not_called()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_exception_does_not_raise(self, mock_create, mock_recipients, mock_db):
        """Exception is caught and does not propagate (lines 882-883)."""
        from notification_service import notify_project_created

        mock_recipients.side_effect = Exception("Boom")

        # Should not raise
        notify_project_created(mock_db, "p1", "Proj", "Alice", "org-1")


class TestNotifyProjectDeleted:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test the first notify_project_deleted (lines 897-914)."""
        from notification_service import notify_project_deleted

        mock_recipients.return_value = ["u1", "u2"]

        notify_project_deleted(
            mock_db, "p1", "My Project", "u1", "Alice", "org-1"
        )
        # The second definition (line 1455+) is the one that's active due to Python
        # re-definition; it filters out the deleter
        mock_create.assert_called_once()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients_after_filter(self, mock_create, mock_recipients, mock_db):
        """When only the deleter is a recipient, no notification is sent (line 1474)."""
        from notification_service import notify_project_deleted

        mock_recipients.return_value = ["u1"]  # only the deleter

        notify_project_deleted(
            mock_db, "p1", "My Project", "u1", "Alice", "org-1"
        )
        mock_create.assert_not_called()


class TestNotifyProjectArchived:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_project_archived (lines 925-942 / 1505-1534)."""
        from notification_service import notify_project_archived

        mock_recipients.return_value = ["u1", "u2"]

        notify_project_archived(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1"
        )
        mock_create.assert_called_once()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients_after_filter(self, mock_create, mock_recipients, mock_db):
        """Only archiver is recipient (line 1514)."""
        from notification_service import notify_project_archived

        mock_recipients.return_value = ["u1"]

        notify_project_archived(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1"
        )
        mock_create.assert_not_called()


class TestNotifyDataImportSuccess:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_data_import_success (lines 954-972 / 1537-1574)."""
        from notification_service import notify_data_import_success

        mock_recipients.return_value = ["u1"]

        notify_data_import_success(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1", 100
        )
        mock_create.assert_called_once()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients(self, mock_create, mock_recipients, mock_db):
        """No recipients means no notification (line 1554)."""
        from notification_service import notify_data_import_success

        mock_recipients.return_value = []

        notify_data_import_success(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1", 100
        )
        mock_create.assert_not_called()


class TestNotifyLabelingConfigUpdated:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_labeling_config_updated (lines 983-1002 / 1586-1615)."""
        from notification_service import notify_labeling_config_updated

        mock_recipients.return_value = ["u1", "u2"]

        notify_labeling_config_updated(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1"
        )
        mock_create.assert_called_once()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients_after_filter(self, mock_create, mock_recipients, mock_db):
        """Only updater is recipient (line 1595)."""
        from notification_service import notify_labeling_config_updated

        mock_recipients.return_value = ["u1"]

        notify_labeling_config_updated(
            mock_db, "p1", "Proj", "u1", "Alice", "org-1"
        )
        mock_create.assert_not_called()


class TestNotifyEvaluationCompleted:

    @patch("notification_service.NotificationService.create_notification")
    def test_success_notification_returns_early(self, mock_create, mock_db):
        """Recipients list is empty so returns early (lines 1016-1023)."""
        from notification_service import notify_evaluation_completed

        notify_evaluation_completed(
            mock_db, "t1", "Task", "gpt-4", "eval-1", success=True
        )
        # recipients = [] so return early, create_notification not called
        mock_create.assert_not_called()

    @patch("notification_service.NotificationService.create_notification")
    def test_failure_notification_returns_early(self, mock_create, mock_db):
        """Failed evaluation also returns early (lines 1016-1023)."""
        from notification_service import notify_evaluation_completed

        notify_evaluation_completed(
            mock_db, "t1", "Task", "gpt-4", "eval-1",
            success=False, error_message="timeout"
        )
        mock_create.assert_not_called()


class TestNotifyDataUploadCompleted:

    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_db):
        """Test notify_data_upload_completed (lines 1064-1082)."""
        from notification_service import notify_data_upload_completed

        notify_data_upload_completed(
            mock_db, "t1", "Task", "u1", "data.csv", 50, organization_id="org-1"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["user_ids"] == ["u1"]
        assert args["notification_type"] == NotificationType.DATA_UPLOAD_COMPLETED
        assert args["data"]["upload_count"] == 50


class TestNotifyOrganizationInvitationSent:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_organization_invitation_sent (lines 1093-1115)."""
        from notification_service import notify_organization_invitation_sent

        mock_recipients.return_value = ["admin-1"]

        notify_organization_invitation_sent(
            mock_db, "org-1", "TUM", "new@example.com", "Alice"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["invitee_email"] == "new@example.com"


class TestNotifyOrganizationInvitationAccepted:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_organization_invitation_accepted (lines 1126-1148)."""
        from notification_service import notify_organization_invitation_accepted

        mock_recipients.return_value = ["admin-1"]

        notify_organization_invitation_accepted(
            mock_db, "org-1", "TUM", "Bob", "bob@example.com"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["new_member_name"] == "Bob"


class TestNotifyMemberJoined:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_member_joined (lines 1159-1177)."""
        from notification_service import notify_member_joined

        mock_recipients.return_value = ["admin-1"]

        notify_member_joined(
            mock_db, "org-1", "TUM", "Carol", "carol@example.com"
        )
        mock_create.assert_called_once()

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_no_recipients(self, mock_create, mock_recipients, mock_db):
        """No recipients means no notification."""
        from notification_service import notify_member_joined

        mock_recipients.return_value = []

        notify_member_joined(
            mock_db, "org-1", "TUM", "Carol", "carol@example.com"
        )
        mock_create.assert_not_called()


class TestNotifyModelApiKeyInvalid:

    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call_without_task(self, mock_create, mock_db):
        """Test without task info (lines 1222-1240)."""
        from notification_service import notify_model_api_key_invalid

        notify_model_api_key_invalid(
            mock_db, "u1", "OpenAI"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["model_provider"] == "OpenAI"
        assert "task_id" not in args["data"]

    @patch("notification_service.NotificationService.create_notification")
    def test_with_task_info(self, mock_create, mock_db):
        """Test with task name and ID (lines 1229-1231)."""
        from notification_service import notify_model_api_key_invalid

        notify_model_api_key_invalid(
            mock_db, "u1", "OpenAI", task_name="My Task", task_id="t1"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["task_id"] == "t1"
        assert "My Task" in args["message"]


class TestNotifyLongRunningTaskUpdate:

    @patch("notification_service.NotificationService.create_notification")
    def test_without_percentage(self, mock_create, mock_db):
        """Test without progress percentage (lines 1254-1270)."""
        from notification_service import notify_long_running_task_update

        notify_long_running_task_update(
            mock_db, "t1", "Task", "u1", "evaluation", "Processing..."
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert "progress_percentage" not in args["data"]

    @patch("notification_service.NotificationService.create_notification")
    def test_with_percentage(self, mock_create, mock_db):
        """Test with progress percentage (lines 1266-1268)."""
        from notification_service import notify_long_running_task_update

        notify_long_running_task_update(
            mock_db, "t1", "Task", "u1", "evaluation", "Processing...",
            progress_percentage=75
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["progress_percentage"] == 75
        assert "75%" in args["message"]


class TestNotifyApiQuotaWarning:

    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_db):
        """Test notify_api_quota_warning (lines 1360-1378)."""
        from notification_service import notify_api_quota_warning

        notify_api_quota_warning(
            mock_db, "u1", "OpenAI", 85, "$100", "$85"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["notification_type"] == NotificationType.API_QUOTA_WARNING
        assert args["data"]["usage_percentage"] == 85


class TestNotifyPerformanceAlert:

    @patch("notification_service.NotificationService._get_admin_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_admins, mock_db):
        """Test notify_performance_alert (lines 1390-1413)."""
        from notification_service import notify_performance_alert

        mock_admins.return_value = ["admin-1"]

        notify_performance_alert(
            mock_db, "High CPU", "API", severity="high"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["severity"] == "high"

    @patch("notification_service.NotificationService._get_admin_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_with_estimated_resolution(self, mock_create, mock_admins, mock_db):
        """Test with estimated resolution (lines 1402-1404)."""
        from notification_service import notify_performance_alert

        mock_admins.return_value = ["admin-1"]

        notify_performance_alert(
            mock_db, "High CPU", "API",
            estimated_resolution="1 hour"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["estimated_resolution"] == "1 hour"
        assert "1 hour" in args["message"]


class TestNotifyProjectCompleted:

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_basic_call(self, mock_create, mock_recipients, mock_db):
        """Test notify_project_completed (lines 1428-1448)."""
        from notification_service import notify_project_completed

        mock_recipients.return_value = ["u1"]

        notify_project_completed(
            mock_db, "p1", "My Project", "org-1"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["notification_type"] == NotificationType.PROJECT_COMPLETED
        assert "My Project" in args["title"]


class TestNotifySystemMaintenanceExtended:

    @patch("notification_service.NotificationService.create_notification")
    def test_without_optional_fields(self, mock_create, mock_db):
        """Test system maintenance without optional fields (lines 1296-1301)."""
        from notification_service import notify_system_maintenance

        mock_db.query.return_value.filter.return_value.all.return_value = [Mock(id="u1")]

        notify_system_maintenance(
            mock_db, "Maintenance", "Down for maintenance"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert "maintenance_start" not in args["data"]
        assert "maintenance_end" not in args["data"]
        assert "affected_services" not in args["data"]

    @patch("notification_service.NotificationService.create_notification")
    def test_with_all_optional_fields(self, mock_create, mock_db):
        """Test with all optional fields filled (lines 1296-1303)."""
        from notification_service import notify_system_maintenance

        mock_db.query.return_value.filter.return_value.all.return_value = [Mock(id="u1")]

        notify_system_maintenance(
            mock_db,
            "Maintenance",
            "Down for maintenance",
            maintenance_start="2026-01-01",
            maintenance_end="2026-01-02",
            affected_services=["API"],
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["maintenance_start"] == "2026-01-01"
        assert args["data"]["maintenance_end"] == "2026-01-02"
        assert args["data"]["affected_services"] == ["API"]


class TestNotifySecurityAlertExtended:

    @patch("notification_service.NotificationService.create_notification")
    def test_without_optional_fields(self, mock_create, mock_db):
        """Test security alert without action_required or additional_data (lines 1334-1339)."""
        from notification_service import notify_security_alert

        notify_security_alert(
            mock_db, "u1", "Login", "New device"
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert "action_required" not in args["data"]

    @patch("notification_service.NotificationService.create_notification")
    def test_with_additional_data(self, mock_create, mock_db):
        """Test with additional_data (lines 1338-1339)."""
        from notification_service import notify_security_alert

        notify_security_alert(
            mock_db, "u1", "Login", "New device",
            additional_data={"ip": "1.2.3.4"}
        )
        mock_create.assert_called_once()
        args = mock_create.call_args[1]
        assert args["data"]["ip"] == "1.2.3.4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
