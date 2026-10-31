"""CORS and version headers of /api/v1 (any origin, never credentials);
the app-wide CORS policy stays as it is elsewhere."""

from routers.v1 import _middleware

ORIGIN = "https://consumer.example"


async def test_preflight_is_answered_for_any_origin(async_test_client):
    r = await async_test_client.options(
        "/api/v1/projects",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Idempotency-Key",
        },
    )
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in r.headers
    assert r.headers["access-control-allow-methods"] == "GET, POST, PATCH, DELETE, OPTIONS"
    allowed = r.headers["access-control-allow-headers"]
    for name in ("Authorization", "Content-Type", "Idempotency-Key", "If-None-Match", "X-Request-ID"):
        assert name in allowed


async def test_responses_expose_headers_without_credentials(async_test_client):
    # Even for an origin the app-wide policy trusts (with credentials), v1
    # answers with the public policy.
    r = await async_test_client.get(
        "/api/v1/openapi.json", headers={"Origin": "https://what-a-benger.net"}
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in r.headers
    exposed = r.headers["access-control-expose-headers"]
    for name in ("ETag", "X-RateLimit-Remaining", "X-Request-ID", "Retry-After", "Idempotent-Replayed"):
        assert name in exposed
    assert r.headers["x-api-version"] == "1"
    assert r.headers["x-request-id"]
    # Errors carry the headers too.
    r = await async_test_client.get("/api/v1/me", headers={"Origin": ORIGIN})
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "*"


async def test_other_paths_keep_the_app_wide_policy(async_test_client):
    # Outside production the app-wide policy admits the local dev hosts only
    # (app.core.config.DEV_CORS_ORIGIN_REGEX); a production host, and in
    # particular the storage host, never gets a credentialed grant.
    r = await async_test_client.options(
        "/api/projects",
        headers={"Origin": "http://benger.localhost", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers["access-control-allow-origin"] == "http://benger.localhost"
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "x-api-version" not in r.headers
    for origin in ("https://what-a-benger.net", "https://storage.what-a-benger.net"):
        r = await async_test_client.options(
            "/api/projects",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in r.headers
    r = await async_test_client.options(
        "/api/projects",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") != "*"


async def test_deprecated_operation_announces_its_sunset(async_test_client, monkeypatch):
    monkeypatch.setitem(_middleware._SUNSETS, "GET /api/v1/openapi.json", "2027-06-30")
    r = await async_test_client.get("/api/v1/openapi.json")
    assert r.headers["x-api-deprecated"] == "true; sunset=2027-06-30"
    r = await async_test_client.get("/api/v1/docs")
    assert "x-api-deprecated" not in r.headers
