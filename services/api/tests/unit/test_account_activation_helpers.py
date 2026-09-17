"""Unit tests for the shared account-activation helpers (LTI "Konto
aktivieren" flow): eligibility matrix, token mint/reuse semantics, the
host-aware link builder, and the account-link proof helpers (proven
address, masking, confirmation link, mail language, mail eligibility)."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from account_activation import (
    ACCOUNT_LINK_TOKEN_EXPIRY,
    ACTIVATION_TOKEN_EXPIRY,
    EMAIL_METHOD_LMS_CLAIM,
    UNPROVEN_EMAIL_METHODS,
    account_link_mail_eligibility,
    activation_eligibility,
    build_account_link_url,
    build_activation_link,
    clean_display_name,
    current_or_new_activation_token,
    email_is_routable,
    email_ownership_proven,
    issue_activation_token,
    mail_language_for,
    mask_email,
    verify_email_by_link,
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


    def test_issue_without_target_drops_a_parked_address(self):
        """The pending address always belongs to the current token."""
        u = _user(email="erika@uni-x.de", pending_activation_email="parked@uni-y.de")
        issue_activation_token(u, now=NOW)
        assert u.pending_activation_email is None

    def test_token_of_a_parked_address_is_not_reused(self):
        """That token was mailed to the parked address, not to user.email."""
        u = _user(
            email="erika@uni-x.de",
            password_reset_token="mailed-to-parked",
            password_reset_expires=NOW + timedelta(days=5),
            pending_activation_email="parked@uni-y.de",
        )
        token = current_or_new_activation_token(u, now=NOW)
        assert token != "mailed-to-parked"
        assert u.password_reset_token == token
        assert u.pending_activation_email is None

    def test_token_with_a_day_or_less_left_is_not_reused(self):
        """A 24 h password-reset token never travels in a 7-day mail."""
        for left in (timedelta(hours=24), timedelta(hours=2)):
            u = _user(
                password_reset_token="reset-token",
                password_reset_expires=NOW + left,
            )
            token = current_or_new_activation_token(u, now=NOW)
            assert token != "reset-token"
            assert u.password_reset_expires == NOW + ACTIVATION_TOKEN_EXPIRY


class TestLinkBuilder:
    def test_link_uses_brand_frontend_url(self):
        brand = SimpleNamespace(frontend_url="https://vertretbar.net")
        assert build_activation_link(brand, "tok123") == (
            "https://vertretbar.net/activate/tok123"
        )


class TestEmailOwnershipProven:
    """Only a mailbox the account holder proved counts for the email proof
    of an account link (D6). An LMS claim, a provisioning stamp or an org
    admin's "verify" click prove nothing about who reads the mailbox."""

    def _verified(self, **overrides):
        base = dict(
            email="owner@uni-x.de",
            email_verified=True,
            email_verification_method="self",
        )
        base.update(overrides)
        return _user(**base)

    def test_self_verified_routable_address_is_proven(self):
        assert email_ownership_proven(self._verified()) is True

    def test_activation_and_reset_links_prove_the_address(self):
        assert email_ownership_proven(self._verified(email_verification_method="activation"))

    def test_legacy_verified_row_without_method_counts_as_self(self):
        assert email_ownership_proven(self._verified(email_verification_method=None))

    def test_unverified_address_is_not_proven(self):
        assert email_ownership_proven(self._verified(email_verified=False)) is False

    def test_unproven_methods_never_count(self):
        assert UNPROVEN_EMAIL_METHODS == {"system", "lti_claim", "admin"}
        assert EMAIL_METHOD_LMS_CLAIM == "lti_claim"
        for method in ("system", "lti_claim", "admin", " Admin "):
            user = self._verified(email_verification_method=method)
            assert email_ownership_proven(user) is False, method

    def test_unroutable_address_is_not_proven(self):
        user = self._verified(email="lti-x@lti.invalid")
        assert email_ownership_proven(user) is False

    def test_missing_user_is_not_proven(self):
        assert email_ownership_proven(None) is False


class TestMaskEmail:
    def test_keeps_two_characters_and_the_domain(self):
        assert mask_email("student@uni-x.de") == "st…@uni-x.de"

    def test_short_local_part_keeps_one_character(self):
        assert mask_email("ab@uni-x.de") == "a…@uni-x.de"
        assert mask_email("a@uni-x.de") == "a…@uni-x.de"

    def test_never_returns_the_full_local_part(self):
        masked = mask_email("abc@uni-x.de")
        assert "abc" not in masked

    def test_empty_and_domainless_values(self):
        assert mask_email(None) == ""
        assert mask_email("") == ""
        assert mask_email("nodomain") == "no…"


class TestAccountLinkUrl:
    def test_points_at_the_confirmation_page(self):
        assert build_account_link_url("https://what-a-benger.net", "tok") == (
            "https://what-a-benger.net/lti/link-confirm/tok"
        )

    def test_trailing_slash_on_the_base_is_dropped(self):
        assert build_account_link_url("http://benger.localhost/", "tok") == (
            "http://benger.localhost/lti/link-confirm/tok"
        )

    def test_token_lifetime_is_a_day(self):
        assert ACCOUNT_LINK_TOKEN_EXPIRY == timedelta(hours=24)


class TestMailLanguage:
    def test_german_by_default(self):
        assert mail_language_for(_user()) == "de"

    def test_supported_preference_wins(self):
        assert mail_language_for(_user(language_preference="en")) == "en"
        assert mail_language_for(_user(language_preference="en-US")) == "en"
        assert mail_language_for(_user(language_preference="DE")) == "de"

    def test_unsupported_or_blank_preference_falls_back(self):
        assert mail_language_for(_user(language_preference="fr")) == "de"
        assert mail_language_for(_user(language_preference="")) == "de"
        assert mail_language_for(_user(language_preference=None), default="en") == "en"


class TestCleanDisplayName:
    def test_collapses_line_breaks_and_whitespace(self):
        assert clean_display_name("  Moodle\n\nKurs\tA  ") == "Moodle Kurs A"

    def test_cuts_long_names(self):
        cleaned = clean_display_name("x" * 500)
        assert len(cleaned) == 120
        assert cleaned.endswith("…")

    def test_empty_values(self):
        assert clean_display_name(None) == ""
        assert clean_display_name("   ") == ""


class TestAccountLinkMailEligibility:
    def _eligible(self, **overrides):
        base = dict(
            email="owner@uni-x.de",
            email_verified=True,
            email_verification_method="self",
            is_superadmin=False,
            anonymized_at=None,
        )
        base.update(overrides)
        return _user(**base)

    def test_proven_active_account_is_eligible(self):
        assert account_link_mail_eligibility(self._eligible()) is None

    def test_accounts_with_a_password_are_eligible_too(self):
        user = self._eligible(hashed_password="hash", password_set=True)
        assert account_link_mail_eligibility(user) is None

    def test_skip_reasons(self):
        cases = [
            (None, "user_not_found"),
            (self._eligible(is_active=False), "user_inactive"),
            (self._eligible(anonymized_at=NOW), "user_anonymized"),
            (self._eligible(is_superadmin=True), "not_linkable"),
            (self._eligible(email="x@lti.invalid"), "email_not_routable"),
            (self._eligible(email_verified=False), "email_not_proven"),
            (self._eligible(email_verification_method="admin"), "email_not_proven"),
        ]
        for user, reason in cases:
            assert account_link_mail_eligibility(user) == reason

    def test_superadmin_is_refused_even_with_a_proven_address(self):
        user = self._eligible(is_superadmin=True, email_verification_method="self")
        assert account_link_mail_eligibility(user) == "not_linkable"


class TestVerifyEmailByLink:
    """Using an activation or reset link proves the address it went to."""

    def _lms(self, **overrides):
        values = dict(
            email_verified=False,
            email_verification_method=EMAIL_METHOD_LMS_CLAIM,
            email_verified_at=None,
        )
        values.update(overrides)
        return _user(**values)

    def test_unverified_lms_address_is_verified(self):
        user = self._lms()
        assert verify_email_by_link(user, method="activation", now=NOW) is True
        assert (user.email_verified, user.email_verification_method) == (
            True,
            "activation",
        )
        assert user.email_verified_at == NOW

    def test_verified_lms_claim_is_restamped(self):
        """Migration 106 keeps the verified flag of older LMS accounts and
        only marks the method; the link still has to prove the address."""
        old = NOW - timedelta(days=90)
        user = self._lms(email_verified=True, email_verified_at=old)
        assert verify_email_by_link(user, method="self", now=NOW) is True
        assert (user.email_verified, user.email_verification_method) == (True, "self")
        assert user.email_verified_at == NOW

    def test_method_match_ignores_case_and_spaces(self):
        user = self._lms(email_verified=True, email_verification_method=" LTI_Claim ")
        assert verify_email_by_link(user, method="activation", now=NOW) is True
        assert user.email_verification_method == "activation"

    def test_proven_addresses_are_left_alone(self):
        old = NOW - timedelta(days=90)
        for method in ("self", "activation", "admin", "system", None):
            user = self._lms(
                email_verified=True,
                email_verification_method=method,
                email_verified_at=old,
            )
            assert verify_email_by_link(user, method="activation", now=NOW) is False
            assert user.email_verification_method == method
            assert user.email_verified_at == old

    def test_parked_pending_address_blocks(self):
        user = self._lms(email_verified=True, pending_activation_email="new@uni-x.de")
        assert verify_email_by_link(user, method="activation", now=NOW) is False
        assert user.email_verification_method == EMAIL_METHOD_LMS_CLAIM

    def test_unroutable_address_is_not_verified(self):
        user = self._lms(email="lti-x@lti.invalid")
        assert verify_email_by_link(user, method="activation", now=NOW) is False
        assert user.email_verified is False
