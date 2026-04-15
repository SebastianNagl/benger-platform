#!/usr/bin/env python3
"""
Generate proper baseline migration from actual model definitions.
This ensures the migration matches what SQLAlchemy models expect.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add API directory to path
api_dir = Path(__file__).parent.parent / "services" / "api"
sys.path.insert(0, str(api_dir))

def main():
    print("🔨 Generating Proper Baseline Migration")
    print("=" * 50)
    
    # Import after path setup
    from sqlalchemy import create_engine, MetaData
    from database import Base, engine
    
    # Get metadata from all models
    metadata = Base.metadata
    
    print(f"Found {len(metadata.tables)} tables to include in baseline")
    for table_name in sorted(metadata.tables.keys()):
        print(f"  - {table_name}")
    
    # Generate the migration content
    migration_content = f'''"""Baseline migration - complete schema from models

Revision ID: baseline_001
Revises: 
Create Date: {datetime.now().isoformat()}

Generated from actual SQLAlchemy models to ensure compatibility.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'baseline_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create all tables from SQLAlchemy models."""
    # Import Base to ensure all models are loaded
    import models
    from database import Base
    
    # Create all tables using SQLAlchemy metadata
    Base.metadata.create_all(op.get_bind())


def downgrade():
    """Drop all tables."""
    # Import Base to ensure all models are loaded  
    import models
    from database import Base
    
    # Drop all tables
    Base.metadata.drop_all(op.get_bind())
'''
    
    # Write the migration file
    versions_dir = api_dir / "alembic" / "versions"
    baseline_file = versions_dir / "baseline_001_complete_schema.py"
    
    baseline_file.write_text(migration_content)
    print(f"\n✅ Created proper baseline migration: {baseline_file}")
    
    print("\nNext steps:")
    print("1. Test the migration locally")
    print("2. Verify all tables are created correctly")
    print("3. Test demo user creation")

if __name__ == "__main__":
    main()