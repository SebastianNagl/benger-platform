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

Private exams are creator-only, with one exception: an attachment created by
linking the exam to an LMS activity (``attached_via='lti'``) gives that org's
eligible staff the full tier (:func:`lti_staff_role`), whatever org context
the client sends, as long as a connection of that org still links the exam.
It never gives students anything on a private exam, and on an org whose
connections stay superadmin-run it gives only that org's admins access.
That last rule holds at every visibility: on a non-private exam, an LMS
attachment of such an org counts only for its admins and the attachment
group's admins (:func:`drop_protected_lti_attachments`).

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

from typing import Dict, Iterable, Optional


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


_STAFF_ROLE_RANK = {"CONTRIBUTOR": 1, "ORG_ADMIN": 2}


def lti_staff_role(
    project_kind: Optional[str],
    memberships,
    lti_attachments: Optional[Dict[str, Optional[str]]],
    user_groups: Optional[Dict[str, bool]] = None,
    protected_org_ids: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """The staff role an LMS attachment grants on a PRIVATE exam, or None.

    Linking an exam to an LMS activity attaches it to the connection's org
    (``attached_via='lti'``, map from :func:`get_lti_attachment_map`). On a
    private exam that attachment is the only org path, and it is staff-only:
    an ACTIVE membership in an attached org whose role is CONTRIBUTOR or
    ORG_ADMIN, eligible for the attachment's group, gets the role back. A
    group admin of the attachment's group counts as ``'ORG_ADMIN'`` whatever
    their org role (an ANNOTATOR included); every other ANNOTATOR gets None,
    so LMS students never reach the full tier this way. The best role over
    all memberships wins.

    ``protected_org_ids`` are orgs whose LMS connections stay
    superadmin-run (``extensions.is_lti_protected_org``, resolved fail-closed
    by the caller). Every LMS teacher of such a connection is a CONTRIBUTOR
    there, so only its org admins and the attachment group's admins count;
    its contributors get nothing from the attachment.

    The grant does not depend on the organization the client has selected
    (every active membership counts). Callers handle the creator and superadmins. On private projects the
    input is :func:`get_lti_attachment_map`. Non-private exams keep the
    generic rules (every membership counts, whatever the client's context),
    except that an LMS attachment of a protected org is first dropped for
    everyone but its admins (:func:`drop_protected_lti_attachments`).
    """
    if project_kind != "exam" or not lti_attachments:
        return None
    protected = {str(org_id) for org_id in (protected_org_ids or ()) if org_id}
    best: Optional[str] = None
    for membership in memberships or ():
        org_id = str(membership.organization_id)
        if org_id not in lti_attachments or not membership.is_active:
            continue
        group_id = lti_attachments[org_id]
        if not attachment_eligible(
            group_id, membership_role=membership.role, user_groups=user_groups
        ):
            continue
        if not grants_full_tier(project_kind, membership.role, group_id, user_groups):
            continue
        if group_id is not None and (user_groups or {}).get(group_id, False):
            role = "ORG_ADMIN"
        else:
            role = _role_value(membership.role)
        if role not in _STAFF_ROLE_RANK:
            continue
        if org_id in protected and role != "ORG_ADMIN":
            continue
        if best is None or _STAFF_ROLE_RANK[role] > _STAFF_ROLE_RANK[best]:
            best = role
    return best


def drop_protected_lti_attachments(
    attachment_groups: Dict[str, Optional[str]],
    protected_lti_org_ids: Iterable[str],
    memberships,
    user_groups: Optional[Dict[str, bool]] = None,
) -> Dict[str, Optional[str]]:
    """``attachment_groups`` without the LMS attachments of protected orgs
    that do not count for this user (pure).

    For someone else's NON-private exam. ``protected_lti_org_ids`` are the
    orgs among the project's ``attached_via='lti'`` rows (stale ones
    included) whose connections stay superadmin-run. Such a row counts only
    for an active ORG_ADMIN of that org and for an active member who
    group-admins the row's group; everyone else is treated as if the org
    were not attached, the same rule :func:`lti_staff_role` applies to
    private exams. Every pilot teacher is a CONTRIBUTOR of that org, so
    without this the generic rules made them editors of each other's
    linked exams.
    """
    protected = {str(org_id) for org_id in (protected_lti_org_ids or ()) if org_id}
    if not protected or not attachment_groups:
        return dict(attachment_groups or {})
    kept: Dict[str, Optional[str]] = {}
    for org_id, group_id in attachment_groups.items():
        if str(org_id) not in protected:
            kept[org_id] = group_id
            continue
        for membership in memberships or ():
            if str(membership.organization_id) != str(org_id) or not membership.is_active:
                continue
            if _role_value(membership.role) == "ORG_ADMIN" or (
                group_id is not None and (user_groups or {}).get(group_id, False)
            ):
                kept[org_id] = group_id
                break
    return kept


# ---------------------------------------------------------------------------
# SQL builders (core expressions — usable from both db.query and select lanes)
# ---------------------------------------------------------------------------


def non_lti_attachment(po):
    """SQL clause: the attachment row was NOT created by LMS linking.

    ``po`` is the (possibly aliased) ProjectOrganization entity. Used where a
    manual share and a linking attachment must be told apart (share-link
    management, the visibility settings)."""
    return po.attached_via != "lti"


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


def _lti_attachment_filters(project_id: str):
    """WHERE clauses of the project's LMS-linking attachments.

    Only rows with ``attached_via='lti'`` whose org still owns a connection
    with an activity linked to the project. A row that outlived its link
    (a relink before the cleanup existed; migration 106 marked every
    attachment of a private exam as ``lti``) grants nothing.
    """
    from sqlalchemy import exists

    from models import LtiPlatformRegistration, LtiResourceLink
    from project_models import ProjectOrganization

    still_linked = exists().where(
        LtiResourceLink.project_id == ProjectOrganization.project_id,
        LtiResourceLink.registration_id == LtiPlatformRegistration.id,
        LtiPlatformRegistration.organization_id == ProjectOrganization.organization_id,
    )
    return (
        ProjectOrganization.project_id == str(project_id),
        ProjectOrganization.attached_via == "lti",
        still_linked,
    )


def get_lti_attachment_map(db, project_id: str) -> Dict[str, Optional[str]]:
    """Sync: the project's LMS-linking attachments as {org_id: group_id | None}.

    The input of :func:`lti_staff_role` (see :func:`_lti_attachment_filters`
    for which rows count).
    """
    from project_models import ProjectOrganization

    rows = (
        db.query(
            ProjectOrganization.organization_id, ProjectOrganization.group_id
        )
        .filter(*_lti_attachment_filters(project_id))
        .all()
    )
    return {str(org): (str(gid) if gid else None) for org, gid in rows}


async def get_lti_attachment_map_async(db, project_id: str) -> Dict[str, Optional[str]]:
    """Async twin of :func:`get_lti_attachment_map`."""
    from sqlalchemy import select

    from project_models import ProjectOrganization

    result = await db.execute(
        select(
            ProjectOrganization.organization_id, ProjectOrganization.group_id
        ).where(*_lti_attachment_filters(project_id))
    )
    return {str(org): (str(gid) if gid else None) for org, gid in result.all()}


def _build_select_lti_row_org_ids(project_id: str):
    from sqlalchemy import select

    from project_models import ProjectOrganization

    return select(ProjectOrganization.organization_id).where(
        ProjectOrganization.project_id == str(project_id),
        ProjectOrganization.attached_via == "lti",
    )


def get_lti_row_org_ids(db, project_id: str) -> set:
    """Sync: the orgs of every ``attached_via='lti'`` row of the project,
    whether or not a connection still links it (the input of
    :func:`drop_protected_lti_attachments`, like the Korrektur grader rule)."""
    rows = db.execute(_build_select_lti_row_org_ids(project_id)).scalars().all()
    return {str(org_id) for org_id in rows}


async def get_lti_row_org_ids_async(db, project_id: str) -> set:
    """Async twin of :func:`get_lti_row_org_ids`."""
    result = await db.execute(_build_select_lti_row_org_ids(project_id))
    return {str(org_id) for org_id in result.scalars().all()}


# ---------------------------------------------------------------------------
# LMS-linking attachments follow the org's connections
# ---------------------------------------------------------------------------


def collapse_linking_groups(rows) -> Dict[str, Optional[str]]:
    """``{key: group_id | None}`` from ``(key, group_id)`` rows of the
    connections that link something (pure).

    The group a linking attachment carries: None when any of those
    connections is org-wide, else the first of their groups in sorted order.
    """
    found: Dict[str, set] = {}
    for key, group_id in rows:
        found.setdefault(str(key), set()).add(str(group_id) if group_id else None)
    return {
        key: None if None in groups else sorted(groups)[0]
        for key, groups in found.items()
    }


def _build_select_org_linking_groups(
    organization_id: str, project_ids, exclude_registration_id=None
):
    """(project, connection group) of the org's connections whose
    activities point at ``project_ids``."""
    from sqlalchemy import select

    from models import LtiPlatformRegistration, LtiResourceLink

    stmt = (
        select(LtiResourceLink.project_id, LtiPlatformRegistration.group_id)
        .join(
            LtiPlatformRegistration,
            LtiPlatformRegistration.id == LtiResourceLink.registration_id,
        )
        .where(
            LtiPlatformRegistration.organization_id == str(organization_id),
            LtiResourceLink.project_id.in_(sorted(project_ids)),
        )
        .distinct()
    )
    if exclude_registration_id is not None:
        stmt = stmt.where(LtiPlatformRegistration.id != str(exclude_registration_id))
    return stmt


def _build_select_org_attachment_rows(organization_id: str, project_ids):
    from sqlalchemy import select

    from project_models import ProjectOrganization

    return select(
        ProjectOrganization.project_id,
        ProjectOrganization.attached_via,
        ProjectOrganization.group_id,
    ).where(
        ProjectOrganization.organization_id == str(organization_id),
        ProjectOrganization.project_id.in_(sorted(project_ids)),
    )


def plan_lti_attachment_sync(project_ids, wanted, existing) -> Dict[str, Dict]:
    """What :func:`sync_lti_attachments` changes (pure).

    ``wanted``: ``{project: group | None}`` for the projects the org still
    links. ``existing``: ``{project: (attached_via, group)}`` of the org's
    rows. Returns ``{"update": {project: group}, "insert": {project: group},
    "delete": [project]}``. A manual row is never touched (linking never
    narrows a manual share).
    """
    plan: Dict[str, Dict] = {"update": {}, "insert": {}, "delete": []}
    for project_id in sorted({str(p) for p in project_ids}):
        row = existing.get(project_id)
        if project_id in wanted:
            group_id = wanted[project_id]
            if row is None:
                plan["insert"][project_id] = group_id
            elif row[0] == "lti" and row[1] != group_id:
                plan["update"][project_id] = group_id
        elif row is not None and row[0] == "lti":
            plan["delete"].append(project_id)
    return plan


def _lti_sync_statements(organization_id, plan, assigned_by):
    """The writes of a sync plan, as core statements."""
    import uuid

    from sqlalchemy import delete, insert, update

    from project_models import ProjectOrganization

    table = ProjectOrganization.__table__
    org_id = str(organization_id)
    statements = []
    for project_id, group_id in plan["update"].items():
        statements.append(
            update(table)
            .where(
                table.c.organization_id == org_id,
                table.c.project_id == project_id,
                table.c.attached_via == "lti",
            )
            .values(group_id=group_id)
        )
    if plan["delete"]:
        statements.append(
            delete(table).where(
                table.c.organization_id == org_id,
                table.c.project_id.in_(plan["delete"]),
                table.c.attached_via == "lti",
            )
        )
    if plan["insert"] and assigned_by:
        statements.append(
            insert(table).values(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": project_id,
                        "organization_id": org_id,
                        "group_id": group_id,
                        "assigned_by": str(assigned_by),
                        "attached_via": "lti",
                    }
                    for project_id, group_id in plan["insert"].items()
                ]
            )
        )
    return statements


def sync_lti_attachments(
    db,
    organization_id: str,
    project_ids,
    *,
    assigned_by: Optional[str] = None,
    exclude_registration_id: Optional[str] = None,
) -> Dict[str, Dict]:
    """Make the org's LMS-linking attachments of ``project_ids`` match its
    connections (sync, flushes nothing, never commits).

    For each project: if a connection of the org (other than
    ``exclude_registration_id``) still links it, the org's ``lti`` row gets
    the group :func:`collapse_linking_groups` derives, or is created when the
    org has no row (only with ``assigned_by``); otherwise the org's ``lti``
    row is deleted. Manual rows stay. Returns the executed plan (see
    :func:`plan_lti_attachment_sync`). Run it after a connection moves to
    another group or org, or before one is deleted.
    """
    ids = {str(p) for p in (project_ids or ()) if p}
    empty = {"update": {}, "insert": {}, "delete": []}
    if not ids or not organization_id:
        return empty
    wanted = collapse_linking_groups(
        db.execute(
            _build_select_org_linking_groups(
                organization_id, ids, exclude_registration_id
            )
        ).all()
    )
    existing = {
        str(project_id): (via, str(group_id) if group_id else None)
        for project_id, via, group_id in db.execute(
            _build_select_org_attachment_rows(organization_id, ids)
        ).all()
    }
    plan = plan_lti_attachment_sync(ids, wanted, existing)
    if not assigned_by:
        plan["insert"] = {}
    for statement in _lti_sync_statements(organization_id, plan, assigned_by):
        db.execute(statement)
    return plan


async def sync_lti_attachments_async(
    db,
    organization_id: str,
    project_ids,
    *,
    assigned_by: Optional[str] = None,
    exclude_registration_id: Optional[str] = None,
) -> Dict[str, Dict]:
    """Async twin of :func:`sync_lti_attachments`."""
    ids = {str(p) for p in (project_ids or ()) if p}
    empty = {"update": {}, "insert": {}, "delete": []}
    if not ids or not organization_id:
        return empty
    wanted = collapse_linking_groups(
        (
            await db.execute(
                _build_select_org_linking_groups(
                    organization_id, ids, exclude_registration_id
                )
            )
        ).all()
    )
    existing = {
        str(project_id): (via, str(group_id) if group_id else None)
        for project_id, via, group_id in (
            await db.execute(_build_select_org_attachment_rows(organization_id, ids))
        ).all()
    }
    plan = plan_lti_attachment_sync(ids, wanted, existing)
    if not assigned_by:
        plan["insert"] = {}
    for statement in _lti_sync_statements(organization_id, plan, assigned_by):
        await db.execute(statement)
    return plan


def lti_sync_changed(plan) -> list:
    """The project ids a sync plan touched, sorted."""
    return sorted(
        set(plan.get("update") or ()) | set(plan.get("insert") or ()) | set(plan.get("delete") or ())
    )


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


def ensure_invitation_group_membership(db, invitation, user_id: str) -> bool:
    """Join ``user_id`` to a group-scoped invitation's group (sync, no commit).

    The single implementation behind BOTH invitation-consumption paths — the
    accept endpoint (existing users) and register-with-token (new users) —
    so a group-scoped email invite lands the invitee in the group either way.

    Skipped silently when the invitation carries no group or the group is
    gone (FK SET NULL) / deactivated / re-parented to another org — the
    invite then degrades to a plain org invite instead of failing.
    Idempotent: an existing group membership is left untouched (its admin
    flag is NOT escalated). Returns True iff a membership row was added.
    """
    group_id = getattr(invitation, "group_id", None)
    if not group_id:
        return False
    from uuid import uuid4

    from models import OrganizationGroup, OrganizationGroupMembership

    group = (
        db.query(OrganizationGroup)
        .filter(
            OrganizationGroup.id == group_id,
            OrganizationGroup.organization_id == invitation.organization_id,
            OrganizationGroup.is_active == True,  # noqa: E712
        )
        .first()
    )
    if group is None:
        return False
    existing = (
        db.query(OrganizationGroupMembership)
        .filter(
            OrganizationGroupMembership.group_id == group_id,
            OrganizationGroupMembership.user_id == str(user_id),
        )
        .first()
    )
    if existing is not None:
        return False
    db.add(
        OrganizationGroupMembership(
            id=str(uuid4()),
            group_id=group_id,
            user_id=str(user_id),
            is_group_admin=bool(getattr(invitation, "invited_as_group_admin", False)),
        )
    )
    return True
