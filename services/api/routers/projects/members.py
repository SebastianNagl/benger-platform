"""Member management endpoints for projects."""


from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from models import OrganizationGroupMembership, OrganizationMembership, User
from org_groups import attachment_role, best_role, group_member_fan_in_clause
from project_models import Annotation, ProjectOrganization
from routers.projects.deps import ProjectAccess, require_project_access
from services.member_privacy import lms_account_ids, masked_name, project_name_mask
from user_display import prefers_pseudonym

router = APIRouter()


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(require_project_access()),
):
    """List all members of a project.

    Project membership comes from attached organizations only (grouped
    attachments narrow it to the group's members plus the org's ORG_ADMINs).
    ``is_direct_member`` stays in the payload, always ``False``, so the
    response shape is unchanged for clients.

    LMS accounts appear by pseudonym, without email, unless the viewer may
    see that person's real name on this project
    (``project_real_name_user_ids``, D8: people who take part in the linked
    exam through a connection whose students the viewer may see).
    """

    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").

    # Get members from project organizations only. Grouped attachments
    # narrow the fan-in to the group's members + the org's ORG_ADMINs.
    org_result = await db.execute(
        select(OrganizationMembership, ProjectOrganization.group_id)
        .join(
            ProjectOrganization,
            ProjectOrganization.organization_id
            == OrganizationMembership.organization_id,
        )
        .options(
            joinedload(OrganizationMembership.user),
            joinedload(OrganizationMembership.organization),
        )
        .where(
            ProjectOrganization.project_id == project_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            group_member_fan_in_clause(ProjectOrganization, OrganizationMembership),
        )
    )
    org_rows = org_result.unique().all()
    org_members = []
    seen_membership_ids: set = set()
    for om, _group_id in org_rows:
        if om.id not in seen_membership_ids:
            seen_membership_ids.add(om.id)
            org_members.append(om)

    # Effective role per member: the best attachment role over the rows that
    # reach them (``org_groups.attachment_role``: the org role on an
    # org-wide attachment, the group role on a grouped one, ORG_ADMIN for
    # the org's admins).
    group_ids = sorted({str(g) for _, g in org_rows if g})
    group_roles: dict = {}
    if group_ids:
        gm_rows = await db.execute(
            select(
                OrganizationGroupMembership.user_id,
                OrganizationGroupMembership.group_id,
                OrganizationGroupMembership.role,
            ).where(OrganizationGroupMembership.group_id.in_(group_ids))
        )
        for user_id, group_id, role in gm_rows.all():
            group_roles.setdefault(str(user_id), {})[str(group_id)] = role
    roles_by_user: dict = {}
    for om, group_id in org_rows:
        roles_by_user.setdefault(om.user_id, []).append(
            attachment_role(
                str(group_id) if group_id else None,
                om.role,
                group_roles.get(str(om.user_id)),
            )
        )

    mask = await project_name_mask(
        db,
        [om.user for om in org_members],
        viewer=current_user,
        project_id=project_id,
    )

    def _identity(user) -> dict:
        if user is None:
            return {"name": "Unknown", "email": ""}
        return {"name": mask.label(user), "email": mask.email(user)}

    def _privacy(user_id) -> dict:
        return {
            "is_lms_account": mask.is_lms(user_id),
            "is_pseudonymized": mask.is_masked(user_id),
        }

    # One row per user, even when they reach the project through two orgs.
    members = []
    seen_user_ids: set = set()
    for om in org_members:
        if om.user_id not in seen_user_ids:
            seen_user_ids.add(om.user_id)
            members.append(
                {
                    "id": f"org-{om.id}",
                    "user_id": om.user_id,
                    **_identity(om.user),
                    "role": best_role(roles_by_user.get(om.user_id)) or om.role,
                    "is_direct_member": False,
                    "organization_id": om.organization_id,
                    "organization_name": (om.organization.name if om.organization else "Unknown"),
                    "added_at": om.joined_at.isoformat() if om.joined_at else None,
                    **_privacy(om.user_id),
                }
            )

    return members


@router.get("/{project_id}/annotators")
async def get_project_annotators(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(require_project_access()),
):
    """Get users who have actually annotated this project.

    Returns users who have created at least one non-cancelled annotation
    in this project, along with their annotation count.
    """
    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").

    # Query users who have annotated this project
    stmt = (
        select(
            User.id.label("user_id"),
            User.name,
            User.pseudonym,
            User.use_pseudonym,
            func.count(Annotation.id).label("annotation_count"),
        )
        .join(Annotation, Annotation.completed_by == User.id)
        .where(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .group_by(User.id, User.name, User.pseudonym, User.use_pseudonym)
        .order_by(func.count(Annotation.id).desc())
    )

    results = (await db.execute(stmt)).all()

    # Pseudonym-first for everyone (research views key on this label). An
    # LMS account without a pseudonym gets the neutral label, never its
    # real name (D8).
    no_alias_lms = await lms_account_ids(
        db,
        [
            r.user_id
            for r in results
            if not r.pseudonym and prefers_pseudonym(use_pseudonym=r.use_pseudonym)
        ],
    )

    annotators = []
    for r in results:
        display_name = r.pseudonym if r.use_pseudonym and r.pseudonym else r.name
        if str(r.user_id) in no_alias_lms:
            display_name = masked_name(user_id=r.user_id, pseudonym=None)
        annotators.append(
            {
                "id": r.user_id,
                "name": display_name or "Unknown",
                "count": r.annotation_count,
            }
        )

    return {"annotators": annotators}
