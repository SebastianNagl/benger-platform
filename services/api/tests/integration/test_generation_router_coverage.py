"""Behavioral integration tests for ``routers/generation.py`` — the COMPLEMENT
of ``test_generation_branches.py`` / ``test_remaining_router_endpoints.py``.

Those siblings cover the status/stop/delete happy paths and the
404/403/400 guard branches. This file targets the still-uncovered arms:

  - ``get_parse_metrics`` with NO ``project_id`` for a **non-superadmin** user,
    which exercises the org-scoping branch (``get_accessible_project_ids_async``
    → ``accessible_ids`` narrowing) rather than the superadmin "see everything"
    short-circuit. Both the empty-accessible early return and the
    populated-org-scope aggregation are covered, asserting the aggregation
    runs against the org's real generation rows.
  - ``get_parse_metrics`` for a **superadmin** with no ``project_id`` →
    ``include_all_private=True`` returns None (no narrowing) so the aggregation
    spans every child ``Generation`` row.
  - ``stop_generation`` when celery's ``control.revoke`` raises — the warning
    branch swallows it and the row still persists as ``stopped``.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
these tests seed real rows via ``async_test_db`` and drive the HTTP surface
through ``async_test_client``. ``require_user`` is overridden per-test via the
``_as_user`` context manager to return an auth User matching a seeded DB user
(the sync auth dependency can't see the async test transaction).

parse-metrics aggregates over the CHILD ``Generation`` (``DBLLMResponse``) rows
— ``parse_status`` / ``parse_error`` / ``parse_metadata`` / ``status`` — joined
to the parent ``ResponseGeneration`` (``DBResponseGeneration``) for the
``project_id`` scoping. Each child needs a distinct ``run_index`` per parent.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation as DBLLMResponse
from models import Organization, OrganizationMembership
from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
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


async def _make_user(db, *, is_superadmin=False, username_prefix="gen") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Generation User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Org") -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        display_name=name,
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user: User, org: Organization, *, role="CONTRIBUTOR"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _seed_project(
    db,
    owner: User,
    *,
    org: Organization = None,
    is_private: bool = False,
    num_tasks: int = 1,
) -> Project:
    project = Project(
        id=_uid(),
        title="gen-coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        is_private=is_private,
        is_public=False,
    )
    db.add(project)
    await db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=owner.id,
            )
        )
        await db.flush()
    for i in range(num_tasks):
        db.add(
            Task(
                id=_uid(),
                project_id=project.id,
                inner_id=i + 1,
                data={"text": f"Task {i + 1}"},
                created_by=owner.id,
                updated_by=owner.id,
            )
        )
    await db.flush()
    return project


async def _first_task(db, project: Project) -> Task:
    return (
        await db.execute(select(Task).where(Task.project_id == project.id))
    ).scalars().first()


async def _seed_generation(
    db,
    project: Project,
    *,
    created_by: str,
    status_val: str,
    task_id: str = None,
    model_id: str = "gpt-4o",
) -> DBResponseGeneration:
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task_id,
        model_id=model_id,
        status=status_val,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(gen)
    await db.flush()
    return gen


async def _seed_response(
    db,
    gen: DBResponseGeneration,
    task: Task,
    *,
    model_id: str,
    parse_status: str,
    parse_error: str = None,
    parse_metadata: dict = None,
    run_index: int = 0,
) -> None:
    db.add(
        DBLLMResponse(
            id=_uid(),
            generation_id=gen.id,
            task_id=task.id,
            model_id=model_id,
            case_data="input case",
            response_content="generated answer",
            status="completed",
            parse_status=parse_status,
            parse_error=parse_error,
            parse_metadata=parse_metadata,
            run_index=run_index,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# get_parse_metrics — no project_id → org-scoping branch (non-superadmin)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestParseMetricsOrgScoped:
    @pytest.mark.asyncio
    async def test_non_superadmin_org_scope_aggregates_member_projects(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin (contributor) requesting parse-metrics WITHOUT a
        project_id hits the org-scoping branch: get_accessible_project_ids_async
        narrows to the projects the user can see, and the aggregation runs over
        those rows. The contributor is a member of the org, so the project's
        responses are counted."""
        contributor = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, contributor, org)
        project = await _seed_project(async_test_db, contributor, org=org)
        task = await _first_task(async_test_db, project)
        gen = await _seed_generation(
            async_test_db,
            project,
            created_by=contributor.id,
            status_val="completed",
            task_id=task.id,
        )
        await _seed_response(
            async_test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        await _seed_response(
            async_test_db, gen, task, model_id="gpt-4o",
            parse_status="failed", parse_error="bad json", run_index=1,
        )
        org_id = org.id
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                "/api/generation/parse-metrics",
                headers={"X-Organization-Context": org_id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The org-scoped aggregation saw both rows of the member project.
        assert body["total_generations"] >= 2
        assert body["parse_success"] >= 1
        assert body["parse_failed"] >= 1
        errors = {e["error"]: e["count"] for e in body["common_parse_errors"]}
        assert errors.get("bad json", 0) >= 1

    @pytest.mark.asyncio
    async def test_non_superadmin_no_accessible_projects_returns_zeroed(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin requesting metrics in the default ('private') context
        with NO private projects of their own and no public projects in scope →
        get_accessible_project_ids_async returns [] → the `if not accessible_ids`
        early zeroed-metrics return. A response row exists on an admin-owned,
        org-linked PRIVATE project the annotator can't reach, proving the scoping
        actually excludes it (rather than the DB just being empty)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        # Admin-owned private project the annotator can't reach.
        project = await _seed_project(
            async_test_db, admin, org=org, is_private=True
        )
        task = await _first_task(async_test_db, project)
        gen = await _seed_generation(
            async_test_db,
            project,
            created_by=admin.id,
            status_val="completed",
            task_id=task.id,
        )
        await _seed_response(
            async_test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        await async_test_db.commit()

        # No X-Organization-Context header → defaults to "private"; the annotator
        # owns no private projects, so accessible_ids == [].
        with _as_user(annotator):
            resp = await async_test_client.get("/api/generation/parse-metrics")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] == 0
        assert body["parse_success"] == 0
        assert body["parse_success_rate"] == 0
        assert body["common_parse_errors"] == []

    @pytest.mark.asyncio
    async def test_superadmin_no_project_aggregates_all_rows(
        self, async_test_client, async_test_db
    ):
        """Superadmin + no project_id → get_accessible_project_ids_async returns
        None (include_all_private path), so NO narrowing filter is applied and
        the aggregation spans every response row. Seeded rows must show up in the
        counts."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _seed_project(async_test_db, admin, org=org)
        task = await _first_task(async_test_db, project)
        gen = await _seed_generation(
            async_test_db,
            project,
            created_by=admin.id,
            status_val="completed",
            task_id=task.id,
        )
        await _seed_response(
            async_test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 2}, run_index=0,
        )
        await _seed_response(
            async_test_db, gen, task, model_id="gpt-4o",
            parse_status="validation_error", parse_error="schema mismatch",
            run_index=1,
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/generation/parse-metrics")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] >= 2
        assert body["parse_success"] >= 1
        assert body["parse_validation_error"] >= 1


# ---------------------------------------------------------------------------
# stop_generation — celery-revoke failure is swallowed (still 200 + persisted)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStopRevokeResilience:
    @pytest.mark.asyncio
    async def test_revoke_exception_is_swallowed(
        self, async_test_client, async_test_db
    ):
        """If celery's control.revoke raises, the warning branch swallows it and
        the generation still persists as 'stopped' (the broker hiccup must not
        fail the user's stop request)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        gen = await _seed_generation(
            async_test_db, project, created_by=admin.id, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()

        with _as_user(admin):
            with patch("routers.generation.celery_app") as mock_celery:
                mock_celery.control.revoke.side_effect = RuntimeError(
                    "broker unreachable"
                )
                resp = await async_test_client.post(
                    f"/api/generation/{gen_id}/stop"
                )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "stopped"

        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(
                    DBResponseGeneration.id == gen_id
                )
            )
        ).scalar_one_or_none()
        assert refreshed.status == "stopped"
        assert refreshed.completed_at is not None
