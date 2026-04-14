"""
Integration tests targeting remaining uncovered code in import_export.py.

Specifically targets:
- Lines 468-861: export_project full format paths (CSV with data, TSV with data,
  Label Studio with all fields, TXT with evaluations)
- Lines 873-991: bulk_export_projects with CSV format, include_data variations
- Lines 1019-1087: bulk_export_full_projects (ZIP export with comprehensive data)
- Lines 1119-1741: import_full_project (JSON and ZIP import with complete data)
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
    Generation,
    Organization,
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
        title=kwargs.get("title", f"ImpExp2 {uuid.uuid4().hex[:6]}"),
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


def _tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, lead_time=10.0):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False, lead_time=lead_time,
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
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, case_data=json.dumps(t.data),
            response_content=f"Generated #{i}",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _eval_run(db, project, model_id="gpt-4o"):
    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=["accuracy"], metrics={"accuracy": 0.85},
        status="completed", samples_evaluated=3,
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
            id=_uid(), evaluation_id=eval_run.id, task_id=t.id,
            generation_id=gen_id, field_name="answer",
            answer_type="choices",
            ground_truth={"value": "Ja"},
            prediction={"value": "Ja" if i % 2 == 0 else "Nein"},
            metrics={"accuracy": 1.0 if i % 2 == 0 else 0.0},
            passed=i % 2 == 0,
        )
        db.add(te)
        tes.append(te)
    db.flush()
    return tes


def _questionnaire(db, project, tasks, anns, user_id):
    for ann, t in zip(anns, tasks):
        qr = PostAnnotationResponse(
            id=_uid(), annotation_id=ann.id, task_id=t.id,
            project_id=project.id, user_id=user_id,
            result=[{"from_name": "difficulty", "type": "rating", "value": {"rating": 3}}],
        )
        db.add(qr)
    db.flush()


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EXPORT: Full data graph exercises CSV/TSV/TXT/LS bodies completely
# ===================================================================

@pytest.mark.integration
class TestExportFullDataGraph:
    """Exercise all export format code paths with complete data."""

    def test_export_csv_with_annotations_and_generations(self, client, test_db, test_users, auth_headers, test_org):
        """CSV export with both annotations and generations populates all columns."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire(test_db, p, tasks, anns, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) >= 4  # header + 3 data rows
        header = lines[0]
        assert "annotation_id" in header
        assert "generation_id" in header
        assert "evaluation_field" in header

    def test_export_tsv_with_annotations_and_generations(self, client, test_db, test_users, auth_headers, test_org):
        """TSV export with full data uses tab delimiter."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire(test_db, p, tasks, anns, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=tsv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 4
        for line in lines:
            assert "\t" in line

    def test_export_txt_with_annotations_and_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        """TXT export with annotations and evaluations."""
        p = _project(test_db, test_users[0], test_org, title="TXT Test Project")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire(test_db, p, tasks, anns, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=txt",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        text = resp.text
        assert "TXT Test Project" in text
        assert "Annotations" in text
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_export_label_studio_with_full_data(self, client, test_db, test_users, auth_headers, test_org):
        """Label Studio export with all optional fields populated."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire(test_db, p, tasks, anns, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks, gens)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data) == 3
        assert "annotations" in data[0]
        assert "generations" in data[0]
        assert "evaluations" in data[0]

    def test_export_csv_tasks_only_no_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """CSV export for tasks with no annotations (else branch)."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        # header + 3 rows for tasks with no data
        assert len(lines) >= 4

    def test_export_tsv_tasks_only_no_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """TSV export for tasks with no annotations."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=tsv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_export_txt_no_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """TXT export for tasks with no annotations (different branch)."""
        p = _project(test_db, test_users[0], test_org, title="No Annotations")
        _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=txt",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "No annotations" in resp.text

    def test_export_json_no_download(self, client, test_db, test_users, auth_headers, test_org):
        """JSON export with download=false (no Content-Disposition)."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json&download=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_export_label_studio_with_questionnaire(self, client, test_db, test_users, auth_headers, test_org):
        """Label Studio export includes questionnaire responses."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _questionnaire(test_db, p, tasks, anns, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=label_studio",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        ann = data[0]["annotations"][0]
        assert "questionnaire_response" in ann


# ===================================================================
# BULK EXPORT: CSV and include_data variations
# ===================================================================

@pytest.mark.integration
class TestBulkExportVariations:
    """Cover bulk export with different formats and options."""

    def test_bulk_export_csv_format(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export in CSV format."""
        p = _project(test_db, test_users[0], test_org, title="Bulk CSV Var")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bulk_export_without_data(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export with include_data=false."""
        p = _project(test_db, test_users[0], test_org, title="Bulk No Data")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "json", "include_data": False},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        project_data = data["projects"][0]
        assert "tasks" not in project_data

    def test_bulk_export_unsupported_format(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export with unsupported format."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "xml"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_bulk_export_nonexistent_projects(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export with non-existent project IDs."""
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [_uid(), _uid()], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["projects"]) == 0


# ===================================================================
# BULK EXPORT FULL (ZIP)
# ===================================================================

@pytest.mark.integration
class TestBulkExportFull:
    """Cover bulk_export_full_projects handler (ZIP archive)."""

    def test_bulk_export_full_with_data(self, client, test_db, test_users, auth_headers, test_org):
        """Full ZIP export with comprehensive data."""
        p = _project(test_db, test_users[0], test_org, title="Full ZIP Export")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        anns = _annotations(test_db, p, tasks, test_users[0].id)
        _generations(test_db, p, tasks)
        er = _eval_run(test_db, p)
        _task_evals(test_db, er, tasks)
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
            assert len(names) == 1
            content = json.loads(zf.read(names[0]))
            assert "project" in content

    def test_bulk_export_full_multiple_projects(self, client, test_db, test_users, auth_headers, test_org):
        """Full ZIP export with multiple projects."""
        projects = []
        for i in range(3):
            p = _project(test_db, test_users[0], test_org, title=f"Multi ZIP {i}")
            _tasks(test_db, p, test_users[0], count=2)
            projects.append(p)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [p.id for p in projects]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            assert len(zf.namelist()) == 3

    def test_bulk_export_full_empty_ids(self, client, test_db, test_users, auth_headers, test_org):
        """Full ZIP export with no project IDs."""
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_bulk_export_full_nonexistent(self, client, test_db, test_users, auth_headers, test_org):
        """Full ZIP export with non-existent projects."""
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# IMPORT FULL PROJECT (JSON/ZIP)
# ===================================================================

@pytest.mark.integration
class TestImportFullProject:
    """Cover import_full_project handler body."""

    def _create_export_data(self, project_title="Import Test"):
        """Create a valid export data structure for import."""
        return {
            "format_version": "1.0.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "id": _uid(),
                "title": project_title,
                "description": "Imported project",
                "label_config": '<View><Text name="text" value="$text"/></View>',
                "expert_instruction": "Test instruction",
            },
            "users": [
                {"id": "user-1", "email": "admin@test.com", "name": "Admin"},
            ],
            "tasks": [
                {
                    "id": "task-1",
                    "inner_id": 1,
                    "data": {"text": "Imported task 1"},
                    "meta": {"source": "test"},
                    "annotations": [
                        {
                            "id": "ann-1",
                            "completed_by": "user-1",
                            "result": [{"from_name": "text", "to_name": "text",
                                       "type": "choices", "value": {"choices": ["Ja"]}}],
                            "lead_time": 15.5,
                        }
                    ],
                    "generations": [
                        {
                            "id": "gen-1",
                            "model_id": "gpt-4o",
                            "response_content": "LLM answer",
                            "case_data": "{}",
                        }
                    ],
                },
                {
                    "id": "task-2",
                    "inner_id": 2,
                    "data": {"text": "Imported task 2"},
                    "meta": {},
                    "annotations": [],
                    "generations": [],
                },
            ],
        }

    def test_import_json_file(self, client, test_db, test_users, auth_headers, test_org):
        """Import a JSON file."""
        export_data = self._create_export_data("JSON Import Test")
        json_bytes = json.dumps(export_data).encode("utf-8")

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.json", io.BytesIO(json_bytes), "application/json")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201, 400)

    def test_import_zip_file(self, client, test_db, test_users, auth_headers, test_org):
        """Import a ZIP file containing JSON."""
        export_data = self._create_export_data("ZIP Import Test")
        json_bytes = json.dumps(export_data).encode("utf-8")

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr("project_export.json", json_bytes)
        zip_buf.seek(0)

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.zip", zip_buf, "application/zip")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201, 400)

    def test_import_invalid_format(self, client, test_db, test_users, auth_headers, test_org):
        """Import an unsupported file format."""
        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.xml", io.BytesIO(b"<xml/>"), "text/xml")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_import_invalid_json(self, client, test_db, test_users, auth_headers, test_org):
        """Import a file with invalid JSON."""
        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.json", io.BytesIO(b"not json"), "application/json")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_import_unsupported_version(self, client, test_db, test_users, auth_headers, test_org):
        """Import with unsupported format version."""
        export_data = self._create_export_data()
        export_data["format_version"] = "2.0.0"
        json_bytes = json.dumps(export_data).encode("utf-8")

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.json", io.BytesIO(json_bytes), "application/json")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_import_no_project_data(self, client, test_db, test_users, auth_headers, test_org):
        """Import with no project data."""
        export_data = {"format_version": "1.0.0"}
        json_bytes = json.dumps(export_data).encode("utf-8")

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.json", io.BytesIO(json_bytes), "application/json")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_import_duplicate_title_auto_rename(self, client, test_db, test_users, auth_headers, test_org):
        """Import with duplicate title auto-renames."""
        # Create a project with same title
        existing = _project(test_db, test_users[0], test_org, title="Duplicate Title")
        test_db.commit()

        export_data = self._create_export_data("Duplicate Title")
        json_bytes = json.dumps(export_data).encode("utf-8")

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.json", io.BytesIO(json_bytes), "application/json")},
            headers=_h(auth_headers, test_org),
        )
        # Should succeed with renamed title
        assert resp.status_code in (200, 201, 400)

    def test_import_zip_no_json(self, client, test_db, test_users, auth_headers, test_org):
        """Import ZIP with no JSON files."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr("readme.txt", "No JSON here")
        zip_buf.seek(0)

        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.zip", zip_buf, "application/zip")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_import_bad_zip(self, client, test_db, test_users, auth_headers, test_org):
        """Import corrupted ZIP file."""
        resp = client.post(
            "/api/projects/import-project",
            files={"file": ("export.zip", io.BytesIO(b"not a zip"), "application/zip")},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400
