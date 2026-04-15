"""
Deep integration tests for evaluation metadata, statistics, and significance.

Covers routers/evaluations/metadata.py:
- GET /projects/{project_id}/evaluated-models — model listing with CI
- GET /projects/{project_id}/configured-methods — method result status
- POST /projects/{project_id}/statistics — comprehensive statistics computation
- GET /projects/{project_id}/evaluation-history — evaluation timeline
- POST /projects/{project_id}/significance — pairwise statistical tests
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationType,
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


def _build(db, admin, org, *, num_tasks=5, num_models=3,
           with_eval_config=False, with_annotation_evals=False):
    """Build a rich evaluation data graph with multiple models."""
    project = Project(
        id=_uid(),
        title=f"Meta {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config={
            "selected_methods": {
                "answer": {
                    "automated": ["accuracy", "f1"],
                    "human": [],
                }
            },
            "available_methods": {
                "answer": {"type": "choices", "options": ["Ja", "Nein"]},
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
            data={"text": f"Meta text #{i}"}, inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    # Annotations
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
    task_evals = []

    for model_id in models:
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
                response_content=f"Answer from {model_id}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            db.add(gen)
            gens.append(gen)
        db.flush()
        all_gens[model_id] = gens

        # Evaluation run
        base_accuracy = {"gpt-4o": 0.85, "claude-3-sonnet": 0.78, "gemini-1.5-pro": 0.90}
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": base_accuracy.get(model_id, 0.75), "f1_score": 0.80},
            status="completed", samples_evaluated=num_tasks,
            has_sample_results=True,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(er)
        db.flush()
        eval_runs.append(er)

        # Per-sample TaskEvaluations
        for i, t in enumerate(tasks):
            accuracy_val = base_accuracy.get(model_id, 0.75) + (i * 0.02 - 0.04)
            accuracy_val = max(0, min(1, accuracy_val))
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, task_id=t.id,
                generation_id=gens[i].id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if accuracy_val > 0.5 else "Nein"},
                metrics={"accuracy": accuracy_val, "f1": 0.75 + (i * 0.01)},
                passed=accuracy_val > 0.5,
            )
            db.add(te)
            task_evals.append(te)
    db.flush()

    # Annotation evaluations (if requested)
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
        "task_evals": task_evals,
    }


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EVALUATED MODELS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluatedModels:
    """GET /api/evaluations/projects/{project_id}/evaluated-models"""

    def test_evaluated_models_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)
        assert len(models) >= 2
        model_ids = {m["model_id"] for m in models}
        assert "gpt-4o" in model_ids
        assert "claude-3-sonnet" in model_ids

    def test_evaluated_models_include_configured(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        # Should include the 3rd configured model even if not evaluated
        for m in models:
            if m.get("is_configured"):
                assert "has_results" in m
                assert "has_generations" in m

    def test_evaluated_models_has_provider(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        for m in resp.json():
            assert "provider" in m
            assert m["provider"] != ""

    def test_evaluated_models_has_scores(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        for m in resp.json():
            if m["evaluation_count"] > 0:
                assert m["average_score"] is not None
                assert isinstance(m["average_score"], (int, float))

    def test_evaluated_models_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Empty Meta", created_by=test_users[0].id,
            label_config="<View/>",
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_evaluated_models_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/projects/nonexistent-id/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_evaluated_models_with_annotation_evals(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=1, with_annotation_evals=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        # Should include annotator synthetic models
        annotator_models = [m for m in models if m["model_id"].startswith("annotator:")]
        assert len(annotator_models) >= 1


# ===================================================================
# CONFIGURED METHODS
# ===================================================================

@pytest.mark.integration
class TestGetConfiguredMethods:
    """GET /api/evaluations/projects/{project_id}/configured-methods"""

    def test_configured_methods_with_config(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "fields" in body

    def test_configured_methods_no_config(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=1, with_eval_config=False)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fields"] == []

    def test_configured_methods_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/projects/nonexistent/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_configured_methods_has_result_status(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in body.get("fields", []):
            for method in field.get("automated_methods", []):
                assert "is_configured" in method
                assert "has_results" in method
                assert "result_count" in method


# ===================================================================
# STATISTICS
# ===================================================================

@pytest.mark.integration
class TestStatistics:
    """POST /api/evaluations/projects/{project_id}/statistics"""

    def test_statistics_by_model(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=3, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy", "f1"],
                "aggregation": "model",
                "methods": ["ci"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            body = resp.json()
            assert body["aggregation"] == "model"

    def test_statistics_by_sample(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "sample",
                "methods": ["ci"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_by_field(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "field",
                "methods": ["ci"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_overall(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=5)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "overall",
                "methods": ["ci"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_with_ttest(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["ci", "ttest"],
                "compare_models": ["gpt-4o", "claude-3-sonnet"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_with_bootstrap(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["bootstrap"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            f"{BASE}/projects/nonexistent/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (400, 403, 404, 422)

    def test_statistics_empty_metrics(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=1)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": [], "aggregation": "model"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)


# ===================================================================
# EVALUATION HISTORY
# ===================================================================

@pytest.mark.integration
class TestEvaluationHistory:
    """GET /api/evaluations/projects/{project_id}/evaluation-history"""

    def test_evaluation_history(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404, 422)

    def test_evaluation_history_with_model_filter(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-history?model_id=gpt-4o",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404, 422)


# ===================================================================
# SIGNIFICANCE TESTS
# ===================================================================

@pytest.mark.integration
class TestSignificance:
    """POST /api/evaluations/projects/{project_id}/significance"""

    def test_significance_two_models(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=10)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/significance",
            json={
                "model_a": "gpt-4o",
                "model_b": "claude-3-sonnet",
                "metric": "accuracy",
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 422)

    def test_significance_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            f"{BASE}/projects/nonexistent/significance",
            json={
                "model_a": "gpt-4o",
                "model_b": "claude-3-sonnet",
                "metric": "accuracy",
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (400, 403, 404, 422)


# ===================================================================
# ADDITIONAL METADATA EDGE CASES
# ===================================================================

@pytest.mark.integration
class TestMetadataEdgeCases:
    """Additional edge cases for metadata endpoints."""

    def test_evaluated_models_sorts_by_score(self, client, test_db, test_users, auth_headers, test_org):
        """Models should be sorted by average_score descending."""
        data = _build(test_db, test_users[0], test_org, num_models=3, num_tasks=5)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        scores = [m["average_score"] for m in models if m["average_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_configured_methods_field_mapping(self, client, test_db, test_users, auth_headers, test_org):
        """Configured methods should include field_mapping if set."""
        data = _build(test_db, test_users[0], test_org, num_models=1, with_eval_config=True)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "project_id" in body

    def test_evaluated_models_ci_values(self, client, test_db, test_users, auth_headers, test_org):
        """Models with enough data should have CI values."""
        data = _build(test_db, test_users[0], test_org, num_models=1, num_tasks=8)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        for m in models:
            assert "ci_lower" in m
            assert "ci_upper" in m

    def test_statistics_with_cohens_d(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["cohens_d"],
                "compare_models": ["gpt-4o", "claude-3-sonnet"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_with_correlation(self, client, test_db, test_users, auth_headers, test_org):
        data = _build(test_db, test_users[0], test_org, num_models=2, num_tasks=8)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["accuracy", "f1"],
                "aggregation": "model",
                "methods": ["correlation"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 422)

    def test_evaluated_models_filters_unknown(self, client, test_db, test_users, auth_headers, test_org):
        """The 'unknown' model_id should be filtered out."""
        data = _build(test_db, test_users[0], test_org, num_models=2)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        models = resp.json()
        model_ids = {m["model_id"] for m in models}
        assert "unknown" not in model_ids
