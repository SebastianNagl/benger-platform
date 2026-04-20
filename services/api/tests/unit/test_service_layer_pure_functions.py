"""
Unit tests for pure functions in the service layer.

Tests functions that do NOT require a db: Session parameter.
Targets:
- auth_module/user_service.py: password hashing, sanitization
- services/email/email_validation.py: email validation, sanitization, bulk validation
- services/storage/storage_config.py: storage/CDN configuration helpers
- services/storage/cdn_service.py: CDN cache headers, URL generation, cache key generation
- routers/evaluations/helpers.py: extract_metric_name
- routers/evaluations/results.py: _extract_primary_score
"""

import os
import pytest


# ===== user_service pure functions =====


class TestPasswordHashing:
    """Tests for get_password_hash / verify_password in user_service."""

    def test_hash_returns_string(self):
        from user_service import get_password_hash
        result = get_password_hash("testpassword")
        assert isinstance(result, str)

    def test_hash_is_bcrypt(self):
        from user_service import get_password_hash
        result = get_password_hash("testpassword")
        assert result.startswith("$2b$") or result.startswith("$2a$")

    def test_verify_correct_password(self):
        from user_service import get_password_hash, verify_password
        hashed = get_password_hash("secure_pass_123")
        assert verify_password("secure_pass_123", hashed) is True

    def test_verify_wrong_password(self):
        from user_service import get_password_hash, verify_password
        hashed = get_password_hash("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_empty_password(self):
        from user_service import get_password_hash, verify_password
        hashed = get_password_hash("notempty")
        assert verify_password("", hashed) is False

    def test_hash_different_each_time(self):
        from user_service import get_password_hash
        h1 = get_password_hash("samepassword")
        h2 = get_password_hash("samepassword")
        assert h1 != h2  # Different salts

    def test_verify_with_invalid_hash(self):
        from user_service import verify_password
        assert verify_password("anything", "not_a_valid_hash") is False

    def test_aliases_exist(self):
        from user_service import hash_password, check_password
        hashed = hash_password("alias_test")
        assert check_password("alias_test", hashed) is True

    def test_unicode_password(self):
        from user_service import get_password_hash, verify_password
        hashed = get_password_hash("Passwort123!")
        assert verify_password("Passwort123!", hashed) is True

    def test_long_password(self):
        from user_service import get_password_hash, verify_password
        long_pw = "a" * 72  # bcrypt truncates at 72 bytes
        hashed = get_password_hash(long_pw)
        assert verify_password(long_pw, hashed) is True


class TestSanitizeUserInput:
    """Tests for sanitize_user_input in user_service."""

    def test_basic_sanitization(self):
        from user_service import sanitize_user_input
        assert sanitize_user_input("  hello  ") == "hello"

    def test_html_escape(self):
        from user_service import sanitize_user_input
        result = sanitize_user_input("<b>bold</b>")
        assert "<b>" not in result
        assert "&lt;" in result

    def test_script_removal(self):
        from user_service import sanitize_user_input
        result = sanitize_user_input("<script>alert('xss')</script>")
        assert "script" not in result.lower() or "&lt;" in result

    def test_empty_string(self):
        from user_service import sanitize_user_input
        assert sanitize_user_input("") == ""

    def test_none_input(self):
        from user_service import sanitize_user_input
        assert sanitize_user_input(None) is None

    def test_max_length_truncation(self):
        from user_service import sanitize_user_input
        long_input = "a" * 200
        result = sanitize_user_input(long_input)
        assert len(result) <= 100

    def test_iframe_removal(self):
        from user_service import sanitize_user_input
        result = sanitize_user_input("normal text<iframe src='evil'></iframe>more")
        assert "iframe" not in result.lower() or "&lt;" in result

    def test_javascript_protocol(self):
        from user_service import sanitize_user_input
        result = sanitize_user_input("javascript:alert(1)")
        # Should be stripped or escaped
        assert "javascript:" not in result


# ===== email_validation pure functions =====


class TestIsValidEmail:
    """Tests for is_valid_email in services/email/email_validation.py."""

    def test_valid_email(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user@university.de") is True

    def test_valid_email_subdomain(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user@mail.university.de") is True

    def test_invalid_no_at(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("userdomaincom") is False

    def test_invalid_empty(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("") is False

    def test_invalid_multiple_at(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user@@domain.com") is False

    def test_invalid_consecutive_dots(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user..name@domain.com") is False

    def test_invalid_no_domain_dot(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user@domain") is False

    def test_valid_plus_addressing(self):
        from services.email.email_validation import is_valid_email
        assert is_valid_email("user+tag@domain.com") is True


class TestValidateEmailWithDetails:
    """Tests for validate_email_with_details in services/email/email_validation.py."""

    def test_valid_email_returns_true_none(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("test@university.edu")
        assert valid is True
        assert error is None

    def test_empty_email_returns_error(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("")
        assert valid is False
        assert "required" in error.lower()

    def test_whitespace_in_email(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("user @domain.com")
        assert valid is False
        assert "whitespace" in error.lower()

    def test_no_at_symbol(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("userdomain.com")
        assert valid is False
        assert "@" in error

    def test_multiple_at_symbols(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("user@domain@com")
        assert valid is False

    def test_local_part_starts_with_dot(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details(".user@domain.com")
        assert valid is False
        assert "dot" in error.lower()

    def test_local_part_ends_with_dot(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("user.@domain.com")
        assert valid is False
        assert "dot" in error.lower()

    def test_consecutive_dots_in_local(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("us..er@domain.com")
        assert valid is False
        assert "consecutive" in error.lower()

    def test_no_domain(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("user@")
        assert valid is False

    def test_domain_no_dot(self):
        from services.email.email_validation import validate_email_with_details
        valid, error = validate_email_with_details("user@localhost")
        assert valid is False


class TestSanitizeEmail:
    """Tests for sanitize_email in services/email/email_validation.py."""

    def test_strips_whitespace(self):
        from services.email.email_validation import sanitize_email
        assert sanitize_email("  user@domain.com  ") == "user@domain.com"

    def test_lowercases(self):
        from services.email.email_validation import sanitize_email
        assert sanitize_email("User@Domain.COM") == "user@domain.com"

    def test_invalid_returns_none(self):
        from services.email.email_validation import sanitize_email
        assert sanitize_email("not_an_email") is None

    def test_empty_returns_none(self):
        from services.email.email_validation import sanitize_email
        assert sanitize_email("") is None

    def test_none_returns_none(self):
        from services.email.email_validation import sanitize_email
        assert sanitize_email(None) is None


class TestExtractDomain:
    """Tests for extract_domain in services/email/email_validation.py."""

    def test_valid_domain_extraction(self):
        from services.email.email_validation import extract_domain
        assert extract_domain("user@university.de") == "university.de"

    def test_invalid_email_returns_none(self):
        from services.email.email_validation import extract_domain
        assert extract_domain("notanemail") is None

    def test_subdomain_extraction(self):
        from services.email.email_validation import extract_domain
        assert extract_domain("user@mail.university.de") == "mail.university.de"


class TestIsDisposableEmail:
    """Tests for is_disposable_email in services/email/email_validation.py."""

    def test_known_disposable(self):
        from services.email.email_validation import is_disposable_email
        assert is_disposable_email("user@mailinator.com") is True

    def test_legitimate_email(self):
        from services.email.email_validation import is_disposable_email
        assert is_disposable_email("user@university.de") is False

    def test_invalid_email(self):
        from services.email.email_validation import is_disposable_email
        assert is_disposable_email("notanemail") is False

    def test_guerrillamail(self):
        from services.email.email_validation import is_disposable_email
        assert is_disposable_email("user@guerrillamail.com") is True


class TestBulkEmailValidation:
    """Tests for validate_bulk_emails in services/email/email_validation.py."""

    def test_all_valid(self):
        from services.email.email_validation import validate_bulk_emails
        result = validate_bulk_emails(["a@uni.de", "b@uni.de"])
        assert result["stats"]["valid_count"] == 2
        assert result["stats"]["invalid_count"] == 0

    def test_mixed_valid_invalid(self):
        from services.email.email_validation import validate_bulk_emails
        result = validate_bulk_emails(["valid@uni.de", "invalid", "also@valid.com"])
        assert result["stats"]["valid_count"] == 2
        assert result["stats"]["invalid_count"] == 1

    def test_all_invalid(self):
        from services.email.email_validation import validate_bulk_emails
        result = validate_bulk_emails(["bad1", "bad2", "bad3"])
        assert result["stats"]["valid_count"] == 0
        assert result["stats"]["invalid_count"] == 3

    def test_empty_list(self):
        from services.email.email_validation import validate_bulk_emails
        result = validate_bulk_emails([])
        assert result["stats"]["total"] == 0
        assert result["stats"]["validity_rate"] == 0

    def test_stats_total(self):
        from services.email.email_validation import validate_bulk_emails
        emails = ["a@b.com", "c@d.com", "invalid"]
        result = validate_bulk_emails(emails)
        assert result["stats"]["total"] == 3


# ===== LocalStorageBackend pure functions =====


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend path handling and validation."""

    def test_get_full_path(self, tmp_path):
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(tmp_path))
        path = backend._get_full_path("some/key.txt")
        assert str(tmp_path) in str(path)
        assert "some" in str(path)

    def test_get_full_path_strips_leading_slash(self, tmp_path):
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(tmp_path))
        path = backend._get_full_path("/leading/slash.txt")
        assert str(tmp_path) in str(path)

    def test_path_traversal_blocked(self, tmp_path):
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid key"):
            backend._get_full_path("../../etc/passwd")

    def test_simple_key(self, tmp_path):
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(tmp_path))
        path = backend._get_full_path("file.txt")
        assert path.name == "file.txt"

    def test_nested_key(self, tmp_path):
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(tmp_path))
        path = backend._get_full_path("a/b/c/file.txt")
        assert path.name == "file.txt"

    def test_creates_base_dir(self, tmp_path):
        new_dir = tmp_path / "new_storage"
        from services.storage.storage_service import LocalStorageBackend
        backend = LocalStorageBackend(str(new_dir))
        assert new_dir.exists()


# ===== CDN Service pure functions =====


class TestCDNServiceCacheHeaders:
    """Tests for CDNService.get_cache_headers and generate_cache_key."""

    def _make_cdn_service(self):
        """Create a CDNService with a mock provider for testing pure methods."""
        from services.storage.cdn_service import CDNService, CDNProvider

        class MockProvider(CDNProvider):
            async def purge_cache(self, paths):
                return True
            def get_cdn_url(self, path):
                return f"https://cdn.example.com/{path.lstrip('/')}"
            async def warm_cache(self, paths):
                return True

        return CDNService(MockProvider())

    def test_js_cache_headers(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("bundle.js")
        assert "immutable" in headers["Cache-Control"]

    def test_css_cache_headers(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("style.css")
        assert "immutable" in headers["Cache-Control"]

    def test_json_no_cache(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("data.json")
        assert "no-cache" in headers["Cache-Control"]

    def test_pdf_cache_headers(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("document.pdf")
        assert "3600" in headers["Cache-Control"]

    def test_unknown_ext_default(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("file.xyz")
        assert "3600" in headers["Cache-Control"]

    def test_security_headers_present(self):
        svc = self._make_cdn_service()
        headers = svc.get_cache_headers("file.js")
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers
        assert "X-XSS-Protection" in headers

    def test_cdn_url(self):
        svc = self._make_cdn_service()
        url = svc.get_cdn_url("/assets/image.png")
        assert "cdn.example.com" in url
        assert "image.png" in url

    def test_generate_cache_key_no_version(self):
        svc = self._make_cdn_service()
        key = svc.generate_cache_key("path/to/file.js")
        assert key == "path/to/file.js"

    def test_generate_cache_key_with_version(self):
        svc = self._make_cdn_service()
        key = svc.generate_cache_key("path/to/file.js", version="abc123")
        assert "abc123" in key
        assert key.endswith(".js")


# ===== Evaluation helpers pure functions =====


class TestExtractMetricName:
    """Tests for extract_metric_name in routers/evaluations/helpers.py."""

    def test_string_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name("bleu") == "bleu"

    def test_dict_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name({"name": "bleu", "parameters": {"max_order": 4}}) == "bleu"

    def test_dict_no_name(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name({"parameters": {}}) == ""

    def test_none_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name(None) == ""

    def test_integer_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name(42) == ""

    def test_empty_string(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name("") == ""


class TestExtractPrimaryScore:
    """Tests for _extract_primary_score in routers/evaluations/results.py."""

    def test_none_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score({}) is None

    def test_custom_llm_judge_priority(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_custom": 0.9,
            "llm_judge_coherence": 0.7,
            "score": 0.5,
        }
        assert _extract_primary_score(metrics) == 0.9

    def test_custom_llm_judge(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 0.85, "score": 0.5}
        assert _extract_primary_score(metrics) == 0.85

    def test_generic_llm_judge(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_coherence": 0.88}
        assert _extract_primary_score(metrics) == 0.88

    def test_skips_response_suffix(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_test_response": "some text", "score": 0.7}
        assert _extract_primary_score(metrics) == 0.7

    def test_skips_passed_suffix(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_test_passed": True, "score": 0.6}
        assert _extract_primary_score(metrics) == 0.6

    def test_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"some_other_metric": "text", "score": 0.42}
        assert _extract_primary_score(metrics) == 0.42

    def test_overall_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"some_other_metric": "text", "overall_score": 0.55}
        assert _extract_primary_score(metrics) == 0.55

    def test_non_numeric_values_skipped(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": "not_a_number"}
        assert _extract_primary_score(metrics) is None

    def test_zero_score_is_valid(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0}
        assert _extract_primary_score(metrics) == 0

    def test_negative_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": -1.5}
        assert _extract_primary_score(metrics) == -1.5


# ===== CDN factory function =====


class TestCDNFactory:
    """Tests for create_cdn_service factory."""

    def test_none_provider_returns_none(self):
        from services.storage.cdn_service import create_cdn_service
        assert create_cdn_service(None) is None

    def test_empty_provider_returns_none(self):
        from services.storage.cdn_service import create_cdn_service
        assert create_cdn_service("") is None

    def test_unknown_provider_raises(self):
        from services.storage.cdn_service import create_cdn_service
        with pytest.raises(ValueError, match="Unknown CDN provider"):
            create_cdn_service("unknown_provider")


# ===== CloudflareProvider pure methods =====


class TestCloudflareProviderGetURL:
    """Tests for CloudflareProvider.get_cdn_url pure method."""

    def test_get_cdn_url(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="test-zone",
            api_token="test-token",
            domain_name="cdn.example.com",
        )
        url = provider.get_cdn_url("/assets/file.js")
        assert url == "https://cdn.example.com/assets/file.js"

    def test_get_cdn_url_no_leading_slash(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="test-zone",
            api_token="test-token",
            domain_name="cdn.example.com",
        )
        url = provider.get_cdn_url("assets/file.js")
        assert url == "https://cdn.example.com/assets/file.js"

    def test_domain_trailing_slash_stripped(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="test-zone",
            api_token="test-token",
            domain_name="cdn.example.com/",
        )
        url = provider.get_cdn_url("file.js")
        assert url == "https://cdn.example.com/file.js"
