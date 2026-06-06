"""Batch-boundary integration tests for the streaming import (issue #158).

The streaming rewrite flushes + ``expunge_all``s the SQLAlchemy session every
``_IMPORT_BATCH`` rows to keep peak heap O(batch) not O(file). The riskiest
property of that change is correctness *across* a batch boundary: detaching
just-inserted rows must neither drop nor duplicate them, and a child row whose
parent was inserted (and expunged) in an earlier batch must still resolve its
FK. These tests import comfortably more than two batches (with child rows that
FK-reference parents created in an earlier batch) and assert exact counts.

The sync import endpoints (``POST /{id}/import``, ``POST /import-project``) were
removed in the #158 follow-up; these tests now drive the same shared streaming
drivers (``run_nested_import`` / ``run_full_project_import``) the async worker
runs, so the memory-regression coverage survives the endpoint removal.
"""

import io
import json
import uuid

import pytest

from project_models import Annotation, Project, ProjectOrganization, Task
from routers.projects._import_stream import (
    run_full_project_import,
    run_nested_import,
)
from routers.projects.import_export import _IMPORT_BATCH

# Cross two full batches plus a partial remainder, so the run hits the
# flush+expunge boundary twice and ends mid-batch.
ROW_COUNT = 2 * _IMPORT_BATCH + 50


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, admin, org, title="Batch Boundary"):
    project = Project(
        id=_uid(),
        title=title,
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    db.add(ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    ))
    db.flush()
    return project


@pytest.mark.integration
class TestNestedImportBatchBoundary:
    """run_nested_import — Label-Studio nested format into an existing project."""

    def test_imports_all_rows_across_batches(
        self, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org, "Nested Batch")
        test_db.commit()

        # Each task carries one annotation completed by the admin (an existing
        # user), so the child insert exercises the FK path inside each batch.
        import_data = {
            "data": [
                {
                    "data": {"text": f"task {i}"},
                    "annotations": [
                        {
                            "result": [{
                                "from_name": "answer", "to_name": "text",
                                "type": "choices", "value": {"choices": ["Ja"]},
                            }],
                            "completed_by": test_users[0].id,
                        }
                    ],
                }
                for i in range(ROW_COUNT)
            ]
        }
        json_bytes = json.dumps(import_data).encode("utf-8")

        result = run_nested_import(
            test_db, project.id, io.BytesIO(json_bytes), test_users[0].id
        )
        assert result["created_tasks"] == ROW_COUNT
        assert result["created_annotations"] == ROW_COUNT

        # Source of truth: the DB. No rows dropped or duplicated by expunge_all.
        assert test_db.query(Task).filter(
            Task.project_id == project.id
        ).count() == ROW_COUNT
        assert test_db.query(Annotation).filter(
            Annotation.project_id == project.id
        ).count() == ROW_COUNT


@pytest.mark.integration
class TestFlatImportBatchBoundary:
    """run_full_project_import — flat comprehensive format (creates a project)."""

    def _export_payload(self, title):
        # Flat export shape: top-level `tasks` and `annotations` arrays, the
        # annotation referencing its task by id. The importer inserts every task
        # (flushing/expunging across batches) before a *separate* annotations
        # pass FK-references those task ids via the in-RAM id map — so this also
        # proves a parent expunged in an earlier pass stays FK-resolvable.
        tasks = [
            {"id": f"task-{i}", "inner_id": i + 1, "data": {"text": f"task {i}"}}
            for i in range(ROW_COUNT)
        ]
        annotations = [
            {
                "id": f"ann-{i}",
                "task_id": f"task-{i}",
                "completed_by": "user-1",
                "result": [{
                    "from_name": "answer", "to_name": "text",
                    "type": "choices", "value": {"choices": ["Ja"]},
                }],
            }
            for i in range(ROW_COUNT)
        ]
        return {
            "format_version": "1.0.0",
            "project": {
                "title": title,
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            "users": [{"id": "user-1", "email": "u1@test.com", "name": "User One"}],
            "tasks": tasks,
            "annotations": annotations,
        }

    def test_imports_all_rows_across_batches(
        self, test_db, test_users, test_org
    ):
        # test_org gives test_users[0] an active org membership; the full-project
        # importer requires one to own the newly-created project.
        payload = self._export_payload("Flat Batch")
        json_bytes = json.dumps(payload).encode("utf-8")

        result = run_full_project_import(
            test_db, io.BytesIO(json_bytes), test_users[0].id
        )
        counts = result["statistics"]["imported_counts"]
        assert counts["tasks"] == ROW_COUNT
        assert counts["annotations"] == ROW_COUNT

        new_project_id = result["project_id"]
        assert test_db.query(Task).filter(
            Task.project_id == new_project_id
        ).count() == ROW_COUNT
        assert test_db.query(Annotation).filter(
            Annotation.project_id == new_project_id
        ).count() == ROW_COUNT
