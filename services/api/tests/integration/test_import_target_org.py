"""Which organization owns a create-new import (core 2.23).

``POST /project-imports`` stores the target named in the body on the job and
the worker's ``run_full_project_import`` re-validates it. Without a target the
copy is the importer's private project; there is no fallback to the first
membership any more, so importing no longer requires an organization.
"""

import io
import json

import pytest

from project_models import Project, ProjectOrganization
from routers.projects._import_stream import (
    ImportValidationError,
    run_full_project_import,
)


def _payload(title):
    return json.dumps(
        {
            "format_version": "1.0.0",
            "project": {
                "title": title,
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            "tasks": [{"id": "task-1", "data": {"text": "one"}}],
        }
    ).encode("utf-8")


def _owner_orgs(db, project_id):
    return [
        po.organization_id
        for po in db.query(ProjectOrganization)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    ]


@pytest.mark.integration
class TestImportTargetOrg:
    def test_without_a_target_the_copy_is_private(self, test_db, test_users, test_org):
        contributor = test_users[1]
        result = run_full_project_import(
            test_db, io.BytesIO(_payload("Private copy")), contributor.id
        )
        project = test_db.query(Project).filter(Project.id == result["project_id"]).one()
        assert project.is_private is True
        assert project.created_by == contributor.id
        assert _owner_orgs(test_db, project.id) == []

    def test_user_without_any_org_can_import_privately(self, test_db, test_users):
        result = run_full_project_import(
            test_db, io.BytesIO(_payload("No org")), test_users[1].id
        )
        project = test_db.query(Project).filter(Project.id == result["project_id"]).one()
        assert project.is_private is True

    def test_contributor_target_owns_the_copy(self, test_db, test_users, test_org):
        result = run_full_project_import(
            test_db,
            io.BytesIO(_payload("Org copy")),
            test_users[1].id,
            organization_id=test_org.id,
        )
        project = test_db.query(Project).filter(Project.id == result["project_id"]).one()
        assert project.is_private is False
        assert _owner_orgs(test_db, project.id) == [test_org.id]

    def test_annotator_target_is_refused(self, test_db, test_users, test_org):
        with pytest.raises(ImportValidationError) as exc:
            run_full_project_import(
                test_db,
                io.BytesIO(_payload("Annotator copy")),
                test_users[2].id,
                organization_id=test_org.id,
            )
        assert exc.value.status_code == 403
