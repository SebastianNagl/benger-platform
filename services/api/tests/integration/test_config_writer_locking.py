"""Issue #291: Project JSONB config writers must lock the row before merging.

Every config writer does a read-merge-write in Python (deep_merge_dicts), so
without a row lock two concurrent writers can resurrect each other's stale
keys. These tests capture the SQL actually emitted against the test Postgres
and assert the project load runs FOR UPDATE on the write paths.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import status
from sqlalchemy import event

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


@contextmanager
def _capture_statements(engine):
    """Record every SQL statement the engine executes while active."""
    captured = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        yield captured
    finally:
        event.remove(engine, "before_cursor_execute", _capture)


def _project_loads_locked(statements) -> bool:
    return any(
        "projects" in stmt and "FOR UPDATE" in stmt.upper()
        for stmt in statements
        if stmt.strip().upper().startswith("SELECT")
    )


async def _seed(db):
    user = User(
        id=_uid(),
        username=f"lock-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Lock Tester",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    project = Project(
        id=_uid(),
        title=f"Lock Project {uuid.uuid4().hex[:6]}",
        created_by=user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={"existing": {"keep": True}},
    )
    db.add(project)
    await db.commit()
    return user, project


class TestConfigWriterLocking:
    @pytest.mark.asyncio
    async def test_patch_project_locks_row(self, async_test_client, async_test_db):
        user, project = await _seed(async_test_db)
        engine = async_test_db.sync_session.get_bind().engine

        with _as_user(user), _capture_statements(engine) as statements:
            response = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"generation_config": {"new_key": {"a": 1}}},
            )
        assert response.status_code == status.HTTP_200_OK
        assert _project_loads_locked(statements), (
            "PATCH /projects/{id} must load the project FOR UPDATE before "
            "deep-merging the JSONB config columns (issue #291)"
        )

    @pytest.mark.asyncio
    async def test_patch_merge_preserves_sibling_keys(
        self, async_test_client, async_test_db
    ):
        user, project = await _seed(async_test_db)

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"generation_config": {"new_key": {"a": 1}}},
            )
        assert response.status_code == status.HTTP_200_OK

        refreshed = await async_test_db.get(Project, project.id)
        await async_test_db.refresh(refreshed)
        assert refreshed.generation_config["existing"] == {"keep": True}
        assert refreshed.generation_config["new_key"] == {"a": 1}

    @pytest.mark.asyncio
    async def test_prompt_structure_put_locks_row(
        self, async_test_client, async_test_db
    ):
        user, project = await _seed(async_test_db)
        engine = async_test_db.sync_session.get_bind().engine

        with _as_user(user), _capture_statements(engine) as statements:
            response = await async_test_client.put(
                f"/api/projects/{project.id}/generation-config/structures/s1",
                json={
                    "name": "S1",
                    "system_prompt": "sys",
                    "instruction_prompt": "inst",
                },
            )
        assert response.status_code == status.HTTP_200_OK
        assert _project_loads_locked(statements), (
            "prompt-structure writes must load the project FOR UPDATE "
            "(issue #291)"
        )

    @pytest.mark.asyncio
    async def test_eval_config_get_migration_write_locks_row(
        self, async_test_client, async_test_db
    ):
        """The GET lazy-migration path derives+writes evaluation_configs and
        must re-acquire the row under a lock before doing so."""
        user, project = await _seed(async_test_db)
        project.evaluation_config = {
            "label_config_version": "v1",
            "selected_methods": {
                "text": {
                    "automated": ["exact_match"],
                    "field_mapping": {
                        "prediction_field": "text",
                        "reference_field": "text",
                    },
                }
            },
        }
        project.label_config_version = "v1"
        await async_test_db.commit()

        engine = async_test_db.sync_session.get_bind().engine
        with _as_user(user), _capture_statements(engine) as statements:
            response = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json().get("evaluation_configs"), (
            "lazy migration should have derived evaluation_configs"
        )
        assert _project_loads_locked(statements)

    @pytest.mark.asyncio
    async def test_eval_config_get_plain_read_takes_no_lock(
        self, async_test_client, async_test_db
    ):
        """A GET that needs no derivation write must stay lock-free — it is
        the hot read path on every project page load."""
        user, project = await _seed(async_test_db)
        project.evaluation_config = {
            "label_config_version": "v1",
            "selected_methods": {},
            "evaluation_configs": [{"metric": "exact_match", "fields": ["text"]}],
            "detected_answer_types": [],
            "available_methods": {},
        }
        project.label_config_version = "v1"
        await async_test_db.commit()

        engine = async_test_db.sync_session.get_bind().engine
        with _as_user(user), _capture_statements(engine) as statements:
            response = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert response.status_code == status.HTTP_200_OK
        assert not _project_loads_locked(statements)
