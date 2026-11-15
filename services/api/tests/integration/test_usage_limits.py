"""Per-user abuse ceilings (services/usage_limits.py): the request after the
limit answers 429 with Retry-After and a stable code, 0 switches a ceiling
off, and each refusal counts in ``benger_rate_limited_total``.

- BEARER_TOKEN_RPM: session tokens sent as ``Authorization: Bearer``.
- UPLOAD_URLS_PER_DAY: both import upload-url routes together.
- MAX_ACTIVE_RUNS_PER_USER: generation and evaluation starts.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry

from app.core.config import settings
from auth_module import create_access_token
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import EvaluationRun, ResponseGeneration, User
from project_models import Project, Task
from services import limit_metrics
from services import rate_limiter as rl


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def registry():
    """Fresh metric counters for the test."""
    reg = CollectorRegistry()
    limit_metrics.use_registry(reg)
    yield reg
    limit_metrics.use_registry(None)


def _refused(registry, limit: str) -> float:
    return registry.get_sample_value("benger_rate_limited_total", {"limit": limit}) or 0.0


@pytest.fixture
def limiter_on(client, monkeypatch):
    """The real limiter on its memory backend with the TESTING bypass off
    (after ``client``, which sets TESTING=true for its lifetime)."""
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
    monkeypatch.setattr(rl.rate_limiter, "_memory_store", {})
    return rl.rate_limiter


@contextmanager
def _as_user(db_user):
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


def _user(db, *, superadmin=False) -> User:
    user = User(
        id=_uid(),
        username=f"ul-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Limit User",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'user_id': user.id})}"}


# --------------------------------------------------------------------------- #
# BEARER_TOKEN_RPM
# --------------------------------------------------------------------------- #


@pytest.mark.integration
class TestBearerTokenLimit:
    def test_request_after_the_limit_answers_429(
        self, client, test_db, limiter_on, registry, monkeypatch
    ):
        monkeypatch.setattr(settings, "bearer_token_rpm", 3)
        user = _user(test_db)
        test_db.commit()
        for _ in range(3):
            assert client.get("/api/auth/me", headers=_bearer(user)).status_code == 200
        r = client.get("/api/auth/me", headers=_bearer(user))
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == "rate_limited"
        assert 1 <= int(r.headers["Retry-After"]) <= 60
        assert r.headers["X-RateLimit-Limit"] == "3"
        assert _refused(registry, "user_bearer") == 1
        # Per user: another user's token is not affected.
        other = _user(test_db)
        test_db.commit()
        assert client.get("/api/auth/me", headers=_bearer(other)).status_code == 200

    def test_v1_answers_in_the_v1_envelope(self, client, test_db, limiter_on, monkeypatch):
        monkeypatch.setattr(settings, "bearer_token_rpm", 1)
        user = _user(test_db)
        test_db.commit()
        assert client.get("/api/v1/me", headers=_bearer(user)).status_code == 200
        r = client.get("/api/v1/me", headers=_bearer(user))
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in r.headers

    def test_cookie_sessions_are_not_counted(self, client, test_db, limiter_on, monkeypatch):
        monkeypatch.setattr(settings, "bearer_token_rpm", 1)
        user = _user(test_db)
        test_db.commit()
        token = create_access_token(data={"user_id": user.id})
        client.cookies.set("access_token", token)
        try:
            for _ in range(4):
                assert client.get("/api/auth/me").status_code == 200
            # A bearer header next to the cookie: the cookie authenticates
            # (outside /api/v1), so this is a browser request too.
            for _ in range(3):
                r = client.get("/api/auth/me", headers=_bearer(user))
                assert r.status_code == 200
        finally:
            client.cookies.clear()

    def test_zero_disables_and_superadmins_are_exempt(
        self, client, test_db, limiter_on, monkeypatch
    ):
        user = _user(test_db)
        admin = _user(test_db, superadmin=True)
        test_db.commit()
        monkeypatch.setattr(settings, "bearer_token_rpm", 0)
        for _ in range(5):
            assert client.get("/api/auth/me", headers=_bearer(user)).status_code == 200
        monkeypatch.setattr(settings, "bearer_token_rpm", 1)
        for _ in range(3):
            assert client.get("/api/auth/me", headers=_bearer(admin)).status_code == 200


# --------------------------------------------------------------------------- #
# UPLOAD_URLS_PER_DAY
# --------------------------------------------------------------------------- #


_FAKE_UPLOAD = {"upload_url": "https://s3/x", "method": "POST", "fields": {}, "file_key": "k"}


@pytest.fixture
def async_limiter_on(async_test_client, monkeypatch):
    """:func:`limiter_on` for the async client."""
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
    monkeypatch.setattr(rl.rate_limiter, "_memory_store", {})
    return rl.rate_limiter


async def _async_user(db, *, superadmin=False) -> User:
    user = User(
        id=_uid(),
        username=f"ul-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Limit User",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _async_project(db, owner) -> Project:
    project = Project(
        id=_uid(),
        title="Upload limit",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()
    return project


def _mint():
    return patch(
        "routers.projects.import_export.object_storage.get_upload_url",
        return_value=_FAKE_UPLOAD,
    )


@pytest.mark.integration
class TestUploadUrlLimit:
    @pytest.mark.asyncio
    async def test_both_routes_share_one_allowance(
        self, async_test_client, async_test_db, async_limiter_on, registry, monkeypatch
    ):
        monkeypatch.setattr(settings, "upload_urls_per_day", 2)
        user = await _async_user(async_test_db)
        project = await _async_project(async_test_db, user)
        await async_test_db.commit()
        client = async_test_client
        with _as_user(user), _mint() as mint:
            r1 = await client.post(f"/api/projects/{project.id}/imports/upload-url")
            r2 = await client.post("/api/projects/project-imports/upload-url")
            r3 = await client.post("/api/projects/project-imports/upload-url")
            r4 = await client.post(f"/api/projects/{project.id}/imports/upload-url")
        assert (r1.status_code, r2.status_code) == (200, 200), (r1.text, r2.text)
        for r in (r3, r4):
            assert r.status_code == 429
            assert r.json()["detail"]["code"] == "upload_url_limit_exceeded"
            assert 86000 < int(r.headers["Retry-After"]) <= 86400
        # No upload policy was minted for the refused requests.
        assert mint.call_count == 2
        assert _refused(registry, "upload_url") == 2

    @pytest.mark.asyncio
    async def test_a_refused_route_check_does_not_use_the_allowance(
        self, async_test_client, async_test_db, async_limiter_on, monkeypatch
    ):
        monkeypatch.setattr(settings, "upload_urls_per_day", 1)
        owner = await _async_user(async_test_db)
        stranger = await _async_user(async_test_db)
        project = await _async_project(async_test_db, owner)
        await async_test_db.commit()
        client = async_test_client
        with _mint(), _as_user(stranger):
            forbidden = await client.post(f"/api/projects/{project.id}/imports/upload-url")
            ok = await client.post("/api/projects/project-imports/upload-url")
        assert forbidden.status_code == 403
        assert ok.status_code == 200

    @pytest.mark.asyncio
    async def test_zero_disables_and_superadmins_are_exempt(
        self, async_test_client, async_test_db, async_limiter_on, monkeypatch
    ):
        user = await _async_user(async_test_db)
        admin = await _async_user(async_test_db, superadmin=True)
        await async_test_db.commit()
        client = async_test_client
        with _mint():
            monkeypatch.setattr(settings, "upload_urls_per_day", 0)
            with _as_user(user):
                for _ in range(3):
                    r = await client.post("/api/projects/project-imports/upload-url")
                    assert r.status_code == 200
            monkeypatch.setattr(settings, "upload_urls_per_day", 1)
            with _as_user(admin):
                for _ in range(3):
                    r = await client.post("/api/projects/project-imports/upload-url")
                    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# MAX_ACTIVE_RUNS_PER_USER
# --------------------------------------------------------------------------- #


BLEU = {
    "id": "cfg-bleu",
    "metric": "bleu",
    "prediction_fields": ["answer"],
    "reference_fields": ["reference"],
    "enabled": True,
}


def _eval_run(db, user, project, *, status="pending", evaluation_type="evaluation"):
    db.add(
        EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id="m",
            evaluation_type_ids=["bleu"],
            metrics={},
            status=status,
            created_by=user.id,
            eval_metadata={"evaluation_type": evaluation_type},
        )
    )
    db.flush()


def _generation(db, user, project, *, status="pending"):
    db.add(
        ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="m",
            status=status,
            created_by=user.id,
        )
    )
    db.flush()


def _eval_project(db, user) -> Project:
    project = Project(
        id=_uid(),
        title="Run limit",
        created_by=user.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<TextArea name="answer" toName="text"/></View>'
        ),
    )
    db.add(project)
    db.flush()
    db.add(Task(id=_uid(), project_id=project.id, inner_id=1, data={"text": "Q", "reference": "A"}))
    db.flush()
    return project


def _start_evaluation(client, user, project, **extra):
    with _as_user(user), patch(
        "routers.evaluations.multi_field.run.celery_app.send_task",
        return_value=MagicMock(id="celery-run"),
    ), patch(
        "routers.evaluations.multi_field.run.resolve_user_org_for_project",
        return_value=None,
    ):
        return client.post(
            "/api/evaluations/run",
            json={"project_id": project.id, "evaluation_configs": [BLEU], **extra},
        )


@pytest.mark.integration
class TestActiveRunLimit:
    def test_evaluation_start_after_the_limit_answers_429(
        self, client, test_db, registry, monkeypatch
    ):
        monkeypatch.setattr(settings, "max_active_runs_per_user", 2)
        user = _user(test_db)
        project = _eval_project(test_db, user)
        # One evaluation and generation work on one project: two runs.
        _eval_run(test_db, user, project)
        _generation(test_db, user, project)
        _generation(test_db, user, project)
        # Not counted: finished or paused runs, immediate grading, other users.
        _eval_run(test_db, user, project, status="completed")
        _eval_run(test_db, user, project, status="paused")
        _eval_run(test_db, user, project, evaluation_type="immediate", status="running")
        _eval_run(test_db, _user(test_db), project)
        test_db.commit()

        r = _start_evaluation(client, user, project)
        assert r.status_code == 429, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "too_many_active_runs"
        assert detail["limit"] == 2 and detail["active"] == 2
        assert r.headers["Retry-After"] == "60"
        assert _refused(registry, "active_runs") == 1

        monkeypatch.setattr(settings, "max_active_runs_per_user", 3)
        assert _start_evaluation(client, user, project).status_code == 200
        # The new pending run fills the third slot.
        r = _start_evaluation(client, user, project, force_rerun=True)
        assert r.status_code == 429

    def test_zero_disables_and_superadmins_are_exempt(self, client, test_db, monkeypatch):
        user = _user(test_db)
        admin = _user(test_db, superadmin=True)
        project = _eval_project(test_db, user)
        _eval_run(test_db, user, project)
        _eval_run(test_db, admin, project)
        test_db.commit()
        monkeypatch.setattr(settings, "max_active_runs_per_user", 0)
        assert _start_evaluation(client, user, project).status_code == 200
        monkeypatch.setattr(settings, "max_active_runs_per_user", 1)
        assert _start_evaluation(client, admin, project).status_code == 200

    def test_resume_counts_the_resumed_run(self, client, test_db, monkeypatch):
        monkeypatch.setattr(settings, "max_active_runs_per_user", 1)
        user = _user(test_db)
        project = _eval_project(test_db, user)
        _eval_run(test_db, user, project)
        paused = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id="m",
            evaluation_type_ids=["bleu"],
            metrics={},
            status="paused",
            created_by=user.id,
            eval_metadata={"evaluation_type": "evaluation", "evaluation_configs": [BLEU]},
        )
        test_db.add(paused)
        test_db.commit()
        with _as_user(user), patch(
            "routers.evaluations.multi_field.lifecycle.celery_app.send_task",
            return_value=MagicMock(id="celery-resume"),
        ) as send:
            r = client.post(f"/api/evaluations/run/{paused.id}/resume")
        assert r.status_code == 429, r.text
        assert r.json()["detail"]["code"] == "too_many_active_runs"
        send.assert_not_called()
        test_db.refresh(paused)
        assert paused.status == "paused"


@pytest.mark.integration
class TestActiveRunLimitOnGeneration:
    """Generation has no run record: work on one project counts as one run,
    and more generation on a project that already generates is allowed."""

    async def _world(self, db, monkeypatch, limit):
        from tests.integration.test_generation_flow import (
            _add_membership,
            _create_project,
            _make_org,
            _make_user,
            _with_structures,
        )

        monkeypatch.setattr(settings, "max_active_runs_per_user", limit)
        user = await _make_user(db, is_superadmin=False, username_prefix="runlim")
        org = await _make_org(db)
        await _add_membership(db, user, org, role="CONTRIBUTOR")
        config = _with_structures({"selected_configuration": {"models": ["gpt-4o"]}})
        target = await _create_project(db, user, generation_config=config, org=org, num_tasks=2)
        other = await _create_project(db, user, generation_config=config, org=org, num_tasks=1)
        return user, target, other

    async def _start(self, client, user, project):
        from tests.integration.test_generation_flow import STRUCTURE_KEY

        with patch("routers.generation_task_list.celery_app") as celery, _as_user(user):
            r = await client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "missing", "structure_keys": [STRUCTURE_KEY]},
            )
        return r, celery

    @pytest.mark.asyncio
    async def test_new_project_after_the_limit_answers_429(
        self, async_test_client, async_test_db, registry, monkeypatch
    ):
        db = async_test_db
        user, target, other = await self._world(db, monkeypatch, limit=1)
        db.add(
            ResponseGeneration(
                id=_uid(), project_id=other.id, model_id="gpt-4o",
                status="running", created_by=user.id,
            )
        )
        await db.commit()

        r, celery = await self._start(async_test_client, user, target)
        assert r.status_code == 429, r.text
        assert r.json()["detail"]["code"] == "too_many_active_runs"
        assert r.headers["Retry-After"] == "60"
        celery.send_task.assert_not_called()
        assert _refused(registry, "active_runs") == 1

        # The project that already generates may queue more.
        r, celery = await self._start(async_test_client, user, other)
        assert r.status_code == 200, r.text

        # 0 switches the ceiling off.
        monkeypatch.setattr(settings, "max_active_runs_per_user", 0)
        r, _ = await self._start(async_test_client, user, target)
        assert r.status_code == 200, r.text
