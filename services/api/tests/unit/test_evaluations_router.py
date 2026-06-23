"""
Comprehensive tests for evaluations router endpoints.
Tests the router architecture and endpoint functionality.

Sync vs async split after the async-DB migration:
  - ``get_evaluation_status`` (status/{id}), single ``get_evaluation_type``
    (evaluation-types/{id}), and ``get_project_evaluation_results``
    (run/results/project/{pid}) are ASYNC — their tests seed real rows via
    ``async_test_db`` and drive the surface through ``async_test_client``
    (superadmin user → access short-circuits).
  - The ``get_evaluations`` LIST (GET /), the ``get_evaluation_types`` LIST,
    and the ``get_evaluation_types_for_task_type`` helper stay SYNC — those
    tests keep the Mock(spec=Session) / get_db-override lane (the helper's
    SQL now runs through ``db.execute(...).scalars().all()``, so its mock
    models ``execute`` instead of ``query``).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from auth_module.models import User as AuthUser
from models import EvaluationRun as DBEvaluationRun
from models import EvaluationType as DBEvaluationType
from models import User
from project_models import Project
from sqlalchemy.orm import Session


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, *, is_superadmin=True):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"evr-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Router User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        use_pseudonym=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, owner):
    p = Project(
        id=_uid(),
        title=f"Eval Router {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_eval_run(db, owner, *, project_id=None, status="completed",
                         error_message=None, eval_metadata=None, metrics=None,
                         model_id="gpt-4o", run_id=None, created_at=None,
                         samples_evaluated=10):
    run = DBEvaluationRun(
        id=run_id or _uid(),
        project_id=project_id,
        model_id=model_id,
        evaluation_type_ids=[],
        metrics=metrics or {},
        status=status,
        error_message=error_message,
        eval_metadata=eval_metadata,
        samples_evaluated=samples_evaluated,
        created_by=owner.id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    return run


async def _seed_eval_type(db, *, type_id, name="Accuracy", category="performance"):
    et = DBEvaluationType(
        id=type_id,
        name=name,
        description="Measures prediction accuracy",
        category=category,
        higher_is_better=True,
        value_range={"min": 0.0, "max": 1.0},
        applicable_project_types=["qa", "classification"],
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(et)
    await db.flush()
    return et


# Imported lazily where used to match the original module's late binding.
from auth_module.dependencies import require_user  # noqa: E402
from database import get_db  # noqa: E402


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
    def mock_evaluations(self):
        eval1 = DBEvaluationRun(
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
        return [eval1, eval2]

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

    # ---- get_evaluation_status (ASYNC) -----------------------------------

    @pytest.mark.asyncio
    async def test_get_evaluation_status_success(self, async_test_client, async_test_db):
        """Test successful evaluation status retrieval"""
        owner = await _seed_user(async_test_db)
        run = await _seed_eval_run(
            async_test_db, owner, run_id="eval-123", status="completed"
        )
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{run.id}"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "eval-123"
        assert data["status"] == "completed"
        assert data["message"] == "Evaluation status"

    @pytest.mark.asyncio
    async def test_get_evaluation_status_not_found(self, async_test_client, async_test_db):
        """Test evaluation status retrieval when evaluation not found"""
        owner = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                "/api/evaluations/evaluation/status/nonexistent-eval"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Evaluation 'nonexistent-eval' not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_evaluation_status_with_error_message(
        self, async_test_client, async_test_db
    ):
        """Test evaluation status with error message"""
        owner = await _seed_user(async_test_db)
        run = await _seed_eval_run(
            async_test_db,
            owner,
            run_id="eval-failed",
            status="failed",
            error_message="Model API timeout",
            samples_evaluated=0,
        )
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{run.id}"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "eval-failed"
        assert data["status"] == "failed"
        assert data["message"] == "Model API timeout"

    # ---- get_evaluations LIST (SYNC) -------------------------------------

    def test_get_evaluations_success(self, client, mock_user, mock_evaluations):
        """Test successful retrieval of all evaluations"""
        mock_user.is_superadmin = True

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db_user = Mock()
            mock_db_user.id = mock_user.id
            mock_db_user.organization_memberships = []
            mock_user_query = Mock()
            mock_user_query.filter.return_value.first.return_value = mock_db_user
            mock_eval_query = Mock()
            mock_eval_query.order_by.return_value.all.return_value = mock_evaluations

            def query_side_effect(model):
                from models import User as UserModel

                if model == UserModel:
                    return mock_user_query
                return mock_eval_query

            mock_db.query.side_effect = query_side_effect
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/evaluations/")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2
            first_eval = data[0]
            assert first_eval["id"] == "eval-123"
            assert first_eval["project_id"] == "project-abc"
            assert first_eval["model_id"] == "gpt-4o"
            assert first_eval["metrics"]["accuracy"] == 0.85
            assert first_eval["metrics"]["f1_score"] == 0.82
            assert first_eval["status"] == "completed"
            assert first_eval["samples_evaluated"] == 100
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

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_eval_query = Mock()
            mock_eval_query.order_by.return_value.filter.return_value.all.return_value = []
            mock_eval_query.order_by.return_value.all.return_value = []
            mock_db.query.return_value = mock_eval_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=[]):
                response = client.get("/api/evaluations/")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert isinstance(data, list)
                assert len(data) == 0
        finally:
            app.dependency_overrides.clear()

    # ---- get_evaluation_types LIST (SYNC) --------------------------------

    def test_get_evaluation_types_success(self, client, mock_user, mock_evaluation_types):
        """Test successful retrieval of evaluation types"""

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
            first_type = data[0]
            assert first_type["id"] == "eval-type-123"
            assert first_type["name"] == "Accuracy"
            assert first_type["description"] == "Measures prediction accuracy"
            assert first_type["category"] == "performance"
            assert first_type["higher_is_better"] == True  # noqa: E712
            assert first_type["value_range"]["min"] == 0.0
            assert first_type["value_range"]["max"] == 1.0
            assert first_type["applicable_project_types"] == ["qa", "classification"]
            assert first_type["is_active"] == True  # noqa: E712
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

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.bind = Mock()
            mock_db.bind.dialect = Mock()
            mock_db.bind.dialect.name = "sqlite"
            filtered_types = [
                et
                for et in [mock_evaluation_types[0]]
                if "qa" in et.applicable_project_types
            ]
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
            mock_filter.return_value = [mock_evaluation_types[0]]

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/evaluations/evaluation-types?task_type_id=qa")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert isinstance(data, list)
                mock_filter.assert_called_once()
            finally:
                app.dependency_overrides.clear()

    def test_get_evaluation_types_with_category_filter(
        self, client, mock_user, mock_evaluation_types
    ):
        """Test evaluation types retrieval with category filter"""

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            filtered_types = [et for et in mock_evaluation_types if et.category == "performance"]
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

    # ---- single get_evaluation_type (ASYNC) ------------------------------

    @pytest.mark.asyncio
    async def test_get_evaluation_type_success(self, async_test_client, async_test_db):
        """Test successful retrieval of specific evaluation type"""
        owner = await _seed_user(async_test_db)
        await _seed_eval_type(async_test_db, type_id="eval-type-123", name="Accuracy")
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                "/api/evaluations/evaluation-types/eval-type-123"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "eval-type-123"
        assert data["name"] == "Accuracy"
        assert data["description"] == "Measures prediction accuracy"
        assert data["category"] == "performance"
        assert data["higher_is_better"] == True  # noqa: E712
        assert data["value_range"]["min"] == 0.0
        assert data["value_range"]["max"] == 1.0
        assert data["applicable_project_types"] == ["qa", "classification"]
        assert data["is_active"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_evaluation_type_not_found(self, async_test_client, async_test_db):
        """Test retrieval of non-existent evaluation type"""
        owner = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                "/api/evaluations/evaluation-types/nonexistent-type"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Evaluation type 'nonexistent-type' not found" in response.json()["detail"]

    def test_get_evaluation_type_database_error(self, client, mock_user):
        """Test evaluation type retrieval with database error.

        The single-type handler is async, but a get_async_db override that
        raises on use still exercises the 500 path without touching the DB.
        """
        from database import get_async_db

        def override_require_user():
            return mock_user

        async def override_get_async_db():
            class _BoomSession:
                async def execute(self, *a, **k):
                    raise Exception("Database error")

            yield _BoomSession()

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_async_db] = override_get_async_db

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

    @pytest.mark.asyncio
    async def test_evaluation_workflow_complete(self, async_test_client, async_test_db):
        """Test complete evaluation workflow - status check and results retrieval.

        Status read is async (seeded row); the cross-project list is sync, so
        its ``get_db`` is overridden with a mock returning the same logical run.
        """
        owner = await _seed_user(async_test_db)
        run = await _seed_eval_run(
            async_test_db,
            owner,
            run_id="eval-workflow-123",
            status="completed",
            metrics={"accuracy": 0.92, "precision": 0.89, "recall": 0.87},
            eval_metadata={"evaluator": "automated", "duration": "15.2s"},
            samples_evaluated=200,
        )
        await async_test_db.commit()

        mock_list_run = DBEvaluationRun(
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

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_eval_query = Mock()
            mock_eval_query.order_by.return_value.all.return_value = [mock_list_run]
            mock_db.query.return_value = mock_eval_query
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with _as_user(owner), patch(
                "routers.evaluations.status.get_accessible_project_ids", return_value=None
            ):
                response = await async_test_client.get(
                    f"/api/evaluations/evaluation/status/{run.id}"
                )
                assert response.status_code == status.HTTP_200_OK
                status_data = response.json()
                assert status_data["id"] == "eval-workflow-123"
                assert status_data["status"] == "completed"

                response = await async_test_client.get("/api/evaluations/")
                assert response.status_code == status.HTTP_200_OK
                evaluations_data = response.json()
                assert isinstance(evaluations_data, list)
                assert len(evaluations_data) == 1
                evaluation = evaluations_data[0]
                assert evaluation["id"] == "eval-workflow-123"
                assert evaluation["metrics"]["accuracy"] == 0.92
                assert evaluation["samples_evaluated"] == 200
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_evaluation_types_filtering_integration(self, client):
        """Test evaluation types filtering with various parameters"""
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
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_200_OK
            all_types = response.json()
            assert len(all_types) == 3

            mock_db = Mock(spec=Session)
            nlg_types = [et for et in eval_types if et.category == "nlg"]
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

            with patch("routers.evaluations.status.get_evaluation_types_for_task_type") as mock_filter:
                qa_types = [et for et in eval_types if "qa" in et.applicable_project_types]
                mock_filter.return_value = qa_types

                mock_db = Mock(spec=Session)
                mock_db.bind = Mock()
                mock_db.bind.dialect = Mock()
                mock_db.bind.dialect.name = "sqlite"
                mock_query = Mock()
                mock_filter_q = Mock()
                mock_filter_q.filter.return_value = mock_filter_q
                mock_filter_q.all.return_value = qa_types
                mock_query.filter.return_value = mock_filter_q
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
        """Test database-agnostic querying functionality.

        ``get_evaluation_types_for_task_type`` stays sync but now runs its SQL
        via ``db.execute(stmt).scalars().all()`` (the ``db.query`` chain is
        gone), so the mocks model ``execute`` instead.
        """
        from routers.evaluations import get_evaluation_types_for_task_type

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

        def _execute_returning(rows):
            result = Mock()
            result.scalars.return_value.all.return_value = rows
            return result

        try:
            # PostgreSQL dialect
            mock_db_pg = Mock(spec=Session)
            mock_db_pg.bind = Mock()
            mock_db_pg.bind.dialect = Mock()
            mock_db_pg.bind.dialect.name = "postgresql"
            mock_db_pg.execute.return_value = _execute_returning([mock_eval_type])

            result_pg = get_evaluation_types_for_task_type(mock_db_pg, "qa")
            assert len(result_pg) == 1
            assert result_pg[0].id == "test-type"

            # SQLite dialect
            mock_db_sqlite = Mock(spec=Session)
            mock_db_sqlite.bind = Mock()
            mock_db_sqlite.bind.dialect = Mock()
            mock_db_sqlite.bind.dialect.name = "sqlite"
            mock_db_sqlite.execute.return_value = _execute_returning([mock_eval_type])

            result_sqlite = get_evaluation_types_for_task_type(mock_db_sqlite, "qa")
            assert len(result_sqlite) == 1
            assert result_sqlite[0].id == "test-type"

            # Fallback behavior on query failure: first execute raises, the
            # fallback execute returns all active types.
            with patch("routers.evaluations.helpers.logger") as mock_logger:
                mock_db_error = Mock(spec=Session)
                mock_db_error.bind = Mock()
                mock_db_error.bind.dialect = Mock()
                mock_db_error.bind.dialect.name = "postgresql"

                calls = [0]

                def execute_side_effect(*args, **kwargs):
                    calls[0] += 1
                    if calls[0] == 1:
                        raise Exception("JSON query failed")
                    return _execute_returning([mock_eval_type])

                mock_db_error.execute.side_effect = execute_side_effect

                result_fallback = get_evaluation_types_for_task_type(mock_db_error, "qa")
                mock_logger.warning.assert_called_once()
                assert isinstance(result_fallback, list)
                assert len(result_fallback) == 1
                assert result_fallback[0].id == "test-type"
        finally:
            app.dependency_overrides.clear()

    def test_error_handling_and_recovery(self, client):
        """Test error handling and recovery scenarios.

        The cross-project list (sync) and evaluation-types list (sync) keep the
        get_db lane; the single-type 404 path is async and is exercised via a
        get_async_db override that yields an empty real session would require a
        DB, so the not-found path is asserted through a real empty async DB in
        ``test_get_evaluation_type_not_found``. Here we keep the sync list +
        types error/recovery branches.
        """
        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            # Database connection failure on the sync list endpoint -> 500.
            error_client = TestClient(app, raise_server_exceptions=False)

            def override_get_db_error():
                raise Exception("Database connection lost")

            app.dependency_overrides[get_db] = override_get_db_error
            response = error_client.get("/api/evaluations/")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

            # Successful recovery on the evaluation-types list endpoint.
            def override_get_db_success():
                mock_db = Mock(spec=Session)
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.all.return_value = []
                mock_filter.filter.return_value = mock_filter
                mock_query.filter.return_value = mock_filter
                mock_query.all.return_value = []
                mock_db.query.return_value = mock_query
                return mock_db

            app.dependency_overrides[get_db] = override_get_db_success
            response = client.get("/api/evaluations/evaluation-types")
            assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()


class TestEvaluationResultsLatestOnly:
    """Tests for the latest_only parameter on evaluation results endpoint (Issue #933).

    ``get_project_evaluation_results`` is async, so these seed real rows via
    ``async_test_db`` and drive through ``async_test_client``.
    """

    @pytest.mark.asyncio
    async def test_latest_only_true_returns_single_evaluation(
        self, async_test_client, async_test_db
    ):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await self._seed_three(async_test_db, owner, project)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["evaluations"]) == 1
        assert data["evaluations"][0]["evaluation_id"] == "eval-latest"

    @pytest.mark.asyncio
    async def test_latest_only_false_returns_all_evaluations(
        self, async_test_client, async_test_db
    ):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await self._seed_three(async_test_db, owner, project)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}?latest_only=false"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 3
        assert len(data["evaluations"]) == 3

    @pytest.mark.asyncio
    async def test_latest_only_explicit_true_returns_single(
        self, async_test_client, async_test_db
    ):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await self._seed_three(async_test_db, owner, project)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}?latest_only=true"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["evaluations"]) == 1

    @pytest.mark.asyncio
    async def test_empty_evaluations_returns_empty_list(
        self, async_test_client, async_test_db
    ):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["evaluations"]) == 0

    @staticmethod
    async def _seed_three(db, owner, project):
        now = datetime.now(timezone.utc)
        meta = {"evaluation_type": "multi_field", "evaluation_configs": []}
        await _seed_eval_run(
            db, owner, project_id=project.id, run_id="eval-latest",
            model_id="gpt-4o", metrics={"bertscore:pred:ref:precision": 0.92},
            eval_metadata=meta, samples_evaluated=50, created_at=now,
        )
        await _seed_eval_run(
            db, owner, project_id=project.id, run_id="eval-older",
            model_id="gpt-4o", metrics={"bertscore:pred:ref:precision": 0.88},
            eval_metadata=meta, samples_evaluated=50,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        await _seed_eval_run(
            db, owner, project_id=project.id, run_id="eval-oldest",
            model_id="claude-sonnet-4", metrics={"bertscore:pred:ref:precision": 0.85},
            eval_metadata=meta, samples_evaluated=50,
            created_at=datetime(2023, 6, 1, tzinfo=timezone.utc),
        )
