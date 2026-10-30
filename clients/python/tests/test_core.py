from __future__ import annotations

import httpx
import pytest
from conftest import BASE, KEY

from benger_client import (
    DEFAULT_BASE_URL,
    AuthenticationError,
    BengerAPIError,
    BengerClient,
    BengerError,
    BengerTimeoutError,
    InsufficientScopeError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
    mask_key,
    wait_until,
)

# -- configuration and key masking ------------------------------------------ #


def test_key_and_base_url_from_env(monkeypatch):
    monkeypatch.setenv("BENGER_API_KEY", KEY)
    monkeypatch.setenv("BENGER_BASE_URL", "https://example.org/api/")
    with BengerClient() as c:
        assert c.base_url == "https://example.org"


def test_default_base_url(monkeypatch):
    monkeypatch.delenv("BENGER_BASE_URL", raising=False)
    with BengerClient(api_key=KEY) as c:
        assert c.base_url == DEFAULT_BASE_URL == "https://api.what-a-benger.net"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("BENGER_API_KEY", raising=False)
    with pytest.raises(BengerError, match="BENGER_API_KEY"):
        BengerClient()


def test_key_is_masked_everywhere(client, router):
    secret = KEY.split("_")[-1]
    assert mask_key(KEY) == "bgr_test_k3Yx9Q2a_***"
    assert mask_key("some-session-token") == "***"
    assert secret not in repr(client)
    assert "bgr_test_k3Yx9Q2a_***" in repr(client)
    assert secret not in str(vars(client))
    router.add("GET", "/api/v1/me", lambda r: httpx.Response(401, json={"error": {
        "code": "invalid_api_key", "message": "bad key", "request_id": "r1", "details": {}}}))
    with pytest.raises(AuthenticationError) as exc:
        client.me()
    assert secret not in str(exc.value) and secret not in repr(exc.value)
    # The key does reach the API in the header.
    assert router.calls[0].headers["Authorization"] == f"Bearer {KEY}"


def test_refuses_foreign_absolute_url(client):
    with pytest.raises(BengerError, match="Refusing"):
        client.get("https://evil.example/api/v1/me")


def test_absolute_url_on_same_host(client, router):
    router.add("GET", "/api/v1/me", {"principal": {}})
    assert client.get(BASE + "/api/v1/me") == {"principal": {}}


# -- error parsing ----------------------------------------------------------- #


def test_v1_error_envelope(client, router):
    router.add("GET", "/api/v1/projects/p1", lambda r: httpx.Response(403, json={"error": {
        "code": "insufficient_scope", "message": "This API key lacks the scope(s): projects:read",
        "request_id": "req-1", "details": {"required_scopes": ["projects:read"]}}}))
    with pytest.raises(InsufficientScopeError) as exc:
        client.projects.get("p1")
    err = exc.value
    assert (err.status, err.code, err.request_id) == (403, "insufficient_scope", "req-1")
    assert err.required_scopes == ["projects:read"]
    assert err.method == "GET" and err.url == BASE + "/api/v1/projects/p1"


def test_full_api_detail_dict(client, router):
    router.add("POST", "/api/evaluations/run", lambda r: httpx.Response(
        403,
        json={"detail": {"code": "insufficient_scope", "message": "lacks evaluations:run",
                         "required_scopes": ["evaluations:run"]}},
        headers={"X-Request-ID": "hdr-id"},
    ))
    with pytest.raises(InsufficientScopeError) as exc:
        client.post("/api/evaluations/run", json={})
    assert exc.value.required_scopes == ["evaluations:run"]
    assert exc.value.details == {"required_scopes": ["evaluations:run"]}
    assert exc.value.request_id == "hdr-id"


def test_full_api_detail_string(client, router):
    router.add("GET", "/api/projects/x", lambda r: httpx.Response(
        404, json={"detail": "Project not found"}))
    with pytest.raises(NotFoundError) as exc:
        client.projects.get("x", full=True)
    assert (exc.value.code, exc.value.message) == ("not_found", "Project not found")


def test_fastapi_validation_list(client, router):
    router.add("POST", "/api/custom-models/", lambda r: httpx.Response(422, json={"detail": [
        {"loc": ["body", "base_url"], "msg": "Field required", "type": "missing"}]}))
    with pytest.raises(ValidationError) as exc:
        client.post("/api/custom-models/", json={})
    assert exc.value.code == "validation_error"
    assert "base_url: Field required" in exc.value.message
    assert exc.value.details["errors"][0]["type"] == "missing"


def test_non_json_error(client, router):
    router.add("GET", "/api/x", lambda r: httpx.Response(502, text="Bad Gateway"))
    client.max_retries = 0
    with pytest.raises(ServerError) as exc:
        client.get("/api/x")
    assert exc.value.code == "server_error" and exc.value.message == "Bad Gateway"


def test_api_key_not_allowed_here(client, router):
    router.add("POST", "/api/auth/login", lambda r: httpx.Response(401, json={"detail": {
        "code": "api_key_not_allowed_here", "message": "Access keys cannot call this route"}}))
    with pytest.raises(AuthenticationError) as exc:
        client.post("/api/auth/login", json={})
    assert exc.value.code == "api_key_not_allowed_here"


# -- retries ----------------------------------------------------------------- #


def test_429_retries_with_retry_after(client, router, sleeps):
    answers = iter([
        httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {
            "code": "rate_limited", "message": "slow down", "request_id": "a", "details": {}}}),
        httpx.Response(429, headers={"Retry-After": "2"}, json={"detail": {
            "code": "rate_limited", "message": "slow down"}}),
        httpx.Response(200, json={"ok": True}),
    ])
    router.add("POST", "/api/evaluations/run", lambda r: next(answers))
    assert client.post("/api/evaluations/run", json={"project_id": "p"}) == {"ok": True}
    assert sleeps == [7.0, 2.0]
    assert len(router.calls) == 3


def test_429_gives_up_after_max_retries(client, router, sleeps):
    client.max_retries = 2
    router.add("GET", "/api/v1/me", lambda r: httpx.Response(
        429, headers={"Retry-After": "1"},
        json={"error": {"code": "rate_limited", "message": "m", "request_id": "x"}}))
    with pytest.raises(RateLimitError) as exc:
        client.me()
    assert exc.value.retry_after == 1.0
    assert len(router.calls) == 3 and sleeps == [1.0, 1.0]


def test_5xx_retried_for_get_only(client, router, sleeps):
    answers = iter([httpx.Response(503), httpx.Response(200, json=[1])])
    router.add("GET", "/api/runs", lambda r: next(answers))
    assert client.get("/api/runs", params={"type": "generation"}) == [1]
    assert len(sleeps) == 1

    router.add("POST", "/api/projects/", lambda r: httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(ServerError):
        client.post("/api/projects/", json={"title": "t"})
    assert sum(1 for r in router.calls if r.method == "POST") == 1


def test_transport_error_retried_for_get(router, sleeps):
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"principal": {}})

    with BengerClient(api_key=KEY, base_url=BASE, transport=httpx.MockTransport(handler)) as c:
        c._sleep = sleeps.append
        assert c.me() == {"principal": {}}
    assert state["n"] == 2


# -- idempotency ------------------------------------------------------------- #


def test_v1_posts_carry_idempotency_key_stable_across_retries(client, router, sleeps):
    answers = iter([httpx.Response(503), httpx.Response(202, json={"id": "e1", "status": "pending"})])
    router.add("POST", "/api/v1/projects/p1/exports", lambda r: next(answers))
    assert client.exports.create("p1")["id"] == "e1"
    keys = [r.headers.get("Idempotency-Key") for r in router.calls]
    assert keys[0] and keys[0] == keys[1]  # retried because the key makes it safe


def test_explicit_idempotency_key_and_full_api_posts(client, router):
    router.add("POST", "/api/v1/projects/p1/exports", {"id": "e1", "status": "pending"})
    router.add("POST", "/api/projects/", {"id": "p2"})
    client.exports.create("p1", idempotency_key="nightly-2026-10-30")
    client.projects.create("T")
    assert router.calls[0].headers["Idempotency-Key"] == "nightly-2026-10-30"
    assert "Idempotency-Key" not in router.calls[1].headers


# -- pagination and generic calls ------------------------------------------- #


def test_v1_pagination(client, router):
    def handler(request):
        cursor = request.url.params.get("cursor")
        assert request.url.params["limit"] == "2"
        if cursor is None:
            return httpx.Response(200, json={"items": [{"id": 1}, {"id": 2}], "next_cursor": "c2"})
        if cursor == "c2":
            return httpx.Response(200, json={"items": [{"id": 3}], "next_cursor": None})
        return httpx.Response(400, json={"error": {"code": "invalid_cursor", "message": "x"}})

    router.add("GET", "/api/v1/projects", handler)
    assert [p["id"] for p in client.projects.list(limit=2)] == [1, 2, 3]
    router.add("GET", "/api/v1/projects/p1/tasks", handler)
    assert len(client.tasks.list("p1", limit=2)) == 3


def test_generic_request_shapes(client, router):
    router.add("DELETE", "/api/generation/g1", lambda r: httpx.Response(204))
    router.add("GET", "/api/text", lambda r: httpx.Response(200, text="hello"))
    router.add("GET", "/api/redirect", lambda r: httpx.Response(302, headers={"Location": "https://s3/x"}))
    assert client.delete("/api/generation/g1") is None
    assert client.get("/api/text") == "hello"
    assert client.get("/api/redirect") == {"status": 302, "location": "https://s3/x"}


def test_none_params_dropped(client, router):
    router.add("GET", "/api/generation-tasks/projects/p/task-status", {"tasks": []})
    client.generation.task_status("p", status_filter=None)
    assert "status_filter" not in router.calls[0].url.params


def test_error_is_api_error_subclass():
    assert issubclass(InsufficientScopeError, BengerAPIError)


# -- wait_until --------------------------------------------------------------- #


def test_wait_until_returns_and_times_out():
    now = {"t": 0.0}

    def clock():
        return now["t"]

    def sleep(s):
        now["t"] += s

    values = iter([None, 0, {"done": 1}])
    assert wait_until(lambda: next(values), timeout=60, interval=1, sleep=sleep, clock=clock) == {
        "done": 1
    }
    with pytest.raises(BengerTimeoutError) as exc:
        wait_until(lambda: [], timeout=10, interval=3, sleep=sleep, clock=clock)
    assert exc.value.last_value == []
