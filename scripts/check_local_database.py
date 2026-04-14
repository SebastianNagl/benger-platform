#!/usr/bin/env python3
"""
Check local database schema for feature flag tables
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'services', 'api'))

from sqlalchemy import create_engine, inspect, text

# Get local database URL
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URI")
if not DATABASE_URL:
    # Use default local development values
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "benger_dev")
    DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

def get_table_schema(engine, table_name):
    """Get detailed schema information for a table"""
    inspector = inspect(engine)
    
    if table_name not in inspector.get_table_names():
        return None
        
    columns = inspector.get_columns(table_name)
    indexes = inspector.get_indexes(table_name)
    foreign_keys = inspector.get_foreign_keys(table_name)
    
    return {
        'columns': columns,
        'indexes': indexes,
        'foreign_keys': foreign_keys
    }

def main():
    print("🔍 Local Database Schema Check")
    print("=" * 50)
    
    # Connect to local database
    print(f"\n📱 Connecting to local database...")
    print(f"   URL: {DATABASE_URL.split('@')[0]}@***")
    
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print("✅ Connected successfully")
        
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    # Check feature flag tables
    feature_flag_tables = ['feature_flags', 'user_feature_flags', 'organization_feature_flags']
    
    print(f"\n🚩 Feature Flag Tables:")
    for table_name in feature_flag_tables:
        schema = get_table_schema(engine, table_name)
        
        if schema is None:
            print(f"❌ {table_name}: MISSING")
        else:
            print(f"✅ {table_name}: EXISTS")
            print(f"   📋 Columns ({len(schema['columns'])}):")
            for col in schema['columns']:
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                pk = "PK" if col.get('primary_key') else ""
                print(f"      - {col['name']}: {col['type']} {nullable} {pk}")
            
            if schema['indexes']:
                print(f"   📇 Indexes ({len(schema['indexes'])}):")
                for idx in schema['indexes']:
                    unique = "UNIQUE" if idx['unique'] else ""
                    print(f"      - {idx['name']}: {idx['column_names']} {unique}")
            
            if schema['foreign_keys']:
                print(f"   🔗 Foreign Keys ({len(schema['foreign_keys'])}):")
                for fk in schema['foreign_keys']:
                    print(f"      - {fk['name']}: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
            
            # Check data
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                print(f"   📊 Records: {count}")
                
                if table_name == 'feature_flags' and count > 0:
                    result = conn.execute(text("SELECT name, is_enabled FROM feature_flags"))
                    flags = result.fetchall()
                    for name, enabled in flags:
                        print(f"      - {name}: {'enabled' if enabled else 'disabled'}")
        
        print()
    
    # Check migration status
    print("🗂️  Migration Status:")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            print(f"   Current version: {version}")
    except Exception as e:
        print(f"   ❌ Could not check migration status: {e}")
    
    print("=" * 50)
    print("📊 SUMMARY:")
    print("Local database schema checked")
    print("Use this to compare with production configuration")
    print("=" * 50)

if __name__ == "__main__":
    main()