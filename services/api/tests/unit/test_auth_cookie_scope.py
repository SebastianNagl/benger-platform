"""Auth cookies are host-only; legacy domain-wide cookies get expired.

The API never sends a Domain attribute on its auth cookies, so a browser
returns them to the exact host only (never to storage., staging., demo.
under the same apex). While LEGACY_COOKIE_DOMAIN is set, login, refresh and
logout also send Max-Age=0 copies for each legacy domain, ahead of the new
host-only cookies, so browsers drop the domain-wide cookies older releases
set.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from auth_module.auth_cookies import (
    SESSION_TOKEN_COOKIES,
    expire_legacy_cookies,
    legacy_cookie_domains,
)
from auth_module.session_origin import SESSION_ORIGIN_COOKIE

LEGACY = ".what-a-benger.net, .vertretbar.net"


@pytest.fixture
def legacy(monkeypatch):
    monkeypatch.setattr(get_settings(), "legacy_cookie_domain", LEGACY)


@pytest.fixture
def no_legacy(monkeypatch):
    monkeypatch.setattr(get_settings(), "legacy_cookie_domain", None)


def _set_cookies(response) -> list[str]:
    headers = response.headers
    getter = getattr(headers, "get_list", None) or headers.getlist
    return getter("set-cookie")


def _named(cookies, name):
    return [c for c in cookies if c.startswith(f"{name}=")]


def _has_domain(cookie: str) -> bool:
    return "domain=" in cookie.lower()


def _legacy(cookies):
    return [c for c in cookies if _has_domain(c)]


def _assert_legacy_clears(cookies, names):
    legacy = _legacy(cookies)
    assert len(legacy) == 2 * len(names)
    for name in names:
        for domain in (".what-a-benger.net", ".vertretbar.net"):
            [header] = [c for c in _named(legacy, name) if f"Domain={domain}" in c]
            assert "Max-Age=0" in header
            assert "Path=/" in header
            assert "SameSite=lax" in header


def _user():
    from models import User

    return User(
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


def _login():
    from main import app

    user = _user()
    tokens = Mock(access_token="a", refresh_token="r", token_type="bearer", expires_in=1800, user=user)
    with patch("routers.auth.session.authenticate_user", return_value=user), patch(
        "routers.auth.session.create_tokens_with_refresh", return_value=tokens
    ), patch("extensions.after_user_login"):
        resp = TestClient(app).post("/api/auth/login", json={"username": "test", "password": "pw"})
    assert resp.status_code == 200
    return _set_cookies(resp)


def _request(cookies=None):
    r = Mock()
    r.headers = {}
    r.cookies = cookies or {}
    r.client = Mock(host="127.0.0.1")
    return r


async def _refresh():
    from routers.auth import refresh_token_endpoint

    token_resp = Mock(access_token="new-access", refresh_token="new-refresh")
    response = Response()
    with patch("routers.auth.tokens.refresh_access_token", return_value=token_resp):
        await refresh_token_endpoint(
            request=_request({"refresh_token": "old"}), response=response, db=Mock()
        )
    return _set_cookies(response)


async def _logout():
    from routers.auth.tokens import logout

    response = Response()
    with patch(
        "services.refresh_token_service.revoke_refresh_token_async",
        new=AsyncMock(return_value=True),
    ):
        await logout(
            request=_request({"refresh_token": "old"}),
            response=response,
            current_user=Mock(),
            db=Mock(),
        )
    return _set_cookies(response)


async def _logout_all():
    from routers.auth.tokens import logout_all_devices

    response = Response()
    with patch(
        "services.refresh_token_service.revoke_user_tokens_async",
        new=AsyncMock(return_value=1),
    ):
        await logout_all_devices(current_user=Mock(id="u"), response=response, db=Mock())
    return _set_cookies(response)


# --- settings ---------------------------------------------------------------


def test_cookie_domain_is_gone_and_ignores_the_old_env(monkeypatch):
    # The deprecated attribute stays readable for overlays but is always
    # None, even when a deployment still carries COOKIE_DOMAIN.
    monkeypatch.setenv("COOKIE_DOMAIN", ".what-a-benger.net")
    monkeypatch.setenv("LEGACY_COOKIE_DOMAIN", ".what-a-benger.net")
    s = Settings()
    assert s.cookie_domain is None
    assert s.legacy_cookie_domain == ".what-a-benger.net"


def test_legacy_domains_parse_a_comma_list(monkeypatch):
    monkeypatch.setattr(get_settings(), "legacy_cookie_domain", " .a.net, ,.b.net,.a.net ")
    assert legacy_cookie_domains() == [".a.net", ".b.net"]


def test_no_legacy_domains_by_default(no_legacy):
    assert legacy_cookie_domains() == []
    response = Response()
    expire_legacy_cookies(response)
    assert _set_cookies(response) == []


def test_expire_legacy_cookies_marks_the_origin_cookie_readable(legacy):
    response = Response()
    expire_legacy_cookies(response)
    cookies = _set_cookies(response)
    _assert_legacy_clears(cookies, (*SESSION_TOKEN_COOKIES, SESSION_ORIGIN_COOKIE))
    for c in _named(cookies, SESSION_ORIGIN_COOKIE):
        assert "HttpOnly" not in c
    for name in SESSION_TOKEN_COOKIES:
        for c in _named(cookies, name):
            assert "HttpOnly" in c


# --- login ------------------------------------------------------------------


def test_login_cookies_are_host_only(no_legacy):
    cookies = _login()
    assert _named(cookies, "access_token") and _named(cookies, "refresh_token")
    assert not any(_has_domain(c) for c in cookies)
    [access] = _named(cookies, "access_token")
    assert "Max-Age=0" not in access
    assert "HttpOnly" in access
    assert "Path=/" in access
    assert "SameSite=lax" in access


def test_login_expires_legacy_cookies_before_the_new_ones(legacy):
    cookies = _login()
    _assert_legacy_clears(cookies, (*SESSION_TOKEN_COOKIES, SESSION_ORIGIN_COOKIE))
    host_only = [c for c in cookies if not _has_domain(c)]
    [access] = _named(host_only, "access_token")
    [refresh] = _named(host_only, "refresh_token")
    assert "Max-Age=0" not in access and "Max-Age=0" not in refresh
    last_legacy = max(i for i, c in enumerate(cookies) if _has_domain(c))
    assert cookies.index(access) > last_legacy
    assert cookies.index(refresh) > last_legacy


# --- refresh ----------------------------------------------------------------


async def test_refresh_cookies_are_host_only(no_legacy):
    cookies = await _refresh()
    assert len(cookies) == 2
    assert not any(_has_domain(c) for c in cookies)


async def test_refresh_expires_legacy_tokens_but_not_the_origin_marker(legacy):
    cookies = await _refresh()
    _assert_legacy_clears(cookies, SESSION_TOKEN_COOKIES)
    assert _named(cookies, SESSION_ORIGIN_COOKIE) == []
    host_only = [c for c in cookies if not _has_domain(c)]
    assert len(host_only) == 2
    last_legacy = max(i for i, c in enumerate(cookies) if _has_domain(c))
    assert all(cookies.index(c) > last_legacy for c in host_only)


# --- logout -----------------------------------------------------------------


async def test_logout_clears_host_only_cookies(no_legacy):
    cookies = await _logout()
    assert {c.split("=", 1)[0] for c in cookies} == {
        "access_token",
        "refresh_token",
        SESSION_ORIGIN_COOKIE,
    }
    assert all("Max-Age=0" in c for c in cookies)
    assert not any(_has_domain(c) for c in cookies)


async def test_logout_also_expires_legacy_cookies(legacy):
    cookies = await _logout()
    _assert_legacy_clears(cookies, (*SESSION_TOKEN_COOKIES, SESSION_ORIGIN_COOKIE))
    assert len([c for c in cookies if not _has_domain(c)]) == 3


async def test_logout_all_also_expires_legacy_cookies(legacy):
    cookies = await _logout_all()
    _assert_legacy_clears(cookies, (*SESSION_TOKEN_COOKIES, SESSION_ORIGIN_COOKIE))
    assert len([c for c in cookies if not _has_domain(c)]) == 3
