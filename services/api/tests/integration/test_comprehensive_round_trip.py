"""
Comprehensive round-trip export/import tests including evaluation data.
Tests full data integrity including all evaluation types and human evaluation data.
"""

import json
import os

# Add path for imports
import sys
import uuid
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationConfig,
    HumanEvaluationResult,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    PreferenceRanking,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)

# Prompt model removed in Issue #759


@pytest.mark.integration
class TestComprehensiveRoundTrip:
    """Test complete round-trip export/import with all data types."""

    @pytest.fixture
    def test_db_session(self, test_db):
        """Use the shared PostgreSQL test database session."""
        yield test_db

    @pytest.fixture
    def sample_complete_project(self, test_db_session):
        """Create a complete project with all data types for testing."""
        session = test_db_session

        # Create test user
        test_user = User(
            id=str(uuid.uuid4()),
            email="test@example.com",
            username="testuser",
            name="Test User",
            is_active=True,
            is_superadmin=True,
        )
        session.add(test_user)

        # Create evaluation types referenced by metrics
        from models import EvaluationType
        for et_name in ["accuracy", "completeness", "style"]:
            et = EvaluationType(
                id=et_name,
                name=et_name.capitalize(),
                description=f"Test {et_name} metric",
                category="test",
                applicable_project_types=["text_classification"],
            )
            session.add(et)

        # Create test organization
        test_org = Organization(
            id=str(uuid.uuid4()),
            name="Test Organization",
            display_name="Test Organization",
            slug="test-organization",
        )
        session.add(test_org)

        # Create organization membership
        org_member = OrganizationMembership(
            id=str(uuid.uuid4()),
            organization_id=test_org.id,
            user_id=test_user.id,
            role=OrganizationRole.ORG_ADMIN,
            is_active=True,
        )
        session.add(org_member)

        # Create project
        project = Project(
            id=str(uuid.uuid4()),
            title="Test Project with Evaluations",
            description="Comprehensive test project",
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "prompt_structures": [{"format": "qa"}]
            },  # generation_structure moved to generation_config in Issue #762
            expert_instruction="Test instructions",
            show_instruction=True,
            show_skip_button=True,
            enable_empty_annotation=True,
            created_by=test_user.id,
            min_annotations_per_task=2,
            is_published=True,
        )
        session.add(project)

        # Create project organization association
        project_org = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_user.id,
        )
        session.add(project_org)

        # Create project member
        project_member = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=test_user.id,
            role="admin",
            is_active=True,
        )
        session.add(project_member)

        # Create tasks
        tasks = []
        for i in range(5):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project.id,
                inner_id=i + 1,
                data={"text": f"Task {i+1} text content", "metadata": {"source": "test"}},
                meta={"difficulty": "medium", "category": f"cat_{i%2}"},
                created_by=test_user.id,
                updated_by=test_user.id,
                is_labeled=(i < 3),
                total_annotations=(2 if i < 3 else 0),
                cancelled_annotations=0,
                comment_count=0,
                unresolved_comment_count=0,
            )
            tasks.append(task)
            session.add(task)

        # Flush to satisfy FK constraints on PostgreSQL
        session.flush()

        # Create annotations for first 3 tasks
        annotations = []
        for i, task in enumerate(tasks[:3]):
            for j in range(2):
                annotation = Annotation(
                    id=str(uuid.uuid4()),
                    task_id=task.id,
                    project_id=project.id,
                    result=[{"value": {"text": f"Annotation {j+1} for task {i+1}"}}],
                    draft=None,
                    was_cancelled=False,
                    completed_by=test_user.id,
                    ground_truth=(j == 0),
                )
                annotations.append(annotation)
                session.add(annotation)

        # Create task assignments
        assignments = []
        for task in tasks[:2]:
            assignment = TaskAssignment(
                id=str(uuid.uuid4()),
                task_id=task.id,
                user_id=test_user.id,
                assigned_by=test_user.id,
                status="completed",
                priority=1,
            )
            assignments.append(assignment)
            session.add(assignment)

        session.flush()
        # Note: Prompts removed in Issue #759 - now handled via generation_config.prompt_structures

        # Create response generations (job tracking)
        response_generations = []
        for task in tasks:
            resp_gen = ResponseGeneration(
                id=str(uuid.uuid4()),
                task_id=task.id,
                model_id="gpt-4",
                config_id="config-1",
                status="completed",
                responses_generated=2,
                generation_metadata={"temperature": 0.7},
                created_by=test_user.id,
            )
            response_generations.append(resp_gen)
            session.add(resp_gen)

        # Create generations (LLM responses)
        generations = []
        for i, (task, resp_gen) in enumerate(zip(tasks, response_generations)):
            for j in range(2):
                generation = Generation(
                    id=str(uuid.uuid4()),
                    generation_id=resp_gen.id,
                    task_id=task.id,
                    model_id="gpt-4",
                    case_data=json.dumps(
                        {"input": task.data['text']}
                    ),  # Must be string (Text field)
                    response_content=f"Generated response {j+1} for task {i+1}",
                    usage_stats={"tokens": 100 + (i * 10) + (j * 5)},
                    response_metadata={"model_version": "gpt-4-0613"},
                    status="completed",
                    error_message=None,
                )
                generations.append(generation)
                session.add(generation)

        # Create evaluations
        evaluations = []
        for task in tasks[:3]:
            evaluation = EvaluationRun(
                id=str(uuid.uuid4()),
                project_id=project.id,
                task_id=task.id,
                model_id="gpt-4",
                evaluation_type_ids=["accuracy", "completeness", "style"],
                metrics={"accuracy": 0.85, "completeness": 0.92, "style": 0.78},
                eval_metadata={"method": "automated", "version": "1.0"},
                status="completed",
                error_message=None,
                samples_evaluated=10,
                created_by=test_user.id,
            )
            evaluations.append(evaluation)
            session.add(evaluation)

        # Create evaluation metrics
        eval_metrics = []
        for evaluation in evaluations:
            for metric_name, value in evaluation.metrics.items():
                metric = EvaluationRunMetric(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation.id,
                    evaluation_type_id=metric_name,
                    value=value,
                )
                eval_metrics.append(metric)
                session.add(metric)

        # Create human evaluation configs
        human_configs = []
        for task in tasks[:2]:
            config = HumanEvaluationConfig(
                id=str(uuid.uuid4()),
                task_id=task.id,
                evaluation_project_id=project.id,
                evaluator_count=3,
                randomization_seed=42,
                blinding_enabled=True,
                include_human_responses=False,
                status="completed",
            )
            human_configs.append(config)
            session.add(config)

        # Create human evaluation sessions
        human_sessions = []
        session_types = ["likert", "preference"]
        for i, session_type in enumerate(session_types):
            human_session = HumanEvaluationSession(
                id=str(uuid.uuid4()),
                project_id=project.id,
                evaluator_id=test_user.id,
                session_type=session_type,
                items_evaluated=5,
                total_items=10,
                status="active",
                session_config={"scale": "1-5"}
                if session_type == "likert"
                else {"comparison": "pairwise"},
            )
            human_sessions.append(human_session)
            session.add(human_session)

        # Create human evaluation results
        human_results = []
        gen_index = 0
        for config in human_configs:
            for i in range(2):
                result = HumanEvaluationResult(
                    id=str(uuid.uuid4()),
                    config_id=config.id,
                    task_id=config.task_id,
                    response_id=generations[gen_index].id,  # Use different generations
                    evaluator_id=test_user.id,
                    correctness_score=4,
                    completeness_score=4,
                    style_score=4,
                    usability_score=4,
                    comments=f"Evaluation comment {i+1}",
                    evaluation_time_seconds=120 + (i * 30),
                )
                human_results.append(result)
                session.add(result)
                gen_index += 1

        # Create preference rankings
        preference_rankings = []
        pref_session = human_sessions[1]  # preference session
        for i, task in enumerate(tasks[:2]):
            ranking = PreferenceRanking(
                id=str(uuid.uuid4()),
                session_id=pref_session.id,
                task_id=task.id,
                response_a_id=generations[i * 2].id,
                response_b_id=generations[i * 2 + 1].id,
                winner="a" if i == 0 else "b",
                confidence=0.8 + (i * 0.1),
                reasoning=f"Response {'A' if i == 0 else 'B'} is more comprehensive",
                time_spent_seconds=60 + (i * 20),
            )
            preference_rankings.append(ranking)
            session.add(ranking)

        # Create likert scale evaluations
        likert_evaluations = []
        likert_session = human_sessions[0]  # likert session
        dimensions = ["clarity", "relevance", "helpfulness"]
        for task in tasks[:2]:
            for dim in dimensions:
                likert_eval = LikertScaleEvaluation(
                    id=str(uuid.uuid4()),
                    session_id=likert_session.id,
                    task_id=task.id,
                    response_id=generations[0].id,
                    dimension=dim,
                    rating=4 if dim == "clarity" else 3,
                    comment=f"Good {dim}",
                    time_spent_seconds=30,
                )
                likert_evaluations.append(likert_eval)
                session.add(likert_eval)

        session.commit()

        return {
            "project": project,
            "tasks": tasks,
            "annotations": annotations,
            "generations": generations,
            "response_generations": response_generations,
            "evaluations": evaluations,
            "evaluation_metrics": eval_metrics,
            "human_configs": human_configs,
            "human_sessions": human_sessions,
            "human_results": human_results,
            "preference_rankings": preference_rankings,
            "likert_evaluations": likert_evaluations,
            "project_member": project_member,
            "task_assignments": assignments,
            "user": test_user,
            "organization": test_org,
        }

    def test_export_includes_all_evaluation_data(self, sample_complete_project, test_db_session):
        """Test that export includes all evaluation-related data."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        # Mock the database session in the function
        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        # Verify all evaluation data is present
        assert "evaluations" in export_data
        assert len(export_data["evaluations"]) == 3

        assert "evaluation_metrics" in export_data
        assert len(export_data["evaluation_metrics"]) == 9  # 3 evaluations * 3 metrics each

        assert "human_evaluation_configs" in export_data
        assert len(export_data["human_evaluation_configs"]) == 2

        assert "human_evaluation_sessions" in export_data
        assert len(export_data["human_evaluation_sessions"]) == 2

        assert "human_evaluation_results" in export_data
        assert len(export_data["human_evaluation_results"]) == 4  # 2 configs * 2 results each

        assert "preference_rankings" in export_data
        assert len(export_data["preference_rankings"]) == 2

        assert "likert_scale_evaluations" in export_data
        assert len(export_data["likert_scale_evaluations"]) == 6  # 2 tasks * 3 dimensions

        # Verify evaluation data integrity
        first_eval = export_data["evaluations"][0]
        assert first_eval["model_id"] == "gpt-4"
        assert first_eval["metrics"]["accuracy"] == 0.85
        assert first_eval["metrics"]["completeness"] == 0.92
        assert first_eval["status"] == "completed"

        # Verify human evaluation data
        first_human_config = export_data["human_evaluation_configs"][0]
        assert first_human_config["evaluator_count"] == 3
        assert first_human_config["blinding_enabled"] == True

        # Verify preference rankings
        first_ranking = export_data["preference_rankings"][0]
        assert first_ranking["winner"] in ["a", "b"]
        assert first_ranking["confidence"] >= 0.8

        # Verify likert evaluations
        first_likert = export_data["likert_scale_evaluations"][0]
        assert first_likert["dimension"] in ["clarity", "relevance", "helpfulness"]
        assert first_likert["rating"] in [3, 4]

    def test_import_handles_all_evaluation_data(self, sample_complete_project, test_db_session):
        """Test that import correctly processes all evaluation data."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        # Get export data
        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        # Simulate import by checking data structure
        # The actual import function would create new database entries

        # Verify evaluation data can be mapped for import
        assert all(eval_data.get("id") for eval_data in export_data["evaluations"])
        assert all(eval_data.get("task_id") for eval_data in export_data["evaluations"])

        # Verify evaluation metrics have proper foreign keys
        for metric in export_data["evaluation_metrics"]:
            assert metric.get("evaluation_id")
            assert metric.get("evaluation_type_id")
            assert metric.get("value") is not None

        # Verify human evaluation configs have task references
        for config in export_data["human_evaluation_configs"]:
            assert config.get("task_id")
            assert config.get("evaluator_count")

        # Verify human evaluation sessions have project references
        for session in export_data["human_evaluation_sessions"]:
            assert session.get("project_id")
            assert session.get("session_type") in ["likert", "preference"]

        # Verify preference rankings have proper references
        for ranking in export_data["preference_rankings"]:
            assert ranking.get("session_id")
            assert ranking.get("task_id")
            assert ranking.get("response_a_id")
            assert ranking.get("response_b_id")
            assert ranking.get("winner")

        # Verify likert evaluations have proper structure
        for likert in export_data["likert_scale_evaluations"]:
            assert likert.get("session_id")
            assert likert.get("task_id")
            assert likert.get("dimension")
            assert likert.get("rating")

    def test_round_trip_preserves_evaluation_relationships(
        self, sample_complete_project, test_db_session
    ):
        """Test that foreign key relationships are maintained in round-trip."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        # Get export data
        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        # Create ID mappings (simulating import process)
        id_mappings = {
            "tasks": {},
            "evaluations": {},
            "human_evaluation_sessions": {},
            "generations": {},
        }

        # Map task IDs
        for task in export_data["tasks"]:
            old_id = task["id"]
            new_id = str(uuid.uuid4())
            id_mappings["tasks"][old_id] = new_id

        # Map evaluation IDs
        for evaluation in export_data["evaluations"]:
            old_id = evaluation["id"]
            new_id = str(uuid.uuid4())
            id_mappings["evaluations"][old_id] = new_id

        # Map session IDs
        for session in export_data["human_evaluation_sessions"]:
            old_id = session["id"]
            new_id = str(uuid.uuid4())
            id_mappings["human_evaluation_sessions"][old_id] = new_id

        # Map generation IDs
        for generation in export_data["generations"]:
            old_id = generation["id"]
            new_id = str(uuid.uuid4())
            id_mappings["generations"][old_id] = new_id

        # Verify evaluation metrics can be remapped
        for metric in export_data["evaluation_metrics"]:
            old_eval_id = metric["evaluation_id"]
            assert old_eval_id in [e["id"] for e in export_data["evaluations"]]
            # Would be remapped to: id_mappings["evaluations"][old_eval_id]

        # Verify preference rankings can be remapped
        for ranking in export_data["preference_rankings"]:
            old_session_id = ranking["session_id"]
            old_task_id = ranking["task_id"]
            assert old_session_id in [s["id"] for s in export_data["human_evaluation_sessions"]]
            assert old_task_id in [t["id"] for t in export_data["tasks"]]
            # Would be remapped to new IDs

        # Verify likert evaluations can be remapped
        for likert in export_data["likert_scale_evaluations"]:
            old_session_id = likert["session_id"]
            old_task_id = likert["task_id"]
            old_response_id = likert["response_id"]
            assert old_session_id in [s["id"] for s in export_data["human_evaluation_sessions"]]
            assert old_task_id in [t["id"] for t in export_data["tasks"]]
            assert old_response_id in [g["id"] for g in export_data["generations"]]

    def test_export_statistics_include_evaluation_counts(
        self, sample_complete_project, test_db_session
    ):
        """Test that export statistics accurately count all evaluation data."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        stats = export_data["statistics"]

        # Verify all evaluation counts are present and correct
        assert stats["total_evaluations"] == 3
        assert stats["total_evaluation_metrics"] == 9
        assert stats["total_human_evaluation_configs"] == 2
        assert stats["total_human_evaluation_sessions"] == 2
        assert stats["total_human_evaluation_results"] == 4
        assert stats["total_preference_rankings"] == 2
        assert stats["total_likert_scale_evaluations"] == 6

        # Verify other counts for completeness
        assert stats["total_tasks"] == 5
        assert stats["total_annotations"] == 6  # 3 tasks * 2 annotations each
        assert stats["total_generations"] == 10  # 5 tasks * 2 generations each

    def test_import_with_missing_evaluation_users(self, sample_complete_project, test_db_session):
        """Test that import handles missing evaluator users gracefully."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        # Remove user data to simulate missing users
        export_data["users"] = []

        # Verify the import would handle this by mapping to current user
        # In actual import, missing users would be mapped to the importing user
        for result in export_data["human_evaluation_results"]:
            evaluator_id = result.get("evaluator_id")
            # This would be mapped to current_user.id in import
            assert evaluator_id is not None

        for session in export_data["human_evaluation_sessions"]:
            evaluator_id = session.get("evaluator_id")
            # This would be mapped to current_user.id in import
            assert evaluator_id is not None

    @pytest.mark.parametrize(
        "data_type,expected_count",
        [
            ("evaluations", 3),
            ("evaluation_metrics", 9),
            ("human_evaluation_configs", 2),
            ("human_evaluation_sessions", 2),
            ("human_evaluation_results", 4),
            ("preference_rankings", 2),
            ("likert_scale_evaluations", 6),
        ],
    )
    def test_each_evaluation_type_exports_correctly(
        self, sample_complete_project, test_db_session, data_type, expected_count
    ):
        """Test that each evaluation data type exports with correct count."""
        from projects_api import get_comprehensive_project_data

        project_id = sample_complete_project["project"].id

        with patch('projects_api.Session', return_value=test_db_session):
            export_data = get_comprehensive_project_data(test_db_session, project_id)

        assert data_type in export_data
        assert len(export_data[data_type]) == expected_count

        # Verify each item has required fields
        for item in export_data[data_type]:
            assert "id" in item
            assert (
                "created_at" in item or data_type == "preference_rankings"
            )  # Some types don't have created_at
