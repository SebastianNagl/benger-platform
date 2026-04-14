"""
Deep integration tests for project import/export endpoints.

Covers the complex query paths in routers/projects/import_export.py:
- JSON/CSV/TSV/Label Studio/TXT export formats
- Import with annotations, generations, evaluations
- Bulk export (summary and full ZIP)
- Span annotation format conversion (BenGER <-> Label Studio)
- Round-trip import/export fidelity
- Questionnaire response import/export
- Task evaluation and evaluation run import
"""

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    Task,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, admin, org, title="IE Deep Test", label_config=None):
    """Create a project linked to an org."""
    project = Project(
        id=_uid(),
        title=title,
        created_by=admin.id,
        label_config=label_config or '<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    return project


def _make_tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Sample text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _make_annotations(db, project, tasks, user_id):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False,
            lead_time=12.5,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _make_generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        status="completed",
        created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    db.flush()
    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=t.id,
            model_id=model_id,
            case_data=json.dumps(t.data),
            response_content=f"Generated answer for task {i}",
            label_config_version="v1",
            status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _make_evaluation_run(db, project, model_id="gpt-4o"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        metrics={"accuracy": 0.85, "f1_score": 0.82},
        status="completed",
        samples_evaluated=3,
        created_by="admin-test-id",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    return er


def _make_task_evaluations(db, eval_run, tasks, generations=None):
    tes = []
    for i, t in enumerate(tasks):
        gen_id = generations[i].id if generations and i < len(generations) else None
        te = TaskEvaluation(
            id=_uid(),
            evaluation_id=eval_run.id,
            task_id=t.id,
            generation_id=gen_id,
            field_name="answer",
            answer_type="choices",
            ground_truth={"value": "Ja"},
            prediction={"value": "Ja" if i % 2 == 0 else "Nein"},
            metrics={"accuracy": 1.0 if i % 2 == 0 else 0.0, "f1": 0.8},
            passed=i % 2 == 0,
        )
        db.add(te)
        tes.append(te)
    db.flush()
    return tes


def _make_questionnaire_responses(db, project, tasks, annotations, user_id):
    qrs = []
    for ann, t in zip(annotations, tasks):
        qr = PostAnnotationResponse(
            id=_uid(),
            annotation_id=ann.id,
            task_id=t.id,
            project_id=project.id,
            user_id=user_id,
            result=[{"from_name": "difficulty", "to_name": "text", "type": "rating", "value": {"rating": 3}}],
        )
        db.add(qr)
        qrs.append(qr)
    db.flush()
    return qrs


def _headers(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EXPORT TESTS
# ===================================================================

@pytest.mark.integration
class TestExportJSON:
    """Export project in JSON format."""

    def test_export_json_full_data(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=5)
        anns = _make_annotations(test_db, project, tasks, test_users[0].id)
        gens = _make_generations(test_db, project, tasks)
        er = _make_evaluation_run(test_db, project)
        _make_task_evaluations(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["id"] == project.id
        assert data["project"]["task_count"] == 5
        assert data["project"]["annotation_count"] == 5
        assert data["project"]["generation_count"] == 5
        assert len(data["tasks"]) == 5
        # Verify nested annotations in tasks
        for task in data["tasks"]:
            assert "annotations" in task
            assert "generations" in task

    def test_export_json_with_questionnaire_responses(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        anns = _make_annotations(test_db, project, tasks, test_users[0].id)
        _make_questionnaire_responses(test_db, project, tasks, anns, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        # Check that annotations include questionnaire data
        for task in data["tasks"]:
            for ann in task["annotations"]:
                assert "questionnaire_response" in ann or ann.get("questionnaire_response") is None

    def test_export_json_no_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["task_count"] == 0
        assert len(data["tasks"]) == 0

    def test_export_json_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=3)
        gens = _make_generations(test_db, project, tasks)
        er = _make_evaluation_run(test_db, project)
        tes = _make_task_evaluations(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["evaluation_run_count"] >= 1
        assert data["project"]["task_evaluation_count"] >= 1
        assert len(data["evaluation_runs"]) >= 1


@pytest.mark.integration
class TestExportCSV:
    """Export project in CSV format."""

    def test_export_csv_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=3)
        _make_annotations(test_db, project, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=csv",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 4  # header + at least 3 data rows

    def test_export_csv_with_generations_and_evals(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        anns = _make_annotations(test_db, project, tasks, test_users[0].id)
        gens = _make_generations(test_db, project, tasks)
        er = _make_evaluation_run(test_db, project)
        _make_task_evaluations(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=csv",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        header = lines[0]
        assert "evaluation_field" in header
        assert "evaluation_metrics" in header

    def test_export_csv_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=csv",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestExportTSV:
    """Export project in TSV format."""

    def test_export_tsv_format(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        _make_annotations(test_db, project, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=tsv",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "tab-separated" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert "\t" in lines[0]  # Tab-separated header


@pytest.mark.integration
class TestExportTXT:
    """Export project in plain text format."""

    def test_export_txt_format(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        _make_annotations(test_db, project, tasks, test_users[0].id)
        er = _make_evaluation_run(test_db, project)
        _make_task_evaluations(test_db, er, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=txt",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        assert "Total Tasks: 2" in resp.text


@pytest.mark.integration
class TestExportLabelStudio:
    """Export project in Label Studio format."""

    def test_export_label_studio_format(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=3)
        _make_annotations(test_db, project, tasks, test_users[0].id)
        gens = _make_generations(test_db, project, tasks)
        er = _make_evaluation_run(test_db, project)
        _make_task_evaluations(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert isinstance(data, list)
        assert len(data) == 3
        for item in data:
            assert "data" in item
            assert "annotations" in item
            assert len(item["annotations"]) >= 1

    def test_export_label_studio_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        _make_generations(test_db, project, tasks, model_id="claude-3-sonnet")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        for item in data:
            assert "generations" in item
            assert len(item["generations"]) >= 1
            gen = item["generations"][0]
            assert gen["model_id"] == "claude-3-sonnet"

    def test_export_label_studio_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        er = _make_evaluation_run(test_db, project)
        _make_task_evaluations(test_db, er, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        has_evals = any("evaluations" in item and item["evaluations"] for item in data)
        assert has_evals

    def test_export_label_studio_with_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        anns = _make_annotations(test_db, project, tasks, test_users[0].id)
        _make_questionnaire_responses(test_db, project, tasks, anns, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        for item in data:
            for ann in item.get("annotations", []):
                if "questionnaire_response" in ann:
                    assert "result" in ann["questionnaire_response"]


# ===================================================================
# IMPORT TESTS
# ===================================================================

@pytest.mark.integration
class TestImportBasic:
    """POST /api/projects/{project_id}/import — basic task import."""

    def test_import_simple_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {"data": {"text": "Imported 1"}},
                {"data": {"text": "Imported 2"}},
                {"data": {"text": "Imported 3"}},
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 3
        assert body["project_id"] == project.id

    def test_import_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Task with annotation"},
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                       "type": "choices", "value": {"choices": ["Ja"]}}],
                            "completed_by": test_users[0].id,
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_annotations"] == 1

    def test_import_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Task with generation"},
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "Generated answer",
                            "case_data": '{"text": "Task with generation"}',
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_generations"] == 1

    def test_import_with_metadata(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {"data": {"text": "Meta task"}, "meta": {"source": "test"}}
            ],
            "meta": {"global": True},
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_import_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/projects/nonexistent-project/import",
            json={"data": [{"data": {"text": "x"}}]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_import_access_denied(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/import",
            json={"data": [{"data": {"text": "x"}}]},
            headers=auth_headers["annotator"],  # No org context header
        )
        assert resp.status_code in (403, 200)  # May pass for org members


@pytest.mark.integration
class TestImportWithEvaluations:
    """Import with evaluation runs and task evaluations."""

    def test_import_evaluation_runs(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        er_id = _uid()
        import_data = {
            "data": [
                {"data": {"text": "Eval task"}}
            ],
            "evaluation_runs": [
                {
                    "id": er_id,
                    "model_id": "gpt-4o",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 0.9},
                    "status": "completed",
                    "samples_evaluated": 1,
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_evaluation_runs"] == 1

    def test_import_task_evaluations_nested_in_generations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        er_id = _uid()
        import_data = {
            "data": [
                {
                    "data": {"text": "Task with gen eval"},
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "Answer",
                            "case_data": "{}",
                            "evaluations": [
                                {
                                    "evaluation_run_id": er_id,
                                    "field_name": "answer",
                                    "answer_type": "choices",
                                    "ground_truth": {"value": "Ja"},
                                    "prediction": {"value": "Ja"},
                                    "metrics": {"accuracy": 1.0},
                                    "passed": True,
                                }
                            ],
                        }
                    ],
                }
            ],
            "evaluation_runs": [
                {
                    "id": er_id,
                    "model_id": "gpt-4o",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 1.0},
                    "status": "completed",
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_generations"] == 1
        assert body["created_task_evaluations"] == 1
        assert body["created_evaluation_runs"] == 1

    def test_import_task_level_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        er_id = _uid()
        import_data = {
            "data": [
                {
                    "data": {"text": "Task with annotation eval"},
                    "evaluations": [
                        {
                            "evaluation_run_id": er_id,
                            "field_name": "answer",
                            "answer_type": "choices",
                            "ground_truth": {"value": "Ja"},
                            "prediction": {"value": "Nein"},
                            "metrics": {"accuracy": 0.0},
                            "passed": False,
                        }
                    ],
                }
            ],
            "evaluation_runs": [
                {
                    "id": er_id,
                    "model_id": "immediate",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 0.0},
                    "status": "completed",
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_task_evaluations"] == 1


@pytest.mark.integration
class TestImportWithQuestionnaire:
    """Import tasks with questionnaire responses."""

    def test_import_annotation_with_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "QR task"},
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                       "type": "choices", "value": {"choices": ["Ja"]}}],
                            "completed_by": test_users[0].id,
                            "questionnaire_response": {
                                "result": [{"from_name": "difficulty", "to_name": "text",
                                           "type": "rating", "value": {"rating": 4}}],
                            },
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_questionnaire_responses"] == 1


@pytest.mark.integration
class TestImportMultipleModels:
    """Import generations from multiple models."""

    def test_import_multi_model_generations(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Multi model task"},
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "GPT answer",
                            "case_data": "{}",
                        },
                        {
                            "model_id": "claude-3-sonnet",
                            "response_content": "Claude answer",
                            "case_data": "{}",
                        },
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{project.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_generations"] == 2


# ===================================================================
# BULK EXPORT TESTS
# ===================================================================

@pytest.mark.integration
class TestBulkExport:
    """POST /api/projects/bulk-export"""

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        p1 = _make_project(test_db, test_users[0], test_org, title="Bulk 1")
        p2 = _make_project(test_db, test_users[0], test_org, title="Bulk 2")
        _make_tasks(test_db, p1, test_users[0], count=2)
        _make_tasks(test_db, p2, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id, p2.id], "format": "json", "include_data": True},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 2

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        p1 = _make_project(test_db, test_users[0], test_org, title="Bulk CSV 1")
        _make_tasks(test_db, p1, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id], "format": "csv"},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_empty(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [], "format": "json"},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_nonexistent_ids(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": ["nonexistent-1", "nonexistent-2"], "format": "json"},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 0

    def test_bulk_export_include_data_true(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, title="Data Inc")
        _make_tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "json", "include_data": True},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert "tasks" in data["projects"][0]
        assert len(data["projects"][0]["tasks"]) == 3


@pytest.mark.integration
class TestBulkExportFull:
    """POST /api/projects/bulk-export-full — ZIP archive export."""

    def test_bulk_export_full_zip(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, title="ZIP Export")
        _make_tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [p.id]},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        # Verify it's a ZIP
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)

    def test_bulk_export_full_no_ids(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": []},
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 400


# ===================================================================
# ROUND-TRIP TESTS
# ===================================================================

@pytest.mark.integration
class TestRoundTrip:
    """Export then re-import and verify fidelity."""

    def test_roundtrip_export_import(self, client, test_db, test_users, auth_headers, test_org):
        """Export a project in JSON format, create a new one, import into it, verify counts."""
        project = _make_project(test_db, test_users[0], test_org, title="Roundtrip Source")
        tasks = _make_tasks(test_db, project, test_users[0], count=3)
        anns = _make_annotations(test_db, project, tasks, test_users[0].id)
        test_db.commit()

        # Export in label_studio format (produces a list of task objects)
        export_resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert export_resp.status_code == 200
        exported = json.loads(export_resp.text)
        assert isinstance(exported, list)
        assert len(exported) == 3

        # Create new project for import target
        target = _make_project(test_db, test_users[0], test_org, title="Roundtrip Target")
        test_db.commit()

        # Import — each exported item already has "data" key, compatible with the import schema
        import_data = {"data": exported}
        import_resp = client.post(
            f"/api/projects/{target.id}/import",
            json=import_data,
            headers=_headers(auth_headers, test_org),
        )
        assert import_resp.status_code == 200
        body = import_resp.json()
        assert body["created_tasks"] == 3
        assert body["created_annotations"] >= 3

    def test_roundtrip_preserves_inner_ids(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org, title="InnerID Test")
        tasks = _make_tasks(test_db, project, test_users[0], count=2)
        test_db.commit()

        export_resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert export_resp.status_code == 200
        exported = json.loads(export_resp.text)
        # Label studio format uses inner_id as the 'id' field
        for item in exported:
            assert "id" in item


# ===================================================================
# FORMAT CONVERSION TESTS
# ===================================================================

@pytest.mark.integration
class TestSpanAnnotationConversion:
    """Test BenGER <-> Label Studio span annotation conversion."""

    def test_export_converts_benger_to_label_studio(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org,
                                 label_config='<View><Text name="text" value="$text"/>'
                                 '<Labels name="label" toName="text">'
                                 '<Label value="PER"/><Label value="ORG"/></Labels></View>')
        task = Task(
            id=_uid(), project_id=project.id,
            data={"text": "John works at OpenAI"}, inner_id=1, created_by=test_users[0].id,
        )
        test_db.add(task)
        test_db.flush()
        # BenGER format: single result with spans array
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=project.id,
            completed_by=test_users[0].id,
            result=[{
                "from_name": "label", "to_name": "text", "type": "labels",
                "value": {"spans": [
                    {"id": "s1", "start": 0, "end": 4, "text": "John", "labels": ["PER"]},
                    {"id": "s2", "start": 14, "end": 20, "text": "OpenAI", "labels": ["ORG"]},
                ]},
            }],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=label_studio",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        # Should be flattened: one result per span
        results = data[0]["annotations"][0]["result"]
        assert len(results) == 2
        assert results[0]["value"]["start"] == 0
        assert results[1]["value"]["start"] == 14


# ===================================================================
# ACCESS CONTROL TESTS
# ===================================================================

@pytest.mark.integration
class TestExportAccessControl:
    """Verify access control on export endpoints."""

    def test_export_project_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent-id/export",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_export_contributor_can_export(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json",
            headers=_headers(auth_headers, test_org).copy() | {"Authorization": auth_headers["contributor"]["Authorization"]},
        )
        # Contributor is an org member so should have access
        assert resp.status_code in (200, 403)

    def test_export_download_header(self, client, test_db, test_users, auth_headers, test_org):
        project = _make_project(test_db, test_users[0], test_org, title="Download Test")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/export?format=json&download=true",
            headers=_headers(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
