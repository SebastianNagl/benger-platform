#!/bin/bash
# Create admin user on production

echo "👤 Creating admin user on production..."

kubectl exec -n benger deployment/benger-api -- python -c "
from database import get_db_sync
from models import User
from utils.auth_utils import get_password_hash

db = next(get_db_sync())

# Check if admin exists
admin = db.query(User).filter_by(username='admin').first()
if not admin:
    admin = User(
        username='admin',
        email='admin@benger.net',
        hashed_password=get_password_hash('admin'),
        is_superadmin=True,
        email_verified=True,
        profile_completed=True,
        is_active=True,
        name='Admin User'
    )
    db.add(admin)
    db.commit()
    print('✅ Admin user created successfully!')
else:
    print('ℹ️ Admin user already exists')
"

echo "✅ Done!"