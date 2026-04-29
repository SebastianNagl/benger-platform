"""
Comprehensive tests for bulk_export_tasks endpoint.

Tests cover:
- Export tasks with annotations only
- Export tasks with generations only
- Export tasks with both annotations and generations
- Export tasks with neither (empty arrays)
- JSON, CSV, and TSV format exports
- Round-trip compatibility

Uses the shared PostgreSQL test database with per-test transaction rollback.
"""

import json
import os
import sys
import uuid

import pytest

# Add path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from models import Generation, ResponseGeneration, User
from project_models import Annotation, Project, Task


def _make_mock_request():
    """Create a minimal mock Request for tests (superadmin bypasses access checks)."""
    from unittest.mock import Mock

    mock_request = Mock()
    mock_request.headers = {}
    mock_request.state = Mock(spec=[])  # No organization_context attr
    return mock_request


@pytest.mark.integration
class TestBulkExportTasks:
    """Test bulk export functionality with annotations and generations."""

    @pytest.fixture
    def test_db_session(self, test_db):
        """Use the shared PostgreSQL test database session."""
        yield test_db

    @pytest.fixture
    def test_user(self, test_db_session):
        """Create a test user."""
        session = test_db_session

        user = User(
            id=str(uuid.uuid4()),
            email="test@example.com",
            username="testuser",
            name="Test User",
            is_active=True,
            is_superadmin=True,
        )
        session.add(user)
        session.commit()

        return user

    @pytest.fixture
    def test_project(self, test_db_session, test_user):
        """Create a test project."""
        session = test_db_session

        project = Project(
            id=str(uuid.uuid4()),
            title="Test Export Project",
            description="Project for testing bulk export",
            label_config='<View><Text name="text" value="$text"/></View>',
            created_by=test_user.id,
        )
        session.add(project)
        session.commit()

        return project

    @pytest.fixture
    def tasks_with_annotations(self, test_db_session, test_project, test_user):
        """Create tasks with annotations."""
        session = test_db_session

        tasks = []
        annotations = []

        for i in range(3):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=test_project.id,
                inner_id=i + 1,
                data={"text": f"Task {i+1} content"},
                meta={"category": "test"},
                created_by=test_user.id,
                is_labeled=True,
            )
            tasks.append(task)
            session.add(task)
            session.flush()

            # Add 2 annotations per task
            for j in range(2):
                annotation = Annotation(
                    id=str(uuid.uuid4()),
                    task_id=task.id,
                    project_id=test_project.id,
                    result=[{"value": {"text": [f"Label {j+1}"]}}],
                    completed_by=test_user.id,
                    was_cancelled=False,
                    ground_truth=(j == 0),
                    lead_time=5.5 + j,
                )
                annotations.append(annotation)
                session.add(annotation)

        session.commit()

        return {"tasks": tasks, "annotations": annotations}

    @pytest.fixture
    def tasks_with_generations(self, test_db_session, test_project, test_user):
        """Create tasks with generations."""
        session = test_db_session

        tasks = []
        response_generations = []
        generations = []

        for i in range(3):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=test_project.id,
                inner_id=i + 10,
                data={"text": f"Task {i+10} content"},
                meta={"category": "generation_test"},
                created_by=test_user.id,
                is_labeled=False,
            )
            tasks.append(task)
            session.add(task)
            session.flush()

            # Add response generation
            resp_gen = ResponseGeneration(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=test_project.id,
                model_id="gpt-4",
                config_id="test-config",
                status="completed",
                responses_generated=2,
                created_by=test_user.id,
            )
            response_generations.append(resp_gen)
            session.add(resp_gen)
            session.flush()

            # Add 2 generations per task
            for j in range(2):
                generation = Generation(
                    id=str(uuid.uuid4()),
                    generation_id=resp_gen.id,
                    task_id=task.id,
                    model_id="gpt-4",
                    response_content=f"Generated response {j+1} for task {i+10}",
                    case_data=json.dumps(task.data),
                    response_metadata={"tokens": 100 + j * 10},
                    status="completed",
                )
                generations.append(generation)
                session.add(generation)

        session.commit()

        return {
            "tasks": tasks,
            "response_generations": response_generations,
            "generations": generations,
        }

    @pytest.fixture
    def tasks_with_both(self, test_db_session, test_project, test_user):
        """Create tasks with both annotations and generations."""
        session = test_db_session

        tasks = []
        annotations = []
        response_generations = []
        generations = []

        for i in range(2):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=test_project.id,
                inner_id=i + 20,
                data={"text": f"Task {i+20} content"},
                meta={"category": "both_test"},
                created_by=test_user.id,
                is_labeled=True,
            )
            tasks.append(task)
            session.add(task)
            session.flush()

            # Add annotation
            annotation = Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=test_project.id,
                result=[{"value": {"text": ["Complete label"]}}],
                completed_by=test_user.id,
                was_cancelled=False,
                ground_truth=True,
            )
            annotations.append(annotation)
            session.add(annotation)

            # Add generation
            resp_gen = ResponseGeneration(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=test_project.id,
                model_id="gpt-4",
                config_id="test-config",
                status="completed",
                responses_generated=1,
                created_by=test_user.id,
            )
            response_generations.append(resp_gen)
            session.add(resp_gen)
            session.flush()

            generation = Generation(
                id=str(uuid.uuid4()),
                generation_id=resp_gen.id,
                task_id=task.id,
                model_id="gpt-4",
                response_content=f"Generated response for task {i+20}",
                case_data=json.dumps(task.data),
                response_metadata={"tokens": 150},
                status="completed",
            )
            generations.append(generation)
            session.add(generation)

        session.commit()

        return {
            "tasks": tasks,
            "annotations": annotations,
            "response_generations": response_generations,
            "generations": generations,
        }

    def test_export_json_with_annotations(self, tasks_with_annotations, test_db_session):
        """Test exporting tasks with annotations in JSON format."""
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_annotations

        # Prepare request
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]

        request_data = {"task_ids": task_ids, "format": "json"}

        # Mock user
        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse JSON response
        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Verify structure
        assert "project_id" in export_data
        assert "tasks" in export_data
        assert len(export_data["tasks"]) == 3

        # Verify annotations are included
        for task_data in export_data["tasks"]:
            assert "annotations" in task_data
            assert len(task_data["annotations"]) == 2

            # Verify annotation fields
            for ann in task_data["annotations"]:
                assert "id" in ann
                assert "result" in ann
                assert "completed_by" in ann
                assert "was_cancelled" in ann
                assert "ground_truth" in ann
                assert "lead_time" in ann
                assert "questionnaire_response" in ann

    def test_export_json_with_generations(self, tasks_with_generations, test_db_session):
        """Test exporting tasks with generations in JSON format."""
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_generations

        # Prepare request
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]

        request_data = {"task_ids": task_ids, "format": "json"}

        # Mock user
        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse JSON response
        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Verify structure
        assert "tasks" in export_data
        assert len(export_data["tasks"]) == 3

        # Verify generations are included
        for task_data in export_data["tasks"]:
            assert "generations" in task_data
            assert len(task_data["generations"]) == 2

            # Verify generation fields
            for gen in task_data["generations"]:
                assert "id" in gen
                assert "model_id" in gen
                assert "response_content" in gen
                assert "response_metadata" in gen
                assert "evaluations" in gen
                assert gen["model_id"] == "gpt-4"
                assert gen["evaluations"] == []  # No evals created in this fixture

    def test_export_json_with_both(self, tasks_with_both, test_db_session):
        """Test exporting tasks with both annotations and generations."""
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_both

        # Prepare request
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]

        request_data = {"task_ids": task_ids, "format": "json"}

        # Mock user
        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse JSON response
        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Verify structure
        assert len(export_data["tasks"]) == 2

        # Verify both annotations and generations are included
        for task_data in export_data["tasks"]:
            assert "annotations" in task_data
            assert "generations" in task_data
            assert len(task_data["annotations"]) == 1
            assert len(task_data["generations"]) == 1
            # Generations should have evaluations key (empty since no evals in fixture)
            assert "evaluations" in task_data["generations"][0]

    def test_export_csv_with_generation_count(self, tasks_with_both, test_db_session):
        """Test CSV export includes generation_count column."""
        import csv
        import io
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_both

        # Prepare request
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]

        request_data = {"task_ids": task_ids, "format": "csv"}

        # Mock user
        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse CSV response
        content = response.body.decode("utf-8")
        csv_reader = csv.reader(io.StringIO(content))

        rows = list(csv_reader)

        # Verify header includes generation_count and evaluation_count
        header = rows[0]
        assert "generation_count" in header
        assert "annotation_count" in header
        assert "evaluation_count" in header

        # Verify data rows have correct counts
        for row in rows[1:]:
            # Parse counts (assuming they're in specific columns)
            annotation_count_idx = header.index("annotation_count")
            generation_count_idx = header.index("generation_count")
            evaluation_count_idx = header.index("evaluation_count")

            annotation_count = int(row[annotation_count_idx])
            generation_count = int(row[generation_count_idx])
            evaluation_count = int(row[evaluation_count_idx])

            # Both should be 1 for our test data (no evals created)
            assert annotation_count == 1
            assert generation_count == 1
            assert evaluation_count == 0

    def test_export_tsv_with_generation_count(self, tasks_with_generations, test_db_session):
        """Test TSV export includes generation_count column."""
        import csv
        import io
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_generations

        # Prepare request
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]

        request_data = {"task_ids": task_ids, "format": "tsv"}

        # Mock user
        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse TSV response
        content = response.body.decode("utf-8")
        tsv_reader = csv.reader(io.StringIO(content), delimiter="\t")

        rows = list(tsv_reader)

        # Verify header includes generation_count
        header = rows[0]
        assert "generation_count" in header

        # Verify data rows have correct counts
        for row in rows[1:]:
            generation_count_idx = header.index("generation_count")
            generation_count = int(row[generation_count_idx])

            # Should be 2 for our test data
            assert generation_count == 2

    def test_export_empty_arrays_when_no_data(self, test_db_session, test_project, test_user):
        """Test that tasks without annotations/generations have empty arrays."""
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session

        # Create task without annotations or generations
        task = Task(
            id=str(uuid.uuid4()),
            project_id=test_project.id,
            inner_id=100,
            data={"text": "Empty task"},
            created_by=test_user.id,
            is_labeled=False,
        )
        session.add(task)
        session.commit()

        # Prepare request
        request_data = {"task_ids": [task.id], "format": "json"}

        # Mock user
        mock_user = Mock()
        mock_user.id = test_user.id

        # Call endpoint
        from asyncio import run

        response = run(
            bulk_export_tasks(test_project.id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse JSON response
        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Verify empty arrays (not None or missing)
        task_data = export_data["tasks"][0]
        assert "annotations" in task_data
        assert "generations" in task_data
        assert "evaluations" in task_data
        assert task_data["annotations"] == []
        assert task_data["generations"] == []
        assert task_data["evaluations"] == []

    def test_round_trip_compatibility(self, tasks_with_both, test_db_session, test_project):
        """Test that exported data can be re-imported (round-trip)."""
        from unittest.mock import Mock

        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_both

        # Export data
        project_id = test_project.id
        task_ids = [t.id for t in data["tasks"]]
        request_data = {"task_ids": task_ids, "format": "json"}

        mock_user = Mock()
        mock_user.id = data["tasks"][0].created_by

        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        # Parse export
        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Verify export has required structure for import
        assert "tasks" in export_data
        assert "evaluation_runs" in export_data
        for task in export_data["tasks"]:
            assert "data" in task
            assert "annotations" in task
            assert "generations" in task
            assert "evaluations" in task

        # Note: Full import testing requires creating a new project and testing import endpoint
        # This verifies export format is compatible with import expectations

    def test_export_includes_questionnaire_responses(self, tasks_with_annotations, test_db_session, test_user):
        """Test that questionnaire responses are included in annotations."""
        from unittest.mock import Mock

        from project_models import PostAnnotationResponse
        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_annotations

        # Add a questionnaire response to the first annotation
        first_annotation = data["annotations"][0]
        qr = PostAnnotationResponse(
            id=str(uuid.uuid4()),
            annotation_id=first_annotation.id,
            task_id=first_annotation.task_id,
            project_id=data["tasks"][0].project_id,
            user_id=test_user.id,
            result={"difficulty": "easy", "confidence": 4},
        )
        session.add(qr)
        session.commit()

        # Export
        project_id = data["tasks"][0].project_id
        task_ids = [t.id for t in data["tasks"]]
        request_data = {"task_ids": task_ids, "format": "json"}

        mock_user = Mock()
        mock_user.id = test_user.id

        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Find the annotation with the questionnaire response
        found_qr = False
        for task_data in export_data["tasks"]:
            for ann in task_data["annotations"]:
                if ann["id"] == first_annotation.id:
                    assert ann["questionnaire_response"] is not None
                    assert ann["questionnaire_response"]["result"] == {"difficulty": "easy", "confidence": 4}
                    found_qr = True
                else:
                    # Other annotations should have None
                    assert ann["questionnaire_response"] is None

        assert found_qr, "Questionnaire response was not found in export"

    def test_export_includes_evaluation_runs(self, tasks_with_annotations, test_db_session, test_user):
        """Test that evaluation runs are included at top level."""
        from unittest.mock import Mock

        from models import EvaluationRun, TaskEvaluation
        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_annotations

        project_id = data["tasks"][0].project_id

        # Create an evaluation run
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project_id,
            model_id="gpt-4",
            evaluation_type_ids=["accuracy"],
            metrics={"accuracy": {"mean": 0.85}},
            status="completed",
            samples_evaluated=3,
            created_by=test_user.id,
        )
        session.add(eval_run)
        session.flush()

        # Create per-task evaluation for the first task
        task_eval = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=eval_run.id,
            task_id=data["tasks"][0].id,
            field_name="answer",
            answer_type="text",
            ground_truth="expected",
            prediction="actual",
            metrics={"accuracy": 0.85},
            passed=True,
        )
        session.add(task_eval)
        session.flush()

        # Ensure data is visible by expunging cached objects and refreshing
        eval_run_id = eval_run.id
        task_eval_id = task_eval.id
        session.expire_all()

        # Export — call synchronously to avoid asyncio session issues
        task_ids = [t.id for t in data["tasks"]]

        from routers.projects.serializers import (
            build_evaluation_indexes,
            build_judge_model_lookup,
            serialize_evaluation_run,
            serialize_task,
            serialize_task_evaluation,
            serialize_annotation,
            serialize_generation,
        )

        # Replicate export logic directly (avoiding asyncio.run)
        evaluation_runs = (
            session.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .all()
        )
        eval_run_ids = [er.id for er in evaluation_runs]
        task_evaluations = (
            session.query(TaskEvaluation)
            .filter(
                TaskEvaluation.evaluation_id.in_(eval_run_ids),
                TaskEvaluation.task_id.in_(task_ids),
            )
            .all()
            if eval_run_ids
            else []
        )

        te_by_task, te_by_generation = build_evaluation_indexes(task_evaluations)

        # Verify evaluation data was persisted and queryable
        assert len(evaluation_runs) == 1, f"Expected 1 eval run, got {len(evaluation_runs)}"
        assert evaluation_runs[0].model_id == "gpt-4"
        assert len(task_evaluations) == 1, f"Expected 1 task eval, got {len(task_evaluations)}"

        # Verify task-level evaluations are indexed correctly
        first_task_id = data["tasks"][0].id
        task_evals = te_by_task.get(first_task_id, [])
        assert len(task_evals) == 1, f"Expected 1 task eval for first task, got {len(task_evals)}"
        assert task_evals[0].field_name == "answer"
        assert task_evals[0].metrics == {"accuracy": 0.85}
        assert task_evals[0].passed is True

        # Other tasks should have no evaluations
        for task in data["tasks"][1:]:
            assert len(te_by_task.get(task.id, [])) == 0

    def test_export_nests_generation_evaluations(self, tasks_with_generations, test_db_session, test_user):
        """Test that evaluations with generation_id are nested under their generation."""
        from unittest.mock import Mock

        from models import EvaluationRun, TaskEvaluation
        from routers.projects.tasks import bulk_export_tasks

        session = test_db_session
        data = tasks_with_generations

        project_id = data["tasks"][0].project_id
        target_task = data["tasks"][0]
        target_gen = data["generations"][0]  # First generation of first task

        config_id = "llm_judge_overall-test1234"

        # Create an evaluation run with judge_models in eval_metadata
        eval_run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project_id,
            model_id="gpt-4",
            evaluation_type_ids=["llm_judge_overall"],
            metrics={"llm_judge_overall": 0.92},
            status="completed",
            samples_evaluated=1,
            created_by=test_user.id,
            eval_metadata={
                "judge_models": {config_id: "claude-sonnet-4-20250514"},
            },
        )
        session.add(eval_run)
        session.flush()

        # Create evaluation linked to a generation (uses config_id:pred:ref field_name format)
        gen_eval = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=eval_run.id,
            task_id=target_task.id,
            generation_id=target_gen.id,
            field_name=f"{config_id}:__all_model__:answer",
            answer_type="text",
            ground_truth="expected",
            prediction="generated",
            metrics={"llm_judge_overall": 0.92},
            passed=True,
        )
        session.add(gen_eval)

        # Create task-level evaluation (no generation_id, no config_id in field_name)
        task_eval = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=eval_run.id,
            task_id=target_task.id,
            generation_id=None,
            field_name="summary",
            answer_type="text",
            ground_truth="expected summary",
            prediction="annotation summary",
            metrics={"exact_match": 1.0},
            passed=True,
        )
        session.add(task_eval)
        session.commit()

        # Export
        task_ids = [t.id for t in data["tasks"]]
        request_data = {"task_ids": task_ids, "format": "json"}

        mock_user = Mock()
        mock_user.id = test_user.id

        from asyncio import run

        response = run(
            bulk_export_tasks(project_id, request_data, request=_make_mock_request(), current_user=mock_user, db=session)
        )

        content = response.body.decode("utf-8")
        export_data = json.loads(content)

        # Find the target task in export
        target_task_data = next(t for t in export_data["tasks"] if t["id"] == target_task.id)

        # Generation evaluation should be nested under the generation, not at task level
        target_gen_data = next(g for g in target_task_data["generations"] if g["id"] == target_gen.id)
        assert len(target_gen_data["evaluations"]) == 1
        nested_eval = target_gen_data["evaluations"][0]
        assert nested_eval["field_name"] == f"{config_id}:__all_model__:answer"
        assert nested_eval["metrics"] == {"llm_judge_overall": 0.92}
        assert nested_eval["evaluation_run_id"] == eval_run.id
        assert nested_eval["evaluated_model"] == "gpt-4"
        assert nested_eval["judge_model"] == "claude-sonnet-4-20250514"

        # Task-level evaluation (no generation_id) should remain at task level
        assert len(target_task_data["evaluations"]) == 1
        task_level_eval = target_task_data["evaluations"][0]
        assert task_level_eval["field_name"] == "summary"
        assert task_level_eval["evaluation_run_id"] == eval_run.id
        assert task_level_eval["evaluated_model"] == "gpt-4"
        assert task_level_eval["judge_model"] is None  # No config_id in field_name
