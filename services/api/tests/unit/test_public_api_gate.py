"""The access-key feature is unreleased: key management and /api/v1 answer
404 ``feature_disabled`` unless ``extensions.public_api_enabled`` opens the
gate (core 2.38). These tests run with the real gate
(``public_api_gate`` marker, no autouse override)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import extensions
from auth_module import require_user
from main import app

pytestmark = pytest.mark.public_api_gate


def _settings(enabled: bool):
    return SimpleNamespace(public_api_enabled=enabled)


def _snapshot(state, orgs=(), users=()):
    async def _load(db, **_kwargs):
        return {"public_api": {"state": state, "users": list(users), "orgs": list(orgs)}}

    return patch("feature_flags.service.load_snapshot", _load)


class TestHookWrapper:
    """Without a hook the platform's ``public_api`` flag decides (core
    2.42; before, the PUBLIC_API_ENABLED setting did)."""

    @pytest.mark.asyncio
    async def test_off_without_hook_by_default(self):
        with patch.object(extensions, "_single_hook", return_value=None), _snapshot("off"):
            assert await extensions.public_api_enabled(None, None) is False

    @pytest.mark.asyncio
    async def test_flag_opens_it_without_hook(self):
        with patch.object(extensions, "_single_hook", return_value=None), _snapshot("everyone"):
            assert await extensions.public_api_enabled(None, None) is True

    @pytest.mark.asyncio
    async def test_allowlisted_org_key_passes(self):
        with patch.object(extensions, "_single_hook", return_value=None), _snapshot(
            "allowlist", orgs=["org-1"]
        ):
            assert await extensions.public_api_enabled(None, None, organization_id="org-1") is True
            assert await extensions.public_api_enabled(None, None, organization_id="org-2") is False

    def test_setting_sets_the_flag_default(self):
        from feature_flags import registry

        with patch("app.core.config.get_settings", return_value=_settings(True)):
            assert registry.platform_flags()[0].default_state == "everyone"
        with patch("app.core.config.get_settings", return_value=_settings(False)):
            assert registry.platform_flags()[0].default_state == "off"
        assert registry.flag_owner("public_api") == registry.PLATFORM_OWNER

    @pytest.mark.asyncio
    async def test_async_hook_decides_and_gets_the_org(self):
        seen = {}

        async def hook(db, user, *, organization_id=None):
            seen["org"] = organization_id
            return True

        with (
            patch.object(extensions, "_single_hook", return_value=hook),
            patch("app.core.config.get_settings", return_value=_settings(False)),
        ):
            assert await extensions.public_api_enabled(
                "db", "user", organization_id="org-1"
            )
        assert seen["org"] == "org-1"

    @pytest.mark.asyncio
    async def test_sync_hook_is_accepted(self):
        def hook(db, user, *, organization_id=None):
            return False

        with (
            patch.object(extensions, "_single_hook", return_value=hook),
            patch("app.core.config.get_settings", return_value=_settings(True)),
        ):
            assert await extensions.public_api_enabled(None, None) is False

    @pytest.mark.asyncio
    async def test_failing_hook_counts_as_off(self):
        def hook(db, user, *, organization_id=None):
            raise RuntimeError("boom")

        with (
            patch.object(extensions, "_single_hook", return_value=hook),
            patch("app.core.config.get_settings", return_value=_settings(True)),
        ):
            assert await extensions.public_api_enabled(None, None) is False

    def test_hook_is_single_owner(self):
        assert extensions.HOOK_SPECS["public_api_enabled"] == extensions.SINGLE_OWNER


class TestHttpGate:
    def _client(self, enabled: bool):
        async def gate(db, user, *, organization_id=None):
            return enabled

        return patch.object(extensions, "public_api_enabled", gate)

    @pytest.fixture
    def signed_in(self):
        user = SimpleNamespace(id="u-1", is_superadmin=True, is_active=True)
        app.dependency_overrides[require_user] = lambda: user
        yield user
        app.dependency_overrides.pop(require_user, None)

    def test_availability_reports_off(self):
        with self._client(False):
            response = TestClient(app).get("/api/access-keys/availability")
        assert response.status_code == 200
        assert response.json() == {"enabled": False}

    def test_availability_reports_on(self):
        with self._client(True):
            response = TestClient(app).get("/api/access-keys/availability")
        assert response.json() == {"enabled": True}

    @pytest.mark.parametrize(
        "path",
        [
            "/api/access-keys/scopes",
            "/api/users/me/access-keys",
            "/api/admin/access-keys",
            "/api/v1/me",
            "/api/v1/projects",
        ],
    )
    def test_feature_routes_are_not_found_while_off(self, path, signed_in):
        with self._client(False):
            response = TestClient(app).get(path)
        assert response.status_code == 404
        assert "feature_disabled" in response.text

    @pytest.mark.parametrize("path", ["/api/v1/openapi.json", "/api/v1/docs"])
    def test_public_docs_follow_the_gate_anonymously(self, path):
        with self._client(False):
            assert TestClient(app).get(path).status_code == 404
        with self._client(True):
            assert TestClient(app).get(path).status_code != 404

    def test_anonymous_callers_get_the_login_answer_first(self):
        with self._client(False):
            response = TestClient(app).get("/api/users/me/access-keys")
        assert response.status_code == 401

    def test_gate_gets_the_caller_and_the_org_of_an_org_key(self, signed_in):
        seen = {}

        async def gate(db, user, *, organization_id=None):
            seen["user"], seen["org"] = user, organization_id
            return False

        with patch.object(extensions, "public_api_enabled", gate):
            TestClient(app).get("/api/v1/me")
        assert seen["user"] is signed_in
        assert seen["org"] is None
