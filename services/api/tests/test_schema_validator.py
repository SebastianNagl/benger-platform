"""
Comprehensive tests for the schema validator module.

These tests ensure the schema validator correctly detects:
- Missing tables and columns
- Type mismatches
- Foreign key issues
- Migration problems
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Boolean, Column, ForeignKey, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base

from app.core.schema_validator import (
    SchemaValidator,
    ValidationError,
    ValidationMode,
    ValidationResult,
    create_validator_from_env,
)

Base = declarative_base()


# Test models for validation
class TestUser(Base):
    __tablename__ = "test_users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)


class TestProject(Base):
    __tablename__ = "test_projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("test_users.id"))


class TestSchemaValidator:
    """Test suite for SchemaValidator class"""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            engine = create_engine(f"sqlite:///{tmp.name}")
            Base.metadata.create_all(engine)
            yield engine
            engine.dispose()

    @pytest.fixture
    def validator_with_db(self, temp_db):
        """Create a validator with a test database"""
        return SchemaValidator(temp_db, ValidationMode.STRICT)

    def test_validation_mode_initialization(self):
        """Test validator initialization with different modes"""
        # Test strict mode
        validator = SchemaValidator(mode=ValidationMode.STRICT)
        assert validator.mode == ValidationMode.STRICT

        # Test lenient mode
        validator = SchemaValidator(mode=ValidationMode.LENIENT)
        assert validator.mode == ValidationMode.LENIENT

        # Test disabled mode
        validator = SchemaValidator(mode=ValidationMode.DISABLED)
        assert validator.mode == ValidationMode.DISABLED

    def test_disabled_mode_always_passes(self, temp_db):
        """Test that disabled mode always returns valid"""
        validator = SchemaValidator(temp_db, ValidationMode.DISABLED)
        result = validator.validate()

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_missing_table_detection(self, temp_db):
        """Test detection of missing tables"""
        validator = SchemaValidator(temp_db, ValidationMode.STRICT)

        # Override expected schema to include non-existent table
        def mock_expected_schema():
            return {
                "missing_table": {
                    "columns": {"id": "VARCHAR"},
                    "indexes": [],
                    "foreign_keys": [],
                }
            }

        validator.get_expected_schema = mock_expected_schema
        result = validator.validate()

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("missing_table" in str(e) for e in result.errors)

    def test_missing_column_detection(self, temp_db):
        """Test detection of missing columns"""
        validator = SchemaValidator(temp_db, ValidationMode.STRICT)

        # Create a table
        with temp_db.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS test_table (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR
                )
            """
                )
            )
            conn.commit()

        # Override expected schema to include additional column
        def mock_expected_schema():
            return {
                "test_table": {
                    "columns": {
                        "id": "VARCHAR",
                        "name": "VARCHAR",
                        "missing_column": "VARCHAR",  # This column doesn't exist
                    },
                    "indexes": [],
                    "foreign_keys": [],
                }
            }

        validator.get_expected_schema = mock_expected_schema
        result = validator.validate()

        assert result.is_valid is False
        assert any("missing_column" in str(e) for e in result.errors)

    def test_extra_column_warning(self, temp_db):
        """Test that extra columns generate warnings"""
        validator = SchemaValidator(temp_db, ValidationMode.STRICT)

        # Create a table with extra column
        with temp_db.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS test_table (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR,
                    extra_column VARCHAR
                )
            """
                )
            )
            conn.commit()

        # Override expected schema without the extra column
        def mock_expected_schema():
            return {
                "test_table": {
                    "columns": {"id": "VARCHAR", "name": "VARCHAR"},
                    "indexes": [],
                    "foreign_keys": [],
                }
            }

        validator.get_expected_schema = mock_expected_schema
        result = validator.validate()

        # Extra columns should be warnings, not errors
        assert any("extra_column" in str(w) for w in result.warnings)

    def test_lenient_mode_converts_errors_to_warnings(self, temp_db):
        """Test that lenient mode converts errors to warnings"""
        validator = SchemaValidator(temp_db, ValidationMode.LENIENT)

        # Override expected schema to cause errors
        def mock_expected_schema():
            return {
                "missing_table": {
                    "columns": {"id": "VARCHAR"},
                    "indexes": [],
                    "foreign_keys": [],
                }
            }

        validator.get_expected_schema = mock_expected_schema
        result = validator.validate()

        # In lenient mode, should still be valid but with warnings
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) > 0

    def test_type_consistency_check(self, temp_db):
        """Test foreign key type consistency checking"""
        # Create tables with type mismatch
        with temp_db.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE TABLE parent_table (
                    id INTEGER PRIMARY KEY
                )
            """
                )
            )
            conn.execute(
                text(
                    """
                CREATE TABLE child_table (
                    id INTEGER PRIMARY KEY,
                    parent_id VARCHAR,
                    FOREIGN KEY (parent_id) REFERENCES parent_table(id)
                )
            """
                )
            )
            conn.commit()

        validator = SchemaValidator(temp_db, ValidationMode.STRICT)
        result = validator.check_type_consistency()

        # Should detect type mismatch
        assert result.is_valid is False
        assert any("Type mismatch" in str(e) for e in result.errors)

    def test_migration_history_check_no_table(self, temp_db):
        """Test migration history check when alembic_version table doesn't exist"""
        validator = SchemaValidator(temp_db, ValidationMode.STRICT)
        result = validator.check_migration_history()

        # Should warn about missing alembic_version table
        assert any("alembic_version" in str(w) for w in result.warnings)

    def test_migration_history_check_multiple_heads(self, temp_db):
        """Test detection of multiple migration heads"""
        # Create alembic_version table with multiple entries
        with temp_db.connect() as conn:
            conn.execute(
                text(
                    """
                CREATE TABLE alembic_version (
                    version_num VARCHAR PRIMARY KEY
                )
            """
                )
            )
            conn.execute(text("INSERT INTO alembic_version VALUES ('head1')"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('head2')"))
            conn.commit()

        validator = SchemaValidator(temp_db, ValidationMode.STRICT)
        result = validator.check_migration_history()

        # Should detect multiple heads
        assert result.is_valid is False
        assert any("Multiple migration heads" in str(e) for e in result.errors)

    def test_validation_result_summary(self):
        """Test ValidationResult summary generation"""
        # Test valid result
        result = ValidationResult(is_valid=True)
        assert "passed" in result.get_summary().lower()

        # Test invalid result with errors
        result = ValidationResult(is_valid=False)
        result.add_error("test_table", "missing", "Table is missing")
        assert "failed" in result.get_summary().lower()
        assert "1 errors" in result.get_summary()

        # Test result with warnings
        result = ValidationResult(is_valid=True)
        result.add_warning("test_table", "extra", "Extra column found")
        assert "passed" in result.get_summary().lower()
        assert "1 warnings" in result.get_summary()

    def test_validation_error_string_representation(self):
        """Test ValidationError string representation"""
        error = ValidationError(
            table="test_table",
            error_type="missing_column",
            message="Column 'test_col' is missing",
            severity="error",
        )

        str_repr = str(error)
        assert "ERROR" in str_repr
        assert "test_table" in str_repr
        assert "Column 'test_col' is missing" in str_repr

    @patch.dict(
        os.environ,
        {"DATABASE_URI": "sqlite:///test.db", "SCHEMA_VALIDATION_MODE": "strict"},
    )
    def test_create_validator_from_env(self):
        """Test creating validator from environment variables"""
        with patch("app.core.schema_validator.create_engine") as mock_engine:
            mock_engine.return_value = MagicMock()

            validator = create_validator_from_env()

            assert validator is not None
            assert validator.mode == ValidationMode.STRICT
            mock_engine.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_create_validator_from_env_no_database_uri(self):
        """Test validator creation when DATABASE_URI is not set"""
        validator = create_validator_from_env()

        assert validator is not None
        assert validator.mode == ValidationMode.DISABLED

    @patch.dict(os.environ, {"DATABASE_URI": "invalid://uri"})
    def test_create_validator_from_env_invalid_uri(self):
        """Test validator creation with invalid database URI"""
        with patch("app.core.schema_validator.create_engine") as mock_engine:
            mock_engine.side_effect = Exception("Invalid URI")

            validator = create_validator_from_env()

            assert validator is not None
            assert validator.mode == ValidationMode.DISABLED


class TestValidationIntegration:
    """Integration tests for schema validation"""

    @pytest.fixture
    def real_db(self):
        """Create a more realistic test database"""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            engine = create_engine(f"sqlite:///{tmp.name}")

            # Create realistic schema
            with engine.connect() as conn:
                # Users table
                conn.execute(
                    text(
                        """
                    CREATE TABLE users (
                        id VARCHAR PRIMARY KEY,
                        email VARCHAR NOT NULL,
                        username VARCHAR,
                        role VARCHAR,
                        is_active BOOLEAN
                    )
                """
                    )
                )

                # Organizations table
                conn.execute(
                    text(
                        """
                    CREATE TABLE organizations (
                        id VARCHAR PRIMARY KEY,
                        name VARCHAR NOT NULL,
                        slug VARCHAR UNIQUE
                    )
                """
                    )
                )

                # Organization memberships with foreign keys
                conn.execute(
                    text(
                        """
                    CREATE TABLE organization_memberships (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR,
                        organization_id VARCHAR,
                        role VARCHAR,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (organization_id) REFERENCES organizations(id)
                    )
                """
                    )
                )

                # Alembic version table
                conn.execute(
                    text(
                        """
                    CREATE TABLE alembic_version (
                        version_num VARCHAR PRIMARY KEY
                    )
                """
                    )
                )
                conn.execute(text("INSERT INTO alembic_version VALUES ('abc123')"))

                conn.commit()

            yield engine
            engine.dispose()

    def test_full_validation_on_realistic_schema(self, real_db):
        """Test full validation on a realistic database schema"""
        validator = SchemaValidator(real_db, ValidationMode.STRICT)

        # This should validate against the actual expected schema
        result = validator.validate()

        # The validation might fail due to schema differences,
        # but it should complete without exceptions
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "is_valid")
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_concurrent_validation(self, real_db):
        """Test that validation can handle concurrent access"""
        import threading

        results = []

        def run_validation():
            validator = SchemaValidator(real_db, ValidationMode.STRICT)
            result = validator.validate()
            results.append(result)

        # Run validation in multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=run_validation)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All validations should complete
        assert len(results) == 5
        for result in results:
            assert isinstance(result, ValidationResult)
