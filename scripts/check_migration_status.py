#!/usr/bin/env python3
"""
Check migration status in production
"""
import sys
sys.path.append('/app')
from alembic import script, environment
from alembic.config import Config
from alembic.runtime import migration
from sqlalchemy import create_engine
import os

# Initialize Alembic config
cfg = Config("alembic.ini")
script_dir = script.ScriptDirectory.from_config(cfg)

# Get script head
script_head = script_dir.get_current_head()
print(f"📋 Script head: {script_head}")

# Get all heads
all_heads = script_dir.get_heads()
print(f"📋 All script heads: {all_heads}")

# Connect to database and get current revision
DATABASE_URI = os.getenv('DATABASE_URI')
engine = create_engine(DATABASE_URI)

with engine.connect() as conn:
    context = migration.MigrationContext.configure(conn)
    current_db = context.get_current_revision()
    print(f"🗄️  Database current: {current_db}")
    
    # Check if up to date
    is_up_to_date = script_head == current_db
    print(f"✅ Up to date: {is_up_to_date}")
    
    if not is_up_to_date:
        print("\n⚠️  Database is NOT up to date!")
        print("Run 'alembic upgrade head' to apply pending migrations")
    else:
        print("\n✅ Database is up to date with script head")
        
    # Check if there are any untracked revisions
    try:
        # Get all revisions from head down
        revisions = list(script_dir.walk_revisions("head", "base"))
        print(f"\n📊 Total migrations in script: {len(revisions)}")
        
        # Check which revisions are applied
        applied_revisions = []
        # This is a simplified check - in practice Alembic tracks this in alembic_version table
        result = conn.execute("SELECT version_num FROM alembic_version")
        for row in result:
            applied_revisions.append(row[0])
            
        print(f"📊 Applied revisions: {applied_revisions}")
        
    except Exception as e:
        print(f"❌ Error checking revision details: {e}")

print("\n" + "="*50)
print("RECOMMENDATION:")
if not is_up_to_date:
    print("🔧 Run: alembic upgrade head")
else:
    print("✅ No action needed - database is current")
print("="*50)