"""``project_listable()``: the predicate of every project list and count
(not deleted and not a creation-wizard draft), next to its instance twin
``project_is_wizard_draft``. The per-project deciders keep
``project_not_deleted`` so a creator still opens their own draft.

Oracle: the documented rule (migration 141) "alive and not a draft". The
tests reject a predicate that lets a draft or a deleted project through, and
one that hides a live project or (for ``project_not_deleted``) a draft.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from project_models import (
    Project,
    project_is_wizard_draft,
    project_listable,
    project_not_deleted,
)


def _seed(db: Session):
    suffix = uuid.uuid4().hex[:8]
    owner = User(
        id=str(uuid.uuid4()), username=f"listable-{suffix}",
        email=f"listable-{suffix}@example.com", hashed_password="x", name="Owner",
    )
    db.add(owner)
    db.flush()
    rows = {
        "live": Project(id=str(uuid.uuid4()), title="live", created_by=owner.id),
        "deleted": Project(
            id=str(uuid.uuid4()), title="deleted", created_by=owner.id,
            deleted_at=datetime.now(timezone.utc),
        ),
        "draft": Project(
            id=str(uuid.uuid4()), title="draft", created_by=owner.id,
            is_private=True, is_wizard_draft=True,
        ),
        "deleted_draft": Project(
            id=str(uuid.uuid4()), title="deleted draft", created_by=owner.id,
            is_private=True, is_wizard_draft=True,
            deleted_at=datetime.now(timezone.utc),
        ),
    }
    db.add_all(rows.values())
    db.flush()
    return {name: p.id for name, p in rows.items()}


def _select(db: Session, ids, clause):
    found = db.execute(
        select(Project.id).where(Project.id.in_(list(ids.values())), clause)
    ).scalars().all()
    by_id = {v: k for k, v in ids.items()}
    return {by_id[i] for i in found}


def test_listable_keeps_only_live_non_draft_projects(test_db: Session):
    ids = _seed(test_db)
    assert _select(test_db, ids, project_listable()) == {"live"}


def test_not_deleted_keeps_drafts(test_db: Session):
    ids = _seed(test_db)
    assert _select(test_db, ids, project_not_deleted()) == {"live", "draft"}


def test_instance_twin():
    assert project_is_wizard_draft(SimpleNamespace(is_wizard_draft=True)) is True
    assert project_is_wizard_draft(SimpleNamespace(is_wizard_draft=False)) is False
    assert project_is_wizard_draft(SimpleNamespace()) is False
