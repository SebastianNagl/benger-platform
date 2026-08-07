"""Shape tests for migration 090: exam projects get unlimited annotations.

Data-only migration: exam-kind projects with the crowd-labeling default cap
(``maximum_annotations = 1``) are backfilled to 0 (unlimited) so every
participant of a shared/org/LTI exam can submit. Non-exam projects and
deliberately customized caps (values other than 1) are untouched.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "090_exam_unlimited_annotations.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_090", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _mk_user(db):
    from models import User

    user = User(
        id=str(uuid.uuid4()),
        username=f"mig090-{uuid.uuid4().hex[:8]}",
        email=f"mig090-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 090",
    )
    db.add(user)
    db.flush()
    return user


def _mk_project(db, *, kind, cap, owner_id):
    from project_models import Project

    project = Project(
        id=str(uuid.uuid4()),
        title=f"mig090-{kind}-{cap}",
        created_by=owner_id,
        kind=kind,
        maximum_annotations=cap,
    )
    db.add(project)
    db.flush()
    return project


class TestMigration090Shape:
    def test_revision_chains_after_089(self):
        mig = _load_migration()
        assert mig.revision == "090_exam_unlimited_annotations"
        assert mig.down_revision == "089_add_lti_lms_family"

    def test_backfill_targets_only_default_capped_exams(self, test_db: Session):
        owner = _mk_user(test_db)
        capped_exam = _mk_project(test_db, kind="exam", cap=1, owner_id=owner.id)
        custom_exam = _mk_project(test_db, kind="exam", cap=3, owner_id=owner.id)
        research = _mk_project(test_db, kind="research", cap=1, owner_id=owner.id)

        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Idempotent — second run is a no-op.
            mig.upgrade()

        for p in (capped_exam, custom_exam, research):
            test_db.refresh(p)
        assert capped_exam.maximum_annotations == 0
        assert custom_exam.maximum_annotations == 3  # explicit cap respected
        assert research.maximum_annotations == 1  # non-exam untouched
