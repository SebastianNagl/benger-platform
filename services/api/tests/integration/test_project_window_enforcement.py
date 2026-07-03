"""Integration tests for project access-window enforcement (real PostgreSQL).

Two layers:
  1. the enforce wrappers ``enforce_project_read_window(_async)`` /
     ``enforce_project_write_window(_async)`` — owner/admin/contributor exempt,
     the annotator access group gated, across upcoming/open/closed/none.
  2. one HTTP endpoint (``GET /api/projects/tasks/{id}``) proving the read-gate
     is actually wired into the handler (403 for a non-editor pre-open, 200 for
     the owner).

The editor-exemption is ``check_user_can_edit_project`` (creator / superadmin /
ORG_ADMIN / CONTRIBUTOR); everyone else is the "access group".
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task
from routers.projects.helpers import (
    enforce_project_read_window_async,
    enforce_project_write_window_async,
)


def _uid():
    return str(uuid.uuid4())


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Test User",
        is_superadmin=is_superadmin,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db):
    o = Organization(
        id=_uid(),
        name=f"org-{_uid()[:8]}",
        slug=f"org-{_uid()[:8]}",
        display_name="Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(o)
    await db.flush()
    return o


async def _add_membership(db, user_id, org_id, role):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _make_project(db, creator_id, org, *, state):
    now = datetime.now(timezone.utc)
    bounds = {
        "upcoming": (now + timedelta(hours=1), now + timedelta(hours=3)),
        "open": (now - timedelta(hours=1), now + timedelta(hours=1)),
        "closed": (now - timedelta(hours=3), now - timedelta(hours=1)),
        "none": (None, None),
    }[state]
    p = Project(
        id=_uid(),
        title="Windowed Project",
        created_by=creator_id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode="open",
        window_start_at=bounds[0],
        window_end_at=bounds[1],
    )
    db.add(p)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(), project_id=p.id, organization_id=org.id, assigned_by=creator_id
        )
    )
    await db.flush()
    return p


async def _make_task(db, project_id):
    t = Task(id=_uid(), project_id=project_id, data={"text": "hello"}, inner_id=1)
    db.add(t)
    await db.flush()
    return t


@contextmanager
def _as_user(db_user):
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


async def _raised_code(coro):
    """Return the 403 detail code if the enforce coro raised, else None."""
    try:
        await coro
        return None
    except HTTPException as e:
        assert e.status_code == 403
        return e.detail["code"] if isinstance(e.detail, dict) else e.detail


# ── enforce wrappers ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_read_gate_blocks_access_group_pre_open_only(async_test_db):
    db = async_test_db
    org = await _make_org(db)
    owner = await _make_user(db)
    await _add_membership(db, owner.id, org.id, "ORG_ADMIN")
    annot = await _make_user(db)
    await _add_membership(db, annot.id, org.id, "ANNOTATOR")

    # upcoming: annotator blocked, owner exempt
    up = await _make_project(db, owner.id, org, state="upcoming")
    assert await _raised_code(enforce_project_read_window_async(db, annot, up)) == (
        "project_window_upcoming"
    )
    assert await _raised_code(enforce_project_read_window_async(db, owner, up)) is None

    # open / closed / none: reads allowed for the access group (closed = review)
    for state in ("open", "closed", "none"):
        p = await _make_project(db, owner.id, org, state=state)
        assert await _raised_code(enforce_project_read_window_async(db, annot, p)) is None


@pytest.mark.asyncio
async def test_write_gate_blocks_access_group_pre_open_and_after_close(async_test_db):
    db = async_test_db
    org = await _make_org(db)
    owner = await _make_user(db)
    await _add_membership(db, owner.id, org.id, "ORG_ADMIN")
    contributor = await _make_user(db)
    await _add_membership(db, contributor.id, org.id, "CONTRIBUTOR")
    annot = await _make_user(db)
    await _add_membership(db, annot.id, org.id, "ANNOTATOR")
    superadmin = await _make_user(db, is_superadmin=True)

    for state, code in (
        ("upcoming", "project_window_upcoming"),
        ("closed", "project_window_closed"),
    ):
        p = await _make_project(db, owner.id, org, state=state)
        # access group blocked
        assert await _raised_code(
            enforce_project_write_window_async(db, annot, p)
        ) == code
        # every editor is exempt
        for editor in (owner, contributor, superadmin):
            assert (
                await _raised_code(enforce_project_write_window_async(db, editor, p))
                is None
            )

    # open / none: annotator writes allowed
    for state in ("open", "none"):
        p = await _make_project(db, owner.id, org, state=state)
        assert await _raised_code(enforce_project_write_window_async(db, annot, p)) is None


# ── HTTP wiring ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_task_endpoint_enforces_read_window(async_test_db, async_test_client):
    db = async_test_db
    org = await _make_org(db)
    owner = await _make_user(db)
    await _add_membership(db, owner.id, org.id, "ORG_ADMIN")
    annot = await _make_user(db)
    await _add_membership(db, annot.id, org.id, "ANNOTATOR")
    up = await _make_project(db, owner.id, org, state="upcoming")
    task = await _make_task(db, up.id)

    ctx = {"X-Organization-Context": org.id}
    with _as_user(annot):
        r = await async_test_client.get(f"/api/projects/tasks/{task.id}", headers=ctx)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "project_window_upcoming"

    with _as_user(owner):
        r2 = await async_test_client.get(f"/api/projects/tasks/{task.id}", headers=ctx)
    assert r2.status_code == 200
