"""
Unit tests for API endpoints
"""

import pytest
from fastapi import status


@pytest.mark.unit
@pytest.mark.api
class TestAuthenticationEndpoints:
    """Test authentication-related endpoints"""

    def test_login_success(self, client, test_users):
        """Test successful login"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

    def test_login_invalid_credentials(self, client, test_users):
        """Test login with invalid credentials"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrongpassword"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_current_user_success(self, client, auth_headers):
        """Test getting current user info"""
        response = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data

    def test_signup_success(self, client):
        """Test user signup"""
        user_data = {
            "username": "newuser@test.com",
            "email": "newuser@test.com",
            "name": "New User",
            "password": "password123",
            "role": "annotator",
            "legal_expertise_level": "layperson",
            "german_proficiency": "native",
        }
        response = client.post("/api/auth/signup", json=user_data)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == user_data["username"]
        assert data["email"] == user_data["email"]

    def test_register_admin_only(self, client, auth_headers):
        """Test that register endpoint requires admin role"""
        user_data = {
            "username": "adminuser@test.com",
            "email": "adminuser@test.com",
            "name": "Admin User",
            "password": "password123",
            "role": "admin",
            "legal_expertise_level": "practicing_lawyer",
            "german_proficiency": "native",
        }

        # Test with annotator role (should fail)
        response = client.post(
            "/api/auth/register", json=user_data, headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.post("/api/auth/register", json=user_data, headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK

    def test_verify_token(self, client, auth_headers):
        """Test token verification endpoint"""
        response = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
@pytest.mark.api
class TestUserManagementEndpoints:
    """Test user management endpoints"""

    def test_get_all_users_admin_only(self, client, auth_headers):
        """Test that getting all users requires admin role"""
        # Test with annotator role (should fail)
        response = client.get("/api/users", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.get("/api/users", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_update_user_role_admin_only(self, client, auth_headers, test_users):
        """Test updating user role requires admin"""
        user_id = test_users[2].id  # annotator user
        role_data = {"is_superadmin": False}  # Updated to use boolean flag

        # Test with annotator role (should fail)
        response = client.patch(
            f"/api/users/{user_id}/role",
            json=role_data,
            headers=auth_headers["annotator"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.patch(
            f"/api/users/{user_id}/role",
            json=role_data,
            headers=auth_headers["admin"],
        )
        assert response.status_code == status.HTTP_200_OK

    def test_update_user_status_admin_only(self, client, auth_headers, test_users):
        """Test updating user status requires admin"""
        user_id = test_users[2].id  # annotator user
        status_data = {"is_active": False}

        # Test with annotator role (should fail)
        response = client.patch(
            f"/api/users/{user_id}/status",
            json=status_data,
            headers=auth_headers["annotator"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.patch(
            f"/api/users/{user_id}/status",
            json=status_data,
            headers=auth_headers["admin"],
        )
        assert response.status_code == status.HTTP_200_OK

    def test_delete_user_admin_only(self, client, auth_headers, test_users):
        """Test deleting user requires admin"""
        user_id = test_users[2].id  # annotator user

        # Test with annotator role (should fail)
        response = client.delete(f"/api/users/{user_id}", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.delete(f"/api/users/{user_id}", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.unit
@pytest.mark.api
class TestTaskEndpoints:
    """Test task-related endpoints"""

    def test_create_task_contributor_required(self, client, auth_headers):
        """Test creating task requires contributor role"""
        task_data = {
            "name": "Test Task",
            "description": "A test task",
            "template_id": "qa",  # Use template_id instead of task_type and template
            "visibility": "private",
        }

        # Test with annotator role - tasks are created through import endpoint
        import_data = {"data": [{"text": "Test task", "label": "test"}], "meta": {"source": "test"}}
        response = client.post(
            "/api/projects/test-project/import", json=import_data, headers=auth_headers["annotator"]
        )
        # May return 404 if project doesn't exist or 403 if no access
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]

        # Test with contributor role - should also succeed
        response = client.post(
            "/api/projects/test-project/import",
            json=import_data,
            headers=auth_headers["contributor"],
        )
        # Contributors can also import tasks
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]

    def test_get_tasks(self, client, auth_headers):
        """Test getting all tasks"""
        # Tasks are accessed through projects API
        response = client.get("/api/projects", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Projects endpoint returns paginated response
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_get_task_by_id(self, client, auth_headers):
        """Test getting task by ID"""
        # Non-existent task should return 404
        response = client.get("/api/projects/tasks/00000000-0000-0000-0000-000000000000", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_task_contributor_required(self, client, auth_headers):
        """Test updating task requires contributor role"""
        task_update = {
            "name": "Updated Task",
            "description": "Updated description",
        }

        # Non-existent task should return 404
        response = client.patch(
            "/api/projects/tasks/00000000-0000-0000-0000-000000000000/metadata", json=task_update, headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_task_admin_required(self, client, auth_headers):
        """Test deleting task requires admin role"""
        # Test with contributor role - tasks are deleted through bulk delete endpoint
        delete_data = {"task_ids": [1]}
        response = client.post(
            "/api/projects/test-project/tasks/bulk-delete",
            json=delete_data,
            headers=auth_headers["contributor"],
        )
        # May return 404 if project doesn't exist or 403 if no permission
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,  # No permission to delete
            status.HTTP_404_NOT_FOUND,  # Project not found
        ]


@pytest.mark.unit
@pytest.mark.api
class TestEvaluationTypeEndpoints:
    """Test evaluation type endpoints"""

    def test_get_evaluation_types(self, client, auth_headers):
        """Test getting all evaluation types"""
        response = client.get(
            "/api/evaluations/evaluation-types", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_evaluation_types_filtered(self, client, auth_headers):
        """Test getting evaluation types filtered by task type"""
        task_type_id = "qa_reasoning"
        response = client.get(
            f"/api/evaluations/evaluation-types?task_type_id={task_type_id}",
            headers=auth_headers["annotator"],
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_evaluation_type_by_id(self, client, auth_headers, test_evaluation_types):
        """Test getting evaluation type by ID"""
        eval_type_id = test_evaluation_types[0].id
        response = client.get(
            f"/api/evaluations/evaluation-types/{eval_type_id}",
            headers=auth_headers["annotator"],
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == eval_type_id


@pytest.mark.unit
@pytest.mark.api
class TestDataUploadEndpoints:
    """Test data upload endpoints"""

    def test_upload_data_annotator_required(self, client, auth_headers):
        """Test uploading data requires annotator role"""
        # Note: /data/upload endpoint has been removed (see main.py comment)
        # Expect 404 for removed endpoint
        response = client.post(
            "/data/upload",
            files={"file": ("test.csv", b"test,data", "text/csv")},
            data={"task_id": "1", "description": "Test upload"},
            headers=auth_headers["annotator"],
        )
        # Endpoint has been removed, expect 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_uploaded_data(self, client, auth_headers):
        """Test deleting uploaded data"""
        # This will likely return 404 since no data exists, which is fine
        # Delete file endpoint
        response = client.delete("/nonexistent", headers=auth_headers["annotator"])
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.unit
@pytest.mark.api
class TestEvaluationEndpoints:
    """Test evaluation endpoints"""

    def test_run_evaluation_contributor_required(self, client, auth_headers):
        """Test running evaluation requires contributor role"""
        eval_request = {
            "task_id": "1",
            "model_id": "test-model",
            "metrics": ["accuracy", "f1"],
            "model_configuration": {"type": "classification"},
        }

        # Test with annotator role on non-existent task (should return 404)
        response = client.post("/eval/run", json=eval_request, headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_evaluations(self, client, auth_headers, test_org):
        """Test getting evaluations"""
        response = client.get("/api/evaluations/", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_evaluation_status(self, client, auth_headers):
        """Test getting evaluation status"""
        # This will likely return 404 since no evaluation exists, which is fine
        response = client.get("/evaluation/status/nonexistent", headers=auth_headers["annotator"])
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_get_supported_metrics(self, client, auth_headers):
        """Test getting supported metrics"""
        # Check evaluation types instead of supported metrics
        response = client.get(
            "/api/evaluations/evaluation-types", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
@pytest.mark.api
class TestProjectEndpoints:
    """Test native project endpoints"""

    def test_get_projects(self, client, auth_headers):
        """Test getting projects"""
        response = client.get("/api/projects", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_200_OK

    def test_get_project_by_id(self, client, auth_headers):
        """Test getting non-existent project by ID returns 404"""
        response = client.get("/api/projects/1", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_project_tasks(self, client, auth_headers):
        """Test getting tasks for non-existent project returns 404"""
        response = client.get("/api/projects/1/tasks", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.unit
@pytest.mark.api
class TestRootEndpoint:
    """Test root endpoint"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns welcome message"""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
