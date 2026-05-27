"""
Extended unit tests for routers/projects/helpers.py covering business logic.
"""

from unittest.mock import MagicMock, Mock, patch


from routers.projects.helpers import (
    calculate_project_stats_batch,
    get_org_context_from_request,
)


class TestGetOrgContextFromRequest:
    """Tests for get_org_context_from_request."""

    def test_from_state(self):
        request = Mock()
        request.state.organization_context = "org-123"
        assert get_org_context_from_request(request) == "org-123"

    def test_from_header_when_no_state(self):
        request = Mock(spec=["headers"])
        del request.state
        request.headers = {"X-Organization-Context": "org-456"}
        assert get_org_context_from_request(request) == "org-456"

    def test_state_exists_but_no_org_context(self):
        request = Mock()
        del request.state.organization_context
        request.headers = {"X-Organization-Context": "org-789"}
        assert get_org_context_from_request(request) == "org-789"

    def test_none_when_no_context(self):
        request = Mock(spec=["headers"])
        del request.state
        request.headers = {}
        assert get_org_context_from_request(request) is None

    def test_private_context(self):
        request = Mock()
        request.state.organization_context = "private"
        assert get_org_context_from_request(request) == "private"

    def test_empty_string_context(self):
        request = Mock()
        request.state.organization_context = ""
        assert get_org_context_from_request(request) == ""


class TestCheckProjectAccessibleSuperadmin:
    """Tests for check_project_accessible - superadmin path."""

    def test_superadmin_always_accessible(self):
        from routers.projects.helpers import check_project_accessible

        db = Mock()
        user = Mock(is_superadmin=True)
        assert check_project_accessible(db, user, "proj-1") == True  # noqa: E712

    def test_superadmin_with_org_context(self):
        from routers.projects.helpers import check_project_accessible

        db = Mock()
        user = Mock(is_superadmin=True)
        assert check_project_accessible(db, user, "proj-1", org_context="org-1") == True  # noqa: E712

    def test_superadmin_with_private_context(self):
        from routers.projects.helpers import check_project_accessible

        db = Mock()
        user = Mock(is_superadmin=True)
        assert check_project_accessible(db, user, "proj-1", org_context="private") == True  # noqa: E712


class TestCheckProjectAccessibleNotFound:
    """Tests for check_project_accessible - project not found."""

    def test_project_not_found(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock(is_superadmin=False)
        assert check_project_accessible(db, user, "nonexistent") == False  # noqa: E712


class TestCheckProjectAccessiblePrivateContext:
    """Tests for check_project_accessible - private context."""

    def test_private_context_creator_access(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(is_private=True, created_by="user-1", id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project

        user = Mock(is_superadmin=False, id="user-1")
        assert check_project_accessible(db, user, "proj-1", org_context="private") == True  # noqa: E712

    def test_private_context_non_creator_denied(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(is_private=True, created_by="user-2", id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project

        user = Mock(is_superadmin=False, id="user-1")
        assert check_project_accessible(db, user, "proj-1", org_context="private") == False  # noqa: E712

    def test_private_context_non_private_project_denied(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(is_private=False, created_by="user-1", id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project

        user = Mock(is_superadmin=False, id="user-1")
        assert check_project_accessible(db, user, "proj-1", org_context="private") == False  # noqa: E712


class TestCheckProjectAccessibleLegacy:
    """Tests for check_project_accessible - legacy (None context)."""

    def test_legacy_private_project_creator(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(is_private=True, created_by="user-1", id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project

        user = Mock(is_superadmin=False, id="user-1")
        assert check_project_accessible(db, user, "proj-1", org_context=None) == True  # noqa: E712

    def test_legacy_private_project_non_creator(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(is_private=True, created_by="user-2", id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project

        user = Mock(is_superadmin=False, id="user-1")
        assert check_project_accessible(db, user, "proj-1", org_context=None) == False  # noqa: E712


class TestCheckTaskAssignedToUser:
    """Tests for check_task_assigned_to_user."""

    def test_open_mode_always_true(self):
        from routers.projects.helpers import check_task_assigned_to_user

        db = Mock()
        user = Mock(is_superadmin=False)
        project = Mock(assignment_mode="open")
        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

    def test_superadmin_always_true(self):
        from routers.projects.helpers import check_task_assigned_to_user

        db = Mock()
        user = Mock(is_superadmin=True)
        project = Mock(assignment_mode="manual")
        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

    def test_no_assignment_mode_defaults_to_open(self):
        from routers.projects.helpers import check_task_assigned_to_user

        db = Mock()
        user = Mock(is_superadmin=False)
        # assignment_mode defaults to "open"
        project = Mock(spec=[])
        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712


class TestCheckUserCanEditProject:
    """Tests for check_user_can_edit_project."""

    def test_superadmin_can_edit(self):
        from routers.projects.helpers import check_user_can_edit_project

        db = Mock()
        user = Mock(is_superadmin=True)
        assert check_user_can_edit_project(db, user, "proj-1") == True  # noqa: E712

    def test_creator_can_edit(self):
        from routers.projects.helpers import check_user_can_edit_project

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project
        assert check_user_can_edit_project(db, user, "proj-1") == True  # noqa: E712


class TestGetAccessibleProjectIds:
    """Tests for get_accessible_project_ids."""

    def test_superadmin_returns_none_when_include_all_private(self):
        from routers.projects.helpers import get_accessible_project_ids

        db = Mock()
        user = Mock(is_superadmin=True)
        # The unfiltered None sentinel is now an opt-in.
        result = get_accessible_project_ids(
            db, user, "org-1", include_all_private=True
        )
        assert result is None

    def test_private_context_returns_user_private_projects(self):
        from routers.projects.helpers import get_accessible_project_ids

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1")

        mock_rows = [Mock(id="proj-1"), Mock(id="proj-2")]
        db.query.return_value.filter.return_value.all.return_value = mock_rows

        result = get_accessible_project_ids(db, user, "private")
        assert result == ["proj-1", "proj-2"]

    def test_none_context_returns_private_projects(self):
        from routers.projects.helpers import get_accessible_project_ids

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.all.return_value = []

        result = get_accessible_project_ids(db, user, None)
        assert result == []


class TestPublicProjectHelpers:
    """Coverage for the is_public / public_role pathways in helpers."""

    def test_check_project_accessible_short_circuits_on_public(self):
        from routers.projects.helpers import check_project_accessible

        db = MagicMock()
        project = Mock(
            is_private=False,
            is_public=True,
            public_role="ANNOTATOR",
            created_by="creator-1",
            id="proj-pub",
        )
        db.query.return_value.filter.return_value.first.return_value = project

        # Visitor with no claim and a totally unrelated org context: still accessible.
        user = Mock(is_superadmin=False, id="visitor-1")
        assert (
            check_project_accessible(db, user, "proj-pub", org_context="other-org")
            is True
        )

    def test_get_effective_role_public_visitor_falls_back_to_public_role(self):
        from routers.projects.helpers import get_effective_project_role

        db = MagicMock()
        # No org memberships
        memberships_query = MagicMock()
        memberships_query.organization_memberships = []
        with patch(
            "routers.projects.helpers.get_user_with_memberships",
            return_value=memberships_query,
        ):
            project = Mock(
                id="proj-1",
                created_by="creator-1",
                is_public=True,
                public_role="CONTRIBUTOR",
            )
            user = Mock(is_superadmin=False, id="visitor-1")
            assert get_effective_project_role(db, user, project) == "CONTRIBUTOR"

    def test_get_effective_role_creator_is_org_admin(self):
        from routers.projects.helpers import get_effective_project_role

        db = MagicMock()
        project = Mock(
            id="proj-1",
            created_by="me",
            is_public=True,
            public_role="ANNOTATOR",
        )
        user = Mock(is_superadmin=False, id="me")
        assert get_effective_project_role(db, user, project) == "ORG_ADMIN"

    def test_get_effective_role_returns_none_for_private_visitor(self):
        from routers.projects.helpers import get_effective_project_role

        db = MagicMock()
        memberships_query = MagicMock()
        memberships_query.organization_memberships = []
        with patch(
            "routers.projects.helpers.get_user_with_memberships",
            return_value=memberships_query,
        ):
            project = Mock(
                id="proj-1",
                created_by="creator-1",
                is_public=False,
                public_role=None,
            )
            user = Mock(is_superadmin=False, id="visitor-1")
            assert get_effective_project_role(db, user, project) is None


class TestCalculateProjectStatsBatch:
    """Tests for calculate_project_stats_batch."""

    def test_empty_project_ids(self):
        db = Mock()
        result = calculate_project_stats_batch(db, [])
        assert result == {}


class TestCalculateGenerationStats:
    """Tests for calculate_generation_stats."""

    def test_no_generation_config(self):
        from routers.projects.helpers import calculate_generation_stats

        db = Mock()
        project = Mock(generation_config=None)
        response = Mock(task_count=10)

        calculate_generation_stats(db, project, response)

        assert response.generation_config_ready == False  # noqa: E712
        assert response.generation_prompts_ready == False  # noqa: E712
        assert response.generation_models_count == 0
        assert response.generation_completed == False  # noqa: E712

    def test_with_prompt_structures(self):
        from routers.projects.helpers import calculate_generation_stats

        db = Mock()
        project = Mock(
            generation_config={
                "prompt_structures": {"structure1": {}},
                "selected_configuration": {"models": ["gpt-4o", "claude-sonnet-4"]},
            }
        )
        response = Mock(task_count=0)

        calculate_generation_stats(db, project, response)

        assert response.generation_config_ready == True  # noqa: E712
        assert response.generation_prompts_ready == True  # noqa: E712
        assert response.generation_models_count == 2
        assert response.generation_completed == False  # noqa: E712

    def test_empty_prompt_structures(self):
        from routers.projects.helpers import calculate_generation_stats

        db = Mock()
        project = Mock(generation_config={"prompt_structures": {}})
        response = Mock(task_count=0)

        calculate_generation_stats(db, project, response)
        assert response.generation_config_ready == False  # noqa: E712

    def test_no_selected_configuration(self):
        from routers.projects.helpers import calculate_generation_stats

        db = Mock()
        project = Mock(generation_config={"prompt_structures": {"s1": {}}})
        response = Mock(task_count=5)

        calculate_generation_stats(db, project, response)
        assert response.generation_models_count == 0

    def test_no_models_key(self):
        from routers.projects.helpers import calculate_generation_stats

        db = Mock()
        project = Mock(
            generation_config={
                "prompt_structures": {"s1": {}},
                "selected_configuration": {},
            }
        )
        response = Mock(task_count=5)

        calculate_generation_stats(db, project, response)
        assert response.generation_models_count == 0


def _annotation_only_project():
    """Project mock: only annotation stage contributes to progress."""
    project = Mock()
    project.enable_annotation = True
    project.enable_generation = False
    project.enable_evaluation = False
    project.generation_config = None
    project.evaluation_config = None
    return project


class TestCalculateProjectStats:
    """Tests for calculate_project_stats.

    The helper always issues 5 count queries (task / annotation /
    completed-task / evaluation-total / evaluation-completed). The last two
    are independent of the enable_evaluation flag because the response
    object always exposes them for the Statistiken tile. Pass annotation-
    only project mocks so generation contributes nothing and the mix
    collapses to the annotation ratio.
    """

    def test_basic_stats(self):
        from routers.projects.helpers import calculate_project_stats

        db = MagicMock()
        db.query.return_value.filter.return_value.count.side_effect = [10, 5, 7, 0, 0]

        response = Mock()
        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project()
        )

        assert response.task_count == 10
        assert response.annotation_count == 5
        assert response.completed_tasks_count == 7
        assert response.progress_percentage == 70.0

    def test_zero_tasks(self):
        from routers.projects.helpers import calculate_project_stats

        db = MagicMock()
        db.query.return_value.filter.return_value.count.side_effect = [0, 0, 0, 0, 0]

        response = Mock()
        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project()
        )

        assert response.task_count == 0
        assert response.progress_percentage == 0.0

    def test_all_tasks_completed(self):
        from routers.projects.helpers import calculate_project_stats

        db = MagicMock()
        db.query.return_value.filter.return_value.count.side_effect = [5, 10, 5, 0, 0]

        response = Mock()
        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project()
        )
        assert response.progress_percentage == 100.0

    def test_over_100_percent_capped(self):
        from routers.projects.helpers import calculate_project_stats

        db = MagicMock()
        db.query.return_value.filter.return_value.count.side_effect = [5, 10, 6, 0, 0]

        response = Mock()
        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project()
        )
        assert response.progress_percentage == 100.0
