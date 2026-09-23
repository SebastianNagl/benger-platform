"""Linked exams hold exactly one task (owner decision D12).

An exam an LMS activity points at sends one grade per activity to the LMS,
so imports may not give it a second task:

* the import endpoints (upload URL, import job, cloud import) answer 422
  ``multi_task_unsupported`` once the linked exam has its task;
* the shared import drivers refuse a file that would leave a linked exam
  with more than one task, before their single commit.

Unlinked exams and other projects import as before.
"""

import io
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    LtiPlatformRegistration,
    LtiResourceLink,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, ProjectOrganization, Task
from routers.projects._import_stream import (
    ImportValidationError,
    run_nested_import,
    run_tabular_import,
)


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


def _seed(db, *, kind="exam", linked=True, tasks=1):
    """Org + contributor + project (optionally linked) with ``tasks`` tasks.

    Works on a sync session; the async tests run it through ``run_sync``.
    """
    org = Organization(
        id=_uid(), name="Linked Uni", display_name="Linked Uni",
        slug=f"linked-{_uid()[:8]}",
    )
    user = User(
        id=_uid(), username=f"le-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
        name="Teacher", is_superadmin=False, is_active=True, email_verified=True,
    )
    db.add_all([org, user])
    db.flush()
    db.add(OrganizationMembership(
        id=_uid(), user_id=user.id, organization_id=org.id,
        role=OrganizationRole.CONTRIBUTOR, is_active=True,
    ))
    project = Project(
        id=_uid(), title="Linked exam", created_by=user.id, kind=kind,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    db.add(ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=org.id,
        assigned_by=user.id,
    ))
    for index in range(tasks):
        db.add(Task(
            id=_uid(), project_id=project.id, inner_id=index + 1,
            data={"text": f"Fall {index + 1}"},
        ))
    if linked:
        registration = LtiPlatformRegistration(
            id=_uid(), organization_id=org.id, name="Moodle",
            issuer=f"https://moodle-{_uid()[:8]}.example", client_id="c-1",
            auth_login_url="https://x/a", auth_token_url="https://x/t",
            jwks_uri="https://x/j", status="active",
        )
        db.add(registration)
        db.flush()
        db.add(LtiResourceLink(
            id=_uid(), registration_id=registration.id, deployment_id="1",
            resource_link_id=f"rl-{_uid()[:8]}", project_id=project.id,
        ))
    db.flush()
    return org, user, project


def _key(project_id):
    return f"imports/2026/09/{project_id}/20260916_120000_import.json"


async def _seed_async(db, **kwargs):
    seeded = await db.run_sync(lambda session: _seed(session, **kwargs))
    await db.commit()
    return seeded


async def _post_all(client, org, project):
    """The three import entry points, each with a valid body."""
    result = MagicMock()
    result.id = "celery-1"
    with patch(
        "routers.projects.import_export.object_storage.storage_backend", "minio"
    ), patch(
        "routers.projects.import_export.object_storage.get_upload_url",
        return_value={"upload_url": "https://storage.example/u", "file_key": "k"},
    ), patch(
        "routers.projects.import_export.send_task_safe", return_value=result
    ) as send:
        upload = await client.post(
            f"/api/projects/{project.id}/imports/upload-url"
        )
        job = await client.post(
            f"/api/projects/{project.id}/imports",
            json={"object_key": _key(project.id)},
        )
        cloud = await client.post(
            f"/api/projects/{project.id}/cloud-imports",
            json={"connection_id": "missing", "object_keys": ["a.json"]},
        )
    return upload, job, cloud, send


@pytest.mark.integration
class TestLinkedExamImportEndpoints:
    @pytest.mark.asyncio
    async def test_linked_exam_with_its_task_refuses_every_import(
        self, async_test_client, async_test_db
    ):
        org, user, project = await _seed_async(async_test_db)
        with _as_user(user):
            responses = await _post_all(async_test_client, org, project)
        upload, job, cloud, send = responses
        for response in (upload, job, cloud):
            assert response.status_code == 422, response.text
            assert response.json()["detail"]["code"] == "multi_task_unsupported"
            assert "exactly one task" in response.json()["detail"]["message"]
        send.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "seed",
        [
            {"linked": False},  # an exam no activity points at
            {"kind": None},  # a plain project with an activity row
            {"tasks": 0},  # an empty linked exam may take its one task
        ],
        ids=["unlinked", "not-an-exam", "empty-linked-exam"],
    )
    async def test_other_projects_import_as_before(
        self, async_test_client, async_test_db, seed
    ):
        org, user, project = await _seed_async(async_test_db, **seed)
        with _as_user(user):
            upload, job, cloud, _send = await _post_all(
                async_test_client, org, project
            )
        assert upload.status_code == 200, upload.text
        assert job.status_code == 202, job.text
        # The cloud import gets past the gate and fails on the fake connection.
        assert cloud.status_code == 404, cloud.text


def _nested_payload(count):
    return io.BytesIO(
        json.dumps(
            {"data": [{"data": {"text": f"neu {i}"}} for i in range(count)]}
        ).encode()
    )


def _task_count(db, project_id):
    return db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    ).scalar()


@pytest.mark.integration
class TestLinkedExamImportDrivers:
    def test_nested_import_refuses_a_second_task(self, test_db):
        _org, user, project = _seed(test_db)
        test_db.commit()

        with pytest.raises(ImportValidationError) as exc_info:
            run_nested_import(test_db, project.id, _nested_payload(1), user.id)
        test_db.rollback()

        assert exc_info.value.status_code == 422
        assert "multi_task_unsupported" in exc_info.value.detail
        assert _task_count(test_db, project.id) == 1

    def test_empty_linked_exam_takes_exactly_one_task(self, test_db):
        _org, user, project = _seed(test_db, tasks=0)
        test_db.commit()

        with pytest.raises(ImportValidationError):
            run_nested_import(test_db, project.id, _nested_payload(2), user.id)
        test_db.rollback()
        assert _task_count(test_db, project.id) == 0

        result = run_nested_import(test_db, project.id, _nested_payload(1), user.id)
        assert result["created_tasks"] == 1
        assert _task_count(test_db, project.id) == 1

    def test_tabular_import_refuses_a_second_task(self, test_db):
        _org, user, project = _seed(test_db)
        test_db.commit()

        with pytest.raises(ImportValidationError) as exc_info:
            run_tabular_import(
                test_db, project.id, io.BytesIO(b"eine Zeile\n"), user.id, "txt"
            )
        test_db.rollback()
        assert "multi_task_unsupported" in exc_info.value.detail
        assert _task_count(test_db, project.id) == 1

    def test_unlinked_exam_imports_many_tasks(self, test_db):
        _org, user, project = _seed(test_db, linked=False)
        test_db.commit()

        result = run_nested_import(test_db, project.id, _nested_payload(3), user.id)

        assert result["created_tasks"] == 3
        assert _task_count(test_db, project.id) == 4
