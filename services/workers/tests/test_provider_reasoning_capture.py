"""Reasoning text is captured next to the answer for every provider shape.

WHY THIS FILE EXISTS
--------------------
Reasoning models return their reasoning beside the answer, in a different
place per provider. Before this capture every service read only the answer
and dropped the rest, so a self-hosted Qwen3 endpoint (vLLM behind GPUStack)
that put its output into ``message.reasoning`` lost it entirely. Each
service now returns it as ``response["reasoning"]`` (``None`` when the
provider sent none), and these tests pin three things per shape:

* the reasoning text is read from where that provider puts it;
* the answer (``response["content"]``) is exactly what it was before, so
  reasoning never leaks into parsing or scoring;
* reasoning never stands in for an empty answer (the Qwen3 case keeps
  ``content == ""``; falling back is out of scope).

The fixtures in ``fixtures/provider_reasoning/`` are response bodies in each
provider's documented wire shape. Where an SDK parses the body, the test
feeds the body through the real SDK model (``anthropic.types.Message``,
``google.genai.types.GenerateContentResponse``, ``openai`` chat/Responses
types, ``mistralai`` and ``cohere`` response models), so the extraction is
tested against the objects the service sees in production. The aiohttp
services (custom OpenAI-compatible endpoints, DeepInfra, Grok) get the raw
JSON dict, which is what they parse.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")
os.environ.pop("E2E_TEST_MODE", None)

import json  # noqa: E402
import pathlib  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from ai_services import reasoning as reasoning_mod  # noqa: E402
from ai_services.anthropic_service import AnthropicService  # noqa: E402
from ai_services.cohere_service import CohereService  # noqa: E402
from ai_services.deepinfra_service import DeepInfraService  # noqa: E402
from ai_services.google_service import GoogleService  # noqa: E402
from ai_services.grok_service import GrokService  # noqa: E402
from ai_services.mistral_service import MistralService  # noqa: E402
from ai_services.openai_compatible_service import OpenAICompatibleService  # noqa: E402
from ai_services.openai_service import OpenAIService  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "provider_reasoning"


def _fixture(name: str) -> dict:
    body = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    body.pop("_source", None)
    return body


# ---------------------------------------------------------------------------
# aiohttp plumbing (custom endpoints, DeepInfra, Grok)
# ---------------------------------------------------------------------------
class _FakeStream:
    def __init__(self, raw: bytes):
        self._raw = raw

    async def iter_chunked(self, n):
        yield self._raw


class _FakeResponse:
    def __init__(self, body: dict):
        self.status = 200
        self.content_length = None
        self._raw = json.dumps(body).encode("utf-8")
        self.content = _FakeStream(self._raw)

    def raise_for_status(self):
        return None

    async def json(self):
        return json.loads(self._raw)

    async def text(self):
        return self._raw.decode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    body: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return _FakeResponse(type(self).body)


@pytest.fixture()
def fake_http(monkeypatch):
    """Serve a fixture body to every aiohttp-based service."""
    import url_guard

    monkeypatch.setattr(url_guard, "resolve_and_validate", lambda u, **k: (u, ["203.0.113.7"]))
    monkeypatch.setattr(url_guard, "pinned_connector", lambda ips: None)

    def _serve(body: dict):
        _FakeSession.body = body
        return _FakeSession

    targets = [
        "ai_services.openai_compatible_service.aiohttp.ClientSession",
        "ai_services.deepinfra_service.aiohttp.ClientSession",
        "ai_services.grok_service.aiohttp.ClientSession",
    ]
    patchers = [patch(t, _FakeSession) for t in targets]
    for p in patchers:
        p.start()
    yield _serve
    for p in patchers:
        p.stop()


def _custom_service() -> OpenAICompatibleService:
    return OpenAICompatibleService(
        base_url="https://gpustack.example.org/v1",
        api_key="ck-test",
        endpoint_model_name="qwen3-4b-instruct-2507",
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible custom endpoints (vLLM / SGLang behind GPUStack)
# ---------------------------------------------------------------------------
class TestCustomEndpointReasoning:
    def test_reasoning_only_response_keeps_empty_answer(self, fake_http):
        """The captain's Qwen3 case: content null, output in message.reasoning.
        The reasoning is stored; the answer stays empty (no fallback)."""
        fake_http(_fixture("vllm_qwen3_reasoning_only"))
        out = _custom_service().generate(prompt="p", model_name="custom-x")
        assert out["success"] is True
        assert out["content"] == ""
        assert out["reasoning"] == (
            "Die Klage ist zulässig und begründet, weil der Anspruch aus "
            "§ 433 Abs. 2 BGB besteht."
        )

    def test_reasoning_content_beside_answer(self, fake_http):
        fake_http(_fixture("vllm_reasoning_content"))
        out = _custom_service().generate(prompt="p", model_name="custom-x")
        assert out["content"] == "Der Anspruch besteht."
        assert out["reasoning"] == (
            "Zuerst prüfe ich die Anspruchsgrundlage § 433 Abs. 2 BGB.\n"
            "Dann die Einwendungen."
        )

    def test_no_reasoning_is_none(self, fake_http):
        fake_http(_fixture("openai_chat_plain"))
        out = _custom_service().generate(prompt="p", model_name="custom-x")
        assert out["content"] == "Die Berufung ist unzulässig."
        assert out["reasoning"] is None

    def test_structured_output_carries_reasoning_and_validates_answer_only(self, fake_http):
        """The structured path validates the ANSWER against the schema; the
        reasoning rides along untouched and is never parsed."""
        body = _fixture("vllm_reasoning_content")
        body["choices"][0]["message"]["content"] = '{"answer": "ja"}'
        fake_http(body)
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        out = _custom_service().generate_structured(
            prompt="p", system_prompt="s", json_schema=schema, model_name="custom-x"
        )
        assert json.loads(out["content"]) == {"answer": "ja"}
        assert out["metadata"]["validation_status"] == "valid"
        assert out["reasoning"].startswith("Zuerst prüfe ich")


class TestDeepInfraAndGrokReasoning:
    def test_deepinfra_reasoning_content(self, fake_http):
        fake_http(_fixture("deepinfra_deepseek_r1"))
        out = DeepInfraService(api_key="di-test").generate(
            prompt="p", model_name="deepseek-ai/DeepSeek-R1-0528"
        )
        assert out["content"] == "Ergebnis: Der Vertrag ist wirksam."
        assert out["reasoning"] == (
            "Angebot und Annahme liegen vor (§§ 145 ff. BGB). "
            "Kein Nichtigkeitsgrund ersichtlich."
        )

    def test_grok_reasoning_content(self, fake_http):
        fake_http(_fixture("xai_grok_3_mini"))
        out = GrokService(api_key="xai-test").generate(prompt="p", model_name="grok-3-mini")
        assert out["content"] == "Ja, die Frist ist gewahrt."
        assert out["reasoning"].startswith("Die Frist beträgt einen Monat")

    def test_grok_structured_reasoning(self, fake_http):
        body = _fixture("xai_grok_3_mini")
        body["choices"][0]["message"]["content"] = '{"answer": "ja"}'
        fake_http(body)
        out = GrokService(api_key="xai-test").generate_structured(
            prompt="p",
            system_prompt="s",
            json_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            model_name="grok-3-mini",
        )
        assert json.loads(out["content"]) == {"answer": "ja"}
        assert out["reasoning"].startswith("Die Frist beträgt einen Monat")


# ---------------------------------------------------------------------------
# OpenAI (chat completions + Responses API)
# ---------------------------------------------------------------------------
class TestOpenAIReasoning:
    def _svc(self):
        svc = OpenAIService(api_key="sk-openai-test-key")
        svc.client = MagicMock()
        return svc

    def test_chat_completion_without_reasoning_is_none(self):
        from openai.types.chat import ChatCompletion

        svc = self._svc()
        svc.client.chat.completions.create.return_value = ChatCompletion.model_validate(
            _fixture("openai_chat_plain")
        )
        out = svc.generate(prompt="p", model_name="gpt-4.1")
        assert out["content"] == "Die Berufung ist unzulässig."
        assert out["reasoning"] is None

    def test_chat_completion_reasoning_content_from_sdk_extra(self):
        """An OpenAI-compatible server behind this client: the SDK keeps the
        non-standard reasoning_content in model_extra."""
        from openai.types.chat import ChatCompletion

        svc = self._svc()
        svc.client.chat.completions.create.return_value = ChatCompletion.model_validate(
            _fixture("vllm_reasoning_content")
        )
        out = svc.generate(prompt="p", model_name="gpt-4.1")
        assert out["content"] == "Der Anspruch besteht."
        assert out["reasoning"].startswith("Zuerst prüfe ich")

    def test_responses_api_reasoning_summary(self):
        from openai.types.responses import Response

        svc = self._svc()
        svc.client.responses.create.return_value = Response.model_validate(
            _fixture("openai_responses_reasoning_summary")
        )
        out = svc.generate(prompt="p", model_name="gpt-5.5-pro", max_tokens=4000)
        assert out["metadata"]["api_endpoint"] == "responses"
        assert out["content"] == "Die Frist ist abgelaufen."
        assert out["reasoning"] == "Ich vergleiche die Fristen nach ZPO."
        # BenGER does not ask for a summary (see the PR follow-up): the
        # request must not carry reasoning.summary.
        sent = svc.client.responses.create.call_args.kwargs
        assert "summary" not in (sent.get("reasoning") or {})


# ---------------------------------------------------------------------------
# Anthropic thinking blocks
# ---------------------------------------------------------------------------
class TestAnthropicReasoning:
    def _svc(self, fixture_name):
        from anthropic.types import Message

        svc = AnthropicService(api_key="sk-ant-test-key")
        svc.client = MagicMock()
        svc.client.messages.create.return_value = Message.model_validate(_fixture(fixture_name))
        return svc

    def test_thinking_blocks_joined_redacted_skipped_answer_unchanged(self):
        out = self._svc("anthropic_thinking").generate(
            prompt="p", model_name="claude-sonnet-4-5-20250929"
        )
        assert out["content"] == "Die Klage hat Erfolg."
        assert out["reasoning"] == (
            "Ich prüfe zuerst die Zulässigkeit der Klage.\n\n"
            "Dann die Begründetheit nach § 823 Abs. 1 BGB."
        )
        # The encrypted redacted_thinking payload is never stored.
        assert "EmwKAhgB" not in out["reasoning"]

    def test_no_thinking_is_none(self):
        out = self._svc("anthropic_plain").generate(prompt="p", model_name="claude-haiku-4-5-20251001")
        assert out["content"] == "Die Klage hat Erfolg."
        assert out["reasoning"] is None

    def test_structured_path_carries_thinking(self):
        out = self._svc("anthropic_thinking").generate_structured(
            prompt="p",
            system_prompt="s",
            json_schema={"type": "object"},
            model_name="claude-sonnet-4-5-20250929",
        )
        assert out["content"] == "Die Klage hat Erfolg."
        assert out["reasoning"].startswith("Ich prüfe zuerst")


# ---------------------------------------------------------------------------
# Google thought parts
# ---------------------------------------------------------------------------
class TestGoogleReasoning:
    def _svc(self):
        from google.genai import types as gtypes

        svc = GoogleService(api_key="test-google-key")
        svc.client = MagicMock()
        svc.client.models.generate_content.return_value = (
            gtypes.GenerateContentResponse.model_validate(_fixture("google_thought_parts"))
        )
        return svc

    def test_thought_parts_are_reasoning_not_answer(self):
        svc = self._svc()
        out = svc.generate(prompt="p", model_name="gemini-2.5-flash", thinking_budget=1024)
        assert out["content"] == "Der Schadensersatzanspruch besteht."
        assert out["reasoning"] == (
            "**Prüfung der Anspruchsgrundlage**\nIch beginne mit § 280 Abs. 1 BGB."
        )
        config = svc.client.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config.include_thoughts is True
        assert config.thinking_config.thinking_budget == 1024

    def test_zero_budget_does_not_request_thoughts(self):
        svc = self._svc()
        svc.generate(prompt="p", model_name="gemini-2.5-flash", thinking_budget=0)
        config = svc.client.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config.thinking_budget == 0
        assert not config.thinking_config.include_thoughts

    def test_structured_path_reads_thoughts_beside_text(self):
        svc = self._svc()
        out = svc.generate_structured(
            prompt="p",
            system_prompt="s",
            json_schema={"type": "object"},
            model_name="gemini-2.5-flash",
        )
        # response.text skips the thought part, so the answer is unchanged.
        assert out["content"] == "Der Schadensersatzanspruch besteht."
        assert out["reasoning"].startswith("**Prüfung der Anspruchsgrundlage**")


# ---------------------------------------------------------------------------
# Mistral Magistral thinking chunks, Cohere thinking blocks
# ---------------------------------------------------------------------------
class TestMistralAndCohereReasoning:
    def test_magistral_list_content_split(self):
        """Magistral returns list content; before this capture the service
        called .strip() on the list and every such call failed."""
        from mistralai.client import models as mmodels

        svc = MistralService(api_key="dummy-key")
        svc.client = MagicMock()
        svc.client.chat.complete.return_value = mmodels.ChatCompletionResponse.model_validate(
            _fixture("mistral_magistral_thinking")
        )
        out = svc.generate(prompt="p", model_name="magistral-medium-latest")
        assert out["success"] is True
        assert out["content"] == "Ein Kaufvertrag ist zustande gekommen."
        assert out["reasoning"] == "Zunächst ist zu klären, ob ein Vertrag zustande kam."

    def test_mistral_string_content_has_no_reasoning(self):
        from mistralai.client import models as mmodels

        body = _fixture("mistral_magistral_thinking")
        body["choices"][0]["message"]["content"] = "  Nur die Antwort.  "
        svc = MistralService(api_key="dummy-key")
        svc.client = MagicMock()
        svc.client.chat.complete.return_value = mmodels.ChatCompletionResponse.model_validate(body)
        out = svc.generate(prompt="p", model_name="mistral-large-4")
        assert out["content"] == "Nur die Antwort."
        assert out["reasoning"] is None

    def test_cohere_thinking_block(self):
        from cohere.v2.types import V2ChatResponse

        svc = CohereService(api_key="dummy-key")
        svc.client = MagicMock()
        svc.client.chat.return_value = V2ChatResponse.model_validate(
            _fixture("cohere_command_a_reasoning")
        )
        out = svc.generate(prompt="p", model_name="command-a-reasoning-08-2025")
        assert out["content"] == "Der Anspruch ist verjährt."
        assert out["reasoning"] == (
            "Der Nutzer fragt nach der Verjährung; Regelfrist drei Jahre, § 195 BGB."
        )


# ---------------------------------------------------------------------------
# Extractor edge cases and the error path
# ---------------------------------------------------------------------------
class TestReasoningHelpers:
    def test_both_fields_prefer_reasoning_content(self):
        msg = {"reasoning_content": "A", "reasoning": "A"}
        assert reasoning_mod.chat_message_reasoning(msg) == "A"

    def test_non_string_reasoning_ignored(self):
        msg = {"reasoning": [{"type": "reasoning.text", "text": "x"}]}
        assert reasoning_mod.chat_message_reasoning(msg) is None

    def test_whitespace_only_is_none_and_nul_dropped(self):
        assert reasoning_mod.join_reasoning(["   ", None]) is None
        assert reasoning_mod.join_reasoning(["a\x00b"]) == "ab"

    def test_responses_api_raw_reasoning_text(self):
        items = [
            {
                "type": "reasoning",
                "summary": [],
                "content": [{"type": "reasoning_text", "text": "raw trace"}],
            },
            {"type": "message", "content": [{"type": "output_text", "text": "x"}]},
        ]
        assert reasoning_mod.responses_api_reasoning(items) == "raw trace"

    def test_error_response_has_null_reasoning(self):
        svc = AnthropicService(api_key="sk-ant-test-key")
        svc.client = MagicMock()
        svc.client.messages.create.side_effect = RuntimeError("boom")
        out = svc.generate(prompt="p", model_name="claude-haiku-4-5-20251001")
        assert out["success"] is False
        assert "reasoning" in out and out["reasoning"] is None
