"""Real-DB kill tests for the LEADERBOARD aggregation math + ranking order.

The pure (no-DB) helpers of `shared/aggregate_summaries.py` are pinned in
`tests/test_aggregate_summaries_kills.py`. This file pins the parts that are
only reachable against a real Postgres because the per-bucket mean/sum
rollup runs inside a streaming SQL query and the leaderboard tie-break is a
SQL `ORDER BY`:

  * `_aggregate_leaderboard_rows` — per-(model, metric) mean, sum, and the
    `round(..., 4)` the worker WRITES into `llm_leaderboard_scores.score`.
  * `read_llm_leaderboard`        — the published rank order: non-null scores
    first, higher score first (DESC), ties broken by model_id ASC.

A flipped operator, sum/mean swap, wrong rounding precision, or a flipped
sort direction here mis-ranks results users cite — so each assertion is a
hand-computed exact value, not a smoke check.

Uses the workers integration harness (`db_conn` + `make_*` factories from
`tests/integration/conftest.py`; explicit-cleanup Design B). Skipped when no
DATABASE_URI/DATABASE_URL is set (the conftest `_build_engine` skips).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Local seeding helper — one completed EvaluationRun whose TaskEvaluation rows
# carry the given per-(model, metric) numeric values. There is no shared
# TaskEvaluation factory in the integration conftest, so build the rows here.
# ---------------------------------------------------------------------------
def _seed_run_with_metrics(
    db, make_project, make_user, make_task, make_generation, model_metric_values
):
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

    user = make_user()
    project = make_project(created_by=user.id, label_config="<View/>")
    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="agg-kill-run",
        evaluation_type_ids=[],
        metrics={},
        eval_metadata={},
        status="completed",
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.commit()

    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(jr)
    db.commit()

    for idx, (model_id, metrics) in enumerate(model_metric_values):
        task = make_task(project.id, {"text": f"t{idx}"})
        _rg, gen = make_generation(
            project_id=project.id,
            task_id=task.id,
            model_id=model_id,
            created_by=user.id,
            response_content=f"resp{idx}",
            run_index=0,
        )
        te = TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=er.id,
            judge_run_id=jr.id,
            task_id=task.id,
            generation_id=gen.id,
            field_name="agg:pred:gt",
            answer_type="text",
            ground_truth="x",
            prediction="x",
            metrics=metrics,
            passed=True,
        )
        db.add(te)
    db.commit()
    return er.id


class TestAggregateRowsMathDB:
    """Pin the mean / sum / round-to-4 dict the worker WRITES per bucket."""

    def test_mean_aggregation_exact_and_rounded(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        # gpt scores 0.10, 0.20, 0.45 on 'accuracy' -> mean 0.25 exactly.
        # foo scores 0.3333333 twice -> mean 0.3333333 -> round(...,4)=0.3333.
        run_id = _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            [
                ("gpt-kill", {"accuracy": 0.10}),
                ("gpt-kill", {"accuracy": 0.20}),
                ("gpt-kill", {"accuracy": 0.45}),
                ("foo-kill", {"accuracy": 0.3333333}),
                ("foo-kill", {"accuracy": 0.3333333}),
            ],
        )
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc),
        )
        by = {(r["model_id"], r["metric"]): r for r in rows}
        gpt = by[("gpt-kill", "accuracy")]
        foo = by[("foo-kill", "accuracy")]
        # (0.10+0.20+0.45)/3 = 0.25 ; rounding to 4dp leaves it 0.25.
        assert gpt["score"] == pytest.approx(0.25, abs=1e-9)
        # round(0.3333333, 4) == 0.3333 — pins round() AND its precision.
        assert foo["score"] == 0.3333
        # samples_evaluated counts the TaskEvaluation rows for the model.
        assert gpt["samples_evaluated"] == 3
        assert foo["samples_evaluated"] == 2
        # Mean mode populates a CI (n>=2, non-zero variance for gpt).
        assert gpt["ci_lower"] is not None and gpt["ci_upper"] is not None
        assert gpt["ci_lower"] < gpt["score"] < gpt["ci_upper"]

    def test_sum_aggregation_is_total_not_mean_no_ci(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            [
                ("sum-kill", {"accuracy": 1.0}),
                ("sum-kill", {"accuracy": 2.0}),
                ("sum-kill", {"accuracy": 4.0}),
            ],
        )
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc), aggregation="sum",
        )
        row = next(
            r for r in rows
            if r["model_id"] == "sum-kill" and r["metric"] == "accuracy"
        )
        # 1+2+4 = 7 (TOTAL, not the mean 2.333). A sum/mean swap fails here.
        assert row["score"] == pytest.approx(7.0, abs=1e-9)
        # CI is meaningless for a total -> both bounds cleared.
        assert row["ci_lower"] is None
        assert row["ci_upper"] is None

    def test_noise_metric_excluded_from_buckets(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            [("noise-kill", {"accuracy": 0.9, "accuracy_details": 0.1})],
        )
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc),
        )
        metrics = {r["metric"] for r in rows if r["model_id"] == "noise-kill"}
        assert "accuracy" in metrics
        # '_details' noise must never become a ranked metric row.
        assert "accuracy_details" not in metrics


class TestLeaderboardRankingOrderDB:
    """Pin the published TIE-BREAK / sort order of read_llm_leaderboard.

    Order contract (see top_stmt in read_llm_leaderboard):
      1. non-null scores before null scores,
      2. higher score first (DESC),
      3. ties broken by model_id ASC.
    """

    def test_higher_score_ranks_first_and_ties_break_by_model_id(
        self, db_conn, make_project, make_user, make_task, make_generation,
        make_llm_model,
    ):
        from aggregate_summaries import (
            read_llm_leaderboard,
            recompute_llm_leaderboard_scores,
        )
        from models import LLMLeaderboardScore

        # read_llm_leaderboard applies the BYOM visibility gate: a model
        # surfaces only if it exists in llm_models as is_official OR is_public.
        # These synthetic models are never in the seeded catalog, so register
        # them as official rows first, otherwise the pivoted read filters them
        # all out and returns an empty leaderboard.
        for _mid in ("zeta", "alpha", "beta"):
            make_llm_model(model_id=_mid)

        # Three models on 'accuracy': zeta=0.9, alpha=0.5, beta=0.5.
        # Expected order: zeta (0.9) first, then the 0.5 tie broken by
        # model_id ASC -> 'alpha' before 'beta'.
        _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            [
                ("zeta", {"accuracy": 0.9}),
                ("alpha", {"accuracy": 0.5}),
                ("beta", {"accuracy": 0.5}),
            ],
        )
        # recompute writes all SCOPES x PERIODS rows; the 'all' scope includes
        # every completed run regardless of project visibility.
        recompute_llm_leaderboard_scores(db_conn)

        try:
            entries, total, _metrics, _ts = read_llm_leaderboard(
                db_conn,
                project_scope_key="all",
                period="overall",
                sort_metric="accuracy",
                limit=50,
                offset=0,
            )
            order = [
                e["model_id"] for e in entries
                if e["model_id"] in {"zeta", "alpha", "beta"}
            ]
            assert order == ["zeta", "alpha", "beta"], (
                f"leaderboard mis-ranked: {order}"
            )
            assert total >= 3
        finally:
            # The 'all' scope is global; remove the rows this run wrote so the
            # shared docker DB isn't polluted for sibling tests.
            db_conn.query(LLMLeaderboardScore).filter(
                LLMLeaderboardScore.model_id.in_(["zeta", "alpha", "beta"])
            ).delete(synchronize_session=False)
            db_conn.commit()
