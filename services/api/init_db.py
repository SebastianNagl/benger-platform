#!/usr/bin/env python3
"""
Database initialization script
Run this to create tables and insert demo users
"""

import sys

from database import SessionLocal, init_db
from user_service import init_demo_users


def main():
    """Initialize database with tables and demo users"""
    print("🚀 Initializing BenGER database...")

    try:
        # Create tables
        print("📋 Creating database tables...")
        init_db()
        print("✅ Tables created successfully!")

        # Create demo users
        print("👥 Creating demo users...")
        db = SessionLocal()
        try:
            init_demo_users(db)
            print("✅ Demo users created successfully!")
        finally:
            db.close()

        print("🎉 Database initialization complete!")
        print("📝 Demo users:")
        print("   - Username: admin | Password: admin (Superadmin)")
        print("   - Username: contributor | Password: admin (Contributor)")
        print("   - Username: annotator | Password: admin (Annotator)")

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
