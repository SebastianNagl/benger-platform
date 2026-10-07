"""Behavioral tests for ``GET /api/leaderboards/llm-models/{id}/projects``.

The model detail view: one model's evaluation scores broken down by project
and metric, for every project the caller may read. The handler lives in
``services/api/routers/leaderboards.py`` (``get_llm_model_project_scores``)
and the aggregation in ``services/shared/aggregate_summaries.py``
(``aggregate_model_project_rows_async``).

The heavy aggregation runs on a separate committed-read connection (threadpool
+ ``SessionLocal()``), so every row the aggregator must see is committed
through ``committed_live_seed`` (from the sibling coverage module) and deleted
FK-safe on teardown. Rows that only the async handler reads (users, orgs,
memberships, LLMModel visibility) can stay in ``async_test_db``.

Covered:
  * superadmin scope: org + public projects in, another user's private out
  * org member scope: own org + public in, foreign org out
  * anonymous scope: public only
  * a user with zero accessible projects gets [] (pins the empty-scope guard
    in front of ``_build_live_run_ids_stmt``, which treats [] as "no filter")
  * BYOM visibility: private custom model 404, public custom model 200
  * unknown model id → detected provider, empty projects
  * period=weekly drops a run created 10 days ago
  * per-project means, n, project metadata, metric ordering
  * grade_points lifted from ``details``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from models import OrganizationMembership
from tests.integration.test_leaderboards_coverage import (  # noqa: F401
    _as_user,
    _make_llm_model,
    _make_user,
    committed_live_seed,
)

BASE = "/api/leaderboards"


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_project(seed, session, owner, org, *, title, link_org=True,
                  is_private=False, is_public=False):
    """`seed_project` twin that also sets title / privacy flags."""
    p = seed.seed_project(session, owner, org, link_org=link_org)
    p.title = title
    if is_private:
        p.is_private = True
    if is_public:
        p.is_public = True
        p.public_role = "ANNOTATOR"
    session.flush()
    return p


def _membership(session, user, org, role="CONTRIBUTOR"):
    """Committed org membership. The seed helper has no slot for memberships,
    so the test deletes it in its own `finally` before the user teardown."""
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    session.add(m)
    session.flush()
    return m


@pytest.mark.integration
class TestModelProjectScoresScope:
    async def test_superadmin_sees_org_and_public_not_foreign_private(
        self, async_test_client, committed_live_seed
    ):
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        other = seed.seed_user(session, is_superadmin=False)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id, "GPT MP")

        p_org = _seed_project(seed, session, admin, org, title="Beta org")
        p_pub = _seed_project(
            seed, session, admin, org, title="Alpha public", link_org=False, is_public=True
        )
        p_priv = _seed_project(
            seed, session, other, org, title="Gamma private", link_org=False, is_private=True
        )
        seed.seed_completed_eval(
            session, p_org, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.4}, {"bleu": 0.6}],
        )
        seed.seed_completed_eval(
            session, p_pub, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.2, "rouge_l": 0.5}],
        )
        seed.seed_completed_eval(
            session, p_priv, other.id, model_id=model_id,
            metric_values=[{"bleu": 1.0}],
        )
        session.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"] == {
            "id": model_id, "name": "GPT MP", "provider": "openai",
        }
        by_id = {p["project_id"]: p for p in body["projects"]}
        assert set(by_id) == {p_org.id, p_pub.id}
        # Sorted by title.
        assert [p["project_name"] for p in body["projects"]] == [
            "Alpha public", "Beta org",
        ]
        org_row = by_id[p_org.id]
        assert org_row["metrics"]["bleu"]["mean"] == pytest.approx(0.5)
        assert org_row["metrics"]["bleu"]["n"] == 2
        assert org_row["metrics"]["bleu"]["ci_lower"] is not None
        assert org_row["samples_evaluated"] == 2
        assert org_row["generation_count"] == 2
        assert org_row["evaluation_count"] == 1
        assert org_row["last_evaluated"] is not None
        assert org_row["is_public"] is False
        pub_row = by_id[p_pub.id]
        assert pub_row["is_public"] is True
        assert pub_row["metrics"]["rouge_l"]["mean"] == pytest.approx(0.5)
        # bleu is carried by both projects → first; rouge_l by one → second.
        assert body["available_metrics"] == ["bleu", "rouge_l"]
        assert body["filters"] == {"period": "overall"}
        assert body["computed_at"] is not None

    async def test_org_member_sees_own_org_and_public_not_foreign_org(
        self, async_test_client, committed_live_seed
    ):
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        member = seed.seed_user(session, is_superadmin=False)
        org = seed.seed_org(session, "Mine")
        foreign = seed.seed_org(session, "Foreign")
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        m = _membership(session, member, org)

        p_mine = _seed_project(seed, session, admin, org, title="Mine")
        p_foreign = _seed_project(seed, session, admin, foreign, title="Foreign")
        p_pub = _seed_project(
            seed, session, admin, org, title="Public", link_org=False, is_public=True
        )
        for p in (p_mine, p_foreign, p_pub):
            seed.seed_completed_eval(
                session, p, admin.id, model_id=model_id,
                metric_values=[{"bleu": 0.5}],
            )
        session.commit()
        try:
            with _as_user(member):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models/{model_id}/projects"
                )
            assert resp.status_code == 200, resp.text
            ids = {p["project_id"] for p in resp.json()["projects"]}
            assert ids == {p_mine.id, p_pub.id}
        finally:
            session.delete(m)
            session.commit()

    async def test_anonymous_sees_public_only(
        self, async_test_client, committed_live_seed
    ):
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        p_org = _seed_project(seed, session, admin, org, title="Org only")
        p_pub = _seed_project(
            seed, session, admin, org, title="Public", link_org=False, is_public=True
        )
        for p in (p_org, p_pub):
            seed.seed_completed_eval(
                session, p, admin.id, model_id=model_id,
                metric_values=[{"bleu": 0.5}],
            )
        session.commit()

        # No auth override, no token → get_current_user yields None.
        resp = await async_test_client.get(
            f"{BASE}/llm-models/{model_id}/projects"
        )
        assert resp.status_code == 200, resp.text
        ids = {p["project_id"] for p in resp.json()["projects"]}
        assert ids == {p_pub.id}

    async def test_user_without_accessible_projects_gets_nothing(
        self, async_test_client, committed_live_seed
    ):
        """Pins the empty-scope guard: an empty accessible list must not be
        passed to the run lookup (which treats [] as "every project")."""
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        outsider = seed.seed_user(session, is_superadmin=False)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        p_org = _seed_project(seed, session, admin, org, title="Org only")
        seed.seed_completed_eval(
            session, p_org, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.5}],
        )
        session.commit()

        # Sanity: the data is there for someone who may read it.
        with _as_user(admin):
            ok = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects"
            )
        assert {p["project_id"] for p in ok.json()["projects"]} >= {p_org.id}

        with _as_user(outsider):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects"
            )
        assert resp.status_code == 200, resp.text
        # Public projects of other tests may exist; the org project must not.
        ids = {p["project_id"] for p in resp.json()["projects"]}
        assert p_org.id not in ids

    async def test_empty_accessible_scope_short_circuits(
        self, async_test_client, committed_live_seed
    ):
        """With the ACL returning NO projects the handler must answer [] even
        though data for the model exists (an empty project filter must never
        widen to "every project")."""
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        p_org = _seed_project(seed, session, admin, org, title="Org only")
        seed.seed_completed_eval(
            session, p_org, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.5}],
        )
        session.commit()

        with patch(
            "routers.leaderboards.get_accessible_project_ids_async",
            AsyncMock(return_value=[]),
        ):
            with _as_user(admin):
                resp = await async_test_client.get(
                    f"{BASE}/llm-models/{model_id}/projects"
                )
        assert resp.status_code == 200, resp.text
        assert resp.json()["projects"] == []


@pytest.mark.integration
class TestModelProjectScoresModelVisibility:
    async def test_private_custom_model_404s_public_custom_200s(
        self, async_test_client, async_test_db
    ):
        """For a caller who may NOT see the custom model (not creator, not
        superadmin, not in a shared org) a private custom model 404s while a
        public one is readable."""
        admin = await _make_user(async_test_db, is_superadmin=False)
        private_id = f"custom-priv-{_uid()[:8]}"
        public_id = f"custom-pub-{_uid()[:8]}"
        await _make_llm_model(
            async_test_db, private_id, is_official=False, is_public=False
        )
        await _make_llm_model(
            async_test_db, public_id, is_official=False, is_public=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            priv = await async_test_client.get(
                f"{BASE}/llm-models/{private_id}/projects"
            )
            pub = await async_test_client.get(
                f"{BASE}/llm-models/{public_id}/projects"
            )
        assert priv.status_code == 404
        assert pub.status_code == 200, pub.text
        assert pub.json()["projects"] == []

    async def test_private_custom_model_visible_to_its_creator(
        self, async_test_client, async_test_db
    ):
        """The model detail view follows /models visibility: the creator (and
        superadmins) of a private custom model may open it; a stranger still
        gets the existence-hiding 404."""
        from models import LLMModel

        owner = await _make_user(async_test_db, is_superadmin=False)
        stranger = await _make_user(async_test_db, is_superadmin=False)
        admin = await _make_user(async_test_db, is_superadmin=True)
        private_id = f"custom-own-{_uid()[:8]}"
        await _make_llm_model(
            async_test_db, private_id, is_official=False, is_public=False
        )
        row = (
            await async_test_db.execute(
                select(LLMModel).where(LLMModel.id == private_id)
            )
        ).scalar_one()
        row.created_by = owner.id
        await async_test_db.commit()

        with _as_user(owner):
            mine = await async_test_client.get(
                f"{BASE}/llm-models/{private_id}/projects"
            )
        with _as_user(admin):
            sa = await async_test_client.get(
                f"{BASE}/llm-models/{private_id}/projects"
            )
        with _as_user(stranger):
            other = await async_test_client.get(
                f"{BASE}/llm-models/{private_id}/projects"
            )
        anon = await async_test_client.get(
            f"{BASE}/llm-models/{private_id}/projects"
        )
        assert mine.status_code == 200, mine.text
        assert mine.json()["model_info"]["id"] == private_id
        assert sa.status_code == 200
        assert other.status_code == 404
        assert anon.status_code == 404

    async def test_unknown_model_id_detects_provider(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/claude-nonexistent-xyz/projects"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_info"]["id"] == "claude-nonexistent-xyz"
        assert body["model_info"]["provider"].lower() == "anthropic"
        assert body["projects"] == []
        assert body["available_metrics"] == []

    async def test_model_id_with_slash_routes_to_both_endpoints(
        self, async_test_client, committed_live_seed
    ):
        """Catalog ids like `deepseek-ai/DeepSeek-V4-Pro` contain a slash.
        The Next proxy and uvicorn decode `%2F` before routing, so the
        per-model routes must accept a raw slash (`{model_id:path}`), and
        the projects route must not be swallowed by the details route."""
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        model_id = f"vendor-{_uid()[:6]}/Model-{_uid()[:6]}"
        seed.seed_model(session, model_id, "Slashed Model", provider="deepinfra")
        p = _seed_project(seed, session, admin, org, title="Slash")
        seed.seed_completed_eval(
            session, p, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.5}],
        )
        session.commit()

        with _as_user(admin):
            raw = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects"
            )
            encoded = await async_test_client.get(
                f"{BASE}/llm-models/{model_id.replace('/', '%2F')}/projects"
            )
            details = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}?project_ids={p.id}"
            )
        for resp in (raw, encoded):
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["model_info"]["id"] == model_id
            assert [r["project_id"] for r in body["projects"]] == [p.id]
        assert details.status_code == 200, details.text
        assert details.json()["model_info"]["name"] == "Slashed Model"

    async def test_rejects_unknown_period(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/gpt-4o/projects?period=yearly"
            )
        assert resp.status_code == 422


@pytest.mark.integration
class TestModelProjectScoresAggregation:
    async def test_weekly_period_drops_old_run(
        self, async_test_client, committed_live_seed
    ):
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        p_old = _seed_project(seed, session, admin, org, title="Old")
        p_new = _seed_project(seed, session, admin, org, title="New")
        er_old = seed.seed_completed_eval(
            session, p_old, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.5}],
        )
        er_old.created_at = datetime.now(timezone.utc) - timedelta(days=10)
        seed.seed_completed_eval(
            session, p_new, admin.id, model_id=model_id,
            metric_values=[{"bleu": 0.7}],
        )
        session.commit()

        with _as_user(admin):
            overall = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects?period=overall"
            )
            weekly = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects?period=weekly"
            )
        assert {p["project_id"] for p in overall.json()["projects"]} == {
            p_old.id, p_new.id,
        }
        assert {p["project_id"] for p in weekly.json()["projects"]} == {p_new.id}
        assert weekly.json()["filters"] == {"period": "weekly"}

    async def test_grade_points_are_lifted_from_details(
        self, async_test_client, committed_live_seed
    ):
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        model_id = f"gpt-mp-{_uid()[:8]}"
        seed.seed_model(session, model_id)
        p = _seed_project(seed, session, admin, org, title="Falloesung")
        seed.seed_completed_eval(
            session, p, admin.id, model_id=model_id,
            metric_values=[
                {"llm_judge_falloesung": {"value": 0.5, "details": {"grade_points": 9}}},
                {"llm_judge_falloesung": {"value": 0.7, "details": {"grade_points": 13}}},
            ],
            eval_types=["llm_judge_falloesung"],
        )
        session.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/{model_id}/projects"
            )
        assert resp.status_code == 200, resp.text
        row = next(r for r in resp.json()["projects"] if r["project_id"] == p.id)
        assert row["metrics"]["llm_judge_falloesung"]["mean"] == pytest.approx(0.6)
        gp = row["metrics"]["llm_judge_falloesung_grade_points"]
        assert gp["mean"] == pytest.approx(11.0)
        assert gp["n"] == 2
        assert row["project_name"] == "Falloesung"

    async def test_model_without_generations_in_scope_is_empty(
        self, async_test_client, committed_live_seed
    ):
        """A model that exists but never generated in any accessible project
        short-circuits before the heavy scan and reports no projects."""
        seed, session = committed_live_seed
        admin = seed.seed_user(session, is_superadmin=True)
        org = seed.seed_org(session)
        other_model = f"gpt-mp-{_uid()[:8]}"
        idle_model = f"gpt-idle-{_uid()[:8]}"
        seed.seed_model(session, other_model)
        seed.seed_model(session, idle_model)
        p = _seed_project(seed, session, admin, org, title="Busy")
        seed.seed_completed_eval(
            session, p, admin.id, model_id=other_model,
            metric_values=[{"bleu": 0.5}],
        )
        session.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/llm-models/{idle_model}/projects"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["projects"] == []

