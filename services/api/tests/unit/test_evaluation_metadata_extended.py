"""
Unit tests for routers/evaluations/metadata/* to increase coverage.
Tests evaluated models, configured methods, history, and significance endpoints.

The metadata handlers were migrated to the async DB lane (``Depends(get_async_db)``
+ ``await db.execute(select(...))``), so the old ``db.query``-Mock /
``get_db``-override pattern no longer reaches them. These now seed a real
``Project`` row via ``async_test_db`` and drive the surface through
``async_test_client``; the access branch is exercised by patching the async
accessibility helper ``check_project_accessible_async`` on the submodule where
each handler lives.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project


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


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"meta-unit-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta Unit User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, evaluation_config=None, generation_config=None):
    proj = Project(
        id=_uid(),
        title=f"Meta Unit {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(proj)
    await db.commit()
    return proj


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/evaluated-models
# ---------------------------------------------------------------------------


class TestGetEvaluatedModels:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluated-models"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluated-models"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_models(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, generation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluated-models"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/configured-methods
# ---------------------------------------------------------------------------


class TestGetConfiguredMethods:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/configured-methods"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_config(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_with_config(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db,
            user,
            evaluation_config={
                "selected_methods": {
                    "answer": {
                        "automated": ["bleu", "rouge_l"],
                        "human": [],
                    }
                }
            },
        )
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/evaluation-history
# ---------------------------------------------------------------------------


class TestGetEvaluationHistory:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluation-history",
                params={"model_ids": ["gpt-4"], "metrics": "bleu"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={"model_ids": ["gpt-4"], "metrics": "bleu"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_history(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        # Issue #111: ``/evaluation-history`` reads
        # ``project.evaluation_config.get("evaluation_configs")`` to resolve
        # series ``display_name``; a real project with NULL evaluation_config
        # exercises the skip-the-lookup path cleanly.
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={"model_ids": ["gpt-4"], "metrics": "bleu"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"series": []}


# ---------------------------------------------------------------------------
# GET /significance/{project_id}
# ---------------------------------------------------------------------------


class TestGetSignificanceTests:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/significance/nonexistent",
                params={"model_ids": ["gpt-4", "claude"], "metrics": ["bleu"]},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/significance/{proj.id}",
                params={"model_ids": ["gpt-4", "claude"], "metrics": ["bleu"]},
            )
        assert resp.status_code == 403
