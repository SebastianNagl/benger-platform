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

The leaderboard endpoints were migrated to the async DB lane
(``Depends(get_async_db)``), so these tests seed rows via ``async_test_db`` and
drive the HTTP surface through ``async_test_client``. ``get_current_user`` is
overridden per-test (via ``_as_user``) to return an auth User matching the
seeded actor — the sync auth dependency can't see the async test transaction.

The trust gate (``_intersect_with_allowlisted_org_projects``) is patched the
same way as the sibling file: to ``()`` to lift it for live-path tests, or to the
test org's id so a single project is in scope.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMLeaderboardScore,
    LLMModel,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task

pytestmark = pytest.mark.asyncio

BASE = "/api/leaderboards"
ALLOWLIST_ATTR = "routers.leaderboards._LLM_LEADERBOARD_ALLOWLISTED_ORG_IDS"


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth override + async seeding helpers
# ---------------------------------------------------------------------------


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
        username=f"lbc-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="LBC User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name="LBC Org"):
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


async def _setup_project(db, admin, org, *, is_public=False, link_org=True):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"LBC {pid[:6]}",
        created_by=admin.id,
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
    ))
    await db.flush()


async def _make_score(db, *, model_id, scope, period="overall", metric, score,
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
    await db.flush()
    return row


async def _make_task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "t"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    await db.flush()
    return t


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


async def _make_completed_eval_with_samples(db, project, admin_id, *, model_id,
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
    await db.flush()

    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=eval_types or list(metric_values[0].keys()),
        metrics={}, status="completed", samples_evaluated=len(metric_values),
        has_sample_results=True, created_by=admin_id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=None,
        run_index=0, status="completed",
    )
    db.add(jr)
    await db.flush()

    for i, mv in enumerate(metric_values):
        t = await _make_task(db, project, admin_id, inner_id=i + 1)
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id, model_id=model_id,
            # distinct run_index per row: uq_generations_parent_run_index is
            # unique on (generation_id, run_index), so all-zero would collide.
            run_index=i, case_data="{}", response_content="r",
            status="completed", parse_status="success",
        )
        db.add(gen)
        await db.flush()
        te = TaskEvaluation(
            id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=t.id,
            generation_id=gen.id, field_name="answer", answer_type="choices",
            ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
            metrics=mv, passed=True,
        )
        db.add(te)
    await db.flush()
    return er


# ---------------------------------------------------------------------------
# Committed-seed helper for the LIVE-aggregation path
# ---------------------------------------------------------------------------
#
# The live leaderboard aggregator (`live_aggregate_leaderboard_async`) runs its
# heavy task_evaluations scan inside `run_in_threadpool` on a *separate*
# `database.SessionLocal()` connection (see the function's docstring). That
# connection reads last-committed data and does NOT join this test's
# rollback-isolated async transaction — so rows seeded via `async_test_db` are
# invisible to it and the live path returns empty.
#
# To exercise the live path we therefore commit the rows the aggregator needs
# through `SessionLocal()`, then DELETE exactly those rows (FK-safe order) in a
# finalizer so isolation is preserved. Mirrors the workers e2e "explicit-delete
# cleanup" pattern.


class _CommittedLiveSeed:
    """Tracks rows committed through `SessionLocal()` for the live-path tests
    and deletes exactly them (FK-safe order) on teardown."""

    def __init__(self):
        # Each entry: (table_name, id) — deleted children-first on teardown.
        self._users: list[str] = []
        self._orgs: list[str] = []
        self._models: list[str] = []
        self._projects: list[str] = []
        self._project_orgs: list[str] = []
        self._tasks: list[str] = []
        self._response_gens: list[str] = []
        self._eval_runs: list[str] = []
        self._judge_runs: list[str] = []
        self._generations: list[str] = []
        self._task_evals: list[str] = []

    def seed_user(self, session, *, is_superadmin=True):
        u = User(
            id=_uid(),
            username=f"lbc-live-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="LBC Live User",
            is_superadmin=is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(u)
        session.flush()
        self._users.append(u.id)
        return u

    def seed_org(self, session, name="LBC Live Org"):
        org = Organization(
            id=_uid(),
            name=f"{name}-{_uid()[:6]}",
            slug=f"{name.lower().replace(' ', '-')}-{_uid()[:6]}",
            display_name=name,
            created_at=datetime.now(timezone.utc),
        )
        session.add(org)
        session.flush()
        self._orgs.append(org.id)
        return org

    def seed_model(self, session, model_id, name=None, provider="openai"):
        existing = (
            session.execute(select(LLMModel).where(LLMModel.id == model_id))
        ).scalar_one_or_none()
        if existing:
            # Track it for cleanup anyway: these committed model ids are fixed
            # strings, so a row leaked by a prior crashed run would otherwise
            # become permanent (and self-perpetuate via this early-return).
            if existing.id not in self._models:
                self._models.append(existing.id)
            return existing
        m = LLMModel(
            id=model_id, name=name or model_id, provider=provider,
            model_type="chat", capabilities=["text_generation"], is_active=True,
        )
        session.add(m)
        session.flush()
        self._models.append(m.id)
        return m

    def seed_project(self, session, admin, org, *, link_org=True):
        pid = _uid()
        p = Project(
            id=pid,
            title=f"LBC Live {pid[:6]}",
            created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        session.add(p)
        session.flush()
        self._projects.append(p.id)
        if link_org:
            po = ProjectOrganization(
                id=_uid(), project_id=pid,
                organization_id=org.id, assigned_by=admin.id,
            )
            session.add(po)
            session.flush()
            self._project_orgs.append(po.id)
        return p

    def seed_completed_eval(self, session, project, admin_id, *, model_id,
                            metric_values, eval_types=None):
        """Commit a completed EvaluationRun + Generation + TaskEvaluation chain
        so the live aggregator materialises real per-(model, metric) rows."""
        rg = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id=model_id,
            status="completed", created_by=admin_id,
        )
        session.add(rg)
        session.flush()
        self._response_gens.append(rg.id)

        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=eval_types or list(metric_values[0].keys()),
            metrics={}, status="completed", samples_evaluated=len(metric_values),
            has_sample_results=True, created_by=admin_id,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(er)
        session.flush()
        self._eval_runs.append(er.id)

        jr = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        session.add(jr)
        session.flush()
        self._judge_runs.append(jr.id)

        for i, mv in enumerate(metric_values):
            t = Task(
                id=_uid(), project_id=project.id,
                data={"text": "t"}, inner_id=i + 1, created_by=admin_id,
            )
            session.add(t)
            session.flush()
            self._tasks.append(t.id)
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=t.id, model_id=model_id,
                run_index=i, case_data="{}", response_content="r",
                status="completed", parse_status="success",
            )
            session.add(gen)
            session.flush()
            self._generations.append(gen.id)
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=t.id,
                generation_id=gen.id, field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
                metrics=mv, passed=True,
            )
            session.add(te)
            session.flush()
            self._task_evals.append(te.id)
        return er

    def cleanup(self, session):
        """Delete every seeded row, children-first, by primary key."""
        from sqlalchemy import delete

        for model, ids in [
            (TaskEvaluation, self._task_evals),
            (EvaluationJudgeRun, self._judge_runs),
            (Generation, self._generations),
            (EvaluationRun, self._eval_runs),
            (ResponseGeneration, self._response_gens),
            (Task, self._tasks),
            (ProjectOrganization, self._project_orgs),
            (Project, self._projects),
            (LLMModel, self._models),
            (Organization, self._orgs),
            (User, self._users),
        ]:
            if not ids:
                continue
            # Per-delete guard: a single delete failure must not abort the rest
            # and leak every other committed row into the shared DB. Roll back
            # the failed statement and press on; commit what succeeded.
            try:
                session.execute(delete(model).where(model.id.in_(ids)))
                session.commit()
            except Exception:
                session.rollback()


@pytest.fixture
def committed_live_seed():
    """Yield a `_CommittedLiveSeed` whose rows are committed through the
    production `SessionLocal()` (so the live-path threadpool connection sees
    them) and deleted FK-safe on teardown (so test isolation holds)."""
    from database import SessionLocal

    seed = _CommittedLiveSeed()
    session = SessionLocal()
    try:
        yield seed, session
    finally:
        try:
            seed.cleanup(session)
        finally:
            session.close()


# ===========================================================================
# GET /statistics — period=monthly + no-filter default scope
# ===========================================================================


@pytest.mark.integration
class TestStatisticsComplement:
    async def test_monthly_period_cutoff_excludes_old(
        self, async_test_client, async_test_db
    ):
        """period=monthly applies a 30-day cutoff (the elif arm not hit by the
        weekly test): a 60-day-old annotation is excluded, a fresh one counts."""
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
                f"{BASE}/statistics?project_ids={p.id}&period=monthly",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1
        assert body["filters"]["period"] == "monthly"

    async def test_no_project_filter_default_scope_counts_total_users(
        self, async_test_client, async_test_db
    ):
        """No project_ids → the accessible-filter is a no-op (returns None) and
        the query aggregates over every project. total_users reflects active
        users in the system (we seed at least 4 active users)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        # Seed 3 extra active users so total_users >= 4 holds in isolation.
        for _ in range(3):
            await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin.id, 1)
        await _make_annotation(async_test_db, t1, p, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/statistics",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Our seeded annotation is included; total_annotators is at least 1.
        assert body["total_annotations"] >= 1
        assert body["total_annotators"] >= 1
        # 4 active seeded users at minimum.
        assert body["total_users"] >= 4
        assert body["filters"]["project_ids"] == []

    async def test_contributor_org_scoped_statistics(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin (contributor) with org membership can read
        statistics for an org-linked project (accessible-filter keeps the id)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        await _add_membership(async_test_db, contributor, org, role="CONTRIBUTOR")
        p = await _setup_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin.id, 1)
        await _make_annotation(async_test_db, t1, p, contributor.id)
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                f"{BASE}/statistics?project_ids={p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_annotations"] == 1


# ===========================================================================
# GET /llm-models — LIVE aggregation path WITH data
# ===========================================================================


@pytest.mark.integration
class TestLLMLeaderboardLivePath:
    async def test_search_live_path_materialises_rows(
        self, async_test_client, committed_live_seed
    ):
        """A ``search`` param forces the live path (use_precomputed False). With
        the trust gate lifted (empty allowlist) and real task_evaluations, the
        live aggregator materialises rows; the search term filters by model id.

        The live aggregator's heavy scan runs on a separate committed-read
        ``SessionLocal()`` connection, so the eval rows are seeded + committed
        via ``committed_live_seed`` (deleted FK-safe on teardown) rather than on
        the rollback-isolated ``async_test_db`` (which the threadpool can't see).
        """
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        p = seed.seed_project(session, admin, org)
        seed.seed_model(session, "gpt-live-a", "GPT Live A")
        seed.seed_completed_eval(
            session, p, admin.id, model_id="gpt-live-a",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
        )
        session.commit()

        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=bleu&search=gpt-live"
                    "&min_generation_count=0&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {r["model_id"] for r in body["leaderboard"]}
        assert "gpt-live-a" in ids
        assert body["filters"]["search"] == "gpt-live"
        # Live path → computed_at is null.
        assert body["computed_at"] is None
        assert "bleu" in body["available_metrics"]

    async def test_search_live_path_filters_out_nonmatching(
        self, async_test_client, async_test_db
    ):
        """The search term drops models whose id/name don't contain it."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await _make_llm_model(async_test_db, "alpha-model", "Alpha")
        await _make_completed_eval_with_samples(
            async_test_db, p, admin.id, model_id="alpha-model",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
        )
        await async_test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=bleu&search=zzz_no_match"
                    "&min_generation_count=0&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["leaderboard"] == []
        assert body["total_models"] == 0

    async def test_sum_aggregation_forces_live_path(
        self, async_test_client, async_test_db
    ):
        """aggregation=sum forces the live path (use_precomputed requires
        aggregation=='average'). The request succeeds and echoes the mode."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await _make_llm_model(async_test_db, "gpt-sum", "GPT Sum")
        await _make_completed_eval_with_samples(
            async_test_db, p, admin.id, model_id="gpt-sum",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.5}, {"bleu": 0.5}],
        )
        await async_test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=bleu&aggregation=sum"
                    "&min_generation_count=0&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filters"]["aggregation"] == "sum"
        assert body["computed_at"] is None

    async def test_evaluation_types_filter_forces_live_and_surfaces_types(
        self, async_test_client, async_test_db
    ):
        """An evaluation_types filter forces the live path AND the
        available_evaluation_types list surfaces the run's declared types
        (_evaluation_types_in_scope scans EvaluationRun.evaluation_type_ids)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, admin, org)
        p = await _setup_project(async_test_db, admin, org)
        await _make_llm_model(async_test_db, "gpt-et", "GPT ET")
        await _make_completed_eval_with_samples(
            async_test_db, p, admin.id, model_id="gpt-et",
            metric_values=[{"bleu": 0.5}, {"bleu": 0.7}, {"bleu": 0.6}],
            eval_types=["bleu"],
        )
        await async_test_db.commit()

        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=bleu&evaluation_types=bleu"
                    "&min_generation_count=0&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filters"]["evaluation_types"] == ["bleu"]
        assert "bleu" in body["available_evaluation_types"]
        assert body["computed_at"] is None

    async def test_multi_project_filter_uses_live_path(
        self, async_test_client, committed_live_seed
    ):
        """Two explicit project_ids → scope_key None (multi-project) → live
        path. Both projects must be in the trust scope; we patch the allowlist
        to the test org so both qualify.

        Seeded + committed via ``committed_live_seed`` so the live aggregator's
        committed-read threadpool connection sees the eval rows (and the
        ProjectOrganization links the async trust-intersect query reads);
        deleted FK-safe on teardown.
        """
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        p1 = seed.seed_project(session, admin, org)
        p2 = seed.seed_project(session, admin, org)
        seed.seed_model(session, "gpt-multi", "GPT Multi")
        seed.seed_completed_eval(
            session, p1, admin.id, model_id="gpt-multi",
            metric_values=[{"bleu": 0.4}, {"bleu": 0.6}, {"bleu": 0.5}],
        )
        session.commit()

        with patch(ALLOWLIST_ATTR, (org.id,)):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models?metric=bleu"
                    f"&project_ids={p1.id}&project_ids={p2.id}"
                    "&min_generation_count=0&min_samples_evaluated=0",
                    headers={"X-Organization-Context": org.id},
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
    async def test_offset_pagination_of_precomputed_rows(
        self, async_test_client, async_test_db
    ):
        """limit=1 & offset=1 returns the SECOND-ranked model; rank reflects the
        offset (rank starts at offset+1)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "pg-a", "PG A")
        await _make_llm_model(async_test_db, "pg-b", "PG B")
        await _make_llm_model(async_test_db, "pg-c", "PG C")
        await _make_score(async_test_db, model_id="pg-a", scope="tum", metric="accuracy",
                          score=0.9, gens=80, samples=120)
        await _make_score(async_test_db, model_id="pg-b", scope="tum", metric="accuracy",
                          score=0.8, gens=80, samples=120)
        await _make_score(async_test_db, model_id="pg-c", scope="tum", metric="accuracy",
                          score=0.7, gens=80, samples=120)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy&limit=1&offset=1",
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

    async def test_period_passthrough_reads_period_scoped_rows(
        self, async_test_client, async_test_db
    ):
        """period=weekly reads only the weekly-period precomputed rows; the
        overall-period row for the same model is not returned."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "per-a", "Per A")
        await _make_score(async_test_db, model_id="per-a", scope="tum", period="weekly",
                          metric="accuracy", score=0.55, gens=70, samples=70)
        # An overall row with a different score — should NOT be the one read.
        await _make_score(async_test_db, model_id="per-a", scope="tum", period="overall",
                          metric="accuracy", score=0.99, gens=70, samples=70)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models?metric=accuracy&period=weekly",
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
    async def test_live_per_model_aggregate_multi_project(
        self, async_test_client, committed_live_seed
    ):
        """A multi-project filter (scope_key None) drives the live per-model
        aggregate path in get_llm_model_details, building aggregate_metrics from
        the live rows.

        Seeded + committed via ``committed_live_seed`` so the live aggregator's
        committed-read threadpool connection sees the eval rows; deleted FK-safe
        on teardown.
        """
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        p1 = seed.seed_project(session, admin, org)
        p2 = seed.seed_project(session, admin, org)
        seed.seed_model(session, "gpt-live-detail", "GPT Live Detail")
        seed.seed_completed_eval(
            session, p1, admin.id, model_id="gpt-live-detail",
            metric_values=[{"bleu": 0.4}, {"bleu": 0.6}, {"bleu": 0.5}],
        )
        session.commit()

        with patch(ALLOWLIST_ATTR, ()):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models/gpt-live-detail"
                    f"?project_ids={p1.id}&project_ids={p2.id}",
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["name"] == "GPT Live Detail"
        # Live path → computed_at null; samples / generations counted.
        assert body["computed_at"] is None
        assert body["samples_evaluated"] >= 1
        assert "bleu" in body["aggregate_metrics"]

    async def test_known_model_no_scores_returns_empty_aggregate(
        self, async_test_client, async_test_db
    ):
        """A model present in the LLMModel table but with NO precomputed scores
        under the 'all' scope returns its metadata + an empty aggregate."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_llm_model(async_test_db, "gpt-empty-agg", "GPT Empty Agg", provider="openai")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/gpt-empty-agg",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["name"] == "GPT Empty Agg"
        assert body["model_info"]["provider"] == "openai"
        assert body["aggregate_metrics"] == {}
        assert body["evaluation_count"] == 0
        assert body["samples_evaluated"] == 0
