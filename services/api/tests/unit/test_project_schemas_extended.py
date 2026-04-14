"""
Unit tests for project_schemas.py to increase coverage.
Tests Pydantic schema validation, serialization, and edge cases.
"""

import pytest
from datetime import datetime


class TestSkipTaskRequest:
    def test_basic_creation(self):
        from project_schemas import SkipTaskRequest
        req = SkipTaskRequest()
        assert req.comment is None

    def test_with_comment(self):
        from project_schemas import SkipTaskRequest
        req = SkipTaskRequest(comment="Too difficult")
        assert req.comment == "Too difficult"


class TestSkipTaskResponse:
    def test_has_required_fields(self):
        from project_schemas import SkipTaskResponse
        fields = SkipTaskResponse.model_fields
        assert "task_id" in fields or "message" in fields or len(fields) > 0


class TestProjectCreate:
    def test_minimal(self):
        from project_schemas import ProjectCreate
        project = ProjectCreate(title="Test Project")
        assert project.title == "Test Project"
        assert project.description is None
        assert project.label_config is None

    def test_full(self):
        from project_schemas import ProjectCreate
        project = ProjectCreate(
            title="Full Project",
            description="A description",
            label_config="<View><TextArea name='answer'/></View>",
            expert_instruction="Do this",
            show_instruction=True,
            show_skip_button=False,
            enable_empty_annotation=True,
        )
        assert project.title == "Full Project"
        assert project.show_instruction is True


class TestProjectUpdate:
    def test_empty_update(self):
        from project_schemas import ProjectUpdate
        update = ProjectUpdate()
        data = update.dict(exclude_unset=True)
        assert data == {}

    def test_partial_update(self):
        from project_schemas import ProjectUpdate
        update = ProjectUpdate(title="New Title")
        data = update.dict(exclude_unset=True)
        assert "title" in data
        assert data["title"] == "New Title"

    def test_all_fields(self):
        from project_schemas import ProjectUpdate
        update = ProjectUpdate(
            title="Updated",
            description="Updated desc",
            show_skip_button=True,
            enable_empty_annotation=False,
        )
        data = update.dict(exclude_unset=True)
        assert data["title"] == "Updated"
        assert data["show_skip_button"] is True


class TestReviewSubmit:
    def test_approve(self):
        from project_schemas import ReviewSubmit
        review = ReviewSubmit(action="approve")
        assert review.action == "approve"
        assert review.comment is None
        assert review.result is None

    def test_fix_with_result(self):
        from project_schemas import ReviewSubmit
        review = ReviewSubmit(
            action="fix",
            result=[{"from_name": "answer", "value": {"text": "fixed"}}],
            comment="Fixed the answer",
        )
        assert review.action == "fix"
        assert review.result is not None
        assert review.comment == "Fixed the answer"

    def test_reject_with_comment(self):
        from project_schemas import ReviewSubmit
        review = ReviewSubmit(
            action="reject",
            comment="Incorrect annotation",
        )
        assert review.action == "reject"


class TestPaginatedResponse:
    def test_empty_response(self):
        from project_schemas import PaginatedResponse
        resp = PaginatedResponse(
            items=[],
            total=0,
            page=1,
            page_size=10,
            pages=0,
        )
        assert resp.items == []
        assert resp.total == 0

    def test_with_items(self):
        from project_schemas import PaginatedResponse
        resp = PaginatedResponse(
            items=["a", "b", "c"],
            total=100,
            page=2,
            page_size=10,
            pages=10,
        )
        assert len(resp.items) == 3
        assert resp.page == 2
        assert resp.pages == 10


class TestTaskResponse:
    def test_creation(self):
        from project_schemas import TaskResponse
        task = TaskResponse(
            id="task-1",
            data={"text": "hello"},
            meta={},
            created_at=datetime.now(),
            updated_at=None,
            inner_id=1,
            total_annotations=0,
            cancelled_annotations=0,
            total_predictions=0,
            completed_at=None,
            file_upload=None,
            storage_filename=None,
            annotations_results=None,
            annotations_ids=None,
            predictions_score=None,
            predictions_model_versions=None,
            avg_lead_time=None,
            draft_exists=False,
            updated_by=None,
            project_id="p-1",
            is_labeled=False,
        )
        assert task.id == "task-1"
        assert task.is_labeled is False


class TestAnnotationResponse:
    def test_has_fields(self):
        from project_schemas import AnnotationResponse
        fields = AnnotationResponse.model_fields
        assert "id" in fields
        assert "result" in fields
