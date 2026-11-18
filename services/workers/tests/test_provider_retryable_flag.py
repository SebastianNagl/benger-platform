"""The uniform ``metadata.retryable`` flag on every provider's error response.

Callers that repeat a failed generation (the benger-extended Bewertungsbogen
generator) must stop at the first error a retry cannot fix and keep retrying
the transient ones. Before this flag only DeepInfra and Custom endpoints
recorded ``retry_attempts[-1].retryable``; the official providers exposed only
``error_type``, where an unknown model (404), a 5xx and an unresolvable host
all read ``api_error``.

Each provider's ``generate()`` is driven with a fake client (or a fake
``aiohttp`` seam) that raises a real SDK exception of each class, and the
returned error dict must carry the expected flag. ``error_type`` is pinned
next to it so the flag never shifts the existing classification. No network,
no real backoff sleeps.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")
os.environ.pop("E2E_TEST_MODE", None)

import asyncio  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import aiohttp  # noqa: E402
import anthropic  # noqa: E402
import cohere  # noqa: E402
import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402

import ai_services.anthropic_service  # noqa: E402,F401
import ai_services.cohere_service  # noqa: E402,F401
import ai_services.deepinfra_service  # noqa: E402,F401
import ai_services.google_service  # noqa: E402,F401
import ai_services.grok_service  # noqa: E402,F401
import ai_services.mistral_service  # noqa: E402,F401
import ai_services.openai_compatible_service  # noqa: E402,F401
import ai_services.openai_service  # noqa: E402,F401
from ai_services.base_service import (  # noqa: E402
    RetryableUpstreamError,
    classify_error_type,
    classify_retryable,
)

anthropic_mod = sys.modules["ai_services.anthropic_service"]
cohere_mod = sys.modules["ai_services.cohere_service"]
di_mod = sys.modules["ai_services.deepinfra_service"]
google_mod = sys.modules["ai_services.google_service"]
grok_mod = sys.modules["ai_services.grok_service"]
mistral_mod = sys.modules["ai_services.mistral_service"]
ocs_mod = sys.modules["ai_services.openai_compatible_service"]
openai_mod = sys.modules["ai_services.openai_service"]


# --------------------------------------------------------------------------
# Real SDK exceptions, built the way each SDK builds them from a response.
# --------------------------------------------------------------------------


def _openai_status(cls, status, message, code=None):
    import httpx2

    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx2.Response(status, request=request)
    body = {"message": message, "type": "error", "code": code}
    return cls(message, response=response, body=body)


def _openai_request():
    import httpx2

    return httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")


def _openai_dns_failure():
    try:
        try:
            raise socket.gaierror(-2, "Name or service not known")
        except socket.gaierror as cause:
            raise openai.APIConnectionError(request=_openai_request()) from cause
    except openai.APIConnectionError as exc:
        return exc


def _anthropic_status(cls, status, message, error_type="error"):
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    body = {"type": "error", "error": {"type": error_type, "message": message}}
    return cls(message, response=response, body=body)


def _anthropic_request():
    import httpx2

    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _genai(cls, code, status, message):
    return cls(code, {"error": {"code": code, "status": status, "message": message}})


def _mistral(status, body):
    from mistralai.client import errors as mistral_errors

    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    response = httpx.Response(status, request=request, text=body)
    return mistral_errors.SDKError("API error occurred", response, body)


def _aiohttp_status(status, message):
    info = aiohttp.RequestInfo(
        url="https://api.x.ai/v1/chat/completions",
        method="POST",
        headers={},
        real_url="https://api.x.ai/v1/chat/completions",
    )
    return aiohttp.ClientResponseError(info, (), status=status, message=message)


def _aiohttp_dns_failure():
    key = MagicMock()
    key.host, key.port, key.ssl = "no-such-host.invalid", 443, True
    return aiohttp.ClientConnectorError(key, socket.gaierror(-2, "Name or service not known"))


# (label, exception factory, retryable, error_type). error_type is the value
# classify_error_type already gave before the flag existed.
OPENAI_CASES = [
    ("invalid key 401", lambda: _openai_status(openai.AuthenticationError, 401, "Incorrect API key provided", "invalid_api_key"), False, "auth"),
    ("forbidden 403", lambda: _openai_status(openai.PermissionDeniedError, 403, "Project does not have access"), False, "auth"),
    ("unknown model 404", lambda: _openai_status(openai.NotFoundError, 404, "The model `gpt-9` does not exist", "model_not_found"), False, "api_error"),
    ("bad request 400", lambda: _openai_status(openai.BadRequestError, 400, "Unsupported parameter: 'top_k'"), False, "api_error"),
    ("context length 400", lambda: _openai_status(openai.BadRequestError, 400, "This model's maximum context length is 128000 tokens", "context_length_exceeded"), False, "context_length"),
    ("content filter 400", lambda: _openai_status(openai.BadRequestError, 400, "Your request was rejected by our content filter", "content_filter"), False, "content_filter"),
    ("rate limit 429", lambda: _openai_status(openai.RateLimitError, 429, "Rate limit reached for requests", "rate_limit_exceeded"), True, "rate_limit"),
    ("exhausted quota 429", lambda: _openai_status(openai.RateLimitError, 429, "You exceeded your current quota, please check your plan and billing details.", "insufficient_quota"), False, "rate_limit"),
    ("server error 500", lambda: _openai_status(openai.InternalServerError, 500, "The server had an error"), True, "api_error"),
    ("timeout", lambda: openai.APITimeoutError(request=_openai_request()), True, "timeout"),
    ("connection error", lambda: openai.APIConnectionError(request=_openai_request()), True, "api_error"),
    ("unresolvable host", _openai_dns_failure, False, "api_error"),
]

ANTHROPIC_CASES = [
    ("invalid key 401", lambda: _anthropic_status(anthropic.AuthenticationError, 401, "invalid x-api-key", "authentication_error"), False, "auth"),
    ("unknown model 404", lambda: _anthropic_status(anthropic.NotFoundError, 404, "model: claude-9", "not_found_error"), False, "api_error"),
    ("exhausted credit 400", lambda: _anthropic_status(anthropic.BadRequestError, 400, "Your credit balance is too low to access the Anthropic API.", "invalid_request_error"), False, "api_error"),
    ("context length 400", lambda: _anthropic_status(anthropic.BadRequestError, 400, "prompt is too long: 250000 tokens > 200000 maximum context length", "invalid_request_error"), False, "context_length"),
    ("rate limit 429", lambda: _anthropic_status(anthropic.RateLimitError, 429, "Number of request tokens has exceeded your rate limit", "rate_limit_error"), True, "rate_limit"),
    ("server error 500", lambda: _anthropic_status(anthropic.InternalServerError, 500, "Internal server error", "api_error"), True, "api_error"),
    ("overloaded 529", lambda: _anthropic_status(anthropic.APIStatusError, 529, "Overloaded", "overloaded_error"), True, "api_error"),
    ("timeout", lambda: anthropic.APITimeoutError(request=_anthropic_request()), True, "timeout"),
    ("connection error", lambda: anthropic.APIConnectionError(request=_anthropic_request()), True, "api_error"),
]

GOOGLE_CASES = [
    ("invalid key 400", lambda: _genai(genai_errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), False, "api_error"),
    ("forbidden 403", lambda: _genai(genai_errors.ClientError, 403, "PERMISSION_DENIED", "Permission denied on resource project"), False, "auth"),
    ("unknown model 404", lambda: _genai(genai_errors.ClientError, 404, "NOT_FOUND", "models/gemini-9 is not found for API version v1beta"), False, "api_error"),
    ("resource exhausted 429", lambda: _genai(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED", "Resource has been exhausted (e.g. check quota)."), True, "rate_limit"),
    ("server error 500", lambda: _genai(genai_errors.ServerError, 500, "INTERNAL", "An internal error has occurred."), True, "api_error"),
    ("unavailable 503", lambda: _genai(genai_errors.ServerError, 503, "UNAVAILABLE", "The model is overloaded. Please try again later."), True, "api_error"),
    ("prompt blocked", lambda: ValueError("Google blocked this request due to content policy: PROHIBITED_CONTENT."), False, "content_filter"),
]

MISTRAL_CASES = [
    ("invalid key 401", lambda: _mistral(401, '{"message":"Unauthorized","request_id":"x"}'), False, "auth"),
    ("unknown model 400", lambda: _mistral(400, '{"object":"error","message":"Invalid model: mistral-9","type":"invalid_model","code":"1500"}'), False, "api_error"),
    ("unknown model 404", lambda: _mistral(404, '{"object":"error","message":"Not Found"}'), False, "api_error"),
    ("rate limit 429", lambda: _mistral(429, '{"message":"Requests rate limit exceeded"}'), True, "rate_limit"),
    ("server error 503", lambda: _mistral(503, '{"message":"Service unavailable"}'), True, "api_error"),
]

COHERE_CASES = [
    ("invalid key 401", lambda: cohere.UnauthorizedError(body={"message": "invalid api token"}), False, "auth"),
    ("unknown model 404", lambda: cohere.NotFoundError(body={"message": "model 'command-z' not found"}), False, "api_error"),
    ("bad request 400", lambda: cohere.BadRequestError(body={"message": "invalid request: max_tokens"}), False, "api_error"),
    ("rate limit 429", lambda: cohere.TooManyRequestsError(body={"message": "You are using a Trial key, which is limited"}), True, "rate_limit"),
    ("server error 500", lambda: cohere.InternalServerError(body={"message": "internal server error"}), True, "api_error"),
    ("gateway timeout 504", lambda: cohere.GatewayTimeoutError(body={"message": "upstream"}), True, "timeout"),
]

GROK_CASES = [
    ("invalid key 401", lambda: _aiohttp_status(401, "Unauthorized"), False, "auth"),
    ("unknown model 404", lambda: _aiohttp_status(404, "Not Found"), False, "api_error"),
    ("bad request 400", lambda: _aiohttp_status(400, "Bad Request"), False, "api_error"),
    ("rate limit 429", lambda: _aiohttp_status(429, "Too Many Requests"), True, "rate_limit"),
    ("server error 502", lambda: _aiohttp_status(502, "Bad Gateway"), True, "api_error"),
    ("timeout", lambda: asyncio.TimeoutError(), True, "timeout"),
    ("connection reset", lambda: aiohttp.ServerDisconnectedError(), True, "api_error"),
    ("unresolvable host", _aiohttp_dns_failure, False, "api_error"),
]

# DeepInfra and Custom endpoints raise these from their own HTTP path.
HTTP_PATH_CASES = [
    ("invalid key 401", lambda: Exception('HTTP 401: {"detail":{"error":"Invalid token"}}'), False, "auth"),
    ("unknown model 404", lambda: Exception('HTTP 404: {"detail":{"error":"Model is not available"}}'), False, "api_error"),
    ("bad request 400", lambda: Exception('HTTP 400: {"error":"bad request"}'), False, "api_error"),
    ("rate limit 429", lambda: RetryableUpstreamError('HTTP 429: {"error":"too many requests"}', status=429), True, "rate_limit"),
    ("exhausted quota 429", lambda: RetryableUpstreamError('HTTP 429: {"error":{"code":"insufficient_quota"}}', status=429), False, "rate_limit"),
    ("server error 503", lambda: RetryableUpstreamError("HTTP 503: upstream unavailable", status=503), True, "api_error"),
    ("timeout", lambda: asyncio.TimeoutError(), True, "timeout"),
    ("connection reset", lambda: aiohttp.ServerDisconnectedError(), True, "api_error"),
    ("unresolvable host", _aiohttp_dns_failure, False, "api_error"),
]

# Custom endpoints alone pass the url_guard pre-flight.
CUSTOM_CASES = HTTP_PATH_CASES + [
    ("url_guard rejection", lambda: ValueError("The endpoint host is not reachable or is not a public address."), False, "api_error"),
]


# --------------------------------------------------------------------------
# Drivers: one generate() per provider with the failure injected at the
# provider's own client seam.
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _instant_sync_backoff(monkeypatch):
    """The sync providers' decorators call time.sleep between attempts."""
    for mod in (openai_mod, anthropic_mod, google_mod, mistral_mod, cohere_mod, grok_mod):
        if hasattr(mod, "time"):
            monkeypatch.setattr(mod.time, "sleep", lambda *_: None)


def _run_openai(exc, monkeypatch):
    svc = openai_mod.OpenAIService(api_key="sk-test")
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = exc
    svc.client.responses.create.side_effect = exc
    return svc.generate("q", "s", model_name="gpt-4o")


def _run_anthropic(exc, monkeypatch):
    svc = anthropic_mod.AnthropicService(api_key="sk-ant-test")
    svc.client = MagicMock()
    svc.client.messages.create.side_effect = exc
    svc.client.messages.stream.side_effect = exc
    return svc.generate("q", "s", model_name="claude-sonnet-4-5")


def _run_google(exc, monkeypatch):
    svc = google_mod.GoogleService(api_key="google-test")
    svc.client = MagicMock()
    svc.client.models.generate_content.side_effect = exc
    return svc.generate("q", "s", model_name="gemini-2.5-flash")


def _run_mistral(exc, monkeypatch):
    svc = mistral_mod.MistralService(api_key="mistral-test")
    svc.client = MagicMock()
    svc.client.chat.complete.side_effect = exc
    return svc.generate("q", "s", model_name="mistral-large-latest")


def _run_cohere(exc, monkeypatch):
    svc = cohere_mod.CohereService(api_key="cohere-test")
    svc.client = MagicMock()
    svc.client.chat.side_effect = exc
    return svc.generate("q", "s", model_name="command-r-plus")


def _raising_aiohttp(exc):
    class _Session:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise exc

    fake = types.SimpleNamespace(
        ClientSession=_Session,
        ClientTimeout=lambda total=None: total,
        ClientConnectionError=aiohttp.ClientConnectionError,
    )
    return fake


def _run_grok(exc, monkeypatch):
    monkeypatch.setattr(grok_mod, "aiohttp", _raising_aiohttp(exc))
    svc = grok_mod.GrokService(api_key="xai-test")
    return svc.generate("q", "s", model_name="grok-3")


def _run_deepinfra(exc, monkeypatch):
    monkeypatch.setattr(di_mod, "aiohttp", _raising_aiohttp(exc))
    svc = di_mod.DeepInfraService(api_key="deepinfra-test")
    return svc.generate("q", "s", model_name="meta-llama/Llama-3.3-70B-Instruct")


def _run_custom(exc, monkeypatch):
    import url_guard

    if isinstance(exc, ValueError):
        # The pre-flight itself rejects the host.
        def _reject(url, **kwargs):
            raise exc

        monkeypatch.setattr(url_guard, "resolve_and_validate", _reject)
    else:
        monkeypatch.setattr(
            url_guard, "resolve_and_validate", lambda u, **k: (u, ["203.0.113.7"])
        )
        monkeypatch.setattr(url_guard, "pinned_connector", lambda ips: object())
        monkeypatch.setattr(ocs_mod, "aiohttp", _raising_aiohttp(exc))
    svc = ocs_mod.OpenAICompatibleService(
        base_url="https://models.example.org/v1",
        api_key="ck-test",
        endpoint_model_name="meta-llama/Llama-3.3-70B-Instruct",
        input_cost_per_million=1.0,
        output_cost_per_million=1.0,
        supports_seed=False,
    )
    return svc.generate("q", "s", model_name="custom-3f2b6a9e-0000-4111-8222-333344445555")


PROVIDERS = [
    ("openai", _run_openai, OPENAI_CASES),
    ("anthropic", _run_anthropic, ANTHROPIC_CASES),
    ("google", _run_google, GOOGLE_CASES),
    ("mistral", _run_mistral, MISTRAL_CASES),
    ("cohere", _run_cohere, COHERE_CASES),
    ("grok", _run_grok, GROK_CASES),
    ("deepinfra", _run_deepinfra, HTTP_PATH_CASES),
    ("custom", _run_custom, CUSTOM_CASES),
]

PARAMS = [
    pytest.param(run, factory, retryable, error_type, id=f"{name}-{label}")
    for name, run, cases in PROVIDERS
    for label, factory, retryable, error_type in cases
]


@pytest.mark.parametrize("run, factory, retryable, error_type", PARAMS)
def test_error_response_carries_retryable_flag(run, factory, retryable, error_type, monkeypatch):
    exc = factory()
    # The classifier itself, on the exception as the SDK raises it.
    assert classify_retryable(exc) is retryable
    assert classify_error_type(exc) == error_type

    result = run(factory(), monkeypatch)

    assert result["success"] is False
    assert result["metadata"]["retryable"] is retryable
    assert result["metadata"]["error_type"] == error_type


class TestClassifierRules:
    """Rules that do not depend on one provider's exception shape."""

    def test_missing_key_value_error_fails_fast(self):
        exc = ValueError("OpenAI service is not available - check OPENAI_API_KEY configuration")
        assert classify_retryable(exc) is False

    def test_unknown_plain_exception_fails_fast(self):
        assert classify_retryable(KeyError("choices")) is False

    def test_malformed_json_answer_is_retryable(self):
        # A fresh sample can come back as valid JSON.
        exc = ValueError("Could not parse JSON from model output")
        assert classify_error_type(exc) == "parse_error"
        assert classify_retryable(exc) is True

    def test_untyped_rate_limit_text_is_retryable(self):
        assert classify_retryable(Exception("rate limit exceeded, slow down")) is True

    def test_builtin_timeout_and_connection_errors_are_retryable(self):
        assert classify_retryable(TimeoutError("read timed out")) is True
        assert classify_retryable(ConnectionResetError("peer reset")) is True

    def test_dns_failure_deep_in_cause_chain_fails_fast(self):
        try:
            try:
                raise socket.gaierror(-3, "Temporary failure in name resolution")
            except socket.gaierror as inner:
                raise ConnectionError("connect failed") from inner
        except ConnectionError as outer:
            assert classify_retryable(outer) is False

    def test_billing_hard_limit_fails_fast(self):
        exc = _openai_status(
            openai.RateLimitError, 429, "Billing hard limit has been reached", "billing_hard_limit_reached"
        )
        assert classify_retryable(exc) is False

    @pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
    def test_retryable_statuses(self, status):
        assert classify_retryable(_aiohttp_status(status, "x")) is True

    @pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 413, 422])
    def test_non_retryable_statuses(self, status):
        assert classify_retryable(_aiohttp_status(status, "x")) is False

    @pytest.mark.parametrize("status", [200, 302])
    def test_non_error_status_does_not_decide(self, status):
        # A status below 400 is not an HTTP error: the error body decides.
        overloaded = _anthropic_status(anthropic.APIStatusError, status, "Overloaded", "overloaded_error")
        invalid = _anthropic_status(anthropic.APIStatusError, status, "bad input", "invalid_request_error")
        assert classify_retryable(overloaded) is True
        assert classify_retryable(invalid) is False

    def test_deepinfra_decorator_still_retries_exhausted_quota(self):
        # The flag only describes the error: DeepInfra's backoff predicate
        # keeps backing off on every 429, as before.
        exc = RetryableUpstreamError('HTTP 429: {"error":{"code":"insufficient_quota"}}', status=429)
        assert di_mod._is_retryable_error(exc) is True
        assert classify_retryable(exc) is False


class TestGoogleEmptyResponse:
    """Google returns an empty answer as an error dict it builds itself."""

    @staticmethod
    def _empty_response(finish_reason):
        candidate = types.SimpleNamespace(
            content=types.SimpleNamespace(parts=[]),
            finish_reason=finish_reason,
            text="",
        )
        return types.SimpleNamespace(
            candidates=[candidate],
            text="",
            usage_metadata=types.SimpleNamespace(
                prompt_token_count=3, candidates_token_count=0, total_token_count=3
            ),
            prompt_feedback=None,
        )

    def _generate(self, finish_reason):
        svc = google_mod.GoogleService(api_key="google-test")
        svc.client = MagicMock()
        svc.client.models.generate_content.return_value = self._empty_response(finish_reason)
        return svc.generate("q", "s", model_name="gemini-2.5-flash")

    def test_safety_block_is_not_retryable(self):
        result = self._generate("SAFETY")
        assert result["success"] is False
        assert result["metadata"]["error_type"] == "content_filter"
        assert result["metadata"]["retryable"] is False

    def test_empty_answer_without_block_is_retryable(self):
        result = self._generate("STOP")
        assert result["success"] is False
        assert result["metadata"]["error_type"] == "api_error"
        assert result["metadata"]["retryable"] is True


def _anthropic_sse_client(events):
    """A real Anthropic client whose /v1/messages answers HTTP 200 with the
    given server-sent events, as the API does when a stream fails midway."""
    import httpx2

    payload = "".join(f"event: {name}\ndata: {data}\n\n" for name, data in events)

    def handler(request):
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=payload.encode()
        )

    return anthropic.Anthropic(
        api_key="sk-ant-test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


_MESSAGE_START = (
    '{"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant",'
    '"model":"claude-sonnet-4-5","content":[],"stop_reason":null,"stop_sequence":null,'
    '"usage":{"input_tokens":10,"output_tokens":1}}}'
)


@pytest.mark.parametrize(
    "error_type, retryable",
    [("overloaded_error", True), ("api_error", True), ("invalid_request_error", False)],
)
def test_anthropic_midstream_error_after_200(error_type, retryable):
    # A large max_tokens takes the messages.stream path; the API has already
    # answered 200 when it sends the error event.
    error_event = '{"type":"error","error":{"type":"%s","message":"Overloaded"}}' % error_type
    svc = anthropic_mod.AnthropicService(api_key="sk-ant-test")
    svc.client = _anthropic_sse_client([("message_start", _MESSAGE_START), ("error", error_event)])

    result = svc.generate("q", "s", model_name="claude-sonnet-4-5", max_tokens=20000)

    assert result["success"] is False
    assert result["metadata"]["retryable"] is retryable
