"""
Integration tests for label config version API endpoints.
Tests GET endpoints for listing, retrieving, comparing versions, and generation distribution.

The label-config version endpoints (``routers/projects/label_config_versions.py``)
were migrated to the async DB lane, so the suite seeds through ``async_test_db``
and drives the endpoints via ``async_test_client`` + the ``_as_user`` auth
override.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from services.label_config.version_service import LabelConfigVersionService
from models import User
from project_models import Project


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
        is_active=db_user.is_active,
        email_verified=db_user.email_verified,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db) -> User:
    user = User(
        id=f"version-user-{_uid()}",
        username=f"versionuser-{uuid.uuid4().hex[:8]}",
        email=f"version-{uuid.uuid4().hex[:8]}@test.com",
        name="Version User",
        hashed_password="hashed_password",
        is_superadmin=True,  # For auth bypass in tests
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project_with_versions(db, user) -> Project:
    """Create a project with three schema versions (v1, v2, v3)."""
    project = Project(
        id=f"version-project-{_uid()}",
        title="Version Test Project",
        created_by=user.id,
        label_config="<View><Choices name='sentiment'/></View>",
        label_config_version="v1",
        label_config_history={"versions": {}},
    )
    db.add(project)
    await db.flush()

    # update_version_history is a pure in-memory mutation on the Project object.
    schema_v2 = "<View><Choices name='sentiment'/><Rating name='confidence'/></View>"
    LabelConfigVersionService.update_version_history(
        project=project,
        new_label_config=schema_v2,
        description="Added confidence rating field",
        user_id=user.id,
    )
    await db.flush()

    schema_v3 = (
        "<View><Choices name='sentiment'/><Rating name='confidence'/>"
        "<TextArea name='notes'/></View>"
    )
    LabelConfigVersionService.update_version_history(
        project=project,
        new_label_config=schema_v3,
        description="Added notes field",
        user_id=user.id,
    )
    await db.commit()
    return project


class TestLabelConfigVersionEndpoints:
    """Test label config version API endpoints"""

    # ==================================================================
    # GET /projects/{id}/label-config/versions - List Versions
    # ==================================================================

    @pytest.mark.asyncio
    async def test_list_versions_with_history(self, async_test_client, async_test_db):
        """Test listing all versions of a project with history"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions"
            )

        assert response.status_code == 200
        data = response.json()

        assert "versions" in data
        versions_list = data["versions"]
        assert len(versions_list) >= 3

        versions = [v["version"] for v in versions_list]
        assert "v1" in versions
        assert "v2" in versions
        assert "v3" in versions

        v3_entry = next(v for v in versions_list if v["version"] == "v3")
        assert v3_entry["is_current"] == True  # noqa: E712

        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        v2_entry = next(v for v in versions_list if v["version"] == "v2")
        assert v1_entry["is_current"] == False  # noqa: E712
        assert v2_entry["is_current"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_list_versions_no_history(self, async_test_client, async_test_db):
        """Test listing versions for project without history"""
        user = await _make_user(async_test_db)
        project = Project(
            id=f"no-history-{_uid()}",
            title="No History Project",
            created_by=user.id,
            label_config="<View><Choices name='test'/></View>",
            label_config_version="v1",
            label_config_history=None,
        )
        async_test_db.add(project)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions"
            )

        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) >= 1

    @pytest.mark.asyncio
    async def test_list_versions_project_not_found(self, async_test_client, async_test_db):
        """Test listing versions for non-existent project returns 404"""
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/non-existent-project/label-config/versions"
            )
        assert response.status_code == 404

    # ==================================================================
    # GET /projects/{id}/label-config/versions/{version} - Get Version
    # ==================================================================

    @pytest.mark.asyncio
    async def test_get_version_current(self, async_test_client, async_test_db):
        """Test retrieving current version schema"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions/v3"
            )

        assert response.status_code == 200
        data = response.json()
        assert "schema" in data
        assert "<TextArea name='notes'/>" in data["schema"]
        assert data["version"] == "v3"
        assert data["is_current"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_version_historical(self, async_test_client, async_test_db):
        """Test retrieving historical version schema"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions/v1"
            )

        assert response.status_code == 200
        data = response.json()
        assert "schema" in data
        assert "<Choices name='sentiment'/>" in data["schema"]
        assert "<Rating" not in data["schema"]  # v1 didn't have rating
        assert data["version"] == "v1"
        assert data["is_current"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_version_not_found(self, async_test_client, async_test_db):
        """Test retrieving non-existent version returns 404"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions/v99"
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_version_project_not_found(self, async_test_client, async_test_db):
        """Test retrieving version for non-existent project returns 404"""
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/non-existent-project/label-config/versions/v1"
            )
        assert response.status_code == 404

    # ==================================================================
    # GET /projects/{id}/label-config/compare/{v1}/{v2} - Compare
    # ==================================================================

    @pytest.mark.asyncio
    async def test_compare_versions_fields_added(self, async_test_client, async_test_db):
        """Test comparing versions shows fields added"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/compare/v1/v2"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["version1"] == "v1"
        assert data["version2"] == "v2"
        assert "confidence" in data["fields_added"]
        assert len(data["fields_removed"]) == 0
        assert data["has_breaking_changes"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_compare_versions_fields_removed(self, async_test_client, async_test_db):
        """Test comparing versions detects removed fields (breaking change)"""
        user = await _make_user(async_test_db)
        project = Project(
            id=f"removal-{_uid()}",
            title="Removal Test",
            created_by=user.id,
            label_config="<View><Choices name='a'/><Rating name='b'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        async_test_db.add(project)
        await async_test_db.flush()

        schema_v2 = "<View><Choices name='a'/></View>"  # Removed rating 'b'
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_v2,
            description="Removed field b",
            user_id=user.id,
        )
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/compare/v1/v2"
            )

        assert response.status_code == 200
        data = response.json()
        assert "b" in data["fields_removed"]
        assert data["has_breaking_changes"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_compare_versions_breaking_changes_flag(
        self, async_test_client, async_test_db
    ):
        """Test that has_breaking_changes flag is set correctly"""
        user = await _make_user(async_test_db)
        project = Project(
            id=f"breaking-{_uid()}",
            title="Breaking Changes Test",
            created_by=user.id,
            label_config="<View><Choices name='x'/><Choices name='y'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        async_test_db.add(project)
        await async_test_db.flush()

        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config="<View><Choices name='x'/></View>",
            description="Removed y",
            user_id=user.id,
        )
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/compare/v1/v2"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_compare_versions_invalid_versions(self, async_test_client, async_test_db):
        """Test comparing with invalid version returns error"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/compare/v1/v99"
            )
        assert response.status_code in [404, 400, 422]

    # ==================================================================
    # Additional Tests
    # ==================================================================

    @pytest.mark.asyncio
    async def test_version_metadata_includes_user_info(self, async_test_client, async_test_db):
        """Test that version metadata includes user information"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions"
            )

        assert response.status_code == 200
        data = response.json()
        versions_list = data["versions"]

        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        if "created_by" in v1_entry:  # May not be present for all versions
            assert v1_entry["created_by"] is not None
        if "created_at" in v1_entry:
            assert v1_entry["created_at"] is not None

    @pytest.mark.asyncio
    async def test_version_schema_hash_consistency(self, async_test_client, async_test_db):
        """Test that schema hashes are consistent"""
        user = await _make_user(async_test_db)
        project = await _make_project_with_versions(async_test_db, user)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/versions"
            )

        assert response.status_code == 200
        data = response.json()
        versions_list = data["versions"]

        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        if "schema_hash" in v1_entry:
            v1_hash = v1_entry["schema_hash"]
            assert len(v1_hash) == 12  # Truncated SHA256

            with _as_user(user):
                schema_response = await async_test_client.get(
                    f"/api/projects/{project.id}/label-config/versions/v1"
                )
            v1_schema = schema_response.json()["schema"]

            computed_hash = LabelConfigVersionService.compute_schema_hash(v1_schema)
            assert computed_hash == v1_hash
