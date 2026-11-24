"""Who reviews a project's submissions: staff, and peers when the project allows it.

A project with ``projects.peer_review_enabled`` (migration 158) lets its
participants grade each other's submissions next to the staff graders. This
module is the generic grant behind that, with no workflow in it:

- :func:`review_role` answers, for one user and one project, ``"staff"``
  (an effective project role of CONTRIBUTOR or above with the full access
  tier: superadmins, the creator, org and group staff through an
  attachment), ``"peer"`` (the switch is on, the project is not archived,
  and the user takes part as an ANNOTATOR, participants included, with an
  access tier that may still write) or ``None``.
- :func:`peer_candidate_ids` lists, for the whole project, the people
  :func:`review_role` answers ``"peer"`` for: the ANNOTATOR members its
  attachments reach (when the project is open to them, the same rule as the
  participant tier), its consented share members, its students with an
  active entitlement, and on a public project everyone who handed in. Staff,
  service accounts and deactivated accounts are never peers.

The overlay that runs the review workflow decides what a peer may do (which
submissions, how many, when) on top of this; its gradings are stored on the
feedback-only method ``human_graded_metrics.PEER_REVIEW_METRIC`` and never
count as a grade. Only an effective project role of ORG_ADMIN may change
the switch (``PATCH /projects/{id}``).

Sync and async twins share their statement builders (the dual-mode pattern).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import OrganizationGroupMembership, OrganizationMembership, User
from org_groups import attachment_role, best_role, group_member_fan_in_clause, role_at_least
from project_models import (
    Annotation,
    MarketplaceEntitlement,
    Project,
    ProjectOrganization,
    ProjectShareMember,
)
from routers.projects.helpers import (
    TIER_FULL,
    get_effective_project_role,
    get_effective_project_role_async,
    get_project_access_tier,
    get_project_access_tier_async,
    tier_allows_writes,
)

REVIEW_ROLE_STAFF = "staff"
REVIEW_ROLE_PEER = "peer"
REVIEW_ROLES = (REVIEW_ROLE_STAFF, REVIEW_ROLE_PEER)

# Project kinds whose org members reach the project only once its access
# window has started (the participant rule of
# ``helpers._build_select_org_exam_participant``).
_WINDOWED_KINDS = ("exam", "flashcard_collection")


def _project_reviewable(project) -> bool:
    """Peers review only on a live project with the switch on."""
    return (
        bool(getattr(project, "peer_review_enabled", False))
        and not getattr(project, "is_archived", False)
        and getattr(project, "deleted_at", None) is None
    )


def decide_review_role(
    *,
    effective_role: Optional[str],
    access_tier: Optional[str],
    project,
    is_service_account: bool = False,
) -> Optional[str]:
    """Pure: the review role from the resolved role and tier (see the module
    docstring). ``project`` supplies the switch and the archive state; an
    access-key service account is never a peer."""
    if access_tier is None:
        return None
    if access_tier == TIER_FULL and role_at_least(effective_role, "CONTRIBUTOR"):
        return REVIEW_ROLE_STAFF
    if (
        not is_service_account
        and _project_reviewable(project)
        and best_role([effective_role]) == "ANNOTATOR"
        and tier_allows_writes(access_tier)
    ):
        return REVIEW_ROLE_PEER
    return None


def review_role(db: Session, user, project: Project) -> Optional[str]:
    """``"staff"``, ``"peer"`` or ``None`` for ``user`` on ``project`` (sync)."""
    tier = get_project_access_tier(db, user, str(project.id), project=project)
    if tier is None:
        return None
    return decide_review_role(
        effective_role=get_effective_project_role(db, user, project),
        access_tier=tier,
        project=project,
        is_service_account=bool(getattr(user, "is_service_account", False)),
    )


async def review_role_async(db: AsyncSession, user, project: Project) -> Optional[str]:
    """Async twin of :func:`review_role`."""
    tier = await get_project_access_tier_async(db, user, str(project.id), project=project)
    if tier is None:
        return None
    return decide_review_role(
        effective_role=await get_effective_project_role_async(db, user, project),
        access_tier=tier,
        project=project,
        is_service_account=bool(getattr(user, "is_service_account", False)),
    )


# ---------------------------------------------------------------------------
# The candidate list (batch twin of review_role == "peer")
# ---------------------------------------------------------------------------


def _build_select_attached_memberships(project_id: str):
    """Active memberships the project's attachments reach (the roster fan-in:
    the whole org on an org-wide attachment, the group's members and the
    org's admins on a grouped one), one row per (membership, attachment)."""
    return (
        select(
            OrganizationMembership.user_id,
            OrganizationMembership.role,
            ProjectOrganization.group_id,
        )
        .join(
            ProjectOrganization,
            ProjectOrganization.organization_id == OrganizationMembership.organization_id,
        )
        .where(
            ProjectOrganization.project_id == project_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            group_member_fan_in_clause(ProjectOrganization, OrganizationMembership),
        )
    )


def _build_select_group_roles(group_ids: List[str]):
    return select(
        OrganizationGroupMembership.user_id,
        OrganizationGroupMembership.group_id,
        OrganizationGroupMembership.role,
    ).where(OrganizationGroupMembership.group_id.in_(group_ids))


def _build_select_share_member_ids(project_id: str):
    return select(ProjectShareMember.user_id).where(
        ProjectShareMember.project_id == project_id,
        ProjectShareMember.gdpr_consent_at.isnot(None),
    )


def _build_select_entitled_ids(project_id: str):
    return select(MarketplaceEntitlement.user_id).where(
        MarketplaceEntitlement.project_id == project_id,
        MarketplaceEntitlement.revoked_at.is_(None),
    )


def _build_select_submitter_ids(project_id: str):
    return (
        select(Annotation.completed_by)
        .where(
            Annotation.project_id == project_id,
            Annotation.completed_by.isnot(None),
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .distinct()
    )


def _build_select_person_ids(user_ids: List[str]):
    """Which of ``user_ids`` are active people: no superadmin (always staff),
    no access-key service account, no deactivated account."""
    return select(User.id).where(
        User.id.in_(user_ids),
        User.is_active == True,  # noqa: E712
        User.is_superadmin == False,  # noqa: E712
        User.is_service_account.is_(False),
    )


def _attachment_roles(membership_rows, group_role_rows) -> Dict[str, Optional[str]]:
    """Pure: each member's best role over the attachments that reach them."""
    group_roles: Dict[str, Dict[str, str]] = {}
    for user_id, group_id, role in group_role_rows:
        group_roles.setdefault(str(user_id), {})[str(group_id)] = role
    roles: Dict[str, list] = {}
    for user_id, org_role, group_id in membership_rows:
        roles.setdefault(str(user_id), []).append(
            attachment_role(
                str(group_id) if group_id else None,
                org_role,
                group_roles.get(str(user_id)),
            )
        )
    return {user_id: best_role(found) for user_id, found in roles.items()}


def _members_reach_project(project, now: datetime) -> bool:
    """Do the attachments' ANNOTATOR members reach the project at all? Not on
    a private project (creator-only), and on an exam or deck only once its
    window has started (the participant rule)."""
    if getattr(project, "is_private", False):
        return False
    if getattr(project, "kind", None) not in _WINDOWED_KINDS:
        return True
    start = getattr(project, "window_start_at", None)
    if start is None:
        return True
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= now


def _public_submitters_count(project) -> bool:
    return bool(getattr(project, "is_public", False)) and best_role(
        [getattr(project, "public_role", None)]
    ) == "ANNOTATOR"


def _combine_candidates(
    project,
    member_roles: Dict[str, Optional[str]],
    share_ids: Iterable,
    entitled_ids: Iterable,
    submitter_ids: Iterable,
    now: datetime,
) -> Set[str]:
    """Pure: the peer pool before the account filter. Anyone the attachments
    give a staff role, and the creator, are staff and never peers."""
    staff = {u for u, role in member_roles.items() if role_at_least(role, "CONTRIBUTOR")}
    if getattr(project, "created_by", None):
        staff.add(str(project.created_by))
    pool: Set[str] = set()
    if _members_reach_project(project, now):
        pool |= {u for u, role in member_roles.items() if role == "ANNOTATOR"}
    pool |= {str(u) for u in share_ids if u}
    pool |= {str(u) for u in entitled_ids if u}
    if _public_submitters_count(project):
        pool |= {str(u) for u in submitter_ids if u}
    return pool - staff


def _wanted(pool: Set[str], user_ids: Optional[Iterable]) -> List[str]:
    if user_ids is None:
        return sorted(pool)
    wanted = {str(u) for u in user_ids if u}
    return sorted(pool & wanted)


def peer_candidate_ids(
    db: Session, project: Project, user_ids: Optional[Iterable] = None
) -> Set[str]:
    """The people :func:`review_role` answers ``"peer"`` for on ``project``
    (``user_ids``: only among these). Empty while the switch is off, on an
    archived and on a deleted project."""
    if not _project_reviewable(project):
        return set()
    project_id = str(project.id)
    membership_rows = db.execute(_build_select_attached_memberships(project_id)).all()
    group_ids = sorted({str(g) for _, _, g in membership_rows if g})
    group_role_rows = db.execute(_build_select_group_roles(group_ids)).all() if group_ids else []
    submitters = (
        db.execute(_build_select_submitter_ids(project_id)).scalars().all()
        if _public_submitters_count(project)
        else []
    )
    pool = _combine_candidates(
        project,
        _attachment_roles(membership_rows, group_role_rows),
        db.execute(_build_select_share_member_ids(project_id)).scalars().all(),
        db.execute(_build_select_entitled_ids(project_id)).scalars().all(),
        submitters,
        datetime.now(timezone.utc),
    )
    ids = _wanted(pool, user_ids)
    if not ids:
        return set()
    return {str(u) for u in db.execute(_build_select_person_ids(ids)).scalars().all()}


async def peer_candidate_ids_async(
    db: AsyncSession, project: Project, user_ids: Optional[Iterable] = None
) -> Set[str]:
    """Async twin of :func:`peer_candidate_ids`."""
    if not _project_reviewable(project):
        return set()
    project_id = str(project.id)
    membership_rows = (await db.execute(_build_select_attached_memberships(project_id))).all()
    group_ids = sorted({str(g) for _, _, g in membership_rows if g})
    group_role_rows = (
        (await db.execute(_build_select_group_roles(group_ids))).all() if group_ids else []
    )
    submitters = (
        (await db.execute(_build_select_submitter_ids(project_id))).scalars().all()
        if _public_submitters_count(project)
        else []
    )
    pool = _combine_candidates(
        project,
        _attachment_roles(membership_rows, group_role_rows),
        (await db.execute(_build_select_share_member_ids(project_id))).scalars().all(),
        (await db.execute(_build_select_entitled_ids(project_id))).scalars().all(),
        submitters,
        datetime.now(timezone.utc),
    )
    ids = _wanted(pool, user_ids)
    if not ids:
        return set()
    return {
        str(u) for u in (await db.execute(_build_select_person_ids(ids))).scalars().all()
    }
