"""Tests for the precomputed aggregate-summary write + read paths.

The Celery task `recompute_aggregates` populates two summary tables that
back /api/leaderboards/llm-models and /api/dashboard/stats. These tests
seed a small fixture, run the recompute, and verify both the persisted
rows and the read helpers return the correct shape.

Migration 051 introduced the tables; aggregate_summaries.py owns the SQL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMLeaderboardScore,
    LLMModel,
    Organization,
    ProjectSummary,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, Task
from aggregate_summaries import (
    live_aggregate_leaderboard,
    read_dashboard_sum,
    read_llm_leaderboard,
    read_llm_model_aggregate,
    read_project_summary,
    recompute_llm_leaderboard_scores,
    recompute_project_summaries,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded(test_db: Session):
    """One public project, two tasks, two model generations, one EvaluationRun
    with two TaskEvaluation rows scoring two distinct metrics. Returns the
    objects the tests need to reference by id.
    """
    user = User(
        id=str(uuid.uuid4()),
        username=f"agg_test_{uuid.uuid4().hex[:6]}",
        email=f"agg_{uuid.uuid4().hex[:6]}@example.com",
        name="Aggregate Test User",
        hashed_password="x",
        is_active=True,
        is_superadmin=False,
        email_verified=True,
    )
    test_db.add(user)

    project = Project(
        id=str(uuid.uuid4()),
        title="Aggregate test project",
        description="for test_aggregate_summaries",
        created_by=user.id,
        label_config="<View/>",
        is_public=True,
        # ck_projects_public_role_required_when_public — must be set
        # alongside is_public=True.
        public_role="ANNOTATOR",
    )
    test_db.add(project)
    test_db.flush()

    tasks = []
    for i in range(2):
        t = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            data={"text": f"task {i}"},
            inner_id=i + 1,
            is_labeled=(i == 0),  # one task is "labeled"
        )
        test_db.add(t)
        tasks.append(t)

    # One annotation on the first task so annotations_count > 0.
    ann = Annotation(
        id=str(uuid.uuid4()),
        task_id=tasks[0].id,
        project_id=project.id,
        completed_by=user.id,
        result=[{"value": "x"}],  # non-empty
        was_cancelled=False,
    )
    test_db.add(ann)

    # Two generations with two distinct model IDs. Each Generation gets
    # its own parent ResponseGeneration so the
    # `uq_generations_parent_run_index` (generation_id, run_index) constraint
    # holds — two children of the same parent at run_index=0 would collide.
    rg_a = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=tasks[0].id,
        model_id="gpt-4o",
        status="completed",
        created_by=user.id,
    )
    rg_b = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=tasks[1].id,
        model_id="claude-sonnet-4-6",
        status="completed",
        created_by=user.id,
    )
    test_db.add_all([rg_a, rg_b])
    test_db.flush()

    gen_a = Generation(
        id=str(uuid.uuid4()),
        generation_id=rg_a.id,
        task_id=tasks[0].id,
        model_id="gpt-4o",
        run_index=0,
        response_content="resp-a",
        case_data=json.dumps({}),
        status="completed",
        parse_status="success",
    )
    gen_b = Generation(
        id=str(uuid.uuid4()),
        generation_id=rg_b.id,
        task_id=tasks[1].id,
        model_id="claude-sonnet-4-6",
        run_index=0,
        response_content="resp-b",
        case_data=json.dumps({}),
        status="completed",
        parse_status="success",
    )
    test_db.add_all([gen_a, gen_b])
    test_db.flush()

    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["accuracy"],
        metrics={"accuracy": 0.83},
        eval_metadata={},
        status="completed",
        samples_evaluated=2,
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    test_db.add(er)
    test_db.flush()

    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    test_db.add(jr)
    test_db.flush()

    # TaskEvaluation rows: one per generation, with two real metrics + one
    # noise metric (`_details`) that must NOT show up in the precomputed
    # aggregates.
    te_a = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=tasks[0].id,
        generation_id=gen_a.id,
        field_name="accuracy:pred:gt",
        answer_type="text",
        ground_truth="x",
        prediction="x",
        metrics={"accuracy": 0.9, "accuracy_details": {"raw": "x"}},
        passed=True,
    )
    te_b = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=tasks[1].id,
        generation_id=gen_b.id,
        field_name="accuracy:pred:gt",
        answer_type="text",
        ground_truth="y",
        prediction="z",
        metrics={"accuracy": 0.6, "accuracy_details": {"raw": "y"}},
        passed=False,
    )
    test_db.add_all([te_a, te_b])
    test_db.commit()

    return {
        "user": user,
        "project": project,
        "tasks": tasks,
        "evaluation_run": er,
        "task_evaluations": [te_a, te_b],
        "generations": [gen_a, gen_b],
    }


# ---------------------------------------------------------------------------
# project_summaries
# ---------------------------------------------------------------------------

class TestProjectSummaries:
    def test_recompute_writes_row_per_period(self, test_db, seeded):
        upserts = recompute_project_summaries(test_db)
        assert upserts >= 3  # at least the 3 periods for our one project

        row = read_project_summary(test_db, seeded["project"].id, period="overall")
        assert row is not None
        assert row.total_tasks == 2
        assert row.labeled_tasks == 1
        assert row.annotations_count == 1
        # Both generations parsed successfully → counted.
        assert row.generations_count == 2
        # `accuracy_details` is noise — only one real (subject, metric) pair
        # per evaluated generation: 2 evaluations × 1 real metric = 2.
        assert row.evaluation_pairs_count == 2
        # available_models is the JSONB list of distinct generation model ids.
        assert set(row.available_models) == {"gpt-4o", "claude-sonnet-4-6"}

    def test_recompute_is_idempotent(self, test_db, seeded):
        upserts_a = recompute_project_summaries(test_db)
        upserts_b = recompute_project_summaries(test_db)
        # Same number of (project, period) tuples → same number of upserts.
        assert upserts_a == upserts_b
        # And the row count stays bounded.
        count = test_db.query(ProjectSummary).filter(
            ProjectSummary.project_id == seeded["project"].id
        ).count()
        assert count == 3  # exactly one row per period

    def test_read_dashboard_sum_aggregates_across_projects(self, test_db, seeded):
        recompute_project_summaries(test_db)
        # Single-project filter list
        sums = read_dashboard_sum(
            test_db, accessible_project_ids=[seeded["project"].id], period="overall"
        )
        assert sums["project_count"] == 1
        assert sums["total_tasks"] == 2
        assert sums["labeled_tasks"] == 1
        assert sums["annotations_count"] == 1
        assert sums["generations_count"] == 2
        assert sums["evaluation_pairs_count"] == 2

    def test_read_dashboard_sum_returns_zeros_for_empty_scope(self, test_db):
        # No projects in scope at all
        sums = read_dashboard_sum(test_db, accessible_project_ids=[], period="overall")
        assert sums["project_count"] == 0
        assert sums["total_tasks"] == 0
        assert sums["evaluation_pairs_count"] == 0


# ---------------------------------------------------------------------------
# llm_leaderboard_scores
# ---------------------------------------------------------------------------

class TestLLMLeaderboardScores:
    def test_recompute_writes_rows_per_model_metric(self, test_db, seeded):
        upserts = recompute_llm_leaderboard_scores(test_db)
        assert upserts > 0

        # One specific-metric row per (model, accuracy) for each scope/period
        # plus an `average` row per model. With 'all' + 'public' scopes ×
        # 3 periods × 1 model with eval data (gpt-4o) × 1 metric + 1 average
        # row = at least 12 upserts.
        # We assert structure rather than exact count to stay robust to schema
        # tweaks.
        rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.model_id == "gpt-4o",
            LLMLeaderboardScore.project_scope_key == "public",
            LLMLeaderboardScore.period == "overall",
        ).all()
        metrics_present = {r.metric for r in rows}
        assert "accuracy" in metrics_present
        assert "average" in metrics_present
        # Noise key must NOT make it into the precomputed rows.
        assert "accuracy_details" not in metrics_present

    def test_score_is_mean_of_raw_metric_values(self, test_db, seeded):
        recompute_llm_leaderboard_scores(test_db)
        row = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.model_id == "gpt-4o",
            LLMLeaderboardScore.project_scope_key == "public",
            LLMLeaderboardScore.period == "overall",
            LLMLeaderboardScore.metric == "accuracy",
        ).one()
        # Two TaskEvaluation rows for accuracy: 0.9 and 0.6 → mean 0.75
        # ...but only gen_a maps to gpt-4o; gen_b is claude-sonnet-4-6. So
        # gpt-4o's "accuracy" row reflects gen_a only: mean = 0.9.
        assert row.score == pytest.approx(0.9, abs=1e-3)
        # samples_evaluated reflects the COUNT of TaskEvaluation rows for
        # this model — 1 (gen_a only).
        assert row.samples_evaluated == 1
        assert row.generation_count == 1

    def test_read_llm_leaderboard_returns_pivoted_entries(self, test_db, seeded):
        recompute_llm_leaderboard_scores(test_db)
        # gpt-4o is the only model with evals; sort by 'average' (default).
        entries, total_models, available_metrics, computed_at = read_llm_leaderboard(
            test_db,
            project_scope_key="public",
            period="overall",
            sort_metric="average",
            limit=10,
            offset=0,
        )
        assert total_models >= 1
        # gpt-4o should appear (with eval data) and (potentially) claude too.
        model_ids = [e["model_id"] for e in entries]
        assert "gpt-4o" in model_ids
        # 'metrics' dict on each entry should NOT include the 'average' synthetic key.
        gpt_entry = next(e for e in entries if e["model_id"] == "gpt-4o")
        assert "accuracy" in gpt_entry["metrics"]
        assert computed_at is not None

    def test_live_fallback_for_unusual_filter(self, test_db, seeded):
        # No precompute yet; live aggregation should still return data.
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded["project"].id],
            period="overall",
            evaluation_types=None,
        )
        # At least one row per (model, metric) combination present.
        model_metric_pairs = {(r["model_id"], r["metric"]) for r in rows}
        assert ("gpt-4o", "accuracy") in model_metric_pairs
        # PR #116: the synthetic cross-metric 'average' row is no longer
        # emitted — pooling values from incompatible scales (0–1, 0–18,
        # 0–100) into one mean produced dimensionally meaningless numbers
        # that rendered as "1400%". The metric picker no longer offers it.
        assert not any(r["metric"] == "average" for r in rows)


# ---------------------------------------------------------------------------
# Period filter
# ---------------------------------------------------------------------------

class TestPeriodFilter:
    def test_weekly_period_excludes_old_evaluations(self, test_db, seeded):
        # Backdate the EvaluationRun outside the weekly window
        er = seeded["evaluation_run"]
        er.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        er.completed_at = er.created_at
        test_db.commit()

        recompute_llm_leaderboard_scores(test_db)

        weekly_rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.model_id == "gpt-4o",
            LLMLeaderboardScore.period == "weekly",
        ).all()
        # No rows in the weekly window for this model/metric — the run is
        # too old.
        assert weekly_rows == []

        overall_rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.model_id == "gpt-4o",
            LLMLeaderboardScore.period == "overall",
        ).all()
        # 'overall' has no cutoff → row still present.
        assert overall_rows != []


# ---------------------------------------------------------------------------
# Per-model details
# ---------------------------------------------------------------------------

class TestReadLLMModelAggregate:
    def test_returns_per_metric_dict_for_known_model(self, test_db, seeded):
        recompute_llm_leaderboard_scores(test_db)
        agg = read_llm_model_aggregate(
            test_db, model_id="gpt-4o", project_scope_key="public", period="overall"
        )
        assert "accuracy" in agg["metrics"]
        assert agg["metrics"]["accuracy"]["mean"] == pytest.approx(0.9, abs=1e-3)
        assert agg["evaluation_count"] >= 1
        assert agg["samples_evaluated"] >= 1
        assert agg["computed_at"] is not None

    def test_returns_empty_for_unknown_model(self, test_db, seeded):
        recompute_llm_leaderboard_scores(test_db)
        agg = read_llm_model_aggregate(
            test_db,
            model_id="does-not-exist",
            project_scope_key="public",
            period="overall",
        )
        assert agg["metrics"] == {}
        assert agg["evaluation_count"] == 0


# ---------------------------------------------------------------------------
# Falllösung grade-points lift
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_falloesung(test_db: Session):
    """Two task_evaluations carrying the canonical Falllösung metric shape:
    `metrics.llm_judge_falloesung = {value, details: {raw_score, grade_points}}`.

    Grade points live INSIDE `details`, not as a sibling top-level key. The
    aggregator must lift them out via the dedicated UNION ALL branch so the
    leaderboard's default column (`llm_judge_falloesung_grade_points`) has
    rows to render.
    """
    user = User(
        id=str(uuid.uuid4()),
        username=f"fal_{uuid.uuid4().hex[:6]}",
        email=f"fal_{uuid.uuid4().hex[:6]}@example.com",
        name="Falloesung Test User",
        hashed_password="x",
        is_active=True,
        is_superadmin=False,
        email_verified=True,
    )
    test_db.add(user)

    project = Project(
        id=str(uuid.uuid4()),
        title="Falloesung lift test",
        description="for test_aggregate_summaries",
        created_by=user.id,
        label_config="<View/>",
        is_public=True,
        public_role="ANNOTATOR",
    )
    test_db.add(project)
    test_db.flush()

    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "fal task"},
        inner_id=1,
        is_labeled=True,
    )
    test_db.add(task)
    test_db.flush()

    rg = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        model_id="gpt-4o",
        status="completed",
        created_by=user.id,
    )
    test_db.add(rg)
    test_db.flush()

    gen_high = Generation(
        id=str(uuid.uuid4()),
        generation_id=rg.id,
        task_id=task.id,
        model_id="gpt-4o",
        run_index=0,
        response_content="answer A",
        case_data=json.dumps({}),
        status="completed",
        parse_status="success",
    )
    gen_low = Generation(
        id=str(uuid.uuid4()),
        generation_id=rg.id,
        task_id=task.id,
        model_id="gpt-4o",
        run_index=1,
        response_content="answer B",
        case_data=json.dumps({}),
        status="completed",
        parse_status="success",
    )
    test_db.add_all([gen_high, gen_low])
    test_db.flush()

    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["llm_judge_falloesung"],
        metrics={},
        eval_metadata={},
        status="completed",
        samples_evaluated=2,
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    test_db.add(er)
    test_db.flush()

    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    test_db.add(jr)
    test_db.flush()

    # Raw_score 80 → grade_points 14 (per FALLOESUNG_GRADE_TABLE).
    # Raw_score 40 → grade_points 4.
    # Mean grade_points = 9.0.
    te_high = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=task.id,
        generation_id=gen_high.id,
        field_name="llm_judge_falloesung",
        answer_type="text",
        ground_truth=None,
        prediction=None,
        metrics={
            "llm_judge_falloesung": {
                "value": 0.8,
                "method": "llm_judge_falloesung",
                "details": {
                    "raw_score": 80.0,
                    "grade_points": 14,
                    "passed": True,
                },
                "error": None,
            }
        },
        passed=True,
    )
    te_low = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=task.id,
        generation_id=gen_low.id,
        field_name="llm_judge_falloesung",
        answer_type="text",
        ground_truth=None,
        prediction=None,
        metrics={
            "llm_judge_falloesung": {
                "value": 0.4,
                "method": "llm_judge_falloesung",
                "details": {
                    "raw_score": 40.0,
                    "grade_points": 4,
                    "passed": False,
                },
                "error": None,
            }
        },
        passed=False,
    )
    # A third row missing grade_points — must NOT emit the synthetic metric.
    te_missing = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=task.id,
        generation_id=gen_high.id,
        field_name="llm_judge_falloesung",
        answer_type="text",
        ground_truth=None,
        prediction=None,
        metrics={
            "llm_judge_falloesung": {
                "value": None,
                "details": {"error": "parse failed"},
                "error": "parse failed",
            }
        },
        passed=False,
    )
    test_db.add_all([te_high, te_low, te_missing])
    test_db.commit()

    return {"project": project, "evaluation_run": er}


class TestFalloesungGradePointsLift:
    def test_synthetic_metric_emitted_per_row(self, test_db, seeded_falloesung):
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded_falloesung["project"].id],
            period="overall",
            evaluation_types=None,
        )
        metric_keys = {(r["model_id"], r["metric"]) for r in rows}
        assert ("gpt-4o", "llm_judge_falloesung") in metric_keys
        assert ("gpt-4o", "llm_judge_falloesung_grade_points") in metric_keys

    def test_synthetic_metric_score_is_mean_of_per_row_grade_points(
        self, test_db, seeded_falloesung
    ):
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded_falloesung["project"].id],
            period="overall",
            evaluation_types=None,
        )
        gp_row = next(
            r for r in rows
            if r["model_id"] == "gpt-4o"
            and r["metric"] == "llm_judge_falloesung_grade_points"
        )
        # Mean of grade_points 14 and 4 (the parse-failed row contributes nothing).
        assert gp_row["score"] == pytest.approx(9.0, abs=1e-3)

    def test_precomputed_path_includes_grade_points(self, test_db, seeded_falloesung):
        recompute_llm_leaderboard_scores(test_db)
        gp_rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.model_id == "gpt-4o",
            LLMLeaderboardScore.metric == "llm_judge_falloesung_grade_points",
        ).all()
        # At least one row per (scope, period) combo that the recompute writes.
        assert gp_rows
        # The grade_points scale is 0..18, so the mean is well above 1.
        assert all(r.score is not None and r.score > 1 for r in gp_rows)


# ---------------------------------------------------------------------------
# Sum aggregation + per-row evaluation_types filter (PR #116)
# ---------------------------------------------------------------------------

class TestSumAggregation:
    def test_sum_returns_total_not_mean(self, test_db, seeded_falloesung):
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded_falloesung["project"].id],
            period="overall",
            evaluation_types=None,
            aggregation="sum",
        )
        gp_row = next(
            r for r in rows
            if r["model_id"] == "gpt-4o"
            and r["metric"] == "llm_judge_falloesung_grade_points"
        )
        # Seed has two non-error grade_points values: 14 + 4 = 18 total.
        assert gp_row["score"] == pytest.approx(18.0, abs=1e-3)
        # CI doesn't apply to a sum; the aggregator clears the bounds so
        # the frontend can hide the CI for the row.
        assert gp_row["ci_lower"] is None
        assert gp_row["ci_upper"] is None

    def test_average_default_unchanged(self, test_db, seeded_falloesung):
        # Sanity: not passing `aggregation` defaults to 'average' and
        # produces the same mean as the existing test fixture asserts.
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded_falloesung["project"].id],
            period="overall",
            evaluation_types=None,
        )
        gp_row = next(
            r for r in rows
            if r["model_id"] == "gpt-4o"
            and r["metric"] == "llm_judge_falloesung_grade_points"
        )
        assert gp_row["score"] == pytest.approx(9.0, abs=1e-3)
        # CI is populated under mean aggregation.
        assert gp_row["ci_lower"] is not None
        assert gp_row["ci_upper"] is not None


class TestEvaluationTypesPerRowFilter:
    def test_eval_types_filters_metric_keys_per_row(self, test_db, seeded):
        # The 'seeded' fixture writes both 'accuracy' and 'accuracy_details'
        # (noise, already filtered) into each TaskEvaluation's metrics dict.
        # Asking for evaluation_types=['accuracy'] should yield rows whose
        # metric key is exactly 'accuracy', not some other metric from the
        # same run that happens to be present in the JSON.
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded["project"].id],
            period="overall",
            evaluation_types=["accuracy"],
        )
        metric_keys = {r["metric"] for r in rows}
        assert metric_keys == {"accuracy"}, (
            f"expected only 'accuracy' rows, got {metric_keys}"
        )

    def test_eval_types_with_unknown_returns_no_rows(self, test_db, seeded):
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded["project"].id],
            period="overall",
            evaluation_types=["this_metric_does_not_exist"],
        )
        # The run-level pre-filter already excludes runs that didn't declare
        # this type, so live aggregation returns nothing. The per-row filter
        # adds defence in depth for runs whose declaration drifted from
        # actual produced metrics.
        assert rows == []

    def test_eval_types_none_returns_all_metric_keys(self, test_db, seeded):
        # Without an eval_types filter the aggregator emits every metric
        # key produced by the runs (the old behaviour).
        rows = live_aggregate_leaderboard(
            test_db,
            project_ids=[seeded["project"].id],
            period="overall",
            evaluation_types=None,
        )
        metric_keys = {r["metric"] for r in rows}
        # At minimum 'accuracy' must be in there; the noise key
        # 'accuracy_details' must NOT be (it's filtered by metric_filters).
        assert "accuracy" in metric_keys
        assert "accuracy_details" not in metric_keys


# ---------------------------------------------------------------------------
# Read-path threshold filter
# ---------------------------------------------------------------------------

class TestReadLLMLeaderboardThreshold:
    def test_min_generation_count_drops_low_sample_models(self, test_db, seeded):
        # The 'seeded' fixture wires gpt-4o with one task_evaluation
        # (samples_evaluated=1, generation_count=1). With a threshold of
        # 50 the model must drop out entirely.
        recompute_llm_leaderboard_scores(test_db)
        entries, total, _, _ = read_llm_leaderboard(
            test_db,
            project_scope_key="public",
            period="overall",
            sort_metric="accuracy",
            limit=10,
            offset=0,
            min_generation_count=50,
        )
        assert total == 0
        assert entries == []

    def test_min_threshold_zero_is_no_op(self, test_db, seeded):
        # Sanity: threshold=0 matches the pre-PR behaviour (every model
        # surfaces). Guards against accidentally filtering on 0.
        recompute_llm_leaderboard_scores(test_db)
        _, total_no_filter, _, _ = read_llm_leaderboard(
            test_db,
            project_scope_key="public",
            period="overall",
            sort_metric="accuracy",
            limit=10,
            offset=0,
        )
        _, total_zero, _, _ = read_llm_leaderboard(
            test_db,
            project_scope_key="public",
            period="overall",
            sort_metric="accuracy",
            limit=10,
            offset=0,
            min_generation_count=0,
            min_samples_evaluated=0,
        )
        assert total_no_filter == total_zero


# ---------------------------------------------------------------------------
# TUM precomputed scope
# ---------------------------------------------------------------------------

class TestTumScope:
    def test_recompute_emits_tum_scope_rows_when_project_assigned(
        self, test_db, seeded
    ):
        # Assign the seeded public project to the TUM allowlist org so the
        # 'tum' scope picks it up. Uses the actual allowlist constant so
        # the test fails loudly if the org id changes.
        from aggregate_summaries import _TUM_SCOPE_ORG_IDS
        from project_models import ProjectOrganization

        tum_org_id = _TUM_SCOPE_ORG_IDS[0]
        # Seed the org if a fresh fixture is missing it.
        if not test_db.get(Organization, tum_org_id):
            test_db.add(
                Organization(
                    id=tum_org_id,
                    name="TUM",
                    display_name="TUM",
                    slug="tum",
                    is_active=True,
                )
            )
        test_db.add(
            ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=seeded["project"].id,
                organization_id=tum_org_id,
                assigned_by=seeded["user"].id,
            )
        )
        test_db.commit()

        recompute_llm_leaderboard_scores(test_db)
        tum_rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.project_scope_key == "tum",
        ).all()
        assert tum_rows, "scope='tum' rows must be emitted for TUM-assigned projects"
        # And the same model that surfaces under 'public' (seeded) shows
        # up under 'tum' too — the scope just narrows the project set.
        assert any(r.model_id == "gpt-4o" for r in tum_rows)

    def test_non_tum_project_not_emitted_under_tum_scope(self, test_db, seeded):
        # Without a project_organizations row pointing at TUM, the seeded
        # project must NOT contribute to the 'tum' scope. Guards against
        # a SQL bug where the JOIN degenerates into a cross product.
        recompute_llm_leaderboard_scores(test_db)
        tum_rows = test_db.query(LLMLeaderboardScore).filter(
            LLMLeaderboardScore.project_scope_key == "tum",
        ).all()
        assert tum_rows == []
