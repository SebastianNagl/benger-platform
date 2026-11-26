"""Every provider client records the request it sends, as sent.

For the HTTP clients (DeepInfra, xAI, custom OpenAI-compatible endpoints)
and the OpenAI SDK client, a local mock server receives the request: the
recorded body must equal the JSON the server got. For the other SDK clients
the SDK call is replaced by a stand-in that keeps its keyword arguments: the
record must equal them. Each client also continues a conversation
(``continuation``) after the first user prompt, which a format retry needs.
"""

import json
import os

os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest  # noqa: E402

from ai_services.request_capture import (  # noqa: E402
    build_request_record,
    capture_requests,
)
from mock_chat_server import mock_chat_server  # noqa: E402
from system_profile import parameters_sent  # noqa: E402

SYSTEM = (
    'Du bist Schlichterin für Mietsachen. Antworte nur mit JSON:\n{"anteil": <Zahl>}'
)
USER = "Akte S-41/26 \u2013 Müller ./. Öztürk\n\nDie Mieterin minderte die Miete; § 536 BGB."
CONTINUATION = [
    {"role": "assistant", "content": "Die Minderung ist teilweise berechtigt."},
    {"role": "user", "content": "Bitte antworte nur mit dem JSON-Objekt."},
]
EXPECTED_MESSAGES = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": USER},
    *CONTINUATION,
]
SCHEMA = {
    "type": "object",
    "properties": {"anteil": {"type": "number"}},
    "required": ["anteil"],
}


def _call(service, *, structured=False, continuation=None, **kwargs):
    extra = {"continuation": continuation} if continuation else {}
    with capture_requests() as captured:
        if structured:
            result = service.generate_structured(
                prompt=USER, system_prompt=SYSTEM, json_schema=SCHEMA, **kwargs, **extra
            )
        else:
            result = service.generate(
                prompt=USER, system_prompt=SYSTEM, **kwargs, **extra
            )
    return result, captured


# ---------------------------------------------------------------- HTTP clients


def _deepinfra(base_url):
    from ai_services.deepinfra_service import DeepInfraService

    service = DeepInfraService(api_key="test-key")
    service.base_url = base_url
    return service


def _grok(base_url):
    from ai_services.grok_service import GrokService

    service = GrokService(api_key="test-key")
    service.base_url = base_url
    return service


@pytest.mark.parametrize("make, provider", [(_deepinfra, "DeepInfra"), (_grok, "Grok")])
def test_http_clients_record_the_body_the_server_received(make, provider):
    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        server.reply('{"anteil": 40}')
        service = make(server.base_url)
        first, captured_first = _call(
            service, model_name="acme/model", temperature=0.7, max_tokens=600
        )
        retry, captured_retry = _call(
            service,
            model_name="acme/model",
            temperature=0.7,
            max_tokens=600,
            continuation=CONTINUATION,
        )
    assert first["success"] and retry["success"]
    wire_first, wire_retry = server.json_bodies()
    assert [e["body"] for e in captured_first] == [wire_first]
    assert [e["body"] for e in captured_retry] == [wire_retry]
    assert captured_first[0]["provider"] == provider
    assert captured_first[0]["capture"] == "http_body"
    assert parameters_sent(captured_first[0]) == {"temperature": 0.7, "max_tokens": 600}
    assert wire_first["messages"] == EXPECTED_MESSAGES[:2]
    assert wire_retry["messages"] == EXPECTED_MESSAGES
    # The record's neutral view is the same conversation.
    assert build_request_record(captured_retry)["messages"] == EXPECTED_MESSAGES


def test_structured_request_records_the_injected_format_block():
    """DeepInfra has no native structured output: the client adds a schema
    block to the system prompt. The record shows it, as the server got it."""
    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        service = _deepinfra(server.base_url)
        result, captured = _call(service, structured=True, model_name="acme/model")
    assert result["success"]
    [wire] = server.json_bodies()
    assert captured[0]["body"] == wire
    system = wire["messages"][0]["content"]
    assert system.startswith(SYSTEM) and "## Output Format" in system
    assert json.dumps(SCHEMA, indent=2) in system


def test_custom_endpoint_records_the_body_the_server_received(monkeypatch):
    import url_guard
    from ai_services.openai_compatible_service import OpenAICompatibleService

    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        # The mock server is on loopback, which the SSRF guard refuses.
        monkeypatch.setattr(
            url_guard, "resolve_and_validate", lambda url: (url, ["127.0.0.1"])
        )
        service = OpenAICompatibleService(
            base_url=server.base_url, api_key=None, endpoint_model_name="local/model"
        )
        result, captured = _call(
            service, model_name="local/model", continuation=CONTINUATION
        )
    assert result["success"], result.get("error")
    [wire] = server.json_bodies()
    assert captured[0]["body"] == wire
    assert captured[0]["provider"] == "Custom"
    assert wire["messages"] == EXPECTED_MESSAGES


def test_openai_sdk_records_the_body_on_the_wire():
    from openai import OpenAI

    from ai_services.openai_service import OpenAIService

    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        service = OpenAIService(api_key="test-key")
        service.client = OpenAI(
            api_key="test-key", base_url=server.base_url, max_retries=0
        )
        result, captured = _call(
            service,
            model_name="gpt-4o",
            temperature=0.0,
            max_tokens=300,
            continuation=CONTINUATION,
        )
    assert result["success"], result.get("error")
    [wire] = server.json_bodies()
    assert captured[0]["capture"] == "http_body"
    assert captured[0]["body"] == wire
    assert wire["messages"] == EXPECTED_MESSAGES


def test_openai_prompt_json_fallback_sends_the_schema_not_a_placeholder():
    """A model without json_schema support gets the schema in the system
    prompt. The block used to be a plain string, so the model received the
    literal text ``{json.dumps(json_schema, indent=2)}``."""
    from openai import OpenAI

    from ai_services.openai_service import OpenAIService

    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        service = OpenAIService(api_key="test-key")
        service.client = OpenAI(
            api_key="test-key", base_url=server.base_url, max_retries=0
        )
        _call(service, structured=True, model_name="gpt-3.5-turbo", temperature=0.0)
    [wire] = server.json_bodies()
    system = wire["messages"][0]["content"]
    assert "json.dumps" not in system
    assert json.dumps(SCHEMA, indent=2) in system


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra", "gpt-6.2-sol"])
def test_openai_gpt6_judges_get_native_json_schema_output(model):
    """GPT-6 ids were missing from the json_schema prefix list, so a GPT-6
    judge fell back to the schema pasted into the system prompt. They now
    get native structured output, in the GPT-5 request shape."""
    from openai import OpenAI

    from ai_services.openai_service import OpenAIService

    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        service = OpenAIService(api_key="test-key")
        service.client = OpenAI(
            api_key="test-key", base_url=server.base_url, max_retries=0
        )
        result, _ = _call(
            service, structured=True, model_name=model, temperature=0.0, max_tokens=300
        )
    assert result["success"], result.get("error")
    [wire] = server.json_bodies()
    assert wire["response_format"]["type"] == "json_schema"
    assert wire["response_format"]["json_schema"]["schema"] == SCHEMA
    assert wire["messages"][0]["content"] == SYSTEM
    assert wire["temperature"] == 1.0
    assert "top_p" not in wire


# ----------------------------------------------------------------- SDK clients
#
# Each SDK client is pointed at the mock server; the mock answers in the
# OpenAI shape, so the non-OpenAI clients fail to read the answer, after the
# request was sent. The record must be the body the server received,
# including every knob the service filled in, coerced or dropped.


def _sdk_service(name, base_url):
    if name == "anthropic":
        from anthropic import Anthropic

        from ai_services.anthropic_service import AnthropicService

        service = AnthropicService(api_key="test-key")
        service.client = Anthropic(api_key="test-key", base_url=base_url, max_retries=0)
    elif name == "mistral":
        try:
            from mistralai import Mistral
        except ImportError:
            from mistralai.client import Mistral

        from ai_services.mistral_service import MistralService

        service = MistralService(api_key="test-key")
        service.client = Mistral(api_key="test-key", server_url=base_url)
    elif name == "cohere":
        import cohere

        from ai_services.cohere_service import CohereService

        service = CohereService(api_key="test-key")
        service.client = cohere.ClientV2(api_key="test-key", base_url=base_url)
    elif name == "google":
        from google import genai
        from google.genai import types

        from ai_services.google_service import GoogleService

        service = GoogleService(api_key="test-key")
        service.client = genai.Client(
            api_key="test-key", http_options=types.HttpOptions(base_url=base_url)
        )
    else:  # pragma: no cover
        raise ValueError(name)
    return service


SDK_CASES = [
    ("anthropic", "claude-sonnet-4-5", "anthropic.messages"),
    ("mistral", "mistral-small-latest", "mistral.chat"),
    ("cohere", "command-a-03-2025", "cohere.chat"),
    ("google", "gemini-2.5-flash", "google.generate_content"),
]


@pytest.mark.parametrize("name, model, api", SDK_CASES, ids=[c[0] for c in SDK_CASES])
def test_sdk_clients_record_the_body_the_server_received(name, model, api):
    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        service = _sdk_service(name, server.base_url)
        _, captured = _call(
            service,
            model_name=model,
            temperature=0.3,
            max_tokens=300,
            continuation=CONTINUATION,
        )
    assert server.bodies, "the SDK sent nothing"
    wire = json.loads(server.bodies[0])
    assert len(captured) == 1
    entry = captured[0]
    assert (entry["api"], entry["capture"]) == (api, "http_body")
    assert entry["body"] == wire
    assert entry["path"] == server.paths[0].split("?")[0]
    # The provider-neutral view is the conversation that was sent.
    assert build_request_record(captured)["messages"] == EXPECTED_MESSAGES
    sent = parameters_sent(entry)
    assert (sent["temperature"], sent["max_tokens"]) == (0.3, 300)


@pytest.mark.parametrize(
    "name, model, knob, expected",
    [
        (
            "mistral",
            "magistral-medium-latest",
            {"prompt_mode": "reasoning"},
            {"prompt_mode": "reasoning"},
        ),
        (
            "cohere",
            "command-a-reasoning-08-2025",
            {"thinking_token_budget": 2048},
            {"thinking_token_budget": 2048},
        ),
    ],
    ids=["mistral", "cohere"],
)
def test_sdk_reasoning_knobs_enter_the_profile_as_sent(name, model, knob, expected):
    with mock_chat_server() as server:
        server.reply('{"anteil": 30}')
        _, captured = _call(
            _sdk_service(name, server.base_url),
            model_name=model,
            temperature=0.3,
            max_tokens=300,
            **knob,
        )
    assert captured[0]["capture"] == "http_body"
    sent = parameters_sent(captured[0])
    assert {k: sent.get(k) for k in expected} == expected


def test_filled_coerced_and_dropped_knobs_are_recorded_as_sent():
    """What the services change on their own lands in the record: Anthropic
    sends temperature through extra_body (merged into the body) and the
    thinking budget; Gemini 2.5 gets a default thinking budget nobody asked
    for; GPT-5 is forced to temperature 1 and loses top_p, the penalties and
    the seed."""
    from openai import OpenAI

    from ai_services.openai_service import OpenAIService

    with mock_chat_server() as server:
        server.reply("{}")
        server.reply("{}")
        server.reply("{}")
        _, anthropic = _call(
            _sdk_service("anthropic", server.base_url),
            model_name="claude-sonnet-4-5",
            temperature=0.2,
            max_tokens=300,
            thinking_budget=2048,
        )
        _, google = _call(
            _sdk_service("google", server.base_url),
            model_name="gemini-2.5-flash",
            temperature=0.2,
            max_tokens=300,
        )
        openai_service = OpenAIService(api_key="test-key")
        openai_service.client = OpenAI(
            api_key="test-key", base_url=server.base_url, max_retries=0
        )
        _, gpt5 = _call(
            openai_service, model_name="gpt-5", temperature=0.2, max_tokens=300
        )
    wire_anthropic, wire_google, wire_gpt5 = server.json_bodies()

    assert anthropic[0]["body"] == wire_anthropic
    assert wire_anthropic["temperature"] == 0.2 and "extra_body" not in wire_anthropic
    assert wire_anthropic["thinking"] == {"type": "enabled", "budget_tokens": 2048}

    assert google[0]["body"] == wire_google
    assert wire_google["generationConfig"]["thinkingConfig"]["thinking_budget"] == 1024

    assert gpt5[0]["body"] == wire_gpt5
    assert wire_gpt5["temperature"] == 1.0
    assert not {"top_p", "frequency_penalty", "presence_penalty", "seed"} & set(
        wire_gpt5
    )
    assert wire_gpt5["max_completion_tokens"] == 300

    # The system profile is what was sent, not what was configured.
    assert parameters_sent(anthropic[0]) == {
        "temperature": 0.2,
        "max_tokens": 300,
        "thinking_budget": 2048,
    }
    assert parameters_sent(google[0]) == {
        "temperature": 0.2,
        "max_tokens": 300,
        "thinking_budget": 1024,
    }
    assert parameters_sent(gpt5[0]) == {"temperature": 1.0, "max_tokens": 300}


def test_openai_responses_profile_is_read_from_the_wire():
    from openai import OpenAI

    from ai_services.openai_service import OpenAIService

    with mock_chat_server() as server:
        server.reply("{}")
        service = OpenAIService(api_key="test-key")
        service.client = OpenAI(
            api_key="test-key", base_url=server.base_url, max_retries=0
        )
        _, captured = _call(
            service,
            model_name="gpt-5-pro",
            temperature=0.2,
            max_tokens=400,
            reasoning_effort="high",
        )
    [wire] = server.json_bodies()
    assert server.paths[0].endswith("/responses")
    assert captured[0]["api"] == "openai.responses" and captured[0]["body"] == wire
    sent = parameters_sent(captured[0])
    assert sent["max_tokens"] == wire["max_output_tokens"] == 400
    assert sent["reasoning_effort"] == "high"
    assert sent.get("temperature") == wire.get("temperature")


class _KeepKwargs:
    """Stand-in for an SDK method that sends nothing over httpx: keeps the
    call's kwargs, then fails."""

    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("stand-in: no network")


def test_sdk_kwargs_are_kept_when_nothing_reaches_httpx():
    from ai_services.anthropic_service import AnthropicService
    from ai_services.request_capture import _jsonable

    service = AnthropicService(api_key="test-key")
    create = _KeepKwargs()
    service.client = type("C", (), {"messages": type("M", (), {"create": create})()})()
    _, captured = _call(
        service, model_name="claude-x", max_tokens=300, continuation=CONTINUATION
    )
    [kwargs] = create.calls
    assert captured[0]["capture"] == "sdk_kwargs"
    assert captured[0]["body"] == _jsonable(kwargs)
    assert build_request_record(captured)["messages"] == EXPECTED_MESSAGES


def test_google_single_prompt_keeps_the_plain_contents():
    from ai_services.google_service import GoogleService

    service = GoogleService(api_key="test-key")
    keep = _KeepKwargs()
    service.client = type(
        "C", (), {"models": type("M", (), {"generate_content": keep})()}
    )()
    _call(service, model_name="gemini-x")
    assert keep.calls[-1]["contents"] == USER
