"""``extensions.include_extension_routers``: prefix policy and collisions.

Two fake packages are injected into ``sys.modules`` and loaded through the
registry; the routers are real ``APIRouter`` objects mounted on a real
``FastAPI`` app, so the checks run against what FastAPI actually serves.
"""

import logging
import sys
import types

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import extension_registry as registry
import extensions
from core_version import CORE_API_VERSION


def _router(*paths):
    router = APIRouter()
    for path in paths:

        def _make(p):
            async def handler():
                return {"path": p}

            return handler

        router.add_api_route(path, _make(path), methods=["GET"])
    return router


def _package(name, routers, *, ext_id=None):
    mod = types.ModuleType(name)
    mod.__file__ = f"/fake/{name}/__init__.py"
    mod.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]
    # These tests are about mounting; the runtime gate (core 2.42) is
    # covered in test_extension_runtime_gating.py, so the fakes start on.
    mod.DEFAULT_RUNTIME_STATE = "everyone"
    if ext_id:
        mod.EXTENSION_ID = ext_id
    mod.get_routers = lambda: list(routers)
    return mod


def _app():
    app = FastAPI()
    app.include_router(_router("/x"), prefix="/api/projects")
    return app


def _paths(app):
    return set(app.openapi()["paths"])


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", None)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_EXTENSION_ROUTE_POLICY", raising=False)
    registry.reset()
    yield
    registry.reset()
    extensions._extended = None


def _load(monkeypatch, *packages):
    for package in packages:
        monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setenv("BENGER_EXTENSIONS", ",".join(p.__name__ for p in packages))
    assert extensions.load_extended() is True


class TestCommunityEdition:
    def test_nothing_is_mounted(self):
        app = _app()
        assert extensions.include_extension_routers(app) == 0
        assert _paths(app) == {"/api/projects/x"}
        assert extensions.get_extended_routers() == []


class TestPrefixPolicy:
    def test_extended_may_mount_anywhere(self, monkeypatch):
        extended = _package(
            "benger_extended",
            [(_router("/{id}/timer"), {"prefix": "/api/projects"}), (_router("/internal/metrics"), {})],
        )
        _load(monkeypatch, extended)
        app = _app()
        assert extensions.include_extension_routers(app) == 2
        assert {"/api/projects/{id}/timer", "/internal/metrics"} <= _paths(app)
        # The single-package accessor still answers for benger_extended.
        assert len(extensions.get_extended_routers()) == 2

    def test_other_packages_mount_under_their_namespace(self, monkeypatch):
        comp = _package(
            "benger_compliance",
            [
                (_router("/status"), {"prefix": "/api/ext/compliance"}),
                (_router("/a"), {"prefix": "/api/ext/compliance/runs"}),
            ],
        )
        _load(monkeypatch, comp)
        app = _app()
        assert extensions.include_extension_routers(app) == 2
        assert {"/api/ext/compliance/status", "/api/ext/compliance/runs/a"} <= _paths(app)
        assert TestClient(app).get("/api/ext/compliance/status").json() == {"path": "/status"}

    def test_namespace_follows_the_declared_id(self, monkeypatch):
        comp = _package(
            "benger_x", [(_router("/status"), {"prefix": "/api/ext/risky"})], ext_id="risky"
        )
        _load(monkeypatch, comp)
        app = _app()
        assert extensions.include_extension_routers(app) == 1
        assert "/api/ext/risky/status" in _paths(app)

    def test_violation_is_skipped_for_an_optional_package(self, monkeypatch, caplog):
        comp = _package(
            "benger_compliance",
            [
                (_router("/y"), {"prefix": "/api/projects"}),
                (_router("/status"), {"prefix": "/api/ext/compliance"}),
            ],
        )
        _load(monkeypatch, comp)
        app = _app()
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.include_extension_routers(app) == 1
        assert "/api/projects/y" not in _paths(app)
        assert "/api/ext/compliance/status" in _paths(app)
        assert "must mount under '/api/ext/compliance'" in caplog.text

    def test_violation_fails_a_required_package(self, monkeypatch):
        comp = _package("benger_compliance", [(_router("/y"), {"prefix": "/api/projects"})])
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_compliance")
        _load(monkeypatch, comp)
        with pytest.raises(RuntimeError, match="must mount under"):
            extensions.include_extension_routers(_app())


class TestCollisions:
    def test_platform_overlap_is_logged_and_the_platform_wins(self, monkeypatch, caplog):
        extended = _package("benger_extended", [(_router("/x"), {"prefix": "/api/projects"})])
        _load(monkeypatch, extended)
        app = _app()
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.include_extension_routers(app) == 1
        assert "the platform already serves" in caplog.text
        assert "('GET', '/api/projects/x')" in caplog.text

    def test_extension_overlap_fails_a_required_later_package(self, monkeypatch):
        extended = _package(
            "benger_extended", [(_router("/status"), {"prefix": "/api/ext/compliance"})]
        )
        comp = _package(
            "benger_compliance", [(_router("/status"), {"prefix": "/api/ext/compliance"})]
        )
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_compliance")
        _load(monkeypatch, extended, comp)
        with pytest.raises(RuntimeError, match="another package already mounted"):
            extensions.include_extension_routers(_app())

    def test_extension_overlap_is_logged_for_an_optional_later_package(
        self, monkeypatch, caplog
    ):
        extended = _package(
            "benger_extended", [(_router("/status"), {"prefix": "/api/ext/compliance"})]
        )
        comp = _package(
            "benger_compliance",
            [(_router("/status", "/other"), {"prefix": "/api/ext/compliance"})],
        )
        _load(monkeypatch, extended, comp)
        app = _app()
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.include_extension_routers(app) == 2
        assert "another package already mounted" in caplog.text
        assert "/api/ext/compliance/other" in _paths(app)

    def test_warn_policy_never_raises(self, monkeypatch, caplog):
        extended = _package(
            "benger_extended", [(_router("/status"), {"prefix": "/api/ext/compliance"})]
        )
        comp = _package(
            "benger_compliance", [(_router("/status"), {"prefix": "/api/ext/compliance"})]
        )
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_compliance")
        monkeypatch.setenv("BENGER_EXTENSION_ROUTE_POLICY", "warn")
        _load(monkeypatch, extended, comp)
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.include_extension_routers(_app()) == 2
        assert "another package already mounted" in caplog.text

    def test_a_package_may_repeat_its_own_paths_across_routers(self, monkeypatch, caplog):
        comp = _package(
            "benger_compliance",
            [
                (_router("/status"), {"prefix": "/api/ext/compliance"}),
                (_router("/status"), {"prefix": "/api/ext/compliance"}),
            ],
        )
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_compliance")
        _load(monkeypatch, comp)
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.include_extension_routers(_app()) == 2
        assert "another package already mounted" not in caplog.text


class TestRouteSignatures:
    def test_nested_includes_are_flattened(self):
        inner = _router("/leaf")
        outer = APIRouter()
        outer.include_router(inner, prefix="/in")
        assert extensions._router_signatures(outer, {"prefix": "/p"}) == {("GET", "/p/in/leaf")}

    def test_platform_signatures_include_the_app_routes(self):
        app = _app()
        assert ("GET", "/api/projects/x") in extensions._route_signatures(app.routes)
