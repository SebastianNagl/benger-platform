"""Single source of truth for organization-group scoping.

Groups partition project visibility and provider API keys INSIDE an org
(org → group → user). The rule, stated once:

An attachment row ``(org O, group G)`` of project P is eligible for user U iff
    G IS NULL                          (org-wide attachment — pre-groups behavior)
    OR U is a superadmin
    OR U is P's creator                (creators never lose sight of their project)
    OR U holds an active ORG_ADMIN membership in O
    OR U is a member of G.

Full tier on exams additionally requires a staff role — org role != ANNOTATOR
OR U is a *group admin* of G (invariant: group admin ⇒ admin powers on the
group's projects, regardless of org role).

Everything here exists in exactly one form so the many enforcement sites
(project list arms, per-project deciders, participant/student arms, admin
gates, key resolution) cannot drift. Lives in /shared so the api, the
workers, and the extended package import one implementation. No
fastapi/pydantic imports (worker container constraint); sync + async
variants follow the dual-mode pattern from the workspace CLAUDE.md.

Group ``is_active`` is deliberately NOT consulted by any predicate here:
deactivating a group hides it from pickers and blocks new attachments, but
never silently changes visibility or key scope of existing rows.
"""

from typing import Dict, Optional


def _role_value(role) -> Optional[str]:
    """Normalize an OrganizationRole enum or bare string to its upper value."""
    if role is None:
        return None
    return str(getattr(role, "value", role)).upper()


# ---------------------------------------------------------------------------
# Pure predicates (no DB access) — shared by the sync/async decision lanes.
# ---------------------------------------------------------------------------


def attachment_eligible(
    group_id: Optional[str],
    *,
    is_superadmin: bool = False,
    is_creator: bool = False,
    membership_role=None,
    user_groups: Optional[Dict[str, bool]] = None,
) -> bool:
    """Is one org attachment visible to the user? (the module-docstring rule)

    ``membership_role`` is the user's role in THAT org (None = not a member —
    callers gate org membership separately, this only decides the group axis).
    ``user_groups`` maps group_id → is_group_admin for the user's group
    memberships (any org — group ids are globally unique and composite FKs
    guarantee an attachment's group belongs to the attachment's org).
    """
    if group_id is None:
        return True
    if is_superadmin or is_creator:
        return True
    if _role_value(membership_role) == "ORG_ADMIN":
        return True
    return group_id in (user_groups or {})


def grants_full_tier(
    project_kind: Optional[str],
    membership_role,
    group_id: Optional[str] = None,
    user_groups: Optional[Dict[str, bool]] = None,
) -> bool:
    """Does an (eligible) org membership grant the FULL tier on this project?

    Non-exams: always. Exams: staff only — ANNOTATORs reach org exams through
    the narrow participant tier instead, EXCEPT when they group-admin the
    attachment's group (group admin ⇒ admin on the group's projects).
    """
    if project_kind != "exam":
        return True
    if _role_value(membership_role) != "ANNOTATOR":
        return True
    return bool(group_id is not None and (user_groups or {}).get(group_id, False))


# ---------------------------------------------------------------------------
# SQL builders (core expressions — usable from both db.query and select lanes)
# ---------------------------------------------------------------------------


def build_select_user_group_ids(user_id: str, admin_only: bool = False):
    """Select of the user's group ids (optionally only group-admin ones)."""
    from sqlalchemy import select

    from models import OrganizationGroupMembership

    stmt = select(OrganizationGroupMembership.group_id).where(
        OrganizationGroupMembership.user_id == str(user_id)
    )
    if admin_only:
        stmt = stmt.where(OrganizationGroupMembership.is_group_admin.is_(True))
    return stmt


def build_select_group_admin_on_attachments(user_id: str, project_id: str):
    """Select yielding a row iff the user group-admins ANY of the project's
    grouped attachments — the group-admin arm of the ORG_ADMIN-only gates
    (Musterlösung edit, share-link management)."""
    from sqlalchemy import select

    from models import OrganizationGroupMembership
    from project_models import ProjectOrganization

    return (
        select(OrganizationGroupMembership.id)
        .join(
            ProjectOrganization,
            ProjectOrganization.group_id == OrganizationGroupMembership.group_id,
        )
        .where(
            ProjectOrganization.project_id == str(project_id),
            OrganizationGroupMembership.user_id == str(user_id),
            OrganizationGroupMembership.is_group_admin.is_(True),
        )
        .limit(1)
    )


def group_member_fan_in_clause(po, om):
    """Which org MEMBERS belong to a project's org fan-in (project rosters,
    assignee eligibility, notification recipients): the whole org for an
    ungrouped attachment; the group's members plus the org's ORG_ADMINs for
    a grouped one. ``po``/``om`` are the joined ProjectOrganization /
    OrganizationMembership entities of the query."""
    from sqlalchemy import or_, select

    from models import OrganizationGroupMembership, OrganizationRole

    return or_(
        po.group_id.is_(None),
        om.role == OrganizationRole.ORG_ADMIN,
        om.user_id.in_(
            select(OrganizationGroupMembership.user_id).where(
                OrganizationGroupMembership.group_id == po.group_id
            )
        ),
    )


def attachment_group_clause(po, user_id: str, *, membership=None, project=None):
    """The eligibility predicate as a composable SQL clause for list arms.

    ``po`` is the (possibly aliased) ProjectOrganization entity of the query;
    pass ``membership`` (OrganizationMembership entity, when joined) to get
    the ORG_ADMIN arm and ``project`` (Project entity) to get the creator arm
    — omit what a given arm's superadmin/creator handling already covers.
    """
    from sqlalchemy import or_

    conditions = [
        po.group_id.is_(None),
        po.group_id.in_(build_select_user_group_ids(user_id)),
    ]
    if membership is not None:
        from models import OrganizationRole

        conditions.append(membership.role == OrganizationRole.ORG_ADMIN)
    if project is not None:
        conditions.append(project.created_by == str(user_id))
    return or_(*conditions)


# ---------------------------------------------------------------------------
# Loaders (dual-mode) — the inputs the pure deciders need.
# ---------------------------------------------------------------------------


def get_user_group_context(db, user_id: str) -> Dict[str, bool]:
    """Sync: the user's group memberships as {group_id: is_group_admin}."""
    from models import OrganizationGroupMembership

    rows = (
        db.query(
            OrganizationGroupMembership.group_id,
            OrganizationGroupMembership.is_group_admin,
        )
        .filter(OrganizationGroupMembership.user_id == str(user_id))
        .all()
    )
    return {str(r[0]): bool(r[1]) for r in rows}


async def get_user_group_context_async(db, user_id: str) -> Dict[str, bool]:
    """Async twin of :func:`get_user_group_context`."""
    from sqlalchemy import select

    from models import OrganizationGroupMembership

    result = await db.execute(
        select(
            OrganizationGroupMembership.group_id,
            OrganizationGroupMembership.is_group_admin,
        ).where(OrganizationGroupMembership.user_id == str(user_id))
    )
    return {str(gid): bool(admin) for gid, admin in result.all()}


def get_attachment_group_map(db, project_id: str) -> Dict[str, Optional[str]]:
    """Sync: the project's org attachments as {org_id: group_id | None}."""
    from project_models import ProjectOrganization

    rows = (
        db.query(
            ProjectOrganization.organization_id, ProjectOrganization.group_id
        )
        .filter(ProjectOrganization.project_id == str(project_id))
        .all()
    )
    return {str(org): (str(gid) if gid else None) for org, gid in rows}


async def get_attachment_group_map_async(db, project_id: str) -> Dict[str, Optional[str]]:
    """Async twin of :func:`get_attachment_group_map`."""
    from sqlalchemy import select

    from project_models import ProjectOrganization

    result = await db.execute(
        select(
            ProjectOrganization.organization_id, ProjectOrganization.group_id
        ).where(ProjectOrganization.project_id == str(project_id))
    )
    return {str(org): (str(gid) if gid else None) for org, gid in result.all()}


def resolve_project_group_for_org(db, project_id, org_id) -> Optional[str]:
    """Sync: the group scoping the project's attachment to ``org_id``.

    None when the attachment is org-wide, missing, or the ids are falsy —
    key resolution then uses the org-wide key pool. The key follows the
    PROJECT's attachment, never the dispatching user's groups.
    """
    if not project_id or not org_id:
        return None
    from project_models import ProjectOrganization

    row = (
        db.query(ProjectOrganization.group_id)
        .filter(
            ProjectOrganization.project_id == str(project_id),
            ProjectOrganization.organization_id == str(org_id),
        )
        .first()
    )
    return str(row[0]) if row and row[0] else None


async def resolve_project_group_for_org_async(db, project_id, org_id) -> Optional[str]:
    """Async twin of :func:`resolve_project_group_for_org`."""
    if not project_id or not org_id:
        return None
    from sqlalchemy import select

    from project_models import ProjectOrganization

    row = (
        await db.execute(
            select(ProjectOrganization.group_id).where(
                ProjectOrganization.project_id == str(project_id),
                ProjectOrganization.organization_id == str(org_id),
            )
        )
    ).scalar_one_or_none()
    return str(row) if row else None
