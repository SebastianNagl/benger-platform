"""The check step of grading sheets on the platform side (core 2.53).

On a project with ``rubric_review_required`` a sheet becomes active only
once a person confirmed it (``review_state == "confirmed"``); every
activation path refuses it otherwise, with nothing written. Projects without
the flag behave as before. Also: the clone of an edited sheet keeps its
check, ``origin`` is stored and size-checked, and the responses carry the
review fields.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from project_models import Project, TaskRubric
from task_rubric_service import (
    MAX_ORIGIN_BYTES,
    RubricReviewRequired,
    RubricValidationError,
    activate_task_rubric,
    create_task_rubric,
)
from tests.integration.test_task_rubrics_router import (
    _as_user,
    _make_project,
    _make_task,
    _make_user,
    _reload_rubric,
    _seed_grading,
    _seed_rubric,
    _structure,
)


async def _review_project(db, owner) -> Project:
    project = await _make_project(db, owner)
    project.rubric_review_required = True
    await db.flush()
    return project


async def _rubric_count(db, task) -> int:
    return (
        await db.execute(select(func.count()).select_from(TaskRubric).where(TaskRubric.task_id == task.id))
    ).scalar_one()


def _assert_refused(resp, rubric_id=None):
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "rubric_review_required"
    assert detail["message"]
    if rubric_id is not None:
        assert detail["rubric_id"] == rubric_id


class TestFlagOff:
    @pytest.mark.asyncio
    async def test_unchecked_sheets_activate_as_before(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        candidate = await _seed_rubric(async_test_db, project, task)
        await async_test_db.commit()
        assert project.rubric_review_required is False

        with _as_user(owner):
            created = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure(), "activate": True},
            )
            activated = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics/{candidate.id}/activate"
            )
        assert created.status_code == 201, created.text
        assert created.json()["review_state"] is None
        assert activated.status_code == 200 and activated.json()["status"] == "active"


class TestFlagOn:
    @pytest.mark.asyncio
    async def test_create_with_activate_is_refused_and_leaves_no_row(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure(), "activate": True},
            )
        _assert_refused(resp)
        assert await _rubric_count(async_test_db, task) == 0

    @pytest.mark.asyncio
    async def test_create_as_candidate_still_works(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure()},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "candidate"
        assert body["review_state"] is None
        assert body["reviewed_at"] is None and body["reviewed_by"] is None

    @pytest.mark.asyncio
    async def test_activate_route_refuses_an_unconfirmed_sheet(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        active = await _seed_rubric(async_test_db, project, task, status="active")
        rejected = await _seed_rubric(async_test_db, project, task)
        rejected.review_state = "unusable"
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics/{rejected.id}/activate"
            )
        _assert_refused(resp, rejected.id)
        # Nothing moved: the active sheet stays active, the other a candidate.
        assert (await _reload_rubric(async_test_db, active.id)).status == "active"
        assert (await _reload_rubric(async_test_db, rejected.id)).status == "candidate"

    @pytest.mark.asyncio
    async def test_a_confirmed_sheet_activates_and_reports_its_check(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db)
        reviewer = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task)
        checked_at = datetime(2026, 11, 16, 9, 30, tzinfo=timezone.utc)
        rubric.review_state = "confirmed"
        rubric.reviewed_at = checked_at
        rubric.reviewed_by = reviewer.id
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}/activate"
            )
            listed = await async_test_client.get(
                f"/api/projects/{project.id}/task-rubrics?task_id={task.id}"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "active"
        (row,) = listed.json()
        assert row["review_state"] == "confirmed"
        assert row["reviewed_by"] == reviewer.id
        assert datetime.fromisoformat(row["reviewed_at"]) == checked_at

    @pytest.mark.asyncio
    async def test_edit_that_clones_an_unconfirmed_active_sheet_is_refused(
        self, async_test_client, async_test_db
    ):
        """The project turned the check on after the sheet was activated and
        graded: an edit would clone and re-activate it, which needs a check."""
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task, status="active")
        await _seed_grading(async_test_db, project, task, rubric, owner)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": _structure()},
            )
        _assert_refused(resp, rubric.id)
        old = await _reload_rubric(async_test_db, rubric.id)
        assert old.status == "active"
        assert "superseded_by" not in (old.generation_metadata or {})
        assert await _rubric_count(async_test_db, task) == 1

    @pytest.mark.asyncio
    async def test_edit_in_place_of_an_unconfirmed_active_sheet_is_allowed(
        self, async_test_client, async_test_db
    ):
        """No activation happens when the sheet has no gradings yet."""
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task, status="active")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": _structure()},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == rubric.id and resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_the_clone_of_a_confirmed_sheet_keeps_its_check(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db)
        reviewer = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task, status="active")
        checked_at = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
        rubric.review_state = "confirmed"
        rubric.reviewed_at = checked_at
        rubric.reviewed_by = reviewer.id
        await _seed_grading(async_test_db, project, task, rubric, owner)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": _structure()},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["replaced_rubric_id"] == rubric.id and body["status"] == "active"
        assert body["review_state"] == "confirmed"
        assert body["reviewed_by"] == reviewer.id
        assert datetime.fromisoformat(body["reviewed_at"]) == checked_at
        assert (await _reload_rubric(async_test_db, rubric.id)).status == "archived"


class TestServiceRule:
    @pytest.mark.asyncio
    async def test_service_entry_points_raise_before_writing(self, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        candidate = await _seed_rubric(async_test_db, project, task)
        await async_test_db.flush()

        with pytest.raises(RubricReviewRequired) as refused:
            await create_task_rubric(
                async_test_db, task=task, project_id=project.id, actor_id=owner.id,
                structure=_structure(), grade_scale=None, title=None, status="active",
            )
        assert refused.value.code == "rubric_review_required"
        assert await _rubric_count(async_test_db, task) == 1  # only the candidate

        with pytest.raises(RubricReviewRequired) as refused:
            await activate_task_rubric(async_test_db, candidate, task)
        assert refused.value.rubric_id == candidate.id
        assert candidate.status == "candidate"

        candidate.review_state = "confirmed"
        await activate_task_rubric(async_test_db, candidate, task)
        assert candidate.status == "active"
        await async_test_db.rollback()


class TestOrigin:
    @pytest.mark.asyncio
    async def test_origin_is_stored_in_the_generation_metadata(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()
        origin = {"kind": "upload", "file_name": "bogen.xlsx", "file_sha256": "a" * 64, "parser": "table"}

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure(), "origin": origin},
            )
        assert resp.status_code == 201, resp.text
        assert resp.json()["generation_metadata"] == {"origin": origin}

    @pytest.mark.asyncio
    async def test_oversized_origin_is_refused(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={
                    "task_id": task.id,
                    "structure": _structure(),
                    "origin": {"kind": "manual", "pad": "x" * MAX_ORIGIN_BYTES},
                },
            )
        assert resp.status_code == 422
        assert "origin is" in resp.text
        assert await _rubric_count(async_test_db, task) == 0

    @pytest.mark.asyncio
    async def test_origin_merges_into_given_metadata_and_must_be_an_object(self, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.flush()

        rubric = await create_task_rubric(
            async_test_db, task=task, project_id=project.id, actor_id=owner.id,
            structure=_structure(), grade_scale=None, title=None,
            generation_metadata={"contract_version": "checklist-8"}, origin={"kind": "manual"},
        )
        assert rubric.generation_metadata == {
            "contract_version": "checklist-8", "origin": {"kind": "manual"},
        }
        with pytest.raises(RubricValidationError, match="origin must be an object"):
            await create_task_rubric(
                async_test_db, task=task, project_id=project.id, actor_id=owner.id,
                structure=_structure(), grade_scale=None, title=None, origin=["manual"],
            )
        await async_test_db.rollback()


class TestProjectResponse:
    @pytest.mark.asyncio
    async def test_project_read_carries_the_flag_and_patch_cannot_set_it(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db)
        project = await _review_project(async_test_db, owner)
        await async_test_db.commit()

        with _as_user(owner):
            detail = await async_test_client.get(f"/api/projects/{project.id}")
            patched = await async_test_client.patch(
                f"/api/projects/{project.id}", json={"rubric_review_required": False}
            )
        assert detail.status_code == 200, detail.text
        assert detail.json()["rubric_review_required"] is True
        assert patched.status_code == 200, patched.text
        assert patched.json()["rubric_review_required"] is True
        refreshed = (
            await async_test_db.execute(
                select(Project.rubric_review_required).where(Project.id == project.id)
            )
        ).scalar_one()
        assert refreshed is True
