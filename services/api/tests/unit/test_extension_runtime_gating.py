"""Runtime gating of extension packages (core 2.42): HOOK_GATING, router
gates with UNGATED_ROUTES, and metric owners.

Fake packages are injected into ``sys.modules`` and loaded through
``extensions.load_extended`` (which registers their master flags); the
master state comes from the flag snapshot in the (fake) Redis cache, the
same place the API reads it from.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import extension_activation as activation
import extension_registry as registry
import extensions
from core_version import CORE_API_VERSION
from feature_flags import registry as flag_registry
from feature_flags import service

MASTER = "extension.fake"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", None)
    for var in (
        "BENGER_REQUIRE_EXTENDED",
        "BENGER_REQUIRE_EXTENSIONS",
        "BENGER_EXTENSION_ROUTE_POLICY",
    ):
        monkeypatch.delenv(var, raising=False)
    registry.reset()
    yield
    registry.reset()
    flag_registry.reset_master_flags()
    extensions._extended = None


def _set_master(mock_redis_client, state, users=(), orgs=()):
    import json

    mock_redis_client.set(
        service.SNAPSHOT_KEY,
        json.dumps({MASTER: {"state": state, "users": list(users), "orgs": list(orgs)}}),
    )


def _router(*paths, method="GET"):
    router = APIRouter()
    for path in paths:

        def _make(p):
            async def handler():
                return {"path": p}

            return handler

        router.add_api_route(path, _make(path), methods=[method])
    return router


def _package(name="benger_fake", *, routers=(), hooks=None, ungated=None, default=None):
    mod = types.ModuleType(name)
    mod.__file__ = f"/fake/{name}/__init__.py"
    mod.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]
    mod.EXTENSION_ID = "fake"
    if default:
        mod.DEFAULT_RUNTIME_STATE = default
    if ungated is not None:
        mod.UNGATED_ROUTES = ungated
    mod.get_routers = lambda: list(routers)
    if hooks is not None:
        mod.get_hooks = lambda: dict(hooks)
    return mod


def _load(monkeypatch, package, *, required=False):
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setenv("BENGER_EXTENSIONS", package.__name__)
    if required:
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", package.__name__)
    assert extensions.load_extended() is True


class TestHookGating:
    def test_every_hook_key_has_a_class(self):
        assert set(extensions.HOOK_GATING) == set(extensions.HOOK_SPECS)
        assert set(extensions.HOOK_GATING.values()) <= set(activation.GATING_CLASSES)

    def test_classes_are_pinned(self):
        """Privacy, billing, LMS grade sync, monitoring and exam-timer hooks
        must keep running while a package is switched off. Moving one to
        GATED needs this test to change on purpose."""
        always = {
            "before_annotation_write",
            "on_annotation_created",
            "on_draft_saved",
            "after_eval_config_save",
            "on_ops_event",
            "privacy_protected_member_ids",
            "lti_protected_org_ids",
            "project_real_name_viewer",
            "project_real_name_user_ids",
            "projects_real_name_user_ids",
            "lti_anonymization_policy",
            "dispatch_lti_grade_sync",
            "resend_all_lti_grades",
            "public_api_enabled",
        }
        policy_global = {"validate_signup", "after_user_signup"}
        for key, gating in extensions.HOOK_GATING.items():
            if key in always:
                assert gating == activation.ALWAYS, key
            elif key in policy_global:
                assert gating == activation.POLICY_GLOBAL, key
            else:
                assert gating == activation.GATED, key

    def test_always_hooks_run_and_gated_hooks_skip_while_off(self, monkeypatch, mock_redis):
        calls = []
        hooks = {
            "after_user_login": lambda *a: calls.append("login"),
            "privacy_protected_member_ids": lambda db, org, ids, **kw: {"u1"},
            "validate_signup": lambda db, user_create: calls.append("signup"),
            "tasks_with_feedback_for_user": lambda *a: {"t1"},
        }
        _load(monkeypatch, _package(hooks=hooks))
        _set_master(mock_redis, "off")
        with activation.use_context(user_id="u1", inherit=False):
            extensions.after_user_login(None, object(), {})
            extensions.validate_signup(None, object())
            assert extensions.privacy_protected_member_ids(None, None, ["u1", "u2"]) == {"u1"}
            assert extensions.tasks_with_feedback_for_user(None, "p1", "u1", ["t1"]) == set()
        assert calls == []

        _set_master(mock_redis, "allowlist", users=["someone-else"])
        with activation.use_context(user_id="u1", inherit=False):
            extensions.after_user_login(None, object(), {})
            extensions.validate_signup(None, object())
        # POLICY_GLOBAL runs (state is not off), GATED still skips for u1.
        assert calls == ["signup"]

        _set_master(mock_redis, "allowlist", users=["u1"])
        with activation.use_context(user_id="u1", inherit=False):
            extensions.after_user_login(None, object(), {})
            assert extensions.tasks_with_feedback_for_user(None, "p1", "u1", ["t1"]) == {"t1"}
        assert calls == ["signup", "login"]

    def test_master_flag_is_registered_with_the_package_default(self, monkeypatch):
        _load(monkeypatch, _package(default="allowlist"))
        definition = flag_registry.flag(MASTER)
        assert definition.default_state == "allowlist"
        assert flag_registry.flag_owner(MASTER) == "benger_fake"

    def test_fallback_defaults(self, monkeypatch):
        _load(monkeypatch, _package())
        assert flag_registry.flag(MASTER).default_state == "off"


class TestRouterGating:
    def _app(self):
        app = FastAPI()
        extensions.include_extension_routers(app)
        return TestClient(app)

    def test_inactive_package_routes_answer_feature_disabled(self, monkeypatch, mock_redis):
        routers = [(_router("/status", "/webhook"), {"prefix": "/api/ext/fake"})]
        _load(
            monkeypatch,
            _package(routers=routers, ungated={("GET", "/api/ext/fake/webhook")}),
        )
        _set_master(mock_redis, "off")
        client = self._app()
        response = client.get("/api/ext/fake/status")
        assert response.status_code == 404
        assert response.json() == {
            "detail": {"code": "feature_disabled", "flag": "extension.fake"}
        }
        # The ungated route stays reachable while the package is off.
        assert client.get("/api/ext/fake/webhook").json() == {"path": "/webhook"}

        _set_master(mock_redis, "everyone")
        assert client.get("/api/ext/fake/status").json() == {"path": "/status"}

    def test_session_user_from_the_jwt_counts(self, monkeypatch, mock_redis):
        from auth_module import create_access_token
        from middleware.extension_context import ExtensionContextMiddleware

        routers = [(_router("/status"), {"prefix": "/api/ext/fake"})]
        _load(monkeypatch, _package(routers=routers))
        _set_master(mock_redis, "allowlist", users=["u-listed"])
        app = FastAPI()
        extensions.include_extension_routers(app)
        app.add_middleware(ExtensionContextMiddleware)
        client = TestClient(app)
        assert client.get("/api/ext/fake/status").status_code == 404
        token = create_access_token({"user_id": "u-listed"})
        ok = client.get("/api/ext/fake/status", cookies={"access_token": token})
        assert ok.status_code == 200
        other = create_access_token({"user_id": "u-other"})
        no = client.get("/api/ext/fake/status", headers={"Authorization": f"Bearer {other}"})
        assert no.status_code == 404

    def test_unknown_ungated_entry_fails_a_required_package(self, monkeypatch):
        routers = [(_router("/status"), {"prefix": "/api/ext/fake"})]
        _load(
            monkeypatch,
            _package(routers=routers, ungated={("POST", "/api/ext/fake/nope")}),
            required=True,
        )
        with pytest.raises(RuntimeError, match="UNGATED_ROUTES"):
            extensions.include_extension_routers(FastAPI())

    def test_unknown_ungated_entry_is_logged_for_an_optional_package(
        self, monkeypatch, caplog
    ):
        routers = [(_router("/status"), {"prefix": "/api/ext/fake"})]
        _load(
            monkeypatch,
            _package(routers=routers, ungated={("POST", "/api/ext/fake/nope")}),
        )
        with caplog.at_level(logging.ERROR, logger="extensions"):
            assert extensions.include_extension_routers(FastAPI()) == 1
        assert "UNGATED_ROUTES" in caplog.text


class TestMetricOwners:
    def test_metrics_follow_their_owner(self, monkeypatch, mock_redis):
        from services.evaluation import config

        _load(monkeypatch, _package())
        monkeypatch.setattr(config, "_extended_metrics", {})
        monkeypatch.setattr(config, "_extended_metric_owners", {})
        with registry.owner("benger_fake"):
            config.register_extended_metrics("long_text", ["fake_metric"])
        config.register_extended_metrics("long_text", ["unowned_metric"])
        assert config.extended_metric_owner("long_text", "fake_metric") == "benger_fake"

        _set_master(mock_redis, "off")
        with activation.use_context(user_id="u1", inherit=False):
            metrics = config.get_metrics_for_answer_type(config.AnswerType.LONG_TEXT)
        assert "fake_metric" not in metrics
        assert "unowned_metric" in metrics

        _set_master(mock_redis, "everyone")
        with activation.use_context(user_id="u1", inherit=False):
            metrics = config.get_metrics_for_answer_type(config.AnswerType.LONG_TEXT)
        assert "fake_metric" in metrics

    def test_package_import_runs_under_its_owner(self, monkeypatch):
        seen = []

        class _Finder:
            def find_spec(self, name, path=None, target=None):
                if name != "benger_owner_probe":
                    return None
                import importlib.machinery

                loader = self

                return importlib.machinery.ModuleSpec(name, loader)

            def create_module(self, spec):
                return None

            def exec_module(self, module):
                seen.append(registry.current_owner())
                module.__file__ = "/fake/benger_owner_probe/__init__.py"
                module.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]

        finder = _Finder()
        monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
        monkeypatch.delitem(sys.modules, "benger_owner_probe", raising=False)
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_owner_probe")
        registry.load_all()
        sys.modules.pop("benger_owner_probe", None)
        assert seen == ["benger_owner_probe"]
