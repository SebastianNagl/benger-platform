"""Complement behavioral tests for the LLM leaderboard router.

Target: ``services/api/routers/leaderboards.py`` (mounted at ``/api/leaderboards``,
included directly in ``main.py``).

This file is the COMPLEMENT of ``tests/integration/test_leaderboards_branches.py``.
That file covers the precomputed-read happy paths, the strict/trust-scope 400s,
the threshold drop, include_all_models padding, the period=weekly cutoff on
/statistics, and the details handler. This file fills the still-uncovered arms:

  GET /statistics ........... period=monthly cutoff branch; the no-project-filter
                              default scope (accessible-filter no-op → all
                              annotations in scope); contributor org-scoped access.
  GET /llm-models ........... the LIVE-aggregation path WITH real task_evaluation
                              data (search + aggregation=sum + evaluation_types
                              forcing live, rows materialised, available_metrics
                              populated, available_evaluation_types surfaced);
                              the multi-project explicit filter → scope_key None →
                              live path; offset/limit pagination of precomputed
                              rows; the period passthrough on the precomputed read.
  GET /llm-models/{id} ...... the LIVE per-model aggregate path (multi-project
                              filter, scope_key None) with real task_evaluation
                              data; the known-model-but-no-scores precomputed read
                              returning an empty aggregate.

The trust gate (``_intersect_with_allowlisted_org_projects``) is patched the
same way as the sibling file: to ``()`` to lift it for live-path tests, or to the
test org's id so a single project is in scope.

NOTE: ``/llm-models/compare`` is shadowed by ``/llm-models/{model_id}`` (declared
first) and is unreachable by path — its handler body (``compare_llm_models``,
lines ~763-868) cannot be driven over HTTP. The sibling file locks in the
route-order behaviour; we don't re-assert it here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMLeaderboardScore,
    LLMModel,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Annotation, Project, ProjectOrganization, Task

BASE = "/api/leaderboards"
ALLOWLIST_ATTR = "routers.leaderboards._LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS"


def _uid() -> str:
    return str(uuid.uuid4())


def _setup_project(db, admin, org, *, is_public=False, link_org=True):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"LBC {pid[:6]}",
        created_by=admin.id,
        is_public=is_public,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    db.flush()
    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        db.flush()
    return p


def _make_llm_model(db, model_id, name=None, provider="openai", active=True):
    if db.query(LLMModel).filter(LLMModel.id == model_id).first():
        return
    db.add(LLMModel(
        id=model_id, name=name or model_id, provider=provider,
        model_type="chat", capabilities=["text_generation"], is_active=active,
    ))
    db.flush()


def _make_score(db, *, model_id, scope, period="overall", metric, score,
                samples=100, evals=2, gens=60, ci_lower=None, ci_upper=None,
                last_at=None):
    row = LLMLeaderboardScore(
        id=_uid(),
        model_id=model_id,
        project_scope_key=scope,
        period=period,
        metric=metric,
        score=score,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        samples_evaluated=samples,
        evaluation_count=evals,
        generation_count=gens,
        last_evaluated_at=last_at or datetime.now(timezone.utc),
        computed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def _make_task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "t"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    db.flush()
    return t


def _make_annotation(db, task, project, user_id, *, created_at=None,
                     was_cancelled=False, result=None):
    kwargs = dict(
        id=_uid(), task_id=task.id, project_id=project.id,
        completed_by=user_id,
        result=result if result is not None else [
            {"from_name": "answer", "to_name": "text", "type": "choices",
             "value": {"choices": ["Ja"]}}
        ],
        was_cancelled=was_cancelled,
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    ann = Annotation(**kwargs)
    db.add(ann)
    db.flush()
    return ann


def _make_completed_eval_with_samples(db, project, admin_id, *, model_id,
                                      metric_values, eval_types=None):
    """Seed a completed EvaluationRun + Generation + TaskEvaluation rows so the
    LIVE aggregation path (live_aggregate_leaderboard) materialises real
    per-(model, metric) rows. ``metric_values`` is a list of dicts written as
    TaskEvaluation.metrics (one row each)."""
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by=admin_id,
    )
    db.add(rg)
    db.flush()

    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=eval_types or list(metric_values[0].keys()),
        metrics={}, status="completed", samples_evaluated=len(metric_values),
        has_sample_results=True, created_by=admin_id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=None,
        run_index=0, status="completed",
    )
    db.add(jr)
    db.flush()

    for i, mv in enumerate(metric_values):
        t = _make_task(db, project, admin_id, inner_id=i + 1)
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id, model_id=model_id,
            # distinct run_index per row: uq_generations_parent_run_index is
            # unique on (generation_id, run_index), so all-zero would collide.
            run_index=i, case_data="{}", response_content="r",
            status="completed", parse_status="success",
        )
        db.add(gen)
        db.flush()
        te = TaskEvaluation(
            id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=t.id,
            generation_id=gen.id, field_name="answer", answer_type="choices",
            ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
            metrics=mv, passed=True,
        )
        db.add(te)
    db.flush()
    return er


# ===========================================================================
# GET /statistics — period=monthly + no-filter default scope
# ===========================================================================


@pytest.mark.integration
class TestStatisticsComplement:
    def test_monthly_period_cutoff_excludes_old(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """period=monthly applies a 30-day cutoff (the elif arm not hit by the
        weekly test): a 60-day-old annotation is excluded, a fresh one counts."""
        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        t2 = _make_task(test_db, p, test_users[0].id, 2)
        _make_annotation(test_db, t1, p, test_users[0].id,
                         created_at=datetime.now(timezone.utc) - timedelta(days=60))
        _make_annotation(test_db, t2, p, test_users[0].id,
                         created_at=datetime.now(timezone.utc))
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}&period=monthly",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["filters"]["period"] == "monthly"

    def test_no_project_filter_default_scope_counts_total_users(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """No project_ids → the accessible-filter is a no-op (returns None) and
        the query aggregates over every project. total_users reflects active
        users in the system (the 4 fixture users are all active)."""
        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        _make_annotation(test_db, t1, p, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Our seeded annotation is included; total_annotators is at least 1.
        assert body["total_annotations"] >= 1
        assert body["total_annotators"] >= 1
        # 4 active fixture users at minimum.
        assert body["total_users"] >= 4
        assert body["filters"]["project_ids"] == []

    def test_contributor_org_scoped_statistics(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A non-superadmin (contributor) with org membership can read
        statistics for an org-linked project (accessible-filter keeps the id)."""
        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        _make_annotation(test_db, t1, p, test_users[1].id)
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1


# ===========================================================================
# GET /llm-models — LIVE aggregation path WITH data
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardLivePath:
    def test_search_live_path_materialises_rows(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A ``search`` param forces the live path (use_precomputed False). With
        the trust gate lifted (empty allowlist) and real task_evaluations, the
        live aggregator materialises rows; the search term filters by model id."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-live-a", "GPT Live A")
        _make_completed_eval_with_samples(
            test_db, p, test_users[0].id, model_id="gpt-live-a",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models?metric=bleu&search=gpt-live"
                "&min_generation_count=0&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {r["model_id"] for r in body["leaderboard"]}
        assert "gpt-live-a" in ids
        assert body["filters"]["search"] == "gpt-live"
        # Live path → computed_at is null.
        assert body["computed_at"] is None
        assert "bleu" in body["available_metrics"]

    def test_search_live_path_filters_out_nonmatching(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The search term drops models whose id/name don't contain it."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "alpha-model", "Alpha")
        _make_completed_eval_with_samples(
            test_db, p, test_users[0].id, model_id="alpha-model",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models?metric=bleu&search=zzz_no_match"
                "&min_generation_count=0&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["leaderboard"] == []
        assert body["total_models"] == 0

    def test_sum_aggregation_forces_live_path(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """aggregation=sum forces the live path (use_precomputed requires
        aggregation=='average'). The request succeeds and echoes the mode."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-sum", "GPT Sum")
        _make_completed_eval_with_samples(
            test_db, p, test_users[0].id, model_id="gpt-sum",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.5}, {"bleu": 0.5}],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models?metric=bleu&aggregation=sum"
                "&min_generation_count=0&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filters"]["aggregation"] == "sum"
        assert body["computed_at"] is None

    def test_evaluation_types_filter_forces_live_and_surfaces_types(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An evaluation_types filter forces the live path AND the
        available_evaluation_types list surfaces the run's declared types
        (_evaluation_types_in_scope scans EvaluationRun.evaluation_type_ids)."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-et", "GPT ET")
        _make_completed_eval_with_samples(
            test_db, p, test_users[0].id, model_id="gpt-et",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
            eval_types=["bleu"],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models?metric=bleu&evaluation_types=bleu"
                "&min_generation_count=0&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filters"]["evaluation_types"] == ["bleu"]
        assert "bleu" in body["available_evaluation_types"]
        assert body["computed_at"] is None

    def test_multi_project_filter_uses_live_path(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two explicit project_ids → scope_key None (multi-project) → live
        path. Both projects must be in the trust scope; we patch the allowlist
        to the test org so both qualify."""
        p1 = _setup_project(test_db, test_users[0], test_org)
        p2 = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-multi", "GPT Multi")
        _make_completed_eval_with_samples(
            test_db, p1, test_users[0].id, model_id="gpt-multi",
            metric_values=[{"bleu": 0.4}, {"bleu": 0.6}, {"bleu": 0.5}],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, (test_org.id,)):
            resp = client.get(
                f"{BASE}/llm-models?metric=bleu"
                f"&project_ids={p1.id}&project_ids={p2.id}"
                "&min_generation_count=0&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {r["model_id"] for r in body["leaderboard"]}
        assert "gpt-multi" in ids
        # Live path → no precomputed snapshot.
        assert body["computed_at"] is None
        assert set(body["filters"]["project_ids"]) == {p1.id, p2.id}


# ===========================================================================
# GET /llm-models — precomputed pagination + period
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardPagination:
    def test_offset_pagination_of_precomputed_rows(
        self, client, test_db, test_users, auth_headers
    ):
        """limit=1 & offset=1 returns the SECOND-ranked model; rank reflects the
        offset (rank starts at offset+1)."""
        _make_llm_model(test_db, "pg-a", "PG A")
        _make_llm_model(test_db, "pg-b", "PG B")
        _make_llm_model(test_db, "pg-c", "PG C")
        _make_score(test_db, model_id="pg-a", scope="tum", metric="accuracy",
                    score=0.9, gens=80, samples=120)
        _make_score(test_db, model_id="pg-b", scope="tum", metric="accuracy",
                    score=0.8, gens=80, samples=120)
        _make_score(test_db, model_id="pg-c", scope="tum", metric="accuracy",
                    score=0.7, gens=80, samples=120)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy&limit=1&offset=1",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["leaderboard"]) == 1
        entry = body["leaderboard"][0]
        # second-ranked overall is pg-b; rank = offset+1 = 2.
        assert entry["model_id"] == "pg-b"
        assert entry["rank"] == 2
        # total_models counts all qualifying models, not just the page.
        assert body["total_models"] >= 3

    def test_period_passthrough_reads_period_scoped_rows(
        self, client, test_db, test_users, auth_headers
    ):
        """period=weekly reads only the weekly-period precomputed rows; the
        overall-period row for the same model is not returned."""
        _make_llm_model(test_db, "per-a", "Per A")
        _make_score(test_db, model_id="per-a", scope="tum", period="weekly",
                    metric="accuracy", score=0.55, gens=70, samples=70)
        # An overall row with a different score — should NOT be the one read.
        _make_score(test_db, model_id="per-a", scope="tum", period="overall",
                    metric="accuracy", score=0.99, gens=70, samples=70)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy&period=weekly",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows = {r["model_id"]: r for r in body["leaderboard"]}
        assert "per-a" in rows
        assert rows["per-a"]["average_score"] == pytest.approx(0.55)
        assert body["filters"]["period"] == "weekly"


# ===========================================================================
# GET /llm-models/{model_id} — live path + empty precomputed aggregate
# ===========================================================================


@pytest.mark.integration
class TestLLMModelDetailsComplement:
    def test_live_per_model_aggregate_multi_project(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A multi-project filter (scope_key None) drives the live per-model
        aggregate path in get_llm_model_details, building aggregate_metrics from
        the live rows."""
        p1 = _setup_project(test_db, test_users[0], test_org)
        p2 = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-live-detail", "GPT Live Detail")
        _make_completed_eval_with_samples(
            test_db, p1, test_users[0].id, model_id="gpt-live-detail",
            metric_values=[{"bleu": 0.4}, {"bleu": 0.6}, {"bleu": 0.5}],
        )
        test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models/gpt-live-detail"
                f"?project_ids={p1.id}&project_ids={p2.id}",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["name"] == "GPT Live Detail"
        # Live path → computed_at null; samples / generations counted.
        assert body["computed_at"] is None
        assert body["samples_evaluated"] >= 1
        assert "bleu" in body["aggregate_metrics"]

    def test_known_model_no_scores_returns_empty_aggregate(
        self, client, test_db, test_users, auth_headers
    ):
        """A model present in the LLMModel table but with NO precomputed scores
        under the 'all' scope returns its metadata + an empty aggregate."""
        _make_llm_model(test_db, "gpt-empty-agg", "GPT Empty Agg", provider="openai")
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models/gpt-empty-agg",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["name"] == "GPT Empty Agg"
        assert body["model_info"]["provider"] == "openai"
        assert body["aggregate_metrics"] == {}
        assert body["evaluation_count"] == 0
        assert body["samples_evaluated"] == 0
