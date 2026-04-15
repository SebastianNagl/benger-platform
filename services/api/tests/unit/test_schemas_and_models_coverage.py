"""
Unit tests for project_schemas.py, schemas/, and model validation — covers schema creation and validation.
"""

from unittest.mock import Mock

import pytest


class TestProjectSchemasValidation:
    """Tests for project_schemas.py validation logic."""

    def test_skip_task_request_empty(self):
        from project_schemas import SkipTaskRequest
        req = SkipTaskRequest()
        assert req is not None


class TestEvaluationSchemas:
    """Tests for schemas/evaluation_schemas.py."""

    def test_sample_evaluation_list_response(self):
        from schemas.evaluation_schemas import SampleEvaluationListResponse
        resp = SampleEvaluationListResponse(
            items=[], total=0, page=1, page_size=50, has_next=False
        )
        assert resp.total == 0

    def test_metric_distribution(self):
        from schemas.evaluation_schemas import MetricDistribution
        dist = MetricDistribution(
            metric_name="accuracy",
            mean=0.85,
            median=0.87,
            std=0.05,
            min=0.7,
            max=0.95,
            quartiles={"q1": 0.8, "q2": 0.87, "q3": 0.9},
            histogram={},
        )
        assert dist.mean == 0.85

    def test_confusion_matrix(self):
        from schemas.evaluation_schemas import ConfusionMatrix
        cm = ConfusionMatrix(
            field_name="answer",
            labels=["A", "B"],
            matrix=[[5, 1], [2, 4]],
            accuracy=0.75,
            precision_per_class={"A": 0.71, "B": 0.8},
            recall_per_class={"A": 0.83, "B": 0.67},
            f1_per_class={"A": 0.77, "B": 0.73},
        )
        assert cm.accuracy == 0.75

    def test_config_validation_result(self):
        from schemas.evaluation_schemas import ConfigValidationResult
        result = ConfigValidationResult(
            valid=True,
            errors=[],
            warnings=["Minor issue"],
            generation_fields=["answer"],
            evaluation_fields=["answer"],
            matched_fields=["answer"],
            missing_in_evaluation=[],
            missing_in_generation=[],
        )
        assert result.valid is True


class TestEvaluationHelpers:
    """Tests for evaluation helper types."""

    def test_evaluation_results_response(self):
        from routers.evaluations.helpers import EvaluationResultsResponse
        from datetime import datetime
        resp = EvaluationResultsResponse(
            project_id="proj-1",
            results={"type": "automated", "metrics": {"accuracy": 0.9}},
            metadata={},
            created_at=datetime(2025, 1, 1),
        )
        assert resp.project_id == "proj-1"

    def test_evaluation_status(self):
        from routers.evaluations.helpers import EvaluationStatus
        status = EvaluationStatus(
            id="eval-1", status="completed", message="Done"
        )
        assert status.status == "completed"

class TestOrganizationModels:
    """Tests for organization-related Pydantic models."""

    def test_organization_create(self):
        from routers.organizations import OrganizationCreate
        org = OrganizationCreate(
            name="New Org",
            display_name="New Organization",
            slug="new-org",
        )
        assert org.slug == "new-org"

    def test_organization_update(self):
        from routers.organizations import OrganizationUpdate
        update = OrganizationUpdate(name="Updated Name")
        assert update.name == "Updated Name"
        assert update.description is None

    def test_organization_member_response(self):
        from routers.organizations import OrganizationMemberResponse
        from models import OrganizationRole
        from datetime import datetime
        resp = OrganizationMemberResponse(
            id="mem-1",
            user_id="user-1",
            organization_id="org-1",
            role=OrganizationRole.ANNOTATOR,
            is_active=True,
            joined_at=datetime(2025, 1, 1),
            user_name="Test User",
            user_email="test@test.com",
        )
        assert resp.user_name == "Test User"

    def test_update_member_role(self):
        from routers.organizations import UpdateMemberRole
        from models import OrganizationRole
        update = UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR)
        assert update.role == OrganizationRole.CONTRIBUTOR

    def test_add_user_to_organization(self):
        from routers.organizations import AddUserToOrganization
        add = AddUserToOrganization(user_id="user-1")
        assert add.user_id == "user-1"

    def test_verify_email_request(self):
        from routers.organizations import VerifyEmailRequest
        req = VerifyEmailRequest(reason="Admin verification")
        assert req.reason == "Admin verification"

    def test_bulk_verify_email_request(self):
        from routers.organizations import BulkVerifyEmailRequest
        req = BulkVerifyEmailRequest(user_ids=["u1", "u2"], reason="Batch")
        assert len(req.user_ids) == 2

    def test_user_response(self):
        from routers.organizations import UserResponse
        from datetime import datetime
        resp = UserResponse(
            id="u1",
            username="testuser",
            email="test@test.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime(2025, 1, 1),
        )
        assert resp.username == "testuser"

    def test_user_superadmin_update(self):
        from routers.organizations import UserSuperadminUpdate
        update = UserSuperadminUpdate(is_superadmin=True)
        assert update.is_superadmin is True


class TestStatisticsModels:
    """Tests for statistics-related models in metadata.py."""

    def test_statistics_request(self):
        from routers.evaluations.metadata import StatisticsRequest
        req = StatisticsRequest(metrics=["accuracy", "bleu"])
        assert len(req.metrics) == 2
        assert req.aggregation == "model"

    def test_metric_statistics(self):
        from routers.evaluations.metadata import MetricStatistics
        stats = MetricStatistics(
            mean=0.85, std=0.05, ci_lower=0.8, ci_upper=0.9, n=100
        )
        assert stats.mean == 0.85

    def test_pairwise_comparison(self):
        from routers.evaluations.metadata import PairwiseComparison
        comp = PairwiseComparison(
            model_a="gpt-4", model_b="claude-3", metric="accuracy",
            ttest_p=0.03, ttest_significant=True, significant=True,
        )
        assert comp.significant is True

    def test_model_statistics(self):
        from routers.evaluations.metadata import ModelStatistics, MetricStatistics
        stats = ModelStatistics(
            model_id="gpt-4",
            model_name="GPT-4",
            metrics={
                "accuracy": MetricStatistics(
                    mean=0.9, std=0.02, ci_lower=0.88, ci_upper=0.92, n=50
                )
            },
            sample_count=50,
        )
        assert stats.model_id == "gpt-4"

    def test_raw_score(self):
        from routers.evaluations.metadata import RawScore
        score = RawScore(
            model_id="gpt-4", metric="accuracy", value=0.95
        )
        assert score.value == 0.95

    def test_statistics_response(self):
        from routers.evaluations.metadata import StatisticsResponse, MetricStatistics
        resp = StatisticsResponse(
            aggregation="model",
            metrics={
                "accuracy": MetricStatistics(
                    mean=0.85, std=0.05, ci_lower=0.8, ci_upper=0.9, n=100
                )
            },
        )
        assert resp.aggregation == "model"
