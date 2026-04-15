"""
Integration tests for project export in ALL formats (json, csv, tsv, txt, label_studio).

Targets: routers/projects/import_export.py — export handler body, CSV/TSV/TXT/LS branches
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _make_project(db, admin, org, *, with_annotations=True, with_generations=True,
                   with_questionnaire=True, with_evaluations=True, num_tasks=3):
    """Create a fully-populated project for export testing."""
    project = Project(
        id=_uid(),
        title="Export Test Project",
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
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Export task text #{i}", "question": f"Q{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    annotations = []
    if with_annotations:
        for t in tasks:
            ann = Annotation(
                id=_uid(), task_id=t.id, project_id=project.id,
                completed_by=admin.id,
                result=[{"from_name": "answer", "to_name": "text", "type": "choices",
                         "value": {"choices": ["Ja"]}}],
                was_cancelled=False,
            )
            db.add(ann)
            annotations.append(ann)
        db.flush()

    qr_list = []
    if with_questionnaire and annotations:
        for ann in annotations:
            qr = PostAnnotationResponse(
                id=_uid(),
                annotation_id=ann.id,
                task_id=ann.task_id,
                project_id=project.id,
                user_id=admin.id,
                result=[{"from_name": "q1", "value": {"choices": ["Good"]}}],
            )
            db.add(qr)
            qr_list.append(qr)
        db.flush()

    generations = []
    if with_generations:
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            status="completed",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(rg)
        db.flush()

        for t in tasks:
            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=t.id,
                model_id="gpt-4o",
                case_data=json.dumps({"text": "case data"}),
                response_content="Generated answer",
                status="completed",
            )
            db.add(gen)
            generations.append(gen)
        db.flush()

    eval_runs = []
    task_evals = []
    if with_evaluations:
        er = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"accuracy": 0.9},
            status="completed",
            samples_evaluated=num_tasks,
            created_by=admin.id,
        )
        db.add(er)
        db.flush()
        eval_runs.append(er)

        for i, t in enumerate(tasks):
            te = TaskEvaluation(
                id=_uid(),
                evaluation_id=er.id,
                task_id=t.id,
                generation_id=generations[i].id if generations else None,
                field_name="answer",
                answer_type="choices",
                ground_truth="Ja",
                prediction="Ja",
                metrics={"accuracy": 1.0},
                passed=True,
            )
            db.add(te)
            task_evals.append(te)
        db.flush()

    db.commit()
    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "task_evals": task_evals,
        "questionnaire_responses": qr_list,
    }


@pytest.mark.integration
class TestExportJSON:
    def test_export_json_structure(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert "project" in body
        assert "tasks" in body
        assert "evaluation_runs" in body
        assert body["project"]["task_count"] == 3
        assert body["project"]["annotation_count"] == 3
        assert body["project"]["generation_count"] == 3

    def test_export_json_task_has_annotations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for task in body["tasks"]:
            assert "annotations" in task
            assert "generations" in task
            assert "evaluations" in task

    def test_export_json_has_questionnaire_response(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        # At least one annotation should have a questionnaire_response
        has_qr = any(
            ann.get("questionnaire_response") is not None
            for task in body["tasks"]
            for ann in task.get("annotations", [])
        )
        assert has_qr

    def test_export_json_has_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert len(body["evaluation_runs"]) >= 1

    def test_export_json_no_download(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json&download=false",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        # No Content-Disposition header when download=false
        assert "Content-Disposition" not in resp.headers

    def test_export_json_download(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json&download=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]


@pytest.mark.integration
class TestExportCSV:
    def test_export_csv_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least one data row

    def test_export_csv_header_columns(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        header = resp.text.strip().split("\n")[0]
        assert "task_id" in header
        assert "annotation_id" in header
        assert "generation_id" in header

    def test_export_csv_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(
            test_db, test_users[0], test_org, num_tasks=0,
            with_annotations=False, with_generations=False,
            with_questionnaire=False, with_evaluations=False,
        )
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_csv_tasks_no_annotations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(
            test_db, test_users[0], test_org,
            with_annotations=False, with_generations=False,
            with_questionnaire=False, with_evaluations=False,
        )
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        # Header + 3 tasks (with empty annotation/generation columns)
        assert len(lines) >= 4


@pytest.mark.integration
class TestExportTSV:
    def test_export_tsv_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=tsv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "tab-separated" in resp.headers.get("content-type", "")

    def test_export_tsv_has_tabs(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=tsv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        header = resp.text.strip().split("\n")[0]
        assert "\t" in header

    def test_export_tsv_header_columns(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=tsv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        header = resp.text.strip().split("\n")[0]
        assert "task_id" in header
        assert "evaluation_field" in header

    def test_export_tsv_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(
            test_db, test_users[0], test_org, num_tasks=0,
            with_annotations=False, with_generations=False,
            with_questionnaire=False, with_evaluations=False,
        )
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=tsv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestExportTXT:
    def test_export_txt_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=txt",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_export_txt_has_project_info(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=txt",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "Project:" in resp.text
        assert "Export Test Project" in resp.text
        assert "Total Tasks:" in resp.text

    def test_export_txt_has_annotations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=txt",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "Annotations" in resp.text

    def test_export_txt_has_task_data(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=txt",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert "Task" in resp.text
        assert "Data:" in resp.text

    def test_export_txt_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(
            test_db, test_users[0], test_org, num_tasks=0,
            with_annotations=False, with_generations=False,
            with_questionnaire=False, with_evaluations=False,
        )
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=txt",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestExportLabelStudio:
    def test_export_label_studio_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert isinstance(body, list)
        assert len(body) == 3

    def test_export_label_studio_task_structure(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        task = body[0]
        assert "data" in task
        assert "annotations" in task
        assert "predictions" in task
        assert "meta" in task
        assert "is_labeled" in task

    def test_export_label_studio_annotations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for task in body:
            assert len(task["annotations"]) >= 1
            ann = task["annotations"][0]
            assert "completed_by" in ann
            assert "result" in ann

    def test_export_label_studio_generations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for task in body:
            assert "generations" in task
            assert len(task["generations"]) >= 1
            gen = task["generations"][0]
            assert "model_id" in gen
            assert "response_content" in gen

    def test_export_label_studio_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        has_evaluations = any("evaluations" in task for task in body)
        assert has_evaluations

    def test_export_label_studio_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        has_qr = any(
            ann.get("questionnaire_response") is not None
            for task in body
            for ann in task.get("annotations", [])
        )
        assert has_qr

    def test_export_label_studio_empty(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(
            test_db, test_users[0], test_org, num_tasks=0,
            with_annotations=False, with_generations=False,
            with_questionnaire=False, with_evaluations=False,
        )
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert body == []


@pytest.mark.integration
class TestExportAccess:
    def test_export_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent-id/export?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)

    def test_export_contributor_access(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_project(test_db, test_users[0], test_org, with_generations=False,
                              with_questionnaire=False, with_evaluations=False)
        resp = client.get(
            f"/api/projects/{data['project'].id}/export?format=json",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
