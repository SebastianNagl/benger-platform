"""
Core Schema Validator Module

Validates that the database schema matches the SQLAlchemy model definitions.
Reads expected schema directly from Base.metadata (no hardcoded tables).
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ValidationMode(Enum):
    """Schema validation modes"""

    STRICT = "strict"  # Fail on any schema mismatch
    LENIENT = "lenient"  # Warn but continue on mismatches
    DISABLED = "disabled"  # Skip validation entirely


@dataclass
class ValidationError:
    """Represents a schema validation error"""

    table: str
    error_type: str
    message: str
    severity: str = "error"  # error, warning, info

    def __str__(self):
        return f"[{self.severity.upper()}] {self.table}: {self.message}"


@dataclass
class ValidationResult:
    """Result of schema validation"""

    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def add_error(self, table: str, error_type: str, message: str):
        """Add an error to the validation result"""
        self.errors.append(ValidationError(table, error_type, message, "error"))
        self.is_valid = False

    def add_warning(self, table: str, error_type: str, message: str):
        """Add a warning to the validation result"""
        self.warnings.append(ValidationError(table, error_type, message, "warning"))

    def get_summary(self) -> str:
        """Get a summary of validation results"""
        if self.is_valid:
            msg = "Schema validation passed"
            if self.warnings:
                msg += f" with {len(self.warnings)} warnings"
            return msg
        else:
            return f"Schema validation failed: {len(self.errors)} errors, {len(self.warnings)} warnings"


class SchemaValidator:
    """Database schema validator — compares SQLAlchemy models against actual DB"""

    # Tables managed outside our models (Alembic, extensions)
    IGNORED_TABLES = {"alembic_version"}

    def __init__(
        self,
        engine: Optional[Engine] = None,
        mode: ValidationMode = ValidationMode.STRICT,
    ):
        self.engine = engine
        self.mode = mode
        self.inspector = None

        if engine:
            self.inspector = inspect(engine)

    def get_expected_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        Build expected schema from SQLAlchemy model definitions (Base.metadata).
        This ensures the validator always matches the actual models.
        """
        # Import models to ensure they're registered with Base.metadata
        from database import Base

        # Force model imports so all tables are registered
        try:
            import models  # noqa: F401
            import project_models  # noqa: F401
        except ImportError:
            pass

        schema = {}
        for table_name, table in Base.metadata.tables.items():
            columns = {}
            for col in table.columns:
                # Normalize type names for comparison
                type_str = type(col.type).__name__.upper()
                columns[col.name] = type_str

            foreign_keys = []
            for fk in table.foreign_keys:
                ref_table, ref_col = fk.target_fullname.split(".")
                foreign_keys.append((fk.parent.name, ref_table, ref_col))

            indexes = []
            for idx in table.indexes:
                if idx.name:
                    indexes.append(idx.name)

            schema[table_name] = {
                "columns": columns,
                "indexes": indexes,
                "foreign_keys": foreign_keys,
            }

        return schema

    def validate(self) -> ValidationResult:
        """Validate database schema against SQLAlchemy models"""
        if self.mode == ValidationMode.DISABLED:
            logger.info("Schema validation is disabled")
            return ValidationResult(is_valid=True)

        if not self.engine or not self.inspector:
            logger.error("No database engine configured for validation")
            return ValidationResult(
                is_valid=False,
                errors=[ValidationError("", "configuration", "No database engine configured")],
            )

        result = ValidationResult(is_valid=True)

        try:
            expected_schema = self.get_expected_schema()
            actual_tables = set(self.inspector.get_table_names())

            # Check that all model tables exist in the database
            for table_name, table_spec in expected_schema.items():
                if table_name not in actual_tables:
                    result.add_error(
                        table_name,
                        "missing_table",
                        f"Table '{table_name}' defined in models but missing from database",
                    )
                    continue

                # Validate columns exist
                self._validate_columns(table_name, table_spec.get("columns", {}), result)

            # Extra tables in DB that aren't in models — just informational
            expected_tables = set(expected_schema.keys())
            extra_tables = actual_tables - expected_tables - self.IGNORED_TABLES
            if extra_tables:
                logger.debug(f"Tables in DB but not in models: {extra_tables}")

            # Handle validation mode
            if self.mode == ValidationMode.LENIENT and result.errors:
                logger.warning(
                    f"Schema validation found {len(result.errors)} errors in lenient mode"
                )
                result.warnings.extend(result.errors)
                result.errors = []
                result.is_valid = True

        except SQLAlchemyError as e:
            logger.error(f"Database error during schema validation: {e}")
            result.add_error("", "database_error", str(e))
        except Exception as e:
            logger.error(f"Unexpected error during schema validation: {e}")
            result.add_error("", "unexpected_error", str(e))

        return result

    def _validate_columns(
        self,
        table_name: str,
        expected_columns: Dict[str, str],
        result: ValidationResult,
    ):
        """Validate that all model columns exist in the database table"""
        try:
            actual_columns = {
                col["name"] for col in self.inspector.get_columns(table_name)
            }

            # Check for columns defined in models but missing from DB
            for col_name in expected_columns:
                if col_name not in actual_columns:
                    result.add_error(
                        table_name, "missing_column", f"Column '{col_name}' is missing from database"
                    )

            # Extra DB columns not in models — warning, not an error (migrations may add columns
            # that haven't been added to models yet, or columns from extensions)
            extra_columns = actual_columns - set(expected_columns.keys())
            if extra_columns:
                for col_name in sorted(extra_columns):
                    result.add_warning(
                        table_name, "extra_column", f"Column '{col_name}' exists in DB but not in models"
                    )
                logger.debug(f"{table_name}: extra DB columns not in models: {extra_columns}")

        except Exception as e:
            result.add_error(table_name, "column_validation_error", str(e))

    def check_type_consistency(self) -> ValidationResult:
        """Check for type consistency across foreign key relationships"""
        result = ValidationResult(is_valid=True)

        try:
            for table_name in self.inspector.get_table_names():
                if table_name in self.IGNORED_TABLES:
                    continue

                foreign_keys = self.inspector.get_foreign_keys(table_name)

                for fk in foreign_keys:
                    if not fk.get("constrained_columns") or not fk.get("referred_columns"):
                        continue

                    local_col = fk["constrained_columns"][0]
                    ref_table = fk["referred_table"]
                    ref_col = fk["referred_columns"][0]

                    local_columns = {
                        col["name"]: str(col["type"])
                        for col in self.inspector.get_columns(table_name)
                    }
                    ref_columns = {
                        col["name"]: str(col["type"])
                        for col in self.inspector.get_columns(ref_table)
                    }

                    local_type = local_columns.get(local_col, "UNKNOWN")
                    ref_type = ref_columns.get(ref_col, "UNKNOWN")

                    if local_type != ref_type and "UNKNOWN" not in [local_type, ref_type]:
                        result.add_error(
                            table_name,
                            "type_mismatch",
                            f"Type mismatch: {table_name}.{local_col} ({local_type}) -> {ref_table}.{ref_col} ({ref_type})",
                        )
        except Exception as e:
            result.add_error("", "type_consistency_check_error", str(e))

        return result

    def check_migration_history(self) -> ValidationResult:
        """Check alembic migration history for issues"""
        result = ValidationResult(is_valid=True)

        try:
            with self.engine.connect() as conn:
                if "alembic_version" not in self.inspector.get_table_names():
                    result.add_warning("", "migration_history", "No alembic_version table found")
                    return result

                current = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()

                if not current:
                    result.add_warning("", "migration_history", "No migration version recorded")
                elif len(current) > 1:
                    result.add_error(
                        "",
                        "migration_history",
                        f"Multiple migration heads detected: {[row[0] for row in current]}",
                    )
        except Exception as e:
            result.add_error("", "migration_history_check_error", str(e))

        return result


def create_validator_from_env(mode: Optional[str] = None) -> SchemaValidator:
    """Create a schema validator from environment configuration"""
    database_uri = os.getenv("DATABASE_URI") or os.getenv("DATABASE_URL")
    if not database_uri:
        logger.warning("No DATABASE_URI found in environment")
        return SchemaValidator(mode=ValidationMode.DISABLED)

    if mode:
        validation_mode = ValidationMode(mode.lower())
    else:
        mode_str = os.getenv("SCHEMA_VALIDATION_MODE", "strict").lower()
        validation_mode = ValidationMode(mode_str)

    try:
        engine = create_engine(database_uri)
        return SchemaValidator(engine, validation_mode)
    except Exception as e:
        logger.error(f"Failed to create schema validator: {e}")
        return SchemaValidator(mode=ValidationMode.DISABLED)
