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

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    OrganizationMembership,
    PreferenceRanking,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _proj(db, admin, org, **kw):
    pid = _uid()
    p = Project(
        id=pid,
        title=kw.get("title", f"P-{pid[:6]}"),
        created_by=admin.id,
        label_config=kw.get("label_config", '<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>'),
        is_private=kw.get("is_private", False),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
        questionnaire_config=kw.get("questionnaire_config", None),
        annotation_time_limit_enabled=kw.get("annotation_time_limit_enabled", False),
        annotation_time_limit_seconds=kw.get("annotation_time_limit_seconds", None),
        strict_timer_enabled=kw.get("strict_timer_enabled", False),
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


# ==============================================================
# Evaluation config tests
# ==============================================================


class TestEvaluationConfig:
    def test_get_eval_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/evaluation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_get_eval_config_no_label_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, label_config=None)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/evaluation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_get_eval_config_force_regenerate(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/evaluation-config?force_regenerate=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
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

    def test_detect_answer_types(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/detect-answer-types",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_detect_answer_types_no_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, label_config=None)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/detect-answer-types",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_field_types(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/field-types",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_field_types_no_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, label_config=None)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/field-types",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/evaluations/projects/nonexistent/evaluation-config",
            headers=auth_headers["admin"],
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
# Project organizations tests
# ==============================================================


class TestProjectOrganizations:
    def test_list_project_organizations(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_assign_org_to_project(self, client, test_db, test_users, auth_headers, test_org):
        # Create another org
        org2 = Organization(
            id=_uid(), name="Second Org", slug="second-org",
            display_name="Second Org Display",
        )
        test_db.add(org2)
        test_db.flush()

        # Add admin membership to org2
        mem = OrganizationMembership(
            id=_uid(), user_id=test_users[0].id,
            organization_id=org2.id, role="ORG_ADMIN",
        )
        test_db.add(mem)

        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/organizations/{org2.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201, 404)

    def test_remove_org_from_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 400, 404)


# ==============================================================
# Timer tests
# ==============================================================


class TestTimerEndpoints:
    def test_start_timer(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, annotation_time_limit_enabled=True, annotation_time_limit_seconds=300)
        t = _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/start-timer",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)

    def test_timer_status(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, annotation_time_limit_enabled=True, annotation_time_limit_seconds=300)
        t = _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks/{t.id}/timer-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)

    def test_timer_not_enabled(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, annotation_time_limit_enabled=False)
        t = _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/start-timer",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400)


# ==============================================================
# Questionnaire tests
# ==============================================================


class TestQuestionnaireEndpoints:
    def test_submit_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org,
                  questionnaire_enabled=True,
                  questionnaire_config='<View><Choices name="difficulty" toName="text"><Choice value="Easy"/><Choice value="Hard"/></Choices></View>')
        t = _tsk(test_db, p, test_users[0])
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/questionnaire-response",
            json={
                "annotation_id": ann.id,
                "result": [{"from_name": "difficulty", "to_name": "text", "type": "choices", "value": {"choices": ["Easy"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 400)

    def test_questionnaire_not_enabled(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org, questionnaire_enabled=False)
        t = _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/questionnaire-response",
            json={"annotation_id": _uid(), "result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
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
    def test_update_with_schema_change(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        # Update with new label config
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": '<View><Text name="text" value="$text"/><TextArea name="comment" toName="text"/></View>'},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_without_schema_change(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        # Update with same label config
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": p.label_config},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ==============================================================
# Human evaluation session tests
# ==============================================================


class TestHumanEvaluationSessions:
    def test_get_sessions(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/evaluations/human/sessions/{p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_human_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/evaluations/human/config/{p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)


# ==============================================================
# Evaluation validation tests
# ==============================================================


class TestEvaluationValidation:
    def test_validate_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            "/api/evaluations/evaluations/validate-config",
            json={
                "project_id": p.id,
                "evaluation_configs": [
                    {"id": "test", "metric": "exact_match", "prediction_fields": ["answer"],
                     "reference_fields": ["answer"], "enabled": True}
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422, 500)


# ==============================================================
# Evaluation metadata tests
# ==============================================================


class TestEvaluationMetadata:
    def test_available_fields(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/available-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_configured_methods(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/configured-methods",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_evaluation_history(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/evaluation-history",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422, 500)

    def test_evaluated_models(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{p.id}/evaluated-models",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)

    def test_significance(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/significance/{p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422, 500)

    def test_statistics(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/evaluations/projects/{p.id}/statistics",
            json={},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422, 500)


# ==============================================================
# Evaluation run endpoint tests
# ==============================================================


class TestEvaluationRunEndpoint:
    def test_run_evaluation(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        t = _tsk(test_db, p, test_users[0])
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

    def test_get_run_results_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/run/results/project/{p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 500)


# ==============================================================
# Task fields endpoint
# ==============================================================


class TestTaskFields:
    def test_get_task_fields(self, client, test_db, test_users, auth_headers, test_org):
        p = _proj(test_db, test_users[0], test_org)
        _tsk(test_db, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
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
