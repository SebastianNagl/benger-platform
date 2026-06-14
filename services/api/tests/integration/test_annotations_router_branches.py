"""Behavioral integration tests for the projects/annotations router — net-new
branches only.

Scope rationale: the create/list/update happy paths, task-not-found,
cancelled-annotation, instruction_variant/ai_assisted, mark-labeled, all_users,
the maximum_annotations 400, the was_cancelled counter toggle, and the
"can only update your own annotation" 403 are ALREADY covered by
``tests/integration/test_annotations_integration.py``,
``tests/integration/test_annotations_coverage.py``, and
``tests/unit/test_coverage_boost_annotations.py`` (all real-DB via ``client``).

This file deliberately covers ONLY the branches those three miss:
  * GET ``completed_by_username`` resolution — match AND no-match (returns []).
  * GET ``latest_only`` per-annotator deduplication.
  * GET empty-result (``cast(result) != '[]'``) exclusion from listings.
  * POST server-side TaskDraft cleanup on submit.
  * POST ``min_annotations_per_task`` labeling threshold (labels only AT min).

Idioms mirror test_project_progress_mix.py (direct model inserts + flush) and
the shared client/test_db/test_users/auth_headers fixtures. The admin user
(test_users[0], is_superadmin=True) short-circuits check_project_accessible and
check_task_assigned_to_user, so open-mode projects it creates are reachable.

Full paths through the /api/projects router prefix:
  POST   /api/projects/tasks/{task_id}/annotations
  GET    /api/projects/tasks/{task_id}/annotations
"""

import uuid

import pytest

from project_models import Annotation, Project, Task, TaskDraft


def _make_project(test_db, *, created_by, **overrides):
    project = Project(
        id=str(uuid.uuid4()),
        title="Annotations Router Branch Test",
        created_by=created_by,
        assignment_mode=overrides.pop("assignment_mode", "open"),
        maximum_annotations=overrides.pop("maximum_annotations", 0),
        min_annotations_per_task=overrides.pop("min_annotations_per_task", 1),
        **overrides,
    )
    test_db.add(project)
    test_db.flush()
    return project


def _make_task(test_db, project, *, inner_id=1, **overrides):
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "Some legal text to annotate"},
        **overrides,
    )
    test_db.add(task)
    test_db.flush()
    return task


def _seed_annotation(test_db, task, project, completed_by, result=None):
    ann = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=completed_by,
        result=result if result is not None else [{"value": {"choices": ["x"]}}],
        was_cancelled=False,
    )
    test_db.add(ann)
    test_db.flush()
    return ann


def _payload(**overrides):
    payload = {
        "result": [{"value": {"choices": ["positive"]}, "from_name": "label"}],
        "was_cancelled": False,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# GET completed_by_username resolution (match + no-match) — uncovered elsewhere
# ---------------------------------------------------------------------------

class TestListByUsername:
    def test_filter_by_username_match(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        contributor = test_users[1]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)
        _seed_annotation(test_db, task, project, admin.id)
        theirs = _seed_annotation(test_db, task, project, contributor.id)

        # contributor.username == "contributor@test.com"; the handler resolves
        # the display string back to a user via username/name/pseudonym.
        resp = client.get(
            f"/api/projects/tasks/{task.id}/annotations",
            params={"completed_by_username": contributor.username},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {a["id"] for a in resp.json()}
        assert ids == {theirs.id}

    def test_filter_by_username_no_match_returns_empty(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)
        _seed_annotation(test_db, task, project, admin.id)

        # No user resolves -> early `return []` branch.
        resp = client.get(
            f"/api/projects/tasks/{task.id}/annotations",
            params={"completed_by_username": "no-such-display-name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET latest_only dedup + empty-result exclusion — uncovered elsewhere
# ---------------------------------------------------------------------------

class TestListLatestAndEmpty:
    def test_latest_only_dedupes_per_annotator(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)
        _seed_annotation(test_db, task, project, admin.id)
        _seed_annotation(test_db, task, project, admin.id)

        resp = client.get(
            f"/api/projects/tasks/{task.id}/annotations",
            params={"latest_only": "true"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Two annotations from one user collapse to a single latest row.
        assert len(body) == 1
        assert body[0]["completed_by"] == admin.id

    def test_empty_result_annotations_excluded(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)
        real = _seed_annotation(test_db, task, project, admin.id)
        # result == [] is filtered by the `cast(result, String) != '[]'` clause.
        _seed_annotation(test_db, task, project, admin.id, result=[])

        resp = client.get(
            f"/api/projects/tasks/{task.id}/annotations",
            params={"all_users": "true"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {a["id"] for a in resp.json()}
        assert ids == {real.id}


# ---------------------------------------------------------------------------
# POST TaskDraft cleanup + min_annotations labeling threshold — uncovered
# ---------------------------------------------------------------------------

class TestCreateSideEffects:
    def test_create_clears_existing_server_draft(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)

        draft = TaskDraft(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            user_id=admin.id,
            draft_result=[{"value": {"choices": ["draft"]}}],
        )
        test_db.add(draft)
        test_db.flush()

        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=_payload(),
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text

        test_db.expire_all()
        remaining = (
            test_db.query(TaskDraft)
            .filter(TaskDraft.task_id == task.id, TaskDraft.user_id == admin.id)
            .count()
        )
        # Submitting the annotation deletes the user's server-side draft.
        assert remaining == 0

    def test_labels_task_only_at_min_annotations(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(
            test_db,
            created_by=admin.id,
            maximum_annotations=0,
            min_annotations_per_task=2,
        )
        task = _make_task(test_db, project)

        first = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=_payload(),
            headers=auth_headers["admin"],
        )
        assert first.status_code == 200, first.text
        test_db.expire_all()
        after_one = test_db.query(Task).filter(Task.id == task.id).first()
        # One non-cancelled annotation is below the min of 2 -> not labeled.
        assert after_one.is_labeled is False

        second = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=_payload(),
            headers=auth_headers["admin"],
        )
        assert second.status_code == 200, second.text
        test_db.expire_all()
        after_two = test_db.query(Task).filter(Task.id == task.id).first()
        # Second non-cancelled annotation meets the min -> labeled.
        assert after_two.is_labeled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
