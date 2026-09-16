"""Anonymize an account: remove who the person is, keep what they did.

Owner decision D16 (LMS self-service): org admins, and group admins for their
group's connections, anonymize the accounts an LMS launch created. Superadmins
can anonymize any account through ``POST /api/users/{id}/anonymize``. There is
no hard delete here, and nothing is ever reassigned to another account.

What anonymizing does, in the caller's transaction (the caller commits):

* **Scrubbed on the user row:** name (``ANONYMIZED_NAME``), username and email
  (a random ``anon-<hex>`` handle and ``anon-<hex>@anonymized.invalid``, which
  no LMS relaunch can derive and no mail goes to), the parked activation
  address, password and every reset, verification and invitation token, the
  personal provider API keys, and the research-profile answers. The account is
  deactivated and ``anonymized_at`` is stamped. The pseudonym is replaced by
  a fresh ``Anonym-<hex>`` one: staff saw the old pseudonym next to the real
  name, so keeping it would tie the remaining records to the person. Kept:
  the research-consent timestamp (the legal basis of the records that
  remain).
* **Deleted:** refresh tokens (open sessions end, and ``refresh_access_token``
  never checks ``is_active``), every LMS identity link with its claims
  snapshot and consent fields, the account's grade transfer rows, the profile
  history, own notifications and preferences, personal custom-model keys,
  group memberships, and other users' notifications that embed the person's
  name or email (``project_created`` of their projects, notices that name
  them as the acting account by id, and notices that carry their name or
  address as text: assignment, invitation, deletion, archive, import and
  member-joined notices).
* **Updated:** every org membership is deactivated (rows stay for
  statistics), share links the person created are revoked, invitations lose
  their pending-user pointer, and invitations sent to the old address get the
  placeholder address (pending ones expire now).
* **Kept untouched:** annotations, task evaluations, drafts, timer sessions,
  grading feedback, entitlements, created projects and LMS activity
  participation rows (``lti_resource_link_users``, ids and timestamps only).
  The user row survives, so no foreign key changes.

Who may be anonymized is decided by :func:`anonymization_check_sync`. It
returns blocker codes (refusals) and warning codes (shown before confirming):

==========================  ==================================================
``superadmin``              the account is a platform administrator
``self``                    the actor would anonymize their own account
``already_anonymized``      nothing left to do
``has_payment_records``     a payment provider still holds name and email
``not_provisioned``         the LMS link did not create the account (an
                            account linked by proof is only unlinked)
``linked_elsewhere``        an LMS link on a connection outside the scope
``member_elsewhere``        an active membership outside the scope (an
                            ANNOTATOR membership in an org the extended
                            policy marks as implicit does not count), or,
                            for a group admin, a group they do not administer
``target_is_org_admin``     a group admin may not anonymize an org admin
extended codes              from ``extensions.lti_anonymization_policy``
                            (e.g. ``active_subscription``)
==========================  ==================================================

Warning: ``has_password`` (the person set up their own password; it is
removed as well).

The checks run on a sync ``Session``; the async entry points bridge through
``AsyncSession.run_sync``, so both lanes run the same statements in the same
transaction. :func:`anonymize_user_sync` locks the user row (``FOR UPDATE``,
the lock the activation mail worker takes too) and checks again before it
writes.

After the commit, call :func:`revoke_lms_link_tokens` so the open LMS
account-link confirmation tokens (Redis, extended edition) go away. It uses a
guarded import of ``benger_extended.lti.identity.revoke_link_tokens`` instead
of a hook: it is a best-effort cleanup outside the transaction, the extended
confirm path refuses anonymized accounts anyway, and it only runs when
``extensions`` loaded the extended package (handshake passed).
"""

from __future__ import annotations

import importlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Iterable, List, Optional

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import extensions
from models import (
    CustomModelCredential,
    Invitation,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiUserLink,
    MarketplaceOrder,
    Notification,
    NotificationType,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    RefreshToken,
    StudentSubscription,
    TaskEvaluation,
    User,
    UserColumnPreferences,
    UserNotificationPreference,
    UserProfileHistory,
)
from project_models import Annotation, Project, ProjectShareLink

logger = logging.getLogger(__name__)

ANONYMIZED_NAME = "Anonymisiert"
ANONYMIZED_EMAIL_DOMAIN = "anonymized.invalid"
ANONYMIZED_USERNAME_PREFIX = "anon-"
#: A fresh pseudonym replaces the old one: staff saw the old pseudonym next
#: to the real name, so keeping it would let them re-identify the records.
ANONYMIZED_PSEUDONYM_PREFIX = "Anonym-"
#: Username prefixes only the system hands out: ``anon-`` (this module) and
#: ``lti-`` (accounts an LMS launch creates). Signup and profile updates
#: should refuse them (:func:`is_reserved_username`).
RESERVED_USERNAME_PREFIXES = (ANONYMIZED_USERNAME_PREFIX, "lti-")
LINK_PROVISIONED = "provisioned"

BLOCKER_SUPERADMIN = "superadmin"
BLOCKER_SELF = "self"
BLOCKER_ALREADY_ANONYMIZED = "already_anonymized"
BLOCKER_HAS_PAYMENT_RECORDS = "has_payment_records"
BLOCKER_NOT_PROVISIONED = "not_provisioned"
BLOCKER_LINKED_ELSEWHERE = "linked_elsewhere"
BLOCKER_MEMBER_ELSEWHERE = "member_elsewhere"
BLOCKER_TARGET_IS_ORG_ADMIN = "target_is_org_admin"
WARNING_HAS_PASSWORD = "has_password"

#: Research-profile answers (the ``create_profile_snapshot`` list plus the
#: legal specialization and state exam fields). Quasi-identifiers, so they go.
PROFILE_FIELDS = (
    "legal_expertise_level",
    "german_proficiency",
    "degree_program_type",
    "current_semester",
    "gender",
    "age",
    "job",
    "years_of_experience",
    "subjective_competence_civil",
    "subjective_competence_public",
    "subjective_competence_criminal",
    "grade_zwischenpruefung",
    "grade_vorgeruecktenubung",
    "grade_first_staatsexamen",
    "grade_second_staatsexamen",
    "ati_s_scores",
    "ptt_a_scores",
    "ki_experience_scores",
    "legal_specializations",
    "german_state_exams_count",
    "german_state_exams_data",
)

#: Credentials and tokens that die with the identity.
_CLEARED_FIELDS = (
    "hashed_password",
    "password_reset_token",
    "password_reset_expires",
    "pending_activation_email",
    "email_verification_token",
    "email_verification_sent_at",
    "email_verified_by_id",
    "email_verified_at",
    "email_verification_method",
    "invitation_token",
    "invitation_expires_at",
    "encrypted_openai_api_key",
    "encrypted_anthropic_api_key",
    "encrypted_google_api_key",
    "encrypted_deepinfra_api_key",
    "encrypted_grok_api_key",
    "encrypted_mistral_api_key",
    "encrypted_cohere_api_key",
    "profile_confirmed_at",
)

_HANDLE_ATTEMPTS = 8


def is_reserved_username(username: Optional[str]) -> bool:
    """True when ``username`` uses a prefix only the system hands out."""
    return bool(username) and str(username).strip().lower().startswith(
        RESERVED_USERNAME_PREFIXES
    )


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AnonymizationScope:
    """The part of the platform the actor administers.

    ``group_ids`` None means the whole organization (org admins, and
    superadmins acting on one org's connections); otherwise only connections
    and groups with one of these ids count as inside the scope.
    """

    organization_id: str
    group_ids: Optional[FrozenSet[str]] = None

    @property
    def org_wide(self) -> bool:
        return self.group_ids is None


@dataclass
class AnonymizationCheck:
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return not self.blockers


class AnonymizationRefused(Exception):
    """The account may not be anonymized; ``blockers`` says why."""

    def __init__(self, blockers: Iterable[str]):
        self.blockers = list(blockers)
        super().__init__(", ".join(self.blockers) or "refused")


class AnonymizationUserNotFound(LookupError):
    """No account with that id."""


@dataclass
class AnonymizationResult:
    user_id: str
    anonymized_at: datetime
    pseudonym: Optional[str]
    warnings: List[str]
    removed: Dict[str, int]
    kept: Dict[str, int]


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def _role_value(role: Any) -> str:
    return str(getattr(role, "value", role) or "").upper()


def _has_payment_records(db: Session, user_id: str) -> bool:
    subscription = db.execute(
        select(
            exists().where(
                StudentSubscription.user_id == user_id,
                or_(
                    StudentSubscription.provider_customer_id.isnot(None),
                    StudentSubscription.provider_subscription_id.isnot(None),
                ),
            )
        )
    ).scalar()
    if subscription:
        return True
    return bool(
        db.execute(
            select(exists().where(MarketplaceOrder.buyer_user_id == user_id))
        ).scalar()
    )


def _linked_elsewhere(db: Session, user_id: str, scope: AnonymizationScope) -> bool:
    outside = LtiPlatformRegistration.organization_id != scope.organization_id
    if not scope.org_wide:
        outside = or_(
            outside,
            LtiPlatformRegistration.group_id.is_(None),
            LtiPlatformRegistration.group_id.notin_(sorted(scope.group_ids)),
        )
    stmt = (
        select(LtiUserLink.id)
        .join(
            LtiPlatformRegistration,
            LtiPlatformRegistration.id == LtiUserLink.registration_id,
        )
        .where(LtiUserLink.user_id == user_id, outside)
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def _member_elsewhere(
    db: Session,
    user_id: str,
    scope: AnonymizationScope,
    implicit_org_ids: FrozenSet[str],
) -> bool:
    rows = db.execute(
        select(OrganizationMembership.organization_id, OrganizationMembership.role).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id != scope.organization_id,
        )
    ).all()
    for org_id, role in rows:
        implicit = (
            str(org_id) in implicit_org_ids
            and _role_value(role) == OrganizationRole.ANNOTATOR.value
        )
        if not implicit:
            return True
    if scope.org_wide:
        return False
    # A group admin covers only their groups: a membership in another group
    # of the org belongs to someone else's scope.
    stmt = (
        select(OrganizationGroupMembership.id)
        .join(
            OrganizationGroup,
            OrganizationGroup.id == OrganizationGroupMembership.group_id,
        )
        .where(
            OrganizationGroupMembership.user_id == user_id,
            OrganizationGroup.organization_id == scope.organization_id,
            OrganizationGroup.id.notin_(sorted(scope.group_ids)),
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def _is_org_admin(db: Session, user_id: str, organization_id: str) -> bool:
    role = db.execute(
        select(OrganizationMembership.role).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    ).scalar()
    return _role_value(role) == OrganizationRole.ORG_ADMIN.value


def _provisioned_link(db: Session, link_id: str, user_id: str) -> bool:
    row = db.execute(
        select(LtiUserLink.user_id, LtiUserLink.link_method).where(
            LtiUserLink.id == link_id
        )
    ).first()
    return row is not None and row.user_id == user_id and row.link_method == LINK_PROVISIONED


def anonymization_check_sync(
    db: Session,
    user: User,
    *,
    actor_id: Optional[str],
    scope: Optional[AnonymizationScope] = None,
    via_link_id: Optional[str] = None,
) -> AnonymizationCheck:
    """Blockers and warnings for anonymizing ``user``.

    ``scope`` None skips the scope rules (``linked_elsewhere``,
    ``member_elsewhere``, ``target_is_org_admin``); the superadmin user admin
    uses that. ``via_link_id`` names the LMS link the request came through;
    it must be a provisioned link of this account.
    """
    check = AnonymizationCheck()
    blockers = check.blockers
    if user.is_superadmin:
        blockers.append(BLOCKER_SUPERADMIN)
    if actor_id is not None and str(actor_id) == str(user.id):
        blockers.append(BLOCKER_SELF)
    if user.anonymized_at is not None:
        blockers.append(BLOCKER_ALREADY_ANONYMIZED)
    if via_link_id is not None and not _provisioned_link(db, via_link_id, user.id):
        blockers.append(BLOCKER_NOT_PROVISIONED)
    if _has_payment_records(db, user.id):
        blockers.append(BLOCKER_HAS_PAYMENT_RECORDS)

    policy = extensions.lti_anonymization_policy(db, user.id)
    implicit_org_ids = frozenset(policy.get("implicit_org_ids") or ())
    if scope is not None:
        if _linked_elsewhere(db, user.id, scope):
            blockers.append(BLOCKER_LINKED_ELSEWHERE)
        if _member_elsewhere(db, user.id, scope, implicit_org_ids):
            blockers.append(BLOCKER_MEMBER_ELSEWHERE)
        if not scope.org_wide and _is_org_admin(db, user.id, scope.organization_id):
            blockers.append(BLOCKER_TARGET_IS_ORG_ADMIN)
    for code in policy.get("blockers") or ():
        if code not in blockers:
            blockers.append(code)

    if user.hashed_password is not None or user.password_set:
        check.warnings.append(WARNING_HAS_PASSWORD)
    return check


async def anonymization_check(
    db: AsyncSession, user: User, **kwargs: Any
) -> AnonymizationCheck:
    """Async twin of :func:`anonymization_check_sync`."""
    return await db.run_sync(
        lambda session: anonymization_check_sync(session, user, **kwargs)
    )


# --------------------------------------------------------------------------- #
# Footprint
# --------------------------------------------------------------------------- #
def _count(db: Session, stmt) -> int:
    return int(db.execute(stmt).scalar() or 0)


def anonymization_footprint_sync(db: Session, user_id: str) -> Dict[str, Dict[str, int]]:
    """What stays (``keeps``) and what goes (``removes``), as counts."""
    return {
        "keeps": {
            "annotations": _count(
                db,
                select(func.count(Annotation.id)).where(
                    Annotation.completed_by == user_id
                ),
            ),
            "task_evaluations": _count(
                db,
                select(func.count(TaskEvaluation.id))
                .join(Annotation, Annotation.id == TaskEvaluation.annotation_id)
                .where(Annotation.completed_by == user_id),
            ),
            "projects_created": _count(
                db,
                select(func.count(Project.id)).where(
                    Project.created_by == user_id, Project.deleted_at.is_(None)
                ),
            ),
        },
        "removes": {
            "lti_user_links": _count(
                db,
                select(func.count(LtiUserLink.id)).where(LtiUserLink.user_id == user_id),
            ),
            "lti_grade_syncs": _count(
                db,
                select(func.count(LtiGradeSync.id)).where(
                    LtiGradeSync.user_id == user_id
                ),
            ),
            "sessions": _count(
                db,
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_active == True,  # noqa: E712
                ),
            ),
            "memberships": _count(
                db,
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                ),
            ),
        },
    }


async def anonymization_footprint(
    db: AsyncSession, user_id: str
) -> Dict[str, Dict[str, int]]:
    """Async twin of :func:`anonymization_footprint_sync`."""
    return await db.run_sync(
        lambda session: anonymization_footprint_sync(session, user_id)
    )


# --------------------------------------------------------------------------- #
# Anonymize
# --------------------------------------------------------------------------- #
def _free_handle(db: Session) -> str:
    """A random ``anon-<hex>`` handle no username or email uses yet."""
    for _attempt in range(_HANDLE_ATTEMPTS):
        handle = f"{ANONYMIZED_USERNAME_PREFIX}{secrets.token_hex(8)}"
        email = f"{handle}@{ANONYMIZED_EMAIL_DOMAIN}"
        taken = db.execute(
            select(
                exists().where(
                    or_(User.username == handle, func.lower(User.email) == email)
                )
            )
        ).scalar()
        if not taken:
            return handle
    raise RuntimeError("no free anonymized handle")


def _rowcount(result) -> int:
    return max(int(result.rowcount or 0), 0)


def _delete(db: Session, model, *conditions) -> int:
    return _rowcount(
        db.execute(
            delete(model)
            .where(*conditions)
            .execution_options(synchronize_session=False)
        )
    )


def _update(db: Session, model, values: Dict[str, Any], *conditions) -> int:
    return _rowcount(
        db.execute(
            update(model)
            .where(*conditions)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    )


#: Notification payload keys that name the person who acted (by account id).
_ACTOR_ID_KEYS = (
    "deleted_by_user_id",
    "archived_by_user_id",
    "updated_by_user_id",
    "imported_by_user_id",
)
#: Payload keys that carry a person's name or address as text (the actor of
#: an assignment, invitation, deletion, ...; the new member of a join).
_PERSON_TEXT_KEYS = (
    "assigned_by",
    "removed_by",
    "inviter_name",
    "creator_name",
    "new_member_name",
    "new_member_email",
    "invitee_email",
    "deleted_by_username",
    "archived_by_username",
    "updated_by_username",
    "imported_by_username",
)
#: Names too generic to identify anyone; never matched as text.
_GENERIC_NAMES = frozenset({"", "lti student", "user", "unknown", "anonymisiert"})


def _foreign_notification_filter(
    user_id: str, old_email: Optional[str], old_name: Optional[str] = None
):
    """Other users' notifications that name the person: the
    ``project_created`` notices of their projects, notices whose payload
    names them as the acting account, and notices that carry their name or
    address as text (the message text of such a notice usually repeats
    it, so the whole row goes)."""
    created_projects = select(Project.id).where(Project.created_by == user_id)
    clauses = [
        and_(
            Notification.type == NotificationType.PROJECT_CREATED,
            Notification.data["project_id"].as_string().in_(created_projects),
        )
    ]
    for key in _ACTOR_ID_KEYS:
        clauses.append(Notification.data[key].as_string() == str(user_id))
    texts = set()
    address = (old_email or "").strip().lower()
    if address:
        texts.add(address)
    name = (old_name or "").strip().lower()
    if name not in _GENERIC_NAMES:
        texts.add(name)
    if texts:
        for key in _PERSON_TEXT_KEYS:
            clauses.append(
                func.lower(func.trim(Notification.data[key].as_string())).in_(
                    sorted(texts)
                )
            )
    return and_(Notification.user_id != user_id, or_(*clauses))


def _free_pseudonym(db: Session) -> str:
    """A random ``Anonym-<hex>`` pseudonym no account uses yet."""
    for _attempt in range(_HANDLE_ATTEMPTS):
        pseudonym = f"{ANONYMIZED_PSEUDONYM_PREFIX}{secrets.token_hex(6)}"
        taken = db.execute(
            select(exists().where(User.pseudonym == pseudonym))
        ).scalar()
        if not taken:
            return pseudonym
    raise RuntimeError("no free anonymized pseudonym")


def anonymize_user_sync(
    db: Session,
    user_id: str,
    *,
    actor_id: Optional[str],
    reason: str,
    scope: Optional[AnonymizationScope] = None,
    via_link_id: Optional[str] = None,
) -> AnonymizationResult:
    """Anonymize one account in the current transaction (flushes, never
    commits).

    Locks the user row, runs :func:`anonymization_check_sync` with the same
    arguments and raises :class:`AnonymizationRefused` on any blocker, or
    :class:`AnonymizationUserNotFound`. ``reason`` is logged only (e.g.
    ``lti_admin``, ``registration_deleted``, ``superadmin``).
    """
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if user is None:
        raise AnonymizationUserNotFound(user_id)

    check = anonymization_check_sync(
        db, user, actor_id=actor_id, scope=scope, via_link_id=via_link_id
    )
    if check.blockers:
        raise AnonymizationRefused(check.blockers)

    kept = anonymization_footprint_sync(db, user.id)["keeps"]
    now = datetime.now(timezone.utc)
    old_email = user.email
    old_name = user.name
    handle = _free_handle(db)
    pseudonym = _free_pseudonym(db)
    new_email = f"{handle}@{ANONYMIZED_EMAIL_DOMAIN}"
    uid = user.id

    removed: Dict[str, int] = {}
    removed["sessions"] = _delete(db, RefreshToken, RefreshToken.user_id == uid)
    removed["lti_user_links"] = _delete(db, LtiUserLink, LtiUserLink.user_id == uid)
    removed["lti_grade_syncs"] = _delete(db, LtiGradeSync, LtiGradeSync.user_id == uid)
    removed["profile_history"] = _delete(
        db, UserProfileHistory, UserProfileHistory.user_id == uid
    )
    removed["foreign_notifications"] = _delete(
        db, Notification, _foreign_notification_filter(uid, old_email, old_name)
    )
    removed["notifications"] = _delete(db, Notification, Notification.user_id == uid)
    removed["notification_preferences"] = _delete(
        db, UserNotificationPreference, UserNotificationPreference.user_id == uid
    )
    removed["column_preferences"] = _delete(
        db, UserColumnPreferences, UserColumnPreferences.user_id == uid
    )
    removed["custom_model_credentials"] = _delete(
        db, CustomModelCredential, CustomModelCredential.user_id == uid
    )
    removed["group_memberships"] = _delete(
        db, OrganizationGroupMembership, OrganizationGroupMembership.user_id == uid
    )
    removed["memberships"] = _update(
        db,
        OrganizationMembership,
        {"is_active": False},
        OrganizationMembership.user_id == uid,
        OrganizationMembership.is_active == True,  # noqa: E712
    )
    removed["share_links"] = _update(
        db,
        ProjectShareLink,
        {"revoked_at": now},
        ProjectShareLink.created_by == uid,
        ProjectShareLink.revoked_at.is_(None),
    )
    _update(db, Invitation, {"pending_user_id": None}, Invitation.pending_user_id == uid)
    invitations = 0
    address = (old_email or "").strip().lower()
    if address:
        same_address = func.lower(Invitation.email) == address
        _update(
            db,
            Invitation,
            {"expires_at": now},
            same_address,
            Invitation.accepted == False,  # noqa: E712
            Invitation.expires_at > now,
        )
        invitations = _update(db, Invitation, {"email": new_email}, same_address)
    removed["invitations"] = invitations

    user.username = handle
    user.email = new_email
    user.name = ANONYMIZED_NAME
    user.pseudonym = pseudonym
    user.use_pseudonym = True
    user.is_active = False
    user.anonymized_at = now
    user.password_set = False
    user.email_verified = False
    user.mandatory_profile_completed = False
    user.timezone = "UTC"
    for name in _CLEARED_FIELDS + PROFILE_FIELDS:
        setattr(user, name, None)
    db.flush()

    logger.info(
        "Anonymized user %s (actor %s, reason %s)", uid, actor_id or "-", reason
    )
    return AnonymizationResult(
        user_id=uid,
        anonymized_at=now,
        pseudonym=user.pseudonym,
        warnings=list(check.warnings),
        removed=removed,
        kept=kept,
    )


async def anonymize_user(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> AnonymizationResult:
    """Async twin of :func:`anonymize_user_sync` (same keyword arguments)."""
    return await db.run_sync(
        lambda session: anonymize_user_sync(session, user_id, **kwargs)
    )


def revoke_lms_link_tokens(user_ids: Iterable[str]) -> int:
    """Delete the open LMS account-link confirmation tokens of the given
    accounts. Call after the commit. Best effort: returns the number of
    tokens removed and never raises (the extended confirm path refuses
    anonymized accounts on its own, and the tokens expire within 24 h).
    """
    ids = [str(uid) for uid in user_ids if uid]
    if not ids or getattr(extensions, "_extended", None) is None:
        return 0
    try:
        identity = importlib.import_module("benger_extended.lti.identity")
        revoke = getattr(identity, "revoke_link_tokens")
    except Exception:
        logger.warning("LMS link token cleanup unavailable", exc_info=True)
        return 0
    removed = 0
    for uid in ids:
        try:
            removed += int(revoke(uid) or 0)
        except Exception:
            logger.warning("Could not revoke LMS link tokens of %s", uid, exc_info=True)
    return removed
