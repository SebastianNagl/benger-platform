"""Real names of LMS accounts in lists (owner decision D8).

An account an LMS launch created (or one linked to an LMS identity) carries
the clear name and email of the learning platform and is shown by pseudonym.
Who may see the real name:

- org member list and ``/organizations/manage/users``: superadmins, the
  account itself, and admins of an org whose own connection the account
  belongs to (so a platform-wide org's admins only unmask the students of
  that org's own connections);
- group roster: org admins for the accounts of that org's own connections,
  group admins for the accounts of the org's connections scoped to a group
  they administer (group membership reveals nothing);
- project views (project members, task listing annotators and assignments,
  the export ``users`` block): the people ``project_real_name_user_ids``
  names for the viewer.

The extended hooks are replaced by fakes that read the platform link table
with the documented definition (a provisioned link, or any link that is not
unlinked), so the tests drive the platform's calling rules end to end.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import or_, select

from models import (
    LtiPlatformRegistration,
    LtiUserLink,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Annotation, Project, Task, TaskAssignment
from tests.integration.test_group_visibility import (
    _as_user,
    _attach,
    _group,
    _org,
    _project,
)

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Hook fakes
# --------------------------------------------------------------------------- #
class _FakeExtended:
    COMPATIBLE_CORE_VERSIONS = ["2.20"]

    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _protected(db, organization_id, user_ids, group_ids=None):
    """The documented LMS-user definition, read from the link table
    (``group_ids``: only connections scoped to those groups)."""
    query = db.query(LtiUserLink.user_id).filter(
        LtiUserLink.user_id.in_(list(user_ids)),
        or_(
            LtiUserLink.link_method == "provisioned",
            LtiUserLink.unlinked_at.is_(None),
        ),
    )
    if organization_id is not None:
        query = query.join(
            LtiPlatformRegistration,
            LtiPlatformRegistration.id == LtiUserLink.registration_id,
        ).filter(LtiPlatformRegistration.organization_id == str(organization_id))
        if group_ids is not None:
            query = query.filter(
                LtiPlatformRegistration.group_id.in_(list(group_ids))
            )
    return {row[0] for row in query.distinct().all()}


class _Viewers:
    """``project_real_name_user_ids`` fake: viewers in ``allowed`` see every
    name; ``people[viewer_id]`` limits a viewer to those people."""

    def __init__(self):
        self.allowed = set()
        self.people = {}
        self.calls = []

    def __call__(self, db, viewer, project_id, user_ids):
        self.calls.append((str(viewer.id), project_id))
        if str(viewer.id) in self.people:
            return set(self.people[str(viewer.id)]) & set(user_ids)
        return set(user_ids) if str(viewer.id) in self.allowed else set()


@pytest.fixture
def viewers(monkeypatch):
    import extensions

    fake = _Viewers()
    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": _protected,
                "project_real_name_user_ids": fake,
            }
        ),
    )
    return fake


@contextmanager
def _as_nobody():
    """``get_current_user`` answers None (anonymous or deactivated)."""
    from auth_module.dependencies import get_current_user
    from main import app

    app.dependency_overrides[get_current_user] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #
def _hex() -> str:
    return uuid.uuid4().hex[:10]


def _new_person(name, *, pseudonym="Kluge Eule", use_pseudonym=True, superadmin=False):
    tag = _hex()
    return User(
        id=str(uuid.uuid4()),
        username=f"u-{tag}",
        email=f"{tag}@uni.example",
        name=name,
        pseudonym=f"{pseudonym} {tag}" if pseudonym else None,
        use_pseudonym=use_pseudonym,
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


async def _person(db, name, **kwargs) -> User:
    user = _new_person(name, **kwargs)
    db.add(user)
    await db.flush()
    return user


def _new_registration(org, group=None) -> LtiPlatformRegistration:
    tag = _hex()
    return LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        group_id=group.id if group is not None else None,
        name=f"Moodle {tag}",
        issuer=f"https://lms-{tag}.example",
        client_id=f"client-{tag}",
        auth_login_url=f"https://lms-{tag}.example/auth",
        auth_token_url=f"https://lms-{tag}.example/token",
        jwks_uri=f"https://lms-{tag}.example/jwks",
    )


def _new_link(registration, user, *, method="provisioned", unlinked=False):
    return LtiUserLink(
        id=str(uuid.uuid4()),
        registration_id=registration.id,
        sub=f"sub-{_hex()}",
        user_id=user.id,
        link_method=method,
        unlinked_at=datetime.now(timezone.utc) if unlinked else None,
    )


async def _registration(db, org, group=None) -> LtiPlatformRegistration:
    registration = _new_registration(org, group)
    db.add(registration)
    await db.flush()
    return registration


async def _link(db, registration, user, **kwargs) -> None:
    db.add(_new_link(registration, user, **kwargs))
    await db.flush()


async def _join(db, org, user, role) -> None:
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


async def _world(db):
    """The connection org ``uni`` with its staff and students.

    - ``student``: LMS account of uni's connection;
    - ``foreign``: LMS account of another org's connection, also a uni member;
    - ``optout``: LMS account of uni that turned the pseudonym off;
    - ``teacher``: LMS account of uni with the contributor role;
    - ``plain``: an ordinary (non-LMS) member with a pseudonym;
    - ``gadmin``: an annotator who administers group ``g`` (student,
      foreign and ``ostudent`` are members);
    - ``gstudent``: LMS account of uni's connection scoped to ``g`` (not a
      member of ``g``);
    - ``ostudent``: LMS account of uni's connection scoped to group ``g2``
      (a member of ``g``).
    """
    superadmin = await _person(db, "Super Admin", superadmin=True)
    admin = await _person(db, "Org Admin")
    contrib = await _person(db, "Colleague Contributor")
    gadmin = await _person(db, "Group Admin")
    plain = await _person(db, "Plain Member")
    student = await _person(db, "Erika Mustermann", pseudonym="Kluge Eule")
    foreign = await _person(db, "Fremde Studentin", pseudonym="Stilles Wasser")
    optout = await _person(db, "Otto Offen", use_pseudonym=False)
    teacher = await _person(db, "Lehrende Person", pseudonym="Weiser Fuchs")
    gstudent = await _person(db, "Gruppen Studentin", pseudonym="Flinker Otter")
    ostudent = await _person(db, "Andere Gruppe", pseudonym="Ruhiger See")

    uni = await _org(
        db,
        (admin, OrganizationRole.ORG_ADMIN),
        (contrib, OrganizationRole.CONTRIBUTOR),
        (gadmin, OrganizationRole.ANNOTATOR),
        (plain, OrganizationRole.ANNOTATOR),
        (student, OrganizationRole.ANNOTATOR),
        (foreign, OrganizationRole.ANNOTATOR),
        (optout, OrganizationRole.ANNOTATOR),
        (teacher, OrganizationRole.CONTRIBUTOR),
        (gstudent, OrganizationRole.ANNOTATOR),
        (ostudent, OrganizationRole.ANNOTATOR),
    )
    other = await _org(db, (foreign, OrganizationRole.ANNOTATOR))

    reg_uni = await _registration(db, uni)
    reg_other = await _registration(db, other)
    for user in (student, optout, teacher):
        await _link(db, reg_uni, user)
    await _link(db, reg_other, foreign)

    group = await _group(
        db,
        uni,
        "Kurs A",
        (gadmin, True),
        (student, False),
        (foreign, False),
        (ostudent, False),
    )
    group_b = await _group(db, uni, "Kurs C")
    reg_group = await _registration(db, uni, group)
    reg_group_b = await _registration(db, uni, group_b)
    await _link(db, reg_group, gstudent)
    await _link(db, reg_group_b, ostudent)
    await db.commit()
    return {
        "superadmin": superadmin,
        "admin": admin,
        "contrib": contrib,
        "gadmin": gadmin,
        "plain": plain,
        "student": student,
        "foreign": foreign,
        "optout": optout,
        "teacher": teacher,
        "gstudent": gstudent,
        "ostudent": ostudent,
        "uni": uni,
        "other": other,
        "reg_uni": reg_uni,
        "reg_other": reg_other,
        "group": group,
        "group_b": group_b,
    }


def _rows_by_user(rows, key="user_id"):
    return {row[key]: row for row in rows}


def _assert_masked(row, user, *, name_key="user_name", email_key="user_email"):
    assert row[name_key] == user.pseudonym
    assert row[name_key] != user.name
    assert row[email_key] is None
    assert row["is_lms_account"] is True
    assert row["is_pseudonymized"] is True


def _assert_revealed(row, user, *, lms, name_key="user_name", email_key="user_email"):
    assert row[name_key] == user.name
    assert row[email_key] == user.email
    assert row["is_lms_account"] is lms
    assert row["is_pseudonymized"] is False


async def _org_members(client, org, viewer):
    with _as_user(viewer):
        response = await client.get(f"/api/organizations/{org.id}/members")
    assert response.status_code == 200, response.text
    return _rows_by_user(response.json())


# --------------------------------------------------------------------------- #
# Org member list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_contributor_sees_lms_students_by_pseudonym(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["contrib"])

    _assert_masked(rows[w["student"].id], w["student"])
    _assert_masked(rows[w["foreign"].id], w["foreign"])
    _assert_masked(rows[w["teacher"].id], w["teacher"])
    # Opted out of the pseudonym: shown by name, still flagged.
    _assert_revealed(rows[w["optout"].id], w["optout"], lms=True)
    # Ordinary members and staff keep today's view.
    _assert_revealed(rows[w["plain"].id], w["plain"], lms=False)
    _assert_revealed(rows[w["admin"].id], w["admin"], lms=False)
    # Masked rows keep their ids and group chips.
    assert rows[w["student"].id]["groups"][0]["id"] == w["group"].id


@pytest.mark.asyncio
async def test_org_admin_sees_names_of_own_connection_only(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["admin"])

    _assert_revealed(rows[w["student"].id], w["student"], lms=True)
    _assert_revealed(rows[w["teacher"].id], w["teacher"], lms=True)
    # An LMS student of another org's connection stays masked even here.
    _assert_masked(rows[w["foreign"].id], w["foreign"])


@pytest.mark.asyncio
async def test_protected_org_roster_is_for_its_admins_only(
    async_test_client, async_test_db, monkeypatch
):
    """A platform-wide org every LMS user and pilot teacher joins: its
    plain contributors get no roster and no user enumeration; its org
    admins and superadmins keep both, and its group admins keep the roster
    (to manage their groups)."""
    import extensions

    w = await _world(async_test_db)
    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": _protected,
                "lti_protected_org_ids": lambda db: {w["uni"].id},
            }
        ),
    )
    url = f"/api/organizations/{w['uni'].id}/members"
    for viewer in (w["contrib"], w["teacher"]):
        with _as_user(viewer):
            response = await async_test_client.get(url)
        assert response.status_code == 403, response.text
    gadmin_rows = await _org_members(async_test_client, w["uni"], w["gadmin"])
    _assert_masked(gadmin_rows[w["foreign"].id], w["foreign"])
    # A contributor who administers a group keeps it too.
    await _group(async_test_db, w["uni"], "Kurs B", (w["contrib"], True))
    assert w["plain"].id in await _org_members(async_test_client, w["uni"], w["contrib"])

    rows = await _org_members(async_test_client, w["uni"], w["admin"])
    _assert_revealed(rows[w["student"].id], w["student"], lms=True)
    assert w["plain"].id in await _org_members(
        async_test_client, w["uni"], w["superadmin"]
    )

    # /manage/users: uni's members are not listed to its contributors; a
    # contributor seat in another org still lists that org.
    other = await _org(async_test_db, (w["contrib"], OrganizationRole.CONTRIBUTOR))
    colleague = await _person(async_test_db, "Kollege Anderswo")
    await _join(async_test_db, other, colleague, OrganizationRole.ANNOTATOR)
    await async_test_db.commit()
    listed = await _manage_users(async_test_client, w["contrib"])
    assert w["plain"].id not in listed
    assert w["student"].id not in listed
    assert colleague.id in listed
    assert w["plain"].id in await _manage_users(async_test_client, w["admin"])


@pytest.mark.asyncio
async def test_protected_org_lookup_failure_closes_the_roster(
    async_test_client, async_test_db, monkeypatch
):
    import extensions

    def _boom(db):
        raise RuntimeError("hook down")

    w = await _world(async_test_db)
    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": _protected,
                "lti_protected_org_ids": _boom,
            }
        ),
    )
    with _as_user(w["contrib"]):
        response = await async_test_client.get(
            f"/api/organizations/{w['uni'].id}/members"
        )
    assert response.status_code == 403
    assert await _manage_users(async_test_client, w["contrib"]) == {}
    # Org admins are not affected by the lookup.
    assert w["plain"].id in await _org_members(async_test_client, w["uni"], w["admin"])


@pytest.mark.asyncio
async def test_superadmin_sees_every_name(async_test_client, async_test_db, viewers):
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["superadmin"])

    for key in ("student", "foreign", "teacher", "optout"):
        _assert_revealed(rows[w[key].id], w[key], lms=True)


@pytest.mark.asyncio
async def test_lms_teacher_sees_own_row_but_not_students(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["teacher"])

    _assert_revealed(rows[w["teacher"].id], w["teacher"], lms=True)
    _assert_masked(rows[w["student"].id], w["student"])


async def _roster(client, w, viewer, group_key="group"):
    with _as_user(viewer):
        response = await client.get(
            f"/api/organizations/{w['uni'].id}/groups/{w[group_key].id}/members"
        )
    assert response.status_code == 200, response.text
    return _rows_by_user(response.json())


@pytest.mark.asyncio
async def test_group_admin_sees_their_groups_connection_users_by_name(
    async_test_client, async_test_db, viewers
):
    """D1/D8: a group admin sees the LMS users of the connections scoped to
    their group, not whoever is a member of the group."""
    w = await _world(async_test_db)

    rows = await _org_members(async_test_client, w["uni"], w["gadmin"])
    _assert_revealed(rows[w["gstudent"].id], w["gstudent"], lms=True)
    # Org-wide connection, another group's connection, another org: masked,
    # although student, ostudent and foreign are members of the group.
    _assert_masked(rows[w["student"].id], w["student"])
    _assert_masked(rows[w["ostudent"].id], w["ostudent"])
    _assert_masked(rows[w["foreign"].id], w["foreign"])
    _assert_masked(rows[w["teacher"].id], w["teacher"])

    roster = await _roster(async_test_client, w, w["gadmin"])
    _assert_masked(roster[w["student"].id], w["student"])
    _assert_masked(roster[w["ostudent"].id], w["ostudent"])
    _assert_masked(roster[w["foreign"].id], w["foreign"])
    _assert_revealed(roster[w["gadmin"].id], w["gadmin"], lms=False)

    # The org admin sees every student of the org's own connections.
    admin_roster = await _roster(async_test_client, w, w["admin"])
    _assert_revealed(admin_roster[w["student"].id], w["student"], lms=True)
    _assert_revealed(admin_roster[w["ostudent"].id], w["ostudent"], lms=True)
    _assert_masked(admin_roster[w["foreign"].id], w["foreign"])


@pytest.mark.asyncio
async def test_adding_a_member_to_the_group_reveals_nothing(
    async_test_client, async_test_db, viewers
):
    """A group admin may add any org member to their group. That must not
    unmask a student of an org-wide or foreign-group connection."""
    w = await _world(async_test_db)
    newbie = await _person(async_test_db, "Neue Studentin", pseudonym="Leiser Wind")
    await _join(async_test_db, w["uni"], newbie, OrganizationRole.ANNOTATOR)
    await _link(async_test_db, w["reg_uni"], newbie)
    await async_test_db.commit()

    rows = await _org_members(async_test_client, w["uni"], w["gadmin"])
    _assert_masked(rows[newbie.id], newbie)

    group_url = f"/api/organizations/{w['uni'].id}/groups/{w['group'].id}/members"
    with _as_user(w["gadmin"]):
        for user in (newbie, w["gstudent"]):
            added = await async_test_client.post(group_url, json={"user_id": user.id})
            assert added.status_code == 201, added.text

    roster = await _roster(async_test_client, w, w["gadmin"])
    _assert_masked(roster[newbie.id], newbie)
    _assert_masked(roster[w["student"].id], w["student"])
    _assert_revealed(roster[w["gstudent"].id], w["gstudent"], lms=True)
    rows = await _org_members(async_test_client, w["uni"], w["gadmin"])
    _assert_masked(rows[newbie.id], newbie)
    _assert_revealed(rows[w["gstudent"].id], w["gstudent"], lms=True)


@pytest.mark.asyncio
async def test_admin_of_a_group_without_connections_sees_no_lms_names(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    lead = await _person(async_test_db, "Kurs B Leitung")
    await _join(async_test_db, w["uni"], lead, OrganizationRole.CONTRIBUTOR)
    from models import OrganizationGroupMembership

    async_test_db.add(
        OrganizationGroupMembership(
            id=str(uuid.uuid4()),
            group_id=w["group_b"].id,
            user_id=lead.id,
            is_group_admin=True,
        )
    )
    await async_test_db.commit()

    rows = await _org_members(async_test_client, w["uni"], lead)
    # Kurs B has a connection: its student is shown by name, nobody else.
    _assert_revealed(rows[w["ostudent"].id], w["ostudent"], lms=True)
    for key in ("student", "gstudent", "foreign", "teacher"):
        _assert_masked(rows[w[key].id], w[key])


@pytest.mark.asyncio
async def test_group_reveal_fails_closed_with_an_old_hook(
    async_test_client, async_test_db, monkeypatch
):
    """An LMS-user hook that does not know ``group_ids`` reveals nobody to
    group admins; org admins keep their view."""
    import extensions

    def old_signature(db, organization_id, user_ids):
        return _protected(db, organization_id, user_ids)

    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended({"privacy_protected_member_ids": old_signature}),
    )
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["gadmin"])
    _assert_masked(rows[w["gstudent"].id], w["gstudent"])
    rows = await _org_members(async_test_client, w["uni"], w["admin"])
    _assert_revealed(rows[w["gstudent"].id], w["gstudent"], lms=True)


@pytest.mark.asyncio
async def test_superadmin_roster_shows_every_name(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    with _as_user(w["superadmin"]):
        response = await async_test_client.get(
            f"/api/organizations/{w['uni'].id}/groups/{w['group'].id}/members"
        )
    assert response.status_code == 200, response.text
    roster = _rows_by_user(response.json())
    _assert_revealed(roster[w["foreign"].id], w["foreign"], lms=True)


@pytest.mark.asyncio
async def test_platform_org_admin_unmasks_only_its_own_connections(
    async_test_client, async_test_db, viewers
):
    """A platform-wide org where every LMS user is an annotator: its admins
    see the students of its own connections, not those of university
    connections that also joined it."""
    db = async_test_db
    platform_admin = await _person(db, "Plattform Admin")
    own_student = await _person(db, "Eigene Studentin", pseudonym="Mutiger Adler")
    uni_student = await _person(db, "Uni Student", pseudonym="Ruhiger See")
    platform = await _org(
        db,
        (platform_admin, OrganizationRole.ORG_ADMIN),
        (own_student, OrganizationRole.ANNOTATOR),
        (uni_student, OrganizationRole.ANNOTATOR),
    )
    uni = await _org(db, (uni_student, OrganizationRole.ANNOTATOR))
    await _link(db, await _registration(db, platform), own_student)
    await _link(db, await _registration(db, uni), uni_student)
    await db.commit()

    rows = await _org_members(async_test_client, platform, platform_admin)

    _assert_revealed(rows[own_student.id], own_student, lms=True)
    _assert_masked(rows[uni_student.id], uni_student)


@pytest.mark.asyncio
async def test_unlinked_accounts(async_test_client, async_test_db, viewers):
    """A provisioned account keeps the LMS clear name after an unlink and
    stays masked; an existing account whose proof link was removed is an
    ordinary account again."""
    db = async_test_db
    w = await _world(db)
    unlinked_provisioned = await _person(db, "Ehemals LMS", pseudonym="Alter Baum")
    unlinked_proof = await _person(db, "Eigenes Konto", pseudonym="Junger Baum")
    await _join(db, w["uni"], unlinked_provisioned, OrganizationRole.ANNOTATOR)
    await _join(db, w["uni"], unlinked_proof, OrganizationRole.ANNOTATOR)
    await _link(db, w["reg_uni"], unlinked_provisioned, unlinked=True)
    await _link(db, w["reg_uni"], unlinked_proof, method="login_proof", unlinked=True)
    await db.commit()

    rows = await _org_members(async_test_client, w["uni"], w["contrib"])

    _assert_masked(rows[unlinked_provisioned.id], unlinked_provisioned)
    _assert_revealed(rows[unlinked_proof.id], unlinked_proof, lms=False)


@pytest.mark.asyncio
async def test_masked_account_without_pseudonym_gets_a_neutral_label(
    async_test_client, async_test_db, viewers
):
    db = async_test_db
    w = await _world(db)
    nameless = await _person(db, "Ohne Pseudonym", pseudonym=None)
    await _join(db, w["uni"], nameless, OrganizationRole.ANNOTATOR)
    await _link(db, w["reg_uni"], nameless)
    await db.commit()

    rows = await _org_members(async_test_client, w["uni"], w["contrib"])

    row = rows[nameless.id]
    assert row["user_name"] == f"User {nameless.id[:8]}"
    assert row["user_email"] is None
    assert row["is_pseudonymized"] is True


@pytest.mark.asyncio
async def test_community_edition_lists_are_unchanged(
    async_test_client, async_test_db, monkeypatch
):
    """Without the extended hooks there are no LMS accounts to mask."""
    import extensions

    monkeypatch.setattr(extensions, "_extended", None)
    w = await _world(async_test_db)
    rows = await _org_members(async_test_client, w["uni"], w["contrib"])

    _assert_revealed(rows[w["student"].id], w["student"], lms=False)


@pytest.mark.asyncio
async def test_email_verification_responses_follow_the_mask(
    async_test_client, async_test_db, viewers
):
    db = async_test_db
    w = await _world(db)
    for key in ("student", "foreign"):
        w[key].email_verified = False
    await db.commit()
    base = f"/api/organizations/{w['uni'].id}/members"

    with _as_user(w["admin"]):
        own = await async_test_client.post(
            f"{base}/{w['student'].id}/verify-email", json={}
        )
        foreign = await async_test_client.post(
            f"{base}/{w['foreign'].id}/verify-email", json={}
        )
        again = await async_test_client.post(
            f"{base}/verify-emails",
            json={"user_ids": [w["student"].id, w["foreign"].id]},
        )

    assert own.status_code == 200, own.text
    assert own.json()["email"] == w["student"].email
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["message"] == "Email verified successfully"
    assert foreign.json()["email"] is None
    results = {row["user_id"]: row for row in again.json()["results"]}
    assert results[w["student"].id]["email"] == w["student"].email
    assert results[w["foreign"].id]["status"] == "skipped"
    assert results[w["foreign"].id]["email"] is None


# --------------------------------------------------------------------------- #
# /organizations/manage/users
# --------------------------------------------------------------------------- #
async def _manage_users(client, viewer, search=None):
    params = {"search": search} if search else {}
    with _as_user(viewer):
        response = await client.get("/api/organizations/manage/users", params=params)
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()}


@pytest.mark.asyncio
async def test_manage_users_masks_lms_accounts_for_contributors(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    student = w["student"]

    rows = await _manage_users(async_test_client, w["contrib"])
    row = rows[student.id]
    _assert_masked(row, student, name_key="name", email_key="email")
    assert row["username"] == student.pseudonym
    _assert_revealed(rows[w["plain"].id], w["plain"], lms=False, name_key="name", email_key="email")
    _assert_revealed(rows[w["optout"].id], w["optout"], lms=True, name_key="name", email_key="email")

    # The search cannot tie a real name, login or email to a masked account...
    for probe in ("Mustermann", student.username, student.email):
        assert student.id not in await _manage_users(async_test_client, w["contrib"], probe)
    # ...but finds it by pseudonym, still masked.
    found = await _manage_users(async_test_client, w["contrib"], student.pseudonym.split()[0])
    assert found[student.id]["name"] == student.pseudonym
    # Ordinary accounts are still found by name.
    assert w["plain"].id in await _manage_users(async_test_client, w["contrib"], "Plain Member")


@pytest.mark.asyncio
async def test_manage_users_org_admin_sees_own_connection(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)

    rows = await _manage_users(async_test_client, w["admin"])
    _assert_revealed(rows[w["student"].id], w["student"], lms=True, name_key="name", email_key="email")
    _assert_masked(rows[w["foreign"].id], w["foreign"], name_key="name", email_key="email")

    found = await _manage_users(async_test_client, w["admin"], "Mustermann")
    assert found[w["student"].id]["name"] == "Erika Mustermann"
    assert w["foreign"].id not in await _manage_users(
        async_test_client, w["admin"], "Fremde"
    )


@pytest.mark.asyncio
async def test_manage_users_superadmin_sees_everyone(
    async_test_client, async_test_db, viewers
):
    w = await _world(async_test_db)
    rows = await _manage_users(async_test_client, w["superadmin"], "Fremde")
    _assert_revealed(rows[w["foreign"].id], w["foreign"], lms=True, name_key="name", email_key="email")


@pytest.mark.asyncio
async def test_hook_calls_are_chunked_with_the_same_answer(
    async_test_client, async_test_db, viewers, monkeypatch
):
    """Id lists reach the hooks in chunks (bind-parameter limit); the lists
    and the search answer exactly as with one call."""
    from services import member_privacy

    w = await _world(async_test_db)
    before_members = await _org_members(async_test_client, w["uni"], w["admin"])
    before_search = await _manage_users(async_test_client, w["contrib"], "Kluge")

    import extensions

    sizes = []

    def counting(db, organization_id, user_ids, **kwargs):
        sizes.append(len(user_ids))
        return _protected(db, organization_id, user_ids, **kwargs)

    monkeypatch.setattr(member_privacy, "_HOOK_CHUNK", 2)
    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": counting,
                "project_real_name_user_ids": viewers,
            }
        ),
    )
    assert await _org_members(async_test_client, w["uni"], w["admin"]) == before_members
    assert sizes and max(sizes) <= 2
    after_search = await _manage_users(async_test_client, w["contrib"], "Kluge")
    assert after_search == before_search
    assert after_search[w["student"].id]["is_pseudonymized"] is True


@pytest.mark.asyncio
async def test_a_failing_chunk_still_masks(async_test_client, async_test_db, monkeypatch):
    """One failing chunk of the "who is an LMS user" call masks that chunk's
    accounts; one failing chunk of an admin reveal reveals nobody in it."""
    from services import member_privacy

    import extensions

    w = await _world(async_test_db)
    calls = {"none": 0}

    def flaky(db, organization_id, user_ids, **kwargs):
        if organization_id is None:
            calls["none"] += 1
            if calls["none"] == 1:
                raise RuntimeError("chunk failed")
        elif w["student"].id in user_ids:
            raise RuntimeError("reveal chunk failed")
        return _protected(db, organization_id, user_ids, **kwargs)

    monkeypatch.setattr(member_privacy, "_HOOK_CHUNK", 1)
    monkeypatch.setattr(
        extensions, "_extended", _FakeExtended({"privacy_protected_member_ids": flaky})
    )
    rows = await _org_members(async_test_client, w["uni"], w["admin"])
    # The student's own reveal chunk failed: masked for the org admin too.
    _assert_masked(rows[w["student"].id], w["student"])
    # Other accounts of the org's connections are still revealed.
    _assert_revealed(rows[w["gstudent"].id], w["gstudent"], lms=True)
    masked = [row for row in rows.values() if row["is_pseudonymized"]]
    assert all(row["user_email"] is None for row in masked)


# --------------------------------------------------------------------------- #
# Handlers on optional auth
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/api/organizations/{org}/members", None),
        ("put", "/api/organizations/{org}/members/{user}/role", {"role": "CONTRIBUTOR"}),
        ("delete", "/api/organizations/{org}/members/{user}", None),
        ("post", "/api/organizations/{org}/members", {"user_id": "{user}"}),
        ("post", "/api/organizations/{org}/members/{user}/verify-email", {}),
        ("post", "/api/organizations/{org}/members/verify-emails", {"user_ids": ["{user}"]}),
        ("post", "/api/organizations/", {"name": "x", "display_name": "x", "slug": "x-no-user"}),
        ("delete", "/api/organizations/{org}", None),
        ("get", "/api/organizations/manage/users", None),
        ("put", "/api/organizations/manage/users/{user}/superadmin", {"is_superadmin": True}),
        ("delete", "/api/organizations/manage/users/{user}", None),
    ],
)
async def test_no_current_user_is_401_not_500(
    async_test_client, async_test_db, method, path, body
):
    """``get_current_user`` answers None for deactivated (anonymized)
    accounts; these handlers must refuse cleanly."""
    db = async_test_db
    target = await _person(db, "Ziel")
    org = await _org(db, (target, OrganizationRole.ANNOTATOR))
    url = path.format(org=org.id, user=target.id)
    payload = (
        json.loads(json.dumps(body).replace("{user}", target.id))
        if body is not None
        else None
    )

    with _as_nobody():
        kwargs = {"json": payload} if payload is not None else {}
        response = await getattr(async_test_client, method)(url, **kwargs)

    assert response.status_code == 401, response.text


# --------------------------------------------------------------------------- #
# Project views
# --------------------------------------------------------------------------- #
async def _project_world(db):
    w = await _world(db)
    project = await _project(db, w["contrib"])
    await _attach(db, project, w["uni"], w["contrib"])
    task_id = (
        await db.execute(select(Task.id).where(Task.project_id == project.id))
    ).scalar_one()
    db.add(
        Annotation(
            id=str(uuid.uuid4()),
            task_id=task_id,
            project_id=project.id,
            completed_by=w["student"].id,
            result=[{"value": "Antwort"}],
        )
    )
    db.add(
        TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=task_id,
            user_id=w["student"].id,
            assigned_by=w["contrib"].id,
            status="assigned",
        )
    )
    await db.commit()
    w["project"] = project
    w["task_id"] = task_id
    return w


@pytest.mark.asyncio
async def test_project_members_are_masked_unless_real_name_viewer(
    async_test_client, async_test_db, viewers
):
    w = await _project_world(async_test_db)
    url = f"/api/projects/{w['project'].id}/members"

    with _as_user(w["contrib"]):
        response = await async_test_client.get(url)
    assert response.status_code == 200, response.text
    rows = _rows_by_user(response.json())
    _assert_masked(rows[w["student"].id], w["student"], name_key="name", email_key="email")
    _assert_revealed(rows[w["plain"].id], w["plain"], lms=False, name_key="name", email_key="email")
    _assert_revealed(rows[w["contrib"].id], w["contrib"], lms=False, name_key="name", email_key="email")
    assert (w["contrib"].id, w["project"].id) in viewers.calls

    viewers.allowed.add(w["contrib"].id)
    with _as_user(w["contrib"]):
        response = await async_test_client.get(url)
    rows = _rows_by_user(response.json())
    _assert_revealed(rows[w["student"].id], w["student"], lms=True, name_key="name", email_key="email")
    _assert_revealed(rows[w["foreign"].id], w["foreign"], lms=True, name_key="name", email_key="email")


@pytest.mark.asyncio
async def test_project_members_unmask_only_the_people_the_hook_names(
    async_test_client, async_test_db, viewers
):
    """The org-wide fan-in lists every member of the connection org; only
    the exam's own participants the viewer may see are shown by name."""
    w = await _project_world(async_test_db)
    viewers.people[w["contrib"].id] = {w["student"].id}
    with _as_user(w["contrib"]):
        response = await async_test_client.get(f"/api/projects/{w['project'].id}/members")
    assert response.status_code == 200, response.text
    rows = _rows_by_user(response.json())
    _assert_revealed(rows[w["student"].id], w["student"], lms=True, name_key="name", email_key="email")
    _assert_masked(rows[w["foreign"].id], w["foreign"], name_key="name", email_key="email")
    _assert_masked(rows[w["teacher"].id], w["teacher"], name_key="name", email_key="email")


@pytest.mark.asyncio
async def test_superadmin_skips_the_viewer_hook(
    async_test_client, async_test_db, viewers
):
    w = await _project_world(async_test_db)
    with _as_user(w["superadmin"]):
        response = await async_test_client.get(
            f"/api/projects/{w['project'].id}/members"
        )
    assert response.status_code == 200, response.text
    rows = _rows_by_user(response.json())
    _assert_revealed(rows[w["student"].id], w["student"], lms=True, name_key="name", email_key="email")
    assert viewers.calls == []


@pytest.mark.asyncio
async def test_task_listing_masks_annotators_and_assignments(
    async_test_client, async_test_db, viewers
):
    w = await _project_world(async_test_db)
    url = f"/api/projects/{w['project'].id}/tasks"

    def _item(response):
        assert response.status_code == 200, response.text
        items = {item["id"]: item for item in response.json()["items"]}
        return items[w["task_id"]]

    with _as_user(w["contrib"]):
        item = _item(await async_test_client.get(url))
    student = w["student"]
    assert item["annotators"] == [{"id": student.id, "name": student.pseudonym}]
    assignment = item["assignments"][0]
    assert assignment["user_id"] == student.id
    assert assignment["user_name"] == student.pseudonym
    assert assignment["user_email"] is None

    assignments_url = f"{url}/{w['task_id']}/assignments"
    with _as_user(w["contrib"]):
        response = await async_test_client.get(assignments_url)
    assert response.status_code == 200, response.text
    assert response.json()[0]["user_name"] == student.pseudonym
    assert response.json()[0]["user_email"] is None

    viewers.allowed.add(w["contrib"].id)
    with _as_user(w["contrib"]):
        item = _item(await async_test_client.get(url))
    assert item["annotators"] == [{"id": student.id, "name": student.name}]
    assert item["assignments"][0]["user_name"] == student.name
    assert item["assignments"][0]["user_email"] == student.email
    with _as_user(w["contrib"]):
        response = await async_test_client.get(assignments_url)
    assert response.json()[0]["user_name"] == student.name
    assert response.json()[0]["user_email"] == student.email


@pytest.mark.asyncio
async def test_lms_creator_name_follows_the_viewer(
    async_test_client, async_test_db, viewers
):
    """A project an LMS teacher created shows the creator by pseudonym to
    viewers who may not see the teacher's real name (e.g. students), in the
    detail and in the list."""
    db = async_test_db
    w = await _world(db)
    teacher = w["teacher"]
    project = await _project(db, teacher)
    project.is_public = True
    project.public_role = "ANNOTATOR"
    ordinary = await _project(db, w["contrib"])
    ordinary.is_public = True
    ordinary.public_role = "ANNOTATOR"
    await db.commit()

    async def creator_names(viewer):
        with _as_user(viewer):
            detail = await async_test_client.get(f"/api/projects/{project.id}")
            listing = await async_test_client.get(
                "/api/projects/", params={"page_size": 500}
            )
        assert detail.status_code == 200, detail.text
        assert listing.status_code == 200, listing.text
        names = {item["id"]: item["created_by_name"] for item in listing.json()["items"]}
        return detail.json()["created_by_name"], names

    detail, names = await creator_names(w["student"])
    assert detail == teacher.pseudonym
    assert names[project.id] == teacher.pseudonym
    assert names[ordinary.id] == w["contrib"].name

    viewers.allowed.add(w["student"].id)
    detail, names = await creator_names(w["student"])
    assert detail == teacher.name
    assert names[project.id] == teacher.name

    for viewer in (teacher, w["superadmin"]):
        detail, _ = await creator_names(viewer)
        assert detail == teacher.name


@pytest.mark.asyncio
async def test_edit_and_visibility_responses_mask_the_creator(
    async_test_client, async_test_db, viewers
):
    """``PATCH /projects/{id}`` and the visibility PATCH answer with the same
    creator label as ``GET``: an editor who may not see the LMS teacher's
    real name does not get it from a no-op edit."""
    db = async_test_db
    w = await _world(db)
    teacher = w["teacher"]
    project = await _project(db, teacher)
    await _attach(db, project, w["uni"], teacher)
    await db.commit()

    with _as_user(w["contrib"]):
        edited = await async_test_client.patch(f"/api/projects/{project.id}", json={})
    assert edited.status_code == 200, edited.text
    assert edited.json()["created_by_name"] == teacher.pseudonym

    viewers.allowed.add(w["contrib"].id)
    with _as_user(w["contrib"]):
        edited = await async_test_client.patch(f"/api/projects/{project.id}", json={})
    assert edited.status_code == 200, edited.text
    assert edited.json()["created_by_name"] == teacher.name
    viewers.allowed.discard(w["contrib"].id)

    # Handing an own project to the LMS teacher: the response shows the new
    # owner as the caller may see them.
    own = await _project(db, w["contrib"], private=True)
    await db.commit()
    with _as_user(w["contrib"]):
        moved = await async_test_client.patch(
            f"/api/projects/{own.id}/visibility",
            json={"is_private": True, "owner_user_id": teacher.id},
        )
    assert moved.status_code == 200, moved.text
    assert moved.json()["created_by_name"] == teacher.pseudonym


@pytest.mark.asyncio
async def test_project_list_asks_the_name_hook_once_per_page(
    async_test_client, async_test_db, viewers, monkeypatch
):
    """The project list masks LMS creators with one bulk hook call, however
    many rows the page has; rows that need no check never reach it."""
    import extensions

    db = async_test_db
    w = await _world(db)
    teacher = w["teacher"]
    projects = []
    for _ in range(4):
        project = await _project(db, teacher)
        await _attach(db, project, w["uni"], teacher)
        projects.append(project)
    await db.commit()

    bulk_calls = []
    lms_calls = []

    def bulk(sync_db, viewer, wanted):
        bulk_calls.append({pid: list(ids) for pid, ids in wanted.items()})
        return {
            pid: set(ids) if str(viewer.id) in viewers.allowed else set()
            for pid, ids in wanted.items()
        }

    def protected(sync_db, organization_id, user_ids, **kwargs):
        lms_calls.append(organization_id)
        return _protected(sync_db, organization_id, user_ids, **kwargs)

    single_calls = []

    def single(*args):
        single_calls.append(args)
        return set()

    monkeypatch.setattr(
        extensions,
        "_extended",
        _FakeExtended(
            {
                "privacy_protected_member_ids": protected,
                "project_real_name_user_ids": single,
                "projects_real_name_user_ids": bulk,
            }
        ),
    )

    async def names(viewer):
        bulk_calls.clear()
        lms_calls.clear()
        with _as_user(viewer):
            listing = await async_test_client.get(
                "/api/projects/",
                params={"page_size": 500},
                headers={"X-Organization-Context": w["uni"].id},
            )
        assert listing.status_code == 200, listing.text
        return {item["id"]: item["created_by_name"] for item in listing.json()["items"]}

    got = await names(w["contrib"])
    for project in projects:
        assert got[project.id] == teacher.pseudonym
    assert single_calls == []
    assert len(bulk_calls) == 1
    assert {p.id for p in projects} <= set(bulk_calls[0])
    assert lms_calls == [None]

    viewers.allowed.add(w["contrib"].id)
    got = await names(w["contrib"])
    assert {got[p.id] for p in projects} == {teacher.name}
    assert len(bulk_calls) == 1

    # The creator and superadmins never reach the bulk hook.
    for viewer in (teacher, w["superadmin"]):
        got = await names(viewer)
        assert {got[p.id] for p in projects} == {teacher.name}
        assert bulk_calls == []
        assert lms_calls == [None]


@pytest.mark.asyncio
async def test_project_annotators_never_fall_back_to_a_real_name(
    async_test_client, async_test_db, viewers
):
    db = async_test_db
    w = await _project_world(db)
    nameless = await _person(db, "Ohne Pseudonym", pseudonym=None)
    ordinary = await _person(db, "Normale Person", pseudonym=None)
    await _link(db, w["reg_uni"], nameless)
    for user in (nameless, ordinary):
        db.add(
            Annotation(
                id=str(uuid.uuid4()),
                task_id=w["task_id"],
                project_id=w["project"].id,
                completed_by=user.id,
                result=[{"value": "x"}],
            )
        )
    await db.commit()

    with _as_user(w["contrib"]):
        response = await async_test_client.get(
            f"/api/projects/{w['project'].id}/annotators"
        )
    assert response.status_code == 200, response.text
    names = {row["id"]: row["name"] for row in response.json()["annotators"]}
    assert names[w["student"].id] == w["student"].pseudonym
    assert names[nameless.id] == f"User {nameless.id[:8]}"
    assert names[ordinary.id] == "Normale Person"


# --------------------------------------------------------------------------- #
# /auth/me and the login user
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/auth/me", "/api/auth/me/contexts"])
async def test_me_carries_pseudonym_and_lms_flag(async_test_client, async_test_db, path):
    w = await _world(async_test_db)

    def _user_of(response):
        assert response.status_code == 200, response.text
        body = response.json()
        return body["user"] if path.endswith("contexts") else body

    with _as_user(w["student"]):
        me = _user_of(await async_test_client.get(path))
    assert me["pseudonym"] == w["student"].pseudonym
    assert me["use_pseudonym"] is True
    assert me["is_lms_account"] is True

    with _as_user(w["plain"]):
        me = _user_of(await async_test_client.get(path))
    assert me["pseudonym"] == w["plain"].pseudonym
    assert me["is_lms_account"] is False

    with _as_user(w["optout"]):
        me = _user_of(await async_test_client.get(path))
    assert me["use_pseudonym"] is False
    assert me["is_lms_account"] is True


@pytest.mark.asyncio
async def test_me_lms_flag_follows_the_link_definition(async_test_client, async_test_db):
    """The header flag means "an LMS launch created the account": a
    provisioned link (also unlinked) or the LMS origin marker (the
    connection was deleted). An existing account linked by proof keeps its
    own header, live link or not, although lists mask it (D8)."""
    from lms_name_masking import is_lms_account

    db = async_test_db
    w = await _world(db)
    live_provisioned = await _person(db, "LMS Konto")
    unlinked_provisioned = await _person(db, "Ehemals LMS")
    marker_only = await _person(db, "Verbindung geloescht")
    marker_only.lms_provisioned_at = datetime.now(timezone.utc)
    unlinked_proof = await _person(db, "Eigenes Konto", pseudonym="Anders")
    live_login_proof = await _person(db, "Login-Nachweis", pseudonym="Anders")
    live_email_proof = await _person(db, "Mail-Nachweis", pseudonym="Anders")
    await _link(db, w["reg_uni"], live_provisioned)
    await _link(db, w["reg_uni"], unlinked_provisioned, unlinked=True)
    await _link(db, w["reg_uni"], unlinked_proof, method="login_proof", unlinked=True)
    await _link(db, w["reg_uni"], live_login_proof, method="login_proof")
    await _link(db, w["reg_uni"], live_email_proof, method="email_proof")
    await db.commit()

    cases = (
        (live_provisioned, True, True),
        (unlinked_provisioned, True, True),
        (marker_only, True, True),
        (unlinked_proof, False, False),
        (live_login_proof, False, True),
        (live_email_proof, False, True),
    )
    for user, header, masked_in_lists in cases:
        with _as_user(user):
            response = await async_test_client.get("/api/auth/me")
        assert response.status_code == 200, response.text
        assert response.json()["is_lms_account"] is header, user.name
        assert await is_lms_account(db, user.id) is masked_in_lists, user.name


def test_link_table_reading_counts_the_lms_origin(test_db):
    """The community fallback (exports, ``/manage/users`` prefilter) counts
    an account whose connection is gone by its LMS origin marker."""
    from sqlalchemy import select as sa_select

    from lms_name_masking import (
        is_lms_account_sync,
        is_lms_provisioned_account_sync,
        lms_link_exists,
        lms_user_ids_from_links,
    )

    marked = _new_person("Geloeschte Anbindung")
    marked.lms_provisioned_at = datetime.now(timezone.utc)
    plain = _new_person("Ohne LMS")
    test_db.add_all([marked, plain])
    test_db.flush()
    ids = [marked.id, plain.id]

    assert lms_user_ids_from_links(test_db, ids) == {marked.id}
    assert is_lms_account_sync(test_db, marked.id) is True
    assert is_lms_account_sync(test_db, plain.id) is False
    assert is_lms_provisioned_account_sync(test_db, marked.id) is True
    assert is_lms_provisioned_account_sync(test_db, plain.id) is False
    # Used on the outer ``users`` table: no accidental correlation.
    found = test_db.execute(
        sa_select(User.id).where(User.id.in_(ids), lms_link_exists(User.id))
    ).scalars().all()
    assert set(found) == {marked.id}


def test_login_user_carries_display_name_fields(client, test_db, test_users):
    """The login response's user matches the /auth/me shape, so the header
    does not change after the first hydration."""
    from models import User as DBUser

    creds = {"username": "annotator@test.com", "password": "annotator123"}
    user = client.post("/api/auth/login", json=creds).json()["user"]
    assert user["is_lms_account"] is False
    assert user["use_pseudonym"] is True
    assert "pseudonym" in user

    org = Organization(
        id=str(uuid.uuid4()), name="lms-org", display_name="LMS Org", slug=f"lms-{_hex()}"
    )
    test_db.add(org)
    test_db.flush()
    registration = _new_registration(org)
    test_db.add(registration)
    test_db.flush()
    row = test_db.query(DBUser).filter(DBUser.id == "annotator-test-id").one()
    row.pseudonym = f"Heller Stern {_hex()}"
    # Linked by proof: the account keeps its own header.
    proof = _new_link(registration, row, method="login_proof")
    test_db.add(proof)
    test_db.commit()
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    assert response.json()["user"]["is_lms_account"] is False

    test_db.delete(proof)
    test_db.add(_new_link(registration, row))
    test_db.commit()

    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["is_lms_account"] is True
    assert user["pseudonym"] == row.pseudonym


# --------------------------------------------------------------------------- #
# Export users block
# --------------------------------------------------------------------------- #
@pytest.fixture
def export_world(test_db):
    """A project whose only annotator is an LMS student, plus viewers."""
    db = test_db
    student = _new_person("Erika Mustermann", pseudonym="Kluge Eule")
    teacher = _new_person("Lehrkraft")
    superadmin = _new_person("Super Admin", superadmin=True)
    db.add_all([student, teacher, superadmin])
    db.flush()
    org = Organization(
        id=str(uuid.uuid4()), name="export-org", display_name="Export Org", slug=f"exp-{_hex()}"
    )
    db.add(org)
    db.flush()
    registration = _new_registration(org)
    db.add(registration)
    db.flush()
    db.add(_new_link(registration, student))
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Export {_hex()}",
        created_by=teacher.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=1,
        data={"text": "Fall"},
        created_by=teacher.id,
    )
    db.add(task)
    db.flush()
    db.add(
        Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            completed_by=student.id,
            result=[{"value": "Antwort"}],
        )
    )
    db.commit()
    return {
        "db": db,
        "project": project,
        "student": student,
        "teacher": teacher,
        "superadmin": superadmin,
    }


def _ndjson_users(db, project_id, viewer):
    from export_stream import stream_export_ndjson

    records = [json.loads(line) for line in stream_export_ndjson(db, project_id, viewer=viewer)]
    return {r["id"]: r for r in records if r["_type"] == "user"}


def _comprehensive_users(db, project_id, viewer):
    from export_stream import stream_comprehensive_project_data_json

    body = json.loads("".join(stream_comprehensive_project_data_json(db, project_id, viewer=viewer)))
    return {r["id"]: r for r in body["users"]}


def _masked_record(record, user):
    return record["name"] == user.pseudonym and record["email"] is None and record["username"] is None


def _real_record(record, user):
    return (
        record["name"] == user.name
        and record["email"] == user.email
        and record["username"] == user.username
    )


@pytest.mark.parametrize("read_users", [_ndjson_users, _comprehensive_users])
def test_export_users_block_without_hooks(export_world, read_users):
    """Without the extended worker hook the link table decides and only
    superadmins see real names."""
    w = export_world
    db, pid, student = w["db"], w["project"].id, w["student"]

    assert _masked_record(read_users(db, pid, w["teacher"])[student.id], student)
    assert _masked_record(read_users(db, pid, None)[student.id], student)
    assert _real_record(read_users(db, pid, w["superadmin"])[student.id], student)
    # The exporting user's own record is never masked.
    assert _real_record(read_users(db, pid, student)[student.id], student)
    # Ordinary accounts are exported as before.
    assert _real_record(read_users(db, pid, w["teacher"])[w["teacher"].id], w["teacher"])


@pytest.mark.parametrize("read_users", [_ndjson_users, _comprehensive_users])
def test_export_users_block_follows_the_viewer_hook(
    export_world, read_users, monkeypatch
):
    import lms_name_masking

    w = export_world
    fake = _Viewers()
    monkeypatch.setattr(
        lms_name_masking.NameVisibility,
        "load",
        classmethod(lambda cls: cls(_protected, fake)),
    )
    db, pid, student = w["db"], w["project"].id, w["student"]

    assert _masked_record(read_users(db, pid, w["teacher"])[student.id], student)
    fake.allowed.add(w["teacher"].id)
    assert _real_record(read_users(db, pid, w["teacher"])[student.id], student)


def test_export_select_generator_passes_the_viewer(export_world, monkeypatch):
    import lms_name_masking
    from export_stream import select_export_generator

    w = export_world
    fake = _Viewers()
    fake.allowed.add(w["teacher"].id)
    monkeypatch.setattr(
        lms_name_masking.NameVisibility,
        "load",
        classmethod(lambda cls: cls(_protected, fake)),
    )
    for fmt in ("comprehensive", "ndjson"):
        body = "".join(
            select_export_generator(w["db"], w["project"], fmt, viewer=w["teacher"])
        )
        assert w["student"].name in body
        assert w["student"].email in body
    assert (w["teacher"].id, w["project"].id) in fake.calls


def test_failing_hooks_never_reveal_a_name(export_world, monkeypatch):
    import lms_name_masking

    def _boom(*args, **kwargs):
        raise RuntimeError("hook exploded")

    w = export_world
    monkeypatch.setattr(
        lms_name_masking.NameVisibility,
        "load",
        classmethod(lambda cls: cls(_boom, _boom)),
    )
    users = _ndjson_users(w["db"], w["project"].id, w["teacher"])
    # The link table still identifies the LMS student; the teacher is not
    # allowed while the viewer hook fails.
    assert _masked_record(users[w["student"].id], w["student"])
    assert _real_record(users[w["teacher"].id], w["teacher"])


def test_name_visibility_loads_the_extended_worker_hook(monkeypatch):
    import sys
    import types

    import extensions
    from lms_name_masking import NameVisibility

    # The API process uses the worker hook only while the extension loader
    # accepted the extended package.
    monkeypatch.setattr(extensions, "_extended", object())

    calls = []

    def lms_ids(db, org_id, ids):
        calls.append(("lms", org_id, list(ids)))
        return {"u1", "stranger"}

    def viewer(db, user, project_id, ids):
        calls.append(("viewer", user.id, project_id, list(ids)))
        return set()

    package = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    workers.get_name_visibility_fns = lambda: (lms_ids, viewer)
    package.workers = workers
    monkeypatch.setitem(sys.modules, "benger_extended", package)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)

    policy = NameVisibility.load()
    users = [
        types.SimpleNamespace(id="u1", pseudonym="A", use_pseudonym=True),
        types.SimpleNamespace(id="u2", pseudonym="B", use_pseudonym=True),
    ]
    viewer_user = types.SimpleNamespace(id="v1", is_superadmin=False)

    assert policy.masked_user_ids(None, users, project_id="p1", viewer=viewer_user) == {"u1"}
    assert calls == [("lms", None, ["u1", "u2"]), ("viewer", "v1", "p1", ["u1"])]

    # A package without the worker hook falls back to the link table.
    del workers.get_name_visibility_fns
    assert NameVisibility.load()._lms_user_ids is None


# --------------------------------------------------------------------------- #
# Masked exports imported again
# --------------------------------------------------------------------------- #
def _second_student_world(w):
    """export_world plus a second LMS student on the same task and a
    task-level assignment for each student; the teacher (the exporter and
    importer) is an org member so the import has an org to own the copy."""
    db = w["db"]
    project = w["project"]
    task_id = db.query(Task.id).filter(Task.project_id == project.id).scalar()
    second = _new_person("Max Muster", pseudonym="Stiller Bach")
    db.add(second)
    db.flush()
    link_row = db.query(LtiUserLink).filter(LtiUserLink.user_id == w["student"].id).one()
    registration = db.get(LtiPlatformRegistration, link_row.registration_id)
    db.add(_new_link(registration, second))
    db.add(
        Annotation(
            id=str(uuid.uuid4()),
            task_id=task_id,
            project_id=project.id,
            completed_by=second.id,
            result=[{"value": "Zweite Antwort"}],
        )
    )
    for user in (w["student"], second):
        db.add(
            TaskAssignment(
                id=str(uuid.uuid4()),
                task_id=task_id,
                user_id=user.id,
                assigned_by=w["teacher"].id,
                status="assigned",
            )
        )
    db.add(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=w["teacher"].id,
            organization_id=registration.organization_id,
            role=OrganizationRole.CONTRIBUTOR,
            is_active=True,
        )
    )
    db.commit()
    return second


def _export_body(fmt, db, project_id, viewer):
    from export_stream import stream_comprehensive_project_data_json, stream_export_ndjson

    stream = {
        "ndjson": stream_export_ndjson,
        "comprehensive": stream_comprehensive_project_data_json,
    }[fmt]
    return "".join(stream(db, project_id, viewer=viewer))


def _import(db, body, importer):
    import io

    from import_stream import run_full_project_import

    spool = io.BytesIO(body.encode("utf-8"))
    return run_full_project_import(db, spool, importer.id)


def _imported_project(db, source_id, importer):
    return (
        db.query(Project)
        .filter(Project.created_by == importer.id, Project.id != source_id)
        .order_by(Project.created_at.desc())
        .first()
    )


@pytest.mark.parametrize("fmt", ["ndjson", "comprehensive"])
def test_masked_export_reimport_keeps_each_students_work(export_world, fmt):
    """A copy on the same deployment keeps who wrote what, although the
    exporter saw the students only by pseudonym (no email in the file)."""
    w = export_world
    db, source = w["db"], w["project"]
    second = _second_student_world(w)
    body = _export_body(fmt, db, source.id, w["teacher"])
    assert w["student"].email not in body
    assert second.email not in body
    assert w["student"].username not in body

    _import(db, body, w["teacher"])

    copy = _imported_project(db, source.id, w["teacher"])
    assert copy is not None
    authors = {
        a.completed_by for a in db.query(Annotation).filter(Annotation.project_id == copy.id)
    }
    assert authors == {w["student"].id, second.id}
    assignees = {
        a.user_id
        for a in db.query(TaskAssignment)
        .join(Task, Task.id == TaskAssignment.task_id)
        .filter(Task.project_id == copy.id)
    }
    assert assignees == {w["student"].id, second.id}


@pytest.mark.parametrize("fmt", ["ndjson", "comprehensive"])
def test_masked_export_from_elsewhere_falls_back_without_failing(export_world, fmt):
    """Accounts the importing deployment does not know map to the importer.
    Two of them on one task collapse onto one user: the import keeps the
    first answer and one assignment instead of failing on the unique
    indexes."""
    w = export_world
    db, source = w["db"], w["project"]
    second = _second_student_world(w)
    body = _export_body(fmt, db, source.id, w["teacher"])
    for user in (w["student"], second):
        body = body.replace(user.id, f"elsewhere-{user.id[:8]}")

    _import(db, body, w["teacher"])

    copy = _imported_project(db, source.id, w["teacher"])
    assert copy is not None
    annotations = db.query(Annotation).filter(Annotation.project_id == copy.id).all()
    assert [a.completed_by for a in annotations] == [w["teacher"].id]
    assignments = (
        db.query(TaskAssignment)
        .join(Task, Task.id == TaskAssignment.task_id)
        .filter(Task.project_id == copy.id)
        .all()
    )
    assert [a.user_id for a in assignments] == [w["teacher"].id]


def test_masked_record_is_flagged_and_crafted_flags_need_a_known_id(export_world):
    """Only a record marked ``masked`` is matched by id, and only to an
    existing account."""
    from import_stream import _FullImportContext, _insert_user

    w = export_world
    db = w["db"]
    ctx = _FullImportContext(db, w["teacher"].id)
    _insert_user(ctx, {"id": w["student"].id, "email": None, "masked": True})
    _insert_user(ctx, {"id": w["superadmin"].id, "email": None})
    _insert_user(ctx, {"id": "nobody-here", "email": None, "masked": True})

    users = ctx.id_mappings["users"]
    assert users[w["student"].id] == w["student"].id
    assert ctx.matched_user_ids == {w["student"].id: w["student"].id}
    # Unflagged or unknown: the importer.
    assert users[w["superadmin"].id] == w["teacher"].id
    assert users["nobody-here"] == w["teacher"].id

    records = _ndjson_users(db, w["project"].id, w["teacher"])
    assert records[w["student"].id]["masked"] is True
    assert "masked" not in records[w["teacher"].id]
