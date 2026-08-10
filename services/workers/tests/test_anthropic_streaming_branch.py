"""AnthropicService.generate() streaming branch (large output budgets).

Non-streaming Anthropic requests are bound by a ~10-minute wall and the
SDK refuses big ``max_tokens`` outright — long generations (v3
Bewertungsbogen documents run 20k+ output tokens) hard-fail without
streaming. ``generate()`` therefore streams for ``max_tokens >= 16384``
and accumulates the identical final message, so response parsing is
shared between both paths. These tests pin the branch cut-over and the
streamed-path parsing.
"""

import types
from unittest.mock import MagicMock

from ai_services.anthropic_service import AnthropicService


def _final_message(*, text, input_tokens=100, output_tokens=200, stop_reason="end_turn"):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(text=text)],
        stop_reason=stop_reason,
        usage=types.SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens
        ),
    )


class _FakeStream:
    """Duck-type of ``client.messages.stream(...)``: context manager with a
    ``text_stream`` iterator and ``get_final_message()``."""

    def __init__(self, final):
        self._final = final
        self.text_stream = iter(["chunk1", "chunk2"])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


def _service(final_message):
    svc = AnthropicService(api_key="sk-ant-test-key")
    svc.client = MagicMock()
    svc.client.messages.stream.return_value = _FakeStream(final_message)
    svc.client.messages.create.return_value = final_message
    return svc


def test_large_budget_uses_streaming_path():
    svc = _service(_final_message(text="streamed doc"))
    result = svc.generate(
        prompt="p", system_prompt="s", model_name="claude-sonnet-4-6", max_tokens=32000
    )
    assert svc.client.messages.stream.called
    assert not svc.client.messages.create.called
    assert result["success"] is True
    assert result["content"] == "streamed doc"
    assert result["usage"]["completion_tokens"] == 200


def test_small_budget_stays_non_streaming():
    svc = _service(_final_message(text="direct doc"))
    result = svc.generate(
        prompt="p", system_prompt="s", model_name="claude-sonnet-4-6", max_tokens=8000
    )
    assert svc.client.messages.create.called
    assert not svc.client.messages.stream.called
    assert result["content"] == "direct doc"


def test_streamed_truncation_flag_survives_parsing():
    svc = _service(
        _final_message(text="cut off", output_tokens=32000, stop_reason="max_tokens")
    )
    result = svc.generate(
        prompt="p", system_prompt="s", model_name="claude-sonnet-4-6", max_tokens=32000
    )
    assert result["metadata"]["finish_reason"] == "max_tokens"
    assert result["metadata"]["truncated"] is True
