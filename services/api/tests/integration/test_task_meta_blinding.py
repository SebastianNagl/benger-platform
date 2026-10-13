"""Annotator blinding of ``task.meta`` (compliance prep, 2026-10-13).

``task.meta`` carries the editing history (``audit_log``: data edits with
their before/after values, i.e. reference-solution edits, plus the editor's
e-mail) and the archive flag. Every endpoint that blinds ``task.data`` now
also reduces ``meta`` for blinded callers to the ``tags`` and the public
benchmark descriptors (``routers.projects.tasks.blinding.PUBLIC_META_KEYS``):

- ``GET /projects/{id}/tasks``, ``/next``, ``GET /projects/tasks/{task_id}``,
- ``GET /api/data/`` (payload and search) and ``POST /api/data/export``.

Editor tiers keep the full meta. The post-submit reveal keeps uncovering
``task.data`` per task; it never uncovers the audit log.
"""

import json
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
from routers.projects.tasks.blinding import PUBLIC_META_KEYS, blind_task_meta


def _uid() -> str:
    return str(uuid.uuid4())


BOUND_CONFIG = (
    '<View><Text name="sachverhalt_view" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sachverhalt_view"/></View>'
)

SECRET_BEFORE = "ALTE GEHEIME MUSTERLOESUNG"
SECRET_AFTER = "NEUE GEHEIME MUSTERLOESUNG"
GRADER_NOTE = "NUR FUER KORREKTOREN"

TASK_DATA = {
    "sachverhalt": "K kauft von B einen Gebrauchtwagen.",
    "musterloesung": SECRET_AFTER,
}

TASK_META = {
    "tags": ["zivilrecht", "kaufrecht"],
    "benchmark": {
        "rechtsgebiet": "Zivilrecht",
        "art": "Klausur",
        "bearbeitungszeit": 300,
        "notenschluessel": GRADER_NOTE,
        "korrekturhinweise": GRADER_NOTE,
    },
    "audit_log": [
        {
            "timestamp": "2026-10-01T10:00:00",
            "user_id": "editor",
            "user_email": "editor@example.com",
            "action": "data_update",
            "changes": {
                "before": {"musterloesung": SECRET_BEFORE},
                "after": {"musterloesung": SECRET_AFTER},
            },
        }
    ],
    "is_archived": False,
}

BLINDED_META = {
    "tags": ["zivilrecht", "kaufrecht"],
    "benchmark": {"rechtsgebiet": "Zivilrecht", "art": "Klausur", "bearbeitungszeit": 300},
}


# ---------------------------------------------------------------------------
# The pure helper
# ---------------------------------------------------------------------------


class TestBlindTaskMeta:
    def test_editor_decision_returns_meta_untouched(self):
        assert blind_task_meta(TASK_META, None) is TASK_META
        assert blind_task_meta(None, None) is None

    def test_blinded_caller_gets_tags_and_public_benchmark_only(self):
        assert blind_task_meta(TASK_META, {"sachverhalt"}) == BLINDED_META
        # An empty bound set (malformed config, fail-closed) blinds the same way.
        assert blind_task_meta(TASK_META, set()) == BLINDED_META

    def test_empty_keys_are_dropped(self):
        assert blind_task_meta({"tags": [], "benchmark": {}}, set()) == {}
        assert blind_task_meta({"tags": None, "benchmark": {"secret": 1}}, set()) == {}
        assert blind_task_meta({"audit_log": [{"x": 1}], "is_archived": True}, set()) == {}

    def test_non_dict_meta_is_served_empty_to_blinded_callers(self):
        assert blind_task_meta(None, set()) == {}
        assert blind_task_meta(["not", "an", "object"], set()) == {}
        assert blind_task_meta("string", set()) == {}

    def test_public_keys_are_the_benchmark_descriptors(self):
        assert set(PUBLIC_META_KEYS) == {
            "rechtsgebiet",
            "rechtsgebiete",
            "teilgebiete",
            "art",
            "zielgruppe",
            "landesrecht",
            "herkunft_bundesland",
            "bearbeitungszeit",
        }


# ---------------------------------------------------------------------------
# Endpoint harness (same shape as test_task_data_blinding.py)
# ---------------------------------------------------------------------------


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
    admin = await _seed_user(db, "mblind-admin")
    contributor = await _seed_user(db, "mblind-contrib")
    annotator = await _seed_user(db, "mblind-anno")

    org = Organization(
        id=_uid(),
        name="MBlind Org",
        slug=f"mblind-org-{_uid()[:8]}",
        display_name="MBlind Org",
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
        title=f"MBlind Project {_uid()[:6]}",
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
            meta=json.loads(json.dumps(TASK_META)),
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


def _assert_no_hidden_meta(payload) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    assert "audit_log" not in text
    assert "is_archived" not in text
    assert SECRET_BEFORE not in text
    assert GRADER_NOTE not in text
    assert "editor@example.com" not in text


async def _list(client, user, project_id, **params):
    with _as_user(user):
        resp = await client.get("/api/data/", params={"project_ids": [project_id], **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _export(client, user, task_ids):
    with _as_user(user):
        resp = await client.post("/api/data/export?format=json", json=task_ids)
    assert resp.status_code == 200, resp.text
    return json.loads(resp.content)["tasks"]


class TestPerProjectEndpoints:
    @pytest.mark.asyncio
    async def test_list_blinds_meta_for_annotator(self, async_test_client, world):
        with _as_user(world["annotator"]):
            resp = await async_test_client.get(f"/api/projects/{world['project'].id}/tasks")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        for item in items:
            assert item["meta"] == BLINDED_META
            assert item["data"] == {"sachverhalt": TASK_DATA["sachverhalt"]}
        _assert_no_hidden_meta(resp.json())

    @pytest.mark.asyncio
    async def test_next_blinds_meta_for_annotator(self, async_test_client, world):
        with _as_user(world["annotator"]):
            resp = await async_test_client.get(f"/api/projects/{world['project'].id}/next")
        assert resp.status_code == 200, resp.text
        task = resp.json()["task"]
        assert task["meta"] == BLINDED_META
        _assert_no_hidden_meta(resp.json())

    @pytest.mark.asyncio
    async def test_single_task_blinds_meta_for_annotator(self, async_test_client, world):
        with _as_user(world["annotator"]):
            resp = await async_test_client.get(f"/api/projects/tasks/{world['tasks'][0].id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"] == BLINDED_META
        _assert_no_hidden_meta(body)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_editors_keep_full_meta(self, async_test_client, world, who):
        with _as_user(world[who]):
            listing = await async_test_client.get(f"/api/projects/{world['project'].id}/tasks")
            single = await async_test_client.get(f"/api/projects/tasks/{world['tasks'][0].id}")
            nxt = await async_test_client.get(f"/api/projects/{world['project'].id}/next")
        assert listing.status_code == 200, listing.text
        for item in listing.json()["items"]:
            assert item["meta"] == TASK_META
        assert single.status_code == 200, single.text
        assert single.json()["meta"] == TASK_META
        assert nxt.status_code == 200, nxt.text
        assert nxt.json()["task"]["meta"] == TASK_META

    @pytest.mark.asyncio
    async def test_post_submit_reveal_uncovers_data_but_never_the_audit_log(
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
        with _as_user(world["annotator"]):
            resp = await async_test_client.get(f"/api/projects/tasks/{world['tasks'][0].id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The reveal rule is unchanged: full data for the submitted task ...
        assert body["data"] == TASK_DATA
        # ... but the editing history stays hidden.
        assert body["meta"] == BLINDED_META
        _assert_no_hidden_meta(body)

    @pytest.mark.asyncio
    async def test_non_object_meta_is_served_empty_to_annotator(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][0].meta = ["not", "an", "object"]
        await async_test_db.commit()
        with _as_user(world["annotator"]):
            resp = await async_test_client.get(f"/api/projects/tasks/{world['tasks'][0].id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["meta"] == {}


class TestCrossProjectDataSurface:
    @pytest.mark.asyncio
    async def test_listing_blinds_meta_for_annotator(self, async_test_client, world):
        body = await _list(async_test_client, world["annotator"], world["project"].id)
        assert body["total"] == 2
        for item in body["items"]:
            assert item["meta"] == BLINDED_META
        _assert_no_hidden_meta(body)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("who", ["admin", "contributor"])
    async def test_listing_keeps_full_meta_for_editors(self, async_test_client, world, who):
        body = await _list(async_test_client, world[who], world["project"].id)
        for item in body["items"]:
            assert item["meta"] == TASK_META

    @pytest.mark.asyncio
    async def test_export_blinds_meta_for_annotator_and_not_for_editors(
        self, async_test_client, world
    ):
        ids = [t.id for t in world["tasks"]]
        rows = await _export(async_test_client, world["annotator"], ids)
        assert len(rows) == 2
        for row in rows:
            assert row["meta"] == BLINDED_META
        _assert_no_hidden_meta(rows)
        editor_rows = await _export(async_test_client, world["contributor"], ids)
        for row in editor_rows:
            assert row["meta"] == TASK_META

    @pytest.mark.asyncio
    async def test_search_is_no_oracle_over_hidden_meta(self, async_test_client, world):
        anno = world["annotator"]
        pid = world["project"].id
        # The audit log's before-value and the grader note never match.
        for hidden in ("ALTE GEHEIME", GRADER_NOTE, "editor@example", "audit_log"):
            body = await _list(async_test_client, anno, pid, search=hidden)
            assert body["total"] == 0 and body["items"] == [], hidden
        # Tags and the public benchmark descriptors stay searchable.
        assert (await _list(async_test_client, anno, pid, search="kaufrecht"))["total"] == 2
        assert (await _list(async_test_client, anno, pid, search="Zivilrecht"))["total"] == 2
        assert (await _list(async_test_client, anno, pid, search="Klausur"))["total"] == 2
        # Editors search the raw meta, unchanged.
        editor = await _list(async_test_client, world["contributor"], pid, search="ALTE GEHEIME")
        assert editor["total"] == 2

    @pytest.mark.asyncio
    async def test_blinded_search_tolerates_non_object_meta(
        self, async_test_client, async_test_db, world
    ):
        world["tasks"][0].meta = ["kaufrecht"]
        world["tasks"][1].meta = None
        await async_test_db.commit()
        body = await _list(async_test_client, world["annotator"], world["project"].id, search="kaufrecht")
        assert body["total"] == 0
        listed = await _list(async_test_client, world["annotator"], world["project"].id)
        assert listed["total"] == 2
        for item in listed["items"]:
            assert item["meta"] == {}
