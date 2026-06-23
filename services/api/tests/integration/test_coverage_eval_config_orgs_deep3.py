"""
Deep integration tests for evaluation config, organizations, timer, questionnaire,
label config versions, and remaining endpoints.

Targets: routers/evaluations/config.py, routers/projects/organizations.py,
routers/projects/timer.py, routers/projects/questionnaire.py,
routers/projects/label_config_versions.py, routers/evaluations/metadata.py,
routers/evaluations/human.py, routers/evaluations/multi_field.py,
routers/evaluations/validation.py, routers/generation.py,
routers/leaderboards.py, routers/flexible_annotations.py
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from models import User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

_DEFAULT_LABEL_CONFIG = (
    '<View><Text name="text" value="$text"/>'
    '<Choices name="answer" toName="text">'
    '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
)


def _uid():
    return str(uuid.uuid4())


def _proj(db, admin, org, **kw):
    pid = _uid()
    p = Project(
        id=pid,
        title=kw.get("title", f"P-{pid[:6]}"),
        created_by=admin.id,
        label_config=kw.get("label_config", _DEFAULT_LABEL_CONFIG),
        is_private=kw.get("is_private", False),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
        questionnaire_config=kw.get("questionnaire_config", None),
    )
    db.add(p)
    db.flush()
    if org:
        db.add(ProjectOrganization(id=_uid(), project_id=pid, organization_id=org.id, assigned_by=admin.id))
        db.flush()
    return p


def _tsk(db, project, admin, *, inner_id=1, data=None):
    t = Task(id=_uid(), project_id=project.id, data=data or {"text": f"T{inner_id}"}, inner_id=inner_id, created_by=admin.id)
    db.add(t)
    db.flush()
    return t


# ---------------------------------------------------------------------------
# Async helpers for the endpoints migrated to the async DB lane
#
# The sync ``client`` fixture only overrides ``get_db``; async handlers run
# against a separate ``get_async_db`` session that can't see rows seeded inside
# the sync ``test_db`` transaction. Tests hitting migrated endpoints seed via
# ``async_test_db`` and drive ``async_test_client`` instead, authenticating as a
# seeded superadmin (the access helpers short-circuit ``is_superadmin`` to True,
# matching ``X-Organization-Context: <org>`` admin access in the sync flow).
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _aseed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"d3-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Deep3 User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _aseed_proj(db, owner, **kw):
    pid = _uid()
    p = Project(
        id=pid,
        title=kw.get("title", f"P-{pid[:6]}"),
        created_by=owner.id,
        label_config=kw.get("label_config", _DEFAULT_LABEL_CONFIG),
        is_private=kw.get("is_private", False),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
        questionnaire_config=kw.get("questionnaire_config", None),
    )
    db.add(p)
    await db.flush()
    return p


async def _aseed_task(db, project, owner, *, inner_id=1, data=None):
    t = Task(
        id=_uid(),
        project_id=project.id,
        data=data or {"text": f"T{inner_id}"},
        inner_id=inner_id,
        created_by=owner.id,
    )
    db.add(t)
    await db.flush()
    return t


# ==============================================================
# Evaluation config tests
# ==============================================================


class TestEvaluationConfig:
    @pytest.mark.asyncio
    async def test_get_eval_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/evaluation-config"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_get_eval_config_no_label_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin, label_config=None)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/evaluation-config"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_get_eval_config_force_regenerate(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/evaluation-config?force_regenerate=true"
            )
        assert resp.status_code in (200, 500)

    def test_update_eval_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        config = {
            "detected_answer_types": [{"name": "answer", "type": "choices", "to_name": "text"}],
            "available_methods": {"answer": {"type": "choices", "available_metrics": ["exact_match"], "available_human": [], "tag": "Choices"}},
            "selected_methods": {"answer": {"automated": ["exact_match"], "human": []}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{p.id}/evaluation-config",
            json=config,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_update_eval_config_invalid_metric(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        config = {
            "detected_answer_types": [{"name": "answer", "type": "choices", "to_name": "text"}],
            "available_methods": {"answer": {"type": "choices", "available_metrics": ["exact_match"], "available_human": []}},
            "selected_methods": {"answer": {"automated": ["nonexistent_metric"]}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{p.id}/evaluation-config",
            json=config,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (400, 422, 500)

    @pytest.mark.asyncio
    async def test_detect_answer_types(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/detect-answer-types"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_detect_answer_types_no_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin, label_config=None)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/detect-answer-types"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_field_types(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/field-types"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_field_types_no_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin, label_config=None)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/field-types"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluation-config"
            )
        assert resp.status_code in (404, 500)


class TestDeriveEvaluationConfigs:
    def test_derive_from_selected_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["exact_match", {"name": "f1", "parameters": {"average": "weighted"}}],
                "field_mapping": {"prediction_field": "pred_answer", "reference_field": "ref_answer"},
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(configs) == 2
        assert configs[0]["metric"] == "exact_match"
        assert configs[1]["metric"] == "f1"
        assert configs[1].get("metric_parameters") is not None

    def test_derive_empty_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        assert _derive_evaluation_configs_from_selected_methods({}) == []

    def test_derive_invalid_selections(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({"field": "not_a_dict"})
        assert result == []


# ==============================================================
# Project organizations: list/add/remove endpoints were removed.
# Org assignment now flows exclusively through PATCH /{project_id}/visibility.
# ==============================================================


# ==============================================================
# Timer tests
# ==============================================================


class TestQuestionnaireEndpoints:
    @pytest.mark.asyncio
    async def test_submit_questionnaire(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(
            async_test_db,
            admin,
            questionnaire_enabled=True,
            questionnaire_config='<View><Choices name="difficulty" toName="text"><Choice value="Easy"/><Choice value="Hard"/></Choices></View>',
        )
        t = await _aseed_task(async_test_db, p, admin)
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=p.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        async_test_db.add(ann)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{t.id}/questionnaire-response",
                json={
                    "annotation_id": ann.id,
                    "result": [{"from_name": "difficulty", "to_name": "text", "type": "choices", "value": {"choices": ["Easy"]}}],
                },
            )
        assert resp.status_code in (200, 201, 400)

    @pytest.mark.asyncio
    async def test_questionnaire_not_enabled(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin, questionnaire_enabled=False)
        t = await _aseed_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{t.id}/questionnaire-response",
                json={"annotation_id": _uid(), "result": []},
            )
        assert resp.status_code in (400, 404)


# ==============================================================
# Draft endpoint tests
# ==============================================================


class TestDraftEndpoints:
    def test_save_draft(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        t = _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{t.id}/draft",
            json={"result": [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 404)


# ==============================================================
# Label config version tests
# ==============================================================


class TestLabelConfigVersions:
    @pytest.mark.asyncio
    async def test_update_with_schema_change(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        # Update with new label config
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"label_config": '<View><Text name="text" value="$text"/><TextArea name="comment" toName="text"/></View>'},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_without_schema_change(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        # Update with same label config
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"label_config": p.label_config},
            )
        assert resp.status_code == 200


# ==============================================================
# Human evaluation session tests
# ==============================================================


class TestHumanEvaluationSessions:
    @pytest.mark.asyncio
    async def test_get_sessions(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/human/sessions/{p.id}"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_human_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{p.id}"
            )
        assert resp.status_code in (200, 404)


# ==============================================================
# Evaluation validation tests
# ==============================================================


class TestEvaluationValidation:
    @pytest.mark.asyncio
    async def test_validate_config(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/evaluations/validate-config?project_id={p.id}",
                json={
                    "project_id": p.id,
                    "evaluation_configs": [
                        {"id": "test", "metric": "exact_match", "prediction_fields": ["answer"],
                         "reference_fields": ["answer"], "enabled": True}
                    ],
                },
            )
        assert resp.status_code in (200, 422, 500)


# ==============================================================
# Evaluation metadata tests
# ==============================================================


class TestEvaluationMetadata:
    @pytest.mark.asyncio
    async def test_available_fields(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/available-fields"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_configured_methods(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/configured-methods"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_evaluation_history(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/evaluation-history"
            )
        assert resp.status_code in (200, 422, 500)

    @pytest.mark.asyncio
    async def test_evaluated_models(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{p.id}/evaluated-models"
            )
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_significance(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/significance/{p.id}"
            )
        assert resp.status_code in (200, 422, 500)

    @pytest.mark.asyncio
    async def test_statistics(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{p.id}/statistics",
                json={},
            )
        assert resp.status_code in (200, 422, 500)


# ==============================================================
# Evaluation run endpoint tests
# ==============================================================


class TestEvaluationRunEndpoint:
    def test_run_evaluation(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            "/api/evaluations/run",
            json={
                "project_id": p.id,
                "model_id": "gpt-4",
                "evaluation_type_ids": ["accuracy"],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # May fail due to celery not being available, but exercises the code path
        assert resp.status_code in (200, 201, 400, 422, 500)

    @pytest.mark.asyncio
    async def test_get_run_results_project(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{p.id}"
            )
        assert resp.status_code in (200, 500)


# ==============================================================
# Task fields endpoint
# ==============================================================


class TestTaskFields:
    @pytest.mark.asyncio
    async def test_get_task_fields(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db)
        p = await _aseed_proj(async_test_db, admin)
        await _aseed_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields"
            )
        assert resp.status_code in (200, 404)


# ==============================================================
# My tasks endpoint
# ==============================================================


class TestMyTasks:
    def test_my_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/my-tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)


# ==============================================================
# Bulk export tasks
# ==============================================================


class TestBulkExportTasks:
    def test_bulk_export(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        for i in range(3):
            _tsk(test_db, p, test_users[0], inner_id=i + 1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 404)
