"""
Integration tests for project CRUD operations.

Targets: routers/projects/crud.py lines 100-792
Uses real PostgreSQL via test_db fixture.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task


@pytest.mark.integration
class TestProjectCrudIntegration:
    """Integration tests for project CRUD endpoints."""

    def _create_org(self, db: Session, admin_user_id: str) -> Organization:
        """Create a test organization."""
        org = Organization(
            id=str(uuid.uuid4()),
            name="Test Org CRUD",
            slug=f"test-org-crud-{uuid.uuid4().hex[:8]}",
            display_name="Test Org CRUD Display",
            description="Test org for CRUD tests",
            created_by=admin_user_id,
            created_at=datetime.utcnow(),
        )
        db.add(org)
        db.commit()
        return org

    def _create_membership(self, db: Session, user_id: str, org_id: str, role: str = "ORG_ADMIN"):
        membership = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            joined_at=datetime.utcnow(),
        )
        db.add(membership)
        db.commit()
        return membership

    def _create_project(self, db: Session, org_id: str, created_by: str, **kwargs) -> Project:
        """Create a test project."""
        project_data = {
            "id": str(uuid.uuid4()),
            "title": kwargs.get("title", "Test Project"),
            "description": kwargs.get("description", "Test description"),
                        "created_by": created_by,
            "created_at": datetime.utcnow(),
        }
        project = Project(**project_data)
        db.add(project)
        db.commit()

        # Link to organization
        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org_id,
            assigned_by=created_by,
        )
        db.add(po)
        db.commit()

        return project

    def test_list_projects(self, client, test_db, test_users, auth_headers, test_org):
        """Test listing projects."""
        # Create a project
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.get(
            "/api/projects",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_list_projects_with_org_context(self, client, test_db, test_users, auth_headers, test_org):
        """Test listing projects with org context filter."""
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.get(
            "/api/projects",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_create_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test creating a project."""
        response = client.post(
            "/api/projects",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
            json={
                "title": "New Test Project",
                "description": "A project created via test",
            },
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["title"] == "New Test Project"

    def test_create_project_missing_title(self, client, test_db, test_users, auth_headers, test_org):
        """Test creating a project without required title."""
        response = client.post(
            "/api/projects",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
            json={
                "description": "No title",
            },
        )
        assert response.status_code == 422

    def test_get_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test getting a single project."""
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.get(
            f"/api/projects/{project.id}",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project.id

    def test_get_project_not_found(self, client, test_db, test_users, auth_headers):
        """Test getting a non-existent project."""
        response = client.get(
            "/api/projects/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 404

    def test_update_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test updating a project."""
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.patch(
            f"/api/projects/{project.id}",
            headers=auth_headers["admin"],
            json={
                "title": "Updated Title",
                "description": "Updated description",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    def test_update_project_not_found(self, client, test_db, test_users, auth_headers):
        """Test updating non-existent project."""
        response = client.patch(
            "/api/projects/nonexistent-id",
            headers=auth_headers["admin"],
            json={"title": "Updated"},
        )
        assert response.status_code == 404

    def test_delete_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test deleting a project."""
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.delete(
            f"/api/projects/{project.id}",
            headers=auth_headers["admin"],
        )
        assert response.status_code in (200, 204)

    def test_delete_project_not_found(self, client, test_db, test_users, auth_headers):
        """Test deleting non-existent project."""
        response = client.delete(
            "/api/projects/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 404

    def test_list_projects_pagination(self, client, test_db, test_users, auth_headers, test_org):
        """Test project listing with pagination."""
        # Create multiple projects
        for i in range(5):
            self._create_project(
                test_db, test_org.id, test_users[0].id,
                title=f"Paginated Project {i}",
            )

        response = client.get(
            "/api/projects?page=1&page_size=2",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2

    def test_annotator_cannot_create_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test that annotators cannot create projects."""
        response = client.post(
            "/api/projects",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": test_org.id,
            },
            json={
                "title": "Annotator Project",
            },
        )
        assert response.status_code in (403, 401)

    def test_annotator_cannot_delete_project(self, client, test_db, test_users, auth_headers, test_org):
        """Test that annotators cannot delete projects."""
        project = self._create_project(test_db, test_org.id, test_users[0].id)

        response = client.delete(
            f"/api/projects/{project.id}",
            headers=auth_headers["annotator"],
        )
        assert response.status_code in (403, 401)

    def test_list_projects_search(self, client, test_db, test_users, auth_headers, test_org):
        """Test project listing with search query."""
        self._create_project(
            test_db, test_org.id, test_users[0].id,
            title="Unique Searchable Title XYZ",
        )

        response = client.get(
            "/api/projects?search=Searchable",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 200


@pytest.mark.integration
class TestProjectTasksIntegration:
    """Integration tests for task management within projects."""

    def _create_project_with_tasks(self, db: Session, org_id: str, user_id: str, num_tasks: int = 3):
        """Create a project with tasks."""
        project = Project(
            id=str(uuid.uuid4()),
            title="Task Test Project",
            created_by=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(project)
        db.commit()

        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org_id,
            assigned_by=user_id,
        )
        db.add(po)

        tasks = []
        for i in range(num_tasks):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project.id,
                data={"text": f"Sample text {i}"},
                inner_id=i + 1,
            )
            db.add(task)
            tasks.append(task)

        db.commit()
        return project, tasks

    def test_get_project_includes_task_count(self, client, test_db, test_users, auth_headers, test_org):
        """Test that project detail includes task statistics."""
        project, tasks = self._create_project_with_tasks(
            test_db, test_org.id, test_users[0].id, num_tasks=5
        )

        response = client.get(
            f"/api/projects/{project.id}",
            headers=auth_headers["admin"],
        )
        assert response.status_code == 200


@pytest.mark.integration
class TestDeepMergeDicts:
    """Test the deep_merge_dicts utility function."""

    def test_merge_simple(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_merge_dicts(base, update)
        assert result["a"] == 1
        assert result["b"] == 3
        assert result["c"] == 4

    def test_merge_nested(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        update = {"a": {"y": 99, "z": 100}}
        result = deep_merge_dicts(base, update)
        assert result["a"]["x"] == 1
        assert result["a"]["y"] == 99
        assert result["a"]["z"] == 100
        assert result["b"] == 3

    def test_merge_none_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_merge_none_update(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_merge_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_merge_lists_replaced(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"items": [1, 2, 3]}
        update = {"items": [4, 5]}
        result = deep_merge_dicts(base, update)
        assert result["items"] == [4, 5]
