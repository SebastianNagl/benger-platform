"""The daily stale-draft sweep (``wizard_drafts.purge_stale_wizard_drafts``).

A draft nobody changed for 30 days is discarded like "Discard draft": its
``deleted_at`` is stamped under the project row lock (so a state save or a
finish that got there first keeps it) and the batched purge is queued; a
discarded draft whose purge never finished gets it queued again. The worker's
beat task calls the same function.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update

from models import ProjectPurgeJob
from project_models import Project, ProjectWizardDraft
from tests.integration.test_group_visibility import _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)


async def _draft(db, creator, *, touched_days_ago, finished=False, deleted=False):
    project = Project(
        id=str(uuid.uuid4()), title="Entwurf", created_by=creator.id, is_private=True,
        is_wizard_draft=not finished,
        deleted_at=NOW - timedelta(days=1) if deleted else None,
    )
    db.add(project)
    await db.flush()
    db.add(ProjectWizardDraft(
        project_id=project.id, created_by=creator.id, client_key=str(uuid.uuid4()),
        touched_at=NOW - timedelta(days=touched_days_ago),
        finished_at=NOW - timedelta(days=40) if finished else None,
    ))
    await db.commit()
    return project


def _sender(fail=False):
    sent = []

    def send(job_id):
        if fail:
            raise ConnectionError("broker down")
        sent.append(job_id)
        return SimpleNamespace(id=f"celery-{job_id}")

    return sent, send


async def _sweep(db, send):
    from wizard_drafts import purge_stale_wizard_drafts

    return await db.run_sync(lambda s: purge_stale_wizard_drafts(s, send, now=NOW))


async def _deleted_at(db, project_id):
    return (
        await db.execute(select(Project.deleted_at).where(Project.id == project_id))
    ).scalar_one()


async def test_the_sweep_discards_only_stale_unfinished_drafts(async_test_db):
    db = async_test_db
    teacher = await _user(db)
    stale = await _draft(db, teacher, touched_days_ago=31)
    fresh = await _draft(db, teacher, touched_days_ago=29)
    finished = await _draft(db, teacher, touched_days_ago=90, finished=True)
    regular = Project(id=str(uuid.uuid4()), title="Normal", created_by=teacher.id, is_private=True)
    db.add(regular)
    await db.commit()
    stale, fresh, finished, regular = (
        SimpleNamespace(id=p.id) for p in (stale, fresh, finished, regular)
    )

    sent, send = _sender()
    result = await _sweep(db, send)
    assert stale.id in result["stamped"]
    assert fresh.id not in result["stamped"] and finished.id not in result["stamped"]
    assert stale.id in result["purge_queued"]
    assert await _deleted_at(db, stale.id) is not None
    for keep in (fresh, finished, regular):
        assert await _deleted_at(db, keep.id) is None
    job = (
        await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.project_id == stale.id))
    ).scalar_one()
    assert job.requested_by is None and job.status == "pending"
    assert job.id in sent

    # Run again: nothing new to stamp; the pending purge is sent once more
    # (the worker runs a job once, whatever the number of messages).
    sent2, send2 = _sender()
    again = await _sweep(db, send2)
    assert stale.id not in again["stamped"]
    assert sent2.count(job.id) == 1
    jobs = (
        await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.project_id == stale.id))
    ).scalars().all()
    assert len(jobs) == 1


async def test_a_save_that_wins_the_race_keeps_the_draft(async_test_db):
    """The sweep re-checks ``touched_at`` under the project lock: a draft
    saved after the candidate query is not stamped."""
    from wizard_drafts import stamp_stale_draft

    db = async_test_db
    teacher = await _user(db)
    draft = await _draft(db, teacher, touched_days_ago=31)
    pid = draft.id
    cutoff = NOW - timedelta(days=30)
    await db.execute(
        update(ProjectWizardDraft)
        .where(ProjectWizardDraft.project_id == pid)
        .values(touched_at=NOW)
    )
    await db.commit()
    assert await db.run_sync(lambda s: stamp_stale_draft(s, pid, cutoff)) is None
    await db.rollback()
    assert await _deleted_at(db, pid) is None


async def test_a_draft_that_lost_its_wizard_row_is_discarded(async_test_db):
    """Hard-deleting the creator cascades the ``project_wizard_drafts`` row
    away while the project stays a draft; such a draft can never be resumed
    or finished, so the next sweep stamps it and queues its purge, however
    recently it was touched."""
    db = async_test_db
    teacher = await _user(db)
    orphan = SimpleNamespace(id=(await _draft(db, teacher, touched_days_ago=1)).id)
    await db.execute(delete(ProjectWizardDraft).where(ProjectWizardDraft.project_id == orphan.id))
    await db.commit()

    sent, send = _sender()
    result = await _sweep(db, send)
    assert orphan.id in result["stamped"]
    assert orphan.id in result["purge_queued"]
    assert await _deleted_at(db, orphan.id) is not None
    job = (
        await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.project_id == orphan.id))
    ).scalar_one()
    assert job.status == "pending" and job.id in sent


async def test_a_discarded_draft_without_purge_is_queued_again(async_test_db):
    db = async_test_db
    teacher = await _user(db)
    stuck = SimpleNamespace(id=(await _draft(db, teacher, touched_days_ago=2, deleted=True)).id)
    _, failing = _sender(fail=True)
    result = await _sweep(db, failing)
    assert stuck.id not in result["purge_queued"]
    failed = (
        await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.project_id == stuck.id))
    ).scalar_one()
    assert failed.status == "failed"

    sent, send = _sender()
    result = await _sweep(db, send)
    assert stuck.id in result["purge_queued"]
    live = (
        await db.execute(
            select(ProjectPurgeJob).where(
                ProjectPurgeJob.project_id == stuck.id, ProjectPurgeJob.status == "pending"
            )
        )
    ).scalar_one()
    assert sent == [live.id]


async def test_the_purge_removes_the_draft_row(async_test_db):
    from project_purge import run_project_purge_job

    db = async_test_db
    teacher = await _user(db)
    stale = SimpleNamespace(id=(await _draft(db, teacher, touched_days_ago=31)).id)
    sent, send = _sender()
    await _sweep(db, send)
    result = await db.run_sync(lambda s: run_project_purge_job(s, sent[0]))
    assert result["status"] == "completed"
    assert await db.get(ProjectWizardDraft, stale.id) is None
    assert (
        await db.execute(select(Project.id).where(Project.id == stale.id))
    ).first() is None


def test_retention_is_thirty_days():
    from wizard_drafts import WIZARD_DRAFT_RETENTION, draft_expires_at

    assert WIZARD_DRAFT_RETENTION == timedelta(days=30)
    assert draft_expires_at(NOW) == NOW + timedelta(days=30)
    assert draft_expires_at(None) is None
