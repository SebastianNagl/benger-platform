"""
Comprehensive tests for evaluations router endpoints.
Tests the router architecture and endpoint functionality.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import EvaluationRun as DBEvaluationRun
from models import EvaluationType as DBEvaluationType
from models import User


class TestEvaluationsRouter:
    """Test evaluations router endpoints"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_evaluation(self):
        return DBEvaluationRun(
            id="eval-123",
            task_id="task-456",
            project_id="project-abc",
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": 0.85, "f1_score": 0.82},
            status="completed",
            eval_metadata={"evaluator": "human", "notes": "test evaluation"},
            samples_evaluated=100,
            created_by="user-123",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_evaluation_type(self):
        return DBEvaluationType(
            id="eval-type-123",
            name="Accuracy",
            description="Measures prediction accuracy",
            category="performance",
            higher_is_better=True,
            value_range={"min": 0.0, "max": 1.0},
            applicable_project_types=["qa", "classification"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_evaluations(self, mock_evaluation):
        eval2 = DBEvaluationRun(
            id="eval-456",
            task_id="task-789",
            project_id="project-xyz",
            model_id="claude-sonnet-4",
            evaluation_type_ids=["accuracy", "bleu"],
            metrics={"accuracy": 0.88, "bleu_score": 0.75},
            status="completed",
            eval_metadata={"evaluator": "automated"},
            samples_evaluated=150,
            created_by="user-456",
            created_at=datetime.now(timezone.utc),
        )
        return [mock_evaluation, eval2]

    @pytest.fixture
    def mock_evaluation_types(self, mock_evaluation_type):
        eval_type2 = DBEvaluationType(
            id="eval-type-456",
            name="BLEU Score",
            description="Measures translation/generation quality",
            category="nlg",
            higher_is_better=True,
            value_range={"min": 0.0, "max": 1.0},
            applicable_project_types=["generation", "translation"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        return [mock_evaluation_type, eval_type2]

    def test_get_evaluation_status_success(self, client, mock_user, mock_evaluation):
        """Test successful evaluation status retrieval"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_evaluation
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("routers.evaluations.status.check_project_accessible", return_value=True):
                response = client.get("/api/evaluations/evaluation/status/eval-123")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()

                assert data["id"] == "eval-123"
                assert data["status"] == "completed"
                assert data["message"] == "Evaluation status"
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_status_not_found(self, client, mock_user):
        """Test evaluation status retrieval when evaluation not found"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = None
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation/status/nonexistent-eval")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Evaluation 'nonexistent-eval' not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_status_with_error_message(self, client, mock_user):
        """Test evaluation status with error message"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        failed_evaluation = DBEvaluationRun(
            id="eval-failed",
            task_id="project-456",
            project_id="project-456",
            model_id="gpt-4o",
            metrics={},
            status="failed",
            error_message="Model API timeout",
            samples_evaluated=0,
            created_at=datetime.now(timezone.utc),
        )

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = failed_evaluation
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("routers.evaluations.status.check_project_accessible", return_value=True):
                response = client.get("/api/evaluations/evaluation/status/eval-failed")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()

                assert data["id"] == "eval-failed"
                assert data["status"] == "failed"
                assert data["message"] == "Model API timeout"
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluations_success(self, client, mock_user, mock_evaluations):
        """Test successful retrieval of all evaluations"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        # Make user a superadmin to see all evaluations
        mock_user.is_superadmin = True

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)

            # Create a mock user with organization memberships
            mock_db_user = Mock()
            mock_db_user.id = mock_user.id
            mock_db_user.organization_memberships = []  # Empty list so it's iterable

            # Setup query chain for user query
            mock_user_query = Mock()
            mock_user_query.filter.return_value.first.return_value = mock_db_user

            # Setup query chain for evaluations query
            mock_eval_query = Mock()
            mock_eval_query.order_by.return_value.all.return_value = mock_evaluations

            # Return appropriate query based on model being queried
            def query_side_effect(model):
                from models import User as UserModel

                if model == UserModel:
                    return mock_user_query
                else:
                    return mock_eval_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluations")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert isinstance(data, list)
            assert len(data) == 2

            # Verify first evaluation
            first_eval = data[0]
            assert first_eval["id"] == "eval-123"
            assert first_eval["project_id"] == "project-abc"
            assert first_eval["model_id"] == "gpt-4o"
            assert first_eval["metrics"]["accuracy"] == 0.85
            assert first_eval["metrics"]["f1_score"] == 0.82
            assert first_eval["status"] == "completed"
            assert first_eval["samples_evaluated"] == 100

            # Verify second evaluation
            second_eval = data[1]
            assert second_eval["id"] == "eval-456"
            assert second_eval["project_id"] == "project-xyz"
            assert second_eval["model_id"] == "claude-sonnet-4"
            assert second_eval["metrics"]["accuracy"] == 0.88
            assert second_eval["metrics"]["bleu_score"] == 0.75
            assert second_eval["samples_evaluated"] == 150
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluations_empty_result(self, client, mock_user):
        """Test retrieval when no evaluations exist"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)

            # Setup query chain for evaluations query
            mock_eval_query = Mock()
            mock_eval_query.order_by.return_value.filter.return_value.all.return_value = []
            mock_eval_query.order_by.return_value.all.return_value = []

            mock_db.query.return_value = mock_eval_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=[]):
                response = client.get("/api/evaluations/evaluations")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()

                assert isinstance(data, list)
                assert len(data) == 0
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_types_success(self, client, mock_user, mock_evaluation_types):
        """Test successful retrieval of evaluation types"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().all.return_value = mock_evaluation_types
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert isinstance(data, list)
            assert len(data) == 2

            # Verify first evaluation type
            first_type = data[0]
            assert first_type["id"] == "eval-type-123"
            assert first_type["name"] == "Accuracy"
            assert first_type["description"] == "Measures prediction accuracy"
            assert first_type["category"] == "performance"
            assert first_type["higher_is_better"] is True
            assert first_type["value_range"]["min"] == 0.0
            assert first_type["value_range"]["max"] == 1.0
            assert first_type["applicable_project_types"] == ["qa", "classification"]
            assert first_type["is_active"] is True

            # Verify second evaluation type
            second_type = data[1]
            assert second_type["id"] == "eval-type-456"
            assert second_type["name"] == "BLEU Score"
            assert second_type["category"] == "nlg"
            assert second_type["applicable_project_types"] == ["generation", "translation"]
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_types_with_task_type_filter(
        self, client, mock_user, mock_evaluation_types
    ):
        """Test evaluation types retrieval with task type filter"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Add bind.dialect.name for database detection
            mock_db.bind = Mock()
            mock_db.bind.dialect = Mock()
            mock_db.bind.dialect.name = "sqlite"
            # Mock the database-agnostic filtering
            filtered_types = [
                mock_evaluation_type
                for mock_evaluation_type in [mock_evaluation_types[0]]
                if "qa" in mock_evaluation_type.applicable_project_types
            ]
            # Setup proper query chain for both paths
            mock_query = Mock()
            mock_filter1 = Mock()
            mock_filter2 = Mock()
            mock_filter2.all.return_value = filtered_types
            mock_filter1.filter.return_value = mock_filter2
            mock_filter1.all.return_value = filtered_types
            mock_query.filter.return_value = mock_filter1
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.evaluations.status.get_evaluation_types_for_task_type") as mock_filter:
            mock_filter.return_value = [mock_evaluation_types[0]]  # Only return first type

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/evaluations/evaluation-types?task_type_id=qa")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()

                assert isinstance(data, list)
                # Should be filtered based on task type
                mock_filter.assert_called_once()
            finally:
                app.dependency_overrides.clear()

    def test_get_evaluation_types_with_category_filter(
        self, client, mock_user, mock_evaluation_types
    ):
        """Test evaluation types retrieval with category filter"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Filter by performance category
            filtered_types = [et for et in mock_evaluation_types if et.category == "performance"]
            # Setup proper query chain mocking
            mock_query = Mock()
            mock_filter = Mock()
            mock_filter.filter.return_value = mock_filter
            mock_filter.all.return_value = filtered_types
            mock_query.filter.return_value = mock_filter
            mock_db.query.return_value = mock_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types?category=performance")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["category"] == "performance"
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_types_database_error(self, client, mock_user):
        """Test evaluation types retrieval with database error"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().all.side_effect = Exception("Database connection failed")
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Error retrieving evaluation types" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_type_success(self, client, mock_user, mock_evaluation_type):
        """Test successful retrieval of specific evaluation type"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_evaluation_type
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types/eval-type-123")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["id"] == "eval-type-123"
            assert data["name"] == "Accuracy"
            assert data["description"] == "Measures prediction accuracy"
            assert data["category"] == "performance"
            assert data["higher_is_better"] is True
            assert data["value_range"]["min"] == 0.0
            assert data["value_range"]["max"] == 1.0
            assert data["applicable_project_types"] == ["qa", "classification"]
            assert data["is_active"] is True
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_type_not_found(self, client, mock_user):
        """Test retrieval of non-existent evaluation type"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = None
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types/nonexistent-type")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Evaluation type 'nonexistent-type' not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_get_evaluation_type_database_error(self, client, mock_user):
        """Test evaluation type retrieval with database error"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.side_effect = Exception("Database error")
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/evaluation-types/eval-type-123")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Error retrieving evaluation type" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestEvaluationsRouterIntegration:
    """Integration tests for evaluations router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_evaluation_workflow_complete(self, client):
        """Test complete evaluation workflow - status check and results retrieval"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=True,  # Make user a superadmin to see all evaluations
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

        mock_evaluation = DBEvaluationRun(
            id="eval-workflow-123",
            task_id="project-456",
            project_id="project-456",
            model_id="gpt-4o",
            metrics={"accuracy": 0.92, "precision": 0.89, "recall": 0.87},
            status="completed",
            eval_metadata={"evaluator": "automated", "duration": "15.2s"},
            samples_evaluated=200,
            created_at=datetime.now(timezone.utc),
        )

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)

            # Create a mock user with organization memberships
            mock_db_user = Mock()
            mock_db_user.id = mock_user.id
            mock_db_user.organization_memberships = []  # Empty list so it's iterable

            # Setup different query chains based on what's being queried
            def query_side_effect(model):
                from models import User as UserModel

                mock_query = Mock()
                if model == UserModel:
                    # User query
                    mock_query.filter.return_value.first.return_value = mock_db_user
                else:
                    # Evaluation query
                    mock_query.filter.return_value.first.return_value = mock_evaluation
                    mock_query.order_by.return_value.all.return_value = [mock_evaluation]
                return mock_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Step 1: Check evaluation status
            response = client.get("/api/evaluations/evaluation/status/eval-workflow-123")
            assert response.status_code == status.HTTP_200_OK
            status_data = response.json()

            assert status_data["id"] == "eval-workflow-123"
            assert status_data["status"] == "completed"

            # Step 2: Get all evaluations
            response = client.get("/api/evaluations/evaluations")
            assert response.status_code == status.HTTP_200_OK
            evaluations_data = response.json()

            assert isinstance(evaluations_data, list)
            assert len(evaluations_data) == 1

            evaluation = evaluations_data[0]
            assert evaluation["id"] == "eval-workflow-123"
            assert evaluation["metrics"]["accuracy"] == 0.92
            assert evaluation["samples_evaluated"] == 200

        finally:
            app.dependency_overrides.clear()

    def test_evaluation_types_filtering_integration(self, client):
        """Test evaluation types filtering with various parameters"""
        from database import get_db
        from main import app
        from routers.evaluations import require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

        # Create diverse evaluation types
        eval_types = [
            DBEvaluationType(
                id="accuracy-type",
                name="Accuracy",
                description="Classification accuracy",
                category="performance",
                higher_is_better=True,
                applicable_project_types=["classification", "qa"],
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
            DBEvaluationType(
                id="bleu-type",
                name="BLEU",
                description="Translation quality",
                category="nlg",
                higher_is_better=True,
                applicable_project_types=["generation", "translation"],
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
            DBEvaluationType(
                id="perplexity-type",
                name="Perplexity",
                description="Language model quality",
                category="nlg",
                higher_is_better=False,
                applicable_project_types=["generation"],
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Setup proper query chain
            mock_query = Mock()
            mock_filter = Mock()
            mock_filter.filter.return_value = mock_filter
            mock_filter.all.return_value = eval_types
            mock_query.filter.return_value = mock_filter
            mock_db.query.return_value = mock_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Test 1: Get all evaluation types
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_200_OK
            all_types = response.json()
            assert len(all_types) == 3

            # Test 2: Filter by category
            mock_db = Mock(spec=Session)
            nlg_types = [et for et in eval_types if et.category == "nlg"]
            # Setup proper query chain
            mock_query = Mock()
            mock_filter = Mock()
            mock_filter.filter.return_value = mock_filter
            mock_filter.all.return_value = nlg_types
            mock_query.filter.return_value = mock_filter
            mock_db.query.return_value = mock_query
            app.dependency_overrides[get_db] = lambda: mock_db

            response = client.get("/api/evaluations/evaluation-types?category=nlg")
            assert response.status_code == status.HTTP_200_OK
            filtered_types = response.json()
            assert len(filtered_types) == 2
            for eval_type in filtered_types:
                assert eval_type["category"] == "nlg"

            # Test 3: Filter by task type
            with patch("routers.evaluations.status.get_evaluation_types_for_task_type") as mock_filter:
                qa_types = [et for et in eval_types if "qa" in et.applicable_project_types]
                mock_filter.return_value = qa_types

                mock_db = Mock(spec=Session)
                # Add bind.dialect.name for database detection
                mock_db.bind = Mock()
                mock_db.bind.dialect = Mock()
                mock_db.bind.dialect.name = "sqlite"
                # Setup proper query chain
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.filter.return_value = mock_filter
                mock_filter.all.return_value = qa_types
                mock_query.filter.return_value = mock_filter
                mock_db.query.return_value = mock_query
                app.dependency_overrides[get_db] = lambda: mock_db

                response = client.get("/api/evaluations/evaluation-types?task_type_id=qa")
                assert response.status_code == status.HTTP_200_OK
                qa_filtered = response.json()

                for eval_type in qa_filtered:
                    assert "qa" in eval_type["applicable_project_types"]

        finally:
            app.dependency_overrides.clear()

    def test_database_agnostic_querying(self, client):
        """Test database-agnostic querying functionality"""
        from main import app
        from routers.evaluations import get_evaluation_types_for_task_type, require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

        # Test helper function directly with mock database
        mock_eval_type = DBEvaluationType(
            id="test-type",
            name="Test Type",
            description="Test evaluation type",
            category="test",
            applicable_project_types=["qa", "generation"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            # Test PostgreSQL dialect
            mock_db_pg = Mock(spec=Session)
            mock_db_pg.bind = Mock()
            mock_db_pg.bind.dialect = Mock()
            mock_db_pg.bind.dialect.name = "postgresql"
            # Setup proper query chain
            mock_query = Mock()
            mock_filter = Mock()
            mock_filter.filter.return_value = mock_filter
            mock_filter.all.return_value = [mock_eval_type]
            mock_query.filter.return_value = mock_filter
            mock_db_pg.query.return_value = mock_query

            result_pg = get_evaluation_types_for_task_type(mock_db_pg, "qa")
            assert len(result_pg) == 1
            assert result_pg[0].id == "test-type"

            # Test SQLite dialect
            mock_db_sqlite = Mock(spec=Session)
            mock_db_sqlite.bind = Mock()
            mock_db_sqlite.bind.dialect = Mock()
            mock_db_sqlite.bind.dialect.name = "sqlite"
            # Setup proper query chain
            mock_query = Mock()
            mock_filter = Mock()
            mock_filter.filter.return_value = mock_filter
            mock_filter.all.return_value = [mock_eval_type]
            mock_query.filter.return_value = mock_filter
            mock_db_sqlite.query.return_value = mock_query

            result_sqlite = get_evaluation_types_for_task_type(mock_db_sqlite, "qa")
            assert len(result_sqlite) == 1
            assert result_sqlite[0].id == "test-type"

            # Test fallback behavior on query failure
            # Patch with logging to verify fallback behavior
            with patch("routers.evaluations.helpers.logger") as mock_logger:
                mock_db_error = Mock(spec=Session)
                mock_db_error.bind = Mock()
                mock_db_error.bind.dialect = Mock()
                mock_db_error.bind.dialect.name = "postgresql"

                # Create mock query that will fail on JSON operation but succeed on fallback
                mock_query = Mock()

                # First filter attempt (with JSON) will fail
                def filter_side_effect(*args, **kwargs):
                    # Check if this is the JSON query (has "jsonb" in the text)
                    if args and hasattr(args[0], '_bindparams'):
                        # This is the jsonb query - make it fail
                        raise Exception("JSON query failed")
                    # This is the fallback query - return normal mock
                    mock_filter = Mock()
                    mock_filter.all.return_value = [mock_eval_type]
                    return mock_filter

                mock_query.filter.side_effect = filter_side_effect
                mock_db_error.query.return_value = mock_query

                result_fallback = get_evaluation_types_for_task_type(mock_db_error, "qa")

                # Verify warning was logged (indicating fallback was used)
                mock_logger.warning.assert_called_once()

                # Should fall back to returning all active types
                assert isinstance(result_fallback, list)
                assert len(result_fallback) == 1
                assert result_fallback[0].id == "test-type"

        finally:
            app.dependency_overrides.clear()

    def test_error_handling_and_recovery(self, client):
        """Test error handling and recovery scenarios"""
        from fastapi.testclient import TestClient

        from database import get_db
        from main import app
        from routers.evaluations import require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=True,  # Use superadmin to bypass org checks
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            # Test database connection failures
            # Use a client that doesn't raise server exceptions to test 500 responses
            error_client = TestClient(app, raise_server_exceptions=False)

            def override_get_db_error():
                # Raise exception immediately when getting DB session
                raise Exception("Database connection lost")

            app.dependency_overrides[get_db] = override_get_db_error

            # FastAPI TestClient with raise_server_exceptions=False returns 500 for unhandled exceptions
            response = error_client.get("/api/evaluations/evaluations")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

            # Test partial failures (not found scenarios)
            def override_get_db_partial():
                mock_db = Mock(spec=Session)
                # Setup mock chain for not found
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.first.return_value = None  # Not found
                mock_query.filter.return_value = mock_filter
                mock_db.query.return_value = mock_query
                return mock_db

            app.dependency_overrides[get_db] = override_get_db_partial

            response = client.get("/api/evaluations/evaluation/status/missing-eval")
            assert response.status_code == status.HTTP_404_NOT_FOUND

            response = client.get("/api/evaluations/evaluation-types/missing-type")
            assert response.status_code == status.HTTP_404_NOT_FOUND

            # Test successful recovery after error with evaluation-types endpoint
            # (simpler endpoint that doesn't require complex org membership mocking)
            def override_get_db_success():
                mock_db = Mock(spec=Session)
                # Setup mock chain for successful empty queries
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.all.return_value = []
                mock_filter.filter.return_value = mock_filter
                mock_query.filter.return_value = mock_filter
                mock_query.all.return_value = []
                mock_db.query.return_value = mock_query
                return mock_db

            app.dependency_overrides[get_db] = override_get_db_success

            # Test evaluation-types endpoint (doesn't require org membership iteration)
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_200_OK

        finally:
            app.dependency_overrides.clear()


class TestEvaluationResultsLatestOnly:
    """Tests for the latest_only parameter on evaluation results endpoint (Issue #933)"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=True,  # Superadmin for easy access
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_evaluations(self):
        """Create multiple evaluations with different timestamps"""
        now = datetime.now(timezone.utc)

        eval1 = DBEvaluationRun(
            id="eval-latest",
            task_id="project-123",
            project_id="project-123",
            model_id="gpt-4o",
            evaluation_type_ids=["bertscore"],
            metrics={"bertscore:pred:ref:precision": 0.92},
            status="completed",
            eval_metadata={"evaluation_type": "multi_field", "evaluation_configs": []},
            samples_evaluated=50,
            created_by="user-123",
            created_at=now,  # Latest
        )

        eval2 = DBEvaluationRun(
            id="eval-older",
            task_id="project-123",
            project_id="project-123",
            model_id="gpt-4o",
            evaluation_type_ids=["bertscore"],
            metrics={"bertscore:pred:ref:precision": 0.88},
            status="completed",
            eval_metadata={"evaluation_type": "multi_field", "evaluation_configs": []},
            samples_evaluated=50,
            created_by="user-123",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),  # Older
        )

        eval3 = DBEvaluationRun(
            id="eval-oldest",
            task_id="project-123",
            project_id="project-123",
            model_id="claude-sonnet-4",
            evaluation_type_ids=["bertscore"],
            metrics={"bertscore:pred:ref:precision": 0.85},
            status="completed",
            eval_metadata={"evaluation_type": "multi_field", "evaluation_configs": []},
            samples_evaluated=50,
            created_by="user-123",
            created_at=datetime(2023, 6, 1, tzinfo=timezone.utc),  # Oldest
        )

        return [eval1, eval2, eval3]

    def test_latest_only_true_returns_single_evaluation(
        self, client, mock_user, mock_evaluations
    ):
        """Test that latest_only=true (default) returns only the most recent evaluation"""
        from auth_module import require_user
        from database import get_db
        from models import EvaluationRun as DBEvaluationRun
        from models import TaskEvaluation
        from project_models import Project

        app.dependency_overrides[require_user] = lambda: mock_user

        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.is_private = False

        def override_get_db():
            mock_db = Mock(spec=Session)

            def query_side_effect(model):
                """Return different mock query chains based on the model being queried"""
                mock_query = Mock()
                mock_filter = Mock()

                if model == Project:
                    # Project query: .filter(...).first() returns project
                    mock_filter.first.return_value = mock_project
                    mock_query.filter.return_value = mock_filter
                elif model == DBEvaluationRun:
                    # Evaluation query: .filter(...).order_by(...).all() returns evaluations
                    mock_order_by = Mock()
                    mock_order_by.all.return_value = mock_evaluations
                    mock_filter.order_by.return_value = mock_order_by
                    mock_query.filter.return_value = mock_filter
                elif model == TaskEvaluation:
                    # Sample results query: .filter(...).count() returns 0
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter
                else:
                    # Default fallback
                    mock_filter.first.return_value = None
                    mock_filter.all.return_value = []
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter

                return mock_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Default (latest_only=true)
            response = client.get("/api/evaluations/run/results/project/project-123")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Should return only 1 evaluation (the latest)
            assert data["total_count"] == 1
            assert len(data["evaluations"]) == 1
            assert data["evaluations"][0]["evaluation_id"] == "eval-latest"

        finally:
            app.dependency_overrides.clear()

    def test_latest_only_false_returns_all_evaluations(
        self, client, mock_user, mock_evaluations
    ):
        """Test that latest_only=false returns all historical evaluations"""
        from auth_module import require_user
        from database import get_db
        from models import EvaluationRun as DBEvaluationRun
        from models import TaskEvaluation
        from project_models import Project

        app.dependency_overrides[require_user] = lambda: mock_user

        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.is_private = False

        def override_get_db():
            mock_db = Mock(spec=Session)

            def query_side_effect(model):
                """Return different mock query chains based on the model being queried"""
                mock_query = Mock()
                mock_filter = Mock()

                if model == Project:
                    mock_filter.first.return_value = mock_project
                    mock_query.filter.return_value = mock_filter
                elif model == DBEvaluationRun:
                    mock_order_by = Mock()
                    mock_order_by.all.return_value = mock_evaluations
                    mock_filter.order_by.return_value = mock_order_by
                    mock_query.filter.return_value = mock_filter
                elif model == TaskEvaluation:
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter
                else:
                    mock_filter.first.return_value = None
                    mock_filter.all.return_value = []
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter

                return mock_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Explicitly set latest_only=false
            response = client.get(
                "/api/evaluations/run/results/project/project-123?latest_only=false"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Should return all 3 evaluations
            assert data["total_count"] == 3
            assert len(data["evaluations"]) == 3

        finally:
            app.dependency_overrides.clear()

    def test_latest_only_explicit_true_returns_single(
        self, client, mock_user, mock_evaluations
    ):
        """Test that explicit latest_only=true returns single evaluation"""
        from auth_module import require_user
        from database import get_db
        from models import EvaluationRun as DBEvaluationRun
        from models import TaskEvaluation
        from project_models import Project

        app.dependency_overrides[require_user] = lambda: mock_user

        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.is_private = False

        def override_get_db():
            mock_db = Mock(spec=Session)

            def query_side_effect(model):
                """Return different mock query chains based on the model being queried"""
                mock_query = Mock()
                mock_filter = Mock()

                if model == Project:
                    mock_filter.first.return_value = mock_project
                    mock_query.filter.return_value = mock_filter
                elif model == DBEvaluationRun:
                    mock_order_by = Mock()
                    mock_order_by.all.return_value = mock_evaluations
                    mock_filter.order_by.return_value = mock_order_by
                    mock_query.filter.return_value = mock_filter
                elif model == TaskEvaluation:
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter
                else:
                    mock_filter.first.return_value = None
                    mock_filter.all.return_value = []
                    mock_filter.count.return_value = 0
                    mock_query.filter.return_value = mock_filter

                return mock_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get(
                "/api/evaluations/run/results/project/project-123?latest_only=true"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["total_count"] == 1
            assert len(data["evaluations"]) == 1

        finally:
            app.dependency_overrides.clear()

    def test_empty_evaluations_returns_empty_list(self, client, mock_user):
        """Test that empty evaluations list returns properly with latest_only"""
        from auth_module import require_user
        from database import get_db

        app.dependency_overrides[require_user] = lambda: mock_user

        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.is_private = False

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_query = Mock()
            mock_filter = Mock()
            mock_order_by = Mock()

            mock_filter.first.return_value = mock_project
            mock_order_by.all.return_value = []  # No evaluations
            mock_filter.order_by.return_value = mock_order_by
            mock_query.filter.return_value = mock_filter
            mock_db.query.return_value = mock_query

            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/run/results/project/project-123")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["total_count"] == 0
            assert len(data["evaluations"]) == 0

        finally:
            app.dependency_overrides.clear()
