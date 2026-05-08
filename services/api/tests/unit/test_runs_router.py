"""Unit tests for the /api/runs single-run inventory router.

Covers permission filtering (non-superadmin must not see runs from
projects they can't access), generation/evaluation tab shapes, and
the linked-evaluations expansion on the generation detail endpoint.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest


def _make_user(is_superadmin: bool = False, user_id: str = "u1"):
    user = Mock()
    user.id = user_id
    user.is_superadmin = is_superadmin
    return user


def _make_request():
    request = Mock()
    request.state.organization_context = "private"
    return request


def _gen_row(rid: str, project_id: str, model_id: str = "gpt-4o"):
    g = Mock()
    g.id = rid
    g.project_id = project_id
    g.model_id = model_id
    g.task_id = None
    g.structure_key = None
    g.status = "completed"
    g.created_at = datetime.now(timezone.utc)
    g.completed_at = datetime.now(timezone.utc)
    g.created_by = "u1"
    g.error_message = None
    g.runs_requested = 1
    g.runs_completed = 1
    g.runs_failed = 0
    return g


def _eval_row(rid: str, project_id: str):
    e = Mock()
    e.id = rid
    e.project_id = project_id
    e.model_id = "gpt-4o"
    e.status = "completed"
    e.created_at = datetime.now(timezone.utc)
    e.completed_at = datetime.now(timezone.utc)
    e.created_by = "u1"
    e.error_message = None
    e.samples_evaluated = 13
    e.eval_metadata = {
        "evaluation_configs": [{"metric": "llm_judge_classic", "metric_parameters": {}}],
    }
    return e


# ---------------------------------------------------------------------------
# list_runs — permission filtering
# ---------------------------------------------------------------------------


class TestListRunsPermissionFilter:
    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible")
    @patch("routers.runs.get_org_context_from_request")
    async def test_evaluation_tab_filters_inaccessible_projects(
        self, mock_org_ctx, mock_access
    ):
        """Non-superadmin must not see runs from projects they can't access."""
        from routers.runs import list_runs

        mock_org_ctx.return_value = "private"
        # User can access project-A; project-B is forbidden.
        mock_access.side_effect = lambda db, user, pid, ctx: pid == "project-A"

        accessible = _eval_row("eval-1", "project-A")
        forbidden = _eval_row("eval-2", "project-B")

        db = Mock()
        # First query: count(); second: paginated rows; third: project titles map.
        query_results = [
            ([accessible, forbidden],),  # .all() for eval rows
        ]
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 2
        mock_q.all.return_value = [accessible, forbidden]
        # The project titles map query that runs after permission filter
        # also goes through db.query(...).filter(...).all() — return [].
        mock_titles_q = MagicMock()
        mock_titles_q.filter.return_value = mock_titles_q
        mock_titles_q.all.return_value = []
        db.query.side_effect = [mock_q, mock_titles_q]

        resp = await list_runs(
            request=_make_request(),
            type="evaluation",
            project_id=None,
            status_filter=None,
            page=1,
            page_size=25,
            current_user=_make_user(is_superadmin=False),
            db=db,
        )

        # Total stays at the unfiltered count (the filter is applied in
        # Python after the DB pull) — but items must only contain the
        # accessible row.
        item_ids = {it.id for it in resp.items}
        assert "eval-1" in item_ids
        assert "eval-2" not in item_ids

    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible")
    @patch("routers.runs.get_org_context_from_request")
    async def test_generation_tab_filters_inaccessible_projects(
        self, mock_org_ctx, mock_access
    ):
        from routers.runs import list_runs

        mock_org_ctx.return_value = "private"
        mock_access.side_effect = lambda db, user, pid, ctx: pid == "project-A"

        accessible = _gen_row("gen-1", "project-A")
        forbidden = _gen_row("gen-2", "project-B")

        db = Mock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 2
        mock_q.all.return_value = [accessible, forbidden]
        mock_titles_q = MagicMock()
        mock_titles_q.filter.return_value = mock_titles_q
        mock_titles_q.all.return_value = []
        db.query.side_effect = [mock_q, mock_titles_q]

        resp = await list_runs(
            request=_make_request(),
            type="generation",
            project_id=None,
            status_filter=None,
            page=1,
            page_size=25,
            current_user=_make_user(is_superadmin=False),
            db=db,
        )

        item_ids = {it.id for it in resp.items}
        assert "gen-1" in item_ids
        assert "gen-2" not in item_ids


# ---------------------------------------------------------------------------
# get_generation_run — 403 on inaccessible project
# ---------------------------------------------------------------------------


class TestGetGenerationRunPermission:
    @pytest.mark.asyncio
    @patch("routers.runs.check_project_accessible", return_value=False)
    @patch("routers.runs.get_org_context_from_request", return_value="private")
    async def test_returns_403_when_project_inaccessible(self, *_):
        from fastapi import HTTPException

        from routers.runs import get_generation_run

        gen = _gen_row("gen-x", "project-Z")

        db = Mock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        with pytest.raises(HTTPException) as exc:
            await get_generation_run(
                generation_id="gen-x",
                request=_make_request(),
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_404_when_generation_missing(self):
        from fastapi import HTTPException

        from routers.runs import get_generation_run

        db = Mock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        with pytest.raises(HTTPException) as exc:
            await get_generation_run(
                generation_id="missing",
                request=_make_request(),
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Helpers — judge model + metric extraction
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
