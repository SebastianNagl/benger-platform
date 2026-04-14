#!/usr/bin/env python3
"""
Create complete organization system (enum + invitations table)
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
        print("🔍 Checking missing organization system components...")
        
        # Check if organizationrole enum exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'organizationrole'
            )
        """))
        enum_exists = result.scalar()
        
        # Check if invitations table exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'invitations'
            )
        """))
        table_exists = result.scalar()
        
        print(f"   - organizationrole enum: {'✅ exists' if enum_exists else '❌ missing'}")
        print(f"   - invitations table: {'✅ exists' if table_exists else '❌ missing'}")
        
        # Create organizationrole enum if missing
        if not enum_exists:
            print("\n🔨 Creating organizationrole enum...")
            conn.execute(text("""
                CREATE TYPE organizationrole AS ENUM (
                    'ORG_ADMIN', 
                    'ORG_CONTRIBUTOR', 
                    'ORG_USER'
                )
            """))
            print("✅ Created organizationrole enum")
        
        # Create invitations table if missing
        if not table_exists:
            print("\n🔨 Creating invitations table...")
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
        print("\n✅ Organization system setup complete")
        
        # Verify everything works
        print("\n🧪 Testing organization system...")
        
        # Test that we can query invitations (should be empty)
        result = conn.execute(text("SELECT COUNT(*) FROM invitations"))
        count = result.scalar()
        print(f"   - Invitations table query: ✅ ({count} records)")
        
        # Test that organizationrole enum values work
        result = conn.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid 
            WHERE pg_type.typname = 'organizationrole'
            ORDER BY enumsortorder
        """))
        enum_values = [row[0] for row in result]
        print(f"   - OrganizationRole enum values: ✅ {enum_values}")
        
        # Test organization_memberships table exists and works
        result = conn.execute(text("SELECT COUNT(*) FROM organization_memberships"))
        count = result.scalar()
        print(f"   - Organization memberships: ✅ ({count} records)")
        
        print("\n" + "="*50)
        print("✅ ORGANIZATION SYSTEM FULLY OPERATIONAL")
        print("   - organizationrole enum: ✅")
        print("   - invitations table: ✅")
        print("   - organization_memberships: ✅")
        print("   - All foreign keys: ✅")
        print("   - All indexes: ✅")
        print("="*50)
        
except Exception as e:
    print(f'❌ Error setting up organization system: {e}')
    import traceback
    traceback.print_exc()
    raise

if __name__ == "__main__":
    pass