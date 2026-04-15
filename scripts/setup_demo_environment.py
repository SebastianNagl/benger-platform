#!/usr/bin/env python3
"""
Comprehensive setup script for BenGER demo environment.
Initializes database with demo users, organizations, and feature flags.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

def setup_benger_demo():
    """Initialize BenGER with complete demo data."""
    
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment == "production":
        print("🔒 Production environment - skipping demo setup for security")
        return
    
    print("🚀 Setting up BenGER demo environment...")
    
    # Run migrations
    print("📦 Running database migrations...")
    result = subprocess.run([
        "docker", "exec", "infra-api-1",
        "alembic", "upgrade", "head"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Migration failed: {result.stderr}")
        return False
    
    print("✅ Migrations completed")
    
    # Initialize demo data via API container
    print("👥 Creating demo users and organizations...")
    
    init_script = """
from database import SessionLocal
from user_service import init_demo_users

db = SessionLocal()
try:
    init_demo_users(db)
    print("✅ Demo setup completed")
finally:
    db.close()
"""
    
    result = subprocess.run([
        "docker", "exec", "-i", "infra-api-1",
        "python", "-c", init_script
    ], capture_output=True, text=True)
    
    print(result.stdout)
    
    if result.returncode != 0:
        print(f"❌ Demo setup failed: {result.stderr}")
        return False
    
    print("""
🎉 BenGER Demo Environment Ready!

Demo Users:
- admin / admin (Superadmin)
- contributor / admin (Contributor role)
- annotator / admin (Annotator role)

Organization: TUM

Feature Flags (all enabled):
- data: Data Management
- generations: Generation features
- evaluations: Evaluation features
- reports: Reports page
- how-to: How-To documentation

Access the application at:
- Development: http://benger.localhost
- API: http://api.localhost
""")
    
    return True


if __name__ == "__main__":
    if not setup_benger_demo():
        sys.exit(1)
