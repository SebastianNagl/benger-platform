#!/usr/bin/env python3
"""
Database Schema Validator

This script validates that the production database schema matches
the expected structure defined by the application models.

Usage:
    python schema_validator.py

Environment Variables:
    DATABASE_URI - PostgreSQL connection string

Exit Codes:
    0 - Schema validation passed
    1 - Schema validation failed
    2 - Connection error
"""

import os
import sys
from typing import Dict, List, Set

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


def get_database_engine():
    """Create database engine from environment variables"""
    database_uri = os.getenv("DATABASE_URI")
    if not database_uri:
        print("❌ ERROR: DATABASE_URI environment variable not set")
        sys.exit(2)

    try:
        # Add connection pool settings and timeout
        engine = create_engine(
            database_uri,
            pool_pre_ping=True,  # Verify connections before using
            pool_timeout=10,  # 10 second timeout
            connect_args={
                "connect_timeout": 10,  # PostgreSQL connection timeout
                "options": "-c statement_timeout=30000",  # 30 second statement timeout
            },
        )
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except SQLAlchemyError as e:
        print(f"❌ ERROR: Database connection failed: {e}")
        sys.exit(2)


def get_expected_schema() -> Dict[str, List[str]]:
    """Define the expected database schema based on actual models.

    Updated to match the current squashed migration (001_complete_baseline).
    Only checks core columns that must exist - extra columns are informational.
    """
    return {
        "users": [
            "id",
            "username",
            "email",
            "name",
            "hashed_password",
            "is_superadmin",
            "is_active",
            "created_at",
            "updated_at",
            "encrypted_openai_api_key",
            "encrypted_anthropic_api_key",
            "encrypted_google_api_key",
            "encrypted_deepinfra_api_key",
        ],
        "organizations": [
            "id",
            "name",
            "slug",
            "created_at",
            "updated_at",
        ],
        "organization_memberships": [
            "id",
            "user_id",
            "organization_id",
            "role",
            "joined_at",
        ],
        "projects": [
            "id",
            "title",
            "created_by",
            "created_at",
            "updated_at",
        ],
        "tasks": [
            "id",
            "project_id",
            "data",
            "created_by",
            "created_at",
            "updated_at",
        ],
        "annotations": [
            "id",
            "task_id",
            "project_id",
            "completed_by",
            "created_at",
            "updated_at",
        ],
        "evaluation_runs": [
            "id",
            "project_id",
            "model_id",
            "evaluation_type_ids",
            "metrics",
            "status",
            "created_by",
            "created_at",
            "completed_at",
        ],
        "evaluation_types": [
            "id",
            "name",
            "description",
            "category",
            "higher_is_better",
            "value_range",
            "applicable_project_types",
            "is_active",
            "created_at",
            "updated_at",
        ],
        "evaluation_run_metrics": [
            "id",
            "evaluation_id",
            "evaluation_type_id",
            "value",
            "created_at",
        ],
        "llm_models": [
            "id",
            "name",
            "provider",
            "model_type",
            "is_active",
            "created_at",
        ],
        "response_generations": [
            "id",
            "project_id",
            "model_id",
            "status",
            "created_by",
            "created_at",
        ],
        "generations": [
            "id",
            "generation_id",
            "task_id",
            "model_id",
            "response_content",
            "status",
            "created_at",
        ],
        "uploaded_data": [
            "id",
            "name",
            "original_filename",
            "file_path",
            "size",
            "format",
            "task_id",
            "uploaded_by",
            "upload_date",
            "processed",
        ],
        "user_column_preferences": [
            "id",
            "user_id",
            "task_id",
            "column_settings",
            "created_at",
            "updated_at",
        ],
        "feature_flags": [
            "id",
            "name",
            "is_enabled",
            "created_at",
        ],
        "notifications": [
            "id",
            "user_id",
            "type",
            "title",
            "message",
            "created_at",
        ],
    }


def validate_table_exists(inspector, table_name: str) -> bool:
    """Check if a table exists in the database"""
    try:
        return inspector.has_table(table_name)
    except SQLAlchemyError:
        return False


def get_table_columns(inspector, table_name: str) -> Set[str]:
    """Get all column names for a table"""
    try:
        columns = inspector.get_columns(table_name)
        return {col["name"] for col in columns}
    except SQLAlchemyError:
        return set()


def validate_schema() -> bool:
    """
    Validate database schema against expected structure

    Returns:
        bool: True if validation passes, False otherwise
    """
    print("🔍 Starting database schema validation...")

    engine = get_database_engine()
    inspector = inspect(engine)
    expected_schema = get_expected_schema()

    validation_passed = True

    # Check each expected table
    for table_name, expected_columns in expected_schema.items():
        print(f"\n📋 Validating table: {table_name}")

        # Check if table exists
        if not validate_table_exists(inspector, table_name):
            print(f"❌ Table '{table_name}' does not exist")
            validation_passed = False
            continue

        print(f"✅ Table '{table_name}' exists")

        # Check columns
        actual_columns = get_table_columns(inspector, table_name)
        expected_columns_set = set(expected_columns)

        # Check for missing columns
        missing_columns = expected_columns_set - actual_columns
        if missing_columns:
            print(f"❌ Missing columns in '{table_name}': {sorted(missing_columns)}")
            validation_passed = False

        # Check for extra columns (informational only)
        extra_columns = actual_columns - expected_columns_set
        if extra_columns:
            print(f"ℹ️  Extra columns in '{table_name}': {sorted(extra_columns)}")

        # Show status
        if not missing_columns:
            print(f"✅ All required columns present in '{table_name}'")

        print(
            f"📊 Columns in '{table_name}': {len(actual_columns)} actual, {len(expected_columns)} expected"
        )

    return validation_passed


def validate_data_integrity() -> bool:
    """
    Validate data integrity constraints that have caused issues

    Returns:
        bool: True if validation passes, False otherwise
    """
    print("\n🔍 Validating data integrity...")

    engine = get_database_engine()
    validation_passed = True

    try:
        with engine.connect() as conn:
            # Check for orphaned tasks (tasks with created_by pointing to non-existent users)
            # Note: tasks.created_by CAN be NULL (SET NULL on user delete) - that's valid
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) FROM tasks t
                LEFT JOIN users u ON t.created_by = u.id
                WHERE t.created_by IS NOT NULL AND u.id IS NULL
            """
                )
            )
            orphaned_tasks_count = result.fetchone()[0]

            if orphaned_tasks_count > 0:
                print(f"❌ Found {orphaned_tasks_count} tasks with invalid created_by references")
                validation_passed = False
            else:
                print("✅ All tasks have valid user references")

            # Check for orphaned evaluations (evaluations with invalid project_id)
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) FROM evaluation_runs e
                LEFT JOIN projects p ON e.project_id = p.id
                WHERE e.project_id IS NOT NULL AND p.id IS NULL
            """
                )
            )
            orphaned_evals_count = result.fetchone()[0]

            if orphaned_evals_count > 0:
                print(
                    f"❌ Found {orphaned_evals_count} evaluations with invalid project_id references"
                )
                validation_passed = False
            else:
                print("✅ All evaluations have valid project references")

    except SQLAlchemyError as e:
        print(f"❌ Data integrity check failed: {e}")
        validation_passed = False

    return validation_passed


def generate_fix_commands(engine) -> List[str]:
    """
    Generate SQL commands to fix common schema issues

    Returns:
        List[str]: SQL commands to fix issues
    """
    print("\n🔧 Generating fix commands...")

    inspector = inspect(engine)
    expected_schema = get_expected_schema()
    fix_commands = []

    for table_name, expected_columns in expected_schema.items():
        if not validate_table_exists(inspector, table_name):
            print(f"⚠️  Cannot generate fixes for missing table: {table_name}")
            continue

        actual_columns = get_table_columns(inspector, table_name)
        missing_columns = set(expected_columns) - actual_columns

        for column in missing_columns:
            # Determine column type based on common patterns
            if "encrypted_" in column:
                column_type = "TEXT"
            elif column.endswith("_id"):
                column_type = "UUID"
            elif column.endswith("_at"):
                column_type = "TIMESTAMP WITH TIME ZONE"
            elif column in ["name", "description", "username", "email"]:
                column_type = "VARCHAR(255)"
            elif column == "is_active":
                column_type = "BOOLEAN DEFAULT TRUE"
            else:
                column_type = "TEXT"

            fix_command = (
                f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column} {column_type};"
            )
            fix_commands.append(fix_command)

    return fix_commands


def main():
    """Main validation function"""
    print("🚀 BenGer Database Schema Validator")
    print("=" * 50)

    try:
        # Validate schema structure
        schema_valid = validate_schema()

        # Validate data integrity
        data_valid = validate_data_integrity()

        # Overall result
        print("\n" + "=" * 50)
        if schema_valid and data_valid:
            print("✅ ALL VALIDATIONS PASSED")
            print("🟢 Database schema is healthy and ready for production")
            sys.exit(0)
        else:
            print("❌ VALIDATION FAILED")

            # Generate fix commands if schema issues found
            if not schema_valid:
                engine = get_database_engine()
                fix_commands = generate_fix_commands(engine)

                if fix_commands:
                    print("\n🔧 Suggested fix commands:")
                    print('kubectl exec -n benger deployment/benger-api -- python -c "')
                    print("import os; from sqlalchemy import create_engine, text;")
                    print("engine = create_engine(os.getenv('DATABASE_URI'));")
                    print("conn = engine.connect();")
                    for cmd in fix_commands:
                        print(f"conn.execute(text('{cmd}'));")
                    print("conn.commit();")
                    print("print('Schema fixes applied');")
                    print('"')

            print("🔴 Database schema validation failed")
            sys.exit(1)

    except Exception as e:
        print(f"💥 FATAL ERROR: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
