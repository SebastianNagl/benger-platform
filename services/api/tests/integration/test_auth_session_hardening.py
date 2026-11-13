"""Session hardening: refresh token rotation, reuse detection and tokens
kept out of browser-visible response bodies (real PostgreSQL).

* ``POST /api/auth/refresh`` rotates the refresh token on every call. The
  rotated token is dead once a short grace period has passed (it covers two
  tabs refreshing at the same moment); presenting it after that counts as
  reuse of a stolen token and revokes the whole token family, so the
  successor dies too. Refresh also refuses deactivated users.
* ``POST /api/auth/login`` and ``/refresh`` carry the tokens only in HttpOnly
  cookies. Scripts that need a bearer token use ``POST /api/auth/token``,
  which returns an access token in the body and sets no cookie.
* JWTs without a ``typ`` claim are no longer accepted.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from auth_module.config import ALGORITHM, SECRET_KEY
from models import RefreshToken, User
from services import refresh_token_service
from services.refresh_token_service import hash_token

ADMIN_LOGIN = {"username": "admin@test.com", "password": "admin123"}
CONTRIBUTOR_LOGIN = {"username": "contributor@test.com", "password": "contrib123"}


def _login(client, credentials=ADMIN_LOGIN):
    resp = client.post("/api/auth/login", json=credentials)
    assert resp.status_code == 200, resp.text
    refresh = resp.cookies.get("refresh_token")
    assert refresh
    return resp, refresh


def _refresh_with(client, refresh_token):
    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_token)
    return client.post("/api/auth/refresh")


def _row(test_db, plain):
    test_db.expire_all()
    return (
        test_db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(plain))
        .one()
    )


def _age_rotation(test_db, plain, seconds):
    row = _row(test_db, plain)
    row.rotated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    test_db.commit()


@pytest.mark.integration
class TestRefreshRotation:
    def test_refresh_issues_a_new_refresh_cookie(self, client, test_db, test_users):
        _, first = _login(client)

        resp = _refresh_with(client, first)

        assert resp.status_code == 200, resp.text
        second = resp.cookies.get("refresh_token")
        assert second and second != first
        old, new = _row(test_db, first), _row(test_db, second)
        assert old.is_active is False and old.rotated_at is not None
        assert new.is_active is True
        assert new.family_id == (old.family_id or old.id)

    def test_successor_keeps_rotating(self, client, test_db, test_users):
        _, first = _login(client)
        second = _refresh_with(client, first).cookies.get("refresh_token")

        resp = _refresh_with(client, second)

        assert resp.status_code == 200
        third = resp.cookies.get("refresh_token")
        assert third and third not in (first, second)

    def test_reuse_after_grace_revokes_the_family(self, client, test_db, test_users):
        _, first = _login(client)
        second = _refresh_with(client, first).cookies.get("refresh_token")
        _age_rotation(test_db, first, refresh_token_service.REFRESH_TOKEN_REUSE_GRACE_SECONDS + 5)

        reuse = _refresh_with(client, first)

        assert reuse.status_code == 401
        assert _row(test_db, second).is_active is False
        assert _refresh_with(client, second).status_code == 401

    def test_reuse_does_not_touch_other_sessions(self, client, test_db, test_users):
        _, first = _login(client)
        _, other_device = _login(client)
        _refresh_with(client, first)
        _age_rotation(test_db, first, refresh_token_service.REFRESH_TOKEN_REUSE_GRACE_SECONDS + 5)

        assert _refresh_with(client, first).status_code == 401

        assert _row(test_db, other_device).is_active is True
        assert _refresh_with(client, other_device).status_code == 200

    def test_concurrent_refresh_within_grace_keeps_the_session(
        self, client, test_db, test_users
    ):
        _, first = _login(client)
        second = _refresh_with(client, first).cookies.get("refresh_token")

        # A second tab still holding the old cookie refreshes a moment later.
        late = _refresh_with(client, first)

        assert late.status_code == 200
        assert late.cookies.get("access_token")
        # No new refresh token: the browser keeps the one the first call set.
        assert late.cookies.get("refresh_token") is None
        assert _row(test_db, second).is_active is True
        assert _refresh_with(client, second).status_code == 200

    def test_grace_ends_with_the_family(self, client, test_db, test_users):
        _, first = _login(client)
        second = _refresh_with(client, first).cookies.get("refresh_token")
        # Logout revokes the live token; the rotated one must not revive it.
        row = _row(test_db, second)
        row.is_active = False
        test_db.commit()

        assert _refresh_with(client, first).status_code == 401

    def test_refresh_refuses_a_deactivated_user(self, client, test_db, test_users):
        _, first = _login(client)
        user = test_db.query(User).filter(User.id == "admin-test-id").one()
        user.is_active = False
        test_db.commit()

        resp = _refresh_with(client, first)

        assert resp.status_code == 401
        assert resp.cookies.get("access_token") is None
        # The token was not rotated for the refused call.
        assert _row(test_db, first).rotated_at is None

    def test_unknown_token_401(self, client, test_db, test_users):
        assert _refresh_with(client, "not-a-real-token").status_code == 401


def _refresh_cookie_max_age(resp):
    header = next(
        h for h in resp.headers.get_list("set-cookie") if h.startswith("refresh_token=")
    )
    attrs = dict(
        part.strip().split("=", 1) for part in header.split(";")[1:] if "=" in part
    )
    return int(attrs["Max-Age"])


@pytest.mark.integration
class TestSessionLifetimeIsAbsolute:
    """Rotation keeps the 7-day limit from the password sign-in; it does not slide."""

    def test_refreshes_do_not_extend_the_session(self, client, test_db, test_users):
        _, first = _login(client)
        login_expiry = _row(test_db, first).expires_at
        assert abs(
            login_expiry - (datetime.now(timezone.utc) + timedelta(days=7))
        ) < timedelta(minutes=1)
        # Six days and 23 hours later: one hour of the session is left.
        row = _row(test_db, first)
        row.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        test_db.commit()
        session_end = row.expires_at

        current = first
        for _ in range(3):
            resp = _refresh_with(client, current)
            assert resp.status_code == 200, resp.text
            current = resp.cookies.get("refresh_token")
            assert _row(test_db, current).expires_at == session_end
            assert 0 < _refresh_cookie_max_age(resp) <= 3600

        # The hour is over: the session ends although it was refreshed.
        for plain in (first, current):
            row = _row(test_db, plain)
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        test_db.commit()

        assert _refresh_with(client, current).status_code == 401


@pytest.mark.integration
class TestTokensStayInCookies:
    def test_login_body_carries_no_tokens(self, client, test_db, test_users):
        resp, _ = _login(client)

        body = resp.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["user"]["id"] == "admin-test-id"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert resp.cookies.get("access_token")

    def test_refresh_body_carries_no_tokens(self, client, test_db, test_users):
        _, first = _login(client)

        body = _refresh_with(client, first).json()

        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["user"]["id"] == "admin-test-id"

    def test_token_endpoint_returns_bearer_token_without_cookies(
        self, client, test_db, test_users
    ):
        client.cookies.clear()
        resp = client.post("/api/auth/token", json=CONTRIBUTOR_LOGIN)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert "refresh_token" not in body
        assert body["user"]["id"] == "contributor-test-id"
        assert not resp.cookies
        assert "set-cookie" not in resp.headers

        client.cookies.clear()
        me = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["id"] == "contributor-test-id"

    def test_token_endpoint_wrong_password_401(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/token",
            json={"username": "contributor@test.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_token_endpoint_unverified_email_403(self, client, test_db, test_users):
        user = test_db.query(User).filter(User.id == "contributor-test-id").one()
        user.email_verified = False
        test_db.commit()

        resp = client.post("/api/auth/token", json=CONTRIBUTOR_LOGIN)

        assert resp.status_code == 403


@pytest.mark.integration
class TestTypClaimRequired:
    def _token(self, **claims):
        payload = {
            "sub": "admin@test.com",
            "user_id": "admin-test-id",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            **claims,
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    def test_token_without_typ_is_rejected(self, client, test_db, test_users):
        client.cookies.clear()
        resp = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {self._token()}"}
        )
        assert resp.status_code == 401

    def test_token_with_access_typ_is_accepted(self, client, test_db, test_users):
        client.cookies.clear()
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {self._token(typ='access')}"},
        )
        assert resp.status_code == 200
