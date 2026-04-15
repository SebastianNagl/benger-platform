"""
Unit tests for services/analytics_service.py — covers all major methods.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from services.analytics_service import (
    AnalyticsService,
    AnalyticsOverview,
    Benchmarks,
    PerformanceTrend,
    ProjectInsights,
    QualityMetrics,
    UserAnalytics,
)


class TestAnalyticsServiceInit:
    """Tests for AnalyticsService initialization."""

    def test_default_init(self):
        svc = AnalyticsService()
        assert svc.redis_client is None
        assert svc.cache_ttl == 300

    def test_with_redis(self):
        redis = Mock()
        svc = AnalyticsService(redis_client=redis)
        assert svc.redis_client is redis


class TestCalculateOverview:
    """Tests for _calculate_overview."""

    def test_basic_overview(self):
        svc = AnalyticsService()
        db = Mock()

        # Base query mock (count returns 10)
        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.count.return_value = 10

        # Completed query (8 completed)
        completed_q = MagicMock()
        completed_q.count.return_value = 8
        base_q.filter.side_effect = lambda *args: completed_q

        # Annotators (3 unique)
        base_q_new = MagicMock()
        base_q_new.filter.return_value = base_q_new
        base_q_new.count.return_value = 10
        base_q_new.with_entities.return_value.distinct.return_value.count.return_value = 3

        # Task count
        task_q = MagicMock()
        task_q.filter.return_value = task_q
        task_q.count.return_value = 20

        # Annotations with lead_time
        ann1 = Mock(lead_time=120)
        ann2 = Mock(lead_time=60)
        time_q = MagicMock()
        time_q.filter.return_value = time_q
        time_q.all.return_value = [ann1, ann2]

        # Setup the chain
        main_q = MagicMock()
        main_q.filter.return_value = main_q
        main_q.count.side_effect = [10, 8]
        main_q.with_entities.return_value.distinct.return_value.count.return_value = 3
        main_q.filter.return_value.all.return_value = [ann1, ann2]

        db.query.side_effect = [main_q, task_q]

        result = svc._calculate_overview(db, "proj-1", [])
        assert isinstance(result, AnalyticsOverview)

    def test_zero_annotations(self):
        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.count.return_value = 0
        base_q.with_entities.return_value.distinct.return_value.count.return_value = 0
        base_q.filter.return_value.all.return_value = []

        task_q = MagicMock()
        task_q.filter.return_value = task_q
        task_q.count.return_value = 0

        db.query.side_effect = [base_q, task_q]

        result = svc._calculate_overview(db, "proj-1", [])
        assert result.total_annotations == 0
        assert result.average_quality == 0
        assert result.completion_rate == 0
        assert result.throughput_per_hour == 0


class TestExtractRatingFromAnnotation:
    """Tests for _extract_rating_from_annotation."""

    def test_none_result(self):
        svc = AnalyticsService()
        assert svc._extract_rating_from_annotation(None) is None

    def test_empty_list(self):
        svc = AnalyticsService()
        assert svc._extract_rating_from_annotation([]) is None

    def test_choices_annotation(self):
        svc = AnalyticsService()
        result = [{"value": {"choices": ["Positive", "Neutral"]}}]
        rating = svc._extract_rating_from_annotation(result)
        assert "Neutral" in rating
        assert "Positive" in rating

    def test_text_annotation(self):
        svc = AnalyticsService()
        result = [{"value": {"text": "some answer"}}]
        rating = svc._extract_rating_from_annotation(result)
        assert rating == "some answer"

    def test_span_annotation(self):
        svc = AnalyticsService()
        result = [
            {
                "value": {
                    "spans": [
                        {"labels": ["PER"], "start": 0, "end": 5},
                        {"labels": ["ORG"], "start": 10, "end": 15},
                    ]
                }
            }
        ]
        rating = svc._extract_rating_from_annotation(result)
        assert "PER" in rating
        assert "ORG" in rating

    def test_non_list_result(self):
        svc = AnalyticsService()
        result = "simple_string"
        rating = svc._extract_rating_from_annotation(result)
        assert rating == "simple_string"

    def test_empty_string_result(self):
        svc = AnalyticsService()
        assert svc._extract_rating_from_annotation("") is None


class TestCalculateFleissKappa:
    """Tests for _calculate_fleiss_kappa."""

    def test_empty_matrix(self):
        svc = AnalyticsService()
        assert svc._calculate_fleiss_kappa([]) == 1.0

    def test_empty_rows(self):
        svc = AnalyticsService()
        assert svc._calculate_fleiss_kappa([[]]) == 1.0

    def test_all_none(self):
        svc = AnalyticsService()
        matrix = [[None, None], [None, None]]
        assert svc._calculate_fleiss_kappa(matrix) == 1.0

    def test_perfect_agreement(self):
        svc = AnalyticsService()
        matrix = [
            ["A", "A"],
            ["B", "B"],
            ["A", "A"],
        ]
        kappa = svc._calculate_fleiss_kappa(matrix)
        assert kappa == 1.0

    def test_mixed_agreement(self):
        svc = AnalyticsService()
        matrix = [
            ["A", "B"],
            ["A", "A"],
            ["B", "A"],
        ]
        kappa = svc._calculate_fleiss_kappa(matrix)
        assert 0.0 <= kappa <= 1.0

    def test_complete_disagreement(self):
        svc = AnalyticsService()
        # With 2 raters and 2 categories, alternating disagreement
        matrix = [
            ["A", "B"],
            ["B", "A"],
        ]
        kappa = svc._calculate_fleiss_kappa(matrix)
        assert kappa == 0.0  # Complete disagreement, kappa = 0 or negative clamped to 0


class TestGetProjectStatistics:
    """Tests for get_project_statistics."""

    def test_project_not_found(self):
        svc = AnalyticsService()
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Project proj-1 not found"):
            svc.get_project_statistics(db, "proj-1")

    def test_cached_result(self):
        redis = Mock()
        cached = json.dumps({"project_id": "proj-1", "cached": True})
        redis.get.return_value = cached

        svc = AnalyticsService(redis_client=redis)
        db = Mock()

        result = svc.get_project_statistics(db, "proj-1")
        assert result["cached"] is True

    def test_cache_miss_calculates(self):
        redis = Mock()
        redis.get.return_value = None

        svc = AnalyticsService(redis_client=redis)
        db = Mock()

        project = Mock(title="Test Project")
        db.query.return_value.filter.return_value.first.return_value = project

        with patch.object(
            svc, "_calculate_overview"
        ) as mock_overview, patch.object(
            svc, "_calculate_performance_trends"
        ) as mock_trends, patch.object(
            svc, "_calculate_quality_metrics"
        ) as mock_quality, patch.object(
            svc, "_calculate_user_analytics"
        ) as mock_users, patch.object(
            svc, "_calculate_project_insights"
        ) as mock_insights, patch.object(
            svc, "_calculate_benchmarks"
        ) as mock_benchmarks:
            mock_overview.return_value = AnalyticsOverview(
                total_annotations=10,
                total_annotators=3,
                average_quality=80.0,
                completion_rate=70.0,
                total_time_spent=3600,
                throughput_per_hour=2.5,
            )
            mock_trends.return_value = []
            mock_quality.return_value = QualityMetrics(
                quality_distribution=[],
                inter_annotator_agreement=0.8,
                consistency_score=0.9,
                error_rate=0.1,
                revision_rate=0.05,
            )
            mock_users.return_value = []
            mock_insights.return_value = ProjectInsights(
                busiest_hours=[],
                completion_patterns=[],
                difficulty_analysis=[],
                annotation_types=[],
            )
            mock_benchmarks.return_value = Benchmarks(
                industry_average_quality=None,
                industry_average_time=None,
                similar_projects=[],
            )

            result = svc.get_project_statistics(db, "proj-1")

            assert result["project_id"] == "proj-1"
            assert result["project_name"] == "Test Project"
            assert result["overview"]["total_annotations"] == 10
            # Should cache the result
            redis.set.assert_called_once()

    def test_without_redis(self):
        svc = AnalyticsService()
        db = Mock()

        project = Mock(title="Test")
        db.query.return_value.filter.return_value.first.return_value = project

        with patch.object(
            svc, "_calculate_overview"
        ) as mock_overview, patch.object(
            svc, "_calculate_performance_trends"
        ) as mock_trends, patch.object(
            svc, "_calculate_quality_metrics"
        ) as mock_quality, patch.object(
            svc, "_calculate_user_analytics"
        ) as mock_users, patch.object(
            svc, "_calculate_project_insights"
        ) as mock_insights, patch.object(
            svc, "_calculate_benchmarks"
        ) as mock_benchmarks:
            mock_overview.return_value = AnalyticsOverview(
                total_annotations=0, total_annotators=0, average_quality=0,
                completion_rate=0, total_time_spent=0, throughput_per_hour=0,
            )
            mock_trends.return_value = []
            mock_quality.return_value = QualityMetrics(
                quality_distribution=[], inter_annotator_agreement=1.0,
                consistency_score=1.0, error_rate=0, revision_rate=0,
            )
            mock_users.return_value = []
            mock_insights.return_value = ProjectInsights(
                busiest_hours=[], completion_patterns=[],
                difficulty_analysis=[], annotation_types=[],
            )
            mock_benchmarks.return_value = Benchmarks(
                industry_average_quality=None, industry_average_time=None,
                similar_projects=[],
            )

            result = svc.get_project_statistics(db, "proj-1")
            assert result is not None


class TestCalculatePerformanceTrends:
    """Tests for _calculate_performance_trends."""

    def test_default_date_range(self):
        svc = AnalyticsService()
        db = Mock()

        day_q = MagicMock()
        day_q.filter.return_value = day_q
        day_q.count.return_value = 0
        day_q.all.return_value = []
        day_q.with_entities.return_value.distinct.return_value.count.return_value = 0

        db.query.return_value = day_q

        result = svc._calculate_performance_trends(db, "proj-1", None, None)
        assert isinstance(result, list)
        assert len(result) == 31  # 30 days + 1 for inclusive end

    def test_custom_date_range(self):
        svc = AnalyticsService()
        db = Mock()

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 3)

        day_q = MagicMock()
        day_q.filter.return_value = day_q
        day_q.count.return_value = 2
        day_q.all.return_value = []
        day_q.with_entities.return_value.distinct.return_value.count.return_value = 1

        db.query.return_value = day_q

        result = svc._calculate_performance_trends(db, "proj-1", start, end)
        assert len(result) == 3


class TestCalculateQualityMetrics:
    """Tests for _calculate_quality_metrics."""

    def test_no_annotations(self):
        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.count.side_effect = [0, 0, 0, 0]

        # IAA query
        iaa_q = MagicMock()
        iaa_q.filter.return_value = iaa_q
        iaa_q.group_by.return_value = iaa_q
        iaa_q.having.return_value = iaa_q
        iaa_q.with_entities.return_value = iaa_q
        iaa_q.all.return_value = []

        db.query.side_effect = [base_q, iaa_q]

        with patch.object(svc, "_calculate_inter_annotator_agreement", return_value=1.0):
            result = svc._calculate_quality_metrics(db, "proj-1", [])
            assert isinstance(result, QualityMetrics)
            assert result.consistency_score == 1.0
            assert result.error_rate == 0


class TestCalculateBenchmarks:
    """Tests for _calculate_benchmarks."""

    def test_no_other_projects(self):
        svc = AnalyticsService()
        db = Mock()

        global_stat = Mock(
            total_annotations=0, completed_annotations=0, avg_lead_time=None
        )
        global_q = MagicMock()
        global_q.join.return_value = global_q
        global_q.filter.return_value = global_q
        global_q.first.return_value = global_stat

        project_q = MagicMock()
        project_q.outerjoin.return_value = project_q
        project_q.filter.return_value = project_q
        project_q.group_by.return_value = project_q
        project_q.limit.return_value = project_q
        project_q.all.return_value = []

        db.query.side_effect = [global_q, project_q]

        result = svc._calculate_benchmarks(db, "proj-1")
        assert isinstance(result, Benchmarks)
        assert result.industry_average_quality is None
        assert result.industry_average_time is None
        assert result.similar_projects == []

    def test_with_other_projects(self):
        svc = AnalyticsService()
        db = Mock()

        global_stat = Mock(
            total_annotations=100, completed_annotations=90, avg_lead_time=45.5
        )
        global_q = MagicMock()
        global_q.join.return_value = global_q
        global_q.filter.return_value = global_q
        global_q.first.return_value = global_stat

        proj_stat = Mock(
            id="other-proj", title="Other Project",
            total_annotations=50, completed_annotations=40,
            unique_users=5, avg_lead_time=30.0,
        )
        project_q = MagicMock()
        project_q.outerjoin.return_value = project_q
        project_q.filter.return_value = project_q
        project_q.group_by.return_value = project_q
        project_q.limit.return_value = project_q
        project_q.all.return_value = [proj_stat]

        db.query.side_effect = [global_q, project_q]

        result = svc._calculate_benchmarks(db, "proj-1")
        assert result.industry_average_quality == 90.0
        assert result.industry_average_time == 45.5
        assert len(result.similar_projects) == 1
        assert result.similar_projects[0]["project_name"] == "Other Project"


class TestCalculateUserAnalytics:
    """Tests for _calculate_user_analytics."""

    def test_no_users(self):
        svc = AnalyticsService()
        db = Mock()

        user_q = MagicMock()
        user_q.join.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.group_by.return_value = user_q
        user_q.all.return_value = []

        db.query.return_value = user_q

        result = svc._calculate_user_analytics(db, "proj-1", [])
        assert result == []

    def test_with_user_stats(self):
        svc = AnalyticsService()
        db = Mock()

        stat = Mock(
            user_id="user-1",
            email="test@test.com",
            annotations_count=10,
            completed_count=8,
            avg_lead_time=120.0,
            total_lead_time=1200.0,
            recent_count=5,
            last_active_date=datetime(2025, 6, 1),
        )
        stat.name = "Test User"

        user_q = MagicMock()
        user_q.join.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.group_by.return_value = user_q
        user_q.all.return_value = [stat]

        db.query.return_value = user_q

        result = svc._calculate_user_analytics(db, "proj-1", [])
        assert len(result) == 1
        assert result[0].user_id == "user-1"
        assert result[0].annotations_count == 10
        assert result[0].quality_score == 80.0  # 8/10 * 100

    def test_user_no_name_uses_email(self):
        svc = AnalyticsService()
        db = Mock()

        stat = Mock(
            user_id="user-1",
            email="test@test.com",
            annotations_count=5,
            completed_count=5,
            avg_lead_time=None,
            total_lead_time=None,
            recent_count=0,
            last_active_date=None,
        )
        # Mock.name is special in unittest.mock; set it separately
        stat.name = None

        user_q = MagicMock()
        user_q.join.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.group_by.return_value = user_q
        user_q.all.return_value = [stat]

        db.query.return_value = user_q

        result = svc._calculate_user_analytics(db, "proj-1", [])
        assert result[0].user_name == "test@test.com"
        assert result[0].last_active == "Never"
        assert result[0].throughput == 0


class TestCalculateProjectInsights:
    """Tests for _calculate_project_insights."""

    def test_empty_project(self):
        svc = AnalyticsService()
        db = Mock()

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.all.return_value = []
        base_q.count.return_value = 0

        task_q = MagicMock()
        task_q.join.return_value = task_q
        task_q.filter.return_value = task_q
        task_q.group_by.return_value = task_q
        task_q.all.return_value = []

        db.query.side_effect = [base_q, task_q, base_q, base_q]

        result = svc._calculate_project_insights(db, "proj-1", [])
        assert isinstance(result, ProjectInsights)
        assert result.busiest_hours == []

    def test_with_annotations(self):
        svc = AnalyticsService()
        db = Mock()

        ann1 = Mock(created_at=datetime(2025, 1, 1, 10, 0))
        ann2 = Mock(created_at=datetime(2025, 1, 1, 10, 30))
        ann3 = Mock(created_at=datetime(2025, 1, 2, 14, 0))

        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.all.return_value = [ann1, ann2, ann3]
        base_q.count.side_effect = [3, 0]

        task_q = MagicMock()
        task_q.join.return_value = task_q
        task_q.filter.return_value = task_q
        task_q.group_by.return_value = task_q
        task_q.all.return_value = []

        db.query.side_effect = [base_q, task_q, base_q, base_q]

        result = svc._calculate_project_insights(db, "proj-1", [])
        assert len(result.busiest_hours) > 0
        assert result.busiest_hours[0]["hour"] == 10  # Most annotations at 10:00
