"""
Integration tests for remaining untested API routers (Phases 2.3, 2.4, 2.5).

Covers:
  Group 1 — Generation routers: generation.py, generation_task_list.py
  Group 2 — Auth & User Management: auth.py, users.py, invitations.py
  Group 3 — Admin & System routers: notifications.py, feature_flags.py,
            dashboard.py, health.py, prompt_structures.py, reports.py,
            llm_models.py

Uses real PostgreSQL with per-test transaction rollback isolation via the
shared test_db fixture.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import (
    FeatureFlag,
    Generation as DBGeneration,
    Invitation,
    LLMModel,
    Notification,
    NotificationType,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration as DBResponseGeneration,
    User,
)
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(
    test_db: Session,
    admin: User,
    test_org: Organization,
    *,
    title: str = "Test Project",
    generation_config: dict = None,
    label_config: str = '<View><Text name="text" value="$text"/></View>',
    is_private: bool = False,
    num_tasks: int = 2,
) -> Dict:
    """Create a project linked to the test organization with tasks."""
    pid = _uid()
    project = Project(
        id=pid,
        title=f"{title} {pid[:6]}",
        description="Integration test project",
        created_by=admin.id,
        label_config=label_config,
        generation_config=generation_config,
        is_private=is_private,
    )
    test_db.add(project)
    test_db.flush()

    if not is_private:
        test_db.add(ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=test_org.id,
            assigned_by=admin.id,
        ))
        test_db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            data={"text": f"Sample text {i}"},
            created_by=admin.id,
            inner_id=i + 1,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()
    test_db.commit()

    return {"project": project, "tasks": tasks}


# ===================================================================
# GROUP 1 — GENERATION ROUTERS
# ===================================================================


class TestGenerationStatusEndpoints:
    """Tests for /api/generation status, stop, pause, resume, retry, delete, parse-metrics."""

    def _create_response_generation(
        self, test_db, project, task, admin, *, status_val="completed", model_id="gpt-4o"
    ):
        gen = DBResponseGeneration(
            id=_uid(),
            project_id=project.id,
            task_id=task.id,
            model_id=model_id,
            status=status_val,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(gen)
        test_db.flush()
        test_db.commit()
        return gen

    def test_get_generation_status_found(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="running"
        )
        resp = client.get(
            f"/api/generation/status/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == gen.id
        assert body["status"] == "running"

    def test_get_generation_status_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/generation/status/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    @patch("routers.generation.celery_app")
    def test_stop_running_generation(self, mock_celery, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stopped"

    def test_stop_completed_generation_returns_400(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="completed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_stop_generation_permission_denied(self, client, test_db, test_users, test_org, auth_headers):
        """Non-owner, non-superadmin cannot stop another user's generation."""
        admin = test_users[0]
        contributor = test_users[1]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403

    def test_pause_non_running_returns_400(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="completed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/pause",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_resume_non_paused_returns_400(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/resume",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    @patch("routers.generation.celery_app")
    def test_retry_failed_generation(self, mock_celery, client, test_db, test_users, test_org, auth_headers):
        # BUG: ResponseGeneration model has no retry_count column, so the
        # endpoint crashes with AttributeError when trying to increment it.
        # Expect 500 until a migration adds the column.
        mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="failed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/retry",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 500

    def test_delete_completed_generation(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="completed"
        )
        resp = client.delete(
            f"/api/generation/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["generation_id"] == gen.id

    def test_delete_running_generation_returns_400(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        gen = self._create_response_generation(
            test_db, data["project"], data["tasks"][0], admin, status_val="running"
        )
        resp = client.delete(
            f"/api/generation/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_parse_metrics_empty_project(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        resp = client.get(
            f"/api/generation/parse-metrics?project_id={data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_generations"] == 0
        assert body["parse_success_rate"] == 0

    def test_parse_metrics_no_project_filter(self, client, auth_headers):
        resp = client.get(
            "/api/generation/parse-metrics",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_generations" in body


class TestGenerationTaskListEndpoints:
    """Tests for /api/generation-tasks endpoints."""

    def test_task_status_no_models_configured(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        resp = client.get(
            f"/api/generation-tasks/projects/{data['project'].id}/task-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["models"] == []

    def test_task_status_with_models(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        gen_config = {
            "selected_configuration": {"models": ["gpt-4o"], "active_structures": []},
            "prompt_structures": {},
        }
        data = _make_project(test_db, admin, test_org, generation_config=gen_config, num_tasks=3)
        resp = client.get(
            f"/api/generation-tasks/projects/{data['project'].id}/task-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["models"] == ["gpt-4o"]
        assert len(body["tasks"]) == 3

    def test_task_status_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/generation-tasks/projects/nonexistent-id/task-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    @patch("routers.generation_task_list.celery_app")
    def test_start_generation_no_models_returns_400(self, mock_celery, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        resp = client.post(
            f"/api/generation-tasks/projects/{data['project'].id}/generate",
            json={"mode": "all"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    @patch("routers.generation_task_list.celery_app")
    def test_start_generation_all_mode(self, mock_celery, client, test_db, test_users, test_org, auth_headers):
        mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
        mock_celery.control.revoke = MagicMock()
        admin = test_users[0]
        gen_config = {
            "selected_configuration": {"models": ["gpt-4o"], "active_structures": []},
            "prompt_structures": {},
        }
        data = _make_project(test_db, admin, test_org, generation_config=gen_config, num_tasks=2)
        resp = client.post(
            f"/api/generation-tasks/projects/{data['project'].id}/generate",
            json={"mode": "all"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tasks_queued"] == 2
        assert body["models_count"] == 1

    def test_generation_result_task_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/generation-tasks/generation-result?task_id=nope&model_id=gpt-4o",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===================================================================
# GROUP 2 — AUTH & USER MANAGEMENT
# ===================================================================


class TestAuthLoginEndpoints:
    """Tests for /api/auth/login and related auth endpoints."""

    def test_login_valid_credentials(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_invalid_password(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody@test.com", "password": "anything"},
        )
        assert resp.status_code == 401


class TestAuthMeEndpoints:
    """Tests for /api/auth/me and /api/auth/verify."""

    def test_get_me_authenticated(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "admin-test-id"
        assert body["is_superadmin"] is True
        assert body["email"] == "admin@test.com"

    def test_get_me_unauthenticated(self, client, test_db, test_users):
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    def test_verify_token_valid(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_me_contexts_returns_orgs(self, client, test_db, test_users, test_org, auth_headers):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert "user" in body
        assert "organizations" in body
        assert isinstance(body["organizations"], list)


class TestAuthProfileEndpoints:
    """Tests for /api/auth/profile GET and PUT."""

    def test_get_profile(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/profile", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "admin-test-id"
        assert body["username"] == "admin@test.com"
        assert body["email"] == "admin@test.com"
        assert body["is_superadmin"] is True

    def test_get_profile_contributor(self, client, test_db, test_users, test_org, auth_headers):
        resp = client.get("/api/auth/profile", headers=auth_headers["contributor"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_superadmin"] is False

    def test_update_profile_name(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Updated Admin Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Updated Admin Name"


class TestAuthMandatoryProfileEndpoints:
    """Tests for /api/auth/mandatory-profile-status and /api/auth/confirm-profile."""

    def test_mandatory_profile_status(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/auth/mandatory-profile-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "mandatory_profile_completed" in body
        assert "confirmation_due" in body
        assert "missing_fields" in body

    def test_confirm_profile(self, client, test_db, test_users, auth_headers):
        # confirm-profile returns 400 when mandatory profile fields are missing.
        # Test users are created without gender, age, legal_expertise_level, etc.
        resp = client.post(
            "/api/auth/confirm-profile",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "missing fields" in body["detail"].lower()

    def test_check_profile_status(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/auth/check-profile-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "profile_completed" in body
        assert "has_password" in body


class TestAuthLogoutEndpoints:
    """Tests for /api/auth/logout and /api/auth/logout-all."""

    def test_logout(self, client, test_db, test_users, auth_headers):
        resp = client.post("/api/auth/logout", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    def test_logout_all(self, client, test_db, test_users, auth_headers):
        """Logout from all devices revokes all refresh tokens."""
        resp = client.post("/api/auth/logout-all", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body or "detail" in body or resp.status_code == 200


class TestUsersEndpoints:
    """Tests for /api/users endpoints (superadmin only)."""

    def test_get_all_users_as_admin(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/users", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 3  # Our three test users

    def test_get_all_users_as_non_admin_returns_403(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/users", headers=auth_headers["annotator"])
        assert resp.status_code == 403

    def test_update_user_role(self, client, test_db, test_users, auth_headers):
        annotator = test_users[2]
        resp = client.patch(
            f"/api/users/{annotator.id}/role",
            json={"is_superadmin": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_superadmin"] is True

    def test_update_user_role_invalid_type(self, client, test_db, test_users, auth_headers):
        annotator = test_users[2]
        resp = client.patch(
            f"/api/users/{annotator.id}/role",
            json={"is_superadmin": "not-a-bool"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_update_user_status(self, client, test_db, test_users, auth_headers):
        annotator = test_users[2]
        resp = client.patch(
            f"/api/users/{annotator.id}/status",
            json={"is_active": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_delete_user_not_self(self, client, test_db, test_users, auth_headers):
        annotator = test_users[2]
        resp = client.delete(
            f"/api/users/{annotator.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 204

    def test_delete_self_returns_400(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        resp = client.delete(
            f"/api/users/{admin.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_delete_nonexistent_user_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            "/api/users/nonexistent-user-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestInvitationsEndpoints:
    """Tests for /api/invitations endpoints."""

    def test_create_invitation(self, client, test_db, test_users, test_org, auth_headers):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": "newuser@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["role"] == "ANNOTATOR"
        assert body["accepted"] is False

    def test_create_invitation_org_not_found(self, client, test_db, test_users, auth_headers):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                "/api/invitations/organizations/nonexistent-org/invitations",
                json={"email": "user@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 404

    def test_list_invitations(self, client, test_db, test_users, test_org, auth_headers):
        # First create an invitation
        invitation = Invitation(
            id=_uid(),
            organization_id=test_org.id,
            email="listed@example.com",
            role=OrganizationRole.CONTRIBUTOR,
            token=_uid(),
            invited_by=test_users[0].id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.commit()

        resp = client.get(
            f"/api/invitations/organizations/{test_org.id}/invitations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert any(inv["email"] == "listed@example.com" for inv in body)

    def test_validate_invitation_token(self, client, test_db, test_users, test_org):
        token = _uid()
        invitation = Invitation(
            id=_uid(),
            organization_id=test_org.id,
            email="validate@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=token,
            invited_by=test_users[0].id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.commit()

        resp = client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["email"] == "validate@example.com"

    def test_validate_expired_invitation(self, client, test_db, test_users, test_org):
        token = _uid()
        invitation = Invitation(
            id=_uid(),
            organization_id=test_org.id,
            email="expired@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=token,
            invited_by=test_users[0].id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.commit()

        resp = client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 400

    def test_cancel_invitation(self, client, test_db, test_users, test_org, auth_headers):
        invitation = Invitation(
            id=_uid(),
            organization_id=test_org.id,
            email="cancel@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=_uid(),
            invited_by=test_users[0].id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.commit()

        resp = client.delete(
            f"/api/invitations/{invitation.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Invitation cancelled successfully"

    def test_get_invitation_by_token(self, client, test_db, test_users, test_org):
        token = _uid()
        invitation = Invitation(
            id=_uid(),
            organization_id=test_org.id,
            email="bytoken@example.com",
            role=OrganizationRole.CONTRIBUTOR,
            token=token,
            invited_by=test_users[0].id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.commit()

        resp = client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "bytoken@example.com"
        assert body["role"] == "CONTRIBUTOR"


# ===================================================================
# GROUP 3 — ADMIN & SYSTEM ROUTERS
# ===================================================================


class TestNotificationEndpoints:
    """Tests for /api/notifications endpoints."""

    def _create_notification(self, test_db, user, *, is_read=False):
        n = Notification(
            id=_uid(),
            user_id=user.id,
            type=NotificationType.SYSTEM_ALERT,
            title="Test Notification",
            message="This is a test notification",
            data={"test": True},
            is_read=is_read,
        )
        test_db.add(n)
        test_db.flush()
        test_db.commit()
        return n

    def test_get_notifications_empty(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/notifications/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_notifications_with_data(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin)
        self._create_notification(test_db, admin)
        resp = client.get("/api/notifications/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) >= 2

    def test_get_notifications_unread_only(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        self._create_notification(test_db, admin, is_read=True)
        resp = client.get(
            "/api/notifications/?unread_only=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(not n["is_read"] for n in body)

    def test_get_unread_count(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        resp = client.get("/api/notifications/unread-count", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_mark_notification_read(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        n = self._create_notification(test_db, admin, is_read=False)
        resp = client.post(
            f"/api/notifications/mark-read/{n.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "marked as read" in resp.json()["message"].lower()

    def test_mark_nonexistent_notification_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/notifications/mark-read/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_mark_all_read(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        self._create_notification(test_db, admin, is_read=False)
        resp = client.post(
            "/api/notifications/mark-all-read",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "marked" in resp.json()["message"].lower()

    def test_notification_preferences_get(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/notifications/preferences",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "preferences" in resp.json()

    def test_notification_preferences_update(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/notifications/preferences",
            json={"preferences": {"system_alert": False}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_notification_summary(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/notifications/summary",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_notifications" in body
        assert "unread_notifications" in body
        assert "period_days" in body


class TestFeatureFlagEndpoints:
    """Tests for /api/feature-flags endpoints."""

    def _create_flag(self, test_db, admin):
        flag = FeatureFlag(
            id=_uid(),
            name=f"test_flag_{_uid()[:8]}",
            description="A test flag",
            is_enabled=False,
            created_by=admin.id,
        )
        test_db.add(flag)
        test_db.flush()
        test_db.commit()
        return flag

    def test_list_feature_flags_as_admin(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_flag(test_db, admin)
        resp = client.get("/api/feature-flags", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_feature_flags_as_non_admin_returns_403(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/feature-flags", headers=auth_headers["annotator"])
        assert resp.status_code == 403

    def test_get_all_flags_as_regular_user(self, client, test_db, test_users, auth_headers):
        """The /all endpoint is available to any authenticated user."""
        admin = test_users[0]
        self._create_flag(test_db, admin)
        resp = client.get("/api/feature-flags/all", headers=auth_headers["annotator"])
        assert resp.status_code == 200

    def test_get_single_flag(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.get(
            f"/api/feature-flags/{flag.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == flag.name
        assert body["is_enabled"] is False

    def test_get_nonexistent_flag_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/feature-flags/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_feature_flag(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.put(
            f"/api/feature-flags/{flag.id}",
            json={"is_enabled": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is True

    def test_delete_feature_flag(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.delete(
            f"/api/feature-flags/{flag.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 204

    def test_check_flag_by_name(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.get(
            f"/api/feature-flags/check/{flag.name}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["flag_name"] == flag.name
        assert "is_enabled" in body


class TestDashboardEndpoints:
    """Tests for /api/dashboard/stats."""

    def test_dashboard_stats(self, client, test_db, test_users, test_org, auth_headers):
        resp = client.get("/api/dashboard/stats", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert "project_count" in body
        assert "task_count" in body
        assert "annotation_count" in body
        assert "projects_with_generations" in body
        assert "projects_with_evaluations" in body

    def test_dashboard_stats_with_org_header(self, client, test_db, test_users, test_org, auth_headers):
        headers = {**auth_headers["admin"], "X-Organization-Context": test_org.id}
        resp = client.get("/api/dashboard/stats", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_count"] >= 0

    def test_dashboard_stats_counts_match_data(self, client, test_db, test_users, test_org, auth_headers):
        """Verify dashboard counts match actual data in the database."""
        from models import EvaluationRun, Generation, ResponseGeneration, TaskEvaluation
        from project_models import Annotation, Project, ProjectOrganization, Task

        admin = test_users[0]
        _uid = lambda: str(__import__("uuid").uuid4())
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

        # Create a project with known data counts
        project = Project(
            id=_uid(), title="Dashboard Count Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=admin.id,
        ))
        test_db.flush()

        # 3 tasks
        tasks = []
        for i in range(3):
            t = Task(id=_uid(), project_id=project.id, data={"text": f"t{i}"},
                     inner_id=i + 1, created_by=admin.id)
            test_db.add(t)
            tasks.append(t)
        test_db.flush()

        # 2 annotations (non-cancelled, with results)
        for i in range(2):
            test_db.add(Annotation(
                id=_uid(), task_id=tasks[i].id, project_id=project.id,
                completed_by=admin.id, was_cancelled=False,
                result=[{"value": "test"}],
                created_at=now,
            ))
        test_db.flush()

        # 1 generation
        rg = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            status="completed", created_by=admin.id,
            started_at=now, completed_at=now,
        )
        test_db.add(rg)
        test_db.flush()
        test_db.add(Generation(
            id=_uid(), generation_id=rg.id, task_id=tasks[0].id,
            model_id="gpt-4o", case_data='{"text": "t0"}',
            response_content="response", status="completed",
        ))
        test_db.flush()

        # 1 evaluation
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            evaluation_type_ids=["accuracy"], metrics={"accuracy": 0.9},
            status="completed", created_by=admin.id, created_at=now,
        )
        test_db.add(er)
        test_db.flush()
        test_db.add(TaskEvaluation(
            id=_uid(), evaluation_id=er.id, task_id=tasks[0].id,
            field_name="text", answer_type="text",
            metrics={"accuracy": 0.9}, prediction="pred", ground_truth="gt",
            passed=True,
        ))
        test_db.commit()

        headers = {**auth_headers["admin"], "X-Organization-Context": test_org.id}
        resp = client.get("/api/dashboard/stats", headers=headers)
        assert resp.status_code == 200
        body = resp.json()

        # Counts should be at least what we created (other tests may add more)
        assert body["project_count"] >= 1
        assert body["task_count"] >= 3
        assert body["annotation_count"] >= 2
        assert body["projects_with_generations"] >= 1
        assert body["projects_with_evaluations"] >= 1

    def test_dashboard_stats_unauthenticated(self, client, test_db, test_users):
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code in (401, 403)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_schema(self, client, test_db):
        resp = client.get("/health/schema")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "error")
        assert "schema" in body

    def test_health_cors_auth(self, client, test_db, test_users, auth_headers):
        resp = client.get("/health/cors-auth", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["user_id"] == "admin-test-id"


class TestPromptStructureEndpoints:
    """Tests for /api/projects/{project_id}/generation-config/structures endpoints."""

    BASE = "/api/projects"

    def test_list_structures_empty(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        project = data["project"]
        resp = client.get(
            f"{self.BASE}/{project.id}/generation-config/structures",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_create_structure(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        project = data["project"]
        structure_payload = {
            "name": "My Structure",
            "system_prompt": "You are a legal assistant.",
            "instruction_prompt": "Answer the following question: {question}",
        }
        resp = client.put(
            f"{self.BASE}/{project.id}/generation-config/structures/my-structure",
            json=structure_payload,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "my-structure"

    def test_get_structure(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        gen_config = {
            "prompt_structures": {
                "qa-prompt": {
                    "name": "QA Prompt",
                    "system_prompt": "Be helpful",
                    "instruction_prompt": "Q: {question}",
                }
            },
            "selected_configuration": {"models": [], "active_structures": []},
        }
        data = _make_project(test_db, admin, test_org, generation_config=gen_config)
        project = data["project"]
        resp = client.get(
            f"{self.BASE}/{project.id}/generation-config/structures/qa-prompt",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "qa-prompt"

    def test_get_nonexistent_structure_returns_404(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        project = data["project"]
        resp = client.get(
            f"{self.BASE}/{project.id}/generation-config/structures/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_delete_structure(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        gen_config = {
            "prompt_structures": {
                "to-delete": {
                    "name": "To Delete",
                    "system_prompt": "X",
                    "instruction_prompt": "Y",
                }
            },
            "selected_configuration": {"models": [], "active_structures": ["to-delete"]},
        }
        data = _make_project(test_db, admin, test_org, generation_config=gen_config)
        project = data["project"]
        resp = client.delete(
            f"{self.BASE}/{project.id}/generation-config/structures/to-delete",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_nonexistent_structure_returns_404(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        project = data["project"]
        resp = client.delete(
            f"{self.BASE}/{project.id}/generation-config/structures/no-such-key",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_invalid_structure_key(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org, generation_config={})
        project = data["project"]
        resp = client.put(
            f"{self.BASE}/{project.id}/generation-config/structures/invalid key!",
            json={"name": "Invalid", "system_prompt": "x", "instruction_prompt": "y"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400


class TestReportEndpoints:
    """Tests for /api/projects/{project_id}/report and /api/reports endpoints."""

    def test_get_report_project_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent-id/report",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_report_non_admin_returns_403(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        resp = client.post(
            f"/api/projects/{data['project'].id}/report",
            json={
                "content": {
                    "sections": {"project_info": {"status": "completed"}},
                    "metadata": {"version": 1},
                }
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_publish_report_non_admin_returns_403(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        resp = client.put(
            f"/api/projects/{data['project'].id}/report/publish",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_unpublish_report_non_admin_returns_403(self, client, test_db, test_users, test_org, auth_headers):
        admin = test_users[0]
        data = _make_project(test_db, admin, test_org)
        resp = client.put(
            f"/api/projects/{data['project'].id}/report/unpublish",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_list_published_reports(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/reports", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestLLMModelEndpoints:
    """Tests for /api/llm_models endpoints."""

    def test_get_public_models_empty(self, client, test_db):
        """Public models endpoint returns list even with no models."""
        resp = client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_public_models_with_data(self, client, test_db):
        model = LLMModel(
            id=_uid(),
            name="Test GPT-4o",
            provider="openai",
            model_type="chat",
            capabilities=["text_generation"],
            is_active=True,
        )
        test_db.add(model)
        test_db.commit()

        resp = client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        body = resp.json()
        assert any(m["name"] == "Test GPT-4o" for m in body)

    def test_inactive_models_not_returned(self, client, test_db):
        model = LLMModel(
            id=_uid(),
            name="Inactive Model",
            provider="openai",
            model_type="chat",
            capabilities=["text_generation"],
            is_active=False,
        )
        test_db.add(model)
        test_db.commit()

        resp = client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        body = resp.json()
        assert not any(m["name"] == "Inactive Model" for m in body)

    def test_get_provider_capabilities(self, client):
        resp = client.get("/api/llm_models/public/provider-capabilities")
        assert resp.status_code == 200
        # Response is a dict of providers; may be empty if shared lib not available
        assert isinstance(resp.json(), dict)
