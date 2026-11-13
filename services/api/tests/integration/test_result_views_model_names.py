"""Result views name the model they show (defect 11).

A custom model's id is a random ``custom-<uuid>``. The evaluation results
table showed names while the run page and its per-sample rows showed raw ids
(and the rows showed no model at all, so the rows of a merged model looked
like any other run's)."""

import uuid
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMModel,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Project, Task

MODEL = "custom-view-0001"


def _uid():
    return str(uuid.uuid4())


async def _seed(db):
    user = User(
        id=_uid(), username=f"rv-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
        name="Viewer", is_superadmin=True, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.add(LLMModel(
        id=MODEL, name="View custom", provider="custom", model_type="chat",
        capabilities=["text_generation"], is_official=False, is_public=True,
        base_url="http://gpu.example.org:40001/v1", endpoint_model_name="view",
    ))
    await db.flush()
    project = Project(id=_uid(), title="Views", created_by=user.id)
    db.add(project)
    await db.flush()
    task = Task(id=_uid(), project_id=project.id, inner_id=1, data={"text": "Q"})
    db.add(task)
    await db.flush()
    job = ResponseGeneration(
        id=_uid(), project_id=project.id, task_id=task.id, model_id=MODEL,
        status="completed", created_by=user.id,
    )
    db.add(job)
    await db.flush()
    gen = Generation(
        id=_uid(), generation_id=job.id, task_id=task.id, model_id=MODEL,
        case_data="{}", response_content="A", status="completed",
    )
    db.add(gen)
    run = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=MODEL, evaluation_type_ids=["bleu"],
        metrics={}, status="completed", created_by=user.id,
        eval_metadata={"evaluation_type": "evaluation"},
    )
    db.add(run)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=_uid(), evaluation_id=run.id, judge_model_id="gpt-judge", run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()
    db.add(TaskEvaluation(
        id=_uid(), evaluation_id=run.id, judge_run_id=judge_run.id, task_id=task.id,
        generation_id=gen.id, field_name="cfg|answer|reference", answer_type="text",
        ground_truth="A", prediction="A", metrics={"bleu": 0.5}, passed=True,
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return user, run


def _as(user):
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id=user.id, username=user.username, email=user.email, name=user.name,
        is_superadmin=True, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.integration
class TestModelNamesInResultViews:
    @pytest.mark.asyncio
    async def test_sample_rows_carry_their_model(self, async_test_client, async_test_db):
        user, run = await _seed(async_test_db)
        _as(user)
        try:
            resp = await async_test_client.get(f"/api/evaluations/{run.id}/samples")
        finally:
            app.dependency_overrides.pop(require_user, None)
        assert resp.status_code == 200, resp.text
        (item,) = resp.json()["items"]
        assert item["model_id"] == MODEL
        assert item["model_name"] == "View custom"

    @pytest.mark.asyncio
    async def test_run_detail_names_its_model(self, async_test_client, async_test_db):
        user, run = await _seed(async_test_db)
        _as(user)
        try:
            resp = await async_test_client.get(f"/api/evaluations/run/results/{run.id}")
        finally:
            app.dependency_overrides.pop(require_user, None)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_id"] == MODEL
        assert body["model_name"] == "View custom"
