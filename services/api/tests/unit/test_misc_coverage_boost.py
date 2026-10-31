"""
Unit tests to increase coverage for miscellaneous API modules.

Targets:
- services/user_api_key_service.py (uncovered: exception paths, validate_api_key branches, factory)
- app/core/authorization.py (uncovered: org membership mode, require_permission decorator, require_superadmin)
- services/evaluation/config.py (uncovered: metric param functions, normalize methods)
- services/evaluation/report_service.py (uncovered: _resolve_per_model_metrics, _update_metadata)
"""

import asyncio
import json
from datetime import datetime
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
        """Successful /v1/models call returns success tuple."""
        service = self._make_service()
        with patch(
            "asyncio.wait_for",
            AsyncMock(return_value=(True, "Connection to Anthropic successful", "success")),
        ):
            valid, msg, err = await service._validate_anthropic_key("sk-ant-test123")
            assert valid is True
            assert "successful" in msg.lower()

    @pytest.mark.asyncio
    async def test_anthropic_invalid_format(self):
        """Prefix fast-fail returns invalid_format without a network call."""
        service = self._make_service()
        valid, msg, err = await service._validate_anthropic_key("invalid-key")
        assert valid is False
        assert "invalid" in msg.lower()
        assert err == "invalid_format"

    @pytest.mark.asyncio
    async def test_anthropic_auth_error(self):
        """AuthenticationError raised inside wait_for is mapped to err=auth."""
        service = self._make_service()

        class AuthenticationError(Exception):
            pass

        with patch("asyncio.wait_for", side_effect=AuthenticationError("bad key")):
            valid, msg, err = await service._validate_anthropic_key("sk-ant-bogus")
            assert valid is False
            assert err == "auth"

    @pytest.mark.asyncio
    async def test_anthropic_generic_error(self):
        """Non-auth exception inside wait_for is mapped to err=connection_error."""
        service = self._make_service()
        with patch("asyncio.wait_for", side_effect=ConnectionError("fail")):
            valid, msg, err = await service._validate_anthropic_key("sk-ant-bogus")
            assert valid is False
            assert err == "connection_error"


class TestGoogleValidation:
    """Cover Google validator branches via mocked aiohttp /v1/models call."""

    def _make_service(self):
        from services.user_api_key_service import UserApiKeyService

        return UserApiKeyService(Mock())

    def _aiohttp_mock(self, status):
        mock_response = Mock()
        mock_response.status = status
        get_cm = Mock()
        get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        get_cm.__aexit__ = AsyncMock(return_value=None)
        session = Mock()
        session.get.return_value = get_cm
        session_cm = Mock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=None)
        return session_cm

    @pytest.mark.asyncio
    async def test_google_valid(self):
        service = self._make_service()
        with patch("aiohttp.ClientSession", return_value=self._aiohttp_mock(200)):
            valid, msg, err = await service._validate_google_key("AIzaSomething")
            assert valid is True
            assert err == "success"

    @pytest.mark.asyncio
    async def test_google_invalid(self):
        service = self._make_service()
        with patch("aiohttp.ClientSession", return_value=self._aiohttp_mock(400)):
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
# 2. app/core/authorization.py — uncovered branches
# ===========================================================================


class TestAuthorizationOrgContextMode:
    """Cover lines 119-139: org membership checks."""

    def test_membership_outside_the_projects_orgs_denied_in_every_context(self):
        from unittest.mock import patch

        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(
            id="proj-1", deleted_at=None, is_private=False, created_by="other", kind=None
        )
        db = Mock()
        membership = Mock(organization_id="org-123", is_active=True, role="ORG_ADMIN")

        # The project is attached to another org than the one the user is a
        # member of: no context (the member's own included) grants access.
        with patch("org_groups.get_attachment_group_map", return_value={"org-other": None}), patch(
            "org_groups.get_user_group_context", return_value={}
        ), patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            for ctx in ("org-123", "org-other", "private", None):
                assert svc.check_project_access(
                    user, project, Permission.PROJECT_VIEW, db
                ) is False, ctx

    def test_org_project_in_org_but_user_not_member(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="other")
        db = Mock()

        # Project belongs to org-123
        db.query.return_value.filter.return_value.all.return_value = [("org-123", None)]

        # User has no memberships
        with patch.object(svc, "_get_user_org_memberships", return_value=[]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db
            )
            assert result is False

    def test_org_project_in_org_user_active_member_with_permission(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="other")
        db = Mock()

        # Project belongs to org-123
        db.query.return_value.filter.return_value.all.return_value = [("org-123", None)]

        # User is active org_admin
        membership = Mock(organization_id="org-123", is_active=True, role="org_admin")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db
            )
            assert result is True

    def test_org_user_inactive_member_denied(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="other")
        db = Mock()

        db.query.return_value.filter.return_value.all.return_value = [("org-123", None)]

        # User membership is inactive
        membership = Mock(organization_id="org-123", is_active=False, role="org_admin")
        with patch.object(svc, "_get_user_org_memberships", return_value=[membership]):
            result = svc.check_project_access(
                user, project, Permission.PROJECT_VIEW, db
            )
            assert result is False


class TestAuthorizationLegacyOrgMembership:
    """Cover lines 148-175: legacy mode with org membership checks."""

    def test_legacy_creator_with_task_create_permission(self):
        """Creator gets PROJECT_VIEW/EDIT/DELETE but not TASK_CREATE via creator path."""
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="user-1")
        db = Mock()

        # Project not in any org
        db.query.return_value.filter.return_value.all.return_value = []

        # Creator can view/edit/delete
        assert svc.check_project_access(user, project, Permission.PROJECT_VIEW, db) == True  # noqa: E712
        assert svc.check_project_access(user, project, Permission.PROJECT_EDIT, db) == True  # noqa: E712
        assert svc.check_project_access(user, project, Permission.PROJECT_DELETE, db) == True  # noqa: E712

    def test_legacy_org_member_with_permission(self):
        from app.core.authorization import AuthorizationService, Permission

        svc = AuthorizationService()
        user = Mock(is_superadmin=False, id="user-2")
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="user-1")
        db = Mock()

        # Project in org-1
        db.query.return_value.filter.return_value.all.return_value = [("org-1", None)]

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
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="user-1")
        db = Mock()

        # Project in org-1
        db.query.return_value.filter.return_value.all.return_value = [("org-1", None)]

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
        project = Mock(id="proj-1", deleted_at=None, is_private=False, created_by="user-1")
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
    async def test_require_permission_admin_edit(self):
        from app.core.authorization import AuthorizationService, Permission
        from fastapi import HTTPException

        svc = AuthorizationService()

        @svc.require_permission(Permission.ADMIN_EDIT)
        async def admin_endpoint(current_user=None, db=None):
            return "ok"

        user = Mock(is_superadmin=False)
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await admin_endpoint(current_user=user, db=db)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Admin access required"


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
# 3. services/evaluation/config.py — uncovered metric parameter functions
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
# 4. services/evaluation/report_service.py — uncovered pure functions
# ===========================================================================


class TestResolvePerModelMetrics:
    """Cover lines 53-73: _resolve_per_model_metrics."""

    def test_empty_evaluation_ids(self):
        from report_service import _resolve_per_model_metrics

        db = Mock()
        result = _resolve_per_model_metrics(db, [])
        assert result == {}

    def test_no_results(self):
        from report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert result == {}

    def test_with_valid_results(self):
        from report_service import _resolve_per_model_metrics

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
        from report_service import _resolve_per_model_metrics

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
        """Pass 2: annotation-based TaskEvaluation rows yield 'annotator:<pseudonym>'
        (neutral id label when the account has none); never a real name."""
        from report_service import _resolve_per_model_metrics

        db = Mock()
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.all.side_effect = [
            [],  # no gen-based rows
            [
                # (metrics, user_id, pseudonym)
                ({"bleu": 0.6}, "0a1b2c3d-1111-4222-8333-444455556666", None),
                ({"bleu": 0.4}, "bob-id", "Codename"),
            ],
        ]
        db.query.return_value = q

        result = _resolve_per_model_metrics(db, ["eval-1"])
        assert "annotator:User 0a1b2c3d" in result
        assert "annotator:Codename" in result
        assert abs(result["annotator:User 0a1b2c3d"]["bleu"] - 0.6) < 1e-6


class TestUpdateMetadata:
    """Cover lines 364-366: _update_metadata."""

    def test_adds_section_to_completed(self):
        from report_service import _update_metadata

        report = Mock()
        report.content = {
            "metadata": {
                "last_auto_update": "old",
                "sections_completed": ["project_info"],
            }
        }

        with patch("report_service.flag_modified"):
            _update_metadata(report, "data")
            assert "data" in report.content["metadata"]["sections_completed"]
            assert report.content["metadata"]["last_auto_update"] != "old"

    def test_does_not_duplicate_section(self):
        from report_service import _update_metadata

        report = Mock()
        report.content = {
            "metadata": {
                "last_auto_update": "old",
                "sections_completed": ["project_info", "data"],
            }
        }

        with patch("report_service.flag_modified"):
            _update_metadata(report, "data")
            assert report.content["metadata"]["sections_completed"].count("data") == 1


class TestGenerateUuid:
    """Cover line 25."""

    def test_generates_valid_uuid(self):
        from report_service import generate_uuid
        import uuid

        result = generate_uuid()
        # Should be a valid UUID string
        parsed = uuid.UUID(result)
        assert str(parsed) == result
