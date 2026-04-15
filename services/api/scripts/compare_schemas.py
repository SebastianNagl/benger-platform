#!/usr/bin/env python3
"""
Schema Comparison Tool

Compares database schema defined in models with migration results
to ensure consistency.
"""

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config


class SchemaComparator:
    """Compare schemas from different sources"""

    def __init__(self, models_path: str, migrations_path: str):
        """
        Initialize the schema comparator

        Args:
            models_path: Path to the models directory
            migrations_path: Path to the alembic migrations directory
        """
        self.models_path = Path(models_path)
        self.migrations_path = Path(migrations_path)
        self.differences = []

    def load_models_schema(self) -> Dict[str, Dict]:
        """Load schema from SQLAlchemy models"""
        schema = {}

        # Find all Python files in models directory
        model_files = list(self.models_path.rglob("*.py"))

        for model_file in model_files:
            if model_file.name.startswith("_"):
                continue

            # Dynamically import the module
            spec = importlib.util.spec_from_file_location(f"model_{model_file.stem}", model_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find SQLAlchemy models in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if hasattr(attr, "__tablename__") and hasattr(attr, "__table__"):
                        table_name = attr.__tablename__
                        schema[table_name] = {
                            "columns": {},
                            "indexes": [],
                            "foreign_keys": [],
                        }

                        # Extract column information
                        for column in attr.__table__.columns:
                            schema[table_name]["columns"][column.name] = {
                                "type": str(column.type),
                                "nullable": column.nullable,
                                "primary_key": column.primary_key,
                            }

                        # Extract indexes
                        for index in attr.__table__.indexes:
                            schema[table_name]["indexes"].append(index.name)

                        # Extract foreign keys
                        for fk in attr.__table__.foreign_keys:
                            schema[table_name]["foreign_keys"].append(
                                {
                                    "column": fk.parent.name,
                                    "references": f"{fk.column.table.name}.{fk.column.name}",
                                }
                            )

        return schema

    def apply_migrations_to_temp_db(self) -> Dict[str, Dict]:
        """Apply migrations to a temporary database and extract schema"""
        schema = {}

        # Create a temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            tmp_db_path = tmp_db.name

        try:
            # Configure Alembic
            alembic_cfg = Config()
            alembic_cfg.set_main_option("script_location", str(self.migrations_path.parent))
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_db_path}")

            # Run migrations
            command.upgrade(alembic_cfg, "head")

            # Connect to the database and extract schema
            engine = create_engine(f"sqlite:///{tmp_db_path}")
            inspector = inspect(engine)

            for table_name in inspector.get_table_names():
                if table_name == "alembic_version":
                    continue

                schema[table_name] = {"columns": {}, "indexes": [], "foreign_keys": []}

                # Get columns
                for column in inspector.get_columns(table_name):
                    schema[table_name]["columns"][column["name"]] = {
                        "type": str(column["type"]),
                        "nullable": column["nullable"],
                        "primary_key": column.get("primary_key", False),
                    }

                # Get indexes
                for index in inspector.get_indexes(table_name):
                    schema[table_name]["indexes"].append(index["name"])

                # Get foreign keys
                for fk in inspector.get_foreign_keys(table_name):
                    if fk["constrained_columns"] and fk["referred_columns"]:
                        schema[table_name]["foreign_keys"].append(
                            {
                                "column": fk["constrained_columns"][0],
                                "references": f"{fk['referred_table']}.{fk['referred_columns'][0]}",
                            }
                        )

            engine.dispose()

        finally:
            # Clean up temporary database
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)

        return schema

    def compare_schemas(self, schema1: Dict, schema2: Dict) -> List[str]:
        """
        Compare two schemas and return differences

        Args:
            schema1: First schema (e.g., from models)
            schema2: Second schema (e.g., from migrations)

        Returns:
            List of difference descriptions
        """
        differences = []

        # Check for missing tables
        tables1 = set(schema1.keys())
        tables2 = set(schema2.keys())

        missing_in_2 = tables1 - tables2
        missing_in_1 = tables2 - tables1

        for table in missing_in_2:
            differences.append(f"Table '{table}' exists in models but not in migrations")

        for table in missing_in_1:
            differences.append(f"Table '{table}' exists in migrations but not in models")

        # Check common tables
        common_tables = tables1 & tables2

        for table in common_tables:
            # Check columns
            cols1 = set(schema1[table]["columns"].keys())
            cols2 = set(schema2[table]["columns"].keys())

            missing_cols_in_2 = cols1 - cols2
            missing_cols_in_1 = cols2 - cols1

            for col in missing_cols_in_2:
                differences.append(f"Column '{table}.{col}' exists in models but not in migrations")

            for col in missing_cols_in_1:
                differences.append(f"Column '{table}.{col}' exists in migrations but not in models")

            # Check column properties for common columns
            common_cols = cols1 & cols2
            for col in common_cols:
                col1_info = schema1[table]["columns"][col]
                col2_info = schema2[table]["columns"][col]

                # Check nullability
                if col1_info.get("nullable") != col2_info.get("nullable"):
                    differences.append(
                        f"Column '{table}.{col}' nullable mismatch: "
                        f"models={col1_info.get('nullable')}, migrations={col2_info.get('nullable')}"
                    )

        return differences

    def run_comparison(self) -> bool:
        """
        Run the full schema comparison

        Returns:
            True if schemas match, False otherwise
        """
        print("📊 Loading schema from models...")
        try:
            models_schema = self.load_models_schema()
            print(f"  Found {len(models_schema)} tables in models")
        except Exception as e:
            print(f"❌ Failed to load models schema: {e}")
            return False

        print("🔄 Applying migrations to temporary database...")
        try:
            migration_schema = self.apply_migrations_to_temp_db()
            print(f"  Found {len(migration_schema)} tables after migrations")
        except Exception as e:
            print(f"❌ Failed to apply migrations: {e}")
            return False

        print("🔍 Comparing schemas...")
        self.differences = self.compare_schemas(models_schema, migration_schema)

        if not self.differences:
            print("✅ Schemas match perfectly!")
            return True
        else:
            print(f"❌ Found {len(self.differences)} differences:")
            for diff in self.differences:
                print(f"  - {diff}")
            return False


def main():
    """Main entry point for the schema comparison tool"""
    parser = argparse.ArgumentParser(
        description="Compare database schemas from models and migrations"
    )
    parser.add_argument(
        "--models",
        default="app/models",
        help="Path to the models directory (default: app/models)",
    )
    parser.add_argument(
        "--migrations",
        default="alembic/versions",
        help="Path to the migrations directory (default: alembic/versions)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code if differences are found",
    )

    args = parser.parse_args()

    # Validate paths
    models_path = Path(args.models)
    migrations_path = Path(args.migrations)

    if not models_path.exists():
        print(f"❌ Models path does not exist: {models_path}")
        sys.exit(2)

    if not migrations_path.exists():
        print(f"❌ Migrations path does not exist: {migrations_path}")
        sys.exit(2)

    # Run comparison
    comparator = SchemaComparator(args.models, args.migrations)
    schemas_match = comparator.run_comparison()

    # Exit with appropriate code
    if args.strict and not schemas_match:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
