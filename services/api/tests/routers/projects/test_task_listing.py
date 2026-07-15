"""Behavioral tests for the project task-listing read endpoints.

Target: ``services/api/routers/projects/tasks/listing.py`` (mounted under
``/api/projects`` via ``routers/projects/__init__.py``). The three async read
endpoints — the paginated/filtered task list, the ``/next`` task dispenser
(open / manual / auto assignment modes), and the single-task read — carried
almost no behavioral coverage after the June tasks-router decomposition.

Every test drives the real async HTTP stack (``async_test_client``) with a
seeded transaction (``async_test_db``, SAVEPOINT-isolated) and a real user
bound via a ``require_user`` dependency override. Data is seeded with uuid4
ids so tests never collide.

Access recap (routers/projects/helpers):
  * a superadmin is allowed everywhere;
  * a private project is reachable only by its creator;
  * a non-private, org-linked project is reachable by active members of that
    org, and an ANNOTATOR member with assignment_mode manual/auto sees only
    tasks assigned to them.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
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

PROJECTS = "/api/projects"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, is_superadmin=None):
    sa = db_user.is_superadmin if is_superadmin is None else is_superadmin
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=sa,
        is_active=True,
        email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


# --------------------------------------------------------------------------- #
# Seeding helpers
# --------------------------------------------------------------------------- #
async def _mk_user(db, *, superadmin=True, name="User") -> User:
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_project(db, owner, **kw) -> Project:
    kw.setdefault("is_private", True)
    p = Project(id=_uid(), title=f"P {_uid()[:6]}", created_by=owner.id, **kw)
    db.add(p)
    await db.flush()
    return p


async def _mk_task(db, project, *, inner_id=1, data=None, **kw) -> Task:
    t = Task(
        id=_uid(),
        project_id=project.id,
        data=data if data is not None else {"text": f"task {inner_id}"},
        inner_id=inner_id,
        created_by=project.created_by,
        **kw,
    )
    db.add(t)
    await db.flush()
    return t


async def _mk_annotation(db, task, user, *, result=None, was_cancelled=False, draft=None,
                         reviewed_by=None) -> Annotation:
    a = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=task.project_id,
        completed_by=user.id,
        result=result if result is not None else [{"from_name": "x", "value": {"text": ["y"]}}],
        was_cancelled=was_cancelled,
        draft=draft,
        reviewed_by=reviewed_by,
    )
    db.add(a)
    await db.flush()
    return a


async def _mk_org(db) -> Organization:
    oid = _uid()
    org = Organization(
        id=oid, name=f"org-{oid[:6]}", display_name=f"Org {oid[:6]}",
        slug=f"org-{oid[:8]}", is_active=True,
    )
    db.add(org)
    await db.flush()
    return org


async def _mk_membership(db, user, org, role=OrganizationRole.ANNOTATOR):
    m = OrganizationMembership(
        id=_uid(), user_id=user.id, organization_id=org.id, role=role, is_active=True,
    )
    db.add(m)
    await db.flush()
    return m


async def _link_org(db, project, org, assigner):
    po = ProjectOrganization(
        id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=assigner.id,
    )
    db.add(po)
    await db.flush()
    return po


async def _mk_assignment(db, task, user, assigner, *, status="assigned", target_type="task",
                         priority=0, due_date=None) -> TaskAssignment:
    a = TaskAssignment(
        id=_uid(),
        task_id=task.id,
        user_id=user.id,
        assigned_by=assigner.id,
        status=status,
        target_type=target_type,
        priority=priority,
        due_date=due_date,
    )
    db.add(a)
    await db.flush()
    return a


async def _mk_skip(db, task, project, user):
    s = SkippedTask(id=_uid(), task_id=task.id, project_id=project.id, skipped_by=user.id)
    db.add(s)
    await db.flush()
    return s


async def _mk_generation(db, task, *, model_id="gpt-4"):
    rg = ResponseGeneration(
        id=_uid(), project_id=task.project_id, task_id=task.id,
        model_id=model_id, status="completed", created_by=task.created_by,
    )
    db.add(rg)
    await db.flush()
    g = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data="{}", response_content="resp", status="completed",
    )
    db.add(g)
    await db.flush()
    return g


# ===========================================================================
# GET /{project_id}/tasks — list_project_tasks
# ===========================================================================
@pytest.mark.integration
class TestListProjectTasks:
    @pytest.mark.asyncio
    async def test_basic_pagination_envelope(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        for i in range(5):
            await _mk_task(async_test_db, p, inner_id=i + 1)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?page=1&page_size=2")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert body["pages"] == 3
        assert len(body["items"]) == 2
        # Each item carries the enriched shape.
        item = body["items"][0]
        assert {"id", "data", "assignments", "annotators", "reviewers",
                "total_generations", "generation_models"} <= set(item)

    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/missing-{_uid()}/tasks")
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        outsider = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner, is_private=True)
        await async_test_db.commit()
        with _as_user(outsider):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_only_labeled_and_only_unlabeled(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        await _mk_task(async_test_db, p, inner_id=1, is_labeled=True)
        await _mk_task(async_test_db, p, inner_id=2, is_labeled=False)
        await _mk_task(async_test_db, p, inner_id=3, is_labeled=False)
        await async_test_db.commit()

        with _as_user(owner):
            labeled = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?only_labeled=true")
            unlabeled = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?only_unlabeled=true")
        assert labeled.json()["total"] == 1
        assert unlabeled.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_search_matches_data_and_id(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        await _mk_task(async_test_db, p, inner_id=1, data={"text": "Kaufvertrag BGB"})
        await _mk_task(async_test_db, p, inner_id=2, data={"text": "Mietrecht"})
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?search=Kaufvertrag")
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        assert "Kaufvertrag" in str(r.json()["items"][0]["data"])

    @pytest.mark.asyncio
    async def test_date_range_filters(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        old = await _mk_task(async_test_db, p, inner_id=1)
        old.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        new = await _mk_task(async_test_db, p, inner_id=2)
        new.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(
                f"{PROJECTS}/{p.id}/tasks?date_from=2025-01-01&date_to=2027-01-01"
            )
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert new.id in ids and old.id not in ids

    @pytest.mark.asyncio
    async def test_invalid_date_string_is_ignored(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        await _mk_task(async_test_db, p, inner_id=1)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?date_from=not-a-date")
        # Unparseable dates are tolerated (treated as no bound).
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sort_by", ["id", "created", "completed", "annotations", "generations"])
    @pytest.mark.parametrize("order", ["asc", "desc"])
    async def test_sort_variants(self, async_test_client, async_test_db, sort_by, order):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t1 = await _mk_task(async_test_db, p, inner_id=1, total_annotations=1, is_labeled=True)
        t2 = await _mk_task(async_test_db, p, inner_id=2, total_annotations=3, is_labeled=False)
        await _mk_generation(async_test_db, t2, model_id="gpt-4")
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(
                f"{PROJECTS}/{p.id}/tasks?sort_by={sort_by}&sort_order={order}"
            )
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 2
        assert len(r.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_randomize_task_order_project(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner, randomize_task_order=True)
        for i in range(4):
            await _mk_task(async_test_db, p, inner_id=i + 1)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_ids_only_short_circuit_and_truncation(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        for i in range(3):
            await _mk_task(async_test_db, p, inner_id=i + 1)
        await async_test_db.commit()

        with _as_user(owner):
            full = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?ids_only=true")
            capped = await async_test_client.get(
                f"{PROJECTS}/{p.id}/tasks?ids_only=true&ids_limit=2"
            )
        assert full.status_code == 200, full.text
        fb = full.json()
        assert set(fb) == {"ids", "total", "truncated"}
        assert len(fb["ids"]) == 3
        assert fb["truncated"] is False
        cb = capped.json()
        assert len(cb["ids"]) == 2
        assert cb["total"] == 3
        assert cb["truncated"] is True

    @pytest.mark.asyncio
    async def test_generation_counts_and_models_enrichment(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_generation(async_test_db, t, model_id="gpt-4")
        await _mk_generation(async_test_db, t, model_id="claude")
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["total_generations"] == 2
        assert set(item["generation_models"]) == {"gpt-4", "claude"}

    @pytest.mark.asyncio
    async def test_assignments_annotators_reviewers_enrichment(
        self, async_test_client, async_test_db
    ):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False, name="Worker")
        reviewer = await _mk_user(async_test_db, superadmin=False, name="Reviewer")
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_assignment(async_test_db, t, worker, owner, status="in_progress")
        # An annotation submitted by `worker` and reviewed by `reviewer`.
        await _mk_annotation(
            async_test_db, t, worker,
            result=[{"from_name": "a", "value": {"text": ["z"]}}],
            reviewed_by=reviewer.id,
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert len(item["assignments"]) == 1
        assert item["assignments"][0]["user_id"] == worker.id
        assert item["assignments"][0]["user_name"] == "Worker"
        assert {a["id"] for a in item["annotators"]} == {worker.id}
        assert {rv["id"] for rv in item["reviewers"]} == {reviewer.id}

    @pytest.mark.asyncio
    async def test_exclude_my_annotations(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t_done = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)  # untouched
        await _mk_annotation(
            async_test_db, t_done, owner,
            result=[{"from_name": "a", "value": {"text": ["z"]}}],
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(
                f"{PROJECTS}/{p.id}/tasks?exclude_my_annotations=true"
            )
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert t_done.id not in ids
        assert r.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_exclude_my_annotations_respects_my_skips(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner, skip_queue="requeue_for_others")
        t_skipped = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)
        await _mk_skip(async_test_db, t_skipped, p, owner)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(
                f"{PROJECTS}/{p.id}/tasks?exclude_my_annotations=true"
            )
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert t_skipped.id not in ids

    @pytest.mark.asyncio
    async def test_ignore_skipped_queue_excludes_any_skip(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        other = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner, skip_queue="ignore_skipped")
        t_skipped = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)
        # Skipped by someone ELSE — ignore_skipped hides it from everyone.
        await _mk_skip(async_test_db, t_skipped, p, other)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert t_skipped.id not in ids
        assert r.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_only_assigned_filter(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner)
        t_assigned = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)
        await _mk_assignment(async_test_db, t_assigned, worker, owner)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks?only_assigned=true")
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert ids == {t_assigned.id}

    @pytest.mark.asyncio
    async def test_annotator_sees_only_assigned_in_manual_mode(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin ANNOTATOR of an org-linked, manual-mode project sees
        only tasks assigned to them (role-based visibility branch)."""
        owner = await _mk_user(async_test_db)
        annotator = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, annotator, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(
            async_test_db, owner, is_private=False, assignment_mode="manual",
        )
        await _link_org(async_test_db, p, org, owner)
        mine = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)  # assigned to nobody
        await _mk_assignment(async_test_db, mine, annotator, owner, status="assigned")
        await async_test_db.commit()

        with _as_user(annotator):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["items"]}
        assert ids == {mine.id}

    @pytest.mark.asyncio
    async def test_annotator_data_is_blinded(self, async_test_client, async_test_db):
        """An annotator receives task.data reduced to label-config-bound keys;
        the unbound reference key (musterloesung) is stripped."""
        owner = await _mk_user(async_test_db)
        annotator = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, annotator, org, OrganizationRole.ANNOTATOR)
        label_config = (
            '<View><Text name="t" value="$sachverhalt"/>'
            '<Choices name="answer" toName="t"><Choice value="Ja"/></Choices></View>'
        )
        p = await _mk_project(
            async_test_db, owner, is_private=False, assignment_mode="open",
            label_config=label_config,
        )
        await _link_org(async_test_db, p, org, owner)
        await _mk_task(
            async_test_db, p, inner_id=1,
            data={"sachverhalt": "Fall A", "musterloesung": "geheim"},
        )
        await async_test_db.commit()

        with _as_user(annotator):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/tasks")
        assert r.status_code == 200, r.text
        data = r.json()["items"][0]["data"]
        assert "sachverhalt" in data
        assert "musterloesung" not in data


# ===========================================================================
# GET /{project_id}/next — get_next_task
# ===========================================================================
@pytest.mark.integration
class TestNextTask:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/missing-{_uid()}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is None
        assert r.json()["detail"] == "Project not found"

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        outsider = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner, is_private=True)
        await async_test_db.commit()
        with _as_user(outsider):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_open_mode_returns_unannotated_with_metrics(
        self, async_test_client, async_test_db
    ):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner, assignment_mode="open")
        await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["task"] is not None
        assert body["total_tasks"] == 2
        assert body["remaining"] == 2
        assert body["user_completed_tasks"] == 0
        assert body["current_position"] == 1

    @pytest.mark.asyncio
    async def test_open_mode_no_tasks_left(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner, assignment_mode="open")
        t = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_annotation(async_test_db, t, owner)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is None
        assert r.json()["detail"] == "No more tasks to label"

    @pytest.mark.asyncio
    async def test_open_mode_resumes_draft(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner, assignment_mode="open")
        drafted = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_task(async_test_db, p, inner_id=2)
        # Draft present, result empty → the endpoint resumes this task.
        await _mk_annotation(
            async_test_db, drafted, owner,
            result=[], draft=[{"from_name": "a", "value": {"text": ["wip"]}}],
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"]["id"] == drafted.id

    @pytest.mark.asyncio
    async def test_open_mode_randomized(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(
            async_test_db, owner, assignment_mode="open", randomize_task_order=True
        )
        await _mk_task(async_test_db, p, inner_id=1)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is not None

    @pytest.mark.asyncio
    async def test_open_mode_skips_my_skipped(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(
            async_test_db, owner, assignment_mode="open", skip_queue="requeue_for_others"
        )
        skipped = await _mk_task(async_test_db, p, inner_id=1)
        keep = await _mk_task(async_test_db, p, inner_id=2)
        await _mk_skip(async_test_db, skipped, p, owner)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"]["id"] == keep.id

    @pytest.mark.asyncio
    async def test_manual_mode_returns_and_starts_assignment(
        self, async_test_client, async_test_db
    ):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, worker, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(async_test_db, owner, is_private=False, assignment_mode="manual")
        await _link_org(async_test_db, p, org, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)
        assn = await _mk_assignment(async_test_db, t, worker, owner, status="assigned")
        await async_test_db.commit()

        with _as_user(worker):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"]["id"] == t.id
        # Assignment flipped assigned → in_progress.
        from sqlalchemy import select
        row = (
            await async_test_db.execute(select(TaskAssignment).where(TaskAssignment.id == assn.id))
        ).scalar_one()
        assert row.status == "in_progress"

    @pytest.mark.asyncio
    async def test_manual_mode_no_assignment(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, worker, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(async_test_db, owner, is_private=False, assignment_mode="manual")
        await _link_org(async_test_db, p, org, owner)
        await _mk_task(async_test_db, p, inner_id=1)  # not assigned to worker
        await async_test_db.commit()

        with _as_user(worker):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is None
        assert r.json()["detail"] == "No more assigned tasks"

    @pytest.mark.asyncio
    async def test_auto_mode_autoassigns_new_task(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, worker, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(
            async_test_db, owner, is_private=False, assignment_mode="auto", maximum_annotations=1,
        )
        await _link_org(async_test_db, p, org, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)
        await async_test_db.commit()

        with _as_user(worker):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"]["id"] == t.id
        # A self-assignment row was created on the fly.
        from sqlalchemy import select
        rows = (
            await async_test_db.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == t.id, TaskAssignment.user_id == worker.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_auto_mode_resumes_existing_assignment(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        worker = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, worker, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(async_test_db, owner, is_private=False, assignment_mode="auto")
        await _link_org(async_test_db, p, org, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)
        await _mk_assignment(async_test_db, t, worker, owner, status="in_progress")
        await async_test_db.commit()

        with _as_user(worker):
            r = await async_test_client.get(f"{PROJECTS}/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"]["id"] == t.id


# ===========================================================================
# GET /tasks/{task_id} — get_task
# ===========================================================================
@pytest.mark.integration
class TestGetTask:
    @pytest.mark.asyncio
    async def test_get_task_success(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, inner_id=7, data={"text": "hi"})
        await _mk_generation(async_test_db, t, model_id="gpt-4")
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/tasks/{t.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == t.id
        assert body["inner_id"] == 7
        assert body["total_generations"] == 1
        assert body["project_id"] == p.id
        assert "comment_count" in body

    @pytest.mark.asyncio
    async def test_get_task_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.get(f"{PROJECTS}/tasks/missing-{_uid()}")
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_get_task_access_denied_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        outsider = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner, is_private=True)
        t = await _mk_task(async_test_db, p, inner_id=1)
        await async_test_db.commit()
        with _as_user(outsider):
            r = await async_test_client.get(f"{PROJECTS}/tasks/{t.id}")
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_get_task_manual_mode_unassigned_is_hidden(
        self, async_test_client, async_test_db
    ):
        """In manual mode an unassigned annotator gets 404 (Label-Studio-aligned
        invisibility), not 403."""
        owner = await _mk_user(async_test_db)
        annotator = await _mk_user(async_test_db, superadmin=False)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, annotator, org, OrganizationRole.ANNOTATOR)
        p = await _mk_project(async_test_db, owner, is_private=False, assignment_mode="manual")
        await _link_org(async_test_db, p, org, owner)
        t = await _mk_task(async_test_db, p, inner_id=1)  # not assigned to annotator
        await async_test_db.commit()

        with _as_user(annotator):
            r = await async_test_client.get(f"{PROJECTS}/tasks/{t.id}")
        assert r.status_code == 404, r.text
