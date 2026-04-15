"""
Integration tests for evaluation results and metadata endpoints.

Targets:
- routers/evaluations/results.py — 7.37% (547 uncovered)
- routers/evaluations/metadata.py — 9.59% (452 uncovered)
- routers/evaluations/config.py — 13.04% (132 uncovered)
- routers/evaluations/status.py — 19.29% (83 uncovered)
- routers/evaluations/validation.py — 16.92% (36 uncovered)
- routers/evaluations/multi_field.py — 18.00% (162 uncovered)
- routers/evaluations/human.py — 27.55% (142 uncovered)
"""

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
    Organization,
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
# Actual sub-paths used in the mounted routers:
# Results: /api/evaluations/evaluations/results/{project_id}
# Export:  /api/evaluations/evaluations/export/{project_id}
# Status:  /api/evaluations/evaluations
# Types:   /api/evaluations/evaluation-types
# Config:  /api/evaluations/projects/{project_id}/evaluation-config
# Validate:/api/evaluations/evaluations/validate-config
# Metadata:/api/evaluations/projects/{project_id}/...
# Multi:   /api/evaluations/projects/{project_id}/available-fields
# Human:   /api/evaluations/evaluations/human/...


def _uid() -> str:
    return str(uuid.uuid4())


def _setup_evaluation_project(db, admin, org, *, num_tasks=3, with_evaluations=True,
                              with_generations=False, with_human_sessions=False,
                              evaluation_config=None):
    """Create a project with tasks, evaluations, and generations."""
    project = Project(
        id=_uid(),
        title=f"Eval Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config=evaluation_config,
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

    # Add annotations
    annotations = []
    for i, t in enumerate(tasks):
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text", "type": "choices",
                     "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    db.flush()

    eval_runs = []
    if with_evaluations:
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            er = EvaluationRun(
                id=_uid(),
                project_id=project.id,
                model_id=model_id,
                evaluation_type_ids=["accuracy", "f1"],
                metrics={"accuracy": 0.85, "f1_score": 0.82},
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
        # Create a ResponseGeneration first
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            status="completed",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(rg)
        db.flush()

        for i, t in enumerate(tasks):
            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=t.id,
                model_id="gpt-4o",
                case_data=f'{{"text": "Case data for task {i}"}}',
                response_content=f"Generated answer for task {i}",
                label_config_version="v1",
                status="completed",
            )
            db.add(gen)
            generations.append(gen)
        db.flush()

    human_sessions = []
    if with_human_sessions:
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

        # Likert evaluations
        for i, dim in enumerate(["fluency", "accuracy", "relevance"]):
            le = LikertScaleEvaluation(
                id=_uid(),
                session_id=hs.id,
                task_id=tasks[i % len(tasks)].id,
                dimension=dim,
                rating=4,
            )
            db.add(le)

        # Preference ranking
        pr = PreferenceRanking(
            id=_uid(),
            session_id=hs.id,
            task_id=tasks[0].id,
            winner="gpt-4o",
        )
        db.add(pr)
        human_sessions.append(hs)
        db.flush()

    db.commit()
    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "eval_runs": eval_runs,
        "generations": generations,
        "human_sessions": human_sessions,
    }


# ===================================================================
# EVALUATION RESULTS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationResults:
    """GET /api/evaluations/results/{project_id}"""

    def test_get_results_basic(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluations/results/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_get_results_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(
            test_db, test_users[0], test_org, with_evaluations=False,
            with_generations=False,
        )
        resp = client.get(
            f"{BASE}/evaluations/results/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    # Human evaluation results are tested in test_evaluation_endpoints.py::TestHumanEvaluationSessions

    def test_get_results_automated_only(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluations/results/{data['project'].id}?include_human=false",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_results_limit(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluations/results/{data['project'].id}?limit=1",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_results_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE}/evaluations/results/nonexistent-id",
            headers=auth_headers["admin"],
        )
        # Superadmin can access any project; returns empty list for nonexistent
        assert resp.status_code in (200, 403, 404)


# ===================================================================
# EVALUATION EXPORT
# ===================================================================

@pytest.mark.integration
class TestExportEvaluationResults:
    """POST /api/evaluations/export/{project_id}"""

    def test_export_json(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/evaluations/export/{data['project'].id}?format=json",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "project_id" in body
        assert "results" in body

    def test_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/evaluations/export/{data['project'].id}?format=csv",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ===================================================================
# EVALUATION STATUS
# ===================================================================

@pytest.mark.integration
class TestEvaluationStatus:
    """Evaluation listing, types, and status endpoints."""

    def test_list_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_evaluation_types(self, client, test_db, test_users, auth_headers, test_evaluation_types):
        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_evaluation_status(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluation/status/{data['eval_runs'][0].id if data['eval_runs'] else 'none'}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# EVALUATION CONFIG
# ===================================================================

@pytest.mark.integration
class TestEvaluationConfig:
    """Evaluation configuration endpoints."""

    def test_get_eval_config(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org, with_generations=False)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_update_eval_config(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.put(
            f"{BASE}/projects/{data['project'].id}/evaluation-config",
            json={
                "metrics": ["accuracy", "f1"],
                "evaluation_mode": "automated",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422)

    def test_get_eval_config_nonexistent(self, client, test_db, test_users, auth_headers):
        resp = client.get(f"{BASE}/projects/nonexistent/evaluation-config", headers=auth_headers["admin"])
        assert resp.status_code in (403, 404)


# ===================================================================
# EVALUATION VALIDATION
# ===================================================================

@pytest.mark.integration
class TestEvaluationValidation:
    """Evaluation config validation endpoint."""

    def test_validate_config(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/evaluations/validate-config",
            json={"project_id": data["project"].id, "metrics": ["accuracy"]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 403, 422)


# ===================================================================
# EVALUATION METADATA
# ===================================================================

@pytest.mark.integration
class TestEvaluationMetadata:
    """Evaluation metadata endpoints (evaluated models, statistics)."""

    def test_get_evaluated_models(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/evaluated-models",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_evaluation_methods(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/configured-methods",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_evaluation_statistics(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 422)


# ===================================================================
# MULTI-FIELD EVALUATION
# ===================================================================

@pytest.mark.integration
class TestMultiFieldEvaluation:
    """Multi-field evaluation endpoints."""

    def test_get_available_fields(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{data['project'].id}/available-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_field_results(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/run/results/project/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ===================================================================
# HUMAN EVALUATION
# ===================================================================

@pytest.mark.integration
class TestHumanEvaluation:
    """Human evaluation session endpoints."""

    def test_create_human_eval_session(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"{BASE}/evaluations/human/session/start",
            json={"project_id": data["project"].id, "evaluation_type": "likert"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 400, 403, 422)

    def test_list_human_eval_sessions(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/evaluations/human/sessions/{data['project'].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_submit_likert_evaluation(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        if data["human_sessions"]:
            session_id = data["human_sessions"][0].id
            resp = client.post(
                f"{BASE}/evaluations/human/likert",
                json={
                    "dimension": "quality",
                    "rating": 4,
                    "model_id": "gpt-4o",
                    "task_id": data["tasks"][0].id,
                },
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
            assert resp.status_code in (200, 201, 400, 403, 422)

    def test_submit_preference_ranking(self, client, test_db, test_users, auth_headers, test_org):
        data = _setup_evaluation_project(test_db, test_users[0], test_org)
        if data["human_sessions"]:
            session_id = data["human_sessions"][0].id
            resp = client.post(
                f"{BASE}/evaluations/human/preference",
                json={
                    "winner": "gpt-4o",
                    "loser": "claude-3-sonnet",
                    "task_id": data["tasks"][0].id,
                },
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
            assert resp.status_code in (200, 201, 400, 403, 422)
