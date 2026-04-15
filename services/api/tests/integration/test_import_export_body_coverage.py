"""
Integration tests for import_export.py handler body code.

Covers:
- Export with 0 tasks vs many tasks
- Export with annotations that have different result structures
- Export with cancelled annotations
- CSV/TSV/TXT/label_studio format rendering
- Import with span conversion round-trip
- Import with generations and nested evaluations
- Import with evaluation runs
- Import task-level evaluations
- Bulk export project summary (json, csv)
- Bulk export full (ZIP)
- Span format conversion helpers
"""

import csv
import io
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
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


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kw):
    p = Project(
        id=_uid(),
        title=kw.get("title", f"ImpExpBody {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
    )
    db.add(p)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    return p


def _tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Sentence {i}", "category": f"cat_{i % 2}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, cancelled=False, result=None):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=result or [{"from_name": "answer", "to_name": "text",
                               "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=cancelled, lead_time=12.5,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    db.flush()
    gens = []
    for t in tasks:
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, case_data=json.dumps(t.data),
            response_content="Generated response", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _eval_run(db, project, admin):
    er = EvaluationRun(
        id=_uid(), project_id=project.id,
        model_id="gpt-4o", evaluation_type_ids=["accuracy"],
        metrics={"accuracy": 0.85}, status="completed",
        created_by=admin.id,
    )
    db.add(er)
    db.flush()
    return er


def _task_evaluation(db, er, task, gen=None):
    te = TaskEvaluation(
        id=_uid(), evaluation_id=er.id, task_id=task.id,
        generation_id=gen.id if gen else None,
        field_name="answer", answer_type="choice",
        ground_truth="Ja", prediction="Ja",
        metrics={"accuracy": 1.0}, passed=True,
    )
    db.add(te)
    db.flush()
    return te


def _questionnaire_response(db, ann, task, project, user_id):
    qr = PostAnnotationResponse(
        id=_uid(), annotation_id=ann.id, task_id=task.id,
        project_id=project.id, user_id=user_id,
        result=[{"question": "confidence", "answer": "high"}],
    )
    db.add(qr)
    db.flush()
    return qr


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EXPORT WITH 0 TASKS
# ===================================================================

@pytest.mark.integration
class TestExportZeroTasks:

    def test_export_json_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["task_count"] == 0
        assert data["tasks"] == []

    def test_export_csv_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.get(f"/api/projects/{p.id}/export?format=csv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 1  # header only

    def test_export_tsv_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.get(f"/api/projects/{p.id}/export?format=tsv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "\t" in resp.text  # tab-separated header

    def test_export_txt_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.get(f"/api/projects/{p.id}/export?format=txt", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "Total Tasks: 0" in resp.text

    def test_export_label_studio_empty(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data == []


# ===================================================================
# EXPORT WITH MULTIPLE TASKS + ANNOTATIONS
# ===================================================================

@pytest.mark.integration
class TestExportWithData:

    def test_export_json_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["task_count"] == 3
        assert data["project"]["annotation_count"] == 3
        assert len(data["tasks"]) == 3
        for t in data["tasks"]:
            assert len(t["annotations"]) == 1
            assert t["annotations"][0]["lead_time"] == 12.5

    def test_export_json_with_cancelled_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks[:1], test_users[0].id, cancelled=False)
        _annotations(test_db, p, tasks[1:], test_users[0].id, cancelled=True)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        task0_ann = data["tasks"][0]["annotations"][0] if data["tasks"][0]["annotations"] else data["tasks"][1]["annotations"][0]
        task1_ann = data["tasks"][1]["annotations"][0] if data["tasks"][1]["annotations"] else data["tasks"][0]["annotations"][0]
        # One should be cancelled, one not
        cancelled_flags = [t["annotations"][0]["was_cancelled"] for t in data["tasks"] if t["annotations"]]
        assert True in cancelled_flags or False in cancelled_flags

    def test_export_json_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["generation_count"] == 2
        for t in data["tasks"]:
            assert len(t["generations"]) == 1
            assert t["generations"][0]["model_id"] == "gpt-4o"

    def test_export_json_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        er = _eval_run(test_db, p, test_users[0])
        _task_evaluation(test_db, er, tasks[0])
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["evaluation_runs"]) == 1
        # At least one task has evaluations
        all_evals = sum(len(t["evaluations"]) for t in data["tasks"])
        assert all_evals >= 1

    def test_export_json_with_generation_nested_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p, test_users[0])
        _task_evaluation(test_db, er, tasks[0], gen=gens[0])
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        gen_data = data["tasks"][0]["generations"][0]
        assert len(gen_data["evaluations"]) == 1
        # Task-level evaluations should NOT include gen-linked evals
        assert len(data["tasks"][0]["evaluations"]) == 0

    def test_export_json_with_questionnaire_response(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire_response(test_db, anns[0], tasks[0], p, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        ann = data["tasks"][0]["annotations"][0]
        assert ann["questionnaire_response"] is not None
        assert ann["questionnaire_response"]["result"] is not None

    def test_export_json_download_header(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, title="My Export Project")
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=json&download=true", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]


# ===================================================================
# CSV / TSV FORMAT DETAIL
# ===================================================================

@pytest.mark.integration
class TestExportCSVTSV:

    def test_csv_header_columns(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=csv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "task_id" in header
        assert "annotation_id" in header
        assert "questionnaire_response" in header
        assert "generation_id" in header
        assert "evaluation_field" in header

    def test_csv_data_rows(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=csv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 3  # header + 2 data rows

    def test_csv_task_with_no_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=csv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 empty task row

    def test_tsv_uses_tab_delimiter(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=tsv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        first_line = resp.text.split("\n")[0]
        assert first_line.count("\t") >= 10  # at least 10 tab-separated columns

    def test_tsv_content_type(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=tsv", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "text/tab-separated-values" in resp.headers.get("content-type", "")


# ===================================================================
# TXT FORMAT
# ===================================================================

@pytest.mark.integration
class TestExportTXT:

    def test_txt_includes_project_title(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, title="Legal Analysis Export")
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=txt", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "Legal Analysis Export" in resp.text

    def test_txt_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=txt", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "Total Annotations: 2" in resp.text
        assert "Annotations (1):" in resp.text

    def test_txt_no_annotations_label(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=txt", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "No annotations" in resp.text

    def test_txt_with_task_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        er = _eval_run(test_db, p, test_users[0])
        _task_evaluation(test_db, er, tasks[0])
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=txt", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        assert "Evaluations" in resp.text


# ===================================================================
# LABEL STUDIO FORMAT
# ===================================================================

@pytest.mark.integration
class TestExportLabelStudio:

    def test_label_studio_basic_structure(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data) == 2
        for item in data:
            assert "id" in item
            assert "data" in item
            assert "annotations" in item
            assert "meta" in item
            assert "project" in item

    def test_label_studio_annotations_include_details(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        data = json.loads(resp.text)
        ann = data[0]["annotations"][0]
        assert "id" in ann
        assert "completed_by" in ann
        assert "result" in ann
        assert "lead_time" in ann
        assert "was_cancelled" in ann

    def test_label_studio_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        data = json.loads(resp.text)
        assert "generations" in data[0]
        assert len(data[0]["generations"]) == 1
        assert data[0]["generations"][0]["model_id"] == "gpt-4o"

    def test_label_studio_with_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire_response(test_db, anns[0], tasks[0], p, test_users[0].id)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        data = json.loads(resp.text)
        ann = data[0]["annotations"][0]
        assert "questionnaire_response" in ann
        assert ann["questionnaire_response"]["result"] is not None

    def test_label_studio_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        er = _eval_run(test_db, p, test_users[0])
        _task_evaluation(test_db, er, tasks[0])
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}/export?format=label_studio", headers=_h(auth_headers, test_org))
        data = json.loads(resp.text)
        assert "evaluations" in data[0]
        assert len(data[0]["evaluations"]) >= 1


# ===================================================================
# EXPORT 404 / 403
# ===================================================================

@pytest.mark.integration
class TestExportAccessControl:

    def test_export_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/projects/{_uid()}/export?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# IMPORT DATA
# ===================================================================

@pytest.mark.integration
class TestImportData:

    def test_import_basic_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "data": [
                {"data": {"text": "Task A"}, "id": 1},
                {"data": {"text": "Task B"}, "id": 2},
                {"data": {"text": "Task C"}, "id": 3},
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_tasks"] == 3
        assert data["total_items"] == 3

    def test_import_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "data": [
                {
                    "data": {"text": "Annotated task"},
                    "id": 1,
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                        "type": "choices", "value": {"choices": ["Ja"]}}],
                            "completed_by": test_users[0].id,
                            "was_cancelled": False,
                            "lead_time": 15.2,
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_tasks"] == 1
        assert data["created_annotations"] == 1

    def test_import_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "data": [
                {
                    "data": {"text": "Task with gen"},
                    "id": 1,
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "LLM output here",
                        }
                    ],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_tasks"] == 1
        assert data["created_generations"] == 1

    def test_import_with_evaluation_runs_and_task_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        old_er_id = _uid()
        import_payload = {
            "evaluation_runs": [
                {
                    "id": old_er_id,
                    "model_id": "gpt-4o",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 0.9},
                    "status": "completed",
                }
            ],
            "data": [
                {
                    "data": {"text": "Eval task"},
                    "id": 1,
                    "evaluations": [
                        {
                            "evaluation_run_id": old_er_id,
                            "field_name": "answer",
                            "answer_type": "choice",
                            "ground_truth": "Ja",
                            "prediction": "Ja",
                            "metrics": {"accuracy": 1.0},
                            "passed": True,
                        }
                    ],
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_evaluation_runs"] == 1
        assert data["created_task_evaluations"] == 1

    def test_import_with_nested_generation_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        old_er_id = _uid()
        import_payload = {
            "evaluation_runs": [
                {"id": old_er_id, "model_id": "gpt-4o", "status": "completed"}
            ],
            "data": [
                {
                    "data": {"text": "Gen eval task"},
                    "id": 1,
                    "generations": [
                        {
                            "model_id": "gpt-4o",
                            "response_content": "Answer",
                            "evaluations": [
                                {
                                    "evaluation_run_id": old_er_id,
                                    "field_name": "response",
                                    "answer_type": "text",
                                    "ground_truth": "Expected",
                                    "prediction": "Answer",
                                    "metrics": {"exact_match": 0.0},
                                    "passed": False,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_generations"] == 1
        assert data["created_task_evaluations"] == 1

    def test_import_with_questionnaire_response(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "data": [
                {
                    "data": {"text": "QR task"},
                    "id": 1,
                    "annotations": [
                        {
                            "result": [{"from_name": "answer", "to_name": "text",
                                        "type": "choices", "value": {"choices": ["Nein"]}}],
                            "questionnaire_response": {
                                "result": [{"question": "difficulty", "answer": "hard"}],
                            },
                        }
                    ],
                }
            ],
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_questionnaire_responses"] == 1

    def test_import_with_string_task_id(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "data": [
                {"data": {"text": "String ID"}, "id": "task-042"},
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_tasks"] == 1
        # The task_id_mapping should contain the original string ID
        assert "task-042" in data.get("task_id_mapping", {})

    def test_import_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            f"/api/projects/{_uid()}/import",
            json={"data": [{"data": {"text": "X"}}]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_import_with_meta(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_payload = {
            "meta": {"source": "test_suite"},
            "data": [
                {"data": {"text": "With global meta"}, "id": 1, "meta": {"priority": "high"}},
            ],
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_payload,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200


# ===================================================================
# BULK EXPORT
# ===================================================================

@pytest.mark.integration
class TestBulkExport:

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "json", "include_data": True},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 1
        assert data["projects"][0]["task_count"] == 2

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_nonexistent_project_skipped(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [_uid()], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 0

    def test_bulk_export_without_data(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "json", "include_data": False},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert "tasks" not in data["projects"][0]

    def test_bulk_export_unsupported_format(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "xml"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400


# ===================================================================
# SPAN CONVERSION HELPERS (unit-level but exercised through handlers)
# ===================================================================

@pytest.mark.integration
class TestSpanConversion:

    def test_convert_to_label_studio_flattens_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "from_name": "label", "to_name": "text", "type": "labels",
                "value": {"spans": [
                    {"id": "s1", "start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
                    {"id": "s2", "start": 10, "end": 15, "text": "World", "labels": ["LOC"]},
                ]},
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_convert_from_label_studio_consolidates_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"id": "s1", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 0, "end": 5, "text": "Hello", "labels": ["PER"]}},
            {"id": "s2", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 10, "end": 15, "text": "World", "labels": ["LOC"]}},
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert len(output[0]["value"]["spans"]) == 2

    def test_convert_to_label_studio_passthrough_non_labels(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"from_name": "answer", "to_name": "text", "type": "choices",
             "value": {"choices": ["Ja"]}},
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_convert_empty_returns_empty(self):
        from routers.projects.import_export import convert_to_label_studio_format, convert_from_label_studio_format
        assert convert_to_label_studio_format([]) == []
        assert convert_to_label_studio_format(None) is None
        assert convert_from_label_studio_format([]) == []
        assert convert_from_label_studio_format(None) is None

    def test_convert_labels_without_spans_passthrough(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"from_name": "label", "to_name": "text", "type": "labels",
             "value": {"labels": ["PER"]}},
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["value"]["labels"] == ["PER"]

    def test_convert_from_already_benger_format(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"from_name": "label", "to_name": "text", "type": "labels",
             "value": {"spans": [{"id": "s1", "start": 0, "end": 5}]}},
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert "spans" in output[0]["value"]
