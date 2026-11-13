"""End-to-end: model and judge reasoning land in their own columns.

Drives the REAL generation loop (``generate_llm_responses``) and the REAL
evaluation chord (``run_evaluation``) against the test Postgres with fake
provider services that return reasoning beside the answer, the way
``ai_services`` now reports it (``response["reasoning"]``).

Pinned:

* ``generations.reasoning`` holds the model's reasoning, ``response_content``
  holds the answer unchanged, and a provider without reasoning leaves NULL;
* ``task_evaluations.raw_reasoning`` holds the judge model's reasoning, the
  score comes from the answer alone, and the reasoning is not copied into the
  metrics blob the score readers parse.
"""

import json

import pytest

import tasks
from models import Generation, ResponseGeneration, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

STRUCTURE_KEY = "s0"
GEN_CONFIG = {
    "prompt_structures": {
        STRUCTURE_KEY: {
            "name": "Test",
            "system_prompt": "Du bist Jurist.",
            "instruction_prompt": "$text",
        }
    }
}


class _ReasoningService:
    """Provider stand-in returning the standard service dict with reasoning."""

    def __init__(self, content, reasoning):
        self._content = content
        self._reasoning = reasoning
        self.calls = 0
        self._key_resolution_route = "test_key"
        self._provider_name = "OpenAI"
        self._invocation_user_id = None
        self._invocation_organization_id = None
        self._invocation_project_id = None

    def is_available(self):
        return True

    def generate(self, prompt=None, system_prompt=None, model_name=None,
                 temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        return {
            "success": True,
            "content": self._content,
            "reasoning": self._reasoning,
            "model": model_name,
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "metadata": {"finish_reason": "stop", "truncated": False, "refusal": False},
        }


def _run_generation(db_conn, project, task, model, user):
    import uuid as _uuid

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
    assert result["status"] == "success"
    [child] = db_conn.query(Generation).filter(Generation.generation_id == rg.id).all()
    return child


@pytest.mark.parametrize(
    "reasoning",
    ["Erst § 433 BGB prüfen, dann die Einwendungen.", None],
    ids=["with_reasoning", "without_reasoning"],
)
def test_generation_stores_reasoning_beside_answer(
    db_conn, make_user, make_llm_model, make_project, make_task, monkeypatch,
    reasoning,
):
    service = _ReasoningService("Antwort: Der Anspruch besteht.", reasoning)
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: service
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None, generation_config=GEN_CONFIG)
    task = make_task(project.id, {"text": "Besteht der Anspruch?"}, created_by=user.id)
    db_conn.commit()

    child = _run_generation(db_conn, project, task, model, user)

    assert service.calls == 1
    assert child.response_content == "Antwort: Der Anspruch besteht."
    assert child.reasoning == reasoning
    # The reasoning is a column of its own, not folded into the metadata blob.
    metadata = child.response_metadata
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    assert "reasoning" not in (metadata or {})


def test_llm_judge_reasoning_goes_to_raw_reasoning_column(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, monkeypatch,
):
    monkeypatch.delenv("E2E_TEST_MODE", raising=False)
    judge_service = _ReasoningService(
        json.dumps({"score": 0.8, "justification": "Im Kern richtig."}),
        "Die Antwort nennt § 433 BGB, also ist sie im Kern richtig.",
    )
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user",
        lambda *a, **k: judge_service,
    )

    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[{
            "id": "jcfg",
            "metric": "llm_judge_correctness",
            "prediction_fields": ["__all_model__"],
            "reference_fields": ["task.expected"],
            "metric_parameters": {
                "judges": [{"judge_model_id": "gpt-4o", "runs": 1}],
                "score_scale": "0-1",
            },
            "enabled": True,
        }],
    )
    db_conn.expire_all()

    [row] = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert judge_service.calls >= 1
    assert row.error_message is None
    assert row.metrics["llm_judge_correctness"] == pytest.approx(0.8)
    assert row.raw_reasoning == "Die Antwort nennt § 433 BGB, also ist sie im Kern richtig."
    # raw_output keeps the judge's answer; the reasoning is not duplicated
    # into the metrics blob.
    assert json.loads(row.raw_output)["score"] == 0.8
    blob = json.dumps(row.metrics, ensure_ascii=False)
    assert "_raw_reasoning" not in blob
    assert "Die Antwort nennt" not in blob
