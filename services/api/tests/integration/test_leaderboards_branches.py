"""Behavioral integration tests for the LLM leaderboard router.

Target: ``services/api/routers/leaderboards.py`` (mounted at its own prefix
``/api/leaderboards`` and included directly in ``main.py``). The existing
``tests/unit/test_leaderboards_visibility.py`` is static-analysis only (regex
over the source); this file drives real HTTP round-trips against the
precomputed-read path and the live-aggregation path, asserting status +
response JSON and (for the seeded precomputed rows) the DB state they read
from.

How the leaderboard resolves data (see ``services/shared/aggregate_summaries``):
  * The default request (no ``project_ids``) expands to the TUM trust
    allowlist and serves from the precomputed ``llm_leaderboard_scores`` table
    under ``project_scope_key='tum'``.
  * An authenticated single-project request maps to ``scope_key=<project_id>``;
    an anonymous request with no filter maps to ``'public'``.
  * Unusual combos (sum aggregation, evaluation_types filter, search,
    multi-project) fall through to ``live_aggregate_leaderboard``.

The trust gate (``_intersect_with_allowlisted_org_projects``) restricts which
projects contribute. Test projects aren't TUM-linked, so single-project tests
patch ``_LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS`` to the test org's id (so the
project is "in scope"), and live-path tests patch the allowlist to ``()`` to
lift the gate entirely.

Endpoints + branches covered:
  GET /statistics ............ annotation aggregation, period=weekly/monthly
                               cutoff, project_ids scoping, zero-annotator
                               average branch.
  GET /llm-models ............ precomputed 'tum' default read (metric sort,
                               period, generation_count column), single-project
                               'all'/<id> scope, the strict-filter 400 on an
                               inaccessible project_id, the trust-scope 400,
                               the min-samples threshold drop, the search live
                               path, include_all_models catalog padding, the
                               limit cap 422.
  GET /llm-models/{id} ....... precomputed per-model aggregate, unknown-model
                               fallback metadata (detect_provider_from_model_id),
                               period passthrough.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import LLMLeaderboardScore, LLMModel
from project_models import Annotation, Project, ProjectOrganization, Task

BASE = "/api/leaderboards"
ALLOWLIST_ATTR = "routers.leaderboards._LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS"


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _setup_project(db, admin, org, *, is_private=False, is_public=False,
                   link_org=True):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"LB {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
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
                samples=100, evals=2, gens=60,
                ci_lower=None, ci_upper=None, computed_at=None,
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
        computed_at=computed_at or datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


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


def _make_task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "t"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    db.flush()
    return t


# ===========================================================================
# GET /statistics
# ===========================================================================


@pytest.mark.integration
class TestStatistics:
    def test_aggregates_annotation_counts(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two non-cancelled annotations with non-empty results from one user →
        total_annotations=2, total_annotators=1, average=2.0."""
        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        t2 = _make_task(test_db, p, test_users[0].id, 2)
        _make_annotation(test_db, t1, p, test_users[0].id)
        _make_annotation(test_db, t2, p, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 2
        assert body["total_annotators"] == 1
        assert body["average_annotations_per_user"] == pytest.approx(2.0)
        assert body["filters"]["period"] == "overall"

    def test_cancelled_and_empty_results_excluded(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A cancelled annotation and an empty-result annotation are both
        filtered out (was_cancelled / jsonb_array_length>0 guards)."""
        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        t2 = _make_task(test_db, p, test_users[0].id, 2)
        t3 = _make_task(test_db, p, test_users[0].id, 3)
        _make_annotation(test_db, t1, p, test_users[0].id)  # counts
        _make_annotation(test_db, t2, p, test_users[0].id, was_cancelled=True)  # excluded
        _make_annotation(test_db, t3, p, test_users[0].id, result=[])  # excluded (empty)
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["total_annotators"] == 1

    def test_zero_annotators_average_is_zero(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """No qualifying annotations → the ``total_annotators > 0`` guard's
        False arm returns average 0 (no div-by-zero)."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_task(test_db, p, test_users[0].id, 1)
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 0
        assert body["total_annotators"] == 0
        assert body["average_annotations_per_user"] == 0

    def test_weekly_period_cutoff_excludes_old(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """period=weekly applies a 7-day cutoff: an annotation from 60 days ago
        is excluded while a fresh one counts."""
        from datetime import timedelta

        p = _setup_project(test_db, test_users[0], test_org)
        t1 = _make_task(test_db, p, test_users[0].id, 1)
        t2 = _make_task(test_db, p, test_users[0].id, 2)
        _make_annotation(test_db, t1, p, test_users[0].id,
                         created_at=datetime.now(timezone.utc) - timedelta(days=60))
        _make_annotation(test_db, t2, p, test_users[0].id,
                         created_at=datetime.now(timezone.utc))
        test_db.commit()

        resp = client.get(
            f"{BASE}/statistics?project_ids={p.id}&period=weekly",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["filters"]["period"] == "weekly"

    def test_invalid_period_422(self, client, test_db, test_users, auth_headers):
        """period must match the regex — 'yearly' is a 422."""
        resp = client.get(
            f"{BASE}/statistics?period=yearly",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# GET /llm-models  (default precomputed 'tum' scope)
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardDefault:
    def test_default_reads_precomputed_tum_scope(
        self, client, test_db, test_users, auth_headers
    ):
        """A default request (no project_ids) reads the precomputed 'tum' rows.
        Two models, ranked by the 'accuracy' metric descending."""
        _make_llm_model(test_db, "gpt-lb-a", "GPT LB A")
        _make_llm_model(test_db, "gpt-lb-b", "GPT LB B")
        _make_score(test_db, model_id="gpt-lb-a", scope="tum", metric="accuracy",
                    score=0.9, gens=80, samples=120)
        _make_score(test_db, model_id="gpt-lb-b", scope="tum", metric="accuracy",
                    score=0.6, gens=70, samples=110)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows = {r["model_id"]: r for r in body["leaderboard"]}
        assert "gpt-lb-a" in rows and "gpt-lb-b" in rows
        # Ranked by accuracy descending → A first.
        assert body["leaderboard"][0]["model_id"] == "gpt-lb-a"
        assert rows["gpt-lb-a"]["rank"] == 1
        assert rows["gpt-lb-a"]["average_score"] == pytest.approx(0.9)
        assert rows["gpt-lb-a"]["generation_count"] == 80
        assert rows["gpt-lb-a"]["model_name"] == "GPT LB A"
        assert "accuracy" in body["available_metrics"]
        # Precomputed read populates computed_at.
        assert body["computed_at"] is not None
        assert body["filters"]["metric"] == "accuracy"

    def test_min_samples_threshold_drops_low_sample_model(
        self, client, test_db, test_users, auth_headers
    ):
        """min_generation_count filters out a model whose generation_count is
        below the threshold; the qualifying one survives."""
        _make_llm_model(test_db, "gpt-hi", "GPT Hi")
        _make_llm_model(test_db, "gpt-lo", "GPT Lo")
        _make_score(test_db, model_id="gpt-hi", scope="tum", metric="accuracy",
                    score=0.8, gens=90, samples=90)
        _make_score(test_db, model_id="gpt-lo", scope="tum", metric="accuracy",
                    score=0.95, gens=5, samples=5)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy"
            "&min_generation_count=50&min_samples_evaluated=50",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-hi" in ids
        assert "gpt-lo" not in ids

    def test_threshold_off_keeps_low_sample_model(
        self, client, test_db, test_users, auth_headers
    ):
        """With thresholds set to 0, even the low-sample model surfaces."""
        _make_llm_model(test_db, "gpt-lo2", "GPT Lo2")
        _make_score(test_db, model_id="gpt-lo2", scope="tum", metric="accuracy",
                    score=0.95, gens=5, samples=5)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy"
            "&min_generation_count=0&min_samples_evaluated=0",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-lo2" in ids

    def test_include_all_models_pads_catalog(
        self, client, test_db, test_users, auth_headers
    ):
        """include_all_models (with thresholds off) pads the leaderboard with
        active catalog models that have zero scores, as n/a rows."""
        _make_llm_model(test_db, "gpt-scored", "GPT Scored")
        _make_llm_model(test_db, "gpt-unscored", "GPT Unscored")
        _make_score(test_db, model_id="gpt-scored", scope="tum", metric="accuracy",
                    score=0.7, gens=60, samples=60)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?metric=accuracy&include_all_models=true"
            "&min_generation_count=0&min_samples_evaluated=0",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        rows = {r["model_id"]: r for r in resp.json()["leaderboard"]}
        # The unscored catalog model appears with a None average_score.
        assert "gpt-unscored" in rows
        assert rows["gpt-unscored"]["average_score"] is None
        assert rows["gpt-unscored"]["samples_evaluated"] == 0

    def test_limit_over_cap_422(self, client, test_db, test_users, auth_headers):
        """limit has le=200 — 500 is a 422 before any DB work."""
        resp = client.get(
            f"{BASE}/llm-models?limit=500",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422, resp.text

    def test_invalid_aggregation_422(self, client, test_db, test_users, auth_headers):
        """aggregation must be average|sum — 'median' is a 422."""
        resp = client.get(
            f"{BASE}/llm-models?aggregation=median",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# GET /llm-models  (single-project scope + trust gate)
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardSingleProject:
    def test_single_project_in_trust_scope_reads_precomputed(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An authenticated single-project request (project IS allowlisted via
        the patched org) maps to scope_key=<project_id> and reads precomputed
        rows under that scope."""
        p = _setup_project(test_db, test_users[0], test_org)
        _make_llm_model(test_db, "gpt-proj", "GPT Proj")
        _make_score(test_db, model_id="gpt-proj", scope=p.id, metric="accuracy",
                    score=0.77, gens=60, samples=60)
        test_db.commit()

        with patch(ALLOWLIST_ATTR, (test_org.id,)):
            resp = client.get(
                f"{BASE}/llm-models?metric=accuracy&project_ids={p.id}",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows = {r["model_id"]: r for r in body["leaderboard"]}
        assert "gpt-proj" in rows
        assert rows["gpt-proj"]["average_score"] == pytest.approx(0.77)
        assert body["filters"]["project_ids"] == [p.id]

    def test_project_not_in_trust_scope_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A project that's accessible but NOT in the trust allowlist (the real
        constant lists only TUM) → the 'not in the LLM leaderboard trust scope'
        400."""
        p = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        # Force a non-empty allowlist that does NOT contain the test org, so
        # the intersect strips the project and 400s.
        with patch(ALLOWLIST_ATTR, (str(uuid.uuid4()),)):
            resp = client.get(
                f"{BASE}/llm-models?project_ids={p.id}",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 400, resp.text
        assert "trust scope" in resp.json()["detail"]

    def test_inaccessible_project_strict_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A non-superadmin asking for a private project they cannot access:
        ``_filter_accessible_project_ids(strict=True)`` strips it and raises a
        400 (before the trust gate even runs)."""
        p = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models?project_ids={p.id}",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 400, resp.text
        assert "no accessible project" in resp.json()["detail"]

    def test_search_uses_live_path(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A ``search`` param forces the live-aggregation path (use_precomputed
        is False when search is set). With the gate lifted (allowlist empty) and
        no underlying task_evaluations, the live path returns an empty
        leaderboard but a 200 with the echoed search filter."""
        _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        # Search for a model name that cannot match anything — this still
        # forces the live-aggregation path (search set) but keeps the result
        # empty on the shared CI DB, which carries baseline/other-test
        # task_evaluations that a real term like "gpt" would surface.
        with patch(ALLOWLIST_ATTR, ()):
            resp = client.get(
                f"{BASE}/llm-models?search=zzz-no-such-model&min_generation_count=0"
                "&min_samples_evaluated=0",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filters"]["search"] == "zzz-no-such-model"
        # Live path, no matching eval data → no rows, computed_at stays null.
        assert body["leaderboard"] == []
        assert body["computed_at"] is None


# ===========================================================================
# GET /llm-models  (anonymous → 'public' scope)
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardAnonymous:
    def test_anonymous_default_reads_tum_then_public_metrics(
        self, client, test_db, test_users
    ):
        """An anonymous request (no auth header) still hits the no-filter
        default → scope 'tum' for the precomputed read. Confirms anonymous
        access is allowed (get_current_user returns None, no 401)."""
        _make_llm_model(test_db, "gpt-anon", "GPT Anon")
        _make_score(test_db, model_id="gpt-anon", scope="tum", metric="accuracy",
                    score=0.5, gens=60, samples=60)
        test_db.commit()

        resp = client.get(f"{BASE}/llm-models?metric=accuracy")
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-anon" in ids


# ===========================================================================
# GET /llm-models/{model_id}
# ===========================================================================


@pytest.mark.integration
class TestLLMModelDetails:
    def test_known_model_reads_precomputed_aggregate(
        self, client, test_db, test_users, auth_headers
    ):
        """A known model with precomputed rows under the authenticated 'all'
        scope returns its per-metric aggregate."""
        _make_llm_model(test_db, "gpt-detail", "GPT Detail", provider="openai")
        _make_score(test_db, model_id="gpt-detail", scope="all", metric="accuracy",
                    score=0.81, samples=50, evals=3, gens=40,
                    ci_lower=0.7, ci_upper=0.9)
        _make_score(test_db, model_id="gpt-detail", scope="all", metric="f1",
                    score=0.79, samples=50, evals=3, gens=40)
        test_db.commit()

        resp = client.get(
            f"{BASE}/llm-models/gpt-detail",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["name"] == "GPT Detail"
        assert body["model_info"]["provider"] == "openai"
        assert body["aggregate_metrics"]["accuracy"]["mean"] == pytest.approx(0.81)
        assert body["aggregate_metrics"]["accuracy"]["ci_lower"] == pytest.approx(0.7)
        assert body["aggregate_metrics"]["f1"]["mean"] == pytest.approx(0.79)
        assert body["evaluation_count"] == 3
        assert body["generation_count"] == 40
        assert body["computed_at"] is not None

    def test_unknown_model_falls_back_to_detected_provider(
        self, client, test_db, test_users, auth_headers
    ):
        """A model_id absent from the LLMModel table uses
        detect_provider_from_model_id for the provider and the id as the name,
        with an empty aggregate."""
        resp = client.get(
            f"{BASE}/llm-models/claude-sonnet-unknown",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["id"] == "claude-sonnet-unknown"
        assert body["model_info"]["name"] == "claude-sonnet-unknown"
        # "claude-" prefix → Anthropic.
        assert body["model_info"]["provider"] == "Anthropic"
        assert body["aggregate_metrics"] == {}
        assert body["evaluation_count"] == 0

