"""Annotator task-data blinding on the classic serving endpoints (extended #56).

The label config binds only some ``task.data`` keys (``value="$key"``); keys
that are NOT bound — reference solutions, ground truth — were historically
shipped verbatim in the JSON of ``GET /{id}/tasks``, ``GET /{id}/next`` and
``GET /tasks/{task_id}``, so an annotator inspecting the network tab could
read the Musterlösung before submitting.

Pinned policy (routers/projects/tasks/blinding.py):
- annotator-tier (org ANNOTATOR role, or access without any role) → data
  reduced to the bound keys,
- EXCEPT the post-submit reveal: ``annotator_full_visibility_after_submit``
  + own active annotation on the task → full data for that task,
- editor-tier (CONTRIBUTOR / ORG_ADMIN / superadmin / creator) → never
  blinded,
- malformed label config fails CLOSED for annotators (empty visible set).

Same async harness as test_project_tasks_branches.py: rows seeded via
``async_test_db``, HTTP via ``async_test_client``, ``require_user``
overridden per acting user.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, OrganizationRole, User
from project_models import Annotation, Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


BOUND_CONFIG = (
    '<View><Text name="sachverhalt_view" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sachverhalt_view"/></View>'
)

SECRET_DATA = {
    "sachverhalt": "K kauft von B einen Gebrauchtwagen.",
    "musterloesung": "GEHEIME MUSTERLÖSUNG §123 BGB",
    "ground_truth": "GOLD",
}


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
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, name: str, *, superadmin: bool = False) -> User:
    u = User(
        id=_uid(),
        username=f"{name}-{_uid()[:8]}@test.com",
        email=f"{name}-{_uid()[:8]}@test.com",
        name=name,
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture(scope="function")
async def blinding_world(async_test_db):
    """Org with an admin (creator), a contributor, an annotator; one project
    carrying a bound + two unbound (secret) task.data keys; two tasks."""
    db = async_test_db
    admin = await _seed_user(db, "blind-admin")
    contributor = await _seed_user(db, "blind-contrib")
    annotator = await _seed_user(db, "blind-anno")

    org = Organization(
        id=_uid(),
        name="Blinding Org",
        slug=f"blind-org-{_uid()[:8]}",
        display_name="Blinding Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    for user, role in (
        (admin, OrganizationRole.ORG_ADMIN),
        (contributor, OrganizationRole.CONTRIBUTOR),
        (annotator, OrganizationRole.ANNOTATOR),
    ):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        )

    project = Project(
        id=_uid(),
        title=f"Blinding Project {_uid()[:6]}",
        label_config=BOUND_CONFIG,
        created_by=admin.id,
        is_published=True,
        assignment_mode="open",
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=admin.id,
        )
    )

    tasks = []
    for i in range(2):
        t = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data=dict(SECRET_DATA),
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.commit()
    return {
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
        "org": org,
        "project": project,
        "tasks": tasks,
    }


async def _annotate(db, task: Task, user: User):
    db.add(
        Annotation(
            id=_uid(),
            task_id=task.id,
            project_id=task.project_id,
            completed_by=user.id,
            result=[{"from_name": "loesung", "value": {"text": ["x"]}}],
            was_cancelled=False,
        )
    )
    await db.commit()


class TestAnnotatorBlinded:
    @pytest.mark.asyncio
    async def test_list_blinds_unbound_keys_for_annotator(
        self, async_test_client, blinding_world
    ):
        w = blinding_world
        with _as_user(w["annotator"]):
            resp = await async_test_client.get(f"/api/projects/{w['project'].id}/tasks")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        for item in items:
            assert item["data"] == {"sachverhalt": SECRET_DATA["sachverhalt"]}
            assert "musterloesung" not in item["data"]
            assert "ground_truth" not in item["data"]

    @pytest.mark.asyncio
    async def test_next_blinds_unbound_keys_for_annotator(
        self, async_test_client, blinding_world
    ):
        w = blinding_world
        with _as_user(w["annotator"]):
            resp = await async_test_client.get(f"/api/projects/{w['project'].id}/next")
        assert resp.status_code == 200, resp.text
        task = resp.json()["task"]
        assert task is not None
        assert task["data"] == {"sachverhalt": SECRET_DATA["sachverhalt"]}

    @pytest.mark.asyncio
    async def test_single_task_blinds_unbound_keys_for_annotator(
        self, async_test_client, blinding_world
    ):
        w = blinding_world
        with _as_user(w["annotator"]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"sachverhalt": SECRET_DATA["sachverhalt"]}

    @pytest.mark.asyncio
    async def test_malformed_config_fails_closed_for_annotator(
        self, async_test_client, async_test_db, blinding_world
    ):
        w = blinding_world
        w["project"].label_config = "<View><unclosed"
        await async_test_db.commit()
        with _as_user(w["annotator"]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert resp.status_code == 200, resp.text
        # Nothing is bound on a broken config → annotator sees NO data keys.
        assert resp.json()["data"] == {}


class TestEditorTierUnblinded:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_list_serves_full_data(self, async_test_client, blinding_world, who):
        w = blinding_world
        with _as_user(w[who]):
            resp = await async_test_client.get(f"/api/projects/{w['project'].id}/tasks")
        assert resp.status_code == 200, resp.text
        for item in resp.json()["items"]:
            assert item["data"] == SECRET_DATA

    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_single_task_serves_full_data(
        self, async_test_client, blinding_world, who
    ):
        w = blinding_world
        with _as_user(w[who]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == SECRET_DATA


class TestPostSubmitReveal:
    @pytest.mark.asyncio
    async def test_reveal_flag_plus_own_annotation_unblinds_that_task_only(
        self, async_test_client, async_test_db, blinding_world
    ):
        w = blinding_world
        w["project"].annotator_full_visibility_after_submit = True
        await _annotate(async_test_db, w["tasks"][0], w["annotator"])

        with _as_user(w["annotator"]):
            resp = await async_test_client.get(f"/api/projects/{w['project'].id}/tasks")
        assert resp.status_code == 200, resp.text
        by_id = {item["id"]: item["data"] for item in resp.json()["items"]}
        # Submitted task: full data (the intended post-submit reveal).
        assert by_id[w["tasks"][0].id] == SECRET_DATA
        # Untouched task: still blinded.
        assert by_id[w["tasks"][1].id] == {"sachverhalt": SECRET_DATA["sachverhalt"]}

        with _as_user(w["annotator"]):
            single = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert single.json()["data"] == SECRET_DATA

    @pytest.mark.asyncio
    async def test_no_reveal_without_flag_even_after_submitting(
        self, async_test_client, async_test_db, blinding_world
    ):
        w = blinding_world  # flag stays False (default)
        await _annotate(async_test_db, w["tasks"][0], w["annotator"])

        with _as_user(w["annotator"]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"sachverhalt": SECRET_DATA["sachverhalt"]}

    @pytest.mark.asyncio
    async def test_cancelled_annotation_does_not_reveal(
        self, async_test_client, async_test_db, blinding_world
    ):
        w = blinding_world
        w["project"].annotator_full_visibility_after_submit = True
        async_test_db.add(
            Annotation(
                id=_uid(),
                task_id=w["tasks"][0].id,
                project_id=w["project"].id,
                completed_by=w["annotator"].id,
                result=[],
                was_cancelled=True,
            )
        )
        await async_test_db.commit()

        with _as_user(w["annotator"]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{w['tasks'][0].id}"
            )
        assert resp.json()["data"] == {"sachverhalt": SECRET_DATA["sachverhalt"]}
