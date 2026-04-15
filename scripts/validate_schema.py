#!/usr/bin/env python3
"""
Schema validation script to prevent future migration issues
Run this before deployments to ensure model-database consistency
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'api'))

from database import SessionLocal
from sqlalchemy import text, inspect
from models import Base
import argparse

def check_schema_consistency(verbose=False):
    """Check if database schema matches SQLAlchemy models"""
    
    db = SessionLocal()
    inspector = inspect(db.bind)
    
    # Get all model tables
    model_tables = {table.name: table for table in Base.metadata.tables.values()}
    db_tables = set(inspector.get_table_names())
    
    issues = []
    warnings = []
    
    # Check for missing tables
    for table_name in model_tables:
        if table_name in ['tasks_old', 'tags']:  # Known unused
            continue
        if table_name not in db_tables:
            issues.append(f"Table '{table_name}' exists in models but not in database")
    
    # Check for missing columns
    for table_name in model_tables:
        if table_name not in db_tables:
            continue
            
        model_cols = {col.name for col in model_tables[table_name].columns}
        db_cols = {col['name'] for col in inspector.get_columns(table_name)}
        
        missing_in_db = model_cols - db_cols
        extra_in_db = db_cols - model_cols
        
        for col in missing_in_db:
            issues.append(f"Column '{table_name}.{col}' exists in model but not in database")
        
        for col in extra_in_db:
            if col not in ['email_verified_at', 'verification_token']:  # Known legacy
                warnings.append(f"Column '{table_name}.{col}' exists in database but not in model")
    
    # Check alembic version
    result = db.execute(text("SELECT version_num FROM alembic_version"))
    current_version = result.scalar()
    
    # Check for merge-only migrations
    if current_version:
        try:
            migration_file = f"services/api/alembic/versions/{current_version}.py"
            if os.path.exists(migration_file):
                with open(migration_file, 'r') as f:
                    content = f.read()
                    if 'def upgrade()' in content and 'just merging' in content:
                        issues.append(f"Current migration '{current_version}' appears to be merge-only")
        except:
            pass
    
    db.close()
    
    # Report results
    if verbose:
        print("=" * 70)
        print("SCHEMA VALIDATION REPORT")
        print("=" * 70)
        print(f"\nCurrent migration: {current_version}")
        print(f"Model tables: {len(model_tables)}")
        print(f"Database tables: {len(db_tables)}")
        
        if issues:
            print(f"\n❌ CRITICAL ISSUES ({len(issues)}):")
            for issue in issues[:10]:
                print(f"  - {issue}")
            if len(issues) > 10:
                print(f"  ... and {len(issues) - 10} more")
        
        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for warning in warnings[:5]:
                print(f"  - {warning}")
            if len(warnings) > 5:
                print(f"  ... and {len(warnings) - 5} more")
        
        if not issues:
            print("\n✅ Schema validation PASSED")
        else:
            print("\n❌ Schema validation FAILED")
    
    return len(issues) == 0, issues, warnings


def check_migration_health():
    """Check for migration chain issues"""
    
    db = SessionLocal()
    
    # Check for multiple heads
    from alembic.config import Config
    from alembic import command
    from io import StringIO
    
    alembic_cfg = Config("services/api/alembic.ini")
    
    # Capture output
    output = StringIO()
    alembic_cfg.print_stdout = lambda *args: output.write(str(args[0]) + '\n')
    
    try:
        command.heads(alembic_cfg)
        heads_output = output.getvalue()
        head_count = heads_output.count('(head)')
        
        if head_count > 1:
            return False, f"Multiple migration heads detected ({head_count})"
        elif head_count == 0:
            return False, "No migration head found"
        else:
            return True, "Single migration head"
    except Exception as e:
        return False, f"Error checking migrations: {e}"
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Validate database schema against models')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--fix', action='store_true', help='Attempt to fix issues (not implemented)')
    parser.add_argument('--ci', action='store_true', help='CI mode - exit with error code if issues found')
    
    args = parser.parse_args()
    
    # Check schema
    schema_ok, issues, warnings = check_schema_consistency(args.verbose or not args.ci)
    
    # Check migrations
    migration_ok, migration_msg = check_migration_health()
    
    if args.ci:
        # CI mode - just exit with appropriate code
        if not schema_ok or not migration_ok:
            sys.exit(1)
        sys.exit(0)
    else:
        # Interactive mode
        if not args.verbose:
            if schema_ok and migration_ok:
                print("✅ Schema validation passed")
            else:
                print(f"❌ Schema validation failed: {len(issues)} issues")
                if not migration_ok:
                    print(f"❌ {migration_msg}")
        
        if args.fix:
            print("\n⚠️  Auto-fix not yet implemented")
            print("Run with --verbose to see specific issues")
    
    return 0 if (schema_ok and migration_ok) else 1


if __name__ == "__main__":
    sys.exit(main())