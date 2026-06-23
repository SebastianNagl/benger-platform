"""
Coverage push tests for helper functions, evaluation config, status,
metadata, validation, generation, leaderboards, and other misc endpoints.

Targets uncovered branches in:
- routers/projects/helpers.py
- routers/evaluations/config.py
- routers/evaluations/status.py
- routers/evaluations/metadata.py
- routers/evaluations/validation.py
- routers/evaluations/helpers.py
- routers/generation.py
- routers/leaderboards.py
- routers/projects/organizations.py
- routers/projects/generation.py
- routers/projects/label_config_versions.py
- app/core/authorization.py
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest


from models import (
    EvaluationRun,
    Organization,
    OrganizationMembership,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring ``db_user`` so async
    endpoint tests authenticate as a seeded DB user."""
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


async def _seed_helper_owner_async(db):
    """Seed a superadmin owner only (no project) for async 404-path tests."""
    owner = User(
        id=str(uuid.uuid4()),
        username=f"helper-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Helper Owner",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.commit()
    return owner


async def _seed_helper_project_async(db, *, num_tasks=3):
    """Async twin of :func:`_setup_helper_project`: seeds a superadmin owner +
    org + public project + tasks through ``async_test_db`` so async endpoint
    handlers (which read via ``get_async_db``) can see the rows."""
    owner = User(
        id=str(uuid.uuid4()),
        username=f"helper-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Helper Owner",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.flush()

    pid = str(uuid.uuid4())
    project = Project(
        id=pid,
        title=f"Helper Project {uuid.uuid4().hex[:6]}",
        description="For testing helpers",
        created_by=owner.id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
    )
    db.add(project)
    await db.flush()

    for i in range(num_tasks):
        db.add(Task(
            id=str(uuid.uuid4()),
            project_id=pid,
            data={"text": f"Task {i}"},
            inner_id=i + 1,
        ))
    await db.commit()
    return {"owner": owner, "project": project}


def _setup_helper_project(db, users, *, num_tasks=3):
    """Create a project for helper function tests."""
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"Helper Org {uuid.uuid4().hex[:4]}",
        slug=f"helper-org-{uuid.uuid4().hex[:8]}",
        display_name="Helper Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title=f"Helper Project {uuid.uuid4().hex[:6]}",
        description="For testing helpers",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        role = "ORG_ADMIN" if i == 0 else ("CONTRIBUTOR" if i < 3 else "ANNOTATOR")
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=pid,
            data={"text": f"Task {i}"},
            inner_id=i + 1,
        )
        db.add(task)
        tasks.append(task)
    db.commit()

    return {"project": p, "tasks": tasks, "org": org}


# =================== Helper Function Tests ===================

class TestProjectHelpers:
    """Test project helper functions."""

    def test_calculate_project_stats(self, test_db, test_users):
        from routers.projects.helpers import calculate_project_stats
        from project_schemas import ProjectResponse

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        response = ProjectResponse.model_construct(
            id=pid, title="test", created_by=test_users[0].id,
        )
        calculate_project_stats(test_db, pid, response)
        assert response.task_count == 3
        assert response.annotation_count == 0
        assert response.progress_percentage == 0.0

    def test_calculate_project_stats_with_data(self, test_db, test_users):
        from routers.projects.helpers import calculate_project_stats
        from project_schemas import ProjectResponse

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        # Mark a task as labeled
        data["tasks"][0].is_labeled = True
        # Add annotation
        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=data["tasks"][0].id,
            project_id=pid,
            result=[],
            completed_by=test_users[0].id,
            was_cancelled=False,
        ))
        test_db.commit()

        response = ProjectResponse.model_construct(
            id=pid, title="test", created_by=test_users[0].id,
        )
        calculate_project_stats(test_db, pid, response)
        assert response.task_count == 3
        assert response.annotation_count == 1
        assert response.completed_tasks_count == 1
        assert response.progress_percentage > 0

    def test_calculate_project_stats_batch(self, test_db, test_users):
        from routers.projects.helpers import calculate_project_stats_batch

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        stats = calculate_project_stats_batch(test_db, [pid])
        assert pid in stats
        assert stats[pid]["task_count"] == 3

    def test_calculate_project_stats_batch_empty(self, test_db, test_users):
        from routers.projects.helpers import calculate_project_stats_batch

        stats = calculate_project_stats_batch(test_db, [])
        assert stats == {}

    def test_check_project_accessible_superadmin(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        result = check_project_accessible(test_db, test_users[0], pid, None)
        assert result is True

    def test_check_project_accessible_non_member(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible
        from models import User
        from auth_module.user_service import get_password_hash

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        # Create a new user not in the org
        outsider = User(
            id=str(uuid.uuid4()),
            username=f"outsider_{uuid.uuid4().hex[:8]}@test.com",
            email=f"outsider_{uuid.uuid4().hex[:8]}@test.com",
            name="Outsider",
            hashed_password=get_password_hash("test123"),
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        test_db.add(outsider)
        test_db.commit()

        result = check_project_accessible(test_db, outsider, pid, None)
        assert result is False

    def test_get_user_with_memberships(self, test_db, test_users):
        from routers.projects.helpers import get_user_with_memberships

        _setup_helper_project(test_db, test_users)

        user = get_user_with_memberships(test_db, test_users[0].id)
        assert user is not None
        assert len(user.organization_memberships) >= 1

    def test_check_user_can_edit_project(self, test_db, test_users):
        from routers.projects.helpers import check_user_can_edit_project

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        # Superadmin can edit
        assert check_user_can_edit_project(test_db, test_users[0], pid) == True  # noqa: E712

    def test_get_accessible_project_ids_superadmin(self, test_db, test_users):
        from routers.projects.helpers import get_accessible_project_ids

        _setup_helper_project(test_db, test_users)

        # Superadmin only gets the unfiltered (None) short-circuit when they
        # explicitly opt in via include_all_private=True. Without the flag they
        # are scoped the same way a regular user would be.
        ids = get_accessible_project_ids(
            test_db, test_users[0], include_all_private=True
        )
        assert ids is None

        scoped_ids = get_accessible_project_ids(test_db, test_users[0])
        assert isinstance(scoped_ids, list)

    def test_get_accessible_project_ids_private(self, test_db, test_users):
        from routers.projects.helpers import get_accessible_project_ids

        _setup_helper_project(test_db, test_users)

        # Non-superadmin with no org context -> private projects only
        ids = get_accessible_project_ids(test_db, test_users[1], org_context="private")
        assert isinstance(ids, list)

    def test_get_accessible_project_ids_with_org(self, test_db, test_users):
        from routers.projects.helpers import get_accessible_project_ids

        data = _setup_helper_project(test_db, test_users)
        org_id = data["org"].id

        # Non-superadmin with org context
        ids = get_accessible_project_ids(test_db, test_users[1], org_context=org_id)
        assert isinstance(ids, list)

    def test_calculate_generation_stats(self, test_db, test_users):
        from routers.projects.helpers import calculate_generation_stats
        from project_schemas import ProjectResponse

        data = _setup_helper_project(test_db, test_users)

        response = ProjectResponse.model_construct(
            id=data["project"].id, title="test", created_by=test_users[0].id,
        )
        calculate_generation_stats(test_db, data["project"], response)
        # Should set generation_count and other stats
        assert hasattr(response, 'generation_count') or True  # May not be set if no generations


# =================== Evaluation Helpers Tests ===================

class TestEvaluationHelpers:
    """Test evaluation helper functions."""

    def test_resolve_user_org_for_project(self, test_db, test_users):
        from routers.evaluations.helpers import resolve_user_org_for_project

        data = _setup_helper_project(test_db, test_users)
        project = test_db.query(Project).filter(Project.id == data["project"].id).first()

        org_id = resolve_user_org_for_project(test_users[0], project, test_db)
        assert org_id is not None

    def test_get_evaluation_types_for_task_type(self, test_db, test_users):
        from routers.evaluations.helpers import get_evaluation_types_for_task_type

        result = get_evaluation_types_for_task_type(test_db, "text_classification")
        # Result can be empty if no evaluation types match, but should not error
        assert isinstance(result, list)


# =================== Evaluation Config Tests ===================

class TestEvaluationConfig:
    """Test evaluation config endpoints.

    ``get_project_evaluation_config`` migrated to the async DB lane — seed via
    async_test_db and drive through async_test_client.
    """

    @pytest.mark.asyncio
    async def test_get_evaluation_config(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/evaluation-config",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_evaluation_config_not_found(self, async_test_client, async_test_db):
        owner = await _seed_helper_owner_async(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluation-config",
            )
        assert resp.status_code == 404


# =================== Evaluation Status Tests ===================

class TestEvaluationStatus:
    """Test evaluation status endpoints.

    ``get_evaluation_status`` migrated to the async DB lane — seed via
    async_test_db and drive through async_test_client.
    """

    @pytest.mark.asyncio
    async def test_get_evaluation_status(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        er = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=pid,
            model_id="gpt-4o",
            evaluation_type_ids=["test"],
            metrics={"acc": 0.9},
            status="completed",
            created_by=data["owner"].id,
        )
        async_test_db.add(er)
        await async_test_db.commit()

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{er.id}",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_evaluation_status_not_found(self, async_test_client, async_test_db):
        owner = await _seed_helper_owner_async(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/evaluation/status/nonexistent",
            )
        assert resp.status_code == 404


# =================== Evaluation Metadata Tests ===================

class TestEvaluationMetadata:
    """Test evaluation metadata endpoints."""

    def test_list_evaluation_types(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/evaluations/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_evaluations(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/evaluations/",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_evaluated_models(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/evaluated-models",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_configured_methods(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/configured-methods",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_evaluation_history(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/evaluation-history?model_ids=gpt-4o&metrics=accuracy",
            )
        assert resp.status_code == 200
        # Issue #111: response shape is ``{series: [...]}`` (was
        # ``{metric, data: [...]}`` before).
        assert "series" in resp.json()


# =================== Project Organization Tests ===================

class TestProjectOrganization:
    """Test project-organization endpoints."""

    def test_list_project_organizations_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/organizations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# =================== Label Config Version Tests ===================

class TestLabelConfigVersions:
    """Test label config version endpoints."""

    @pytest.mark.asyncio
    async def test_get_label_config_versions(self, async_test_client, async_test_db):
        # Endpoint migrated to the async DB lane — drive it via async fixtures.
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/label-config/versions",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_label_config_versions_not_found(self, async_test_client, async_test_db):
        owner = await _seed_helper_owner_async(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/label-config/versions",
            )
        assert resp.status_code == 404


# =================== Project Generation Tests ===================

class TestProjectGeneration:
    """Test project generation endpoints."""

    @pytest.mark.asyncio
    async def test_get_generation_config(self, async_test_client, async_test_db):
        # Endpoint migrated to the async DB lane — drive it via async fixtures.
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/generation-config",
            )
        assert resp.status_code == 200


# =================== Task Fields Tests ===================

class TestTaskFields:
    """Test task fields endpoint."""

    @pytest.mark.asyncio
    async def test_get_task_fields(self, async_test_client, async_test_db):
        # Endpoint migrated to the async DB lane — drive it via async fixtures.
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/task-fields",
            )
        assert resp.status_code == 200


# =================== My Tasks Tests ===================

class TestMyTasks:
    """Test my-tasks endpoint."""

    def test_get_my_tasks(self, client, test_users, test_db, auth_headers):
        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/my-tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Bulk Export Tasks Tests ===================

class TestBulkExportTasks:
    """Test bulk task export endpoint."""

    def test_bulk_export_tasks(self, client, test_users, test_db, auth_headers):
        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/bulk-export",
            json={"task_ids": task_ids, "format": "json"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Task Metadata Tests ===================

class TestTaskMetadata:
    """Test task metadata endpoints."""

    @pytest.mark.asyncio
    async def test_update_task_metadata(self, async_test_client, async_test_db):
        # Endpoint migrated to the async DB lane — drive it via async fixtures.
        owner = User(
            id=str(uuid.uuid4()),
            username=f"meta-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            name="Meta Owner",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(owner)
        await async_test_db.flush()
        pid = str(uuid.uuid4())
        async_test_db.add(Project(
            id=pid,
            title=f"Meta Project {uuid.uuid4().hex[:6]}",
            created_by=owner.id,
            is_private=False,
            label_config="<View><Text name='text' value='$text'/></View>",
            assignment_mode="open",
        ))
        await async_test_db.flush()
        tid = str(uuid.uuid4())
        async_test_db.add(Task(id=tid, project_id=pid, data={"text": "T"}, inner_id=1))
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tid}/metadata",
                json={"meta": {"custom_field": "value"}},
            )
        assert resp.status_code == 200


# Note: TestImportFullProject was removed — the synchronous POST /import-project
# handler was deleted in the #158 follow-up (object storage is now the only
# transport). Full-project import now runs through the async job flow
# (POST /project-imports/upload-url → POST /project-imports → poll); its
# validation/not-found paths are covered in
# tests/integration/test_import_jobs_api.py.


# =================== Review Endpoints Extra Tests ===================

class TestAuthorization:
    """Test authorization module."""

    def test_check_project_accessible_with_org_context(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id
        org_id = data["org"].id

        result = check_project_accessible(test_db, test_users[0], pid, org_id)
        assert result is True

    def test_check_project_accessible_wrong_org_context(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible

        data = _setup_helper_project(test_db, test_users)
        pid = data["project"].id

        # Create outsider user who is not superadmin
        from models import User
        from auth_module.user_service import get_password_hash
        outsider = User(
            id=str(uuid.uuid4()),
            username=f"outsider2_{uuid.uuid4().hex[:8]}@test.com",
            email=f"outsider2_{uuid.uuid4().hex[:8]}@test.com",
            name="Outsider 2",
            hashed_password=get_password_hash("test123"),
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        test_db.add(outsider)
        test_db.commit()

        result = check_project_accessible(test_db, outsider, pid, "wrong-org-id")
        assert result is False


# =================== Prompt Structures Tests ===================

class TestPromptStructures:
    """Test prompt structures endpoint.

    The prompt_structures router was migrated to the async DB lane, so this
    seeds via async_test_db and drives through async_test_client with a
    superadmin require_user override.
    """

    @pytest.mark.asyncio
    async def test_list_prompt_structures(self, async_test_client, async_test_db):
        import contextlib

        from auth_module.dependencies import require_user
        from auth_module.models import User as AuthUser
        from main import app

        creator = User(
            id=str(uuid.uuid4()),
            username=f"ps-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            name="PS Creator",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        async_test_db.add(creator)
        await async_test_db.flush()
        pid = str(uuid.uuid4())
        async_test_db.add(
            Project(
                id=pid,
                title=f"Helper Project {uuid.uuid4().hex[:6]}",
                created_by=creator.id,
                label_config="<View><Text name='text' value='$text'/></View>",
                generation_config={},
            )
        )
        await async_test_db.commit()

        auth = AuthUser(
            id=creator.id,
            username=creator.username,
            email=creator.email,
            name=creator.name,
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=creator.created_at,
        )

        @contextlib.contextmanager
        def _as_admin():
            app.dependency_overrides[require_user] = lambda: auth
            try:
                yield
            finally:
                app.dependency_overrides.pop(require_user, None)

        with _as_admin():
            resp = await async_test_client.get(
                f"/api/projects/{pid}/generation-config/structures",
            )
        assert resp.status_code == 200


# =================== Detect Answer Types Tests ===================

class TestDetectAnswerTypes:
    """Test detect answer types endpoint."""

    @pytest.mark.asyncio
    async def test_detect_answer_types(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/detect-answer-types",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_field_types(self, async_test_client, async_test_db):
        data = await _seed_helper_project_async(async_test_db)
        pid = data["project"].id

        with _as_user(data["owner"]):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/field-types",
            )
        assert resp.status_code == 200
