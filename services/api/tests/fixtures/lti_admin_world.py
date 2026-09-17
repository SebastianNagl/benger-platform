"""Seed helpers for the LMS connection admin tests (``/api/admin/lti``).

Imported explicitly by ``tests/routers/test_lti_admin*.py``; not a fixture
plugin. Everything is written through the async test session, which rolls
back after each test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import (
    LtiDeployment,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiRegistrationInvite,
    LtiResourceLink,
    LtiResourceLinkUser,
    LtiUserLink,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, Task

MAIN_URL = "https://main.example.test"
STUDENT_URL = "https://student.example.test"
LINEITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"


def _hex() -> str:
    return uuid.uuid4().hex[:10]


def set_tool_host_env(monkeypatch, *, student: bool = True) -> None:
    """Both tool hosts configured (or only the main one)."""
    monkeypatch.setenv("FRONTEND_URL", MAIN_URL + "/")
    if student:
        monkeypatch.setenv("VERTRETBAR_FRONTEND_URL", STUDENT_URL)
    else:
        monkeypatch.delenv("VERTRETBAR_FRONTEND_URL", raising=False)


@contextmanager
def as_user(db_user):
    """Serve every request of the block as ``db_user``."""
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


class FakeExtended:
    """Stand-in for a loaded extended package with the given hooks."""

    COMPATIBLE_CORE_VERSIONS = ["2.20"]

    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


async def make_user(db, *, superadmin: bool = False, name: Optional[str] = None):
    suffix = _hex()
    user = User(
        id=str(uuid.uuid4()),
        username=f"lti-admin-{suffix}",
        email=f"lti-admin-{suffix}@example.com",
        name=name or f"Real Name {suffix}",
        pseudonym=f"Pseudo-{suffix}",
        use_pseudonym=True,
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def make_org(db, *, active: bool = True) -> Organization:
    suffix = _hex()
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"lti-org-{suffix}",
        display_name="LTI Test Org",
        slug=f"lti-org-{suffix}",
        is_active=active,
    )
    db.add(org)
    await db.flush()
    return org


async def make_group(db, org, *, active: bool = True) -> OrganizationGroup:
    group = OrganizationGroup(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name=f"Chair {_hex()}",
        is_active=active,
    )
    db.add(group)
    await db.flush()
    return group


async def add_member(db, user, org, role: OrganizationRole, *, active: bool = True):
    db.add(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=active,
        )
    )
    await db.flush()


async def add_group_member(db, user, group, *, admin: bool):
    db.add(
        OrganizationGroupMembership(
            id=str(uuid.uuid4()),
            group_id=group.id,
            user_id=user.id,
            is_group_admin=admin,
        )
    )
    await db.flush()


def registration_payload(organization_id: str, **overrides) -> dict:
    body = {
        "organization_id": organization_id,
        "name": "Uni Passau Moodle",
        "issuer": "https://moodle.uni-passau.de",
        "client_id": f"client-{_hex()}",
        "auth_login_url": "https://moodle.uni-passau.de/mod/lti/auth.php",
        "auth_token_url": "https://moodle.uni-passau.de/mod/lti/token.php",
        "jwks_uri": "https://moodle.uni-passau.de/mod/lti/certs.php",
        "deployment_ids": ["1"],
    }
    body.update(overrides)
    return body


async def make_registration(
    db,
    org,
    *,
    group=None,
    status: str = "active",
    name: str = "Seeded Moodle",
    tool_host: str = "student_locked",
    deployment_ids=("1",),
    instructor_org_role: str = "contributor",
) -> LtiPlatformRegistration:
    host = f"https://lms-{_hex()}.example.com"
    reg = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        group_id=group.id if group is not None else None,
        name=name,
        issuer=host,
        client_id=f"client-{_hex()}",
        auth_login_url=f"{host}/auth",
        auth_token_url=f"{host}/token",
        jwks_uri=f"{host}/certs",
        status=status,
        tool_host=tool_host,
        instructor_org_role=instructor_org_role,
    )
    db.add(reg)
    await db.flush()
    for deployment_id in deployment_ids:
        db.add(
            LtiDeployment(
                id=str(uuid.uuid4()),
                registration_id=reg.id,
                deployment_id=deployment_id,
            )
        )
    await db.flush()
    return reg


async def make_project(db, owner, *, tasks: int = 1, title: str = "Probeklausur"):
    project = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner.id,
        is_private=True,
        kind="exam",
        origin="student",
    )
    db.add(project)
    await db.flush()
    for index in range(tasks):
        db.add(
            Task(
                id=str(uuid.uuid4()),
                project_id=project.id,
                data={"sachverhalt": "S"},
                inner_id=index + 1,
            )
        )
    await db.flush()
    return project


async def make_resource_link(db, reg, *, project=None, **fields) -> LtiResourceLink:
    link = LtiResourceLink(
        id=str(uuid.uuid4()),
        registration_id=reg.id,
        deployment_id="1",
        resource_link_id=f"rl-{_hex()}",
        project_id=project.id if project is not None else None,
        **fields,
    )
    db.add(link)
    await db.flush()
    return link


async def make_user_link(
    db, reg, user, *, link_method: Optional[str] = "provisioned", **fields
) -> LtiUserLink:
    link = LtiUserLink(
        id=str(uuid.uuid4()),
        registration_id=reg.id,
        sub=f"sub-{_hex()}",
        user_id=user.id,
        link_method=link_method,
        claims={"name": user.name, "email": user.email, "roles": []},
        consent_at=datetime.now(timezone.utc),
        consent_version="lti-2",
        **fields,
    )
    db.add(link)
    await db.flush()
    return link


async def make_participation(db, link, user, *, instructor: bool = False):
    row = LtiResourceLinkUser(
        id=str(uuid.uuid4()),
        resource_link_id=link.id,
        user_id=user.id,
        is_instructor=instructor,
    )
    db.add(row)
    await db.flush()
    return row


async def make_grade_sync(
    db, link, user, *, status: str = "failed", kind: str = "final"
) -> LtiGradeSync:
    sync = LtiGradeSync(
        id=str(uuid.uuid4()),
        resource_link_id=link.id,
        user_id=user.id,
        kind=kind,
        status=status,
        attempts=3 if status == "failed" else 0,
        last_error="AGS lineitem POST returned 500" if status == "failed" else None,
    )
    db.add(sync)
    await db.flush()
    return sync


async def make_invite(db, org, *, group=None, creator=None) -> LtiRegistrationInvite:
    invite = LtiRegistrationInvite(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        group_id=group.id if group is not None else None,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        created_by=creator.id if creator is not None else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db.add(invite)
    await db.flush()
    return invite


@dataclass
class World:
    """One university org with two chairs, a foreign org and every role."""

    org: Organization
    other_org: Organization
    group_a: OrganizationGroup
    group_b: OrganizationGroup
    superadmin: User
    org_admin: User
    foreign_admin: User
    # CONTRIBUTOR in the org and admin of group A.
    group_admin: User
    # ANNOTATOR in the org and admin of group A.
    annotator_group_admin: User
    contributor: User
    member: User
    stranger: User


async def build_world(db) -> World:
    org = await make_org(db)
    other_org = await make_org(db)
    group_a = await make_group(db, org)
    group_b = await make_group(db, org)

    superadmin = await make_user(db, superadmin=True)
    org_admin = await make_user(db)
    await add_member(db, org_admin, org, OrganizationRole.ORG_ADMIN)
    foreign_admin = await make_user(db)
    await add_member(db, foreign_admin, other_org, OrganizationRole.ORG_ADMIN)
    group_admin = await make_user(db)
    await add_member(db, group_admin, org, OrganizationRole.CONTRIBUTOR)
    await add_group_member(db, group_admin, group_a, admin=True)
    await add_group_member(db, group_admin, group_b, admin=False)
    annotator_group_admin = await make_user(db)
    await add_member(db, annotator_group_admin, org, OrganizationRole.ANNOTATOR)
    await add_group_member(db, annotator_group_admin, group_a, admin=True)
    contributor = await make_user(db)
    await add_member(db, contributor, org, OrganizationRole.CONTRIBUTOR)
    await add_group_member(db, contributor, group_a, admin=False)
    member = await make_user(db)
    await add_member(db, member, org, OrganizationRole.ANNOTATOR)
    stranger = await make_user(db)
    await db.commit()
    return World(
        org=org,
        other_org=other_org,
        group_a=group_a,
        group_b=group_b,
        superadmin=superadmin,
        org_admin=org_admin,
        foreign_admin=foreign_admin,
        group_admin=group_admin,
        annotator_group_admin=annotator_group_admin,
        contributor=contributor,
        member=member,
        stranger=stranger,
    )


def detail_code(response) -> Optional[str]:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None
