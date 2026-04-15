#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Migration Utilities for BenGER

This module provides utilities for managing database migrations across different environments.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth_module import initialize_database  # noqa: E402
from database import DATABASE_URL, initialize_task_types_and_evaluation_types  # noqa: E402
from models import Base  # noqa: E402

load_dotenv()


class MigrationManager:
    """Manages database migrations for BenGER"""

    def __init__(self):
        self.database_url = DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            connect_args=({"check_same_thread": False} if "sqlite" in self.database_url else {}),
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Configure Alembic
        self.alembic_cfg = Config("alembic.ini")
        self.alembic_cfg.set_main_option("sqlalchemy.url", self.database_url)

    def create_tables(self):
        """
        DEPRECATED: Use run_migrations() instead
        Database schema should be managed via Alembic migrations only
        """
        raise DeprecationWarning(
            "create_tables() is deprecated. Use run_migrations() to manage database schema via Alembic. "
            "This ensures proper schema versioning and migration tracking."
        )

    def initialize_data(self):
        """Initialize database with default data"""
        print("Initializing database with default data...")
        db = self.SessionLocal()
        try:
            # Initialize demo users
            initialize_database(db)
            print("✅ Demo users initialized")

            # Initialize task types and evaluation types
            initialize_task_types_and_evaluation_types(db)
            print("✅ Task types and evaluation types initialized")

        except Exception as e:
            print(f"❌ Error initializing data: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def run_migrations(self):
        """Run all pending migrations"""
        print("Running database migrations...")
        try:
            command.upgrade(self.alembic_cfg, "head")
            print("✅ Migrations completed successfully")
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise

    def create_migration(self, message: str):
        """Create a new migration"""
        print(f"Creating migration: {message}")
        try:
            command.revision(self.alembic_cfg, autogenerate=True, message=message)
            print("✅ Migration created successfully")
        except Exception as e:
            print(f"❌ Failed to create migration: {e}")
            raise

    def migration_status(self):
        """Show current migration status"""
        print("Current migration status:")
        try:
            command.current(self.alembic_cfg)
            print("\nMigration history:")
            command.history(self.alembic_cfg)
        except Exception as e:
            print(f"❌ Failed to get migration status: {e}")
            raise

    def reset_database(self):
        """Reset database using Alembic (WARNING: This will delete all data!)"""
        print("⚠️  WARNING: This will delete all data!")
        confirm = input("Are you sure you want to reset the database? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Database reset cancelled")
            return

        print("Rolling back all migrations...")
        try:
            # Downgrade to base (removes all tables)
            command.downgrade(self.alembic_cfg, "base")
            print("✅ All migrations rolled back")
        except Exception as e:
            print(f"⚠️ Downgrade failed, forcing clean slate: {e}")
            # If downgrade fails, drop all tables manually as last resort
            Base.metadata.drop_all(bind=self.engine)
            print("✅ All tables dropped (forced)")

        # Run all migrations from scratch
        print("Running migrations from base...")
        self.run_migrations()

        # Initialize data
        self.initialize_data()

        print("✅ Database reset completed")

    def backup_database(self, backup_path: str = None):
        """Backup database (SQLite only)"""
        if "sqlite" not in self.database_url:
            print("❌ Backup only supported for SQLite databases")
            return

        if not backup_path:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"benger_backup_{timestamp}.db"

        # Extract database file path from URL
        db_file = self.database_url.replace("sqlite:///", "").replace("sqlite://", "")

        if os.path.exists(db_file):
            import shutil

            shutil.copy2(db_file, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
        else:
            print(f"❌ Database file not found: {db_file}")


def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description="BenGER Database Migration Utilities")
    parser.add_argument(
        "command",
        choices=["init", "migrate", "create", "status", "reset", "backup"],
        help="Command to execute",
    )
    parser.add_argument("-m", "--message", help="Migration message (for create command)")
    parser.add_argument("-b", "--backup-path", help="Backup file path (for backup command)")

    args = parser.parse_args()

    manager = MigrationManager()

    try:
        if args.command == "init":
            print("🚀 Initializing database...")
            manager.create_tables()
            manager.initialize_data()
            print("✅ Database initialization completed!")

        elif args.command == "migrate":
            print("🔄 Running migrations...")
            manager.run_migrations()

        elif args.command == "create":
            if not args.message:
                print("❌ Migration message is required. Use -m 'Your message'")
                sys.exit(1)
            manager.create_migration(args.message)

        elif args.command == "status":
            manager.migration_status()

        elif args.command == "reset":
            manager.reset_database()

        elif args.command == "backup":
            manager.backup_database(args.backup_path)

    except Exception as e:
        print(f"❌ Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
