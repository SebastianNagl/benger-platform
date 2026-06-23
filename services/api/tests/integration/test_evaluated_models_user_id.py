"""
Wire-shape contract tests for the `/api/evaluations/projects/{project_id}/evaluated-models`
endpoint, covering the `user_id` field surfaced for issue #69 (targeted re-evaluate
scope). The frontend's EvaluationControlModal keys annotator-section selection
on `user_id`; if the contract drifts (key missing on annotator rows, present on
non-annotator rows, or two distinct users collapsing under one id) annotator
scoping silently dispatches against the wrong person.

Tests build their own minimal fixture inline rather than calling the shared
_build_graph harness in test_evaluation_metadata_coverage.py — that harness is
out-of-step with several recent migrations (041 / 042 / 043) and fixing it is
out of scope for the wrap-up.

The handler was migrated to the async DB lane (``Depends(get_async_db)`` +
``await db.execute(select(...))``), so these tests seed through ``async_test_db``
and drive the surface through ``async_test_client``. Access goes through
``check_project_accessible_async``, which short-circuits ``True`` for a
superadmin — so the seeded admin is a superadmin and no patch is needed.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    Task,
)

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override ``require_user`` with an ``auth_module.models.User`` built from
    a seeded DB ``User`` for the duration of the block."""
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, *, is_superadmin=True):
    """Seed a real superadmin ``models.User`` so access passes via the
    superadmin short-circuit in ``check_project_accessible_async``."""
    u = User(
        id=_uid(),
        username=f"userid-contract-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="UserId Contract Admin",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project_with_eval(db, admin):
    """Minimal project with one Task and one annotation-side EvaluationRun
    (no Generations needed — this exercises only the annotator-discovery
    join path in metadata.py).

    No ProjectOrganization row is seeded: access goes through the superadmin
    short-circuit in ``check_project_accessible_async``, so org membership is
    never consulted (and fabricating an org id would violate the
    project_organizations FK)."""
    project = Project(
        id=_uid(),
        title=f"UserIdContract {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    await db.flush()

    task = Task(
        id=_uid(), project_id=project.id,
        data={"text": "fixture text"}, inner_id=1,
        created_by=admin.id,
    )
    db.add(task)

    eval_run = EvaluationRun(
        id=_uid(), project_id=project.id,
        # Non-annotator model rows are surfaced via models_with_evaluations
        # (a distinct query on evaluation_runs.model_id) — the literal "gpt-4o"
        # below is what makes the second non-Annotator row appear in the
        # response, so the user_id-absence assertion has something to bite on.
        model_id="gpt-4o",
        evaluation_type_ids=["accuracy"],
        metrics={"accuracy": 0.9},
        status="completed", samples_evaluated=1,
        has_sample_results=True, created_by=admin.id,
    )
    db.add(eval_run)
    await db.flush()

    judge_run = EvaluationJudgeRun(
        id=_uid(), evaluation_id=eval_run.id,
        judge_model_id=None, run_index=0, status="completed",
    )
    db.add(judge_run)
    await db.flush()

    return project, task, eval_run, judge_run


async def _add_annotator_eval(db, project, task, eval_run, judge_run, user):
    """Attach one Annotation + annotation-side TaskEvaluation for `user`
    so they surface in the /evaluated-models response as a provider=Annotator
    row."""
    ann = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id,
        completed_by=user.id,
        result=[{"from_name": "answer", "to_name": "text",
                 "type": "choices", "value": {"choices": ["Ja"]}}],
        was_cancelled=False,
    )
    db.add(ann)
    await db.flush()

    db.add(TaskEvaluation(
        id=_uid(), evaluation_id=eval_run.id, judge_run_id=judge_run.id,
        task_id=task.id, generation_id=None, annotation_id=ann.id,
        field_name="answer", answer_type="choices",
        ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
        metrics={"accuracy": 1.0}, passed=True,
    ))
    await db.flush()


@pytest.mark.integration
class TestEvaluatedModelsUserIdContract:
    """Issue #69 wrap-up: lock down the user_id wire-shape contract."""

    @pytest.mark.asyncio
    async def test_user_id_present_only_on_annotator_rows(
        self, async_test_client, async_test_db
    ):
        """`user_id` is emitted iff the row is an annotator row. The frontend
        modal keys annotator selection on this id and skips rows without it
        (EvaluationControlModal.tsx: `if (!row.user_id) continue`)."""
        db = async_test_db
        admin = await _seed_user(db)
        project, task, eval_run, judge_run = await _seed_project_with_eval(
            db, admin
        )
        await _add_annotator_eval(db, project, task, eval_run, judge_run, admin)

        admin_id = admin.id
        pid = project.id
        await db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{pid}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text
        models = resp.json()

        annotator_rows = [m for m in models if m["provider"] == "Annotator"]
        non_annotator_rows = [m for m in models if m["provider"] != "Annotator"]
        assert annotator_rows, f"expected at least one annotator row in {models}"
        assert non_annotator_rows, f"expected at least one model row in {models}"

        for row in annotator_rows:
            assert row.get("user_id"), (
                "annotator rows must carry a non-empty user_id "
                f"(got: {row.get('user_id')!r} in {row})"
            )
            assert row["user_id"] == admin_id, (
                f"user_id {row['user_id']!r} should equal seeded admin.id "
                f"{admin_id!r}"
            )
        for row in non_annotator_rows:
            assert "user_id" not in row, (
                "non-annotator rows must NOT carry a user_id key "
                f"(D2 contract; got {row.get('user_id')!r} in {row})"
            )

    @pytest.mark.asyncio
    async def test_two_users_same_display_surface_distinctly(
        self, async_test_client, async_test_db
    ):
        """Two distinct users sharing the same display name must each surface
        as their own row with a distinct `user_id`. Locks the multi-row
        expansion (Phase A2 alternative implementation in metadata.py:289-321,
        425-446) so a future refactor can't regress to silent overwrite of the
        second user's id by the first."""
        db = async_test_db
        admin = await _seed_user(db)
        project, task, eval_run, judge_run = await _seed_project_with_eval(
            db, admin
        )

        # `User.name` is non-unique (only username/email/pseudonym carry
        # uniqueness constraints), so this is the realistic real-world
        # collision case: two annotators with use_pseudonym=False and the
        # same display name.
        shared_display = "Anna Schmidt"
        suffix = uuid.uuid4().hex[:6]
        user_a = User(
            id=_uid(),
            username=f"anna-a-{suffix}",
            email=f"anna-a-{suffix}@example.com",
            name=shared_display, use_pseudonym=False,
            email_verified=True, is_active=True,
        )
        user_b = User(
            id=_uid(),
            username=f"anna-b-{suffix}",
            email=f"anna-b-{suffix}@example.com",
            name=shared_display, use_pseudonym=False,
            email_verified=True, is_active=True,
        )
        # AsyncSession.add_all is a SYNC method — do NOT await it.
        db.add_all([user_a, user_b])
        await db.flush()

        await _add_annotator_eval(db, project, task, eval_run, judge_run, user_a)
        await _add_annotator_eval(db, project, task, eval_run, judge_run, user_b)

        pid = project.id
        ua_id = user_a.id
        ub_id = user_b.id
        await db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{pid}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text
        models = resp.json()

        rows_for_anna = [
            m for m in models
            if m["provider"] == "Annotator"
            and m["model_name"] == f"Annotator: {shared_display}"
        ]
        assert len(rows_for_anna) == 2, (
            "two distinct users with the same display name must each get "
            f"their own row (got {len(rows_for_anna)}: {rows_for_anna})"
        )
        user_ids = {row["user_id"] for row in rows_for_anna}
        assert user_ids == {ua_id, ub_id}, (
            "each Anna row must carry the underlying user's id, not a "
            f"silently-overwritten one (got {user_ids}, expected "
            f"{{{ua_id!r}, {ub_id!r}}})"
        )
