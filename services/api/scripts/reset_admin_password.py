#!/usr/bin/env python3
"""
Reset admin user password to 'admin' for development environment
"""

import sys

from auth_module.user_service import get_password_hash
from database import SessionLocal
from models import User


def reset_admin_password():
    """Reset admin user password to 'admin'"""
    db = SessionLocal()
    try:
        # Get admin user
        admin_user = db.query(User).filter(User.username == "admin").first()

        if not admin_user:
            print("❌ Admin user not found!")
            return False

        print(f"Found admin user: {admin_user.username} ({admin_user.email})")

        # Reset password to 'admin'
        new_password = "admin"
        admin_user.hashed_password = get_password_hash(new_password)

        # Also ensure the user is active and email is verified
        admin_user.is_active = True
        admin_user.email_verified = True
        admin_user.is_superadmin = True

        db.commit()
        print(f"✅ Admin password reset to: {new_password}")
        print("✅ Admin user is now active, email verified, and superadmin")

        # Verify the change
        from auth_module.user_service import authenticate_user

        result = authenticate_user(db, "admin", "admin")
        if result:
            print("✅ Authentication test successful!")
        else:
            print("❌ Authentication test failed!")

        return True

    except Exception as e:
        print(f"❌ Error resetting admin password: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = reset_admin_password()
    sys.exit(0 if success else 1)
