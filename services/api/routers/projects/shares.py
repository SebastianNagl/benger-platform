"""Per-project password sharing for student exams (issue #35).

An owner mints a password-protected share link; an invitee (who must already
have a BenGER account) joins by entering the password, which records a
``ProjectShareMember`` and captures GDPR consent. The owner sees an invitee
roster ranked by score; the cohort leaderboard ranks the same members.

Two routers:
- ``router`` — project-scoped owner operations, mounted under ``/api/projects``.
- ``token_router`` — invitee operations keyed by the opaque share token,
  mounted at ``/api/shares`` in ``main.py``.

Security notes:
- Passwords are bcrypt-hashed via ``auth_module.user_service.get_password_hash``
  (never md5 — the prod Postgres runs FIPS OpenSSL where md5 raises).
- The full token / password are never logged.
- ``expires_at`` / ``max_uses`` / ``revoked_at`` gate JOIN only; ongoing access
  is governed by membership existence (owner eviction removes the row).
- ``max_uses`` is enforced transactionally (``SELECT ... FOR UPDATE`` on the
  link) so concurrent joins can't overshoot the cap.
- Rate-limiting / brute-force lockout on join is a deliberate v1 follow-up
  (tracked in the issue), not implemented here.
"""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.user_service import get_password_hash, verify_password
from database import get_async_db
from models import User
from project_models import (
    Annotation,
    Project,
    ProjectShareLink,
    ProjectShareMember,
    Task,
)
from models import TaskEvaluation

from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import attempt_score_from_metrics, get_share_access_async

router = APIRouter()
token_router = APIRouter(prefix="/api/shares", tags=["shares"])

# Bump when the consent copy materially changes so withdrawals/re-consents are
# auditable. Kept here (not the DB) because it tracks the wording, not data.
CONSENT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #
class ShareCreate(BaseModel):
    password: str = Field(min_length=4, max_length=128)
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(None, ge=1)
    # Opt-in: surface this share in the global discovery directory.
    is_listed: bool = False


class ShareUpdate(BaseModel):
    # All optional — rotate the password and/or adjust the lifecycle.
    password: Optional[str] = Field(None, min_length=4, max_length=128)
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(None, ge=1)
    is_listed: Optional[bool] = None


class ShareJoin(BaseModel):
    password: str = Field(max_length=128)
    gdpr_consent: bool = Field(
        description="Must be true: consent to share identifiable performance "
        "data with the exam owner and cohort."
    )


def _share_public_dict(link: ProjectShareLink) -> dict:
    """Owner-facing link representation (includes the token for copy-link)."""
    return {
        "id": link.id,
        "token": link.token,
        "project_id": link.project_id,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "max_uses": link.max_uses,
        "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
        "is_listed": link.is_listed,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


async def _compute_member_scores(
    db: AsyncSession, project_id: str, user_ids: list[str]
) -> dict[str, dict]:
    """Best/last score per member, computed from ``task_evaluations``.

    Scores live canonically in ``task_evaluations`` (never denormalized onto
    the membership row — that drifts on re-grades). A member's attempt score
    is the unified 0..1 ``value`` of the evaluation attached to their
    annotation on this project's tasks, extracted from the nested-canonical
    ``metrics`` shape ``{"<metric_key>": {"value": ...}}`` via
    :func:`attempt_score_from_metrics` (metric writers never produce a
    top-level ``value``; reading one here silently zeroed every roster).
    ``best`` = max across attempts, ``last`` = the most recent. Returns
    ``{user_id: {"best": float|None, "last": float|None, "attempts": int}}``.
    """
    if not user_ids:
        return {}

    stmt = (
        select(
            Annotation.completed_by.label("user_id"),
            Annotation.id.label("annotation_id"),
            TaskEvaluation.metrics.label("metrics"),
            TaskEvaluation.id.label("eval_id"),
            Annotation.created_at.label("attempted_at"),
        )
        .select_from(TaskEvaluation)
        .join(Annotation, Annotation.id == TaskEvaluation.annotation_id)
        .join(Task, Task.id == TaskEvaluation.task_id)
        .where(
            Task.project_id == project_id,
            Annotation.completed_by.in_(user_ids),
        )
        # Secondary key makes "last" deterministic when one annotation
        # carries several evaluation rows (e.g. AI judge + human Korrektur).
        .order_by(Annotation.created_at.asc(), TaskEvaluation.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    out: dict[str, dict] = {uid: {"best": None, "last": None, "attempts": 0} for uid in user_ids}
    scored_annotations: set[str] = set()
    for r in rows:
        score = attempt_score_from_metrics(r.metrics)
        if score is None:
            continue
        agg = out.setdefault(r.user_id, {"best": None, "last": None, "attempts": 0})
        # An attempt = a distinct scored annotation; one annotation may carry
        # several evaluation rows (AI judge + human Korrektur) but is still
        # one attempt.
        if r.annotation_id not in scored_annotations:
            scored_annotations.add(r.annotation_id)
            agg["attempts"] += 1
        agg["last"] = score  # rows are ascending by time -> last wins
        agg["best"] = score if agg["best"] is None else max(agg["best"], score)
    return out


def _display_name(user: User) -> str:
    """Pseudonym-aware display name (privacy-first; honors use_pseudonym)."""
    if getattr(user, "use_pseudonym", True) and getattr(user, "pseudonym", None):
        return user.pseudonym
    return user.name or user.username


# --------------------------------------------------------------------------- #
# Owner operations (project-scoped, /api/projects/{id}/shares...)
# --------------------------------------------------------------------------- #
@router.post("/{project_id}/shares", status_code=201)
async def create_share(
    project_id: str,
    body: ShareCreate,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Mint a password-protected share link for the project (owner/editor)."""
    link = ProjectShareLink(
        id=str(uuid.uuid4()),
        token=secrets.token_urlsafe(32),
        project_id=project_id,
        created_by=str(current_user.id),
        password_hash=get_password_hash(body.password),
        expires_at=body.expires_at,
        max_uses=body.max_uses,
        is_listed=body.is_listed,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _share_public_dict(link)


@router.get("/{project_id}/shares")
async def list_shares(
    project_id: str,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """List the project's share links (owner/editor)."""
    rows = (
        await db.execute(
            select(ProjectShareLink)
            .where(ProjectShareLink.project_id == project_id)
            .order_by(ProjectShareLink.created_at.desc())
        )
    ).scalars().all()
    return [_share_public_dict(link) for link in rows]


async def _load_owned_link(
    db: AsyncSession, project_id: str, share_id: str
) -> ProjectShareLink:
    link = (
        await db.execute(
            select(ProjectShareLink).where(
                ProjectShareLink.id == share_id,
                ProjectShareLink.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    return link


@router.put("/{project_id}/shares/{share_id}")
async def update_share(
    project_id: str,
    share_id: str,
    body: ShareUpdate,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Rotate the password and/or adjust expiry / max_uses (owner/editor)."""
    link = await _load_owned_link(db, project_id, share_id)
    if body.password is not None:
        link.password_hash = get_password_hash(body.password)
    if body.expires_at is not None:
        link.expires_at = body.expires_at
    if body.max_uses is not None:
        link.max_uses = body.max_uses
    if body.is_listed is not None:
        link.is_listed = body.is_listed
    await db.commit()
    await db.refresh(link)
    return _share_public_dict(link)


@router.delete("/{project_id}/shares/{share_id}", status_code=204)
async def revoke_share(
    project_id: str,
    share_id: str,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke a link (blocks future joins; existing members keep access until
    explicitly evicted)."""
    link = await _load_owned_link(db, project_id, share_id)
    if link.revoked_at is None:
        link.revoked_at = datetime.now(timezone.utc)
        await db.commit()


@router.get("/{project_id}/shares/roster")
async def get_roster(
    project_id: str,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Invitee roster with attempts + best/last score (owner/editor).

    Only consented members appear (GDPR). Names are pseudonym-aware.
    """
    members = (
        await db.execute(
            select(ProjectShareMember, User)
            .join(User, User.id == ProjectShareMember.user_id)
            .where(
                ProjectShareMember.project_id == project_id,
                ProjectShareMember.gdpr_consent_at.isnot(None),
            )
        )
    ).all()
    user_ids = [m.ProjectShareMember.user_id for m in members]
    scores = await _compute_member_scores(db, project_id, user_ids)
    out = []
    for row in members:
        member, user = row.ProjectShareMember, row.User
        s = scores.get(member.user_id, {})
        out.append(
            {
                "user_id": member.user_id,
                "display_name": _display_name(user),
                # Computed from task_evaluations like best/last — the
                # ProjectShareMember.attempts column has no writer and is
                # permanently 0 (kept only for API/schema stability).
                "attempts": s.get("attempts", 0),
                "best_score": s.get("best"),
                "last_score": s.get("last"),
                "joined_at": member.created_at.isoformat() if member.created_at else None,
            }
        )
    return out


@router.delete("/{project_id}/shares/roster/{user_id}", status_code=204)
async def evict_member(
    project_id: str,
    user_id: str,
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Evict a member — removes ongoing participant access (owner/editor)."""
    member = (
        await db.execute(
            select(ProjectShareMember).where(
                ProjectShareMember.project_id == project_id,
                ProjectShareMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member:
        await db.delete(member)
        await db.commit()


@router.get("/{project_id}/cohort-leaderboard")
async def cohort_leaderboard(
    project_id: str,
    request: Request,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Rank the shared exam's consented invitees by best (then last) score.

    A per-exam *cohort* view — NOT a global human ranking. Visible to the owner
    and to any member of the cohort (so students see where they stand). Honors
    pseudonyms and the consent gate.
    """
    # Access: project owner/editor OR a consented share member.
    from routers.projects.helpers import (
        check_project_accessible_async,
        get_org_context_from_request,
    )

    org_context = get_org_context_from_request(request)
    is_owner = await check_project_accessible_async(
        db, current_user, project_id, org_context
    )
    if not is_owner and not await get_share_access_async(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    members = (
        await db.execute(
            select(ProjectShareMember, User)
            .join(User, User.id == ProjectShareMember.user_id)
            .where(
                ProjectShareMember.project_id == project_id,
                ProjectShareMember.gdpr_consent_at.isnot(None),
            )
        )
    ).all()
    user_ids = [m.ProjectShareMember.user_id for m in members]
    scores = await _compute_member_scores(db, project_id, user_ids)
    by_user = {row.User.id: row.User for row in members}

    ranked = []
    for uid in user_ids:
        s = scores.get(uid, {})
        ranked.append(
            {
                "user_id": uid,
                "display_name": _display_name(by_user[uid]),
                "best_score": s.get("best"),
                "last_score": s.get("last"),
                "attempts": s.get("attempts", 0),
            }
        )
    # Rank by best score desc, then last score desc; unscored members last.
    ranked.sort(
        key=lambda r: (
            r["best_score"] is not None,
            r["best_score"] or 0,
            r["last_score"] or 0,
        ),
        reverse=True,
    )
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return ranked


# --------------------------------------------------------------------------- #
# Invitee operations (token-scoped, /api/shares/{token}...)
# --------------------------------------------------------------------------- #

# Student-generated project kinds that may be discovered + joined.
STUDENT_SHARE_KINDS = ("exam", "flashcard_collection", "flashcard_deck")


# NOTE: declared BEFORE the "/{token}" route so a request to /api/shares/discover
# matches this literal route rather than being captured as token="discover".
@token_router.get("/discover")
async def discover_shares(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Browse student exams/decks whose owners opted to list them (issue #35).

    Global directory: any logged-in student sees every listed, still-joinable
    student share except their own. Browsing reveals only title + owner name; a
    password is still required to JOIN (via POST /shares/{token}/join).
    Revoked/expired links are filtered out here; the rare max_uses-exhausted
    case is left to the join endpoint's 410.
    """
    now = datetime.now(timezone.utc)
    uid = str(current_user.id)

    rows = (
        await db.execute(
            select(ProjectShareLink, Project, User)
            .join(Project, Project.id == ProjectShareLink.project_id)
            .join(User, User.id == Project.created_by)
            .where(
                ProjectShareLink.is_listed.is_(True),
                ProjectShareLink.revoked_at.is_(None),
                or_(
                    ProjectShareLink.expires_at.is_(None),
                    ProjectShareLink.expires_at > now,
                ),
                Project.origin == "student",
                Project.kind.in_(STUDENT_SHARE_KINDS),
                Project.created_by != uid,
            )
            .order_by(ProjectShareLink.created_at.desc())
        )
    ).all()

    # One query for the caller's consented memberships -> mark already-joined.
    member_pids = set(
        (
            await db.execute(
                select(ProjectShareMember.project_id).where(
                    ProjectShareMember.user_id == uid,
                    ProjectShareMember.gdpr_consent_at.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )

    # One entry per project (newest listed link wins) so a project with several
    # listed links isn't shown multiple times.
    seen = set()
    out = []
    for link, project, owner in rows:
        if project.id in seen:
            continue
        seen.add(project.id)
        out.append(
            {
                "token": link.token,
                "project_id": project.id,
                "title": project.title,
                "kind": project.kind,
                "owner_name": _display_name(owner) if owner else None,
                "already_member": project.id in member_pids,
            }
        )
    return out


async def _load_link_by_token(db: AsyncSession, token: str) -> ProjectShareLink:
    link = (
        await db.execute(
            select(ProjectShareLink).where(ProjectShareLink.token == token)
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    return link


@token_router.get("/{token}")
async def get_share_info(
    token: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Minimal pre-join info for the join page: exam title + owner name.

    Reveals nothing sensitive (no roster, no Musterlösung) to a token holder
    who has not yet entered the password.
    """
    link = await _load_link_by_token(db, token)
    project = (
        await db.execute(select(Project).where(Project.id == link.project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    owner = (
        await db.execute(select(User).where(User.id == project.created_by))
    ).scalar_one_or_none()
    already_member = await get_share_access_async(db, current_user, link.project_id)
    return {
        "project_id": link.project_id,
        "title": project.title,
        # kind lets the join page route to the exam vs deck surface afterwards.
        "kind": project.kind,
        "owner_name": _display_name(owner) if owner else None,
        "revoked": link.revoked_at is not None,
        "already_member": already_member is not None,
        "consent_version": CONSENT_VERSION,
    }


@token_router.post("/{token}/join")
async def join_share(
    token: str,
    body: ShareJoin,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Join a shared exam by password, capturing GDPR consent.

    Enforces revoked/expired/max_uses gates transactionally. NOTE: brute-force
    lockout / rate-limiting on this endpoint is a tracked v1 follow-up.
    """
    if not body.gdpr_consent:
        raise HTTPException(
            status_code=400,
            detail="Consent is required to join a shared exam.",
        )

    # Lock the link row so a concurrent join can't overshoot max_uses.
    link = (
        await db.execute(
            select(ProjectShareLink)
            .where(ProjectShareLink.token == token)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")

    now = datetime.now(timezone.utc)
    if link.revoked_at is not None:
        raise HTTPException(status_code=410, detail="This share link has been revoked.")
    if link.expires_at is not None and link.expires_at <= now:
        raise HTTPException(status_code=410, detail="This share link has expired.")

    if not verify_password(body.password, link.password_hash):
        raise HTTPException(status_code=403, detail="Incorrect password.")

    # Idempotent: re-joining is a no-op that just refreshes consent.
    existing = (
        await db.execute(
            select(ProjectShareMember).where(
                ProjectShareMember.share_link_id == link.id,
                ProjectShareMember.user_id == str(current_user.id),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.gdpr_consent_at = now
        existing.consent_version = CONSENT_VERSION
        await db.commit()
        return {"project_id": link.project_id, "status": "already_member"}

    if link.max_uses is not None:
        used = (
            await db.execute(
                select(func.count(ProjectShareMember.id)).where(
                    ProjectShareMember.share_link_id == link.id
                )
            )
        ).scalar_one()
        if used >= link.max_uses:
            raise HTTPException(
                status_code=410, detail="This share link has reached its usage limit."
            )

    member = ProjectShareMember(
        id=str(uuid.uuid4()),
        share_link_id=link.id,
        project_id=link.project_id,
        user_id=str(current_user.id),
        attempts=0,
        gdpr_consent_at=now,
        consent_version=CONSENT_VERSION,
    )
    db.add(member)
    await db.commit()
    return {"project_id": link.project_id, "status": "joined"}


@token_router.delete("/{token}/membership", status_code=204)
async def withdraw_membership(
    token: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Self-service withdrawal (GDPR Art. 7(3)) — leave the cohort.

    Withdrawal must be as easy as consent: this deletes the caller's own
    membership row, removing them from the roster/leaderboard and revoking
    their participant access.
    """
    link = await _load_link_by_token(db, token)
    member = (
        await db.execute(
            select(ProjectShareMember).where(
                ProjectShareMember.share_link_id == link.id,
                ProjectShareMember.user_id == str(current_user.id),
            )
        )
    ).scalar_one_or_none()
    if member:
        await db.delete(member)
        await db.commit()
