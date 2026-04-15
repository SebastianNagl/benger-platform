"""
Unit tests for services/analytics_service.py to increase coverage.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from services.analytics_service import (
    AnalyticsOverview,
    PerformanceTrend,
    AnalyticsService,
    QualityMetrics,
    UserAnalytics,
    ProjectInsights,
    Benchmarks,
)


class TestDataclasses:
    def test_analytics_overview(self):
        overview = AnalyticsOverview(
            total_annotations=100,
            total_annotators=5,
            average_quality=0.85,
            completion_rate=0.75,
            total_time_spent=3600,
            throughput_per_hour=25.0,
        )
        assert overview.total_annotations == 100

    def test_performance_trend(self):
        trend = PerformanceTrend(
            date="2025-01-20",
            annotations_completed=50,
            average_quality=0.9,
            average_time=120.0,
            active_users=3,
        )
        assert trend.date == "2025-01-20"
        assert trend.active_users == 3

    def test_quality_metrics(self):
        qm = QualityMetrics(
            quality_distribution=[],
            inter_annotator_agreement=0.85,
            consistency_score=0.9,
            error_rate=0.05,
            revision_rate=0.1,
        )
        assert qm.inter_annotator_agreement == 0.85

    def test_user_analytics(self):
        ua = UserAnalytics(
            user_id="u1",
            user_name="test",
            annotations_count=50,
            quality_score=0.9,
            average_time=60.0,
            throughput=5.0,
            consistency=0.95,
            activity_score=0.8,
            last_active="2025-01-20",
        )
        assert ua.user_id == "u1"

    def test_project_insights(self):
        pi = ProjectInsights(
            busiest_hours=[],
            completion_patterns=[],
            difficulty_analysis=[],
            annotation_types=[],
        )
        assert pi.busiest_hours == []

    def test_benchmarks(self):
        b = Benchmarks(
            industry_average_quality=0.85,
            industry_average_time=90.0,
            similar_projects=[],
        )
        assert b.industry_average_quality == 0.85

    def test_benchmarks_none_values(self):
        b = Benchmarks(
            industry_average_quality=None,
            industry_average_time=None,
            similar_projects=[],
        )
        assert b.industry_average_quality is None


class TestAnalyticsServiceImport:
    def test_class_exists(self):
        assert AnalyticsService is not None

    def test_global_instance(self):
        from services.analytics_service import analytics_service
        assert analytics_service is not None
