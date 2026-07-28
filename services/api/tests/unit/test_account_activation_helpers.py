"""Unit tests for the shared account-activation helpers (LTI "Konto
aktivieren" flow): eligibility matrix, token mint/reuse semantics, and the
host-aware link builder."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from account_activation import (
    ACTIVATION_TOKEN_EXPIRY,
    activation_eligibility,
    build_activation_link,
    current_or_new_activation_token,
    email_is_routable,
    issue_activation_token,
)

NOW = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def _user(**overrides):
    defaults = dict(
        id=str(uuid.uuid4()),
        is_active=True,
        hashed_password=None,
        password_set=False,
        email="student@uni-x.de",
        password_reset_token=None,
        password_reset_expires=None,
        pending_activation_email=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestEmailRoutable:
    def test_real_addresses_routable(self):
        assert email_is_routable("a@uni-x.de") is True

    def test_synthetic_lti_addresses_not_routable(self):
        assert email_is_routable("lti-abc123@lti.invalid") is False
        assert email_is_routable("x@sub.something.invalid") is False

    def test_empty_not_routable(self):
        assert email_is_routable(None) is False
        assert email_is_routable("") is False


class TestEligibility:
    def test_fresh_passwordless_real_email_is_eligible(self):
        assert activation_eligibility(_user(), now=NOW) is None

    def test_password_holder_skipped(self):
        assert (
            activation_eligibility(_user(hashed_password="hash"), now=NOW)
            == "already_has_password"
        )

    def test_password_set_flag_skipped(self):
        assert (
            activation_eligibility(_user(password_set=True), now=NOW)
            == "password_already_set"
        )

    def test_inactive_user_skipped(self):
        assert activation_eligibility(_user(is_active=False), now=NOW) == "user_inactive"

    def test_synthetic_email_skipped_without_target(self):
        u = _user(email="lti-x@lti.invalid")
        assert activation_eligibility(u, now=NOW) == "email_not_routable"

    def test_synthetic_email_with_routable_target_is_eligible(self):
        u = _user(email="lti-x@lti.invalid")
        assert (
            activation_eligibility(u, target_email="real@uni-x.de", now=NOW) is None
        )

    def test_pending_token_is_not_a_skip_reason(self):
        u = _user(
            password_reset_token="tok",
            password_reset_expires=NOW + timedelta(days=1),
        )
        assert activation_eligibility(u, now=NOW) is None


class TestTokenMintAndReuse:
    def test_issue_sets_token_expiry_and_pending_email(self):
        u = _user(email="lti-x@lti.invalid")
        token = issue_activation_token(u, pending_email="real@uni-x.de", now=NOW)
        assert u.password_reset_token == token
        assert u.password_reset_expires == NOW + ACTIVATION_TOKEN_EXPIRY
        assert u.pending_activation_email == "real@uni-x.de"

    def test_valid_token_reused_for_auto_path_retries(self):
        u = _user(
            password_reset_token="existing-token",
            password_reset_expires=NOW + timedelta(days=3),
        )
        assert current_or_new_activation_token(u, now=NOW) == "existing-token"

    def test_expired_token_replaced(self):
        u = _user(
            password_reset_token="old",
            password_reset_expires=NOW - timedelta(hours=1),
        )
        token = current_or_new_activation_token(u, now=NOW)
        assert token != "old"
        assert u.password_reset_token == token

    def test_force_always_remints(self):
        u = _user(
            password_reset_token="old",
            password_reset_expires=NOW + timedelta(days=3),
        )
        token = current_or_new_activation_token(u, force=True, now=NOW)
        assert token != "old"

    def test_pending_email_change_remints(self):
        u = _user(
            email="lti-x@lti.invalid",
            password_reset_token="old",
            password_reset_expires=NOW + timedelta(days=3),
        )
        token = current_or_new_activation_token(
            u, pending_email="typo-fixed@uni-x.de", now=NOW
        )
        assert token != "old"
        assert u.pending_activation_email == "typo-fixed@uni-x.de"


class TestLinkBuilder:
    def test_link_uses_brand_frontend_url(self):
        brand = SimpleNamespace(frontend_url="https://vertretbar.net")
        assert build_activation_link(brand, "tok123") == (
            "https://vertretbar.net/activate/tok123"
        )
