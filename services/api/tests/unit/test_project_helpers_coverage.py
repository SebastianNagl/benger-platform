"""
Unit tests for routers/projects/helpers.py — covers all uncovered branches.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest
from fastapi import HTTPException

from routers.projects.helpers import (
    calculate_project_stats,
    calculate_project_stats_batch,
    calculate_generation_stats,
    get_user_with_memberships,
    get_accessible_project_ids,
    get_org_context_from_request,
    check_project_accessible,
    check_task_assigned_to_user,
    check_user_can_edit_project,
    get_project_organizations,
    get_comprehensive_project_data,
)


# ============= calculate_project_stats =============


class TestCalculateProjectStats:
    """Tests for calculate_project_stats."""

    def test_with_tasks_and_annotations(self):
        db = Mock()
        response = Mock()

        # Setup mock chains
        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.count.return_value = 10

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.count.return_value = 5

        completed_query = MagicMock()
        completed_query.filter.return_value = completed_query
        completed_query.count.return_value = 7

        db.query.side_effect = [task_query, ann_query, completed_query]

        calculate_project_stats(db, "proj-1", response)

        assert response.task_count == 10
        assert response.annotation_count == 5
        assert response.completed_tasks_count == 7
        assert response.progress_percentage == 70.0

    def test_zero_tasks(self):
        db = Mock()
        response = Mock()

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.count.return_value = 0

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.count.return_value = 0

        completed_query = MagicMock()
        completed_query.filter.return_value = completed_query
        completed_query.count.return_value = 0

        db.query.side_effect = [task_query, ann_query, completed_query]

        calculate_project_stats(db, "proj-1", response)

        assert response.task_count == 0
        assert response.progress_percentage == 0.0

    def test_progress_capped_at_100(self):
        db = Mock()
        response = Mock()

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.count.return_value = 5

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.count.return_value = 10

        completed_query = MagicMock()
        completed_query.filter.return_value = completed_query
        completed_query.count.return_value = 6  # More than total tasks

        db.query.side_effect = [task_query, ann_query, completed_query]

        calculate_project_stats(db, "proj-1", response)

        assert response.progress_percentage == 100.0


# ============= calculate_project_stats_batch =============


class TestCalculateProjectStatsBatch:
    """Tests for calculate_project_stats_batch."""

    def test_empty_project_ids(self):
        db = Mock()
        result = calculate_project_stats_batch(db, [])
        assert result == {}

    def test_single_project(self):
        db = Mock()

        task_stat = Mock(project_id="proj-1", task_count=10, completed_tasks_count=7)
        ann_stat = Mock(project_id="proj-1", annotation_count=5)

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.group_by.return_value = task_query
        task_query.all.return_value = [task_stat]

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.group_by.return_value = ann_query
        ann_query.all.return_value = [ann_stat]

        db.query.side_effect = [task_query, ann_query]

        result = calculate_project_stats_batch(db, ["proj-1"])

        assert result["proj-1"]["task_count"] == 10
        assert result["proj-1"]["completed_tasks_count"] == 7
        assert result["proj-1"]["annotation_count"] == 5

    def test_project_with_no_stats(self):
        db = Mock()

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.group_by.return_value = task_query
        task_query.all.return_value = []

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.group_by.return_value = ann_query
        ann_query.all.return_value = []

        db.query.side_effect = [task_query, ann_query]

        result = calculate_project_stats_batch(db, ["proj-x"])

        assert result["proj-x"]["task_count"] == 0
        assert result["proj-x"]["completed_tasks_count"] == 0
        assert result["proj-x"]["annotation_count"] == 0

    def test_none_values_default_to_zero(self):
        db = Mock()

        task_stat = Mock(project_id="proj-1", task_count=None, completed_tasks_count=None)
        ann_stat = Mock(project_id="proj-1", annotation_count=None)

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.group_by.return_value = task_query
        task_query.all.return_value = [task_stat]

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.group_by.return_value = ann_query
        ann_query.all.return_value = [ann_stat]

        db.query.side_effect = [task_query, ann_query]

        result = calculate_project_stats_batch(db, ["proj-1"])

        assert result["proj-1"]["task_count"] == 0


# ============= calculate_generation_stats =============


class TestCalculateGenerationStats:
    """Tests for calculate_generation_stats."""

    def test_no_generation_config(self):
        db = Mock()
        project = Mock(generation_config=None, id="proj-1")
        response = Mock(task_count=5)

        calculate_generation_stats(db, project, response)

        assert response.generation_config_ready is False
        assert response.generation_prompts_ready is False
        assert response.generation_models_count == 0
        assert response.generation_completed is False

    def test_with_prompt_structures(self):
        db = Mock()
        project = Mock(
            generation_config={
                "prompt_structures": {"struct1": {}},
                "selected_configuration": {"models": ["gpt-4", "claude"]},
            },
            id="proj-1",
        )
        response = Mock(task_count=0, generation_models_count=0)

        calculate_generation_stats(db, project, response)

        assert response.generation_config_ready is True
        assert response.generation_prompts_ready is True
        assert response.generation_models_count == 2

    def test_generation_completed(self):
        db = Mock()
        project = Mock(
            generation_config={
                "prompt_structures": {"struct1": {}},
                "selected_configuration": {"models": ["gpt-4"]},
            },
            id="proj-1",
        )
        response = Mock(task_count=2, generation_models_count=0)

        # 1) generation_count query (Statistiken tile)
        gen_count_query = MagicMock()
        gen_count_query.join.return_value = gen_count_query
        gen_count_query.filter.return_value = gen_count_query
        gen_count_query.scalar.return_value = 0

        # 2) Task IDs query
        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task1 = Mock(id="t1")
        task2 = Mock(id="t2")
        task_query.all.return_value = [task1, task2]

        # 3) Completed generations count
        gen_query = MagicMock()
        gen_query.filter.return_value = gen_query
        gen_query.count.return_value = 2  # 2 tasks * 1 model = 2

        db.query.side_effect = [gen_count_query, task_query, gen_query]

        calculate_generation_stats(db, project, response)

        assert response.generation_completed is True

    def test_generation_not_completed(self):
        db = Mock()
        project = Mock(
            generation_config={
                "prompt_structures": {"struct1": {}},
                "selected_configuration": {"models": ["gpt-4"]},
            },
            id="proj-1",
        )
        response = Mock(task_count=2, generation_models_count=0)

        gen_count_query = MagicMock()
        gen_count_query.join.return_value = gen_count_query
        gen_count_query.filter.return_value = gen_count_query
        gen_count_query.scalar.return_value = 0

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task1 = Mock(id="t1")
        task2 = Mock(id="t2")
        task_query.all.return_value = [task1, task2]

        gen_query = MagicMock()
        gen_query.filter.return_value = gen_query
        gen_query.count.return_value = 1  # Only 1 of 2 completed

        db.query.side_effect = [gen_count_query, task_query, gen_query]

        calculate_generation_stats(db, project, response)

        assert response.generation_completed is False

    def test_no_models_configured(self):
        db = Mock()
        project = Mock(
            generation_config={"prompt_structures": {"struct1": {}}},
            id="proj-1",
        )
        response = Mock(task_count=5, generation_models_count=0)

        calculate_generation_stats(db, project, response)

        assert response.generation_models_count == 0
        assert response.generation_completed is False


# ============= get_accessible_project_ids =============


class TestGetAccessibleProjectIds:
    """Tests for get_accessible_project_ids."""

    def test_superadmin_returns_none(self):
        db = Mock()
        user = Mock(is_superadmin=True)
        result = get_accessible_project_ids(db, user, org_context="org-1")
        assert result is None

    def test_private_context(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        rows = [Mock(id="proj-1"), Mock(id="proj-2")]
        db.query.return_value.filter.return_value.all.return_value = rows

        result = get_accessible_project_ids(db, user, org_context="private")
        assert result == ["proj-1", "proj-2"]

    def test_no_context(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        rows = [Mock(id="proj-1")]
        db.query.return_value.filter.return_value.all.return_value = rows

        result = get_accessible_project_ids(db, user, org_context=None)
        assert result == ["proj-1"]

    def test_org_context_with_membership(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        # Mock get_user_with_memberships
        membership = Mock(organization_id="org-1", is_active=True)
        user_with_memberships = Mock(organization_memberships=[membership])

        # 1) public_ids query (no public projects in this scenario)
        public_query = MagicMock()
        public_query.filter.return_value = public_query
        public_query.all.return_value = []

        # 2) get_user_with_memberships
        user_query = MagicMock()
        user_query.options.return_value = user_query
        user_query.filter.return_value = user_query
        user_query.first.return_value = user_with_memberships

        # 3) Project IDs in the org
        proj_query = MagicMock()
        proj_query.filter.return_value = proj_query
        proj_row = Mock(project_id="proj-1")
        proj_query.all.return_value = [proj_row]

        db.query.side_effect = [public_query, user_query, proj_query]

        result = get_accessible_project_ids(db, user, org_context="org-1")
        assert result == ["proj-1"]

    def test_org_context_no_membership_raises(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        user_with_memberships = Mock(organization_memberships=[])
        user_query = MagicMock()
        user_query.options.return_value = user_query
        user_query.filter.return_value = user_query
        user_query.first.return_value = user_with_memberships

        db.query.return_value = user_query

        with pytest.raises(HTTPException) as exc_info:
            get_accessible_project_ids(db, user, org_context="org-not-member")
        assert exc_info.value.status_code == 403

    def test_org_context_no_user_memberships(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        user_query = MagicMock()
        user_query.options.return_value = user_query
        user_query.filter.return_value = user_query
        user_query.first.return_value = None

        db.query.return_value = user_query

        with pytest.raises(HTTPException) as exc_info:
            get_accessible_project_ids(db, user, org_context="org-1")
        assert exc_info.value.status_code == 403


# ============= check_project_accessible (more branches) =============


class TestCheckProjectAccessibleBranches:
    """Additional branch tests for check_project_accessible."""

    def test_private_context_own_project(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context="private") is True

    def test_private_context_not_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-2")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context="private") is False

    def test_org_context_project_not_in_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False)

        # First call: get project
        db.query.return_value.filter.return_value.first.return_value = project
        # Second call: project org IDs
        proj_org_query = MagicMock()
        proj_org_query.filter.return_value = proj_org_query
        proj_org_query.all.return_value = []  # Not in org

        # We need to handle the chain of calls
        call_count = [0]
        original_query = db.query

        def query_side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query(*args)
            return proj_org_query

        db.query.side_effect = [
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=project))
                )
            ),
            proj_org_query,
        ]

        assert check_project_accessible(db, user, "proj-1", org_context="org-1") is False

    def test_org_context_user_not_active_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False)

        # Project query
        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        # Project org IDs
        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        # User memberships (inactive)
        membership = Mock(organization_id="org-1", is_active=False)
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        db.query.side_effect = [proj_q, org_q, user_q]

        assert check_project_accessible(db, user, "proj-1", org_context="org-1") is False

    def test_legacy_private_project_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project

        # No org context
        assert check_project_accessible(db, user, "proj-1", org_context=None) is True

    def test_legacy_private_project_not_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-2")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context=None) is False

    def test_legacy_no_org_fallback_to_creator(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, created_by="user-1")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = []  # No orgs

        db.query.side_effect = [proj_q, org_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) is True

    def test_legacy_user_in_project_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        membership = Mock(organization_id="org-1", is_active=True)
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        db.query.side_effect = [proj_q, org_q, user_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) is True

    def test_legacy_user_not_in_project_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        membership = Mock(organization_id="org-2", is_active=True)  # Different org
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        db.query.side_effect = [proj_q, org_q, user_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) is False

    def test_legacy_user_no_memberships(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        db.query.side_effect = [proj_q, org_q, user_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) is False


# ============= check_task_assigned_to_user =============


class TestCheckTaskAssignedToUser:
    """Tests for check_task_assigned_to_user."""

    def test_open_assignment_mode(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="open")

        assert check_task_assigned_to_user(db, user, "task-1", project) is True

    def test_superadmin_bypass(self):
        db = Mock()
        user = Mock(is_superadmin=True, id="user-1")
        project = Mock(assignment_mode="manual")

        assert check_task_assigned_to_user(db, user, "task-1", project) is True

    def test_non_annotator_role_bypass(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="manual", id="proj-1")

        membership = Mock(organization_id="org-1", is_active=True, role="CONTRIBUTOR")
        user_with_mem = Mock(organization_memberships=[membership])

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        db.query.side_effect = [user_q, org_q]

        assert check_task_assigned_to_user(db, user, "task-1", project) is True

    def test_annotator_with_assignment(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="manual", id="proj-1")

        membership = Mock(organization_id="org-1", is_active=True, role="ANNOTATOR")
        user_with_mem = Mock(organization_memberships=[membership])

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        assignment = Mock()
        assign_q = MagicMock()
        assign_q.filter.return_value = assign_q
        assign_q.first.return_value = assignment

        db.query.side_effect = [user_q, org_q, assign_q]

        assert check_task_assigned_to_user(db, user, "task-1", project) is True

    def test_annotator_without_assignment(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="manual", id="proj-1")

        membership = Mock(organization_id="org-1", is_active=True, role="ANNOTATOR")
        user_with_mem = Mock(organization_memberships=[membership])

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        assign_q = MagicMock()
        assign_q.filter.return_value = assign_q
        assign_q.first.return_value = None

        db.query.side_effect = [user_q, org_q, assign_q]

        assert check_task_assigned_to_user(db, user, "task-1", project) is False

    def test_no_memberships(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="auto", id="proj-1")

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        # Will need assignment query since user_role is None
        assign_q = MagicMock()
        assign_q.filter.return_value = assign_q
        assign_q.first.return_value = None

        db.query.side_effect = [user_q, assign_q]

        assert check_task_assigned_to_user(db, user, "task-1", project) is False


# ============= check_user_can_edit_project =============


class TestCheckUserCanEditProject:
    """Tests for check_user_can_edit_project."""

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True, id="user-1")
        assert check_user_can_edit_project(db, user, "proj-1") is True

    def test_project_creator(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project
        assert check_user_can_edit_project(db, user, "proj-1") is True

    def test_org_admin_can_edit(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="ORG_ADMIN")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        db.query.side_effect = [proj_q, user_q, org_q]

        assert check_user_can_edit_project(db, user, "proj-1") is True

    def test_annotator_cannot_edit(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="ANNOTATOR")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        db.query.side_effect = [proj_q, user_q, org_q]

        assert check_user_can_edit_project(db, user, "proj-1") is False

    def test_no_project_found(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = None

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        db.query.side_effect = [proj_q, user_q]

        assert check_user_can_edit_project(db, user, "proj-1") is False

    def test_custom_allowed_roles(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="CONTRIBUTOR")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_row = Mock(organization_id="org-1")
        org_q.all.return_value = [org_row]

        db.query.side_effect = [proj_q, user_q, org_q]

        assert check_user_can_edit_project(
            db, user, "proj-1", allowed_roles=("ORG_ADMIN",)
        ) is False


# ============= get_project_organizations =============


class TestGetProjectOrganizations:
    """Tests for get_project_organizations."""

    def test_with_organizations(self):
        db = Mock()

        org1 = Mock(id="org-1")
        org1.name = "Org One"
        org2 = Mock(id="org-2")
        org2.name = "Org Two"
        po1 = Mock(organization=org1)
        po2 = Mock(organization=org2)

        query = MagicMock()
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = [po1, po2]
        db.query.return_value = query

        result = get_project_organizations(db, "proj-1")
        assert len(result) == 2
        assert result[0] == {"id": "org-1", "name": "Org One"}
        assert result[1] == {"id": "org-2", "name": "Org Two"}

    def test_filters_out_none_organization(self):
        db = Mock()

        org1 = Mock(id="org-1")
        org1.name = "Org One"
        po1 = Mock(organization=org1)
        po2 = Mock(organization=None)

        query = MagicMock()
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = [po1, po2]
        db.query.return_value = query

        result = get_project_organizations(db, "proj-1")
        assert len(result) == 1

    def test_empty_result(self):
        db = Mock()

        query = MagicMock()
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = []
        db.query.return_value = query

        result = get_project_organizations(db, "proj-1")
        assert result == []


# ============= require_project_access =============


class TestRequireProjectAccess:
    """Tests for require_project_access FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.helpers import require_project_access

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await require_project_access(
                project_id="proj-1",
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.projects.helpers import require_project_access

        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.projects.helpers.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_project_access(
                    project_id="proj-1",
                    request=request,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self):
        from routers.projects.helpers import require_project_access

        db = Mock()
        project = Mock(id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock(is_superadmin=True)
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.projects.helpers.check_project_accessible", return_value=True
        ):
            result = await require_project_access(
                project_id="proj-1",
                request=request,
                current_user=user,
                db=db,
            )
            assert result == project
