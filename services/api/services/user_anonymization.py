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

from sqlalchemy import and_, case, delete, exists, func, or_, select, update
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
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    ProjectShareLink,
    Task,
    TaskAssignment,
)

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
            # Every refresh token row, revoked and expired ones included:
            # anonymizing deletes them all, and the preview must match the
            # count the audit event records afterwards.
            "sessions": _count(
                db,
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.user_id == user_id
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
#: Accounts per set-based pass (bounded ``IN`` lists and lock sets).
BATCH_SIZE = 200


def _free_names(db: Session, count: int, make, taken_stmt) -> List[str]:
    """``count`` fresh random values from ``make()`` that ``taken_stmt``
    (a callable returning a SELECT of the taken ones) does not report."""
    found: List[str] = []
    for _attempt in range(_HANDLE_ATTEMPTS):
        wanted = count - len(found)
        if wanted <= 0:
            break
        proposals = {make() for _ in range(wanted)} - set(found)
        taken = set(db.execute(taken_stmt(sorted(proposals))).scalars().all())
        found.extend(sorted(proposals - taken))
    if len(found) < count:
        raise RuntimeError("no free anonymized handle")
    return found[:count]


def _free_handles(db: Session, count: int) -> List[str]:
    """``count`` random ``anon-<hex>`` handles no username or email uses."""

    def taken(handles):
        emails = [f"{h}@{ANONYMIZED_EMAIL_DOMAIN}" for h in handles]
        return select(User.username).where(User.username.in_(handles)).union(
            select(
                func.split_part(func.lower(User.email), "@", 1)
            ).where(func.lower(User.email).in_(emails))
        )

    return _free_names(
        db,
        count,
        lambda: f"{ANONYMIZED_USERNAME_PREFIX}{secrets.token_hex(8)}",
        taken,
    )


def _free_pseudonyms(db: Session, count: int) -> List[str]:
    """``count`` random ``Anonym-<hex>`` pseudonyms no account uses."""
    return _free_names(
        db,
        count,
        lambda: f"{ANONYMIZED_PSEUDONYM_PREFIX}{secrets.token_hex(6)}",
        lambda names: select(User.pseudonym).where(User.pseudonym.in_(names)),
    )


def _free_handle(db: Session) -> str:
    """A random ``anon-<hex>`` handle no username or email uses yet."""
    return _free_handles(db, 1)[0]


def _free_pseudonym(db: Session) -> str:
    """A random ``Anonym-<hex>`` pseudonym no account uses yet."""
    return _free_pseudonyms(db, 1)[0]


def _counts(rows) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in rows:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _delete_by_user(db: Session, model, column, user_ids: List[str], *conditions):
    """Delete the rows of ``user_ids``; the number per user."""
    rows = db.execute(
        delete(model)
        .where(column.in_(user_ids), *conditions)
        .returning(column)
        .execution_options(synchronize_session=False)
    ).scalars()
    return _counts(rows)


def _update_by_user(
    db: Session, model, column, user_ids: List[str], values: Dict[str, Any], *conditions
):
    """Update the rows of ``user_ids``; the number per user."""
    rows = db.execute(
        update(model)
        .where(column.in_(user_ids), *conditions)
        .values(**values)
        .returning(column)
        .execution_options(synchronize_session=False)
    ).scalars()
    return _counts(rows)


def _footprints_kept(db: Session, user_ids: List[str]) -> Dict[str, Dict[str, int]]:
    """``anonymization_footprint_sync(...)["keeps"]`` for many accounts."""
    annotations = dict(
        db.execute(
            select(Annotation.completed_by, func.count(Annotation.id))
            .where(Annotation.completed_by.in_(user_ids))
            .group_by(Annotation.completed_by)
        ).all()
    )
    evaluations = dict(
        db.execute(
            select(Annotation.completed_by, func.count(TaskEvaluation.id))
            .join(Annotation, Annotation.id == TaskEvaluation.annotation_id)
            .where(Annotation.completed_by.in_(user_ids))
            .group_by(Annotation.completed_by)
        ).all()
    )
    projects = dict(
        db.execute(
            select(Project.created_by, func.count(Project.id))
            .where(Project.created_by.in_(user_ids), Project.deleted_at.is_(None))
            .group_by(Project.created_by)
        ).all()
    )
    return {
        uid: {
            "annotations": int(annotations.get(uid, 0)),
            "task_evaluations": int(evaluations.get(uid, 0)),
            "projects_created": int(projects.get(uid, 0)),
        }
        for uid in user_ids
    }


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
#: Their ``*_by_username`` companions carry the same person's name and are
#: covered by the id.
_ACTOR_ID_KEYS = (
    "deleted_by_user_id",
    "archived_by_user_id",
    "updated_by_user_id",
    "imported_by_user_id",
    "assigned_by_user_id",
    "removed_by_user_id",
    "inviter_user_id",
    "new_member_user_id",
)
#: Payload keys that carry a person's address as text. Addresses are unique,
#: so they match platform-wide.
_ADDRESS_TEXT_KEYS = ("new_member_email", "invitee_email")
#: Payload keys that carry a person's name as text (the actor of an
#: assignment or invitation, the creator of a project, the new member of a
#: join; the assignment keys hold the address when the actor had no name).
#: Names are not unique, so a name only matches inside the organizations and
#: projects the person belonged to (:func:`_in_person_scope`).
_NAME_TEXT_KEYS = (
    "assigned_by",
    "removed_by",
    "inviter_name",
    "creator_name",
    "new_member_name",
)
#: Names too generic to identify anyone; never matched as text.
_GENERIC_NAMES = frozenset({"", "lti student", "user", "unknown", "anonymisiert"})


def _text(value: Any) -> Optional[str]:
    """``lower(trim(data->>key))`` in Python (``trim`` strips spaces only)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip(" ").lower()
    if isinstance(value, (dict, list)):
        return None
    return str(value).strip(" ").lower()


@dataclass
class _Person:
    user_id: str
    address: str
    name: Optional[str]
    org_ids: set = field(default_factory=set)
    project_ids: set = field(default_factory=set)
    created_project_ids: set = field(default_factory=set)


def _notification_candidates(db: Session, people: List[_Person]):
    """Other users' notifications that may name one of ``people``: a superset
    in one scan; :func:`_names_person` decides per row."""
    ids = [p.user_id for p in people]
    texts = sorted(
        {p.address for p in people if p.address}
        | {p.name for p in people if p.name}
    )
    clauses = [
        and_(
            Notification.type == NotificationType.PROJECT_CREATED,
            Notification.data["project_id"]
            .as_string()
            .in_(select(Project.id).where(Project.created_by.in_(ids))),
        )
    ]
    for key in _ACTOR_ID_KEYS:
        clauses.append(Notification.data[key].as_string().in_(ids))
    if texts:
        for key in _ADDRESS_TEXT_KEYS + _NAME_TEXT_KEYS:
            clauses.append(
                func.lower(func.trim(Notification.data[key].as_string())).in_(texts)
            )
    return db.execute(
        select(
            Notification.id,
            Notification.type,
            Notification.data,
            Notification.organization_id,
        ).where(Notification.user_id.notin_(ids), or_(*clauses))
    ).all()


def _load_person_scopes(db: Session, people: List[_Person], rows) -> None:
    """Fill each person's org and project sets, as far as ``rows`` (the
    candidate notifications) need them."""
    by_id = {p.user_id: p for p in people}
    ids = sorted(by_id)
    for uid, project_id in db.execute(
        select(Project.created_by, Project.id).where(Project.created_by.in_(ids))
    ).all():
        by_id[str(uid)].created_project_ids.add(str(project_id))
    if not any(p.name for p in people):
        return
    for uid, org_id in db.execute(
        select(OrganizationMembership.user_id, OrganizationMembership.organization_id)
        .where(OrganizationMembership.user_id.in_(ids))
    ).all():
        by_id[str(uid)].org_ids.add(str(org_id))
    project_ids = sorted(
        {
            str(data.get("project_id"))
            for _id, _type, data, _org in rows
            if isinstance(data, dict) and data.get("project_id")
        }
    )
    if not project_ids:
        return
    for p in people:
        p.project_ids |= p.created_project_ids & set(project_ids)
    for stmt in (
        select(ProjectMember.user_id, ProjectMember.project_id).where(
            ProjectMember.user_id.in_(ids), ProjectMember.project_id.in_(project_ids)
        ),
        select(TaskAssignment.user_id, Task.project_id)
        .join(Task, Task.id == TaskAssignment.task_id)
        .where(TaskAssignment.user_id.in_(ids), Task.project_id.in_(project_ids)),
        select(Annotation.completed_by, Annotation.project_id).where(
            Annotation.completed_by.in_(ids), Annotation.project_id.in_(project_ids)
        ),
    ):
        for uid, project_id in db.execute(stmt.distinct()).all():
            by_id[str(uid)].project_ids.add(str(project_id))
    attached: Dict[str, set] = {}
    for project_id, org_id in db.execute(
        select(ProjectOrganization.project_id, ProjectOrganization.organization_id)
        .where(ProjectOrganization.project_id.in_(project_ids))
    ).all():
        attached.setdefault(str(org_id), set()).add(str(project_id))
    for p in people:
        for org_id in p.org_ids:
            p.project_ids |= attached.get(org_id, set())


def _names_person(person: _Person, ntype, data, organization_id) -> bool:
    """True when the notification names ``person`` (see
    :func:`_notification_candidates`)."""
    if not isinstance(data, dict):
        return False
    project_id = data.get("project_id")
    project_id = str(project_id) if project_id else None
    if (
        ntype == NotificationType.PROJECT_CREATED
        and project_id in person.created_project_ids
    ):
        return True
    for key in _ACTOR_ID_KEYS:
        value = data.get(key)
        if value is not None and str(value) == person.user_id:
            return True
    if person.address:
        for key in _ADDRESS_TEXT_KEYS + _NAME_TEXT_KEYS:
            if _text(data.get(key)) == person.address:
                return True
    if not person.name:
        return False
    if not any(_text(data.get(key)) == person.name for key in _NAME_TEXT_KEYS):
        return False
    return _in_person_scope(person, project_id, organization_id)


def _in_person_scope(person: _Person, project_id, organization_id) -> bool:
    """The notification belongs to an org the person was a member of, or to
    a project they created, joined, worked on or that is attached to one of
    their orgs."""
    if organization_id is not None and str(organization_id) in person.org_ids:
        return True
    return project_id is not None and project_id in person.project_ids


def _delete_foreign_notifications(db: Session, people: List[_Person]) -> Dict[str, int]:
    """Delete other users' notifications that name one of ``people``. The
    number per person; a notice naming several of them counts for the first
    (in id order)."""
    rows = _notification_candidates(db, people)
    if not rows:
        return {}
    _load_person_scopes(db, people, rows)
    ordered = sorted(people, key=lambda p: p.user_id)
    doomed: List[str] = []
    counts: Dict[str, int] = {}
    for notification_id, ntype, data, organization_id in rows:
        for person in ordered:
            if _names_person(person, ntype, data, organization_id):
                doomed.append(notification_id)
                counts[person.user_id] = counts.get(person.user_id, 0) + 1
                break
    for start in range(0, len(doomed), 1000):
        _delete(db, Notification, Notification.id.in_(doomed[start : start + 1000]))
    return counts


def _person(user: User) -> _Person:
    name = (user.name or "").strip().lower()
    return _Person(
        user_id=str(user.id),
        address=(user.email or "").strip().lower(),
        name=None if name in _GENERIC_NAMES else name,
    )


@dataclass
class AnonymizationOutcome:
    """One candidate of :func:`anonymize_users_sync`: anonymized
    (``result``), refused (``blockers``) or unknown (``not_found``)."""

    user_id: str
    via_link_id: Optional[str] = None
    result: Optional[AnonymizationResult] = None
    blockers: List[str] = field(default_factory=list)
    not_found: bool = False


def _anonymize_batch(
    db: Session,
    outcomes: List[AnonymizationOutcome],
    *,
    actor_id: Optional[str],
    reason: str,
    scope: Optional[AnonymizationScope],
) -> None:
    """One pass over distinct accounts (see :func:`anonymize_users_sync`)."""
    ids = sorted({o.user_id for o in outcomes})
    users = {
        str(u.id): u
        for u in db.execute(
            select(User)
            .where(User.id.in_(ids))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars()
    }
    eligible = []
    for outcome in outcomes:
        user = users.get(outcome.user_id)
        if user is None:
            outcome.not_found = True
            continue
        check = anonymization_check_sync(
            db,
            user,
            actor_id=actor_id,
            scope=scope,
            via_link_id=outcome.via_link_id,
        )
        if check.blockers:
            outcome.blockers = list(check.blockers)
            continue
        eligible.append((outcome, user, check))
    if not eligible:
        return

    uids = [str(user.id) for _o, user, _c in eligible]
    kept = _footprints_kept(db, uids)
    now = datetime.now(timezone.utc)
    people = [_person(user) for _o, user, _c in eligible]
    handles = _free_handles(db, len(eligible))
    pseudonyms = _free_pseudonyms(db, len(eligible))
    new_email = {
        uid: f"{handle}@{ANONYMIZED_EMAIL_DOMAIN}" for uid, handle in zip(uids, handles)
    }

    steps: List[tuple] = [
        ("sessions", lambda: _delete_by_user(db, RefreshToken, RefreshToken.user_id, uids)),
        ("lti_user_links", lambda: _delete_by_user(db, LtiUserLink, LtiUserLink.user_id, uids)),
        ("lti_grade_syncs", lambda: _delete_by_user(db, LtiGradeSync, LtiGradeSync.user_id, uids)),
        (
            "profile_history",
            lambda: _delete_by_user(db, UserProfileHistory, UserProfileHistory.user_id, uids),
        ),
        ("foreign_notifications", lambda: _delete_foreign_notifications(db, people)),
        ("notifications", lambda: _delete_by_user(db, Notification, Notification.user_id, uids)),
        (
            "notification_preferences",
            lambda: _delete_by_user(
                db, UserNotificationPreference, UserNotificationPreference.user_id, uids
            ),
        ),
        (
            "column_preferences",
            lambda: _delete_by_user(
                db, UserColumnPreferences, UserColumnPreferences.user_id, uids
            ),
        ),
        (
            "custom_model_credentials",
            lambda: _delete_by_user(
                db, CustomModelCredential, CustomModelCredential.user_id, uids
            ),
        ),
        (
            "group_memberships",
            lambda: _delete_by_user(
                db, OrganizationGroupMembership, OrganizationGroupMembership.user_id, uids
            ),
        ),
        (
            "memberships",
            lambda: _update_by_user(
                db,
                OrganizationMembership,
                OrganizationMembership.user_id,
                uids,
                {"is_active": False},
                OrganizationMembership.is_active == True,  # noqa: E712
            ),
        ),
        (
            "share_links",
            lambda: _update_by_user(
                db,
                ProjectShareLink,
                ProjectShareLink.created_by,
                uids,
                {"revoked_at": now},
                ProjectShareLink.revoked_at.is_(None),
            ),
        ),
    ]
    removed: Dict[str, Dict[str, int]] = {uid: {} for uid in uids}
    for key, run in steps:
        counts = run()
        for uid in uids:
            removed[uid][key] = int(counts.get(uid, 0))

    _update(
        db, Invitation, {"pending_user_id": None}, Invitation.pending_user_id.in_(uids)
    )
    by_address = {p.address: p.user_id for p in people if p.address}
    invitations: Dict[str, int] = {}
    if by_address:
        addresses = sorted(by_address)
        same_address = func.lower(Invitation.email).in_(addresses)
        _update(
            db,
            Invitation,
            {"expires_at": now},
            same_address,
            Invitation.accepted == False,  # noqa: E712
            Invitation.expires_at > now,
        )
        placeholder = case(
            {address: new_email[uid] for address, uid in by_address.items()},
            value=func.lower(Invitation.email),
        )
        rows = db.execute(
            update(Invitation)
            .where(same_address)
            .values(email=placeholder)
            .returning(Invitation.email)
            .execution_options(synchronize_session=False)
        ).scalars()
        owner_of = {email: uid for uid, email in new_email.items()}
        for email in rows:
            uid = owner_of.get(email)
            if uid is not None:
                invitations[uid] = invitations.get(uid, 0) + 1
    for uid in uids:
        removed[uid]["invitations"] = invitations.get(uid, 0)

    for (outcome, user, check), handle, pseudonym in zip(eligible, handles, pseudonyms):
        uid = str(user.id)
        user.username = handle
        user.email = new_email[uid]
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
        outcome.result = AnonymizationResult(
            user_id=uid,
            anonymized_at=now,
            pseudonym=pseudonym,
            warnings=list(check.warnings),
            removed=removed[uid],
            kept=kept[uid],
        )
    db.flush()
    for uid in uids:
        logger.info(
            "Anonymized user %s (actor %s, reason %s)", uid, actor_id or "-", reason
        )


def anonymize_users_sync(
    db: Session,
    candidates: Iterable[tuple],
    *,
    actor_id: Optional[str],
    reason: str,
    scope: Optional[AnonymizationScope] = None,
) -> List[AnonymizationOutcome]:
    """Anonymize many accounts in the current transaction (flushes, never
    commits). ``candidates`` are ``(user_id, via_link_id)`` pairs; the
    outcomes come back in the same order.

    Set-based: the accounts are locked together (``FOR UPDATE`` in id order,
    so concurrent callers cannot deadlock), each is checked like in
    :func:`anonymize_user_sync`, and the eligible ones are scrubbed with one
    statement per table and one scan of the notifications, in passes of
    :data:`BATCH_SIZE`. An account named twice is handled in a later pass
    and then refused like a second single call would be.
    """
    outcomes = [
        AnonymizationOutcome(user_id=str(uid), via_link_id=link)
        for uid, link in candidates
    ]
    pending = list(range(len(outcomes)))
    while pending:
        seen: set = set()
        this_pass: List[int] = []
        later: List[int] = []
        for index in pending:
            uid = outcomes[index].user_id
            (later if uid in seen else this_pass).append(index)
            seen.add(uid)
        for start in range(0, len(this_pass), BATCH_SIZE):
            _anonymize_batch(
                db,
                [outcomes[i] for i in this_pass[start : start + BATCH_SIZE]],
                actor_id=actor_id,
                reason=reason,
                scope=scope,
            )
        pending = later
    return outcomes


async def anonymize_users(
    db: AsyncSession, candidates: Iterable[tuple], **kwargs: Any
) -> List[AnonymizationOutcome]:
    """Async twin of :func:`anonymize_users_sync` (same keyword arguments)."""
    pairs = list(candidates)
    return await db.run_sync(
        lambda session: anonymize_users_sync(session, pairs, **kwargs)
    )


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
    ``lti_admin``, ``registration_deleted``, ``superadmin``). The same code
    as :func:`anonymize_users_sync`, for one account.
    """
    (outcome,) = anonymize_users_sync(
        db,
        [(user_id, via_link_id)],
        actor_id=actor_id,
        reason=reason,
        scope=scope,
    )
    if outcome.not_found:
        raise AnonymizationUserNotFound(user_id)
    if outcome.blockers:
        raise AnonymizationRefused(outcome.blockers)
    return outcome.result


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
