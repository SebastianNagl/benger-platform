"""
Unit tests for routers/dashboard.py to increase branch coverage.
Covers dashboard stats with different org contexts and user types.

The dashboard handler was migrated to the async DB lane (Depends(get_async_db),
AsyncSession). These tests therefore drive an httpx AsyncClient and override
`get_async_db` with a lightweight async session double. `get_accessible_project_ids`
stays sync (it lives in the off-limits projects/helpers.py) and is reached via
`db.run_sync(...)`, so the double's `run_sync` invokes the passed callable with a
dummy sync session — letting the existing `patch(...get_accessible_project_ids)`
shims keep working unchanged.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from auth_module.models import User
from database import get_async_db
from auth_module.dependencies import require_user


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_async_db(scalar_value=None):
    """An async-session double.

    - `await db.execute(...)` -> a result whose `.scalar()` returns
      `scalar_value` (used by the superadmin `SELECT COUNT(*) FROM projects`
      backstop and the live-count fallbacks).
    - `await db.run_sync(fn)` -> `fn(<dummy sync session>)`, so the handler's
      `db.run_sync(lambda sync_db: get_accessible_project_ids(sync_db, ...))`
      resolves through the patched `get_accessible_project_ids`.
    """
    mock_db = MagicMock()

    result = MagicMock()
    result.scalar.return_value = scalar_value
    result.all.return_value = []
    result.first.return_value = None

    async def _execute(*_args, **_kwargs):
        return result

    async def _run_sync(fn, *args, **kwargs):
        return fn(Mock(), *args, **kwargs)

    mock_db.execute = _execute
    mock_db.run_sync = _run_sync
    return mock_db


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")



@pytest.fixture(autouse=True)
def _overview_view():
    """These tests drive the overview of the dashboard (teachers and admins);
    the personal view of annotators is covered by
    tests/integration/test_dashboard_personal_view.py."""
    with patch("routers.dashboard.sees_overview_async", AsyncMock(return_value=True)):
        yield


class TestDashboardStats:
    @pytest.mark.asyncio
    async def test_cached_stats(self):
        user = _make_user()
        mock_db = _mock_async_db()
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        try:
            with patch("routers.dashboard.cache") as mock_cache:
                mock_cache.get.return_value = {
                    "project_count": 5,
                    "task_count": 100,
                    "annotation_count": 50,
                    "projects_with_generations": 3,
                    "projects_with_evaluations": 2,
                }
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 5
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_no_accessible_projects(self):
        user = _make_user(is_superadmin=False)
        mock_db = _mock_async_db()
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=[]):
                mock_cache.get.return_value = None
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_superadmin_all_projects(self):
        user = _make_user(is_superadmin=True)
        # New code path: dashboard reads via `read_dashboard_sum_async`. The
        # superadmin branch also fires a `SELECT COUNT(*) FROM projects`
        # scalar to backstop the precomputed project_count.
        mock_db = _mock_async_db(scalar_value=10)

        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=None), \
                 patch("routers.dashboard.read_dashboard_sum_async") as mock_sums, \
                 patch("routers.dashboard._live_evaluations_count_async", return_value=3):
                mock_cache.get.return_value = None

                async def _sums(*_a, **_k):
                    return {
                        "project_count": 10, "total_tasks": 200, "labeled_tasks": 100,
                        "annotations_count": 100, "generations_count": 5,
                        "response_generations_count": 8, "evaluation_pairs_count": 3,
                    }

                mock_sums.side_effect = _sums
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 10
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_scoped_to_org(self):
        user = _make_user(is_superadmin=False)
        mock_db = _mock_async_db()

        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=["p-1", "p-2"]), \
                 patch("routers.dashboard.read_dashboard_sum_async") as mock_sums, \
                 patch("routers.dashboard._live_evaluations_count_async", return_value=1):
                mock_cache.get.return_value = None

                async def _sums(*_a, **_k):
                    return {
                        "project_count": 3, "total_tasks": 50, "labeled_tasks": 30,
                        "annotations_count": 20, "generations_count": 2,
                        "response_generations_count": 3, "evaluation_pairs_count": 1,
                    }

                mock_sums.side_effect = _sums
                async with await _client() as client:
                    resp = await client.get(
                        "/api/dashboard/stats",
                    )
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 3
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_db_error_returns_503(self):
        user = _make_user()
        mock_db = _mock_async_db()
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", side_effect=Exception("DB down")):
                mock_cache.get.return_value = None
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 503
                assert "project_count" not in resp.json()
                mock_cache.set.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_statement_timeout_on_empty_summaries_is_not_zeros(self):
        """Regression: empty project_summaries + live fallback past the timeout.

        On the dev stack project_summaries was empty (no beat), so the
        handler fell back to the live scored-pairs count over all of
        task_evaluations, which ran into Postgres' statement_timeout. The
        handler then answered 200 with every counter at 0 while 48 projects
        existed. A live count that still fails (for the projects without a
        summary row) must answer an error and cache nothing instead.
        """
        from sqlalchemy.exc import OperationalError

        user = _make_user(is_superadmin=True)
        mock_db = _mock_async_db(scalar_value=48)
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        empty_summaries = {
            "project_count": 0,
            "total_tasks": 0,
            "annotations_count": 0,
            "generations_count": 0,
            "evaluation_pairs_count": 0,
        }

        async def _timed_out(*_args, **_kwargs):
            raise OperationalError(
                "SELECT DISTINCT ...",
                {},
                Exception("canceling statement due to statement timeout"),
            )

        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=None), \
                 patch("routers.dashboard.read_dashboard_sum_async", return_value=empty_summaries), \
                 patch("routers.dashboard.unsummarized_project_ids_async", return_value=["p-1"]), \
                 patch("routers.dashboard._live_evaluations_count_async", side_effect=_timed_out):
                mock_cache.get.return_value = None
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 503
                body = resp.json()
                assert "project_count" not in body
                assert body["detail"] == "Dashboard statistics are temporarily unavailable."
                mock_cache.set.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_summarized_projects_are_never_recounted_live(self):
        """Projects with a summary row are read from it, even when a counter
        sums to 0; only the live count of an empty set would run."""
        user = _make_user(is_superadmin=True)
        mock_db = _mock_async_db(scalar_value=2)
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        sums = {
            "project_count": 2, "total_tasks": 10, "annotations_count": 0,
            "generations_count": 0, "evaluation_pairs_count": 0,
        }
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=None), \
                 patch("routers.dashboard.read_dashboard_sum_async", return_value=sums), \
                 patch("routers.dashboard.unsummarized_project_ids_async", return_value=[]), \
                 patch("routers.dashboard._live_dashboard_counts_async") as live_counts, \
                 patch("routers.dashboard._live_evaluations_count_async") as live_evals:
                mock_cache.get.return_value = None
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json() == {
                    "scope": "overview",
                    "project_count": 2, "task_count": 10, "annotation_count": 0,
                    "projects_with_generations": 0, "projects_with_evaluations": 0,
                }
                live_counts.assert_not_called()
                live_evals.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_projects_without_summary_are_counted_live_and_added(self):
        user = _make_user(is_superadmin=False)
        mock_db = _mock_async_db()
        app.dependency_overrides[require_user] = lambda: user

        async def _override():
            yield mock_db

        app.dependency_overrides[get_async_db] = _override
        sums = {
            "project_count": 1, "total_tasks": 10, "annotations_count": 4,
            "generations_count": 3, "evaluation_pairs_count": 7,
        }

        async def _live_counts(_db, ids):
            assert ids == ["p-new"]
            return {"total_tasks": 2, "annotations_count": 1, "generations_count": 1}

        async def _live_evals(_db, ids):
            assert ids == ["p-new"]
            return 5

        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=["p-old", "p-new"]), \
                 patch("routers.dashboard.read_dashboard_sum_async", return_value=sums), \
                 patch("routers.dashboard.unsummarized_project_ids_async", return_value=["p-new"]), \
                 patch("routers.dashboard._live_dashboard_counts_async", side_effect=_live_counts), \
                 patch("routers.dashboard._live_evaluations_count_async", side_effect=_live_evals):
                mock_cache.get.return_value = None
                async with await _client() as client:
                    resp = await client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json() == {
                    "scope": "overview",
                    "project_count": 2, "task_count": 12, "annotation_count": 5,
                    "projects_with_generations": 4, "projects_with_evaluations": 12,
                }
        finally:
            app.dependency_overrides.clear()
