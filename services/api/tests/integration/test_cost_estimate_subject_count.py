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
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Generation, LLMModel, ResponseGeneration, User
from project_models import Annotation, Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Fixture builders (focused on what the cost endpoint reads)
# ---------------------------------------------------------------------------


def _seed_judge_pricing(test_db: Session, judge_id: str) -> None:
    """Cost endpoint pulls per-token pricing from the llm_models table.
    Seed a row for the judge model so the formula multiplies cleanly."""
    if test_db.query(LLMModel).filter(LLMModel.id == judge_id).first():
        return
    test_db.add(LLMModel(
        id=judge_id,
        name=judge_id,
        provider="anthropic",
        model_type="chat",
        capabilities=["text_generation"],
        input_cost_per_million=1.0,
        output_cost_per_million=5.0,
        is_active=True,
    ))
    test_db.commit()


def _seed_project_with_subjects(
    test_db: Session,
    test_users: List[User],
    test_org,
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
    admin = test_users[0]

    project = Project(
        id=str(uuid.uuid4()),
        title="cost-subject-count-test",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=admin.id,
        is_published=True,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=admin.id,
    ))
    test_db.flush()

    # Tasks
    tasks: List[Task] = []
    for i in range(num_tasks):
        t = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"q": f"Q{i + 1}"},
            created_by=admin.id,
            updated_by=admin.id,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()

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
                created_by=admin.id,
            )
            test_db.add(rg)
            test_db.flush()
            test_db.add(Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=task.id,
                model_id=model_id,
                case_data="...",
                response_content="...",
                status="completed",
                parse_status="success",
            ))
    test_db.flush()

    # Annotators — reuse N test users; each annotates every task once.
    # Total annotations: num_tasks × num_annotators.
    annotator_user_ids = [u.id for u in test_users[:num_annotators]]
    for task in tasks:
        for uid in annotator_user_ids:
            test_db.add(Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=project.id,
                completed_by=uid,
                result=[],
                was_cancelled=False,
                created_at=datetime.utcnow(),
            ))
    test_db.commit()

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


def _post_estimate(client: TestClient, auth_headers, **body) -> Dict:
    """Post to the cost-estimate endpoint and return the parsed body. Asserts
    a 2xx so failed requests don't masquerade as zero subject_counts."""
    resp = client.post(
        "/api/llm-models/cost-estimate",
        json=body,
        headers=auth_headers["admin"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSubjectCount:
    """The subject_count math is the heart of the new cost preview. Each
    test pins one degree of freedom."""

    def test_legacy_no_configs_yields_zero_subject_count(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """When the modal doesn't pass `evaluation_configs`, the endpoint
        falls back to the legacy tasks-count formula and reports zero
        subjects (the new path is opt-in via configs being supplied)."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            runs_per_call=1,
        )
        assert body["subject_count"] == 0

    def test_llm_field_config_counts_generations(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """One LLM-side prediction_field × N generations = N cells."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            runs_per_call=1,
            evaluation_configs=[
                {"metric": "exact_match", "prediction_fields": ["model:answer"]},
            ],
        )
        assert body["subject_count"] == data["expected_generation_count"]

    def test_human_field_config_counts_annotations(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """One human-side prediction_field × M annotations = M cells."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            runs_per_call=1,
            evaluation_configs=[
                {"metric": "exact_match", "prediction_fields": ["human:answer"]},
            ],
        )
        assert body["subject_count"] == data["expected_annotation_count"]

    def test_falloesung_unprefixed_routed_to_annotations(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The shared classifier's backward-compat rule: for
        `llm_judge_falloesung` with no `human:` prefix, the unprefixed
        field counts against annotations, not generations. This was the
        original motivating bug — getting it wrong here means the cost
        preview lies for the metric the feature was built for."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            runs_per_call=1,
            evaluation_configs=[
                {"metric": "llm_judge_falloesung", "prediction_fields": ["loesung"]},
            ],
        )
        # Single unprefixed field × annotation count.
        assert body["subject_count"] == data["expected_annotation_count"]

    def test_model_ids_filter_narrows_generation_subjects(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """`model_ids=[m0]` should drop the count by half when there are 2
        generation models in the project."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(
            test_db, test_users, test_org,
            num_tasks=4, num_generation_models=2,
        )
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            model_ids=[data["model_ids"][0]],
            runs_per_call=1,
            evaluation_configs=[
                {"metric": "exact_match", "prediction_fields": ["model:answer"]},
            ],
        )
        # Only one model selected → half the generations.
        expected = data["expected_generation_count"] // 2
        assert body["subject_count"] == expected

    def test_annotator_user_ids_filter_narrows_annotation_subjects(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """`annotator_user_ids=[uid_0]` should drop the count by half when
        there are 2 annotators each annotating every task."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(
            test_db, test_users, test_org,
            num_tasks=4, num_annotators=2,
        )
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            annotator_user_ids=[data["annotator_user_ids"][0]],
            runs_per_call=1,
            evaluation_configs=[
                {"metric": "exact_match", "prediction_fields": ["human:answer"]},
            ],
        )
        expected = data["expected_annotation_count"] // 2
        assert body["subject_count"] == expected

    def test_zero_subjects_with_configs_produces_zero_cost(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A1 critical-bug regression test: when the user narrows scope to
        a model with no generations, `subject_count` is zero AND the
        formula stays in subject-count mode (does NOT fall back to the
        full-sweep tasks formula). Old code flipped back and showed a
        full-sweep cost — this asserts the gate is on
        `bool(evaluation_configs)`, not on `subject_count > 0`."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
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

    def test_mixed_human_and_llm_fields_sum_correctly(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A config with both a `model:` and a `human:` prediction_field
        contributes (gen_count + ann_count) cells per run."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
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
        expected = (
            data["expected_generation_count"] + data["expected_annotation_count"]
        )
        assert body["subject_count"] == expected


class TestRequestValidation:
    """B3 cross-mode rejection — validator integration check."""

    def test_generation_mode_with_evaluation_configs_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The validator rejects payloads that mix mode=generation with
        eval-only keys. Returns 422 (Pydantic validation), not 400."""
        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        resp = client.post(
            "/api/llm-models/cost-estimate",
            json={
                "project_id": data["project"].id,
                "mode": "generation",
                "model_ids": ["gpt-5"],
                "evaluation_configs": [
                    {"metric": "exact_match", "prediction_fields": ["x"]}
                ],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422
        assert "evaluation_configs" in resp.text

    def test_estimated_at_present_on_response(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """E4: the response carries an ISO timestamp the frontend uses for
        the staleness tooltip. Must be ISO-8601 parseable."""
        from datetime import datetime as _dt

        _seed_judge_pricing(test_db, JUDGE_ID)
        data = _seed_project_with_subjects(test_db, test_users, test_org)
        body = _post_estimate(
            client, auth_headers,
            project_id=data["project"].id,
            mode="evaluation",
            judge_models=[JUDGE_ID],
            runs_per_call=1,
        )
        assert "estimated_at" in body
        # fromisoformat tolerates the +00:00 suffix from datetime.now(tz=utc).
        _dt.fromisoformat(body["estimated_at"])
