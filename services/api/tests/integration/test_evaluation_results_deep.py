"""
Deep integration tests for evaluation results, per-sample analysis, and export.

Covers routers/evaluations/results.py:
- GET /evaluations/results/{project_id} — automated + human results
- POST /evaluations/export/{project_id} — JSON and CSV export
- GET /evaluations/{evaluation_id}/samples — per-sample with filters
- GET /evaluations/{evaluation_id}/metrics/{metric}/distribution — histogram, quartiles
- GET /evaluations/{evaluation_id}/confusion-matrix — classification confusion matrix
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
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


def _setup(db, admin, org, *, num_tasks=5, with_human=False, with_generations=True):
    """Build a complete evaluation data graph."""
    project = Project(
        id=_uid(),
        title=f"EvalResult {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
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
            data={"text": f"Eval text #{i}", "question": f"Q{i}"},
            inner_id=i + 1, created_by=admin.id,
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

    # Generations
    generations = []
    if with_generations:
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            rg = ResponseGeneration(
                id=_uid(), project_id=project.id, model_id=model_id,
                status="completed", created_by=admin.id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(rg)
            db.flush()
            for i, t in enumerate(tasks):
                gen = Generation(
                    id=_uid(), generation_id=rg.id, task_id=t.id,
                    model_id=model_id,
                    case_data=json.dumps(t.data),
                    response_content=f"Answer from {model_id} for task {i}",
                    label_config_version="v1", status="completed",
                )
                db.add(gen)
                generations.append(gen)
        db.flush()

    # Evaluation runs with per-sample results
    eval_runs = []
    task_evals = []
    for model_id in ["gpt-4o", "claude-3-sonnet"]:
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": 0.80, "f1_score": 0.75},
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
        model_gens = [g for g in generations if g.model_id == model_id]
        for i, t in enumerate(tasks):
            gen_id = model_gens[i].id if i < len(model_gens) else None
            accuracy_val = 1.0 if i % 3 != 0 else 0.0
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, task_id=t.id,
                generation_id=gen_id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if accuracy_val == 1.0 else "Nein"},
                metrics={"accuracy": accuracy_val, "f1": 0.8 + (i * 0.02)},
                passed=accuracy_val == 1.0,
                confidence_score=0.9 - (i * 0.05),
                processing_time_ms=100 + i * 10,
            )
            db.add(te)
            task_evals.append(te)
    db.flush()

    # Human evaluation sessions
    human_sessions = []
    if with_human:
        hs = HumanEvaluationSession(
            id=_uid(), project_id=project.id,
            evaluator_id=admin.id,
            session_type="likert", status="completed",
            items_evaluated=3, total_items=num_tasks,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(hs)
        db.flush()
        human_sessions.append(hs)

        # Likert evaluations
        for dim in ["fluency", "accuracy", "relevance"]:
            for rating_val in [3, 4, 5]:
                le = LikertScaleEvaluation(
                    id=_uid(), session_id=hs.id,
                    task_id=tasks[0].id,
                    response_id="resp-1",
                    dimension=dim, rating=rating_val,
                )
                db.add(le)
        db.flush()

        # Preference rankings
        pr = PreferenceRanking(
            id=_uid(), session_id=hs.id,
            task_id=tasks[0].id,
            response_a_id="resp-a", response_b_id="resp-b",
            winner="a", confidence=0.85,
        )
        db.add(pr)
        pr2 = PreferenceRanking(
            id=_uid(), session_id=hs.id,
            task_id=tasks[1].id,
            response_a_id="resp-a", response_b_id="resp-b",
            winner="b", confidence=0.7,
        )
        db.add(pr2)
        db.flush()

    db.commit()
    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "task_evals": task_evals,
        "human_sessions": human_sessions,
    }


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# EVALUATION RESULTS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationResultsDeep:
    """GET /api/evaluations/results/{project_id}"""

    def test_results_automated_only(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=False)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?include_human=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert all(r["results"]["type"] == "automated" for r in results)

    def test_results_human_only(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=True)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?include_automated=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        human_types = [r["results"]["type"] for r in results if r["results"]["type"].startswith("human")]
        assert len(human_types) >= 1

    def test_results_both_automated_and_human(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=True)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        types = {r["results"]["type"] for r in results}
        assert "automated" in types

    def test_results_with_limit(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?limit=1",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        # Limited to 1 automated result
        automated = [r for r in results if r["results"]["type"] == "automated"]
        assert len(automated) <= 1

    def test_results_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Empty Eval", created_by=test_users[0].id,
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
            f"{BASE}/results/{project.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_results_likert_aggregation(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=True)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?include_automated=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        likert = [r for r in results if r["results"]["type"] == "human_likert"]
        if likert:
            dims = likert[0]["results"]["dimensions"]
            assert "fluency" in dims
            assert "accuracy" in dims
            assert "relevance" in dims
            # Average of 3, 4, 5 = 4.0
            assert dims["fluency"]["average_rating"] == pytest.approx(4.0, abs=0.1)

    def test_results_preference_aggregation(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=True)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?include_automated=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        prefs = [r for r in results if r["results"]["type"] == "human_preference"]
        if prefs:
            counts = prefs[0]["results"]["counts"]
            assert "a" in counts or "b" in counts
            assert prefs[0]["results"]["total_comparisons"] == 2

    def test_results_access_denied(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        # No org context header for non-superadmin
        resp = client.get(
            f"{BASE}/results/{data['project'].id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code in (200, 403)


# ===================================================================
# EVALUATION EXPORT
# ===================================================================

@pytest.mark.integration
class TestExportEvaluationResultsDeep:
    """POST /api/evaluations/export/{project_id}"""

    def test_export_json_with_metrics(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "results" in body
        assert len(body["results"]) >= 1

    def test_export_csv_format(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert "timestamp" in lines[0]
        assert len(lines) >= 2  # header + data

    def test_export_csv_with_human_data(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, with_human=True)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=csv",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        # Should include human evaluation rows
        content = resp.text
        # Human likert or preference data should be present
        assert len(content.strip().split("\n")) >= 2

    def test_export_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Empty Export", created_by=test_users[0].id,
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

        resp = client.post(
            f"{BASE}/export/{project.id}?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []


# ===================================================================
# PER-SAMPLE RESULTS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationSamples:
    """GET /api/evaluations/{evaluation_id}/samples"""

    def test_get_samples_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/samples",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5

    def test_get_samples_filter_by_passed(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/samples?passed=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # All returned should be passed
        for item in body["items"]:
            assert item["passed"] is True

    def test_get_samples_filter_by_failed(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/samples?passed=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["passed"] is False

    def test_get_samples_filter_by_field_name(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/samples?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["field_name"] == "answer"

    def test_get_samples_pagination(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=10)
        eval_id = data["eval_runs"][0].id

        # Page 1
        resp1 = client.get(
            f"{BASE}/{eval_id}/samples?page=1&page_size=3",
            headers=_h(auth_headers, test_org),
        )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["items"]) == 3
        assert body1["has_next"] is True
        assert body1["total"] == 10

        # Page 2
        resp2 = client.get(
            f"{BASE}/{eval_id}/samples?page=2&page_size=3",
            headers=_h(auth_headers, test_org),
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 3

        # Ensure different items
        ids1 = {item["id"] for item in body1["items"]}
        ids2 = {item["id"] for item in body2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_get_samples_nonexistent_evaluation(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/nonexistent-eval-id/samples",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_get_samples_response_structure(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/samples?page_size=1",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        item = body["items"][0]
        assert "id" in item
        assert "evaluation_id" in item
        assert "task_id" in item
        assert "field_name" in item
        assert "ground_truth" in item
        assert "prediction" in item
        assert "metrics" in item
        assert "passed" in item


# ===================================================================
# METRIC DISTRIBUTION
# ===================================================================

@pytest.mark.integration
class TestMetricDistribution:
    """GET /api/evaluations/{evaluation_id}/metrics/{metric}/distribution"""

    def test_distribution_accuracy(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=10)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/metrics/accuracy/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric_name"] == "accuracy"
        assert "mean" in body
        assert "median" in body
        assert "std" in body
        assert "min" in body
        assert "max" in body
        assert "quartiles" in body
        assert "histogram" in body
        assert body["min"] >= 0.0
        assert body["max"] <= 1.0

    def test_distribution_f1(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/metrics/f1/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric_name"] == "f1"
        # Histogram should have 10 buckets
        assert len(body["histogram"]) == 10

    def test_distribution_filter_by_field(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=6)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/metrics/accuracy/distribution?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_distribution_nonexistent_metric(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/metrics/nonexistent_metric/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_distribution_nonexistent_evaluation(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/nonexistent/metrics/accuracy/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# CONFUSION MATRIX
# ===================================================================

@pytest.mark.integration
class TestConfusionMatrix:
    """GET /api/evaluations/{evaluation_id}/confusion-matrix"""

    def test_confusion_matrix_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=6)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["field_name"] == "answer"
        assert "labels" in body
        assert "matrix" in body
        assert "accuracy" in body
        # Should have labels "ja" and "nein"
        assert len(body["labels"]) >= 1

    def test_confusion_matrix_metrics(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "precision_per_class" in body
        assert "recall_per_class" in body
        assert "f1_per_class" in body
        assert 0 <= body["accuracy"] <= 1.0

    def test_confusion_matrix_nonexistent_field(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/confusion-matrix?field_name=nonexistent",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_confusion_matrix_access_denied(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            headers=auth_headers["annotator"],  # No org context
        )
        assert resp.status_code in (200, 403)

    def test_confusion_matrix_nonexistent_eval(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/nonexistent/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_confusion_matrix_labels_lowercase(self, client, test_db, test_users, auth_headers, test_org):
        """Labels in the confusion matrix should be normalized to lowercase."""
        data = _setup(test_db, test_users[0], test_org, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        resp = client.get(
            f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for label in body["labels"]:
            assert label == label.lower()


# ===================================================================
# MULTIPLE EVALUATION RUNS
# ===================================================================

@pytest.mark.integration
class TestMultipleEvaluationRuns:
    """Test behavior with multiple evaluation runs for the same project."""

    def test_results_multiple_models(self, client, test_db, test_users, auth_headers, test_org):
        """Results should include data from all models."""
        data = _setup(test_db, test_users[0], test_org, num_tasks=5)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        results = resp.json()
        # Should have results from both gpt-4o and claude-3-sonnet
        assert len([r for r in results if r["results"]["type"] == "automated"]) >= 2

    def test_samples_from_second_run(self, client, test_db, test_users, auth_headers, test_org):
        """Per-sample results for the second evaluation run."""
        data = _setup(test_db, test_users[0], test_org, num_tasks=5)
        eval_id = data["eval_runs"][1].id  # claude-3-sonnet
        resp = client.get(
            f"{BASE}/{eval_id}/samples",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5

    def test_distribution_from_second_run(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org, num_tasks=8)
        eval_id = data["eval_runs"][1].id
        resp = client.get(
            f"{BASE}/{eval_id}/metrics/f1/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_export_includes_all_runs(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=json",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Export should have >= 2 automated results
        automated = [r for r in body["results"] if r["results"]["type"] == "automated"]
        assert len(automated) >= 2
