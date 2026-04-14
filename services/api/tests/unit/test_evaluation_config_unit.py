"""
Unit tests for evaluation config and validation routers.

Targets:
- routers/evaluations/config.py — 13.04%
- routers/evaluations/status.py — 19.29%
- routers/evaluations/validation.py — 16.92%
- routers/evaluations/helpers.py — 83.33%
"""

import pytest


class TestEvaluationConfigRouter:
    """Test evaluation config router structure."""

    def test_config_router_exists(self):
        from routers.evaluations.config import router
        assert router is not None

    def test_config_router_has_routes(self):
        from routers.evaluations.config import router
        routes = [r.path for r in router.routes]
        assert len(routes) >= 1


class TestEvaluationStatusRouter:
    """Test evaluation status router structure."""

    def test_status_router_exists(self):
        from routers.evaluations.status import router
        assert router is not None

    def test_status_router_has_routes(self):
        from routers.evaluations.status import router
        routes = [r.path for r in router.routes]
        assert len(routes) >= 1


class TestEvaluationValidationRouter:
    """Test evaluation validation router structure."""

    def test_validation_router_exists(self):
        from routers.evaluations.validation import router
        assert router is not None


class TestEvaluationMultiFieldRouter:
    """Test multi-field evaluation router structure."""

    def test_multi_field_router_exists(self):
        from routers.evaluations.multi_field import router
        assert router is not None


class TestEvaluationHumanRouter:
    """Test human evaluation router structure."""

    def test_human_router_exists(self):
        from routers.evaluations.human import router
        assert router is not None


class TestEvaluationHelpersModels:
    """Test evaluation helper models."""

    def test_evaluation_results_response(self):
        from routers.evaluations.helpers import EvaluationResultsResponse
        from datetime import datetime
        resp = EvaluationResultsResponse(
            project_id="proj-1",
            results={"type": "automated", "metrics": {"accuracy": 0.9}},
            metadata={"evaluator": "test"},
            created_at=datetime.now(),
        )
        assert resp.project_id == "proj-1"
        assert resp.results["type"] == "automated"

    def test_resolve_user_org_for_project_importable(self):
        from routers.evaluations.helpers import resolve_user_org_for_project
        assert resolve_user_org_for_project is not None
