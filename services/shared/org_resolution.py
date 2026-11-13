"""Single source of truth for dispatch-time org resolution.

Which organization's API keys may an LLM dispatch (generation, evaluation,
rubric proposal, …) spend on behalf of a user? Three independently drifting
copies of this decision existed (``routers/evaluations/helpers.py``,
``immediate_eval_dispatch.resolve_org``, and an async replica in the extended
bewertungsbogen router) — the same project and user could bill a different
key depending on which button was pressed. They now all delegate here.

Semantics (2026-08-31, per the owner's who-pays rule):

- the user's first ACTIVE membership among the project's orgs wins;
- a superadmin without a membership falls back to the project's first org
  (admin backfills keep working);
- everyone else resolves to ``None`` → personal-key resolution. The old
  unconditional first-org fallback let any project-visible non-member spend
  an org-pays org's key.

A caller who could bill more than one org may name the payer instead
(``requested_org_id``, the "billed to" picker of the generation and
evaluation dialogs). The choice must be one of :func:`billing_org_options`:
an org attached to the project that provides keys there, and that the
caller is an active member of (superadmins: any attached org). Anything else
raises :class:`BillingOrgNotAllowed`; the default rule above applies only
when nothing is requested.

A run the caller starts by hand (generation, evaluation) passes
``min_role="CONTRIBUTOR"``: only a membership whose role on the project's
attachment of that org (``org_groups.attachment_role``: the org role, or the
group role on a grouped attachment) is CONTRIBUTOR or higher may spend the
org's keys, the same role the app requires to start such a run. An
ANNOTATOR membership then counts as no membership (personal keys). Without
``min_role`` (grading that an annotator's submission triggers on a project
an editor configured) every active membership counts.

Lives in /shared so the api, the workers, and the extended package import one
implementation. No fastapi/pydantic imports (worker container constraint);
sync + async variants follow the dual-mode pattern from the workspace
CLAUDE.md.
"""

from typing import Dict, List, Optional


class BillingOrgNotAllowed(Exception):
    """The requested paying org is not one the caller may bill here."""


def _user_id_of(user) -> Optional[str]:
    """Accept a User object or a bare id."""
    if user is None:
        return None
    return str(getattr(user, "id", user))


def _is_superadmin_sync(db, user) -> bool:
    """Fail-closed superadmin check; avoids a query when the object knows."""
    if user is None:
        return False
    if hasattr(user, "is_superadmin"):
        return bool(user.is_superadmin)
    try:
        from models import User

        row = db.query(User.is_superadmin).filter(User.id == str(user)).first()
        return bool(row and row[0])
    except Exception:
        return False


def _eligible_member_org_ids_sync(db, user_id, project_id, member_rows, min_role):
    """The org ids among ``member_rows`` ((org_id, org_role) pairs of ACTIVE
    memberships in the project's orgs) whose attachment role reaches
    ``min_role``; all of them when ``min_role`` is None."""
    if not min_role:
        return {str(org_id) for org_id, _ in member_rows}
    from org_groups import (
        attachment_role,
        get_attachment_group_map,
        get_user_group_context,
        role_at_least,
    )

    groups = get_attachment_group_map(db, str(project_id))
    user_groups = get_user_group_context(db, str(user_id))
    return {
        str(org_id)
        for org_id, org_role in member_rows
        if role_at_least(
            attachment_role(groups.get(str(org_id)), org_role, user_groups), min_role
        )
    }


async def _eligible_member_org_ids_async(db, user_id, project_id, member_rows, min_role):
    """Async twin of :func:`_eligible_member_org_ids_sync`."""
    if not min_role:
        return {str(org_id) for org_id, _ in member_rows}
    from org_groups import (
        attachment_role,
        get_attachment_group_map_async,
        get_user_group_context_async,
        role_at_least,
    )

    groups = await get_attachment_group_map_async(db, str(project_id))
    user_groups = await get_user_group_context_async(db, str(user_id))
    return {
        str(org_id)
        for org_id, org_role in member_rows
        if role_at_least(
            attachment_role(groups.get(str(org_id)), org_role, user_groups), min_role
        )
    }


def _payer_options(orgs, member_org_ids, is_superadmin, org_pays) -> List[Dict[str, str]]:
    """The billable subset of a project's ``(id, name)`` orgs, by name.

    Superadmins may bill any attached org, everyone else only the ones they
    are an active member of; either way only orgs that provide keys on the
    project (``org_pays``: org id → bool) count, since naming a members-pay
    org would just spend the personal key."""
    options = [
        {"id": org_id, "name": name}
        for org_id, name in orgs
        if (is_superadmin or org_id in member_org_ids) and org_pays.get(org_id)
    ]
    return sorted(options, key=lambda o: (o["name"].casefold(), o["id"]))


def billing_org_options(
    db, user, project, *, min_role: Optional[str] = None
) -> List[Dict[str, str]]:
    """Sync: the orgs ``user`` may bill for a dispatch on ``project``
    (``min_role``: see the module docstring)."""
    orgs = getattr(project, "organizations", None) or []
    if not orgs:
        return []
    from models import OrganizationMembership
    from org_groups import org_pays_for_project

    org_ids = [str(o.id) for o in orgs]
    member_rows = (
        db.query(OrganizationMembership.organization_id, OrganizationMembership.role)
        .filter(
            OrganizationMembership.user_id == _user_id_of(user),
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(org_ids),
        )
        .all()
    )
    member_org_ids = _eligible_member_org_ids_sync(
        db, _user_id_of(user), project.id, member_rows, min_role
    )
    is_superadmin = _is_superadmin_sync(db, user)
    candidates = [o for o in org_ids if is_superadmin or o in member_org_ids]
    org_pays = {o: org_pays_for_project(db, o, project) for o in candidates}
    return _payer_options(
        [(str(o.id), o.display_name or o.name) for o in orgs],
        member_org_ids,
        is_superadmin,
        org_pays,
    )


def _check_requested_org(options, requested_org_id) -> str:
    if str(requested_org_id) not in {o["id"] for o in options}:
        raise BillingOrgNotAllowed(
            "You cannot bill this organization for runs on this project"
        )
    return str(requested_org_id)


def resolve_dispatch_org_for_project(
    db,
    user,
    project,
    requested_org_id: Optional[str] = None,
    *,
    min_role: Optional[str] = None,
) -> Optional[str]:
    """Sync: org whose keys a dispatch on ``project`` may spend for ``user``.

    ``user`` may be a User object or a bare user id (worker contexts).
    ``requested_org_id`` is the caller's explicit payer; it must be one of
    :func:`billing_org_options` or :class:`BillingOrgNotAllowed` is raised.
    ``min_role``: see the module docstring.
    """
    if requested_org_id:
        return _check_requested_org(
            billing_org_options(db, user, project, min_role=min_role),
            requested_org_id,
        )
    orgs = getattr(project, "organizations", None) or []
    if not orgs:
        return None
    from models import OrganizationMembership

    org_ids = {str(o.id) for o in orgs}
    user_id = _user_id_of(user)
    member_rows = (
        db.query(OrganizationMembership.organization_id, OrganizationMembership.role)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(org_ids),
        )
        # A fixed order: the dialogs show this default before a run starts,
        # so the run must resolve to the same org every time.
        .order_by(OrganizationMembership.organization_id)
        .all()
    )
    eligible = _eligible_member_org_ids_sync(
        db, user_id, project.id, member_rows, min_role
    )
    for org_id, _ in member_rows:
        if str(org_id) in eligible:
            return str(org_id)
    if _is_superadmin_sync(db, user):
        return min(org_ids)
    return None


async def _is_superadmin_async(db, user) -> bool:
    if hasattr(user, "is_superadmin"):
        return bool(user.is_superadmin)
    from sqlalchemy import select

    from models import User

    row = (
        (await db.execute(select(User.is_superadmin).where(User.id == _user_id_of(user))))
        .scalars()
        .first()
    )
    return bool(row)


async def billing_org_options_async(
    db, user, project_id: str, *, min_role: Optional[str] = None
) -> List[Dict[str, str]]:
    """Async twin of :func:`billing_org_options` working from a project id."""
    from sqlalchemy import select

    from models import Organization, OrganizationMembership
    from org_groups import require_private_keys_for_async, resolve_project_group_for_org_async
    from project_models import ProjectOrganization

    rows = (
        await db.execute(
            select(Organization.id, Organization.display_name, Organization.name)
            .join(ProjectOrganization, ProjectOrganization.organization_id == Organization.id)
            .where(ProjectOrganization.project_id == str(project_id))
        )
    ).all()
    if not rows:
        return []
    orgs = [(str(r[0]), r[1] or r[2]) for r in rows]
    org_ids = [o for o, _ in orgs]
    member_rows = (
        await db.execute(
            select(
                OrganizationMembership.organization_id, OrganizationMembership.role
            ).where(
                OrganizationMembership.user_id == _user_id_of(user),
                OrganizationMembership.organization_id.in_(org_ids),
                OrganizationMembership.is_active.is_(True),
            )
        )
    ).all()
    member_org_ids = await _eligible_member_org_ids_async(
        db, _user_id_of(user), project_id, member_rows, min_role
    )
    is_superadmin = await _is_superadmin_async(db, user)
    org_pays = {}
    for org_id in org_ids:
        if not (is_superadmin or org_id in member_org_ids):
            continue
        group_id = await resolve_project_group_for_org_async(db, project_id, org_id)
        org_pays[org_id] = not await require_private_keys_for_async(db, org_id, group_id)
    return _payer_options(orgs, member_org_ids, is_superadmin, org_pays)


async def resolve_dispatch_org_for_project_async(
    db,
    user,
    project_id: str,
    requested_org_id: Optional[str] = None,
    *,
    min_role: Optional[str] = None,
) -> Optional[str]:
    """Async twin working from a project id (no loaded relationship)."""
    from sqlalchemy import select

    if requested_org_id:
        return _check_requested_org(
            await billing_org_options_async(db, user, project_id, min_role=min_role),
            requested_org_id,
        )

    from models import OrganizationMembership
    from project_models import ProjectOrganization

    project_org_ids = (
        (
            await db.execute(
                select(ProjectOrganization.organization_id).where(
                    ProjectOrganization.project_id == str(project_id)
                )
            )
        )
        .scalars()
        .all()
    )
    if not project_org_ids:
        return None
    user_id = _user_id_of(user)
    member_rows = (
        await db.execute(
            select(
                OrganizationMembership.organization_id, OrganizationMembership.role
            )
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id.in_(project_org_ids),
                OrganizationMembership.is_active.is_(True),
            )
            # Same fixed order as the sync twin.
            .order_by(OrganizationMembership.organization_id)
        )
    ).all()
    eligible = await _eligible_member_org_ids_async(
        db, user_id, project_id, member_rows, min_role
    )
    for org_id, _ in member_rows:
        if str(org_id) in eligible:
            return str(org_id)
    if await _is_superadmin_async(db, user):
        return min(str(o) for o in project_org_ids)
    return None
