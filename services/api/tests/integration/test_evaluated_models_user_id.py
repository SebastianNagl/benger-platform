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
"""

import uuid
from datetime import datetime, timezone

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


def _seed_project_with_eval(db, admin, org):
    """Minimal project with one Task and one annotation-side EvaluationRun
    (no Generations needed — this exercises only the annotator-discovery
    join path in metadata.py)."""
    project = Project(
        id=_uid(),
        title=f"UserIdContract {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()

    db.add(ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    ))

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
    db.flush()

    judge_run = EvaluationJudgeRun(
        id=_uid(), evaluation_id=eval_run.id,
        judge_model_id=None, run_index=0, status="completed",
    )
    db.add(judge_run)
    db.flush()

    return project, task, eval_run, judge_run


def _add_annotator_eval(db, project, task, eval_run, judge_run, user):
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
    db.flush()

    db.add(TaskEvaluation(
        id=_uid(), evaluation_id=eval_run.id, judge_run_id=judge_run.id,
        task_id=task.id, generation_id=None, annotation_id=ann.id,
        field_name="answer", answer_type="choices",
        ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
        metrics={"accuracy": 1.0}, passed=True,
    ))


@pytest.mark.integration
class TestEvaluatedModelsUserIdContract:
    """Issue #69 wrap-up: lock down the user_id wire-shape contract."""

    def test_user_id_present_only_on_annotator_rows(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """`user_id` is emitted iff the row is an annotator row. The frontend
        modal keys annotator selection on this id and skips rows without it
        (EvaluationControlModal.tsx: `if (!row.user_id) continue`)."""
        admin = test_users[0]
        project, task, eval_run, judge_run = _seed_project_with_eval(
            test_db, admin, test_org
        )
        _add_annotator_eval(test_db, project, task, eval_run, judge_run, admin)
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=_h(auth_headers, test_org),
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
            assert row["user_id"] == admin.id, (
                f"user_id {row['user_id']!r} should equal seeded admin.id "
                f"{admin.id!r}"
            )
        for row in non_annotator_rows:
            assert "user_id" not in row, (
                "non-annotator rows must NOT carry a user_id key "
                f"(D2 contract; got {row.get('user_id')!r} in {row})"
            )

    def test_two_users_same_display_surface_distinctly(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two distinct users sharing the same display name must each surface
        as their own row with a distinct `user_id`. Locks the multi-row
        expansion (Phase A2 alternative implementation in metadata.py:289-321,
        425-446) so a future refactor can't regress to silent overwrite of the
        second user's id by the first."""
        admin = test_users[0]
        project, task, eval_run, judge_run = _seed_project_with_eval(
            test_db, admin, test_org
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
        test_db.add_all([user_a, user_b])
        test_db.flush()

        _add_annotator_eval(test_db, project, task, eval_run, judge_run, user_a)
        _add_annotator_eval(test_db, project, task, eval_run, judge_run, user_b)
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=_h(auth_headers, test_org),
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
        assert user_ids == {user_a.id, user_b.id}, (
            "each Anna row must carry the underlying user's id, not a "
            f"silently-overwritten one (got {user_ids}, expected "
            f"{{{user_a.id!r}, {user_b.id!r}}})"
        )
