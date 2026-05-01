"""
Unit tests to increase coverage for miscellaneous API modules.

Targets:
- services/user_api_key_service.py (uncovered: exception paths, validate_api_key branches, factory)
- services/analytics_service.py (uncovered: date_filter branches, IAA with annotators)
- app/core/authorization.py (uncovered: org_context mode, require_permission decorator, require_superadmin)
- services/evaluation/config.py (uncovered: metric param functions, normalize methods)
- services/evaluation/report_service.py (uncovered: _resolve_per_model_metrics, _update_metadata)
- services/websocket_clustering.py (uncovered: initialize branches, _listen_for_cluster_messages, _send_heartbeat)
- middleware/org_context.py (uncovered: dispatch with slug resolved, org_context passthrough)
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# ===========================================================================
# 1. user_api_key_service.py — uncovered exception paths & validate_api_key
# ===========================================================================


class TestUserApiKeyServiceExceptionPaths:
    """Cover lines 90-93, 129-131, 153-154, 164-167, 194-196."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    def test_set_user_api_key_generic_exception_triggers_rollback(self):
        """Lines 90-93: Exception during set_user_api_key triggers rollback."""
        service = self._make_service()
        service.encryption_service.is_valid_api_key_format.return_value = True
        service.encryption_service.encrypt_api_key.return_value = "encrypted"

        mock_db = Mock()
        mock_user = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        # Make setattr on user raise an exception
        mock_db.commit.side_effect = RuntimeError("unexpected DB error")

        result = service.set_user_api_key(mock_db, "user-1", "openai", "sk-test")
        assert result is False
        mock_db.rollback.assert_called_once()

    def test_get_user_api_key_exception_returns_none(self):
        """Lines 129-131: Exception during get_user_api_key returns None."""
        service = self._make_service()
        service.encryption_service.decrypt_api_key.side_effect = RuntimeError("decrypt fail")

        mock_db = Mock()
        mock_user = Mock()
        mock_user.encrypted_openai_api_key = "encrypted_value"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = service.get_user_api_key(mock_db, "user-1", "openai")
        assert result is None

    def test_remove_user_api_key_user_not_found(self):
        """Lines 153-154: User not found in remove_user_api_key."""
        service = self._make_service()
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.remove_user_api_key(mock_db, "user-1", "openai")
        assert result is False

    def test_remove_user_api_key_exception_triggers_rollback(self):
        """Lines 164-167: Exception during remove triggers rollback."""
        service = self._make_service()
        mock_db = Mock()
        mock_user = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db.commit.side_effect = RuntimeError("DB error")

        result = service.remove_user_api_key(mock_db, "user-1", "openai")
        assert result is False
        mock_db.rollback.assert_called_once()

    def test_get_user_api_key_status_exception_returns_empty(self):
        """Lines 194-196: Exception during status check returns empty dict."""
        service = self._make_service()
        mock_db = Mock()
        mock_db.query.side_effect = RuntimeError("DB error")

        result = service.get_user_api_key_status(mock_db, "user-1")
        assert result == {}


class TestUserApiKeyValidateProviders:
    """Cover lines 234-255 (validate_api_key dispatch) and 259-274 (openai), 278-304, 308-319."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider",
        ["OpenAI", "Anthropic", "Google", "DeepInfra", "Grok", "Mistral", "Cohere"],
    )
    async def test_validate_api_key_dispatches_to_correct_provider(self, provider):
        """Verify dispatch table routes to the correct internal validator."""
        service = self._make_service()
        method_map = {
            "OpenAI": "_validate_openai_key",
            "Anthropic": "_validate_anthropic_key",
            "Google": "_validate_google_key",
            "DeepInfra": "_validate_deepinfra_key",
            "Grok": "_validate_grok_key",
            "Mistral": "_validate_mistral_key",
            "Cohere": "_validate_cohere_key",
        }
        method_name = method_map[provider]
        with patch.object(
            service, method_name, return_value=(True, "Valid", f"{provider} key valid")
        ) as mock_v:
            valid, msg, detail = await service.validate_api_key("test-key-123", provider)
            assert valid is True
            assert msg == "Valid"
            assert provider in detail
            mock_v.assert_called_once_with("test-key-123")

    @pytest.mark.asyncio
    async def test_validate_api_key_unsupported_returns_false(self):
        """Line 251: unsupported provider."""
        service = self._make_service()
        valid, msg, err = await service.validate_api_key("key", "unsupported_provider")
        assert valid is False
        assert "Unsupported" in msg

    @pytest.mark.asyncio
    async def test_validate_api_key_exception_caught(self):
        """Lines 253-255: exception during validation."""
        service = self._make_service()
        with patch.object(
            service, "_validate_openai_key", side_effect=RuntimeError("boom")
        ):
            valid, msg, err = await service.validate_api_key("key", "openai")
            assert valid is False
            assert "boom" in msg
            assert err == "unknown"


class TestOpenAIValidationBranches:
    """Cover lines 259-274: _validate_openai_key branches."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    @pytest.mark.asyncio
    async def test_openai_timeout(self):
        """Line 266: timeout path."""
        service = self._make_service()
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            valid, msg, err = await service._validate_openai_key("key")
            assert valid is False
            assert "timeout" in msg.lower()
            assert err == "timeout"

    @pytest.mark.asyncio
    async def test_openai_connection_error(self):
        """Line 274: generic exception."""
        service = self._make_service()
        with patch("asyncio.wait_for", side_effect=ConnectionError("fail")):
            valid, msg, err = await service._validate_openai_key("key")
            assert valid is False
            assert err == "connection_error"


class TestAnthropicValidationBranches:
    """Cover lines 293-304: _validate_anthropic_key branches."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    @pytest.mark.asyncio
    async def test_anthropic_success_format(self):
        """Lines 308-309: valid key format."""
        service = self._make_service()
        valid, msg, err = await service._validate_anthropic_key("sk-ant-test123")
        assert valid is True
        assert "successful" in msg.lower()

    @pytest.mark.asyncio
    async def test_anthropic_invalid_format(self):
        """Lines 310-311: invalid key format."""
        service = self._make_service()
        valid, msg, err = await service._validate_anthropic_key("invalid-key")
        assert valid is False
        assert "invalid" in msg.lower()

    @pytest.mark.asyncio
    async def test_anthropic_auth_error(self):
        """Lines 300-303: AuthenticationError exception."""
        service = self._make_service()

        class AuthenticationError(Exception):
            pass

        with patch("asyncio.wait_for", side_effect=AuthenticationError("bad key")):
            valid, msg, err = await service._validate_anthropic_key("key")
            assert valid is False
            assert err == "auth"

    @pytest.mark.asyncio
    async def test_anthropic_generic_error(self):
        """Line 304: generic exception."""
        service = self._make_service()
        with patch("asyncio.wait_for", side_effect=ConnectionError("fail")):
            valid, msg, err = await service._validate_anthropic_key("key")
            assert valid is False
            assert err == "connection_error"


class TestGoogleValidation:
    """Cover lines 316-319."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    @pytest.mark.asyncio
    async def test_google_valid(self):
        service = self._make_service()
        valid, msg, err = await service._validate_google_key("AIzaSomething")
        assert valid is True

    @pytest.mark.asyncio
    async def test_google_invalid(self):
        service = self._make_service()
        valid, msg, err = await service._validate_google_key("invalid-key")
        assert valid is False
        assert err == "auth"


class TestCreateUserApiKeyServiceFactory:
    """Cover lines 450, 459-461."""

    def test_factory_function(self):
        from services.user_api_key_service import create_user_api_key_service, UserApiKeyService

        enc = Mock()
        service = create_user_api_key_service(enc)
        assert isinstance(service, UserApiKeyService)
        assert service.encryption_service is enc


# ===========================================================================
# 2. analytics_service.py — uncovered branches
# ===========================================================================


class TestAnalyticsDateFilter:
    """Cover lines 142, 144 (date_filter append branches in _calculate_overview)."""

    def test_overview_with_date_filters(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.count.return_value = 0
        base_q.with_entities.return_value.distinct.return_value.count.return_value = 0
        base_q.all.return_value = []

        task_q = MagicMock()
        task_q.filter.return_value = task_q
        task_q.count.return_value = 0

        db.query.side_effect = [base_q, task_q]

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)

        # Build date_filter list (simulating what get_project_statistics does)
        date_filter = [True, True]  # Simplified - just need non-empty list

        result = svc._calculate_overview(db, "proj-1", date_filter)
        assert result.total_annotations == 0


class TestAnalyticsIAAWithAnnotators:
    """Cover lines 408-457 (inter-annotator agreement with actual multi-annotated tasks)."""

    def test_iaa_with_multi_annotated_tasks(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        # Base query for multi-annotated tasks
        base_q = MagicMock()
        base_q.filter.return_value = base_q

        # Multi-annotated tasks query
        multi_q = MagicMock()
        base_q.group_by.return_value = multi_q
        multi_q.having.return_value = multi_q
        multi_q.with_entities.return_value = multi_q
        multi_q.all.return_value = [("task-1",), ("task-2",)]

        # Annotations for each task
        ann1_t1 = Mock(completed_by="user-1", result=[{"value": {"choices": ["A"]}}])
        ann2_t1 = Mock(completed_by="user-2", result=[{"value": {"choices": ["A"]}}])
        ann1_t2 = Mock(completed_by="user-1", result=[{"value": {"choices": ["B"]}}])
        ann2_t2 = Mock(completed_by="user-2", result=[{"value": {"choices": ["A"]}}])

        task_filter_q = MagicMock()
        task_filter_q.filter.return_value = task_filter_q
        task_filter_q.all.side_effect = [
            [ann1_t1, ann2_t1],  # task-1
            [ann1_t2, ann2_t2],  # task-2
        ]

        # Setup query chain
        db.query.return_value = base_q
        base_q.filter.side_effect = [base_q, task_filter_q, task_filter_q]

        result = svc._calculate_inter_annotator_agreement(db, "proj-1", [])
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_iaa_single_annotator_returns_1(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.group_by.return_value = base_q
        base_q.having.return_value = base_q
        base_q.with_entities.return_value = base_q
        base_q.all.return_value = [("task-1",)]

        # Only one annotator
        ann1 = Mock(completed_by="user-1", result=[{"value": {"choices": ["A"]}}])
        task_q = MagicMock()
        task_q.filter.return_value = task_q
        task_q.all.return_value = [ann1]

        db.query.return_value = base_q
        base_q.filter.side_effect = [base_q, task_q]

        result = svc._calculate_inter_annotator_agreement(db, "proj-1", [])
        assert result == 1.0


class TestAnalyticsQualityWithDateFilter:
    """Cover line 351 (date_filter in _calculate_quality_metrics)."""

    def test_quality_metrics_with_date_filter(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.count.side_effect = [5, 4, 1, 2]

        db.query.return_value = base_q

        with patch.object(svc, "_calculate_inter_annotator_agreement", return_value=0.85):
            result = svc._calculate_quality_metrics(db, "proj-1", [True])
            assert result.consistency_score > 0


class TestAnalyticsProjectInsightsDateFilter:
    """Cover lines 642, 649-648, 661-660 (date_filter in _calculate_project_insights)."""

    def test_project_insights_with_date_filter(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.all.return_value = []
        base_q.count.return_value = 0

        task_q = MagicMock()
        task_q.join.return_value = task_q
        task_q.filter.return_value = task_q
        task_q.group_by.return_value = task_q
        task_q.all.return_value = []

        db.query.side_effect = [base_q, task_q, base_q, base_q]

        result = svc._calculate_project_insights(db, "proj-1", [True])
        assert result.busiest_hours == []


class TestAnalyticsDifficultyAnalysis:
    """Cover lines 698-715 (difficulty analysis with tasks)."""

    def test_difficulty_analysis_with_task_times(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService()
        db = Mock()

        ann1 = Mock(created_at=datetime(2025, 1, 1, 10, 0))
        ann2 = Mock(created_at=datetime(2025, 1, 2, 14, 0))

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.all.return_value = [ann1, ann2]
        base_q.count.side_effect = [2, 0]

        # Tasks with varying times (3 tasks with different avg times)
        task_stat1 = Mock()
        task_stat1.__iter__ = Mock(return_value=iter(["t1", 10.0]))
        task_stat1.__getitem__ = lambda self, i: ["t1", 10.0][i]

        task_q = MagicMock()
        task_q.join.return_value = task_q
        task_q.filter.return_value = task_q
        task_q.group_by.return_value = task_q
        # Return tuples of (task_id, avg_time) with enough variance
        task_q.all.return_value = [
            ("t1", 10.0),
            ("t2", 50.0),
            ("t3", 100.0),
            ("t4", 200.0),
        ]

        db.query.side_effect = [base_q, task_q, base_q, base_q]

        result = svc._calculate_project_insights(db, "proj-1", [])
        assert len(result.difficulty_analysis) == 3
        difficulties = [d["difficulty"] for d in result.difficulty_analysis]
        assert "Easy" in difficulties
        assert "Medium" in difficulties
        assert "Hard" in difficulties


# ===========================================================================
# 3. app/core/authorization.py — uncovered branches
# ===========================================================================


class TestAuthorizationOrgContextMode:
    """Cover lines 119-139: org_context mode with org membership checks."""

    def test_org_context_project_not_in_org_denied(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", is_private=False, created_by="other")
        db = Mock()

        # Project has no org matching org_context
        db.query.return_value.filter.return_value.all.return_value = [("org-other",)]

        result = svc.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context="org-123"
        )
        assert result is False

    def test_org_context_project_in_org_but_user_not_member(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", is_private=False, created_by="other")
        db = Mock()

        # Project belongs to org-123
        db.query.return_value.filter.return_value.all.return_value = [("org-123",)]

        # User has no memberships
        with patch.object(svc, "_get_user_org_memberships", return_value=[]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db, org_context="org-123"
            )
            assert result is False

    def test_org_context_project_in_org_user_active_member_with_permission(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", is_private=False, created_by="other")
        db = Mock()

        # Project belongs to org-123
        db.query.return_value.filter.return_value.all.return_value = [("org-123",)]

        # User is active org_admin
        membership = Mock(organization_id="org-123", is_active=True, role="org_admin")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db, org_context="org-123"
            )
            assert result is True

    def test_org_context_user_inactive_member_denied(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", is_private=False, created_by="other")
        db = Mock()

        db.query.return_value.filter.return_value.all.return_value = [("org-123",)]

        # User membership is inactive
        membership = Mock(organization_id="org-123", is_active=False, role="org_admin")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db, org_context="org-123"
            )
            assert result is False


class TestAuthorizationLegacyOrgMembership:
    """Cover lines 148-175: legacy mode with org membership checks."""

    def test_legacy_creator_with_task_create_permission(self):
        """Creator gets PROJECT_VIEW/EDIT/DELETE but not TASK_CREATE via creator path."""
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", is_private=False, created_by="user-1")
        db = Mock()

        # Project not in any org
        db.query.return_value.filter.return_value.all.return_value = []

        # Creator can view/edit/delete
        assert svc.check_project_access(user, project, Permission.PROJECT_VIEW, db) is True
        assert svc.check_project_access(user, project, Permission.PROJECT_EDIT, db) is True
        assert svc.check_project_access(user, project, Permission.PROJECT_DELETE, db) is True

    def test_legacy_org_member_with_permission(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-2")
        project = Mock(id="proj-1", is_private=False, created_by="user-1")
        db = Mock()

        # Project in org-1
        db.query.return_value.filter.return_value.all.return_value = [("org-1",)]

        # User is contributor in org-1
        membership = Mock(organization_id="org-1", role="contributor")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db
            )
            assert result is True

    def test_legacy_org_member_no_match(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-2")
        project = Mock(id="proj-1", is_private=False, created_by="user-1")
        db = Mock()

        # Project in org-1
        db.query.return_value.filter.return_value.all.return_value = [("org-1",)]

        # User in different org
        membership = Mock(organization_id="org-2", role="org_admin")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db
            )
            assert result is False

    def test_legacy_no_orgs_non_creator_denied(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-2")
        project = Mock(id="proj-1", is_private=False, created_by="user-1")
        db = Mock()

        db.query.return_value.filter.return_value.all.return_value = []

        result = svc.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is False


class TestRequirePermissionDecorator:
    """Cover lines 294-329: require_permission decorator."""

    @pytest.mark.asyncio
    async def test_require_permission_admin_non_superadmin_raises(self):
        from app.core.authorization import AuthorizationService, Permission
        from fastapi import HTTPException

        svc = AuthorizationService()

        @svc.require_permission(Permission.ADMIN_VIEW)
        async def admin_endpoint(current_user=None, db=None):
            return "ok"

        user = Mock(is_superadmin=False)
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await admin_endpoint(current_user=user, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_permission_admin_superadmin_allowed(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()

        @svc.require_permission(Permission.ADMIN_VIEW)
        async def admin_endpoint(current_user=None, db=None):
            return "ok"

        user = Mock(is_superadmin=True)
        db = Mock()

        result = await admin_endpoint(current_user=user, db=db)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_require_permission_with_resource_getter_project(self):
        from app.core.authorization import AuthorizationService, Permission
        from fastapi import HTTPException
        from project_models import Project

        svc = AuthorizationService()

        mock_project = Mock(spec=Project)
        mock_project.id = "proj-1"

        async def get_project(*args, **kwargs):
            return mock_project

        @svc.require_permission(Permission.PROJECT_EDIT, resource_getter=get_project)
        async def edit_endpoint(current_user=None, db=None):
            return "edited"

        user = Mock(is_superadmin=False)
        db = Mock()

        with patch.object(svc, "check_project_access", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await edit_endpoint(current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_permission_feature_flag_manage(self):
        from app.core.authorization import AuthorizationService, Permission
        from fastapi import HTTPException

        svc = AuthorizationService()

        @svc.require_permission(Permission.FEATURE_FLAG_MANAGE)
        async def flag_endpoint(current_user=None, db=None):
            return "ok"

        user = Mock(is_superadmin=False)
        db = Mock()

        with pytest.raises(HTTPException):
            await flag_endpoint(current_user=user, db=db)


class TestConvenienceDecorators:
    """Cover lines 377, 382, 387, 392, 398-409."""

    def test_require_project_view_uses_correct_permission(self):
        from app.core.authorization import require_project_view, Permission, auth_service

        with patch.object(auth_service, "require_permission", return_value=lambda f: f) as mock_rp:
            require_project_view()
            mock_rp.assert_called_once_with(Permission.PROJECT_VIEW)

    def test_require_project_edit_uses_correct_permission(self):
        from app.core.authorization import require_project_edit, Permission, auth_service

        with patch.object(auth_service, "require_permission", return_value=lambda f: f) as mock_rp:
            require_project_edit()
            mock_rp.assert_called_once_with(Permission.PROJECT_EDIT)

    def test_require_project_delete_uses_correct_permission(self):
        from app.core.authorization import require_project_delete, Permission, auth_service

        with patch.object(auth_service, "require_permission", return_value=lambda f: f) as mock_rp:
            require_project_delete()
            mock_rp.assert_called_once_with(Permission.PROJECT_DELETE)

    def test_require_admin_uses_correct_permission(self):
        from app.core.authorization import require_admin, Permission, auth_service

        with patch.object(auth_service, "require_permission", return_value=lambda f: f) as mock_rp:
            require_admin()
            mock_rp.assert_called_once_with(Permission.ADMIN_VIEW)

    @pytest.mark.asyncio
    async def test_require_superadmin_non_superadmin_raises(self):
        from app.core.authorization import require_superadmin
        from fastapi import HTTPException

        decorator = require_superadmin()

        @decorator
        async def superadmin_endpoint(current_user=None):
            return "ok"

        user = Mock(is_superadmin=False)
        with pytest.raises(HTTPException) as exc_info:
            await superadmin_endpoint(current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_superadmin_superadmin_passes(self):
        from app.core.authorization import require_superadmin

        decorator = require_superadmin()

        @decorator
        async def superadmin_endpoint(current_user=None):
            return "ok"

        user = Mock(is_superadmin=True)
        result = await superadmin_endpoint(current_user=user)
        assert result == "ok"


# ===========================================================================
# 4. services/evaluation/config.py — uncovered metric parameter functions
# ===========================================================================


class TestGetMetricDefaults:
    """Cover lines 588-598."""

    def test_bleu_defaults(self):
        from services.evaluation.config import get_metric_defaults

        result = get_metric_defaults("bleu")
        assert result["max_order"] == 4
        assert result["weights"] == [0.25, 0.25, 0.25, 0.25]

    def test_rouge_defaults(self):
        from services.evaluation.config import get_metric_defaults

        result = get_metric_defaults("rouge")
        assert result["variant"] == "rougeL"

    def test_meteor_defaults(self):
        from services.evaluation.config import get_metric_defaults

        result = get_metric_defaults("meteor")
        assert result["alpha"] == 0.9

    def test_chrf_defaults(self):
        from services.evaluation.config import get_metric_defaults

        result = get_metric_defaults("chrf")
        assert result["char_order"] == 6

    def test_unknown_metric_empty(self):
        from services.evaluation.config import get_metric_defaults

        result = get_metric_defaults("nonexistent")
        assert result == {}


class TestNormalizeMetricSelection:
    """Cover lines 616-628."""

    def test_string_input_with_defaults(self):
        from services.evaluation.config import normalize_metric_selection

        result = normalize_metric_selection("bleu")
        assert result["name"] == "bleu"
        assert result["parameters"]["max_order"] == 4

    def test_string_input_without_defaults(self):
        from services.evaluation.config import normalize_metric_selection

        result = normalize_metric_selection("exact_match")
        assert result["name"] == "exact_match"
        assert result["parameters"] == {}

    def test_dict_input_merges_with_defaults(self):
        from services.evaluation.config import normalize_metric_selection

        result = normalize_metric_selection(
            {"name": "bleu", "parameters": {"max_order": 2}}
        )
        assert result["name"] == "bleu"
        assert result["parameters"]["max_order"] == 2  # User override
        assert result["parameters"]["smoothing"] == "method1"  # Default preserved

    def test_dict_input_no_params(self):
        from services.evaluation.config import normalize_metric_selection

        result = normalize_metric_selection({"name": "rouge"})
        assert result["name"] == "rouge"
        assert result["parameters"]["variant"] == "rougeL"


class TestNormalizeSelectedMethods:
    """Cover lines 641-662."""

    def test_list_format(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({
            "answer": ["bleu", "rouge"],
        })
        assert len(result["answer"]["metrics"]) == 2
        assert result["answer"]["metrics"][0]["name"] == "bleu"

    def test_dict_with_metrics_key(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({
            "answer": {"metrics": ["bleu"]},
        })
        assert len(result["answer"]["metrics"]) == 1

    def test_dict_with_automated_key(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({
            "answer": {"automated": ["bleu", "rouge"]},
        })
        assert len(result["answer"]["metrics"]) == 2

    def test_dict_with_non_list_metrics(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({
            "answer": {"metrics": "not_a_list"},
        })
        assert result["answer"]["metrics"] == []

    def test_non_dict_non_list_value(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({
            "answer": 42,
        })
        assert result["answer"]["metrics"] == []

    def test_empty_input(self):
        from services.evaluation.config import normalize_selected_methods

        result = normalize_selected_methods({})
        assert result == {}


class TestGetMetricParameters:
    """Cover lines 679-698."""

    def test_no_config_returns_defaults(self):
        from services.evaluation.config import get_metric_parameters

        result = get_metric_parameters(None, "answer", "bleu")
        assert result["max_order"] == 4

    def test_no_selected_methods_key(self):
        from services.evaluation.config import get_metric_parameters

        result = get_metric_parameters({"other": "data"}, "answer", "bleu")
        assert result["max_order"] == 4

    def test_list_format_dict_metric_found(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "answer": [
                    {"name": "bleu", "parameters": {"max_order": 2}},
                ]
            }
        }
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 2

    def test_list_format_string_metric_found(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "answer": ["bleu", "rouge"],
            }
        }
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 4  # Returns defaults

    def test_dict_format_with_automated_key(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu"],
                },
            }
        }
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 4

    def test_metric_not_found_returns_defaults(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "answer": ["rouge"],
            }
        }
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 4

    def test_field_not_found_returns_defaults(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "other_field": ["bleu"],
            }
        }
        # Field "answer" not in selected_methods, so field_selections is {}
        # empty dict.get("metrics", ...) returns empty list, metric not found -> returns defaults
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 4  # Returns bleu defaults

    def test_dict_metric_without_parameters(self):
        from services.evaluation.config import get_metric_parameters

        config = {
            "selected_methods": {
                "answer": [
                    {"name": "bleu"},  # No parameters key
                ]
            }
        }
        result = get_metric_parameters(config, "answer", "bleu")
        assert result["max_order"] == 4  # Falls back to defaults


class TestGetAvailableMethodsForProject:
    """Cover lines 564-566 (exception path in get_available_methods_for_project)."""

    def test_exception_returns_empty(self):
        from services.evaluation.config import get_available_methods_for_project

        with patch(
            "services.evaluation.config.AnswerTypeDetector", side_effect=RuntimeError("boom")
        ):
            result = get_available_methods_for_project("<View><Broken/></View>")
            assert result["detected_answer_types"] == []
            assert result["available_methods"] == {}


# ===========================================================================
# 5. services/evaluation/report_service.py — uncovered pure functions
# ===========================================================================


class TestResolvePerModelMetrics:
    """Cover lines 53-73: _resolve_per_model_metrics."""

    def test_empty_evaluation_ids(self):
        from services.evaluation.report_service import _resolve_per_model_metrics

        db = Mock()
        result = _resolve_per_model_metrics(db, [])
        assert result == {}

    def test_no_results(self):
        from services.evaluation.report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert result == {}

    def test_with_valid_results(self):
        from services.evaluation.report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        # Resolver issues two queries: pass 1 = gen-based (model_id, metrics)
        # tuples; pass 2 = annotation-based (metrics, username, name, pseudonym,
        # use_pseudonym). Use side_effect so each .all() returns the right shape.
        q.all.side_effect = [
            [
                ("gpt-4", {"f1": 0.9, "bleu": 0.8}),
                ("gpt-4", {"f1": 0.8, "bleu": 0.7}),
                ("claude-3", {"f1": 0.85}),
            ],
            [],  # no annotation-based rows
        ]
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert "gpt-4" in result
        assert "claude-3" in result
        assert abs(result["gpt-4"]["f1"] - 0.85) < 0.01  # Average of 0.9 and 0.8

    def test_skips_unknown_model_id(self):
        from services.evaluation.report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.all.side_effect = [
            [
                ("unknown", {"f1": 0.9}),
                (None, {"f1": 0.8}),
                ("gpt-4", None),  # None metrics -> skipped
            ],
            [],
        ]
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert "unknown" not in result
        assert None not in result
        # gpt-4 had None metrics, so it was skipped entirely
        assert "gpt-4" not in result

    def test_resolves_annotator_synthetic_ids(self):
        """Pass 2: annotation-based TaskEvaluation rows yield 'annotator:<display>'."""
        from services.evaluation.report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.all.side_effect = [
            [],  # no gen-based rows
            [
                # (metrics, username, name, pseudonym, use_pseudonym)
                ({"bleu": 0.6}, "alice", "Alice A.", None, False),
                ({"bleu": 0.4}, "bob", "Bob B.", "Codename", True),
            ],
        ]
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert "annotator:Alice A." in result
        assert "annotator:Codename" in result  # use_pseudonym wins
        assert abs(result["annotator:Alice A."]["bleu"] - 0.6) < 1e-6


class TestUpdateMetadata:
    """Cover lines 364-366: _update_metadata."""

    def test_adds_section_to_completed(self):
        from services.evaluation.report_service import _update_metadata

        report = Mock()
        report.content = {
            "metadata": {
                "last_auto_update": "old",
                "sections_completed": ["project_info"],
            }
        }

        with patch("services.evaluation.report_service.flag_modified"):
            _update_metadata(report, "data")
            assert "data" in report.content["metadata"]["sections_completed"]
            assert report.content["metadata"]["last_auto_update"] != "old"

    def test_does_not_duplicate_section(self):
        from services.evaluation.report_service import _update_metadata

        report = Mock()
        report.content = {
            "metadata": {
                "last_auto_update": "old",
                "sections_completed": ["project_info", "data"],
            }
        }

        with patch("services.evaluation.report_service.flag_modified"):
            _update_metadata(report, "data")
            assert report.content["metadata"]["sections_completed"].count("data") == 1


class TestGenerateUuid:
    """Cover line 25."""

    def test_generates_valid_uuid(self):
        from services.evaluation.report_service import generate_uuid
        import uuid

        result = generate_uuid()
        # Should be a valid UUID string
        parsed = uuid.UUID(result)
        assert str(parsed) == result


# ===========================================================================
# 6. services/websocket_clustering.py — uncovered branches
# ===========================================================================


class TestWebSocketClusteringInitBranches:
    """Cover lines 60-64, 73-80 (connection_pool attribute branches)."""

    @pytest.mark.asyncio
    async def test_initialize_with_connection_pool(self):
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=AsyncMock())
        mock_redis.pubsub.return_value.subscribe = AsyncMock()

        sync_redis = MagicMock()
        # Has connection_pool but not _connection_pool
        del_attrs = []
        if hasattr(sync_redis, '_connection_pool'):
            del_attrs.append('_connection_pool')
        sync_redis.connection_pool = MagicMock()
        sync_redis.connection_pool.connection_kwargs = {
            "host": "redis-host",
            "port": 6380,
            "db": 1,
        }
        # Remove _connection_pool so it falls through to connection_pool branch
        sync_redis._connection_pool = None

        with patch("websocket_clustering.get_redis_client", return_value=sync_redis), \
             patch("websocket_clustering.redis.Redis", return_value=mock_redis):
            # Mock hasattr check: _connection_pool returns False
            original_hasattr = hasattr

            def custom_hasattr(obj, name):
                if name == "_connection_pool" and obj is sync_redis:
                    return False
                return original_hasattr(obj, name)

            with patch("builtins.hasattr", side_effect=custom_hasattr):
                await manager.initialize()

    @pytest.mark.asyncio
    async def test_initialize_fallback_defaults(self):
        """Lines 73-80: fallback when no pool attributes exist."""
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=AsyncMock())
        mock_redis.pubsub.return_value.subscribe = AsyncMock()

        # Client with no connection pool attributes
        sync_redis = MagicMock(spec=[])

        with patch("websocket_clustering.get_redis_client", return_value=sync_redis), \
             patch("websocket_clustering.redis.Redis", return_value=mock_redis):
            await manager.initialize()
            assert manager.is_listening is True


class TestWebSocketListenForMessages:
    """Cover lines 231, 234-254."""

    @pytest.mark.asyncio
    async def test_listen_returns_when_no_pubsub(self):
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager.pubsub = None
        # Should return immediately without error
        await manager._listen_for_cluster_messages()

    @pytest.mark.asyncio
    async def test_handle_cluster_message_no_local_connections(self):
        """Lines 271-274: project_broadcast but no local connections."""
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager._forward_to_local_connections = AsyncMock()

        data = {
            "type": "project_broadcast",
            "project_id": "proj-1",
            "message": {"test": True},
            "exclude_user": None,
        }

        await manager._handle_cluster_message(data)
        # No local connections for proj-1, so forward should not be called
        manager._forward_to_local_connections.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_cluster_message_user_message_not_local(self):
        """Lines 282-286: user_message but user not in local connections."""
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager._forward_to_local_user = AsyncMock()

        data = {
            "type": "user_message",
            "project_id": "proj-1",
            "user_id": "user-1",
            "message": {"test": True},
        }

        await manager._handle_cluster_message(data)
        manager._forward_to_local_user.assert_not_called()


class TestWebSocketGetProjectUsersError:
    """Cover lines 220-223: error in get_project_users loop."""

    @pytest.mark.asyncio
    async def test_get_project_users_parse_error(self):
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager.redis_client = AsyncMock()
        manager.redis_client.keys.return_value = ["key1", "key2"]
        # First key returns valid data, second returns invalid
        manager.redis_client.get.side_effect = [
            json.dumps({"user_id": "user-1"}),
            "invalid json{{{",
        ]

        users = await manager.get_project_users("proj-1")
        assert len(users) == 1
        assert users[0]["user_id"] == "user-1"


class TestWebSocketCleanupPartial:
    """Cover lines 351-358 with partial cleanup (no pubsub)."""

    @pytest.mark.asyncio
    async def test_cleanup_without_pubsub(self):
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager.is_listening = True
        manager.pubsub = None
        manager.redis_client = None

        await manager.cleanup()
        assert manager.is_listening is False

    @pytest.mark.asyncio
    async def test_cleanup_with_redis_only(self):
        from websocket_clustering import WebSocketClusterManager

        manager = WebSocketClusterManager()
        manager.is_listening = True
        manager.pubsub = None
        manager.redis_client = AsyncMock()

        await manager.cleanup()
        assert manager.is_listening is False
        manager.redis_client.close.assert_called_once()


# ===========================================================================
# 7. middleware/org_context.py — uncovered dispatch branches
# ===========================================================================


class TestOrgContextDispatchBranches:
    """Cover lines 31-52: dispatch method branches."""

    def _make_request(self, headers_dict):
        """Create a mock request with proper headers.get() behavior."""
        request = Mock()
        # Use a real dict for headers so .get() works naturally
        request.headers = headers_dict
        request.state = Mock(spec=[])
        return request

    @pytest.mark.asyncio
    async def test_dispatch_with_valid_slug_resolved(self):
        """Lines 42-44: slug resolved to org_id."""
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        request = self._make_request({"X-Organization-Slug": "my-org"})
        call_next = AsyncMock(return_value=Mock())

        with patch.object(middleware, "_resolve_slug", return_value="org-123"):
            await middleware.dispatch(request, call_next)
            assert request.state.organization_context == "org-123"

    @pytest.mark.asyncio
    async def test_dispatch_with_valid_slug_not_resolved(self):
        """Lines 45-46: slug valid format but not found."""
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        request = self._make_request({"X-Organization-Slug": "unknown-org"})
        call_next = AsyncMock(return_value=Mock())

        with patch.object(middleware, "_resolve_slug", return_value=None):
            await middleware.dispatch(request, call_next)
            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_with_org_context_header(self):
        """Lines 48-50: X-Organization-Context passed through."""
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        request = self._make_request({"X-Organization-Context": "direct-org-id"})
        call_next = AsyncMock(return_value=Mock())

        await middleware.dispatch(request, call_next)
        assert request.state.organization_context == "direct-org-id"

    @pytest.mark.asyncio
    async def test_dispatch_no_headers(self):
        """Lines 51-52: no org headers - private mode."""
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        request = self._make_request({})
        call_next = AsyncMock(return_value=Mock())

        await middleware.dispatch(request, call_next)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_invalid_slug_returns_400(self):
        """Lines 34-40: invalid slug format."""
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        request = self._make_request({"X-Organization-Slug": "INVALID!slug"})
        call_next = AsyncMock(return_value=Mock())

        response = await middleware.dispatch(request, call_next)
        # Should return JSONResponse with 400
        assert response.status_code == 400
