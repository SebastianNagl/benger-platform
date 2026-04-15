"""
Unit tests for localization/translations.py to increase branch coverage.
Tests translation functions and language detection.
"""

import pytest


class TestEmailTranslations:
    def test_get_de(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("de", "email", "verification_subject")
        assert isinstance(result, str)

    def test_get_en(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("en", "email", "verification_subject")
        assert isinstance(result, str)

    def test_get_unknown_key_fallback(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("de", "email", "nonexistent_key_xyz")
        assert isinstance(result, str)

    def test_get_unknown_language_fallback(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("fr", "email", "verification_subject")
        assert isinstance(result, str)


class TestTranslationShorthand:
    def test_t_function(self):
        from localization.translations import t
        result = t("de", "email", "verification_subject")
        assert isinstance(result, str)

    def test_t_with_en(self):
        from localization.translations import t
        result = t("en", "email", "verification_subject")
        assert isinstance(result, str)


class TestSupportedLanguage:
    def test_enum_values(self):
        from localization.translations import SupportedLanguage
        assert hasattr(SupportedLanguage, 'GERMAN') or hasattr(SupportedLanguage, 'DE')
        assert hasattr(SupportedLanguage, 'ENGLISH') or hasattr(SupportedLanguage, 'EN')

    def test_enum_members(self):
        from localization.translations import SupportedLanguage
        members = list(SupportedLanguage)
        assert len(members) >= 2


class TestLanguageDetector:
    def test_detect_from_user_agent_de(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language(accept_language="de-DE,de;q=0.9")
        assert isinstance(result, str)

    def test_detect_from_user_agent_en(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language(accept_language="en-US,en;q=0.9")
        assert isinstance(result, str)

    def test_detect_empty(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language()
        assert isinstance(result, str)

    def test_language_detector_class(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_request_headers()
        assert isinstance(result, str)

    def test_language_detector_from_profile(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile("de")
        assert isinstance(result, str)

    def test_language_detector_none_profile(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile(None)
        assert isinstance(result, str)
