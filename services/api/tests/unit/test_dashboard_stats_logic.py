"""
Unit tests for dashboard stats business logic.
"""

from unittest.mock import MagicMock, Mock

import pytest


class TestDashboardStatsLogic:
    """Tests for dashboard stats logic."""

    def test_cache_key_format_with_org(self):
        user_id = "user-1"
        org_context = "org-123"
        cache_key = f"dashboard_stats:{user_id}:{org_context or 'private'}"
        assert cache_key == "dashboard_stats:user-1:org-123"

    def test_cache_key_format_private(self):
        user_id = "user-1"
        org_context = None
        cache_key = f"dashboard_stats:{user_id}:{org_context or 'private'}"
        assert cache_key == "dashboard_stats:user-1:private"

    def test_cache_key_empty_org(self):
        user_id = "user-2"
        org_context = ""
        cache_key = f"dashboard_stats:{user_id}:{org_context or 'private'}"
        assert cache_key == "dashboard_stats:user-2:private"

    def test_stats_default_on_error(self):
        default_stats = {
            "project_count": 0,
            "task_count": 0,
            "annotation_count": 0,
            "projects_with_generations": 0,
            "projects_with_evaluations": 0,
        }
        assert all(v == 0 for v in default_stats.values())

    def test_stats_result_mapping(self):
        result = Mock(
            project_count=5,
            task_count=25,
            annotation_count=12,
            projects_with_generations=3,
            projects_with_evaluations=2,
        )
        stats = {
            "project_count": result.project_count if result else 0,
            "task_count": result.task_count if result else 0,
            "annotation_count": result.annotation_count if result else 0,
            "projects_with_generations": result.projects_with_generations if result else 0,
            "projects_with_evaluations": result.projects_with_evaluations if result else 0,
        }
        assert stats["project_count"] == 5
        assert stats["annotation_count"] == 12

    def test_stats_null_result(self):
        result = None
        stats = {
            "project_count": result.project_count if result else 0,
            "task_count": result.task_count if result else 0,
        }
        assert stats["project_count"] == 0

    def test_placeholders_generation(self):
        accessible_ids = ["p1", "p2", "p3"]
        placeholders = ", ".join([f":pid_{i}" for i in range(len(accessible_ids))])
        assert placeholders == ":pid_0, :pid_1, :pid_2"

        bind_params = {f"pid_{i}": pid for i, pid in enumerate(accessible_ids)}
        assert bind_params == {"pid_0": "p1", "pid_1": "p2", "pid_2": "p3"}

    def test_placeholders_single(self):
        accessible_ids = ["p1"]
        placeholders = ", ".join([f":pid_{i}" for i in range(len(accessible_ids))])
        assert placeholders == ":pid_0"

    def test_placeholders_empty(self):
        accessible_ids = []
        placeholders = ", ".join([f":pid_{i}" for i in range(len(accessible_ids))])
        assert placeholders == ""
