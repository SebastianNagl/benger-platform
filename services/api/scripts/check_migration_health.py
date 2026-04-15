#!/usr/bin/env python3
"""
Migration Health Check Script

Validates the health of database migrations including:
- No broken migration chains
- No empty merge migrations
- No duplicate revisions
- Proper naming conventions
"""

import re
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class MigrationHealthChecker:
    """Check the health of database migrations"""

    def __init__(self, migrations_dir: str = "alembic"):
        """Initialize the migration health checker"""
        self.migrations_dir = Path(migrations_dir)
        self.issues = []
        self.warnings = []

        # Configure Alembic
        self.config = Config()
        self.config.set_main_option("script_location", str(self.migrations_dir))

        try:
            self.script_dir = ScriptDirectory.from_config(self.config)
        except Exception as e:
            self.issues.append(f"Failed to load migrations: {e}")
            self.script_dir = None

    def check_migration_chain(self) -> bool:
        """Check if the migration chain is intact"""
        if not self.script_dir:
            return False

        try:
            # Get all revisions
            revisions = list(self.script_dir.walk_revisions())

            # Check for multiple heads
            heads = self.script_dir.get_heads()
            if len(heads) > 1:
                self.issues.append(f"Multiple migration heads detected: {heads}")
                self.issues.append("Run 'alembic merge' to create a merge migration")
                return False

            # Check for broken chains
            for revision in revisions:
                if revision.down_revision:
                    # Handle both single and multiple down revisions (merge migrations)
                    down_revs = (
                        revision.down_revision
                        if isinstance(revision.down_revision, tuple)
                        else (revision.down_revision,)
                    )

                    for down_rev in down_revs:
                        if down_rev and down_rev != "None":
                            # Check if down revision exists
                            try:
                                self.script_dir.get_revision(down_rev)
                            except Exception:
                                self.issues.append(
                                    f"Migration {revision.revision} references non-existent parent {down_rev}"
                                )
                                return False

            return True

        except Exception as e:
            self.issues.append(f"Error checking migration chain: {e}")
            return False

    def check_empty_merge_migrations(self) -> bool:
        """Check for empty merge migrations"""
        if not self.script_dir:
            return False

        has_empty_merges = False

        for revision in self.script_dir.walk_revisions():
            # Check if this is a merge migration
            if revision.branch_labels or (
                revision.down_revision and "," in str(revision.down_revision)
            ):
                # Read the migration file
                migration_file = Path(revision.path)
                if migration_file.exists():
                    content = migration_file.read_text()

                    # Extract upgrade function
                    upgrade_match = re.search(
                        r"def upgrade\(\)[^:]*:\s*(.*?)(?=def downgrade|$)",
                        content,
                        re.DOTALL,
                    )

                    if upgrade_match:
                        upgrade_body = upgrade_match.group(1).strip()

                        # Check if it's essentially empty
                        meaningful_lines = [
                            line.strip()
                            for line in upgrade_body.split("\n")
                            if line.strip()
                            and not line.strip().startswith("#")
                            and not line.strip().startswith('"""')
                            and line.strip() not in ["pass", '"""', "'''"]
                        ]

                        if len(meaningful_lines) < 2:
                            self.issues.append(
                                f"Merge migration {revision.revision} ({migration_file.name}) "
                                f"has empty or nearly empty upgrade() function"
                            )
                            has_empty_merges = True

        return not has_empty_merges

    def check_duplicate_revisions(self) -> bool:
        """Check for duplicate revision IDs"""
        if not self.script_dir:
            return False

        revisions = {}
        has_duplicates = False

        migrations_path = self.migrations_dir / "versions"
        if migrations_path.exists():
            for migration_file in migrations_path.glob("*.py"):
                if migration_file.name.startswith("_"):
                    continue

                content = migration_file.read_text()

                # Extract revision ID
                revision_match = re.search(r'revision[:\s]*=\s*["\']([^"\']+)["\']', content)
                if revision_match:
                    revision_id = revision_match.group(1)

                    if revision_id in revisions:
                        self.issues.append(
                            f"Duplicate revision ID {revision_id} found in "
                            f"{migration_file.name} and {revisions[revision_id]}"
                        )
                        has_duplicates = True
                    else:
                        revisions[revision_id] = migration_file.name

        return not has_duplicates

    def check_naming_conventions(self) -> bool:
        """Check migration naming conventions"""
        migrations_path = self.migrations_dir / "versions"
        if not migrations_path.exists():
            return True

        has_issues = False

        for migration_file in migrations_path.glob("*.py"):
            if migration_file.name.startswith("_"):
                continue

            filename = migration_file.stem

            # Check for meaningful names
            if len(filename) < 10:
                self.warnings.append(f"Migration {filename} has a very short name")

            # Check for descriptive names (should contain underscores or be descriptive)
            if "_" not in filename and not any(c.isupper() for c in filename[1:]):
                self.warnings.append(
                    f"Migration {filename} should have a more descriptive name "
                    f"(e.g., add_user_table, fix_foreign_keys)"
                )

        return not has_issues

    def check_migration_imports(self) -> bool:
        """Check that migrations have required imports"""
        migrations_path = self.migrations_dir / "versions"
        if not migrations_path.exists():
            return True

        required_imports = ["from alembic import op", "import sqlalchemy as sa"]

        has_issues = False

        for migration_file in migrations_path.glob("*.py"):
            if migration_file.name.startswith("_"):
                continue

            content = migration_file.read_text()

            for required_import in required_imports:
                if required_import not in content:
                    self.issues.append(
                        f"Migration {migration_file.name} missing required import: {required_import}"
                    )
                    has_issues = True

        return not has_issues

    def run_all_checks(self) -> bool:
        """Run all health checks"""
        print("🔍 Checking migration health...")

        checks = [
            ("Migration chain integrity", self.check_migration_chain),
            ("No empty merge migrations", self.check_empty_merge_migrations),
            ("No duplicate revisions", self.check_duplicate_revisions),
            ("Proper naming conventions", self.check_naming_conventions),
            ("Required imports present", self.check_migration_imports),
        ]

        all_passed = True

        for check_name, check_func in checks:
            try:
                passed = check_func()
                status = "✅" if passed else "❌"
                print(f"  {status} {check_name}")

                if not passed:
                    all_passed = False
            except Exception as e:
                print(f"  ❌ {check_name}: {e}")
                all_passed = False

        # Print issues
        if self.issues:
            print("\n❌ Critical Issues Found:")
            for issue in self.issues:
                print(f"  - {issue}")

        # Print warnings
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if all_passed and not self.issues:
            print("\n✅ All migration health checks passed!")
            return True
        else:
            print("\n❌ Migration health checks failed!")
            return False


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Check database migration health")
    parser.add_argument(
        "--migrations-dir",
        default="alembic",
        help="Path to the Alembic migrations directory (default: alembic)",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")

    args = parser.parse_args()

    # Run health checks
    checker = MigrationHealthChecker(args.migrations_dir)
    passed = checker.run_all_checks()

    # In strict mode, warnings also cause failure
    if args.strict and checker.warnings:
        passed = False

    # Exit with appropriate code
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
