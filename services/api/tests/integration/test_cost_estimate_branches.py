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
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import LLMModel, ResponseGeneration, User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Seeding helpers (mirrors test_cost_estimate_subject_count.py idioms)
# ---------------------------------------------------------------------------


PRICED_MODEL = "test-priced-model"
FREE_MODEL = "test-free-model"
REASONING_MODEL = "test-reasoning-model"


def _seed_model(
    test_db: Session,
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
    if test_db.query(LLMModel).filter(LLMModel.id == model_id).first():
        return
    test_db.add(LLMModel(
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
    test_db.commit()


def _seed_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    *,
    num_tasks: int = 3,
    is_private: bool = False,
    generation_config: Optional[dict] = None,
    link_org: bool = True,
) -> Project:
    """Create a project owned by the admin (test_users[0]) with `num_tasks`
    tasks. Links it to test_org by default so org-context access checks pass
    for members; set link_org=False / is_private=True to build an
    inaccessible project for the 403 path."""
    admin = test_users[0]
    project = Project(
        id=str(uuid.uuid4()),
        title="cost-branches-test",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=admin.id,
        is_published=True,
        is_private=is_private,
        generation_config=generation_config,
    )
    test_db.add(project)
    test_db.flush()
    if link_org:
        test_db.add(ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=admin.id,
        ))
    test_db.flush()
    for i in range(num_tasks):
        test_db.add(Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"q": f"Q{i + 1}"},
            created_by=admin.id,
            updated_by=admin.id,
        ))
    test_db.commit()
    return project


def _post(client: TestClient, headers, **body):
    return client.post("/api/llm-models/cost-estimate", json=body, headers=headers)


def _per_model(body: Dict, model_id: str) -> Dict:
    rows = [m for m in body["per_model"] if m["model_id"] == model_id]
    assert rows, f"{model_id} not in per_model: {body['per_model']}"
    return rows[0]


# ---------------------------------------------------------------------------
# Error branches: 404 / 403 / 400
# ---------------------------------------------------------------------------


class TestErrorBranches:
    def test_project_not_found_returns_404(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Unknown project_id → 404 'Project not found' (first guard)."""
        _seed_model(test_db, PRICED_MODEL)
        resp = _post(
            client, auth_headers["admin"],
            project_id="does-not-exist-" + uuid.uuid4().hex,
            mode="generation",
            model_ids=[PRICED_MODEL],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Project not found"

    def test_access_denied_returns_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A non-superadmin who is not the creator of a PRIVATE project gets
        403 'Access denied'. The project exists (passes the 404 guard) but
        check_project_accessible returns False for is_private projects unless
        the requester is the creator."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(
            test_db, test_users, test_org,
            is_private=True, link_org=False,
        )
        # annotator is not superadmin and not the project creator (admin is).
        resp = _post(
            client, auth_headers["annotator"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_no_target_models_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """generation mode with an empty model_ids list → 400 (the
        'model_ids required' guard, distinct from a 422)."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[],
        )
        assert resp.status_code == 400, resp.text
        assert "model_ids required" in resp.json()["detail"]

    def test_evaluation_no_judge_or_model_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """evaluation mode with neither judge_models nor model_ids → same
        400 guard (target_models stays empty)."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="evaluation",
            model_ids=[],
            judge_models=[],
        )
        assert resp.status_code == 400, resp.text
        assert "model_ids required" in resp.json()["detail"]

    def test_project_with_no_tasks_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A project that exists and is accessible but has zero tasks → 400
        'Project has no tasks to estimate against'."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=0)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
        )
        assert resp.status_code == 400, resp.text
        assert "no tasks" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Validation (422) branches
# ---------------------------------------------------------------------------


class TestValidation:
    def test_runs_per_call_above_max_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """runs_per_call has ge=1, le=25 — 26 fails Pydantic validation."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            runs_per_call=26,
        )
        assert resp.status_code == 422, resp.text

    def test_samples_per_task_below_min_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """samples_per_task has ge=1 — 0 fails validation."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            samples_per_task=0,
        )
        assert resp.status_code == 422, resp.text

    def test_invalid_mode_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """mode is Literal['generation','evaluation'] — anything else → 422."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="bogus-mode",
            model_ids=[PRICED_MODEL],
        )
        assert resp.status_code == 422, resp.text

    def test_generation_mode_with_judge_models_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The cross-mode validator rejects judge_models in generation mode
        with a 422 naming the offending key."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            judge_models=["some-judge"],
        )
        assert resp.status_code == 422, resp.text
        assert "judge_models" in resp.text

    def test_generation_mode_with_annotator_ids_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """annotator_user_ids is eval-only — set in generation mode → 422."""
        project = _seed_project(test_db, test_users, test_org)
        resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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
    def test_unknown_model_id_pricing_unknown_zero_cost(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A model id with no llm_models row → _resolve_pricing None →
        pricing_known False, all dollar fields 0, but the model still
        appears in per_model and cells_to_generate is computed."""
        project = _seed_project(test_db, test_users, test_org, num_tasks=4)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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

    def test_free_model_both_costs_null_pricing_unknown(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A model whose cost columns are both NULL → _resolve_pricing
        returns None (free model branch) → pricing_known False even though
        the row exists in llm_models."""
        _seed_model(test_db, FREE_MODEL, input_cost=None, output_cost=None)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[FREE_MODEL],
        )
        assert body_resp.status_code == 200, body_resp.text
        row = _per_model(body_resp.json(), FREE_MODEL)
        assert row["pricing_known"] is False
        assert row["total_usd"] == 0.0

    def test_priced_model_produces_nonzero_cost(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A fully-priced model over a project with tasks → pricing_known
        True and a positive total_usd (tokens × price)."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = _seed_project(test_db, test_users, test_org, num_tasks=3)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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

    def test_mixed_priced_and_unknown_models_sum(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Two models in one request: one priced, one unknown. The loop must
        emit a per_model row for each and total_usd equals only the priced
        model's contribution."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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

    def test_all_models_unknown_token_estimate_present(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """When no model has pricing the response still surfaces a token
        breakdown (the token_breakdown-is-None fallback is NOT hit because
        the per-model loop computes tokens before the pricing check)."""
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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
    def test_mode_all_counts_every_task(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """generation_mode='all' counts every (task × structure) cell even
        when generations already exist. 5 tasks, one structure (None) → 5."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=5)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            generation_mode="all",
        )
        assert body_resp.status_code == 200, body_resp.text
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 5

    def test_mode_all_with_structure_keys_multiplies(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Two structure_keys × 3 tasks → 6 cells under mode='all'."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=3)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            generation_mode="all",
            structure_keys=["s1", "s2"],
        )
        assert body_resp.status_code == 200, body_resp.text
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 6

    def test_mode_missing_skips_completed_counts_failed(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """generation_mode='missing' counts only cells whose latest
        ResponseGeneration is failed or absent. We seed 4 tasks: 2 completed
        (skipped), 1 failed (counted), 1 with no row (counted) → 2 cells.

        Asserts the persisted ResponseGeneration rows that drive the count,
        then asserts the endpoint's cells_to_generate matches."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=4)
        tasks = (
            test_db.query(Task)
            .filter(Task.project_id == project.id)
            .order_by(Task.inner_id)
            .all()
        )
        admin = test_users[0]
        # task[0], task[1]: completed (skipped under missing)
        # task[2]: failed (counted); task[3]: no row at all (counted)
        statuses = ["completed", "completed", "failed"]
        for task, status in zip(tasks, statuses):
            test_db.add(ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=project.id,
                task_id=task.id,
                model_id=PRICED_MODEL,
                structure_key=None,
                status=status,
                responses_generated=1 if status == "completed" else 0,
                created_by=admin.id,
                created_at=datetime.utcnow(),
            ))
        test_db.commit()

        # DB-state assertion: 3 rows seeded, statuses as expected.
        rows = (
            test_db.query(ResponseGeneration)
            .filter(
                ResponseGeneration.project_id == project.id,
                ResponseGeneration.model_id == PRICED_MODEL,
            )
            .all()
        )
        assert len(rows) == 3
        assert sorted(r.status for r in rows) == ["completed", "completed", "failed"]

        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            generation_mode="missing",
        )
        assert body_resp.status_code == 200, body_resp.text
        # failed(1) + absent(1) = 2 cells to (re)generate.
        assert _per_model(body_resp.json(), PRICED_MODEL)["cells_to_generate"] == 2

    def test_mode_missing_all_completed_yields_zero_cells(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Every task already has a completed generation → missing counts 0
        and total cost is 0 even for a priced model."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        project = _seed_project(test_db, test_users, test_org, num_tasks=3)
        admin = test_users[0]
        for task in test_db.query(Task).filter(Task.project_id == project.id).all():
            test_db.add(ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=project.id,
                task_id=task.id,
                model_id=PRICED_MODEL,
                structure_key=None,
                status="completed",
                responses_generated=1,
                created_by=admin.id,
                created_at=datetime.utcnow(),
            ))
        test_db.commit()
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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
    def test_per_model_max_tokens_override_raises_output(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """selected_configuration.model_configs[<model>].max_tokens overrides
        the project default, so a higher per-model cap yields a larger
        output_estimate. Two priced models, identical except the override:
        the overridden one must cost more per call."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        override_model = "test-override-model"
        _seed_model(test_db, override_model, input_cost=10.0, output_cost=30.0)
        gen_config = {
            "selected_configuration": {
                "parameters": {"max_tokens": 1000},
                "model_configs": {override_model: {"max_tokens": 16000}},
            }
        }
        project = _seed_project(
            test_db, test_users, test_org,
            num_tasks=3, generation_config=gen_config,
        )
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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

    def test_reasoning_model_higher_utilization(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A model whose catalog entry declares default_config.reasoning_config
        is reasoning-tier → 0.9 output utilization vs 0.6 for a plain model.
        With identical pricing and the same max_tokens, the reasoning model's
        per_call_usd is strictly larger."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        _seed_model(
            test_db, REASONING_MODEL,
            input_cost=10.0, output_cost=30.0,
            default_config={"reasoning_config": {"effort": "high"}},
        )
        project = _seed_project(test_db, test_users, test_org, num_tasks=3)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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

    def test_reasoning_via_recommended_parameters(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The other reasoning-tier signal: recommended_parameters.default
        carrying a reasoning_effort value also flips utilization to 0.9."""
        _seed_model(test_db, PRICED_MODEL, input_cost=10.0, output_cost=30.0)
        rec_model = "test-rec-reasoning-model"
        _seed_model(
            test_db, rec_model,
            input_cost=10.0, output_cost=30.0,
            recommended_parameters={"default": {"reasoning_effort": "medium"}},
        )
        project = _seed_project(test_db, test_users, test_org, num_tasks=3)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
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
    def test_generation_all_note_mentions_every_cell(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """generation_mode != 'missing' → note says 'every (task × structure)
        cell' and carries the generation utilization sentence."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            generation_mode="all",
        )
        assert body_resp.status_code == 200, body_resp.text
        note = body_resp.json()["note"]
        assert "every (task × structure) cell" in note
        assert "Output utilization is 90 %" in note

    def test_generation_missing_note_mentions_actually_fire(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """generation_mode == 'missing' → note says cells that would
        'actually fire'."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="generation",
            model_ids=[PRICED_MODEL],
            generation_mode="missing",
        )
        assert body_resp.status_code == 200, body_resp.text
        note = body_resp.json()["note"]
        assert "actually fire" in note

    def test_evaluation_note_mentions_judge_utilization(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """evaluation mode → note carries the 15 %-of-max_tokens judge
        sentence, and the response mode echoes 'evaluation'."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="evaluation",
            judge_models=[PRICED_MODEL],
        )
        assert body_resp.status_code == 200, body_resp.text
        body = body_resp.json()
        assert body["mode"] == "evaluation"
        assert "output utilization is 15 %" in body["note"]

    def test_evaluation_with_configs_appends_extra_caveat(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """evaluation + evaluation_configs → the extra per-judge caveat
        sentence is appended to the note."""
        _seed_model(test_db, PRICED_MODEL)
        project = _seed_project(test_db, test_users, test_org, num_tasks=2)
        body_resp = _post(
            client, auth_headers["admin"],
            project_id=project.id,
            mode="evaluation",
            judge_models=[PRICED_MODEL],
            evaluation_configs=[
                {"metric": "exact_match", "prediction_fields": ["model:answer"]},
            ],
        )
        assert body_resp.status_code == 200, body_resp.text
        assert "count cells per-judge" in body_resp.json()["note"]
