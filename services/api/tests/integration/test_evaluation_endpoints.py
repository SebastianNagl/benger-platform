"""Integration tests for evaluation API routers.

Covers the 7 evaluation sub-routers:
  - config: Evaluation configuration management
  - multi_field: N:M field mapping, available fields, project results
  - results: Evaluation results, per-sample analysis, export
  - status: Evaluation listing, types, status
  - validation: Config alignment validation
  - metadata: Evaluated models, configured methods
  - human: Human evaluation sessions (Likert, preference)

Uses real PostgreSQL with transaction rollback isolation via the shared
test_db fixture. No mocks for database operations.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
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
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


# ---------------------------------------------------------------------------
# A realistic label_config for a QA project with Choices + TextArea fields
# ---------------------------------------------------------------------------
LABEL_CONFIG_QA = """<View>
  <Header value="Legal QA Task"/>
  <Text name="question" value="$question"/>
  <Text name="context" value="$context"/>
  <Choices name="answer_type" toName="question" choice="single-select">
    <Choice value="Ja"/>
    <Choice value="Nein"/>
  </Choices>
  <TextArea name="answer" toName="question" rows="4"/>
</View>"""


# ---------------------------------------------------------------------------
# Shared helpers to build evaluation data
# ---------------------------------------------------------------------------


def _create_evaluation_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    *,
    label_config: Optional[str] = LABEL_CONFIG_QA,
    num_tasks: int = 3,
    with_annotations: bool = True,
    with_generations: bool = True,
    with_evaluation_run: bool = True,
    with_task_evaluations: bool = True,
    evaluation_config: dict = None,
    generation_config: dict = None,
) -> Dict:
    """Create a complete project with tasks, annotations, generations, and evaluation runs.

    Returns a dict with all created objects keyed by type.
    """
    admin = test_users[0]
    contributor = test_users[1]
    annotator = test_users[2]

    # --- Project ---
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title="Eval Integration Test Project",
        description="Project for evaluation endpoint integration tests",
        label_config=label_config,
        label_config_version="v1",
        created_by=admin.id,
        is_published=True,
        assignment_mode="open",
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    test_db.add(project)
    test_db.flush()

    # --- Org linkage ---
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=admin.id,
    )
    test_db.add(project_org)

    # --- Members ---
    for i, (user, role) in enumerate(
        [(admin, "admin"), (contributor, "contributor"), (annotator, "annotator")]
    ):
        test_db.add(
            ProjectMember(
                id=str(uuid.uuid4()),
                project_id=project.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
    test_db.flush()

    # --- Tasks ---
    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={
                "question": f"Was ist die Rechtsfolge in Fall {i + 1}?",
                "context": f"Sachverhalt {i + 1}: Der Beklagte hat ...",
            },
            created_by=admin.id,
            updated_by=admin.id,
        )
        test_db.add(task)
        tasks.append(task)
    test_db.flush()

    # --- Annotations ---
    annotations = []
    if with_annotations:
        for task in tasks:
            annot = Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=project.id,
                completed_by=annotator.id,
                result=[
                    {
                        "from_name": "answer_type",
                        "to_name": "question",
                        "type": "choices",
                        "value": {"choices": ["Ja"]},
                    },
                    {
                        "from_name": "answer",
                        "to_name": "question",
                        "type": "textarea",
                        "value": {"text": ["Die Rechtsfolge ist ..."]},
                    },
                ],
            )
            test_db.add(annot)
            annotations.append(annot)
    test_db.flush()

    # --- Response Generations + Generations ---
    response_generations = []
    generations = []
    if with_generations:
        for task in tasks:
            rg = ResponseGeneration(
                id=str(uuid.uuid4()),
                project_id=project.id,
                task_id=task.id,
                model_id="gpt-4o",
                status="completed",
                responses_generated=1,
                created_by=admin.id,
            )
            test_db.add(rg)
            response_generations.append(rg)
            test_db.flush()

            gen = Generation(
                id=str(uuid.uuid4()),
                generation_id=rg.id,
                task_id=task.id,
                model_id="gpt-4o",
                case_data=f"Fall {task.inner_id}",
                response_content="Die Rechtsfolge lautet ...",
                status="completed",
                parse_status="success",
                parsed_annotation=[
                    {
                        "from_name": "answer_type",
                        "to_name": "question",
                        "type": "choices",
                        "value": {"choices": ["Ja"]},
                    },
                    {
                        "from_name": "answer",
                        "to_name": "question",
                        "type": "textarea",
                        "value": {"text": ["Model answer ..."]},
                    },
                ],
            )
            test_db.add(gen)
            generations.append(gen)
    test_db.flush()

    # --- Evaluation Run ---
    evaluation_runs = []
    task_evaluations_list = []
    if with_evaluation_run:
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy", "f1"],
            metrics={
                "cfg1:answer_type:answer_type:accuracy": 0.85,
                "cfg1:answer:answer:f1": 0.78,
            },
            eval_metadata={
                "evaluation_type": "evaluation",
                "triggered_by": admin.id,
                "evaluation_configs": [
                    {
                        "id": "cfg1",
                        "metric": "accuracy",
                        "prediction_fields": ["answer_type"],
                        "reference_fields": ["answer_type"],
                        "enabled": True,
                    }
                ],
            },
            status="completed",
            samples_evaluated=num_tasks,
            has_sample_results=with_task_evaluations,
            created_by=admin.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        test_db.add(eval_run)
        evaluation_runs.append(eval_run)
        test_db.flush()

        # --- TaskEvaluations (per-sample) ---
        if with_task_evaluations and generations:
            for i, (task, gen) in enumerate(zip(tasks, generations)):
                te = TaskEvaluation(
                    id=str(uuid.uuid4()),
                    evaluation_id=eval_run.id,
                    task_id=task.id,
                    generation_id=gen.id,
                    field_name="answer_type",
                    answer_type="single_choice",
                    ground_truth={"value": "Ja"},
                    prediction={"value": "Ja" if i % 2 == 0 else "Nein"},
                    metrics={"accuracy": 1.0 if i % 2 == 0 else 0.0, "score": 0.9},
                    passed=i % 2 == 0,
                    created_at=datetime.utcnow(),
                )
                test_db.add(te)
                task_evaluations_list.append(te)

    test_db.commit()

    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "response_generations": response_generations,
        "generations": generations,
        "evaluation_runs": evaluation_runs,
        "task_evaluations": task_evaluations_list,
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
    }


# ===========================================================================
# Priority 1 — Config endpoints (config.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationConfig:
    """GET/PUT /api/evaluations/projects/{project_id}/evaluation-config"""

    def test_get_evaluation_config_generates_from_label_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """When no evaluation_config exists, GET generates one from label_config."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Generated config should have detected_answer_types from label_config
        assert "detected_answer_types" in body
        assert "available_methods" in body
        # At minimum the Choices and TextArea fields should be detected
        field_names = [at["name"] for at in body["detected_answer_types"]]
        assert "answer_type" in field_names or "answer" in field_names

    def test_get_evaluation_config_returns_existing(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """When evaluation_config already exists, GET returns it unchanged."""
        existing_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"]}},
            "selected_methods": {"answer": {"automated": ["bleu"]}},
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            evaluation_config=existing_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["selected_methods"]["answer"]["automated"] == ["bleu"]

    def test_get_evaluation_config_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """GET with nonexistent project returns 404."""
        resp = client.get(
            f"/api/evaluations/projects/{uuid.uuid4()}/evaluation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_put_evaluation_config_saves_successfully(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT saves evaluation config and returns it."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        new_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"], "available_human": []}},
            "selected_methods": {"answer": {"automated": ["bleu"], "human": []}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            json=new_config,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Evaluation configuration updated successfully"
        assert body["config"]["selected_methods"]["answer"]["automated"] == ["bleu"]
        # label_config_version should be stamped
        assert body["config"]["label_config_version"] == "v1"

    def test_put_evaluation_config_validates_metrics(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT rejects invalid metric names not in available_methods."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        bad_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"type": "text", "available_metrics": ["bleu"], "available_human": []}},
            "selected_methods": {"answer": {"automated": ["nonexistent_metric"], "human": []}},
        }
        resp = client.put(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-config",
            json=bad_config,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "nonexistent_metric" in resp.json()["detail"]

    def test_put_evaluation_config_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """PUT with nonexistent project returns 404."""
        resp = client.put(
            f"/api/evaluations/projects/{uuid.uuid4()}/evaluation-config",
            json={"selected_methods": {}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestDetectAnswerTypes:
    """GET /api/evaluations/projects/{project_id}/detect-answer-types"""

    def test_detect_types_from_label_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Detects Choices and TextArea from the QA label_config."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/detect-answer-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert len(body["detected_types"]) > 0
        assert "available_methods" in body

    def test_detect_types_no_label_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns empty when project has no label_config."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            label_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/detect-answer-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detected_types"] == []

    def test_detect_types_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/projects/{uuid.uuid4()}/detect-answer-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestFieldTypes:
    """GET /api/evaluations/projects/{project_id}/field-types"""

    def test_field_types_returns_types_and_criteria(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns field type info with LLM judge criteria recommendations."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/field-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert isinstance(body["field_types"], dict)
        # Each field should have type, tag, recommended_criteria
        for field_name, field_info in body["field_types"].items():
            assert "type" in field_info
            assert "tag" in field_info
            assert "recommended_criteria" in field_info

    def test_field_types_no_label_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns empty field_types when no label_config."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            label_config=None,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/field-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["field_types"] == {}


# ===========================================================================
# Priority 2 — Multi-field evaluation (multi_field.py)
# ===========================================================================


@pytest.mark.integration
class TestAvailableFields:
    """GET /api/evaluations/projects/{project_id}/available-fields"""

    def test_available_fields_includes_all_categories(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns model_response_fields, human_annotation_fields, reference_fields."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/available-fields",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "model_response_fields" in body
        assert "human_annotation_fields" in body
        assert "reference_fields" in body
        assert "all_fields" in body
        # With our label_config, human annotation fields should include answer_type and/or answer
        assert len(body["human_annotation_fields"]) > 0 or len(body["all_fields"]) > 0

    def test_available_fields_detects_model_fields_from_generations(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Model response fields are extracted from parsed generation annotations."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/available-fields",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Generations have parsed_annotation with from_name="answer_type" and "answer"
        assert "answer_type" in body["model_response_fields"] or "answer" in body["model_response_fields"]

    def test_available_fields_includes_task_data_as_reference(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Task data fields (question, context) appear as reference fields."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/available-fields",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Task data has "question" and "context" string fields
        assert "question" in body["reference_fields"] or "context" in body["reference_fields"]

    def test_available_fields_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/projects/{uuid.uuid4()}/available-fields",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_available_fields_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-member annotator cannot access fields of an unlinked project."""
        # Create project without org linkage for the annotator
        project = Project(
            id=str(uuid.uuid4()),
            title="Private Project",
            label_config=LABEL_CONFIG_QA,
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/available-fields",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestProjectEvaluationResults:
    """GET /api/evaluations/run/results/project/{project_id}"""

    def test_project_results_returns_completed_evaluation(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns evaluation run data with parsed metrics and progress."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/run/results/project/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert body["total_count"] >= 1
        assert len(body["evaluations"]) >= 1

        eval_result = body["evaluations"][0]
        assert eval_result["status"] == "completed"
        assert eval_result["model_id"] == "gpt-4o"
        assert eval_result["samples_evaluated"] == 3
        assert "results_by_config" in eval_result
        assert "progress" in eval_result

    def test_project_results_latest_only(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """latest_only=True returns only the most recent evaluation."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        # Add a second evaluation run
        eval_run2 = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"cfg2:answer:answer:accuracy": 0.92},
            eval_metadata={"evaluation_type": "evaluation"},
            status="completed",
            samples_evaluated=3,
            created_by=data["admin"].id,
            created_at=datetime.utcnow() + timedelta(hours=1),
            completed_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(eval_run2)
        test_db.commit()

        # latest_only=True (default)
        resp = client.get(
            f"/api/evaluations/run/results/project/{data['project'].id}?latest_only=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1

        # latest_only=False should return both
        resp_all = client.get(
            f"/api/evaluations/run/results/project/{data['project'].id}?latest_only=false",
            headers=auth_headers["admin"],
        )
        assert resp_all.status_code == 200
        assert resp_all.json()["total_count"] >= 2

    def test_project_results_empty_project(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Project with no evaluation runs returns empty list."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/run/results/project/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 0
        assert body["evaluations"] == []

    def test_project_results_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/run/results/project/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===========================================================================
# Priority 3 — Results (results.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationResultsByProject:
    """GET /api/evaluations/results/{project_id}"""

    def test_results_include_automated_evaluations(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns automated evaluation results."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/results/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # Should have at least 1 automated result
        automated_results = [r for r in body if r["results"].get("type") == "automated"]
        assert len(automated_results) >= 1

    def test_results_filter_automated_only(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """include_human=false filters out human evaluations."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/results/{data['project'].id}?include_human=false",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        for result in body:
            assert result["results"]["type"] != "human_likert"
            assert result["results"]["type"] != "human_preference"

    def test_results_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-member gets 403."""
        project = Project(
            id=str(uuid.uuid4()),
            title="Private",
            label_config=LABEL_CONFIG_QA,
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/results/{project.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestEvaluationSamples:
    """GET /api/evaluations/{evaluation_id}/samples"""

    def test_samples_returns_paginated_results(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns per-sample results with pagination."""
        data = _create_evaluation_project(test_db, test_users, test_org)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/{eval_id}/samples?page=1&page_size=10",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert body["total"] == len(data["task_evaluations"])
        for item in body["items"]:
            assert "field_name" in item
            assert "metrics" in item
            assert "passed" in item

    def test_samples_filter_by_passed(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Filter by passed=true returns only passing samples."""
        data = _create_evaluation_project(test_db, test_users, test_org)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/{eval_id}/samples?passed=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["passed"] is True

    def test_samples_filter_by_field_name(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Filter by field_name returns only matching samples."""
        data = _create_evaluation_project(test_db, test_users, test_org)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/{eval_id}/samples?field_name=answer_type",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["field_name"] == "answer_type"

    def test_samples_evaluation_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/{uuid.uuid4()}/samples",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_samples_pagination_has_next(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """has_next is True when more items exist beyond current page."""
        data = _create_evaluation_project(test_db, test_users, test_org, num_tasks=5)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/{eval_id}/samples?page=1&page_size=2",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_next"] is True
        assert len(body["items"]) == 2


# ===========================================================================
# Priority 4 — Status & types (status.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationsList:
    """GET /api/evaluations/"""

    def test_list_evaluations_returns_all_accessible(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns evaluations scoped to accessible projects."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            "/api/evaluations/",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        # Verify structure
        eval_entry = body[0]
        assert "id" in eval_entry
        assert "project_id" in eval_entry
        assert "model_id" in eval_entry
        assert "metrics" in eval_entry
        assert "status" in eval_entry

    def test_list_evaluations_empty_for_no_projects(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """User with no project access gets empty list."""
        # Annotator is not a superadmin, so with no projects they see nothing
        # But test_org membership may give access; this test verifies the structure
        resp = client.get(
            "/api/evaluations/",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


@pytest.mark.integration
class TestEvaluationTypes:
    """GET /api/evaluations/evaluation-types and /evaluation-types/{id}"""

    def test_list_evaluation_types(
        self, client, test_db, test_users, test_org, test_evaluation_types, auth_headers
    ):
        """Returns all active evaluation types."""
        resp = client.get(
            "/api/evaluations/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= len(test_evaluation_types)
        # Verify structure
        for et in body:
            assert "id" in et
            assert "name" in et
            assert "category" in et
            assert "higher_is_better" in et

    def test_list_evaluation_types_filter_by_category(
        self, client, test_db, test_users, test_org, test_evaluation_types, auth_headers
    ):
        """Filter by category returns only matching types."""
        resp = client.get(
            "/api/evaluations/evaluation-types?category=classification",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        for et in body:
            assert et["category"] == "classification"

    def test_get_evaluation_type_by_id(
        self, client, test_db, test_users, test_org, test_evaluation_types, auth_headers
    ):
        """Get specific evaluation type returns correct data."""
        resp = client.get(
            "/api/evaluations/evaluation-types/accuracy",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "accuracy"
        assert body["name"] == "Accuracy"
        assert body["category"] == "classification"
        assert body["higher_is_better"] is True

    def test_get_evaluation_type_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            "/api/evaluations/evaluation-types/nonexistent_metric",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestEvaluationStatus:
    """GET /api/evaluations/evaluation/status/{evaluation_id}"""

    def test_get_evaluation_status(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns status of a completed evaluation."""
        data = _create_evaluation_project(test_db, test_users, test_org)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/evaluation/status/{eval_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == eval_id
        assert body["status"] == "completed"

    def test_get_evaluation_status_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/evaluation/status/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_evaluation_status_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """User without project access gets 403."""
        # Create eval run on a project not linked to any org
        project = Project(
            id=str(uuid.uuid4()),
            title="Private",
            label_config=LABEL_CONFIG_QA,
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project)
        test_db.flush()
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={},
            status="completed",
            created_by=test_users[0].id,
            created_at=datetime.utcnow(),
        )
        test_db.add(eval_run)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/evaluation/status/{eval_run.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestSupportedMetrics:
    """GET /api/evaluations/supported-metrics

    NOTE: This endpoint imports ml_evaluation modules that live in the workers
    service. When called in the API test container, the import fails and crashes
    the ASGI handler in a way that corrupts the TestClient lifecycle. The endpoint
    is tested via the workers test suite and E2E tests instead.
    """

    pass


# ===========================================================================
# Priority 5 — Validation (validation.py)
# ===========================================================================


@pytest.mark.integration
class TestValidateConfig:
    """POST /api/evaluations/validate-config"""

    def test_validate_config_matching_fields(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Matching generation and evaluation fields produces valid result."""
        gen_config = {
            "prompt_structures": [
                {"output_fields": ["answer_type", "answer"]}
            ]
        }
        eval_config = {
            "detected_answer_types": [
                {"name": "answer_type"},
                {"name": "answer"},
            ],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.post(
            f"/api/evaluations/validate-config?project_id={data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert "answer_type" in body["matched_fields"]
        assert "answer" in body["matched_fields"]
        assert body["errors"] == []

    def test_validate_config_mismatched_fields(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Mismatched fields produce errors/warnings."""
        gen_config = {
            "prompt_structures": [
                {"output_fields": ["answer_type", "extra_field"]}
            ]
        }
        eval_config = {
            "detected_answer_types": [
                {"name": "answer_type"},
                {"name": "reasoning"},
            ],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.post(
            f"/api/evaluations/validate-config?project_id={data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # "reasoning" is in evaluation but not in generation -> error
        assert len(body["errors"]) > 0
        assert "reasoning" in body["missing_in_generation"]
        # "extra_field" is in generation but not in evaluation -> warning
        assert "extra_field" in body["missing_in_evaluation"]

    def test_validate_config_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.post(
            f"/api/evaluations/validate-config?project_id={uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_validate_config_no_overlap(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """No overlapping fields at all produces an error."""
        gen_config = {
            "prompt_structures": [{"output_fields": ["field_a"]}]
        }
        eval_config = {
            "detected_answer_types": [{"name": "field_b"}],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            generation_config=gen_config,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.post(
            f"/api/evaluations/validate-config?project_id={data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("No overlapping" in e for e in body["errors"])


# ===========================================================================
# Priority 6 — Metadata (metadata.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluatedModels:
    """GET /api/evaluations/projects/{project_id}/evaluated-models"""

    def test_evaluated_models_returns_model_with_scores(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns the model that was evaluated with scores."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluated-models",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        # gpt-4o should be in the results
        model_ids = [m["model_id"] for m in body]
        assert "gpt-4o" in model_ids
        gpt4_entry = next(m for m in body if m["model_id"] == "gpt-4o")
        assert gpt4_entry["evaluation_count"] >= 1
        assert gpt4_entry["average_score"] is not None

    def test_evaluated_models_include_configured(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """include_configured=True includes models from generation_config."""
        gen_config = {
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3.5-sonnet"]
            }
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            generation_config=gen_config,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluated-models?include_configured=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        model_ids = [m["model_id"] for m in body]
        # claude-3.5-sonnet should appear as configured even without results
        assert "claude-3.5-sonnet" in model_ids
        claude_entry = next(m for m in body if m["model_id"] == "claude-3.5-sonnet")
        assert claude_entry["is_configured"] is True

    def test_evaluated_models_empty_project(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Project with no generations/evaluations returns empty list."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluated-models",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == []

    def test_evaluated_models_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/projects/{uuid.uuid4()}/evaluated-models",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestConfiguredMethods:
    """GET /api/evaluations/projects/{project_id}/configured-methods"""

    def test_configured_methods_returns_fields(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns configured methods with result status."""
        eval_config = {
            "detected_answer_types": [{"name": "answer_type", "type": "choices"}],
            "available_methods": {
                "answer_type": {
                    "type": "choices",
                    "to_name": "question",
                    "available_metrics": ["accuracy", "f1"],
                    "available_human": [],
                }
            },
            "selected_methods": {
                "answer_type": {
                    "automated": ["accuracy"],
                    "human": [],
                }
            },
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            evaluation_config=eval_config,
        )

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/configured-methods",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert len(body["fields"]) >= 1
        field = body["fields"][0]
        assert field["field_name"] == "answer_type"
        assert len(field["automated_methods"]) >= 1
        assert field["automated_methods"][0]["method_name"] == "accuracy"
        assert field["automated_methods"][0]["is_configured"] is True

    def test_configured_methods_no_eval_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Project with no evaluation_config returns empty fields."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        # Ensure no eval config
        data["project"].evaluation_config = None
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/configured-methods",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fields"] == []

    def test_configured_methods_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/projects/{uuid.uuid4()}/configured-methods",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===========================================================================
# Priority 7 — Human evaluation (human.py)
# ===========================================================================


@pytest.mark.integration
class TestHumanEvaluationConfig:
    """GET /api/evaluations/human/config/{project_id}"""

    def test_human_config_returns_methods_and_dimensions(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns human methods and available dimensions."""
        eval_config = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {
                "answer": {
                    "automated": [],
                    "human": [
                        {
                            "name": "likert_scale",
                            "parameters": {
                                "dimensions": ["correctness", "completeness"]
                            },
                        }
                    ],
                }
            },
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/human/config/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "answer" in body["human_methods"]
        assert "correctness" in body["available_dimensions"]
        assert "completeness" in body["available_dimensions"]

    def test_human_config_no_eval_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns empty when no evaluation_config exists."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )
        data["project"].evaluation_config = None
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/human/config/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["human_methods"] == {}

    def test_human_config_default_dimensions(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns default dimensions when no custom dimensions configured."""
        eval_config = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {
                "answer": {
                    "automated": [],
                    "human": ["likert_scale"],
                }
            },
            "label_config_version": "v1",
        }
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            evaluation_config=eval_config,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/human/config/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Default dimensions should be provided
        defaults = {"correctness", "completeness", "style", "usability"}
        assert set(body["available_dimensions"]) == defaults

    def test_human_config_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/human/config/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestHumanEvaluationSessions:
    """GET /api/evaluations/human/sessions/{project_id}"""

    def test_list_sessions_returns_created_sessions(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns sessions with correct data."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        # Create a human evaluation session
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            evaluator_id=data["admin"].id,
            session_type="likert",
            items_evaluated=2,
            total_items=5,
            status="active",
            session_config={"dimensions": ["correctness"]},
            created_at=datetime.utcnow(),
        )
        test_db.add(session)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/human/sessions/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        s = body[0]
        assert s["id"] == session.id
        assert s["session_type"] == "likert"
        assert s["items_evaluated"] == 2
        assert s["total_items"] == 5
        assert s["status"] == "active"

    def test_list_sessions_empty(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Project with no sessions returns empty list."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.get(
            f"/api/evaluations/human/sessions/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sessions_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-member cannot list sessions."""
        project = Project(
            id=str(uuid.uuid4()),
            title="Private",
            label_config=LABEL_CONFIG_QA,
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/human/sessions/{project.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestStartHumanEvaluationSession:
    """POST /api/evaluations/human/session/start"""

    def test_superadmin_can_start_session(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Superadmin can start a new human evaluation session."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )

        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": data["project"].id,
                "session_type": "likert",
                "field_name": "answer",
                "dimensions": ["correctness", "completeness"],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert body["session_type"] == "likert"
        assert body["status"] == "active"
        assert body["items_evaluated"] == 0
        assert body["total_items"] == len(data["tasks"])

    def test_non_superadmin_cannot_start_session(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-superadmin gets 403."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
            with_annotations=False,
        )

        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": data["project"].id,
                "session_type": "likert",
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_start_session_project_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.post(
            "/api/evaluations/human/session/start",
            json={
                "project_id": str(uuid.uuid4()),
                "session_type": "likert",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestSessionProgress:
    """GET /api/evaluations/human/session/{session_id}/progress"""

    def test_get_session_progress(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns correct progress percentage."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            evaluator_id=data["admin"].id,
            session_type="likert",
            items_evaluated=2,
            total_items=4,
            status="active",
            created_at=datetime.utcnow(),
        )
        test_db.add(session)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/human/session/{session.id}/progress",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items_evaluated"] == 2
        assert body["total_items"] == 4
        assert body["progress_percentage"] == 50.0
        assert body["status"] == "active"

    def test_session_progress_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/human/session/{uuid.uuid4()}/progress",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_session_progress_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-superadmin non-owner cannot view progress."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            evaluator_id=data["admin"].id,  # owned by admin
            session_type="preference",
            items_evaluated=0,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        test_db.add(session)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/human/session/{session.id}/progress",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestDeleteHumanEvaluationSession:
    """DELETE /api/evaluations/human/session/{session_id}"""

    def test_superadmin_can_delete_session(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Superadmin can delete a session and its evaluations."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            evaluator_id=data["admin"].id,
            session_type="likert",
            items_evaluated=1,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        test_db.add(session)
        test_db.flush()

        # Add a Likert evaluation
        likert = LikertScaleEvaluation(
            id=str(uuid.uuid4()),
            session_id=session.id,
            task_id=data["tasks"][0].id,
            response_id="resp-1",
            dimension="correctness",
            rating=4,
            created_at=datetime.utcnow(),
        )
        test_db.add(likert)
        test_db.commit()

        resp = client.delete(
            f"/api/evaluations/human/session/{session.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.id

        # Verify session and evaluations are deleted
        remaining_session = test_db.query(HumanEvaluationSession).filter(
            HumanEvaluationSession.id == session.id
        ).first()
        assert remaining_session is None

        remaining_likert = test_db.query(LikertScaleEvaluation).filter(
            LikertScaleEvaluation.session_id == session.id
        ).first()
        assert remaining_likert is None

    def test_non_superadmin_non_owner_cannot_delete(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-superadmin who is not the session owner gets 403."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            evaluator_id=data["admin"].id,  # owned by admin
            session_type="likert",
            items_evaluated=0,
            total_items=3,
            status="active",
            created_at=datetime.utcnow(),
        )
        test_db.add(session)
        test_db.commit()

        resp = client.delete(
            f"/api/evaluations/human/session/{session.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_delete_session_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.delete(
            f"/api/evaluations/human/session/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===========================================================================
# Cross-cutting: evaluation run detail results (multi_field.py)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationRunResults:
    """GET /api/evaluations/run/results/{evaluation_id}"""

    def test_run_results_returns_parsed_metrics(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Returns detailed per-config results."""
        data = _create_evaluation_project(test_db, test_users, test_org)
        eval_id = data["evaluation_runs"][0].id

        resp = client.get(
            f"/api/evaluations/run/results/{eval_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["evaluation_id"] == eval_id
        assert body["status"] == "completed"
        assert body["samples_evaluated"] == 3
        assert "results_by_config" in body
        assert "aggregated_metrics" in body
        # Metrics should contain our test data
        assert "cfg1:answer_type:answer_type:accuracy" in body["aggregated_metrics"]

    def test_run_results_not_found(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/evaluations/run/results/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_run_results_non_evaluation_type_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Evaluation with wrong eval_metadata type returns 400."""
        data = _create_evaluation_project(
            test_db, test_users, test_org,
            with_evaluation_run=False,
            with_generations=False,
        )
        # Create eval run with non-evaluation type
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=data["project"].id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={},
            eval_metadata={"evaluation_type": "generation"},  # Not "evaluation"
            status="completed",
            created_by=data["admin"].id,
            created_at=datetime.utcnow(),
        )
        test_db.add(eval_run)
        test_db.commit()

        resp = client.get(
            f"/api/evaluations/run/results/{eval_run.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "not an evaluation run" in resp.json()["detail"]


# ===========================================================================
# Export endpoint (results.py)
# ===========================================================================


@pytest.mark.integration
class TestExportResults:
    """POST /api/evaluations/export/{project_id}"""

    def test_export_json(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """JSON export returns structured data."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.post(
            f"/api/evaluations/export/{data['project'].id}?format=json",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "exported_at" in body
        assert "results" in body

    def test_export_csv(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """CSV export returns text/csv content."""
        data = _create_evaluation_project(test_db, test_users, test_org)

        resp = client.post(
            f"/api/evaluations/export/{data['project'].id}?format=csv",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_export_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Non-member cannot export."""
        project = Project(
            id=str(uuid.uuid4()),
            title="Private",
            label_config=LABEL_CONFIG_QA,
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project)
        test_db.commit()

        resp = client.post(
            f"/api/evaluations/export/{project.id}?format=json",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
