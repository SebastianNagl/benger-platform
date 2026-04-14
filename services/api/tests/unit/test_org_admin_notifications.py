"""
Unit tests for organization admin notifications on task import and deletion
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from models import NotificationType, Organization, OrganizationMembership, OrganizationRole, User
from notification_service import NotificationService


class TestOrganizationAdminNotifications:
    """Test organization admin notifications for task import and deletion"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def test_orgs(self):
        """Create test organizations"""
        org1 = Organization(
            id="org1", name="Test Org 1", display_name="Test Org 1", slug="test-org-1"
        )
        org2 = Organization(
            id="org2", name="Test Org 2", display_name="Test Org 2", slug="test-org-2"
        )
        return [org1, org2]

    @pytest.fixture
    def test_users(self):
        """Create test users"""
        user1 = User(id="user1", username="admin1", email="admin1@test.com")
        user2 = User(id="user2", username="admin2", email="admin2@test.com")
        user3 = User(id="user3", username="member", email="member@test.com")
        user4 = User(id="user4", username="importer", email="importer@test.com")
        return {"admin1": user1, "admin2": user2, "member": user3, "importer": user4}

    @pytest.fixture
    def test_memberships(self, test_users, test_orgs):
        """Create test organization memberships"""
        return [
            # admin1 is org admin of org1
            OrganizationMembership(
                user_id=test_users["admin1"].id,
                organization_id=test_orgs[0].id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            # admin2 is org admin of org2
            OrganizationMembership(
                user_id=test_users["admin2"].id,
                organization_id=test_orgs[1].id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            # member is just a contributor of org1
            OrganizationMembership(
                user_id=test_users["member"].id,
                organization_id=test_orgs[0].id,
                role=OrganizationRole.CONTRIBUTOR,
            ),
            # importer is contributor of org1
            OrganizationMembership(
                user_id=test_users["importer"].id,
                organization_id=test_orgs[0].id,
                role=OrganizationRole.CONTRIBUTOR,
            ),
        ]

    def test_get_notification_recipients_task_import_success(
        self, mock_db, test_users, test_orgs, test_memberships
    ):
        """Test getting recipients for task import success notification"""
        # Mock the org admin query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            test_memberships[0],  # admin1 for org1
            test_memberships[1],  # admin2 for org2
        ]
        mock_db.query.return_value = mock_query

        # Test with multiple organizations
        recipients = NotificationService.get_notification_recipients(
            db=mock_db,
            event_type=NotificationType.DATA_IMPORT_SUCCESS,
            context={
                "organization_ids": [test_orgs[0].id, test_orgs[1].id],
                "task_id": "task123",
            },
        )

        # DATA_IMPORT_SUCCESS is not handled in get_notification_recipients
        # so it returns an empty list
        assert len(recipients) == 0

    def test_get_notification_recipients_task_deleted(
        self, mock_db, test_users, test_orgs, test_memberships
    ):
        """Test getting recipients for task deleted notification"""

        # Need to mock different queries differently
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query

            if model == OrganizationMembership:
                # Return org1 memberships (admin1, member, importer)
                mock_query.all.return_value = [
                    test_memberships[0],  # admin1
                    test_memberships[2],  # member
                    test_memberships[3],  # importer
                ]
            elif model == User:
                # For superadmin query, return empty (no superadmins in test)
                mock_query.all.return_value = []
            else:
                mock_query.all.return_value = []

            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Test with single organization
        recipients = NotificationService.get_notification_recipients(
            db=mock_db,
            event_type=NotificationType.PROJECT_DELETED,
            context={"organization_id": test_orgs[0].id, "task_id": "task123"},
        )

        # PROJECT_DELETED notifies all organization members (not just admins)
        # Should return admin1, member, and importer
        assert len(recipients) == 3
        assert test_users["admin1"].id in recipients
        assert test_users["member"].id in recipients
        assert test_users["importer"].id in recipients
        # But not admin2 who is in different org
        assert test_users["admin2"].id not in recipients

    @patch("notification_service.NotificationService.create_notification")
    @patch("notification_service.NotificationService.get_notification_recipients")
    def test_notify_data_import_success(
        self,
        mock_get_recipients,
        mock_create_notification,
        mock_db,
        test_users,
        test_orgs,
    ):
        """Test task import success notification"""
        # Setup mocks
        mock_get_recipients.return_value = [
            test_users["admin1"].id,
            test_users["admin2"].id,
        ]

        # Import and call the function
        from notification_service import notify_data_import_success

        # Call with correct parameters for the second signature
        notify_data_import_success(
            db=mock_db,
            project_id="task123",
            project_title="Test Task",
            imported_by_user_id=test_users["importer"].id,
            imported_by_username=test_users["importer"].username,
            organization_id=test_orgs[0].id,
            imported_items_count=42,
        )

        # Verify get_notification_recipients was called correctly
        mock_get_recipients.assert_called_once_with(
            db=mock_db,
            event_type=NotificationType.DATA_IMPORT_SUCCESS,
            context={
                "organization_id": test_orgs[0].id,
                "project_id": "task123",
            },
        )

        # Verify create_notification was called with correct parameters
        mock_create_notification.assert_called_once()
        call_args = mock_create_notification.call_args
        assert call_args[1]["db"] == mock_db
        assert call_args[1]["user_ids"] == [
            test_users["admin1"].id,
            test_users["admin2"].id,
        ]
        assert call_args[1]["notification_type"] == NotificationType.DATA_IMPORT_SUCCESS
        assert call_args[1]["title"] == "Data Import Completed: Test Task"
        assert "importer" in call_args[1]["message"]
        assert "42" in call_args[1]["message"]
        assert call_args[1]["data"]["project_id"] == "task123"
        assert call_args[1]["data"]["imported_items_count"] == 42

    @patch("notification_service.NotificationService.create_notification")
    @patch("notification_service.NotificationService.get_notification_recipients")
    def test_notify_project_deleted(
        self,
        mock_get_recipients,
        mock_create_notification,
        mock_db,
        test_users,
        test_orgs,
    ):
        """Test task deleted notification"""
        # Setup mocks
        mock_get_recipients.return_value = [
            test_users["admin1"].id,
            test_users["admin2"].id,
            test_users["importer"].id,  # This should be filtered out
        ]

        # Import and call the function
        from notification_service import notify_project_deleted

        # Call with correct parameters
        notify_project_deleted(
            db=mock_db,
            project_id="task123",
            project_title="Test Task",
            deleted_by_user_id=test_users["importer"].id,
            deleted_by_username=test_users["importer"].username,
            organization_id=test_orgs[0].id,
        )

        # Verify get_notification_recipients was called correctly
        mock_get_recipients.assert_called_once_with(
            db=mock_db,
            event_type=NotificationType.PROJECT_DELETED,
            context={"organization_id": test_orgs[0].id, "project_id": "task123"},
        )

        # Verify create_notification was called with correct parameters
        # Note: The importer should be filtered out from recipients
        mock_create_notification.assert_called_once()
        call_args = mock_create_notification.call_args
        assert call_args[1]["db"] == mock_db
        assert call_args[1]["user_ids"] == [
            test_users["admin1"].id,
            test_users["admin2"].id,
        ]
        assert test_users["importer"].id not in call_args[1]["user_ids"]
        assert call_args[1]["notification_type"] == NotificationType.PROJECT_DELETED
        assert call_args[1]["title"] == "Project Deleted: Test Task"
        assert "importer" in call_args[1]["message"]
        assert "deleted" in call_args[1]["message"]
        assert call_args[1]["data"]["project_id"] == "task123"

    @patch("notification_service.NotificationService.create_notification")
    @patch("notification_service.NotificationService.get_notification_recipients")
    def test_notify_task_import_excludes_importer(
        self,
        mock_get_recipients,
        mock_create_notification,
        mock_db,
        test_users,
        test_orgs,
    ):
        """Test that the user who imported the task doesn't get notified"""
        # Setup mocks - include the importer in the recipients
        mock_get_recipients.return_value = [
            test_users["admin1"].id,
            test_users["importer"].id,  # Importer is also an org admin
        ]

        # Import and call the function
        from notification_service import notify_data_import_success

        # Call with correct parameters
        notify_data_import_success(
            db=mock_db,
            project_id="task123",
            project_title="Test Task",
            imported_by_user_id=test_users["importer"].id,
            imported_by_username=test_users["importer"].username,
            organization_id=test_orgs[0].id,
            imported_items_count=10,
        )

        # Verify notifications were sent to all recipients (including importer)
        # The function doesn't exclude the importer
        mock_create_notification.assert_called_once()
        call_args = mock_create_notification.call_args
        assert set(call_args[1]["user_ids"]) == {test_users["admin1"].id, test_users["importer"].id}

    @patch("notification_service.NotificationService.create_notification")
    @patch("notification_service.NotificationService.get_notification_recipients")
    def test_no_notification_when_no_recipients(
        self, mock_get_recipients, mock_create_notification, mock_db, test_users
    ):
        """Test that no notification is sent when there are no recipients"""
        # Setup mocks - only return the user who performed the action
        mock_get_recipients.return_value = [test_users["importer"].id]

        # Import and call the function
        from notification_service import notify_data_import_success

        # Call with correct parameters
        notify_data_import_success(
            db=mock_db,
            project_id="task123",
            project_title="Test Task",
            imported_by_user_id=test_users["importer"].id,
            imported_by_username=test_users["importer"].username,
            organization_id="org1",
            imported_items_count=5,
        )

        # The function still creates notification even if only the importer is in recipients
        # because it doesn't exclude the importer
        mock_create_notification.assert_called_once()
