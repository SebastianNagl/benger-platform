"""Annotator blinding on the cross-project data surface and field discovery.

The per-project serving endpoints blind ``task.data`` for non-editor tiers
(routers/projects/tasks/blinding.py, pinned by test_task_data_blinding.py).
These tests pin the same policy on:

- ``GET /api/data/`` — cross-project task listing (payload + search filter),
- ``POST /api/data/export`` — JSON export of the same scope,
- ``GET /api/projects/{id}/task-fields`` — field discovery with sample values.

Editor tiers (ORG_ADMIN / CONTRIBUTOR / creator / superadmin) keep the full
data; annotator-tier org members get the label-config-bound keys only.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

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

SECRET = "GEHEIME MUSTERLOESUNG 123 BGB"

# Capitalized bound key (matched case-insensitively, like the labeling UI),
# plus reference fields in several spellings and a nested one.
TASK_DATA = {
    "Sachverhalt": "K kauft von B einen Gebrauchtwagen.",
    "Musterlösung": SECRET,
    "musterloesung": SECRET,
    "reference": {"musterloesung": SECRET},
}
BLINDED_VIEW = {"Sachverhalt": TASK_DATA["Sachverhalt"]}


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


async def _seed_user(db, name: str) -> User:
    u = User(
        id=_uid(),
        username=f"{name}-{_uid()[:8]}@test.com",
        email=f"{name}-{_uid()[:8]}@test.com",
        name=name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture(scope="function")
async def world(async_test_db):
    db = async_test_db
    admin = await _seed_user(db, "xblind-admin")
    contributor = await _seed_user(db, "xblind-contrib")
    annotator = await _seed_user(db, "xblind-anno")

    org = Organization(
        id=_uid(),
        name="XBlind Org",
        slug=f"xblind-org-{_uid()[:8]}",
        display_name="XBlind Org",
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
        title=f"XBlind Project {_uid()[:6]}",
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
            data=json.loads(json.dumps(TASK_DATA)),
            meta={},
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
        "project": project,
        "tasks": tasks,
    }


async def _list(client, user, project_id, **params):
    with _as_user(user):
        resp = await client.get(
            "/api/data/", params={"project_ids": [project_id], **params}
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _export(client, user, task_ids):
    with _as_user(user):
        resp = await client.post("/api/data/export?format=json", json=task_ids)
    assert resp.status_code == 200, resp.text
    return json.loads(resp.content)["tasks"]


async def _fields(client, user, project_id):
    with _as_user(user):
        resp = await client.get(
            f"/api/projects/{project_id}/task-fields", params={"sample_count": 20}
        )
    assert resp.status_code == 200, resp.text
    return {f["path"]: f for f in resp.json()["fields"]}


class TestGlobalListing:
    @pytest.mark.asyncio
    async def test_annotator_gets_blinded_data(self, async_test_client, world):
        body = await _list(async_test_client, world["annotator"], world["project"].id)
        assert body["total"] == 2
        for item in body["items"]:
            assert item["data"] == BLINDED_VIEW
            assert SECRET not in json.dumps(item, ensure_ascii=False)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_editor_gets_full_data(self, async_test_client, world, who):
        body = await _list(async_test_client, world[who], world["project"].id)
        assert body["total"] == 2
        for item in body["items"]:
            assert item["data"] == TASK_DATA

    @pytest.mark.asyncio
    async def test_search_is_no_oracle_over_hidden_fields(
        self, async_test_client, world
    ):
        anno = await _list(
            async_test_client, world["annotator"], world["project"].id, search="GEHEIME"
        )
        assert anno["total"] == 0 and anno["items"] == []
        # Visible content stays searchable for the annotator.
        visible = await _list(
            async_test_client, world["annotator"], world["project"].id, search="Gebraucht"
        )
        assert visible["total"] == 2
        # Editors search the full payload, unchanged.
        editor = await _list(
            async_test_client, world["contributor"], world["project"].id, search="GEHEIME"
        )
        assert editor["total"] == 2

    @pytest.mark.asyncio
    async def test_post_submit_reveal_applies_per_task(
        self, async_test_client, async_test_db, world
    ):
        world["project"].annotator_full_visibility_after_submit = True
        async_test_db.add(
            Annotation(
                id=_uid(),
                task_id=world["tasks"][0].id,
                project_id=world["project"].id,
                completed_by=world["annotator"].id,
                result=[{"from_name": "loesung", "value": {"text": ["x"]}}],
                was_cancelled=False,
            )
        )
        await async_test_db.commit()
        body = await _list(async_test_client, world["annotator"], world["project"].id)
        by_id = {item["id"]: item["data"] for item in body["items"]}
        assert by_id[world["tasks"][0].id] == TASK_DATA
        assert by_id[world["tasks"][1].id] == BLINDED_VIEW

    @pytest.mark.asyncio
    async def test_upcoming_window_hides_project_from_annotator_only(
        self, async_test_client, async_test_db, world
    ):
        world["project"].window_start_at = datetime.now(timezone.utc) + timedelta(days=1)
        await async_test_db.commit()
        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 0 and anno["items"] == []
        editor = await _list(async_test_client, world["admin"], world["project"].id)
        assert editor["total"] == 2


class TestGlobalExport:
    @pytest.mark.asyncio
    async def test_annotator_export_is_blinded(self, async_test_client, world):
        ids = [t.id for t in world["tasks"]]
        rows = await _export(async_test_client, world["annotator"], ids)
        assert len(rows) == 2
        for row in rows:
            assert row["data"] == BLINDED_VIEW

    @pytest.mark.asyncio
    async def test_editor_export_is_full(self, async_test_client, world):
        ids = [t.id for t in world["tasks"]]
        rows = await _export(async_test_client, world["contributor"], ids)
        assert len(rows) == 2
        for row in rows:
            assert row["data"] == TASK_DATA


class TestTaskFields:
    @pytest.mark.asyncio
    async def test_annotator_sees_only_bound_fields_without_samples(
        self, async_test_client, world
    ):
        fields = await _fields(async_test_client, world["annotator"], world["project"].id)
        assert set(fields) == {"$Sachverhalt"}
        assert fields["$Sachverhalt"]["sample_value"] is None
        assert SECRET not in json.dumps(fields, ensure_ascii=False)

    @pytest.mark.asyncio
    async def test_bound_reference_field_still_hidden_from_annotator(
        self, async_test_client, async_test_db, world
    ):
        """Defense in depth: even a config that binds the Musterlösung does not
        make task-fields list it for a non-editor."""
        world["project"].label_config = (
            '<View><Text name="sv" value="$sachverhalt"/>'
            '<Text name="ml" value="$musterlösung"/>'
            '<TextArea name="loesung" toName="sv"/></View>'
        )
        await async_test_db.commit()
        fields = await _fields(async_test_client, world["annotator"], world["project"].id)
        assert set(fields) == {"$Sachverhalt"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_editor_field_listing_unchanged(self, async_test_client, world, who):
        fields = await _fields(async_test_client, world[who], world["project"].id)
        # "reference" (top-level) is in the pre-existing sensitive list; the
        # other keys and their samples are served to editors as before.
        assert fields["$Sachverhalt"]["sample_value"] == TASK_DATA["Sachverhalt"]
        assert fields["$Musterlösung"]["sample_value"] == SECRET
        assert fields["$musterloesung"]["sample_value"] == SECRET
        assert "$reference" not in fields


class TestSearchRobustness:
    @pytest.mark.asyncio
    async def test_blinded_search_tolerates_non_object_payloads(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][1].data = ["not", "an", "object"]
        await async_test_db.commit()
        body = await _list(
            async_test_client, world["annotator"], world["project"].id, search="Gebraucht"
        )
        assert [item["id"] for item in body["items"]] == [world["tasks"][0].id]
