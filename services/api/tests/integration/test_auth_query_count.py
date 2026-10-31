"""SQL cost of authenticating one request (audit E2).

``db_user_to_user`` used to iterate the lazy ``organization_memberships``
collection and then each lazy ``membership.organization``: 2 + K statements
per request for a user with K memberships. The user lookup now issues
exactly two statements (the user, then all memberships with their
organizations joined), lists only ACTIVE memberships, and ends the
transaction it opened so the pooled sync connection does not sit idle in
transaction for the rest of an async-lane request.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from auth_module import create_access_token
from auth_module.dependencies import require_user
from database import get_db
from models import Organization, OrganizationMembership, OrganizationRole, User

_NON_QUERY_PREFIXES = ("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")


def _make_user_with_memberships(db, *, active, inactive):
    user = User(
        id=f"authcount-{uuid.uuid4()}",
        username=f"authcount-{uuid.uuid4().hex[:8]}",
        email=f"authcount-{uuid.uuid4().hex[:8]}@test.com",
        name="Auth Count",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    active_ids = []
    for i in range(active + inactive):
        org = Organization(
            id=str(uuid.uuid4()),
            name=f"Auth Count Org {i}",
            slug=f"auth-count-{uuid.uuid4().hex[:10]}",
            display_name=f"Auth Count Org {i}",
        )
        db.add(org)
        db.flush()
        is_active = i < active
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.ANNOTATOR,
                is_active=is_active,
            )
        )
        if is_active:
            active_ids.append(org.id)
    user_id = user.id
    db.commit()
    # Plain values only: touching the expired ORM row would open a new
    # transaction, and a real request starts with a fresh, idle session.
    return user_id, active_ids


def _probe_app(test_db, *, touch_db_first=False):
    app = FastAPI()

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    def touch(db=Depends(get_db)):
        if touch_db_first:
            db.execute(text("SELECT 1"))

    @app.get("/probe")
    def probe(_touched=Depends(touch), current_user=Depends(require_user)):
        return {"organizations": current_user.organizations or []}

    return app


class _StatementCounter:
    def __init__(self, engine):
        self.engine = engine
        self.statements = []

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        if not statement.lstrip().upper().startswith(_NON_QUERY_PREFIXES):
            self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)


@pytest.mark.parametrize("memberships", [1, 4])
def test_authenticated_request_costs_two_statements(test_db, memberships):
    user_id, active_org_ids = _make_user_with_memberships(
        test_db, active=memberships, inactive=1
    )
    # A fresh request starts with nothing loaded.
    test_db.expire_all()
    token = create_access_token(data={"user_id": user_id})
    client = TestClient(_probe_app(test_db))

    with _StatementCounter(test_db.get_bind().engine) as counter:
        resp = client.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    # Old shape: 1 (user) + 1 (memberships) + K (one per organization).
    assert len(counter.statements) == 2, counter.statements
    returned = {o["id"] for o in resp.json()["organizations"]}
    assert returned == set(active_org_ids), "inactive memberships must not be listed"
    for org in resp.json()["organizations"]:
        assert org["name"].startswith("Auth Count Org")
        assert org["role"] == "ANNOTATOR"


def test_auth_ends_the_transaction_it_opened(test_db):
    user_id, _ = _make_user_with_memberships(test_db, active=1, inactive=0)
    token = create_access_token(data={"user_id": user_id})
    client = TestClient(_probe_app(test_db))

    resp = client.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert not test_db.in_transaction(), (
        "require_user left its read transaction open; the connection stays "
        "checked out idle in transaction for the rest of the request"
    )


def test_auth_leaves_a_transaction_it_did_not_open(test_db):
    """When another dependency used the session first, its transaction may
    carry locks or state the handler relies on; auth must not end it."""
    user_id, _ = _make_user_with_memberships(test_db, active=1, inactive=0)
    token = create_access_token(data={"user_id": user_id})
    client = TestClient(_probe_app(test_db, touch_db_first=True))

    resp = client.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert test_db.in_transaction()
