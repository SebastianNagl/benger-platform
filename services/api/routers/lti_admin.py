"""Admin API for LMS (LTI 1.3) connections of an organization.

Who may do what:

* **Superadmins** manage every connection, in every organization.
* **Org admins** manage the connections of their organization.
* **Group admins** manage the connections scoped to one of their groups.
  They never see org-wide connections and cannot grant LMS teachers a higher
  organization role than their own.
* Everyone who may manage a connection sees the real names of its LMS users
  (owner decision D8: org admins of the connection's organization, group
  admins for their group's connections, superadmins).
* Connections of **protected organizations**
  (``extensions.lti_protected_org_ids``) stay superadmin-only.
* Admins anonymize the accounts a connection's launches created (owner
  decision D16): per LMS link (preview, then ``POST .../anonymize``), or all
  at once when the connection is deleted with ``accounts=anonymize``. The
  scope rules always use the connection's organization (and, for group
  admins, their groups), also for superadmins; the superadmin user admin
  (``POST /api/users/{id}/anonymize``) is the unscoped path. The rules and
  the scrub live in ``services/user_anonymization.py``.

Every endpoint checks the scope through ``auth_module.org_scope``. List
endpoints need ``organization_id`` unless the caller is a superadmin. Every
change writes an ``lti_admin_events`` row (ids and config values only, never
personal data). Errors use ``{"detail": {"code", "message"}}``.

Tool URLs (invite link, tool sheet) always come from the connection's stored
``tool_host`` via ``shared/public_hosts.py``, never from the request.

Split-rule note: this router is the generic persistence surface over the
platform-owned ``lti_*`` tables. It contains NO LTI protocol logic: the OIDC
login/launch endpoints, Dynamic Registration and the AGS grade-passback
client live in ``benger_extended`` (which is why the tool URLs point at
``/api/lti/*`` routes that only exist in the extended edition). Grade pushes
are queued through the ``dispatch_lti_grade_sync`` hook. The community
edition ships this admin surface over an otherwise-dormant schema.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

import extensions
from auth_module.dependencies import require_user
from auth_module.org_scope import OrgAdminScope, require_scope_admin
from database import get_async_db
from models import (
    LtiAdminEvent,
    LtiDeployment,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiRegistrationInvite,
    LtiResourceLink,
    LtiResourceLinkUser,
    LtiUserLink,
    OrganizationGroup,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from org_groups import lti_sync_changed, sync_lti_attachments_async
from project_models import MarketplaceEntitlement, Project, Task
from public_hosts import (
    ToolHostUnavailable,
    available_tool_hosts,
    tool_base_url,
    validate_tool_host,
)
from schemas.lti_schemas import (
    LtiAdminEventRead,
    LtiDeploymentCreate,
    LtiDeploymentRead,
    LtiDeploymentStatusUpdate,
    LtiGradeSyncAdminRead,
    LtiGradeSyncRead,
    LtiGradeSyncRetryRead,
    LtiRegistrationCreate,
    LtiRegistrationInviteCreate,
    LtiRegistrationInviteCreated,
    LtiRegistrationInviteRead,
    LtiRegistrationRead,
    LtiRegistrationUpdate,
    LtiResourceLinkAdminRead,
    LtiResourceLinkProjectRead,
    LtiToolConfigRead,
    LtiToolHostRead,
    LtiUserLinkAdminPage,
    LtiUserLinkAdminRead,
)
from schemas.user_anonymization_schemas import (
    AnonymizationPreviewRead,
    AnonymizationUserRead,
    AnonymizeRequest,
    AnonymizeResult,
    ConnectionAccountSkipped,
    ConnectionAnonymizationPreviewRead,
    ConnectionDeleteReport,
)
from services.user_anonymization import (
    AnonymizationRefused,
    AnonymizationScope,
    AnonymizationUserNotFound,
    anonymization_check,
    anonymization_footprint,
    anonymize_user,
    anonymize_users,
    revoke_lms_link_tokens,
)
from user_display import display_name

router = APIRouter(prefix="/api/admin/lti", tags=["admin", "lti"])

# The read-write AGS line item scope. An LMS that grants it lets the tool
# manage its own grade columns (Moodle: "Notensynchronisation und
# Spaltenverwaltung").
AGS_LINEITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
EVENTS_LIMIT = 100
USER_LINKS_MAX_LIMIT = 200

# Instructor org roles a connection can grant, lowest first.
_INSTRUCTOR_ROLE_RANK = {"none": 0, "contributor": 1, "org_admin": 2}
_ORG_ROLE_RANK = {
    OrganizationRole.ANNOTATOR.value: 0,
    OrganizationRole.CONTRIBUTOR.value: 1,
    OrganizationRole.ORG_ADMIN.value: 2,
}
# Registration fields that may be set to NULL; an explicit null on any other
# field of the partial update is ignored.
_NULLABLE_UPDATE_FIELDS = {"group_id", "lms_family"}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
def _error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message, **extra}
    )


def _not_found(code: str, what: str) -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, code, f"{what} not found")


def _tool_host_unavailable(key: object) -> HTTPException:
    return _error(
        status.HTTP_400_BAD_REQUEST,
        ToolHostUnavailable.code,
        f"The tool host {key!r} is not available in this deployment.",
    )


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #
async def _is_protected_org(db: AsyncSession, organization_id: str) -> bool:
    return await db.run_sync(
        lambda session: extensions.is_lti_protected_org(session, organization_id)
    )


async def _require_scope(
    db: AsyncSession,
    user: Any,
    organization_id: str,
    group_id: Optional[str] = None,
    *,
    any_group: bool = False,
) -> OrgAdminScope:
    """Admin scope for (org, group), refusing protected orgs to non-superadmins."""
    scope = await require_scope_admin(
        db, user, organization_id, group_id, any_group=any_group
    )
    if not scope.is_superadmin and await _is_protected_org(db, organization_id):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "connection_protected",
            "Only platform administrators can manage the LMS connections of "
            "this organization.",
        )
    return scope


async def _list_scope(
    db: AsyncSession, user: Any, organization_id: Optional[str]
) -> Optional[OrgAdminScope]:
    """Scope for a list endpoint. None means "superadmin": no row filter
    beyond the optional org filter, which stays a plain filter for them (an
    unknown id lists nothing)."""
    if getattr(user, "is_superadmin", False):
        return None
    if organization_id is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "organization_id_required",
            "Choose an organization.",
        )
    return await _require_scope(db, user, organization_id, any_group=True)


def _group_filter(scope: Optional[OrgAdminScope], column):
    """Restrict rows to the caller's groups unless the scope is org-wide."""
    if scope is None or scope.org_wide:
        return None
    return column.in_(sorted(scope.admin_group_ids))


def _reveals_names(scope: Optional[OrgAdminScope], group_id: Optional[str]) -> bool:
    """D8: real names of a connection's LMS users are for superadmins, org
    admins and the admins of the connection's group."""
    return scope is None or scope.covers(group_id)


async def _load_registration(
    db: AsyncSession, registration_id: str
) -> LtiPlatformRegistration:
    """Fetch a registration with deployments eagerly loaded, or 404."""
    reg = (
        await db.execute(
            select(LtiPlatformRegistration)
            .options(selectinload(LtiPlatformRegistration.deployments))
            .where(LtiPlatformRegistration.id == registration_id)
            # Refresh rows (and the deployment list) a long-lived session
            # already holds.
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not reg:
        raise _not_found("registration_not_found", "Registration")
    return reg


async def _load_registration_scoped(
    db: AsyncSession, user: Any, registration_id: str
) -> Tuple[LtiPlatformRegistration, OrgAdminScope]:
    reg = await _load_registration(db, registration_id)
    scope = await _require_scope(db, user, reg.organization_id, reg.group_id)
    return reg, scope


async def _require_active_group(
    db: AsyncSession, organization_id: str, group_id: Optional[str]
) -> None:
    """A connection's group must be an ACTIVE group of its org."""
    if not group_id:
        return
    group = (
        await db.execute(
            select(OrganizationGroup).where(
                OrganizationGroup.id == group_id,
                OrganizationGroup.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if group is None:
        raise _not_found("group_not_found", "Group")
    if not group.is_active:
        raise _error(
            status.HTTP_400_BAD_REQUEST, "group_inactive", "This group is not active."
        )


async def _max_instructor_role(
    db: AsyncSession, user: Any, scope: OrgAdminScope
) -> str:
    """Highest instructor org role the caller may grant in this org.

    Org admins and superadmins: any. Group admins: never ``org_admin``, and
    ``contributor`` only when they are at least a contributor themselves.
    """
    if scope.org_wide:
        return "org_admin"
    role = (
        await db.execute(
            select(OrganizationMembership.role).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == scope.org_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar()
    rank = _ORG_ROLE_RANK.get(str(getattr(role, "value", role)).upper(), 0)
    return "contributor" if rank >= 1 else "none"


def _check_role_cap(requested: str, allowed: str) -> None:
    if _INSTRUCTOR_ROLE_RANK[requested] > _INSTRUCTOR_ROLE_RANK[allowed]:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "instructor_role_cap",
            "LMS teachers cannot get a higher organization role than you hold.",
            max_role=allowed,
        )


async def _reject_issuer_client_conflict(
    db: AsyncSession,
    scope: OrgAdminScope,
    issuer: str,
    client_id: str,
    *,
    exclude_id: Optional[str] = None,
) -> None:
    """(issuer, client_id) is globally unique.

    Non-superadmins get a generic answer that never names the organization
    or connection that holds the pair.
    """
    stmt = select(LtiPlatformRegistration.id).where(
        LtiPlatformRegistration.issuer == issuer,
        LtiPlatformRegistration.client_id == client_id,
    )
    if exclude_id:
        stmt = stmt.where(LtiPlatformRegistration.id != exclude_id)
    existing_id = (await db.execute(stmt)).scalar_one_or_none()
    if existing_id is None:
        return
    extra = {"registration_id": existing_id} if scope.is_superadmin else {}
    raise _error(
        status.HTTP_409_CONFLICT,
        "issuer_client_taken",
        "This issuer and client ID are already used by another connection.",
        **extra,
    )


def _validated_tool_host(key: Optional[str]) -> str:
    try:
        return validate_tool_host(key)
    except ToolHostUnavailable:
        raise _tool_host_unavailable(key) from None


def _base_url_or_none(key: Optional[str]) -> Optional[str]:
    try:
        return tool_base_url(key)
    except ToolHostUnavailable:
        return None


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _record_event(
    db: AsyncSession,
    *,
    organization_id: str,
    actor: Any,
    action: str,
    registration: Optional[LtiPlatformRegistration] = None,
    registration_id: Optional[str] = None,
    registration_name: Optional[str] = None,
    group_id: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
) -> None:
    """Stage one audit row. The caller commits it with the change itself.

    ``group_id`` is the group scope the entry belongs to (the registration's
    when one is given); group admins read the org feed through it.
    """
    if registration is not None:
        registration_id = registration_id or registration.id
        registration_name = registration_name or registration.name
        group_id = group_id or registration.group_id
    db.add(
        LtiAdminEvent(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            registration_id=registration_id,
            registration_name=registration_name,
            group_id=group_id,
            actor_user_id=getattr(actor, "id", None),
            actor_kind="user",
            action=action,
            changes={k: _json_value(v) for k, v in (changes or {}).items()},
            # Wall-clock time, so events of one request keep their order.
            created_at=datetime.now(timezone.utc),
        )
    )


def _diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    return {
        field: {"old": _json_value(old.get(field)), "new": _json_value(value)}
        for field, value in new.items()
        if old.get(field) != value
    }


# --------------------------------------------------------------------------- #
# Read shapes
# --------------------------------------------------------------------------- #
def _registration_read(
    reg: LtiPlatformRegistration,
    *,
    resource_link_count: Optional[int] = None,
    resource_links_missing_ags: int = 0,
    user_link_count: Optional[int] = None,
) -> LtiRegistrationRead:
    """Build the read shape from an eagerly-loaded registration row."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    deployments = sorted(
        reg.deployments, key=lambda d: (d.created_at or epoch, d.deployment_id)
    )
    return LtiRegistrationRead(
        id=reg.id,
        organization_id=reg.organization_id,
        name=reg.name,
        issuer=reg.issuer,
        client_id=reg.client_id,
        auth_login_url=reg.auth_login_url,
        auth_token_url=reg.auth_token_url,
        jwks_uri=reg.jwks_uri,
        lms_family=reg.lms_family,
        link_existing_users_by_email=reg.link_existing_users_by_email,
        instructor_org_role=reg.instructor_org_role,
        student_org_role=reg.student_org_role,
        group_id=reg.group_id,
        status=reg.status,
        tool_host=reg.tool_host,
        tool_base_url=_base_url_or_none(reg.tool_host),
        created_at=reg.created_at,
        updated_at=reg.updated_at,
        deployments=[LtiDeploymentRead.model_validate(d) for d in deployments],
        deployment_count=len(deployments),
        resource_link_count=resource_link_count,
        resource_links_missing_ags=resource_links_missing_ags,
        user_link_count=user_link_count,
    )


async def _missing_ags_counts(db: AsyncSession, registration_ids) -> dict:
    """registration_id -> count of BOUND resource links without an AGS
    lineitem (activities that cannot receive grades). One grouped query."""
    ids = list(registration_ids)
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(LtiResourceLink.registration_id, func.count())
            .where(
                LtiResourceLink.registration_id.in_(ids),
                LtiResourceLink.project_id.isnot(None),
                LtiResourceLink.lineitem_url.is_(None),
            )
            .group_by(LtiResourceLink.registration_id)
        )
    ).all()
    return {rid: count for rid, count in rows}


async def _users_by_id(db: AsyncSession, user_ids: Iterable[Optional[str]]) -> dict:
    ids = sorted({uid for uid in user_ids if uid})
    if not ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: user for user in rows}


def _registration_subquery(registration_id: str):
    return select(LtiResourceLink.id).where(
        LtiResourceLink.registration_id == registration_id
    )


# --------------------------------------------------------------------------- #
# Anonymization helpers
# --------------------------------------------------------------------------- #
def _anonymization_scope(
    reg: LtiPlatformRegistration, scope: OrgAdminScope
) -> AnonymizationScope:
    """The connection's org, narrowed to the caller's groups for group
    admins. Superadmins get the org-wide scope: accounts that reach beyond
    this organization go through the superadmin user admin instead."""
    if scope.org_wide:
        return AnonymizationScope(organization_id=reg.organization_id)
    return AnonymizationScope(
        organization_id=reg.organization_id,
        group_ids=frozenset(scope.admin_group_ids),
    )


def _anonymization_blocked(blockers: List[str]) -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        "anonymization_blocked",
        "This account cannot be anonymized here.",
        blockers=list(blockers),
    )


async def _provisioned_connection_accounts(
    db: AsyncSession, registration_id: str
) -> List[Tuple[LtiUserLink, User]]:
    """One (link, user) pair per account the connection's launches created,
    oldest link first. Tombstones of unlinked identities count too."""
    rows = (
        await db.execute(
            select(LtiUserLink, User)
            .join(User, User.id == LtiUserLink.user_id)
            .where(
                LtiUserLink.registration_id == registration_id,
                LtiUserLink.link_method == "provisioned",
            )
            .order_by(LtiUserLink.created_at, LtiUserLink.id)
        )
    ).all()
    seen = set()
    pairs = []
    for link, user in rows:
        if user.id in seen:
            continue
        seen.add(user.id)
        pairs.append((link, user))
    return pairs


def _account_label(user: User, reveal: bool) -> str:
    """Real name for viewers who may see it, else the pseudonym (never a
    fallback to the name for LMS accounts)."""
    if reveal:
        return display_name(user, True)
    return user.pseudonym or f"User {str(user.id)[:8]}"


def _skipped_account(
    link: LtiUserLink, user: User, reveal: bool, blockers: List[str]
) -> ConnectionAccountSkipped:
    return ConnectionAccountSkipped(
        user_link_id=link.id,
        user_id=user.id,
        display=_account_label(user, reveal),
        blockers=list(blockers),
    )


def _anonymized_changes(link_id: Optional[str], result, reason: str) -> Dict[str, Any]:
    """Audit payload of one anonymization: ids and counts, no personal data."""
    return {
        "user_link_id": link_id,
        "user_id": result.user_id,
        "reason": reason,
        "warnings": list(result.warnings),
        "removed": dict(result.removed),
    }


async def _anonymize_connection_accounts(
    db: AsyncSession,
    actor: Any,
    reg: LtiPlatformRegistration,
    scope: OrgAdminScope,
) -> Tuple[List[str], List[ConnectionAccountSkipped]]:
    """Anonymize every eligible provisioned account of a connection that is
    about to be deleted. Writes one audit row per account (without the
    registration id, which the delete removes). Nothing is committed."""
    anon_scope = _anonymization_scope(reg, scope)
    reveal = _reveals_names(scope, reg.group_id)
    anonymized: List[str] = []
    skipped: List[ConnectionAccountSkipped] = []
    pairs = await _provisioned_connection_accounts(db, reg.id)
    # One set-based run for all accounts (locks, scrubs and the notification
    # scan once), so a large connection fits in one request.
    outcomes = await anonymize_users(
        db,
        [(user.id, link.id) for link, user in pairs],
        actor_id=actor.id,
        reason="registration_deleted",
        scope=anon_scope,
    )
    for (link, user), outcome in zip(pairs, outcomes):
        if outcome.not_found:
            continue
        if outcome.result is None:
            skipped.append(_skipped_account(link, user, reveal, outcome.blockers))
            continue
        result = outcome.result
        anonymized.append(result.user_id)
        _record_event(
            db,
            organization_id=reg.organization_id,
            actor=actor,
            action="user_anonymized",
            registration_name=reg.name,
            group_id=reg.group_id,
            changes={
                "registration_id": reg.id,
                **_anonymized_changes(link.id, result, "registration_deleted"),
            },
        )
    return anonymized, skipped


# --------------------------------------------------------------------------- #
# Tool hosts
# --------------------------------------------------------------------------- #
@router.get("/tool-hosts", response_model=List[LtiToolHostRead])
async def list_tool_hosts(_user=Depends(require_user)):
    """The public hosts a connection's tool URLs can use in this deployment.

    Public URLs only, so any signed-in user may read them.
    """
    return [
        LtiToolHostRead(
            key=option.key,
            label=option.host,
            host=option.host,
            base_url=option.base_url,
            is_default=option.is_default,
        )
        for option in available_tool_hosts()
    ]


# --------------------------------------------------------------------------- #
# Registrations
# --------------------------------------------------------------------------- #
@router.post("/registrations", status_code=201, response_model=LtiRegistrationRead)
async def create_registration(
    body: LtiRegistrationCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Register an LMS installation for an organization or one of its groups.

    The connection is active right away. ``deployment_ids`` become child
    ``LtiDeployment`` rows (deduplicated, order preserved). The
    (issuer, client_id) pair is globally unique. A group admin must pick one
    of their groups; an omitted ``instructor_org_role`` is capped to what the
    caller may grant.
    """
    scope = await _require_scope(db, current_user, body.organization_id, body.group_id)
    await _require_active_group(db, body.organization_id, body.group_id)

    max_role = await _max_instructor_role(db, current_user, scope)
    instructor_org_role = body.instructor_org_role
    if "instructor_org_role" in body.model_fields_set:
        _check_role_cap(instructor_org_role, max_role)
    elif _INSTRUCTOR_ROLE_RANK[instructor_org_role] > _INSTRUCTOR_ROLE_RANK[max_role]:
        instructor_org_role = max_role

    tool_host = _validated_tool_host(body.tool_host)
    await _reject_issuer_client_conflict(db, scope, body.issuer, body.client_id)

    reg = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        group_id=body.group_id,
        name=body.name,
        issuer=body.issuer,
        client_id=body.client_id,
        auth_login_url=body.auth_login_url,
        auth_token_url=body.auth_token_url,
        jwks_uri=body.jwks_uri,
        lms_family=body.lms_family,
        link_existing_users_by_email=body.link_existing_users_by_email,
        instructor_org_role=instructor_org_role,
        student_org_role=body.student_org_role,
        tool_host=tool_host,
        status="active",
    )
    db.add(reg)
    deployment_ids = list(dict.fromkeys(body.deployment_ids))
    for deployment_id in deployment_ids:
        db.add(
            LtiDeployment(
                id=str(uuid.uuid4()),
                registration_id=reg.id,
                deployment_id=deployment_id,
            )
        )
    # The audit row references the registration without an ORM relationship,
    # so the registration must be written first.
    await db.flush()
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="registration_created",
        registration=reg,
        changes={
            "group_id": reg.group_id,
            "issuer": reg.issuer,
            "client_id": reg.client_id,
            "lms_family": reg.lms_family,
            "instructor_org_role": reg.instructor_org_role,
            "student_org_role": reg.student_org_role,
            "tool_host": reg.tool_host,
            "status": reg.status,
            "deployment_ids": deployment_ids,
        },
    )
    await db.commit()

    return _registration_read(await _load_registration(db, reg.id))


@router.get("/registrations", response_model=List[LtiRegistrationRead])
async def list_registrations(
    organization_id: Optional[str] = Query(None),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Connections of one organization (incl. deployments and counts).

    Superadmins may leave out ``organization_id`` to list every connection.
    Group admins only see the connections of their groups.
    """
    scope = await _list_scope(db, current_user, organization_id)
    stmt = (
        select(LtiPlatformRegistration)
        .options(selectinload(LtiPlatformRegistration.deployments))
        .order_by(LtiPlatformRegistration.created_at.desc())
    )
    if organization_id:
        stmt = stmt.where(LtiPlatformRegistration.organization_id == organization_id)
    group_clause = _group_filter(scope, LtiPlatformRegistration.group_id)
    if group_clause is not None:
        stmt = stmt.where(group_clause)
    regs = (await db.execute(stmt)).scalars().all()
    missing_ags = await _missing_ags_counts(db, [reg.id for reg in regs])
    return [
        _registration_read(reg, resource_links_missing_ags=missing_ags.get(reg.id, 0))
        for reg in regs
    ]


# --------------------------------------------------------------------------- #
# Dynamic Registration invites
#
# Routes with the fixed "/registrations/invites" path segment MUST stay
# registered before "/registrations/{registration_id}" below — Starlette
# matches in registration order, so the parametrized route would otherwise
# swallow them with registration_id="invites".
# --------------------------------------------------------------------------- #
def _invite_status(invite: LtiRegistrationInvite, now: datetime) -> str:
    if invite.used_at is not None:
        return "used"
    if invite.expires_at < now:
        return "expired"
    return "pending"


def _invite_read(
    invite: LtiRegistrationInvite, now: datetime
) -> LtiRegistrationInviteRead:
    return LtiRegistrationInviteRead(
        id=invite.id,
        organization_id=invite.organization_id,
        group_id=invite.group_id,
        tool_host=invite.tool_host,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        resulting_registration_id=invite.resulting_registration_id,
        status=_invite_status(invite, now),
    )


@router.post(
    "/registrations/invites",
    status_code=201,
    response_model=LtiRegistrationInviteCreated,
)
async def create_registration_invite(
    body: LtiRegistrationInviteCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Mint a one-time LTI Dynamic Registration invite.

    The raw token (and the ``register_url`` embedding it) appears ONLY in
    this response — like an API key, only its sha256 is stored. The URL
    points at the chosen tool host; the ``/api/lti/register/init`` endpoint
    that consumes it is served by the extended edition.
    """
    await _require_scope(db, current_user, body.organization_id, body.group_id)
    await _require_active_group(db, body.organization_id, body.group_id)
    tool_host = _validated_tool_host(body.tool_host)
    try:
        base = tool_base_url(tool_host)
    except ToolHostUnavailable:
        raise _tool_host_unavailable(tool_host) from None

    token = secrets.token_urlsafe(32)
    invite = LtiRegistrationInvite(
        id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        group_id=body.group_id,
        tool_host=tool_host,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        created_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
    )
    db.add(invite)
    _record_event(
        db,
        organization_id=invite.organization_id,
        actor=current_user,
        action="invite_created",
        group_id=invite.group_id,
        changes={
            "invite_id": invite.id,
            "group_id": invite.group_id,
            "tool_host": invite.tool_host,
            "expires_at": invite.expires_at,
        },
    )
    await db.commit()
    await db.refresh(invite)

    return LtiRegistrationInviteCreated(
        id=invite.id,
        organization_id=invite.organization_id,
        group_id=invite.group_id,
        tool_host=invite.tool_host,
        token=token,
        register_url=f"{base}/api/lti/register/init?token={token}",
        expires_at=invite.expires_at,
    )


@router.get("/registrations/invites", response_model=List[LtiRegistrationInviteRead])
async def list_registration_invites(
    organization_id: Optional[str] = Query(None),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Dynamic Registration invites, newest first, with computed status.

    Same scope rules as the connection list. Never returns the raw token or
    its hash.
    """
    scope = await _list_scope(db, current_user, organization_id)
    stmt = select(LtiRegistrationInvite).order_by(
        LtiRegistrationInvite.created_at.desc()
    )
    if organization_id:
        stmt = stmt.where(LtiRegistrationInvite.organization_id == organization_id)
    group_clause = _group_filter(scope, LtiRegistrationInvite.group_id)
    if group_clause is not None:
        stmt = stmt.where(group_clause)
    invites = (await db.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return [_invite_read(invite, now) for invite in invites]


@router.delete("/registrations/invites/{invite_id}", status_code=204)
async def revoke_registration_invite(
    invite_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke an unused invite (hard delete).

    A used invite is an audit record tied to the registration it created —
    it cannot be revoked (409).
    """
    invite = (
        await db.execute(
            select(LtiRegistrationInvite).where(LtiRegistrationInvite.id == invite_id)
        )
    ).scalar_one_or_none()
    if not invite:
        raise _not_found("invite_not_found", "Invite")
    await _require_scope(db, current_user, invite.organization_id, invite.group_id)
    if invite.used_at is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "invite_used",
            "This invite was used; it is kept as a record.",
        )
    _record_event(
        db,
        organization_id=invite.organization_id,
        actor=current_user,
        action="invite_revoked",
        group_id=invite.group_id,
        changes={"invite_id": invite.id, "group_id": invite.group_id},
    )
    await db.delete(invite)
    await db.commit()
    return Response(status_code=204)


@router.get("/registrations/{registration_id}", response_model=LtiRegistrationRead)
async def get_registration(
    registration_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """One connection with deployments, activity and linked-user counts."""
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    resource_link_count = (
        await db.execute(
            select(func.count())
            .select_from(LtiResourceLink)
            .where(LtiResourceLink.registration_id == registration_id)
        )
    ).scalar() or 0
    user_link_count = (
        await db.execute(
            select(func.count())
            .select_from(LtiUserLink)
            .where(
                LtiUserLink.registration_id == registration_id,
                LtiUserLink.unlinked_at.is_(None),
            )
        )
    ).scalar() or 0
    missing_ags = await _missing_ags_counts(db, [registration_id])
    return _registration_read(
        reg,
        resource_link_count=resource_link_count,
        resource_links_missing_ags=missing_ags.get(registration_id, 0),
        user_link_count=user_link_count,
    )


_AUDITED_FIELDS = (
    "organization_id",
    "name",
    "issuer",
    "client_id",
    "auth_login_url",
    "auth_token_url",
    "jwks_uri",
    "lms_family",
    "link_existing_users_by_email",
    "instructor_org_role",
    "student_org_role",
    "group_id",
    "status",
    "tool_host",
)


@router.put("/registrations/{registration_id}", response_model=LtiRegistrationRead)
async def update_registration(
    registration_id: str,
    body: LtiRegistrationUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update connection fields and/or status (partial: only sent fields).

    Only superadmins may move a connection to another organization. A group
    change needs admin rights for the old and the new scope.
    """
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    data = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if value is not None or key in _NULLABLE_UPDATE_FIELDS
    }

    new_org = data.get("organization_id", reg.organization_id)
    new_group = data.get("group_id", reg.group_id)
    if new_org != reg.organization_id and not scope.is_superadmin:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "org_move_forbidden",
            "Only platform administrators can move a connection to another "
            "organization.",
        )
    if (new_org, new_group) != (reg.organization_id, reg.group_id):
        scope = await _require_scope(db, current_user, new_org, new_group)
    if "group_id" in data or "organization_id" in data:
        # Validate the EFFECTIVE (org, group) pair whenever either side
        # moves: the composite FK would reject a mismatch at commit anyway,
        # but a clean 4xx beats an IntegrityError 500. An org move keeps the
        # group only if it belongs to the new org.
        await _require_active_group(db, new_org, new_group)

    if (
        "instructor_org_role" in data
        and data["instructor_org_role"] != reg.instructor_org_role
    ):
        _check_role_cap(
            data["instructor_org_role"],
            await _max_instructor_role(db, current_user, scope),
        )
    if "tool_host" in data:
        data["tool_host"] = _validated_tool_host(data["tool_host"])

    new_issuer = data.get("issuer", reg.issuer)
    new_client_id = data.get("client_id", reg.client_id)
    if (new_issuer, new_client_id) != (reg.issuer, reg.client_id):
        await _reject_issuer_client_conflict(
            db, scope, new_issuer, new_client_id, exclude_id=registration_id
        )

    old_values = {field: getattr(reg, field) for field in _AUDITED_FIELDS}
    changes = _diff(old_values, {k: v for k, v in data.items() if k in _AUDITED_FIELDS})
    old_org = reg.organization_id
    moved = (new_org, new_group) != (reg.organization_id, reg.group_id)
    linked_ids: List[str] = []
    if moved:
        linked_ids = await _linked_project_ids(db, reg.id)
    for field_name, value in data.items():
        setattr(reg, field_name, value)
    if linked_ids:
        # The attachments linking created follow the connection: the new
        # (org, group) gets them, the old org keeps them only where another
        # of its connections still links the exam.
        await db.flush()
        resynced = set(
            lti_sync_changed(
                await sync_lti_attachments_async(
                    db, new_org, linked_ids, assigned_by=current_user.id
                )
            )
        )
        if old_org != new_org:
            resynced |= set(
                lti_sync_changed(
                    await sync_lti_attachments_async(db, old_org, linked_ids)
                )
            )
        if resynced:
            changes["resynced_project_ids"] = sorted(resynced)
    if changes:
        _record_event(
            db,
            organization_id=reg.organization_id,
            actor=current_user,
            action="registration_updated",
            registration=reg,
            changes=changes,
        )
    await db.commit()

    return _registration_read(await _load_registration(db, registration_id))


async def _linked_project_ids(db: AsyncSession, registration_id: str) -> List[str]:
    """The projects the connection's activities point at."""
    return sorted(
        (
            await db.execute(
                select(LtiResourceLink.project_id)
                .where(
                    LtiResourceLink.registration_id == registration_id,
                    LtiResourceLink.project_id.isnot(None),
                )
                .distinct()
            )
        ).scalars()
    )


async def _cleanup_org_attachments(
    db: AsyncSession, reg: LtiPlatformRegistration
) -> Tuple[List[str], List[str], int]:
    """Undo what linking gave the org once no connection of it links a project.

    For every exam this connection links that no OTHER connection of the same
    org still links: drop the org attachment linking created
    (``attached_via='lti'``; a manual share stays) and revoke the LMS
    entitlements of users who no longer reach the exam through any other live
    link. An exam another connection of the org still links keeps its
    attachment with the group the remaining connections give it
    (``org_groups.sync_lti_attachments``). Returns the exams no longer linked
    from the org, the exams whose attachment was dropped, and the number of
    revoked entitlements.
    """
    linked = set(await _linked_project_ids(db, reg.id))
    if not linked:
        return [], [], 0
    still_linked = set(
        (
            await db.execute(
                select(LtiResourceLink.project_id)
                .join(
                    LtiPlatformRegistration,
                    LtiPlatformRegistration.id == LtiResourceLink.registration_id,
                )
                .where(
                    LtiPlatformRegistration.organization_id == reg.organization_id,
                    LtiPlatformRegistration.id != reg.id,
                    LtiResourceLink.project_id.in_(sorted(linked)),
                )
                .distinct()
            )
        ).scalars()
    )
    plan = await sync_lti_attachments_async(
        db, reg.organization_id, linked, exclude_registration_id=reg.id
    )
    orphaned = sorted(linked - still_linked)
    if not orphaned:
        return [], [], 0
    detached = sorted(plan["delete"])

    # An entitlement stays when its user still has a live identity link on
    # another connection (of any org) that links the same exam.
    other_link = LtiResourceLink.__table__.alias("other_link")
    other_user_link = LtiUserLink.__table__.alias("other_user_link")
    live_path = (
        select(other_user_link.c.id)
        .select_from(
            other_user_link.join(
                other_link,
                other_link.c.registration_id == other_user_link.c.registration_id,
            )
        )
        .where(
            other_user_link.c.user_id == MarketplaceEntitlement.user_id,
            other_user_link.c.registration_id != reg.id,
            other_user_link.c.unlinked_at.is_(None),
            other_link.c.project_id == MarketplaceEntitlement.project_id,
        )
        .correlate(MarketplaceEntitlement.__table__)
        .exists()
    )
    revoked = await db.execute(
        update(MarketplaceEntitlement)
        .where(
            MarketplaceEntitlement.project_id.in_(orphaned),
            MarketplaceEntitlement.source == "lti",
            MarketplaceEntitlement.revoked_at.is_(None),
            ~live_path,
        )
        .values(revoked_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    return orphaned, detached, revoked.rowcount or 0


async def _keep_lms_origin(db: AsyncSession, reg: LtiPlatformRegistration) -> None:
    """Stamp the LMS origin on every account the connection created.

    Deleting the connection cascades its identity links away, including the
    tombstones that keep an account recognizable as an LMS account. The
    marker on the user row takes over, so kept accounts stay masked (D8) and
    the connection org's admins can still see their names. Launches set it
    when they create an account; this covers accounts an older pod created.
    """
    creators = select(LtiUserLink.user_id).where(
        LtiUserLink.registration_id == reg.id,
        LtiUserLink.link_method == "provisioned",
    )
    await db.execute(
        update(User)
        .where(User.id.in_(creators))
        .values(
            lms_provisioned_at=func.coalesce(User.lms_provisioned_at, func.now()),
            lms_origin_org_id=reg.organization_id,
        )
        .execution_options(synchronize_session=False)
    )


@router.delete(
    "/registrations/{registration_id}",
    status_code=204,
    responses={200: {"model": ConnectionDeleteReport}},
)
async def delete_registration(
    registration_id: str,
    accounts: Optional[Literal["keep", "anonymize"]] = Query(
        None,
        description=(
            "What happens to accounts the connection created. Required when "
            "there are any: 'keep' leaves them as standalone accounts, "
            "'anonymize' anonymizes every eligible one first."
        ),
    ),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a disabled connection.

    Two steps on purpose: switch the connection off first. The database drops
    its deployments, activities, identity links, participation and grade
    transfer rows; accounts survive unless ``accounts=anonymize``. Kept
    accounts stay LMS accounts (``users.lms_provisioned_at``), so they stay
    masked. Exams no other connection
    of the org links lose the org attachment linking created, and LMS
    entitlements nobody can reach through another link any more are revoked.

    With ``accounts=anonymize`` every provisioned account the caller may
    anonymize is anonymized in the same transaction, then the connection is
    deleted. The answer (200) lists the accounts that were skipped and why;
    they stay as standalone accounts. ``GET .../anonymization`` previews it.
    With ``accounts=keep`` the answer is 204.
    """
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    if reg.status != "disabled":
        raise _error(
            status.HTTP_409_CONFLICT,
            "registration_active",
            "Switch the connection off before deleting it.",
        )

    counts = (
        await db.execute(
            select(
                func.count(LtiUserLink.id),
                func.count(LtiUserLink.id).filter(
                    LtiUserLink.link_method == "provisioned"
                ),
            ).where(LtiUserLink.registration_id == reg.id)
        )
    ).one()
    user_links, provisioned = int(counts[0] or 0), int(counts[1] or 0)
    if provisioned and accounts is None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "accounts_choice_required",
            "Decide what happens to the accounts this connection created.",
            provisioned_accounts=provisioned,
        )
    resource_links = (
        await db.execute(
            select(func.count())
            .select_from(LtiResourceLink)
            .where(LtiResourceLink.registration_id == reg.id)
        )
    ).scalar() or 0

    anonymized: List[str] = []
    skipped: List[ConnectionAccountSkipped] = []
    if accounts == "anonymize":
        anonymized, skipped = await _anonymize_connection_accounts(
            db, current_user, reg, scope
        )

    unlinked, detached, revoked = await _cleanup_org_attachments(db, reg)
    changes = {
        "registration_id": reg.id,
        "group_id": reg.group_id,
        "accounts": accounts,
        "resource_links": resource_links,
        "user_links": user_links,
        "provisioned_accounts": provisioned,
        "unlinked_project_ids": unlinked,
        "detached_project_ids": detached,
        "revoked_entitlements": revoked,
    }
    if accounts == "anonymize":
        changes["anonymized_accounts"] = len(anonymized)
        changes["skipped_accounts"] = [
            {"user_id": item.user_id, "blockers": item.blockers} for item in skipped
        ]
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="registration_deleted",
        # The row goes away; the event keeps the id in its changes, the name
        # as a snapshot and the group scope for the org feed.
        registration_name=reg.name,
        group_id=reg.group_id,
        changes=changes,
    )
    await _keep_lms_origin(db, reg)
    reg_id = reg.id
    await db.delete(reg)
    await db.commit()

    if accounts != "anonymize":
        return Response(status_code=204)
    await run_in_threadpool(revoke_lms_link_tokens, anonymized)
    report = ConnectionDeleteReport(
        registration_id=reg_id,
        anonymized_accounts=len(anonymized),
        anonymized_user_ids=anonymized,
        skipped=skipped,
    )
    return JSONResponse(status_code=200, content=report.model_dump(mode="json"))


@router.get(
    "/registrations/{registration_id}/anonymization",
    response_model=ConnectionAnonymizationPreviewRead,
)
async def preview_connection_anonymization(
    registration_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """What deleting the connection with ``accounts=anonymize`` would do:
    how many provisioned accounts it has, how many the caller may anonymize
    (with their warnings) and which ones would be skipped and why."""
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    anon_scope = _anonymization_scope(reg, scope)
    reveal = _reveals_names(scope, reg.group_id)
    pairs = await _provisioned_connection_accounts(db, reg.id)
    eligible = 0
    warnings: Dict[str, int] = {}
    skipped: List[ConnectionAccountSkipped] = []
    for link, user in pairs:
        check = await anonymization_check(
            db,
            user,
            actor_id=current_user.id,
            scope=anon_scope,
            via_link_id=link.id,
        )
        if check.blockers:
            skipped.append(_skipped_account(link, user, reveal, check.blockers))
            continue
        eligible += 1
        for code in check.warnings:
            warnings[code] = warnings.get(code, 0) + 1
    return ConnectionAnonymizationPreviewRead(
        registration_id=reg.id,
        provisioned_accounts=len(pairs),
        eligible_accounts=eligible,
        warnings=warnings,
        skipped=skipped,
    )


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
async def _load_deployment(
    db: AsyncSession, registration_id: str, deployment_pk: str
) -> LtiDeployment:
    deployment = (
        await db.execute(
            select(LtiDeployment).where(
                LtiDeployment.id == deployment_pk,
                LtiDeployment.registration_id == registration_id,
            )
        )
    ).scalar_one_or_none()
    if not deployment:
        raise _not_found("deployment_not_found", "Deployment")
    return deployment


@router.post(
    "/registrations/{registration_id}/deployments",
    status_code=201,
    response_model=LtiDeploymentRead,
)
async def add_deployment(
    registration_id: str,
    body: LtiDeploymentCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Add a deployment id to a connection (unique per connection)."""
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    existing = (
        await db.execute(
            select(LtiDeployment.id).where(
                LtiDeployment.registration_id == registration_id,
                LtiDeployment.deployment_id == body.deployment_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise _error(
            status.HTTP_409_CONFLICT,
            "deployment_exists",
            "This deployment ID is already registered.",
        )

    deployment = LtiDeployment(
        id=str(uuid.uuid4()),
        registration_id=registration_id,
        deployment_id=body.deployment_id,
    )
    db.add(deployment)
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="deployment_added",
        registration=reg,
        changes={"deployment_id": body.deployment_id},
    )
    await db.commit()
    await db.refresh(deployment)
    return LtiDeploymentRead.model_validate(deployment)


@router.patch(
    "/registrations/{registration_id}/deployments/{deployment_pk}",
    response_model=LtiDeploymentRead,
)
async def update_deployment_status(
    registration_id: str,
    deployment_pk: str,
    body: LtiDeploymentStatusUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Switch one deployment on or off."""
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    deployment = await _load_deployment(db, registration_id, deployment_pk)
    if deployment.status != body.status:
        _record_event(
            db,
            organization_id=reg.organization_id,
            actor=current_user,
            action="deployment_status_changed",
            registration=reg,
            changes={
                "deployment_id": deployment.deployment_id,
                "status": {"old": deployment.status, "new": body.status},
            },
        )
        deployment.status = body.status
        await db.commit()
        await db.refresh(deployment)
    return LtiDeploymentRead.model_validate(deployment)


@router.delete(
    "/registrations/{registration_id}/deployments/{deployment_pk}", status_code=204
)
async def remove_deployment(
    registration_id: str,
    deployment_pk: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove a deployment row (by its primary key) from a connection."""
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    deployment = await _load_deployment(db, registration_id, deployment_pk)
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="deployment_removed",
        registration=reg,
        changes={"deployment_id": deployment.deployment_id},
    )
    await db.delete(deployment)
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Tool config
# --------------------------------------------------------------------------- #
@router.get(
    "/registrations/{registration_id}/tool-config",
    response_model=LtiToolConfigRead,
)
async def get_tool_config(
    registration_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The tool-side URLs to paste into the LMS's external-tool form.

    Built from the connection's tool host; a ``base_url`` query parameter
    from older clients is ignored. The ``/api/lti/*`` routes themselves are
    served by the extended edition. No deep-linking URL is advertised — the
    tool rejects deep-linking launches (binding happens via the
    instructor-launch picker), so publishing one would point LMS admins at a
    route that does not exist.
    """
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    try:
        base = tool_base_url(reg.tool_host)
    except ToolHostUnavailable:
        raise _tool_host_unavailable(reg.tool_host) from None
    return LtiToolConfigRead(
        login_url=f"{base}/api/lti/login",
        launch_url=f"{base}/api/lti/launch",
        jwks_url=f"{base}/api/lti/jwks",
        tool_host=reg.tool_host,
        base_url=base,
    )


# --------------------------------------------------------------------------- #
# Activities, LMS users, history
# --------------------------------------------------------------------------- #
@router.get(
    "/registrations/{registration_id}/resource-links",
    response_model=List[LtiResourceLinkAdminRead],
)
async def list_resource_links(
    registration_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The LMS activities of a connection with their exam and grade state."""
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    links = (
        (
            await db.execute(
                select(LtiResourceLink)
                .where(LtiResourceLink.registration_id == reg.id)
                .order_by(
                    LtiResourceLink.context_title.asc().nulls_last(),
                    LtiResourceLink.resource_title.asc().nulls_last(),
                    LtiResourceLink.created_at.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    if not links:
        return []
    link_ids = [link.id for link in links]
    project_ids = sorted({link.project_id for link in links if link.project_id})

    projects: Dict[str, Any] = {}
    task_counts: Dict[str, int] = {}
    if project_ids:
        projects = {
            row.id: row
            for row in (
                await db.execute(
                    select(Project.id, Project.title, Project.deleted_at).where(
                        Project.id.in_(project_ids)
                    )
                )
            ).all()
        }
        task_counts = dict(
            (
                await db.execute(
                    select(Task.project_id, func.count(Task.id))
                    .where(Task.project_id.in_(project_ids))
                    .group_by(Task.project_id)
                )
            ).all()
        )

    participation = {
        row.resource_link_id: row
        for row in (
            await db.execute(
                select(
                    LtiResourceLinkUser.resource_link_id,
                    func.count(LtiResourceLinkUser.id)
                    .filter(LtiResourceLinkUser.is_instructor == False)  # noqa: E712
                    .label("learners"),
                    func.count(LtiResourceLinkUser.id)
                    .filter(LtiResourceLinkUser.is_instructor == True)  # noqa: E712
                    .label("instructors"),
                    func.max(LtiResourceLinkUser.last_launch_at).label("last_launch"),
                )
                .where(LtiResourceLinkUser.resource_link_id.in_(link_ids))
                .group_by(LtiResourceLinkUser.resource_link_id)
            )
        ).all()
    }
    sync_counts: Dict[str, Dict[str, int]] = {}
    for link_id, sync_status, count in (
        await db.execute(
            select(LtiGradeSync.resource_link_id, LtiGradeSync.status, func.count())
            .where(LtiGradeSync.resource_link_id.in_(link_ids))
            .group_by(LtiGradeSync.resource_link_id, LtiGradeSync.status)
        )
    ).all():
        sync_counts.setdefault(link_id, {})[sync_status] = count

    linkers = await _users_by_id(db, (link.linked_by for link in links))
    reveal = _reveals_names(scope, reg.group_id)
    result = []
    for link in links:
        project = None
        if link.project_id:
            row = projects.get(link.project_id)
            project = LtiResourceLinkProjectRead(
                id=link.project_id,
                title=row.title if row else None,
                task_count=task_counts.get(link.project_id, 0),
                deleted=row is None or row.deleted_at is not None,
            )
        scopes = _granted_scopes(link.ags_scopes)
        stats = participation.get(link.id)
        linker = linkers.get(link.linked_by)
        result.append(
            LtiResourceLinkAdminRead(
                id=link.id,
                deployment_id=link.deployment_id,
                resource_link_id=link.resource_link_id,
                context_id=link.context_id,
                context_title=link.context_title,
                resource_title=link.resource_title,
                project=project,
                linked_by_display=(
                    (display_name(linker, reveal) or None) if linker else None
                ),
                linked_at=link.linked_at,
                grades_supported=bool(link.lineitem_url),
                lineitems_available=bool(link.lineitems_url),
                granted_scopes=scopes,
                column_management=AGS_LINEITEM_SCOPE in scopes,
                sync_ai_grades=link.sync_ai_grades,
                ai_lineitem_status=link.ai_lineitem_status,
                ai_lineitem_error=link.ai_lineitem_error,
                participant_count=int(stats.learners) if stats else 0,
                instructor_count=int(stats.instructors) if stats else 0,
                last_launch_at=stats.last_launch if stats else None,
                sync_counts=sync_counts.get(link.id, {}),
                created_at=link.created_at,
            )
        )
    return result


def _granted_scopes(raw: Any) -> List[str]:
    """The AGS scopes a launch granted, as a list. Launches store the claim
    as the LMS sent it: a JSON list, or (per the spec's space-separated form)
    one string."""
    if isinstance(raw, str):
        raw = raw.split()
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [str(scope) for scope in raw if scope]


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _claimed_role(claims: Any) -> Optional[str]:
    role = claims.get("role") if isinstance(claims, dict) else None
    return role if role in ("instructor", "learner") else None


@router.get(
    "/registrations/{registration_id}/user-links",
    response_model=LtiUserLinkAdminPage,
)
async def list_user_links(
    registration_id: str,
    limit: int = Query(50, ge=1, le=USER_LINKS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, max_length=200),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The LMS identities of a connection, most recent launch first.

    Real names and emails only for viewers who may see them (D8); the search
    only matches them for those viewers, too.
    """
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    reveal = _reveals_names(scope, reg.group_id)

    conditions = [LtiUserLink.registration_id == reg.id]
    needle = (q or "").strip()
    if needle:
        pattern = _like_pattern(needle)
        fields = [User.pseudonym, LtiUserLink.sub]
        if reveal:
            fields += [User.name, User.email]
        conditions.append(or_(*(f.ilike(pattern, escape="\\") for f in fields)))

    base = (
        select(LtiUserLink, User)
        .join(User, User.id == LtiUserLink.user_id)
        .where(and_(*conditions))
    )
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar() or 0
    rows = (
        await db.execute(
            base.order_by(
                LtiUserLink.last_launch_at.desc().nulls_last(),
                LtiUserLink.created_at.desc(),
                LtiUserLink.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    instructor_by_user: Dict[str, bool] = {}
    user_ids = [user.id for _link, user in rows]
    if user_ids:
        instructor_by_user = dict(
            (
                await db.execute(
                    select(
                        LtiResourceLinkUser.user_id,
                        func.bool_or(LtiResourceLinkUser.is_instructor),
                    )
                    .where(
                        LtiResourceLinkUser.user_id.in_(user_ids),
                        LtiResourceLinkUser.resource_link_id.in_(
                            _registration_subquery(reg.id)
                        ),
                    )
                    .group_by(LtiResourceLinkUser.user_id)
                )
            ).all()
        )

    items = []
    for link, user in rows:
        role = _claimed_role(link.claims)
        if role is None and user.id in instructor_by_user:
            role = "instructor" if instructor_by_user[user.id] else "learner"
        items.append(
            LtiUserLinkAdminRead(
                id=link.id,
                user_id=user.id,
                sub=link.sub,
                pseudonym=user.pseudonym,
                name=user.name if reveal else None,
                email=user.email if reveal else None,
                role=role,
                link_method=link.link_method,
                provisioned_account=link.link_method == "provisioned",
                consent_at=link.consent_at,
                consent_version=link.consent_version,
                research_consent_at=link.research_consent_at,
                last_launch_at=link.last_launch_at,
                unlinked_at=link.unlinked_at,
                anonymized=user.anonymized_at is not None,
                created_at=link.created_at,
            )
        )
    return LtiUserLinkAdminPage(items=items, total=total, limit=limit, offset=offset)


@router.delete("/registrations/{registration_id}/user-links/{link_id}", status_code=204)
async def unlink_user(
    registration_id: str,
    link_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Detach an LMS identity from its account.

    The account and its memberships stay. The account's grade transfer rows
    and activity participation on this connection go away. A link the launch
    provisioned is kept as a tombstone (``unlinked_at``), so the account stays
    recognizable as an LMS account and can still be anonymized; any other
    link is deleted. The next launch asks for consent again; see the LMS
    docs for when it offers the account again.
    """
    reg, _scope = await _load_registration_scoped(db, current_user, registration_id)
    link = (
        await db.execute(
            select(LtiUserLink).where(
                LtiUserLink.id == link_id,
                LtiUserLink.registration_id == reg.id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise _not_found("user_link_not_found", "LMS account link")
    if link.unlinked_at is not None:
        return Response(status_code=204)

    link_ids = _registration_subquery(reg.id)
    syncs = await db.execute(
        delete(LtiGradeSync).where(
            LtiGradeSync.user_id == link.user_id,
            LtiGradeSync.resource_link_id.in_(link_ids),
        )
    )
    participations = await db.execute(
        delete(LtiResourceLinkUser).where(
            LtiResourceLinkUser.user_id == link.user_id,
            LtiResourceLinkUser.resource_link_id.in_(link_ids),
        )
    )
    tombstone = link.link_method == "provisioned"
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="user_link_unlinked",
        registration=reg,
        changes={
            "user_link_id": link.id,
            "user_id": link.user_id,
            "link_method": link.link_method,
            "tombstone": tombstone,
            "grade_syncs_deleted": syncs.rowcount or 0,
            "participations_deleted": participations.rowcount or 0,
        },
    )
    if tombstone:
        link.unlinked_at = datetime.now(timezone.utc)
        # The LMS name/email snapshot is not needed once the link is gone.
        # The tool's record of the group it added the account to stays (no
        # personal data): a relaunch reuses this row, and the record keeps a
        # group removal or group admin demotion from being undone.
        link.claims = _retained_claims(link.claims)
        # A relaunch reuses this row; it must ask for consent again.
        link.consent_at = None
        link.consent_version = None
        link.research_consent_at = None
    else:
        await db.delete(link)
    await db.commit()
    return Response(status_code=204)


#: ``lti_user_links.claims`` keys an unlink keeps (tool bookkeeping only).
_RETAINED_CLAIM_KEYS = ("group_grant",)


def _retained_claims(claims: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(claims, dict):
        return None
    kept = {key: claims[key] for key in _RETAINED_CLAIM_KEYS if key in claims}
    return kept or None


async def _load_user_link_with_user(
    db: AsyncSession, reg: LtiPlatformRegistration, link_id: str
) -> Tuple[LtiUserLink, User]:
    found = (
        await db.execute(
            select(LtiUserLink, User)
            .join(User, User.id == LtiUserLink.user_id)
            .where(
                LtiUserLink.id == link_id,
                LtiUserLink.registration_id == reg.id,
            )
            .execution_options(populate_existing=True)
        )
    ).first()
    if found is None:
        raise _not_found("user_link_not_found", "LMS account link")
    return found[0], found[1]


@router.get(
    "/registrations/{registration_id}/user-links/{link_id}/anonymization",
    response_model=AnonymizationPreviewRead,
)
async def preview_user_anonymization(
    registration_id: str,
    link_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Whether the account behind an LMS link may be anonymized, and what
    stays and goes. Blockers and warnings are codes (see
    ``services/user_anonymization.py``); real name and email only for
    viewers who may see them (D8)."""
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    link, user = await _load_user_link_with_user(db, reg, link_id)
    check = await anonymization_check(
        db,
        user,
        actor_id=current_user.id,
        scope=_anonymization_scope(reg, scope),
        via_link_id=link.id,
    )
    footprint = await anonymization_footprint(db, user.id)
    reveal = _reveals_names(scope, reg.group_id)
    return AnonymizationPreviewRead(
        user_link_id=link.id,
        registration_id=reg.id,
        user=AnonymizationUserRead(
            id=user.id,
            display=_account_label(user, reveal),
            pseudonym=user.pseudonym,
            name=user.name if reveal else None,
            email=user.email if reveal else None,
        ),
        eligible=check.eligible,
        blockers=check.blockers,
        warnings=check.warnings,
        keeps=footprint["keeps"],
        removes=footprint["removes"],
    )


@router.post(
    "/registrations/{registration_id}/user-links/{link_id}/anonymize",
    response_model=AnonymizeResult,
)
async def anonymize_linked_user(
    registration_id: str,
    link_id: str,
    body: AnonymizeRequest,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Anonymize the account behind an LMS link (owner decision D16).

    ``expected_user_id`` is the account the preview showed; a link that now
    points elsewhere answers 409 ``link_changed``. Refusals answer 409
    ``anonymization_blocked`` with the ``blockers``. The account keeps its
    answers and grades; its LMS links, grade transfer rows and sessions go.
    The audit row holds ids and counts only.
    """
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    link, user = await _load_user_link_with_user(db, reg, link_id)
    if user.id != body.expected_user_id:
        raise _error(
            status.HTTP_409_CONFLICT,
            "link_changed",
            "This LMS link now belongs to another account. Reload the list.",
        )
    try:
        result = await anonymize_user(
            db,
            user.id,
            actor_id=current_user.id,
            reason="lti_admin",
            scope=_anonymization_scope(reg, scope),
            via_link_id=link.id,
        )
    except AnonymizationRefused as refused:
        # Nothing was written; closing the session releases the row lock.
        raise _anonymization_blocked(refused.blockers) from None
    except AnonymizationUserNotFound:
        raise _not_found("user_link_not_found", "LMS account link") from None
    _record_event(
        db,
        organization_id=reg.organization_id,
        actor=current_user,
        action="user_anonymized",
        registration=reg,
        changes=_anonymized_changes(link_id, result, "lti_admin"),
    )
    await db.commit()
    await run_in_threadpool(revoke_lms_link_tokens, [result.user_id])
    return AnonymizeResult(
        user_id=result.user_id,
        anonymized_at=result.anonymized_at,
        pseudonym=result.pseudonym,
        warnings=result.warnings,
        removed=result.removed,
        kept=result.kept,
    )


def _event_read(event: LtiAdminEvent, actor, reveal: bool) -> LtiAdminEventRead:
    return LtiAdminEventRead(
        id=event.id,
        organization_id=event.organization_id,
        registration_id=event.registration_id,
        registration_name=event.registration_name,
        group_id=event.group_id,
        actor_user_id=event.actor_user_id,
        actor_display=(display_name(actor, reveal) or None) if actor else None,
        actor_kind=event.actor_kind,
        action=event.action,
        changes=event.changes,
        created_at=event.created_at,
    )


@router.get("/events", response_model=List[LtiAdminEventRead])
async def list_organization_events(
    organization_id: Optional[str] = Query(None),
    registration_id: Optional[str] = Query(
        None,
        description=(
            "Only entries about this connection, also after it was deleted "
            "(the delete and anonymize entries keep its id)."
        ),
    ),
    deleted_only: bool = Query(
        False, description="Only entries whose connection no longer exists."
    ),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The newest LMS connection history of an organization (at most 100).

    Unlike the per-connection history, this includes invites and the
    entries of deleted connections (the deletion itself and the accounts
    anonymized with it). Group admins see the entries of their groups;
    org-wide entries are for org admins. Non-superadmins must name the
    organization.
    """
    scope = await _list_scope(db, current_user, organization_id)
    stmt = select(LtiAdminEvent)
    if organization_id is not None:
        stmt = stmt.where(LtiAdminEvent.organization_id == organization_id)
    group_clause = _group_filter(scope, LtiAdminEvent.group_id)
    if group_clause is not None:
        stmt = stmt.where(group_clause)
    if registration_id is not None:
        stmt = stmt.where(
            or_(
                LtiAdminEvent.registration_id == registration_id,
                LtiAdminEvent.changes["registration_id"].as_string()
                == registration_id,
            )
        )
    if deleted_only:
        stmt = stmt.where(LtiAdminEvent.registration_id.is_(None))
    events = (
        (
            await db.execute(
                stmt.order_by(LtiAdminEvent.created_at.desc(), LtiAdminEvent.id).limit(
                    EVENTS_LIMIT
                )
            )
        )
        .scalars()
        .all()
    )
    actors = await _users_by_id(db, (event.actor_user_id for event in events))
    return [
        _event_read(
            event,
            actors.get(event.actor_user_id),
            _reveals_names(scope, event.group_id),
        )
        for event in events
    ]


@router.get(
    "/registrations/{registration_id}/events",
    response_model=List[LtiAdminEventRead],
)
async def list_registration_events(
    registration_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The newest changes to a connection (at most 100)."""
    reg, scope = await _load_registration_scoped(db, current_user, registration_id)
    events = (
        (
            await db.execute(
                select(LtiAdminEvent)
                .where(LtiAdminEvent.registration_id == reg.id)
                .order_by(LtiAdminEvent.created_at.desc(), LtiAdminEvent.id)
                .limit(EVENTS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    actors = await _users_by_id(db, (event.actor_user_id for event in events))
    reveal = _reveals_names(scope, reg.group_id)
    return [
        _event_read(event, actors.get(event.actor_user_id), reveal)
        for event in events
    ]


# --------------------------------------------------------------------------- #
# Grade-sync outbox
# --------------------------------------------------------------------------- #
def _grade_sync_select():
    return (
        select(
            LtiGradeSync,
            LtiResourceLink,
            LtiPlatformRegistration.name,
            LtiPlatformRegistration.organization_id,
            LtiPlatformRegistration.group_id,
            Project.title,
            User.pseudonym,
            User.name,
        )
        .join(LtiResourceLink, LtiResourceLink.id == LtiGradeSync.resource_link_id)
        .join(
            LtiPlatformRegistration,
            LtiPlatformRegistration.id == LtiResourceLink.registration_id,
        )
        .join(User, User.id == LtiGradeSync.user_id)
        .outerjoin(Project, Project.id == LtiResourceLink.project_id)
    )


def _grade_sync_read(
    row, scope: Optional[OrgAdminScope], model=LtiGradeSyncAdminRead, **extra
):
    sync, link, reg_name, org_id, group_id, project_title, pseudonym, name = row
    reveal = _reveals_names(scope, group_id)
    base = LtiGradeSyncRead.model_validate(sync).model_dump()
    base.update(
        registration_id=link.registration_id,
        registration_name=reg_name,
        organization_id=org_id,
        context_title=link.context_title,
        resource_title=link.resource_title,
        project_id=link.project_id,
        project_title=project_title,
        student_pseudonym=pseudonym,
        student_name=name if reveal else None,
        **extra,
    )
    return model(**base)


@router.get("/grade-syncs", response_model=List[LtiGradeSyncAdminRead])
async def list_grade_syncs(
    project_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    registration_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Grade transfer rows with student and activity context, newest first.

    Filterable by project, organization, connection and status. Same scope
    rules as the connection list.
    """
    scope = await _list_scope(db, current_user, organization_id)
    stmt = _grade_sync_select()
    if organization_id:
        stmt = stmt.where(LtiPlatformRegistration.organization_id == organization_id)
    group_clause = _group_filter(scope, LtiPlatformRegistration.group_id)
    if group_clause is not None:
        stmt = stmt.where(group_clause)
    if project_id:
        stmt = stmt.where(LtiResourceLink.project_id == project_id)
    if registration_id:
        stmt = stmt.where(LtiResourceLink.registration_id == registration_id)
    if status_filter:
        stmt = stmt.where(LtiGradeSync.status == status_filter)
    stmt = stmt.order_by(LtiGradeSync.created_at.desc(), LtiGradeSync.id).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_grade_sync_read(row, scope) for row in rows]


@router.post("/grade-syncs/{grade_sync_id}/retry", response_model=LtiGradeSyncRetryRead)
async def retry_grade_sync(
    grade_sync_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Reset a (typically failed) transfer row and queue its push now.

    ``dispatched`` is False when the push could not be queued (community
    edition or broker trouble); the hourly sweep then sends it.
    """
    found = (
        await db.execute(
            select(
                LtiGradeSync,
                LtiPlatformRegistration.id,
                LtiPlatformRegistration.name,
                LtiPlatformRegistration.organization_id,
                LtiPlatformRegistration.group_id,
            )
            .join(LtiResourceLink, LtiResourceLink.id == LtiGradeSync.resource_link_id)
            .join(
                LtiPlatformRegistration,
                LtiPlatformRegistration.id == LtiResourceLink.registration_id,
            )
            .where(LtiGradeSync.id == grade_sync_id)
        )
    ).first()
    if found is None:
        raise _not_found("grade_sync_not_found", "Grade transfer")
    row, reg_id, reg_name, org_id, group_id = found
    scope = await _require_scope(db, current_user, org_id, group_id)

    _record_event(
        db,
        organization_id=org_id,
        actor=current_user,
        action="grade_sync_retried",
        registration_id=reg_id,
        registration_name=reg_name,
        changes={
            "grade_sync_id": row.id,
            "kind": row.kind,
            "previous_status": row.status,
            "previous_attempts": row.attempts,
        },
    )
    row.status = "pending"
    row.attempts = 0
    row.next_retry_at = datetime.now(timezone.utc)
    row.last_error = None
    await db.commit()

    dispatched = await run_in_threadpool(extensions.dispatch_lti_grade_sync, row.id)

    refreshed = (
        await db.execute(
            _grade_sync_select()
            .where(LtiGradeSync.id == row.id)
            .execution_options(populate_existing=True)
        )
    ).one()
    return _grade_sync_read(
        refreshed,
        scope,
        model=LtiGradeSyncRetryRead,
        dispatched=dispatched,
    )
