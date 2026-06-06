"""Test for Issue #581: data import must set ResponseGeneration.project_id and
avoid redundant in-function model imports.

The sync import endpoint these tests originally drove (``import_project_data`` /
the old ``import_data`` alias) was removed in the #158 follow-up. The import
insert logic now lives in the shared streaming driver ``run_nested_import`` — the
same code the async worker runs — so the #581 regression guard (every imported
ResponseGeneration carries ``project_id``) is re-pointed at that driver.
"""

import io
import json
import uuid

import pytest

from models import ResponseGeneration
from project_models import Project, ProjectOrganization, Task
from routers.projects._import_stream import run_nested_import


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, admin, org, title="Issue 581"):
    project = Project(
        id=_uid(),
        title=title,
        created_by=admin.id,
        label_config="<View><Text name='text' value='$text'/></View>",
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
class TestImportFix581:
    """Issue #581 — imported generations must persist with project_id."""

    def _payload_with_generations(self):
        # One task carrying one generation (the BenGER `generations` extension on
        # a nested Label-Studio item). The driver groups generations by model_id
        # into a ResponseGeneration, then inserts a Generation per row.
        return {
            "data": [
                {
                    "data": {"text": "Sample task"},
                    "meta": {"category": "test"},
                    "annotations": [],
                    "generations": [
                        {
                            "model_id": "gpt-4",
                            "response_content": "Generated response",
                            "response_metadata": {},
                        }
                    ],
                }
            ],
            "meta": {"source": "test"},
        }

    def test_import_with_generations_sets_project_id(
        self, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        body = json.dumps(self._payload_with_generations()).encode("utf-8")
        result = run_nested_import(
            test_db, project.id, io.BytesIO(body), test_users[0].id
        )

        assert result["created_tasks"] == 1
        assert result["created_generations"] == 1

        # #581 core guard: the imported ResponseGeneration must carry project_id
        # (a NULL would orphan the row and 500 the results view).
        gens = (
            test_db.query(ResponseGeneration)
            .filter(ResponseGeneration.project_id == project.id)
            .all()
        )
        assert len(gens) == 1
        rg = gens[0]
        assert rg.project_id == project.id
        assert rg.model_id == "gpt-4"
        assert rg.status == "completed"
        assert rg.created_by == test_users[0].id

    def test_import_without_generations_still_works(
        self, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org, "Issue 581 no-gen")
        test_db.commit()

        body = json.dumps(
            {"data": [{"data": {"text": "Task without generation"}, "meta": {}}]}
        ).encode("utf-8")
        result = run_nested_import(
            test_db, project.id, io.BytesIO(body), test_users[0].id
        )

        assert result["created_tasks"] == 1
        assert result["created_generations"] == 0
        assert (
            test_db.query(Task).filter(Task.project_id == project.id).count() == 1
        )
        assert (
            test_db.query(ResponseGeneration)
            .filter(ResponseGeneration.project_id == project.id)
            .count()
            == 0
        )

    def test_calculate_generation_stats_no_redundant_import(self):
        """#581 also removed a redundant in-function ResponseGeneration import."""
        import inspect

        from projects_api import calculate_generation_stats

        source = inspect.getsource(calculate_generation_stats)
        assert (
            "from models import ResponseGeneration" not in source
        ), "ResponseGeneration should not be imported inside calculate_generation_stats"
