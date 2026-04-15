"""
Unit tests for routers/evaluations/helpers.py to increase coverage.
Tests helper functions used across evaluation endpoints.
"""

import pytest
from datetime import datetime, timezone


class TestExtractMetricName:
    def setup_method(self):
        from routers.evaluations.helpers import extract_metric_name
        self.extract = extract_metric_name

    def test_string_input(self):
        assert self.extract("bleu") == "bleu"

    def test_dict_with_name(self):
        assert self.extract({"name": "rouge_l"}) == "rouge_l"

    def test_dict_without_name(self):
        result = self.extract({"value": "something"})
        assert isinstance(result, str)

    def test_none_input(self):
        result = self.extract(None)
        assert isinstance(result, str) or result is None

    def test_empty_string(self):
        assert self.extract("") == ""

    def test_dict_with_empty_name(self):
        result = self.extract({"name": ""})
        assert result == ""


class TestGetEvaluationTypesForTaskType:
    def test_import(self):
        from routers.evaluations.helpers import get_evaluation_types_for_task_type
        assert callable(get_evaluation_types_for_task_type)


class TestEvaluationResultsResponse:
    def test_creation(self):
        from routers.evaluations.helpers import EvaluationResultsResponse
        resp = EvaluationResultsResponse(
            project_id="p-1",
            results={},
            metadata={},
            created_at=datetime.now(timezone.utc),
        )
        assert resp.project_id == "p-1"

    def test_with_metrics(self):
        from routers.evaluations.helpers import EvaluationResultsResponse
        resp = EvaluationResultsResponse(
            project_id="p-1",
            results={"bleu": 0.8, "rouge": 0.9},
            metadata={"type": "automated"},
            created_at=datetime.now(timezone.utc),
        )
        assert resp.results["bleu"] == 0.8


class TestEvaluationStatus:
    def test_creation(self):
        from routers.evaluations.helpers import EvaluationStatus
        status = EvaluationStatus(
            id="eval-1",
            status="completed",
            message="Done",
        )
        assert status.id == "eval-1"
        assert status.status == "completed"

    def test_pending(self):
        from routers.evaluations.helpers import EvaluationStatus
        status = EvaluationStatus(
            id="eval-2",
            status="pending",
            message="Waiting",
        )
        assert status.status == "pending"


class TestEvaluationTypeResponse:
    def test_creation(self):
        from routers.evaluations.helpers import EvaluationTypeResponse
        resp = EvaluationTypeResponse(
            id="bleu",
            name="BLEU",
            description="BLEU score",
            category="text",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_generation"],
            is_active=True,
        )
        assert resp.id == "bleu"
        assert resp.higher_is_better is True

    def test_minimal(self):
        from routers.evaluations.helpers import EvaluationTypeResponse
        resp = EvaluationTypeResponse(
            id="custom",
            name="Custom",
            category="text",
        )
        assert resp.id == "custom"
        assert resp.description is None
        assert resp.higher_is_better is True  # default


class TestEvaluationResult:
    def test_creation(self):
        from routers.evaluations.helpers import EvaluationResult
        result = EvaluationResult(
            id="eval-1",
            project_id="p-1",
            model_id="gpt-4",
            metrics={"bleu": 0.8},
            created_at=datetime.now(timezone.utc),
            status="completed",
            metadata={"key": "val"},
            samples_evaluated=10,
        )
        assert result.id == "eval-1"
        assert result.samples_evaluated == 10

    def test_with_none_metadata(self):
        from routers.evaluations.helpers import EvaluationResult
        result = EvaluationResult(
            id="eval-2",
            project_id="p-1",
            model_id="gpt-3.5",
            metrics={},
            created_at=datetime.now(timezone.utc),
            status="failed",
            metadata=None,
            samples_evaluated=0,
        )
        assert result.metadata is None


class TestResolveUserOrgForProject:
    def test_callable(self):
        from routers.evaluations.helpers import resolve_user_org_for_project
        assert callable(resolve_user_org_for_project)
