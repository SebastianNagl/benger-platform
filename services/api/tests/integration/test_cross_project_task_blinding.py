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


async def _second_org_project(db, world):
    """A project in another org where the CONTRIBUTOR of ``world`` is only an
    ANNOTATOR (so a selection spanning both projects is mixed for them)."""
    org2 = Organization(
        id=_uid(),
        name="XBlind Org 2",
        slug=f"xblind-org2-{_uid()[:8]}",
        display_name="XBlind Org 2",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org2)
    await db.flush()
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=world["contributor"].id,
            organization_id=org2.id,
            role=OrganizationRole.ANNOTATOR,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    project2 = Project(
        id=_uid(),
        title=f"XBlind Project 2 {_uid()[:6]}",
        label_config=BOUND_CONFIG,
        created_by=world["admin"].id,
        is_published=True,
        assignment_mode="open",
    )
    db.add(project2)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project2.id,
            organization_id=org2.id,
            assigned_by=world["admin"].id,
        )
    )
    task2 = Task(
        id=_uid(),
        project_id=project2.id,
        inner_id=1,
        data={"Sachverhalt": "x"},
        meta={},
        created_by=world["admin"].id,
        updated_by=world["admin"].id,
    )
    db.add(task2)
    await db.commit()
    return task2


async def _is_labeled(db, task_ids):
    from sqlalchemy import select

    rows = await db.execute(select(Task.id, Task.is_labeled).where(Task.id.in_(task_ids)))
    return {tid: labeled for tid, labeled in rows.all()}


class TestBulkWritesRequireEditRights:
    @pytest.mark.asyncio
    async def test_annotator_cannot_bulk_update_status(
        self, async_test_client, async_test_db, world
    ):
        ids = [t.id for t in world["tasks"]]
        with _as_user(world["annotator"]):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true", json=ids
            )
        assert resp.status_code == 403, resp.text
        async_test_db.expire_all()
        assert set((await _is_labeled(async_test_db, ids)).values()) == {False}

    @pytest.mark.asyncio
    async def test_annotator_cannot_bulk_assign(
        self, async_test_client, async_test_db, world
    ):
        ids = [t.id for t in world["tasks"]]
        with _as_user(world["annotator"]):
            resp = await async_test_client.post(
                f"/api/data/bulk-assign?user_id={world['annotator'].id}", json=ids
            )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_editor_bulk_writes_still_work(
        self, async_test_client, async_test_db, world
    ):
        ids = [t.id for t in world["tasks"]]
        with _as_user(world["contributor"]):
            status = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true", json=ids
            )
            assign = await async_test_client.post(
                f"/api/data/bulk-assign?user_id={world['annotator'].id}", json=ids
            )
        assert status.status_code == 200, status.text
        assert assign.status_code == 200, assign.text
        async_test_db.expire_all()
        assert set((await _is_labeled(async_test_db, ids)).values()) == {True}

    @pytest.mark.asyncio
    async def test_mixed_selection_is_rejected_whole(
        self, async_test_client, async_test_db, world
    ):
        task2 = await _second_org_project(async_test_db, world)
        ids = [world["tasks"][0].id, task2.id]
        with _as_user(world["contributor"]):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true", json=ids
            )
        assert resp.status_code == 403, resp.text
        async_test_db.expire_all()
        # Nothing was written, not even on the editable project.
        assert set((await _is_labeled(async_test_db, ids)).values()) == {False}


class TestGlobalListingAssignee:
    @pytest.mark.asyncio
    async def test_other_users_assignment_hidden_from_annotator(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][0].assigned_to = world["contributor"].id
        world["tasks"][1].assigned_to = world["annotator"].id
        await async_test_db.commit()

        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        by_id = {item["id"]: item["assigned_to"] for item in anno["items"]}
        assert by_id[world["tasks"][0].id] is None
        assert world["contributor"].email not in json.dumps(anno)
        # Their own assignment stays visible.
        assert by_id[world["tasks"][1].id] == world["annotator"].name

        editor = await _list(async_test_client, world["admin"], world["project"].id)
        by_id = {item["id"]: item["assigned_to"] for item in editor["items"]}
        assert by_id[world["tasks"][0].id] == world["contributor"].name
        assert by_id[world["tasks"][1].id] == world["annotator"].name


class TestProjectListingSearch:
    @pytest.mark.asyncio
    async def test_blinded_search_matches_bound_key_case_insensitively(
        self, async_test_client, world
    ):
        """``$sachverhalt`` binds the ``Sachverhalt`` key (like the labeling
        UI), so its content must be searchable for the annotator too."""
        with _as_user(world["annotator"]):
            hit = await async_test_client.get(
                f"/api/projects/{world['project'].id}/tasks", params={"search": "Gebraucht"}
            )
            miss = await async_test_client.get(
                f"/api/projects/{world['project'].id}/tasks", params={"search": "GEHEIME"}
            )
        assert hit.status_code == 200, hit.text
        assert len(hit.json()["items"]) == 2
        assert miss.status_code == 200, miss.text
        assert miss.json()["items"] == []


# ---------------------------------------------------------------------------
# Per-project access parity: /api/data applies the same access decision and
# task scoping as the per-project task listing (GET /api/projects/{id}/tasks).
# ---------------------------------------------------------------------------


async def _per_project(client, user, project_id, **params):
    with _as_user(user):
        return await client.get(f"/api/projects/{project_id}/tasks", params=params)


async def _export_raw(client, user, fmt="json", task_ids=None):
    with _as_user(user):
        resp = await client.post(f"/api/data/export?format={fmt}", json=task_ids)
    assert resp.status_code == 200, resp.text
    return resp


class TestPerProjectAccessParity:
    @pytest.mark.asyncio
    async def test_annotator_does_not_see_private_org_exam(
        self, async_test_client, async_test_db, world
    ):
        world["project"].kind = "exam"
        world["project"].is_private = True
        await async_test_db.commit()

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 403
        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 0 and anno["items"] == []
        rows = await _export(
            async_test_client, world["annotator"], [t.id for t in world["tasks"]]
        )
        assert rows == []
        # The creator keeps the full view.
        admin = await _list(async_test_client, world["admin"], world["project"].id)
        assert admin["total"] == 2

    @pytest.mark.asyncio
    async def test_open_org_exam_is_listed_like_per_project(
        self, async_test_client, async_test_db, world
    ):
        """A non-private, open org exam reaches an org ANNOTATOR through the
        participant tier on the per-project listing; /api/data shows the same
        rows, blinded."""
        world["project"].kind = "exam"
        await async_test_db.commit()

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 200, per_project.text
        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == per_project.json()["total"] == 2
        for item in anno["items"]:
            assert item["data"] == BLINDED_VIEW

    @pytest.mark.asyncio
    async def test_annotator_does_not_see_upcoming_org_exam(
        self, async_test_client, async_test_db, world
    ):
        world["project"].kind = "exam"
        world["project"].window_start_at = datetime.now(timezone.utc) + timedelta(days=1)
        world["project"].window_end_at = datetime.now(timezone.utc) + timedelta(days=2)
        await async_test_db.commit()

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 403
        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 0 and anno["items"] == []

    @pytest.mark.asyncio
    async def test_annotator_does_not_see_archived_project(
        self, async_test_client, async_test_db, world
    ):
        world["project"].is_archived = True
        await async_test_db.commit()

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 403
        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 0 and anno["items"] == []
        with _as_user(world["annotator"]):
            everything = await async_test_client.get("/api/data/")
        assert world["project"].id not in {
            i["project_id"] for i in everything.json()["items"]
        }
        contrib = await _list(async_test_client, world["contributor"], world["project"].id)
        assert contrib["total"] == 2

    @pytest.mark.asyncio
    async def test_attempted_tier_keeps_own_task_read_only(
        self, async_test_client, async_test_db, world
    ):
        world["project"].is_archived = True
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

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 200, per_project.text
        per_project_ids = [t["id"] for t in per_project.json()["items"]]
        assert per_project_ids == [world["tasks"][0].id]

        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 1
        assert [i["id"] for i in anno["items"]] == per_project_ids
        assert anno["items"][0]["data"] == BLINDED_VIEW
        rows = await _export(
            async_test_client, world["annotator"], [t.id for t in world["tasks"]]
        )
        assert [r["id"] for r in rows] == per_project_ids
        # Read-only: bulk writes stay refused.
        with _as_user(world["annotator"]):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true", json=per_project_ids
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manual_assignment_limits_annotator_to_assigned_tasks(
        self, async_test_client, async_test_db, world
    ):
        from project_models import TaskAssignment

        world["project"].assignment_mode = "manual"
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=world["tasks"][1].id,
                user_id=world["annotator"].id,
                assigned_by=world["admin"].id,
                status="assigned",
            )
        )
        await async_test_db.commit()

        per_project = await _per_project(
            async_test_client, world["annotator"], world["project"].id
        )
        assert per_project.status_code == 200, per_project.text
        assert [t["id"] for t in per_project.json()["items"]] == [world["tasks"][1].id]

        anno = await _list(async_test_client, world["annotator"], world["project"].id)
        assert anno["total"] == 1 == len(anno["items"])
        assert anno["items"][0]["id"] == world["tasks"][1].id
        # The count uses the same scoping as the items, under filters too.
        searched = await _list(
            async_test_client, world["annotator"], world["project"].id, search="Gebraucht"
        )
        assert searched["total"] == 1 == len(searched["items"])
        rows = await _export(
            async_test_client, world["annotator"], [t.id for t in world["tasks"]]
        )
        assert [r["id"] for r in rows] == [world["tasks"][1].id]
        # Editors keep every task.
        contrib = await _list(async_test_client, world["contributor"], world["project"].id)
        assert contrib["total"] == 2


class TestAssigneePrivacy:
    @pytest.mark.asyncio
    async def test_export_shows_only_own_assignment_to_blinded_caller(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][0].assigned_to = world["contributor"].id
        world["tasks"][1].assigned_to = world["annotator"].id
        await async_test_db.commit()
        ids = [t.id for t in world["tasks"]]

        resp = await _export_raw(async_test_client, world["annotator"], "json", ids)
        by_id = {r["id"]: r["assigned_to"] for r in json.loads(resp.content)["tasks"]}
        assert by_id == {ids[0]: None, ids[1]: world["annotator"].id}

        csv_resp = await _export_raw(async_test_client, world["annotator"], "csv", ids)
        assert world["contributor"].id not in csv_resp.text
        assert world["annotator"].id in csv_resp.text

        resp = await _export_raw(async_test_client, world["admin"], "json", ids)
        by_id = {r["id"]: r["assigned_to"] for r in json.loads(resp.content)["tasks"]}
        assert by_id == {ids[0]: world["contributor"].id, ids[1]: world["annotator"].id}

    @pytest.mark.asyncio
    async def test_assigned_to_filter_cannot_probe_other_users(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][0].assigned_to = world["contributor"].id
        world["tasks"][1].assigned_to = world["annotator"].id
        await async_test_db.commit()
        pid = world["project"].id

        probe = await _list(
            async_test_client, world["annotator"], pid, assigned_to=world["contributor"].id
        )
        assert probe["total"] == 0 and probe["items"] == []
        own = await _list(
            async_test_client, world["annotator"], pid, assigned_to=world["annotator"].id
        )
        assert [i["id"] for i in own["items"]] == [world["tasks"][1].id]
        assert own["total"] == 1
        # "in progress" on a blinded project means assigned to the caller.
        in_progress = await _list(
            async_test_client, world["annotator"], pid, status="in_progress"
        )
        assert [i["id"] for i in in_progress["items"]] == [world["tasks"][1].id]

        editor = await _list(
            async_test_client, world["admin"], pid, assigned_to=world["contributor"].id
        )
        assert [i["id"] for i in editor["items"]] == [world["tasks"][0].id]
        editor_ip = await _list(async_test_client, world["admin"], pid, status="in_progress")
        assert editor_ip["total"] == 2


class TestSharpSSearch:
    @pytest.mark.asyncio
    async def test_bound_key_with_sharp_s_is_searchable(
        self, async_test_client, async_test_db, world
    ):
        """``$maßstab`` binds a ``Maßstab`` key: Python casefolds it to
        ``massstab`` while Postgres ``lower`` keeps ``maßstab``; the search
        must still find the visible content (and only that)."""
        world["project"].label_config = (
            '<View><Text name="m" value="$maßstab"/>'
            '<TextArea name="loesung" toName="m"/></View>'
        )
        for task in world["tasks"]:
            task.data = {"Maßstab": "Kaufvertrag über ein Fahrrad", "Musterlösung": SECRET}
        await async_test_db.commit()
        pid = world["project"].id

        hit = await _list(async_test_client, world["annotator"], pid, search="Fahrrad")
        assert hit["total"] == 2
        for item in hit["items"]:
            assert item["data"] == {"Maßstab": "Kaufvertrag über ein Fahrrad"}
        miss = await _list(async_test_client, world["annotator"], pid, search="GEHEIME")
        assert miss["total"] == 0

        per_hit = await _per_project(
            async_test_client, world["annotator"], pid, search="Fahrrad"
        )
        assert per_hit.status_code == 200, per_hit.text
        assert len(per_hit.json()["items"]) == 2
        per_miss = await _per_project(
            async_test_client, world["annotator"], pid, search="GEHEIME"
        )
        assert per_miss.json()["items"] == []
