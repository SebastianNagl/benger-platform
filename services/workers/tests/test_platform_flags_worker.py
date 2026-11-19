"""Worker-side behaviour of the platform flag ``variant_experiments``
(core 2.69): with it off, generation and export run as before the
experiment features; with it on, they run the new way. The jobs open a
``feature_flags.scope`` with the answer for their owner, so these tests set
the scope directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from feature_flags.registry import VARIANT_EXPERIMENTS
from feature_flags.scope import flag_scope, scoped_flag

MULTI = (
    '<View><Text name="text" value="$text"/>'
    '<Choices name="tags" toName="text" choice="multiple">'
    '<Choice value="a"/><Choice value="b"/></Choices>'
    '<Choices name="ok" toName="text"><Choice value="true"/><Choice value="false"/></Choices>'
    "</View>"
)


# --------------------------------------------------------------------------- #
# scope
# --------------------------------------------------------------------------- #


def test_scope_answers_and_nests():
    with flag_scope({VARIANT_EXPERIMENTS: True}):
        assert scoped_flag(VARIANT_EXPERIMENTS) is True
        with flag_scope({VARIANT_EXPERIMENTS: False}):
            assert scoped_flag(VARIANT_EXPERIMENTS) is False
        assert scoped_flag(VARIANT_EXPERIMENTS) is True


def test_outside_a_scope_the_flag_is_off_by_default():
    assert scoped_flag(VARIANT_EXPERIMENTS) is False


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
def test_outside_a_scope_the_context_decides():
    assert scoped_flag(VARIANT_EXPERIMENTS) is True


# --------------------------------------------------------------------------- #
# answer schema and parsing
# --------------------------------------------------------------------------- #


def test_multi_choice_schema_is_a_single_value_while_off():
    from ai_services.schema_generator import generate_json_schema_from_label_config

    off = generate_json_schema_from_label_config(MULTI, variant_experiments=False)
    on = generate_json_schema_from_label_config(MULTI, variant_experiments=True)
    assert off["properties"]["tags"] == {"type": "string", "enum": ["a", "b"]}
    assert on["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string", "enum": ["a", "b"]},
    }
    # A single-value Choices is the same either way.
    assert off["properties"]["ok"] == on["properties"]["ok"]


def test_format_instructions_follow_the_flag():
    from ai_services.schema_generator import generate_format_instructions

    off = generate_format_instructions(MULTI, variant_experiments=False)
    on = generate_format_instructions(MULTI, variant_experiments=True)
    assert "one of: a, b" in off and "list of one or more of" not in off
    assert "list of one or more of: a, b" in on


def _parser(on: bool):
    from response_parser import ResponseParser

    return ResponseParser({}, MULTI, variant_experiments=on)


def test_parser_reads_answers_as_before_while_off():
    # A list for a multi-choice field was a validation error before.
    assert _parser(False).parse('{"tags": ["a", "b"], "ok": "true"}').status == "validation_error"
    assert _parser(True).parse('{"tags": ["a", "b"], "ok": "true"}').status == "success"
    # A JSON boolean is no choice value while off.
    assert _parser(False).parse('{"tags": "a", "ok": true}').status == "validation_error"
    assert _parser(True).parse('{"tags": "a", "ok": true}').status == "success"
    # JSON after prose is not looked for while off: the JSON decode fails
    # and only the old pattern fallback runs.
    prose = 'Here is my answer.\n{"tags": "a", "ok": "false"}'
    on = _parser(True).parse(prose)
    assert on.status == "success"
    assert {r["from_name"] for r in on.parsed_annotation} == {"tags", "ok"}
    off = _parser(False).parse(prose)
    assert (off.status, off.parsed_annotation) != (on.status, on.parsed_annotation)


def test_parser_reads_the_same_single_values_either_way():
    answer = '{"tags": "b", "ok": "false"}'
    off, on = _parser(False).parse(answer), _parser(True).parse(answer)
    assert off.status == on.status == "success"
    assert off.parsed_annotation == on.parsed_annotation


# --------------------------------------------------------------------------- #
# export rows
# --------------------------------------------------------------------------- #


def _generation():
    from datetime import datetime, timezone

    return SimpleNamespace(
        id="g1", model_id="m", response_content="x", reasoning=None, case_data="{}",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), response_metadata={},
        generation_id="rg1", task_id="t1", usage_stats={}, status="completed",
        error_message=None, parse_status="success", parse_error=None,
        parsed_annotation=[], parse_metadata={}, label_config_version="v1",
        label_config_snapshot="<View/>", run_index=0, seed=None, finish_reason="stop",
        truncated=False, refusal=False, error_type=None, latency_ms=10,
        input_tokens=1, output_tokens=2, request_record={"v": 1},
        request_sha256="a" * 64, first_response_content=None, retried=False,
    )


def test_data_export_rows_have_the_previous_fields_while_off():
    from serializers import serialize_generation

    with flag_scope({VARIANT_EXPERIMENTS: False}):
        row = serialize_generation(_generation(), mode="data", evaluations=[], structure_key="s")
        full = serialize_generation(_generation(), mode="full")
    assert list(row) == [
        "id", "model_id", "response_content", "reasoning", "case_data",
        "created_at", "response_metadata", "evaluations",
    ]
    assert "request_record" not in full and "structure_key" not in full
    assert full["run_index"] == 0 and full["seed"] is None


def test_export_rows_are_lossless_with_the_flag():
    from serializers import serialize_generation

    with flag_scope({VARIANT_EXPERIMENTS: True}):
        row = serialize_generation(_generation(), mode="data", evaluations=[], structure_key="s")
    assert row["structure_key"] == "s" and row["request_record"] == {"v": 1}
    assert row["run_index"] == 0 and "parse_status" in row


# --------------------------------------------------------------------------- #
# request capture, provider calls, catalog knobs
# --------------------------------------------------------------------------- #


def test_importing_request_capture_does_not_patch_httpx():
    shared = os.path.join(os.path.dirname(__file__), "..", "..", "shared")
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import httpx\n"
        "import ai_services.request_capture as rc\n"
        "print(getattr(httpx.Client.send, '_benger_request_capture', False))\n"
        "with rc.capture_requests():\n"
        "    pass\n"
        "print(getattr(httpx.Client.send, '_benger_request_capture', False))\n"
    ) % os.path.abspath(shared)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "True"]


class _Service:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        from ai_services.request_capture import record_request

        self.calls.append(scoped_flag(VARIANT_EXPERIMENTS))
        record_request("Fake", "chat", {"model": kwargs.get("model_name")})
        return {"response_text": "ok"}


def test_provider_call_captures_nothing_while_off():
    from generation.llm_generation_service import _call_provider

    service = _Service()
    _, captured_off = _call_provider(service, False, {"model_name": "m"}, False)
    _, captured_on = _call_provider(service, False, {"model_name": "m"}, True)
    assert captured_off == [] and len(captured_on) == 1
    # The provider sees the job's answer through the scope.
    assert service.calls == [False, True]


def test_flagged_reasoning_knob_counts_only_with_the_flag(monkeypatch):
    from ai_services import provider_capabilities as pc

    monkeypatch.setattr(
        pc,
        "_REASONING_CONFIG_CACHE",
        {
            "flagged": {"parameter": "enable_thinking", "default": "on", "feature_flag": VARIANT_EXPERIMENTS},
            "plain": {"parameter": "reasoning_effort", "values": ["low"], "default": "low"},
        },
    )
    with flag_scope({VARIANT_EXPERIMENTS: False}):
        assert pc.model_reasoning_config("flagged") is None
        assert pc.model_reasoning_config("plain")["parameter"] == "reasoning_effort"
    with flag_scope({VARIANT_EXPERIMENTS: True}):
        assert pc.model_reasoning_config("flagged")["parameter"] == "enable_thinking"


def test_deepinfra_records_no_system_key_fields_while_off():
    from ai_services.deepinfra_service import _system_key_fields

    with flag_scope({VARIANT_EXPERIMENTS: False}):
        assert _system_key_fields({"enable_thinking": "on"}, "m", "m") == {}
    with flag_scope({VARIANT_EXPERIMENTS: True}):
        assert _system_key_fields({}, "m", "r") == {
            "reasoning_params_sent": {},
            "provider_model_id": "m",
            "response_model": "r",
        }


def test_catalog_marks_hide_models_and_knobs():
    from catalog_flags import model_offered, served_default_config

    off = lambda name: False  # noqa: E731
    on = lambda name: True  # noqa: E731
    panel = {"feature_flag": VARIANT_EXPERIMENTS}
    knob = {"reasoning_config": {"parameter": "enable_thinking", "feature_flag": VARIANT_EXPERIMENTS}}
    assert not model_offered(panel, off) and model_offered(panel, on)
    assert model_offered({}, off) and model_offered(None, off)
    assert "reasoning_config" not in served_default_config(knob, off)
    assert served_default_config(knob, on) == knob
    plain = {"reasoning_config": {"parameter": "reasoning_effort"}}
    assert served_default_config(plain, off) == plain


def test_flagged_metrics_are_dropped_while_off():
    from metric_filters import without_flagged_metrics

    configs = [{"metric": "bleu"}, {"metric": "text_pattern"}]
    assert without_flagged_metrics(configs, lambda name: False) == [{"metric": "bleu"}]
    assert without_flagged_metrics(configs, lambda name: True) == configs


def test_failing_flag_read_answers_the_default():
    from feature_flags.worker import flag_enabled_or_default

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no database")

    assert flag_enabled_or_default(Broken(), "u1", VARIANT_EXPERIMENTS) is False
