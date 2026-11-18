"""A task's variant assignment never reaches the system under test.

``task.meta.variant`` says which tasks are twins of one another (CORE 2.57);
a model that saw it could answer the twins alike on purpose. The generation
loop builds prompts from ``task.data`` only, so a canary placed in the
assignment must appear neither in the messages the provider receives nor in
the generation's stored ``case_data``. Synthetic content only.
"""

import json
import uuid

import pytest

import tasks
from models import Generation, ResponseGeneration

pytestmark = [pytest.mark.integration, pytest.mark.database]

CANARY = "CANARY-VARIANT-91d0"
CONFIG = (
    '<View><Text name="facts_view" value="$facts"/>'
    '<TextArea name="answer" toName="facts_view"/></View>'
)
STRUCTURE = {
    "s0": {
        "name": "Test",
        "system_prompt": "You decide small civil disputes.",
        "instruction_prompt": "$facts",
    }
}
SPEC = {
    "schema_version": 1,
    "unit": {"name": "case"},
    "factors": [{"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]}],
}


class RecordingAIService:
    """Returns a fixed answer and keeps every prompt it was sent."""

    def __init__(self):
        self.sent = []
        self._key_resolution_route = "test_key"
        self._provider_name = "OpenAI"
        self._invocation_user_id = None
        self._invocation_organization_id = None
        self._invocation_project_id = None

    def is_available(self):
        return True

    def generate(self, prompt=None, system_prompt=None, **kwargs):
        self.sent.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
        text = '{"answer": "The claim succeeds."}'
        return {
            "success": True,
            "response_text": text,
            "content": text,
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "cost_usd": 0.0,
            "provider": "OpenAI",
            "temperature": 0.0,
            "metadata": {},
        }

    def generate_structured(self, *args, **kwargs):
        self.sent.append({"structured_args": args, **kwargs})
        return self.generate()


def test_variant_assignment_is_in_no_prompt_and_no_case_data(
    db_conn, make_user, make_llm_model, make_project, monkeypatch
):
    from project_models import Task
    from variant_design_guard import new_design_row

    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(
        created_by=user.id, label_config=CONFIG, generation_config={"prompt_structures": STRUCTURE}
    )
    db_conn.add(new_design_row(project.id, "swap", SPEC, created_by=user.id))
    db_conn.commit()
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=1,
        data={"facts": "Alma Reyes asks for the fence to be moved."},
        meta={
            "variant": {
                "design": "swap",
                "unit": "u1",
                "factors": {"role": "claimant"},
                "provenance": {"generator": CANARY},
            }
        },
        created_by=user.id,
    )
    db_conn.add(task)
    db_conn.commit()
    assert db_conn.get(Task, task.id).variant_design == "swap"

    rg = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        model_id=model.id,
        status="pending",
        runs_requested=1,
        structure_key="s0",
        created_by=user.id,
    )
    db_conn.add(rg)
    db_conn.commit()

    fake = RecordingAIService()
    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda db, user_id, provider, *a, **k: fake,
    )
    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        structure_key="s0",
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )
    assert result["status"] == "success", result

    assert fake.sent, "the provider was never called"
    sent = json.dumps(fake.sent, default=str)
    assert "Alma Reyes" in sent  # the bound task data does go out
    assert CANARY not in sent
    assert '"variant"' not in sent and "'variant'" not in sent

    child = db_conn.query(Generation).filter(Generation.generation_id == rg.id).one()
    db_conn.expire(rg)
    stored = " ".join(str(v) for v in (child.case_data, rg.prompt_used) if v is not None)
    assert CANARY not in stored
    assert "variant" not in json.loads(child.case_data)
