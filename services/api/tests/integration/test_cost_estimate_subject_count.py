"""Integration tests for the cost-estimate `subject_count` math (issue #69).

Builds a project with a known number of generations and annotations, then
calls `/api/llm-models/cost-estimate` with various scope combinations and
asserts `subject_count` matches the formula:

    subject_count = sum_over_configs(
        n_llm_fields × |Generation rows matching model_ids|
        + n_human_fields × |Annotation rows matching annotator_user_ids|
    )

The math is what the cost preview multiplies by per-call price; if any
piece drifts the dollar number lies. These tests are the reference for
that contract.

Note on dollars: we don't assert specific cost numbers — pricing depends
on the LLMModel rows seeded by tiktoken-driven token counts, which add
their own variance. We assert subject_count (deterministic) and the
relative shape of `total_usd` (zero/non-zero, narrowed-vs-full).

The endpoint is on the async lane (`estimate_cost` takes an
``AsyncSession`` and bridges the sync cost computation through
``db.run_sync`` in the SAME transaction), so these tests run on the async
fixtures and override ``require_user`` to a superadmin acting user — the
bridged computation sees the SAVEPOINT-isolated rows with no mocking.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMModel,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, Task


# ---------------------------------------------------------------------------
# Auth override + acting-user seed
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user):
    """Override `require_user` to act as `db_user`. Happy-path tests act as
    a superadmin so `check_project_accessible_async` short-circuits True."""
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db: AsyncSession, *, is_superadmin: bool = True) -> User:
    """Create a real acting User row (superadmin by default)."""
    uid = str(uuid.uuid4())
    user = User(
        id=uid,
        username=f"cost-subj-user-{uid[:8]}",
        email=f"cost-subj-user-{uid[:8]}@example.com",
        name="Cost Subject Test User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Fixture builders (focused on what the cost endpoint reads)
# ---------------------------------------------------------------------------


async def _seed_judge_pricing(db: AsyncSession, judge_id: str) -> None:
    """Cost endpoint pulls per-token pricing from the llm_models table.
    Seed a row for the judge model so the formula multiplies cleanly."""
    existing = (
        await db.execute(select(LLMModel).where(LLMModel.id == judge_id))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(LLMModel(
        id=judge_id,
        name=judge_id,
        provider="anthropic",
        model_type="chat",
        capabilities=["text_generation"],
        input_cost_per_million=1.0,
        output_cost_per_million=5.0,
        is_active=True,
    ))
    await db.flush()


async def _seed_project_with_subjects(
    db: AsyncSession,
    owner: User,
    *,
    num_tasks: int = 3,
    num_generation_models: int = 2,
    num_annotators: int = 2,
) -> Dict:
    """Create a project with `num_tasks` tasks, each with one Generation per
    `num_generation_models` model and one Annotation per `num_annotators`
    annotator. Total subjects:
        - generations: num_tasks × num_generation_models
        - annotations: num_tasks × num_annotators

    Returns dict with project, model_ids, annotator_user_ids, expected
    counts."""
    project = Project(
        id=str(uuid.uuid4()),
        title="cost-subject-count-test",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=owner.id,
        is_published=True,
    )
    db.add(project)
    await db.flush()

    # Tasks
    tasks: List[Task] = []
    for i in range(num_tasks):
        t = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"q": f"Q{i + 1}"},
            created_by=owner.id,
            updated_by=owner.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    # Generation models — pick stable ids the test can filter on.
    model_ids = [f"test-model-{i}" for i in range(num_generation_models)]
    for task in tasks:
        for model_id in model_ids:
            rg = ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=project.id,
                task_id=task.id,
                model_id=model_id,
                status="completed",
                responses_generated=1,
                created_by=owner.id,
            )
            db.add(rg)
            await db.flush()
            # Generation has no project_id column — the cost-estimate
            # filter joins via ResponseGeneration.project_id instead.
            db.add(Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=task.id,
                model_id=model_id,
                run_index=0,
                case_data="{}",
                response_content="...",
                status="completed",
                parse_status="success",
            ))
    await db.flush()

    # Annotators — seed N annotator users; each annotates every task once.
    # Total annotations: num_tasks × num_annotators.
    annotator_users: List[User] = []
    for _ in range(num_annotators):
        annotator_users.append(await _seed_user(db, is_superadmin=False))
    annotator_user_ids = [u.id for u in annotator_users]
    for task in tasks:
        for uid in annotator_user_ids:
            db.add(Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=project.id,
                completed_by=uid,
                result=[],
                was_cancelled=False,
                created_at=datetime.utcnow(),
            ))
    await db.flush()

    return {
        "project": project,
        "model_ids": model_ids,
        "annotator_user_ids": annotator_user_ids,
        "expected_generation_count": num_tasks * num_generation_models,
        "expected_annotation_count": num_tasks * num_annotators,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


JUDGE_ID = "test-judge-haiku"


async def _post_estimate(client, **body) -> Dict:
    """Post to the cost-estimate endpoint and return the parsed body. Asserts
    a 2xx so failed requests don't masquerade as zero subject_counts."""
    resp = await client.post("/api/llm-models/cost-estimate", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSubjectCount:
    """The subject_count math is the heart of the new cost preview. Each
    test pins one degree of freedom."""

    @pytest.mark.asyncio
    async def test_legacy_no_configs_yields_zero_subject_count(
        self, async_test_client, async_test_db
    ):
        """When the modal doesn't pass `evaluation_configs`, the endpoint
        falls back to the legacy tasks-count formula and reports zero
        subjects (the new path is opt-in via configs being supplied)."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
            )
        assert body["subject_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_field_config_counts_generations(
        self, async_test_client, async_test_db
    ):
        """One LLM-side prediction_field × N generations = N cells."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        expected = data["expected_generation_count"]
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["model:answer"]},
                ],
            )
        assert body["subject_count"] == expected

    @pytest.mark.asyncio
    async def test_human_field_config_counts_annotations(
        self, async_test_client, async_test_db
    ):
        """One human-side prediction_field × M annotations = M cells."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        expected = data["expected_annotation_count"]
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["human:answer"]},
                ],
            )
        assert body["subject_count"] == expected

    @pytest.mark.asyncio
    async def test_falloesung_unprefixed_routed_to_annotations(
        self, async_test_client, async_test_db
    ):
        """The shared classifier's backward-compat rule: for
        `llm_judge_falloesung` with no `human:` prefix, the unprefixed
        field counts against annotations, not generations. This was the
        original motivating bug — getting it wrong here means the cost
        preview lies for the metric the feature was built for."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        expected = data["expected_annotation_count"]
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "llm_judge_falloesung", "prediction_fields": ["loesung"]},
                ],
            )
        # Single unprefixed field × annotation count.
        assert body["subject_count"] == expected

    @pytest.mark.asyncio
    async def test_model_ids_filter_narrows_generation_subjects(
        self, async_test_client, async_test_db
    ):
        """`model_ids=[m0]` should drop the count by half when there are 2
        generation models in the project."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(
            async_test_db, actor,
            num_tasks=4, num_generation_models=2,
        )
        pid = data["project"].id
        model0 = data["model_ids"][0]
        expected = data["expected_generation_count"] // 2
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                model_ids=[model0],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["model:answer"]},
                ],
            )
        # Only one model selected → half the generations.
        assert body["subject_count"] == expected

    @pytest.mark.asyncio
    async def test_annotator_user_ids_filter_narrows_annotation_subjects(
        self, async_test_client, async_test_db
    ):
        """`annotator_user_ids=[uid_0]` should drop the count by half when
        there are 2 annotators each annotating every task."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(
            async_test_db, actor,
            num_tasks=4, num_annotators=2,
        )
        pid = data["project"].id
        uid0 = data["annotator_user_ids"][0]
        expected = data["expected_annotation_count"] // 2
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                annotator_user_ids=[uid0],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["human:answer"]},
                ],
            )
        assert body["subject_count"] == expected

    @pytest.mark.asyncio
    async def test_zero_subjects_with_configs_produces_zero_cost(
        self, async_test_client, async_test_db
    ):
        """A1 critical-bug regression test: when the user narrows scope to
        a model with no generations, `subject_count` is zero AND the
        formula stays in subject-count mode (does NOT fall back to the
        full-sweep tasks formula). Old code flipped back and showed a
        full-sweep cost — this asserts the gate is on
        `bool(evaluation_configs)`, not on `subject_count > 0`."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                model_ids=["nonexistent-model-id"],
                runs_per_call=1,
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["model:answer"]},
                ],
            )
        assert body["subject_count"] == 0
        # Pre-fix the cost would have been ~tasks × per_call × runs (non-zero).
        assert body["total_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_human_and_llm_fields_sum_correctly(
        self, async_test_client, async_test_db
    ):
        """A config with both a `model:` and a `human:` prediction_field
        contributes (gen_count + ann_count) cells per run."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        expected = (
            data["expected_generation_count"] + data["expected_annotation_count"]
        )
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
                evaluation_configs=[
                    {
                        "metric": "exact_match",
                        "prediction_fields": ["model:a", "human:b"],
                    },
                ],
            )
        assert body["subject_count"] == expected


# ---------------------------------------------------------------------------
# Issue #132 regression helpers and tests
# ---------------------------------------------------------------------------


JUDGE_A = "test-judge-a"
JUDGE_B = "test-judge-b"


async def _set_project_judge_configs(
    db: AsyncSession, project: Project, configs: List[Dict],
) -> None:
    """Set `project.evaluation_config.evaluation_configs` so the cost
    endpoint's `_load_llm_judge_configs` can find these configs.

    Each config dict needs: id, metric, prediction_fields, judges:[{judge_model_id, runs}].
    """
    project.evaluation_config = {"evaluation_configs": configs}
    db.add(project)
    await db.flush()


async def _gen_ids_for_project(db: AsyncSession, project_id: str) -> List[str]:
    rows = (
        (
            await db.execute(
                select(Generation.id)
                .join(Task, Generation.task_id == Task.id)
                .where(Task.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _ann_ids_for_project(db: AsyncSession, project_id: str) -> List[str]:
    rows = (
        (
            await db.execute(
                select(Annotation.id).where(
                    Annotation.project_id == project_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _seed_scored_cells(
    db: AsyncSession,
    project: Project,
    judge_model_id: str,
    *,
    config_id: str,
    pred_field: str,
    reference_field: str = "musterloesung",
    generation_ids: List[str] = (),
    annotation_ids: List[str] = (),
) -> None:
    """Create EvaluationRun + EvaluationJudgeRun + TaskEvaluation rows
    that look identical to what the worker writes under
    `field_name = "{config_id}|{pred_field}|{reference_field}"`.

    The skip-set query in `_already_scored_subjects` filters on this
    field_name shape, the project_id (via the EvaluationRun join),
    metrics is not null, and error_message is null.
    """
    admin_id = project.created_by
    eval_run = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id=judge_model_id,
        evaluation_type_ids=["llm_judge_falloesung"],
        metrics={"placeholder": 1.0},
        status="completed",
        created_by=admin_id,
    )
    db.add(eval_run)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=eval_run.id,
        judge_model_id=judge_model_id,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()

    field_name = f"{config_id}|{pred_field}|{reference_field}"
    # TaskEvaluation has several NOT NULL columns the worker fills in; we
    # only care that the skip-set query's WHERE clauses are satisfied
    # (project_id via EvaluationRun join, field_name LIKE pattern, metrics
    # not null, error_message null, subject_col not null), but the table
    # constraints still require task_id/answer_type/ground_truth/etc.
    gen_to_task: Dict[str, str] = {}
    if generation_ids:
        gen_rows = (
            await db.execute(
                select(Generation.id, Generation.task_id).where(
                    Generation.id.in_(list(generation_ids))
                )
            )
        ).all()
        gen_to_task = {gid: tid for gid, tid in gen_rows}
    ann_to_task: Dict[str, str] = {}
    if annotation_ids:
        ann_rows = (
            await db.execute(
                select(Annotation.id, Annotation.task_id).where(
                    Annotation.id.in_(list(annotation_ids))
                )
            )
        ).all()
        ann_to_task = {aid: tid for aid, tid in ann_rows}
    for gid in generation_ids:
        db.add(TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=eval_run.id,
            judge_run_id=judge_run.id,
            task_id=gen_to_task[gid],
            generation_id=gid,
            field_name=field_name,
            answer_type="long_text",
            ground_truth={},
            prediction={},
            passed=True,
            metrics={"llm_judge_falloesung": {"value": 0.8, "error": None}},
            error_message=None,
        ))
    for aid in annotation_ids:
        db.add(TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=eval_run.id,
            judge_run_id=judge_run.id,
            task_id=ann_to_task[aid],
            annotation_id=aid,
            field_name=field_name,
            answer_type="long_text",
            ground_truth={},
            prediction={},
            passed=True,
            metrics={"llm_judge_falloesung": {"value": 0.7, "error": None}},
            error_message=None,
        ))
    await db.flush()


def _per_model_cells(body: Dict, judge_id: str) -> int:
    """Pluck the `cells_to_generate` for a specific judge from the response."""
    rows = [m for m in body["per_model"] if m["model_id"] == judge_id]
    assert rows, f"judge {judge_id} not in per_model: {body['per_model']}"
    return rows[0]["cells_to_generate"]


class TestEvaluationJudgeCalls:
    """Issue #132: `_count_evaluation_judge_calls` regression tests.

    These pin the per-judge cell-count behavior that drives the dollar
    figure. Pre-fix the estimator over-counted by ~63x on partially-
    covered projects; each test below kills one defect.
    """

    @pytest.mark.asyncio
    async def test_missing_subtracts_per_config(
        self, async_test_client, async_test_db
    ):
        """Defect 3: skip-set must key off `config_id`, not metric prefix.
        Two configs share the same metric; one is fully covered, the new
        one is empty. The covered config's cells must NOT be credited to
        the new config.
        """
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_A)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        expected = data["expected_generation_count"]
        covered_cfg_id = "llm_judge_falloesung-covered-aaa"
        new_cfg_id = "llm_judge_falloesung-new-bbb"
        await _set_project_judge_configs(async_test_db, data["project"], [
            {
                "id": covered_cfg_id,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
            {
                "id": new_cfg_id,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
        ])
        # Cover every generation under the covered config only.
        all_gen_ids = await _gen_ids_for_project(async_test_db, pid)
        await _seed_scored_cells(
            async_test_db, data["project"], JUDGE_A,
            config_id=covered_cfg_id, pred_field="__all_model__",
            generation_ids=all_gen_ids,
        )
        await async_test_db.commit()

        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_A],
                generation_mode="missing",
                runs_per_call=1,
                evaluation_configs=[{
                    "metric": "llm_judge_falloesung",
                    "prediction_fields": ["__all_model__"],
                }],
            )
        # Pre-fix: skip-set matched both configs via metric_id wildcard, so
        # `new_cfg`'s subjects also looked "done" — missing reported 0,
        # under-counting. Post-fix: covered_cfg subtracts only its own rows
        # (0 missing), new_cfg subtracts nothing (full pool missing).
        # Total cells = 0 (covered) + N_gens (new) = N_gens.
        assert _per_model_cells(body, JUDGE_A) == expected

    @pytest.mark.asyncio
    async def test_bare_pred_field_subtracts_both_arms(
        self, async_test_client, async_test_db
    ):
        """Defect 3 sub: bare prediction_field rows are stored under the
        same composite for both arms (`{cfg}|loesung|...`), distinguished
        by which subject_col is populated. Pre-fix the human-arm subquery
        looked up `human:loesung` which the worker never writes, so
        annotation rows under bare-field configs never got subtracted.
        """
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_A)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        cfg_id = "llm_judge_falloesung-bare-ccc"
        await _set_project_judge_configs(async_test_db, data["project"], [
            {
                "id": cfg_id,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["loesung"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
        ])
        all_gen_ids = await _gen_ids_for_project(async_test_db, pid)
        all_ann_ids = await _ann_ids_for_project(async_test_db, pid)
        # Bare-field: worker writes both arms under the same field_name shape.
        await _seed_scored_cells(
            async_test_db, data["project"], JUDGE_A,
            config_id=cfg_id, pred_field="loesung",
            generation_ids=all_gen_ids, annotation_ids=all_ann_ids,
        )
        await async_test_db.commit()

        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_A],
                generation_mode="missing",
                runs_per_call=1,
                evaluation_configs=[{
                    "metric": "llm_judge_falloesung",
                    "prediction_fields": ["loesung"],
                }],
            )
        # Both arms covered → missing should be 0.
        assert _per_model_cells(body, JUDGE_A) == 0

    @pytest.mark.asyncio
    async def test_per_config_runs_not_inflated_by_other_configs(
        self, async_test_client, async_test_db
    ):
        """Defect 2: each config's per-judge `runs` is applied locally.
        Pre-fix the request-level `runs_per_call` (a global max across
        all selected configs) multiplied every config's per-judge runs,
        so a `runs:1` config sitting next to a `runs:3` config was billed
        at 1×3=3.
        """
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_A)
        cfg_runs1 = "llm_judge_falloesung-runs1-ddd"
        cfg_runs3 = "llm_judge_falloesung-runs3-eee"
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        n = data["expected_generation_count"]
        await _set_project_judge_configs(async_test_db, data["project"], [
            {
                "id": cfg_runs1,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
            {
                "id": cfg_runs3,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 3}]},
            },
        ])
        await async_test_db.commit()

        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_A],
                # Frontend sends the global max — backend must IGNORE this in
                # the eval-with-configs branch and use each cfg's own runs.
                runs_per_call=3,
                evaluation_configs=[{
                    "metric": "llm_judge_falloesung",
                    "prediction_fields": ["__all_model__"],
                }],
            )
        # Pre-fix: (cfg_runs1: n × 1 × 3) + (cfg_runs3: n × 3 × 3) = 12n.
        # Post-fix: (cfg_runs1: n × 1) + (cfg_runs3: n × 3) = 4n.
        assert _per_model_cells(body, JUDGE_A) == 4 * n

    @pytest.mark.asyncio
    async def test_judge_only_charged_for_configs_naming_it(
        self, async_test_client, async_test_db
    ):
        """Defect 1: per-judge dollar math must route through
        `_count_evaluation_judge_calls`, not `_count_eval_subjects`.
        Pre-fix every judge was billed for the full subject_count across
        all configs, regardless of whether the judge appeared in them.
        """
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_A)
        await _seed_judge_pricing(async_test_db, JUDGE_B)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        n = data["expected_generation_count"]
        cfg_a = "llm_judge_falloesung-onlyA-fff"
        cfg_b = "llm_judge_falloesung-onlyB-ggg"
        await _set_project_judge_configs(async_test_db, data["project"], [
            {
                "id": cfg_a,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
            {
                "id": cfg_b,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_B, "runs": 1}]},
            },
        ])
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_A, JUDGE_B],
                runs_per_call=1,
                evaluation_configs=[{
                    "metric": "llm_judge_falloesung",
                    "prediction_fields": ["__all_model__"],
                }],
            )
        # Each judge appears in exactly one config of size n. Pre-fix both
        # judges saw 2n (the union). Post-fix each sees n.
        assert _per_model_cells(body, JUDGE_A) == n
        assert _per_model_cells(body, JUDGE_B) == n

    @pytest.mark.asyncio
    async def test_rescored_cells_dedup_server_side(
        self, async_test_client, async_test_db
    ):
        """Issue #106: the skip-set query must return one row per scored
        subject, not one per historical TaskEvaluation row. Every re-run of
        an evaluation used to add a full copy of the result set to the rows
        the API pulls into Python before deduplicating.
        """
        from sqlalchemy import event

        from routers.cost_estimate import _scored_for

        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_A)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        cfg_id = "llm_judge_falloesung-rescored-ccc"
        await _set_project_judge_configs(async_test_db, data["project"], [
            {
                "id": cfg_id,
                "enabled": True,
                "metric": "llm_judge_falloesung",
                "prediction_fields": ["__all_model__"],
                "metric_parameters": {"judges": [{"judge_model_id": JUDGE_A, "runs": 1}]},
            },
        ])
        all_gen_ids = await _gen_ids_for_project(async_test_db, pid)
        # Score every cell twice — two historical runs over the same subjects.
        for _ in range(2):
            await _seed_scored_cells(
                async_test_db, data["project"], JUDGE_A,
                config_id=cfg_id, pred_field="__all_model__",
                generation_ids=all_gen_ids,
            )
        await async_test_db.commit()

        # `_scored_for` is sync-only and takes a sync Session. Bridge it onto
        # a sync Session bound to THIS async connection/transaction via
        # run_sync, exactly as the endpoint does, so it sees the seeded rows.
        def _run_scored_for(sync_db):
            captured: List[str] = []

            def _capture(conn, cursor, statement, parameters, context, executemany):
                captured.append(statement)

            bind = sync_db.get_bind()
            event.listen(bind, "before_cursor_execute", _capture)
            try:
                scored = _scored_for(
                    sync_db, pid,
                    config_id=cfg_id, pred_field_norm="__all_model__",
                    subject_col=TaskEvaluation.generation_id, kind="generation",
                )
            finally:
                event.remove(bind, "before_cursor_execute", _capture)
            return scored, captured

        scored, captured = await async_test_db.run_sync(_run_scored_for)

        # Set semantics unchanged: each subject counted once.
        assert scored == {("generation", gid) for gid in all_gen_ids}
        # And the dedup happened in SQL, not by fetching duplicate rows.
        selects = [s for s in captured if s.lstrip().upper().startswith("SELECT")]
        assert selects, "skip-set query was not captured"
        assert any("DISTINCT" in s.upper() for s in selects)

        # End-to-end: a fully (re-)covered config reports zero missing cells.
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_A],
                generation_mode="missing",
                runs_per_call=1,
                evaluation_configs=[{
                    "metric": "llm_judge_falloesung",
                    "prediction_fields": ["__all_model__"],
                }],
            )
        assert _per_model_cells(body, JUDGE_A) == 0


class TestRequestValidation:
    """B3 cross-mode rejection — validator integration check."""

    @pytest.mark.asyncio
    async def test_generation_mode_with_evaluation_configs_rejected(
        self, async_test_client, async_test_db
    ):
        """The validator rejects payloads that mix mode=generation with
        eval-only keys. Returns 422 (Pydantic validation), not 400."""
        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await async_test_client.post(
                "/api/llm-models/cost-estimate",
                json={
                    "project_id": pid,
                    "mode": "generation",
                    "model_ids": ["gpt-5"],
                    "evaluation_configs": [
                        {"metric": "exact_match", "prediction_fields": ["x"]}
                    ],
                },
            )
        assert resp.status_code == 422
        assert "evaluation_configs" in resp.text

    @pytest.mark.asyncio
    async def test_estimated_at_present_on_response(
        self, async_test_client, async_test_db
    ):
        """E4: the response carries an ISO timestamp the frontend uses for
        the staleness tooltip. Must be ISO-8601 parseable."""
        from datetime import datetime as _dt

        actor = await _seed_user(async_test_db)
        await _seed_judge_pricing(async_test_db, JUDGE_ID)
        data = await _seed_project_with_subjects(async_test_db, actor)
        pid = data["project"].id
        await async_test_db.commit()
        with _as_user(actor):
            body = await _post_estimate(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[JUDGE_ID],
                runs_per_call=1,
            )
        assert "estimated_at" in body
        # fromisoformat tolerates the +00:00 suffix from datetime.now(tz=utc).
        _dt.fromisoformat(body["estimated_at"])
