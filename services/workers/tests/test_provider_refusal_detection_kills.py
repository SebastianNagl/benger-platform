"""Mutation-grade pins for the REFUSAL-detection fix in the provider clients.

WHY THIS FILE EXISTS
--------------------
A content-policy refusal that gets silently scored as a real model answer
biases an academic LLM benchmark: the leaderboard credits the model with an
answer it actually declined to give. Until this fix the OpenAI-compatible
providers (Grok, DeepInfra) and Cohere hardcoded ``"refusal": False`` on the
success path, so a content-filter block was indistinguishable from a normal
answer.

THE FIX (in ``services/shared/ai_services/base_service.py``):

  * ``REFUSAL_FINISH_REASONS = frozenset({"content_filter", "ERROR_TOXIC"})``
  * ``derive_refusal(finish_reason) -> bool`` — True iff the finish_reason is
    in that set; False for None / "" / any other reason.

  ``grok_service.generate()``, ``deepinfra_service._generate_async()`` and
  ``cohere_service.generate()`` now call ``derive_refusal(finish_reason)`` in
  their main parse path (was a hardcoded ``False``). ``mistral_service`` does
  too — its normal finish reasons ("stop"/"length") aren't in the set, so it
  stays False unless a content_filter-style reason appears, which proves the
  centralized mapping is wired in rather than re-hardcoded.

WHAT THIS FILE PINS
-------------------
1. ``derive_refusal`` truth table + the EXACT frozenset membership (so a
   reverted set, an extra member, or an inverted return is caught).
2. End-to-end, per-provider: a refusal finish_reason makes the returned
   ``metadata.refusal`` True, and a normal finish_reason keeps it False
   (regression guard). These kill a reverted/inverted ``derive_refusal``
   call and a wrong/typo'd ``finish_reason`` field name in any provider.

The E2E-construction + client-mock approach mirrors the sibling parsing files
``test_provider_parsing_cohere_mistral_grok_kills.py`` and
``test_provider_parsing_google_deepinfra_kills.py``: env vars set before
import, service built with a dummy key, client replaced with a duck-typed
fake, ``E2E_TEST_MODE`` popped so the REAL parse path runs (not the canned
E2E mock dict).
"""

from __future__ import annotations

import os

# Encryption / auth env must be set BEFORE importing the service modules:
# importing the ai_services package transitively pulls /shared modules whose
# module-level singletons read these. conftest already sets BENGER_TEST_MODE;
# we add the rest defensively so this file is import-safe in isolation too.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-0000000000000000")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
# Make absolutely sure the E2E short-circuit branch is NOT taken — we want the
# REAL parsing path (which calls derive_refusal), not the canned E2E mock dict.
os.environ.pop("E2E_TEST_MODE", None)

import importlib.util  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402


# --------------------------------------------------------------------------
# 1) derive_refusal unit tests
#
# Direct file-import of the helper under test (mirrors
# test_ai_service_metadata.py). Going through the ``ai_services`` package would
# eagerly import every provider's SDK; the base-service helpers have no SDK
# dependencies.
# --------------------------------------------------------------------------
_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_base_service_path = os.path.join(
    _services_root, "shared", "ai_services", "base_service.py"
)
_spec = importlib.util.spec_from_file_location("base_service", _base_service_path)
_base_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base_service)

derive_refusal = _base_service.derive_refusal
REFUSAL_FINISH_REASONS = _base_service.REFUSAL_FINISH_REASONS


class TestDeriveRefusal:
    """Truth table for derive_refusal. A refusal is a content-policy/safety
    decline — distinct from a normal stop or a length truncation."""

    def test_content_filter_is_refusal(self):
        """OpenAI-compatible (Grok/DeepInfra) content-policy block."""
        assert derive_refusal("content_filter") is True

    def test_error_toxic_is_refusal(self):
        """Cohere content-policy block."""
        assert derive_refusal("ERROR_TOXIC") is True

    def test_normal_stop_reasons_are_not_refusals(self):
        """The everyday terminators across providers must never be a refusal:
        a single inverted/over-broad rule would mislabel every normal answer."""
        assert derive_refusal("stop") is False        # OpenAI / Grok / DeepInfra / Mistral
        assert derive_refusal("length") is False       # OpenAI / Cohere / Mistral truncation
        assert derive_refusal("MAX_TOKENS") is False    # Google truncation
        assert derive_refusal("COMPLETE") is False      # Cohere normal terminator

    def test_none_and_empty_are_not_refusals(self):
        """Missing / empty finish_reason → not a refusal (the ``if not
        finish_reason`` guard). Catches a mutation that drops the guard."""
        assert derive_refusal(None) is False
        assert derive_refusal("") is False

    def test_frozenset_membership_is_exactly_the_two_documented_reasons(self):
        """Pin the EXACT set. A widened set (mislabels normal answers) or a
        narrowed set (misses real refusals) both fail here. Equality, not
        subset, so a reverted/extra member is caught either way."""
        assert REFUSAL_FINISH_REASONS == frozenset({"content_filter", "ERROR_TOXIC"})
        assert isinstance(REFUSAL_FINISH_REASONS, frozenset)


# --------------------------------------------------------------------------
# 2) Per-provider end-to-end refusal detection.
#
# Construction + client-mock pattern reused verbatim from the sibling parsing
# files. Each service is built with a dummy api-key, its client replaced with
# a duck-typed fake that returns exactly the attributes the parser reads, and
# generate() is driven so the REAL parse path computes metadata.refusal.
# --------------------------------------------------------------------------
from ai_services.cohere_service import CohereService  # noqa: E402
from ai_services.grok_service import GrokService  # noqa: E402
from ai_services.mistral_service import MistralService  # noqa: E402
from ai_services import deepinfra_service as di_mod  # noqa: E402

DeepInfraService = di_mod.DeepInfraService


# ===== GROK fakes (OpenAI-compatible HTTP JSON over aiohttp) ===============
def _grok_json(content, *, finish_reason, prompt_tokens=1,
               completion_tokens=1, total_tokens=2):
    """Build the OpenAI-compatible JSON dict the Grok async path decodes."""
    choice = {"message": {"content": content}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return {
        "choices": [choice],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


class _FakeAiohttpResponse:
    """Minimal async-context-manager response standing in for aiohttp's."""

    def __init__(self, json_payload):
        self._json = json_payload

    def raise_for_status(self):
        return None

    async def json(self):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAiohttpSession:
    """Stand-in for aiohttp.ClientSession; .post returns our fake response."""

    def __init__(self, json_payload):
        self._json = json_payload

    def post(self, *args, **kwargs):
        return _FakeAiohttpResponse(self._json)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _make_grok():
    svc = GrokService(api_key="dummy-key")
    assert svc.is_available()
    return svc


def _run_grok_generate(svc, grok_json, **gen_kwargs):
    with patch(
        "ai_services.grok_service.aiohttp.ClientSession",
        return_value=_FakeAiohttpSession(grok_json),
    ):
        return svc.generate(prompt="p", system_prompt="s", **gen_kwargs)


# ===== DEEPINFRA fakes (OpenAI-compatible HTTP JSON over aiohttp) ==========
class _FakeAioResponse:
    """Duck-types the bits of aiohttp's response _generate_async reads:
    ``.status``, ``await .text()``, ``await .json()``."""

    def __init__(self, *, status=200, json_body=None, text_body=""):
        self.status = status
        self._json = json_body or {}
        self._text = text_body

    async def text(self):
        return self._text

    async def json(self):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAioSession:
    """Replaces ``aiohttp.ClientSession`` in the deepinfra module."""

    response_factory = None  # set per-test: () -> _FakeAioResponse

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None, timeout=None):
        return type(self).response_factory()


def _make_deepinfra_service():
    """api_key makes ``self.client is True`` so is_available() is True and
    the real parser runs."""
    return DeepInfraService(api_key="test-deepinfra-key")


def _deepinfra_json(content, *, finish_reason, prompt_tokens=5,
                    completion_tokens=5, total_tokens=10):
    choice = {"message": {"content": content}, "finish_reason": finish_reason}
    return {
        "choices": [choice],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


@pytest.fixture
def patch_aiohttp(monkeypatch):
    """Patch aiohttp.ClientSession inside deepinfra_service with the fake;
    yields a setter that installs the per-test response factory."""

    def _install(response_factory):
        _FakeAioSession.response_factory = staticmethod(response_factory)
        monkeypatch.setattr(di_mod.aiohttp, "ClientSession", _FakeAioSession)
        return _FakeAioSession

    return _install


# ===== COHERE fakes (v2 chat objects) =====================================
def _cohere_response(blocks, *, finish_reason, input_tokens=1, output_tokens=1):
    content_blocks = [types.SimpleNamespace(text=t) for t in blocks]
    resp = types.SimpleNamespace()
    resp.message = types.SimpleNamespace(content=content_blocks)
    resp.finish_reason = finish_reason
    tokens = types.SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens
    )
    resp.usage = types.SimpleNamespace(tokens=tokens)
    return resp


def _make_cohere(client_chat_return):
    svc = CohereService(api_key="dummy-key")
    svc.client = MagicMock()
    svc.client.chat = MagicMock(return_value=client_chat_return)
    return svc


# ===== MISTRAL fakes (chat.complete objects) ==============================
def _mistral_response(content, *, finish_reason, prompt_tokens=1,
                      completion_tokens=1, total_tokens=2):
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message, finish_reason=finish_reason)
    resp = types.SimpleNamespace()
    resp.choices = [choice]
    resp.usage = types.SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return resp


def _make_mistral(complete_return):
    svc = MistralService(api_key="dummy-key")
    svc.client = MagicMock()
    svc.client.chat = MagicMock()
    svc.client.chat.complete = MagicMock(return_value=complete_return)
    return svc


# ==========================================================================
# GROK — refusal threaded from finish_reason
# ==========================================================================
class TestGrokRefusalDetection:
    """Grok (OpenAI-compatible): a 'content_filter' finish_reason must set
    metadata.refusal True; a normal 'stop' must keep it False."""

    def test_content_filter_finish_reason_flags_refusal(self):
        """LOAD-BEARING: the fix. content_filter → refusal True via
        derive_refusal. Kills the old hardcoded False and an inverted call."""
        payload = _grok_json("", finish_reason="content_filter")
        svc = _make_grok()
        out = _run_grok_generate(svc, payload, model_name="grok-3")
        assert out["metadata"]["finish_reason"] == "content_filter"
        assert out["metadata"]["refusal"] is True

    def test_normal_stop_keeps_refusal_false(self):
        """REGRESSION guard: a normal answer must NOT be mislabelled a
        refusal (the complement of the content_filter case)."""
        payload = _grok_json("Die Berufung hat Erfolg.", finish_reason="stop")
        svc = _make_grok()
        out = _run_grok_generate(svc, payload, model_name="grok-3")
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# DEEPINFRA — refusal threaded from finish_reason
# ==========================================================================
class TestDeepInfraRefusalDetection:
    def test_content_filter_finish_reason_flags_refusal(self, patch_aiohttp):
        """LOAD-BEARING: content_filter → refusal True on the DeepInfra
        success path (was hardcoded False)."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body=_deepinfra_json("", finish_reason="content_filter")
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")
        assert out["metadata"]["finish_reason"] == "content_filter"
        assert out["metadata"]["refusal"] is True

    def test_normal_stop_keeps_refusal_false(self, patch_aiohttp):
        """REGRESSION guard: stop → refusal False."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body=_deepinfra_json("Die Antwort lautet 42.", finish_reason="stop")
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# COHERE — refusal threaded from finish_reason
# ==========================================================================
class TestCohereRefusalDetection:
    """Cohere signals a content-policy block via finish_reason 'ERROR_TOXIC'
    (its own vocabulary). The fix maps it through derive_refusal."""

    def test_error_toxic_flags_refusal_but_not_truncated(self):
        """LOAD-BEARING: ERROR_TOXIC → refusal True. AND it must NOT be
        flagged truncated: Cohere's truncated line ORs ``finish_reason ==
        'MAX_TOKENS'``, and ERROR_TOXIC is neither in the truncated set nor
        == 'MAX_TOKENS', so truncated stays False. This pins that the two
        flags don't bleed into each other."""
        resp = _cohere_response(
            [""], finish_reason="ERROR_TOXIC", input_tokens=10, output_tokens=0
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p", model_name="command-r-plus-08-2024")
        assert out["metadata"]["finish_reason"] == "ERROR_TOXIC"
        assert out["metadata"]["refusal"] is True
        assert out["metadata"]["truncated"] is False

    def test_normal_complete_keeps_refusal_false(self):
        """REGRESSION guard: COMPLETE (Cohere's normal terminator) →
        refusal False."""
        resp = _cohere_response(
            ["Die Klage ist begründet."], finish_reason="COMPLETE",
            input_tokens=10, output_tokens=20,
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p", model_name="command-r-plus-08-2024")
        assert out["metadata"]["finish_reason"] == "COMPLETE"
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# MISTRAL — centralized mapping applies (defensive)
# ==========================================================================
class TestMistralRefusalDetection:
    """Mistral's normal reasons ('stop'/'length') are not refusals, so it
    stays False — BUT if a content_filter-style reason appears, the same
    centralized derive_refusal mapping must flag it. This proves the wiring,
    not a re-hardcoded False."""

    def test_content_filter_finish_reason_flags_refusal(self):
        """A content_filter reason → refusal True, proving derive_refusal is
        actually called on Mistral's path (not hardcoded)."""
        resp = _mistral_response("", finish_reason="content_filter")
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p", model_name="mistral-large-latest")
        assert out["metadata"]["finish_reason"] == "content_filter"
        assert out["metadata"]["refusal"] is True

    def test_normal_stop_keeps_refusal_false(self):
        """REGRESSION guard: stop → refusal False."""
        resp = _mistral_response("Der Anspruch besteht.", finish_reason="stop")
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p", model_name="mistral-large-latest")
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["refusal"] is False
