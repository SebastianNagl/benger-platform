"""POST /api/evaluations/run records the model(s) it evaluates and makes a
run started through the API with inline configs show up on the
evaluations page.

Defect 5: a run was labelled with the project's most common generation
model whatever ``model_ids`` said, so a run restricted to another model read
"Modell: <most common>" and a merge of it put that model on the selection.
Defect 13: inline configs were not stored, so the evaluations page (which
lists the project's configs) said "not configured" next to finished rows.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import EvaluationRun, Generation, ResponseGeneration, User
from project_models import Project, Task
from routers.evaluations.multi_field.run import _run_model_label

CONFIG = {
    "id": "cfg-bleu",
    "metric": "bleu",
    "prediction_fields": ["answer"],
    "reference_fields": ["reference"],
    "enabled": True,
}


def _uid():
    return str(uuid.uuid4())


@pytest.fixture
def seeded(test_db):
    user = User(
        id=_uid(), username=f"er-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
        name="Runner", is_superadmin=True, is_active=True, email_verified=True,
    )
    test_db.add(user)
    test_db.flush()
    project = Project(
        id=_uid(), title="Run labels", created_by=user.id,
        label_config='<View><Text name="text" value="$text"/><TextArea name="answer" toName="text"/></View>',
    )
    test_db.add(project)
    test_db.flush()
    task = Task(id=_uid(), project_id=project.id, inner_id=1, data={"text": "Q", "reference": "A"})
    test_db.add(task)
    test_db.flush()
    # The common model has two generations, the other one.
    for model_id, n in (("model-common", 2), ("model-other", 1)):
        job = ResponseGeneration(
            id=_uid(), project_id=project.id, task_id=task.id, model_id=model_id,
            status="completed", created_by=user.id,
        )
        test_db.add(job)
        test_db.flush()
        for r in range(n):
            test_db.add(Generation(
                id=_uid(), generation_id=job.id, task_id=task.id, model_id=model_id,
                run_index=r, case_data="{}", response_content="A", status="completed",
                parse_status="success",
            ))
    test_db.commit()
    return user, project


def _run(client, user, body):
    auth_user = AuthUser(
        id=user.id, username=user.username, email=user.email, name=user.name,
        is_superadmin=True, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        with patch(
            "routers.evaluations.multi_field.run.celery_app.send_task",
            return_value=MagicMock(id="celery-run"),
        ), patch(
            "routers.evaluations.multi_field.run.resolve_user_org_for_project",
            return_value=None,
        ):
            return client.post("/api/evaluations/run", json=body)
    finally:
        app.dependency_overrides.pop(require_user, None)


@pytest.mark.integration
class TestRunRecordsItsModel:
    def test_a_run_restricted_to_one_model_carries_that_model(self, client, test_db, seeded):
        user, project = seeded
        resp = _run(client, user, {
            "project_id": project.id,
            "evaluation_configs": [CONFIG],
            "model_ids": ["model-other"],
        })
        assert resp.status_code == 200, resp.text
        run = test_db.get(EvaluationRun, resp.json()["evaluation_id"])
        assert run.model_id == "model-other"
        assert run.eval_metadata["evaluated_model_ids"] == ["model-other"]

    def test_a_run_over_several_models_names_none(self, client, test_db, seeded):
        user, project = seeded
        resp = _run(client, user, {"project_id": project.id, "evaluation_configs": [CONFIG]})
        assert resp.status_code == 200, resp.text
        run = test_db.get(EvaluationRun, resp.json()["evaluation_id"])
        assert run.model_id == "unknown"
        assert run.eval_metadata["evaluated_model_ids"] == ["model-common", "model-other"]


@pytest.mark.integration
class TestInlineConfigsAreStored:
    def test_configs_of_a_run_on_an_unconfigured_project_are_saved(
        self, client, test_db, seeded
    ):
        user, project = seeded
        resp = _run(client, user, {
            "project_id": project.id,
            "evaluation_configs": [CONFIG],
            "model_ids": ["model-other"],
        })
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        stored = test_db.get(Project, project.id).evaluation_config
        assert [c["id"] for c in stored["evaluation_configs"]] == ["cfg-bleu"]

    def test_existing_configs_are_left_alone(self, client, test_db, seeded):
        user, project = seeded
        project.evaluation_config = {"evaluation_configs": [{**CONFIG, "id": "cfg-mine"}]}
        test_db.commit()
        resp = _run(client, user, {
            "project_id": project.id,
            "evaluation_configs": [CONFIG],
            "model_ids": ["model-other"],
        })
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        stored = test_db.get(Project, project.id).evaluation_config
        assert [c["id"] for c in stored["evaluation_configs"]] == ["cfg-mine"]


def test_run_model_label():
    assert _run_model_label(["m"]) == "m"
    assert _run_model_label(["a", "b"]) == "unknown"
    assert _run_model_label([]) == "unknown"
