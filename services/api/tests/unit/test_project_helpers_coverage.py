"""
Unit tests for routers/projects/helpers.py — covers all uncovered branches.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from routers.projects.helpers import (
    calculate_project_stats,
    calculate_project_stats_batch,
    calculate_generation_stats,
    get_accessible_project_ids,
    check_project_accessible,
    check_task_assigned_to_user,
    check_user_can_edit_project,
    get_project_organizations,
)


# ============= calculate_project_stats =============


def _annotation_only_project_mock():
    """Project mock with only annotation stage enabled so the helper
    only fires task/annotation/completed-task queries and the scored-pairs
    fallback — generation/evaluation stages contribute (0, 0) to progress."""
    project = MagicMock()
    project.enable_annotation = True
    project.enable_generation = False
    project.enable_evaluation = False
    project.generation_config = None
    project.evaluation_config = None
    return project


class TestCalculateProjectStats:
    """Tests for calculate_project_stats."""

    def test_with_tasks_and_annotations(self):
        db = Mock()
        # read_project_summary's db.execute(...).scalar_one_or_none() → None
        # forces the live fallback path that this Mock chain mirrors.
        db.execute.return_value.scalar_one_or_none.return_value = None
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

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, completed_query, scored_pairs_query]

        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project_mock()
        )

        assert response.task_count == 10
        assert response.annotation_count == 5
        assert response.completed_tasks_count == 7
        assert response.progress_percentage == 70.0

    def test_zero_tasks(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None
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

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, completed_query, scored_pairs_query]

        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project_mock()
        )

        assert response.task_count == 0
        assert response.progress_percentage == 0.0

    def test_progress_capped_at_100(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None
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

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, completed_query, scored_pairs_query]

        calculate_project_stats(
            db, "proj-1", response, project=_annotation_only_project_mock()
        )

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
        # `read_project_summary` batch read returns no precomputed rows;
        # batch path then needs the scored-pairs fallback for the project.
        db.execute.return_value.all.return_value = []

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

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, scored_pairs_query]

        result = calculate_project_stats_batch(db, ["proj-1"])

        assert result["proj-1"]["task_count"] == 10
        assert result["proj-1"]["completed_tasks_count"] == 7
        assert result["proj-1"]["annotation_count"] == 5

    def test_project_with_no_stats(self):
        db = Mock()
        db.execute.return_value.all.return_value = []

        task_query = MagicMock()
        task_query.filter.return_value = task_query
        task_query.group_by.return_value = task_query
        task_query.all.return_value = []

        ann_query = MagicMock()
        ann_query.filter.return_value = ann_query
        ann_query.group_by.return_value = ann_query
        ann_query.all.return_value = []

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, scored_pairs_query]

        result = calculate_project_stats_batch(db, ["proj-x"])

        assert result["proj-x"]["task_count"] == 0
        assert result["proj-x"]["completed_tasks_count"] == 0
        assert result["proj-x"]["annotation_count"] == 0

    def test_none_values_default_to_zero(self):
        db = Mock()
        db.execute.return_value.all.return_value = []

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

        scored_pairs_query = MagicMock()
        scored_pairs_query.select_from.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []

        db.query.side_effect = [task_query, ann_query, scored_pairs_query]

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

        assert response.generation_config_ready == False  # noqa: E712
        assert response.generation_prompts_ready == False  # noqa: E712
        assert response.generation_models_count == 0
        assert response.generation_completed == False  # noqa: E712

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

        assert response.generation_config_ready == True  # noqa: E712
        assert response.generation_prompts_ready == True  # noqa: E712
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

        assert response.generation_completed == True  # noqa: E712

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

        assert response.generation_completed == False  # noqa: E712

    def test_no_models_configured(self):
        db = Mock()
        project = Mock(
            generation_config={"prompt_structures": {"struct1": {}}},
            id="proj-1",
        )
        response = Mock(task_count=5, generation_models_count=0)

        calculate_generation_stats(db, project, response)

        assert response.generation_models_count == 0
        assert response.generation_completed == False  # noqa: E712


# ============= get_accessible_project_ids =============


class TestGetAccessibleProjectIds:
    """Tests for get_accessible_project_ids."""

    def test_superadmin_returns_none_when_include_all_private(self):
        # The "no filter" sentinel is now opt-in: superadmin must pass
        # include_all_private=True to get full visibility back.
        db = Mock()
        user = Mock(is_superadmin=True)

        # When the flag is set the helper short-circuits before any query,
        # so we don't need to mock `db.query` for this path.
        result = get_accessible_project_ids(
            db, user, org_context="org-1", include_all_private=True
        )
        assert result is None

    def _union_db(self, own_private_ids, org_rows):
        """A db whose ``query`` chains answer the public and own-private
        reads and whose ``execute`` answers the member-org rows query."""
        db = Mock()
        public_query = MagicMock()
        public_query.filter.return_value = public_query
        public_query.all.return_value = []
        own_query = MagicMock()
        own_query.filter.return_value = own_query
        own_query.all.return_value = [Mock(id=i) for i in own_private_ids]
        db.query.side_effect = [public_query, own_query]
        db.execute.return_value.all.return_value = org_rows
        return db

    @staticmethod
    def _org_row(project_id, org_id, **kw):
        row = dict(
            project_id=project_id,
            organization_id=org_id,
            group_id=None,
            attached_via="manual",
            is_private=False,
            created_by="user-2",
            kind=None,
            is_archived=False,
        )
        row.update(kw)
        return Mock(**row)

    def _run(self, db, user, memberships, org_context, staff_ids=frozenset(), groups=None):
        loaded = Mock(organization_memberships=list(memberships)) if memberships is not None else None
        with patch(
            "routers.projects.helpers.get_user_with_memberships", return_value=loaded
        ), patch(
            "routers.projects.helpers.get_lti_staff_project_ids",
            return_value=set(staff_ids),
        ), patch(
            "routers.projects.helpers.get_user_group_context",
            return_value=dict(groups or {}),
        ), patch(
            "routers.projects.helpers._lti_protected_org_ids", return_value=set()
        ):
            return get_accessible_project_ids(db, user, org_context=org_context)

    def test_private_context_lists_own_private_projects(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = self._union_db(["proj-1", "proj-2"], [])
        assert self._run(db, user, [], "private") == ["proj-1", "proj-2"]

    def test_no_context_appends_lms_staff_exams(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = self._union_db(["proj-1"], [])
        # LMS-linked exams the caller opens as org staff follow the own ones.
        assert self._run(db, user, [], None, staff_ids={"lti-exam"}) == [
            "proj-1",
            "lti-exam",
        ]

    def test_every_membership_lists_its_org_projects_whatever_the_context(self):
        user = Mock(is_superadmin=False, id="user-1")
        memberships = [
            Mock(organization_id="org-1", is_active=True, role="CONTRIBUTOR"),
            Mock(organization_id="org-2", is_active=True, role="CONTRIBUTOR"),
        ]
        rows = [self._org_row("proj-1", "org-1"), self._org_row("proj-2", "org-2")]
        # The selected organization is not a read boundary: the same union
        # under the org's context, another org's context and the private one.
        for ctx in ("org-1", "org-2", "org-elsewhere", "private", None):
            db = self._union_db(["own-1"], rows)
            assert self._run(db, user, memberships, ctx) == ["own-1", "proj-1", "proj-2"], ctx

    def test_inactive_membership_lists_nothing(self):
        user = Mock(is_superadmin=False, id="user-1")
        memberships = [Mock(organization_id="org-1", is_active=False, role="ORG_ADMIN")]
        db = self._union_db([], [self._org_row("proj-1", "org-1")])
        # No active membership: the org rows query is never issued.
        assert self._run(db, user, memberships, "org-1") == []
        db.execute.assert_not_called()

    def test_foreign_context_never_raises(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = self._union_db([], [])
        assert self._run(db, user, None, "org-not-member") == []
        db = self._union_db(["own-1"], [])
        assert self._run(db, user, [], "org-not-member") == ["own-1"]


class TestPickMemberOrgProjects:
    """The pure per-row rules of the union list (one row per attachment)."""

    @staticmethod
    def _row(project_id, org_id, **kw):
        row = dict(
            project_id=project_id,
            organization_id=org_id,
            group_id=None,
            attached_via="manual",
            is_private=False,
            created_by="author",
            kind=None,
            is_archived=False,
        )
        row.update(kw)
        return Mock(**row)

    @staticmethod
    def _active(**roles):
        return {
            org: Mock(organization_id=org, is_active=True, role=role)
            for org, role in roles.items()
        }

    def _pick(self, rows, active, user_id="u1", groups=None, staff=(), protected=()):
        from routers.projects.helpers import _pick_member_org_projects

        return _pick_member_org_projects(
            rows, active, user_id, dict(groups or {}), set(staff), set(protected)
        )

    def test_group_eligibility(self):
        rows = [
            self._row("wide", "o1"),
            self._row("mine", "o1", group_id="g1"),
            self._row("other", "o1", group_id="g2"),
        ]
        contributor = self._active(o1="CONTRIBUTOR")
        assert self._pick(rows, contributor, groups={"g1": False}) == ["wide", "mine"]
        # ORG_ADMINs see through group boundaries.
        assert self._pick(rows, self._active(o1="ORG_ADMIN")) == ["wide", "mine", "other"]
        # A membership the rows do not belong to lists nothing.
        assert self._pick(rows, self._active(o9="ORG_ADMIN")) == []

    def test_foreign_private_only_for_lms_staff(self):
        rows = [self._row("priv", "o1", is_private=True, kind="exam", attached_via="lti")]
        contributor = self._active(o1="CONTRIBUTOR")
        assert self._pick(rows, contributor) == []
        assert self._pick(rows, contributor, staff={"priv"}) == ["priv"]
        # The creator keeps their own private project.
        assert self._pick(rows, contributor, user_id="author") == ["priv"]

    def test_annotator_exam_and_archive_carve_outs(self):
        rows = [
            self._row("exam", "o1", kind="exam"),
            self._row("old", "o1", is_archived=True),
            self._row("plain", "o1"),
            self._row("gexam", "o1", kind="exam", group_id="g1"),
        ]
        annotator = self._active(o1="ANNOTATOR")
        assert self._pick(rows, annotator, groups={"g1": False}) == ["plain"]
        # A group admin of the attachment's group is staff on its projects.
        assert self._pick(rows, annotator, groups={"g1": True}) == ["plain", "gexam"]
        # Staff through another attached org still lists the same rows.
        rows2 = rows + [self._row("exam", "o2", kind="exam")]
        two = self._active(o1="ANNOTATOR", o2="CONTRIBUTOR")
        assert self._pick(rows2, two) == ["plain", "exam"]
        assert self._pick(rows, self._active(o1="CONTRIBUTOR"), groups={"g1": False}) == [
            "exam",
            "old",
            "plain",
            "gexam",
        ]

    def test_protected_lms_org_lists_only_for_admins(self):
        rows = [self._row("linked", "o1", kind="exam", attached_via="lti")]
        assert self._pick(rows, self._active(o1="CONTRIBUTOR"), protected={"o1"}) == []
        assert self._pick(rows, self._active(o1="ORG_ADMIN"), protected={"o1"}) == ["linked"]
        grouped = [self._row("linked", "o1", kind="exam", attached_via="lti", group_id="g1")]
        assert self._pick(
            grouped, self._active(o1="CONTRIBUTOR"), groups={"g1": True}, protected={"o1"}
        ) == ["linked"]
        # A manual row of the same org is not an LMS row: the generic rules.
        manual = [self._row("shared", "o1", kind="exam")]
        assert self._pick(manual, self._active(o1="CONTRIBUTOR"), protected={"o1"}) == ["shared"]


# ============= check_project_accessible (more branches) =============


class TestCheckProjectAccessibleBranches:
    """Additional branch tests for check_project_accessible."""

    def test_private_context_own_project(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=True, created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context="private") == True  # noqa: E712

    def test_private_context_not_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=True, is_archived=False, created_by="user-2")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context="private") == False  # noqa: E712

    def test_org_context_project_not_in_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, is_archived=False)

        # First call: get project
        db.query.return_value.filter.return_value.first.return_value = project
        # Second call: attachment map rows (organization_id, group_id) tuples
        proj_org_query = MagicMock()
        proj_org_query.filter.return_value = proj_org_query
        proj_org_query.all.return_value = []  # Not in org

        # Third/fourth calls (group-aware flow): user memberships + the
        # caller's group context.
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=project))
                )
            ),
            proj_org_query,
            user_q,
            ogm_q,
        ]

        assert check_project_accessible(db, user, "proj-1", org_context="org-1") == False  # noqa: E712

    def test_org_context_user_not_active_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, is_archived=False)

        # Project query
        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        # Attachment map rows: (organization_id, group_id) tuples
        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        # User memberships (inactive)
        membership = Mock(organization_id="org-1", is_active=False)
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        # Caller's group context (empty)
        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, org_q, user_q, ogm_q]

        assert check_project_accessible(db, user, "proj-1", org_context="org-1") == False  # noqa: E712

    def test_legacy_private_project_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=True, created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project

        # No org context
        assert check_project_accessible(db, user, "proj-1", org_context=None) == True  # noqa: E712

    def test_legacy_private_project_not_owner(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=True, is_archived=False, created_by="user-2")
        db.query.return_value.filter.return_value.first.return_value = project

        assert check_project_accessible(db, user, "proj-1", org_context=None) == False  # noqa: E712

    def test_legacy_no_org_fallback_to_creator(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, created_by="user-1")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = []  # No orgs

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, org_q, user_q, ogm_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) == True  # noqa: E712

    def test_legacy_user_in_project_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, is_archived=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        membership = Mock(organization_id="org-1", is_active=True)
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, org_q, user_q, ogm_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) == True  # noqa: E712

    def test_legacy_user_not_in_project_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, is_archived=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        membership = Mock(organization_id="org-2", is_active=True)  # Different org
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, org_q, user_q, ogm_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) == False  # noqa: E712

    def test_legacy_user_no_memberships(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, is_private=False, is_archived=False, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = None

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, org_q, user_q, ogm_q]

        assert check_project_accessible(db, user, "proj-1", org_context=None) == False  # noqa: E712


# ============= check_task_assigned_to_user =============


class TestCheckTaskAssignedToUser:
    """Tests for check_task_assigned_to_user."""

    def test_open_assignment_mode(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(assignment_mode="open")

        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

    def test_superadmin_bypass(self):
        db = Mock()
        user = Mock(is_superadmin=True, id="user-1")
        project = Mock(assignment_mode="manual")

        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

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

        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

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

        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

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
        # No own annotation either (the attempted-tier fallback).
        db.execute.return_value.first.return_value = None

        assert check_task_assigned_to_user(db, user, "task-1", project) == False  # noqa: E712

    def test_annotator_without_assignment_but_own_annotation(self):
        """An own non-cancelled annotation counts as assigned (attempted tier)."""
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
        org_q.all.return_value = [Mock(organization_id="org-1")]

        assign_q = MagicMock()
        assign_q.filter.return_value = assign_q
        assign_q.first.return_value = None

        db.query.side_effect = [user_q, org_q, assign_q]
        db.execute.return_value.first.return_value = ("ann-1",)

        assert check_task_assigned_to_user(db, user, "task-1", project) == True  # noqa: E712

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
        db.execute.return_value.first.return_value = None

        assert check_task_assigned_to_user(db, user, "task-1", project) == False  # noqa: E712


# ============= check_user_can_edit_project =============


class TestCheckUserCanEditProject:
    """Tests for check_user_can_edit_project."""

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True, id="user-1")
        assert check_user_can_edit_project(db, user, "proj-1") == True  # noqa: E712

    def test_project_creator(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, created_by="user-1")
        db.query.return_value.filter.return_value.first.return_value = project
        assert check_user_can_edit_project(db, user, "proj-1") == True  # noqa: E712

    def test_org_admin_can_edit(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="ORG_ADMIN")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        # Attachment map rows: (organization_id, group_id) tuples
        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, user_q, org_q, ogm_q]

        assert check_user_can_edit_project(db, user, "proj-1") == True  # noqa: E712

    def test_annotator_cannot_edit(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="ANNOTATOR")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        # Attachment map rows: (organization_id, group_id) tuples
        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, user_q, org_q, ogm_q]

        assert check_user_can_edit_project(db, user, "proj-1") == False  # noqa: E712

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

        assert check_user_can_edit_project(db, user, "proj-1") == False  # noqa: E712

    def test_custom_allowed_roles(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(deleted_at=None, created_by="user-2")

        proj_q = MagicMock()
        proj_q.filter.return_value = proj_q
        proj_q.first.return_value = project

        membership = Mock(organization_id="org-1", is_active=True, role="CONTRIBUTOR")
        user_with_mem = Mock(organization_memberships=[membership])
        user_q = MagicMock()
        user_q.options.return_value = user_q
        user_q.filter.return_value = user_q
        user_q.first.return_value = user_with_mem

        # Attachment map rows: (organization_id, group_id) tuples
        org_q = MagicMock()
        org_q.filter.return_value = org_q
        org_q.all.return_value = [("org-1", None)]

        ogm_q = MagicMock()
        ogm_q.filter.return_value = ogm_q
        ogm_q.all.return_value = []

        db.query.side_effect = [proj_q, user_q, org_q, ogm_q]

        assert check_user_can_edit_project(
            db, user, "proj-1", allowed_roles=("ORG_ADMIN",)
        ) == False  # noqa: E712


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
    """Tests for the canonical ``require_project_access`` FastAPI dependency
    (``routers.projects.deps`` — a factory returning the dependency callable;
    yields a ``ProjectAccess`` container)."""

    @staticmethod
    def _async_db(scalar):
        """Fake AsyncSession whose ``await db.execute(...).scalar_one_or_none()``
        returns ``scalar`` — covers the project-load in the dependency."""
        result = Mock()
        result.scalar_one_or_none.return_value = scalar
        db = Mock()
        db.execute = AsyncMock(return_value=result)
        return db

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.deps import require_project_access

        dep = require_project_access()
        db = self._async_db(None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await dep(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.projects.deps import require_project_access

        dep = require_project_access()
        project = Mock(deleted_at=None)
        db = self._async_db(project)
        user = Mock(is_superadmin=False)
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await dep(project_id="proj-1", request=request, current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self):
        from routers.projects.deps import ProjectAccess, require_project_access

        dep = require_project_access()
        project = Mock(id="proj-1")
        db = self._async_db(project)
        user = Mock(is_superadmin=True)
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await dep(
                project_id="proj-1", request=request, current_user=user, db=db
            )
            assert isinstance(result, ProjectAccess)
            assert result.project == project
            assert result.user == user
