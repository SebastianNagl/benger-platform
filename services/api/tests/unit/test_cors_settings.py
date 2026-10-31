"""CORS policy (audit S1, 2026-10-31).

The browser frontends reach the API only through the same-origin Next route
proxy, so production allows no cross-origin browser access unless
CORS_ALLOWED_ORIGINS lists exact origins. Outside production a regex admits
local dev hosts only. A credentialed CORS grant to the storage, staging or
demo hosts (or any *.what-a-benger.net) would let a page stored there read
/api/auth/refresh with the victim's cookie.
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import DEV_CORS_ORIGIN_REGEX, Settings, cors_middleware_kwargs


def _app_for(settings: Settings) -> TestClient:
    app = FastAPI()
    kwargs = cors_middleware_kwargs(settings)
    if kwargs is not None:
        app.add_middleware(CORSMiddleware, **kwargs)

    @app.post("/api/auth/refresh")
    def refresh():
        return {"access_token": "t"}

    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/auth/refresh",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )


HOSTILE_ORIGINS = [
    "https://storage.what-a-benger.net",
    "https://staging.what-a-benger.net",
    "https://demo.what-a-benger.net",
    "https://what-a-benger.net",
    "https://api.what-a-benger.net",
    "http://what-a-benger.net",
    "https://evil.example",
    "https://localhost.evil.example",
    "https://benger.localhost.evil.example",
]


@pytest.mark.unit
class TestProductionCors:
    def test_no_middleware_without_allowlist(self, monkeypatch):
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        assert cors_middleware_kwargs(Settings(environment="production")) is None

    @pytest.mark.parametrize("origin", HOSTILE_ORIGINS + ["http://localhost:3000"])
    def test_no_origin_is_granted_by_default(self, monkeypatch, origin):
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        client = _app_for(Settings(environment="production"))
        resp = client.post("/api/auth/refresh", headers={"Origin": origin})
        assert "access-control-allow-origin" not in resp.headers
        assert "access-control-allow-credentials" not in resp.headers

    def test_explicit_allowlist_only(self, monkeypatch):
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS", " https://partner.example/ , *, partner2.example,"
        )
        settings = Settings(environment="production")
        # Trailing slash trimmed; "*" and scheme-less entries dropped.
        assert settings.cors_allowed_origin_list == ["https://partner.example"]
        kwargs = cors_middleware_kwargs(settings)
        assert kwargs["allow_origins"] == ["https://partner.example"]
        assert "allow_origin_regex" not in kwargs

        client = _app_for(settings)
        ok = _preflight(client, "https://partner.example")
        assert ok.headers["access-control-allow-origin"] == "https://partner.example"
        for origin in HOSTILE_ORIGINS:
            resp = client.post("/api/auth/refresh", headers={"Origin": origin})
            assert "access-control-allow-origin" not in resp.headers, origin

    def test_regex_is_never_used_in_production(self):
        assert Settings(environment="production").cors_origin_regex is None
        assert Settings(environment="Production").cors_origin_regex is None


@pytest.mark.unit
class TestDevCors:
    @pytest.mark.parametrize("environment", ["development", "test", "staging", "demo"])
    def test_dev_regex_outside_production(self, monkeypatch, environment):
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        kwargs = cors_middleware_kwargs(Settings(environment=environment))
        assert kwargs["allow_origin_regex"] == DEV_CORS_ORIGIN_REGEX
        assert kwargs["allow_origins"] == []
        assert kwargs["allow_credentials"] is True

    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost",
            "http://localhost:3000",
            "https://localhost:8443",
            "http://benger.localhost",
            "http://app.benger.localhost",
            "http://vertretbar.localhost",
            "http://app.vertretbar.localhost:3000",
        ],
    )
    def test_local_hosts_allowed(self, monkeypatch, origin):
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        client = _app_for(Settings(environment="development"))
        resp = _preflight(client, origin)
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.parametrize("origin", HOSTILE_ORIGINS)
    def test_deployed_and_foreign_hosts_refused(self, monkeypatch, origin):
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        client = _app_for(Settings(environment="development"))
        resp = client.post("/api/auth/refresh", headers={"Origin": origin})
        assert "access-control-allow-origin" not in resp.headers

    def test_main_app_wires_the_settings(self):
        """The real app grants the dev host and refuses the storage host."""
        from main import app

        client = TestClient(app)
        ok = _preflight(client, "http://localhost:3000")
        assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
        bad = _preflight(client, "https://storage.what-a-benger.net")
        assert "access-control-allow-origin" not in bad.headers
