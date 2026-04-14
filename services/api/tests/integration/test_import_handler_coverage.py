"""
Integration tests for the import handler body in import_export.py.

Targets: routers/projects/import_export.py — import_project_data handler,
         covering Label Studio format, generations, evaluations, task_id_mapping,
         questionnaire responses, and error branches.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import EvaluationRun, Generation, ResponseGeneration, TaskEvaluation
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _make_empty_project(db, admin, org):
    """Create an empty project for import testing."""
    project = Project(
        id=_uid(),
        title="Import Target",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.commit()
    return project


@pytest.mark.integration
class TestImportBasicTasks:
    """POST /api/projects/{project_id}/import — basic task import."""

    def test_import_simple_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {"text": "Simple task 1"},
                {"text": "Simple task 2"},
                {"text": "Simple task 3"},
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 3
        assert body["total_items"] == 3
        assert body["project_id"] == project.id

    def test_import_label_studio_format(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "id": "task-001",
                    "data": {"text": "LS task 1"},
                    "meta": {"source": "import"},
                    "annotations": [
                        {
                            "result": [
                                {"from_name": "answer", "to_name": "text",
                                 "type": "choices", "value": {"choices": ["Ja"]}}
                            ],
                            "was_cancelled": False,
                        }
                    ],
                },
                {
                    "id": 2,
                    "data": {"text": "LS task 2"},
                },
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 2
        assert body["created_annotations"] == 1

    def test_import_with_meta(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "with meta"},
                    "meta": {"source": "test", "extra": "data"},
                }
            ],
            "meta": {"global_key": "global_value"},
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1

    def test_import_returns_task_id_mapping(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {"id": "original-1", "data": {"text": "Mapped task 1"}},
                {"id": "original-2", "data": {"text": "Mapped task 2"}},
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "task_id_mapping" in body
        assert "original-1" in body["task_id_mapping"]
        assert "original-2" in body["task_id_mapping"]


@pytest.mark.integration
class TestImportWithGenerations:
    """Import tasks with generation data (BenGER extension)."""

    def test_import_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "Gen task"},
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "Generated answer 1",
                        },
                        {
                            "model_id": "claude-3-sonnet",
                            "response_content": "Generated answer 2",
                        },
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_generations"] == 2

    def test_import_multiple_models(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "Multi-model task"},
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "GPT answer",
                        },
                        {
                            "model_id": "gpt-4o",
                            "response_content": "GPT answer 2",
                        },
                        {
                            "model_id": "claude-3-sonnet",
                            "response_content": "Claude answer",
                        },
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_generations"] == 3


@pytest.mark.integration
class TestImportWithEvaluationRuns:
    """Import with evaluation_runs data."""

    def test_import_evaluation_runs_only(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {"data": {"text": "Eval task"}},
            ],
            "evaluation_runs": [
                {
                    "id": _uid(),
                    "model_id": "gpt-4o",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 0.85},
                    "status": "completed",
                    "samples_evaluated": 1,
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_evaluation_runs"] == 1
        assert body["created_tasks"] == 1


@pytest.mark.integration
class TestImportWithQuestionnaireResponses:
    """Import annotations with questionnaire response data."""

    def test_import_questionnaire_responses(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "QR task"},
                    "annotations": [
                        {
                            "result": [
                                {"from_name": "answer", "to_name": "text",
                                 "type": "choices", "value": {"choices": ["Ja"]}}
                            ],
                            "questionnaire_response": {
                                "result": [
                                    {"from_name": "q1", "value": {"choices": ["Good"]}}
                                ]
                            },
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_annotations"] == 1
        assert body["created_questionnaire_responses"] == 1


@pytest.mark.integration
class TestImportSpanConversion:
    """Import with span annotation format conversion."""

    def test_import_label_studio_span_annotations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "This is a span test text"},
                    "annotations": [
                        {
                            "result": [
                                {
                                    "id": "span-1",
                                    "from_name": "label",
                                    "to_name": "text",
                                    "type": "labels",
                                    "value": {
                                        "start": 0,
                                        "end": 4,
                                        "text": "This",
                                        "labels": ["Entity"],
                                    },
                                },
                                {
                                    "id": "span-2",
                                    "from_name": "label",
                                    "to_name": "text",
                                    "type": "labels",
                                    "value": {
                                        "start": 10,
                                        "end": 14,
                                        "text": "span",
                                        "labels": ["Entity"],
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_annotations"] == 1


@pytest.mark.integration
class TestImportAccessControl:
    """Access control for the import endpoint."""

    def test_import_nonexistent_project(self, client, test_db, test_users, auth_headers):
        payload = {"data": [{"text": "test"}]}
        resp = client.post(
            "/api/projects/nonexistent-id/import",
            json=payload,
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)

    def test_import_empty_data(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {"data": []}
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 0

    def test_import_multiple_annotations_per_task(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "Multi-annotation task"},
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                        "type": "choices", "value": {"choices": ["Ja"]}}],
                            "completed_by": test_users[0].id,
                        },
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                        "type": "choices", "value": {"choices": ["Nein"]}}],
                            "completed_by": test_users[1].id,
                        },
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_annotations"] == 2

    def test_import_annotation_with_ground_truth(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_empty_project(test_db, test_users[0], test_org)
        payload = {
            "data": [
                {
                    "data": {"text": "Ground truth task"},
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                        "type": "choices", "value": {"choices": ["Ja"]}}],
                            "ground_truth": True,
                            "lead_time": 15.5,
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=payload,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_annotations"] == 1


@pytest.mark.integration
class TestBulkExport:
    """POST /api/projects/bulk-export"""

    def _make_project_with_tasks(self, db, admin, org):
        project = Project(
            id=_uid(), title="Bulk Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        db.add(project)
        db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=org.id, assigned_by=admin.id,
        )
        db.add(po)
        db.flush()
        for i in range(2):
            t = Task(
                id=_uid(), project_id=project.id,
                data={"text": f"Bulk task {i}"}, inner_id=i + 1,
                created_by=admin.id,
            )
            db.add(t)
        db.commit()
        return project

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        p1 = self._make_project_with_tasks(test_db, test_users[0], test_org)
        p2 = self._make_project_with_tasks(test_db, test_users[0], test_org)
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id, p2.id], "format": "json", "include_data": True},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert "projects" in body
        assert len(body["projects"]) == 2

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        p1 = self._make_project_with_tasks(test_db, test_users[0], test_org)
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id], "format": "csv"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_without_data(self, client, test_db, test_users, auth_headers, test_org):
        p1 = self._make_project_with_tasks(test_db, test_users[0], test_org)
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id], "format": "json", "include_data": False},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert "projects" in body
        # Without include_data, tasks should not be present
        assert "tasks" not in body["projects"][0]

    def test_bulk_export_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": ["nonexistent-id"], "format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert body["projects"] == []

    def test_bulk_export_empty_list(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [], "format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert body["projects"] == []
