"""User fixtures for BenGER API tests.

Provides test user creation, authentication headers, and user-related helpers.

Four test users cover all permission levels:
- admin (superadmin) — full system access
- org_admin (non-superadmin, ORG_ADMIN role) — org-level management
- contributor (CONTRIBUTOR role) — project editing, no deletion
- annotator (ANNOTATOR role) — annotation only
"""

from datetime import datetime
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import User
from user_service import get_password_hash


@pytest.fixture(scope="function")
def test_users(test_db: Session) -> List[User]:
    """Create test users in the database.

    Returns list of 4 users:
    [0] admin (superadmin=True, ORG_ADMIN membership)
    [1] contributor (superadmin=False, CONTRIBUTOR membership)
    [2] annotator (superadmin=False, ANNOTATOR membership)
    [3] org_admin (superadmin=False, ORG_ADMIN membership)
    """
    users_data = [
        {
            "id": "admin-test-id",
            "username": "admin@test.com",
            "email": "admin@test.com",
            "name": "Test Admin",
            "hashed_password": get_password_hash("admin123"),
            "is_superadmin": True,
            "is_active": True,
            "email_verified": True,
        },
        {
            "id": "contributor-test-id",
            "username": "contributor@test.com",
            "email": "contributor@test.com",
            "name": "Test Contributor",
            "hashed_password": get_password_hash("contrib123"),
            "is_superadmin": False,
            "is_active": True,
            "email_verified": True,
        },
        {
            "id": "annotator-test-id",
            "username": "annotator@test.com",
            "email": "annotator@test.com",
            "name": "Test Annotator",
            "hashed_password": get_password_hash("annotator123"),
            "is_superadmin": False,
            "is_active": True,
            "email_verified": True,
        },
        {
            "id": "org-admin-test-id",
            "username": "orgadmin@test.com",
            "email": "orgadmin@test.com",
            "name": "Test Org Admin",
            "hashed_password": get_password_hash("orgadmin123"),
            "is_superadmin": False,
            "is_active": True,
            "email_verified": True,
        },
    ]

    users = []
    for user_data in users_data:
        user = User(**user_data)
        test_db.add(user)
        users.append(user)

    test_db.commit()
    return users


@pytest.fixture(scope="function")
def test_user(test_db: Session) -> User:
    """Create a single test user with token for tests requiring one user."""
    from auth_module import create_access_token

    user = User(
        id="test-user-gen",
        username="genuser",
        email="gen@test.com",
        name="Generation Test User",
        hashed_password=get_password_hash("testpassword"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.utcnow(),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Attach token as attribute for auth_headers fixture
    user.token = create_access_token(data={"user_id": user.id})

    return user


@pytest.fixture(scope="function")
def auth_headers(client: TestClient, test_users: List[User]) -> Dict[str, Dict[str, str]]:
    """Get authentication headers for all 4 permission levels.

    Returns dict with keys: "admin", "org_admin", "contributor", "annotator"
    """
    from auth_module import create_access_token

    headers = {}

    for user in test_users:
        direct_token = create_access_token(data={"user_id": user.id})

        # Map users to role names
        if user.is_superadmin:
            role_name = "admin"
        elif "orgadmin" in user.username:
            role_name = "org_admin"
        elif "contributor" in user.username:
            role_name = "contributor"
        elif "annotator" in user.username:
            role_name = "annotator"
        else:
            role_name = "user"

        headers[role_name] = {"Authorization": f"Bearer {direct_token}"}

    # Ensure all required roles are present
    required_roles = ["admin", "org_admin", "contributor", "annotator"]
    for role in required_roles:
        if role not in headers:
            print(f"Warning: Missing auth header for role: {role}")
            headers[role] = {"Authorization": "Bearer dummy_token"}

    return headers
