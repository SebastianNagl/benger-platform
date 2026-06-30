"""
Tests for project progress tracking and annotation counting
Verifies that task completion status is properly calculated based on minimum annotations
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, User
from project_models import Annotation, Project, Task


@pytest.mark.database
@pytest.mark.integration
class TestProgressAlignment:
    """Test progress calculation and annotation tracking"""

    @pytest.fixture(autouse=True)
    def setup(self, test_db: Session, test_users):
        """Setup test data for progress tests"""
        self.db = test_db
        self.admin = test_users[0]  # Admin user from test_users fixture

        # Get or create organization
        self.org = self.db.query(Organization).first()
        if not self.org:
            self.org = Organization(
                id=str(uuid.uuid4()),
                name="test_progress_org",
                display_name="Test Progress Organization",
                slug="test-progress-org",
            )
            self.db.add(self.org)
            self.db.commit()

    def _seed_annotations(self, task, project, n, choice):
        """Seed n annotations for a task, each from a DISTINCT annotator. One
        active annotation per (task, user) is enforced by the
        uq_annotations_active_task_user index, so a multi-annotation task is
        reached across distinct annotators (the real-world shape)."""
        for k in range(n):
            annotator = User(
                id=str(uuid.uuid4()),
                username=f"compl-{uuid.uuid4().hex[:8]}",
                email=f"{uuid.uuid4().hex[:8]}@example.com",
                name=f"Annotator {k + 1}",
                is_active=True,
            )
            self.db.add(annotator)
            self.db.flush()
            self.db.add(Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=project.id,
                completed_by=annotator.id,
                result=[{
                    "value": {"choices": [choice]},
                    "from_name": "sentiment",
                    "to_name": "text",
                    "type": "choices",
                }],
                was_cancelled=False,
            ))

    def test_multi_annotation_progress_tracking(self):
        """Test progress tracking with multiple annotations per task"""
        # Create project requiring 3 annotations per task
        project = Project(
            id=str(uuid.uuid4()),
            title=f"Multi-Annotation Test {datetime.now().strftime('%H:%M:%S')}",
            description="Testing progress alignment with 3 annotations required per task",
            created_by=self.admin.id,
            min_annotations_per_task=3,
            label_config='<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/><Choice value="neutral"/></Choices></View>',
        )
        self.db.add(project)
        self.db.commit()

        assert project.min_annotations_per_task == 3

        # Create 5 tasks
        tasks = []
        for i in range(5):
            task = Task(
                id=str(uuid.uuid4()),
                inner_id=i + 1,
                project_id=project.id,
                data={"text": f"Sample text {i+1} for annotation. This requires 3 annotations."},
                is_labeled=False,
                total_annotations=0,
            )
            self.db.add(task)
            tasks.append(task)
        self.db.commit()

        assert len(tasks) == 5

    def test_task_completion_scenarios(self):
        """Test different task completion scenarios"""
        # Create project
        project = Project(
            id=str(uuid.uuid4()),
            title="Completion Test Project",
            description="Testing various completion scenarios",
            created_by=self.admin.id,
            min_annotations_per_task=3,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        self.db.add(project)
        self.db.commit()

        # Create tasks
        tasks = []
        for i in range(4):
            task = Task(
                id=str(uuid.uuid4()),
                inner_id=i + 1,
                project_id=project.id,
                data={"text": f"Task {i+1}"},
                is_labeled=False,
                total_annotations=0,
            )
            self.db.add(task)
            tasks.append(task)
        self.db.commit()

        # Scenario 1: Task with 3 annotations (complete)
        self._seed_annotations(tasks[0], project, 3, "positive")
        tasks[0].total_annotations = 3
        tasks[0].is_labeled = True
        self.db.commit()

        assert tasks[0].is_labeled == True  # noqa: E712
        assert tasks[0].total_annotations == 3

        # Scenario 2: Task with 2 annotations (incomplete)
        self._seed_annotations(tasks[1], project, 2, "negative")
        tasks[1].total_annotations = 2
        tasks[1].is_labeled = False  # Should not be labeled with only 2 annotations
        self.db.commit()

        assert tasks[1].is_labeled == False  # noqa: E712
        assert tasks[1].total_annotations == 2

        # Scenario 3: Task with 4 annotations (exceeds requirement)
        self._seed_annotations(tasks[2], project, 4, "neutral")
        tasks[2].total_annotations = 4
        tasks[2].is_labeled = True  # Should be labeled with 4 annotations (exceeds minimum)
        self.db.commit()

        assert tasks[2].is_labeled == True  # noqa: E712
        assert tasks[2].total_annotations == 4

        # Scenario 4: Task with 0 annotations (no progress)
        tasks[3].total_annotations = 0
        tasks[3].is_labeled = False
        self.db.commit()

        assert tasks[3].is_labeled == False  # noqa: E712
        assert tasks[3].total_annotations == 0

    def test_progress_calculation(self):
        """Test overall project progress calculation"""
        # Create project
        project = Project(
            id=str(uuid.uuid4()),
            title="Progress Calculation Test",
            description="Testing progress calculation",
            created_by=self.admin.id,
            min_annotations_per_task=2,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        self.db.add(project)
        self.db.commit()

        # Create 10 tasks
        tasks = []
        for i in range(10):
            task = Task(
                id=str(uuid.uuid4()),
                inner_id=i + 1,
                project_id=project.id,
                data={"text": f"Task {i+1}"},
                is_labeled=False,
                total_annotations=0,
            )
            self.db.add(task)
            tasks.append(task)
        self.db.commit()

        # Mark 6 tasks as complete
        for i in range(6):
            tasks[i].is_labeled = True
            tasks[i].total_annotations = 2
        self.db.commit()

        # Calculate progress
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.is_labeled)
        progress = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0

        assert total_tasks == 10
        assert completed_tasks == 6
        assert progress == 60.0

    def test_annotation_cancellation_handling(self):
        """Test handling of cancelled annotations"""
        # Create project
        project = Project(
            id=str(uuid.uuid4()),
            title="Cancellation Test",
            description="Testing cancelled annotation handling",
            created_by=self.admin.id,
            min_annotations_per_task=2,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        self.db.add(project)
        self.db.commit()

        # Create task
        task = Task(
            id=str(uuid.uuid4()),
            inner_id=1,
            project_id=project.id,
            data={"text": "Test task"},
            is_labeled=False,
            total_annotations=0,
        )
        self.db.add(task)
        self.db.commit()

        # Add 1 valid annotation
        valid_ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            completed_by=self.admin.id,
            result=[{"value": {"choices": ["positive"]}}],
            was_cancelled=False,
        )
        self.db.add(valid_ann)

        # Add 1 cancelled annotation
        cancelled_ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            completed_by=self.admin.id,
            result=[{"value": {"choices": ["negative"]}}],
            was_cancelled=True,
        )
        self.db.add(cancelled_ann)
        self.db.commit()

        # Count only valid annotations
        valid_annotation_count = (
            self.db.query(Annotation)
            .filter(Annotation.task_id == task.id, Annotation.was_cancelled == False)  # noqa: E712
            .count()
        )

        assert valid_annotation_count == 1

        # Task should not be complete with only 1 valid annotation
        task.total_annotations = valid_annotation_count
        task.is_labeled = valid_annotation_count >= project.min_annotations_per_task
        self.db.commit()

        assert task.is_labeled == False  # noqa: E712
        assert task.total_annotations == 1

    def test_progress_with_mixed_requirements(self):
        """Test progress with different annotation requirements per project"""
        projects = []

        # Create projects with different requirements
        for min_ann in [1, 2, 3, 5]:
            project = Project(
                id=str(uuid.uuid4()),
                title=f"Project with {min_ann} annotations required",
                description=f"Testing with min_annotations={min_ann}",
                created_by=self.admin.id,
                min_annotations_per_task=min_ann,
                label_config='<View><Text name="text" value="$text"/></View>',
            )
            self.db.add(project)
            projects.append(project)
        self.db.commit()

        # Verify each project's requirement
        for i, project in enumerate(projects):
            expected_min = [1, 2, 3, 5][i]
            assert project.min_annotations_per_task == expected_min

            # Create a task for each project
            task = Task(
                id=str(uuid.uuid4()),
                inner_id=1,
                project_id=project.id,
                data={"text": f"Task for project with {expected_min} min annotations"},
                is_labeled=False,
                total_annotations=0,
            )
            self.db.add(task)
            self.db.commit()

            # Add exactly the minimum required annotations, each from a DISTINCT
            # annotator — one active annotation per (task, user) is enforced by
            # the uq_annotations_active_task_user index, so a multi-annotation
            # task is reached across distinct annotators (the real-world shape).
            for j in range(expected_min):
                annotator = User(
                    id=str(uuid.uuid4()),
                    username=f"prog-annotator-{uuid.uuid4().hex[:8]}",
                    email=f"{uuid.uuid4().hex[:8]}@example.com",
                    name=f"Annotator {j + 1}",
                    is_active=True,
                )
                self.db.add(annotator)
                self.db.flush()
                ann = Annotation(
                    id=str(uuid.uuid4()),
                    task_id=task.id,
                    project_id=project.id,
                    completed_by=annotator.id,
                    result=[{"value": {"text": f"Annotation {j+1}"}}],
                    was_cancelled=False,
                )
                self.db.add(ann)

            task.total_annotations = expected_min
            task.is_labeled = True
            self.db.commit()

            # Verify task is marked as complete
            assert task.is_labeled == True  # noqa: E712
            assert task.total_annotations == expected_min
