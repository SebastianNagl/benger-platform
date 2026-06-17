"""Mutation-kill / pinning tests for the GENERATION-side response parsing
in the Anthropic and OpenAI provider clients.

WHY THIS FILE EXISTS
--------------------
``AnthropicService.generate()`` and ``OpenAIService.generate()`` parse the
raw provider SDK response into the *stored generation* — the content that
later gets fed to evaluators/judges and scored. A mis-parse here is the
worst class of bug on a benchmarking platform: a TRUNCATED or REFUSED or
EMPTY response that is silently recorded as a complete, well-formed answer
then gets scored "perfectly" against the gold answer. The benchmark INPUT
is wrong, but nothing downstream can tell. Neither ``generate()`` had a
dedicated test before this file.

These tests mock the SDK client (``self.client``) — no real API call is
ever made — and duck-type fake response objects with exactly the
attributes the parsing code reads, then PIN the dict that
``_create_response_dict`` returns:

    {
      "content": <str>,
      "usage": {"prompt_tokens", "completion_tokens", "total_tokens"},
      "metadata": {"finish_reason", "truncated", "refusal", ...},
      "success": True,
    }

The load-bearing assertion is ``metadata["truncated"]``: a generation that
hit the output-token cap MUST be flagged True (Anthropic stop_reason
"max_tokens", OpenAI finish_reason "length"), else it is scored as if the
model chose to stop.

ENV NOTE: importing ``anthropic_service`` transitively constructs an
``EncryptionService`` whose module-level singleton refuses to start
without an encryption key / test sentinel. The workers ``conftest.py``
already sets ``BENGER_TEST_MODE=1`` (the sentinel), but we belt-and-braces
the documented env vars at the very TOP of this module — BEFORE the import
of the services — so the file is also runnable in isolation.
"""

from __future__ import annotations

import os

# --- MUST run before importing the provider services (see module docstring) ---
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")
# Make sure E2E mock-mode is OFF — otherwise generate() short-circuits to a
# canned mock response and never touches our fake SDK objects.
os.environ.pop("E2E_TEST_MODE", None)

import types  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from ai_services.anthropic_service import AnthropicService  # noqa: E402
from ai_services.openai_service import OpenAIService  # noqa: E402


# ---------------------------------------------------------------------------
# Fake-response builders (duck-typed to exactly what the parsing code reads)
# ---------------------------------------------------------------------------
def _anthropic_response(
    *,
    text="hello world",
    input_tokens=10,
    output_tokens=5,
    stop_reason="end_turn",
    content_blocks=None,
    omit_usage=False,
):
    """Build a fake ``anthropic.Anthropic().messages.create(...)`` return.

    The code reads: ``response.content[0].text`` (guarded by truthiness of
    ``response.content``), ``response.usage.input_tokens`` /
    ``.output_tokens`` (guarded by ``hasattr(response, "usage")``), and
    ``getattr(response, "stop_reason", None)``.
    """
    if content_blocks is None:
        content_blocks = [types.SimpleNamespace(text=text)]
    ns = types.SimpleNamespace(
        content=content_blocks,
        stop_reason=stop_reason,
    )
    if not omit_usage:
        ns.usage = types.SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens
        )
    return ns


def _openai_response(
    *,
    content="hello world",
    prompt_tokens=10,
    completion_tokens=5,
    total_tokens=15,
    finish_reason="stop",
    refusal=None,
):
    """Build a fake ``OpenAI().chat.completions.create(...)`` return.

    The code reads: ``response.choices[0].message.content`` (``.strip()``
    when truthy, else ""), ``getattr(message, "refusal", None)``,
    ``response.usage.prompt_tokens`` / ``.completion_tokens`` /
    ``.total_tokens``, and ``response.choices[0].finish_reason``.
    """
    message = types.SimpleNamespace(content=content, refusal=refusal)
    choice = types.SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = types.SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return types.SimpleNamespace(choices=[choice], usage=usage)


def _make_anthropic(fake_response):
    """Construct AnthropicService with a stubbed SDK client.

    ``__init__`` only needs an api_key string; ``_initialize_client`` then
    builds a real ``anthropic.Anthropic`` which we immediately replace with
    a MagicMock whose ``messages.create`` returns our fake response. The
    non-placeholder api_key makes ``is_available()`` True so generate()
    proceeds to the real parsing path.
    """
    svc = AnthropicService(api_key="sk-ant-test-key")
    svc.client = MagicMock()
    svc.client.messages.create.return_value = fake_response
    return svc


def _make_openai(fake_response):
    """Construct OpenAIService with a stubbed SDK client (see _make_anthropic)."""
    svc = OpenAIService(api_key="sk-openai-test-key")
    svc.client = MagicMock()
    svc.client.chat.completions.create.return_value = fake_response
    return svc


# ===========================================================================
# ANTHROPIC — generate() parsing rules
# ===========================================================================
class TestAnthropicParsing:
    def test_normal_response_extracts_content_tokens_and_flags(self):
        """NORMAL: a clean end_turn response.

        content must be the first block's text verbatim; prompt/completion
        tokens must be input_tokens / output_tokens; total = sum;
        finish_reason mapped through unchanged; truncated False, refusal
        False, success True. This is the baseline every other case deviates
        from.
        """
        svc = _make_anthropic(
            _anthropic_response(
                text="Die Klage ist zulässig.",
                input_tokens=120,
                output_tokens=60,
                stop_reason="end_turn",
            )
        )
        out = svc.generate(prompt="frage", model_name="claude-sonnet-4-20250514")

        assert out["success"] is True
        assert out["content"] == "Die Klage ist zulässig."
        assert out["usage"]["prompt_tokens"] == 120
        assert out["usage"]["completion_tokens"] == 60
        assert out["usage"]["total_tokens"] == 180
        assert out["metadata"]["finish_reason"] == "end_turn"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False

    def test_truncated_max_tokens_is_flagged(self):
        """TRUNCATED (load-bearing): Anthropic stops at the output cap with
        stop_reason='max_tokens'. derive_truncated MUST map this exact token
        the API uses to truncated=True. If this regresses, a cut-off legal
        analysis is stored and scored as a complete answer — the single most
        damaging silent corruption on the platform. refusal stays False
        (a truncation is not a refusal).
        """
        svc = _make_anthropic(
            _anthropic_response(text="Die Klage ist zul", stop_reason="max_tokens")
        )
        out = svc.generate(prompt="frage")

        assert out["metadata"]["finish_reason"] == "max_tokens"
        assert out["metadata"]["truncated"] is True
        assert out["metadata"]["refusal"] is False
        # Content is whatever partial text came back — still extracted.
        assert out["content"] == "Die Klage ist zul"

    def test_normal_stop_reason_is_not_truncated(self):
        """Negative half of the truncation rule: stop_sequence / tool_use /
        end_turn are normal stops and must NOT be flagged truncated. Pins
        that derive_truncated is selective, not 'anything non-end_turn'.
        """
        for reason in ("end_turn", "stop_sequence", "tool_use"):
            svc = _make_anthropic(_anthropic_response(stop_reason=reason))
            out = svc.generate(prompt="frage")
            assert out["metadata"]["truncated"] is False, reason

    def test_refusal_stop_reason_sets_refusal_flag(self):
        """REFUSAL: Claude 3.5+ surfaces a safety refusal via
        stop_reason='refusal'. The code sets refusal = (finish_reason ==
        'refusal'). A refused generation must be marked so it is excluded
        from scoring rather than graded as a (bad) answer. truncated stays
        False because 'refusal' is not a token-limit reason.
        """
        svc = _make_anthropic(
            _anthropic_response(text="", stop_reason="refusal")
        )
        out = svc.generate(prompt="frage")

        assert out["metadata"]["refusal"] is True
        assert out["metadata"]["finish_reason"] == "refusal"
        assert out["metadata"]["truncated"] is False

    def test_empty_content_list_yields_empty_string_no_indexerror(self):
        """EMPTY content: when response.content == [] the guard
        ``response.content[0].text if response.content else ""`` must yield
        "" rather than raising IndexError. An empty list is falsy, so the
        else-branch fires.
        """
        svc = _make_anthropic(
            _anthropic_response(content_blocks=[], stop_reason="end_turn")
        )
        out = svc.generate(prompt="frage")

        assert out["content"] == ""
        assert out["success"] is True  # parsing did not crash

    def test_none_content_yields_empty_string(self):
        """EMPTY content variant: response.content is None (also falsy) →
        else-branch → "" with no AttributeError on None[0].
        """
        svc = _make_anthropic(
            _anthropic_response(content_blocks=None, stop_reason="end_turn")
        )
        # content_blocks=None means the builder default fires; force None:
        svc.client.messages.create.return_value = types.SimpleNamespace(
            content=None,
            usage=types.SimpleNamespace(input_tokens=3, output_tokens=0),
            stop_reason="end_turn",
        )
        out = svc.generate(prompt="frage")

        assert out["content"] == ""
        assert out["success"] is True

    def test_missing_usage_attribute_yields_zero_tokens(self):
        """MISSING usage: a response object without a ``.usage`` attribute
        must not crash — the ``hasattr(response, 'usage')`` guard makes both
        token counts 0 (and total 0). Pins that the guard is honored on both
        input and output extraction.
        """
        svc = _make_anthropic(
            _anthropic_response(stop_reason="end_turn", omit_usage=True)
        )
        out = svc.generate(prompt="frage")

        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0
        assert out["usage"]["total_tokens"] == 0
        assert out["success"] is True

    def test_missing_stop_reason_maps_to_none_and_not_truncated(self):
        """A response with no stop_reason attribute at all →
        getattr(..., None) → finish_reason None → not truncated, not
        refusal. Defensive: some SDK shapes / older snapshots omit it.
        """
        resp = types.SimpleNamespace(
            content=[types.SimpleNamespace(text="x")],
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        svc = _make_anthropic(resp)
        out = svc.generate(prompt="frage")

        assert out["metadata"]["finish_reason"] is None
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False

    def test_multiblock_content_takes_first_block_only(self):
        """Multi-block content: Anthropic can return several content blocks
        (e.g. a thinking block + text). The code extracts ONLY
        content[0].text. This pins the documented behavior so a future
        change that starts joining blocks is a deliberate, test-visible
        decision rather than an accident.
        """
        svc = _make_anthropic(
            _anthropic_response(
                content_blocks=[
                    types.SimpleNamespace(text="FIRST"),
                    types.SimpleNamespace(text="SECOND"),
                ],
                stop_reason="end_turn",
            )
        )
        out = svc.generate(prompt="frage")
        assert out["content"] == "FIRST"


# ===========================================================================
# OPENAI — generate() parsing rules
# ===========================================================================
class TestOpenAIParsing:
    def test_normal_response_extracts_content_tokens_and_flags(self):
        """NORMAL: a clean finish_reason='stop' response.

        content = message.content.strip(); usage taken straight from
        response.usage.{prompt,completion,total}_tokens; finish_reason
        mapped through; truncated False; refusal False; success True.
        """
        svc = _make_openai(
            _openai_response(
                content="Die Klage ist begründet.",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                finish_reason="stop",
            )
        )
        out = svc.generate(prompt="frage", model_name="gpt-4o")

        assert out["success"] is True
        assert out["content"] == "Die Klage ist begründet."
        assert out["usage"]["prompt_tokens"] == 100
        assert out["usage"]["completion_tokens"] == 50
        assert out["usage"]["total_tokens"] == 150
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False

    def test_truncated_length_is_flagged(self):
        """TRUNCATED (load-bearing): OpenAI signals an output-cap stop with
        finish_reason='length'. derive_truncated MUST map this exact token
        to truncated=True. A regression here stores a cut-off answer as
        complete and scores it against the gold answer — silent benchmark
        corruption. refusal stays False.
        """
        svc = _make_openai(
            _openai_response(content="Die Klage ist", finish_reason="length")
        )
        out = svc.generate(prompt="frage")

        assert out["metadata"]["finish_reason"] == "length"
        assert out["metadata"]["truncated"] is True
        assert out["metadata"]["refusal"] is False
        assert out["content"] == "Die Klage ist"

    def test_normal_stop_reason_is_not_truncated(self):
        """Negative half of the truncation rule for OpenAI: 'stop' and
        'tool_calls' are normal terminations, not truncations. Pins that
        derive_truncated only flags the literal 'length' token.
        """
        for reason in ("stop", "tool_calls"):
            svc = _make_openai(_openai_response(finish_reason=reason))
            out = svc.generate(prompt="frage")
            assert out["metadata"]["truncated"] is False, reason

    def test_refusal_message_field_sets_refusal_flag(self):
        """REFUSAL: OpenAI (gpt-4o+) surfaces a safety refusal on
        message.refusal (a non-empty string). The code sets
        refusal = bool(getattr(message, 'refusal', None)). A truthy refusal
        string must flag the generation as refused. finish_reason here is
        still 'stop', so truncated stays False — refusal is an independent
        axis from truncation on OpenAI.
        """
        svc = _make_openai(
            _openai_response(
                content="",
                finish_reason="stop",
                refusal="I can't help with that.",
            )
        )
        out = svc.generate(prompt="frage")

        assert out["metadata"]["refusal"] is True
        assert out["metadata"]["truncated"] is False

    def test_content_filter_finish_reason_is_not_truncated(self):
        """CONTENT FILTER: finish_reason='content_filter' is OpenAI's other
        safety signal. It is NOT in TRUNCATED_FINISH_REASONS, so truncated
        must be False, and because message.refusal is None here, refusal is
        also False. This pins the documented handling: content_filter passes
        through as finish_reason but does not get mislabeled as a truncation.
        A content-filtered (often empty) completion is therefore visible via
        finish_reason for downstream filtering, not hidden as a normal stop.
        """
        svc = _make_openai(
            _openai_response(
                content="", finish_reason="content_filter", refusal=None
            )
        )
        out = svc.generate(prompt="frage")

        assert out["metadata"]["finish_reason"] == "content_filter"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False
        assert out["content"] == ""

    def test_none_content_yields_empty_string_no_crash(self):
        """EMPTY content: message.content is None (common when the model
        emits only a refusal or is content-filtered). The guard
        ``message.content.strip() if message.content else ""`` must NOT call
        .strip() on None — None is falsy so the else-branch yields "".
        """
        svc = _make_openai(
            _openai_response(content=None, finish_reason="stop")
        )
        out = svc.generate(prompt="frage")

        assert out["content"] == ""
        assert out["success"] is True

    def test_whitespace_content_is_stripped(self):
        """WHITESPACE STRIP: the OpenAI path strips surrounding whitespace
        (the Anthropic path does NOT — see test_anthropic_does_not_strip).
        Pins the provider-specific behavior so leading/trailing newlines from
        the model don't leak into the stored generation on the OpenAI side.
        """
        svc = _make_openai(
            _openai_response(content="  \n  antwort mit rand  \n ", finish_reason="stop")
        )
        out = svc.generate(prompt="frage")
        assert out["content"] == "antwort mit rand"

    def test_empty_string_content_stays_empty(self):
        """EMPTY content variant: message.content == "" (falsy) → else-branch
        → "" (no .strip() call needed, and no crash).
        """
        svc = _make_openai(_openai_response(content="", finish_reason="stop"))
        out = svc.generate(prompt="frage")
        assert out["content"] == ""
        assert out["success"] is True


# ===========================================================================
# Cross-provider divergence pin (one place documents the asymmetry)
# ===========================================================================
class TestProviderStripAsymmetry:
    def test_anthropic_does_not_strip_but_openai_does(self):
        """The two parsers handle whitespace DIFFERENTLY and that is
        intentional: OpenAI calls ``.strip()`` on the content; Anthropic
        stores ``content[0].text`` verbatim. This single test makes the
        asymmetry explicit so neither side is 'fixed' to match the other
        without a deliberate, test-visible change. (For a JSON-emitting
        generation, surrounding whitespace is harmless to the parser, but
        the stored bytes differ between providers — relevant to anyone
        diffing raw generations across providers.)
        """
        padded = "  geantwortet  "

        a = _make_anthropic(_anthropic_response(text=padded, stop_reason="end_turn"))
        a_out = a.generate(prompt="frage")
        assert a_out["content"] == padded  # verbatim, NOT stripped

        o = _make_openai(_openai_response(content=padded, finish_reason="stop"))
        o_out = o.generate(prompt="frage")
        assert o_out["content"] == "geantwortet"  # stripped


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
