"""End-to-end: the seed a generation stores is the seed that was sent.

Kolibri-1 benchmark, K3: a custom model whose row did not declare seed support
went out unseeded while its run config showed seed 42, and nothing said so.
Drives the REAL generation loop (``generate_llm_responses``) against the test
Postgres with a fake provider service that, like every real AI service,
reports the seed it sent in ``metadata["seed"]`` (None when it left it out).

Pinned:

* a run with no usable seed configured (``"seed": null``) requests 42;
* a seed the service sent lands on the generation row and in the run's
  stored parameters;
* a seed the service did not send is stored as None on both, and recorded as
  ``seed_not_sent`` (requested value and reason) in the row's metadata and in
  the run's parameters, which the UI shows.
"""

import json

import pytest

import tasks
from generation.llm_generation_service import (
    SEED_DECLARED_UNSUPPORTED,
    SEED_UNSUPPORTED_BY_MODEL,
    _resolve_seed,
    _seed_not_sent,
)
from models import Generation, ResponseGeneration

pytestmark = [pytest.mark.integration, pytest.mark.database]

STRUCTURE_KEY = "s0"


def _gen_config(seed_params):
    return {
        "prompt_structures": {
            STRUCTURE_KEY: {
                "name": "Test",
                "system_prompt": "Du bist Jurist.",
                "instruction_prompt": "$text",
            }
        },
        "selected_configuration": {"parameters": seed_params},
    }


class _SeedService:
    """Provider stand-in that sends the seed only when it supports one."""

    def __init__(self, supports_seed):
        self.supports_seed = supports_seed
        self.received_seeds = []
        self._key_resolution_route = "test_key"
        self._provider_name = "OpenAI"
        self._invocation_user_id = None
        self._invocation_organization_id = None
        self._invocation_project_id = None

    def is_available(self):
        return True

    def generate(
        self,
        prompt=None,
        system_prompt=None,
        model_name=None,
        temperature=None,
        max_tokens=None,
        **kwargs
    ):
        self.received_seeds.append(kwargs.get("seed"))
        sent = kwargs.get("seed") if self.supports_seed else None
        return {
            "success": True,
            "content": "Antwort: Ja",
            "model": model_name,
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "metadata": {"finish_reason": "stop", "seed": sent},
        }


def _run(
    db_conn,
    monkeypatch,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    service,
    seed_params,
):
    import uuid as _uuid

    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda db, user_id, provider, *a, **k: service,
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(
        created_by=user.id,
        label_config=None,
        generation_config=_gen_config(seed_params),
    )
    task = make_task(
        project.id, {"text": "Ist der Vertrag gültig?"}, created_by=user.id
    )
    rg = ResponseGeneration(
        id=str(_uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        model_id=model.id,
        status="pending",
        runs_requested=1,
        structure_key=STRUCTURE_KEY,
        created_by=user.id,
    )
    db_conn.add(rg)
    db_conn.commit()

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        structure_key=STRUCTURE_KEY,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )
    assert result["status"] == "success", result
    child = db_conn.query(Generation).filter(Generation.generation_id == rg.id).one()
    db_conn.expire(rg)
    parent = db_conn.get(ResponseGeneration, rg.id)
    metadata = child.response_metadata
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return child, parent, metadata


def test_null_seed_config_requests_the_default_and_stores_it(
    db_conn,
    monkeypatch,
    make_user,
    make_llm_model,
    make_project,
    make_task,
):
    service = _SeedService(supports_seed=True)
    child, parent, metadata = _run(
        db_conn,
        monkeypatch,
        make_user,
        make_llm_model,
        make_project,
        make_task,
        service,
        {"seed": None},
    )
    assert service.received_seeds == [42]
    assert child.seed == 42
    assert metadata["seed"] == 42
    assert "seed_not_sent" not in metadata
    assert parent.parameters["seed"] == 42
    assert "seed_not_sent" not in parent.parameters
    provenance = parent.parameters["_param_provenance"]["seed"]
    assert provenance["value"] == 42
    assert provenance["defaulted_from"] is None


def test_configured_seed_is_sent_and_stored(
    db_conn,
    monkeypatch,
    make_user,
    make_llm_model,
    make_project,
    make_task,
):
    service = _SeedService(supports_seed=True)
    child, parent, _metadata = _run(
        db_conn,
        monkeypatch,
        make_user,
        make_llm_model,
        make_project,
        make_task,
        service,
        {"seed": 7},
    )
    assert service.received_seeds == [7]
    assert child.seed == 7
    assert parent.parameters["seed"] == 7


def test_seed_not_sent_is_recorded_and_never_stored_as_sent(
    db_conn,
    monkeypatch,
    make_user,
    make_llm_model,
    make_project,
    make_task,
):
    service = _SeedService(supports_seed=False)
    child, parent, metadata = _run(
        db_conn,
        monkeypatch,
        make_user,
        make_llm_model,
        make_project,
        make_task,
        service,
        {"seed": 42},
    )
    expected = {"requested": 42, "reason": SEED_UNSUPPORTED_BY_MODEL}
    assert child.seed is None
    assert metadata["seed"] is None
    assert metadata["seed_not_sent"] == expected
    # The run's stored parameters (what the run detail and result views show)
    # carry the seed that was sent, with the requested one beside it.
    assert parent.parameters["seed"] is None
    assert parent.parameters["seed_not_sent"] == expected
    assert parent.parameters["_param_provenance"]["seed"]["value"] is None
    assert parent.parameters["_param_provenance"]["seed"]["not_sent"] == expected


class TestSeedHelpers:
    @pytest.mark.parametrize("value, expected", [(42, 42), (0, 0), ("7", 7), (7.0, 7)])
    def test_usable_seed_is_kept(self, value, expected):
        provenance = {"seed": {"value": value, "source": "user_project"}}
        assert _resolve_seed(value, provenance) == expected
        assert provenance["seed"] == {"value": value, "source": "user_project"}

    @pytest.mark.parametrize("value", [None, "abc", -1, 7.5, True, [], {}])
    def test_unusable_seed_falls_back_to_the_default(self, value):
        provenance = {"seed": {"value": value, "source": "user_project"}}
        assert _resolve_seed(value, provenance) == 42
        assert provenance["seed"] == {
            "value": 42,
            "source": "system",
            "defaulted_from": value,
        }

    def test_sent_seed_is_no_record(self):
        assert _seed_not_sent(42, {"seed": 42}, "gpt-4o") is None

    def test_no_requested_seed_is_no_record(self):
        assert _seed_not_sent(None, {"seed": None}, "gpt-4o") is None

    def test_catalog_model_reason(self):
        assert _seed_not_sent(42, {"seed": None}, "claude-x") == {
            "requested": 42,
            "reason": SEED_UNSUPPORTED_BY_MODEL,
        }

    def test_custom_model_reason(self):
        # A custom row only leaves the seed out when it declares
        # parameter_constraints.seed.supported: false.
        assert _seed_not_sent(42, {}, "custom-3f2b6a9e") == {
            "requested": 42,
            "reason": SEED_DECLARED_UNSUPPORTED,
        }
