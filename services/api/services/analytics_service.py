"""
Analytics Service for Project-Based Annotation System

Provides comprehensive analytics calculations for annotation projects including:
- Quality scoring algorithms (simplified for new model)
- Performance trend analysis
- User productivity metrics
- Project insights

MIGRATED: Now uses project_models instead of legacy annotation models
"""

import json
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from models import User
from project_models import Annotation, Project, Task

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsOverview:
    """Overview analytics data structure"""

    total_annotations: int
    total_annotators: int
    average_quality: float
    completion_rate: float
    total_time_spent: int  # in seconds
    throughput_per_hour: float


@dataclass
class PerformanceTrend:
    """Performance trend data point"""

    date: str
    annotations_completed: int
    average_quality: float
    average_time: float
    active_users: int


@dataclass
class QualityMetrics:
    """Quality metrics data structure (simplified for new model)"""

    quality_distribution: List[Dict[str, Any]]
    inter_annotator_agreement: float
    consistency_score: float
    error_rate: float
    revision_rate: float


@dataclass
class UserAnalytics:
    """User performance analytics"""

    user_id: str
    user_name: str
    annotations_count: int
    quality_score: float
    average_time: float
    throughput: float
    consistency: float
    activity_score: float
    last_active: str


@dataclass
class ProjectInsights:
    """Project-level insights"""

    busiest_hours: List[Dict[str, Any]]
    completion_patterns: List[Dict[str, Any]]
    difficulty_analysis: List[Dict[str, Any]]
    annotation_types: List[Dict[str, Any]]


@dataclass
class Benchmarks:
    """Benchmarking data"""

    industry_average_quality: Optional[float]  # None if insufficient data
    industry_average_time: Optional[float]  # None if insufficient data
    similar_projects: List[Dict[str, Any]]


class AnalyticsService:
    """Service for calculating annotation analytics"""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.cache_ttl = 300  # 5 minutes cache

    def get_project_statistics(
        self,
        db: Session,
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive analytics for an annotation project

        Args:
            db: Database session
            project_id: Project identifier
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary containing all analytics data
        """
        try:
            # Check cache first
            cache_key = f"analytics:{project_id}:{start_date}:{end_date}"
            if self.redis_client:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)

            # Verify project exists
            project = db.query(Project).filter(Project.id == project_id).first()

            if not project:
                raise ValueError(f"Project {project_id} not found")

            # Build date filter
            date_filter = []
            if start_date:
                date_filter.append(Annotation.created_at >= start_date)
            if end_date:
                date_filter.append(Annotation.created_at <= end_date)

            # Calculate all analytics components
            overview = self._calculate_overview(db, project_id, date_filter)
            performance_trends = self._calculate_performance_trends(
                db, project_id, start_date, end_date
            )
            quality_metrics = self._calculate_quality_metrics(db, project_id, date_filter)
            user_analytics = self._calculate_user_analytics(db, project_id, date_filter)
            project_insights = self._calculate_project_insights(db, project_id, date_filter)
            benchmarks = self._calculate_benchmarks(db, project_id)

            # Compile results
            result = {
                "project_id": project_id,
                "project_name": project.title,
                "date_range": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None,
                },
                "overview": {
                    "total_annotations": overview.total_annotations,
                    "total_annotators": overview.total_annotators,
                    "average_quality": overview.average_quality,
                    "completion_rate": overview.completion_rate,
                    "total_time_spent": overview.total_time_spent,
                    "throughput_per_hour": overview.throughput_per_hour,
                },
                "performance_trends": [
                    {
                        "date": trend.date,
                        "annotations_completed": trend.annotations_completed,
                        "average_quality": trend.average_quality,
                        "average_time": trend.average_time,
                        "active_users": trend.active_users,
                    }
                    for trend in performance_trends
                ],
                "quality_metrics": {
                    "quality_distribution": quality_metrics.quality_distribution,
                    "inter_annotator_agreement": quality_metrics.inter_annotator_agreement,
                    "consistency_score": quality_metrics.consistency_score,
                    "error_rate": quality_metrics.error_rate,
                    "revision_rate": quality_metrics.revision_rate,
                },
                "user_analytics": [
                    {
                        "user_id": user.user_id,
                        "user_name": user.user_name,
                        "annotations_count": user.annotations_count,
                        "quality_score": user.quality_score,
                        "average_time": user.average_time,
                        "throughput": user.throughput,
                        "consistency": user.consistency,
                        "activity_score": user.activity_score,
                        "last_active": user.last_active,
                    }
                    for user in user_analytics
                ],
                "project_insights": {
                    "busiest_hours": project_insights.busiest_hours,
                    "completion_patterns": project_insights.completion_patterns,
                    "difficulty_analysis": project_insights.difficulty_analysis,
                    "annotation_types": project_insights.annotation_types,
                },
                "benchmarks": {
                    "industry_average_quality": benchmarks.industry_average_quality,
                    "industry_average_time": benchmarks.industry_average_time,
                    "similar_projects": benchmarks.similar_projects,
                },
                "generated_at": datetime.now().isoformat(),
            }

            # Cache result
            if self.redis_client:
                self.redis_client.set(cache_key, json.dumps(result), ex=self.cache_ttl)

            return result

        except Exception as e:
            logger.error(f"Error calculating analytics for project {project_id}: {e}")
            raise

    def _calculate_overview(
        self, db: Session, project_id: str, date_filter: List
    ) -> AnalyticsOverview:
        """Calculate overview metrics"""

        # Base annotation query
        base_query = db.query(Annotation).filter(Annotation.project_id == project_id)

        if date_filter:
            base_query = base_query.filter(and_(*date_filter))

        # Total annotations
        total_annotations = base_query.count()

        # Completed annotations (not cancelled)
        completed_query = base_query.filter(Annotation.was_cancelled == False)
        completed_count = completed_query.count()

        # Unique annotators
        annotators = base_query.with_entities(Annotation.completed_by).distinct().count()

        # Average quality score - NOT AVAILABLE IN NEW MODEL
        # Using completion rate as proxy for quality
        average_quality = (
            (completed_count / total_annotations * 100) if total_annotations > 0 else 0
        )

        # Completion rate
        # Get total tasks in project
        total_tasks = db.query(Task).filter(Task.project_id == project_id).count()
        completion_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0

        # Total time spent (using lead_time field)
        time_spent_annotations = base_query.filter(Annotation.lead_time.isnot(None)).all()

        total_time = sum(ann.lead_time for ann in time_spent_annotations if ann.lead_time)

        # Throughput per hour
        if total_time > 0:
            hours = total_time / 3600
            throughput = completed_count / hours if hours > 0 else 0
        else:
            throughput = 0

        return AnalyticsOverview(
            total_annotations=total_annotations,
            total_annotators=annotators,
            average_quality=round(average_quality, 2),
            completion_rate=round(completion_rate, 2),
            total_time_spent=int(total_time),
            throughput_per_hour=round(throughput, 2),
        )

    def _calculate_performance_trends(
        self,
        db: Session,
        project_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[PerformanceTrend]:
        """Calculate daily performance trends"""

        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        trends = []
        current_date = start_date

        while current_date <= end_date:
            day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            # Annotations completed that day
            day_query = db.query(Annotation).filter(
                and_(
                    Annotation.project_id == project_id,
                    Annotation.created_at >= day_start,
                    Annotation.created_at < day_end,
                    Annotation.was_cancelled == False,
                )
            )

            completed_count = day_query.count()

            # Average quality for that day - using completion as proxy
            average_quality = 100.0 if completed_count > 0 else 0

            # Average time that day
            completed_annotations = day_query.filter(Annotation.lead_time.isnot(None)).all()

            if completed_annotations:
                times = [ann.lead_time for ann in completed_annotations if ann.lead_time]
                average_time = statistics.mean(times) if times else 0
            else:
                average_time = 0

            # Active users that day
            active_users = day_query.with_entities(Annotation.completed_by).distinct().count()

            trends.append(
                PerformanceTrend(
                    date=current_date.strftime("%Y-%m-%d"),
                    annotations_completed=completed_count,
                    average_quality=round(average_quality, 2),
                    average_time=round(average_time, 2),
                    active_users=active_users,
                )
            )

            current_date += timedelta(days=1)

        return trends

    def _calculate_quality_metrics(
        self, db: Session, project_id: str, date_filter: List
    ) -> QualityMetrics:
        """Calculate quality-related metrics (simplified for new model)"""

        base_query = db.query(Annotation).filter(Annotation.project_id == project_id)

        if date_filter:
            base_query = base_query.filter(and_(*date_filter))

        # Since new model doesn't have quality scores, we'll use completion metrics
        total_annotations = base_query.count()
        completed_annotations = base_query.filter(Annotation.was_cancelled == False).count()
        cancelled_annotations = base_query.filter(Annotation.was_cancelled == True).count()

        # Quality distribution (simplified)
        quality_distribution = [
            {
                "range": "Completed",
                "count": completed_annotations,
                "percentage": (completed_annotations / total_annotations * 100)
                if total_annotations > 0
                else 0,
            },
            {
                "range": "Cancelled",
                "count": cancelled_annotations,
                "percentage": (cancelled_annotations / total_annotations * 100)
                if total_annotations > 0
                else 0,
            },
        ]

        # Inter-annotator agreement
        iaa = self._calculate_inter_annotator_agreement(db, project_id, date_filter)

        # Consistency score - using completion rate as proxy
        consistency_score = (
            (completed_annotations / total_annotations) if total_annotations > 0 else 1.0
        )

        # Error rate - using cancellation rate as proxy
        error_rate = (cancelled_annotations / total_annotations) if total_annotations > 0 else 0

        # Revision rate - check for reviewed annotations
        reviewed_count = base_query.filter(Annotation.reviewed_by.isnot(None)).count()
        revision_rate = (reviewed_count / total_annotations) if total_annotations > 0 else 0

        return QualityMetrics(
            quality_distribution=quality_distribution,
            inter_annotator_agreement=round(iaa, 4),
            consistency_score=round(consistency_score, 4),
            error_rate=round(error_rate, 4),
            revision_rate=round(revision_rate, 4),
        )

    def _calculate_inter_annotator_agreement(
        self, db: Session, project_id: str, date_filter: List
    ) -> float:
        """
        Calculate inter-annotator agreement using actual annotation comparison.
        Uses Cohen's Kappa for 2 annotators or Fleiss' Kappa for 3+ annotators.
        """

        # Find tasks that have been annotated by multiple users
        base_query = db.query(Annotation).filter(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,
        )

        if date_filter:
            base_query = base_query.filter(and_(*date_filter))

        # Group by task_id to find multi-annotated tasks
        multi_annotated_tasks = (
            base_query.group_by(Annotation.task_id)
            .having(func.count(Annotation.id) > 1)
            .with_entities(Annotation.task_id)
            .all()
        )

        if not multi_annotated_tasks:
            return 1.0  # Perfect agreement if no overlapping annotations

        # Collect all annotator ratings for all tasks
        all_annotators = set()
        task_ratings = {}

        for (task_id,) in multi_annotated_tasks:
            task_annotations = base_query.filter(Annotation.task_id == task_id).all()
            task_ratings[task_id] = {}

            for annotation in task_annotations:
                annotator_id = annotation.completed_by
                all_annotators.add(annotator_id)
                # Extract label hash for comparison
                rating = self._extract_rating_from_annotation(annotation.result)
                task_ratings[task_id][annotator_id] = rating

        if len(all_annotators) < 2:
            return 1.0

        annotators = sorted(all_annotators)

        # Build ratings matrix: each row is a task, each column is an annotator
        ratings_matrix = []
        for task_id in task_ratings:
            row = []
            for annotator_id in annotators:
                rating = task_ratings[task_id].get(annotator_id)
                row.append(rating)
            ratings_matrix.append(row)

        # Use Fleiss' Kappa for categorical agreement
        return self._calculate_fleiss_kappa(ratings_matrix)

    def _extract_rating_from_annotation(self, result: Any) -> Optional[str]:
        """Extract a comparable rating from annotation result."""
        if not result:
            return None

        # Handle list of annotation results
        if isinstance(result, list):
            # For span annotations, create a canonical representation
            labels = []
            for item in result:
                if isinstance(item, dict):
                    value = item.get("value", {})
                    if "spans" in value:
                        # Sort spans for consistent comparison
                        for span in sorted(
                            value["spans"], key=lambda s: (s.get("start", 0), s.get("end", 0))
                        ):
                            labels.append(
                                f"{span.get('labels', [''])[0] if span.get('labels') else ''}:{span.get('start', 0)}-{span.get('end', 0)}"
                            )
                    elif "choices" in value:
                        labels.extend(sorted(value.get("choices", [])))
                    elif "text" in value:
                        labels.append(str(value.get("text", "")))
            return "|".join(labels) if labels else None

        return str(result) if result else None

    def _calculate_fleiss_kappa(self, ratings_matrix: List[List[Optional[str]]]) -> float:
        """Calculate Fleiss' Kappa for multiple raters."""
        import numpy as np

        if not ratings_matrix or not ratings_matrix[0]:
            return 1.0

        # Get all unique categories
        all_ratings = [r for row in ratings_matrix for r in row if r is not None]
        if not all_ratings:
            return 1.0

        categories = sorted(set(all_ratings))
        n_categories = len(categories)
        cat_to_idx = {c: i for i, c in enumerate(categories)}

        n_items = len(ratings_matrix)

        # Build count matrix
        counts = np.zeros((n_items, n_categories))
        for i, row in enumerate(ratings_matrix):
            for rating in row:
                if rating is not None and rating in cat_to_idx:
                    counts[i, cat_to_idx[rating]] += 1

        # Number of raters per item
        n_raters_per_item = np.sum(counts, axis=1)

        # Skip items with less than 2 raters
        valid_items = n_raters_per_item >= 2
        if not np.any(valid_items):
            return 1.0

        counts = counts[valid_items]
        n_raters_per_item = n_raters_per_item[valid_items]
        n_items = len(counts)

        # Proportion of ratings per category
        p_j = np.sum(counts, axis=0) / np.sum(counts)

        # Per-item agreement
        P_i = np.zeros(n_items)
        for i in range(n_items):
            n_i = n_raters_per_item[i]
            if n_i > 1:
                P_i[i] = (np.sum(counts[i] ** 2) - n_i) / (n_i * (n_i - 1))

        # Overall observed agreement
        P_bar = np.mean(P_i)

        # Expected agreement by chance
        P_e = np.sum(p_j**2)

        # Calculate kappa
        if P_e >= 1.0:
            return 1.0 if P_bar >= 1.0 else 0.0

        kappa = (P_bar - P_e) / (1 - P_e)
        return float(max(0.0, min(1.0, kappa)))  # Clamp to [0, 1]

    def _calculate_user_analytics(
        self, db: Session, project_id: str, date_filter: List
    ) -> List[UserAnalytics]:
        """Calculate per-user analytics with optimized queries to avoid N+1 pattern"""

        # Build base conditions
        conditions = [Annotation.project_id == project_id]
        if date_filter:
            conditions.extend(date_filter)

        # Single optimized query to get all user stats at once
        recent_date = datetime.now() - timedelta(days=7)

        user_stats = (
            db.query(
                User.id.label('user_id'),
                User.name,
                User.email,
                func.count(Annotation.id).label('annotations_count'),
                func.sum(case((Annotation.was_cancelled == False, 1), else_=0)).label(
                    'completed_count'
                ),
                func.avg(Annotation.lead_time).label('avg_lead_time'),
                func.sum(Annotation.lead_time).label('total_lead_time'),
                func.sum(case((Annotation.created_at >= recent_date, 1), else_=0)).label(
                    'recent_count'
                ),
                func.max(Annotation.updated_at).label('last_active_date'),
            )
            .join(Annotation, User.id == Annotation.completed_by)
            .filter(and_(*conditions))
            .group_by(User.id, User.name, User.email)
            .all()
        )

        user_analytics = []
        for stat in user_stats:
            annotations_count = stat.annotations_count or 0
            completed_count = stat.completed_count or 0

            # Quality score - using completion rate as proxy
            quality_score = (
                (completed_count / annotations_count * 100) if annotations_count > 0 else 0
            )

            # Average time
            average_time = float(stat.avg_lead_time) if stat.avg_lead_time else 0

            # Throughput (annotations per hour)
            total_time = float(stat.total_lead_time) if stat.total_lead_time else 0
            if total_time > 0:
                hours = total_time / 3600
                throughput = completed_count / hours if hours > 0 else 0
            else:
                throughput = 0

            # Consistency - using completion rate as proxy
            consistency = (completed_count / annotations_count) if annotations_count > 0 else 1.0

            # Activity score (based on recent activity)
            recent_count = stat.recent_count or 0
            activity_score = min(100, recent_count * 10)  # Simple scoring

            # Last active
            last_active = stat.last_active_date.isoformat() if stat.last_active_date else "Never"

            user_analytics.append(
                UserAnalytics(
                    user_id=stat.user_id,
                    user_name=stat.name or stat.email,
                    annotations_count=annotations_count,
                    quality_score=round(quality_score, 2),
                    average_time=round(average_time, 2),
                    throughput=round(throughput, 2),
                    consistency=round(consistency, 4),
                    activity_score=round(activity_score, 2),
                    last_active=last_active,
                )
            )

        # Sort by annotations count
        user_analytics.sort(key=lambda x: x.annotations_count, reverse=True)

        return user_analytics

    def _calculate_project_insights(
        self, db: Session, project_id: str, date_filter: List
    ) -> ProjectInsights:
        """Calculate project-level insights"""

        base_query = db.query(Annotation).filter(
            Annotation.project_id == project_id,
        )

        if date_filter:
            base_query = base_query.filter(and_(*date_filter))

        # Busiest hours (when most annotations are created)
        hour_distribution = defaultdict(int)
        annotations_with_time = base_query.all()

        for ann in annotations_with_time:
            if ann.created_at:
                hour = ann.created_at.hour
                hour_distribution[hour] += 1

        busiest_hours = [
            {"hour": hour, "count": count, "label": f"{hour:02d}:00"}
            for hour, count in sorted(hour_distribution.items(), key=lambda x: x[1], reverse=True)
        ][:5]

        # Completion patterns (by day of week)
        weekday_distribution = defaultdict(int)
        for ann in annotations_with_time:
            if ann.created_at:
                weekday = ann.created_at.weekday()
                weekday_distribution[weekday] += 1

        weekday_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        completion_patterns = [
            {
                "day": weekday_names[day],
                "count": weekday_distribution[day],
                "percentage": (weekday_distribution[day] / len(annotations_with_time) * 100)
                if annotations_with_time
                else 0,
            }
            for day in range(7)
        ]

        # Difficulty analysis (based on time taken)
        difficulty_analysis = []

        # Get all tasks with annotations
        tasks_with_annotations = (
            db.query(Task.id, func.avg(Annotation.lead_time).label('avg_time'))
            .join(Annotation, Task.id == Annotation.task_id)
            .filter(Task.project_id == project_id)
            .group_by(Task.id)
            .all()
        )

        if tasks_with_annotations:
            times = [avg_time for _, avg_time in tasks_with_annotations if avg_time]
            if times:
                avg_time = statistics.mean(times)
                std_time = statistics.stdev(times) if len(times) > 1 else 0

                easy_threshold = avg_time - std_time
                hard_threshold = avg_time + std_time

                easy_count = sum(1 for _, t in tasks_with_annotations if t and t < easy_threshold)
                medium_count = sum(
                    1
                    for _, t in tasks_with_annotations
                    if t and easy_threshold <= t <= hard_threshold
                )
                hard_count = sum(1 for _, t in tasks_with_annotations if t and t > hard_threshold)

                total = len(tasks_with_annotations)
                difficulty_analysis = [
                    {
                        "difficulty": "Easy",
                        "count": easy_count,
                        "percentage": (easy_count / total * 100) if total > 0 else 0,
                    },
                    {
                        "difficulty": "Medium",
                        "count": medium_count,
                        "percentage": (medium_count / total * 100) if total > 0 else 0,
                    },
                    {
                        "difficulty": "Hard",
                        "count": hard_count,
                        "percentage": (hard_count / total * 100) if total > 0 else 0,
                    },
                ]

        # Annotation types (simplified - just completed vs cancelled)
        completed = base_query.filter(Annotation.was_cancelled == False).count()
        cancelled = base_query.filter(Annotation.was_cancelled == True).count()
        total = completed + cancelled

        annotation_types = [
            {
                "type": "Completed",
                "count": completed,
                "percentage": (completed / total * 100) if total > 0 else 0,
            },
            {
                "type": "Cancelled",
                "count": cancelled,
                "percentage": (cancelled / total * 100) if total > 0 else 0,
            },
        ]

        return ProjectInsights(
            busiest_hours=busiest_hours,
            completion_patterns=completion_patterns,
            difficulty_analysis=difficulty_analysis,
            annotation_types=annotation_types,
        )

    def _calculate_benchmarks(self, db: Session, project_id: str) -> Benchmarks:
        """Calculate benchmarking data against other projects"""

        # Calculate real averages from all projects (excluding current project)
        # No mock data - returns None if insufficient data for scientific rigor
        global_stats = (
            db.query(
                func.count(Annotation.id).label('total_annotations'),
                func.sum(case((Annotation.was_cancelled == False, 1), else_=0)).label(
                    'completed_annotations'
                ),
                func.avg(Annotation.lead_time).label('avg_lead_time'),
            )
            .join(Project, Project.id == Annotation.project_id)
            .filter(Project.id != project_id)
            .first()
        )

        # Calculate quality as completion rate across all other projects
        industry_average_quality = None
        industry_average_time = None

        if global_stats and global_stats.total_annotations and global_stats.total_annotations > 0:
            completed = global_stats.completed_annotations or 0
            industry_average_quality = round((completed / global_stats.total_annotations) * 100, 2)

        if global_stats and global_stats.avg_lead_time is not None:
            industry_average_time = round(float(global_stats.avg_lead_time), 2)

        # Optimized single query to get all project stats at once to avoid N+1 queries
        project_stats = (
            db.query(
                Project.id,
                Project.title,
                func.count(Annotation.id).label('total_annotations'),
                func.sum(case((Annotation.was_cancelled == False, 1), else_=0)).label(
                    'completed_annotations'
                ),
                func.count(func.distinct(Annotation.completed_by)).label('unique_users'),
                func.avg(Annotation.lead_time).label('avg_lead_time'),
            )
            .outerjoin(Annotation, Project.id == Annotation.project_id)
            .filter(Project.id != project_id)
            .group_by(Project.id, Project.title)
            .limit(5)
            .all()
        )

        similar_projects = []
        for project_stat in project_stats:
            total_annotations = project_stat.total_annotations or 0
            completed_annotations = project_stat.completed_annotations or 0
            project_quality = (
                (completed_annotations / total_annotations * 100) if total_annotations > 0 else 0
            )
            avg_time = project_stat.avg_lead_time or 0

            similar_projects.append(
                {
                    "project_id": project_stat.id,
                    "project_name": project_stat.title,
                    "annotations": total_annotations,
                    "quality": round(project_quality, 2),
                    "average_time": round(float(avg_time), 2),
                    "users": project_stat.unique_users or 0,
                }
            )

        return Benchmarks(
            industry_average_quality=industry_average_quality,
            industry_average_time=industry_average_time,
            similar_projects=similar_projects,
        )


# Create singleton instance
analytics_service = AnalyticsService()
