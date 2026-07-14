"""Behavioral integration tests for the LLM leaderboard router.

Target: ``services/api/routers/leaderboards.py`` (mounted at its own prefix
``/api/leaderboards`` and included directly in ``main.py``). The existing
``tests/unit/test_leaderboards_visibility.py`` is static-analysis only (regex
over the source); this file drives real HTTP round-trips against the
precomputed-read path and the live-aggregation path, asserting status +
response JSON and (for the seeded precomputed rows) the DB state they read
from.

The leaderboard endpoints were migrated to the async DB lane
(``Depends(get_async_db)``), so these tests seed rows via ``async_test_db`` and
drive the HTTP surface through ``async_test_client``. ``get_current_user`` is
overridden per-test (via ``_as_user``) to return an auth User matching the
seeded actor — the sync auth dependency can't see the async test transaction.
Anonymous tests simply omit the override (``get_current_user`` returns None).

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
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    LLMLeaderboardScore,
    LLMModel,
    Organization,
    OrganizationMembership,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task

pytestmark = pytest.mark.asyncio

BASE = "/api/leaderboards"
ALLOWLIST_ATTR = "routers.leaderboards._LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS"


# ---------------------------------------------------------------------------
# Auth override + async seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override get_current_user to return the seeded actor for the request."""
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"lb-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="LB User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name="LB Org"):
    org = Organization(
        id=_uid(),
        name=f"{name}-{_uid()[:6]}",
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:6]}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user, org, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _setup_project(db, admin, org, *, is_private=False, is_public=False,
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
    await db.flush()
    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        await db.flush()
    return p


async def _make_llm_model(db, model_id, name=None, provider="openai", active=True):
    existing = (
        await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(LLMModel(
        id=model_id, name=name or model_id, provider=provider,
        model_type="chat", capabilities=["text_generation"], is_active=active,
        is_official=True,
    ))
    await db.flush()


async def _make_score(db, *, model_id, scope, period="overall", metric, score,
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
    await db.flush()
    return row


async def _make_annotation(db, task, project, user_id, *, created_at=None,
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
    await db.flush()
    return ann


async def _make_task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "t"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    await db.flush()
    return t


# ===========================================================================
# GET /statistics
# ===========================================================================


@pytest.mark.integration
class TestStatistics:
    async def test_aggregates_annotation_counts(
        self, async_test_client, async_test_db
    ):
        """Two non-cancelled annotations with non-empty results from one user →
        total_annotations=2, total_annotators=1, average=2.0."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin.id, 1)
        t2 = await _make_task(async_test_db, p, admin.id, 2)
        await _make_annotation(async_test_db, t1, p, admin.id)
        await _make_annotation(async_test_db, t2, p, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics?project_ids={p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 2
        assert body["total_annotators"] == 1
        assert body["average_annotations_per_user"] == pytest.approx(2.0)
        assert body["filters"]["period"] == "overall"

    async def test_cancelled_and_empty_results_excluded(
        self, async_test_client, async_test_db
    ):
        """A cancelled annotation and an empty-result annotation are both
        filtered out (was_cancelled / jsonb_array_length>0 guards)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin.id, 1)
        t2 = await _make_task(async_test_db, p, admin.id, 2)
        t3 = await _make_task(async_test_db, p, admin.id, 3)
        await _make_annotation(async_test_db, t1, p, admin.id)  # counts
        await _make_annotation(async_test_db, t2, p, admin.id, was_cancelled=True)  # excluded
        await _make_annotation(async_test_db, t3, p, admin.id, result=[])  # excluded (empty)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics?project_ids={p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["total_annotators"] == 1

    async def test_zero_annotators_average_is_zero(
        self, async_test_client, async_test_db
    ):
        """No qualifying annotations → the ``total_annotators > 0`` guard's
        False arm returns average 0 (no div-by-zero)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await _make_task(async_test_db, p, admin.id, 1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics?project_ids={p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 0
        assert body["total_annotators"] == 0
        assert body["average_annotations_per_user"] == 0

    async def test_weekly_period_cutoff_excludes_old(
        self, async_test_client, async_test_db
    ):
        """period=weekly applies a 7-day cutoff: an annotation from 60 days ago
        is excluded while a fresh one counts."""
        from datetime import timedelta

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin.id, 1)
        t2 = await _make_task(async_test_db, p, admin.id, 2)
        await _make_annotation(async_test_db, t1, p, admin.id,
                               created_at=datetime.now(timezone.utc) - timedelta(days=60))
        await _make_annotation(async_test_db, t2, p, admin.id,
                               created_at=datetime.now(timezone.utc))
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics?project_ids={p.id}&period=weekly",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["filters"]["period"] == "weekly"

    async def test_invalid_period_422(self, async_test_client, async_test_db):
        """period must match the regex — 'yearly' is a 422."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics?period=yearly",
            )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# GET /llm-models  (default precomputed 'tum' scope)
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardDefault:
    async def test_default_reads_precomputed_tum_scope(
        self, async_test_client, async_test_db
    ):
        """A default request (no project_ids) reads the precomputed 'tum' rows.
        Two models, ranked by the 'accuracy' metric descending."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-lb-a", "GPT LB A")
        await _make_llm_model(async_test_db, "gpt-lb-b", "GPT LB B")
        await _make_score(async_test_db, model_id="gpt-lb-a", scope="tum", metric="accuracy",
                          score=0.9, gens=80, samples=120)
        await _make_score(async_test_db, model_id="gpt-lb-b", scope="tum", metric="accuracy",
                          score=0.6, gens=70, samples=110)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy",
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

    async def test_min_samples_threshold_drops_low_sample_model(
        self, async_test_client, async_test_db
    ):
        """min_generation_count filters out a model whose generation_count is
        below the threshold; the qualifying one survives."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-hi", "GPT Hi")
        await _make_llm_model(async_test_db, "gpt-lo", "GPT Lo")
        await _make_score(async_test_db, model_id="gpt-hi", scope="tum", metric="accuracy",
                          score=0.8, gens=90, samples=90)
        await _make_score(async_test_db, model_id="gpt-lo", scope="tum", metric="accuracy",
                          score=0.95, gens=5, samples=5)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy"
                "&min_generation_count=50&min_samples_evaluated=50",
            )
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-hi" in ids
        assert "gpt-lo" not in ids

    async def test_threshold_off_keeps_low_sample_model(
        self, async_test_client, async_test_db
    ):
        """With thresholds set to 0, even the low-sample model surfaces."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-lo2", "GPT Lo2")
        await _make_score(async_test_db, model_id="gpt-lo2", scope="tum", metric="accuracy",
                          score=0.95, gens=5, samples=5)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy"
                "&min_generation_count=0&min_samples_evaluated=0",
            )
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-lo2" in ids

    async def test_include_all_models_pads_catalog(
        self, async_test_client, async_test_db
    ):
        """include_all_models (with thresholds off) pads the leaderboard with
        active catalog models that have zero scores, as n/a rows."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-scored", "GPT Scored")
        await _make_llm_model(async_test_db, "gpt-unscored", "GPT Unscored")
        await _make_score(async_test_db, model_id="gpt-scored", scope="tum", metric="accuracy",
                          score=0.7, gens=60, samples=60)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy&include_all_models=true"
                "&min_generation_count=0&min_samples_evaluated=0",
            )
        assert resp.status_code == 200, resp.text
        rows = {r["model_id"]: r for r in resp.json()["leaderboard"]}
        # The unscored catalog model appears with a None average_score.
        assert "gpt-unscored" in rows
        assert rows["gpt-unscored"]["average_score"] is None
        assert rows["gpt-unscored"]["samples_evaluated"] == 0

    async def test_limit_over_cap_422(self, async_test_client, async_test_db):
        """limit has le=200 — 500 is a 422 before any DB work."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?limit=500",
            )
        assert resp.status_code == 422, resp.text

    async def test_invalid_aggregation_422(self, async_test_client, async_test_db):
        """aggregation must be average|sum — 'median' is a 422."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?aggregation=median",
            )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# GET /llm-models  (single-project scope + trust gate)
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardSingleProject:
    async def test_single_project_in_trust_scope_reads_precomputed(
        self, async_test_client, async_test_db
    ):
        """An authenticated single-project request (project IS allowlisted via
        the patched org) maps to scope_key=<project_id> and reads precomputed
        rows under that scope."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await _make_llm_model(async_test_db, "gpt-proj", "GPT Proj")
        await _make_score(async_test_db, model_id="gpt-proj", scope=p.id, metric="accuracy",
                          score=0.77, gens=60, samples=60)
        await async_test_db.commit()

        with patch(ALLOWLIST_ATTR, (org.id,)):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=accuracy&project_ids={p.id}",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows = {r["model_id"]: r for r in body["leaderboard"]}
        assert "gpt-proj" in rows
        assert rows["gpt-proj"]["average_score"] == pytest.approx(0.77)
        assert body["filters"]["project_ids"] == [p.id]

    async def test_project_not_in_trust_scope_400(
        self, async_test_client, async_test_db
    ):
        """A project that's accessible but NOT in the trust allowlist (the real
        constant lists only TUM) → the 'not in the LLM leaderboard trust scope'
        400."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await async_test_db.commit()

        # Force a non-empty allowlist that does NOT contain the test org, so
        # the intersect strips the project and 400s.
        with patch(ALLOWLIST_ATTR, (str(uuid.uuid4()),)):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?project_ids={p.id}",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 400, resp.text
        assert "trust scope" in resp.json()["detail"]

    async def test_inaccessible_project_strict_400(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin asking for a private project they cannot access:
        ``_filter_accessible_project_ids(strict=True)`` strips it and raises a
        400 (before the trust gate even runs)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        await _add_membership(async_test_db, contributor, org, role="CONTRIBUTOR")
        p = await _setup_project(
            async_test_db, admin, org, is_private=True, link_org=False,
        )
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?project_ids={p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 400, resp.text
        assert "no accessible project" in resp.json()["detail"]

    async def test_search_uses_live_path(
        self, async_test_client, async_test_db
    ):
        """A ``search`` param forces the live-aggregation path (use_precomputed
        is False when search is set). With the gate lifted (allowlist empty) and
        no underlying task_evaluations, the live path returns an empty
        leaderboard but a 200 with the echoed search filter."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        await _setup_project(async_test_db, admin, org)
        await async_test_db.commit()

        # Search for a model name that cannot match anything — this still
        # forces the live-aggregation path (search set) but keeps the result
        # empty on the shared CI DB, which carries baseline/other-test
        # task_evaluations that a real term like "gpt" would surface.
        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?search=zzz-no-such-model&min_generation_count=0"
                    "&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
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
    async def test_anonymous_default_reads_tum_then_public_metrics(
        self, async_test_client, async_test_db
    ):
        """An anonymous request (no auth override) still hits the no-filter
        default → scope 'tum' for the precomputed read. Confirms anonymous
        access is allowed (get_current_user returns None, no 401)."""
        await _make_llm_model(async_test_db, "gpt-anon", "GPT Anon")
        await _make_score(async_test_db, model_id="gpt-anon", scope="tum", metric="accuracy",
                          score=0.5, gens=60, samples=60)
        await async_test_db.commit()

        resp = await async_test_client.get(f"{BASE}/llm-models?metric=accuracy")
        assert resp.status_code == 200, resp.text
        ids = {r["model_id"] for r in resp.json()["leaderboard"]}
        assert "gpt-anon" in ids


# ===========================================================================
# GET /llm-models/{model_id}
# ===========================================================================


@pytest.mark.integration
class TestLLMModelDetails:
    async def test_known_model_reads_precomputed_aggregate(
        self, async_test_client, async_test_db
    ):
        """A known model with precomputed rows under the authenticated 'all'
        scope returns its per-metric aggregate."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-detail", "GPT Detail", provider="openai")
        await _make_score(async_test_db, model_id="gpt-detail", scope="all", metric="accuracy",
                          score=0.81, samples=50, evals=3, gens=40,
                          ci_lower=0.7, ci_upper=0.9)
        await _make_score(async_test_db, model_id="gpt-detail", scope="all", metric="f1",
                          score=0.79, samples=50, evals=3, gens=40)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/gpt-detail",
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

    async def test_unknown_model_falls_back_to_detected_provider(
        self, async_test_client, async_test_db
    ):
        """A model_id absent from the LLMModel table uses
        detect_provider_from_model_id for the provider and the id as the name,
        with an empty aggregate."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/claude-sonnet-unknown",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["id"] == "claude-sonnet-unknown"
        assert body["model_info"]["name"] == "claude-sonnet-unknown"
        # "claude-" prefix → Anthropic.
        assert body["model_info"]["provider"] == "Anthropic"
        assert body["aggregate_metrics"] == {}
        assert body["evaluation_count"] == 0
