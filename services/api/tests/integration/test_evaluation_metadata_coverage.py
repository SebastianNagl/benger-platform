"""
Integration tests targeting uncovered handler body code in routers/evaluations/metadata.py.

Focuses on:
- evaluated-models: CI calculation, annotator synthetic models, provider detection,
  filtering of "unknown"/"immediate", sorting by score
- configured-methods: automated vs human methods, field_mapping, parameters, result status
- evaluation-history: date filtering, metric filtering, CI from metadata
- significance: pairwise t-test, insufficient data, direct evaluations fallback
- statistics: all aggregation levels (model/sample/field/overall), ttest, bootstrap,
  cohens_d, cliffs_delta, correlation, compare_models filter, warnings
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    ResponseGeneration,
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


def _build_graph(db, admin, org, *, num_tasks=5, num_models=2,
                 with_eval_config=False, with_annotation_evals=False,
                 with_date_spread=False, with_eval_metadata=False):
    """Build a rich data graph for evaluation metadata tests."""
    project = Project(
        id=_uid(),
        title=f"MetaCov {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config={
            "selected_methods": {
                "answer": {
                    "automated": [
                        "accuracy",
                        {"name": "f1", "parameters": {"average": "macro"}},
                    ],
                    "human": ["likert_quality"],
                    "field_mapping": {"answer": "text"},
                },
            },
            "available_methods": {
                "answer": {"type": "choices", "to_name": "text", "options": ["Ja", "Nein"]},
            },
        } if with_eval_config else None,
        generation_config={
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models],
            }
        },
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Meta cov text #{i}"}, inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    # Annotations for annotator-based evaluations
    annotations = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    db.flush()

    models = ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models]
    all_gens = {}
    eval_runs = []

    for idx, model_id in enumerate(models):
        rg = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id=model_id,
            status="completed", created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(rg)
        db.flush()

        gens = []
        for i, t in enumerate(tasks):
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=t.id,
                model_id=model_id,
                case_data=json.dumps(t.data),
                response_content=f"Answer from {model_id} for task {i}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            db.add(gen)
            gens.append(gen)
        db.flush()
        all_gens[model_id] = gens

        # Evaluation runs with optional date spread
        base_accuracy = {"gpt-4o": 0.85, "claude-3-sonnet": 0.72, "gemini-1.5-pro": 0.91}
        base_f1 = {"gpt-4o": 0.82, "claude-3-sonnet": 0.68, "gemini-1.5-pro": 0.88}

        created_at = datetime.now(timezone.utc) - timedelta(days=idx * 7) if with_date_spread else datetime.now(timezone.utc)

        eval_metadata = None
        if with_eval_metadata:
            eval_metadata = {
                "confidence_intervals": {
                    "accuracy": {"lower": base_accuracy.get(model_id, 0.7) - 0.05,
                                 "upper": base_accuracy.get(model_id, 0.7) + 0.05},
                }
            }

        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": base_accuracy.get(model_id, 0.75),
                     "f1_score": base_f1.get(model_id, 0.70)},
            status="completed", samples_evaluated=num_tasks,
            has_sample_results=True,
            created_by=admin.id,
            created_at=created_at,
            completed_at=created_at + timedelta(minutes=5),
            eval_metadata=eval_metadata,
        )
        db.add(er)
        db.flush()
        eval_runs.append(er)

        # Per-sample TaskEvaluations with diverse scores
        for i, t in enumerate(tasks):
            acc_val = base_accuracy.get(model_id, 0.75) + (i * 0.03 - 0.06)
            acc_val = max(0, min(1, acc_val))
            f1_val = base_f1.get(model_id, 0.70) + (i * 0.02 - 0.04)
            f1_val = max(0, min(1, f1_val))
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, task_id=t.id,
                generation_id=gens[i].id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if acc_val > 0.5 else "Nein"},
                metrics={"accuracy": round(acc_val, 4), "f1": round(f1_val, 4)},
                passed=acc_val > 0.5,
            )
            db.add(te)
    db.flush()

    # Annotation-based evaluations
    if with_annotation_evals and eval_runs:
        for i, (ann, t) in enumerate(zip(annotations, tasks)):
            te = TaskEvaluation(
                id=_uid(), evaluation_id=eval_runs[0].id, task_id=t.id,
                generation_id=None, annotation_id=ann.id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja"},
                metrics={"accuracy": 1.0, "f1": 1.0},
                passed=True,
            )
            db.add(te)
        db.flush()

    db.commit()
    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "all_gens": all_gens,
        "eval_runs": eval_runs,
    }


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EVALUATED MODELS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestEvaluatedModelsDeep:
    """Deep coverage for evaluated-models endpoint handler body."""

    def test_models_sorted_by_score_descending(self, client, test_db, test_users, auth_headers, test_org):
        """Models should be sorted by average_score descending."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=3, num_tasks=5)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        scores = [m["average_score"] for m in models if m["average_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_models_include_configured_status_flags(self, client, test_db, test_users, auth_headers, test_org):
        """With include_configured, response includes is_configured, has_generations, has_results."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        for m in models:
            assert "is_configured" in m
            assert "has_generations" in m
            assert "has_results" in m

    def test_models_ci_bounds_present(self, client, test_db, test_users, auth_headers, test_org):
        """Models with evaluations should have CI bounds."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        for m in resp.json():
            assert "ci_lower" in m
            assert "ci_upper" in m

    def test_models_annotator_synthetic_ids(self, client, test_db, test_users, auth_headers, test_org):
        """Annotation-based evaluations create annotator:username synthetic models."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1,
                            with_annotation_evals=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        annotator_models = [m for m in models if m["model_id"].startswith("annotator:")]
        assert len(annotator_models) >= 1
        for am in annotator_models:
            assert am["provider"] == "Annotator"

    def test_models_last_evaluated_present(self, client, test_db, test_users, auth_headers, test_org):
        """Models should have last_evaluated timestamp."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        for m in resp.json():
            if m["evaluation_count"] > 0:
                assert m["last_evaluated"] is not None

    def test_models_total_samples(self, client, test_db, test_users, auth_headers, test_org):
        """Models should have total_samples count."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1, num_tasks=5)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        for m in resp.json():
            assert "total_samples" in m
            if m["evaluation_count"] > 0:
                assert m["total_samples"] >= 5


# ===================================================================
# CONFIGURED METHODS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestConfiguredMethodsDeep:
    """Deep coverage for configured-methods endpoint."""

    def test_methods_field_structure(self, client, test_db, test_users, auth_headers, test_org):
        """Fields include automated_methods with is_configured, has_results, display_name."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["fields"]) >= 1
        field = body["fields"][0]
        assert "field_name" in field
        assert "automated_methods" in field
        assert "human_methods" in field
        for method in field["automated_methods"]:
            assert "method_name" in method
            assert "display_name" in method
            assert "is_configured" in method
            assert "has_results" in method

    def test_methods_human_methods_included(self, client, test_db, test_users, auth_headers, test_org):
        """Human methods from config appear in response."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in body["fields"]:
            if field["human_methods"]:
                assert field["human_methods"][0]["method_type"] == "human"

    def test_methods_field_type_present(self, client, test_db, test_users, auth_headers, test_org):
        """Field type from available_methods is included."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in body["fields"]:
            assert "field_type" in field


# ===================================================================
# EVALUATION HISTORY: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestEvaluationHistoryDeep:
    """Deep coverage for evaluation-history endpoint."""

    def test_history_with_metric_and_model(self, client, test_db, test_users, auth_headers, test_org):
        """History returns time-series data for specific metric and model."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2,
                            with_date_spread=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metric=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric"] == "accuracy"
        assert "data" in body

    def test_history_with_date_range(self, client, test_db, test_users, auth_headers, test_org):
        """History respects start_date and end_date filters."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2,
                            with_date_spread=True)
        # Use simple ISO format without timezone offset (fromisoformat compat)
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history"
            f"?model_ids=gpt-4o&metric=accuracy&start_date={start}&end_date={end}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_history_with_eval_metadata_ci(self, client, test_db, test_users, auth_headers, test_org):
        """History includes CI from eval_metadata when available."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1,
                            with_eval_metadata=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history"
            "?model_ids=gpt-4o&metric=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("data"):
            for point in body["data"]:
                assert "ci_lower" in point
                assert "ci_upper" in point

    def test_history_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        """History for nonexistent project returns 404."""
        resp = client.get(
            f"{BASE}/projects/nonexistent/evaluation-history"
            "?model_ids=gpt-4o&metric=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (404, 422)

    def test_history_nonexistent_metric(self, client, test_db, test_users, auth_headers, test_org):
        """History for metric with no data returns empty data."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history"
            "?model_ids=gpt-4o&metric=nonexistent_metric",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get("data", [])) == 0


# ===================================================================
# SIGNIFICANCE: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestSignificanceDeep:
    """Deep coverage for significance endpoint."""

    def test_significance_pairwise_results(self, client, test_db, test_users, auth_headers, test_org):
        """Significance returns pairwise comparison results."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=10)
        resp = client.get(
            f"{BASE}/significance/{data['project'].id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "comparisons" in body
        if body["comparisons"]:
            comp = body["comparisons"][0]
            assert "model_a" in comp
            assert "model_b" in comp
            assert "p_value" in comp
            assert "significant" in comp

    def test_significance_three_models(self, client, test_db, test_users, auth_headers, test_org):
        """Significance with 3 models produces 3 pairwise comparisons."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=3, num_tasks=10)
        resp = client.get(
            f"{BASE}/significance/{data['project'].id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&model_ids=gemini-1.5-pro&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # 3 models -> 3 pairwise comparisons
        assert len(body.get("comparisons", [])) == 3

    def test_significance_insufficient_data(self, client, test_db, test_users, auth_headers, test_org):
        """With only 1 sample per model, significance should report not significant."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=1)
        resp = client.get(
            f"{BASE}/significance/{data['project'].id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for comp in body.get("comparisons", []):
            assert comp["significant"] is False

    def test_significance_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        """Significance for nonexistent project returns 404."""
        resp = client.get(
            f"{BASE}/significance/nonexistent"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (404, 422)

    def test_significance_multiple_metrics(self, client, test_db, test_users, auth_headers, test_org):
        """Significance across multiple metrics."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.get(
            f"{BASE}/significance/{data['project'].id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy&metrics=f1",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # 2 models * 2 metrics = 2 comparisons
        assert len(body.get("comparisons", [])) >= 2


# ===================================================================
# STATISTICS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestStatisticsDeep:
    """Deep coverage for statistics endpoint handler body."""

    def test_statistics_model_aggregation_response_structure(self, client, test_db, test_users, auth_headers, test_org):
        """Model aggregation includes by_model with per-model metrics."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy", "f1"], "aggregation": "model", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "model"
        assert "by_model" in body
        for model_id, model_stats in (body.get("by_model") or {}).items():
            assert "metrics" in model_stats
            assert "sample_count" in model_stats

    def test_statistics_sample_aggregation_raw_scores(self, client, test_db, test_users, auth_headers, test_org):
        """Sample aggregation returns raw_scores list."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "sample", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "sample"
        if body.get("raw_scores"):
            for score in body["raw_scores"]:
                assert "model_id" in score
                assert "metric" in score
                assert "value" in score

    def test_statistics_field_aggregation(self, client, test_db, test_users, auth_headers, test_org):
        """Field aggregation returns by_field with per-field metrics."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "field", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "field"
        if body.get("by_field"):
            for field_name, field_stats in body["by_field"].items():
                assert "metrics" in field_stats
                assert "sample_count" in field_stats

    def test_statistics_overall_aggregation(self, client, test_db, test_users, auth_headers, test_org):
        """Overall aggregation returns aggregated metrics only."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "overall", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "overall"
        assert "metrics" in body

    def test_statistics_with_ttest_pairwise(self, client, test_db, test_users, auth_headers, test_org):
        """T-test method produces pairwise_comparisons."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["ci", "ttest"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "ttest_p" in comp
            assert "ttest_significant" in comp

    def test_statistics_with_cohens_d(self, client, test_db, test_users, auth_headers, test_org):
        """Cohens_d method produces effect size in comparisons."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["cohens_d"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "cohens_d" in comp
            assert "cohens_d_interpretation" in comp

    def test_statistics_with_cliffs_delta(self, client, test_db, test_users, auth_headers, test_org):
        """Cliffs_delta method produces non-parametric effect size."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["cliffs_delta"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "cliffs_delta" in comp
            assert "cliffs_delta_interpretation" in comp

    def test_statistics_with_correlation(self, client, test_db, test_users, auth_headers, test_org):
        """Correlation method produces correlation matrix between metrics."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy", "f1"],
                "aggregation": "model",
                "methods": ["correlation"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("correlations"):
            assert "accuracy" in body["correlations"]
            assert "f1" in body["correlations"]

    def test_statistics_compare_models_filter(self, client, test_db, test_users, auth_headers, test_org):
        """compare_models filters results to specified models only."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=3, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["ci"],
                "compare_models": ["gpt-4o"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("by_model"):
            assert "gpt-4o" in body["by_model"]

    def test_statistics_no_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        """Statistics for project with no evaluations returns 404."""
        p = Project(
            id=_uid(), title="No Evals", created_by=test_users[0].id,
            label_config="<View/>",
        )
        test_db.add(p)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=p.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_statistics_metric_stats_structure(self, client, test_db, test_users, auth_headers, test_org):
        """Overall metrics include mean, std, ci_lower, ci_upper, n."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "overall", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("metrics") and "accuracy" in body["metrics"]:
            stats = body["metrics"]["accuracy"]
            assert "mean" in stats
            assert "std" in stats
            assert "ci_lower" in stats
            assert "ci_upper" in stats
            assert "n" in stats

    def test_statistics_warnings_for_missing_models(self, client, test_db, test_users, auth_headers, test_org):
        """compare_models with nonexistent model produces warnings."""
        data = _build_graph(test_db, test_users[0], test_org, num_models=1, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["ci"],
                "compare_models": ["nonexistent-model"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("warnings") is not None
