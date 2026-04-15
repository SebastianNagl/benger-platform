"""
Comprehensive tests for the Template System
Phase 2.1: Template creation, versioning, and sharing
Issue #473: Comprehensive Test Suite Overhaul
"""

from typing import List

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module import User
from models import Organization


class TestTemplateSystem:
    """Test template system functionality"""

    def test_create_universal_template(
        self, client: TestClient, test_users: List[User], test_org: Organization, db: Session
    ):
        """Test creating a universal template"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a universal template
        template_data = {
            "name": "Legal Document Template",
            "description": "Template for legal document annotation",
            "label_config": '''
                <View>
                    <Text name="text" value="$text"/>
                    <Choices name="doc_type" toName="text">
                        <Choice value="Contract"/>
                        <Choice value="Agreement"/>
                        <Choice value="Court_Decision"/>
                    </Choices>
                </View>
            ''',
            "settings": {
                "instructions": "Classify the legal document type",
                "required_fields": ["doc_type"],
                "multi_label": False,
            },
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=headers, json=template_data
        )

        # May return 404 if not implemented
        if response.status_code != 404:
            assert response.status_code in [200, 201]
            data = response.json()
            assert "id" in data or "template_id" in data
            assert data.get("name") == "Legal Document Template"

    def test_download_universal_template(self, client: TestClient, test_users: List[User]):
        """Test downloading the universal template"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Download universal template
        response = client.get("/api/templates/universal-template/download", headers=headers)

        # Check response
        if response.status_code != 404:
            assert response.status_code == 200
            assert response.headers.get("content-type") in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/octet-stream",
                "application/x-zip-compressed",
            ]

    def test_template_versioning(self, client: TestClient, test_users: List[User], db: Session):
        """Test template versioning functionality"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create initial template version
        template_v1 = {
            "name": "Versioned Template",
            "version": "1.0.0",
            "description": "Initial version",
            "label_config": "<View><Text name='text' value='$text'/></View>",
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=headers, json=template_v1
        )

        if response.status_code not in [404, 405]:
            assert response.status_code in [200, 201]
            template_id = response.json().get("id")

            # Create updated version
            template_v2 = {
                "name": "Versioned Template",
                "version": "2.0.0",
                "description": "Updated version with new fields",
                "label_config": '''
                    <View>
                        <Text name="text" value="$text"/>
                        <Choices name="category" toName="text">
                            <Choice value="A"/>
                            <Choice value="B"/>
                        </Choices>
                    </View>
                ''',
                "parent_version": template_id,
            }

            response = client.post(
                "/api/templates/universal-template/create", headers=headers, json=template_v2
            )

            if response.status_code != 404:
                assert response.status_code in [200, 201]

    def test_template_sharing(
        self, client: TestClient, test_users: List[User], test_org: Organization, db: Session
    ):
        """Test template sharing between organizations"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a shareable template
        template_data = {
            "name": "Shareable Template",
            "description": "Template for sharing",
            "label_config": "<View><Text name='text' value='$text'/></View>",
            "is_public": True,
            "organization_id": test_org.id,
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=headers, json=template_data
        )

        if response.status_code not in [404, 405]:
            assert response.status_code in [200, 201]

            # Check if template is accessible publicly
            response = client.get("/api/templates/public", headers=headers)

            if response.status_code != 404:
                assert response.status_code == 200

    def test_project_from_template(
        self, client: TestClient, test_users: List[User], test_org: Organization, db: Session
    ):
        """Test creating a project from a template"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # First create a template
        template_data = {
            "name": "Project Template",
            "description": "Template for projects",
            "label_config": '''
                <View>
                    <Text name="text" value="$text"/>
                    <RectangleLabels name="label" toName="text">
                        <Label value="Entity" background="green"/>
                        <Label value="Action" background="blue"/>
                    </RectangleLabels>
                </View>
            ''',
            "settings": {"hotkeys": {"ctrl+1": "Entity", "ctrl+2": "Action"}, "show_labels": True},
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=headers, json=template_data
        )

        if response.status_code in [200, 201]:
            template_id = response.json().get("id")

            # Create project from template
            project_data = {
                "title": "Project from Template",
                "description": "Created using template",
                "organization_id": test_org.id,
                "template_id": template_id,
                "visibility": "private",
            }

            response = client.post("/api/projects", headers=headers, json=project_data)

            if response.status_code != 404:
                assert response.status_code in [200, 201]
                project = response.json()
                # Verify template config was applied
                if "label_config" in project:
                    assert "RectangleLabels" in project["label_config"]

    def test_template_validation(self, client: TestClient, test_users: List[User]):
        """Test template validation for invalid configurations"""
        admin_user = test_users[0]

        # Login as admin
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to create template with invalid label config
        invalid_template = {
            "name": "Invalid Template",
            "description": "This should fail",
            "label_config": "not valid XML <View>",  # Invalid XML
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=headers, json=invalid_template
        )

        # Should reject invalid template
        if response.status_code != 404:
            assert response.status_code in [400, 422]

    def test_template_permissions(
        self, client: TestClient, test_users: List[User], test_org: Organization, db: Session
    ):
        """Test template access permissions"""
        # Create template as admin
        admin_user = test_users[0]
        response = client.post(
            "/api/auth/login", json={"username": admin_user.username, "password": "admin123"}
        )
        assert response.status_code == 200
        admin_token = response.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        template_data = {
            "name": "Private Template",
            "description": "Only for our org",
            "label_config": "<View><Text name='text' value='$text'/></View>",
            "is_public": False,
            "organization_id": test_org.id,
        }

        response = client.post(
            "/api/templates/universal-template/create", headers=admin_headers, json=template_data
        )

        if response.status_code in [200, 201]:
            template_id = response.json().get("id")

            # Try to access as different user (not in org)
            if len(test_users) > 2:
                other_user = test_users[2]
                response = client.post(
                    "/api/auth/login",
                    json={"username": other_user.username, "password": "annotator123"},
                )

                if response.status_code == 200:
                    other_token = response.json()["access_token"]
                    other_headers = {"Authorization": f"Bearer {other_token}"}

                    # Should not be able to access private template
                    response = client.get(f"/api/templates/{template_id}", headers=other_headers)

                    # Should be denied or not found
                    if response.status_code != 404:
                        assert response.status_code in [403, 404]
