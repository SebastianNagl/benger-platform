#!/usr/bin/env python3
"""
Seed verified load-test users for locust runs.

Creates N users (default 1000) that are:
- email-verified (method 'system', no mail is ever sent)
- active, profile complete, password set
- ANNOTATOR members of the TUM org (created if missing)
- uniformly prefixed (default 'loadtest_') so they can be cleaned up later

All users share ONE password (bcrypt hashing 1000 distinct passwords would
take minutes; one hash re-used across rows verifies identically). The
credentials are written as CSV to --out for locust to consume.

Usage (inside the api container):
    python scripts/seed_load_test_users.py --count 1000 --password 'S3cret!' --out /tmp/loadtest_users.csv
    python scripts/seed_load_test_users.py --cleanup
"""

import argparse
import csv
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone

_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in ("/shared", os.path.join(_api_dir, "..", "shared"), _api_dir):
    if os.path.isdir(_p):
        sys.path.insert(0, os.path.abspath(_p))

from auth_module.user_service import get_password_hash  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)

DEFAULT_PREFIX = "loadtest_"
ORG_SLUG = "tum"


def get_or_create_tum(db):
    org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
    if org is None:
        org = Organization(
            id=str(uuid.uuid4()),
            name="TUM",
            display_name="TUM",
            slug=ORG_SLUG,
            description="TUM organization",
            is_active=True,
        )
        db.add(org)
        db.commit()
        print(f"Created org '{ORG_SLUG}' ({org.id})")
    return org


def seed(db, count: int, prefix: str, password: str, out_path: str):
    org = get_or_create_tum(db)
    hashed = get_password_hash(password)
    now = datetime.now(timezone.utc)

    existing = {
        u.username: u.id
        for u in db.query(User.username, User.id).filter(User.username.like(f"{prefix}%"))
    }
    member_ids = {
        m.user_id
        for m in db.query(OrganizationMembership.user_id).filter(
            OrganizationMembership.organization_id == org.id
        )
    }

    rows = []
    created = skipped = 0
    for i in range(1, count + 1):
        username = f"{prefix}{i:04d}"
        email = f"{username}@loadtest.invalid"
        rows.append((username, email, password))

        if username in existing:
            user_id = existing[username]
            skipped += 1
        else:
            user_id = str(uuid.uuid4())
            db.add(
                User(
                    id=user_id,
                    username=username,
                    email=email,
                    name=f"Load Test {i:04d}",
                    hashed_password=hashed,
                    password_set=True,
                    email_verified=True,
                    email_verified_at=now,
                    email_verification_method="system",
                    profile_completed=True,
                    is_active=True,
                    pseudonym=f"{prefix}pseudonym-{i:04d}",
                    use_pseudonym=True,
                )
            )
            created += 1

        if user_id not in member_ids:
            db.add(
                OrganizationMembership(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    organization_id=org.id,
                    role=OrganizationRole.ANNOTATOR,
                    is_active=True,
                )
            )

        if i % 200 == 0:
            db.commit()
            print(f"  ... {i}/{count}")
    db.commit()

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "email", "password"])
        writer.writerows(rows)

    print(f"Done: {created} created, {skipped} already existed (kept).")
    print(f"Credentials CSV: {out_path}")


def cleanup(db, prefix: str):
    users = db.query(User).filter(User.username.like(f"{prefix}%")).all()
    if not users:
        print(f"No users matching '{prefix}%' found.")
        return
    user_ids = [u.id for u in users]
    n_mem = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id.in_(user_ids))
        .delete(synchronize_session=False)
    )
    n_usr = db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
    print(f"Deleted {n_usr} users and {n_mem} memberships.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--password", default=None, help="Shared password (generated if omitted)")
    parser.add_argument("--out", default="/tmp/loadtest_users.csv")
    parser.add_argument("--cleanup", action="store_true", help="Delete all users with the prefix")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.cleanup:
            cleanup(db, args.prefix)
        else:
            password = args.password or secrets.token_urlsafe(12)
            if args.password is None:
                print(f"Generated shared password: {password}")
            seed(db, args.count, args.prefix, password, args.out)
    finally:
        db.close()


if __name__ == "__main__":
    main()
