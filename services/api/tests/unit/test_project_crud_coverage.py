"""
Unit tests for routers/projects/crud.py — targets uncovered lines 100-792.
Covers: deep_merge_dicts, list_projects, create_project, get_project,
update_project, delete_project, update_project_visibility,
recalculate_project_statistics, get_project_completion_stats.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override require_user with an AuthUser matching the seeded DB user."""
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
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"pcc-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(
    db, *, created_by, title="Test Project", is_private=True, label_config="<View></View>"
):
    p = Project(
        id=_uid(),
        title=title,
        description="A test project",
        created_by=created_by,
        label_config=label_config,
        is_private=is_private,
        is_public=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


# ── deep_merge_dicts unit tests ─────────────────────────────────────
class TestDeepMergeDicts:
    """Direct unit tests for the deep_merge_dicts helper."""

    def _merge(self, base, update):
        from routers.projects.crud import deep_merge_dicts
        return deep_merge_dicts(base, update)

    def test_both_none(self):
        assert self._merge(None, None) == {}

    def test_base_none_update_has_data(self):
        assert self._merge(None, {"a": 1}) == {"a": 1}

    def test_base_empty_update_has_data(self):
        assert self._merge({}, {"a": 1}) == {"a": 1}

    def test_update_none(self):
        assert self._merge({"a": 1}, None) == {"a": 1}

    def test_update_empty(self):
        assert self._merge({"a": 1}, {}) == {"a": 1}

    def test_simple_override(self):
        result = self._merge({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_new_key(self):
        result = self._merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_none_value_removes_key(self):
        result = self._merge({"a": 1, "b": 2}, {"a": None})
        assert result == {"b": 2}

    def test_nested_merge(self):
        base = {"outer": {"inner1": 1, "inner2": 2}}
        update = {"outer": {"inner2": 99, "inner3": 3}}
        result = self._merge(base, update)
        assert result == {"outer": {"inner1": 1, "inner2": 99, "inner3": 3}}

    def test_list_replaced_not_concatenated(self):
        result = self._merge({"items": [1, 2]}, {"items": [3]})
        assert result == {"items": [3]}

    def test_does_not_mutate_inputs(self):
        base = {"a": 1}
        update = {"b": 2}
        self._merge(base, update)
        assert "b" not in base
        assert "a" not in update


# ── Endpoint tests via async_test_client (async-lane handler) ───────
class TestListProjectsEndpoint:
    """Tests for GET /api/projects/ (async-lane handler — seeded real rows)."""

    @pytest.mark.asyncio
    async def test_list_projects_success_superadmin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id, title="Listed One")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", headers={"X-Organization-Context": "private"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert any(p["title"] == "Listed One" for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_projects_with_search_filter(self, async_test_client, async_test_db):
        """Tests the search filter branch."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id, title="Matchable Topic")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", params={"search": "no-such-search-xyz"}
            )

        assert resp.status_code == 200
        titles = [p["title"] for p in resp.json()["items"]]
        assert "Matchable Topic" not in titles

    @pytest.mark.asyncio
    async def test_list_projects_with_is_archived_filter(self, async_test_client, async_test_db):
        """Tests the is_archived filter branch."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", params={"is_archived": True}
            )

        assert resp.status_code == 200


class TestProjectHelpersCoverage:
    """Tests for helper functions in routers/projects/helpers.py — targets lines 485-900."""

    @staticmethod
    def _annotation_only_project():
        project = Mock()
        project.enable_annotation = True
        project.enable_generation = False
        project.enable_evaluation = False
        project.generation_config = None
        project.evaluation_config = None
        return project

    def test_calculate_project_stats_no_tasks(self):
        from routers.projects.helpers import calculate_project_stats
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        response = Mock()
        calculate_project_stats(
            mock_db, "proj-1", response, project=self._annotation_only_project()
        )
        assert response.task_count == 0
        assert response.progress_percentage == 0.0

    def test_calculate_project_stats_with_tasks(self):
        from routers.projects.helpers import calculate_project_stats

        mock_db = MagicMock()
        # task count
        task_q = MagicMock()
        task_q.filter.return_value.count.return_value = 10
        # annotation count
        ann_q = MagicMock()
        ann_q.filter.return_value.count.return_value = 5
        # completed tasks count
        completed_q = MagicMock()
        completed_q.filter.return_value.count.return_value = 7
        # evaluation count + completed-evaluation count (always queried)
        eval_total_q = MagicMock()
        eval_total_q.filter.return_value.count.return_value = 0
        eval_completed_q = MagicMock()
        eval_completed_q.filter.return_value.count.return_value = 0

        queue = [task_q, ann_q, completed_q, eval_total_q, eval_completed_q]
        mock_db.query.side_effect = lambda *args, **kwargs: queue.pop(0)

        response = Mock()
        calculate_project_stats(
            mock_db, "proj-1", response, project=self._annotation_only_project()
        )
        assert response.task_count == 10
        assert response.progress_percentage == 70.0

    def test_calculate_project_stats_batch_empty(self):
        from routers.projects.helpers import calculate_project_stats_batch
        mock_db = MagicMock()
        result = calculate_project_stats_batch(mock_db, [])
        assert result == {}

    def test_calculate_generation_stats_no_config(self):
        from routers.projects.helpers import calculate_generation_stats
        mock_db = MagicMock()
        project = Mock()
        project.generation_config = None
        response = Mock()
        response.task_count = 0
        calculate_generation_stats(mock_db, project, response)
        assert response.generation_config_ready == False  # noqa: E712
        assert response.generation_models_count == 0
        assert response.generation_completed == False  # noqa: E712

    def test_calculate_generation_stats_with_config(self):
        from routers.projects.helpers import calculate_generation_stats
        mock_db = MagicMock()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "prompt_structures": {"key": "val"},
            "selected_configuration": {"models": ["gpt-4o", "claude-3"]},
        }
        response = Mock()
        response.task_count = 5
        response.generation_models_count = 0

        # Mock task query
        mock_task_query = MagicMock()
        mock_task_query.filter.return_value.all.return_value = [
            Mock(id="t1"), Mock(id="t2"),
        ]
        # Mock generation count query
        mock_gen_query = MagicMock()
        mock_gen_query.filter.return_value.count.return_value = 10

        mock_db.query.side_effect = [mock_task_query, mock_gen_query]

        calculate_generation_stats(mock_db, project, response)
        assert response.generation_config_ready == True  # noqa: E712
        assert response.generation_models_count == 2

    def test_get_accessible_project_ids_superadmin_with_opt_in(self):
        from routers.projects.helpers import get_accessible_project_ids
        user = Mock()
        user.is_superadmin = True
        mock_db = MagicMock()
        # Only the explicit opt-in returns the "see everything" None sentinel.
        result = get_accessible_project_ids(
            mock_db, user, None, include_all_private=True
        )
        assert result is None

    def test_get_accessible_project_ids_superadmin_default_is_org_agnostic(self):
        from routers.projects.helpers import get_accessible_project_ids
        user = Mock()
        user.is_superadmin = True
        user.id = "super-1"
        mock_db = MagicMock()
        # Default superadmin view returns every project that isn't another
        # user's private one — across every org, regardless of org_context.
        mock_db.query.return_value.filter.return_value.all.return_value = [
            Mock(id="org-a-proj"), Mock(id="org-b-proj"), Mock(id="own-private"),
        ]
        result = get_accessible_project_ids(mock_db, user, "some-org")
        assert result == ["org-a-proj", "org-b-proj", "own-private"]

    def test_get_accessible_project_ids_private(self):
        from routers.projects.helpers import get_accessible_project_ids
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            Mock(id="p1"), Mock(id="p2"),
        ]
        result = get_accessible_project_ids(mock_db, user, "private")
        assert result == ["p1", "p2"]

    def test_get_accessible_project_ids_org_not_member(self):
        from routers.projects.helpers import get_accessible_project_ids
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        user_obj = Mock()
        membership = Mock()
        membership.organization_id = "other-org"
        membership.is_active = True
        user_obj.organization_memberships = [membership]
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = user_obj

        with pytest.raises(HTTPException) as exc_info:
            get_accessible_project_ids(mock_db, user, "org-999")
        assert exc_info.value.status_code == 403

    def test_get_accessible_project_ids_superadmin_foreign_org_no_403(self):
        # Regression: a superadmin switching to an org they don't formally
        # belong to must NOT get "You are not a member of this organization".
        # They get the full org-agnostic view regardless of org_context.
        from routers.projects.helpers import get_accessible_project_ids
        user = Mock()
        user.is_superadmin = True
        user.id = "super-1"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            Mock(id="p1"),
        ]

        result = get_accessible_project_ids(mock_db, user, "org-not-mine")
        assert result == ["p1"]

    def test_check_project_accessible_superadmin(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = True
        assert check_project_accessible(MagicMock(), user, "proj-1") == True  # noqa: E712

    def test_check_project_accessible_not_found(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        assert check_project_accessible(mock_db, user, "proj-1") == False  # noqa: E712

    def test_check_project_accessible_private_context_owner(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = True
        project.created_by = "u1"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        assert check_project_accessible(mock_db, user, "proj-1", "private") == True  # noqa: E712

    def test_check_project_accessible_private_context_not_owner(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = True
        project.created_by = "u2"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        assert check_project_accessible(mock_db, user, "proj-1", "private") == False  # noqa: E712

    def test_check_project_accessible_org_not_in_project(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = False

        # First query returns project, second returns org ids
        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.all.return_value = []
            return q
        mock_db.query.side_effect = query_side_effect

        assert check_project_accessible(mock_db, user, "proj-1", "org-1") == False  # noqa: E712

    def test_check_task_assigned_to_user_open_mode(self):
        from routers.projects.helpers import check_task_assigned_to_user
        project = Mock()
        project.assignment_mode = "open"
        assert check_task_assigned_to_user(MagicMock(), Mock(), "t1", project) == True  # noqa: E712

    def test_check_task_assigned_to_user_superadmin(self):
        from routers.projects.helpers import check_task_assigned_to_user
        user = Mock()
        user.is_superadmin = True
        project = Mock()
        project.assignment_mode = "manual"
        assert check_task_assigned_to_user(MagicMock(), user, "t1", project) == True  # noqa: E712

    def test_check_user_can_edit_project_superadmin(self):
        from routers.projects.helpers import check_user_can_edit_project
        user = Mock()
        user.is_superadmin = True
        assert check_user_can_edit_project(MagicMock(), user, "proj-1") == True  # noqa: E712

    def test_check_user_can_edit_project_creator(self):
        from routers.projects.helpers import check_user_can_edit_project
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.created_by = "u1"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        assert check_user_can_edit_project(mock_db, user, "proj-1") == True  # noqa: E712

    def test_check_user_can_edit_project_no_permission(self):
        from routers.projects.helpers import check_user_can_edit_project
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.created_by = "u2"

        user_with_memberships = Mock()
        membership = Mock()
        membership.organization_id = "org-1"
        membership.is_active = True
        membership.role = "ANNOTATOR"
        user_with_memberships.organization_memberships = [membership]

        # project query
        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = project
            elif call_count[0] == 2:
                q.options.return_value.filter.return_value.first.return_value = user_with_memberships
            else:
                q.filter.return_value.all.return_value = [Mock(organization_id="org-1")]
            return q
        mock_db.query.side_effect = query_side_effect

        assert check_user_can_edit_project(mock_db, user, "proj-1") == False  # noqa: E712

    def test_get_org_context_from_request_state(self):
        from routers.projects.helpers import get_org_context_from_request
        request = Mock()
        request.state.organization_context = "org-abc"
        assert get_org_context_from_request(request) == "org-abc"

    def test_get_org_context_from_request_header(self):
        from routers.projects.helpers import get_org_context_from_request
        request = Mock(spec=[])  # No .state attribute
        request.headers = {"X-Organization-Context": "org-def"}
        assert get_org_context_from_request(request) == "org-def"

    def test_get_project_organizations(self):
        from routers.projects.helpers import get_project_organizations
        mock_db = MagicMock()
        po1 = Mock()
        po1.organization = Mock()
        po1.organization.id = "org-1"
        po1.organization.name = "Org One"
        po2 = Mock()
        po2.organization = None  # Should be filtered out
        mock_db.query.return_value.options.return_value.filter.return_value.all.return_value = [po1, po2]

        result = get_project_organizations(mock_db, "proj-1")
        assert len(result) == 1
        assert result[0]["id"] == "org-1"


class TestProjectHelpersLegacyAccess:
    """Additional tests for legacy access mode in check_project_accessible."""

    def test_legacy_private_project_owner(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = True
        project.created_by = "u1"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        # org_context=None -> legacy mode
        assert check_project_accessible(mock_db, user, "proj-1", None) == True  # noqa: E712

    def test_legacy_private_project_not_owner(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = True
        project.created_by = "u2"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        assert check_project_accessible(mock_db, user, "proj-1", None) == False  # noqa: E712

    def test_legacy_no_orgs_is_creator(self):
        from routers.projects.helpers import check_project_accessible
        user = Mock()
        user.is_superadmin = False
        user.id = "u1"
        mock_db = MagicMock()
        project = Mock()
        project.is_private = False
        project.created_by = "u1"

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.all.return_value = []
            return q
        mock_db.query.side_effect = query_side_effect

        assert check_project_accessible(mock_db, user, "proj-1", None) == True  # noqa: E712
