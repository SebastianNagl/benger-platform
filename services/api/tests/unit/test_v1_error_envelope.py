"""The v1 error envelope applies to /api/v1 paths only."""

from fastapi import FastAPI, HTTPException, Query
from httpx import ASGITransport, AsyncClient

from middleware.api_usage import ApiUsageMiddleware
from routers.v1._errors import V1Error, _split_detail, install_v1_exception_handlers


def _shared_helper():
    """Stands in for a platform helper (routers/projects/helpers.py style)."""
    raise HTTPException(status_code=403, detail="Access denied")


def _app() -> FastAPI:
    app = FastAPI()
    install_v1_exception_handlers(app)
    app.add_middleware(ApiUsageMiddleware)

    @app.get("/api/v1/helper")
    def v1_helper():
        _shared_helper()

    @app.get("/api/helper")
    def browser_helper():
        _shared_helper()

    @app.get("/api/v1/coded")
    def coded():
        raise V1Error(409, "conflict_here", "Already there", thing_id="t1")

    @app.get("/api/v1/dict-detail")
    def dict_detail():
        raise HTTPException(
            status_code=403,
            detail={"code": "project_window_upcoming", "message": "Not open", "window_start_at": "x"},
            headers={"X-Extra": "1"},
        )

    @app.get("/api/v1/validated")
    def v1_validated(n: int = Query(...)):
        return {"n": n}

    @app.get("/api/validated")
    def browser_validated(n: int = Query(...)):
        return {"n": n}

    return app


async def _client():
    return AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t")


async def test_shared_helper_403_is_reshaped_on_v1_only():
    async with await _client() as c:
        r = await c.get("/api/v1/helper", headers={"X-Request-ID": "req-1"})
        assert r.status_code == 403
        assert r.json() == {
            "error": {
                "code": "forbidden",
                "message": "Access denied",
                "request_id": "req-1",
                "details": {},
            }
        }
        assert r.headers["x-request-id"] == "req-1"
        r = await c.get("/api/helper")
        assert r.status_code == 403
        assert r.json() == {"detail": "Access denied"}


async def test_v1_error_codes_and_details():
    async with await _client() as c:
        r = await c.get("/api/v1/coded")
        error = r.json()["error"]
        assert r.status_code == 409
        assert error["code"] == "conflict_here" and error["message"] == "Already there"
        assert error["details"] == {"thing_id": "t1"}
        # A generated request id is echoed in body and header.
        assert error["request_id"] == r.headers["x-request-id"]

        r = await c.get("/api/v1/dict-detail")
        assert r.json()["error"]["code"] == "project_window_upcoming"
        assert r.json()["error"]["details"] == {"window_start_at": "x"}
        assert r.headers["x-extra"] == "1"


async def test_validation_errors():
    async with await _client() as c:
        r = await c.get("/api/v1/validated", params={"n": "abc"})
        assert r.status_code == 422
        error = r.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"]["errors"][0]["loc"] == ["query", "n"]
        assert "input" not in error["details"]["errors"][0]
        r = await c.get("/api/validated", params={"n": "abc"})
        assert r.status_code == 422 and "detail" in r.json()


async def test_unknown_routes_on_the_main_app(async_test_client):
    r = await async_test_client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = await async_test_client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    r = await async_test_client.delete("/api/v1/me")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


async def test_unauthenticated_v1_request_uses_the_envelope(async_test_client):
    r = await async_test_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    r = await async_test_client.get(
        "/api/v1/me", headers={"Authorization": "Bearer bgr_test_nope_nope"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_api_key"


def test_split_detail_fallbacks():
    assert _split_detail(404, None) == ("not_found", "Not found", {})
    assert _split_detail(418, "teapot") == ("error", "teapot", {})
    assert _split_detail(400, {"message": "m"}) == ("bad_request", "m", {})
    assert _split_detail(400, {"detail": "d", "x": 1}) == ("bad_request", "d", {"x": 1})
