#!/usr/bin/env python3
"""
Setup demo organization and memberships for existing users
"""

import os
import sys
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Organization, OrganizationMembership, User


def setup_demo_organization():
    """Setup demo organization and add demo users to it"""
    db = SessionLocal()

    try:
        # Check environment
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment == "production":
            print("🔒 Production environment detected - skipping demo setup")
            return

        print("\n🏢 Setting up demo organization...")

        # Create or get TUM
        org = db.query(Organization).filter(Organization.name == "TUM").first()
        if not org:
            org = Organization(
                id=str(uuid.uuid4()),
                name="TUM",
                display_name="TUM",
                slug="tum",
                description="Default organization for development testing",
                is_active=True,
            )
            db.add(org)
            db.commit()
            print("✅ Created TUM")
        else:
            print("✅ TUM already exists")

        # Add demo users to organization
        demo_users = [
            ("admin", "ORG_ADMIN"),
            ("contributor", "CONTRIBUTOR"),
            ("annotator", "ANNOTATOR"),
        ]

        for username, role in demo_users:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                print(f"⚠️  User {username} not found")
                continue

            # Check if membership exists
            membership = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.organization_id == org.id,
                )
                .first()
            )

            if not membership:
                membership = OrganizationMembership(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    organization_id=org.id,
                    role=role,
                    is_active=True,
                )
                db.add(membership)
                db.commit()
                print(f"✅ Added {username} to TUM as {role}")
            else:
                print(f"✅ {username} already in TUM")

        print("\n🎉 Demo organization setup complete!")
        print("\nOrganization Members:")

        # List all members
        members = (
            db.query(User.username, OrganizationMembership.role)
            .join(OrganizationMembership, User.id == OrganizationMembership.user_id)
            .filter(OrganizationMembership.organization_id == org.id)
            .all()
        )

        for username, role in members:
            print(f"  - {username}: {role}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    setup_demo_organization()
