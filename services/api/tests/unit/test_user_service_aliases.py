"""
Tests for Issue #143: Password Hashing Function Import Issues
Verifies that function aliases work correctly
"""

import pytest

from user_service import check_password, get_password_hash, hash_password, verify_password


class TestPasswordHashingAliases:
    """Test password hashing function aliases"""

    def test_hash_password_alias_works(self):
        """Test that hash_password is an alias for get_password_hash"""
        password = "test_password_123"

        # Both functions should return the same type of hash
        hash1 = get_password_hash(password)
        hash2 = hash_password(password)

        # They won't be identical due to bcrypt salting, but both should be valid
        assert isinstance(hash1, str)
        assert isinstance(hash2, str)
        assert hash1.startswith("$2b$")  # bcrypt hash prefix
        assert hash2.startswith("$2b$")  # bcrypt hash prefix

        # Both hashes should verify against the original password
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_check_password_alias_works(self):
        """Test that check_password is an alias for verify_password"""
        password = "test_password_456"
        wrong_password = "wrong_password"

        # Create a hash
        password_hash = get_password_hash(password)

        # Both verification functions should work identically
        assert verify_password(password, password_hash) == True
        assert check_password(password, password_hash) == True

        assert verify_password(wrong_password, password_hash) == False
        assert check_password(wrong_password, password_hash) == False

    def test_aliases_are_same_function_objects(self):
        """Test that aliases point to the same function objects"""
        # Direct function comparison
        assert hash_password is get_password_hash
        assert check_password is verify_password

        # They should have the same memory address
        assert id(hash_password) == id(get_password_hash)
        assert id(check_password) == id(verify_password)

    def test_import_variations_work(self):
        """Test that various import patterns work correctly"""
        # Test import variations that developers might try

        # Original function names
        # Common alias names
        from user_service import check_password, get_password_hash, hash_password, verify_password

        # All imports should work without error
        assert callable(get_password_hash)
        assert callable(verify_password)
        assert callable(hash_password)
        assert callable(check_password)

    def test_function_documentation_preserved(self):
        """Test that aliases preserve original function documentation"""
        # Check that docstrings are preserved
        assert get_password_hash.__doc__ == hash_password.__doc__
        assert verify_password.__doc__ == check_password.__doc__

        # Check that function names are different (aliases don't change __name__)
        assert get_password_hash.__name__ == "get_password_hash"
        assert hash_password.__name__ == "get_password_hash"  # Points to same function
        assert verify_password.__name__ == "verify_password"
        assert check_password.__name__ == "verify_password"  # Points to same function

    def test_cross_compatibility(self):
        """Test that hashes created with one function work with the other"""
        password = "cross_compat_test"

        # Create hash with original function, verify with alias
        hash_original = get_password_hash(password)
        assert check_password(password, hash_original)

        # Create hash with alias, verify with original
        hash_alias = hash_password(password)
        assert verify_password(password, hash_alias)

        # Mix and match all combinations
        assert verify_password(password, hash_original)
        assert check_password(password, hash_alias)


class TestRealWorldUsageCases:
    """Test real-world usage scenarios that led to Issue #143"""

    def test_original_failing_code_pattern(self):
        """Test the code pattern that originally failed"""
        # This import pattern now works thanks to the alias
        from user_service import hash_password

        # Original failing code pattern (now works)
        password = "user_password"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$")

    def test_user_creation_pattern(self):
        """Test common user creation pattern"""
        from user_service import hash_password, verify_password

        # Simulate user creation
        user_password = "secure_password_123"
        stored_hash = hash_password(user_password)

        # Simulate user login verification
        assert verify_password(user_password, stored_hash)
        assert not verify_password("wrong_password", stored_hash)

    def test_multiple_import_styles(self):
        """Test that different import styles all work"""
        # Style 1: Direct imports
        # Style 2: Module import
        import user_service
        from user_service import get_password_hash, hash_password

        # All should work
        password = "test_import_styles"

        hash1 = get_password_hash(password)
        hash2 = hash_password(password)
        hash3 = user_service.get_password_hash(password)
        hash4 = user_service.hash_password(password)

        # All should produce valid bcrypt hashes
        for h in [hash1, hash2, hash3, hash4]:
            assert isinstance(h, str)
            assert h.startswith("$2b$")
            assert user_service.verify_password(password, h)


class TestBackwardCompatibility:
    """Ensure changes don't break existing code"""

    def test_original_functions_still_work(self):
        """Test that original function names still work"""
        from user_service import get_password_hash, verify_password

        password = "backward_compat_test"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed)
        assert not verify_password("wrong", hashed)

    def test_no_namespace_pollution(self):
        """Test that we haven't added unexpected exports"""
        import user_service

        # Check that private functions aren't exposed
        assert not hasattr(user_service, "_internal_function")
        assert not hasattr(
            user_service, "pwd_context"
        )  # Should not expose internal context without underscore

        # Check that expected functions are present
        expected_functions = [
            "get_password_hash",
            "hash_password",
            "verify_password",
            "check_password",
            "get_user_by_id",
            "get_user_by_username",
            "get_user_by_email",
            "create_user",
            "update_user_profile",
            "delete_user",
            "authenticate_user",
            "get_users",
        ]

        for func_name in expected_functions:
            assert hasattr(user_service, func_name), f"Missing expected function: {func_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
