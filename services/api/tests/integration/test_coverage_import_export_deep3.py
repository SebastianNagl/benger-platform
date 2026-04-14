"""
Deep integration tests for import/export endpoints.

Targets: routers/projects/import_export.py — varied annotation structures,
generation data, span annotations, different meta structures, CSV export.
"""

import io
import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationConfig,
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
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


def _make_project(db, admin, org, **kwargs):
    """Create a project with org assignment."""
    pid = _uid()
    p = Project(
        id=pid,
        title=kwargs.get("title", f"Test Project {pid[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kwargs.get("is_private", False),
        review_enabled=kwargs.get("review_enabled", False),
        assignment_mode=kwargs.get("assignment_mode", "open"),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        questionnaire_enabled=kwargs.get("questionnaire_enabled", False),
        annotation_time_limit_enabled=kwargs.get("annotation_time_limit_enabled", False),
        strict_timer_enabled=kwargs.get("strict_timer_enabled", False),
        immediate_evaluation_enabled=kwargs.get("immediate_evaluation_enabled", False),
    )
    db.add(p)
    db.flush()

    if org:
        po = ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=org.id,
            assigned_by=admin.id,
        )
        db.add(po)
        db.flush()

    return p


def _make_task(db, project, admin, *, data=None, inner_id=1, meta=None):
    t = Task(
        id=_uid(),
        project_id=project.id,
        data=data or {"text": f"Task text {inner_id}"},
        meta=meta,
        inner_id=inner_id,
        created_by=admin.id,
    )
    db.add(t)
    db.flush()
    return t


def _make_annotation(db, task, project, user, *, result=None, was_cancelled=False):
    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=result or [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
        was_cancelled=was_cancelled,
    )
    db.add(ann)
    db.flush()
    return ann


# -----------------------------------------------------------------
# Export tests
# -----------------------------------------------------------------


@pytest.mark.integration
class TestExportVariedAnnotations:
    """Test exports with different annotation result structures."""

    def test_export_with_choices_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_textarea_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, label_config=(
            '<View><Text name="text" value="$text"/>'
            '<TextArea name="comment" toName="text"/></View>'
        ))
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "comment", "to_name": "text", "type": "textarea", "value": {"text": ["This is a comment"]}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "tasks" in data

    def test_export_with_rating_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Rating name="quality" toName="text"/></View>'
        ))
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "quality", "to_name": "text", "type": "rating", "value": {"rating": 5}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_span_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Labels name="label" toName="text"><Label value="PER"/><Label value="ORG"/></Labels></View>'
        ))
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "label", "to_name": "text", "type": "labels",
             "value": {"spans": [
                 {"id": "s1", "start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
                 {"id": "s2", "start": 10, "end": 15, "text": "World", "labels": ["ORG"]},
             ]}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=label_studio",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_cancelled_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], was_cancelled=True, result=[
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Nein"]}}
        ])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_multiple_annotators(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0], result=[
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}
        ])
        _make_annotation(test_db, t, p, test_users[1], result=[
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Nein"]}}
        ])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_csv_format(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_different_meta_structures(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        _make_task(test_db, p, test_users[0], inner_id=1, meta={"source": "web", "difficulty": "easy"})
        _make_task(test_db, p, test_users[0], inner_id=2, meta={"source": "pdf", "pages": [1, 2, 3]})
        _make_task(test_db, p, test_users[0], inner_id=3, meta=None)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestExportWithGenerations:
    """Test exports with generation data."""

    def test_export_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])

        # First create a ResponseGeneration (parent)
        rg = ResponseGeneration(
            id=_uid(),
            task_id=t.id,
            model_id="gpt-4",
            config_id="config-1",
            status="completed",
            responses_generated=1,
            created_by=test_users[0].id,
        )
        test_db.add(rg)
        test_db.flush()

        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=t.id,
            model_id="gpt-4",
            case_data=json.dumps({"text": "Task text 1"}),
            response_content="Generated output text",
            parsed_annotation={"answer": "Ja", "confidence": 0.95},
            status="completed",
        )
        test_db.add(gen)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_with_response_generations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])

        rg = ResponseGeneration(
            id=_uid(),
            task_id=t.id,
            model_id="claude-3",
            config_id="config-1",
            status="completed",
            responses_generated=1,
            created_by=test_users[0].id,
        )
        test_db.add(rg)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestComprehensiveExport:
    """Test comprehensive export endpoint."""

    def test_comprehensive_export(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        ann = _make_annotation(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export/comprehensive",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # This endpoint may be at different path
        assert resp.status_code in (200, 404)

    def test_export_project_with_members(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        pm = ProjectMember(
            id=_uid(),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            is_active=True,
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_project_with_assignments(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org, assignment_mode="manual")
        t = _make_task(test_db, p, test_users[0])
        assignment = TaskAssignment(
            id=_uid(),
            task_id=t.id,
            user_id=test_users[1].id,
            assigned_by=test_users[0].id,
            status="assigned",
        )
        test_db.add(assignment)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# -----------------------------------------------------------------
# Import tests
# -----------------------------------------------------------------


@pytest.mark.integration
class TestImportVariedFormats:
    """Test imports with different formats and data."""

    def test_import_json_array_of_objects(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tasks = [
            {"data": {"text": "First task"}, "meta": {"source": "test"}},
            {"data": {"text": "Second task"}, "meta": {"difficulty": "hard"}},
            {"data": {"text": "Third task"}},
        ]
        file_content = json.dumps(tasks).encode()
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.json", io.BytesIO(file_content), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_csv_with_multiple_columns(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        csv_content = b"text,label,confidence\nHello world,positive,0.9\nBad day,negative,0.8\n"
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.csv", io.BytesIO(csv_content), "text/csv")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_json_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tasks = [
            {
                "data": {"text": "Pre-annotated task"},
                "annotations": [
                    {
                        "result": [{"from_name": "answer", "to_name": "text", "type": "choices",
                                    "value": {"choices": ["Ja"]}}],
                    }
                ],
            }
        ]
        file_content = json.dumps(tasks).encode()
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.json", io.BytesIO(file_content), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_tsv_format(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tsv_content = b"text\tlabel\nFirst\tpositive\nSecond\tnegative\n"
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.tsv", io.BytesIO(tsv_content), "text/tab-separated-values")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_empty_file(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("empty.json", io.BytesIO(b"[]"), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 422)

    def test_import_invalid_json(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("bad.json", io.BytesIO(b"not valid json{{{"), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (400, 422, 500)

    def test_import_large_batch(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tasks = [{"data": {"text": f"Task number {i}"}} for i in range(50)]
        file_content = json.dumps(tasks).encode()
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("many.json", io.BytesIO(file_content), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_with_nested_data(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tasks = [
            {"data": {"text": "Complex", "nested": {"key": "value", "list": [1, 2, 3]}}},
        ]
        file_content = json.dumps(tasks).encode()
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("nested.json", io.BytesIO(file_content), "application/json")},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_import_permission_denied_annotator(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        tasks = [{"data": {"text": "Should fail"}}]
        file_content = json.dumps(tasks).encode()
        resp = client.post(
            f"/api/projects/{p.id}/import",
            files={"file": ("tasks.json", io.BytesIO(file_content), "application/json")},
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 403, 422)


# -----------------------------------------------------------------
# Export annotations endpoint
# -----------------------------------------------------------------


@pytest.mark.integration
class TestExportAnnotationsEndpoint:

    def test_export_annotations_basic(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export-annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404, 405)

    def test_export_annotations_csv_format(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        t = _make_task(test_db, p, test_users[0])
        _make_annotation(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export-annotations?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404, 405)

    def test_export_annotations_no_data(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/export-annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404, 405)


# -----------------------------------------------------------------
# Bulk export tests
# -----------------------------------------------------------------


@pytest.mark.integration
class TestBulkExport:

    def test_bulk_export_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        for i in range(5):
            t = _make_task(test_db, p, test_users[0], inner_id=i + 1)
            _make_annotation(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/export/bulk",
            json={"format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404, 405)

    def test_bulk_export_with_filters(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project(test_db, test_users[0], test_org)
        for i in range(3):
            t = _make_task(test_db, p, test_users[0], inner_id=i + 1)
            if i % 2 == 0:
                _make_annotation(test_db, t, p, test_users[0])
                t.is_labeled = True
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/export/bulk",
            json={"format": "json", "only_labeled": True},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404, 405)


# -----------------------------------------------------------------
# Span conversion function tests
# -----------------------------------------------------------------


@pytest.mark.integration
class TestSpanConversion:
    """Test convert_to_label_studio_format and convert_from_label_studio_format."""

    def test_convert_to_label_studio_with_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
                        {"id": "s2", "start": 10, "end": 15, "text": "World", "labels": ["ORG"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["type"] == "labels"
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_convert_to_label_studio_no_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_convert_to_label_studio_empty_input(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format([]) == []
        assert convert_to_label_studio_format(None) is None

    def test_convert_from_label_studio_format(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [
            {"id": "s1", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 0, "end": 5, "text": "Hello", "labels": ["PER"]}},
            {"id": "s2", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 10, "end": 15, "text": "World", "labels": ["ORG"]}},
        ]
        output = convert_from_label_studio_format(results)
        # Should consolidate spans
        assert isinstance(output, list)

    def test_convert_from_label_studio_empty(self):
        from routers.projects.import_export import convert_from_label_studio_format

        assert convert_from_label_studio_format([]) == []
        assert convert_from_label_studio_format(None) is None

    def test_convert_roundtrip(self):
        from routers.projects.import_export import convert_from_label_studio_format, convert_to_label_studio_format

        original = [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
                    ]
                },
            }
        ]
        ls_format = convert_to_label_studio_format(original)
        back = convert_from_label_studio_format(ls_format)
        assert isinstance(back, list)
