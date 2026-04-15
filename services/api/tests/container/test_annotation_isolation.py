"""
Tests for annotation data isolation between users.

Verifies that GET /tasks/{task_id}/annotations only returns the current user's
annotations by default, preventing data leakage in multi-annotator projects.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, User
from project_models import Annotation, Project, Task


@pytest.mark.database
@pytest.mark.integration
class TestAnnotationIsolation:
    """Verify annotations are isolated per user at the database query level."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db: Session, test_users):
        """Setup test data."""
        self.db = test_db
        self.admin = test_users[0]

        self.org = self.db.query(Organization).first()
        if not self.org:
            self.org = Organization(
                id=str(uuid.uuid4()),
                name="test_isolation_org",
                display_name="Test Isolation Org",
                slug="test-isolation-org",
            )
            self.db.add(self.org)
            self.db.commit()

    def _create_user(self, username: str) -> User:
        """Create a test user."""
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=f"{username}@test.com",
            name=f"Test {username}",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        self.db.add(user)
        self.db.commit()
        return user

    def _create_project_with_task(self, owner_id: str, min_annotations: int = 2):
        """Create a project with one task."""
        project = Project(
            id=str(uuid.uuid4()),
            title=f"Isolation Test {datetime.now().strftime('%H:%M:%S.%f')}",
            description="Testing annotation isolation",
            created_by=owner_id,
            min_annotations_per_task=min_annotations,
            label_config='<View><Text name="text" value="$text"/><TextArea name="answer" toName="text"/></View>',
        )
        self.db.add(project)
        self.db.flush()

        task = Task(
            id=str(uuid.uuid4()),
            inner_id=1,
            project_id=project.id,
            data={"text": "Test question"},
            is_labeled=False,
            total_annotations=0,
        )
        self.db.add(task)
        self.db.commit()
        return project, task

    def _create_annotation(self, task_id: str, project_id: str, user_id: str, answer: str):
        """Create an annotation for a task by a specific user."""
        annotation = Annotation(
            id=str(uuid.uuid4()),
            task_id=task_id,
            project_id=project_id,
            completed_by=user_id,
            result=[{"from_name": "answer", "type": "textarea", "value": {"text": [answer]}}],
            was_cancelled=False,
            ground_truth=False,
            created_at=datetime.utcnow(),
        )
        self.db.add(annotation)
        self.db.commit()
        return annotation

    def test_two_users_same_task_see_only_own_annotation(self):
        """Core isolation test: two users annotate same task, each sees only their own."""
        user_a = self._create_user("annotator_a")
        user_b = self._create_user("annotator_b")
        project, task = self._create_project_with_task(self.admin.id, min_annotations=2)

        ann_a = self._create_annotation(task.id, project.id, user_a.id, "Answer from A")
        ann_b = self._create_annotation(task.id, project.id, user_b.id, "Answer from B")

        # Simulate the endpoint query for user A (default: completed_by filter)
        from sqlalchemy import String, cast

        results_for_a = (
            self.db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.completed_by == user_a.id,
                Annotation.result != None,
                cast(Annotation.result, String) != "[]",
            )
            .all()
        )

        assert len(results_for_a) == 1
        assert results_for_a[0].id == ann_a.id
        assert results_for_a[0].completed_by == user_a.id

        # Simulate the endpoint query for user B
        results_for_b = (
            self.db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.completed_by == user_b.id,
                Annotation.result != None,
                cast(Annotation.result, String) != "[]",
            )
            .all()
        )

        assert len(results_for_b) == 1
        assert results_for_b[0].id == ann_b.id
        assert results_for_b[0].completed_by == user_b.id

    def test_all_users_query_returns_both_annotations(self):
        """Without completed_by filter, both annotations are returned."""
        user_a = self._create_user("all_a")
        user_b = self._create_user("all_b")
        project, task = self._create_project_with_task(self.admin.id, min_annotations=2)

        self._create_annotation(task.id, project.id, user_a.id, "A answer")
        self._create_annotation(task.id, project.id, user_b.id, "B answer")

        from sqlalchemy import String, cast

        results = (
            self.db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.result != None,
                cast(Annotation.result, String) != "[]",
            )
            .all()
        )

        assert len(results) == 2
        user_ids = {r.completed_by for r in results}
        assert user_a.id in user_ids
        assert user_b.id in user_ids

    def test_unannotated_user_gets_empty_result(self):
        """A user who hasn't annotated a task gets no results."""
        user_a = self._create_user("has_ann")
        user_c = self._create_user("no_ann")
        project, task = self._create_project_with_task(self.admin.id)

        self._create_annotation(task.id, project.id, user_a.id, "A's answer")

        from sqlalchemy import String, cast

        results_for_c = (
            self.db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.completed_by == user_c.id,
                Annotation.result != None,
                cast(Annotation.result, String) != "[]",
            )
            .all()
        )

        assert len(results_for_c) == 0

    def test_endpoint_function_has_completed_by_filter(self):
        """Verify the actual endpoint code includes completed_by filtering."""
        import inspect
        import textwrap

        from routers.projects.annotations import list_task_annotations

        source = inspect.getsource(list_task_annotations)

        # The endpoint must filter by completed_by when all_users is False
        assert "completed_by" in source, (
            "Endpoint must filter by completed_by to prevent annotation data leakage"
        )
        assert "all_users" in source, (
            "Endpoint must have all_users parameter for opt-in cross-user access"
        )
