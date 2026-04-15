"""
Coverage push tests for import/export handler branches.

Targets specific uncovered branches in routers/projects/import_export.py:
- Export in txt format
- Export in tsv format
- Import with evaluation_runs, task-level evaluations, generations with evaluations
- Import with Label Studio format items (data+annotations+generations+evaluations)
- Bulk export in CSV format
- Bulk export full (ZIP) format
- Span conversion functions with edge cases
"""

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
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


def _setup_project_with_data(db, users, *, add_annotations=True, add_generations=True,
                              add_evaluations=True, add_questionnaire=True,
                              annotation_extras=None):
    """Create a fully populated project with all data types."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Coverage Test Org",
        slug=f"cov-org-{uuid.uuid4().hex[:8]}",
        display_name="Coverage Test Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Coverage Export Project",
        description="For testing export branches",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
        generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        evaluation_config={"default_temperature": 0.2},
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i == 0 else "CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    tasks = []
    annotations = []
    generations = []
    eval_runs = []
    task_evals = []
    qr_list = []

    for i in range(3):
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            project_id=pid,
            data={"text": f"Sample text {i}", "content": f"Content {i}"},
            meta={"tags": [f"tag-{i}"], "source": "test"},
            inner_id=i + 1,
            is_labeled=add_annotations,
        )
        db.add(task)
        tasks.append(task)
    db.commit()

    if add_annotations:
        for i, task in enumerate(tasks):
            ann_id = str(uuid.uuid4())
            extras = annotation_extras or {}
            ann = Annotation(
                id=ann_id,
                task_id=task.id,
                project_id=pid,
                result=[{"from_name": "text", "type": "textarea", "value": {"text": [f"answer {i}"]}}],
                completed_by=users[1].id,
                was_cancelled=False,
                ground_truth=(i == 0),
                lead_time=120.5 + i,
                draft={"partial": True} if i == 1 else None,
                prediction_scores={"score": 0.9} if i == 2 else None,
                **extras,
            )
            db.add(ann)
            annotations.append(ann)
        db.commit()

    if add_questionnaire and add_annotations:
        for ann in annotations[:1]:
            qr_id = str(uuid.uuid4())
            qr = PostAnnotationResponse(
                id=qr_id,
                annotation_id=ann.id,
                task_id=ann.task_id,
                project_id=pid,
                user_id=users[1].id,
                result={"difficulty": 3, "confidence": "high"},
            )
            db.add(qr)
            qr_list.append(qr)
        db.commit()

    if add_generations:
        for task in tasks:
            rg_id = str(uuid.uuid4())
            rg = ResponseGeneration(
                id=rg_id,
                task_id=task.id,
                project_id=pid,
                model_id="gpt-4o",
                config_id="default",
                status="completed",
                responses_generated=1,
                created_by=users[0].id,
                completed_at=datetime.utcnow(),
            )
            db.add(rg)
            db.commit()

            gen_id = str(uuid.uuid4())
            gen = Generation(
                id=gen_id,
                generation_id=rg_id,
                task_id=task.id,
                model_id="gpt-4o",
                case_data=json.dumps(task.data),
                response_content=f"Generated response for task {task.inner_id}",
                usage_stats={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                response_metadata={"model": "gpt-4o", "temperature": 0.2},
                status="completed",
                parse_status="success",
            )
            db.add(gen)
            generations.append(gen)
        db.commit()

    if add_evaluations:
        er_id = str(uuid.uuid4())
        er = EvaluationRun(
            id=er_id,
            project_id=pid,
            model_id="gpt-4o",
            evaluation_type_ids=["exact_match"],
            metrics={"accuracy": 0.85, "f1": 0.90},
            eval_metadata={"evaluation_type": "automated", "judge_models": {"config1": "gpt-4o"}},
            status="completed",
            samples_evaluated=3,
            has_sample_results=True,
            created_by=users[0].id,
        )
        db.add(er)
        eval_runs.append(er)
        db.commit()

        for j, task in enumerate(tasks):
            te_id = str(uuid.uuid4())
            gen_id = generations[j].id if generations else None
            te = TaskEvaluation(
                id=te_id,
                evaluation_id=er_id,
                task_id=task.id,
                generation_id=gen_id,
                field_name="config1:answer",
                answer_type="text",
                ground_truth={"value": f"answer {j}"},
                prediction={"value": f"predicted {j}"},
                metrics={"exact_match": 1.0 if j == 0 else 0.0, "llm_judge_custom": 0.8},
                passed=(j == 0),
                confidence_score=0.95 if j == 0 else 0.5,
                error_message=None,
                processing_time_ms=150 + j * 10,
            )
            db.add(te)
            task_evals.append(te)
        db.commit()

    return {
        "project": p,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "task_evals": task_evals,
        "questionnaire_responses": qr_list,
        "org": org,
    }


class TestExportLabelStudioFormat:
    """Test export in label_studio format with all optional fields populated."""

    def test_export_label_studio_with_annotations(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users, add_generations=True, add_evaluations=True)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        assert isinstance(content, list)
        assert len(content) == 3

        task0 = content[0]
        assert "data" in task0
        assert "annotations" in task0
        assert "meta" in task0
        assert task0["meta"].get("tags") is not None

    def test_export_label_studio_annotation_draft(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        # Find annotation with draft
        for task_item in content:
            for ann in task_item.get("annotations", []):
                if ann.get("draft"):
                    assert ann["draft"]["partial"] is True

    def test_export_label_studio_annotation_prediction(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        found_prediction = False
        for task_item in content:
            for ann in task_item.get("annotations", []):
                if ann.get("prediction"):
                    found_prediction = True
                    assert ann["prediction"]["score"] == 0.9
        assert found_prediction

    def test_export_label_studio_generations(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        found_gen = False
        for task_item in content:
            if "generations" in task_item:
                found_gen = True
                gen = task_item["generations"][0]
                assert gen["model_id"] == "gpt-4o"
                assert "response_content" in gen
        assert found_gen

    def test_export_label_studio_evaluations(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        found_eval = False
        for task_item in content:
            if "evaluations" in task_item and task_item["evaluations"]:
                found_eval = True
                ev = task_item["evaluations"][0]
                assert "metrics" in ev
                assert "confidence_score" in ev
        assert found_eval

    def test_export_label_studio_questionnaire(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=label_studio",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        content = json.loads(resp.text)
        found_qr = False
        for task_item in content:
            for ann in task_item.get("annotations", []):
                if ann.get("questionnaire_response"):
                    found_qr = True
                    assert "result" in ann["questionnaire_response"]
        assert found_qr


class TestExportTxtFormat:
    """Test export in txt format covering all txt branches."""

    def test_export_txt_with_annotations(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users, add_generations=False, add_evaluations=False)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=txt",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        text = resp.text
        assert "Coverage Export Project" in text
        assert "Annotations (" in text

    def test_export_txt_with_evaluations(self, client, test_users, test_db, auth_headers):
        """Txt format shows task-level evaluations. Create task evals without generation_id."""
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        # Add task-level evaluation (no generation_id) so it appears in txt export
        te_id = str(uuid.uuid4())
        te = TaskEvaluation(
            id=te_id,
            evaluation_id=data["eval_runs"][0].id,
            task_id=data["tasks"][0].id,
            generation_id=None,
            field_name="task_field",
            answer_type="text",
            ground_truth={"value": "gt"},
            prediction={"value": "pred"},
            metrics={"bleu": 0.7},
            passed=True,
        )
        test_db.add(te)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{pid}/export?format=txt",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        text = resp.text
        assert "Evaluations (" in text

    def test_export_txt_empty_project(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=txt",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "No annotations" in resp.text


class TestExportTsvFormat:
    """Test export in TSV format."""

    def test_export_tsv_with_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=tsv",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/tab-separated-values" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) > 1  # Header + data
        assert "task_id" in lines[0]

    def test_export_tsv_empty_tasks(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=tsv",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) > 1


class TestExportCsvFormat:
    """Test export in CSV format."""

    def test_export_csv_with_all_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=csv",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert "task_id" in lines[0]
        assert "questionnaire_response" in lines[0]

    def test_export_csv_empty_project(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=csv",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


class TestExportJsonFormat:
    """Test export in JSON format."""

    def test_export_json_with_evaluations(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert "evaluation_runs" in body
        assert len(body["evaluation_runs"]) > 0
        assert "tasks" in body

        # Verify nested evaluations in generations
        for task_data in body["tasks"]:
            for gen in task_data.get("generations", []):
                if gen.get("evaluations"):
                    assert "metrics" in gen["evaluations"][0]

    def test_export_json_with_questionnaire(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        found_qr = False
        for task_data in body["tasks"]:
            for ann in task_data.get("annotations", []):
                if ann.get("questionnaire_response"):
                    found_qr = True
        assert found_qr


class TestExportNoDownload:
    """Test export with download=false."""

    def test_export_json_no_download(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users, add_generations=False, add_evaluations=False)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/export?format=json&download=false",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "Content-Disposition" not in resp.headers


class TestExportNotFound:
    """Test export with non-existent project."""

    def test_export_project_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent-id/export?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestImportWithEvaluationRuns:
    """Test import with evaluation_runs and task_evaluations."""

    def test_import_with_evaluation_runs(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        import_data = {
            "data": [
                {
                    "data": {"text": "Imported task 1"},
                    "id": "task-001",
                    "meta": {"source": "import"},
                    "annotations": [
                        {
                            "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["answer"]}}],
                            "completed_by": test_users[1].id,
                            "lead_time": 45.5,
                            "draft": {"in_progress": True},
                            "was_cancelled": False,
                            "ground_truth": True,
                        }
                    ],
                    "generations": [
                        {
                            "id": "gen-old-1",
                            "model_id": "gpt-4o",
                            "response_content": "Generated content",
                            "case_data": "{\"text\": \"test\"}",
                            "response_metadata": {"temperature": 0.7},
                            "evaluations": [
                                {
                                    "evaluation_run_id": "er-old-1",
                                    "field_name": "answer",
                                    "answer_type": "text",
                                    "ground_truth": {"value": "answer"},
                                    "prediction": {"value": "predicted"},
                                    "metrics": {"exact_match": 0.0},
                                    "passed": False,
                                    "confidence_score": 0.3,
                                    "processing_time_ms": 200,
                                }
                            ],
                        }
                    ],
                    "evaluations": [
                        {
                            "evaluation_run_id": "er-old-1",
                            "field_name": "task_level_field",
                            "answer_type": "text",
                            "ground_truth": {"value": "gt"},
                            "prediction": {"value": "pred"},
                            "metrics": {"bleu": 0.6},
                            "passed": True,
                            "confidence_score": 0.85,
                            "processing_time_ms": 100,
                        }
                    ],
                }
            ],
            "meta": {"batch": "test-import"},
            "evaluation_runs": [
                {
                    "id": "er-old-1",
                    "model_id": "gpt-4o",
                    "evaluation_type_ids": ["exact_match"],
                    "metrics": {"accuracy": 0.75},
                    "eval_metadata": {"type": "automated"},
                    "status": "completed",
                    "samples_evaluated": 1,
                }
            ],
        }

        with patch("report_service.update_report_data_section"):
            resp = client.post(
                f"/api/projects/{pid}/import",
                json=import_data,
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_annotations"] == 1
        assert body["created_generations"] == 1
        assert body["created_evaluation_runs"] == 1
        assert body["created_task_evaluations"] >= 2

    def test_import_with_integer_task_id(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        import_data = {
            "data": [
                {
                    "data": {"text": "Task with int id"},
                    "id": 42,
                }
            ],
        }
        with patch("report_service.update_report_data_section"):
            resp = client.post(
                f"/api/projects/{pid}/import",
                json=import_data,
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200

    def test_import_with_questionnaire_response(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_annotations=False, add_generations=False,
            add_evaluations=False, add_questionnaire=False
        )
        pid = data["project"].id

        import_data = {
            "data": [
                {
                    "data": {"text": "task with qr"},
                    "annotations": [
                        {
                            "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["a"]}}],
                            "completed_by": test_users[1].id,
                            "questionnaire_response": {
                                "result": {"difficulty": 3},
                            },
                        }
                    ],
                }
            ],
        }
        with patch("report_service.update_report_data_section"):
            resp = client.post(
                f"/api/projects/{pid}/import",
                json=import_data,
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200
        assert resp.json()["created_questionnaire_responses"] == 1


class TestImportNotFound:
    """Test import with non-existent project."""

    def test_import_project_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/nonexistent/import",
            json={"data": [{"text": "test"}]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestBulkExportCsv:
    """Test bulk export in CSV format."""

    def test_bulk_export_csv(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "csv", "include_data": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_json_with_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "json", "include_data": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_bulk_export_no_include_data(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "json", "include_data": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for proj in body["projects"]:
            assert "tasks" not in proj

    def test_bulk_export_unsupported_format(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(
            test_db, test_users, add_generations=False, add_evaluations=False
        )
        pid = data["project"].id

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [pid], "format": "xml"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_bulk_export_nonexistent_project(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": ["nonexistent-id"], "format": "json"},
            headers=auth_headers["admin"],
        )
        # Should return valid response with empty projects list
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert body["projects"] == []


class TestBulkExportFull:
    """Test full project export (ZIP format)."""

    def test_bulk_export_full_zip(self, client, test_users, test_db, auth_headers):
        data = _setup_project_with_data(test_db, test_users)
        pid = data["project"].id

        with patch("routers.projects.helpers.get_comprehensive_project_data") as mock_export:
            mock_export.return_value = {
                "format_version": "2.0.0",
                "project": {"id": pid, "title": "Test"},
                "tasks": [],
            }
            resp = client.post(
                "/api/projects/bulk-export-full",
                json={"project_ids": [pid]},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200
        assert "application/zip" in resp.headers.get("content-type", "")

    def test_bulk_export_full_no_ids(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_bulk_export_full_no_accessible(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": ["nonexistent"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestSpanConversion:
    """Test span annotation conversion functions."""

    def test_convert_to_label_studio_empty(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format(None) is None
        assert convert_to_label_studio_format([]) == []
        assert convert_to_label_studio_format("not a list") == "not a list"

    def test_convert_to_label_studio_with_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "text": "hello", "labels": ["NER"]},
                        {"id": "s2", "start": 10, "end": 15, "text": "world", "labels": ["NER"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_convert_to_label_studio_no_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"other": "data"},
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0] == results[0]

    def test_convert_to_label_studio_non_span_type(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"type": "choices", "from_name": "choice", "value": {"choices": ["A"]}},
        ]
        output = convert_to_label_studio_format(results)
        assert output == results

    def test_convert_from_label_studio_empty(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format(None) is None
        assert convert_from_label_studio_format([]) == []

    def test_convert_from_label_studio_with_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "text": "hello", "labels": ["NER"]},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 10, "end": 15, "text": "world", "labels": ["NER"]},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert len(output[0]["value"]["spans"]) == 2

    def test_convert_from_label_studio_already_benger(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"spans": [{"id": "s1", "start": 0, "end": 5}]},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert "spans" in output[0]["value"]

    def test_convert_from_label_studio_other_labels(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"other": "data"},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1

    def test_convert_from_label_studio_non_labels(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"type": "choices", "value": {"choices": ["A"]}},
        ]
        output = convert_from_label_studio_format(results)
        assert output == results
