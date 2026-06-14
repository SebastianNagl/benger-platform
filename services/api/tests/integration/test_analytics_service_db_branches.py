"""Real-DB branch-coverage tests for ``services/analytics_service.py``.

The existing analytics suites (``tests/unit/test_analytics_service_*.py``) drive
the service against ``Mock`` query chains. That covers the dataclasses and the
private helpers in isolation, but it cannot exercise the *actual* SQLAlchemy
query bodies — the ``group_by/having`` multi-annotated-task detection, the
distribution percentage math, the ``lead_time`` aggregation, or the
project-not-found guard — because those paths depend on real rows coming back
from a real session.

These tests build genuine ``Project`` / ``Task`` / ``Annotation`` rows in
``test_db`` and call the public + private methods directly, asserting the
returned dataclass / dict values. Every assertion is on real output computed
from real persisted state.

Targets:
- ``get_project_statistics``: full end-to-end happy path (drives every
  ``_calculate_*`` helper) + project-not-found ``ValueError``.
- ``_calculate_overview``: totals, unique-annotator distinct count,
  completion-rate vs task count, ``lead_time`` total + throughput, and the
  empty-project zero-division guards.
- ``_calculate_quality_metrics``: completed/cancelled distribution percentages,
  consistency/error-rate proxies, and the all-empty guard.
- ``_calculate_inter_annotator_agreement``: perfect-agreement (no overlap)
  short-circuit, single-annotator short-circuit, and the real multi-annotator
  Fleiss path with agreeing vs disagreeing ratings.
"""

import uuid
from typing import List, Optional

import pytest
from sqlalchemy.orm import Session

from models import User
from project_models import Annotation, Project, Task
from services.analytics_service import (
    AnalyticsOverview,
    AnalyticsService,
    QualityMetrics,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(test_db: Session, user_id: str) -> Project:
    project = Project(
        id=_uid(),
        title="Analytics DB Project",
        description="real-db analytics coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=user_id,
    )
    test_db.add(project)
    test_db.flush()
    return project


def _make_task(test_db: Session, project_id: str, user_id: str, inner_id: int) -> Task:
    task = Task(
        id=_uid(),
        project_id=project_id,
        inner_id=inner_id,
        data={"text": f"task-{inner_id}"},
        created_by=user_id,
        updated_by=user_id,
    )
    test_db.add(task)
    test_db.flush()
    return task


def _make_annotation(
    test_db: Session,
    *,
    task_id: str,
    project_id: str,
    completed_by: str,
    result,
    was_cancelled: bool = False,
    lead_time: Optional[float] = None,
) -> Annotation:
    ann = Annotation(
        id=_uid(),
        task_id=task_id,
        project_id=project_id,
        completed_by=completed_by,
        result=result,
        was_cancelled=was_cancelled,
        lead_time=lead_time,
    )
    test_db.add(ann)
    return ann


# ---------------------------------------------------------------------------
# get_project_statistics — end-to-end + guard
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetProjectStatistics:
    def test_project_not_found_raises_value_error(self, test_db: Session):
        svc = AnalyticsService()
        with pytest.raises(ValueError):
            svc.get_project_statistics(db=test_db, project_id="does-not-exist")

    def test_full_statistics_happy_path(self, test_db: Session, test_users: List[User]):
        """A populated project returns a fully-formed analytics dict driving
        every ``_calculate_*`` helper."""
        project = _make_project(test_db, test_users[0].id)
        t1 = _make_task(test_db, project.id, test_users[0].id, 1)
        t2 = _make_task(test_db, project.id, test_users[0].id, 2)
        _make_annotation(
            test_db, task_id=t1.id, project_id=project.id,
            completed_by=test_users[1].id, result=[{"value": {"text": "ok"}}],
            lead_time=120.0,
        )
        _make_annotation(
            test_db, task_id=t2.id, project_id=project.id,
            completed_by=test_users[2].id, result=[{"value": {"text": "no"}}],
            was_cancelled=True, lead_time=60.0,
        )
        test_db.commit()

        svc = AnalyticsService()
        result = svc.get_project_statistics(db=test_db, project_id=project.id)

        assert result["project_id"] == project.id
        assert result["project_name"] == "Analytics DB Project"
        assert result["overview"]["total_annotations"] == 2
        # Two distinct annotators.
        assert result["overview"]["total_annotators"] == 2
        # Top-level structure present.
        assert "quality_metrics" in result
        assert "user_analytics" in result
        assert "project_insights" in result
        assert "benchmarks" in result
        assert "generated_at" in result


# ---------------------------------------------------------------------------
# _calculate_overview
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCalculateOverview:
    def test_empty_project_all_zero(self, test_db: Session, test_users: List[User]):
        project = _make_project(test_db, test_users[0].id)
        test_db.commit()

        svc = AnalyticsService()
        overview = svc._calculate_overview(test_db, project.id, [])

        assert isinstance(overview, AnalyticsOverview)
        assert overview.total_annotations == 0
        assert overview.total_annotators == 0
        # Zero-division guards -> 0.
        assert overview.average_quality == 0
        assert overview.completion_rate == 0
        assert overview.total_time_spent == 0
        assert overview.throughput_per_hour == 0

    def test_counts_and_time_and_throughput(self, test_db: Session, test_users: List[User]):
        project = _make_project(test_db, test_users[0].id)
        t1 = _make_task(test_db, project.id, test_users[0].id, 1)
        t2 = _make_task(test_db, project.id, test_users[0].id, 2)
        # 2 completed (one each from two annotators), total lead_time 3600s = 1h.
        _make_annotation(
            test_db, task_id=t1.id, project_id=project.id,
            completed_by=test_users[1].id, result=[{"value": {"text": "a"}}],
            lead_time=1800.0,
        )
        _make_annotation(
            test_db, task_id=t2.id, project_id=project.id,
            completed_by=test_users[2].id, result=[{"value": {"text": "b"}}],
            lead_time=1800.0,
        )
        test_db.commit()

        svc = AnalyticsService()
        overview = svc._calculate_overview(test_db, project.id, [])

        assert overview.total_annotations == 2
        assert overview.total_annotators == 2
        # 2 completed / 2 total tasks = 100%.
        assert overview.completion_rate == 100.0
        # average_quality proxy = completed/total annotations * 100.
        assert overview.average_quality == 100.0
        # 1800 + 1800 = 3600s.
        assert overview.total_time_spent == 3600
        # 2 completed over 1 hour = 2.0 / hour.
        assert overview.throughput_per_hour == 2.0

    def test_cancelled_excluded_from_completed(self, test_db: Session, test_users: List[User]):
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(test_db, project.id, test_users[0].id, 1)
        _make_annotation(
            test_db, task_id=task.id, project_id=project.id,
            completed_by=test_users[1].id, result=[{"value": {"text": "x"}}],
            was_cancelled=True, lead_time=None,
        )
        test_db.commit()

        svc = AnalyticsService()
        overview = svc._calculate_overview(test_db, project.id, [])

        assert overview.total_annotations == 1
        # The only annotation is cancelled -> completion rate 0.
        assert overview.completion_rate == 0
        # No lead_time rows -> total time and throughput zero.
        assert overview.total_time_spent == 0
        assert overview.throughput_per_hour == 0


# ---------------------------------------------------------------------------
# _calculate_quality_metrics
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCalculateQualityMetrics:
    def test_empty_project_guards(self, test_db: Session, test_users: List[User]):
        project = _make_project(test_db, test_users[0].id)
        test_db.commit()

        svc = AnalyticsService()
        qm = svc._calculate_quality_metrics(test_db, project.id, [])

        assert isinstance(qm, QualityMetrics)
        # No annotations -> percentages default to 0, consistency proxy 1.0.
        completed = next(d for d in qm.quality_distribution if d["range"] == "Completed")
        cancelled = next(d for d in qm.quality_distribution if d["range"] == "Cancelled")
        assert completed["count"] == 0
        assert completed["percentage"] == 0
        assert cancelled["count"] == 0
        assert qm.consistency_score == 1.0
        assert qm.error_rate == 0
        assert qm.revision_rate == 0

    def test_distribution_percentages(self, test_db: Session, test_users: List[User]):
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(test_db, project.id, test_users[0].id, 1)
        # 3 completed, 1 cancelled -> 75% / 25%.
        for _ in range(3):
            _make_annotation(
                test_db, task_id=task.id, project_id=project.id,
                completed_by=test_users[1].id, result=[{"value": {"text": "ok"}}],
            )
        _make_annotation(
            test_db, task_id=task.id, project_id=project.id,
            completed_by=test_users[2].id, result=[{"value": {"text": "bad"}}],
            was_cancelled=True,
        )
        test_db.commit()

        svc = AnalyticsService()
        qm = svc._calculate_quality_metrics(test_db, project.id, [])

        completed = next(d for d in qm.quality_distribution if d["range"] == "Completed")
        cancelled = next(d for d in qm.quality_distribution if d["range"] == "Cancelled")
        assert completed["count"] == 3
        assert completed["percentage"] == pytest.approx(75.0)
        assert cancelled["count"] == 1
        assert cancelled["percentage"] == pytest.approx(25.0)
        # consistency = completed/total = 0.75, error = cancelled/total = 0.25.
        assert qm.consistency_score == pytest.approx(0.75)
        assert qm.error_rate == pytest.approx(0.25)
        # IAA is rounded to 4 places and within [0, 1].
        assert 0.0 <= qm.inter_annotator_agreement <= 1.0


# ---------------------------------------------------------------------------
# _calculate_inter_annotator_agreement
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestInterAnnotatorAgreement:
    def test_no_overlap_perfect_agreement(self, test_db: Session, test_users: List[User]):
        """Each task annotated by exactly one user -> no multi-annotated tasks
        -> short-circuit to 1.0."""
        project = _make_project(test_db, test_users[0].id)
        t1 = _make_task(test_db, project.id, test_users[0].id, 1)
        t2 = _make_task(test_db, project.id, test_users[0].id, 2)
        _make_annotation(
            test_db, task_id=t1.id, project_id=project.id,
            completed_by=test_users[1].id, result=[{"value": {"text": "a"}}],
        )
        _make_annotation(
            test_db, task_id=t2.id, project_id=project.id,
            completed_by=test_users[2].id, result=[{"value": {"text": "b"}}],
        )
        test_db.commit()

        svc = AnalyticsService()
        assert svc._calculate_inter_annotator_agreement(test_db, project.id, []) == 1.0

    def test_single_annotator_short_circuit(self, test_db: Session, test_users: List[User]):
        """One task annotated twice by the SAME user -> <2 distinct annotators
        -> 1.0."""
        project = _make_project(test_db, test_users[0].id)
        task = _make_task(test_db, project.id, test_users[0].id, 1)
        for _ in range(2):
            _make_annotation(
                test_db, task_id=task.id, project_id=project.id,
                completed_by=test_users[1].id, result=[{"value": {"text": "same"}}],
            )
        test_db.commit()

        svc = AnalyticsService()
        assert svc._calculate_inter_annotator_agreement(test_db, project.id, []) == 1.0

    def test_two_annotators_agree(self, test_db: Session, test_users: List[User]):
        """Two annotators give matching choices on overlapping tasks -> the real
        Fleiss path runs and yields perfect (clamped) agreement 1.0."""
        project = _make_project(test_db, test_users[0].id)
        t1 = _make_task(test_db, project.id, test_users[0].id, 1)
        t2 = _make_task(test_db, project.id, test_users[0].id, 2)
        for task, choice in ((t1, "yes"), (t2, "no")):
            for annotator in (test_users[1], test_users[2]):
                _make_annotation(
                    test_db, task_id=task.id, project_id=project.id,
                    completed_by=annotator.id,
                    result=[{"value": {"choices": [choice]}}],
                )
        test_db.commit()

        svc = AnalyticsService()
        iaa = svc._calculate_inter_annotator_agreement(test_db, project.id, [])
        assert iaa == pytest.approx(1.0)

    def test_two_annotators_disagree_in_range(self, test_db: Session, test_users: List[User]):
        """Annotators disagree on overlapping tasks -> Fleiss runs and returns a
        value clamped into [0, 1]."""
        project = _make_project(test_db, test_users[0].id)
        t1 = _make_task(test_db, project.id, test_users[0].id, 1)
        t2 = _make_task(test_db, project.id, test_users[0].id, 2)
        # u1 says yes/yes, u2 says no/no on the two shared tasks.
        for task in (t1, t2):
            _make_annotation(
                test_db, task_id=task.id, project_id=project.id,
                completed_by=test_users[1].id,
                result=[{"value": {"choices": ["yes"]}}],
            )
            _make_annotation(
                test_db, task_id=task.id, project_id=project.id,
                completed_by=test_users[2].id,
                result=[{"value": {"choices": ["no"]}}],
            )
        test_db.commit()

        svc = AnalyticsService()
        iaa = svc._calculate_inter_annotator_agreement(test_db, project.id, [])
        assert 0.0 <= iaa <= 1.0
