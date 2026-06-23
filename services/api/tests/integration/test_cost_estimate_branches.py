"""Integration tests for cost-estimate error/edge branches.

Targets the uncovered paths in `services/api/routers/cost_estimate.py`:
the project-not-found 404, the access-denied 403, the two 400 guards
(no target models, project with no tasks), pricing-unknown vs free-model
vs priced-model `per_model` shaping, the generation-mode `cells_to_generate`
math (all vs missing), the per-model `max_tokens` override and reasoning-tier
utilization branch, the multi-model loop, and the mode-dependent `note`
text. Mirrors the request idioms and LLMModel/Project seeding of
`test_cost_estimate_subject_count.py` exactly so the structure matches a
known-passing suite.

We assert HTTP status + response JSON, and (for the cells_to_generate
tests) the persisted ResponseGeneration DB rows that drive the count.
Dollar figures depend on tiktoken token counts so we assert their
*shape* (zero vs non-zero, pricing_known flag) rather than exact values.

The endpoint is on the async lane (`estimate_cost` takes an
``AsyncSession`` via ``Depends(get_async_db)`` and bridges the sync cost
computation through ``db.run_sync`` in the SAME transaction). These tests
therefore run on the async fixtures (`async_test_client` + `async_test_db`)
and override ``require_user`` directly — the bridged computation sees the
SAVEPOINT-isolated rows seeded in this transaction with no mocking.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import LLMModel, ResponseGeneration, User
from project_models import Project, Task


# ---------------------------------------------------------------------------
# Auth override
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user):
    """Override `require_user` to act as `db_user` for the duration of the
    block. The endpoint's access gate (`check_project_accessible_async`)
    short-circuits to True for superadmins; for the 403 test the acting
    user is a non-superadmin non-creator with no membership."""
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


# ---------------------------------------------------------------------------
# Seeding helpers (async; mirror the original sync idioms)
# ---------------------------------------------------------------------------


PRICED_MODEL = "test-priced-model"
FREE_MODEL = "test-free-model"
REASONING_MODEL = "test-reasoning-model"


async def _seed_user(db: AsyncSession, *, is_superadmin: bool = True) -> User:
    """Create a real acting User row. Superadmin by default so the access
    gate passes for happy-path tests; pass is_superadmin=False for the
    403 access-denied path."""
    uid = str(uuid.uuid4())
    user = User(
        id=uid,
        username=f"cost-user-{uid[:8]}",
        email=f"cost-user-{uid[:8]}@example.com",
        name="Cost Test User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_model(
    db: AsyncSession,
    model_id: str,
    *,
    input_cost: Optional[float] = 1.0,
    output_cost: Optional[float] = 5.0,
    default_config: Optional[dict] = None,
    recommended_parameters: Optional[dict] = None,
) -> None:
    """Seed an LLMModel row the cost endpoint prices against. Uses the real
    column names from services/shared/models.py (input_cost_per_million /
    output_cost_per_million / default_config / recommended_parameters)."""
    existing = (
        await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(LLMModel(
        id=model_id,
        name=model_id,
        provider="anthropic",
        model_type="chat",
        capabilities=["text_generation"],
        input_cost_per_million=input_cost,
        output_cost_per_million=output_cost,
        default_config=default_config,
        recommended_parameters=recommended_parameters,
        is_active=True,
    ))
    await db.flush()


async def _seed_project(
    db: AsyncSession,
    owner: User,
    *,
    num_tasks: int = 3,
    is_private: bool = False,
    generation_config: Optional[dict] = None,
) -> Project:
    """Create a project owned by `owner` with `num_tasks` tasks. For
    happy-path tests `owner` is a superadmin so access passes regardless of
    org linkage; for the 403 path the project is private and the acting
    user is a non-creator non-superadmin with no membership."""
    project = Project(
        id=str(uuid.uuid4()),
        title="cost-branches-test",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=owner.id,
        is_published=True,
        is_private=is_private,
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()
    for i in range(num_tasks):
        db.add(Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"q": f"Q{i + 1}"},
            created_by=owner.id,
            updated_by=owner.id,
        ))
    await db.flush()
    return project


async def _post(client, **body):
    return await client.post("/api/llm-models/cost-estimate", json=body)


def _per_model(body: Dict, model_id: str) -> Dict:
    rows = [m for m in body["per_model"] if m["model_id"] == model_id]
    assert rows, f"{model_id} not in per_model: {body['per_model']}"
    return rows[0]


# ---------------------------------------------------------------------------
# Error branches: 404 / 403 / 400
# ---------------------------------------------------------------------------


class TestErrorBranches:
    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(
        self, async_test_client, async_test_db
    ):
        """Unknown project_id → 404 'Project not found' (first guard)."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id="does-not-exist-" + uuid.uuid4().hex,
                mode="generation",
                model_ids=[PRICED_MODEL],
            )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Project not found"

    @pytest.mark.asyncio
    async def test_access_denied_returns_403(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin who is not the creator of a PRIVATE project gets
        403 'Access denied'. The project exists (passes the 404 guard) but
        check_project_accessible_async returns False for is_private projects
        with no membership for a non-creator non-superadmin requester."""
        creator = await _seed_user(async_test_db, is_superadmin=True)
        actor = await _seed_user(async_test_db, is_superadmin=False)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, creator, is_private=True)
        pid = project.id
        await async_test_db.commit()
        # actor is not superadmin and not the project creator (creator is).
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_no_target_models_returns_400(
        self, async_test_client, async_test_db
    ):
        """generation mode with an empty model_ids list → 400 (the
        'model_ids required' guard, distinct from a 422)."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[],
            )
        assert resp.status_code == 400, resp.text
        assert "model_ids required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_evaluation_no_judge_or_model_returns_400(
        self, async_test_client, async_test_db
    ):
        """evaluation mode with neither judge_models nor model_ids → same
        400 guard (target_models stays empty)."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                model_ids=[],
                judge_models=[],
            )
        assert resp.status_code == 400, resp.text
        assert "model_ids required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_project_with_no_tasks_returns_400(
        self, async_test_client, async_test_db
    ):
        """A project that exists and is accessible but has zero tasks → 400
        'Project has no tasks to estimate against'."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=0)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
            )
        assert resp.status_code == 400, resp.text
        assert "no tasks" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Validation (422) branches
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.asyncio
    async def test_runs_per_call_above_max_rejected(
        self, async_test_client, async_test_db
    ):
        """runs_per_call has ge=1, le=25 — 26 fails Pydantic validation."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                runs_per_call=26,
            )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_samples_per_task_below_min_rejected(
        self, async_test_client, async_test_db
    ):
        """samples_per_task has ge=1 — 0 fails validation."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                samples_per_task=0,
            )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_invalid_mode_rejected(
        self, async_test_client, async_test_db
    ):
        """mode is Literal['generation','evaluation'] — anything else → 422."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="bogus-mode",
                model_ids=[PRICED_MODEL],
            )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_generation_mode_with_judge_models_rejected(
        self, async_test_client, async_test_db
    ):
        """The cross-mode validator rejects judge_models in generation mode
        with a 422 naming the offending key."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                judge_models=["some-judge"],
            )
        assert resp.status_code == 422, resp.text
        assert "judge_models" in resp.text

    @pytest.mark.asyncio
    async def test_generation_mode_with_annotator_ids_rejected(
        self, async_test_client, async_test_db
    ):
        """annotator_user_ids is eval-only — set in generation mode → 422."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                annotator_user_ids=["annotator-test-id"],
            )
        assert resp.status_code == 422, resp.text
        assert "annotator_user_ids" in resp.text


# ---------------------------------------------------------------------------
# Pricing branches: unknown / free / priced
# ---------------------------------------------------------------------------


class TestPricingBranches:
    @pytest.mark.asyncio
    async def test_unknown_model_id_pricing_unknown_zero_cost(
        self, async_test_client, async_test_db
    ):
        """A model id with no llm_models row → _resolve_pricing None →
        pricing_known False, all dollar fields 0, but the model still
        appears in per_model and cells_to_generate is computed."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor, num_tasks=4)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=["totally-unknown-model"],
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        row = _per_model(body, "totally-unknown-model")
        assert row["pricing_known"] is False
        assert row["per_call_usd"] == 0.0
        assert row["per_run_usd"] == 0.0
        assert row["total_usd"] == 0.0
        # generation_mode unset → all cells fire: 4 tasks × 1 structure (None).
        assert row["cells_to_generate"] == 4
        assert body["total_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_free_model_both_costs_null_pricing_unknown(
        self, async_test_client, async_test_db
    ):
        """A model whose cost columns are both NULL → _resolve_pricing
        returns None (free model branch) → pricing_known False even though
        the row exists in llm_models."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, FREE_MODEL, input_cost=None, output_cost=None)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[FREE_MODEL],
            )
        assert body_resp.status_code == 200, body_resp.text
        row = _per_model(body_resp.json(), FREE_MODEL)
        assert row["pricing_known"] is False
        assert row["total_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_priced_model_produces_nonzero_cost(
        self, async_test_client, async_test_db
    ):
        """A fully-priced model over a project with tasks → pricing_known
        True and a positive total_usd (tokens × price)."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = await _seed_project(async_test_db, actor, num_tasks=3)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        row = _per_model(body, PRICED_MODEL)
        assert row["pricing_known"] is True
        assert row["per_call_usd"] > 0.0
        assert row["total_usd"] > 0.0
        assert body["total_usd"] == row["total_usd"]
        # token breakdown is populated (not the unavailable fallback).
        assert body["token_estimate"]["encoding"] != "unavailable"

    @pytest.mark.asyncio
    async def test_mixed_priced_and_unknown_models_sum(
        self, async_test_client, async_test_db
    ):
        """Two models in one request: one priced, one unknown. The loop must
        emit a per_model row for each and total_usd equals only the priced
        model's contribution."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL, "unknown-x"],
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        assert len(body["per_model"]) == 2
        priced = _per_model(body, PRICED_MODEL)
        unknown = _per_model(body, "unknown-x")
        assert priced["pricing_known"] is True
        assert unknown["pricing_known"] is False
        assert unknown["total_usd"] == 0.0
        assert body["total_usd"] == priced["total_usd"]

    @pytest.mark.asyncio
    async def test_all_models_unknown_token_estimate_present(
        self, async_test_client, async_test_db
    ):
        """When no model has pricing the response still surfaces a token
        breakdown (the token_breakdown-is-None fallback is NOT hit because
        the per-model loop computes tokens before the pricing check)."""
        actor = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=["unknown-a", "unknown-b"],
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        assert body["total_usd"] == 0.0
        assert all(m["pricing_known"] is False for m in body["per_model"])
        assert "token_estimate" in body


# ---------------------------------------------------------------------------
# Generation cells_to_generate branches (all vs missing) + DB state
# ---------------------------------------------------------------------------


class TestGenerationCells:
    @pytest.mark.asyncio
    async def test_mode_all_counts_every_task(
        self, async_test_client, async_test_db
    ):
        """generation_mode='all' counts every (task × structure) cell even
        when generations already exist. 5 tasks, one structure (None) → 5."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=5)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="all",
            )
        assert body_resp.status_code == 200, body_resp.text
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 5

    @pytest.mark.asyncio
    async def test_mode_all_with_structure_keys_multiplies(
        self, async_test_client, async_test_db
    ):
        """Two structure_keys × 3 tasks → 6 cells under mode='all'."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=3)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="all",
                structure_keys=["s1", "s2"],
            )
        assert body_resp.status_code == 200, body_resp.text
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 6

    @pytest.mark.asyncio
    async def test_mode_missing_skips_completed_counts_failed(
        self, async_test_client, async_test_db
    ):
        """generation_mode='missing' counts only cells whose latest
        ResponseGeneration is failed or absent. We seed 4 tasks: 2 completed
        (skipped), 1 failed (counted), 1 with no row (counted) → 2 cells.

        Asserts the persisted ResponseGeneration rows that drive the count,
        then asserts the endpoint's cells_to_generate matches."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=4)
        pid = project.id
        tasks = (
            (
                await async_test_db.execute(
                    select(Task)
                    .where(Task.project_id == pid)
                    .order_by(Task.inner_id)
                )
            )
            .scalars()
            .all()
        )
        # task[0], task[1]: completed (skipped under missing)
        # task[2]: failed (counted); task[3]: no row at all (counted)
        statuses = ["completed", "completed", "failed"]
        for task, status in zip(tasks, statuses):
            async_test_db.add(ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=pid,
                task_id=task.id,
                model_id=PRICED_MODEL,
                structure_key=None,
                status=status,
                responses_generated=1 if status == "completed" else 0,
                created_by=actor.id,
                created_at=datetime.utcnow(),
            ))
        await async_test_db.commit()

        # DB-state assertion: 3 rows seeded, statuses as expected.
        rows = (
            (
                await async_test_db.execute(
                    select(ResponseGeneration).where(
                        ResponseGeneration.project_id == pid,
                        ResponseGeneration.model_id == PRICED_MODEL,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 3
        assert sorted(r.status for r in rows) == ["completed", "completed", "failed"]

        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="missing",
            )
        assert body_resp.status_code == 200, body_resp.text
        # failed(1) + absent(1) = 2 cells to (re)generate.
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 2

    @pytest.mark.asyncio
    async def test_mode_missing_all_completed_yields_zero_cells(
        self, async_test_client, async_test_db
    ):
        """Every task already has a completed generation → missing counts 0
        and total cost is 0 even for a priced model."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = await _seed_project(async_test_db, actor, num_tasks=3)
        pid = project.id
        tasks = (
            (await async_test_db.execute(select(Task).where(Task.project_id == pid)))
            .scalars()
            .all()
        )
        for task in tasks:
            async_test_db.add(ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=pid,
                task_id=task.id,
                model_id=PRICED_MODEL,
                structure_key=None,
                status="completed",
                responses_generated=1,
                created_by=actor.id,
                created_at=datetime.utcnow(),
            ))
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="missing",
            )
        assert body_resp.status_code == 200, body_resp.text
        row = _per_model(body_resp.json(), PRICED_MODEL)
        assert row["cells_to_generate"] == 0
        assert row["total_usd"] == 0.0


# ---------------------------------------------------------------------------
# Per-model max_tokens override + reasoning-tier utilization
# ---------------------------------------------------------------------------


class TestModelParameterBranches:
    @pytest.mark.asyncio
    async def test_per_model_max_tokens_override_raises_output(
        self, async_test_client, async_test_db
    ):
        """selected_configuration.model_configs[<model>].max_tokens overrides
        the project default, so a higher per-model cap yields a larger
        output_estimate. Two priced models, identical except the override:
        the overridden one must cost more per call."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        override_model = "test-override-model"
        await _seed_model(async_test_db, override_model, input_cost=10.0, output_cost=30.0)
        gen_config = {
            "selected_configuration": {
                "parameters": {"max_tokens": 1000},
                "model_configs": {override_model: {"max_tokens": 16000}},
            }
        }
        project = await _seed_project(
            async_test_db, actor,
            num_tasks=3, generation_config=gen_config,
        )
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL, override_model],
                generation_mode="all",
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        base = _per_model(body, PRICED_MODEL)
        overridden = _per_model(body, override_model)
        # Both priced, same input; the 16k-cap model has a larger output
        # contribution → strictly larger per_call_usd.
        assert overridden["per_call_usd"] > base["per_call_usd"]

    @pytest.mark.asyncio
    async def test_reasoning_model_higher_utilization(
        self, async_test_client, async_test_db
    ):
        """A model whose catalog entry declares default_config.reasoning_config
        is reasoning-tier → 0.9 output utilization vs 0.6 for a plain model.
        With identical pricing and the same max_tokens, the reasoning model's
        per_call_usd is strictly larger."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        await _seed_model(
            async_test_db, REASONING_MODEL,
            input_cost=10.0, output_cost=30.0,
            default_config={"reasoning_config": {"effort": "high"}},
        )
        project = await _seed_project(async_test_db, actor, num_tasks=3)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL, REASONING_MODEL],
                generation_mode="all",
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        plain = _per_model(body, PRICED_MODEL)
        reasoning = _per_model(body, REASONING_MODEL)
        # 0.9 vs 0.6 utilization over the same max_tokens & output price.
        assert reasoning["per_call_usd"] > plain["per_call_usd"]

    @pytest.mark.asyncio
    async def test_reasoning_via_recommended_parameters(
        self, async_test_client, async_test_db
    ):
        """The other reasoning-tier signal: recommended_parameters.default
        carrying a reasoning_effort value also flips utilization to 0.9."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        rec_model = "test-rec-reasoning-model"
        await _seed_model(
            async_test_db, rec_model,
            input_cost=10.0, output_cost=30.0,
            recommended_parameters={"default": {"reasoning_effort": "medium"}},
        )
        project = await _seed_project(async_test_db, actor, num_tasks=3)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL, rec_model],
                generation_mode="all",
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        plain = _per_model(body, PRICED_MODEL)
        reasoning = _per_model(body, rec_model)
        assert reasoning["per_call_usd"] > plain["per_call_usd"]


# ---------------------------------------------------------------------------
# Response note text branches (mode + generation_mode)
# ---------------------------------------------------------------------------


class TestNoteText:
    @pytest.mark.asyncio
    async def test_generation_all_note_mentions_every_cell(
        self, async_test_client, async_test_db
    ):
        """generation_mode != 'missing' → note says 'every (task × structure)
        cell' and carries the generation utilization sentence."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="all",
            )
        assert body_resp.status_code == 200, body_resp.text
        note = body_resp.json()["note"]
        assert "every (task × structure) cell" in note
        assert "Output utilization is 90 %" in note

    @pytest.mark.asyncio
    async def test_generation_missing_note_mentions_actually_fire(
        self, async_test_client, async_test_db
    ):
        """generation_mode == 'missing' → note says cells that would
        'actually fire'."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="generation",
                model_ids=[PRICED_MODEL],
                generation_mode="missing",
            )
        assert body_resp.status_code == 200, body_resp.text
        note = body_resp.json()["note"]
        assert "actually fire" in note

    @pytest.mark.asyncio
    async def test_evaluation_note_mentions_judge_utilization(
        self, async_test_client, async_test_db
    ):
        """evaluation mode → note carries the 15 %-of-max_tokens judge
        sentence, and the response mode echoes 'evaluation'."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[PRICED_MODEL],
            )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        assert body["mode"] == "evaluation"
        assert "output utilization is 15 %" in body["note"]

    @pytest.mark.asyncio
    async def test_evaluation_with_configs_appends_extra_caveat(
        self, async_test_client, async_test_db
    ):
        """evaluation + evaluation_configs → the extra per-judge caveat
        sentence is appended to the note."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, PRICED_MODEL)
        project = await _seed_project(async_test_db, actor, num_tasks=2)
        pid = project.id
        await async_test_db.commit()
        with _as_user(actor):
            body_resp = await _post(
                async_test_client,
                project_id=pid,
                mode="evaluation",
                judge_models=[PRICED_MODEL],
                evaluation_configs=[
                    {"metric": "exact_match", "prediction_fields": ["model:answer"]},
                ],
            )
        assert body_resp.status_code == 200, body_resp.text
        assert "count cells per-judge" in body_resp.json()["note"]
