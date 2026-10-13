"""An email verification token presented as a Bearer session token is
rejected by ``require_user`` (compliance prep, 2026-10-13).

Both token kinds are signed with SECRET_KEY; the ``typ`` claim (and the
verification token's ``purpose`` claim) keep them apart on every route.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from auth_module.service import create_access_token
from auth_module.user_service import get_password_hash
from models import User as DBUser


def _verification_token(user_id: str, email: str) -> str:
    with patch("auth_module.email_verification.EmailService"):
        from auth_module.email_verification import EmailVerificationService

        return EmailVerificationService().generate_verification_token(user_id, email)


@pytest.fixture
def db_user(test_db: Session) -> DBUser:
    user = DBUser(
        id="typ-test-user-id",
        username="typuser",
        email="typ@integration.com",
        name="Typ Test User",
        hashed_password=get_password_hash("testpassword123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.mark.integration
class TestVerificationTokenIsNoSessionToken:
    def test_verification_token_as_bearer_is_rejected(self, client, db_user):
        token = _verification_token(db_user.id, db_user.email)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        # Rejected by the verifier itself, before any user lookup.
        assert resp.json()["detail"] == "Could not validate credentials"

    def test_verification_token_as_cookie_is_rejected(self, client, db_user):
        token = _verification_token(db_user.id, db_user.email)
        client.cookies.set("access_token", token)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Could not validate credentials"

    def test_access_token_still_authenticates(self, client, db_user):
        token = create_access_token({"user_id": db_user.id, "sub": db_user.username})
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == db_user.id
