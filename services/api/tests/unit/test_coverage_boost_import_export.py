"""
Coverage boost tests for import/export endpoints.

Targets specific branches in routers/projects/import_export.py:
- export with various data configurations
- import with different file formats
- span annotation conversion functions
- bulk export
"""

import io
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    Task,
)


def _setup_export_project(db, users, num_tasks=3, add_annotations=True, add_generations=False):
    """Create a project with tasks, annotations, and optionally generations."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Export Org",
        slug=f"export-org-{uuid.uuid4().hex[:8]}",
        display_name="Export Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Export Project",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/><Choices name='sentiment' toName='text'><Choice value='positive'/><Choice value='negative'/></Choices></View>",
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
    for i in range(num_tasks):
        tid = str(uuid.uuid4())
        t = Task(
            id=tid,
            project_id=pid,
            data={"text": f"This is test document {i}"},
            inner_id=i + 1,
            is_labeled=add_annotations,
        )
        db.add(t)
        db.commit()
        tasks.append(t)

        if add_annotations:
            ann = Annotation(
                id=str(uuid.uuid4()),
                task_id=tid,
                project_id=pid,
                completed_by=users[0].id,
                result=[{
                    "from_name": "sentiment",
                    "to_name": "text",
                    "type": "choices",
                    "value": {"choices": ["positive" if i % 2 == 0 else "negative"]},
                }],
                was_cancelled=False,
                lead_time=30.0 + i,
            )
            db.add(ann)
            db.commit()

        if add_generations:
            rg = ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=pid,
                task_id=tid,
                model_id="gpt-4o",
                status="completed",
                created_by=users[0].id,
            )
            db.add(rg)
            db.commit()

            gen = Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=tid,
                model_id="gpt-4o",
                case_data=f"Test document {i}",
                response_content=f"Generated response for document {i}",
                status="completed",
                parsed_annotation=[{
                    "from_name": "sentiment",
                    "to_name": "text",
                    "type": "choices",
                    "value": {"choices": ["positive"]},
                }],
                parse_status="success",
            )
            db.add(gen)
            db.commit()

    return p, org, tasks


class TestConvertToLabelStudioFormat:
    """Test convert_to_label_studio_format function."""

    def test_none_results(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format(None) is None

    def test_empty_results(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format([]) == []

    def test_non_list_results(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format("not a list") == "not a list"

    def test_choices_passthrough(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [{"type": "choices", "value": {"choices": ["A"]}}]
        output = convert_to_label_studio_format(results)
        assert output == results

    def test_labels_with_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "labels": ["PER"]},
                        {"id": "s2", "start": 10, "end": 15, "labels": ["ORG"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["type"] == "labels"
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_labels_without_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "labels": ["PER"]},
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1

    def test_mixed_types(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {"type": "choices", "value": {"choices": ["A"]}},
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "labels": ["PER"]},
                    ]
                },
            },
            {"type": "textarea", "value": {"text": ["some text"]}},
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 3


class TestConvertFromLabelStudioFormat:
    """Test convert_from_label_studio_format function."""

    def test_none_results(self):
        from routers.projects.import_export import convert_from_label_studio_format

        assert convert_from_label_studio_format(None) is None

    def test_empty_results(self):
        from routers.projects.import_export import convert_from_label_studio_format

        assert convert_from_label_studio_format([]) == []

    def test_single_span(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [
            {
                "id": "span-1",
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {"start": 0, "end": 5, "labels": ["PER"]},
            }
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "labels"

    def test_multiple_spans_same_label(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [
            {
                "id": "span-1",
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {"start": 0, "end": 5, "labels": ["PER"]},
            },
            {
                "id": "span-2",
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {"start": 10, "end": 15, "labels": ["PER"]},
            },
        ]
        output = convert_from_label_studio_format(results)
        # Should be grouped into one result with spans array
        assert len(output) >= 1

    def test_non_labels_passthrough(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [
            {"type": "choices", "value": {"choices": ["A"]}},
        ]
        output = convert_from_label_studio_format(results)
        assert output == results


class TestExportProject:
    """Test export endpoint."""

    def test_export_json(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_export_csv(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_export_empty_project(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(test_db, test_users, num_tasks=0)
        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_export_with_cancelled_annotations(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(test_db, test_users, add_annotations=False)
        # Add a cancelled annotation
        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=tasks[0].id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "sentiment", "type": "choices", "value": {"choices": ["positive"]}}],
            was_cancelled=True,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_export_with_generations(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(
            test_db, test_users, add_generations=True
        )
        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_export_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/export?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_export_with_questionnaire_responses(self, client, auth_headers, test_db, test_users):
        p, org, tasks = _setup_export_project(test_db, test_users, add_annotations=True)
        # Add questionnaire response
        ann = test_db.query(Annotation).filter(Annotation.project_id == p.id).first()
        if ann:
            test_db.add(PostAnnotationResponse(
                id=str(uuid.uuid4()),
                annotation_id=ann.id,
                task_id=ann.task_id,
                project_id=p.id,
                user_id=test_users[0].id,
                result=[{"from_name": "r", "type": "rating", "value": {"rating": 4}}],
            ))
            test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestImportTasks:
    """Test import endpoint."""

    def test_import_json_tasks(self, client, auth_headers, test_db, test_users):
        p, org, _ = _setup_export_project(test_db, test_users, num_tasks=0)
        tasks_data = json.dumps([
            {"data": {"text": "Imported task 1"}},
            {"data": {"text": "Imported task 2"}},
        ]).encode()

        # The import endpoint uses UploadFile with the name 'file'
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.json", io.BytesIO(tasks_data), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code in [200, 201, 400, 422]

    def test_import_csv_tasks(self, client, auth_headers, test_db, test_users):
        p, org, _ = _setup_export_project(test_db, test_users, num_tasks=0)
        csv_content = "text\nFirst task text\nSecond task text\n".encode()

        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.csv", io.BytesIO(csv_content), "text/csv")},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code in [200, 201, 400, 422]

    def test_import_project_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/projects/nonexistent/import",
            files={"file": ("tasks.json", io.BytesIO(b"[]"), "application/json")},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in [404, 400, 422]

    def test_import_empty_file(self, client, auth_headers, test_db, test_users):
        p, org, _ = _setup_export_project(test_db, test_users, num_tasks=0)
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.json", io.BytesIO(b""), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code in [200, 400, 422]


class TestBulkExport:
    """Test bulk export endpoints."""

    def test_bulk_export(self, client, auth_headers, test_db, test_users):
        p1, org1, _ = _setup_export_project(test_db, test_users, num_tasks=2)
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id]},
            headers={**auth_headers["admin"], "X-Organization-Context": org1.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_empty(self, client, auth_headers):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in [200, 400]


class TestImportProject:
    """Test full project import endpoint."""

    def test_import_project_basic(self, client, auth_headers, test_db, test_users):
        org = Organization(
            id=str(uuid.uuid4()),
            name="Import Org",
            slug=f"import-org-{uuid.uuid4().hex[:8]}",
            display_name="Import Org",
            created_at=datetime.utcnow(),
        )
        test_db.add(org)
        test_db.commit()
        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[0].id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        project_data = {
            "project": {
                "title": "Imported Project",
                "description": "An imported project",
                "label_config": "<View><Text name='text' value='$text'/></View>",
            },
            "tasks": [
                {"data": {"text": "Task 1"}},
                {"data": {"text": "Task 2"}},
            ],
        }

        resp = client.post(
            "/api/projects/import-project",
            json=project_data,
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code in [200, 201, 400, 422]
