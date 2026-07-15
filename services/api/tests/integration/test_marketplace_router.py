"""Behavioral tests for the vendor-marketplace router.

Target: ``services/api/routers/marketplace.py`` (``/api/marketplace/*`` student
reads + vendor listing CRUD, and ``/api/admin/vendors*`` superadmin approval).
This router had no behavioral coverage. Every endpoint is a generic row read or
CRUD gated by the project-role / superadmin primitives; the tests drive the
real async HTTP stack (``async_test_client`` + ``async_test_db``) with real
seeded rows and assert on responses and DB state.

Access recap:
  * ``get_effective_project_role_async`` returns ORG_ADMIN for a superadmin or
    the project creator, else the caller's active org-membership role — so a
    project's creator is a "vendor editor" (ORG_ADMIN) for it.
  * ``_resolve_vendor_org`` requires the project's org to carry a
    ``VendorAccount`` (the row's existence == superadmin approval).
  * Publishing a listing additionally requires the vendor's
    ``charges_enabled``.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
    VendorAccount,
)
from project_models import (
    Annotation,
    MarketplaceEntitlement,
    MarketplaceGradingCredit,
    MarketplaceGradingRequest,
    MarketplaceListing,
    Project,
    ProjectOrganization,
    Task,
)

MP = "/api/marketplace"
ADMIN = "/api/admin"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, is_superadmin=None):
    sa = db_user.is_superadmin if is_superadmin is None else is_superadmin
    au = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email, name=db_user.name,
        is_superadmin=sa, is_active=True, email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


# --------------------------------------------------------------------------- #
# Seeding helpers
# --------------------------------------------------------------------------- #
async def _mk_user(db, *, superadmin=False) -> User:
    u = User(
        id=_uid(), username=f"u-{_uid()[:8]}", email=f"{_uid()[:8]}@e.com", name="U",
        is_superadmin=superadmin, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_org(db, *, name="Vendor") -> Organization:
    oid = _uid()
    org = Organization(
        id=oid, name=f"org-{oid[:6]}", display_name=name, slug=f"org-{oid[:8]}",
        is_active=True,
    )
    db.add(org)
    await db.flush()
    return org


async def _mk_membership(db, user, org, role=OrganizationRole.ORG_ADMIN):
    m = OrganizationMembership(
        id=_uid(), user_id=user.id, organization_id=org.id, role=role, is_active=True,
    )
    db.add(m)
    await db.flush()
    return m


async def _mk_vendor(db, org, *, charges_enabled=True, approver=None) -> VendorAccount:
    va = VendorAccount(
        id=_uid(), organization_id=org.id, charges_enabled=charges_enabled,
        payouts_enabled=charges_enabled, details_submitted=charges_enabled,
        onboarding_status="active" if charges_enabled else "pending",
        approved_by=approver.id if approver else None,
        stripe_account_id="acct_test" if charges_enabled else None,
    )
    db.add(va)
    await db.flush()
    return va


async def _mk_project(db, owner, org=None, *, kind="exam") -> Project:
    p = Project(
        id=_uid(), title=f"Exam {_uid()[:6]}", created_by=owner.id, is_private=True, kind=kind,
    )
    db.add(p)
    await db.flush()
    if org is not None:
        db.add(ProjectOrganization(
            id=_uid(), project_id=p.id, organization_id=org.id, assigned_by=owner.id,
        ))
        await db.flush()
    return p


async def _mk_listing(db, project, vendor_org, *, published=True, price=1500,
                      grading_mode="ai", hg_price=None, creator=None) -> MarketplaceListing:
    li = MarketplaceListing(
        id=_uid(), project_id=project.id, vendor_org_id=vendor_org.id, kind=project.kind,
        price_cents=price, currency="eur", published=published, grading_mode=grading_mode,
        human_grading_price_cents=hg_price, human_grading_quantity=1,
        created_by=creator.id if creator else project.created_by,
    )
    db.add(li)
    await db.flush()
    return li


async def _mk_entitlement(db, user, project, *, source="purchase", revoked=False):
    e = MarketplaceEntitlement(
        id=_uid(), user_id=user.id, project_id=project.id, source=source,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db.add(e)
    await db.flush()
    return e


async def _mk_credit(db, user, project, org, *, total=3, used=1):
    c = MarketplaceGradingCredit(
        id=_uid(), user_id=user.id, project_id=project.id, vendor_org_id=org.id,
        total_credits=total, used_credits=used,
    )
    db.add(c)
    await db.flush()
    return c


async def _mk_grading_request(db, user, project, org, *, status="pending"):
    task = Task(id=_uid(), project_id=project.id, data={"x": "y"}, inner_id=1)
    db.add(task)
    await db.flush()
    ann = Annotation(id=_uid(), task_id=task.id, project_id=project.id, completed_by=user.id, result=[])
    db.add(ann)
    await db.flush()
    r = MarketplaceGradingRequest(
        id=_uid(), user_id=user.id, project_id=project.id, annotation_id=ann.id,
        vendor_org_id=org.id, status=status,
    )
    db.add(r)
    await db.flush()
    return r


# ===========================================================================
# Student-facing reads
# ===========================================================================
@pytest.mark.integration
class TestStudentReads:
    @pytest.mark.asyncio
    async def test_discover_lists_published_with_flags(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db, name="Acme")
        await _mk_vendor(async_test_db, org)
        pub = await _mk_project(async_test_db, owner, org)
        unpub = await _mk_project(async_test_db, owner, org)
        await _mk_listing(async_test_db, pub, org, published=True)
        await _mk_listing(async_test_db, unpub, org, published=False)
        await _mk_entitlement(async_test_db, buyer, pub)
        await async_test_db.commit()

        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/discover")
        assert r.status_code == 200, r.text
        by_pid = {it["project_id"]: it for it in r.json()}
        assert pub.id in by_pid
        assert unpub.id not in by_pid  # unpublished never shows
        assert by_pid[pub.id]["vendor_name"] == "Acme"
        assert by_pid[pub.id]["entitled"] is True
        assert by_pid[pub.id]["owned"] is False

        # The owner sees owned=True, entitled=False.
        with _as_user(owner):
            r = await async_test_client.get(f"{MP}/discover")
        by_pid = {it["project_id"]: it for it in r.json()}
        assert by_pid[pub.id]["owned"] is True
        assert by_pid[pub.id]["entitled"] is False

    @pytest.mark.asyncio
    async def test_get_listing_detail(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db, name="Shop")
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org)
        li = await _mk_listing(async_test_db, p, org, price=2500, grading_mode="both", hg_price=900)
        await _mk_credit(async_test_db, buyer, p, org, total=5, used=2)
        await async_test_db.commit()

        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/listings/{li.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["price_cents"] == 2500
        assert body["title"] == p.title
        assert body["vendor_name"] == "Shop"
        assert body["offers_human_grading"] is True
        assert body["grading_credits_available"] == 3  # 5 - 2
        assert body["entitled"] is False
        assert body["owned"] is False

    @pytest.mark.asyncio
    async def test_get_listing_no_credits_and_entitled(self, async_test_client, async_test_db):
        """Entitled buyer with no grading credits: entitled=True, credits=0."""
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org)
        li = await _mk_listing(async_test_db, p, org)
        await _mk_entitlement(async_test_db, buyer, p)
        await async_test_db.commit()
        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/listings/{li.id}")
        assert r.status_code == 200, r.text
        assert r.json()["entitled"] is True
        assert r.json()["grading_credits_available"] == 0

    @pytest.mark.asyncio
    async def test_get_listing_404(self, async_test_client, async_test_db):
        u = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(u):
            r = await async_test_client.get(f"{MP}/listings/missing-{_uid()}")
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_entitlements_excludes_revoked(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        active_p = await _mk_project(async_test_db, owner, org)
        revoked_p = await _mk_project(async_test_db, owner, org)
        await _mk_entitlement(async_test_db, buyer, active_p, source="purchase")
        await _mk_entitlement(async_test_db, buyer, revoked_p, source="vendor_grant", revoked=True)
        await async_test_db.commit()

        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/entitlements")
        assert r.status_code == 200, r.text
        pids = {e["project_id"] for e in r.json()}
        assert active_p.id in pids
        assert revoked_p.id not in pids

    @pytest.mark.asyncio
    async def test_grading_credits_available_math(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        p = await _mk_project(async_test_db, owner, org)
        await _mk_credit(async_test_db, buyer, p, org, total=4, used=1)
        await async_test_db.commit()

        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/grading/credits")
        assert r.status_code == 200, r.text
        (row,) = r.json()
        assert row["total_credits"] == 4
        assert row["used_credits"] == 1
        assert row["available"] == 3

    @pytest.mark.asyncio
    async def test_grading_requests_list(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        p = await _mk_project(async_test_db, owner, org)
        req = await _mk_grading_request(async_test_db, buyer, p, org, status="pending")
        await async_test_db.commit()

        with _as_user(buyer):
            r = await async_test_client.get(f"{MP}/grading/requests")
        assert r.status_code == 200, r.text
        (row,) = r.json()
        assert row["request_id"] == req.id
        assert row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_grading_queue_requires_corrector(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        buyer = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, owner, org, OrganizationRole.ORG_ADMIN)
        p = await _mk_project(async_test_db, owner, org)
        await _mk_grading_request(async_test_db, buyer, p, org, status="pending")
        await async_test_db.commit()

        # A stranger (no membership) is denied.
        with _as_user(stranger):
            r = await async_test_client.get(f"{MP}/grading/queue?organization_id={org.id}")
        assert r.status_code == 403, r.text

        # The org admin sees the pending queue.
        with _as_user(owner):
            r = await async_test_client.get(f"{MP}/grading/queue?organization_id={org.id}")
            assert r.status_code == 200, r.text
            assert len(r.json()) == 1
            # The completed filter is empty (nothing graded yet).
            r2 = await async_test_client.get(
                f"{MP}/grading/queue?organization_id={org.id}&status=completed"
            )
        assert r2.status_code == 200, r2.text
        assert r2.json() == []


# ===========================================================================
# Vendor listing CRUD
# ===========================================================================
@pytest.mark.integration
class TestListingCrud:
    @pytest.mark.asyncio
    async def test_create_listing_happy(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, owner, org, OrganizationRole.ORG_ADMIN)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 1200, "published": True},
            )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["project_id"] == p.id
        assert body["published"] is True
        row = (
            await async_test_db.execute(
                select(MarketplaceListing).where(MarketplaceListing.project_id == p.id)
            )
        ).scalar_one()
        assert row.vendor_org_id == org.id

    @pytest.mark.asyncio
    async def test_create_listing_unpublished_draft(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, owner, org, OrganizationRole.CONTRIBUTOR)
        await _mk_vendor(async_test_db, org, charges_enabled=False)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 800, "published": False,
                      "description": "Draft"},
            )
        assert r.status_code == 201, r.text
        assert r.json()["published"] is False
        assert r.json()["description"] == "Draft"

    @pytest.mark.asyncio
    async def test_create_listing_with_human_grading(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 1500, "grading_mode": "both",
                      "human_grading_price_cents": 600, "human_grading_quantity": 2},
            )
        assert r.status_code == 201, r.text
        assert r.json()["offers_human_grading"] is True
        assert r.json()["human_grading_price_cents"] == 600

    @pytest.mark.asyncio
    async def test_create_listing_flashcard_collection(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        p = await _mk_project(async_test_db, owner, org, kind="flashcard_collection")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 500, "currency": "EUR", "published": True},
            )
        assert r.status_code == 201, r.text
        assert r.json()["kind"] == "flashcard_collection"
        assert r.json()["currency"] == "eur"

    @pytest.mark.asyncio
    async def test_create_listing_project_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": f"missing-{_uid()}", "price_cents": 500}
            )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_create_listing_unlistable_kind_400(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="annotation")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": p.id, "price_cents": 500}
            )
        assert r.status_code == 400, r.text
        assert "listable" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_not_editor_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(stranger):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": p.id, "price_cents": 500}
            )
        assert r.status_code == 403, r.text
        assert "vendor editor" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_org_not_vendor_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)  # no VendorAccount
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": p.id, "price_cents": 500}
            )
        assert r.status_code == 403, r.text
        assert "approved vendor" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_publish_without_charges_409(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=False)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": p.id, "price_cents": 500, "published": True}
            )
        assert r.status_code == 409, r.text
        assert "Stripe onboarding" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_duplicate_409(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await _mk_listing(async_test_db, p, org, published=False)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings", json={"project_id": p.id, "price_cents": 500}
            )
        assert r.status_code == 409, r.text
        assert "already exists" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_human_grading_needs_price_400(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 500, "grading_mode": "human"},
            )
        assert r.status_code == 400, r.text
        assert "human_grading_price_cents" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_listing_human_grading_only_exams_400(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="flashcard_collection")
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.post(
                f"{MP}/listings",
                json={"project_id": p.id, "price_cents": 500, "grading_mode": "both",
                      "human_grading_price_cents": 700},
            )
        assert r.status_code == 400, r.text
        assert "only available for exams" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_listing_fields_and_publish_gate(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=False)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org, published=False, price=1000)
        await async_test_db.commit()

        with _as_user(owner):
            # Edit price + description (no publish).
            r = await async_test_client.patch(
                f"{MP}/listings/{li.id}", json={"price_cents": 3000, "description": "New"}
            )
            assert r.status_code == 200, r.text
            assert r.json()["price_cents"] == 3000
            # Publishing while charges disabled → 409.
            r = await async_test_client.patch(f"{MP}/listings/{li.id}", json={"published": True})
            assert r.status_code == 409, r.text

    @pytest.mark.asyncio
    async def test_update_listing_publishes_when_charges_enabled(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org, published=False)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(f"{MP}/listings/{li.id}", json={"published": True})
        assert r.status_code == 200, r.text
        assert r.json()["published"] is True

    @pytest.mark.asyncio
    async def test_update_listing_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(f"{MP}/listings/missing-{_uid()}", json={"price_cents": 500})
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_update_listing_grading_fields(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org, published=False)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(
                f"{MP}/listings/{li.id}",
                json={"grading_mode": "both", "human_grading_price_cents": 800,
                      "human_grading_quantity": 3},
            )
        assert r.status_code == 200, r.text
        assert r.json()["grading_mode"] == "both"
        assert r.json()["human_grading_price_cents"] == 800

    @pytest.mark.asyncio
    async def test_update_listing_human_grading_price_required_400(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org, published=False)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(f"{MP}/listings/{li.id}", json={"grading_mode": "human"})
        assert r.status_code == 400, r.text
        assert "human_grading_price_cents" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_listing_not_editor_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org)
        await async_test_db.commit()
        with _as_user(stranger):
            r = await async_test_client.patch(f"{MP}/listings/{li.id}", json={"price_cents": 999})
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_delete_listing(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.delete(f"{MP}/listings/{li.id}")
        assert r.status_code == 204, r.text
        gone = (
            await async_test_db.execute(
                select(MarketplaceListing).where(MarketplaceListing.id == li.id)
            )
        ).scalar_one_or_none()
        assert gone is None

    @pytest.mark.asyncio
    async def test_delete_listing_not_editor_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, owner, org, kind="exam")
        li = await _mk_listing(async_test_db, p, org)
        await async_test_db.commit()
        with _as_user(stranger):
            r = await async_test_client.delete(f"{MP}/listings/{li.id}")
        assert r.status_code == 403, r.text


# ===========================================================================
# Vendor status / listings
# ===========================================================================
@pytest.mark.integration
class TestVendorViews:
    @pytest.mark.asyncio
    async def test_vendor_account_status_admin_only(self, async_test_client, async_test_db):
        admin = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, admin, org, OrganizationRole.ORG_ADMIN)
        await _mk_vendor(async_test_db, org, charges_enabled=True)
        await async_test_db.commit()

        with _as_user(stranger):
            r = await async_test_client.get(f"{MP}/vendor/account?organization_id={org.id}")
        assert r.status_code == 403, r.text

        with _as_user(admin):
            r = await async_test_client.get(f"{MP}/vendor/account?organization_id={org.id}")
        assert r.status_code == 200, r.text
        assert r.json()["approved"] is True
        assert r.json()["charges_enabled"] is True

    @pytest.mark.asyncio
    async def test_vendor_account_not_approved(self, async_test_client, async_test_db):
        admin = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, admin, org, OrganizationRole.ORG_ADMIN)
        await async_test_db.commit()
        with _as_user(admin):
            r = await async_test_client.get(f"{MP}/vendor/account?organization_id={org.id}")
        assert r.status_code == 200, r.text
        assert r.json()["approved"] is False

    @pytest.mark.asyncio
    async def test_vendor_listings_gated(self, async_test_client, async_test_db):
        admin = await _mk_user(async_test_db)
        stranger = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db)
        await _mk_membership(async_test_db, admin, org, OrganizationRole.CONTRIBUTOR)
        await _mk_vendor(async_test_db, org)
        p = await _mk_project(async_test_db, admin, org, kind="exam")
        await _mk_listing(async_test_db, p, org)
        await async_test_db.commit()

        with _as_user(stranger):
            r = await async_test_client.get(f"{MP}/vendor/listings?organization_id={org.id}")
        assert r.status_code == 403, r.text

        with _as_user(admin):
            r = await async_test_client.get(f"{MP}/vendor/listings?organization_id={org.id}")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1
        assert r.json()[0]["title"] == p.title


# ===========================================================================
# Superadmin vendor approval
# ===========================================================================
@pytest.mark.integration
class TestAdminVendors:
    @pytest.mark.asyncio
    async def test_list_vendors_superadmin_only(self, async_test_client, async_test_db):
        sa = await _mk_user(async_test_db, superadmin=True)
        plain = await _mk_user(async_test_db)
        org = await _mk_org(async_test_db, name="V1")
        await _mk_vendor(async_test_db, org)
        await async_test_db.commit()

        with _as_user(plain):
            r = await async_test_client.get(f"{ADMIN}/vendors")
        assert r.status_code == 403, r.text

        with _as_user(sa):
            r = await async_test_client.get(f"{ADMIN}/vendors")
        assert r.status_code == 200, r.text
        names = {v["organization_name"] for v in r.json()}
        assert "V1" in names

    @pytest.mark.asyncio
    async def test_approve_vendor_creates_and_is_idempotent(self, async_test_client, async_test_db):
        sa = await _mk_user(async_test_db, superadmin=True)
        org = await _mk_org(async_test_db)
        await async_test_db.commit()

        with _as_user(sa):
            r = await async_test_client.post(
                f"{ADMIN}/vendors", json={"organization_id": org.id, "platform_fee_bps": 250}
            )
            assert r.status_code == 201, r.text
            assert r.json()["approved"] is True
            assert r.json()["platform_fee_bps"] == 250

            # Re-approving is idempotent and can update the fee.
            r2 = await async_test_client.post(
                f"{ADMIN}/vendors", json={"organization_id": org.id, "platform_fee_bps": 400}
            )
        assert r2.status_code == 201, r2.text
        assert r2.json()["platform_fee_bps"] == 400
        rows = (
            await async_test_db.execute(
                select(VendorAccount).where(VendorAccount.organization_id == org.id)
            )
        ).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_approve_vendor_org_404(self, async_test_client, async_test_db):
        sa = await _mk_user(async_test_db, superadmin=True)
        await async_test_db.commit()
        with _as_user(sa):
            r = await async_test_client.post(
                f"{ADMIN}/vendors", json={"organization_id": f"missing-{_uid()}"}
            )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_revoke_vendor(self, async_test_client, async_test_db):
        sa = await _mk_user(async_test_db, superadmin=True)
        org = await _mk_org(async_test_db)
        await _mk_vendor(async_test_db, org)
        await async_test_db.commit()
        with _as_user(sa):
            r = await async_test_client.delete(f"{ADMIN}/vendors/{org.id}")
        assert r.status_code == 204, r.text
        gone = (
            await async_test_db.execute(
                select(VendorAccount).where(VendorAccount.organization_id == org.id)
            )
        ).scalar_one_or_none()
        assert gone is None
