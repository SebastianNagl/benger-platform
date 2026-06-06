"""
Coverage boost tests for import/export endpoints.

Targets specific branches in routers/projects/import_export.py:
- span annotation conversion functions (convert_to/from_label_studio_format)
- multi-project bulk export (POST /bulk-export)

The single-project sync export/import endpoints were removed in the #158
follow-up (object storage is now the only transport); their fidelity is
covered by the shared-driver round-trip tests and the async job-endpoint tests.
"""

import uuid
from datetime import datetime


from models import (
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
)
from project_models import (
    Annotation,
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
                run_index=0,
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


class TestBulkExport:
    """Test bulk export endpoints (POST /bulk-export)."""

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
