"""System key and reasoning profiles of open-weight DeepInfra models.

A system under test is a model plus the parameter profile it was run with:
the same model with thinking on and with thinking off is two systems (a
reasoning arm), while its repeats (seeds, run indexes) stay one system.

Covered here:

* ``system_profile``: profile normalisation, hash and key, checked against
  hand-computed values.
* ``DeepInfraService``: sends exactly the reasoning knob the catalog declares
  for the model (``reasoning_effort`` or ``chat_template_kwargs.
  enable_thinking``), with the run's value or the declared default, and
  reports what it sent and which model id it sent and got back.
* A mock generation run through ``generate_llm_responses`` with the real
  DeepInfra client over a fake HTTP session: each answer records the
  provider ids, the parameter profile and its hash, and the reasoning arm
  gets a system key of its own.
* The catalog entries of the four added models and the thinking switches.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("TESTING", "true")
os.environ.pop("E2E_TEST_MODE", None)

import pytest  # noqa: E402

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import system_profile as sp  # noqa: E402
from ai_services import deepinfra_service as di_mod  # noqa: E402
from ai_services import provider_capabilities as pc  # noqa: E402
from seeds.llm_models_loader import load_catalog  # noqa: E402

GPT_OSS_20B = "openai/gpt-oss-20b"
QWEN_27B = "Qwen/Qwen3.8-27B"
GEMMA_26B = "google/gemma-4-26B-A4B-it"
NEMOTRON = "nvidia/NVIDIA-Nemotron-3.5-Lightning"
LLAMA_8B_TURBO = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
MISTRAL_SMALL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
PHI_4 = "microsoft/phi-4"


def _catalog_by_id():
    return {m["id"]: m for m in load_catalog().models}


# ---------------------------------------------------------------------------
# system_profile
# ---------------------------------------------------------------------------
class TestParameterProfile:
    def test_drops_seed_provenance_and_none(self):
        profile = sp.parameter_profile(
            {
                "temperature": 0.7,
                "max_tokens": 4000,
                "seed": 43,
                "seed_not_sent": {"requested": 43},
                "_param_provenance": {"temperature": {}},
                "thinking_budget": None,
                "reasoning_effort": "low",
            }
        )
        assert profile == {"temperature": 0.7, "max_tokens": 4000, "reasoning_effort": "low"}

    def test_numbers_and_thinking_values_are_normalised(self):
        a = sp.parameter_profile({"temperature": 1, "max_tokens": 4000.0, "enable_thinking": True})
        b = sp.parameter_profile({"temperature": 1.0, "max_tokens": 4000, "enable_thinking": "on"})
        assert a == b == {"temperature": 1.0, "max_tokens": 4000, "enable_thinking": "on"}
        assert sp.parameter_profile({"enable_thinking": False}) == {"enable_thinking": "off"}

    @pytest.mark.parametrize("value", ["true", "Yes", "1", "no", " on", "OFF"])
    def test_thinking_flag_accepts_only_the_select_values(self, value):
        assert sp.thinking_flag(value) is None
        think = {"parameter": "enable_thinking", "values": ["off", "on"], "default": "on"}
        assert sp.openai_compatible_reasoning_payload(think, {"enable_thinking": value}) == {}

    def test_hash_is_sha256_of_sorted_compact_json(self):
        profile = {"temperature": 0.7, "max_tokens": 4000, "enable_thinking": "off"}
        canonical = '{"enable_thinking":"off","max_tokens":4000,"temperature":0.7}'
        assert sp.canonical_json(profile) == canonical
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert sp.parameter_profile_sha256(profile) == expected
        assert sp.system_key("m/x", profile) == f"m/x@{expected[:12]}"

    def test_key_order_does_not_change_the_hash(self):
        a = {"temperature": 0.7, "reasoning_effort": "low"}
        b = {"reasoning_effort": "low", "temperature": 0.7}
        assert sp.parameter_profile_sha256(a) == sp.parameter_profile_sha256(b)

    def test_reasoning_arm_and_seed_change(self):
        base = {"temperature": 0.7, "max_tokens": 4000}
        off = sp.system_key(QWEN_27B, sp.parameter_profile({**base, "enable_thinking": "off"}))
        on = sp.system_key(QWEN_27B, sp.parameter_profile({**base, "enable_thinking": "on"}))
        off_other_seed = sp.system_key(
            QWEN_27B, sp.parameter_profile({**base, "enable_thinking": "off", "seed": 99})
        )
        assert off != on
        assert off == off_other_seed

    def test_system_record_shape(self):
        rec = sp.system_record(
            GPT_OSS_20B,
            {"temperature": 0.7, "max_tokens": 4000, "reasoning_effort": "low", "seed": 1},
            provider="DeepInfra",
            provider_model_id=GPT_OSS_20B,
            response_model=GPT_OSS_20B,
        )
        assert rec["parameter_profile"] == {
            "temperature": 0.7,
            "max_tokens": 4000,
            "reasoning_effort": "low",
        }
        canonical = '{"max_tokens":4000,"reasoning_effort":"low","temperature":0.7}'
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert rec["parameter_profile_sha256"] == digest
        assert rec["key"] == f"{GPT_OSS_20B}@{digest[:12]}"
        assert rec["model_id"] == GPT_OSS_20B
        assert rec["provider"] == "DeepInfra"
        assert rec["provider_model_id"] == GPT_OSS_20B
        assert rec["response_model"] == GPT_OSS_20B


class TestReasoningPayload:
    EFFORT = {"parameter": "reasoning_effort", "type": "select", "values": ["low", "medium", "high"], "default": "medium"}
    THINK = {"parameter": "enable_thinking", "type": "select", "values": ["off", "on"], "default": "on"}

    def test_effort_run_value_default_and_invalid(self):
        assert sp.openai_compatible_reasoning_payload(self.EFFORT, {"reasoning_effort": "low"}) == {"reasoning_effort": "low"}
        assert sp.openai_compatible_reasoning_payload(self.EFFORT, {}) == {"reasoning_effort": "medium"}
        assert sp.openai_compatible_reasoning_payload(self.EFFORT, {"reasoning_effort": "xhigh"}) == {}

    def test_thinking_switch(self):
        assert sp.openai_compatible_reasoning_payload(self.THINK, {"enable_thinking": "off"}) == {
            "chat_template_kwargs": {"enable_thinking": False}
        }
        assert sp.openai_compatible_reasoning_payload(self.THINK, {}) == {
            "chat_template_kwargs": {"enable_thinking": True}
        }
        assert sp.openai_compatible_reasoning_payload(self.THINK, {"enable_thinking": "maybe"}) == {}

    def test_undeclared_or_unsupported_knob_sends_nothing(self):
        assert sp.openai_compatible_reasoning_payload(None, {"reasoning_effort": "low"}) == {}
        budget = {"parameter": "thinking_budget", "type": "number", "default": 1024}
        assert sp.openai_compatible_reasoning_payload(budget, {"thinking_budget": 512}) == {}

    def test_reasoning_params_sent_round_trip(self):
        assert sp.reasoning_params_sent({"chat_template_kwargs": {"enable_thinking": False}}) == {
            "enable_thinking": "off"
        }
        assert sp.reasoning_params_sent({"reasoning_effort": "low", "model": "x"}) == {"reasoning_effort": "low"}
        assert sp.reasoning_params_sent({"model": "x"}) == {}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
class TestCatalogEntries:
    @pytest.mark.parametrize(
        "model_id,price_in,price_out",
        [
            (LLAMA_8B_TURBO, 0.02, 0.04),
            (MISTRAL_SMALL, 0.075, 0.2),
            (PHI_4, 0.07, 0.14),
            (GPT_OSS_20B, 0.03, 0.14),
        ],
    )
    def test_added_models_are_active_deepinfra_rows(self, model_id, price_in, price_out):
        row = _catalog_by_id()[model_id]
        assert row["provider"] == "DeepInfra"
        assert row["is_active"] is True
        assert row["model_type"] == "chat"
        assert row["input_cost_per_million"] == price_in
        assert row["output_cost_per_million"] == price_out
        assert pc.get_provider_from_model(model_id) == "deepinfra"

    def test_gpt_oss_20b_declares_reasoning_effort(self):
        rc = _catalog_by_id()[GPT_OSS_20B]["default_config"]["reasoning_config"]
        assert rc["parameter"] == "reasoning_effort"
        assert rc["type"] == "select"
        assert rc["values"] == ["low", "medium", "high"]
        assert rc["default"] in rc["values"]

    @pytest.mark.parametrize("model_id,default", [(QWEN_27B, "on"), (GEMMA_26B, "off"), (NEMOTRON, "off")])
    def test_thinking_switch_defaults_to_provider_default(self, model_id, default):
        # The default equals what DeepInfra does when no switch is sent, so
        # existing runs that never set it keep their behaviour.
        rc = _catalog_by_id()[model_id]["default_config"]["reasoning_config"]
        assert rc == {
            "parameter": "enable_thinking",
            "type": "select",
            "values": ["off", "on"],
            "default": default,
            "label": "Thinking",
        }

    @pytest.mark.parametrize("model_id", [LLAMA_8B_TURBO, MISTRAL_SMALL, PHI_4])
    def test_models_without_thinking_declare_no_knob(self, model_id):
        assert "default_config" not in _catalog_by_id()[model_id]
        pc.reload_capability_caches()
        assert pc.model_reasoning_config(model_id) is None


# ---------------------------------------------------------------------------
# DeepInfra client over a fake HTTP session
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, body):
        self.status = 200
        self._body = body

    async def text(self):
        return json.dumps(self._body)

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    payloads: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None, timeout=None):
        type(self).payloads.append(json)
        return _FakeResponse(
            {
                "model": json["model"],
                "choices": [{"message": {"content": '{"antwort": "ja"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )


@pytest.fixture
def fake_http(monkeypatch):
    _FakeSession.payloads = []
    monkeypatch.setattr(di_mod.aiohttp, "ClientSession", _FakeSession)
    pc.reload_capability_caches()
    return _FakeSession


class TestDeepInfraReasoningKnobs:
    def _svc(self):
        return di_mod.DeepInfraService(api_key="test-deepinfra-key")

    def test_gpt_oss_effort_sent_and_reported(self, fake_http):
        out = self._svc().generate(prompt="p", model_name=GPT_OSS_20B, reasoning_effort="low", seed=7)
        payload = fake_http.payloads[-1]
        assert payload["reasoning_effort"] == "low"
        assert "chat_template_kwargs" not in payload
        md = out["metadata"]
        assert md["reasoning_params_sent"] == {"reasoning_effort": "low"}
        assert md["provider_model_id"] == GPT_OSS_20B
        assert md["response_model"] == GPT_OSS_20B

    def test_gpt_oss_default_effort_when_run_sets_none(self, fake_http):
        self._svc().generate(prompt="p", model_name=GPT_OSS_20B)
        assert fake_http.payloads[-1]["reasoning_effort"] == "medium"

    @pytest.mark.parametrize("model_id,value,flag", [(QWEN_27B, "off", False), (GEMMA_26B, "on", True), (NEMOTRON, "off", False)])
    def test_thinking_switch_sent_as_chat_template_kwargs(self, fake_http, model_id, value, flag):
        out = self._svc().generate(prompt="p", model_name=model_id, enable_thinking=value)
        payload = fake_http.payloads[-1]
        assert payload["chat_template_kwargs"] == {"enable_thinking": flag}
        assert "reasoning_effort" not in payload
        assert out["metadata"]["reasoning_params_sent"] == {"enable_thinking": value}

    @pytest.mark.parametrize("model_id", [LLAMA_8B_TURBO, MISTRAL_SMALL, PHI_4])
    def test_models_without_knob_get_no_reasoning_fields(self, fake_http, model_id):
        out = self._svc().generate(prompt="p", model_name=model_id, reasoning_effort="low", enable_thinking="on")
        payload = fake_http.payloads[-1]
        assert payload["model"] == model_id
        assert "reasoning_effort" not in payload
        assert "chat_template_kwargs" not in payload
        assert out["metadata"]["reasoning_params_sent"] == {}


# ---------------------------------------------------------------------------
# Mock generation run through the worker
# ---------------------------------------------------------------------------
def _query_side_effect(gen, project, task, model):
    """Same DB-lookup sequence as test_tasks_key_resolution_audit."""
    call_idx = [0]

    def side_effect(*args):
        q = MagicMock()
        call_idx[0] += 1
        idx = call_idx[0]
        if idx == 1:
            q.filter.return_value.first.return_value = gen
        elif idx == 2:
            q.filter.return_value.first.return_value = project
        elif idx == 3:
            q.filter.return_value.first.return_value = task
            q.filter.return_value.filter.return_value.first.return_value = task
        elif idx == 4:
            q.filter.return_value.first.return_value = model
        elif idx == 5:
            q.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
        elif idx == 6:
            q.filter.return_value.count.return_value = 0
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.distinct.return_value.all.return_value = []
        return q

    return side_effect


def _mock_run(model_id, model_config):
    import tasks as tasks_module
    from tasks import generate_llm_responses

    row = _catalog_by_id()[model_id]

    gen = MagicMock()
    gen.status = "pending"
    gen.task_id = "task-1"
    gen.structure_key = None
    gen.runs_requested = 1

    project = MagicMock()
    project.deleted_at = None
    project.generation_config = {
        "prompt_structures": [
            {"key": "default", "structure": {"system_prompt": "Du bist Richter.", "instruction_prompt": "$text"}},
        ],
        "selected_configuration": {"parameters": {}, "model_configs": {model_id: model_config}},
    }
    project.label_config = None
    project.label_config_version = None

    task = MagicMock()
    task.id = "task-1"
    task.project_id = "p1"
    task.data = {"text": "Ein erfundener Sachverhalt."}
    task.meta = {}
    task.created_at = datetime.now()

    model = MagicMock()
    model.id = model_id
    model.name = row["name"]
    model.provider = row["provider"]
    model.parameter_constraints = None
    model.recommended_parameters = None
    model.default_config = row.get("default_config")
    model.endpoint_model_name = None

    db = MagicMock()
    db.query.side_effect = _query_side_effect(gen, project, task, model)
    captured = []
    db.add.side_effect = captured.append

    service = di_mod.DeepInfraService(api_key="test-deepinfra-key")
    user_aware = MagicMock()
    user_aware.get_ai_service_for_user.return_value = service
    user_aware.get_ai_service_for_model_row.return_value = service

    with patch.object(tasks_module, "HAS_DATABASE", True), \
         patch.object(tasks_module, "HAS_AI_SERVICES", True), \
         patch.object(tasks_module, "HAS_GENERATION_PARSER", True), \
         patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(tasks_module, "user_aware_ai_service", user_aware), \
         patch.object(tasks_module, "notify_task_completed", MagicMock()):
        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id=model_id,
            user_id="u1",
            structure_key="default",
            organization_id=None,
        )
    assert result["status"] == "success", result
    responses = [o for o in captured if hasattr(o, "response_metadata")]
    assert len(responses) == 1
    return json.loads(responses[0].response_metadata), gen


class TestMockRunSystemKey:
    def test_run_records_provider_ids_and_profile_hash(self, fake_http):
        md, gen = _mock_run(GPT_OSS_20B, {"temperature": 0.7, "max_tokens": 4000, "reasoning_effort": "low"})
        system = md["system"]
        assert system["model_id"] == GPT_OSS_20B
        assert system["provider"] == "DeepInfra"
        assert system["provider_model_id"] == GPT_OSS_20B
        assert system["response_model"] == GPT_OSS_20B
        assert system["parameter_profile"] == {
            "temperature": 0.7,
            "max_tokens": 4000,
            "reasoning_effort": "low",
        }
        canonical = '{"max_tokens":4000,"reasoning_effort":"low","temperature":0.7}'
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        assert system["parameter_profile_sha256"] == digest
        assert system["key"] == f"{GPT_OSS_20B}@{digest[:12]}"
        # What the record says was sent is what went over the wire.
        payload = fake_http.payloads[-1]
        assert payload["model"] == GPT_OSS_20B
        assert payload["reasoning_effort"] == "low"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 4000

    def test_reasoning_arm_is_a_distinct_system(self, fake_http):
        off, _ = _mock_run(QWEN_27B, {"temperature": 0.7, "max_tokens": 4000, "enable_thinking": "off"})
        on, _ = _mock_run(QWEN_27B, {"temperature": 0.7, "max_tokens": 4000, "enable_thinking": "on"})
        assert [p["chat_template_kwargs"] for p in fake_http.payloads] == [
            {"enable_thinking": False},
            {"enable_thinking": True},
        ]
        assert off["system"]["model_id"] == on["system"]["model_id"] == QWEN_27B
        assert off["system"]["key"] != on["system"]["key"]
        assert off["system"]["parameter_profile"]["enable_thinking"] == "off"
        assert on["system"]["parameter_profile"]["enable_thinking"] == "on"

    def test_unset_switch_records_and_sends_the_declared_default(self, fake_http):
        # A run config that never set the switch (selected before the
        # catalog declared it) shows the default in the model picker; the
        # model receives that same value and the profile records it.
        md, gen = _mock_run(QWEN_27B, {"temperature": 0.7, "max_tokens": 4000})
        assert fake_http.payloads[-1]["chat_template_kwargs"] == {"enable_thinking": True}
        assert md["system"]["parameter_profile"]["enable_thinking"] == "on"
        assert gen.parameters["enable_thinking"] == "on"

    def test_model_without_knob_profile_has_no_reasoning(self, fake_http):
        md, _ = _mock_run(PHI_4, {"temperature": 0.7, "max_tokens": 4000})
        assert md["system"]["parameter_profile"] == {"temperature": 0.7, "max_tokens": 4000}
        assert md["system"]["provider_model_id"] == PHI_4
