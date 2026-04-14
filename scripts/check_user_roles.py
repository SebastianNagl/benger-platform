#!/usr/bin/env python3
"""
Check available user roles in the database
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
        # Check what roles exist
        print("📊 Checking available user roles...")
        result = conn.execute(text("SELECT DISTINCT role FROM users"))
        roles = [row[0] for row in result]
        print(f"Available roles: {roles}")
        
        # Check enum values if role is an enum
        try:
            result = conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                JOIN pg_type ON pg_enum.enumtypid = pg_type.oid 
                WHERE pg_type.typname = 'userrole'
            """))
            enum_values = [row[0] for row in result]
            print(f"UserRole enum values: {enum_values}")
        except Exception as e:
            print(f"Could not get enum values: {e}")
        
        # Find any admin-like users
        result = conn.execute(text("SELECT id, email, role FROM users LIMIT 10"))
        users = result.fetchall()
        print(f"\n📋 Sample users:")
        for user_id, email, role in users:
            print(f"   - {email}: {role}")
            
        # Look for any user that might be an admin
        result = conn.execute(text("SELECT id, email, role FROM users WHERE role LIKE '%admin%' OR email LIKE '%admin%'"))
        admin_users = result.fetchall()
        if admin_users:
            print(f"\n👤 Admin-like users:")
            for user_id, email, role in admin_users:
                print(f"   - {email}: {role} (id: {user_id})")
        
except Exception as e:
    print(f'❌ Error checking roles: {e}')
    raise