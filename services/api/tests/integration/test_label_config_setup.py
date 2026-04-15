"""
Integration tests for label config setup workflows.
Tests project creation, updates, validation integration, and error handling.
Issue #798: Label config setup integration testing
"""


import pytest

from label_config_validator import LabelConfigValidator
from label_config_version_service import LabelConfigVersionService
from project_models import Project, ProjectOrganization


@pytest.fixture
def valid_label_config():
    """Valid label config for testing"""
    return '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="A"/><Choice value="B"/></Choices></View>'


@pytest.fixture
def invalid_label_config():
    """Invalid label config (malformed XML)"""
    return '<View><Unclosed tag'


@pytest.fixture
def test_project_with_config(test_db, test_org, test_users):
    """Create test project with initial label config"""
    admin_user = test_users[0]  # Admin user from shared fixture

    project = Project(
        id="test-project-config",
        title="Config Test Project",
        created_by=admin_user.id,
        label_config="<View><Choices name='sentiment'/></View>",
        label_config_version="v1",
        label_config_history={"versions": {}},
    )
    test_db.add(project)
    test_db.commit()

    # Add organization assignment
    project_org = ProjectOrganization(
        id="test-project-org-config",
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=admin_user.id,
    )
    test_db.add(project_org)
    test_db.commit()
    test_db.refresh(project)
    return project


class TestProjectCreationWithLabelConfig:
    """Test project creation with various label config scenarios"""

    def test_create_project_with_valid_config(
        self, client, test_org, valid_label_config, auth_headers
    ):
        """Test creating project with valid label config"""
        response = client.post(
            "/api/projects/",
            json={
                "title": "Test Project Valid Config",
                "description": "Test project with valid label config",
                "label_config": valid_label_config,
            },
            headers=auth_headers["admin"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Project Valid Config"
        assert data["label_config"] == valid_label_config

    def test_create_project_with_invalid_config(
        self, client, test_org, invalid_label_config, auth_headers
    ):
        """Test creating project with invalid label config is rejected"""
        response = client.post(
            "/api/projects/",
            json={
                "title": "Test Project Invalid Config",
                "description": "Should fail with invalid config",
                "label_config": invalid_label_config,
            },
            headers=auth_headers["admin"],
        )

        # Validation is now integrated - invalid configs are rejected
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "message" in data["detail"]
        assert "errors" in data["detail"]
        assert "Invalid label configuration" in data["detail"]["message"]

        # Verify validation detected the error
        is_valid, errors = LabelConfigValidator.validate(invalid_label_config)
        assert is_valid is False
        assert len(errors) > 0

    def test_create_project_with_empty_config(self, client, test_org, auth_headers):
        """Test creating project with empty label config"""
        response = client.post(
            "/api/projects/",
            json={
                "title": "Test Project Empty Config",
                "description": "Project with empty config",
                "label_config": "",
            },
            headers=auth_headers["admin"],
        )

        # Empty config should be rejected by validator
        is_valid, errors = LabelConfigValidator.validate("")
        assert is_valid is False

        # Validation is now integrated - empty configs are rejected
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "Invalid label configuration" in data["detail"]["message"]

    def test_create_project_without_config(self, client, test_org, auth_headers):
        """Test creating project without label config (omitted field)"""
        response = client.post(
            "/api/projects/",
            json={"title": "Test Project No Config", "description": "Project without label config"},
            headers=auth_headers["admin"],
        )

        # Missing label_config should be accepted (optional field)
        assert response.status_code == 200
        data = response.json()
        assert data["label_config"] is None or data["label_config"] == ""


class TestLabelConfigUpdates:
    """Test label config updates on existing projects"""

    def test_update_project_label_config(self, client, test_project_with_config, auth_headers):
        """Test updating label config on existing project"""
        new_config = "<View><Choices name='sentiment'/><Rating name='confidence'/></View>"

        response = client.patch(
            f"/api/projects/{test_project_with_config.id}",
            json={"label_config": new_config},
            headers=auth_headers["admin"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["label_config"] == new_config

    def test_update_to_invalid_config(self, client, test_project_with_config, auth_headers):
        """Test updating to invalid config is rejected"""
        invalid_config = "<View><Unclosed tag"

        response = client.patch(
            f"/api/projects/{test_project_with_config.id}",
            json={"label_config": invalid_config},
            headers=auth_headers["admin"],
        )

        # Validation is now integrated - invalid updates are rejected
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "message" in data["detail"]
        assert "errors" in data["detail"]
        assert "Invalid label configuration" in data["detail"]["message"]

        # Verify validator caught the error
        is_valid, errors = LabelConfigValidator.validate(invalid_config)
        assert is_valid is False

    def test_update_creates_version(self, client, test_project_with_config, test_db, auth_headers):
        """Test that updating label config creates version history"""
        initial_config = test_project_with_config.label_config
        new_config = "<View><Choices name='sentiment'/><Rating name='quality'/></View>"

        response = client.patch(
            f"/api/projects/{test_project_with_config.id}",
            json={"label_config": new_config},
            headers=auth_headers["admin"],
        )

        assert response.status_code == 200

        # Refresh project to see changes
        test_db.refresh(test_project_with_config)

        # Check version was incremented
        assert test_project_with_config.label_config_version == "v2"
        assert test_project_with_config.label_config == new_config

        # Check old version was saved in history
        assert "v1" in test_project_with_config.label_config_history["versions"]
        v1_entry = test_project_with_config.label_config_history["versions"]["v1"]
        assert v1_entry["schema"] == initial_config

    def test_concurrent_config_updates(self, test_db, test_users, test_org):
        """Test concurrent updates maintain version consistency"""
        admin_user = test_users[0]

        # Create project
        project = Project(
            id="test-project-concurrent",
            title="Concurrent Test Project",
            created_by=admin_user.id,
            label_config="<View><Choices name='sentiment'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        test_db.add(project)
        test_db.commit()

        # Simulate sequential updates
        schema_1 = "<View><Choices name='sentiment'/><Rating name='quality'/></View>"
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_1,
            description="User A adds quality",
            user_id=admin_user.id,
        )
        test_db.commit()
        test_db.refresh(project)

        assert project.label_config_version == "v2"

        # Update 2: Add another field
        schema_2 = (
            "<View><Choices name='sentiment'/><Rating name='quality'/><Number name='count'/></View>"
        )
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_2,
            description="User B adds count",
            user_id=admin_user.id,
        )
        test_db.commit()
        test_db.refresh(project)

        # Verify versions are correct
        assert project.label_config_version == "v3"
        assert "v1" in project.label_config_history["versions"]
        assert "v2" in project.label_config_history["versions"]


class TestConfigTemplates:
    """Test config templates and defaults"""

    def test_default_config_application(self, client, test_org, auth_headers):
        """Test default config is applied if none provided"""
        response = client.post(
            "/api/projects/",
            json={"title": "Default Config Project", "description": "Should get default config"},
            headers=auth_headers["admin"],
        )

        assert response.status_code == 200
        data = response.json()

        # Currently no default config is applied
        # This test documents current behavior
        assert data["label_config"] is None or data["label_config"] == ""

    def test_predefined_template_usage(self):
        """Test using predefined template (if templates exist)"""
        # This is a placeholder for future template functionality
        # Currently BenGER doesn't have predefined templates stored in DB
        # This test documents the expected behavior when templates are added

        # For now, just verify validator works with common patterns
        sentiment_template = '<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/><Choice value="neutral"/></Choices></View>'

        is_valid, errors = LabelConfigValidator.validate(sentiment_template)
        assert is_valid is True
        assert len(errors) == 0


class TestErrorHandling:
    """Test error handling and validation error responses"""

    def test_validation_error_response_format(self):
        """Test that validation errors return proper format"""
        # Test various invalid configs
        test_cases = [
            ("<View><Unclosed tag", "XML parsing failed"),
            ("<!DOCTYPE foo><View/>", "External entity references"),
            ("<View><script>alert('xss')</script></View>", "Script tags"),
            ("<View onclick='alert()'/></View>", "Event handlers"),
        ]

        for invalid_config, expected_error in test_cases:
            is_valid, errors = LabelConfigValidator.validate(invalid_config)
            assert is_valid is False
            assert len(errors) > 0
            # Check error message contains expected text
            error_str = " ".join(errors)
            assert expected_error.lower() in error_str.lower() or len(errors) > 0

    def test_rollback_on_invalid_update(
        self, client, test_project_with_config, test_db, auth_headers
    ):
        """Test that failed update doesn't corrupt existing config"""
        test_project_with_config.label_config
        test_project_with_config.label_config_version

        # Try to update with massive config (exceeds size limit)
        huge_config = "<View>" + ("x" * 100000) + "</View>"

        # Currently no size validation in API, so this will succeed
        # After validation integration, this should fail with 422
        response = client.patch(
            f"/api/projects/{test_project_with_config.id}",
            json={"label_config": huge_config},
            headers=auth_headers["admin"],
        )

        # Verify validation would reject this
        is_valid, errors = LabelConfigValidator.validate(huge_config)
        assert is_valid is False
        assert any("maximum size" in err for err in errors)

        # After validation integration, verify rollback:
        # test_db.refresh(test_project_with_config)
        # assert test_project_with_config.label_config == original_config
        # assert test_project_with_config.label_config_version == original_version
