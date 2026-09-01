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

Lives in /shared so the api, the workers, and the extended package import one
implementation. No fastapi/pydantic imports (worker container constraint);
sync + async variants follow the dual-mode pattern from the workspace
CLAUDE.md.
"""

from typing import Optional


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


def resolve_dispatch_org_for_project(db, user, project) -> Optional[str]:
    """Sync: org whose keys a dispatch on ``project`` may spend for ``user``.

    ``user`` may be a User object or a bare user id (worker contexts).
    """
    orgs = getattr(project, "organizations", None) or []
    if not orgs:
        return None
    from models import OrganizationMembership

    org_ids = {str(o.id) for o in orgs}
    user_id = _user_id_of(user)
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(org_ids),
        )
        .first()
    )
    if membership:
        return str(membership.organization_id)
    if _is_superadmin_sync(db, user):
        return str(orgs[0].id)
    return None


async def resolve_dispatch_org_for_project_async(
    db, user, project_id: str
) -> Optional[str]:
    """Async twin working from a project id (no loaded relationship)."""
    from sqlalchemy import select

    from models import OrganizationMembership, User
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
    member_org = (
        (
            await db.execute(
                select(OrganizationMembership.organization_id).where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.organization_id.in_(project_org_ids),
                    OrganizationMembership.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )
    if member_org:
        return str(member_org)
    is_superadmin = bool(getattr(user, "is_superadmin", None))
    if not is_superadmin and not hasattr(user, "is_superadmin"):
        row = (
            (
                await db.execute(
                    select(User.is_superadmin).where(User.id == user_id)
                )
            )
            .scalars()
            .first()
        )
        is_superadmin = bool(row)
    if is_superadmin:
        return str(project_org_ids[0])
    return None


async def validate_org_context_header_async(db, user, org_id) -> Optional[str]:
    """Async twin of :func:`validate_org_context_header`."""
    if not org_id:
        return None
    from sqlalchemy import select

    from models import OrganizationMembership

    user_id = _user_id_of(user)
    membership = (
        (
            await db.execute(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.organization_id == str(org_id),
                    OrganizationMembership.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )
    if membership:
        return str(org_id)
    if bool(getattr(user, "is_superadmin", False)):
        return str(org_id)
    return None


def validate_org_context_header(db, user, org_id) -> Optional[str]:
    """A client-supplied org context (``X-Organization-Context``) is honored
    only for an active member of that org (or a superadmin) — the middleware
    passes the header through unvalidated, so this is the trust boundary."""
    if not org_id:
        return None
    from models import OrganizationMembership

    user_id = _user_id_of(user)
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == str(org_id),
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )
    if membership:
        return str(org_id)
    if _is_superadmin_sync(db, user):
        return str(org_id)
    return None
