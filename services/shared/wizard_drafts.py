"""Creation-wizard drafts: retention and the stale-draft sweep (CORE 2.55).

A wizard draft is a real project the creation wizard makes when the teacher
leaves its first step (``projects.is_wizard_draft``, its wizard side in
``project_wizard_drafts``; routes in ``routers/projects/wizard_drafts.py``).
A draft nobody touched for :data:`WIZARD_DRAFT_RETENTION` is discarded the way
the wizard's "Discard draft" does it: ``deleted_at`` is stamped, then the
batched purge of ``project_purge`` is queued.

Lives in /shared so the API (expiry dates of the draft list) and the worker
(the daily beat task ``tasks.purge_stale_wizard_drafts``) use one definition.
No fastapi imports (worker container constraint).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from project_models import Project, ProjectWizardDraft

logger = logging.getLogger(__name__)

#: A draft is discarded this long after its last change (owner default
#: 2026-11-17: teachers prepare an exam over days or weeks with gaps; the
#: wizard's draft list shows the date).
WIZARD_DRAFT_RETENTION = timedelta(days=30)

#: Upper bound of the serialized wizard state (``PUT .../wizard-draft``).
WIZARD_DRAFT_STATE_MAX_BYTES = 2 * 1024 * 1024


_REFUSALS = {
    "visibility": "The visibility of a wizard draft is set when the wizard finishes",
    "share": "A wizard draft cannot be shared before the wizard finishes",
}


def wizard_draft_refusal(action: str) -> Dict[str, str]:
    """The 409 body (code ``wizard_draft``) of a route that refuses to act on
    a creation-wizard draft before its finish (``action``: ``visibility`` or
    ``share``)."""
    return {"code": "wizard_draft", "message": _REFUSALS[action]}


def draft_expires_at(touched_at: Optional[datetime]) -> Optional[datetime]:
    """When the sweep discards a draft last changed at ``touched_at``."""
    if touched_at is None:
        return None
    return touched_at + WIZARD_DRAFT_RETENTION


def _build_select_stale_draft_ids(cutoff: datetime):
    """Candidates of the sweep: live, unfinished drafts last changed before
    ``cutoff``. Re-checked under the project row lock before the stamp."""
    return (
        select(Project.id)
        .join(ProjectWizardDraft, ProjectWizardDraft.project_id == Project.id)
        .where(
            Project.is_wizard_draft.is_(True),
            Project.deleted_at.is_(None),
            ProjectWizardDraft.finished_at.is_(None),
            ProjectWizardDraft.touched_at < cutoff,
        )
        .order_by(Project.id)
    )


def _build_select_discarded_draft_ids():
    """Drafts already stamped deleted whose project row still exists, i.e.
    whose purge has not finished (a lost message, a failed job, a queue that
    was down when the draft was discarded)."""
    return (
        select(Project.id)
        .where(Project.is_wizard_draft.is_(True), Project.deleted_at.is_not(None))
        .order_by(Project.id)
    )


def stamp_stale_draft(db: Session, project_id: str, cutoff: datetime) -> Optional[Project]:
    """Stamp ``deleted_at`` on the draft ``project_id`` if it is still a live,
    stale draft, judged under the project row lock. The state save and the
    finish route lock the same row first, so whichever commits first wins: a
    save or a finish that got there before keeps the draft. Does not commit."""
    project = db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalar_one_or_none()
    if project is None or not project.is_wizard_draft or project.deleted_at is not None:
        return None
    draft = db.execute(
        select(ProjectWizardDraft).where(ProjectWizardDraft.project_id == project_id)
    ).scalar_one_or_none()
    if draft is None or draft.finished_at is not None or draft.touched_at >= cutoff:
        return None
    project.deleted_at = datetime.now(timezone.utc)
    project.deleted_by = None
    return project


def purge_stale_wizard_drafts(
    db: Session,
    send: Callable[[str], object],
    *,
    now: Optional[datetime] = None,
    retention: timedelta = WIZARD_DRAFT_RETENTION,
) -> Dict[str, List[str]]:
    """Discard every draft untouched for ``retention`` and queue its purge;
    queue the purge again for discarded drafts whose purge never finished.

    ``send(job_id)`` publishes ``tasks.purge_project`` (see
    ``project_purge.enqueue_purge_job_sync``). Commits per draft. Returns the
    ids it stamped and the ids it queued a purge for.
    """
    from project_purge import PurgeQueueUnavailable, enqueue_purge_job_sync

    now = now or datetime.now(timezone.utc)
    cutoff = now - retention
    stamped: List[str] = []
    for project_id in db.execute(_build_select_stale_draft_ids(cutoff)).scalars().all():
        project = stamp_stale_draft(db, project_id, cutoff)
        if project is None:
            db.rollback()
            continue
        db.commit()
        stamped.append(project_id)
        logger.info("wizard draft %s untouched since before %s: discarded", project_id, cutoff)

    queued: List[str] = []
    for project_id in db.execute(_build_select_discarded_draft_ids()).scalars().all():
        project = db.get(Project, project_id)
        if project is None:
            continue
        try:
            enqueue_purge_job_sync(db, project, None, send)
        except PurgeQueueUnavailable:
            logger.warning("purge queue unavailable for wizard draft %s; next sweep retries", project_id)
            continue
        queued.append(project_id)
    return {"stamped": stamped, "purge_queued": queued}
