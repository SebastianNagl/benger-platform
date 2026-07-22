"""Mutation-grade parsing tests for the GENERATION-side response parsing in
two provider clients that had **no dedicated test**:

  * ``services/shared/ai_services/google_service.py``  (GoogleService.generate)
  * ``services/shared/ai_services/deepinfra_service.py`` (DeepInfraService.generate)

Why this matters (academic rigor / benchmark integrity)
-------------------------------------------------------
These ``generate()`` methods turn a raw provider API response into the dict
that becomes the *stored generation* — the benchmark INPUT later graded by
humans and LLM judges. If the parser silently:

  * drops a ``MAX_TOKENS`` / ``length`` finish_reason → a **truncated** answer
    is scored as if the model finished its argument,
  * mis-reads the Google ``candidates → content → parts → text`` shape → the
    wrong (or empty) text is stored,
  * swaps prompt/completion token counts → cost + length stats are corrupt,
  * IndexErrors on an empty/no-candidate response → the whole run dies,

then a WRONG input is scored as if valid. None of those four had coverage, so
this file pins the exact contract with mocked SDKs (no network).

Mocking strategy
----------------
* GOOGLE: construct ``GoogleService(api_key="...")`` then REPLACE ``.client``
  with a ``MagicMock`` whose ``.models.generate_content(...)`` returns a
  duck-typed ``SimpleNamespace`` matching the attributes the parser reads
  (``candidates[0].finish_reason.name``, ``...content.parts[*].text``,
  ``usage_metadata.*_token_count``). ``is_available()`` returns
  ``self.client is not None``, so a non-None mock flips it available.
* DEEPINFRA: ``_generate_async_attempts`` (the retry-decorated per-attempt
  body under the undecorated ``_generate_async`` outer) talks to
  ``aiohttp.ClientSession`` directly (no client object). We construct
  ``DeepInfraService(api_key="...")`` so ``self.client is True``
  (available), then monkeypatch ``aiohttp.ClientSession`` in the service
  module with a fake whose ``.post(...)`` async-context-manager yields a
  fake response exposing ``.status``, ``await .text()`` and
  ``await .json()``. Retry tests additionally patch the module's ``_sleep``
  backoff seam with an instant recorder (the workers conftest already
  no-ops it autouse-wide).

We assert EXACT values; the reasoning is in each test's docstring.
"""

from __future__ import annotations

import os
import types

# Import-time guards: these mirror what the workers conftest already sets,
# but we set them defensively at the very top in case this file is ever
# collected before the encryption_service sentinel is in place.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-not-real-0000000000")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
# Make absolutely sure the E2E mock-response short-circuit inside each
# provider's generate() is NOT taken — we are testing the REAL parser.
os.environ.pop("E2E_TEST_MODE", None)

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

# Import the provider modules directly. Going through the ``ai_services``
# package __init__ would eagerly import every provider SDK (openai,
# anthropic, cohere, mistral, ...); importing the submodules pulls only
# google.genai + aiohttp, both present in the workers image.
from ai_services import google_service as gs_mod  # noqa: E402
from ai_services import deepinfra_service as di_mod  # noqa: E402

GoogleService = gs_mod.GoogleService
DeepInfraService = di_mod.DeepInfraService


# ===========================================================================
# Google fake-response builders (duck-typed to the genai SDK shape)
# ===========================================================================
class _FakeFinishReason:
    """Mimics the genai SDK's finish_reason enum: ``.name`` is the string the
    parser coerces it to (line: ``raw_fr.name if hasattr(raw_fr, 'name')``)."""

    def __init__(self, name: str):
        self.name = name


def _google_part(text):
    return types.SimpleNamespace(text=text)


def _google_response(
    *,
    parts_text=("ok",),
    finish_reason_name="STOP",
    prompt_tokens=100,
    completion_tokens=50,
    total_tokens=150,
    with_usage=True,
    with_candidate=True,
    candidate_text=None,
    safety_ratings=None,
):
    """Build a SimpleNamespace shaped like a genai GenerateContentResponse.

    Only the attributes the parser actually reads are populated; ``hasattr``
    checks in the source mean omitting an attribute exercises the fallback.
    """
    candidates = []
    if with_candidate:
        parts = [_google_part(t) for t in parts_text] if parts_text is not None else None
        content = types.SimpleNamespace(parts=parts)
        candidate = types.SimpleNamespace(
            finish_reason=_FakeFinishReason(finish_reason_name)
            if finish_reason_name is not None
            else None,
            content=content,
            safety_ratings=safety_ratings or [],
        )
        if candidate_text is not None:
            candidate.text = candidate_text
        candidates.append(candidate)

    usage = None
    if with_usage:
        usage = types.SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=completion_tokens,
            total_token_count=total_tokens,
        )

    resp = types.SimpleNamespace(
        candidates=candidates,
        usage_metadata=usage,
        text="",  # response.text fallback; empty unless a test sets it
    )
    return resp


def _make_google_service(fake_response=None, generate_side_effect=None):
    """Construct a GoogleService with its genai client replaced by a mock.

    ``is_available()`` returns ``self.client is not None``; a MagicMock is
    non-None so the service reports available and the real parser runs.
    """
    svc = GoogleService(api_key="test-google-key")
    client = MagicMock()
    if generate_side_effect is not None:
        client.models.generate_content.side_effect = generate_side_effect
    else:
        client.models.generate_content.return_value = fake_response
    svc.client = client
    return svc


# ===========================================================================
# DeepInfra fake-aiohttp plumbing
# ===========================================================================
class _FakeAioResponse:
    """Duck-types the bits of aiohttp's response that _generate_async reads:
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
    """Replaces ``aiohttp.ClientSession`` in the deepinfra module. Its
    ``.post(...)`` returns an async context manager yielding the canned
    response; captures the payload so tests can assert what was sent."""

    last_payload = None
    response_factory = None  # set per-test: () -> _FakeAioResponse

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None, timeout=None):
        type(self).last_payload = json
        return type(self).response_factory()


def _make_deepinfra_service():
    """Construct a DeepInfraService; api_key makes ``self.client is True``
    so ``is_available()`` is True and the real parser runs."""
    return DeepInfraService(api_key="test-deepinfra-key")


@pytest.fixture
def patch_aiohttp(monkeypatch):
    """Patch aiohttp.ClientSession used inside deepinfra_service with the
    fake. Yields a setter that installs the per-test response."""
    _FakeAioSession.last_payload = None

    def _install(response_factory):
        _FakeAioSession.response_factory = staticmethod(response_factory)
        monkeypatch.setattr(di_mod.aiohttp, "ClientSession", _FakeAioSession)
        return _FakeAioSession

    return _install


# ===========================================================================
# GOOGLE — normal / token / finish_reason mapping
# ===========================================================================
class TestGoogleNormal:
    def test_content_extracted_from_candidates_parts_shape(self):
        """NORMAL: text must come from candidates[0].content.parts[*].text,
        concatenated in order. A regression that reads the wrong field (or
        only the first part) stores a truncated/blank benchmark answer."""
        svc = _make_google_service(
            _google_response(parts_text=("Hallo ", "Welt"), finish_reason_name="STOP")
        )
        out = svc.generate(prompt="frage", model_name="gemini-2.0-flash", max_tokens=128)

        assert out["success"] is True
        # Exact concatenation of both parts, in order.
        assert out["content"] == "Hallo Welt"
        assert out["metadata"]["provider"] == "Google"

    def test_tokens_mapped_from_usage_metadata_no_swap(self):
        """NORMAL tokens: prompt_token_count→prompt_tokens,
        candidates_token_count→completion_tokens, total→total. Distinct
        values catch a prompt/completion swap."""
        svc = _make_google_service(
            _google_response(
                parts_text=("x",),
                prompt_tokens=111,
                completion_tokens=22,
                total_tokens=133,
            )
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["usage"]["prompt_tokens"] == 111
        assert out["usage"]["completion_tokens"] == 22
        assert out["usage"]["total_tokens"] == 133

    def test_finish_reason_stop_maps_not_truncated_not_refusal(self):
        """NORMAL stop: finish_reason 'STOP' → truncated False, refusal
        False, error_type None. The enum is coerced to its ``.name`` string."""
        svc = _make_google_service(
            _google_response(parts_text=("done",), finish_reason_name="STOP")
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["metadata"]["finish_reason"] == "STOP"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False
        assert out["metadata"]["error_type"] is None


class TestGoogleTruncation:
    def test_max_tokens_finish_reason_sets_truncated_true(self):
        """TRUNCATED (load-bearing): finish_reason 'MAX_TOKENS' MUST set
        truncated=True. A truncated legal argument scored as complete is a
        corrupt benchmark input. derive_truncated('MAX_TOKENS') → True."""
        svc = _make_google_service(
            _google_response(
                parts_text=("partial argument that got cut off",),
                finish_reason_name="MAX_TOKENS",
            )
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash", max_tokens=8)

        assert out["metadata"]["finish_reason"] == "MAX_TOKENS"
        assert out["metadata"]["truncated"] is True
        # Still a "successful" non-empty parse — truncation is a flag, not a failure.
        assert out["success"] is True
        assert out["content"] == "partial argument that got cut off"

    def test_normal_stop_is_not_flagged_truncated(self):
        """Negative control for the truncation flag: a normal STOP response
        must NOT be flagged truncated (guards an always-True mutation)."""
        svc = _make_google_service(
            _google_response(parts_text=("complete",), finish_reason_name="STOP")
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")
        assert out["metadata"]["truncated"] is False


class TestGoogleSafetyRefusal:
    def test_safety_finish_reason_with_text_flags_refusal(self):
        """SAFETY with (unusual) text present: finish_reason 'SAFETY' sets
        refusal=True. If text came through, it's a successful parse but the
        refusal flag MUST be raised so downstream filters can exclude it."""
        svc = _make_google_service(
            _google_response(
                parts_text=("some content",), finish_reason_name="SAFETY"
            )
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")
        assert out["metadata"]["finish_reason"] == "SAFETY"
        assert out["metadata"]["refusal"] is True

    def test_safety_block_empty_content_maps_to_content_filter(self):
        """SAFETY + empty content (the real safety-block shape): the empty
        branch returns success=False with error_type 'content_filter'
        (because refusal is True), a non-None error message, and truncated
        derived from 'SAFETY' (which is NOT a truncation reason → False).
        No crash."""
        svc = _make_google_service(
            _google_response(parts_text=("",), finish_reason_name="SAFETY")
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["success"] is False
        assert out["content"] == ""
        assert out["metadata"]["refusal"] is True
        assert out["metadata"]["error_type"] == "content_filter"
        assert out["metadata"]["truncated"] is False
        assert out["error"]  # non-empty error message present

    def test_empty_content_non_safety_maps_to_api_error(self):
        """Empty content WITHOUT safety (e.g. capacity drop, finish_reason
        STOP): success=False, error_type 'api_error' (refusal False), no
        crash. Distinguishes the two empty-content error_type branches."""
        svc = _make_google_service(
            _google_response(parts_text=("   ",), finish_reason_name="STOP")
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["success"] is False
        assert out["content"] == ""
        assert out["metadata"]["refusal"] is False
        assert out["metadata"]["error_type"] == "api_error"


class TestGoogleEmptyAndMissing:
    def test_no_candidates_no_block_returns_empty_not_indexerror(self):
        """EMPTY / no-candidates: a response with candidates=[] must NOT
        IndexError on candidates[0]. With no prompt_feedback block_reason it
        falls through to the empty-content branch → success=False, content
        '', error_type 'api_error'."""
        resp = _google_response(with_candidate=False)
        # No prompt_feedback attribute at all → the block-reason path is skipped.
        svc = _make_google_service(resp)
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["success"] is False
        assert out["content"] == ""
        assert out["metadata"]["error_type"] == "api_error"

    def test_prompt_level_block_reason_raises_then_classified_content_filter(self):
        """No candidates BUT prompt_feedback.block_reason set: the parser
        raises ValueError('...content policy...'), which the except block
        turns into an error response classified as 'content_filter'. Pins
        that a prompt-level safety block is surfaced, not swallowed."""
        resp = _google_response(with_candidate=False)
        resp.prompt_feedback = types.SimpleNamespace(block_reason="SAFETY")
        svc = _make_google_service(resp)
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash")

        assert out["success"] is False
        assert out["metadata"]["error_type"] == "content_filter"
        assert out["metadata"]["truncated"] is False

    def test_missing_usage_metadata_falls_back_no_crash(self):
        """MISSING usage: with usage_metadata None the parser estimates
        tokens from char length (len/4) instead of crashing. We don't pin
        the estimate's exact value beyond it being a non-negative int and
        the call succeeding with the real content."""
        svc = _make_google_service(
            _google_response(parts_text=("abcd efgh",), with_usage=False)
        )
        out = svc.generate(prompt="some prompt", model_name="gemini-2.0-flash")

        assert out["success"] is True
        assert out["content"] == "abcd efgh"
        assert isinstance(out["usage"]["prompt_tokens"], int)
        assert isinstance(out["usage"]["completion_tokens"], int)
        assert out["usage"]["prompt_tokens"] >= 0
        assert out["usage"]["completion_tokens"] >= 0


class TestGoogleThinkingTokens:
    def test_thinking_budget_does_not_shrink_max_output_tokens(self):
        """THINKING-tokens subtlety: for a thinking-capable model
        (e.g. 'gemini-2.5-flash'), the service sets a ThinkingConfig with
        the requested thinking_budget but passes ``max_output_tokens`` to
        the API UNCHANGED (== max_tokens). i.e. there is NO subtraction:
        thinking_budget is configured, not netted out of max_output_tokens.

        Boundary pinned: max_tokens=4096, thinking_budget=1024 → the config
        sent to generate_content has max_output_tokens == 4096 (not 3072)
        and thinking_config.thinking_budget == 1024. A future refactor that
        starts subtracting (4096-1024=3072) would change this assertion and
        must be a deliberate decision, not a silent drift."""
        svc = _make_google_service(
            _google_response(parts_text=("thought-through answer",), finish_reason_name="STOP")
        )
        out = svc.generate(
            prompt="p",
            model_name="gemini-2.5-flash",
            max_tokens=4096,
            thinking_budget=1024,
        )
        assert out["success"] is True

        # Inspect exactly what was passed to the SDK.
        call = svc.client.models.generate_content.call_args
        config = call.kwargs["config"]
        assert config.max_output_tokens == 4096  # unchanged — no thinking subtraction
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget == 1024

    def test_non_thinking_model_gets_no_thinking_config(self):
        """Boundary: a non-thinking model ('gemini-2.0-flash') gets
        thinking_config=None and max_output_tokens still == max_tokens."""
        svc = _make_google_service(
            _google_response(parts_text=("answer",), finish_reason_name="STOP")
        )
        out = svc.generate(prompt="p", model_name="gemini-2.0-flash", max_tokens=2048)
        assert out["success"] is True

        config = svc.client.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config is None
        assert config.max_output_tokens == 2048


# ===========================================================================
# DEEPINFRA — OpenAI-compatible parsing
# ===========================================================================
class TestDeepInfraNormal:
    def test_content_from_choices0_message_content(self, patch_aiohttp):
        """NORMAL: content = choices[0].message.content, verbatim."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {
                            "message": {"content": "Die Antwort lautet 42."},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 200,
                        "completion_tokens": 30,
                        "total_tokens": 230,
                    },
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="frage", model_name="DeepSeek-V3.1", max_tokens=64)

        assert out["success"] is True
        assert out["content"] == "Die Antwort lautet 42."
        assert out["metadata"]["provider"] == "DeepInfra"
        # refusal is hardcoded False on the DeepInfra success path.
        assert out["metadata"]["refusal"] is False

    def test_tokens_mapped_no_swap(self, patch_aiohttp):
        """NORMAL tokens: usage.prompt_tokens / completion_tokens / total
        map straight through. Distinct values catch a swap."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {"message": {"content": "x"}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 321,
                        "completion_tokens": 12,
                        "total_tokens": 333,
                    },
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["usage"]["prompt_tokens"] == 321
        assert out["usage"]["completion_tokens"] == 12
        assert out["usage"]["total_tokens"] == 333

    def test_finish_reason_stop_not_truncated(self, patch_aiohttp):
        """NORMAL stop: finish_reason 'stop' → truncated False (negative
        control for the truncation flag)."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {"message": {"content": "complete"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["truncated"] is False


class TestDeepInfraTruncation:
    def test_length_finish_reason_sets_truncated_true(self, patch_aiohttp):
        """TRUNCATED (load-bearing): finish_reason 'length' MUST set
        truncated=True. derive_truncated('length') → True. A cut-off answer
        flagged as complete corrupts the benchmark input."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {
                            "message": {"content": "answer cut off mid-sen"},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1", max_tokens=8)

        assert out["metadata"]["finish_reason"] == "length"
        assert out["metadata"]["truncated"] is True
        assert out["success"] is True
        assert out["content"] == "answer cut off mid-sen"


class TestDeepInfraEmptyAndMissing:
    def test_empty_choices_yields_empty_content_none_finish_reason(self, patch_aiohttp):
        """EMPTY: choices=[] must NOT IndexError. content '', finish_reason
        None (the ``result.get('choices')`` guard short-circuits)."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 0, "total_tokens": 7},
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["content"] == ""
        assert out["metadata"]["finish_reason"] is None
        assert out["metadata"]["truncated"] is False

    def test_empty_string_content_stays_empty(self, patch_aiohttp):
        """DeepInfra empty content: a present-but-empty message.content
        stays '' (not None, no crash)."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {"message": {"content": ""}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3},
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")
        assert out["content"] == ""

    def test_missing_usage_defaults_tokens_zero(self, patch_aiohttp):
        """MISSING usage: no 'usage' key → all token counts default to 0
        (input 0, output 0, total = 0+0). No crash."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                json_body={
                    "choices": [
                        {"message": {"content": "hi"}, "finish_reason": "stop"}
                    ]
                    # no "usage"
                }
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["success"] is True
        assert out["content"] == "hi"
        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0
        assert out["usage"]["total_tokens"] == 0

    def test_http_error_status_becomes_error_response(self, patch_aiohttp, monkeypatch):
        """HTTP 5xx: each attempt raises RetryableUpstreamError('HTTP 503: ...'),
        the retry decorator backs off and re-attempts until exhausted
        (1 initial + 5 retries), and the undecorated _generate_async outer
        converts the terminal raise into a success=False error response (no
        partial/garbage content stored) carrying the full attempt trail."""
        delays = []

        async def _record(delay):
            delays.append(delay)

        monkeypatch.setattr(di_mod, "_sleep", _record)
        patch_aiohttp(
            lambda: _FakeAioResponse(status=503, text_body="upstream unavailable")
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["success"] is False
        assert out["content"] == ""
        assert "503" in (out.get("error") or "")
        # Retry machinery: 6 recorded attempts, 5 instant backoffs.
        assert out["metadata"]["retry_count"] == 6
        assert len(delays) == 5


class TestDeepInfraRetryAndScrub:
    """Retry split behavior on the DeepInfra client: 429/5xx back off and
    re-attempt (through the patched ``_sleep`` seam), auth errors fail fast
    in one attempt, and — negative control for the BYOM endpoint scrubber —
    official-provider error text is persisted VERBATIM (DeepInfraService
    inherits the identity ``_sanitize_error_text`` hook)."""

    def test_deepinfra_429_retries_then_succeeds(self, patch_aiohttp, monkeypatch):
        """429 → RetryableUpstreamError → exactly one backoff, then the 200
        parses normally; success metadata carries the single rate-limit
        attempt in its retry trail."""
        delays = []

        async def _record(delay):
            delays.append(delay)

        monkeypatch.setattr(di_mod, "_sleep", _record)

        responses = [
            _FakeAioResponse(status=429, text_body="too many requests"),
            _FakeAioResponse(
                json_body={
                    "choices": [
                        {
                            "message": {"content": "nach dem Backoff"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 4,
                        "total_tokens": 13,
                    },
                }
            ),
        ]
        # Stateful factory: pop until only the terminal response remains.
        patch_aiohttp(
            lambda: responses.pop(0) if len(responses) > 1 else responses[0]
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["success"] is True
        assert out["content"] == "nach dem Backoff"
        assert out["metadata"]["retry_count"] == 1
        assert out["metadata"]["retry_attempts"][0]["is_rate_limit"] is True
        assert out["metadata"]["retry_attempts"][0]["retried"] is True
        assert len(delays) == 1

    def test_deepinfra_401_fails_fast(self, patch_aiohttp, monkeypatch):
        """Auth failures are NOT transient: exactly one HTTP attempt, zero
        backoffs, error dict classified as 'auth'."""
        delays = []

        async def _record(delay):
            delays.append(delay)

        monkeypatch.setattr(di_mod, "_sleep", _record)

        calls = {"n": 0}

        def _factory():
            calls["n"] += 1
            return _FakeAioResponse(status=401, text_body="invalid api key")

        patch_aiohttp(_factory)
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["success"] is False
        assert "401" in out["error"]
        assert calls["n"] == 1
        assert out["metadata"]["retry_count"] == 1
        assert out["metadata"]["error_type"] == "auth"
        assert delays == []

    def test_deepinfra_error_body_kept_verbatim_no_scrub(self, patch_aiohttp):
        """Negative control for the BYOM endpoint scrubber: DeepInfra is an
        OFFICIAL provider, so its error text must survive verbatim (identity
        _sanitize_error_text) — hostname and all — in both response['error']
        and the retry-history entry. A regression that scrubs official
        errors would destroy debuggability of real upstream incidents."""
        patch_aiohttp(
            lambda: _FakeAioResponse(
                status=404,
                text_body="no route to internal-host.example.org",
            )
        )
        svc = _make_deepinfra_service()
        out = svc.generate(prompt="p", model_name="DeepSeek-V3.1")

        assert out["success"] is False
        assert out["error"].startswith("HTTP 404:")
        assert "internal-host.example.org" in out["error"]
        attempts = out["metadata"]["retry_attempts"]
        assert len(attempts) == 1
        assert "internal-host.example.org" in attempts[0]["error"]
