"""Integration tests for the superadmin LTI 1.3 admin surface (/api/admin/lti).

Drives the platform-owned persistence CRUD through the real async HTTP stack:
the superadmin gate, the registration round-trip incl. deployment management,
(issuer, client_id) uniqueness, tool-config URL derivation, and the grade-sync
outbox reads + retry reset. The LTI protocol itself (login/launch/AGS) lives in
``benger_extended`` and is out of scope here.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from models import (
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiResourceLink,
    Organization,
    User,
)
from project_models import Project


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"lti-user-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="LTI Tester",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db) -> Organization:
    suffix = uuid.uuid4().hex[:8]
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"lti-org-{suffix}",
        display_name="LTI Test Org",
        slug=f"lti-org-{suffix}",
    )
    db.add(org)
    await db.flush()
    return org


def _registration_payload(organization_id: str, **overrides) -> dict:
    body = {
        "organization_id": organization_id,
        "name": "Uni Passau Moodle",
        "issuer": "https://moodle.uni-passau.de",
        "client_id": f"client-{uuid.uuid4().hex[:8]}",
        "auth_login_url": "https://moodle.uni-passau.de/mod/lti/auth.php",
        "auth_token_url": "https://moodle.uni-passau.de/mod/lti/token.php",
        "jwks_uri": "https://moodle.uni-passau.de/mod/lti/certs.php",
        "deployment_ids": ["1"],
    }
    body.update(overrides)
    return body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_gate_blocks_non_admins(async_test_client, async_test_db):
    org = await _make_org(async_test_db)
    normal_user = await _make_user(async_test_db)

    with _as_user(normal_user):
        r = await async_test_client.get("/api/admin/lti/registrations")
        assert r.status_code == 403
        r = await async_test_client.post(
            "/api/admin/lti/registrations", json=_registration_payload(org.id)
        )
        assert r.status_code == 403
        r = await async_test_client.get("/api/admin/lti/grade-syncs")
        assert r.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registration_crud_round_trip(async_test_client, async_test_db):
    org = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)

    with _as_user(admin):
        # Create — duplicate deployment ids collapse, order preserved.
        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(
                org.id, deployment_ids=["dep-1", "dep-2", "dep-1"]
            ),
        )
        assert r.status_code == 201, r.text
        created = r.json()
        reg_id = created["id"]
        assert created["organization_id"] == org.id
        assert created["status"] == "active"
        assert created["link_existing_users_by_email"] is True
        assert created["instructor_org_role"] == "contributor"
        assert created["deployment_count"] == 2
        assert sorted(d["deployment_id"] for d in created["deployments"]) == [
            "dep-1",
            "dep-2",
        ]

        # List includes it, with the deployment count.
        r = await async_test_client.get("/api/admin/lti/registrations")
        assert r.status_code == 200
        listed = [reg for reg in r.json() if reg["id"] == reg_id]
        assert len(listed) == 1
        assert listed[0]["deployment_count"] == 2

        # Detail carries deployments + resource-link count.
        r = await async_test_client.get(f"/api/admin/lti/registrations/{reg_id}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["resource_link_count"] == 0
        assert len(detail["deployments"]) == 2

        # Update a policy knob, an endpoint URL, and the status.
        r = await async_test_client.put(
            f"/api/admin/lti/registrations/{reg_id}",
            json={
                "name": "Uni Passau Moodle (renamed)",
                "jwks_uri": "https://moodle.uni-passau.de/mod/lti/certs2.php",
                "instructor_org_role": "org_admin",
                "status": "disabled",
            },
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["name"] == "Uni Passau Moodle (renamed)"
        assert updated["jwks_uri"].endswith("certs2.php")
        assert updated["instructor_org_role"] == "org_admin"
        assert updated["status"] == "disabled"
        # Untouched fields survive the partial update.
        assert updated["issuer"] == "https://moodle.uni-passau.de"
        assert updated["deployment_count"] == 2

        # Add a deployment; adding it twice conflicts.
        r = await async_test_client.post(
            f"/api/admin/lti/registrations/{reg_id}/deployments",
            json={"deployment_id": "dep-3"},
        )
        assert r.status_code == 201, r.text
        dep_pk = r.json()["id"]
        r = await async_test_client.post(
            f"/api/admin/lti/registrations/{reg_id}/deployments",
            json={"deployment_id": "dep-3"},
        )
        assert r.status_code == 409

        # Remove it again; removing twice 404s.
        r = await async_test_client.delete(
            f"/api/admin/lti/registrations/{reg_id}/deployments/{dep_pk}"
        )
        assert r.status_code == 204
        r = await async_test_client.delete(
            f"/api/admin/lti/registrations/{reg_id}/deployments/{dep_pk}"
        )
        assert r.status_code == 404
        r = await async_test_client.get(f"/api/admin/lti/registrations/{reg_id}")
        assert r.json()["deployment_count"] == 2

        # Unknown registration id 404s.
        r = await async_test_client.get("/api/admin/lti/registrations/nope")
        assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_issuer_client_conflict(async_test_client, async_test_db):
    org = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)

    with _as_user(admin):
        payload = _registration_payload(org.id, client_id="client-dup")
        r = await async_test_client.post("/api/admin/lti/registrations", json=payload)
        assert r.status_code == 201, r.text

        # Same (issuer, client_id) again → 409.
        r = await async_test_client.post("/api/admin/lti/registrations", json=payload)
        assert r.status_code == 409

        # Same issuer, different client_id → fine.
        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(org.id, client_id="client-other"),
        )
        assert r.status_code == 201, r.text
        other_id = r.json()["id"]

        # Updating the second one onto the first pair → 409.
        r = await async_test_client.put(
            f"/api/admin/lti/registrations/{other_id}",
            json={"client_id": "client-dup"},
        )
        assert r.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_org_and_bad_urls(
    async_test_client, async_test_db
):
    org = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)

    with _as_user(admin):
        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(str(uuid.uuid4())),
        )
        assert r.status_code == 404

        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(org.id, jwks_uri="ftp://moodle.example.com/certs"),
        )
        assert r.status_code == 422

        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(org.id, issuer="not-a-url"),
        )
        assert r.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_config_urls(async_test_client, async_test_db):
    org = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)

    with _as_user(admin):
        r = await async_test_client.post(
            "/api/admin/lti/registrations", json=_registration_payload(org.id)
        )
        reg_id = r.json()["id"]

        r = await async_test_client.get(
            f"/api/admin/lti/registrations/{reg_id}/tool-config",
            params={"base_url": "https://benger.example.com/"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {
            "login_url": "https://benger.example.com/api/lti/login",
            "launch_url": "https://benger.example.com/api/lti/launch",
            "jwks_url": "https://benger.example.com/api/lti/jwks",
            "deep_linking_url": "https://benger.example.com/api/lti/deep-linking",
        }

        # Non-http(s) base_url is rejected.
        r = await async_test_client.get(
            f"/api/admin/lti/registrations/{reg_id}/tool-config",
            params={"base_url": "ftp://benger.example.com"},
        )
        assert r.status_code == 400

        # Unknown registration 404s.
        r = await async_test_client.get(
            "/api/admin/lti/registrations/nope/tool-config",
            params={"base_url": "https://benger.example.com"},
        )
        assert r.status_code == 404


async def _seed_grade_sync(db, org, admin) -> tuple:
    """Registration -> project -> resource link -> failed grade-sync row."""
    reg = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="Seeded Moodle",
        issuer=f"https://moodle-{uuid.uuid4().hex[:8]}.example.com",
        client_id="client-seed",
        auth_login_url="https://moodle.example.com/auth",
        auth_token_url="https://moodle.example.com/token",
        jwks_uri="https://moodle.example.com/certs",
    )
    db.add(reg)
    project = Project(
        id=str(uuid.uuid4()),
        title="LTI-verlinkte Probeklausur",
        created_by=admin.id,
        is_private=True,
        kind="exam",
        origin="student",
    )
    db.add(project)
    await db.flush()

    link = LtiResourceLink(
        id=str(uuid.uuid4()),
        registration_id=reg.id,
        deployment_id="1",
        resource_link_id="rl-1",
        project_id=project.id,
    )
    db.add(link)
    await db.flush()

    student = await _make_user(db)
    sync = LtiGradeSync(
        id=str(uuid.uuid4()),
        resource_link_id=link.id,
        user_id=student.id,
        status="failed",
        attempts=3,
        last_error="AGS lineitem POST returned 500",
    )
    db.add(sync)
    await db.commit()
    return project, sync


@pytest.mark.integration
@pytest.mark.asyncio
async def test_grade_sync_list_filters_and_retry_reset(
    async_test_client, async_test_db
):
    org = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)
    project, sync = await _seed_grade_sync(async_test_db, org, admin)

    with _as_user(admin):
        # Unfiltered list sees the row.
        r = await async_test_client.get("/api/admin/lti/grade-syncs")
        assert r.status_code == 200
        assert any(row["id"] == sync.id for row in r.json())

        # Status filter.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"status": "failed"}
        )
        assert [row["id"] for row in r.json()] == [sync.id]
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"status": "pending"}
        )
        assert r.json() == []

        # Project filter (join through lti_resource_links).
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"project_id": project.id}
        )
        assert [row["id"] for row in r.json()] == [sync.id]
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"project_id": str(uuid.uuid4())}
        )
        assert r.json() == []

        # Retry resets the outbox row for the worker.
        r = await async_test_client.post(f"/api/admin/lti/grade-syncs/{sync.id}/retry")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["attempts"] == 0
        assert body["last_error"] is None
        assert body["next_retry_at"] is not None

        # And the reset is visible through the status filter.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"status": "pending"}
        )
        assert [row["id"] for row in r.json()] == [sync.id]

        # Unknown outbox row 404s.
        r = await async_test_client.post(
            f"/api/admin/lti/grade-syncs/{uuid.uuid4()}/retry"
        )
        assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registrations_organization_filter(async_test_client, async_test_db):
    org_a = await _make_org(async_test_db)
    org_b = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)

    with _as_user(admin):
        r = await async_test_client.post(
            "/api/admin/lti/registrations", json=_registration_payload(org_a.id)
        )
        assert r.status_code == 201, r.text
        reg_a = r.json()["id"]
        r = await async_test_client.post(
            "/api/admin/lti/registrations",
            json=_registration_payload(
                org_b.id, issuer="https://moodle.uni-b.example.com"
            ),
        )
        assert r.status_code == 201, r.text
        reg_b = r.json()["id"]

        # Org filter returns only that org's registrations.
        r = await async_test_client.get(
            "/api/admin/lti/registrations", params={"organization_id": org_a.id}
        )
        assert r.status_code == 200
        assert [reg["id"] for reg in r.json()] == [reg_a]
        assert all(reg["organization_id"] == org_a.id for reg in r.json())

        # Unknown org id is a filter miss, not a 404.
        r = await async_test_client.get(
            "/api/admin/lti/registrations",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        assert r.json() == []

        # No param keeps the unfiltered behavior (both rows, shape unchanged).
        r = await async_test_client.get("/api/admin/lti/registrations")
        assert r.status_code == 200
        ids = [reg["id"] for reg in r.json()]
        assert reg_a in ids and reg_b in ids
        assert {"id", "organization_id", "deployments", "deployment_count"} <= set(
            r.json()[0].keys()
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_grade_sync_organization_filter(async_test_client, async_test_db):
    org_a = await _make_org(async_test_db)
    org_b = await _make_org(async_test_db)
    admin = await _make_user(async_test_db, superadmin=True)
    project_a, sync_a = await _seed_grade_sync(async_test_db, org_a, admin)
    project_b, sync_b = await _seed_grade_sync(async_test_db, org_b, admin)

    with _as_user(admin):
        # Org filter alone (join through resource link -> registration).
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"organization_id": org_a.id}
        )
        assert r.status_code == 200
        assert [row["id"] for row in r.json()] == [sync_a.id]

        # Unknown org id yields an empty list, not a 404.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        assert r.json() == []

        # Combined with the status filter.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={"organization_id": org_a.id, "status": "failed"},
        )
        assert [row["id"] for row in r.json()] == [sync_a.id]
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={"organization_id": org_a.id, "status": "pending"},
        )
        assert r.json() == []

        # Combined with project_id – the resource-link join must not double up.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={"organization_id": org_a.id, "project_id": project_a.id},
        )
        assert r.status_code == 200
        assert [row["id"] for row in r.json()] == [sync_a.id]

        # Mismatched org/project combination matches nothing.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={"organization_id": org_a.id, "project_id": project_b.id},
        )
        assert r.json() == []

        # All three filters together.
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs",
            params={
                "organization_id": org_b.id,
                "project_id": project_b.id,
                "status": "failed",
            },
        )
        assert [row["id"] for row in r.json()] == [sync_b.id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_organization_filters_stay_superadmin_only(
    async_test_client, async_test_db
):
    org = await _make_org(async_test_db)
    normal_user = await _make_user(async_test_db)

    with _as_user(normal_user):
        r = await async_test_client.get(
            "/api/admin/lti/registrations", params={"organization_id": org.id}
        )
        assert r.status_code == 403
        r = await async_test_client.get(
            "/api/admin/lti/grade-syncs", params={"organization_id": org.id}
        )
        assert r.status_code == 403
