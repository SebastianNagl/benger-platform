"""Tests for services.evaluation.human_eval_runs.

The helper is the only safe path for creating the singleton EvaluationRun
that human-graded metrics like korrektur_falloesung write into. Tests
cover: idempotency (same row on repeated calls), the metric whitelist,
and that the partial unique index in migration 037 actually rejects a
duplicate human-korrektur run inserted bypassing the helper.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import EvaluationRun, User
from project_models import Project
from services.evaluation.human_eval_runs import (
    HUMAN_GRADED_METRICS,
    get_or_create_human_eval_run,
    is_human_graded_metric,
)


def _make_project(db: Session, admin: User) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=f"human-eval-test-{uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config="<View></View>",
    )
    db.add(project)
    db.flush()
    return project


@pytest.fixture(scope="function")
def admin_user(test_db: Session) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username="helper-admin@test.com",
        email="helper-admin@test.com",
        name="Helper Admin",
        hashed_password="x",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.flush()
    return user


class TestIsHumanGradedMetric:
    def test_korrektur_falloesung_is_human(self):
        assert is_human_graded_metric("korrektur_falloesung")

    def test_llm_judge_is_not_human(self):
        assert not is_human_graded_metric("llm_judge_falloesung")

    def test_unknown_metric_is_not_human(self):
        assert not is_human_graded_metric("not_a_real_metric")


class TestGetOrCreateHumanEvalRun:
    def test_first_call_creates_singleton(self, test_db: Session, admin_user: User):
        project = _make_project(test_db, admin_user)

        run = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()

        assert run.id != None  # noqa: E711
        assert run.project_id == project.id
        assert run.model_id == "human"
        assert run.evaluation_type_ids == ["korrektur_falloesung"]
        assert run.eval_metadata.get("evaluation_type") == "korrektur_falloesung"
        # The synthetic evaluation_configs entry is what makes the singleton
        # appear in the active-metric dropdown (EvaluationResults.tsx:204).
        configs = run.eval_metadata.get("evaluation_configs") or []
        assert any(c.get("metric") == "korrektur_falloesung" for c in configs)
        assert run.status == "completed"
        assert run.created_by == admin_user.id

    def test_second_call_returns_same_row(self, test_db: Session, admin_user: User):
        project = _make_project(test_db, admin_user)

        run1 = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()
        run2 = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()

        assert run1.id == run2.id

        # And only one row exists.
        count = (
            test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project.id)
            .filter(EvaluationRun.model_id == "human")
            .count()
        )
        assert count == 1

    def test_different_projects_get_different_singletons(
        self, test_db: Session, admin_user: User
    ):
        p1 = _make_project(test_db, admin_user)
        p2 = _make_project(test_db, admin_user)

        r1 = get_or_create_human_eval_run(
            test_db, p1.id, "korrektur_falloesung", admin_user.id
        )
        r2 = get_or_create_human_eval_run(
            test_db, p2.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()

        assert r1.id != r2.id
        assert r1.project_id == p1.id
        assert r2.project_id == p2.id

    def test_unknown_metric_rejected(self, test_db: Session, admin_user: User):
        project = _make_project(test_db, admin_user)
        with pytest.raises(ValueError, match="human-graded"):
            get_or_create_human_eval_run(
                test_db, project.id, "llm_judge_falloesung", admin_user.id
            )

    def test_partial_unique_index_rejects_bypass_insert(
        self, test_db: Session, admin_user: User
    ):
        """Inserting a second human-korrektur run for the same project, bypassing
        the helper, must be rejected by the partial unique index from migration
        037 — proving the upsert's race-safety guarantee.
        """
        project = _make_project(test_db, admin_user)

        get_or_create_human_eval_run(
            test_db, project.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()

        # Direct INSERT with the same (project_id, model_id, evaluation_type)
        # tuple should violate the partial unique index.
        with pytest.raises(IntegrityError):
            test_db.execute(
                text(
                    """
                    INSERT INTO evaluation_runs
                      (id, project_id, model_id, evaluation_type_ids, metrics,
                       eval_metadata, status, samples_evaluated, has_sample_results,
                       created_by, created_at)
                    VALUES
                      (:id, :pid, 'human',
                       '["korrektur_falloesung"]'::json,
                       '{}'::json,
                       '{"evaluation_type": "korrektur_falloesung"}'::json,
                       'in_progress', 0, true, :uid, now())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": project.id,
                    "uid": admin_user.id,
                },
            )
            test_db.flush()


class TestKorrekturCustomHumanEvalRun:
    """korrektur_custom is the second human-graded metric (extended#33).

    The extended edition's submit_custom_grade endpoint resolves its run
    through get_or_create_human_eval_run(db, project_id, "korrektur_custom",
    ...) — before the whitelist + migration-061 index landed, that call
    raised ValueError and 500'd in prod.
    """

    def test_korrektur_custom_is_human_graded(self):
        assert is_human_graded_metric("korrektur_custom")

    def test_first_call_creates_singleton(self, test_db: Session, admin_user: User):
        project = _make_project(test_db, admin_user)

        run = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_custom", admin_user.id
        )
        test_db.commit()

        assert run.id != None  # noqa: E711
        assert run.project_id == project.id
        assert run.model_id == "human"
        assert run.evaluation_type_ids == ["korrektur_custom"]
        assert run.eval_metadata.get("evaluation_type") == "korrektur_custom"
        configs = run.eval_metadata.get("evaluation_configs") or []
        assert any(c.get("metric") == "korrektur_custom" for c in configs)
        assert run.status == "completed"
        assert run.created_by == admin_user.id

    def test_second_call_returns_same_row(self, test_db: Session, admin_user: User):
        project = _make_project(test_db, admin_user)

        run1 = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_custom", admin_user.id
        )
        test_db.commit()
        run2 = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_custom", admin_user.id
        )
        test_db.commit()

        assert run1.id == run2.id

    def test_falloesung_and_custom_get_different_runs(
        self, test_db: Session, admin_user: User
    ):
        """The two human-graded metrics must NOT share a singleton: each
        (project, metric) pair gets its own persistent run. This is exactly
        why migration 061 adds a second per-metric partial index instead of
        widening 037's predicate to `evaluation_type IN (...)` — a combined
        (project_id, model_id) unique index would collapse both metrics
        into one row per project.
        """
        project = _make_project(test_db, admin_user)

        falloesung_run = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_falloesung", admin_user.id
        )
        test_db.commit()
        custom_run = get_or_create_human_eval_run(
            test_db, project.id, "korrektur_custom", admin_user.id
        )
        test_db.commit()

        assert falloesung_run.id != custom_run.id
        assert falloesung_run.eval_metadata["evaluation_type"] == "korrektur_falloesung"
        assert custom_run.eval_metadata["evaluation_type"] == "korrektur_custom"

        # Both rows coexist; repeated calls keep resolving to their own
        # singleton rather than the other metric's row.
        assert (
            get_or_create_human_eval_run(
                test_db, project.id, "korrektur_falloesung", admin_user.id
            ).id
            == falloesung_run.id
        )
        assert (
            get_or_create_human_eval_run(
                test_db, project.id, "korrektur_custom", admin_user.id
            ).id
            == custom_run.id
        )

        count = (
            test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project.id)
            .filter(EvaluationRun.model_id == "human")
            .count()
        )
        assert count == 2

    def test_partial_unique_index_rejects_bypass_insert(
        self, test_db: Session, admin_user: User
    ):
        """Same race-safety guarantee as for korrektur_falloesung: a second
        human-korrektur_custom run inserted bypassing the helper must violate
        the migration-061 partial unique index.
        """
        project = _make_project(test_db, admin_user)

        get_or_create_human_eval_run(
            test_db, project.id, "korrektur_custom", admin_user.id
        )
        test_db.commit()

        with pytest.raises(IntegrityError):
            test_db.execute(
                text(
                    """
                    INSERT INTO evaluation_runs
                      (id, project_id, model_id, evaluation_type_ids, metrics,
                       eval_metadata, status, samples_evaluated, has_sample_results,
                       created_by, created_at)
                    VALUES
                      (:id, :pid, 'human',
                       '["korrektur_custom"]'::json,
                       '{}'::json,
                       '{"evaluation_type": "korrektur_custom"}'::json,
                       'in_progress', 0, true, :uid, now())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": project.id,
                    "uid": admin_user.id,
                },
            )
            test_db.flush()


class TestMetricSetExports:
    def test_korrektur_falloesung_in_set(self):
        assert "korrektur_falloesung" in HUMAN_GRADED_METRICS

    def test_korrektur_custom_in_set(self):
        assert "korrektur_custom" in HUMAN_GRADED_METRICS

    def test_set_is_frozen(self):
        with pytest.raises(AttributeError):
            HUMAN_GRADED_METRICS.add("anything")  # type: ignore[attr-defined]
