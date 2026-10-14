"""French (fr) as the third backend language next to de and en.

Covers every place the backend picks a language for user-facing copy:
the EmailTranslations catalog and its detectors, the transactional mail
language helper, the localized Jinja templates (an ``_fr`` file for every
``_de`` file), the inline verification / password-reset mails and the
access-key scope descriptions. Unknown languages keep their old fallback.
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from account_activation import MAIL_LANGUAGES, mail_language_for
from app.core import scopes as sc
from localization.translations import (
    EmailTranslations,
    LanguageDetector,
    SupportedLanguage,
    t,
    t_list,
)

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "email_templates" / "email"
)
_JINJA_VAR = re.compile(r"{{\s*([a-z_]+)\s*}}")
_JINJA_TAG = re.compile(r"{%\s*(if|else|endif)\b[^%]*%}")


@pytest.fixture
def service():
    with patch("mailer.email_service.SendGridClient"):
        from mailer.email_service import EmailService

        svc = EmailService()
        svc.mail_client = MagicMock()
        svc.mail_client.send_message.return_value = {"status": "success"}
        yield svc


def _keys(tree):
    return {(cat, key) for cat, entries in tree.items() for key in entries}


class TestTranslationCatalog:
    def test_french_is_a_supported_language(self):
        assert SupportedLanguage.FRENCH.value == "fr"
        assert {lang.value for lang in SupportedLanguage} == {"de", "en", "fr"}

    def test_french_covers_every_english_key(self):
        catalog = EmailTranslations.translations
        assert _keys(catalog["fr"]) == _keys(catalog["en"])

    def test_french_is_selected(self):
        assert (
            t("fr", "verification_email", "subject") == "Vérifiez votre compte BenGER"
        )
        assert (
            t("fr", "verification_email", "greeting", user_name="Anne")
            == "Bonjour Anne,"
        )
        assert len(t_list("fr", "frontend", "troubleshooting_tips")) == 3
        assert t_list("fr", "frontend", "troubleshooting_tips") != t_list(
            "en", "frontend", "troubleshooting_tips"
        )

    def test_french_placeholders_match_english(self):
        catalog = EmailTranslations.translations
        for cat, entries in catalog["en"].items():
            for key, en in entries.items():
                if isinstance(en, str):
                    fr = catalog["fr"][cat][key]
                    assert set(re.findall(r"{(\w+)}", fr)) == set(
                        re.findall(r"{(\w+)}", en)
                    ), (cat, key)

    def test_french_copy_has_no_em_dash(self):
        for entries in EmailTranslations.translations["fr"].values():
            for value in entries.values():
                text = " ".join(value) if isinstance(value, list) else value
                assert "—" not in text

    def test_unknown_language_still_falls_back_to_english(self):
        assert t("es", "verification_email", "subject") == t(
            "en", "verification_email", "subject"
        )


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "header,expected",
        [
            ("fr-FR,fr;q=0.9,en;q=0.8", "fr"),
            ("fr", "fr"),
            ("es-ES,fr;q=0.8,de;q=0.5", "fr"),
            ("de-DE,fr;q=0.9", "de"),
            ("en-US,fr;q=0.9", "en"),
            ("es-ES,it;q=0.9", "en"),
            ("", "en"),
        ],
    )
    def test_accept_language(self, header, expected):
        assert (
            EmailTranslations.detect_user_language(accept_language=header) == expected
        )
        assert (
            LanguageDetector.detect_from_request_headers(accept_language=header)
            == expected
        )

    @pytest.mark.parametrize(
        "locale,expected",
        [
            ("fr", "fr"),
            ("fr-CA", "fr"),
            ("FR", "fr"),
            ("de", "de"),
            ("es", "en"),
            (None, "en"),
        ],
    )
    def test_user_profile(self, locale, expected):
        assert LanguageDetector.detect_from_user_profile(locale) == expected


class TestMailLanguage:
    def test_french_preference_is_honoured(self):
        assert "fr" in MAIL_LANGUAGES
        assert mail_language_for(SimpleNamespace(language_preference="fr")) == "fr"
        assert mail_language_for(SimpleNamespace(language_preference="fr-BE")) == "fr"

    def test_unknown_preference_keeps_the_default(self):
        assert mail_language_for(SimpleNamespace(language_preference="es")) == "de"
        assert (
            mail_language_for(SimpleNamespace(language_preference="it"), default="en")
            == "en"
        )


class TestLocalizedTemplates:
    def test_every_german_template_has_a_french_counterpart(self):
        german = sorted(TEMPLATE_DIR.glob("*_de.html"))
        assert german, f"no _de templates found in {TEMPLATE_DIR}"
        for de in german:
            fr = de.with_name(de.name.replace("_de.html", "_fr.html"))
            assert fr.exists(), f"missing French template for {de.name}"

    @pytest.mark.parametrize(
        "de_path", sorted(TEMPLATE_DIR.glob("*_de.html")), ids=lambda p: p.name
    )
    def test_french_template_mirrors_the_german_one(self, de_path):
        de = de_path.read_text(encoding="utf-8")
        fr = de_path.with_name(de_path.name.replace("_de.html", "_fr.html")).read_text(
            encoding="utf-8"
        )
        assert fr.startswith("Subject: ")
        assert set(_JINJA_VAR.findall(fr)) == set(_JINJA_VAR.findall(de))
        assert _JINJA_TAG.findall(fr) == _JINJA_TAG.findall(de)
        # Same markup skeleton: tags and attributes, text stripped.
        assert re.findall(r"<[^>]+>", fr) == re.findall(r"<[^>]+>", de)
        assert "—" not in fr

    @pytest.mark.parametrize(
        "language,fallback,expected",
        [
            ("fr", "en", "x_fr.html"),
            ("FR-ca", "en", "x_fr.html"),
            ("de", "en", "x_de.html"),
            ("en", "de", "x.html"),
            ("es", "en", "x.html"),
            ("es", "de", "x_de.html"),
            (None, "de", "x_de.html"),
        ],
    )
    def test_template_choice(self, language, fallback, expected):
        from mailer.email_service import _localized_template

        assert _localized_template("x", language, fallback=fallback) == expected

    def test_invitation_in_french(self, service):
        subject, body = service.build_invitation_email(
            organization_name="Uni X",
            inviter_name="Anne",
            role="annotator",
            invitation_url="https://what-a-benger.net/accept/tok",
            language="fr",
        )
        assert subject == "Invitation à rejoindre Uni X sur BenGER"
        assert "Accepter l'invitation" in body
        assert "https://what-a-benger.net/accept/tok" in body

    def test_invitation_unknown_language_stays_english(self, service):
        subject, _ = service.build_invitation_email(
            organization_name="Uni X",
            inviter_name="Anne",
            role="annotator",
            invitation_url="https://x",
            language="es",
        )
        assert subject == "Invitation to join Uni X on BenGER"

    def test_activation_in_french(self, service):
        subject, body = service.build_account_activation_email(
            activation_url="https://what-a-benger.net/activate/tok",
            frontend_host="what-a-benger.net",
            language="fr",
            expiry_days=7,
        )
        assert subject == "Activez votre compte BenGER"
        assert "valable 7 jours" in body
        assert "directement sur what-a-benger.net" in body

    def test_activation_unknown_language_stays_english(self, service):
        subject, _ = service.build_account_activation_email(
            activation_url="https://x", language="es"
        )
        assert subject == "Activate your BenGER account"

    def test_link_confirmation_in_french(self, service):
        subject, body = service.build_account_link_confirmation_email(
            confirm_url="https://what-a-benger.net/lti/link-confirm/tok",
            connection_name="Moodle Uni X",
            organization_name="",
            language="fr",
            expiry_hours=12,
        )
        assert subject == "Confirmez l'association à votre compte BenGER"
        assert "la connexion « Moodle Uni X »" in body
        assert "de l'organisation" not in body
        assert "valable 12 heures" in body

    def test_link_confirmation_unknown_language_stays_german(self, service):
        subject, _ = service.build_account_link_confirmation_email(
            confirm_url="https://x",
            connection_name="",
            organization_name="",
            language="es",
        )
        assert subject == "Bestätige die Verknüpfung mit deinem BenGER-Konto"


class TestInlineMails:
    async def test_verification_in_french(self, service):
        await service.send_verification_email(
            "a@example.com",
            "Anne",
            "https://x/verify/tok",
            language="fr",
            brand_name="Vertretbar",
        )
        kwargs = service.mail_client.send_message.call_args.kwargs
        assert kwargs["subject"] == "Confirmez votre adresse e-mail pour Vertretbar"
        assert "Bienvenue sur Vertretbar, Anne" in kwargs["html_body"]
        assert "https://x/verify/tok" in kwargs["html_body"]

    async def test_verification_unknown_language_is_english(self, service):
        await service.send_verification_email(
            "a@example.com", "Anne", "https://x", language="es"
        )
        assert service.mail_client.send_message.call_args.kwargs["subject"].startswith(
            "Verify your email"
        )

    async def test_password_reset_in_french(self, service):
        await service.send_password_reset_email(
            "a@example.com", "Anne", "https://x/reset/tok", language="fr"
        )
        kwargs = service.mail_client.send_message.call_args.kwargs
        assert kwargs["subject"] == "Réinitialiser votre mot de passe BenGER"
        assert "Bonjour Anne," in kwargs["html_body"]
        assert "valable 24 heures" in kwargs["html_body"]

    async def test_password_reset_french_expiry_override(self, service):
        await service.send_password_reset_email(
            "a@example.com",
            "Anne",
            "https://x",
            language="fr",
            expiry_label={"fr": "1 heure"},
        )
        assert (
            "valable 1 heure."
            in service.mail_client.send_message.call_args.kwargs["html_body"]
        )

    async def test_password_reset_unknown_language_is_english(self, service):
        await service.send_password_reset_email(
            "a@example.com", "Anne", "https://x", language="es"
        )
        assert (
            service.mail_client.send_message.call_args.kwargs["subject"]
            == "Reset your password for BenGER"
        )


class TestScopeDescriptions:
    def test_every_builtin_scope_has_a_french_description(self):
        for scope in sc.all_scopes():
            if scope.source != "platform":
                continue
            assert scope.description_fr, scope.name
            assert scope.description_fr not in (
                scope.description_de,
                scope.description_en,
            )
            assert scope.to_dict()["description_fr"] == scope.description_fr

    def test_overlay_scopes_take_or_default_the_french_description(self):
        sc.register_scopes(
            {
                "ext:fr": {"description": "Plain", "description_fr": "Lire"},
                "ext:plain": {"description": "Plain"},
            }
        )
        try:
            assert sc.get_scope("ext:fr").description_fr == "Lire"
            assert sc.get_scope("ext:plain").description_fr == "Plain"
        finally:
            sc.unregister_scopes(["ext:fr", "ext:plain"])
