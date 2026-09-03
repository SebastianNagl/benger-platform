"""Public-project write gates (authz audit follow-up).

A project with ``is_public=True`` is READABLE by every signed-in user
(``check_project_accessible``), and ``public_role`` says what a non-member
visitor may do on top of reading: ``ANNOTATOR`` = annotate only,
``CONTRIBUTOR`` = the documented contribute tier (generate / evaluate / import
/ export). Several WRITE and unblinded bulk-READ paths used to gate on the read
check alone, so any signed-in stranger could mutate a public project or dump
its reference solutions. These tests pin the tightened gates:

* ``PUT /api/evaluations/projects/{id}/evaluation-config`` — edit rights
  (``Permission.PROJECT_EDIT``, identical to ``PUT .../generation-config``):
  public visitors of either role 403, creator / org editors keep it.
* ``POST /api/evaluations/run`` — editors (incl. public CONTRIBUTOR) plus real
  org members of any role (the timed-window access group). Public ANNOTATOR
  visitors 403.
* ``PATCH /api/projects/tasks/{id}/metadata`` + ``bulk-metadata`` — write tier
  (effective ORG_ADMIN / CONTRIBUTOR).
* ``POST /api/projects/{id}/exports`` + ``POST .../tasks/bulk-export`` — write
  tier, i.e. exactly the roles that already see unblinded ``task.data``.

Two lanes: the evaluation-config PUT, ``/run`` and ``bulk-export`` handlers are
sync (``Depends(get_db)``) and use ``client``/``test_db``; the metadata and
export-job handlers are async and use ``async_test_client``/``async_test_db``.
Authentication is injected by overriding ``require_user`` (same pattern as
``test_participant_tier.py``), so no JWT round-trip is needed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task

LABEL_CONFIG = (
    '<View><Text name="sachverhalt" value="$sachverhalt"/>'
    '<TextArea name="answer" toName="sachverhalt"/></View>'
)
SECRET = "GEHEIME MUSTERLOESUNG"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _new_user(*, superadmin=False) -> User:
    return User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _new_project(owner, *, public_role=None) -> Project:
    """A project readable by everyone when ``public_role`` is given."""
    return Project(
        id=_uid(),
        title=f"P {_uid()[:6]}",
        created_by=owner.id,
        is_private=False,
        is_public=public_role is not None,
        public_role=public_role,
        label_config=LABEL_CONFIG,
        assignment_mode="open",
        evaluation_config={"selected_methods": {"answer": {"automated": ["bleu"]}}},
    )


def _new_task(project, owner, inner_id=1) -> Task:
    return Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"sachverhalt": "Fall", "musterloesung": SECRET},
        meta={"tag": "orig"},
        created_by=owner.id,
    )


def _new_org() -> Organization:
    slug = f"org-{_uid()[:8]}"
    return Organization(id=_uid(), name=slug, display_name=slug, slug=slug)


def _new_membership(user, org, role) -> OrganizationMembership:
    return OrganizationMembership(
        id=_uid(), user_id=user.id, organization_id=org.id, role=role, is_active=True
    )


# ────────────────────────────────────────────────────────────── sync lane ────


def _seed_sync(test_db, *, public_role):
    """owner + stranger + one task on a project. Returns (owner, stranger, p, task)."""
    owner, stranger = _new_user(), _new_user()
    test_db.add_all([owner, stranger])
    test_db.flush()
    p = _new_project(owner, public_role=public_role)
    test_db.add(p)
    test_db.flush()
    task = _new_task(p, owner)
    test_db.add(task)
    test_db.commit()
    return owner, stranger, p, task


def _seed_org_member_sync(test_db, role):
    """Non-public project attached to an org; ``member`` holds ``role`` there."""
    owner, member = _new_user(), _new_user()
    org = _new_org()
    test_db.add_all([owner, member, org])
    test_db.flush()
    test_db.add(_new_membership(member, org, role))
    p = _new_project(owner)
    test_db.add(p)
    test_db.flush()
    test_db.add(
        ProjectOrganization(id=_uid(), project_id=p.id, organization_id=org.id,
                            assigned_by=owner.id)
    )
    test_db.add(_new_task(p, owner))
    test_db.commit()
    return owner, member, p


EVAL_CONFIG_BODY = {"evaluation_configs": [{"id": "a", "metric": "bleu", "enabled": True}]}


@pytest.mark.integration
class TestEvaluationConfigPut:
    URL = "/api/evaluations/projects/{}/evaluation-config"

    def test_public_annotator_visitor_403(self, client, test_db):
        _owner, stranger, p, _t = _seed_sync(test_db, public_role="ANNOTATOR")
        with _as_user(stranger):
            r = client.put(self.URL.format(p.id), json=EVAL_CONFIG_BODY)
        assert r.status_code == 403, r.text
        test_db.expire_all()
        stored = test_db.query(Project).filter(Project.id == p.id).first().evaluation_config
        assert "evaluation_configs" not in stored

    def test_public_contributor_visitor_403_like_generation_config(self, client, test_db):
        # PROJECT_EDIT is hard-denied to every non-creator on a public project
        # — the same rule PUT /projects/{id}/generation-config applies (see
        # TestGenerationConfigParity below for the sibling).
        _owner, stranger, p, _t = _seed_sync(test_db, public_role="CONTRIBUTOR")
        with _as_user(stranger):
            r = client.put(self.URL.format(p.id), json=EVAL_CONFIG_BODY)
        assert r.status_code == 403, r.text

    def test_creator_keeps_editing_public_project(self, client, test_db):
        owner, _stranger, p, _t = _seed_sync(test_db, public_role="ANNOTATOR")
        with _as_user(owner):
            r = client.put(self.URL.format(p.id), json=EVAL_CONFIG_BODY)
        assert r.status_code == 200, r.text
        test_db.expire_all()
        stored = test_db.query(Project).filter(Project.id == p.id).first().evaluation_config
        assert stored["evaluation_configs"] == EVAL_CONFIG_BODY["evaluation_configs"]
        # deep-merge contract untouched: sibling key survives
        assert stored["selected_methods"] == {"answer": {"automated": ["bleu"]}}

    @pytest.mark.parametrize("role", ["ORG_ADMIN", "CONTRIBUTOR"])
    def test_org_editor_keeps_editing(self, client, test_db, role):
        _owner, member, p = _seed_org_member_sync(test_db, role)
        with _as_user(member):
            r = client.put(self.URL.format(p.id), json=EVAL_CONFIG_BODY)
        assert r.status_code == 200, r.text

    def test_org_annotator_403(self, client, test_db):
        _owner, member, p = _seed_org_member_sync(test_db, "ANNOTATOR")
        with _as_user(member):
            r = client.put(self.URL.format(p.id), json=EVAL_CONFIG_BODY)
        assert r.status_code == 403, r.text


RUN_BODY_PROBE = {"evaluation_configs": []}
# An empty config list passes every access gate and then 400s ("No evaluation
# configurations provided"), so 400 == "the gate admitted this user" without
# having to stand up a Celery dispatch; 403 == blocked by the launch gate.


@pytest.mark.integration
class TestEvaluationRun:
    URL = "/api/evaluations/run"

    def _post(self, client, project):
        return client.post(self.URL, json={"project_id": project.id, **RUN_BODY_PROBE})

    def test_public_annotator_visitor_403(self, client, test_db):
        _owner, stranger, p, _t = _seed_sync(test_db, public_role="ANNOTATOR")
        with _as_user(stranger):
            r = self._post(client, p)
        assert r.status_code == 403, r.text
        assert "members, contributors or admins" in r.json()["detail"]

    def test_public_contributor_visitor_keeps_documented_right(self, client, test_db):
        _owner, stranger, p, _t = _seed_sync(test_db, public_role="CONTRIBUTOR")
        with _as_user(stranger):
            r = self._post(client, p)
        assert r.status_code == 400, r.text

    def test_creator_and_superadmin_pass_gate(self, client, test_db):
        owner, _stranger, p, _t = _seed_sync(test_db, public_role="ANNOTATOR")
        root = _new_user(superadmin=True)
        test_db.add(root)
        test_db.commit()
        for u in (owner, root):
            with _as_user(u):
                r = self._post(client, p)
            assert r.status_code == 400, (u.id, r.text)

    @pytest.mark.parametrize("role", ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR"])
    def test_real_org_members_of_any_role_pass_gate(self, client, test_db, role):
        # Org ANNOTATORs are the timed-window "access group" the window gate
        # exists for — membership-based, so public_role never grants it.
        _owner, member, p = _seed_org_member_sync(test_db, role)
        with _as_user(member):
            r = self._post(client, p)
        assert r.status_code == 400, r.text

    def test_non_member_on_private_project_403(self, client, test_db):
        _owner, stranger, p, _t = _seed_sync(test_db, public_role=None)
        with _as_user(stranger):
            r = self._post(client, p)
        assert r.status_code == 403, r.text


@pytest.mark.integration
class TestBulkExport:
    URL = "/api/projects/{}/tasks/bulk-export"

    def test_public_annotator_visitor_403_no_reference_leak(self, client, test_db):
        _owner, stranger, p, t = _seed_sync(test_db, public_role="ANNOTATOR")
        with _as_user(stranger):
            r = client.post(self.URL.format(p.id), json={"format": "json", "task_ids": [t.id]})
        assert r.status_code == 403, r.text
        assert SECRET not in r.text

    def test_public_contributor_visitor_exports_full_data(self, client, test_db):
        _owner, stranger, p, t = _seed_sync(test_db, public_role="CONTRIBUTOR")
        with _as_user(stranger):
            r = client.post(self.URL.format(p.id), json={"format": "json", "task_ids": [t.id]})
        assert r.status_code == 200, r.text
        assert SECRET in r.text

    def test_creator_exports(self, client, test_db):
        owner, _stranger, p, t = _seed_sync(test_db, public_role="ANNOTATOR")
        with _as_user(owner):
            r = client.post(self.URL.format(p.id), json={"format": "csv", "task_ids": [t.id]})
        assert r.status_code == 200, r.text
        assert SECRET in r.text

    def test_org_contributor_exports_org_annotator_blocked(self, client, test_db):
        _owner, contrib, p = _seed_org_member_sync(test_db, "CONTRIBUTOR")
        with _as_user(contrib):
            r = client.post(self.URL.format(p.id), json={"format": "json"})
        assert r.status_code == 200, r.text
        _owner2, annot, p2 = _seed_org_member_sync(test_db, "ANNOTATOR")
        with _as_user(annot):
            r = client.post(self.URL.format(p2.id), json={"format": "json"})
        assert r.status_code == 403, r.text
        assert SECRET not in r.text


# ───────────────────────────────────────────────────────────── async lane ────


async def _seed_async(db, *, public_role):
    """Returns (owner, stranger, project, [task_id, task_id])."""
    owner, stranger = _new_user(), _new_user()
    db.add_all([owner, stranger])
    await db.flush()
    p = _new_project(owner, public_role=public_role)
    db.add(p)
    await db.flush()
    tasks = [_new_task(p, owner, inner_id=i + 1) for i in range(2)]
    db.add_all(tasks)
    task_ids = [t.id for t in tasks]
    await db.commit()
    return owner, stranger, p, task_ids


async def _meta(db, task_id):
    return (await db.execute(select(Task.meta).where(Task.id == task_id))).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskMetadataPatch:
    SINGLE = "/api/projects/tasks/{}/metadata"
    BULK = "/api/projects/tasks/bulk-metadata"

    async def test_public_annotator_visitor_403_both_endpoints(
        self, async_test_client, async_test_db
    ):
        db = async_test_db
        _owner, stranger, _p, task_ids = await _seed_async(db, public_role="ANNOTATOR")
        with _as_user(stranger):
            r1 = await async_test_client.patch(
                self.SINGLE.format(task_ids[0]), json={"tag": "hacked"}
            )
            r2 = await async_test_client.patch(
                self.BULK,
                json={"task_ids": task_ids, "metadata": {"tag": "hacked"}},
            )
        assert r1.status_code == 403, r1.text
        assert r2.status_code == 403, r2.text
        for tid in task_ids:
            assert await _meta(db, tid) == {"tag": "orig"}

    async def test_public_contributor_visitor_keeps_documented_right(
        self, async_test_client, async_test_db
    ):
        db = async_test_db
        _owner, stranger, _p, task_ids = await _seed_async(db, public_role="CONTRIBUTOR")
        with _as_user(stranger):
            r1 = await async_test_client.patch(
                self.SINGLE.format(task_ids[0]), json={"extra": 1}
            )
            r2 = await async_test_client.patch(
                self.BULK,
                json={"task_ids": [task_ids[1]], "metadata": {"bulk": True}},
            )
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert await _meta(db, task_ids[0]) == {"tag": "orig", "extra": 1}
        assert await _meta(db, task_ids[1]) == {"tag": "orig", "bulk": True}

    async def test_creator_keeps_working(self, async_test_client, async_test_db):
        db = async_test_db
        owner, _stranger, _p, task_ids = await _seed_async(db, public_role="ANNOTATOR")
        with _as_user(owner):
            r = await async_test_client.patch(
                self.SINGLE.format(task_ids[0]) + "?merge=false", json={"only": "this"}
            )
        assert r.status_code == 200, r.text
        assert await _meta(db, task_ids[0]) == {"only": "this"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestExportJobCreate:
    URL = "/api/projects/{}/exports?format=json"

    @contextmanager
    def _worker_stubbed(self):
        fake = MagicMock()
        fake.id = "celery-task-xyz"
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake
        ) as mock_send:
            yield mock_send

    async def test_public_annotator_visitor_403_nothing_enqueued(
        self, async_test_client, async_test_db
    ):
        _owner, stranger, p, _task_ids = await _seed_async(async_test_db, public_role="ANNOTATOR")
        with _as_user(stranger), self._worker_stubbed() as mock_send:
            r = await async_test_client.post(self.URL.format(p.id))
        assert r.status_code == 403, r.text
        mock_send.assert_not_called()

    async def test_public_contributor_visitor_202(self, async_test_client, async_test_db):
        _owner, stranger, p, _task_ids = await _seed_async(async_test_db, public_role="CONTRIBUTOR")
        with _as_user(stranger), self._worker_stubbed() as mock_send:
            r = await async_test_client.post(self.URL.format(p.id))
        assert r.status_code == 202, r.text
        mock_send.assert_called_once()

    async def test_creator_202(self, async_test_client, async_test_db):
        owner, _stranger, p, _task_ids = await _seed_async(async_test_db, public_role="ANNOTATOR")
        with _as_user(owner), self._worker_stubbed():
            r = await async_test_client.post(self.URL.format(p.id))
        assert r.status_code == 202, r.text

    async def test_non_member_on_private_project_403(self, async_test_client, async_test_db):
        _owner, stranger, p, _task_ids = await _seed_async(async_test_db, public_role=None)
        with _as_user(stranger), self._worker_stubbed():
            r = await async_test_client.post(self.URL.format(p.id))
        assert r.status_code == 403, r.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGenerationConfigParity:
    """The evaluation-config PUT now uses the generation-config PUT's gate; pin
    the sibling's public-project rule so the two can't drift apart silently."""

    URL = "/api/projects/{}/generation-config"

    @pytest.mark.parametrize("public_role", ["ANNOTATOR", "CONTRIBUTOR"])
    async def test_public_visitor_403(self, async_test_client, async_test_db, public_role):
        _owner, stranger, p, _task_ids = await _seed_async(async_test_db, public_role=public_role)
        with _as_user(stranger):
            r = await async_test_client.put(self.URL.format(p.id), json={"x": 1})
        assert r.status_code == 403, r.text

    async def test_creator_200(self, async_test_client, async_test_db):
        owner, _stranger, p, _task_ids = await _seed_async(async_test_db, public_role="ANNOTATOR")
        with _as_user(owner):
            r = await async_test_client.put(self.URL.format(p.id), json={"x": 1})
        assert r.status_code == 200, r.text
