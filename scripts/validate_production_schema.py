#!/usr/bin/env python3
"""
Validate that production database schema matches the expected models
"""
import sys
sys.path.append('/app')
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
import os

# Import our models
from models import (
    User, Organization, Task, FeatureFlag, 
    UserFeatureFlag, OrganizationFeatureFlag
)

DATABASE_URI = os.getenv('DATABASE_URI')
engine = create_engine(DATABASE_URI)
inspector = inspect(engine)

def check_table_exists(table_name):
    """Check if a table exists"""
    exists = table_name in inspector.get_table_names()
    print(f"{'✅' if exists else '❌'} Table '{table_name}': {'exists' if exists else 'MISSING'}")
    return exists

def check_table_columns(table_name, expected_columns):
    """Check if table has expected columns with correct types"""
    if not check_table_exists(table_name):
        return False
        
    actual_columns = {col['name']: str(col['type']) for col in inspector.get_columns(table_name)}
    print(f"\n📋 Checking columns for '{table_name}':")
    
    all_good = True
    for col_name, expected_type in expected_columns.items():
        if col_name in actual_columns:
            actual_type = actual_columns[col_name]
            # Simplified type checking - just check if types are compatible
            if expected_type.lower() in actual_type.lower() or actual_type.lower() in expected_type.lower():
                print(f"   ✅ {col_name}: {actual_type}")
            else:
                print(f"   ⚠️  {col_name}: {actual_type} (expected {expected_type})")
                all_good = False
        else:
            print(f"   ❌ {col_name}: MISSING (expected {expected_type})")
            all_good = False
    
    # Check for unexpected columns
    for col_name in actual_columns:
        if col_name not in expected_columns:
            print(f"   ⚠️  {col_name}: UNEXPECTED ({actual_columns[col_name]})")
    
    return all_good

def main():
    print("🔍 Production Database Schema Validation")
    print("=" * 50)
    
    # Check core tables
    core_tables = ['users', 'organizations', 'tasks', 'projects']
    print("\n📊 Core Tables:")
    for table in core_tables:
        check_table_exists(table)
    
    # Check feature flag system
    print("\n🚩 Feature Flag System:")
    
    # Feature flags table
    feature_flags_columns = {
        'id': 'VARCHAR',
        'name': 'VARCHAR',
        'description': 'TEXT',
        'is_enabled': 'BOOLEAN',
        'target_criteria': 'JSON',
        'rollout_percentage': 'INTEGER',
        'created_by': 'VARCHAR',
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP'
    }
    
    ff_ok = check_table_columns('feature_flags', feature_flags_columns)
    
    # User feature flags table
    user_ff_columns = {
        'id': 'VARCHAR',
        'user_id': 'VARCHAR',
        'feature_flag_id': 'VARCHAR',
        'is_enabled': 'BOOLEAN',
        'created_by': 'VARCHAR',
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP'
    }
    
    user_ff_ok = check_table_columns('user_feature_flags', user_ff_columns)
    
    # Organization feature flags table
    org_ff_columns = {
        'id': 'VARCHAR',
        'organization_id': 'VARCHAR',
        'feature_flag_id': 'VARCHAR',
        'is_enabled': 'BOOLEAN',
        'created_by': 'VARCHAR',
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP'
    }
    
    org_ff_ok = check_table_columns('organization_feature_flags', org_ff_columns)
    
    # Check data integrity
    print("\n🔍 Data Integrity Checks:")
    
    with engine.connect() as conn:
        # Check feature flags count
        result = conn.execute(text("SELECT COUNT(*) FROM feature_flags"))
        ff_count = result.scalar()
        print(f"✅ Feature flags count: {ff_count}")
        
        if ff_count > 0:
            result = conn.execute(text("SELECT name, is_enabled FROM feature_flags"))
            flags = result.fetchall()
            for name, enabled in flags:
                print(f"   - {name}: {'✅ enabled' if enabled else '❌ disabled'}")
        
        # Check for orphaned records
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM user_feature_flags uff 
                LEFT JOIN feature_flags ff ON uff.feature_flag_id = ff.id 
                WHERE ff.id IS NULL
            """))
            orphaned_user_flags = result.scalar()
            print(f"{'✅' if orphaned_user_flags == 0 else '⚠️ '} Orphaned user feature flags: {orphaned_user_flags}")
            
            result = conn.execute(text("""
                SELECT COUNT(*) FROM organization_feature_flags off 
                LEFT JOIN feature_flags ff ON off.feature_flag_id = ff.id 
                WHERE ff.id IS NULL
            """))
            orphaned_org_flags = result.scalar()
            print(f"{'✅' if orphaned_org_flags == 0 else '⚠️ '} Orphaned org feature flags: {orphaned_org_flags}")
            
        except Exception as e:
            print(f"⚠️  Could not check orphaned records: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY:")
    
    if ff_ok and user_ff_ok and org_ff_ok:
        print("✅ Feature flag system schema is CORRECT")
        print("✅ Production database is ready for use")
    else:
        print("❌ Schema issues detected")
        print("🔧 Manual fixes may be required")
    
    print("=" * 50)

if __name__ == "__main__":
    main()