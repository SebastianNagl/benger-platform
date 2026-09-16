"""The visibility settings keep LMS-linking attachments (D13).

``PATCH /api/projects/{id}/visibility`` used to delete every org attachment
of the project, which silently cut the connection org's staff off a linked
exam (and its billing attachment). Rows that linking created
(``attached_via='lti'``) now survive every shape of the request: private,
org and public. Naming their org again changes nothing; naming it with a
different group is refused (409 ``lti_attachment_conflict``). A manual row
of an org whose connection links the exam becomes a linking row with the
connection's group scope instead of disappearing, unless the request writes
that org's manual row again. A linking row whose org no longer links the
exam is dropped like a manual one.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import (
    LtiPlatformRegistration,
    LtiResourceLink,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, ProjectOrganization, Task
from routers.projects.helpers import check_project_accessible_async

pytestmark = [pytest.mark.integration]  # asyncio_mode = auto


def _hex() -> str:
    return uuid.uuid4().hex[:10]


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


async def _user(db) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username=f"ltivis-{_hex()}",
        email=f"ltivis-{_hex()}@example.com",
        name="Person",
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _org(db, *members) -> Organization:
    slug = f"ltivis-{_hex()}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    db.add(org)
    await db.flush()
    for user, role in members:
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
            )
        )
    await db.flush()
    return org


async def _group(db, org, *members) -> OrganizationGroup:
    group = OrganizationGroup(
        id=str(uuid.uuid4()), organization_id=org.id, name=f"G {_hex()}", is_active=True
    )
    db.add(group)
    await db.flush()
    for user in members:
        db.add(
            OrganizationGroupMembership(
                id=str(uuid.uuid4()),
                group_id=group.id,
                user_id=user.id,
                is_group_admin=False,
            )
        )
    await db.flush()
    return group


async def _exam(db, owner, *, private=True) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Klausur {_hex()}",
        created_by=owner.id,
        is_private=private,
        is_public=False,
        kind="exam",
        label_config='<View><Text name="sv" value="$sachverhalt"/></View>',
    )
    db.add(project)
    await db.flush()
    db.add(
        Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=1,
            data={"sachverhalt": "S"},
            created_by=owner.id,
        )
    )
    await db.flush()
    return project


async def _attach(db, project, org, *, via, group=None) -> str:
    row_id = str(uuid.uuid4())
    db.add(
        ProjectOrganization(
            id=row_id,
            project_id=project.id,
            organization_id=org.id,
            group_id=group.id if group is not None else None,
            assigned_by=project.created_by,
            attached_via=via,
        )
    )
    await db.flush()
    return row_id


async def _link(db, org, project, *, group=None):
    """An LMS connection of ``org`` with one activity pointing at ``project``."""
    host = f"https://lms-{_hex()}.example.com"
    reg = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        group_id=group.id if group is not None else None,
        name="Moodle",
        issuer=host,
        client_id=f"client-{_hex()}",
        auth_login_url=f"{host}/auth",
        auth_token_url=f"{host}/token",
        jwks_uri=f"{host}/certs",
    )
    db.add(reg)
    await db.flush()
    db.add(
        LtiResourceLink(
            id=str(uuid.uuid4()),
            registration_id=reg.id,
            deployment_id="1",
            resource_link_id=f"rl-{_hex()}",
            project_id=project.id,
        )
    )
    await db.flush()


async def _rows(db, project):
    """{org_id: (row id, attached_via, group_id)} read fresh from the DB."""
    result = await db.execute(
        select(ProjectOrganization)
        .where(ProjectOrganization.project_id == project.id)
        .execution_options(populate_existing=True)
    )
    return {
        row.organization_id: (row.id, row.attached_via, row.group_id)
        for row in result.scalars().all()
    }


async def _fresh(db, project) -> Project:
    result = await db.execute(
        select(Project)
        .where(Project.id == project.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _setup(db):
    """A creator, the connection org (with a group and a colleague), and a
    second org for manual shares."""
    creator = await _user(db)
    colleague = await _user(db)
    uni = await _org(db, (colleague, OrganizationRole.CONTRIBUTOR))
    chair = await _group(db, uni, colleague)
    other = await _org(db, (creator, OrganizationRole.CONTRIBUTOR))
    return creator, colleague, uni, chair, other


def _url(project) -> str:
    return f"/api/projects/{project.id}/visibility"


@pytest.mark.asyncio
async def test_make_private_keeps_the_linking_row_and_drops_manual_ones(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator, private=False)
    lti_row = await _attach(db, exam, uni, via="lti", group=chair)
    await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam, group=chair)
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(_url(exam), json={"is_private": True})
    assert response.status_code == 200, response.text

    assert await _rows(db, exam) == {uni.id: (lti_row, "lti", chair.id)}
    assert (await _fresh(db, exam)).is_private is True
    # The connection's staff keep the private exam, even from the apex host.
    assert await check_project_accessible_async(
        db, colleague, exam.id, org_context="private"
    ) is True


@pytest.mark.asyncio
async def test_make_private_turns_a_linked_orgs_manual_row_into_a_linking_row(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator, private=False)
    # Shared with the org by hand before an activity of the org linked it.
    manual_row = await _attach(db, exam, uni, via="manual")
    await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam)
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(_url(exam), json={"is_private": True})
    assert response.status_code == 200, response.text

    assert await _rows(db, exam) == {uni.id: (manual_row, "lti", None)}
    assert await check_project_accessible_async(
        db, colleague, exam.id, org_context="private"
    ) is True


@pytest.mark.asyncio
async def test_org_mode_keeps_the_linking_row_next_to_new_orgs(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, _colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator)
    lti_row = await _attach(db, exam, uni, via="lti", group=chair)
    await _link(db, uni, exam, group=chair)
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={
                "is_private": False,
                "organization_attachments": [
                    {"organization_id": other.id, "group_id": None}
                ],
            },
        )
    assert response.status_code == 200, response.text

    rows = await _rows(db, exam)
    # Not named in the request, yet the linking row is unchanged.
    assert rows[uni.id] == (lti_row, "lti", chair.id)
    assert rows[other.id][1:] == ("manual", None)
    assert set(rows) == {uni.id, other.id}
    assert (await _fresh(db, exam)).is_private is False


@pytest.mark.asyncio
async def test_org_mode_naming_the_linked_org_again_changes_nothing(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, _colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator)
    lti_row = await _attach(db, exam, uni, via="lti", group=chair)
    manual_row = await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam, group=chair)
    await db.commit()

    # The settings panel sends every current attachment back with its group.
    # The creator is no member of the connection's group: no 403 either.
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={
                "is_private": False,
                "organization_attachments": [
                    {"organization_id": uni.id, "group_id": chair.id},
                    {"organization_id": other.id, "group_id": None},
                ],
            },
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, exam)
    assert rows[uni.id] == (lti_row, "lti", chair.id)
    assert rows[other.id][1:] == ("manual", None)
    assert rows[other.id][0] != manual_row  # manual rows are rewritten as before

    # The legacy id list carries no group and never conflicts.
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={"is_private": False, "organization_ids": [uni.id]},
        )
    assert response.status_code == 200, response.text
    assert await _rows(db, exam) == {uni.id: (lti_row, "lti", chair.id)}


@pytest.mark.asyncio
async def test_org_mode_regrouping_the_linked_org_is_refused(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, _colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator)
    lti_row = await _attach(db, exam, uni, via="lti", group=chair)
    manual_row = await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam, group=chair)
    await db.commit()
    before = await _rows(db, exam)

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={
                "is_private": False,
                "organization_attachments": [
                    {"organization_id": uni.id, "group_id": None}
                ],
            },
        )
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "lti_attachment_conflict"
    assert detail["message"]

    # Nothing changed.
    assert await _rows(db, exam) == before
    assert before[uni.id] == (lti_row, "lti", chair.id)
    assert before[other.id][0] == manual_row
    assert (await _fresh(db, exam)).is_private is True


@pytest.mark.asyncio
async def test_removing_an_org_that_only_has_a_linking_row_changes_nothing_for_it(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, _colleague, uni, _chair, other = await _setup(db)
    exam = await _exam(db, creator, private=False)
    lti_row = await _attach(db, exam, uni, via="lti")
    await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam)
    await db.commit()

    # "Only the other org" drops nothing: uni has only its linking row.
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={"is_private": False, "organization_ids": [other.id]},
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, exam)
    assert rows[uni.id] == (lti_row, "lti", None)
    assert rows[other.id][1] == "manual"


@pytest.mark.asyncio
async def test_org_mode_converts_a_dropped_manual_row_of_a_linked_org(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, _colleague, uni, _chair, other = await _setup(db)
    exam = await _exam(db, creator, private=False)
    uni_row = await _attach(db, exam, uni, via="manual")
    await _link(db, uni, exam)
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={"is_private": False, "organization_ids": [other.id]},
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, exam)
    assert rows[uni.id] == (uni_row, "lti", None)
    assert rows[other.id][1] == "manual"

    # Named again, it stays the linking row: the request cannot replace it.
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={"is_private": False, "organization_ids": [other.id, uni.id]},
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, exam)
    assert rows[uni.id] == (uni_row, "lti", None)


@pytest.mark.asyncio
async def test_make_public_keeps_linking_rows(async_test_client, async_test_db):
    db = async_test_db
    creator, _colleague, uni, chair, other = await _setup(db)
    exam = await _exam(db, creator)
    lti_row = await _attach(db, exam, uni, via="lti", group=chair)
    await _attach(db, exam, other, via="manual")
    await _link(db, uni, exam, group=chair)
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam), json={"is_public": True, "public_role": "ANNOTATOR"}
        )
    assert response.status_code == 200, response.text
    assert await _rows(db, exam) == {uni.id: (lti_row, "lti", chair.id)}
    fresh = await _fresh(db, exam)
    assert fresh.is_public is True and fresh.is_private is False


@pytest.mark.asyncio
async def test_unlinked_projects_behave_as_before(async_test_client, async_test_db):
    db = async_test_db
    creator, _colleague, uni, _chair, other = await _setup(db)
    project = await _exam(db, creator, private=False)
    await _attach(db, project, uni, via="manual")
    await db.commit()

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(project),
            json={"is_private": False, "organization_ids": [other.id]},
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, project)
    assert set(rows) == {other.id}
    assert rows[other.id][1] == "manual"

    with _as_user(creator):
        response = await async_test_client.patch(
            _url(project), json={"is_private": True}
        )
    assert response.status_code == 200, response.text
    assert await _rows(db, project) == {}


@pytest.mark.asyncio
async def test_converted_row_takes_the_group_of_the_linking_connection(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, colleague, uni, chair, other = await _setup(db)
    outsider = await _user(db)
    db.add(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=outsider.id,
            organization_id=uni.id,
            role=OrganizationRole.CONTRIBUTOR,
            is_active=True,
        )
    )
    # An org-wide manual share, then a group-scoped connection links the exam.
    exam = await _exam(db, creator, private=False)
    wide_row = await _attach(db, exam, uni, via="manual")
    await _link(db, uni, exam, group=chair)
    # A group-scoped manual share, then an org-wide connection links it.
    exam2 = await _exam(db, creator, private=False)
    narrow_row = await _attach(db, exam2, uni, via="manual", group=chair)
    await _link(db, uni, exam2)
    await db.commit()

    with _as_user(creator):
        for project in (exam, exam2):
            response = await async_test_client.patch(
                _url(project), json={"is_private": True}
            )
            assert response.status_code == 200, response.text

    # The grant follows the connection: group-scoped, not org-wide ...
    assert await _rows(db, exam) == {uni.id: (wide_row, "lti", chair.id)}
    assert await check_project_accessible_async(
        db, colleague, exam.id, org_context="private"
    ) is True
    assert await check_project_accessible_async(
        db, outsider, exam.id, org_context="private"
    ) is False
    # ... and org-wide, not narrowed to the old share's group.
    assert await _rows(db, exam2) == {uni.id: (narrow_row, "lti", None)}
    assert await check_project_accessible_async(
        db, outsider, exam2.id, org_context="private"
    ) is True


@pytest.mark.asyncio
async def test_linking_row_without_a_live_link_is_dropped(
    async_test_client, async_test_db
):
    db = async_test_db
    creator, colleague, uni, chair, other = await _setup(db)
    # A row that outlived its activity (relinked before the cleanup existed).
    exam = await _exam(db, creator)
    await _attach(db, exam, uni, via="lti", group=chair)
    await db.commit()
    assert await check_project_accessible_async(
        db, colleague, exam.id, org_context="private"
    ) is False

    # Sharing with the org again creates a plain manual row, with no 409.
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam),
            json={
                "is_private": False,
                "organization_attachments": [
                    {"organization_id": other.id, "group_id": None},
                ],
            },
        )
    assert response.status_code == 200, response.text
    rows = await _rows(db, exam)
    assert set(rows) == {other.id}

    exam2 = await _exam(db, creator)
    await _attach(db, exam2, uni, via="lti")
    await db.commit()
    with _as_user(creator):
        response = await async_test_client.patch(
            _url(exam2), json={"is_private": True}
        )
    assert response.status_code == 200, response.text
    assert await _rows(db, exam2) == {}
