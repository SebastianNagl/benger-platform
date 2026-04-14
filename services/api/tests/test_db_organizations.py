#!/usr/bin/env python3
"""
Direct database test to verify get_project_organizations function works
"""

import sys

# Add the API directory to the path so we can import modules
sys.path.append("/Users/sebastiannagl/Code/BenGer/services/api")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from projects_api import get_project_organizations

# Database connection using the same settings as the production environment
DATABASE_URL = "postgresql://postgres:changeme123!@localhost:5432/benger"


def test_project_organizations():
    try:
        # Create database connection
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        # Test project with multiple organizations
        project_id = "6be8474c-5e55-4e99-890a-a39ef9ebff50"

        print(f"Testing get_project_organizations for project: {project_id}")

        # Call our function
        organizations = get_project_organizations(db, project_id)

        print(f"✅ Function returned {len(organizations)} organizations:")

        for i, org in enumerate(organizations, 1):
            print(f"  {i}. {org['name']} (ID: {org['id']})")

        if len(organizations) >= 2:
            print(f"✅ SUCCESS: Multiple organizations detected!")

            # Verify expected organizations
            org_names = [org["name"] for org in organizations]
            if "TUM" in org_names and "Test Research Team" in org_names:
                print(f"✅ Both expected organizations found: TUM and Test Research Team")
            else:
                print(f"❌ Expected organizations not found. Got: {org_names}")
        else:
            print(f"❌ FAILURE: Only {len(organizations)} organization(s) found")

        db.close()

    except Exception as e:
        print(f"❌ Error testing database function: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_project_organizations()
