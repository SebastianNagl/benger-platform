"""The interactive API docs (/docs, /redoc, /openapi.json) are hidden in
production unless INTERNAL_DOCS_ENABLED=true (compliance prep, 2026-10-13).

The OpenAPI schema enumerates every internal route; it is not a public
contract. Dev and test keep the explorer by default (the extended behavioral
suite reads /openapi.json).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, docs_url_kwargs


@pytest.mark.unit
class TestInternalDocsSetting:
    @pytest.mark.parametrize(
        "environment,expected",
        [("production", False), ("development", True), ("test", True), ("staging", True)],
    )
    def test_default_follows_environment(self, monkeypatch, environment, expected):
        monkeypatch.delenv("INTERNAL_DOCS_ENABLED", raising=False)
        assert Settings(environment=environment).internal_docs_enabled is expected

    def test_env_var_overrides_the_default(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_DOCS_ENABLED", "true")
        assert Settings(environment="production").internal_docs_enabled is True
        monkeypatch.setenv("INTERNAL_DOCS_ENABLED", "false")
        assert Settings(environment="development").internal_docs_enabled is False

    def test_docs_url_kwargs(self):
        assert docs_url_kwargs(True) == {
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
        }
        assert docs_url_kwargs(False) == {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
        }


def _app(enabled: bool) -> FastAPI:
    app = FastAPI(title="probe", **docs_url_kwargs(enabled))

    @app.get("/api/probe")
    def probe():
        return {"ok": True}

    return app


@pytest.mark.unit
class TestDocsRoutesFollowTheSetting:
    def test_disabled_docs_answer_404_but_schema_still_builds(self):
        client = TestClient(_app(False))
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, path
        assert client.get("/api/probe").status_code == 200
        # Route introspection in tests (app.openapi()) keeps working.
        assert "/api/probe" in _app(False).openapi()["paths"]

    def test_enabled_docs_are_served(self):
        client = TestClient(_app(True))
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200

    def test_test_environment_keeps_the_docs_on_the_real_app(self):
        from main import app

        assert app.openapi_url == "/openapi.json"
        assert app.docs_url == "/docs"
