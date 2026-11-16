"""``GET /api/admin/rubric-generation-jobs``: the superadmin list of
Bewertungsbogen generation jobs, and the shared serializer."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import Organization
from project_models import RUBRIC_GENERATION_JOB_STATUSES, RubricGenerationJob
from rubric_generation_jobs import RUBRIC_GENERATION_JOB_COLUMNS, serialize_rubric_generation_job
from tests.integration.test_task_rubrics_router import (
    _as_user,
    _make_project,
    _make_task,
    _make_user,
)

URL = "/api/admin/rubric-generation-jobs"
T0 = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


def _job(**values) -> RubricGenerationJob:
    values.setdefault("id", str(uuid.uuid4()))
    values.setdefault("entry_point", "task")
    values.setdefault("celery_task_id", f"celery-{uuid.uuid4()}")
    return RubricGenerationJob(**values)


async def _seed(db):
    """Four jobs of one exam: two failed, one completed, one queued."""
    admin = await _make_user(db, superadmin=True)
    starter = await _make_user(db)
    project = await _make_project(db, starter, title="Klausur Schuldrecht")
    task = await _make_task(db, project, inner_id=7)
    suffix = uuid.uuid4().hex[:8]
    org = Organization(
        id=str(uuid.uuid4()), name=f"Lehrstuhl {suffix}", display_name="Lehrstuhl", slug=f"ls-{suffix}",
    )
    db.add(org)
    await db.flush()
    common = dict(project_id=project.id, task_id=task.id, user_id=starter.id, organization_id=org.id)
    failed_old = _job(
        **common, status="failed", generator_model_id="gpt-5.4-mini", error_code="no_valid_sheet",
        error_message="Kein gültiger Bogen nach 3 Versuchen", error_stage="validate", attempts=3,
        attempt_errors=[{"attempt": 1, "stage": "validate", "detail": "Summe 70 statt 72,5"}],
        created_at=T0, finished_at=T0 + timedelta(minutes=2),
    )
    failed_new = _job(
        **common, status="failed", generator_model_id="gpt-5.4", error_code="provider_error",
        error_message="429", created_at=T0 + timedelta(hours=1), retry_of=None,
    )
    completed = _job(
        **common, status="completed", generator_model_id="gpt-5.4-mini", entry_point="wizard",
        created_at=T0 + timedelta(hours=2), prompt_tokens=1200, completion_tokens=800,
        details={"metered": True},
    )
    # The row outlived its project, task, user and organization.
    orphan = _job(status="queued", entry_point="bulk", created_at=T0 + timedelta(hours=3), celery_task_id=None)
    db.add_all([failed_old, failed_new, completed, orphan])
    await db.flush()
    await db.commit()
    return admin, starter, project, task, org, [failed_old, failed_new, completed, orphan]


class TestAdminList:
    @pytest.mark.asyncio
    async def test_non_superadmin_is_refused(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(URL)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_lists_newest_first_with_joins_and_facets(self, async_test_client, async_test_db):
        admin, starter, project, task, org, jobs = await _seed(async_test_db)
        failed_old, failed_new, completed, orphan = jobs

        with _as_user(admin):
            resp = await async_test_client.get(URL, params={"since": T0.isoformat()})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 4
        assert [item["id"] for item in body["items"]] == [
            orphan.id, completed.id, failed_new.id, failed_old.id,
        ]
        assert body["facets"]["status"] == {"failed": 2, "completed": 1, "queued": 1}
        assert body["facets"]["error_code"] == {"no_valid_sheet": 1, "provider_error": 1}
        assert body["facets"]["generator_model_id"] == {"gpt-5.4-mini": 2, "gpt-5.4": 1}

        by_id = {item["id"]: item for item in body["items"]}
        failure = by_id[failed_old.id]
        assert failure["project_title"] == "Klausur Schuldrecht"
        assert failure["task_inner_id"] == 7
        assert failure["user_label"] == starter.email
        assert failure["organization_name"] == org.name
        assert failure["error_message"] == "Kein gültiger Bogen nach 3 Versuchen"
        assert failure["attempt_errors"] == [
            {"attempt": 1, "stage": "validate", "detail": "Summe 70 statt 72,5"}
        ]
        assert datetime.fromisoformat(failure["created_at"]) == T0
        assert by_id[completed.id]["details"] == {"metered": True}
        assert set(RUBRIC_GENERATION_JOB_COLUMNS) <= set(failure)
        gone = by_id[orphan.id]
        assert gone["project_title"] is None and gone["user_label"] is None
        assert gone["organization_name"] is None and gone["task_inner_id"] is None
        assert gone["details"] == {}

    @pytest.mark.asyncio
    async def test_filters_and_paging(self, async_test_client, async_test_db):
        admin, starter, project, task, org, jobs = await _seed(async_test_db)
        failed_old, failed_new, completed, orphan = jobs

        with _as_user(admin):
            failed = await async_test_client.get(
                URL, params={"status": "failed", "project_id": project.id, "limit": 1}
            )
            later = await async_test_client.get(
                URL, params={"status": "failed", "project_id": project.id, "limit": 1, "offset": 1}
            )
            mini = await async_test_client.get(
                URL, params={"generator_model_id": "gpt-5.4-mini", "user_id": starter.id,
                             "organization_id": org.id, "entry_point": "wizard"}
            )
            window = await async_test_client.get(
                URL, params={"project_id": project.id, "since": (T0 + timedelta(minutes=30)).isoformat(),
                             "until": (T0 + timedelta(hours=2)).isoformat()}
            )
            by_code = await async_test_client.get(URL, params={"error_code": "provider_error",
                                                               "project_id": project.id})
            too_many = await async_test_client.get(URL, params={"limit": 201})

        assert failed.json()["total"] == 2
        assert [i["id"] for i in failed.json()["items"]] == [failed_new.id]
        assert failed.json()["facets"]["status"] == {"failed": 2}
        assert [i["id"] for i in later.json()["items"]] == [failed_old.id]
        assert [i["id"] for i in mini.json()["items"]] == [completed.id]
        assert [i["id"] for i in window.json()["items"]] == [failed_new.id]
        assert [i["id"] for i in by_code.json()["items"]] == [failed_new.id]
        assert too_many.status_code == 422


class TestSerializer:
    def test_every_column_plus_the_display_fields(self):
        job = _job(status="lost", created_at=T0, details={}, attempts=None)
        out = serialize_rubric_generation_job(job, project_title="P", task_inner_id=3)
        assert out["status"] == "lost"
        assert out["created_at"] == T0.isoformat()
        assert out["project_title"] == "P" and out["task_inner_id"] == 3
        assert out["user_label"] is None and out["organization_name"] is None
        assert set(out) == set(RUBRIC_GENERATION_JOB_COLUMNS) | {
            "project_title", "task_inner_id", "user_label", "organization_name",
        }

    def test_status_tuple_matches_the_check_constraint(self):
        check = next(
            c for c in RubricGenerationJob.__table__.constraints
            if c.name == "ck_rubric_generation_jobs_status"
        )
        for status in RUBRIC_GENERATION_JOB_STATUSES:
            assert f"'{status}'" in str(check.sqltext)
