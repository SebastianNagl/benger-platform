"""Unit tests for the /api/runs single-run inventory router.

Covers the pure metadata-extraction helpers and the permission-filtering /
404 / 403 branches of the (async) handlers. The router was migrated to the
async DB lane, so the handler-level tests call the coroutine handlers with a
real ``async_test_db`` AsyncSession (seeding the rows they need) and patch the
async access helper to drive the accessibility branch — ``db.query`` Mocks no
longer model the ``await db.execute(...)`` surface the handlers use.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from auth_module.models import User as AuthUser
from models import ResponseGeneration, User
from project_models import Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _auth_user(is_superadmin: bool = False, user_id: str = "u1"):
    return AuthUser(
        id=user_id,
        username="runs-unit",
        email="runs-unit@test.com",
        name="Runs Unit",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_request():
    request = Mock()
    request.state.organization_context = "private"
    return request


async def _seed_user(db):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Runs Unit User",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, creator):
    proj = Project(
        id=_uid(),
        title=f"Runs Unit {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(proj)
    await db.flush()
    return proj


async def _seed_generation(db, project, *, model_id="gpt-4o", status="completed"):
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=1,
        data={"text": "t"},
        created_by=project.created_by,
        updated_by=project.created_by,
    )
    db.add(task)
    await db.flush()
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id,
        model_id=model_id,
        status=status,
        created_by=project.created_by,
    )
    db.add(rg)
    await db.flush()
    return rg


# ---------------------------------------------------------------------------
# list_runs — permission filtering
# ---------------------------------------------------------------------------


class TestListRunsPermissionFilter:
    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible_async")
    @patch("routers.runs.get_org_context_from_request")
    async def test_evaluation_tab_filters_inaccessible_projects(
        self, mock_org_ctx, mock_access, async_test_db
    ):
        """Non-superadmin must not see runs from projects they can't access."""
        from routers.runs import list_runs

        mock_org_ctx.return_value = "private"

        from models import EvaluationRun

        creator = await _seed_user(async_test_db)
        proj_a = await _seed_project(async_test_db, creator)
        proj_b = await _seed_project(async_test_db, creator)
        er_a = EvaluationRun(
            id=_uid(),
            project_id=proj_a.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"accuracy": 0.9},
            status="completed",
            samples_evaluated=5,
            eval_metadata={"evaluation_configs": [{"metric": "accuracy"}]},
            created_by=creator.id,
        )
        er_b = EvaluationRun(
            id=_uid(),
            project_id=proj_b.id,
            model_id="gpt-4o",
            evaluation_type_ids=["accuracy"],
            metrics={"accuracy": 0.9},
            status="completed",
            samples_evaluated=5,
            eval_metadata={"evaluation_configs": [{"metric": "accuracy"}]},
            created_by=creator.id,
        )
        async_test_db.add_all([er_a, er_b])
        await async_test_db.commit()

        # User can access proj_a; proj_b is forbidden.
        async def _access(db, user, pid, ctx):
            return pid == proj_a.id

        mock_access.side_effect = _access

        resp = await list_runs(
            request=_make_request(),
            type="evaluation",
            project_id=None,
            status_filter=None,
            page=1,
            page_size=200,
            current_user=_auth_user(is_superadmin=False),
            db=async_test_db,
        )

        item_ids = {it.id for it in resp.items}
        assert er_a.id in item_ids
        assert er_b.id not in item_ids

    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible_async")
    @patch("routers.runs.get_org_context_from_request")
    async def test_generation_tab_filters_inaccessible_projects(
        self, mock_org_ctx, mock_access, async_test_db
    ):
        from routers.runs import list_runs

        mock_org_ctx.return_value = "private"

        creator = await _seed_user(async_test_db)
        proj_a = await _seed_project(async_test_db, creator)
        proj_b = await _seed_project(async_test_db, creator)
        gen_a = await _seed_generation(async_test_db, proj_a)
        gen_b = await _seed_generation(async_test_db, proj_b)
        await async_test_db.commit()

        async def _access(db, user, pid, ctx):
            return pid == proj_a.id

        mock_access.side_effect = _access

        resp = await list_runs(
            request=_make_request(),
            type="generation",
            project_id=None,
            status_filter=None,
            page=1,
            page_size=200,
            current_user=_auth_user(is_superadmin=False),
            db=async_test_db,
        )

        item_ids = {it.id for it in resp.items}
        assert gen_a.id in item_ids
        assert gen_b.id not in item_ids


# ---------------------------------------------------------------------------
# get_generation_run — 403 on inaccessible project / 404 on missing
# ---------------------------------------------------------------------------


class TestGetGenerationRunPermission:
    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible_async", return_value=False)
    @patch("routers.runs.get_org_context_from_request", return_value="private")
    async def test_returns_403_when_project_inaccessible(
        self, _mock_ctx, _mock_access, async_test_db
    ):
        from fastapi import HTTPException

        from routers.runs import get_generation_run

        creator = await _seed_user(async_test_db)
        proj = await _seed_project(async_test_db, creator)
        rg = await _seed_generation(async_test_db, proj)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_generation_run(
                generation_id=rg.id,
                request=_make_request(),
                current_user=_auth_user(is_superadmin=False),
                db=async_test_db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_404_when_generation_missing(self, async_test_db):
        from fastapi import HTTPException

        from routers.runs import get_generation_run

        with pytest.raises(HTTPException) as exc:
            await get_generation_run(
                generation_id="missing-" + _uid(),
                request=_make_request(),
                current_user=_auth_user(),
                db=async_test_db,
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Helpers — judge model + metric extraction (pure, no DB)
# ---------------------------------------------------------------------------


class TestExtractJudgeModels:
    def test_extracts_from_new_judges_shape(self):
        from routers.runs import _extract_judge_models

        meta = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_classic",
                    "metric_parameters": {
                        "judges": [
                            {"judge_model_id": "gpt-4o", "runs": 2},
                            {"judge_model_id": "claude-3-7", "runs": 1},
                        ]
                    },
                }
            ]
        }
        assert _extract_judge_models(meta) == ["gpt-4o", "claude-3-7"]

    def test_falls_back_to_legacy_judge_model(self):
        from routers.runs import _extract_judge_models

        meta = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_falloesung",
                    "metric_parameters": {"judge_model": "gpt-4o-mini"},
                }
            ]
        }
        assert _extract_judge_models(meta) == ["gpt-4o-mini"]

    def test_dedupes_across_configs(self):
        from routers.runs import _extract_judge_models

        meta = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_helpfulness",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4o", "runs": 1}]
                    },
                },
                {
                    "metric": "llm_judge_correctness",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4o", "runs": 1}]
                    },
                },
            ]
        }
        assert _extract_judge_models(meta) == ["gpt-4o"]

    def test_empty_metadata_returns_empty(self):
        from routers.runs import _extract_judge_models

        assert _extract_judge_models(None) == []
        assert _extract_judge_models({}) == []
        assert _extract_judge_models({"evaluation_configs": []}) == []
