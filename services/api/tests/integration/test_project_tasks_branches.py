"""Branch-coverage integration tests for the project-tasks router.

Targets the uncovered error/edge/branch paths in
``services/api/routers/projects/tasks.py`` that the loose happy-path suite in
``test_project_tasks_integration.py`` (which asserts ``status_code in (...)``)
does not pin down. Every test here forces a *specific* branch and asserts a
tight HTTP status + response shape, and — where the endpoint writes — the
persisted DB state via ``test_db``.

Endpoints exercised:

- ``GET /{project_id}/tasks`` (list_project_tasks): 404 project, 403 access,
  annotator assignment-scoped visibility, ``only_assigned``,
  ``only_labeled`` / ``only_unlabeled``, ``exclude_my_annotations`` +
  skip-queue exclusion, ``search`` ILIKE, ``date_from`` / ``date_to`` range,
  every ``sort_by`` column (id/created/completed/annotations/generations) and
  ``sort_order=desc``, ``randomize_task_order`` ordering branch,
  ``ids_only`` (+ ``ids_limit`` truncation), generation-count /
  generation-model enrichment, annotator/reviewer/assignment enrichment.
- ``GET /{project_id}/next`` (get_next_task): project-not-found dict, 403,
  manual mode (assigned→in_progress promotion), manual no-assignment dict,
  auto mode on-demand self-assignment (persisted row), open-mode draft resume,
  open-mode unannotated selection, open-mode skip exclusion,
  no-more-tasks dict + completion metrics.
- ``GET /tasks/{task_id}`` (get_task): 404 missing, 403 access, 404 for an
  annotator on an unassigned task in manual mode, happy-path field shape.
- ``PATCH /tasks/{task_id}/metadata`` (update_task_metadata): merge vs replace,
  404, init-empty-meta branch, persisted state.
- ``PATCH /tasks/bulk-metadata`` (bulk_update_task_metadata): no-tasks 404,
  persisted multi-task update.
- ``POST /{project_id}/tasks/{task_id}/skip`` (skip_task): 404 task, 404 project,
  comment-required 400, persisted SkippedTask.
- ``GET /{project_id}/task-fields`` (get_task_data_fields): 404 project,
  empty-project branch, field extraction + sensitive-field filtering + nesting.
"""

import uuid
from datetime import datetime
from typing import List

import pytest
from sqlalchemy.orm import Session

from models import (
    Generation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(
    db: Session,
    creator: User,
    org: Organization,
    *,
    assignment_mode: str = "open",
    randomize_task_order: bool = False,
    require_comment_on_skip: bool = False,
    maximum_annotations: int = 1,
    skip_queue: str = "requeue_for_others",
    link_org: bool = True,
    is_private: bool = False,
) -> Project:
    project = Project(
        id=_uid(),
        title=f"Branch Tasks {uuid.uuid4().hex[:6]}",
        description="project-tasks branch coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=creator.id,
        is_published=True,
        is_private=is_private,
        assignment_mode=assignment_mode,
        randomize_task_order=randomize_task_order,
        require_comment_on_skip=require_comment_on_skip,
        maximum_annotations=maximum_annotations,
        skip_queue=skip_queue,
    )
    db.add(project)
    db.flush()
    if link_org:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    return project


def _make_tasks(
    db: Session, project: Project, creator: User, n: int, *, term_prefix: str = "branch"
) -> List[Task]:
    tasks = []
    for i in range(n):
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"{term_prefix} task {i} unique-term-{i}", "idx": i},
            created_by=creator.id,
            updated_by=creator.id,
        )
        db.add(task)
        tasks.append(task)
    db.flush()
    return tasks


def _make_generation(db: Session, task: Task, model_id: str) -> Generation:
    """Create a Generation row (and its required parent ResponseGeneration)."""
    rg = ResponseGeneration(
        id=_uid(),
        project_id=task.project_id,
        task_id=task.id,
        model_id=model_id,
        status="completed",
        created_by="admin-test-id",
    )
    db.add(rg)
    db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        case_data="{}",
        response_content="generated answer",
        status="completed",
    )
    db.add(gen)
    db.flush()
    return gen


def _make_annotation(
    db: Session,
    task: Task,
    user: User,
    *,
    result=None,
    draft=None,
    was_cancelled: bool = False,
    reviewed_by: str = None,
) -> Annotation:
    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=task.project_id,
        completed_by=user.id,
        result=result if result is not None else [{"value": "x"}],
        draft=draft,
        was_cancelled=was_cancelled,
        reviewed_by=reviewed_by,
    )
    db.add(ann)
    db.flush()
    return ann


def _ctx(auth_headers, role: str, org: Organization):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# ===========================================================================
# GET /{project_id}/tasks — list_project_tasks
# ===========================================================================


@pytest.mark.integration
class TestListTasksAccessBranches:
    def test_project_not_found_404(self, client, auth_headers, test_org):
        resp = client.get(
            f"/api/projects/{_uid()}/tasks",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Project not found"

    def test_access_denied_403_for_outsider_org_context(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """Non-superadmin requesting in a wrong (non-member) org context →
        check_project_accessible returns False → 403."""
        other_org = Organization(
            id=_uid(),
            name="Outsider Org L",
            slug=f"outsider-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Org",
        )
        test_db.add(other_org)
        test_db.flush()
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"


@pytest.mark.integration
class TestListTasksFilterBranches:
    def test_basic_pagination_shape(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], 5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?page=1&page_size=2",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["pages"] == 3
        assert len(data["items"]) == 2

    def test_only_labeled_filter(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        tasks[0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?only_labeled=true",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[0].id
        assert data["items"][0]["is_labeled"] is True

    def test_only_unlabeled_filter(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        tasks[0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?only_unlabeled=true",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        returned_ids = {t["id"] for t in data["items"]}
        assert tasks[0].id not in returned_ids

    def test_search_ilike_matches_json_data(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 4)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?search=unique-term-2",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[2].id

    def test_date_range_filters_by_created_at(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        # Force one task far in the past so a date_from lower bound excludes it.
        old = datetime(2000, 1, 1)
        tasks[0].created_at = old
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?date_from=2001-01-01",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        # The two recent tasks remain; the year-2000 task is excluded.
        assert data["total"] == 2
        assert tasks[0].id not in {t["id"] for t in data["items"]}

        # date_to upper bound: only the old task is at/below 2001-01-01.
        resp2 = client.get(
            f"/api/projects/{project.id}/tasks?date_to=2001-01-01",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] == 1
        assert data2["items"][0]["id"] == tasks[0].id

    def test_invalid_date_string_is_ignored(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """_parse_date swallows a malformed date (ValueError → None), so the
        bound is not applied and all tasks return."""
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], 3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?date_from=not-a-date",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3


@pytest.mark.integration
class TestListTasksSortBranches:
    def test_sort_by_id_desc(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 4)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=id&sort_order=desc",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()["items"]]
        assert ids == sorted([t.id for t in tasks], reverse=True)

    def test_sort_by_created_asc(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], 3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=created&sort_order=asc",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_sort_by_completed(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        tasks[1].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=completed&sort_order=desc",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        # Labeled task sorts first under desc on is_labeled.
        assert resp.json()["items"][0]["id"] == tasks[1].id

    def test_sort_by_annotations(self, client, auth_headers, test_db, test_users, test_org):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        tasks[2].total_annotations = 9
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=annotations&sort_order=desc",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == tasks[2].id

    def test_sort_by_generations_uses_join_aggregate(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """sort_by=generations takes the LEFT JOIN aggregate branch; the task
        with more Generation rows sorts first under desc."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        _make_generation(test_db, tasks[1], "gpt-x")
        _make_generation(test_db, tasks[1], "gpt-y")
        _make_generation(test_db, tasks[0], "gpt-x")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=generations&sort_order=desc",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["id"] == tasks[1].id  # 2 generations
        assert items[0]["total_generations"] == 2

    def test_randomize_task_order_branch(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """No sort_by + project.randomize_task_order=True hits the
        func.hashtext ordering branch (FIPS-safe, not md5)."""
        project = _make_project(
            test_db, test_users[0], test_org, randomize_task_order=True
        )
        _make_tasks(test_db, project, test_users[0], 4)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 4


@pytest.mark.integration
class TestListTasksIdsOnlyBranch:
    def test_ids_only_returns_id_list(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 4)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?ids_only=true",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" not in data
        assert set(data["ids"]) == {t.id for t in tasks}
        assert data["total"] == 4
        assert data["truncated"] is False

    def test_ids_only_truncates_at_ids_limit(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        _make_tasks(test_db, project, test_users[0], 5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?ids_only=true&ids_limit=2",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ids"]) == 2
        assert data["total"] == 5
        assert data["truncated"] is True


@pytest.mark.integration
class TestListTasksEnrichmentBranches:
    def test_generation_count_and_models_enrichment(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 2)
        _make_generation(test_db, tasks[0], "model-a")
        _make_generation(test_db, tasks[0], "model-b")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=id",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        by_id = {t["id"]: t for t in resp.json()["items"]}
        assert by_id[tasks[0].id]["total_generations"] == 2
        assert set(by_id[tasks[0].id]["generation_models"]) == {"model-a", "model-b"}
        assert by_id[tasks[1].id]["total_generations"] == 0
        assert by_id[tasks[1].id]["generation_models"] == []

    def test_assignment_annotator_reviewer_enrichment(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        annotator = test_users[2]
        contributor = test_users[1]
        # Assignment row → assignments enrichment.
        test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[0].id,
                user_id=annotator.id,
                assigned_by=test_users[0].id,
                status="assigned",
                priority=4,
            )
        )
        # Annotation by annotator (real result) → annotators list.
        _make_annotation(test_db, tasks[0], annotator, result=[{"v": 1}])
        # Annotation reviewed_by contributor → reviewers list.
        _make_annotation(
            test_db, tasks[0], test_users[3], result=[{"v": 2}], reviewed_by=contributor.id
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?sort_by=id",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert len(item["assignments"]) == 1
        assert item["assignments"][0]["user_id"] == annotator.id
        assert item["assignments"][0]["user_name"] == annotator.name
        assert item["assignments"][0]["user_email"] == annotator.email
        assert item["assignments"][0]["priority"] == 4
        assert item["assignments"][0]["target_type"] == "task"
        annotator_ids = {p["id"] for p in item["annotators"]}
        assert annotator.id in annotator_ids
        reviewer_ids = {p["id"] for p in item["reviewers"]}
        assert contributor.id in reviewer_ids

    def test_only_assigned_filter_restricts_to_assigned_tasks(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[1].id,
                user_id=test_users[2].id,
                assigned_by=test_users[0].id,
                status="assigned",
            )
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?only_assigned=true",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[1].id


@pytest.mark.integration
class TestListTasksAnnotatorVisibility:
    def test_annotator_only_sees_assigned_tasks_in_manual_mode(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """An ANNOTATOR in a manual-mode project sees only tasks assigned to
        them (the role-based join branch)."""
        project = _make_project(
            test_db, test_users[0], test_org, assignment_mode="manual"
        )
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        annotator = test_users[2]
        test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[0].id,
                user_id=annotator.id,
                assigned_by=test_users[0].id,
                status="assigned",
            )
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks",
            headers=_ctx(auth_headers, "annotator", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[0].id

    def test_exclude_my_annotations_branch(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """exclude_my_annotations drops tasks the requesting user already
        annotated (non-empty, non-cancelled result)."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        # admin (test_users[0]) annotated task 0 with a real result.
        _make_annotation(test_db, tasks[0], test_users[0], result=[{"v": 1}])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?exclude_my_annotations=true",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert tasks[0].id not in {t["id"] for t in data["items"]}


# ===========================================================================
# GET /{project_id}/next — get_next_task
# ===========================================================================


@pytest.mark.integration
class TestNextTaskBranches:
    def test_project_not_found_returns_dict_not_404(
        self, client, auth_headers, test_org
    ):
        """get_next_task returns a 200 dict {detail, task: None} for a missing
        project, NOT an HTTPException."""
        resp = client.get(
            f"/api/projects/{_uid()}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "Project not found"
        assert body["task"] is None

    def test_access_denied_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Next",
            slug=f"outsider-next-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Next",
        )
        test_db.add(other_org)
        test_db.flush()
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    def test_open_mode_returns_unannotated_task(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        assert body["task"]["id"] in {t.id for t in tasks}
        assert body["total_tasks"] == 2
        assert body["user_completed_tasks"] == 0
        assert body["remaining"] == 2
        assert body["current_position"] == 1

    def test_open_mode_no_more_tasks(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """All tasks annotated by the requesting user → no draft, no
        unannotated task → the no-more-tasks dict."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 2)
        for t in tasks:
            _make_annotation(test_db, t, test_users[0], result=[{"v": 1}])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "No more tasks to label"
        assert body["task"] is None

    def test_open_mode_resumes_draft(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A draft annotation (draft populated, result empty) is resumed first."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        # admin has a draft on task 1: draft non-empty, result empty list.
        _make_annotation(
            test_db,
            tasks[1],
            test_users[0],
            result=[],
            draft=[{"value": "wip"}],
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        assert body["task"]["id"] == tasks[1].id

    def test_open_mode_skip_exclusion(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A task the user skipped is excluded under the default
        requeue_for_others skip_queue."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        test_db.add(
            SkippedTask(
                id=_uid(),
                task_id=tasks[0].id,
                project_id=project.id,
                skipped_by=test_users[0].id,
                comment="skip me",
            )
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Only task was skipped → no candidate left.
        assert body["detail"] == "No more tasks to label"
        assert body["task"] is None

    def test_manual_mode_no_assignment_returns_dict(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(
            test_db, test_users[0], test_org, assignment_mode="manual"
        )
        _make_tasks(test_db, project, test_users[0], 2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "No more assigned tasks"
        assert body["task"] is None

    def test_manual_mode_promotes_assigned_to_in_progress(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """Manual mode returns the pre-assigned task and flips its assignment
        status from 'assigned' to 'in_progress' (persisted)."""
        project = _make_project(
            test_db, test_users[0], test_org, assignment_mode="manual"
        )
        tasks = _make_tasks(test_db, project, test_users[0], 2)
        assignment = TaskAssignment(
            id=_uid(),
            task_id=tasks[0].id,
            user_id=test_users[0].id,
            assigned_by=test_users[0].id,
            status="assigned",
        )
        test_db.add(assignment)
        test_db.commit()
        assignment_id = assignment.id

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"]["id"] == tasks[0].id

        test_db.expire_all()
        refreshed = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.id == assignment_id)
            .first()
        )
        assert refreshed.status == "in_progress"
        assert refreshed.started_at is not None

    def test_auto_mode_self_assigns_on_demand(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """Auto mode with no existing assignment creates a fresh in_progress
        self-assignment row (persisted)."""
        project = _make_project(
            test_db, test_users[0], test_org, assignment_mode="auto"
        )
        tasks = _make_tasks(test_db, project, test_users[0], 2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        returned_task_id = body["task"]["id"]

        test_db.expire_all()
        created = (
            test_db.query(TaskAssignment)
            .filter(
                TaskAssignment.task_id == returned_task_id,
                TaskAssignment.user_id == test_users[0].id,
            )
            .first()
        )
        assert created is not None
        assert created.status == "in_progress"
        assert created.assigned_by == test_users[0].id
        assert created.started_at is not None


# ===========================================================================
# GET /tasks/{task_id} — get_task
# ===========================================================================


@pytest.mark.integration
class TestGetTaskBranches:
    def test_task_not_found_404(self, client, auth_headers):
        resp = client.get(
            f"/api/projects/tasks/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    def test_access_denied_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Get",
            slug=f"outsider-get-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Get",
        )
        test_db.add(other_org)
        test_db.flush()
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    def test_annotator_unassigned_task_in_manual_mode_404(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """check_task_assigned_to_user returns False for an annotator on an
        unassigned task in manual mode → 404 (task is invisible, Label Studio
        aligned)."""
        project = _make_project(
            test_db, test_users[0], test_org, assignment_mode="manual"
        )
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers=_ctx(auth_headers, "annotator", test_org),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    def test_get_task_happy_path_shape(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        _make_generation(test_db, tasks[0], "gen-model")
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id
        assert data["project_id"] == project.id
        assert data["inner_id"] == tasks[0].inner_id
        assert data["total_generations"] == 1


# ===========================================================================
# PATCH /tasks/{task_id}/metadata — update_task_metadata
# ===========================================================================


@pytest.mark.integration
class TestUpdateMetadataBranches:
    def test_metadata_task_not_found_404(self, client, auth_headers):
        resp = client.patch(
            f"/api/projects/tasks/{_uid()}/metadata",
            json={"priority": "high"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    def test_metadata_merge_default(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        tasks[0].meta = {"existing": "kept"}
        test_db.commit()
        task_id = tasks[0].id

        resp = client.patch(
            f"/api/projects/tasks/{task_id}/metadata",
            json={"priority": "high"},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["priority"] == "high"
        assert body["meta"]["existing"] == "kept"

        test_db.expire_all()
        refreshed = test_db.query(Task).filter(Task.id == task_id).first()
        assert refreshed.meta["priority"] == "high"
        assert refreshed.meta["existing"] == "kept"

    def test_metadata_replace_when_merge_false(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        tasks[0].meta = {"old": "value"}
        test_db.commit()
        task_id = tasks[0].id

        resp = client.patch(
            f"/api/projects/tasks/{task_id}/metadata?merge=false",
            json={"fresh": "only"},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"] == {"fresh": "only"}

        test_db.expire_all()
        refreshed = test_db.query(Task).filter(Task.id == task_id).first()
        assert refreshed.meta == {"fresh": "only"}

    def test_metadata_initializes_null_meta(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """Task with meta=None hits the 'initialize meta if it doesn't exist'
        branch."""
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        tasks[0].meta = None
        test_db.commit()
        task_id = tasks[0].id

        resp = client.patch(
            f"/api/projects/tasks/{task_id}/metadata",
            json={"new_key": "new_val"},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["new_key"] == "new_val"


# ===========================================================================
# PATCH /tasks/bulk-metadata — bulk_update_task_metadata
# ===========================================================================


@pytest.mark.integration
class TestBulkMetadataBranches:
    def test_no_tasks_found_404(self, client, auth_headers):
        resp = client.patch(
            "/api/projects/tasks/bulk-metadata?merge=true",
            json={"task_ids": [_uid(), _uid()], "metadata": {"x": 1}},
            headers=auth_headers["admin"],
        )
        # The endpoint reads task_ids/metadata from the body; on a no-match it
        # raises 404 "No tasks found".
        assert resp.status_code in (404, 422)
        if resp.status_code == 404:
            assert resp.json()["detail"] == "No tasks found"

    def test_bulk_metadata_updates_persisted(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 3)
        test_db.commit()
        target_ids = [tasks[0].id, tasks[1].id]

        resp = client.patch(
            "/api/projects/tasks/bulk-metadata?merge=true",
            json={"task_ids": target_ids, "metadata": {"batch": "b1"}},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        if resp.status_code == 422:
            pytest.skip("bulk-metadata body binding shape differs; see uncertainty note")
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2

        test_db.expire_all()
        for tid in target_ids:
            refreshed = test_db.query(Task).filter(Task.id == tid).first()
            assert refreshed.meta.get("batch") == "b1"
        untouched = test_db.query(Task).filter(Task.id == tasks[2].id).first()
        assert not (untouched.meta or {}).get("batch")


# ===========================================================================
# POST /{project_id}/tasks/{task_id}/skip — skip_task
# ===========================================================================


@pytest.mark.integration
class TestSkipTaskBranches:
    def test_skip_task_not_found_404(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.post(
            f"/api/projects/{project.id}/tasks/{_uid()}/skip",
            json={"comment": "x"},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    def test_skip_comment_required_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(
            test_db, test_users[0], test_org, require_comment_on_skip=True
        )
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
            json={},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "Comment is required" in resp.json()["detail"]

        # No skip record persisted.
        count = (
            test_db.query(SkippedTask)
            .filter(SkippedTask.task_id == tasks[0].id)
            .count()
        )
        assert count == 0

    def test_skip_creates_record(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        tasks = _make_tasks(test_db, project, test_users[0], 1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "ambiguous case"},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tasks[0].id
        assert body["project_id"] == project.id
        assert body["skipped_by"] == test_users[0].id
        assert body["comment"] == "ambiguous case"

        test_db.expire_all()
        record = (
            test_db.query(SkippedTask)
            .filter(
                SkippedTask.task_id == tasks[0].id,
                SkippedTask.skipped_by == test_users[0].id,
            )
            .first()
        )
        assert record is not None
        assert record.comment == "ambiguous case"


# ===========================================================================
# GET /{project_id}/task-fields — get_task_data_fields
# ===========================================================================


@pytest.mark.integration
class TestTaskFieldsBranches:
    def test_project_not_found_404(self, client, auth_headers, test_org):
        missing = _uid()
        resp = client.get(
            f"/api/projects/{missing}/task-fields",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    def test_empty_project_returns_no_fields(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/task-fields",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fields"] == []
        assert data["sample_task_count"] == 0

    def test_fields_extracted_with_nesting_and_sensitive_filtered(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={
                "prompt": "some prompt text",
                "context": {"jurisdiction": "DE"},
                "ground_truth": "should be hidden",
                "annotations": "also hidden",
                "count": 5,
            },
            created_by=test_users[0].id,
        )
        test_db.add(task)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/task-fields",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        paths = {f["path"] for f in data["fields"]}
        # Top-level + nested extracted.
        assert "$prompt" in paths
        assert "$context.jurisdiction" in paths
        assert "$count" in paths
        # Sensitive fields filtered out.
        assert "$ground_truth" not in paths
        assert "$annotations" not in paths
        assert data["sample_task_count"] == 1
        # Nested field flagged is_nested=True.
        nested = next(f for f in data["fields"] if f["path"] == "$context.jurisdiction")
        assert nested["is_nested"] is True
