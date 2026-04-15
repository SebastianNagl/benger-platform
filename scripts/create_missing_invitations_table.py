#!/usr/bin/env python3
"""
Create missing invitations table in production
"""
import sys
sys.path.append('/app')
from sqlalchemy import create_engine, text
import os

DATABASE_URI = os.getenv('DATABASE_URI')
if not DATABASE_URI:
    print("❌ DATABASE_URI not found in environment")
    exit(1)

print(f'Using DATABASE_URI: {DATABASE_URI.replace(":IkTFjoYiF3", ":***")}')

engine = create_engine(DATABASE_URI)

try:
    with engine.connect() as conn:
        # Check if invitations table exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'invitations'
            )
        """))
        exists = result.scalar()
        
        if exists:
            print("ℹ️  invitations table already exists")
            exit(0)
        
        print("🔨 Creating invitations table...")
        
        # Create the invitations table with the same schema as migration 002
        conn.execute(text("""
            CREATE TABLE invitations (
                id VARCHAR PRIMARY KEY,
                organization_id VARCHAR NOT NULL REFERENCES organizations(id),
                email VARCHAR NOT NULL,
                role organizationrole NOT NULL,
                token VARCHAR NOT NULL UNIQUE,
                invited_by VARCHAR NOT NULL REFERENCES users(id),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                accepted_at TIMESTAMP WITH TIME ZONE,
                is_accepted BOOLEAN NOT NULL DEFAULT FALSE,
                CONSTRAINT unique_pending_invitation UNIQUE (organization_id, email, is_accepted)
            )
        """))
        
        # Create indexes
        conn.execute(text("CREATE INDEX ix_invitations_id ON invitations (id)"))
        conn.execute(text("CREATE INDEX ix_invitations_token ON invitations (token)"))
        conn.execute(text("CREATE INDEX ix_invitations_email ON invitations (email)"))
        conn.execute(text("CREATE INDEX ix_invitations_organization ON invitations (organization_id)"))
        
        print("✅ Created invitations table with indexes")
        
        conn.commit()
        print("✅ Invitations table setup complete")
        
        # Verify the table was created correctly
        result = conn.execute(text("SELECT COUNT(*) FROM invitations"))
        count = result.scalar()
        print(f"📊 Invitations table: {count} records")
        
        # Check table structure
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'invitations'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        print(f"📋 Table structure ({len(columns)} columns):")
        for col_name, data_type, is_nullable in columns:
            nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
            print(f"   - {col_name}: {data_type} {nullable}")
            
    print("\n" + "="*50)
    print("✅ INVITATIONS SYSTEM SETUP COMPLETE")
    print("   - invitations table: ✅")
    print("   - All indexes created: ✅")
    print("   - Foreign key constraints: ✅")
    print("="*50)
        
except Exception as e:
    print(f'❌ Error creating invitations table: {e}')
    raise

if __name__ == "__main__":
    pass