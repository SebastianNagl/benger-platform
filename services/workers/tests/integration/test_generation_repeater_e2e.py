"""End-to-end: a generation for a <Repeater> label config.

Drives the real generation loop (``generate_llm_responses``) against the test
Postgres with a fake provider. Pinned:

* the structured-output schema asks for one object per item of THIS task
  (an array pinned to the task's item count), not for template names;
* the appended format instruction shows one example object per item;
* the array answer is stored under the expanded, indexed control names.
"""

import json

import pytest

import tasks
from models import Generation, ResponseGeneration

pytestmark = [pytest.mark.integration, pytest.mark.database, pytest.mark.flags_on("variant_experiments")]

STRUCTURE_KEY = "s0"

DOCKET = """<View>
  <Repeater on="$cases" indexFlag="{{idx}}" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <Choices name="priority_{{idx}}" toName="case_{{idx}}">
      <Choice value="high"/><Choice value="low"/>
    </Choices>
  </Repeater>
</View>"""


class _StructuredService:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self._key_resolution_route = "test_key"
        self._provider_name = "OpenAI"
        self._invocation_user_id = None
        self._invocation_organization_id = None
        self._invocation_project_id = None

    def is_available(self):
        return True

    def generate_structured(self, prompt=None, system_prompt=None, json_schema=None, **kwargs):
        self.calls.append({"prompt": prompt, "json_schema": json_schema})
        return {
            "success": True,
            "content": json.dumps(self.answer),
            "model": kwargs.get("model_name"),
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "metadata": {"finish_reason": "stop", "seed": kwargs.get("seed")},
        }

    def generate(self, **kwargs):  # pragma: no cover - the structured path is taken
        raise AssertionError("expected structured output for a config with fields")


def test_repeater_generation_asks_per_item_and_stores_indexed_fields(
    db_conn, monkeypatch, make_user, make_llm_model, make_project, make_task,
):
    import uuid as _uuid

    answer = {
        "cases": [
            {"case": 2, "risk": 60, "priority": "high"},
            {"case": 1, "risk": 45, "priority": "low"},
        ]
    }
    service = _StructuredService(answer)
    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda db, user_id, provider, *a, **k: service,
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(
        created_by=user.id,
        label_config=DOCKET,
        generation_config={
            "prompt_structures": {
                STRUCTURE_KEY: {
                    "name": "Docket",
                    "system_prompt": "Assess every case.",
                    "instruction_prompt": "Cases follow.",
                }
            },
            "selected_configuration": {"parameters": {}},
        },
    )
    task = make_task(
        project.id,
        {"cases": [{"text": "A bicycle was taken."}, {"text": "An invoice was paid twice."}]},
        created_by=user.id,
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

    (call,) = service.calls
    schema = call["json_schema"]
    assert list(schema["properties"]) == ["cases"]
    cases = schema["properties"]["cases"]
    assert cases["minItems"] == cases["maxItems"] == 2
    assert list(cases["items"]["properties"]) == ["case", "risk", "priority"]
    instruction = call["prompt"].split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(instruction) == {
        "cases": [
            {"case": 1, "risk": "<your response>", "priority": "<your response>"},
            {"case": 2, "risk": "<your response>", "priority": "<your response>"},
        ]
    }
    assert "{{idx}}" not in call["prompt"]

    child = db_conn.query(Generation).filter(Generation.generation_id == rg.id).one()
    assert child.parse_status == "success", child.parse_error
    stored = {r["from_name"]: r["value"] for r in child.parsed_annotation}
    assert stored == {
        "risk_1": {"number": 60},
        "priority_1": {"choices": ["high"]},
        "risk_0": {"number": 45},
        "priority_0": {"choices": ["low"]},
    }
