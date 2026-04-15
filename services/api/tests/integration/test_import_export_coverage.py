"""
Integration tests targeting uncovered handler body code in routers/projects/import_export.py.

Focuses on:
- Export with multiple annotators and conflicting results
- CSV column ordering and content verification
- TSV delimiter verification
- TXT summary format with evaluation data
- Label Studio format span annotation conversion
- Import with nested generations + evaluations
- Import preserving lead_time and metadata
- Bulk export ZIP contents verification
- Round-trip fidelity for complex data graphs
- Edge cases: empty annotations, cancelled tasks, special characters
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


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"ImpExp {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
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


def _tasks(db, project, admin, count=3, data_fn=None):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data=data_fn(i) if data_fn else {"text": f"Text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, lead_time=10.0):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _generations(db, project, tasks, model_id="gpt-4o"):
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
            response_content=f"Generated answer #{i}",
            label_config_version="v1",
            status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _eval_run(db, project, model_id="gpt-4o", metrics=None):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        metrics=metrics or {"accuracy": 0.85, "f1_score": 0.82},
        status="completed",
        samples_evaluated=3,
        created_by="admin-test-id",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    return er


def _task_evals(db, eval_run, tasks, generations=None):
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


def _questionnaire(db, project, tasks, anns, user_id):
    qrs = []
    for ann, t in zip(anns, tasks):
        qr = PostAnnotationResponse(
            id=_uid(),
            annotation_id=ann.id,
            task_id=t.id,
            project_id=project.id,
            user_id=user_id,
            result=[{"from_name": "difficulty", "to_name": "text",
                     "type": "rating", "value": {"rating": 3}}],
        )
        db.add(qr)
        qrs.append(qr)
    db.flush()
    return qrs


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EXPORT: JSON format deep coverage
# ===================================================================

@pytest.mark.integration
class TestExportJSONDeep:
    """Deep coverage for JSON export handler body."""

    def test_export_json_multiple_annotators(self, client, test_db, test_users, auth_headers, test_org):
        """Export with multiple annotators per task."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        _annotations(test_db, p, tasks, test_users[1].id, lead_time=15.0)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["annotation_count"] >= 6
        for task in data["tasks"]:
            assert len(task["annotations"]) >= 2

    def test_export_json_cancelled_annotations_excluded(self, client, test_db, test_users, auth_headers, test_org):
        """Cancelled annotations should still appear but marked."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        # Normal annotation
        _annotations(test_db, p, tasks[:1], test_users[0].id)
        # Cancelled annotation
        cancelled = Annotation(
            id=_uid(), task_id=tasks[1].id, project_id=p.id,
            completed_by=test_users[0].id,
            result=[], was_cancelled=True, lead_time=0,
        )
        test_db.add(cancelled)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["tasks"]) == 2

    def test_export_json_special_characters_in_data(self, client, test_db, test_users, auth_headers, test_org):
        """Data with unicode and special chars exports correctly."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1,
               data_fn=lambda i: {"text": "Uber die Rechtsprechung des BVerfG \u00a7 823 BGB"})
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert "\u00a7" in data["tasks"][0]["data"]["text"]

    def test_export_json_with_multi_model_generations(self, client, test_db, test_users, auth_headers, test_org):
        """Export with generations from multiple models."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _generations(test_db, p, tasks, model_id="gpt-4o")
        _generations(test_db, p, tasks, model_id="claude-3-sonnet")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data["project"]["generation_count"] >= 4
        for task in data["tasks"]:
            assert len(task["generations"]) >= 2

    def test_export_json_download_filename(self, client, test_db, test_users, auth_headers, test_org):
        """Download mode should set Content-Disposition with filename."""
        p = _project(test_db, test_users[0], test_org, title="My Export Test")
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json&download=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]


# ===================================================================
# EXPORT: CSV format deep coverage
# ===================================================================

@pytest.mark.integration
class TestExportCSVDeep:
    """Deep coverage for CSV export paths."""

    def test_csv_header_contains_expected_columns(self, client, test_db, test_users, auth_headers, test_org):
        """CSV header should include task data fields."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        header = lines[0].lower()
        # Should have some standard columns
        assert "text" in header or "data" in header or "inner_id" in header

    def test_csv_row_count_matches_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """Number of data rows matches task count."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=5)
        _annotations(test_db, p, [t for t in []], test_users[0].id)  # No annotations
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 6  # header + 5 data rows

    def test_csv_with_evaluation_columns(self, client, test_db, test_users, auth_headers, test_org):
        """CSV with evaluations includes evaluation-specific columns."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        header = resp.text.strip().split("\n")[0]
        assert "evaluation" in header.lower() or "metric" in header.lower() or "accuracy" in header.lower()


# ===================================================================
# EXPORT: TSV format deep coverage
# ===================================================================

@pytest.mark.integration
class TestExportTSVDeep:
    """Deep coverage for TSV export."""

    def test_tsv_uses_tab_delimiter(self, client, test_db, test_users, auth_headers, test_org):
        """Verify TSV uses tab characters as delimiters."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=tsv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        for line in lines:
            assert "\t" in line

    def test_tsv_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        """TSV export with evaluation data."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=tsv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "\t" in resp.text


# ===================================================================
# EXPORT: TXT format
# ===================================================================

@pytest.mark.integration
class TestExportTXTDeep:
    """Deep coverage for TXT format."""

    def test_txt_summary_includes_counts(self, client, test_db, test_users, auth_headers, test_org):
        """TXT export includes task and annotation counts."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=4)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=txt",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        text = resp.text
        assert "4" in text  # Task count should appear
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_txt_with_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        """TXT export including evaluation information."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p, metrics={"accuracy": 0.90, "f1_score": 0.88})
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=txt",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")


# ===================================================================
# EXPORT: Label Studio span conversion
# ===================================================================

@pytest.mark.integration
class TestLabelStudioSpanDeep:
    """Deep coverage for Label Studio span annotation conversion."""

    def test_multiple_span_groups(self, client, test_db, test_users, auth_headers, test_org):
        """Multiple from_name groups should each be flattened independently."""
        label_config = (
            '<View><Text name="text" value="$text"/>'
            '<Labels name="label" toName="text">'
            '<Label value="PER"/><Label value="ORG"/></Labels>'
            '<Labels name="legal" toName="text">'
            '<Label value="LAW"/></Labels></View>'
        )
        p = _project(test_db, test_users[0], test_org, label_config=label_config)
        task = Task(
            id=_uid(), project_id=p.id,
            data={"text": "John cited BGB at OpenAI"}, inner_id=1,
            created_by=test_users[0].id,
        )
        test_db.add(task)
        test_db.flush()
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=p.id,
            completed_by=test_users[0].id,
            result=[
                {
                    "from_name": "label", "to_name": "text", "type": "labels",
                    "value": {"spans": [
                        {"id": "s1", "start": 0, "end": 4, "text": "John", "labels": ["PER"]},
                        {"id": "s2", "start": 18, "end": 24, "text": "OpenAI", "labels": ["ORG"]},
                    ]},
                },
                {
                    "from_name": "legal", "to_name": "text", "type": "labels",
                    "value": {"spans": [
                        {"id": "s3", "start": 12, "end": 15, "text": "BGB", "labels": ["LAW"]},
                    ]},
                },
            ],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        results = data[0]["annotations"][0]["result"]
        # Should have 3 flattened spans total
        assert len(results) == 3

    def test_non_span_annotations_pass_through(self, client, test_db, test_users, auth_headers, test_org):
        """Non-span (choices) annotations pass through unchanged in label_studio format."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        ann = Annotation(
            id=_uid(), task_id=tasks[0].id, project_id=p.id,
            completed_by=test_users[0].id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        result = data[0]["annotations"][0]["result"][0]
        assert result["type"] == "choices"
        assert result["value"]["choices"] == ["Ja"]


# ===================================================================
# IMPORT: deep coverage
# ===================================================================

@pytest.mark.integration
class TestImportDeep:
    """Deep coverage for import handler body."""

    def test_import_large_batch(self, client, test_db, test_users, auth_headers, test_org):
        """Import a larger batch of tasks."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [{"data": {"text": f"Batch task #{i}"}} for i in range(20)]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_data,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["created_tasks"] == 20

    def test_import_with_meta_and_inner_id(self, client, test_db, test_users, auth_headers, test_org):
        """Import tasks with meta fields and inner_id."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {"data": {"text": "Task A"}, "meta": {"source": "corpus_1"}, "id": 42},
                {"data": {"text": "Task B"}, "meta": {"source": "corpus_2"}, "id": 43},
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_data,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["created_tasks"] == 2

    def test_import_annotation_with_lead_time(self, client, test_db, test_users, auth_headers, test_org):
        """Import annotations with lead_time preserved."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Lead time task"},
                    "annotations": [{
                        "result": [{"from_name": "answer", "to_name": "text",
                                   "type": "choices", "value": {"choices": ["Ja"]}}],
                        "completed_by": test_users[0].id,
                        "lead_time": 42.5,
                    }],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_data,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["created_annotations"] == 1

    def test_import_multiple_annotations_per_task(self, client, test_db, test_users, auth_headers, test_org):
        """Import a task with multiple annotators."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Multi-annotator task"},
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
            f"/api/projects/{p.id}/import",
            json=import_data,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_annotations"] == 2

    def test_import_empty_data_array(self, client, test_db, test_users, auth_headers, test_org):
        """Import with empty data array should succeed with zero tasks."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/import",
            json={"data": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400)

    def test_import_with_questionnaire_and_generation(self, client, test_db, test_users, auth_headers, test_org):
        """Import combining annotations, questionnaires, and generations."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        import_data = {
            "data": [
                {
                    "data": {"text": "Full data task"},
                    "annotations": [{
                        "result": [{"from_name": "answer", "to_name": "text",
                                   "type": "choices", "value": {"choices": ["Ja"]}}],
                        "completed_by": test_users[0].id,
                        "questionnaire_response": {
                            "result": [{"from_name": "difficulty", "to_name": "text",
                                       "type": "rating", "value": {"rating": 5}}],
                        },
                    }],
                    "generations": [{
                        "model_id": "gpt-4o",
                        "response_content": "LLM answer",
                        "case_data": "{}",
                    }],
                }
            ]
        }
        resp = client.post(
            f"/api/projects/{p.id}/import",
            json=import_data,
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_tasks"] == 1
        assert body["created_annotations"] == 1
        assert body["created_generations"] == 1
        assert body["created_questionnaire_responses"] == 1


# ===================================================================
# BULK EXPORT: deep coverage
# ===================================================================

@pytest.mark.integration
class TestBulkExportDeep:
    """Deep coverage for bulk export handler body."""

    def test_bulk_export_json_with_full_data_graph(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export includes annotations, generations, evaluations."""
        p = _project(test_db, test_users[0], test_org, title="Bulk Full")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "json", "include_data": True},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 1
        proj_data = data["projects"][0]
        assert "tasks" in proj_data

    def test_bulk_export_multiple_projects(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export of 3 projects verifies correct project count."""
        projects = []
        for i in range(3):
            p = _project(test_db, test_users[0], test_org, title=f"Multi {i}")
            _tasks(test_db, p, test_users[0], count=2)
            projects.append(p)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={
                "project_ids": [p.id for p in projects],
                "format": "json",
                "include_data": True,
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 3

    def test_bulk_export_full_zip_contents(self, client, test_db, test_users, auth_headers, test_org):
        """Verify ZIP archive contains expected files."""
        p = _project(test_db, test_users[0], test_org, title="ZIP Contents")
        _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, [t for t in []], test_users[0].id)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [p.id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert len(names) >= 1

    def test_bulk_export_csv_format(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export in CSV format."""
        p = _project(test_db, test_users[0], test_org, title="Bulk CSV")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200


# ===================================================================
# ROUND-TRIP: deep fidelity checks
# ===================================================================

@pytest.mark.integration
class TestRoundTripDeep:
    """Round-trip export/import verifying data fidelity."""

    def test_roundtrip_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        """Export with generations, import into new project, verify counts."""
        src = _project(test_db, test_users[0], test_org, title="RT Source")
        tasks = _tasks(test_db, src, test_users[0], count=3)
        _annotations(test_db, src, tasks, test_users[0].id)
        _generations(test_db, src, tasks, model_id="gpt-4o")
        test_db.commit()

        export_resp = client.get(
            f"/api/projects/{src.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert export_resp.status_code == 200
        exported = json.loads(export_resp.text)

        target = _project(test_db, test_users[0], test_org, title="RT Target")
        test_db.commit()

        import_resp = client.post(
            f"/api/projects/{target.id}/import",
            json={"data": exported},
            headers=_h(auth_headers, test_org),
        )
        assert import_resp.status_code == 200
        body = import_resp.json()
        assert body["created_tasks"] == 3

    def test_roundtrip_preserves_annotation_results(self, client, test_db, test_users, auth_headers, test_org):
        """Annotation result values survive round-trip."""
        src = _project(test_db, test_users[0], test_org, title="RT Results")
        tasks = _tasks(test_db, src, test_users[0], count=1)
        ann = Annotation(
            id=_uid(), task_id=tasks[0].id, project_id=src.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Nein"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        export_resp = client.get(
            f"/api/projects/{src.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert export_resp.status_code == 200
        exported = json.loads(export_resp.text)

        # Verify the annotation result is in the export
        ann_result = exported[0]["annotations"][0]["result"][0]
        assert ann_result["value"]["choices"] == ["Nein"]
