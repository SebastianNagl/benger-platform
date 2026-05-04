"""Tests for migration 038: backfill orphan Korrektur Falllösung runs.

Sets up a scenario that mirrors the pre-038 production state — multiple
per-submission EvaluationRun rows with `model_id='human:<uid>'` plus their
TaskEvaluation rows — and verifies that running the migration body
collapses everything into a single singleton run with grader identity
preserved on the new `created_by` column.
"""

from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import EvaluationRun, TaskEvaluation, User
from project_models import Project, Task


MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "038_korrektur_backfill_orphan_human_runs.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_038", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture
def admin_user(test_db: Session) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username="m038-admin@test.com",
        email="m038-admin@test.com",
        name="Migration 038 Admin",
        hashed_password="x",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.flush()
    return user


@pytest.fixture
def grader_users(test_db: Session) -> list[User]:
    users = []
    for i in range(2):
        u = User(
            id=str(uuid.uuid4()),
            username=f"m038-grader{i}@test.com",
            email=f"m038-grader{i}@test.com",
            name=f"Grader {i}",
            hashed_password="x",
            is_active=True,
            email_verified=True,
        )
        test_db.add(u)
        users.append(u)
    test_db.flush()
    return users


@pytest.fixture
def project(test_db: Session, admin_user: User) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"m038-{uuid.uuid4().hex[:6]}",
        created_by=admin_user.id,
        label_config="<View></View>",
    )
    test_db.add(p)
    test_db.flush()
    return p


@pytest.fixture
def task(test_db: Session, project: Project, admin_user: User) -> Task:
    t = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "x"},
        inner_id=1,
        created_by=admin_user.id,
    )
    test_db.add(t)
    test_db.flush()
    return t


def _seed_orphan_run_with_eval(
    db: Session, project: Project, task: Task, grader: User, score: float
) -> tuple[str, str]:
    """Create one orphan per-submission EvaluationRun + its TaskEvaluation row.

    Mirrors the legacy submit_falloesung_grade write path. Returns
    (run_id, task_eval_id).
    """
    run_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO evaluation_runs
              (id, project_id, model_id, evaluation_type_ids, metrics,
               eval_metadata, status, samples_evaluated, has_sample_results,
               created_by, created_at)
            VALUES
              (:id, :pid, :mid,
               '["korrektur_falloesung"]'::json,
               '{}'::json,
               '{"evaluation_type": "korrektur_falloesung"}'::json,
               'completed', 1, true, :uid, now())
            """
        ),
        {
            "id": run_id,
            "pid": project.id,
            "mid": f"human:{grader.id}",
            "uid": grader.id,
        },
    )
    eval_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO task_evaluations
              (id, evaluation_id, task_id, field_name, answer_type,
               ground_truth, prediction, metrics, passed, judge_prompts_used,
               created_at)
            VALUES
              (:id, :rid, :tid, 'loesung', 'long_text',
               '""'::json, '""'::json,
               (:metrics)::json, :passed,
               (:jpu)::json, now())
            """
        ),
        {
            "id": eval_id,
            "rid": run_id,
            "tid": task.id,
            "metrics": f'{{"korrektur_falloesung": {score}}}',
            "passed": score >= 50,
            "jpu": f'{{"grader_user_id": "{grader.id}", "source": "human"}}',
        },
    )
    db.flush()
    return run_id, eval_id


def _count_human_runs(db: Session, project_id: str, like: str = "human") -> int:
    if like == "human":
        return db.query(EvaluationRun).filter(
            EvaluationRun.project_id == project_id,
            EvaluationRun.model_id == "human",
        ).count()
    # 'human:%'
    return (
        db.execute(
            text(
                "SELECT COUNT(*) FROM evaluation_runs "
                "WHERE project_id = :pid AND model_id LIKE 'human:%'"
            ),
            {"pid": project_id},
        ).scalar()
        or 0
    )


class TestMigration038Backfill:
    def test_collapses_orphans_into_singleton(
        self, test_db: Session, project: Project, task: Task, grader_users: list[User]
    ):
        # Seed 3 orphan runs from 2 graders.
        run1, eval1 = _seed_orphan_run_with_eval(test_db, project, task, grader_users[0], 80.0)
        run2, eval2 = _seed_orphan_run_with_eval(test_db, project, task, grader_users[1], 60.0)
        run3, eval3 = _seed_orphan_run_with_eval(test_db, project, task, grader_users[0], 75.0)
        test_db.commit()

        assert _count_human_runs(test_db, project.id, like="human") == 0
        assert _count_human_runs(test_db, project.id, like="human:%") == 3

        mig = _load_migration()

        # Patch op.get_bind() to use our test connection.
        from alembic import op as _op

        original_get_bind = _op.get_bind
        _op.get_bind = lambda: test_db.get_bind()  # type: ignore[assignment]
        try:
            mig.upgrade()
        finally:
            _op.get_bind = original_get_bind  # type: ignore[assignment]

        # All three orphans collapsed into one singleton.
        assert _count_human_runs(test_db, project.id, like="human") == 1
        assert _count_human_runs(test_db, project.id, like="human:%") == 0

        # All three TaskEvaluation rows preserved + repointed at the singleton.
        singleton_id = (
            test_db.query(EvaluationRun.id)
            .filter(
                EvaluationRun.project_id == project.id,
                EvaluationRun.model_id == "human",
            )
            .scalar()
        )
        evals = (
            test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == singleton_id)
            .all()
        )
        assert len(evals) == 3

        # created_by populated from legacy judge_prompts_used.grader_user_id.
        graders_seen = {e.created_by for e in evals}
        expected = {grader_users[0].id, grader_users[1].id}
        assert graders_seen == expected

    def test_idempotent_on_repeat(
        self, test_db: Session, project: Project, task: Task, grader_users: list[User]
    ):
        _seed_orphan_run_with_eval(test_db, project, task, grader_users[0], 70.0)
        test_db.commit()

        mig = _load_migration()
        from alembic import op as _op

        original_get_bind = _op.get_bind
        _op.get_bind = lambda: test_db.get_bind()  # type: ignore[assignment]
        try:
            mig.upgrade()
            # Snapshot row counts after first run.
            human_runs_after_first = _count_human_runs(test_db, project.id, like="human")
            evals_after_first = (
                test_db.query(TaskEvaluation)
                .filter(TaskEvaluation.evaluation_id.isnot(None))
                .count()
            )

            # Second run — should be a no-op.
            mig.upgrade()
        finally:
            _op.get_bind = original_get_bind  # type: ignore[assignment]

        assert _count_human_runs(test_db, project.id, like="human") == human_runs_after_first
        assert (
            test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id.isnot(None))
            .count()
            == evals_after_first
        )

    def test_no_orphans_no_op(self, test_db: Session, project: Project):
        """Migration on a clean project must not create a singleton uselessly."""
        mig = _load_migration()
        from alembic import op as _op

        original_get_bind = _op.get_bind
        _op.get_bind = lambda: test_db.get_bind()  # type: ignore[assignment]
        try:
            mig.upgrade()
        finally:
            _op.get_bind = original_get_bind  # type: ignore[assignment]

        # No singleton should have been created — nothing to collapse.
        assert _count_human_runs(test_db, project.id, like="human") == 0
