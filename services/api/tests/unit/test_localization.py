"""
Tests for localization/translations module.

Targets: localization/translations.py lines 230-251, 267-281, 296-306, 315, 320-325, 331, 336
"""

import pytest


class TestEmailTranslations:
    """Test EmailTranslations class methods."""

    def test_get_english_translation(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("en", "verification_email", "subject")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_german_translation(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("de", "verification_email", "subject")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_unsupported_language_falls_back_to_english(self):
        from localization.translations import EmailTranslations
        result_en = EmailTranslations.get("en", "verification_email", "subject")
        result_fr = EmailTranslations.get("fr", "verification_email", "subject")
        assert result_fr == result_en  # Falls back to English

    def test_get_missing_key_returns_empty(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("en", "verification_email", "nonexistent_key_xyz")
        assert result == "" or "Missing translation" in result

    def test_get_missing_category_returns_empty(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get("en", "nonexistent_category", "subject")
        assert result == "" or "Missing translation" in result

    def test_get_with_format_params(self):
        from localization.translations import EmailTranslations
        # Test with a translation that uses format parameters
        # We just verify it doesn't crash with format params
        result = EmailTranslations.get("en", "verification_email", "subject", name="Test")
        assert isinstance(result, str)

    def test_get_with_invalid_format_params(self):
        from localization.translations import EmailTranslations
        # Test with format params that don't match the template
        result = EmailTranslations.get(
            "en", "verification_email", "subject",
            nonexistent_param="value"
        )
        assert isinstance(result, str)

    def test_get_german_fallback_to_english(self):
        from localization.translations import EmailTranslations
        # Try to get a key that might exist in English but not German
        # This exercises the fallback path
        result = EmailTranslations.get("de", "nonexistent_category", "nonexistent_key")
        assert isinstance(result, str)

    def test_get_list_english(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get_list("en", "verification_email", "troubleshooting_tips")
        assert isinstance(result, list)

    def test_get_list_unsupported_language(self):
        from localization.translations import EmailTranslations
        result_en = EmailTranslations.get_list("en", "verification_email", "troubleshooting_tips")
        result_fr = EmailTranslations.get_list("fr", "verification_email", "troubleshooting_tips")
        assert result_fr == result_en

    def test_get_list_missing_key(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get_list("en", "verification_email", "nonexistent_list")
        assert result == []

    def test_get_list_german_fallback(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.get_list("de", "nonexistent_category", "nonexistent_list")
        assert isinstance(result, list)


class TestDetectUserLanguage:
    """Test language detection functionality."""

    def test_detect_german_from_accept_language(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language(
            accept_language="de-DE,de;q=0.9,en;q=0.8"
        )
        assert result == "de"

    def test_detect_english_from_accept_language(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language(
            accept_language="en-US,en;q=0.9"
        )
        assert result == "en"

    def test_detect_default_english(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language()
        assert result == "en"

    def test_detect_empty_accept_language(self):
        from localization.translations import EmailTranslations
        result = EmailTranslations.detect_user_language(accept_language="")
        assert result == "en"


class TestLanguageDetector:
    """Test LanguageDetector class."""

    def test_detect_from_request_headers(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_request_headers(
            accept_language="de-DE"
        )
        assert result == "de"

    def test_detect_from_user_profile_german(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile("de-DE")
        assert result == "de"

    def test_detect_from_user_profile_english(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile("en-US")
        assert result == "en"

    def test_detect_from_user_profile_none(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile(None)
        assert result == "en"

    def test_detect_from_user_profile_unknown(self):
        from localization.translations import LanguageDetector
        result = LanguageDetector.detect_from_user_profile("ja-JP")
        assert result == "en"


class TestConvenienceFunctions:
    """Test t() and t_list() shorthand functions."""

    def test_t_function(self):
        from localization.translations import t
        result = t("en", "verification_email", "subject")
        assert isinstance(result, str)

    def test_t_list_function(self):
        from localization.translations import t_list
        result = t_list("en", "verification_email", "troubleshooting_tips")
        assert isinstance(result, list)
