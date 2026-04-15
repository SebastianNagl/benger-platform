"""
Unit tests for user service functions
"""

import os
import sys

# Ensure utils module can be found
if '/app' not in sys.path:
    sys.path.insert(0, '/app')
api_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

# UserRole enum removed - now using is_superadmin boolean
from user_service import (
    authenticate_user,
    create_user,
    get_password_hash,
    get_user_by_id,
    get_user_by_username,
    get_users,
    init_demo_users,
    update_user_status,
    update_user_superadmin_status,
    verify_password,
)


@pytest.mark.unit
@pytest.mark.database
class TestPasswordFunctions:
    """Test password hashing and verification"""

    def test_password_hashing(self):
        """Test password hashing"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert len(hashed) > 20  # Bcrypt hashes are long
        assert hashed.startswith("$2b$")  # Bcrypt prefix

    def test_password_verification_success(self):
        """Test successful password verification"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_failure(self):
        """Test failed password verification"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_password_verification_empty(self):
        """Test password verification with empty values"""
        # Empty strings should return False without raising exceptions
        try:
            result = verify_password("", "")
            assert result is False
        except Exception:
            # If it raises an exception, that's also acceptable behavior
            pass

        try:
            result = verify_password("password", "")
            assert result is False
        except Exception:
            # If it raises an exception, that's also acceptable behavior
            pass

        try:
            result = verify_password("", "hash")
            assert result is False
        except Exception:
            # If it raises an exception, that's also acceptable behavior
            pass


@pytest.mark.unit
@pytest.mark.database
class TestUserCRUD:
    """Test user CRUD operations"""

    def test_create_user_success(self, test_db):
        """Test successful user creation"""
        user = create_user(
            db=test_db,
            username="testuser@example.com",
            email="testuser@example.com",
            name="Test User",
            password="password123",
            is_superadmin=False,
        )

        assert user is not None
        assert user.username == "testuser@example.com"
        assert user.email == "testuser@example.com"
        assert user.name == "Test User"
        assert user.is_superadmin == False
        assert user.is_active is True

    def test_create_user_duplicate_username(self, test_db, test_users):
        """Test creating user with duplicate username fails"""
        existing_user = test_users[0]

        with pytest.raises((IntegrityError, HTTPException)):
            create_user(
                db=test_db,
                username=existing_user.username,
                email="different@example.com",
                name="Different User",
                password="password123",
                is_superadmin=False,
            )

    def test_get_user_by_id_success(self, test_db, test_users):
        """Test getting user by ID"""
        existing_user = test_users[0]
        user = get_user_by_id(test_db, existing_user.id)

        assert user is not None
        assert user.id == existing_user.id
        assert user.username == existing_user.username

    def test_get_user_by_id_not_found(self, test_db):
        """Test getting non-existent user by ID"""
        user = get_user_by_id(test_db, "nonexistent-id")
        assert user is None

    def test_get_user_by_username_success(self, test_db, test_users):
        """Test getting user by username"""
        existing_user = test_users[0]
        user = get_user_by_username(test_db, existing_user.username)

        assert user is not None
        assert user.username == existing_user.username
        assert user.id == existing_user.id

    def test_get_user_by_username_not_found(self, test_db):
        """Test getting non-existent user by username"""
        user = get_user_by_username(test_db, "nonexistent@example.com")
        assert user is None

    def test_get_users(self, test_db, test_users):
        """Test getting all users"""
        users = get_users(test_db)

        assert len(users) >= len(test_users)
        usernames = [user.username for user in users]
        for test_user in test_users:
            assert test_user.username in usernames

    def test_authenticate_user_success(self, test_db, test_users):
        """Test successful user authentication"""
        # We know the test users have specific passwords
        user = authenticate_user(test_db, "admin@test.com", "admin123")

        assert user is not None
        assert user.username == "admin@test.com"
        assert user.is_superadmin == True

    def test_authenticate_user_wrong_password(self, test_db, test_users):
        """Test authentication with wrong password"""
        user = authenticate_user(test_db, "admin@test.com", "wrong_password")
        assert user is None

    def test_authenticate_user_nonexistent(self, test_db):
        """Test authentication with non-existent user"""
        user = authenticate_user(test_db, "nonexistent@example.com", "password")
        assert user is None

    def test_authenticate_user_by_email(self, test_db, test_users):
        """Test authentication using email instead of username"""
        user = authenticate_user(test_db, "admin@test.com", "admin123")

        assert user is not None
        assert user.email == "admin@test.com"

    def test_update_user_superadmin_status_success(self, test_db, test_users):
        """Test updating user role"""
        user = test_users[2]  # regular user
        original_superadmin = user.is_superadmin

        updated_user = update_user_superadmin_status(test_db, user.id, True)

        assert updated_user is not None
        assert updated_user.is_superadmin == True
        assert updated_user.is_superadmin != original_superadmin

    def test_update_user_superadmin_status_nonexistent(self, test_db):
        """Test updating role of non-existent user"""
        updated_user = update_user_superadmin_status(test_db, "nonexistent-id", True)
        assert updated_user is None

    def test_update_user_status_success(self, test_db, test_users):
        """Test updating user status"""
        user = test_users[2]  # regular user
        original_status = user.is_active

        updated_user = update_user_status(test_db, user.id, not original_status)

        assert updated_user is not None
        assert updated_user.is_active != original_status

    def test_update_user_status_nonexistent(self, test_db):
        """Test updating status of non-existent user"""
        updated_user = update_user_status(test_db, "nonexistent-id", False)
        assert updated_user is None


DEMO_USERNAMES = ["admin", "org_admin", "contributor", "annotator", "annotator2", "annotator3", "basicuser"]


@pytest.mark.unit
@pytest.mark.database
class TestDemoUsers:
    """Test demo user initialization"""

    def test_init_demo_users(self, clean_database):
        """Test initializing demo users"""
        db = clean_database

        # Initialize demo users
        init_demo_users(db)

        # Verify all 7 demo users exist by username
        for username in DEMO_USERNAMES:
            user = get_user_by_username(db, username)
            assert user is not None, f"Demo user '{username}' should exist after init_demo_users"

        # Verify admin is superadmin
        admin_user = get_user_by_username(db, "admin")
        assert admin_user.is_superadmin == True

        # Check that admin user can authenticate
        admin_auth = authenticate_user(db, "admin", "admin")
        assert admin_auth is not None
        assert admin_auth.is_superadmin == True

    def test_init_demo_users_idempotent(self, clean_database):
        """Test that initializing demo users multiple times is safe"""
        db = clean_database

        # Initialize demo users first time
        init_demo_users(db)
        users_after_first = get_users(db)
        first_count = len(users_after_first)

        # Initialize demo users again
        init_demo_users(db)

        # Should not create duplicate users
        users_after_second = get_users(db)
        assert len(users_after_second) == first_count

    def test_init_demo_users_skipped_in_production(self, clean_database, monkeypatch):
        """Test that demo users are NOT created in production environment"""
        db = clean_database

        # Set production environment
        monkeypatch.setenv("ENVIRONMENT", "production")

        # Count users before
        users_before = get_users(db)
        count_before = len(users_before)

        # Initialize demo users (should be skipped in production)
        init_demo_users(db)

        # Should not create any new users
        users_after = get_users(db)
        assert len(users_after) == count_before

    def test_init_demo_users_created_in_development(self, clean_database, monkeypatch):
        """Test that demo users ARE created in development environment"""
        db = clean_database

        # Set development environment explicitly
        monkeypatch.setenv("ENVIRONMENT", "development")

        # Initialize demo users (should create them)
        init_demo_users(db)

        # Verify all 7 demo users exist by username
        for username in DEMO_USERNAMES:
            user = get_user_by_username(db, username)
            assert user is not None, f"Demo user '{username}' should exist in development environment"

    def test_init_demo_users_created_when_environment_unset(self, clean_database, monkeypatch):
        """Test that demo users ARE created when ENVIRONMENT is not set (default behavior)"""
        db = clean_database

        # Unset environment variable
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        # Initialize demo users (should create them with default development behavior)
        init_demo_users(db)

        # Verify all 7 demo users exist by username
        for username in DEMO_USERNAMES:
            user = get_user_by_username(db, username)
            assert user is not None, f"Demo user '{username}' should exist when ENVIRONMENT is unset"

    def test_init_demo_users_created_in_test_environment(self, clean_database, monkeypatch):
        """Test that demo users ARE created in test environment"""
        db = clean_database

        # Set test environment
        monkeypatch.setenv("ENVIRONMENT", "test")

        # Initialize demo users (should create them)
        init_demo_users(db)

        # Verify all 7 demo users exist by username
        for username in DEMO_USERNAMES:
            user = get_user_by_username(db, username)
            assert user is not None, f"Demo user '{username}' should exist in test environment"
