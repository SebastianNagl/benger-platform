"""The password login clears the LMS-launch session marker.

An overlay (the LTI launch) marks the sessions it opens with the readable
``benger_session_origin`` cookie so the onboarding tour stays quiet in them;
a regular sign-in must never inherit that mark.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from auth_module.session_origin import SESSION_ORIGIN_COOKIE, clear_session_origin
from fastapi import Response
from fastapi.testclient import TestClient
from main import app
from models import User


def _marker_headers(headers):
    return [c for c in headers if c.startswith(f"{SESSION_ORIGIN_COOKIE}=")]


def test_cookie_name_is_the_contract():
    # benger_extended/lti/consent.py sets it and the frontend reads it.
    assert SESSION_ORIGIN_COOKIE == "benger_session_origin"


def test_clear_session_origin_expires_a_readable_root_cookie():
    response = Response()
    clear_session_origin(response)
    [header] = _marker_headers(response.headers.getlist("set-cookie"))
    assert "Max-Age=0" in header
    assert "Path=/" in header
    assert "HttpOnly" not in header


def test_password_login_clears_the_marker():
    user = User(
        id="test-user",
        username="test",
        email="test@example.com",
        name="Test",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    tokens = Mock(access_token="a", refresh_token="r", token_type="bearer", expires_in=1800, user=user)
    with patch("routers.auth.session.authenticate_user", return_value=user), patch(
        "routers.auth.session.create_tokens_with_refresh", return_value=tokens
    ), patch("extensions.after_user_login"):
        client = TestClient(app)
        client.cookies.set(SESSION_ORIGIN_COOKIE, "lti")
        resp = client.post("/api/auth/login", json={"username": "test", "password": "pw"})

    assert resp.status_code == 200
    [header] = _marker_headers(resp.headers.get_list("set-cookie"))
    assert "Max-Age=0" in header


def test_failed_login_keeps_the_marker():
    with patch("routers.auth.session.authenticate_user", return_value=None):
        resp = TestClient(app).post("/api/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code == 401
    assert _marker_headers(resp.headers.get_list("set-cookie")) == []
