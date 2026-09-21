"""
Email lookups ignore case.

Signup stores the address lowercased, but people type it however they like
("T.Name@campus.lmu.de"). An exact match made login-by-email fail and made
the password-reset request silently send nothing, since that endpoint
answers the same way whether or not the address exists.
"""

from unittest.mock import AsyncMock, patch

import pytest

from auth_module.user_service import get_user_by_email, get_user_by_username_or_email
from models import User


@pytest.mark.integration
class TestEmailLookupCaseInsensitive:
    def test_get_user_by_email_ignores_case(self, test_db, test_users):
        user = get_user_by_email(test_db, "Admin@Test.COM")
        assert user is not None
        assert user.id == "admin-test-id"

    def test_get_user_by_username_or_email_ignores_email_case(self, test_db, test_users):
        user = get_user_by_username_or_email(test_db, " ADMIN@test.com ")
        assert user is not None
        assert user.id == "admin-test-id"

    def test_login_with_mixed_case_email(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "Admin@Test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["id"] == "admin-test-id"

    def test_password_reset_with_mixed_case_email_sends_mail(
        self, client, test_db, test_users
    ):
        with patch(
            "email_service.EmailService.send_password_reset_email",
            new=AsyncMock(return_value=True),
        ) as send:
            resp = client.post(
                "/api/auth/request-password-reset",
                json={"email": "Admin@Test.com"},
            )

        assert resp.status_code == 200
        send.assert_awaited_once()
        assert send.await_args.kwargs["to_email"] == "admin@test.com"
        test_db.expire_all()
        user = test_db.query(User).filter(User.id == "admin-test-id").first()
        assert user.password_reset_token is not None
