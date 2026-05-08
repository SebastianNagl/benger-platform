"""Phase 6.6: tests for the academic-rigor metadata helpers in
``services/shared/ai_services/base_service.py``.

These helpers are called by every provider's ``generate()`` /
``generate_structured()`` to derive the standard ``truncated`` /
``error_type`` fields. Buggy classification quietly corrupts the
audit trail, so the rules get explicit coverage.
"""

from __future__ import annotations

import os
import sys

# Direct file-import of the helpers under test. Going through the
# ``ai_services`` package would eagerly import every provider's SDK
# (openai, anthropic, google.genai, …), which is heavyweight and
# couples this test to the full provider environment. The helpers
# themselves have no SDK dependencies.
import importlib.util  # noqa: E402

_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_base_service_path = os.path.join(
    _services_root, "shared", "ai_services", "base_service.py"
)
_spec = importlib.util.spec_from_file_location(
    "_phase66_base_service", _base_service_path
)
_base_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base_service)

classify_error_type = _base_service.classify_error_type
derive_truncated = _base_service.derive_truncated


class TestDeriveTruncated:
    def test_recognizes_openai_length(self):
        assert derive_truncated("length") is True

    def test_recognizes_anthropic_max_tokens(self):
        assert derive_truncated("max_tokens") is True

    def test_recognizes_google_uppercase(self):
        # Google genai SDK returns enum names like "MAX_TOKENS".
        assert derive_truncated("MAX_TOKENS") is True

    def test_normal_stop_is_not_truncated(self):
        assert derive_truncated("stop") is False
        assert derive_truncated("end_turn") is False
        assert derive_truncated("tool_use") is False

    def test_none_is_not_truncated(self):
        assert derive_truncated(None) is False
        assert derive_truncated("") is False


class TestModelSupportsSeed:
    """Phase 6.6 (#7): per-model seed support resolves correctly from
    YAML overrides + provider-level defaults.

    These tests don't import provider_capabilities through the package
    init (which would pull every SDK); instead the helper is loaded by
    file path. For the catalog-loader fallback path we monkeypatch the
    cache directly to avoid Postgres / seed-file path dependencies.
    """

    def setup_method(self):
        # Load provider_capabilities the same way derive_truncated /
        # classify_error_type are loaded above (avoiding the SDK import
        # cascade in ai_services/__init__.py).
        import importlib.util as _ilu

        _pc_path = os.path.join(
            _services_root, "shared", "ai_services", "provider_capabilities.py"
        )
        spec = _ilu.spec_from_file_location("_phase66_provider_caps", _pc_path)
        self.pc = _ilu.module_from_spec(spec)
        # provider_capabilities.py uses ``from seeds.llm_models_loader``
        # in _load_seed_support_from_catalog(); that import path may
        # not resolve in the test sandbox. Force the cache to empty
        # *before* exec so the helper short-circuits to provider-level.
        spec.loader.exec_module(self.pc)
        self.pc._SEED_SUPPORT_CACHE = {}

    def test_provider_default_openai_supports_seed(self):
        # Without a per-model override, OpenAI's provider-level default
        # (seed_support=True) wins.
        assert self.pc.model_supports_seed("openai", "gpt-4o") is True

    def test_provider_default_anthropic_does_not_support_seed(self):
        # Anthropic doesn't accept the seed parameter.
        assert self.pc.model_supports_seed("anthropic", "claude-opus-4-7") is False

    def test_provider_default_deepinfra_now_supports_seed(self):
        # Phase 6.6 (#7): DeepInfra default flipped from False to True.
        assert self.pc.model_supports_seed("deepinfra", "deepseek-ai/DeepSeek-V3.1") is True

    def test_per_model_override_wins_over_provider_default(self):
        # Simulate the YAML-cached override for Kimi: Kimi is on
        # DeepInfra (provider default True post-#7) but its custom
        # backend doesn't honor seed, so the per-model False override
        # takes precedence.
        self.pc._SEED_SUPPORT_CACHE = {
            "moonshotai/Kimi-K2.5": False,
        }
        assert self.pc.model_supports_seed("deepinfra", "moonshotai/Kimi-K2.5") is False
        # Other DeepInfra models still get the provider-level default.
        assert self.pc.model_supports_seed("deepinfra", "deepseek-ai/DeepSeek-V3.1") is True

    def test_per_model_true_override_wins_for_provider_with_false_default(self):
        # Hypothetical: even if some provider's default is False, an
        # explicit per-model True override flips it to True.
        self.pc._SEED_SUPPORT_CACHE = {
            "anthropic-future-seed-model": True,
        }
        assert self.pc.model_supports_seed("anthropic", "anthropic-future-seed-model") is True


class TestClassifyErrorType:
    def test_rate_limit_by_message(self):
        assert classify_error_type(Exception("HTTP 429: rate limit")) == "rate_limit"
        assert classify_error_type(Exception("quota exceeded")) == "rate_limit"

    def test_rate_limit_by_class_name(self):
        class RateLimitError(Exception):
            pass

        assert classify_error_type(RateLimitError("foo")) == "rate_limit"

    def test_timeout(self):
        assert classify_error_type(TimeoutError("timed out after 30s")) == "timeout"
        assert classify_error_type(Exception("Request timeout")) == "timeout"

    def test_auth(self):
        assert classify_error_type(Exception("401 Unauthorized")) == "auth"
        assert classify_error_type(Exception("invalid API key")) == "auth"

    def test_content_filter(self):
        assert classify_error_type(Exception("blocked by safety filter")) == "content_filter"
        assert classify_error_type(Exception("content policy violation")) == "content_filter"

    def test_context_length(self):
        msg = "Maximum context length exceeded for model"
        assert classify_error_type(Exception(msg)) == "context_length"

    def test_parse_error(self):
        assert classify_error_type(ValueError("could not parse JSON")) == "parse_error"

    def test_falls_back_to_api_error(self):
        assert classify_error_type(Exception("internal server error")) == "api_error"
