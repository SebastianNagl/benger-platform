"""Every JWT signed with SECRET_KEY names its kind in ``typ`` and is accepted
by its own verifier only (compliance prep, 2026-10-13).

- session access tokens carry ``typ="access"``; ``verify_token``,
  ``verify_token_cookie_or_header`` and ``verify_token_for_websocket`` reject
  any other ``typ`` and any payload carrying a ``purpose`` claim,
- email verification tokens carry ``typ="email_verification"`` and are
  accepted by ``validate_verification_token`` only,
- a MISSING ``typ`` is tolerated by both verifiers for one release (tokens
  issued before the change keep working across the deploy).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from auth_module import (
    ACCESS_TOKEN_TYP,
    WebSocketAuthError,
    create_access_token,
    token_typ_accepted,
    verify_token,
    verify_token_cookie_or_header,
    verify_token_for_websocket,
)
from auth_module.config import ALGORITHM, SECRET_KEY


def _sign(payload: dict) -> str:
    """A token signed like the platform signs them, with an arbitrary payload."""
    body = {"exp": datetime.now(timezone.utc) + timedelta(minutes=5), **payload}
    return jose_jwt.encode(body, SECRET_KEY, algorithm=ALGORITHM)


def _verification_token(user_id: str = "u-1", email: str = "u@test.com") -> str:
    with patch("auth_module.email_verification.EmailService"):
        from auth_module.email_verification import EmailVerificationService

        return EmailVerificationService().generate_verification_token(user_id, email)


def _request(*, cookie: str = None, bearer: str = None) -> Mock:
    request = Mock()
    request.cookies = {"access_token": cookie} if cookie else {}
    request.headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return request


def _websocket(*, cookie: str = None, bearer: str = None) -> Mock:
    websocket = Mock()
    websocket.cookies = {"access_token": cookie} if cookie else {}
    websocket.headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return websocket


@pytest.mark.unit
class TestAccessTokenTyp:
    def test_access_token_carries_typ(self):
        token = create_access_token({"user_id": "u-1"})
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["typ"] == ACCESS_TOKEN_TYP == "access"

    def test_caller_cannot_mint_another_kind_through_the_access_factory(self):
        token = create_access_token({"user_id": "u-1", "typ": "email_verification"})
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["typ"] == "access"

    def test_verify_token_accepts_access_token(self):
        payload = verify_token(create_access_token({"user_id": "u-1"}))
        assert payload["user_id"] == "u-1"

    def test_verify_token_tolerates_missing_typ_for_one_release(self):
        # Tokens issued before 2026-10-13 carry no typ; the grace keeps them
        # valid for their remaining lifetime. Drop this test (and the grace)
        # when typ becomes mandatory next release.
        payload = verify_token(_sign({"user_id": "u-1"}))
        assert payload["user_id"] == "u-1"

    @pytest.mark.parametrize("typ", ["email_verification", "refresh", "", "ACCESS"])
    def test_verify_token_rejects_other_typ(self, typ):
        with pytest.raises(HTTPException) as exc:
            verify_token(_sign({"user_id": "u-1", "typ": typ}))
        assert exc.value.status_code == 401

    def test_verify_token_rejects_purpose_claim_even_without_typ(self):
        with pytest.raises(HTTPException) as exc:
            verify_token(_sign({"user_id": "u-1", "purpose": "email_verification"}))
        assert exc.value.status_code == 401

    def test_verify_token_rejects_email_verification_token(self):
        with pytest.raises(HTTPException) as exc:
            verify_token(_verification_token())
        assert exc.value.status_code == 401

    def test_verify_token_expected_typ_is_honoured(self):
        token = _sign({"user_id": "u-1", "typ": "other"})
        assert verify_token(token, expected_typ="other")["user_id"] == "u-1"
        with pytest.raises(HTTPException):
            verify_token(create_access_token({"user_id": "u-1"}), expected_typ="other")

    def test_token_typ_accepted_matrix(self):
        assert token_typ_accepted({"typ": "access"}, "access")
        assert token_typ_accepted({}, "access")  # one-release grace
        assert not token_typ_accepted({"typ": "email_verification"}, "access")
        assert not token_typ_accepted({"purpose": "email_verification"}, "access")
        assert not token_typ_accepted({"typ": "access", "purpose": "x"}, "access")


@pytest.mark.unit
class TestCookieHeaderAndWebSocketVerifiers:
    def test_cookie_verifier_rejects_verification_token_in_cookie(self):
        with pytest.raises(HTTPException) as exc:
            verify_token_cookie_or_header(_request(cookie=_verification_token()))
        assert exc.value.status_code == 401

    def test_cookie_verifier_rejects_verification_token_as_bearer(self):
        with pytest.raises(HTTPException) as exc:
            verify_token_cookie_or_header(_request(bearer=_verification_token()))
        assert exc.value.status_code == 401

    def test_cookie_verifier_accepts_access_token(self):
        token = create_access_token({"user_id": "u-1"})
        assert verify_token_cookie_or_header(_request(bearer=token))["user_id"] == "u-1"
        assert verify_token_cookie_or_header(_request(cookie=token))["user_id"] == "u-1"

    def test_websocket_verifier_rejects_verification_token(self):
        with pytest.raises(WebSocketAuthError):
            verify_token_for_websocket(_websocket(cookie=_verification_token()))
        with pytest.raises(WebSocketAuthError):
            verify_token_for_websocket(_websocket(bearer=_verification_token()))

    def test_websocket_verifier_rejects_other_typ_and_accepts_access(self):
        with pytest.raises(WebSocketAuthError):
            verify_token_for_websocket(_websocket(bearer=_sign({"user_id": "u", "typ": "x"})))
        token = create_access_token({"user_id": "u-1"})
        assert verify_token_for_websocket(_websocket(cookie=token))["user_id"] == "u-1"
        # Legacy token without typ: accepted during the grace release.
        assert verify_token_for_websocket(_websocket(cookie=_sign({"user_id": "u-1"})))


@pytest.mark.unit
class TestEmailVerificationTokenTyp:
    def _service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService

            return EmailVerificationService()

    def test_verification_token_carries_its_own_typ(self):
        import jwt as pyjwt

        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        token = self._service().generate_verification_token("u-1", "u@test.com")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["typ"] == "email_verification"
        assert payload["purpose"] == "email_verification"

    def test_validator_accepts_its_own_token(self):
        svc = self._service()
        token = svc.generate_verification_token("u-1", "u@test.com")
        assert svc.validate_verification_token(token) == ("u-1", "u@test.com")

    def test_validator_tolerates_missing_typ_for_one_release(self):
        # Links mailed before 2026-10-13 carry only the purpose claim and
        # stay valid for up to 48 hours; drop with the grace next release.
        token = _sign({"user_id": "u-1", "email": "u@test.com", "purpose": "email_verification"})
        assert self._service().validate_verification_token(token) == ("u-1", "u@test.com")

    def test_validator_rejects_foreign_typ(self):
        token = _sign(
            {"user_id": "u-1", "email": "u@test.com", "purpose": "email_verification", "typ": "access"}
        )
        assert self._service().validate_verification_token(token) is None

    def test_validator_rejects_session_access_token(self):
        token = create_access_token({"user_id": "u-1", "email": "u@test.com"})
        assert self._service().validate_verification_token(token) is None
