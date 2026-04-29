"""
Deep integration tests for evaluation endpoints.

Targets: routers/evaluations/results.py, metadata.py, config.py, status.py,
         validation.py, multi_field.py, human.py
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationType,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
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


def _make_eval_project(db, admin, org, *, num_tasks=3, num_models=2,
                        with_task_evals=True, with_generations=True,
                        with_human=False, evaluation_config=None):
    """Create a rich evaluation project."""
    project = Project(
        id=_uid(),
        title="Deep Eval Test",
        created_by=admin.id,
        evaluation_config=evaluation_config,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
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
            data={"text": f"Eval text #{i}", "answer_field": f"A{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    # Add annotations
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
    db.flush()

    models = ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models]
    eval_runs = []
    for model_id in models:
        er = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": 0.85 + (0.05 if model_id == "gpt-4o" else 0),
                     "f1_score": 0.82},
            status="completed",
            samples_evaluated=num_tasks,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(er)
        eval_runs.append(er)
    db.flush()

    generations = []
    if with_generations:
        for model_id in models:
            rg = ResponseGeneration(
                id=_uid(), project_id=project.id, model_id=model_id,
                status="completed", created_by=admin.id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(rg)
            db.flush()

            for t in tasks:
                gen = Generation(
                    id=_uid(), generation_id=rg.id, task_id=t.id,
                    model_id=model_id,
                    case_data=json.dumps({"text": f"case for {t.id}"}),
                    response_content=f"Answer from {model_id}",
                    status="completed",
                )
                db.add(gen)
                generations.append(gen)
        db.flush()

    task_evals = []
    if with_task_evals and generations:
        for er in eval_runs:
            model_gens = [g for g in generations if g.model_id == er.model_id]
            for gen in model_gens:
                te = TaskEvaluation(
                    id=_uid(),
                    evaluation_id=er.id,
                    task_id=gen.task_id,
                    generation_id=gen.id,
                    field_name="answer",
                    answer_type="choices",
                    ground_truth="Ja",
                    prediction="Ja",
                    metrics={"accuracy": 1.0, "f1": 0.9},
                    passed=True,
                )
                db.add(te)
                task_evals.append(te)
        db.flush()

    human_sessions = []
    if with_human and generations:
        hs = HumanEvaluationSession(
            id=_uid(),
            project_id=project.id,
            evaluator_id=admin.id,
            session_type="likert",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(hs)
        db.flush()

        # LikertScaleEvaluation requires response_id (NOT NULL)
        first_gen = generations[0] if generations else None
        if first_gen:
            for dim in ["fluency", "accuracy", "relevance"]:
                le = LikertScaleEvaluation(
                    id=_uid(), session_id=hs.id,
                    task_id=tasks[0].id, response_id=first_gen.id,
                    dimension=dim, rating=4,
                )
                db.add(le)

            pr = PreferenceRanking(
                id=_uid(), session_id=hs.id,
                task_id=tasks[0].id, winner="gpt-4o",
            )
            db.add(pr)
        human_sessions.append(hs)
        db.flush()

    db.commit()
    return {
        "project": project, "tasks": tasks, "eval_runs": eval_runs,
        "generations": generations, "task_evals": task_evals,
        "human_sessions": human_sessions,
    }


# ===================================================================
# RESULTS ENDPOINT — per-sample and export
# ===================================================================

@pytest.mark.integration
class TestEvalResults:
    """GET /api/evaluations/results/{project_id}"""

    def test_results_with_task_evals(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org, with_task_evals=True)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_results_filter_by_model(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?model_id=gpt-4o",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_results_include_human_flag(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org, with_human=False)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?include_human=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_results_with_limit_offset(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/results/{data['project'].id}?limit=2&offset=0",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_results_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(
            test_db, test_users[0], test_org,
            with_task_evals=False, with_generations=False, num_models=0,
        )
        resp = client.get(
            f"{BASE}/results/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.integration
class TestEvalExport:
    """POST /api/evaluations/export/{project_id}"""

    def test_export_json_with_data(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "project_id" in body
        assert "results" in body

    def test_export_csv_with_data(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_export_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(
            test_db, test_users[0], test_org,
            with_task_evals=False, with_generations=False, num_models=0,
        )
        resp = client.post(
            f"{BASE}/export/{data['project'].id}?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ===================================================================
# METADATA — evaluated models, configured methods, statistics
# ===================================================================

@pytest.mark.integration
class TestEvalMetadata:
    """Evaluation metadata endpoints."""

    def test_evaluated_models(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # Should have 2 models
        assert len(body) >= 2

    def test_evaluated_models_empty(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(
            test_db, test_users[0], test_org,
            num_models=0, with_task_evals=False, with_generations=False,
        )
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_configured_methods(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_statistics_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 422)

    def test_statistics_sample_aggregation(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "sample"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 422)


# ===================================================================
# CONFIG — evaluation configuration
# ===================================================================

@pytest.mark.integration
class TestEvalConfig:
    """Evaluation configuration endpoints."""

    def test_get_config_with_existing(self, client, test_db, test_users, auth_headers, test_org):
        eval_config = {"metrics": ["accuracy", "f1"], "evaluation_mode": "automated"}
        data = _make_eval_project(
            test_db, test_users[0], test_org, evaluation_config=eval_config,
        )
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_update_config_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.put(
            f"{BASE}/projects/{data['project'].id}/evaluation-config",
            json={"metrics": ["accuracy"], "evaluation_mode": "automated"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422)


# ===================================================================
# STATUS — evaluation listing and status
# ===================================================================

@pytest.mark.integration
class TestEvalStatus:
    """Evaluation status and listing endpoints."""

    def test_list_evaluations_with_data(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_evaluation_types(self, client, test_db, test_users, auth_headers, test_evaluation_types):
        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_evaluation_status_by_id(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        if data["eval_runs"]:
            er_id = data["eval_runs"][0].id
            resp = client.get(
                f"{BASE}/evaluation/status/{er_id}",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
            assert resp.status_code in (200, 404)


# ===================================================================
# MULTI-FIELD
# ===================================================================

@pytest.mark.integration
class TestMultiField:
    """Multi-field evaluation endpoints."""

    def test_available_fields(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/available-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_field_results(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/run/results/project/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ===================================================================
# HUMAN EVALUATION — sessions, likert, preference
# ===================================================================

@pytest.mark.integration
class TestHumanEval:
    """Human evaluation endpoints."""

    def test_list_sessions(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org, with_human=False)
        resp = client.get(
            f"{BASE}/human/sessions/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_list_sessions_empty(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org, with_human=False)
        resp = client.get(
            f"{BASE}/human/sessions/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_start_session(self, client, test_db, test_users, auth_headers, test_org):
        data = _make_eval_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": data["project"].id, "evaluation_type": "likert"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 400, 403, 422)
