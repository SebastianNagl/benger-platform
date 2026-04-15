"""
Integration tests for evaluation results and metadata endpoints.

Tests evaluation handlers in routers/evaluations/results.py and
routers/evaluations/metadata.py using real PostgreSQL.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    Generation,
    TaskEvaluation,
    LLMModel,
    User,
    Organization,
    OrganizationMembership,
)
from project_models import Annotation, Project, Task
from user_service import get_password_hash

# URL prefix: main router = /api/evaluations
# results.py routes start with /evaluations/... => /api/evaluations/evaluations/...
# metadata.py routes like /projects/... => /api/evaluations/projects/...
# metadata.py routes like /significance/... => /api/evaluations/significance/...
RESULTS_PREFIX = "/api/evaluations/evaluations"
META_PREFIX = "/api/evaluations"


# ===== Fixtures =====


@pytest.fixture
def admin_user(test_db: Session) -> User:
    user = User(
        id=f"admin-eval-{uuid.uuid4().hex[:8]}",
        username=f"evaladmin-{uuid.uuid4().hex[:8]}@test.com",
        email=f"evaladmin-{uuid.uuid4().hex[:8]}@test.com",
        name="Eval Admin",
        hashed_password=get_password_hash("admin123"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.utcnow(),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def non_admin_user(test_db: Session) -> User:
    user = User(
        id=f"nonadmin-eval-{uuid.uuid4().hex[:8]}",
        username=f"nonadmin-{uuid.uuid4().hex[:8]}@test.com",
        email=f"nonadmin-{uuid.uuid4().hex[:8]}@test.com",
        name="Non Admin",
        hashed_password=get_password_hash("user123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.utcnow(),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_project(test_db: Session, admin_user: User) -> Project:
    project = Project(
        id=f"proj-eval-{uuid.uuid4().hex[:8]}",
        title="Evaluation Test Project",
        description="A test project for evaluation testing",
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


@pytest.fixture
def test_tasks(test_db: Session, test_project: Project, admin_user: User):
    tasks = []
    for i in range(5):
        task = Task(
            id=f"task-eval-{uuid.uuid4().hex[:8]}",
            project_id=test_project.id,
            data={"text": f"Sample legal text {i}", "content": f"Content for task {i}"},
            inner_id=i + 1,
            created_by=admin_user.id,
            created_at=datetime.utcnow(),
        )
        test_db.add(task)
        tasks.append(task)
    test_db.commit()
    for t in tasks:
        test_db.refresh(t)
    return tasks


@pytest.fixture
def response_generation(test_db: Session, test_project: Project, admin_user: User):
    rg = ResponseGeneration(
        id=f"rg-eval-{uuid.uuid4().hex[:8]}",
        project_id=test_project.id,
        model_id="gpt-4",
        status="completed",
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
    )
    test_db.add(rg)
    test_db.commit()
    test_db.refresh(rg)
    return rg


@pytest.fixture
def test_generations(test_db: Session, test_tasks, response_generation):
    generations = []
    for task in test_tasks:
        gen = Generation(
            id=f"gen-eval-{uuid.uuid4().hex[:8]}",
            generation_id=response_generation.id,
            task_id=task.id,
            model_id="gpt-4",
            case_data="Sample case data",
            response_content="Generated response",
            status="completed",
            parse_status="success",
            created_at=datetime.utcnow(),
        )
        test_db.add(gen)
        generations.append(gen)
    test_db.commit()
    for g in generations:
        test_db.refresh(g)
    return generations


@pytest.fixture
def evaluation_run(test_db: Session, test_project: Project, admin_user: User):
    eval_run = EvaluationRun(
        id=f"eval-run-{uuid.uuid4().hex[:8]}",
        project_id=test_project.id,
        model_id="gpt-4",
        evaluation_type_ids=["accuracy", "f1"],
        metrics={"accuracy": 0.85, "f1_score": 0.82},
        status="completed",
        samples_evaluated=5,
        has_sample_results=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    test_db.add(eval_run)
    test_db.commit()
    test_db.refresh(eval_run)
    return eval_run


@pytest.fixture
def task_evaluations(test_db: Session, evaluation_run, test_tasks, test_generations):
    evals = []
    for i, (task, gen) in enumerate(zip(test_tasks, test_generations)):
        score = 0.7 + (i * 0.05)
        te = TaskEvaluation(
            id=f"te-{uuid.uuid4().hex[:8]}",
            evaluation_id=evaluation_run.id,
            task_id=task.id,
            generation_id=gen.id,
            field_name="text_answer",
            answer_type="text",
            ground_truth={"value": f"correct_answer_{i}"},
            prediction={"value": f"predicted_answer_{i}"},
            metrics={"accuracy": score, "f1_score": score - 0.03},
            passed=score >= 0.75,
            confidence_score=score,
            processing_time_ms=100 + i * 10,
            created_at=datetime.utcnow(),
        )
        test_db.add(te)
        evals.append(te)
    test_db.commit()
    for e in evals:
        test_db.refresh(e)
    return evals


@pytest.fixture
def classification_evaluations(test_db: Session, evaluation_run, test_tasks, test_generations):
    labels = ["positive", "negative", "neutral"]
    evals = []
    predictions = [
        ("positive", "positive"),
        ("negative", "negative"),
        ("neutral", "positive"),
        ("positive", "negative"),
        ("neutral", "neutral"),
    ]
    for i, (task, gen) in enumerate(zip(test_tasks, test_generations)):
        gt, pred = predictions[i]
        te = TaskEvaluation(
            id=f"te-cls-{uuid.uuid4().hex[:8]}",
            evaluation_id=evaluation_run.id,
            task_id=task.id,
            generation_id=gen.id,
            field_name="classification",
            answer_type="classification",
            ground_truth={"value": gt},
            prediction={"value": pred},
            metrics={"accuracy": 1.0 if gt == pred else 0.0},
            passed=gt == pred,
            created_at=datetime.utcnow(),
        )
        test_db.add(te)
        evals.append(te)
    test_db.commit()
    for e in evals:
        test_db.refresh(e)
    return evals


@pytest.fixture
def auth_header(admin_user):
    from auth_module import create_access_token
    token = create_access_token(data={"user_id": admin_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def nonadmin_auth_header(non_admin_user):
    from auth_module import create_access_token
    token = create_access_token(data={"user_id": non_admin_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def human_eval_session(test_db: Session, test_project: Project, admin_user: User):
    session = HumanEvaluationSession(
        id=f"hes-{uuid.uuid4().hex[:8]}",
        project_id=test_project.id,
        evaluator_id=admin_user.id,
        session_type="likert",
        items_evaluated=3,
        status="completed",
        created_at=datetime.utcnow(),
    )
    test_db.add(session)
    test_db.commit()
    test_db.refresh(session)
    return session


@pytest.fixture
def likert_evaluations(test_db: Session, human_eval_session, test_tasks):
    evals = []
    dimensions = ["accuracy", "clarity", "completeness"]
    for task in test_tasks[:3]:
        for dim in dimensions:
            le = LikertScaleEvaluation(
                id=f"le-{uuid.uuid4().hex[:8]}",
                session_id=human_eval_session.id,
                task_id=task.id,
                response_id=f"resp-{uuid.uuid4().hex[:8]}",
                dimension=dim,
                rating=3 + (hash(dim) % 3),
                created_at=datetime.utcnow(),
            )
            test_db.add(le)
            evals.append(le)
    test_db.commit()
    return evals


@pytest.fixture
def preference_eval_session(test_db: Session, test_project: Project, admin_user: User):
    session = HumanEvaluationSession(
        id=f"hes-pref-{uuid.uuid4().hex[:8]}",
        project_id=test_project.id,
        evaluator_id=admin_user.id,
        session_type="preference",
        items_evaluated=5,
        status="completed",
        created_at=datetime.utcnow(),
    )
    test_db.add(session)
    test_db.commit()
    test_db.refresh(session)
    return session


@pytest.fixture
def preference_rankings(test_db: Session, preference_eval_session, test_tasks):
    rankings = []
    winners = ["a", "b", "a", "tie", "a"]
    for i, task in enumerate(test_tasks):
        pr = PreferenceRanking(
            id=f"pr-{uuid.uuid4().hex[:8]}",
            session_id=preference_eval_session.id,
            task_id=task.id,
            response_a_id=f"resp-a-{i}",
            response_b_id=f"resp-b-{i}",
            winner=winners[i],
            confidence=0.8,
            created_at=datetime.utcnow(),
        )
        test_db.add(pr)
        rankings.append(pr)
    test_db.commit()
    return rankings


# ===== Group 1: Evaluation Results Integration Tests =====


class TestGetEvaluationResults:
    """Tests for GET /evaluations/results/{project_id}"""

    def test_get_automated_results(self, client, auth_header, test_project, evaluation_run):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) >= 1
        assert automated[0]["results"]["metrics"]["accuracy"] == 0.85

    def test_get_results_with_human_likert(
        self, client, auth_header, test_project, evaluation_run, likert_evaluations
    ):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        likert = [r for r in data if r["results"].get("type") == "human_likert"]
        assert len(likert) >= 1
        dims = likert[0]["results"]["dimensions"]
        assert "accuracy" in dims or "clarity" in dims or "completeness" in dims

    def test_get_results_with_preference_rankings(
        self, client, auth_header, test_project, evaluation_run, preference_rankings
    ):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        pref = [r for r in data if r["results"].get("type") == "human_preference"]
        assert len(pref) >= 1
        assert "counts" in pref[0]["results"]
        assert "percentages" in pref[0]["results"]

    def test_get_results_automated_only(
        self, client, auth_header, test_project, evaluation_run, likert_evaluations
    ):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}?include_human=false",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        human = [r for r in data if "human" in r["results"].get("type", "")]
        assert len(human) == 0

    def test_get_results_human_only(
        self, client, auth_header, test_project, evaluation_run, likert_evaluations
    ):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}?include_automated=false",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) == 0

    def test_get_results_limit(self, client, auth_header, test_project, evaluation_run):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}?limit=1",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) <= 1

    def test_get_results_no_auth(self, client, test_project):
        resp = client.get(f"{RESULTS_PREFIX}/results/{test_project.id}")
        assert resp.status_code in [401, 403]

    def test_get_results_nonexistent_project(self, client, auth_header):
        """Superadmin can access any project; nonexistent returns empty results."""
        resp = client.get(
            f"{RESULTS_PREFIX}/results/nonexistent-project-id",
            headers=auth_header,
        )
        # Superadmin passes access check; endpoint returns 200 with empty list
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_results_empty_project(self, client, auth_header, test_project):
        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestExportEvaluationResults:
    """Tests for POST /evaluations/export/{project_id}"""

    def test_export_json(self, client, auth_header, test_project, evaluation_run):
        resp = client.post(
            f"{RESULTS_PREFIX}/export/{test_project.id}?format=json",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == test_project.id
        assert "results" in data

    def test_export_csv(self, client, auth_header, test_project, evaluation_run):
        resp = client.post(
            f"{RESULTS_PREFIX}/export/{test_project.id}?format=csv",
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_export_no_auth(self, client, test_project):
        resp = client.post(f"{RESULTS_PREFIX}/export/{test_project.id}?format=json")
        assert resp.status_code in [401, 403]


class TestGetEvaluationSamples:
    """Tests for GET /evaluations/{evaluation_id}/samples"""

    def test_get_samples(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 5

    def test_get_samples_filter_by_field(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples?field_name=text_answer",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5

    def test_get_samples_filter_passed_true(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples?passed=true",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["passed"] is True

    def test_get_samples_filter_passed_false(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples?passed=false",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["passed"] is False

    def test_get_samples_pagination(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples?page=1&page_size=2",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["has_next"] is True

    def test_get_samples_page_2(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/samples?page=2&page_size=2",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert len(data["items"]) == 2

    def test_get_samples_nonexistent_evaluation(self, client, auth_header):
        resp = client.get(
            f"{RESULTS_PREFIX}/nonexistent-eval-id/samples",
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_get_samples_no_auth(self, client, evaluation_run):
        resp = client.get(f"{RESULTS_PREFIX}/{evaluation_run.id}/samples")
        assert resp.status_code in [401, 403]


class TestMetricDistribution:
    """Tests for GET /evaluations/{evaluation_id}/metrics/{metric_name}/distribution"""

    def test_get_distribution(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/metrics/accuracy/distribution",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_name"] == "accuracy"
        assert "mean" in data
        assert "median" in data
        assert "std" in data
        assert "min" in data
        assert "max" in data
        assert "quartiles" in data
        assert "histogram" in data

    def test_distribution_stats_correct(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/metrics/accuracy/distribution",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["min"] <= data["mean"] <= data["max"]
        assert data["min"] <= data["median"] <= data["max"]
        assert data["std"] >= 0

    def test_distribution_with_field_filter(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/metrics/accuracy/distribution?field_name=text_answer",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_name"] == "accuracy"

    def test_distribution_nonexistent_metric(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/metrics/nonexistent_metric/distribution",
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_distribution_nonexistent_evaluation(self, client, auth_header):
        resp = client.get(
            f"{RESULTS_PREFIX}/nonexistent-eval/metrics/accuracy/distribution",
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_distribution_no_auth(self, client, evaluation_run):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/metrics/accuracy/distribution"
        )
        assert resp.status_code in [401, 403]


class TestConfusionMatrix:
    """Tests for GET /evaluations/{evaluation_id}/confusion-matrix"""

    def test_get_confusion_matrix(self, client, auth_header, evaluation_run, classification_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix?field_name=classification",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["field_name"] == "classification"
        assert "labels" in data
        assert "matrix" in data
        assert "accuracy" in data
        assert "precision_per_class" in data
        assert "recall_per_class" in data
        assert "f1_per_class" in data

    def test_confusion_matrix_labels(self, client, auth_header, evaluation_run, classification_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix?field_name=classification",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        labels = data["labels"]
        assert len(labels) >= 2
        assert labels == sorted(labels)

    def test_confusion_matrix_dimensions(self, client, auth_header, evaluation_run, classification_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix?field_name=classification",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        n = len(data["labels"])
        assert len(data["matrix"]) == n
        for row in data["matrix"]:
            assert len(row) == n

    def test_confusion_matrix_accuracy_range(self, client, auth_header, evaluation_run, classification_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix?field_name=classification",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert 0.0 <= data["accuracy"] <= 1.0

    def test_confusion_matrix_no_field(self, client, auth_header, evaluation_run, classification_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix",
            headers=auth_header,
        )
        assert resp.status_code == 422

    def test_confusion_matrix_nonexistent_field(self, client, auth_header, evaluation_run, task_evaluations):
        resp = client.get(
            f"{RESULTS_PREFIX}/{evaluation_run.id}/confusion-matrix?field_name=nonexistent_field",
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_confusion_matrix_nonexistent_evaluation(self, client, auth_header):
        resp = client.get(
            f"{RESULTS_PREFIX}/nonexistent/confusion-matrix?field_name=classification",
            headers=auth_header,
        )
        assert resp.status_code == 404


class TestEvaluationMetadataEndpoints:
    """Tests for metadata endpoints in routers/evaluations/metadata.py"""

    def test_get_evaluated_models(self, client, auth_header, test_project, evaluation_run, test_generations):
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluated-models",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_evaluated_models_includes_model_info(
        self, client, auth_header, test_project, evaluation_run, test_generations
    ):
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluated-models",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data:
            model = data[0]
            assert "model_id" in model
            assert "model_name" in model

    def test_evaluated_models_with_configured(
        self, client, auth_header, test_project, evaluation_run, test_db, test_generations
    ):
        test_project.generation_config = {
            "selected_configuration": {
                "models": ["gpt-4", "claude-3-sonnet"],
            }
        }
        test_db.commit()

        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluated-models?include_configured=true",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_evaluated_models_nonexistent_project(self, client, auth_header):
        resp = client.get(
            f"{META_PREFIX}/projects/nonexistent-project/evaluated-models",
            headers=auth_header,
        )
        assert resp.status_code in [403, 404]

    def test_evaluated_models_no_auth(self, client, test_project):
        resp = client.get(f"{META_PREFIX}/projects/{test_project.id}/evaluated-models")
        assert resp.status_code in [401, 403]

    def test_configured_methods_no_config(self, client, auth_header, test_project):
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/configured-methods",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == test_project.id
        assert data["fields"] == []

    def test_configured_methods_with_config(self, client, auth_header, test_project, test_db):
        test_project.evaluation_config = {
            "selected_methods": {
                "text_answer": {
                    "automated": ["accuracy", "f1"],
                    "human": ["likert"],
                }
            },
            "available_methods": {
                "text_answer": {
                    "type": "text",
                    "to_name": "text",
                }
            },
        }
        test_db.commit()

        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/configured-methods",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fields"]) >= 1
        field = data["fields"][0]
        assert field["field_name"] == "text_answer"
        assert len(field["automated_methods"]) >= 1
        assert len(field["human_methods"]) >= 1


class TestEvaluationHistory:
    """Tests for GET /projects/{project_id}/evaluation-history"""

    def test_evaluation_history(self, client, auth_header, test_project, evaluation_run):
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluation-history"
            f"?model_ids=gpt-4&metric=accuracy",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric"] == "accuracy"
        assert "data" in data

    def test_evaluation_history_data_points(self, client, auth_header, test_project, evaluation_run):
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluation-history"
            f"?model_ids=gpt-4&metric=accuracy",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["data"]:
            point = data["data"][0]
            assert "date" in point
            assert "model_id" in point
            assert "value" in point

    def test_evaluation_history_date_filter(self, client, auth_header, test_project, evaluation_run):
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
        tomorrow = (datetime.utcnow() + timedelta(days=1)).isoformat()
        resp = client.get(
            f"{META_PREFIX}/projects/{test_project.id}/evaluation-history"
            f"?model_ids=gpt-4&metric=accuracy&start_date={yesterday}&end_date={tomorrow}",
            headers=auth_header,
        )
        assert resp.status_code == 200

    def test_evaluation_history_nonexistent_project(self, client, auth_header):
        resp = client.get(
            f"{META_PREFIX}/projects/nonexistent/evaluation-history?model_ids=gpt-4&metric=accuracy",
            headers=auth_header,
        )
        assert resp.status_code in [403, 404]


class TestSignificanceTests:
    """Tests for GET /significance/{project_id}"""

    def test_significance_endpoint(
        self, client, auth_header, test_project, evaluation_run, task_evaluations, test_generations
    ):
        resp = client.get(
            f"{META_PREFIX}/significance/{test_project.id}"
            f"?model_ids=gpt-4&metrics=accuracy",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "comparisons" in data or "message" in data

    def test_significance_nonexistent_project(self, client, auth_header):
        resp = client.get(
            f"{META_PREFIX}/significance/nonexistent?model_ids=gpt-4&metrics=accuracy",
            headers=auth_header,
        )
        assert resp.status_code in [403, 404]


class TestModelComparison:
    """Tests for model comparison via results endpoints."""

    def test_multiple_eval_runs(self, client, auth_header, test_project, admin_user, test_db):
        for i in range(3):
            er = EvaluationRun(
                id=f"er-multi-{uuid.uuid4().hex[:8]}",
                project_id=test_project.id,
                model_id=f"model-{i}",
                evaluation_type_ids=["accuracy"],
                metrics={"accuracy": 0.7 + (i * 0.1)},
                status="completed",
                samples_evaluated=10,
                created_by=admin_user.id,
                created_at=datetime.utcnow(),
            )
            test_db.add(er)
        test_db.commit()

        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}?limit=100",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) >= 3

    def test_result_ordering(self, client, auth_header, test_project, admin_user, test_db):
        for i in range(3):
            er = EvaluationRun(
                id=f"er-order-{uuid.uuid4().hex[:8]}",
                project_id=test_project.id,
                model_id="gpt-4",
                evaluation_type_ids=["accuracy"],
                metrics={"accuracy": 0.5 + (i * 0.1)},
                status="completed",
                samples_evaluated=10,
                created_by=admin_user.id,
                created_at=datetime.utcnow() - timedelta(hours=3 - i),
            )
            test_db.add(er)
        test_db.commit()

        resp = client.get(
            f"{RESULTS_PREFIX}/results/{test_project.id}?limit=100",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        if len(automated) >= 2:
            for i in range(len(automated) - 1):
                t1 = automated[i]["created_at"]
                t2 = automated[i + 1]["created_at"]
                assert t1 >= t2
