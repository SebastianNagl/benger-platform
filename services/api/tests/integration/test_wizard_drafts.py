"""Creation-wizard drafts (CORE 2.55, migration 141).

A draft is a real project, private and without organization rows, that the
creation wizard makes when the teacher leaves step 1. Pinned here: the six
routes (create with target validation and ``client_key`` idempotency, list,
read, save with the version check and the size limit, finish in one
transaction, discard), the task-sync routes, and that a draft is absent from
every list and count and refused by the share, access-key and visibility
routes while its creator still opens it.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from models import OrganizationRole, ProjectPurgeJob
from project_models import (
    Project,
    ProjectOrganization,
    ProjectWizardDraft,
    Task,
    TaskRubric,
)
from tests.integration.test_group_visibility import _as_user, _group, _org, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE = "/api/projects/wizard-drafts"
EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)


def _body(**extra):
    return {
        "title": "Klausur Draft",
        "kind": "exam",
        "label_config": EXAM_CONFIG,
        "icon": "📝",
        "client_key": str(uuid.uuid4()),
        "state": {"title": "Klausur Draft"},
        "step_id": "projectInfo",
        **extra,
    }


async def _create(client, **extra):
    r = await client.post(BASE, json=_body(**extra))
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _org_world(db):
    teacher, colleague, student = [await _user(db) for _ in range(3)]
    org = await _org(
        db,
        (teacher, OrganizationRole.CONTRIBUTOR),
        (colleague, OrganizationRole.ORG_ADMIN),
        (student, OrganizationRole.ANNOTATOR),
    )
    group = await _group(db, org, "Lehrstuhl", (teacher, False))
    return {"teacher": teacher, "colleague": colleague, "student": student, "org": org,
            "group": group}


def _queue():
    sent = []

    def _send(name, args=None, **_kw):
        assert name == "tasks.purge_project"
        sent.append(args[0])
        return SimpleNamespace(id=f"celery-{args[0]}")

    return sent, patch("routers.projects.crud.send_task_safe", side_effect=_send)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_makes_a_private_flagged_project_without_org_rows(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _org_world(db)
    with _as_user(w["teacher"]):
        draft = await _create(
            async_test_client,
            target_organization_id=w["org"].id,
            target_group_id=w["group"].id,
        )
    project = await db.get(Project, draft["project_id"])
    await db.refresh(project)
    assert project.is_wizard_draft is True
    assert project.is_private is True and project.is_public is False
    assert project.kind == "exam" and project.label_config == EXAM_CONFIG
    rows = (
        await db.execute(
            select(ProjectOrganization).where(ProjectOrganization.project_id == project.id)
        )
    ).scalars().all()
    assert rows == []
    assert draft["target_organization_id"] == w["org"].id
    assert draft["target_group_id"] == w["group"].id
    assert draft["state_version"] == 1 and draft["state"] == {"title": "Klausur Draft"}
    touched = datetime.fromisoformat(draft["touched_at"])
    assert datetime.fromisoformat(draft["expires_at"]) - touched == timedelta(days=30)


async def test_create_is_idempotent_per_client_key(async_test_client, async_test_db):
    db = async_test_db
    teacher = await _user(db)
    key = str(uuid.uuid4())
    with _as_user(teacher):
        first = await async_test_client.post(BASE, json=_body(client_key=key))
        again = await async_test_client.post(BASE, json=_body(client_key=key, title="Other"))
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["project_id"] == again.json()["project_id"]
    count = (
        await db.execute(
            select(ProjectWizardDraft).where(ProjectWizardDraft.created_by == teacher.id)
        )
    ).scalars().all()
    assert len(count) == 1


async def test_a_racing_create_with_the_same_key_returns_the_first_draft(
    async_test_client, async_test_db
):
    """Two "Next" requests with one key: the second passes the existence
    check before the first commits, its insert hits the unique key, and it
    answers with the first draft instead of a 500."""
    import routers.projects.wizard_drafts as drafts_router

    db = async_test_db
    teacher = await _user(db)
    key = str(uuid.uuid4())
    with _as_user(teacher):
        first = await _create(async_test_client, client_key=key)
        real = drafts_router._existing_for_key
        calls = []

        async def _miss_once(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return None
            return await real(*args, **kwargs)

        with patch.object(drafts_router, "_existing_for_key", side_effect=_miss_once):
            r = await async_test_client.post(BASE, json=_body(client_key=key))
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] == first["project_id"]
    assert len(calls) == 2


async def test_create_validates_the_target_like_project_create(async_test_client, async_test_db):
    db = async_test_db
    w = await _org_world(db)
    stranger = await _user(db)
    other_org = await _org(db, (stranger, OrganizationRole.ORG_ADMIN))
    foreign_group = await _group(db, other_org, "Fremd", (stranger, True))
    c = async_test_client
    with _as_user(stranger):
        r = await c.post(BASE, json=_body(target_organization_id=w["org"].id))
        assert r.status_code == 403
    with _as_user(w["student"]):
        r = await c.post(BASE, json=_body(target_organization_id=w["org"].id))
        assert r.status_code == 403
    with _as_user(w["teacher"]):
        r = await c.post(
            BASE,
            json=_body(target_organization_id=w["org"].id, target_group_id=foreign_group.id),
        )
        assert r.status_code == 400
        r = await c.post(BASE, json=_body(target_group_id=w["group"].id))
        assert r.status_code == 400
        r = await c.post(BASE, json=_body(target_organization_id=str(uuid.uuid4())))
        assert r.status_code == 404
        r = await c.post(BASE, json=_body(label_config="<View><Broken"))
        assert r.status_code == 422
    drafts = (
        await db.execute(select(ProjectWizardDraft.project_id))
    ).scalars().all()
    projects = (
        await db.execute(select(Project.id).where(Project.created_by.in_(
            [stranger.id, w["student"].id, w["teacher"].id]
        )))
    ).scalars().all()
    assert not set(projects) & set(drafts)


# ---------------------------------------------------------------------------
# Read, list, save
# ---------------------------------------------------------------------------


async def test_read_and_list_are_for_the_creator(async_test_client, async_test_db):
    db = async_test_db
    teacher, other = await _user(db), await _user(db)
    admin = await _user(db, superadmin=True)
    c = async_test_client
    with _as_user(teacher):
        mine = await _create(c)
        listed = (await c.get(BASE)).json()["items"]
        assert [d["project_id"] for d in listed] == [mine["project_id"]]
        assert "state" not in listed[0]
        r = await c.get(f"/api/projects/{mine['project_id']}/wizard-draft")
        assert r.status_code == 200 and r.json()["state"] == {"title": "Klausur Draft"}
        # The creator opens the draft project like any own private project.
        assert (await c.get(f"/api/projects/{mine['project_id']}")).json()["is_wizard_draft"]
    with _as_user(other):
        assert (await c.get(BASE)).json()["items"] == []
        r = await c.get(f"/api/projects/{mine['project_id']}/wizard-draft")
        assert r.status_code == 403
        assert (await c.get(f"/api/projects/{mine['project_id']}")).status_code == 403
    with _as_user(admin):
        # Superadmins list only their own drafts but may open any.
        assert (await c.get(BASE)).json()["items"] == []
        r = await c.get(f"/api/projects/{mine['project_id']}/wizard-draft")
        assert r.status_code == 200
    regular = Project(id=str(uuid.uuid4()), title="Normal", created_by=teacher.id, is_private=True)
    db.add(regular)
    await db.commit()
    with _as_user(teacher):
        r = await c.get(f"/api/projects/{regular.id}/wizard-draft")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "not_wizard_draft"


async def test_save_checks_the_version_and_size(async_test_client, async_test_db):
    db = async_test_db
    teacher = await _user(db)
    c = async_test_client
    with _as_user(teacher):
        draft = await _create(c)
        url = f"/api/projects/{draft['project_id']}/wizard-draft"
        r = await c.put(url, json={"state": {"step": 2}, "step_id": "dataImport", "if_version": 1})
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["state_version"] == 2 and saved["step_id"] == "dataImport"
        assert saved["touched_at"] >= draft["touched_at"]
        # A second tab still on version 1 is told the draft changed.
        r = await c.put(url, json={"state": {"step": 9}, "if_version": 1})
        assert r.status_code == 409
        assert r.json()["detail"] == {
            "code": "draft_version_conflict",
            "message": "The draft was changed elsewhere",
            "current_version": 2,
        }
        big = {"blob": "x" * (2 * 1024 * 1024 + 10)}
        r = await c.put(url, json={"state": big, "if_version": 2})
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "draft_state_too_large"
        current = (await c.get(url)).json()
        assert current["state"] == {"step": 2} and current["state_version"] == 2


async def test_save_moves_the_target_with_validation(async_test_client, async_test_db):
    db = async_test_db
    w = await _org_world(db)
    other_org = await _org(db, (w["colleague"], OrganizationRole.ORG_ADMIN))
    c = async_test_client
    with _as_user(w["teacher"]):
        draft = await _create(c)
        url = f"/api/projects/{draft['project_id']}/wizard-draft"
        r = await c.put(url, json={
            "if_version": 1, "target_organization_id": w["org"].id,
            "target_group_id": w["group"].id,
        })
        assert r.status_code == 200
        assert r.json()["target_group_id"] == w["group"].id
        r = await c.put(url, json={"if_version": 2, "target_organization_id": other_org.id})
        assert r.status_code == 403
        r = await c.put(url, json={"if_version": 2, "target_organization_id": None})
        assert r.status_code == 200
        assert r.json()["target_organization_id"] is None
        assert r.json()["target_group_id"] is None


# ---------------------------------------------------------------------------
# Finish
# ---------------------------------------------------------------------------


async def test_finish_applies_visibility_and_attachments_in_one_step(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _org_world(db)
    c = async_test_client
    calls = []
    with _as_user(w["teacher"]):
        draft = await _create(
            c, target_organization_id=w["org"].id, target_group_id=w["group"].id
        )
        pid = draft["project_id"]
        body = {
            "client_key": draft["client_key"],
            "visibility": "organization",
            "organization_attachments": [
                {"organization_id": w["org"].id, "group_id": w["group"].id}
            ],
        }

        def _notify(**kwargs):
            # Runs after the commit: the project is already finished.
            calls.append(kwargs)

        with patch("routers.projects.crud._notify_project_created_sync", side_effect=_notify):
            r = await c.post(f"/api/projects/{pid}/wizard-draft/finish", json=body)
        assert r.status_code == 200, r.text
        project = r.json()
        assert project["is_wizard_draft"] is False and project["is_private"] is False
        assert [o["id"] for o in project["organizations"]] == [w["org"].id]
        assert project["organizations"][0]["group_id"] == w["group"].id
        assert calls and calls[0]["organization_id"] == w["org"].id
        assert calls[0]["project_id"] == pid

        # A second click (same wizard session) returns the project.
        again = await c.post(f"/api/projects/{pid}/wizard-draft/finish", json=body)
        assert again.status_code == 200 and again.json()["id"] == pid
        # Another session, or a second finish of a regular project: 409.
        other = await c.post(
            f"/api/projects/{pid}/wizard-draft/finish",
            json={**body, "client_key": "someone-else"},
        )
        assert other.status_code == 409
        # The finished project is not a draft any more for the draft routes.
        assert (await c.get(f"/api/projects/{pid}/wizard-draft")).status_code == 409
        assert pid not in [d["project_id"] for d in (await c.get(BASE)).json()["items"]]
    row = await db.get(ProjectWizardDraft, pid)
    await db.refresh(row)
    assert row.finished_at is not None and row.state is None
    # The organization's admin now sees the exam in their list.
    await db.refresh(w["colleague"])
    with _as_user(w["colleague"]):
        ids = [p["id"] for p in (await c.get("/api/projects/")).json()["items"]]
        assert pid in ids


async def test_finish_revalidates_the_creators_rights(async_test_client, async_test_db):
    db = async_test_db
    w = await _org_world(db)
    c = async_test_client
    with _as_user(w["teacher"]):
        draft = await _create(c, target_organization_id=w["org"].id)
    # While the draft waited, the teacher became an annotator of the org.
    from models import OrganizationMembership

    membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == w["teacher"].id,
                OrganizationMembership.organization_id == w["org"].id,
            )
        )
    ).scalar_one()
    membership.role = OrganizationRole.ANNOTATOR
    await db.commit()
    with _as_user(w["teacher"]):
        r = await c.post(
            f"/api/projects/{draft['project_id']}/wizard-draft/finish",
            json={
                "client_key": draft["client_key"],
                "visibility": "organization",
                "organization_attachments": [{"organization_id": w["org"].id}],
            },
        )
    assert r.status_code == 403
    project = await db.get(Project, draft["project_id"])
    await db.refresh(project)
    assert project.is_wizard_draft is True and project.is_private is True
    rows = (
        await db.execute(
            select(ProjectOrganization).where(ProjectOrganization.project_id == project.id)
        )
    ).scalars().all()
    assert rows == []


async def test_finish_private_and_public(async_test_client, async_test_db):
    db = async_test_db
    teacher = await _user(db)
    c = async_test_client
    with _as_user(teacher):
        a = await _create(c)
        r = await c.post(
            f"/api/projects/{a['project_id']}/wizard-draft/finish",
            json={"client_key": a["client_key"], "visibility": "private"},
        )
        assert r.status_code == 200
        assert r.json()["is_private"] is True and r.json()["is_wizard_draft"] is False
        b = await _create(c)
        r = await c.post(
            f"/api/projects/{b['project_id']}/wizard-draft/finish",
            json={"client_key": b["client_key"], "visibility": "public",
                  "public_role": "CONTRIBUTOR"},
        )
        assert r.status_code == 200
        assert r.json()["is_public"] is True and r.json()["public_role"] == "CONTRIBUTOR"
        r = await c.post(
            f"/api/projects/{b['project_id']}/wizard-draft/finish",
            json={"client_key": b["client_key"], "visibility": "organization"},
        )
        # Already finished with that key: the project, not a new finish.
        assert r.status_code == 200 and r.json()["is_public"] is True
        c2 = await _create(c)
        r = await c.post(
            f"/api/projects/{c2['project_id']}/wizard-draft/finish",
            json={"client_key": c2["client_key"], "visibility": "organization",
                  "organization_attachments": []},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Discard and expiry
# ---------------------------------------------------------------------------


async def test_discard_soft_deletes_and_queues_the_purge(async_test_client, async_test_db):
    db = async_test_db
    teacher, other = await _user(db), await _user(db)
    c = async_test_client
    sent, queue = _queue()
    with _as_user(teacher):
        a = await _create(c)
        b = await _create(c)
    with _as_user(other), queue:
        assert (await c.delete(f"/api/projects/{a['project_id']}/wizard-draft")).status_code == 403
    with _as_user(teacher), queue:
        r = await c.delete(f"/api/projects/{a['project_id']}/wizard-draft")
        assert r.status_code == 200, r.text
        assert r.json()["purge_job"]["status"] == "pending"
        # DELETE /projects/{id} on a draft discards it the same way.
        r = await c.delete(f"/api/projects/{b['project_id']}")
        assert r.status_code == 200
        assert r.json()["purge_job"]["project_id"] == b["project_id"]
        # A discarded draft is gone for the draft routes and the list.
        for pid in (a["project_id"], b["project_id"]):
            r = await c.get(f"/api/projects/{pid}/wizard-draft")
            assert r.status_code == 404 and r.json()["detail"]["code"] == "draft_expired"
            r = await c.post(
                f"/api/projects/{pid}/wizard-draft/finish",
                json={"client_key": a["client_key"], "visibility": "private"},
            )
            assert r.status_code == 404 and r.json()["detail"]["code"] == "draft_expired"
        assert (await c.get(BASE)).json()["items"] == []
        # Its client key cannot bring it back.
        r = await c.post(BASE, json=_body(client_key=a["client_key"]))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "draft_discarded"
    jobs = (
        await db.execute(
            select(ProjectPurgeJob).where(
                ProjectPurgeJob.project_id.in_([a["project_id"], b["project_id"]])
            )
        )
    ).scalars().all()
    assert {j.project_id for j in jobs} == {a["project_id"], b["project_id"]}
    assert {j.requested_by for j in jobs} == {teacher.id}
    assert sorted(sent) == sorted(j.id for j in jobs)


async def test_discard_survives_an_unavailable_queue(async_test_client, async_test_db):
    db = async_test_db
    teacher = await _user(db)
    c = async_test_client
    with _as_user(teacher):
        a = await _create(c)
        with patch("routers.projects.crud.send_task_safe", side_effect=ConnectionError("down")):
            r = await c.delete(f"/api/projects/{a['project_id']}/wizard-draft")
    assert r.status_code == 200 and r.json()["purge_job"] is None
    project = await db.get(Project, a["project_id"])
    await db.refresh(project)
    assert project.deleted_at is not None


# ---------------------------------------------------------------------------
# Hidden everywhere, refused where it would leave the creator
# ---------------------------------------------------------------------------


async def test_a_draft_is_absent_from_every_list_and_refused_by_sharing(
    async_test_client, async_test_db
):
    db = async_test_db
    teacher = await _user(db)
    admin = await _user(db, superadmin=True)
    c = async_test_client
    with _as_user(teacher):
        draft = await _create(c)
        pid = draft["project_id"]
    db.add(Task(id=str(uuid.uuid4()), project_id=pid, inner_id=1,
                data={"sachverhalt": "Fall"}, created_by=teacher.id))
    regular = Project(id=str(uuid.uuid4()), title="Normal", created_by=teacher.id, is_private=True)
    db.add(regular)
    await db.commit()

    from routers.access_keys import _check_personal_projects
    from routers.projects.helpers import get_accessible_project_ids_async

    for user in (teacher, admin):
        with _as_user(user) as auth:
            ids = [p["id"] for p in (await c.get("/api/projects/?page_size=500")).json()["items"]]
            assert pid not in ids
            r = await c.get("/api/projects/?page_size=500&include_all_private=true")
            assert pid not in [p["id"] for p in r.json()["items"]]
            assert pid not in (await get_accessible_project_ids_async(db, auth) or [])
            data = (await c.get("/api/data/?page_size=100")).json()
            assert pid not in {t.get("project_id") for t in data.get("items", [])}
    with _as_user(teacher) as auth:
        assert regular.id in [p["id"] for p in (await c.get("/api/projects/")).json()["items"]]
        stats = (await c.get("/api/dashboard/stats")).json()
        assert stats["project_count"] == 1
        # Refused: a share link, a personal key scoped to it, a visibility change.
        r = await c.post(f"/api/projects/{pid}/shares", json={"password": "geheim123"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "wizard_draft"
        r = await c.patch(f"/api/projects/{pid}/visibility", json={"is_public": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "wizard_draft"
        with pytest.raises(HTTPException) as exc:
            await _check_personal_projects(db, auth, [pid])
        assert exc.value.status_code == 422
        await _check_personal_projects(db, auth, [regular.id])
    with _as_user(admin):
        r = await c.get("/api/projects/?page_size=500&only_deleted=true")
        assert pid not in [p["id"] for p in r.json()["items"]]


async def test_a_draft_is_absent_from_v1(async_test_client, async_test_db):
    from services import api_key_service as svc
    from tests.fixtures.v1 import bearer, ids, v1_auth

    db = async_test_db
    teacher = await _user(db)
    with _as_user(teacher):
        draft = await _create(async_test_client)
    regular = Project(id=str(uuid.uuid4()), title="Normal", created_by=teacher.id, is_private=True)
    db.add(regular)
    await db.flush()
    _, plain = await svc.create_personal_key(
        db, teacher.id, {"name": "mine", "scopes": ["projects:read"]}
    )
    with v1_auth(db):
        r = await async_test_client.get("/api/v1/projects", headers=bearer(plain))
    assert r.status_code == 200, r.text
    listed = ids(r.json()["items"])
    assert regular.id in listed and draft["project_id"] not in listed


async def test_share_links_of_a_draft_do_not_resolve(async_test_client, async_test_db):
    from project_models import ProjectShareLink

    db = async_test_db
    teacher, student = await _user(db), await _user(db)
    with _as_user(teacher):
        draft = await _create(async_test_client)
    link = ProjectShareLink(
        id=str(uuid.uuid4()), token=f"tok-{uuid.uuid4().hex}", project_id=draft["project_id"],
        created_by=teacher.id, password_hash="x",
    )
    db.add(link)
    await db.commit()
    with _as_user(student):
        r = await async_test_client.get(f"/api/shares/{link.token}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Task sync
# ---------------------------------------------------------------------------


async def test_task_routes_report_hashes_and_replace_a_changed_row(
    async_test_client, async_test_db
):
    db = async_test_db
    teacher = await _user(db)
    c = async_test_client
    with _as_user(teacher):
        draft = await _create(c)
    pid = draft["project_id"]
    # Two import runs: the second one numbered its task 1 again, so the
    # list follows the stored wizard position, not inner_id.
    t2 = Task(id=str(uuid.uuid4()), project_id=pid, inner_id=1,
              data={"sachverhalt": "Fall 2"},
              meta={"wizard_row_hash": "h2", "wizard_row_index": 1},
              created_by=teacher.id)
    t1 = Task(id=str(uuid.uuid4()), project_id=pid, inner_id=1,
              data={"sachverhalt": "Fall 1", "musterloesung": "alt"},
              meta={"wizard_row_hash": "h1", "wizard_row_index": 0}, created_by=teacher.id)
    manual = Task(id=str(uuid.uuid4()), project_id=pid, inner_id=7,
                  data={"sachverhalt": "von Hand"}, created_by=teacher.id)
    db.add_all([t2, t1, manual])
    await db.flush()
    checked = TaskRubric(
        id=str(uuid.uuid4()), task_id=t1.id, project_id=pid, status="active",
        review_state="confirmed",
        criteria={"s01": {"name": "A", "rubric": "r", "max_score": 10}}, total_points=10,
    )
    candidate = TaskRubric(
        id=str(uuid.uuid4()), task_id=t1.id, project_id=pid, status="candidate",
        criteria={"s01": {"name": "A", "rubric": "r", "max_score": 10}}, total_points=10,
    )
    db.add_all([checked, candidate])
    await db.commit()

    with _as_user(teacher):
        listed = (await c.get(f"/api/projects/{pid}/wizard-draft/tasks")).json()["items"]
        assert [(t["id"], t["row_index"], t["row_hash"]) for t in listed] == [
            (t1.id, 0, "h1"), (t2.id, 1, "h2"), (manual.id, None, None),
        ]
        assert {s["id"]: s["review_state"] for s in listed[0]["sheets"]} == {
            checked.id: "confirmed", candidate.id: None,
        }
        assert listed[1]["sheets"] == [] and listed[0]["generating"] == 0

        r = await c.put(
            f"/api/projects/{pid}/wizard-draft/tasks/{t1.id}",
            json={"data": {"sachverhalt": "Fall 1 (korrigiert)"}, "row_hash": "h1b"},
        )
        assert r.status_code == 200, r.text
        assert sorted(r.json()["archived_sheet_ids"]) == sorted([checked.id, candidate.id])
        r = await c.put(
            f"/api/projects/{pid}/wizard-draft/tasks/{str(uuid.uuid4())}",
            json={"data": {"x": 1}, "row_hash": "h"},
        )
        assert r.status_code == 404
    await db.refresh(t1)
    # Replaced, not merged: the dropped key is gone.
    assert t1.data == {"sachverhalt": "Fall 1 (korrigiert)"}
    assert t1.meta == {"wizard_row_hash": "h1b", "wizard_row_index": 0}
    for rubric in (checked, candidate):
        await db.refresh(rubric)
        assert rubric.status == "archived"
    await db.refresh(t2)
    assert t2.meta == {"wizard_row_hash": "h2", "wizard_row_index": 1}


async def test_task_routes_are_for_drafts_only(async_test_client, async_test_db):
    db = async_test_db
    teacher, other = await _user(db), await _user(db)
    regular = Project(id=str(uuid.uuid4()), title="Normal", created_by=teacher.id, is_private=True)
    db.add(regular)
    await db.commit()
    with _as_user(teacher):
        draft = await _create(async_test_client)
        r = await async_test_client.get(f"/api/projects/{regular.id}/wizard-draft/tasks")
        assert r.status_code == 409
    with _as_user(other):
        r = await async_test_client.get(f"/api/projects/{draft['project_id']}/wizard-draft/tasks")
        assert r.status_code == 403


async def test_import_into_a_draft_keeps_row_positions_and_demotes_unchecked_sheets(
    async_test_client, async_test_db
):
    """The wizard imports its rows with ``id`` = position + 1 and the row's
    hash and position in ``meta``. A draft that requires the check (the
    overlay switches it on right after the draft is created, before the first
    import) imports an unchecked active sheet as a candidate, so an imported
    file cannot bring an unchecked sheet into use."""
    import io
    import json

    from import_stream import run_nested_import

    db = async_test_db
    teacher = await _user(db)
    teacher_id = teacher.id
    with _as_user(teacher):
        draft = await _create(async_test_client)
    pid = draft["project_id"]
    project = await db.get(Project, pid)
    project.rubric_review_required = True
    await db.commit()

    sheet = {
        "title": "Aus der Datei", "status": "active", "source": "human",
        "criteria": {"s01": {"name": "A", "rubric": "r", "max_score": 10}},
        "total_points": 10,
    }
    rows = [
        {"id": 4, "data": {"sachverhalt": "Fall 4"},
         "meta": {"wizard_row_hash": "h4", "wizard_row_index": 3}, "rubrics": [sheet]},
        {"id": 5, "data": {"sachverhalt": "Fall 5"},
         "meta": {"wizard_row_hash": "h5", "wizard_row_index": 4}},
    ]
    body = json.dumps({"data": rows}).encode()
    await db.run_sync(lambda s: run_nested_import(s, pid, io.BytesIO(body), teacher_id))

    tasks = (
        await db.execute(select(Task).where(Task.project_id == pid).order_by(Task.inner_id))
    ).scalars().all()
    assert [(t.inner_id, t.meta["wizard_row_index"], t.meta["wizard_row_hash"]) for t in tasks] == [
        (4, 3, "h4"), (5, 4, "h5"),
    ]
    assert all(t.source_task_id is None for t in tasks)
    statuses = (
        await db.execute(select(TaskRubric.status).where(TaskRubric.project_id == pid))
    ).scalars().all()
    assert statuses == ["candidate"]
    await db.refresh(teacher)
    with _as_user(teacher):
        listed = (await async_test_client.get(f"/api/projects/{pid}/wizard-draft/tasks")).json()
    assert [(t["row_index"], t["row_hash"]) for t in listed["items"]] == [(3, "h4"), (4, "h5")]
    assert listed["items"][0]["sheets"][0]["status"] == "candidate"
