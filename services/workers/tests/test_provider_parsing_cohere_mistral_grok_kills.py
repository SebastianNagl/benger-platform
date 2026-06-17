"""Mutation-grade pins for GENERATION-side response parsing in three
provider clients: Cohere, Mistral, and Grok (xAI).

WHY THIS FILE EXISTS
--------------------
Each provider's ``generate()`` turns a raw provider-API response into the
stored Generation row: the answer ``content``, the ``usage`` token counts,
and the academic-rigor ``metadata`` (``finish_reason`` + derived
``truncated`` / ``refusal``). On a research-grade benchmarking platform a
mis-parsed response is the most dangerous class of bug: a **truncated**,
**refused**, or **empty** model answer that gets silently scored as a valid
benchmark INPUT corrupts the leaderboard with no error ever surfacing.

Before this file there was no dedicated parsing test for any of the three
(``test_coherence_german.py`` is an unrelated NLP-metric test that merely
shares the word "coherence"). The base-service helpers ``derive_truncated``
/ ``classify_error_type`` are covered by ``test_ai_service_metadata.py``;
here we cover the *per-provider extraction* that feeds those helpers — the
exact attribute paths the code reads and how each provider's distinct
finish-reason vocabulary and usage shape get mapped.

APPROACH
--------
We never touch a real API. Each service is constructed with a dummy api-key
string (enough for ``__init__`` / ``_initialize_client`` to set up state),
then its client attribute is *replaced* with a duck-typed fake that returns
exactly the attributes the parsing code reads:

  * Cohere   -> ``self.client.chat(**params)`` returns an object with
                ``.message.content`` (list of blocks each with ``.text``),
                ``.usage.tokens.input_tokens`` / ``.output_tokens``, and
                ``.finish_reason``.
  * Mistral  -> ``self.client.chat.complete(**params)`` returns an object
                with ``.choices[0].message.content`` (str),
                ``.usage.prompt_tokens`` / ``.completion_tokens`` /
                ``.total_tokens``, and ``.choices[0].finish_reason``.
  * Grok     -> OpenAI-compatible HTTP JSON; the async path calls
                ``aiohttp.ClientSession().post(...)`` and reads
                ``result["choices"][0]["message"]["content"]``,
                ``result["usage"][...]``, and
                ``result["choices"][0]["finish_reason"]``. We patch the
                aiohttp session so no socket is opened.

PARSING / TRUNCATION RULES PINNED (read straight from the source):

  Provider | content path                              | token path                          | normal stop | TRUNCATED reason         | refusal
  ---------|-------------------------------------------|-------------------------------------|-------------|--------------------------|--------
  Cohere   | join .message.content[*].text, .strip()   | usage.tokens.input/output_tokens    | "COMPLETE"  | "MAX_TOKENS"             | always False
  Mistral  | choices[0].message.content.strip()        | usage.prompt/completion/total_tokens| "stop"      | "length"                | always False
  Grok     | choices[0]["message"]["content"].strip()  | usage["prompt/completion/total"]    | "stop"      | "length"                | always False

  truncated is computed by ``derive_truncated(finish_reason)`` whose set is
  {"length", "max_tokens", "MAX_TOKENS"}. Cohere additionally ORs in an
  explicit ``finish_reason == "MAX_TOKENS"`` (redundant with the set today,
  but pinned so a future edit to either side can't silently drop Cohere
  truncation detection). None of the three populates ``refusal`` — that is
  documented and pinned as a known limitation, not a bug.
"""

from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

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
# Make absolutely sure the E2E short-circuit branch is NOT taken — we want
# the REAL parsing path, not the canned E2E mock dict.
os.environ.pop("E2E_TEST_MODE", None)

from ai_services.cohere_service import CohereService  # noqa: E402
from ai_services.mistral_service import MistralService  # noqa: E402
from ai_services.grok_service import GrokService  # noqa: E402


# --------------------------------------------------------------------------
# Fake-response builders — duck-typed to match EXACTLY the attributes each
# provider's generate() reads. Anything the code doesn't touch is omitted.
# --------------------------------------------------------------------------
def _cohere_response(blocks, *, finish_reason, input_tokens=None, output_tokens=None,
                     with_usage=True, with_tokens=True):
    """Build a fake Cohere v2 chat response.

    ``blocks`` is a list of strings; each becomes a content block exposing
    ``.text`` (the attribute the code reads). Pass ``with_usage=False`` to
    simulate a response with no usage attribute at all; ``with_tokens=False``
    to simulate a usage object lacking the nested ``.tokens``.
    """
    content_blocks = [types.SimpleNamespace(text=t) for t in blocks]
    message = types.SimpleNamespace(content=content_blocks)

    resp = types.SimpleNamespace()
    resp.message = message
    resp.finish_reason = finish_reason

    if with_usage:
        if with_tokens:
            tokens = types.SimpleNamespace(
                input_tokens=input_tokens, output_tokens=output_tokens
            )
            resp.usage = types.SimpleNamespace(tokens=tokens)
        else:
            # usage present but no .tokens -> code must fall back to 0/0.
            resp.usage = types.SimpleNamespace()
    # with_usage=False -> no `usage` attribute at all; code uses hasattr.
    return resp


def _make_cohere(client_chat_return):
    svc = CohereService(api_key="dummy-key")
    svc.client = MagicMock()
    svc.client.chat = MagicMock(return_value=client_chat_return)
    return svc


def _mistral_response(content, *, finish_reason, prompt_tokens=None,
                      completion_tokens=None, total_tokens=None,
                      with_usage=True, no_choices=False):
    """Build a fake Mistral chat.complete response.

    Content lives at ``choices[0].message.content`` (a plain str).
    ``no_choices=True`` makes ``.choices`` falsy to exercise the empty-string
    fallback path. ``with_usage=False`` drops the ``usage`` attribute.
    """
    resp = types.SimpleNamespace()
    if no_choices:
        resp.choices = []
    else:
        message = types.SimpleNamespace(content=content)
        choice = types.SimpleNamespace(message=message, finish_reason=finish_reason)
        resp.choices = [choice]

    if with_usage:
        resp.usage = types.SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    # with_usage=False -> no `usage` attribute; code uses hasattr -> None -> 0.
    return resp


def _make_mistral(complete_return):
    svc = MistralService(api_key="dummy-key")
    svc.client = MagicMock()
    # mistral path is self.client.chat.complete(**params)
    svc.client.chat = MagicMock()
    svc.client.chat.complete = MagicMock(return_value=complete_return)
    return svc


def _grok_json(content, *, finish_reason, prompt_tokens=None,
               completion_tokens=None, total_tokens=None,
               with_usage=True, no_choices=False):
    """Build the OpenAI-compatible JSON dict the Grok async path decodes."""
    result: dict = {}
    if no_choices:
        result["choices"] = []
    else:
        choice = {"message": {"content": content}}
        if finish_reason is not None:
            choice["finish_reason"] = finish_reason
        result["choices"] = [choice]

    if with_usage:
        usage: dict = {}
        if prompt_tokens is not None:
            usage["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            usage["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            usage["total_tokens"] = total_tokens
        result["usage"] = usage
    # with_usage=False -> no "usage" key; code uses result.get("usage", {}).
    return result


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
    # _initialize_client sets self.client = True when api_key present; keep it.
    assert svc.is_available()
    return svc


def _run_grok_generate(svc, grok_json, **gen_kwargs):
    """Call Grok generate() with the HTTP layer patched to return grok_json."""
    with patch(
        "ai_services.grok_service.aiohttp.ClientSession",
        return_value=_FakeAiohttpSession(grok_json),
    ):
        return svc.generate(prompt="p", system_prompt="s", **gen_kwargs)


# ==========================================================================
# COHERE
# ==========================================================================
class TestCohereParsing:
    """Cohere v2: content = concatenated .message.content[*].text (.strip());
    tokens = usage.tokens.input_tokens/output_tokens; truncation reason is
    "MAX_TOKENS"; refusal always False."""

    def test_normal_response_extracted_exactly(self):
        """A clean COMPLETE response: content joined from blocks and stripped,
        tokens read from usage.tokens, finish_reason passed through,
        truncated=False, refusal=False."""
        resp = _cohere_response(
            ["Die Klage ", "ist begründet."],
            finish_reason="COMPLETE",
            input_tokens=120,
            output_tokens=37,
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p", model_name="command-r-plus-08-2024")

        assert out["success"] is True
        # Blocks concatenated, then .strip() (no leading/trailing ws here).
        assert out["content"] == "Die Klage ist begründet."
        assert out["usage"]["prompt_tokens"] == 120
        assert out["usage"]["completion_tokens"] == 37
        assert out["usage"]["total_tokens"] == 157
        assert out["metadata"]["finish_reason"] == "COMPLETE"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False
        assert out["metadata"]["error_type"] is None

    def test_content_is_stripped(self):
        """Leading/trailing whitespace across blocks is stripped exactly once
        on the joined string (not per block) — pins the .strip() placement."""
        resp = _cohere_response(
            ["  \n  Antwort", " mit Rand  \n "],
            finish_reason="COMPLETE",
            input_tokens=1,
            output_tokens=1,
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["content"] == "Antwort mit Rand"

    def test_truncated_max_tokens_flagged(self):
        """LOAD-BEARING: Cohere signals output-token cutoff with
        finish_reason='MAX_TOKENS'. truncated MUST be True so the benchmark
        input is not scored as a complete answer."""
        resp = _cohere_response(
            ["Die Prüfung beginnt mit"],
            finish_reason="MAX_TOKENS",
            input_tokens=50,
            output_tokens=1500,
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p", max_tokens=1500)
        assert out["metadata"]["finish_reason"] == "MAX_TOKENS"
        assert out["metadata"]["truncated"] is True

    def test_normal_stop_not_truncated(self):
        """COMPLETE (Cohere's normal terminator) must NOT be flagged
        truncated — the complement of the MAX_TOKENS case."""
        resp = _cohere_response(
            ["Vollständige Antwort."],
            finish_reason="COMPLETE",
            input_tokens=10,
            output_tokens=20,
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["metadata"]["truncated"] is False

    def test_empty_content_no_crash(self):
        """A response whose only block carries empty text yields '' (after
        strip) without IndexError/AttributeError."""
        resp = _cohere_response(
            [""], finish_reason="COMPLETE", input_tokens=5, output_tokens=0
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["content"] == ""
        assert out["success"] is True

    def test_no_content_blocks_yields_empty(self):
        """Message present but content list empty -> '' (loop body never
        runs); usage still parsed."""
        resp = _cohere_response(
            [], finish_reason="COMPLETE", input_tokens=8, output_tokens=0
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["content"] == ""
        assert out["usage"]["prompt_tokens"] == 8

    def test_missing_usage_tokens_zero(self):
        """No usage attribute at all -> both token counts default to 0,
        total 0. (Researcher sees 0, not a crash.)"""
        resp = _cohere_response(
            ["x"], finish_reason="COMPLETE", with_usage=False
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0
        assert out["usage"]["total_tokens"] == 0

    def test_usage_without_tokens_attr_zero(self):
        """usage object present but lacking nested .tokens -> 0/0 fallback."""
        resp = _cohere_response(
            ["x"], finish_reason="COMPLETE", with_usage=True, with_tokens=False
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0

    def test_tokens_not_swapped(self):
        """Pin the input->prompt / output->completion mapping so a future
        swap (a classic mutation) is caught: distinct values prove direction."""
        resp = _cohere_response(
            ["x"], finish_reason="COMPLETE", input_tokens=11, output_tokens=22
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["prompt_tokens"] == 11
        assert out["usage"]["completion_tokens"] == 22

    def test_refusal_always_false(self):
        """Cohere has no message.refusal field today; the code hardcodes
        refusal=False. Pinned so the documented limitation is explicit."""
        resp = _cohere_response(
            ["x"], finish_reason="COMPLETE", input_tokens=1, output_tokens=1
        )
        svc = _make_cohere(resp)
        out = svc.generate(prompt="p")
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# MISTRAL
# ==========================================================================
class TestMistralParsing:
    """Mistral: content = choices[0].message.content.strip(); tokens from
    usage.prompt/completion/total_tokens; truncation reason "length";
    refusal always False."""

    def test_normal_response_extracted_exactly(self):
        resp = _mistral_response(
            "Der Anspruch besteht.",
            finish_reason="stop",
            prompt_tokens=200,
            completion_tokens=15,
            total_tokens=215,
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p", model_name="mistral-large-latest")
        assert out["success"] is True
        assert out["content"] == "Der Anspruch besteht."
        assert out["usage"]["prompt_tokens"] == 200
        assert out["usage"]["completion_tokens"] == 15
        assert out["usage"]["total_tokens"] == 215
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False

    def test_content_is_stripped(self):
        resp = _mistral_response(
            "  \n  Antwort  \n ",
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["content"] == "Antwort"

    def test_truncated_length_flagged(self):
        """LOAD-BEARING: Mistral signals output-token cutoff with
        finish_reason='length' -> truncated True via derive_truncated."""
        resp = _mistral_response(
            "Die Subsumtion unter",
            finish_reason="length",
            prompt_tokens=50,
            completion_tokens=1500,
            total_tokens=1550,
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p", max_tokens=1500)
        assert out["metadata"]["finish_reason"] == "length"
        assert out["metadata"]["truncated"] is True

    def test_normal_stop_not_truncated(self):
        resp = _mistral_response(
            "Komplett.",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["metadata"]["truncated"] is False

    def test_total_tokens_taken_from_usage_not_recomputed(self):
        """When usage.total_tokens is present the code uses it verbatim — it
        does NOT recompute prompt+completion. Provider-reported total can
        legitimately differ (e.g. counts reasoning tokens), so pin the
        passthrough with a total that is NOT prompt+completion."""
        resp = _mistral_response(
            "x",
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=999,  # deliberately != 150
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["total_tokens"] == 999

    def test_missing_usage_tokens_zero(self):
        """No usage attribute -> prompt/completion 0, total falls back to
        prompt+completion = 0."""
        resp = _mistral_response(
            "x", finish_reason="stop", with_usage=False
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0
        assert out["usage"]["total_tokens"] == 0

    def test_no_choices_empty_content_and_none_finish_reason(self):
        """Empty choices list -> content '' and finish_reason None (so
        truncated False) without IndexError. This is the degenerate-response
        guard the `if response.choices else ...` ternaries provide."""
        resp = _mistral_response(
            "", finish_reason="stop", prompt_tokens=3, completion_tokens=0,
            total_tokens=3, no_choices=True
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["content"] == ""
        assert out["metadata"]["finish_reason"] is None
        assert out["metadata"]["truncated"] is False
        # usage still parsed from the response.
        assert out["usage"]["total_tokens"] == 3

    def test_tokens_not_swapped(self):
        resp = _mistral_response(
            "x", finish_reason="stop", prompt_tokens=11, completion_tokens=22,
            total_tokens=33
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["usage"]["prompt_tokens"] == 11
        assert out["usage"]["completion_tokens"] == 22

    def test_refusal_always_false(self):
        resp = _mistral_response(
            "x", finish_reason="stop", prompt_tokens=1, completion_tokens=1,
            total_tokens=2
        )
        svc = _make_mistral(resp)
        out = svc.generate(prompt="p")
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# GROK (xAI, OpenAI-compatible HTTP JSON)
# ==========================================================================
class TestGrokParsing:
    """Grok: content = choices[0]['message']['content'].strip(); tokens from
    usage dict with .get defaults; truncation reason "length"; refusal always
    False. Parsing happens on a decoded JSON dict (not SDK objects)."""

    def test_normal_response_extracted_exactly(self):
        payload = _grok_json(
            "Die Berufung hat Erfolg.",
            finish_reason="stop",
            prompt_tokens=300,
            completion_tokens=25,
            total_tokens=325,
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload, model_name="grok-3")
        assert out["success"] is True
        assert out["content"] == "Die Berufung hat Erfolg."
        assert out["usage"]["prompt_tokens"] == 300
        assert out["usage"]["completion_tokens"] == 25
        assert out["usage"]["total_tokens"] == 325
        assert out["metadata"]["finish_reason"] == "stop"
        assert out["metadata"]["truncated"] is False
        assert out["metadata"]["refusal"] is False

    def test_content_is_stripped(self):
        payload = _grok_json(
            "  \n  Antwort  \n ",
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["content"] == "Antwort"

    def test_truncated_length_flagged(self):
        """LOAD-BEARING: Grok (OpenAI-compatible) signals output-token cutoff
        with finish_reason='length' -> truncated True."""
        payload = _grok_json(
            "Im Rahmen der Prüfung",
            finish_reason="length",
            prompt_tokens=50,
            completion_tokens=1500,
            total_tokens=1550,
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload, max_tokens=1500)
        assert out["metadata"]["finish_reason"] == "length"
        assert out["metadata"]["truncated"] is True

    def test_normal_stop_not_truncated(self):
        payload = _grok_json(
            "Fertig.",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["metadata"]["truncated"] is False

    def test_total_tokens_default_from_sum_when_missing(self):
        """usage dict present but no total_tokens key -> code falls back to
        prompt+completion via usage.get('total_tokens', prompt+completion)."""
        payload = _grok_json(
            "x",
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=None,  # omitted from dict
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["usage"]["total_tokens"] == 150

    def test_missing_usage_tokens_zero(self):
        """No usage key -> all token counts 0 (get defaults)."""
        payload = _grok_json(
            "x", finish_reason="stop", with_usage=False
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["usage"]["prompt_tokens"] == 0
        assert out["usage"]["completion_tokens"] == 0
        assert out["usage"]["total_tokens"] == 0

    def test_no_choices_empty_content_and_none_finish_reason(self):
        """Empty choices array -> content '' and finish_reason None without
        KeyError/IndexError (the `if result.get('choices') ...` guards)."""
        payload = _grok_json(
            "", finish_reason="stop", prompt_tokens=3, completion_tokens=0,
            total_tokens=3, no_choices=True
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["content"] == ""
        assert out["metadata"]["finish_reason"] is None
        assert out["metadata"]["truncated"] is False
        assert out["usage"]["total_tokens"] == 3

    def test_missing_finish_reason_key_is_none(self):
        """choices present but finish_reason key absent -> .get returns None
        -> truncated False (not a crash, not a false-positive)."""
        payload = _grok_json(
            "x", finish_reason=None, prompt_tokens=1, completion_tokens=1,
            total_tokens=2
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["metadata"]["finish_reason"] is None
        assert out["metadata"]["truncated"] is False

    def test_tokens_not_swapped(self):
        payload = _grok_json(
            "x", finish_reason="stop", prompt_tokens=11, completion_tokens=22,
            total_tokens=33
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["usage"]["prompt_tokens"] == 11
        assert out["usage"]["completion_tokens"] == 22

    def test_refusal_always_false(self):
        payload = _grok_json(
            "x", finish_reason="stop", prompt_tokens=1, completion_tokens=1,
            total_tokens=2
        )
        svc = _make_grok()
        out = _run_grok_generate(svc, payload)
        assert out["metadata"]["refusal"] is False


# ==========================================================================
# CROSS-PROVIDER consistency: the truncated flag must agree across the three
# distinct finish-reason vocabularies for the SAME semantic event (the model
# hit the output-token ceiling). This is the property a researcher relies on
# when comparing truncation rates between providers on the leaderboard.
# ==========================================================================
class TestCrossProviderTruncationParity:
    def test_all_three_flag_token_limit_truncation(self):
        cohere = _make_cohere(
            _cohere_response(["x"], finish_reason="MAX_TOKENS",
                             input_tokens=1, output_tokens=1)
        )
        mistral = _make_mistral(
            _mistral_response("x", finish_reason="length", prompt_tokens=1,
                              completion_tokens=1, total_tokens=2)
        )
        grok = _make_grok()

        c_out = cohere.generate(prompt="p")
        m_out = mistral.generate(prompt="p")
        g_out = _run_grok_generate(
            grok,
            _grok_json("x", finish_reason="length", prompt_tokens=1,
                       completion_tokens=1, total_tokens=2),
        )
        assert c_out["metadata"]["truncated"] is True
        assert m_out["metadata"]["truncated"] is True
        assert g_out["metadata"]["truncated"] is True

    def test_all_three_clear_flag_on_normal_stop(self):
        cohere = _make_cohere(
            _cohere_response(["x"], finish_reason="COMPLETE",
                             input_tokens=1, output_tokens=1)
        )
        mistral = _make_mistral(
            _mistral_response("x", finish_reason="stop", prompt_tokens=1,
                              completion_tokens=1, total_tokens=2)
        )
        grok = _make_grok()

        c_out = cohere.generate(prompt="p")
        m_out = mistral.generate(prompt="p")
        g_out = _run_grok_generate(
            grok,
            _grok_json("x", finish_reason="stop", prompt_tokens=1,
                       completion_tokens=1, total_tokens=2),
        )
        assert c_out["metadata"]["truncated"] is False
        assert m_out["metadata"]["truncated"] is False
        assert g_out["metadata"]["truncated"] is False
