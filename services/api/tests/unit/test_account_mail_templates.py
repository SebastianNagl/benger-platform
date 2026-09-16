"""Rendered copy of the two LMS account mails (real templates, no mocks of
the Jinja environment).

- Account activation: sent after the student agreed through the learning
  platform; the copy says so and carries no em dash (ws11 §2c).
- Account-link confirmation: the email proof of D6. The subject is static,
  the body names the connection and the organization (escaped, since both
  are free text an org admin or an LMS chooses) and tells the reader to
  ignore the mail if it was not them.
"""

from unittest.mock import patch

import pytest
from jinja2 import TemplateNotFound

CONFIRM_URL = "https://what-a-benger.net/lti/link-confirm/tok-123"
ACTIVATION_URL = "https://what-a-benger.net/activate/tok-456"


@pytest.fixture
def service():
    with patch("mailer.email_service.SendGridClient"):
        from mailer.email_service import EmailService

        yield EmailService(check_feature_flag=False)


def _link_mail(service, **overrides):
    kwargs = dict(
        confirm_url=CONFIRM_URL,
        connection_name="Moodle Uni X",
        organization_name="Uni X",
        brand_name="BenGER",
        frontend_host="what-a-benger.net",
    )
    kwargs.update(overrides)
    return service.build_account_link_confirmation_email(**kwargs)


class TestAccountLinkConfirmationMail:
    def test_german_is_the_default(self, service):
        subject, body = _link_mail(service)

        assert subject == "Bestätige die Verknüpfung mit deinem BenGER-Konto"
        assert "„Moodle Uni X“" in body
        assert "der Organisation Uni X" in body
        assert "Wenn du das nicht warst, ignoriere diese E-Mail." in body
        assert "24 Stunden" in body
        assert f'href="{CONFIRM_URL}"' in body
        assert "what-a-benger.net" in body

    def test_english_variant(self, service):
        subject, body = _link_mail(service, language="en", expiry_hours=12)

        assert subject == "Confirm the link to your BenGER account"
        assert "the connection “Moodle Uni X”" in body
        assert "of the organization Uni X" in body
        assert "If this wasn’t you, ignore this email." in body
        assert "12 hours" in body
        assert CONFIRM_URL in body

    @pytest.mark.parametrize("language", ["de", "en"])
    def test_subject_never_carries_the_free_text_names(self, service, language):
        subject, _ = _link_mail(
            service,
            language=language,
            connection_name="Evil\r\nBcc: victim@example.com",
            organization_name="Org Name",
        )

        assert "Evil" not in subject
        assert "Org Name" not in subject
        assert "\n" not in subject and "\r" not in subject

    @pytest.mark.parametrize("language", ["de", "en"])
    def test_free_text_names_are_escaped(self, service, language):
        _, body = _link_mail(
            service,
            language=language,
            connection_name='<a href="https://evil.example">Klick</a>',
            organization_name="<script>alert(1)</script>",
        )

        assert "<script>" not in body
        assert '<a href="https://evil.example">' not in body
        assert "&lt;script&gt;" in body
        assert "&lt;a href=" in body

    def test_brand_parametrizes_the_copy(self, service):
        subject, body = _link_mail(
            service, brand_name="Lernhilfe", frontend_host="lernen.example"
        )

        assert "Lernhilfe-Konto" in subject
        assert "Lernhilfe-Konto auf lernen.example" in body
        assert "BenGER" not in subject + body

    @pytest.mark.parametrize("language", ["de", "en"])
    def test_missing_names_fall_back_to_neutral_wording(self, service, language):
        _, body = _link_mail(
            service, language=language, connection_name="", organization_name=""
        )

        assert "„“" not in body and "“”" not in body
        if language == "de":
            assert "Über eine Lernplattform-Verbindung wurde angefragt" in body
            assert "der Organisation" not in body
        else:
            assert "through a learning platform connection" in body
            assert "of the organization" not in body

    def test_render_failure_raises_instead_of_sending_a_linkless_mail(self, service):
        missing = TemplateNotFound("account_link_confirmation_de.html")
        with patch.object(service.template_env, "get_template", side_effect=missing):
            with pytest.raises(TemplateNotFound):
                _link_mail(service)


class TestAccountActivationMail:
    @pytest.mark.parametrize("language", ["de", "en"])
    def test_copy_has_no_em_dash(self, service, language):
        subject, body = service.build_account_activation_email(
            activation_url=ACTIVATION_URL,
            brand_name="BenGER",
            frontend_host="what-a-benger.net",
            language=language,
        )

        assert "—" not in subject + body
        assert ACTIVATION_URL in body

    def test_german_copy_says_the_account_followed_the_consent(self, service):
        subject, body = service.build_account_activation_email(
            activation_url=ACTIVATION_URL,
            brand_name="BenGER",
            frontend_host="what-a-benger.net",
            language="de",
            expiry_days=7,
        )

        assert subject == "Aktiviere dein BenGER-Konto"
        assert (
            "Du hast über die Lernplattform deiner Hochschule der Nutzung von "
            "BenGER zugestimmt. Dabei wurde ein Konto für dich angelegt."
        ) in body
        assert "direkt auf what-a-benger.net anmelden" in body
        assert "7 Tage gültig" in body

    def test_english_copy_says_the_account_followed_the_consent(self, service):
        subject, body = service.build_account_activation_email(
            activation_url=ACTIVATION_URL,
            brand_name="BenGER",
            frontend_host="what-a-benger.net",
            language="en",
        )

        assert subject == "Activate your BenGER account"
        assert "You agreed to use BenGER through your university" in body
        assert "An account was created for you at that point." in body
