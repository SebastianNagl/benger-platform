"""Real-DB kill tests for the LEADERBOARD aggregation math + ranking order.

The pure (no-DB) helpers of `shared/aggregate_summaries.py` are pinned in
`tests/test_aggregate_summaries_kills.py`. This file pins the parts that are
only reachable against a real Postgres because the metric coercion and the
per-bucket count/sum/stddev rollup run inside SQL and the leaderboard
tie-break is a SQL `ORDER BY`:

  * `_aggregate_leaderboard_rows` — per-(model, metric) mean, sum, and the
    `round(..., 4)` the worker WRITES into `llm_leaderboard_scores.score`,
    plus an equivalence check against the old all-in-Python algorithm.
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


# ---------------------------------------------------------------------------
# SQL rollup vs the pre-2026-09-17 Python algorithm
# ---------------------------------------------------------------------------
# Reference copy of the old implementation: stream every raw
# (model, metric, jsonb) triple, coerce in Python, bucket every float, then
# mean / sum / t-CI per bucket. `_aggregate_leaderboard_rows` now does the
# coercion and aggregation in Postgres. For every input the old code handled
# sanely (no NaN / inf / absurd magnitudes) both must agree.
_REFERENCE_TRIPLES_SQL = """
    SELECT g.model_id, kv.key AS metric_key, kv.value AS metric_val
    FROM task_evaluations te
    JOIN generations g ON g.id = te.generation_id
    JOIN evaluation_runs er ON er.id = te.evaluation_id
    CROSS JOIN LATERAL jsonb_each(te.metrics::jsonb) AS kv
    WHERE te.evaluation_id = ANY(:run_ids)
      AND te.generation_id IS NOT NULL
      AND te.metrics IS NOT NULL
      AND jsonb_typeof(te.metrics::jsonb) = 'object'
      AND (CAST(:eval_types AS text[]) IS NULL OR kv.key = ANY(:eval_types))
    UNION ALL
    SELECT g.model_id, 'llm_judge_falloesung_grade_points' AS metric_key,
           te.metrics::jsonb->'llm_judge_falloesung'->'details'->'grade_points'
    FROM task_evaluations te
    JOIN generations g ON g.id = te.generation_id
    JOIN evaluation_runs er ON er.id = te.evaluation_id
    WHERE te.evaluation_id = ANY(:run_ids)
      AND te.generation_id IS NOT NULL
      AND te.metrics IS NOT NULL
      AND jsonb_typeof(te.metrics::jsonb) = 'object'
      AND te.metrics::jsonb ? 'llm_judge_falloesung'
      AND te.metrics::jsonb->'llm_judge_falloesung'->'details' ? 'grade_points'
      AND jsonb_typeof(te.metrics::jsonb->'llm_judge_falloesung'->'details'->'grade_points') = 'number'
      AND (CAST(:eval_types AS text[]) IS NULL
           OR 'llm_judge_falloesung_grade_points' = ANY(:eval_types))
"""


def _reference_rows(db, run_ids, *, aggregation="average", evaluation_types=None):
    """Old algorithm, reduced to {(model, metric): (score, ci_lower, ci_upper)}."""
    from collections import defaultdict

    from aggregate_summaries import (
        _coerce_metric_value,
        _confidence_interval,
        _metric_key_is_real,
    )
    from sqlalchemy import text

    buckets = defaultdict(list)
    stmt = text(_REFERENCE_TRIPLES_SQL).bindparams(
        run_ids=run_ids, eval_types=evaluation_types or None
    )
    for model_id, metric_key, metric_val in db.execute(stmt).all():
        if not model_id or not _metric_key_is_real(metric_key):
            continue
        coerced = _coerce_metric_value(metric_val)
        if coerced is None:
            continue
        buckets[(model_id, metric_key)].append(coerced)

    out = {}
    for key, values in buckets.items():
        if aggregation == "sum":
            out[key] = (round(sum(values), 4), None, None)
        else:
            lo, hi = _confidence_interval(values)
            out[key] = (round(sum(values) / len(values), 4), lo, hi)
    return out


def _as_comparable(rows):
    return {
        (r["model_id"], r["metric"]): (r["score"], r["ci_lower"], r["ci_upper"])
        for r in rows
    }


def _assert_same(actual, expected):
    assert set(actual) == set(expected)
    for key, (score, lo, hi) in expected.items():
        a_score, a_lo, a_hi = actual[key]
        assert a_score == pytest.approx(score, abs=1e-9), key
        if lo is None:
            assert a_lo is None and a_hi is None, key
        else:
            assert a_lo == pytest.approx(lo, rel=1e-9, abs=1e-9), key
            assert a_hi == pytest.approx(hi, rel=1e-9, abs=1e-9), key


# One TaskEvaluation.metrics dict per row. Covers every branch of
# `_coerce_metric_value`: numbers, numeric strings (incl. whitespace,
# exponents, underscores), junk strings, booleans, nulls, arrays, dicts with
# value / total_score / score precedence, nested dicts, noise keys and the
# lifted grade_points.
_MIXED_METRICS = [
    ("eq-alpha", {"accuracy": 0.5, "bleu": "0.25", "flag": True,
                  "llm_judge_falloesung": {"value": 0.6, "details": {"grade_points": 11}}}),
    ("eq-alpha", {"accuracy": 1, "bleu": " 1e-1 ", "flag": False,
                  "llm_judge_falloesung": {"value": 0.8, "details": {"grade_points": 14.5}}}),
    ("eq-alpha", {"accuracy": "n/a", "bleu": "1_0.5", "rouge": None,
                  "llm_judge_falloesung": {"value": "0.7", "details": {"grade_points": "9"}}}),
    ("eq-alpha", {"accuracy": {"value": 0.25, "details": {"x": 1}}, "bleu": [0.3],
                  "judge": {"total_score": 14, "score": 3},
                  "accuracy_details": 0.99, "raw_score": 5}),
    ("eq-alpha", {"accuracy": {"value": None, "total_score": "0.75"},
                  "judge": {"score": 3}, "bleu": "", "error": "boom"}),
    ("eq-alpha", {"accuracy": {"value": {"value": 0.4}},
                  "judge": {"value": "bad", "score": 8},
                  "multi": {"value": {"precision": 1.0}, "score": 0.2}}),
    ("eq-beta", {"accuracy": 0.9, "judge": {"value": 0.0, "score": 5},
                 "multi": {"value": {"precision": 1.0}}, "llm_judge_falloesung": 0.4}),
    ("eq-beta", {"accuracy": "\t0.7\n", "judge": {"foo": 1},
                 "llm_judge_falloesung": {"details": {"grade_points": True}}}),
    ("eq-beta", {"accuracy": "+.5", "constant": 0.1, "judge": 7}),
    ("eq-beta", {"accuracy": "5.", "constant": 0.1,
                 "judge": {"value": {"score": 2}}}),
    ("eq-beta", {"constant": 0.1, "only_one": "3"}),
    ("eq-gamma", {"accuracy": 0.3333333, "bleu": {"value": True, "score": 1}}),
    ("eq-gamma", {"accuracy": 0.3333333, "bleu": {"value": [1], "score": "2e0"}}),
]


class TestSqlRollupMatchesPythonReferenceDB:
    """`_aggregate_leaderboard_rows` (Postgres rollup) must reproduce the old
    stream-everything-into-Python algorithm on mixed metric shapes."""

    def _seed(self, db_conn, make_project, make_user, make_task, make_generation):
        return _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            _MIXED_METRICS,
        )

    def test_average_matches_reference(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = self._seed(db_conn, make_project, make_user, make_task, make_generation)
        expected = _reference_rows(db_conn, [run_id])
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc),
        )
        actual = _as_comparable(rows)
        # Sanity: the seed really exercises the interesting buckets.
        assert ("eq-alpha", "llm_judge_falloesung_grade_points") in expected
        assert ("eq-alpha", "judge") in expected
        assert ("eq-beta", "constant") in expected
        assert ("eq-alpha", "flag") not in expected
        assert ("eq-alpha", "accuracy_details") not in expected
        _assert_same(actual, expected)
        # Constant bucket collapses the CI onto the mean.
        assert actual[("eq-beta", "constant")][1:] == (
            pytest.approx(0.1), pytest.approx(0.1)
        )
        # Single-sample bucket has no CI.
        assert actual[("eq-beta", "only_one")] == (3.0, None, None)
        # Output row shape is unchanged.
        assert set(rows[0]) == {
            "model_id", "project_scope_key", "period", "metric", "score",
            "ci_lower", "ci_upper", "samples_evaluated", "evaluation_count",
            "generation_count", "last_evaluated_at", "computed_at",
        }

    def test_sum_matches_reference(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = self._seed(db_conn, make_project, make_user, make_task, make_generation)
        expected = _reference_rows(db_conn, [run_id], aggregation="sum")
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc), aggregation="sum",
        )
        _assert_same(_as_comparable(rows), expected)

    def test_evaluation_types_filter_matches_reference(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = self._seed(db_conn, make_project, make_user, make_task, make_generation)
        types = ["judge", "llm_judge_falloesung_grade_points"]
        expected = _reference_rows(db_conn, [run_id], evaluation_types=types)
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc), evaluation_types=types,
        )
        actual = _as_comparable(rows)
        assert {m for _mid, m in actual} == set(types)
        _assert_same(actual, expected)

    def test_non_finite_values_are_dropped_not_poisoning(
        self, db_conn, make_project, make_user, make_task, make_generation
    ):
        """Deliberate difference: the old code let float('nan') / float('inf')
        poison the bucket mean. They are picked (so a later dict key is not
        tried, like before) and then dropped."""
        from aggregate_summaries import _aggregate_leaderboard_rows

        run_id = _seed_run_with_metrics(
            db_conn, make_project, make_user, make_task, make_generation,
            [
                ("nan-kill", {"accuracy": 0.2, "judge": {"value": "nan", "score": 9}}),
                ("nan-kill", {"accuracy": "NaN", "judge": 1.0}),
                ("nan-kill", {"accuracy": " -inf ", "judge": "1e400"}),
                ("nan-kill", {"accuracy": 0.4, "judge": 3.0, "huge": 1e200}),
            ],
        )
        rows = _aggregate_leaderboard_rows(
            db_conn, [run_id], scope="live", period="overall",
            computed_at=datetime.now(timezone.utc),
        )
        actual = _as_comparable(rows)
        assert actual[("nan-kill", "accuracy")][0] == pytest.approx(0.3)
        # judge: "nan" wins over score=9 and is dropped; "1e400" is inf, dropped.
        assert actual[("nan-kill", "judge")][0] == pytest.approx(2.0)
        assert ("nan-kill", "huge") not in actual
