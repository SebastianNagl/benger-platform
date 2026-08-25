"""Participant access tier (benger "Entdecken" / joined projects) + share governance.

A consented share member, an entitled/enrolled student or an org member on a
windowless org exam holds the NARROW tier: the project lists/opens like an
annotator project (blinded task data, own annotations, my-tasks, cohort
leaderboard), while exports / evaluation config / share management stay 403.
Org projects: only ORG_ADMINs manage share links.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import Organization, OrganizationMembership, OrganizationRole, User
from project_models import (
    MarketplaceEntitlement,
    Project,
    ProjectOrganization,
    ProjectShareLink,
    ProjectShareMember,
    Task,
)

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _project(db, owner, *, private=True, kind=None, origin=None, archived=False,
                   tasks=1, public=False) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=private,
        is_public=public,
        public_role="ANNOTATOR" if public else None,
        kind=kind,
        origin=origin,
        is_archived=archived,
        label_config=EXAM_CONFIG,
        assignment_mode="open",
        evaluation_config={"judge": "secret-prompt"},
    )
    db.add(p)
    await db.flush()
    for i in range(tasks):
        db.add(Task(
            id=str(uuid.uuid4()), project_id=p.id, inner_id=i + 1,
            data={"sachverhalt": f"Fall {i}", "musterloesung": "GEHEIM"},
            created_by=owner.id,
        ))
    await db.commit()
    return p


async def _org(db, *members) -> Organization:
    """members: (user, role) tuples."""
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    db.add(org)
    await db.flush()
    for user, role in members:
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()), user_id=user.id, organization_id=org.id,
            role=role, is_active=True,
        ))
    await db.commit()
    return org


async def _attach(db, project, org, by):
    db.add(ProjectOrganization(id=str(uuid.uuid4()), project_id=project.id,
                               organization_id=org.id, assigned_by=by.id))
    await db.commit()


async def _share_member(db, project, owner, member, *, listed=False) -> ProjectShareLink:
    link = ProjectShareLink(
        id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=project.id,
        created_by=owner.id, password_hash="x", is_listed=listed,
    )
    db.add(link)
    await db.flush()
    db.add(ProjectShareMember(
        id=str(uuid.uuid4()), share_link_id=link.id, project_id=project.id,
        user_id=member.id, attempts=0, gdpr_consent_at=datetime.now(timezone.utc),
        consent_version="1",
    ))
    await db.commit()
    return link


async def _entitle(db, project, user, source="discovered") -> MarketplaceEntitlement:
    e = MarketplaceEntitlement(id=str(uuid.uuid4()), user_id=user.id,
                               project_id=project.id, source=source)
    db.add(e)
    await db.commit()
    return e


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# --------------------------------------------------------------- helpers ----

async def test_tier_helper_matrix(async_test_db):
    from routers.projects.helpers import (
        get_effective_project_role_async,
        get_project_access_tier_async,
    )
    db = async_test_db
    owner, member, entitled, stranger, annot = [await _user(db) for _ in range(5)]
    private = await _project(db, owner)
    await _share_member(db, private, owner, member)
    await _entitle(db, private, entitled)
    org = await _org(db, (annot, OrganizationRole.ANNOTATOR))
    org_exam = await _project(db, owner, private=False, kind="exam")
    await _attach(db, org_exam, org, owner)
    archived = await _project(db, owner, archived=True)
    await _share_member(db, archived, owner, member)

    assert await get_project_access_tier_async(db, owner, private.id) == "full"
    assert await get_project_access_tier_async(db, member, private.id) == "participant"
    assert await get_project_access_tier_async(db, entitled, private.id) == "participant"
    assert await get_project_access_tier_async(db, stranger, private.id) is None
    # Org ANNOTATOR on a windowless org exam: the exam carve-out denies the
    # full tier, the org-exam predicate grants the narrow one.
    assert await get_project_access_tier_async(db, annot, org_exam.id) == "participant"
    # Archived never grants the narrow tier.
    assert await get_project_access_tier_async(db, member, archived.id) is None
    assert await get_project_access_tier_async(db, member, "missing") is None

    # Participants resolve to ANNOTATOR so blinding / write gates apply.
    assert await get_effective_project_role_async(db, member, private) == "ANNOTATOR"
    assert await get_effective_project_role_async(db, stranger, private) is None


async def test_manage_shares_rule(async_test_db):
    from routers.projects.helpers import check_user_can_manage_shares_async
    db = async_test_db
    owner, admin, contrib, outsider = [await _user(db) for _ in range(4)]
    personal = await _project(db, owner)
    assert await check_user_can_manage_shares_async(db, owner, personal)
    assert not await check_user_can_manage_shares_async(db, outsider, personal)

    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN), (contrib, OrganizationRole.CONTRIBUTOR))
    org_project = await _project(db, contrib, private=False)
    await _attach(db, org_project, org, admin)
    assert await check_user_can_manage_shares_async(db, admin, org_project)
    # Creator fast-path deliberately absent for org projects.
    assert not await check_user_can_manage_shares_async(db, contrib, org_project)
    super_ = await _user(db, superadmin=True)
    assert await check_user_can_manage_shares_async(db, super_, org_project)


async def test_participant_project_ids(async_test_db):
    from routers.projects.helpers import get_participant_project_ids_async
    db = async_test_db
    owner, u = await _user(db), await _user(db)
    p_share = await _project(db, owner)
    await _share_member(db, p_share, owner, u)
    p_ent = await _project(db, owner)
    await _entitle(db, p_ent, u)
    p_archived = await _project(db, owner, archived=True)
    await _entitle(db, p_archived, u)
    own = await _project(db, u)
    await _entitle(db, own, u)  # creator: never "participant"
    org = await _org(db, (u, OrganizationRole.ANNOTATOR))
    p_org = await _project(db, owner, private=False, kind="exam")
    await _attach(db, p_org, org, owner)

    got = await get_participant_project_ids_async(db, u.id)
    assert got == {p_share.id: "share", p_ent.id: "entitlement", p_org.id: "org_exam"}


# ------------------------------------------------------------- endpoints ----

async def test_list_and_detail_tag_participants_and_strip_config(async_test_client, async_test_db):
    db = async_test_db
    owner, member = await _user(db), await _user(db)
    joined = await _project(db, owner)
    await _share_member(db, joined, owner, member)
    mine = await _project(db, member)

    with _as_user(member):
        r = await async_test_client.get("/api/projects/")
        assert r.status_code == 200, r.text
        rows = {p["id"]: p for p in r.json()["items"]}
        assert rows[joined.id]["access_tier"] == "participant"
        assert rows[joined.id]["participant_via"] == "share"
        assert rows[joined.id]["evaluation_config"] is None
        assert rows[mine.id]["access_tier"] == "full"
        assert rows[mine.id]["evaluation_config"] == {"judge": "secret-prompt"}

        r = await async_test_client.get(f"/api/projects/{joined.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_tier"] == "participant"
        assert body["participant_via"] == "share"
        assert body["effective_role"] == "ANNOTATOR"
        assert body["can_manage_shares"] is False
        assert body["evaluation_config"] is None and body["generation_config"] is None

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{joined.id}")
        assert r.json()["access_tier"] == "full"
        assert r.json()["can_manage_shares"] is True
        assert r.json()["evaluation_config"] == {"judge": "secret-prompt"}


async def test_participant_solver_endpoints_allowed_and_blinded(async_test_client, async_test_db):
    db = async_test_db
    owner, member, stranger = await _user(db), await _user(db), await _user(db)
    p = await _project(db, owner, tasks=2)
    await _share_member(db, p, owner, member)
    task_id = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().first()

    with _as_user(member):
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert r.status_code == 200, r.text
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        assert items and all("musterloesung" not in t["data"] for t in items)
        assert all(t["data"].get("sachverhalt") for t in items)

        r = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert r.status_code == 200, r.text
        assert "musterloesung" not in (r.json().get("task") or r.json())["data"]

        r = await async_test_client.get(f"/api/projects/tasks/{task_id}")
        assert r.status_code == 200, r.text
        assert "musterloesung" not in r.json()["data"]

        r = await async_test_client.get(
            f"/api/projects/tasks/{task_id}/annotations", params={"all_users": "true"}
        )
        assert r.status_code == 200, r.text

        r = await async_test_client.get(f"/api/projects/{p.id}/cohort-leaderboard")
        assert r.status_code == 200, r.text

        r = await async_test_client.get(f"/api/projects/{p.id}/participation")
        assert r.status_code == 200, r.text
        assert r.json()["tier"] == "participant" and r.json()["via"] == "share"
        assert r.json()["can_leave"] is True

    with _as_user(stranger):
        for path in (f"/api/projects/{p.id}", f"/api/projects/{p.id}/tasks",
                     f"/api/projects/{p.id}/next", f"/api/projects/tasks/{task_id}"):
            r = await async_test_client.get(path)
            assert r.status_code == 403, (path, r.status_code)


async def test_participant_denied_editor_surfaces(async_test_client, async_test_db):
    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner)
    await _share_member(db, p, owner, member)

    with _as_user(member):
        denied = [
            ("post", f"/api/projects/{p.id}/tasks/bulk-export", {"format": "json"}),
            ("post", f"/api/projects/{p.id}/exports", {}),
            ("get", f"/api/projects/{p.id}/shares", None),
            ("get", f"/api/projects/{p.id}/shares/roster", None),
            ("post", f"/api/projects/{p.id}/shares", {"password": "abcdefgh"}),
            ("get", f"/api/evaluations/projects/{p.id}/evaluation-config", None),
            ("patch", f"/api/projects/{p.id}", {"title": "x"}),
            ("delete", f"/api/projects/{p.id}", None),
        ]
        for method, path, body in denied:
            fn = getattr(async_test_client, method)
            r = await (fn(path, json=body) if body is not None else fn(path))
            assert r.status_code in (403, 404, 405), (method, path, r.status_code, r.text[:200])
            assert r.status_code != 200


async def test_all_users_ignored_for_annotators(async_test_client, async_test_db):
    from project_models import Annotation
    db = async_test_db
    owner, annot = await _user(db), await _user(db)
    org = await _org(db, (annot, OrganizationRole.ANNOTATOR), (owner, OrganizationRole.ORG_ADMIN))
    p = await _project(db, owner, private=False)
    await _attach(db, p, org, owner)
    task_id = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().first()
    for u in (owner, annot):
        db.add(Annotation(id=str(uuid.uuid4()), task_id=task_id, project_id=p.id,
                          completed_by=u.id, result=[{"v": u.id}]))
    await db.commit()

    with _as_user(annot):
        r = await async_test_client.get(
            f"/api/projects/tasks/{task_id}/annotations", params={"all_users": "true"}
        )
        assert r.status_code == 200, r.text
        assert {a["completed_by"] for a in r.json()} == {annot.id}
    with _as_user(owner):
        r = await async_test_client.get(
            f"/api/projects/tasks/{task_id}/annotations", params={"all_users": "true"}
        )
        assert {a["completed_by"] for a in r.json()} == {owner.id, annot.id}


async def test_leave_project(async_test_client, async_test_db):
    db = async_test_db
    owner, member, buyer, annot = [await _user(db) for _ in range(4)]
    p = await _project(db, owner)
    await _share_member(db, p, owner, member)
    await _entitle(db, p, member, source="discovered")
    await _entitle(db, p, buyer, source="purchase")
    org = await _org(db, (annot, OrganizationRole.ANNOTATOR))
    org_exam = await _project(db, owner, private=False, kind="exam")
    await _attach(db, org_exam, org, owner)

    with _as_user(member):
        r = await async_test_client.delete(f"/api/projects/{p.id}/participation")
        assert r.status_code == 204, r.text
        r = await async_test_client.get(f"/api/projects/{p.id}")
        assert r.status_code == 403
        r = await async_test_client.delete(f"/api/projects/{p.id}/participation")
        assert r.status_code == 404
    ent = (await db.execute(select(MarketplaceEntitlement).where(
        MarketplaceEntitlement.user_id == member.id))).scalar_one()
    assert ent.revoked_at is not None

    with _as_user(buyer):
        r = await async_test_client.get(f"/api/projects/{p.id}/participation")
        assert r.json()["can_leave"] is False
        assert r.json()["cannot_leave_reason"] == "entitlement_not_leavable"
        r = await async_test_client.delete(f"/api/projects/{p.id}/participation")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "entitlement_not_leavable"

    with _as_user(annot):
        r = await async_test_client.get(f"/api/projects/{org_exam.id}/participation")
        assert r.json()["via"] == "org_exam" and r.json()["can_leave"] is False
        r = await async_test_client.delete(f"/api/projects/{org_exam.id}/participation")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "org_membership"


async def test_share_governance_endpoints(async_test_client, async_test_db):
    db = async_test_db
    admin, contrib = await _user(db), await _user(db)
    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN), (contrib, OrganizationRole.CONTRIBUTOR))
    p = await _project(db, contrib, private=False)
    await _attach(db, p, org, admin)

    with _as_user(contrib):
        r = await async_test_client.post(f"/api/projects/{p.id}/shares", json={"password": "abcdefgh"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "share_admin_only"
    with _as_user(admin):
        r = await async_test_client.post(f"/api/projects/{p.id}/shares", json={"password": "abcdefgh"})
        assert r.status_code == 201, r.text
        share_id = r.json()["id"]
    with _as_user(contrib):
        # Editor tier keeps listing + roster.
        assert (await async_test_client.get(f"/api/projects/{p.id}/shares")).status_code == 200
        assert (await async_test_client.get(f"/api/projects/{p.id}/shares/roster")).status_code == 200
        r = await async_test_client.put(f"/api/projects/{p.id}/shares/{share_id}", json={"is_listed": True})
        assert r.status_code == 403
        r = await async_test_client.delete(f"/api/projects/{p.id}/shares/{share_id}")
        assert r.status_code == 403
    with _as_user(admin):
        r = await async_test_client.put(f"/api/projects/{p.id}/shares/{share_id}", json={"is_listed": True})
        assert r.status_code == 200
        r = await async_test_client.delete(f"/api/projects/{p.id}/shares/{share_id}")
        assert r.status_code == 204

    # Personal project: owner manages, outsider 403.
    owner = await _user(db)
    personal = await _project(db, owner)
    with _as_user(owner):
        r = await async_test_client.post(f"/api/projects/{personal.id}/shares", json={"password": "abcdefgh"})
        assert r.status_code == 201


async def test_discover_scopes(async_test_client, async_test_db):
    db = async_test_db
    owner, browser = await _user(db), await _user(db)
    student_exam = await _project(db, owner, kind="exam", origin="student")
    research = await _project(db, owner, private=False)  # kind NULL, origin NULL
    private_org = await _project(db, owner)  # private, NOT student-origin
    archived = await _project(db, owner, archived=True)
    org = await _org(db, (owner, OrganizationRole.ORG_ADMIN))
    await _attach(db, research, org, owner)
    await _attach(db, private_org, org, owner)
    for proj in (student_exam, research, private_org, archived):
        link = ProjectShareLink(id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=proj.id,
                                created_by=owner.id, password_hash="x", is_listed=True)
        db.add(link)
    await db.commit()

    with _as_user(browser):
        r = await async_test_client.get("/api/shares/discover")
        assert {x["project_id"] for x in r.json()} == {student_exam.id}
        r = await async_test_client.get("/api/shares/discover", params={"scope": "all"})
        by_id = {x["project_id"]: x for x in r.json()}
        # Private NON-student projects never surface in the global directory,
        # listed link or not (their title/owner is not public material);
        # private student-origin peer shares stay listable by design.
        assert set(by_id) == {student_exam.id, research.id}
        assert by_id[research.id]["is_org_project"] is True
        assert by_id[student_exam.id]["is_org_project"] is False


async def test_project_icon_and_editable_kind(async_test_client, async_test_db):
    """icon is set at creation and editable; kind is editable on EXPERT
    projects (enum-validated, incl. clearing to null), but a student-origin
    project's kind can never be changed (anti-un-flag contract)."""
    db = async_test_db
    owner = await _user(db)
    with _as_user(owner):
        r = await async_test_client.post(
            "/api/projects/",
            json={
                "title": "Mit Icon",
                "label_config": EXAM_CONFIG,
                "kind": "exam",
                "icon": "⚖️",
                "is_private": True,
            },
        )
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        assert r.json()["icon"] == "⚖️" and r.json()["kind"] == "exam"
        # Expert project: kind is editable in both directions + clearable.
        r = await async_test_client.patch(
            f"/api/projects/{pid}", json={"icon": "📚", "kind": "flashcard_collection"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["icon"] == "📚"
        assert r.json()["kind"] == "flashcard_collection"
        r = await async_test_client.patch(f"/api/projects/{pid}", json={"kind": None})
        assert r.status_code == 200, r.text
        assert r.json()["kind"] is None
        r = await async_test_client.patch(f"/api/projects/{pid}", json={"kind": "exam"})
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "exam"
        # Unknown values are rejected by the update schema.
        r = await async_test_client.patch(f"/api/projects/{pid}", json={"kind": "leaderboard"})
        assert r.status_code == 422, r.text
        r = await async_test_client.get("/api/projects/")
        assert next(p for p in r.json()["items"] if p["id"] == pid)["icon"] == "📚"

        # Student-origin project: kind CHANGES are 403; echoing the current
        # value back is tolerated (clients PATCH whole objects).
        r = await async_test_client.post(
            "/api/projects/",
            json={
                "title": "Studentische Klausur",
                "label_config": EXAM_CONFIG,
                "kind": "exam",
                "origin": "student",
                "is_private": True,
            },
        )
        assert r.status_code in (200, 201), r.text
        sid = r.json()["id"]
        r = await async_test_client.patch(f"/api/projects/{sid}", json={"kind": None})
        assert r.status_code == 403, r.text
        r = await async_test_client.patch(f"/api/projects/{sid}", json={"kind": "exam"})
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "exam"


async def test_participant_enrichment_and_search_hardening(async_test_client, async_test_db):
    """Blinded callers get no cross-user identities and no raw-JSON search
    oracle over the blinded Musterlösung; editors keep both."""
    from project_models import Annotation

    db = async_test_db
    owner, member, other = await _user(db), await _user(db), await _user(db)
    p = await _project(db, owner, tasks=1)
    await _share_member(db, p, owner, member)
    await _share_member(db, p, owner, other)
    task_id = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().first()
    for u in (member, other):
        db.add(Annotation(id=str(uuid.uuid4()), task_id=task_id, project_id=p.id,
                          completed_by=u.id, result=[{"v": 1}]))
    await db.commit()

    with _as_user(member):
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert r.status_code == 200, r.text
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        # Only the caller appears in annotators; no other identities, no emails.
        for t in items:
            assert {a["id"] for a in t["annotators"]} <= {member.id}
            assert all("user_email" not in a or a["user_id"] == member.id for a in t["assignments"])
        # Raw-JSON search over the blinded key is not an oracle: a prefix of
        # the Musterlösung must NOT match for a blinded caller...
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks", params={"search": "GEHEIM"})
        body = r.json()
        total = body["total"] if isinstance(body, dict) and "total" in body else len(body["items"])
        assert total == 0
        # ...while a visible-field term still matches.
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks", params={"search": "Fall"})
        body = r.json()
        total = body["total"] if isinstance(body, dict) and "total" in body else len(body["items"])
        assert total == 1

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks", params={"search": "GEHEIM"})
        body = r.json()
        total = body["total"] if isinstance(body, dict) and "total" in body else len(body["items"])
        assert total == 1
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        assert {a["id"] for t in items for a in t["annotators"]} == {member.id, other.id}


async def test_participant_skip_blocked_on_global_skip_queue(async_test_client, async_test_db):
    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner, tasks=1)
    p.skip_queue = "ignore_skipped"
    await _share_member(db, p, owner, member)
    await db.commit()
    task_id = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().first()
    with _as_user(member):
        r = await async_test_client.post(f"/api/projects/{p.id}/tasks/{task_id}/skip", json={})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "participant_skip_disabled"
    # requeue mode: participants may skip (self-scoped).
    p.skip_queue = "requeue_for_others"
    await db.commit()
    with _as_user(member):
        r = await async_test_client.post(f"/api/projects/{p.id}/tasks/{task_id}/skip", json={})
        assert r.status_code in (200, 201), r.text


async def test_stale_org_context_falls_back_to_participant_list(async_test_client, async_test_db):
    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner)
    await _share_member(db, p, owner, member)
    with _as_user(member):
        r = await async_test_client.get(
            "/api/projects/", headers={"X-Organization-Context": "org-i-never-joined"}
        )
        assert r.status_code == 200, r.text
        rows = {x["id"]: x for x in r.json()["items"]}
        assert rows[p.id]["access_tier"] == "participant"
    # Without participant standing the stale context still 403s (old behavior).
    stranger = await _user(db)
    with _as_user(stranger):
        r = await async_test_client.get(
            "/api/projects/", headers={"X-Organization-Context": "org-i-never-joined"}
        )
        assert r.status_code == 403


async def test_double_join_via_two_links_keeps_one_membership(async_test_client, async_test_db):
    from auth_module.user_service import get_password_hash

    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner)
    tokens = []
    for _ in range(2):
        link = ProjectShareLink(id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=p.id,
                                created_by=owner.id, password_hash=get_password_hash("abcdefgh"))
        db.add(link)
        tokens.append(link.token)
    await db.commit()
    with _as_user(member):
        for tok in tokens:
            r = await async_test_client.post(
                f"/api/shares/{tok}/join", json={"password": "abcdefgh", "gdpr_consent": True}
            )
            assert r.status_code == 200, r.text
        # One membership row; every participant surface keeps working.
        rows = (await db.execute(select(ProjectShareMember).where(
            ProjectShareMember.project_id == p.id, ProjectShareMember.user_id == member.id
        ))).scalars().all()
        assert len(rows) == 1
        assert (await async_test_client.get(f"/api/projects/{p.id}")).status_code == 200


async def test_icon_must_be_emoji(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    with _as_user(owner):
        r = await async_test_client.post(
            "/api/projects/",
            json={"title": "X", "label_config": EXAM_CONFIG, "icon": "<script>", "is_private": True},
        )
        assert r.status_code == 422
        r = await async_test_client.post(
            "/api/projects/",
            json={"title": "X", "label_config": EXAM_CONFIG, "icon": "👩‍⚖️", "is_private": True},
        )
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        assert r.json()["icon"] == "👩‍⚖️"
        r = await async_test_client.patch(f"/api/projects/{pid}", json={"icon": "abc"})
        assert r.status_code == 422
