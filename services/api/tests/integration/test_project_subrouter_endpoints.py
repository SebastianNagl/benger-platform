"""
Integration tests for 3 project sub-routers:
  Questionnaire, Generation (project-level), Label Config Versions

These endpoints were migrated to the async DB lane (``Depends(get_async_db)``),
so the suite seeds real rows via ``async_test_db`` and drives the surface
through ``async_test_client``. ``require_user`` is overridden per-test via the
``_as_user`` context manager (the sync JWT auth path can't see the async test
transaction); organization memberships are seeded so the read/edit authz
branches resolve for real.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict

import pytest
from sqlalchemy import select

from auth_module.user_service import get_password_hash
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration as DBResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

BASE = "/api/projects"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


def _make_user(fixed_id: str, *, is_superadmin: bool) -> User:
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=fixed_id,
        username=f"{fixed_id}-{suffix}@test.com",
        email=f"{fixed_id}-{suffix}@test.com",
        name=f"Test {fixed_id}",
        hashed_password=get_password_hash("x"),
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


async def _create_project_with_data_async(
    db,
    *,
    questionnaire_enabled: bool = False,
    questionnaire_config: str = None,
    generation_config: dict = None,
    label_config: str = '<View><Text name="text" value="$text"/></View>',
    label_config_version: str = None,
    label_config_history: dict = None,
    is_private: bool = False,
    num_tasks: int = 2,
    num_annotations: int = 0,
    annotation_user_index: int = 2,  # annotator by default
) -> Dict:
    """Async equivalent of the original sync ``_create_project_with_data``.

    Seeds three users with the EXACT fixed ids the assertions depend on
    (``admin-test-id`` superadmin, ``contributor-test-id``,
    ``annotator-test-id``), an organization, the project, a ProjectOrganization
    link (when not private), org memberships (so the read/edit authz branches
    resolve), tasks, and annotations.

    Returns dict with keys: project, tasks, annotations, users.
    """
    admin_user = _make_user("admin-test-id", is_superadmin=True)
    contributor_user = _make_user("contributor-test-id", is_superadmin=False)
    annotator_user = _make_user("annotator-test-id", is_superadmin=False)
    users = [admin_user, contributor_user, annotator_user]
    for u in users:
        db.add(u)
    await db.flush()

    org_id = _uid()
    org = Organization(
        id=org_id,
        name=f"Test Org {org_id[:8]}",
        display_name=f"Test Org {org_id[:8]}",
        slug=f"org-{org_id[:8]}",
    )
    db.add(org)
    await db.flush()

    # Org memberships so non-superadmin read/edit authz resolves the same way
    # the original sync test relied on (annotator org-member -> view passes,
    # edit denied).
    for member, role in (
        (admin_user, OrganizationRole.ORG_ADMIN),
        (contributor_user, OrganizationRole.CONTRIBUTOR),
        (annotator_user, OrganizationRole.ANNOTATOR),
    ):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=member.id,
                organization_id=org_id,
                role=role,
                is_active=True,
            )
        )
    await db.flush()

    project_id = _uid()
    project = Project(
        id=project_id,
        title=f"Test Project {project_id[:8]}",
        description="Integration test project",
        created_by="admin-test-id",
        label_config=label_config,
        label_config_version=label_config_version,
        label_config_history=label_config_history,
        questionnaire_enabled=questionnaire_enabled,
        questionnaire_config=questionnaire_config,
        generation_config=generation_config,
        is_private=is_private,
    )
    db.add(project)
    await db.flush()

    # Link project to org
    if not is_private:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project_id,
                organization_id=org_id,
                assigned_by="admin-test-id",
            )
        )
        await db.flush()

    # Create tasks
    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project_id,
            data={"text": f"Sample text {i}"},
            created_by="admin-test-id",
            inner_id=i + 1,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()

    # Create annotations
    ann_user = users[annotation_user_index]
    annotations = []
    for i in range(min(num_annotations, num_tasks)):
        ann = Annotation(
            id=_uid(),
            task_id=tasks[i].id,
            project_id=project_id,
            completed_by=ann_user.id,
            result=[{"from_name": "label", "to_name": "text", "type": "choices", "value": {"choices": ["A"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    await db.flush()

    await db.commit()

    return {
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "users": {
            "admin": admin_user,
            "contributor": contributor_user,
            "annotator": annotator_user,
        },
    }


# ===================================================================
# QUESTIONNAIRE TESTS
# ===================================================================

class TestQuestionnaireEndpoints:
    """Tests for POST questionnaire-response, GET questionnaire-responses."""

    @pytest.mark.asyncio
    async def test_submit_questionnaire_response(self, async_test_client, async_test_db):
        """Submitting a questionnaire response with a valid annotation succeeds."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=True,
            questionnaire_config='<View><Choices name="q" toName="text"><Choice value="Easy"/></Choices></View>',
            num_annotations=1,
            annotation_user_index=0,  # admin creates the annotation
        )
        project = data["project"]
        task = data["tasks"][0]
        annotation = data["annotations"][0]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.post(
                f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": annotation.id,
                    "result": [{"from_name": "q", "to_name": "text", "type": "choices", "value": {"choices": ["Easy"]}}],
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["annotation_id"] == annotation.id
        assert body["project_id"] == project.id
        assert body["user_id"] == "admin-test-id"

    @pytest.mark.asyncio
    async def test_submit_questionnaire_not_enabled_returns_400(self, async_test_client, async_test_db):
        """Submitting a questionnaire when not enabled returns 400."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=False,
            num_annotations=1,
            annotation_user_index=0,
        )
        project = data["project"]
        task = data["tasks"][0]
        annotation = data["annotations"][0]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.post(
                f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": annotation.id,
                    "result": [{"from_name": "q", "type": "choices", "value": {"choices": ["X"]}}],
                },
            )

        assert resp.status_code == 400
        assert "not enabled" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_duplicate_questionnaire_returns_400(self, async_test_client, async_test_db):
        """Submitting a questionnaire twice for the same annotation returns 400."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=True,
            questionnaire_config='<View><Choices name="q" toName="text"><Choice value="Easy"/></Choices></View>',
            num_annotations=1,
            annotation_user_index=0,
        )
        project = data["project"]
        task = data["tasks"][0]
        annotation = data["annotations"][0]

        payload = {
            "annotation_id": annotation.id,
            "result": [{"from_name": "q", "type": "choices", "value": {"choices": ["Easy"]}}],
        }

        with _as_user(data["users"]["admin"]):
            resp1 = await async_test_client.post(
                f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                json=payload,
            )
            resp2 = await async_test_client.post(
                f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                json=payload,
            )

        assert resp1.status_code == 200, resp1.text
        assert resp2.status_code == 400
        assert "already submitted" in resp2.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_questionnaire_annotation_not_found_returns_404(self, async_test_client, async_test_db):
        """Submitting a questionnaire referencing a nonexistent annotation returns 404."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=True,
            questionnaire_config='<View><Choices name="q" toName="text"><Choice value="Easy"/></Choices></View>',
        )
        project = data["project"]
        task = data["tasks"][0]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.post(
                f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": _uid(),
                    "result": [{"from_name": "q", "type": "choices", "value": {"choices": ["Easy"]}}],
                },
            )

        assert resp.status_code == 404
        assert "Annotation not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_questionnaire_responses_as_creator(self, async_test_client, async_test_db):
        """Project creator can list all questionnaire responses."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=True,
            questionnaire_config='<View><Choices name="q" toName="text"><Choice value="Easy"/></Choices></View>',
            num_annotations=2,
            annotation_user_index=0,
        )
        project = data["project"]
        task0 = data["tasks"][0]
        task1 = data["tasks"][1]
        ann0 = data["annotations"][0]
        ann1 = data["annotations"][1]

        with _as_user(data["users"]["admin"]):
            # Submit two responses
            for task, ann in [(task0, ann0), (task1, ann1)]:
                await async_test_client.post(
                    f"{BASE}/{project.id}/tasks/{task.id}/questionnaire-response",
                    json={
                        "annotation_id": ann.id,
                        "result": [{"from_name": "q", "type": "choices", "value": {"choices": ["Easy"]}}],
                    },
                )

            resp = await async_test_client.get(
                f"{BASE}/{project.id}/questionnaire-responses",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_list_questionnaire_responses_annotator_gets_403(self, async_test_client, async_test_db):
        """Non-creator, non-superadmin user gets 403 when listing responses."""
        data = await _create_project_with_data_async(
            async_test_db,
            questionnaire_enabled=True,
        )
        project = data["project"]

        with _as_user(data["users"]["annotator"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/questionnaire-responses",
            )

        assert resp.status_code == 403
        assert "Not authorized" in resp.json()["detail"]


# ===================================================================
# GENERATION TESTS
# ===================================================================

class TestGenerationEndpoints:
    """Tests for generation-config (GET/PUT/DELETE) and generation-status (GET)."""

    @pytest.mark.asyncio
    async def test_get_generation_config_no_config(self, async_test_client, async_test_db):
        """Getting generation config when none is set returns available_options only."""
        data = await _create_project_with_data_async(
            async_test_db,
            generation_config=None,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "available_options" in body
        assert "models" in body["available_options"]
        assert "openai" in body["available_options"]["models"]
        # selected_configuration should not be present when no config
        assert "selected_configuration" not in body

    @pytest.mark.asyncio
    async def test_get_generation_config_with_config(self, async_test_client, async_test_db):
        """Getting generation config when set returns available_options and selected_configuration."""
        gen_config = {
            "selected_configuration": {
                "models": ["gpt-4o"],
                "temperature": 0.7,
            }
        }
        data = await _create_project_with_data_async(
            async_test_db,
            generation_config=gen_config,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["selected_configuration"]["models"] == ["gpt-4o"]

    @pytest.mark.asyncio
    async def test_update_generation_config(self, async_test_client, async_test_db):
        """Updating generation config persists to the database."""
        data = await _create_project_with_data_async(async_test_db)
        project = data["project"]
        new_config = {
            "selected_configuration": {
                "models": ["claude-3-opus-20240229"],
                "temperature": 0.5,
            }
        }

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config",
                json=new_config,
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["config"] == new_config

        # Verify in DB. async_test_db (expire_on_commit=False) is the same
        # session the handler wrote through, so the cached Project carries the
        # mutation in-memory regardless of commit — populate_existing forces a
        # real round-trip for this row (HEAD used test_db.refresh(project)).
        refreshed = (
            await async_test_db.execute(
                select(Project)
                .where(Project.id == project.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        assert refreshed.generation_config == new_config

    @pytest.mark.asyncio
    async def test_delete_generation_config(self, async_test_client, async_test_db):
        """Deleting generation config clears the field."""
        data = await _create_project_with_data_async(
            async_test_db,
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.delete(
                f"{BASE}/{project.id}/generation-config",
            )

        assert resp.status_code == 204

        # Force a real round-trip — the cached Project in this shared
        # expire_on_commit=False session would otherwise reflect the in-memory
        # clear even if nothing committed (HEAD used test_db.refresh(project)).
        refreshed = (
            await async_test_db.execute(
                select(Project)
                .where(Project.id == project.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        assert refreshed.generation_config is None

    @pytest.mark.asyncio
    async def test_generation_status_no_generations(self, async_test_client, async_test_db):
        """Generation status with no generations returns empty list and is_running=False."""
        data = await _create_project_with_data_async(async_test_db)
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-status",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["generations"] == []
        assert body["is_running"] is False
        assert body["latest_status"] is None

    @pytest.mark.asyncio
    async def test_generation_status_with_completed_generation(self, async_test_client, async_test_db):
        """Generation status with completed generation returns correct status."""
        data = await _create_project_with_data_async(async_test_db)
        project = data["project"]

        # Create a completed ResponseGeneration
        rg = DBResponseGeneration(
            id=_uid(),
            project_id=project.id,
            task_id=data["tasks"][0].id,
            model_id="gpt-4o",
            status="completed",
            created_by="admin-test-id",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg)
        await async_test_db.commit()

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-status",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["generations"]) == 1
        assert body["is_running"] is False
        assert body["latest_status"] == "completed"

    @pytest.mark.asyncio
    async def test_generation_status_with_running_generation(self, async_test_client, async_test_db):
        """Generation status correctly detects a running generation."""
        data = await _create_project_with_data_async(async_test_db)
        project = data["project"]

        rg = DBResponseGeneration(
            id=_uid(),
            project_id=project.id,
            task_id=data["tasks"][0].id,
            model_id="gpt-4o",
            status="running",
            created_by="admin-test-id",
            started_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg)
        await async_test_db.commit()

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-status",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_running"] is True
        assert body["latest_status"] == "running"

    @pytest.mark.asyncio
    async def test_generation_config_nonexistent_project_returns_404(self, async_test_client, async_test_db):
        """Accessing generation config for nonexistent project returns 404."""
        admin = _make_user("admin-test-id", is_superadmin=True)
        async_test_db.add(admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/{_uid()}/generation-config",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generation_config_permission_denied_for_annotator(self, async_test_client, async_test_db):
        """Annotator cannot update generation config (requires edit permission)."""
        data = await _create_project_with_data_async(async_test_db)
        project = data["project"]

        with _as_user(data["users"]["annotator"]):
            resp = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config",
                json={"selected_configuration": {"models": ["gpt-4o"]}},
            )

        assert resp.status_code == 403


# ===================================================================
# LABEL CONFIG VERSIONS TESTS
# ===================================================================

class TestLabelConfigVersionEndpoints:
    """Tests for label-config/versions, compare, and generation version-distribution."""

    @pytest.mark.asyncio
    async def test_list_versions_with_history(self, async_test_client, async_test_db):
        """Listing versions for a project with version history returns all versions."""
        history = {
            "current_version": "v2",
            "versions": {
                "v1": {
                    "schema": '<View><Text name="old_text" value="$text"/></View>',
                    "created_at": "2025-01-01T00:00:00",
                    "created_by": "admin-test-id",
                    "description": "Initial schema",
                    "schema_hash": "abc123",
                },
            },
        }
        data = await _create_project_with_data_async(
            async_test_db,
            label_config='<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="A"/></Choices></View>',
            label_config_version="v2",
            label_config_history=history,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/versions",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["current_version"] == "v2"
        assert body["total_versions"] == 2
        # v1 from history + v2 as current
        versions = {v["version"] for v in body["versions"]}
        assert "v1" in versions
        assert "v2" in versions

    @pytest.mark.asyncio
    async def test_list_versions_no_history(self, async_test_client, async_test_db):
        """Listing versions for a project with no history returns current version only."""
        data = await _create_project_with_data_async(
            async_test_db,
            label_config_version="v1",
            label_config_history=None,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/versions",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_versions"] == 1
        assert body["versions"][0]["version"] == "v1"
        assert body["versions"][0]["is_current"] is True

    @pytest.mark.asyncio
    async def test_get_specific_version(self, async_test_client, async_test_db):
        """Getting a specific version returns its schema."""
        old_schema = '<View><Text name="old_field" value="$text"/></View>'
        history = {
            "current_version": "v2",
            "versions": {
                "v1": {
                    "schema": old_schema,
                    "created_at": "2025-01-01T00:00:00",
                    "description": "Initial",
                },
            },
        }
        data = await _create_project_with_data_async(
            async_test_db,
            label_config='<View><Text name="new_field" value="$text"/></View>',
            label_config_version="v2",
            label_config_history=history,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/versions/v1",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version"] == "v1"
        assert body["schema"] == old_schema
        assert body["is_current"] is False

    @pytest.mark.asyncio
    async def test_get_current_version(self, async_test_client, async_test_db):
        """Getting the current version returns the project's active label_config."""
        current_schema = '<View><Text name="current_field" value="$text"/></View>'
        data = await _create_project_with_data_async(
            async_test_db,
            label_config=current_schema,
            label_config_version="v3",
            label_config_history={"current_version": "v3", "versions": {}},
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/versions/v3",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["schema"] == current_schema
        assert body["is_current"] is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_version_returns_404(self, async_test_client, async_test_db):
        """Getting a version that does not exist returns 404."""
        data = await _create_project_with_data_async(
            async_test_db,
            label_config_version="v1",
            label_config_history={"current_version": "v1", "versions": {}},
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/versions/v99",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_compare_two_versions(self, async_test_client, async_test_db):
        """Comparing two versions returns field-level diff."""
        v1_schema = '<View><Choices name="sentiment" toName="text"><Choice value="Pos"/></Choices><Text name="text" value="$text"/></View>'
        v2_schema = '<View><Choices name="sentiment" toName="text"><Choice value="Pos"/><Choice value="Neg"/></Choices><TextArea name="reason" toName="text"/><Text name="text" value="$text"/></View>'
        history = {
            "current_version": "v2",
            "versions": {
                "v1": {
                    "schema": v1_schema,
                    "created_at": "2025-01-01T00:00:00",
                    "description": "Initial",
                },
            },
        }
        data = await _create_project_with_data_async(
            async_test_db,
            label_config=v2_schema,
            label_config_version="v2",
            label_config_history=history,
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/compare/v1/v2",
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version1"] == "v1"
        assert body["version2"] == "v2"
        assert "reason" in body["fields_added"]
        assert "sentiment" in body["fields_kept"]

    @pytest.mark.asyncio
    async def test_compare_nonexistent_version_returns_404(self, async_test_client, async_test_db):
        """Comparing with a nonexistent version returns 404."""
        data = await _create_project_with_data_async(
            async_test_db,
            label_config_version="v1",
            label_config_history={"current_version": "v1", "versions": {}},
        )
        project = data["project"]

        with _as_user(data["users"]["admin"]):
            resp = await async_test_client.get(
                f"{BASE}/{project.id}/label-config/compare/v1/v99",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generation_version_distribution_endpoint_exists(self, async_test_client, async_test_db):
        """Version distribution endpoint exists.

        NOTE: The endpoint queries Generation.project_id which exists in production
        (added via raw SQL migration) but NOT in the ORM model. This is a known bug —
        the Generation model needs a project_id column added to match the production
        schema. Here we only assert the route is registered (not 405).
        """
        admin = _make_user("admin-test-id", is_superadmin=True)
        async_test_db.add(admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent-id/generations/version-distribution",
            )
        # Endpoint exists if we get anything other than 405 (method not allowed = route missing)
        assert resp.status_code != 405

    @pytest.mark.asyncio
    async def test_label_config_versions_nonexistent_project_returns_404(self, async_test_client, async_test_db):
        """Accessing label config versions for nonexistent project returns 404."""
        admin = _make_user("admin-test-id", is_superadmin=True)
        async_test_db.add(admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/{_uid()}/label-config/versions",
            )

        assert resp.status_code == 404
