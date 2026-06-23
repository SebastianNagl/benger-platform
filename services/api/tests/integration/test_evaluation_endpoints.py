"""Integration tests for evaluation API routers.

Covers the 7 evaluation sub-routers:
  - config: Evaluation configuration management
  - multi_field: N:M field mapping, available fields, project results
  - results: Evaluation results, per-sample analysis, export
  - status: Evaluation listing, types, status
  - validation: Config alignment validation
  - metadata: Evaluated models, configured methods
  - human: Human evaluation sessions (Likert, preference)

ASYNC vs SYNC lanes
-------------------
Most read endpoints were migrated sync→async (``get_async_db`` +
``await db.execute(select(...))`` + the ``*_async`` access helpers). Those
tests seed through ``async_test_db`` and drive ``async_test_client``,
overriding ``require_user`` with a real seeded user via the ``_as_user``
contextmanager (a superadmin owner for happy/200 paths — the superadmin
short-circuit makes all access checks True; a non-superadmin outsider +
a patched ``*_async`` access helper for the deterministic 403s).

The handlers that stayed SYNC (``db: Session = Depends(get_db)``) keep the
legacy ``client``/``test_db``/``auth_headers`` lane:
  - PUT  /projects/{id}/evaluation-config       (update_project_evaluation_config)
  - GET  /                                       (evaluations list)
  - GET  /evaluation-types                       (LIST)
  - POST /human/session/start                    (start_human_evaluation_session)

Seeding uses real PostgreSQL with transaction rollback isolation. No mocks for
database operations.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    EvaluationType,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


# ---------------------------------------------------------------------------
# A realistic label_config for a QA project with Choices + TextArea fields
# ---------------------------------------------------------------------------
LABEL_CONFIG_QA = """<View>
  <Header value="Legal QA Task"/>
  <Text name="question" value="$question"/>
  <Text name="context" value="$context"/>
  <Choices name="answer_type" toName="question" choice="single-select">
    <Choice value="Ja"/>
    <Choice value="Nein"/>
  </Choices>
  <TextArea name="answer" toName="question" rows="4"/>
</View>"""


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth override contextmanager (mirrors the reference branch suites)
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user, is_superadmin=None):
    sa = db_user.is_superadmin if is_superadmin is None else is_superadmin
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=sa,
        is_active=True,
        email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# Async seeding helpers (the default lane for the migrated endpoints)
# ---------------------------------------------------------------------------


async def _make_owner(db, *, name="Test Admin", is_superadmin=True):
    """Seed a project owner. Defaults to a superadmin (the access-check
    short-circuit makes the happy paths reach the handler body)."""
    u = User(
        id=_uid(),
        username=f"eval-ep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db):
    oid = _uid()
    org = Organization(
        id=oid, name=f"org-{oid[:6]}", display_name=f"Org {oid[:6]}",
        slug=f"org-{oid[:8]}", is_active=True,
    )
    db.add(org)
    await db.flush()
    return org


async def _create_eval_project_async(
    db,
    owner,
    org,
    *,
    label_config: Optional[str] = LABEL_CONFIG_QA,
    num_tasks: int = 3,
    with_annotations: bool = True,
    with_generations: bool = True,
    with_evaluation_run: bool = True,
    with_task_evaluations: bool = True,
    evaluation_config: dict = None,
    generation_config: dict = None,
    is_private: bool = False,
    link_org: bool = True,
) -> Dict:
    """Async twin of the legacy ``_create_evaluation_project`` helper.

    Builds a complete project with tasks, annotations, generations, and an
    evaluation run (with per-sample TaskEvaluations) through ``async_test_db``.
    Returns a dict keyed by created-object type.
    """
    project_id = _uid()
    project = Project(
        id=project_id,
        title="Eval Integration Test Project",
        description="Project for evaluation endpoint integration tests",
        label_config=label_config,
        label_config_version="v1",
        created_by=owner.id,
        is_published=True,
        is_private=is_private,
        assignment_mode="open",
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()

    if link_org:
        db.add(ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=owner.id,
        ))
        db.add(ProjectMember(
            id=_uid(),
            project_id=project.id,
            user_id=owner.id,
            role="admin",
            is_active=True,
        ))
        await db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={
                "question": f"Was ist die Rechtsfolge in Fall {i + 1}?",
                "context": f"Sachverhalt {i + 1}: Der Beklagte hat ...",
            },
            created_by=owner.id,
            updated_by=owner.id,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()

    annotations = []
    if with_annotations:
        for task in tasks:
            annot = Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=owner.id,
                result=[
                    {
                        "from_name": "answer_type",
                        "to_name": "question",
                        "type": "choices",
                        "value": {"choices": ["Ja"]},
                    },
                    {
                        "from_name": "answer",
                        "to_name": "question",
                        "type": "textarea",
                        "value": {"text": ["Die Rechtsfolge ist ..."]},
                    },
                ],
            )
            db.add(annot)
            annotations.append(annot)
        await db.flush()

    response_generations = []
    generations = []
    if with_generations:
        for task in tasks:
            rg = ResponseGeneration(
                id=_uid(),
                project_id=project.id,
                task_id=task.id,
                model_id="gpt-4o",
                status="completed",
                responses_generated=1,
                created_by=owner.id,
            )
            db.add(rg)
            await db.flush()
            response_generations.append(rg)

            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=task.id,
                model_id="gpt-4o",
                run_index=0,
                case_data=f"Fall {task.inner_id}",
                response_content="Die Rechtsfolge lautet ...",
                status="completed",
                parse_status="success",
                parsed_annotation=[
                    {
                        "from_name": "answer_type",
                        "to_name": "question",
                        "type": "choices",
                        "value": {"choices": ["Ja"]},
                    },
                    {
                        "from_name": "answer",
                        "to_name": "question",
                        "type": "textarea",
                        "value": {"text": ["Model answer ..."]},
                    },
                ],
            )
            db.add(gen)
            generations.append(gen)
        await db.flush()

    evaluation_runs = []
    task_evaluations_list = []
    if with_evaluation_run:
        eval_run = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy", "f1"],
            metrics={
                "cfg1:answer_type:answer_type:accuracy": 0.85,
                "cfg1:answer:answer:f1": 0.78,
            },
            eval_metadata={
                "evaluation_type": "evaluation",
                "triggered_by": owner.id,
                "evaluation_configs": [
                    {
                        "id": "cfg1",
                        "metric": "accuracy",
                        "prediction_fields": ["answer_type"],
                        "reference_fields": ["answer_type"],
                        "enabled": True,
                    }
                ],
            },
            status="completed",
            samples_evaluated=num_tasks,
            has_sample_results=with_task_evaluations,
            created_by=owner.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(eval_run)
        await db.flush()
        evaluation_runs.append(eval_run)

        # Migration 043 made TaskEvaluation.judge_run_id NOT NULL.
        judge_run = EvaluationJudgeRun(
            id=_uid(),
            evaluation_id=eval_run.id,
            judge_model_id=None,
            run_index=0,
            status="completed",
        )
        db.add(judge_run)
        await db.flush()
        eval_run._test_judge_run = judge_run

        if with_task_evaluations and generations:
            for i, (task, gen) in enumerate(zip(tasks, generations)):
                te = TaskEvaluation(
                    id=_uid(),
                    evaluation_id=eval_run.id,
                    judge_run_id=judge_run.id,
                    task_id=task.id,
                    generation_id=gen.id,
                    field_name="answer_type",
                    answer_type="single_choice",
                    ground_truth={"value": "Ja"},
                    prediction={"value": "Ja" if i % 2 == 0 else "Nein"},
                    metrics={"accuracy": 1.0 if i % 2 == 0 else 0.0, "score": 0.9},
                    passed=i % 2 == 0,
                    created_at=datetime.utcnow(),
                )
                db.add(te)
                task_evaluations_list.append(te)
        await db.flush()

    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "response_generations": response_generations,
        "generations": generations,
        "evaluation_runs": evaluation_runs,
        "task_evaluations": task_evaluations_list,
        "owner": owner,
    }


# ---------------------------------------------------------------------------
# Sync seeding helper (only for the sync-handler tests below)
# ---------------------------------------------------------------------------


def _create_evaluation_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    *,
    label_config: Optional[str] = LABEL_CONFIG_QA,
    num_tasks: int = 3,
    with_annotations: bool = True,
    with_generations: bool = True,
    with_evaluation_run: bool = True,
    with_task_evaluations: bool = True,
    evaluation_config: dict = None,
    generation_config: dict = None,
) -> Dict:
    """Sync project builder for the SYNC-handler tests (PUT config, list
    endpoints, start-session). Mirrors the async twin above."""
    admin = test_users[0]
    contributor = test_users[1]
    annotator = test_users[2]

    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title="Eval Integration Test Project",
        description="Project for evaluation endpoint integration tests",
        label_config=label_config,
        label_config_version="v1",
        created_by=admin.id,
        is_published=True,
        assignment_mode="open",
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    test_db.add(project)
    test_db.flush()

    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=admin.id,
    )
    test_db.add(project_org)

    for user, role in [
        (admin, "admin"), (contributor, "contributor"), (annotator, "annotator")
    ]:
        test_db.add(
            ProjectMember(
                id=str(uuid.uuid4()),
                project_id=project.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
    test_db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={
                "question": f"Was ist die Rechtsfolge in Fall {i + 1}?",
                "context": f"Sachverhalt {i + 1}: Der Beklagte hat ...",
            },
            created_by=admin.id,
            updated_by=admin.id,
        )
        test_db.add(task)
        tasks.append(task)
    test_db.flush()

    test_db.commit()

    return {
        "project": project,
        "tasks": tasks,
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
    }


# ===========================================================================
# Priority 1 — Config endpoints (config.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationConfig:
    """GET (async) / PUT (sync) /api/evaluations/projects/{id}/evaluation-config"""

    @pytest.mark.asyncio
    async def test_get_evaluation_config_generates_from_label_config(
        self, async_test_client, async_test_db
    ):
        """When no evaluation_config exists, GET generates one from label_config."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "detected_answer_types" in body
        assert "available_methods" in body
        field_names = [at["name"] for at in body["detected_answer_types"]]
        assert "answer_type" in field_names or "answer" in field_names

    @pytest.mark.asyncio
    async def test_get_evaluation_config_returns_existing(
        self, async_test_client, async_test_db
    ):
        """When evaluation_config already exists, GET returns it unchanged."""
        existing_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"]}},
            "selected_methods": {"answer": {"automated": ["bleu"]}},
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=existing_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["selected_methods"]["answer"]["automated"] == ["bleu"]

    @pytest.mark.asyncio
    async def test_get_evaluation_config_project_not_found(
        self, async_test_client, async_test_db
    ):
        """GET with nonexistent project returns 404."""
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{uuid.uuid4()}/evaluation-config",
            )
        assert resp.status_code == 404, resp.text

    def test_put_evaluation_config_saves_successfully(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT (SYNC handler) saves evaluation config and returns it."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        new_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"], "available_human": []}},
            "selected_methods": {"answer": {"automated": ["bleu"], "human": []}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            json=new_config,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Evaluation configuration updated successfully"
        assert body["config"]["selected_methods"]["answer"]["automated"] == ["bleu"]
        assert body["config"]["label_config_version"] == "v1"

    def test_put_evaluation_config_validates_metrics(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT (SYNC) rejects invalid metric names not in available_methods."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        bad_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"], "available_human": []}},
            "selected_methods": {"answer": {"automated": ["nonexistent_metric"], "human": []}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            json=bad_config,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "nonexistent_metric" in resp.json()["detail"]

    def test_put_evaluation_config_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT (SYNC) with nonexistent project returns 404."""
        resp = client.put(
            f"/api/evaluations/projects/{uuid.uuid4()}/evaluation-config",
            json={"selected_methods": {}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_put_evaluation_config_invokes_after_save_hook(
        self, client, test_db, test_users, test_org, auth_headers, monkeypatch
    ):
        """PUT (SYNC) runs the after_eval_config_save extension hook with the
        saved config.

        Pinning the hook contract so extended packages (which derive things like
        Korrektur fields from the config) can rely on it firing on every save.
        """
        import extensions

        seen: list[dict] = []

        def fake_hook(db, project, config):
            seen.append({"project_id": project.id, "config": dict(config)})

        monkeypatch.setattr(extensions, "run_after_eval_config_save",
                            lambda db, project, config: fake_hook(db, project, config))

        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        new_config = {"evaluation_configs": [{"metric": "bleu"}]}
        resp = client.put(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            json=new_config,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert len(seen) == 1
        assert seen[0]["project_id"] == data["project"].id
        assert seen[0]["config"]["evaluation_configs"] == [{"metric": "bleu"}]


@pytest.mark.integration
class TestDetectAnswerTypes:
    """GET /api/evaluations/projects/{project_id}/detect-answer-types (async)"""

    @pytest.mark.asyncio
    async def test_detect_types_from_label_config(
        self, async_test_client, async_test_db
    ):
        """Detects Choices and TextArea from the QA label_config."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/detect-answer-types",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert len(body["detected_types"]) > 0
        assert "available_methods" in body

    @pytest.mark.asyncio
    async def test_detect_types_no_label_config(
        self, async_test_client, async_test_db
    ):
        """Returns empty when project has no label_config."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            label_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/detect-answer-types",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["detected_types"] == []

    @pytest.mark.asyncio
    async def test_detect_types_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{uuid.uuid4()}/detect-answer-types",
            )
        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestFieldTypes:
    """GET /api/evaluations/projects/{project_id}/field-types (async)"""

    @pytest.mark.asyncio
    async def test_field_types_returns_types_and_criteria(
        self, async_test_client, async_test_db
    ):
        """Returns field type info with LLM judge criteria recommendations."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/field-types",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert isinstance(body["field_types"], dict)
        for field_name, field_info in body["field_types"].items():
            assert "type" in field_info
            assert "tag" in field_info
            assert "recommended_criteria" in field_info

    @pytest.mark.asyncio
    async def test_field_types_no_label_config(
        self, async_test_client, async_test_db
    ):
        """Returns empty field_types when no label_config."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            label_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/field-types",
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["field_types"] == {}


# ===========================================================================
# Priority 2 — Multi-field evaluation (multi_field.py)
# ===========================================================================


@pytest.mark.integration
class TestAvailableFields:
    """GET /api/evaluations/projects/{project_id}/available-fields (async)"""

    @pytest.mark.asyncio
    async def test_available_fields_includes_all_categories(
        self, async_test_client, async_test_db
    ):
        """Returns model_response_fields, human_annotation_fields, reference_fields."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/available-fields",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "model_response_fields" in body
        assert "human_annotation_fields" in body
        assert "reference_fields" in body
        assert "all_fields" in body
        assert len(body["human_annotation_fields"]) > 0 or len(body["all_fields"]) > 0

    @pytest.mark.asyncio
    async def test_available_fields_detects_model_fields_from_generations(
        self, async_test_client, async_test_db
    ):
        """Model response fields are extracted from parsed generation annotations."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/available-fields",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "answer_type" in body["model_response_fields"] or "answer" in body["model_response_fields"]

    @pytest.mark.asyncio
    async def test_available_fields_includes_task_data_as_reference(
        self, async_test_client, async_test_db
    ):
        """Task data fields (question, context) appear as reference fields."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/available-fields",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "question" in body["reference_fields"] or "context" in body["reference_fields"]

    @pytest.mark.asyncio
    async def test_available_fields_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{uuid.uuid4()}/available-fields",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_available_fields_permission_denied(
        self, async_test_client, async_test_db
    ):
        """Non-member cannot access fields of an unlinked private project."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            is_private=True, link_org=False,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.multi_field.fields.auth_service.check_project_access_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/available-fields",
            )
        assert resp.status_code == 403, resp.text


@pytest.mark.integration
class TestProjectEvaluationResults:
    """GET /api/evaluations/run/results/project/{project_id} (async)"""

    @pytest.mark.asyncio
    async def test_project_results_returns_completed_evaluation(
        self, async_test_client, async_test_db
    ):
        """Returns evaluation run data with parsed metrics and progress."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert body["total_count"] >= 1
        assert len(body["evaluations"]) >= 1

        eval_result = body["evaluations"][0]
        assert eval_result["status"] == "completed"
        assert eval_result["model_id"] == "gpt-4o"
        assert eval_result["samples_evaluated"] == 3
        assert "results_by_config" in eval_result
        assert "progress" in eval_result

    @pytest.mark.asyncio
    async def test_project_results_latest_only(
        self, async_test_client, async_test_db
    ):
        """latest_only=True returns only the most recent evaluation."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)

        eval_run2 = EvaluationRun(
            id=_uid(),
            project_id=data["project"].id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"cfg2:answer:answer:accuracy": 0.92},
            eval_metadata={"evaluation_type": "evaluation"},
            status="completed",
            samples_evaluated=3,
            created_by=data["owner"].id,
            created_at=datetime.utcnow() + timedelta(hours=1),
            completed_at=datetime.utcnow() + timedelta(hours=1),
        )
        async_test_db.add(eval_run2)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{data['project'].id}?latest_only=true",
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["total_count"] == 1

            resp_all = await async_test_client.get(
                f"/api/evaluations/run/results/project/{data['project'].id}?latest_only=false",
            )
        assert resp_all.status_code == 200, resp_all.text
        assert resp_all.json()["total_count"] >= 2

    @pytest.mark.asyncio
    async def test_project_results_empty_project(
        self, async_test_client, async_test_db
    ):
        """Project with no evaluation runs returns empty list."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 0
        assert body["evaluations"] == []

    @pytest.mark.asyncio
    async def test_project_results_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# Priority 3 — Results (results.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationResultsByProject:
    """GET /api/evaluations/results/{project_id} (async)"""

    @pytest.mark.asyncio
    async def test_results_include_automated_evaluations(
        self, async_test_client, async_test_db
    ):
        """Returns automated evaluation results."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/results/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        automated_results = [r for r in body if r["results"].get("type") == "automated"]
        assert len(automated_results) >= 1

    @pytest.mark.asyncio
    async def test_results_filter_automated_only(
        self, async_test_client, async_test_db
    ):
        """include_human=false filters out human evaluations."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/results/{data['project'].id}?include_human=false",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for result in body:
            assert result["results"]["type"] != "human_likert"
            assert result["results"]["type"] != "human_preference"

    @pytest.mark.asyncio
    async def test_results_permission_denied(
        self, async_test_client, async_test_db
    ):
        """Non-member gets 403."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            is_private=True, link_org=False,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/results/{data['project'].id}",
            )
        assert resp.status_code == 403, resp.text


@pytest.mark.integration
class TestEvaluationSamples:
    """GET /api/evaluations/{evaluation_id}/samples (async)"""

    @pytest.mark.asyncio
    async def test_samples_returns_paginated_results(
        self, async_test_client, async_test_db
    ):
        """Returns per-sample results with pagination."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{eval_id}/samples?page=1&page_size=10",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert body["total"] == len(data["task_evaluations"])
        for item in body["items"]:
            assert "field_name" in item
            assert "metrics" in item
            assert "passed" in item

    @pytest.mark.asyncio
    async def test_samples_filter_by_passed(
        self, async_test_client, async_test_db
    ):
        """Filter by passed=true returns only passing samples."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{eval_id}/samples?passed=true",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for item in body["items"]:
            assert item["passed"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_samples_filter_by_field_name(
        self, async_test_client, async_test_db
    ):
        """Filter by field_name returns only matching samples."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{eval_id}/samples?field_name=answer_type",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for item in body["items"]:
            assert item["field_name"] == "answer_type"

    @pytest.mark.asyncio
    async def test_samples_evaluation_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{uuid.uuid4()}/samples",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_samples_pagination_has_next(
        self, async_test_client, async_test_db
    ):
        """has_next is True when more items exist beyond current page."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org, num_tasks=5)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{eval_id}/samples?page=1&page_size=2",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["has_next"] == True  # noqa: E712
        assert len(body["items"]) == 2


# ===========================================================================
# Priority 4 — Status & types (status.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationsList:
    """GET /api/evaluations/ (SYNC handler)"""

    def test_list_evaluations_returns_all_accessible(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns evaluations scoped to accessible projects."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        # Seed an eval run (sync) so the list has something to return.
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"accuracy": 0.85},
            eval_metadata={"evaluation_type": "evaluation"},
            status="completed",
            samples_evaluated=3,
            created_by=data["admin"].id,
            created_at=datetime.utcnow(),
        )
        test_db.add(eval_run)
        test_db.commit()

        resp = client.get(
            "/api/evaluations/",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        eval_entry = body[0]
        assert "id" in eval_entry
        assert "project_id" in eval_entry
        assert "model_id" in eval_entry
        assert "metrics" in eval_entry
        assert "status" in eval_entry

    def test_list_evaluations_empty_for_no_projects(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """User with no project access gets empty list."""
        resp = client.get(
            "/api/evaluations/",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


@pytest.mark.integration
class TestEvaluationTypes:
    """GET /api/evaluations/evaluation-types (LIST, sync) and
    /evaluation-types/{id} (single, async)"""

    def test_list_evaluation_types(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns all active evaluation types (SYNC list).

        Self-seeds a unique-id row rather than the shared
        ``test_evaluation_types`` fixture, whose fixed-id bulk insert
        UniqueViolation's against the long-lived test DB.
        """
        seeded_id = f"acc-{uuid.uuid4().hex[:8]}"
        test_db.add(EvaluationType(
            id=seeded_id,
            name="List Accuracy",
            description="Classification accuracy",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"],
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            "/api/evaluations/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert seeded_id in {et["id"] for et in body}
        for et in body:
            assert "id" in et
            assert "name" in et
            assert "category" in et
            assert "higher_is_better" in et

    def test_list_evaluation_types_filter_by_category(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Filter by category returns only matching types (SYNC list).

        Self-seeds a unique-id classification row (see note on the colliding
        ``test_evaluation_types`` fixture ids above)."""
        seeded_id = f"cls-{uuid.uuid4().hex[:8]}"
        test_db.add(EvaluationType(
            id=seeded_id,
            name="Filter Classification",
            description="classification filter row",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"],
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            "/api/evaluations/evaluation-types?category=classification",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert seeded_id in {et["id"] for et in body}
        for et in body:
            assert et["category"] == "classification"

    @pytest.mark.asyncio
    async def test_get_evaluation_type_by_id(
        self, async_test_client, async_test_db
    ):
        """Get specific evaluation type returns correct data (ASYNC single).

        Self-seeds a unique-id row rather than using the shared
        ``test_evaluation_types`` fixture, whose fixed ids UniqueViolation
        against the long-lived test DB.
        """
        owner = await _make_owner(async_test_db)
        et_id = f"accuracy-{uuid.uuid4().hex[:8]}"
        async_test_db.add(EvaluationType(
            id=et_id,
            name="Accuracy",
            description="Measures prediction accuracy",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0.0, "max": 1.0},
            applicable_project_types=["text_classification"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation-types/{et_id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == et_id
        assert body["name"] == "Accuracy"
        assert body["category"] == "classification"
        assert body["higher_is_better"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_evaluation_type_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/evaluation-types/nonexistent_metric",
            )
        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestEvaluationStatus:
    """GET /api/evaluations/evaluation/status/{evaluation_id} (async)"""

    @pytest.mark.asyncio
    async def test_get_evaluation_status(
        self, async_test_client, async_test_db
    ):
        """Returns status of a completed evaluation."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{eval_id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == eval_id
        assert body["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_evaluation_status_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_get_evaluation_status_permission_denied(
        self, async_test_client, async_test_db
    ):
        """User without project access gets 403."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            is_private=True, link_org=False,
            with_generations=False,
            with_annotations=False,
        )
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.status.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{eval_id}",
            )
        assert resp.status_code == 403, resp.text


@pytest.mark.integration
class TestSupportedMetrics:
    """GET /api/evaluations/supported-metrics

    NOTE: This endpoint imports ml_evaluation modules that live in the workers
    service. When called in the API test container, the import fails and crashes
    the ASGI handler in a way that corrupts the TestClient lifecycle. The endpoint
    is tested via the workers test suite and E2E tests instead.
    """


# ===========================================================================
# Priority 5 — Validation (validation.py)
# ===========================================================================


@pytest.mark.integration
class TestValidateConfig:
    """POST /api/evaluations/validate-config (async)"""

    @pytest.mark.asyncio
    async def test_validate_config_matching_fields(
        self, async_test_client, async_test_db
    ):
        """Matching generation and evaluation fields produces valid result."""
        gen_config = {
            "prompt_structures": [
                {"output_fields": ["answer_type", "answer"]}
            ]
        }
        eval_config = {
            "detected_answer_types": [
                {"name": "answer_type"},
                {"name": "answer"},
            ],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/validate-config?project_id={data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["valid"] == True  # noqa: E712
        assert "answer_type" in body["matched_fields"]
        assert "answer" in body["matched_fields"]
        assert body["errors"] == []

    @pytest.mark.asyncio
    async def test_validate_config_mismatched_fields(
        self, async_test_client, async_test_db
    ):
        """Mismatched fields produce errors/warnings."""
        gen_config = {
            "prompt_structures": [
                {"output_fields": ["answer_type", "extra_field"]}
            ]
        }
        eval_config = {
            "detected_answer_types": [
                {"name": "answer_type"},
                {"name": "reasoning"},
            ],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/validate-config?project_id={data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["errors"]) > 0
        assert "reasoning" in body["missing_in_generation"]
        assert "extra_field" in body["missing_in_evaluation"]

    @pytest.mark.asyncio
    async def test_validate_config_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/validate-config?project_id={uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_validate_config_no_overlap(
        self, async_test_client, async_test_db
    ):
        """No overlapping fields at all produces an error."""
        gen_config = {
            "prompt_structures": [{"output_fields": ["field_a"]}]
        }
        eval_config = {
            "detected_answer_types": [{"name": "field_b"}],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/validate-config?project_id={data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["valid"] == False  # noqa: E712
        assert any("No overlapping" in e for e in body["errors"])


# ===========================================================================
# Priority 6 — Metadata (metadata.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluatedModels:
    """GET /api/evaluations/projects/{project_id}/evaluated-models (async)"""

    @pytest.mark.asyncio
    async def test_evaluated_models_returns_model_with_scores(
        self, async_test_client, async_test_db
    ):
        """Returns the model that was evaluated with scores."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/evaluated-models",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        model_ids = [m["model_id"] for m in body]
        assert "gpt-4o" in model_ids
        gpt4_entry = next(m for m in body if m["model_id"] == "gpt-4o")
        assert gpt4_entry["evaluation_count"] >= 1
        assert gpt4_entry["average_score"] is not None

    @pytest.mark.asyncio
    async def test_evaluated_models_include_configured(
        self, async_test_client, async_test_db
    ):
        """include_configured=True includes models from generation_config."""
        gen_config = {
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3.5-sonnet"]
            }
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            generation_config=gen_config,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        model_ids = [m["model_id"] for m in body]
        assert "claude-3.5-sonnet" in model_ids
        claude_entry = next(m for m in body if m["model_id"] == "claude-3.5-sonnet")
        assert claude_entry["is_configured"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_evaluated_models_empty_project(
        self, async_test_client, async_test_db
    ):
        """Project with no generations/evaluations returns empty list."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/evaluated-models",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == []

    @pytest.mark.asyncio
    async def test_evaluated_models_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{uuid.uuid4()}/evaluated-models",
            )
        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestConfiguredMethods:
    """GET /api/evaluations/projects/{project_id}/configured-methods (async)"""

    @pytest.mark.asyncio
    async def test_configured_methods_returns_fields(
        self, async_test_client, async_test_db
    ):
        """Returns configured methods with result status."""
        eval_config = {
            "detected_answer_types": [{"name": "answer_type", "type": "choices"}],
            "available_methods": {
                "answer_type": {
                    "type": "choices",
                    "to_name": "question",
                    "available_metrics": ["accuracy", "f1"],
                    "available_human": [],
                }
            },
            "selected_methods": {
                "answer_type": {
                    "automated": ["accuracy"],
                    "human": [],
                }
            },
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=eval_config,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert len(body["fields"]) >= 1
        field = body["fields"][0]
        assert field["field_name"] == "answer_type"
        assert len(field["automated_methods"]) >= 1
        assert field["automated_methods"][0]["method_name"] == "accuracy"
        assert field["automated_methods"][0]["is_configured"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_configured_methods_no_eval_config(
        self, async_test_client, async_test_db
    ):
        """Project with no evaluation_config returns empty fields."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project'].id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fields"] == []

    @pytest.mark.asyncio
    async def test_configured_methods_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{uuid.uuid4()}/configured-methods",
            )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# Priority 7 — Human evaluation (human.py)
# ===========================================================================


@pytest.mark.integration
class TestHumanEvaluationConfig:
    """GET /api/evaluations/human/config/{project_id} (async)"""

    @pytest.mark.asyncio
    async def test_human_config_returns_methods_and_dimensions(
        self, async_test_client, async_test_db
    ):
        """Returns human methods and available dimensions."""
        eval_config = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {
                "answer": {
                    "automated": [],
                    "human": [
                        {
                            "name": "likert_scale",
                            "parameters": {
                                "dimensions": ["correctness", "completeness"]
                            },
                        }
                    ],
                }
            },
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "answer" in body["human_methods"]
        assert "correctness" in body["available_dimensions"]
        assert "completeness" in body["available_dimensions"]

    @pytest.mark.asyncio
    async def test_human_config_no_eval_config(
        self, async_test_client, async_test_db
    ):
        """Returns empty when no evaluation_config exists."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["human_methods"] == {}

    @pytest.mark.asyncio
    async def test_human_config_default_dimensions(
        self, async_test_client, async_test_db
    ):
        """Returns default dimensions when no custom dimensions configured."""
        eval_config = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {
                "answer": {
                    "automated": [],
                    "human": ["likert_scale"],
                }
            },
            "label_config_version": "v1",
        }
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        defaults = {"correctness", "completeness", "style", "usability"}
        assert set(body["available_dimensions"]) == defaults

    @pytest.mark.asyncio
    async def test_human_config_project_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestHumanEvaluationSessions:
    """GET /api/evaluations/human/sessions/{project_id} (async)"""

    @pytest.mark.asyncio
    async def test_list_sessions_returns_created_sessions(
        self, async_test_client, async_test_db
    ):
        """Returns sessions with correct data."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=_uid(),
            project_id=data["project"].id,
            evaluator_id=data["owner"].id,
            session_type="likert",
            items_evaluated=2,
            total_items=5,
            status="active",
            session_config={"dimensions": ["correctness"]},
            created_at=datetime.utcnow(),
        )
        async_test_db.add(session)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/sessions/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        s = body[0]
        assert s["id"] == session.id
        assert s["session_type"] == "likert"
        assert s["items_evaluated"] == 2
        assert s["total_items"] == 5
        assert s["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_sessions_empty(
        self, async_test_client, async_test_db
    ):
        """Project with no sessions returns empty list."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/sessions/{data['project'].id}",
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_sessions_permission_denied(
        self, async_test_client, async_test_db
    ):
        """Non-member cannot list sessions."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            is_private=True, link_org=False,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.human.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/human/sessions/{data['project'].id}",
            )
        assert resp.status_code == 403, resp.text


@pytest.mark.integration
class TestStartHumanEvaluationSession:
    """POST /api/evaluations/human/session/start (SYNC handler)"""

    def test_superadmin_can_start_session(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Superadmin can start a new human evaluation session."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )

        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": data["project"].id,
                "session_type": "likert",
                "field_name": "answer",
                "dimensions": ["correctness", "completeness"],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert body["session_type"] == "likert"
        assert body["status"] == "active"
        assert body["items_evaluated"] == 0
        assert body["total_items"] == len(data["tasks"])

    def test_non_superadmin_cannot_start_session(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-superadmin gets 403."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": data["project"].id,
                "session_type": "likert",
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_start_session_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": str(uuid.uuid4()),
                "session_type": "likert",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestSessionProgress:
    """GET /api/evaluations/human/session/{session_id}/progress (async)"""

    @pytest.mark.asyncio
    async def test_get_session_progress(
        self, async_test_client, async_test_db
    ):
        """Returns correct progress percentage."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=_uid(),
            project_id=data["project"].id,
            evaluator_id=data["owner"].id,
            session_type="likert",
            items_evaluated=2,
            total_items=4,
            status="active",
            created_at=datetime.utcnow(),
        )
        async_test_db.add(session)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/session/{session.id}/progress",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items_evaluated"] == 2
        assert body["total_items"] == 4
        assert body["progress_percentage"] == 50.0
        assert body["status"] == "active"

    @pytest.mark.asyncio
    async def test_session_progress_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/human/session/{uuid.uuid4()}/progress",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_session_progress_permission_denied(
        self, async_test_client, async_test_db
    ):
        """Non-superadmin non-owner cannot view progress."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=_uid(),
            project_id=data["project"].id,
            evaluator_id=data["owner"].id,  # owned by owner
            session_type="preference",
            items_evaluated=0,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        async_test_db.add(session)
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get(
                f"/api/evaluations/human/session/{session.id}/progress",
            )
        assert resp.status_code == 403, resp.text


@pytest.mark.integration
class TestDeleteHumanEvaluationSession:
    """DELETE /api/evaluations/human/session/{session_id} (async)"""

    @pytest.mark.asyncio
    async def test_superadmin_can_delete_session(
        self, async_test_client, async_test_db
    ):
        """Superadmin can delete a session and its evaluations."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=_uid(),
            project_id=data["project"].id,
            evaluator_id=data["owner"].id,
            session_type="likert",
            items_evaluated=1,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        async_test_db.add(session)
        await async_test_db.flush()

        likert = LikertScaleEvaluation(
            id=_uid(),
            session_id=session.id,
            task_id=data["tasks"][0].id,
            response_id="resp-1",
            dimension="correctness",
            rating=4,
            created_at=datetime.utcnow(),
        )
        async_test_db.add(likert)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.delete(
                f"/api/evaluations/human/session/{session.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"] == session.id

        # Verify session and evaluations are deleted.
        from sqlalchemy import select as _select
        remaining_session = (
            await async_test_db.execute(
                _select(HumanEvaluationSession).where(
                    HumanEvaluationSession.id == session.id
                )
            )
        ).scalars().first()
        assert remaining_session is None

        remaining_likert = (
            await async_test_db.execute(
                _select(LikertScaleEvaluation).where(
                    LikertScaleEvaluation.session_id == session.id
                )
            )
        ).scalars().first()
        assert remaining_likert is None

    @pytest.mark.asyncio
    async def test_non_superadmin_non_owner_cannot_delete(
        self, async_test_client, async_test_db
    ):
        """Non-superadmin who is not the session owner gets 403."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=_uid(),
            project_id=data["project"].id,
            evaluator_id=data["owner"].id,  # owned by owner
            session_type="likert",
            items_evaluated=0,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        async_test_db.add(session)
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.delete(
                f"/api/evaluations/human/session/{session.id}",
            )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_delete_session_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.delete(
                f"/api/evaluations/human/session/{uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# Cross-cutting: evaluation run detail results (multi_field.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationRunResults:
    """GET /api/evaluations/run/results/{evaluation_id} (async)"""

    @pytest.mark.asyncio
    async def test_run_results_returns_parsed_metrics(
        self, async_test_client, async_test_db
    ):
        """Returns detailed per-config results."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        eval_id = data["evaluation_runs"][0].id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{eval_id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["evaluation_id"] == eval_id
        assert body["status"] == "completed"
        assert body["samples_evaluated"] == 3
        assert "results_by_config" in body
        assert "aggregated_metrics" in body
        assert "cfg1:answer_type:answer_type:accuracy" in body["aggregated_metrics"]

    @pytest.mark.asyncio
    async def test_run_results_not_found(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{uuid.uuid4()}",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_run_results_non_evaluation_type_rejected(
        self, async_test_client, async_test_db
    ):
        """Evaluation with wrong eval_metadata type returns 400."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            with_evaluation_run=False,
            with_generations=False,
        )
        eval_run = EvaluationRun(
            id=_uid(),
            project_id=data["project"].id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={},
            eval_metadata={"evaluation_type": "generation"},  # Not "evaluation"
            status="completed",
            created_by=data["owner"].id,
            created_at=datetime.utcnow(),
        )
        async_test_db.add(eval_run)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{eval_run.id}",
            )
        assert resp.status_code == 400, resp.text
        assert "not an evaluation run" in resp.json()["detail"]


# ===========================================================================
# Export endpoint (results.py)
# ===========================================================================


@pytest.mark.integration
class TestExportResults:
    """POST /api/evaluations/export/{project_id} (async)"""

    @pytest.mark.asyncio
    async def test_export_json(self, async_test_client, async_test_db):
        """JSON export returns structured data."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/export/{data['project'].id}?format=json",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "exported_at" in body
        assert "results" in body

    @pytest.mark.asyncio
    async def test_export_csv(self, async_test_client, async_test_db):
        """CSV export returns text/csv content."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/evaluations/export/{data['project'].id}?format=csv",
            )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_permission_denied(self, async_test_client, async_test_db):
        """Non-member cannot export."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _create_eval_project_async(
            async_test_db, owner, org,
            is_private=True, link_org=False,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/export/{data['project'].id}?format=json",
            )
        assert resp.status_code == 403, resp.text
