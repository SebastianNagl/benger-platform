"""Vendor marketplace — generic listing/entitlement reads + CRUD (platform).

Vendors (organizations flagged with a ``VendorAccount`` by a superadmin) sell
exams and flashcard collections to students. This router owns the *generic*
surface: the global discovery feed, listing CRUD over the platform-owned
``marketplace_listings`` table, a student's entitlement reads, and the
superadmin vendor-approval endpoints. It contains NO payment logic — the
Stripe Connect checkout/onboarding/webhooks live in the extended
``/api/marketplace`` router (``benger_extended``), which writes the
``marketplace_orders`` / ``marketplace_entitlements`` rows this router reads.

Split-rule note: every endpoint here is either a generic row read or generic
CRUD gated by the existing project-role / superadmin primitives. The
``charges_enabled`` publish precondition is a plain row lookup (a vendor can't
publish a priced item before Stripe says they can take money), not proprietary
logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module.dependencies import require_superadmin, require_user
from database import get_async_db
from models import (  # noqa: F401
    MarketplaceOrder,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
    VendorAccount,
)
from project_models import (
    MarketplaceEntitlement,
    MarketplaceGradingCredit,
    MarketplaceGradingRequest,
    MarketplaceListing,
    Project,
    ProjectOrganization,
)
from routers.projects.helpers import (
    get_effective_project_role_async,
    get_entitlement_access_async,
)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
admin_router = APIRouter(prefix="/api/admin", tags=["marketplace-admin"])

# Project kinds a vendor may list (exams + flashcard collections; legacy deck).
LISTABLE_KINDS = ("exam", "flashcard_collection", "flashcard_deck")
EDITOR_ROLES = ("ORG_ADMIN", "CONTRIBUTOR")


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #
class ListingCreate(BaseModel):
    project_id: str
    price_cents: int = Field(ge=50, le=10_000_00)  # Stripe min ~€0.50; sane cap.
    currency: str = Field("eur", min_length=3, max_length=3)
    description: Optional[str] = None
    published: bool = False
    # Human grading: 'ai' (no add-on), 'human'/'both' (offers a paid HG add-on).
    grading_mode: str = Field("ai", pattern="^(ai|human|both)$")
    human_grading_price_cents: Optional[int] = Field(None, ge=50, le=10_000_00)
    human_grading_quantity: int = Field(1, ge=1, le=100)


class ListingUpdate(BaseModel):
    price_cents: Optional[int] = Field(None, ge=50, le=10_000_00)
    description: Optional[str] = None
    published: Optional[bool] = None
    grading_mode: Optional[str] = Field(None, pattern="^(ai|human|both)$")
    human_grading_price_cents: Optional[int] = Field(None, ge=50, le=10_000_00)
    human_grading_quantity: Optional[int] = Field(None, ge=1, le=100)


class VendorApprove(BaseModel):
    organization_id: str
    # Optional per-vendor platform-fee override (basis points); NULL = global default.
    platform_fee_bps: Optional[int] = Field(None, ge=0, le=10000)


def _listing_dict(link: MarketplaceListing) -> dict:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "vendor_org_id": link.vendor_org_id,
        "kind": link.kind,
        "price_cents": link.price_cents,
        "currency": link.currency,
        "published": link.published,
        "description": link.description,
        "grading_mode": link.grading_mode,
        "offers_human_grading": link.grading_mode in ("human", "both"),
        "human_grading_price_cents": link.human_grading_price_cents,
        "human_grading_quantity": link.human_grading_quantity,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _vendor_account_dict(va: Optional[VendorAccount]) -> dict:
    """Public vendor-account status (no raw provider blob)."""
    if va is None:
        return {"approved": False, "charges_enabled": False, "onboarding_status": None}
    return {
        "approved": True,
        "organization_id": va.organization_id,
        "stripe_account_id": va.stripe_account_id,
        "charges_enabled": va.charges_enabled,
        "payouts_enabled": va.payouts_enabled,
        "details_submitted": va.details_submitted,
        "onboarding_status": va.onboarding_status,
        "platform_fee_bps": va.platform_fee_bps,
    }


async def _project_org_ids(db: AsyncSession, project_id: str) -> list[str]:
    return list(
        (
            await db.execute(
                select(ProjectOrganization.organization_id).where(
                    ProjectOrganization.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )


async def _resolve_vendor_org(db: AsyncSession, project_id: str) -> Optional[VendorAccount]:
    """Return the VendorAccount of the (single) vendor org owning this project.

    A vendor item is an org-owned project whose org carries a ``VendorAccount``.
    If several of the project's orgs are vendors, prefer one that can already
    sell (``charges_enabled``); otherwise the first. ``None`` means the project
    is not owned by any approved vendor org.
    """
    org_ids = await _project_org_ids(db, project_id)
    if not org_ids:
        return None
    accounts = (
        (
            await db.execute(
                select(VendorAccount).where(
                    VendorAccount.organization_id.in_(org_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        return None
    return next((a for a in accounts if a.charges_enabled), accounts[0])


async def _available_credits(db: AsyncSession, user_id: str, project_id: str) -> int:
    """Human-grading credits the user still has for a project (total - used)."""
    row = (
        await db.execute(
            select(MarketplaceGradingCredit).where(
                MarketplaceGradingCredit.user_id == user_id,
                MarketplaceGradingCredit.project_id == project_id,
                MarketplaceGradingCredit.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not row:
        return 0
    return max(0, (row.total_credits or 0) - (row.used_credits or 0))


async def _is_org_corrector(db: AsyncSession, user: User, organization_id: str) -> bool:
    """True if the user is an active ORG_ADMIN/CONTRIBUTOR of the org (or superadmin)."""
    if user.is_superadmin:
        return True
    row = (
        await db.execute(
            select(OrganizationMembership.id).where(
                OrganizationMembership.user_id == str(user.id),
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role.in_(
                    [OrganizationRole.ORG_ADMIN, OrganizationRole.CONTRIBUTOR]
                ),
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).first()
    return row is not None


async def _load_listing(db: AsyncSession, listing_id: str) -> MarketplaceListing:
    listing = (
        await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        )
    ).scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


async def _require_listing_editor(
    db: AsyncSession, user: User, listing: MarketplaceListing
) -> None:
    project = (
        await db.execute(select(Project).where(Project.id == listing.project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    role = await get_effective_project_role_async(db, user, project)
    if role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="Not a vendor editor for this item")


# --------------------------------------------------------------------------- #
# Student-facing reads
# --------------------------------------------------------------------------- #
@router.get("/discover")
async def discover_listings(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Global vendor catalogue: every published listing, with the caller's
    access status.

    Not org-scoped — any logged-in student sees every vendor's published item.
    ``entitled`` is true if the caller already bought / was unlocked; ``owned``
    is true if they created the underlying project (vendor staff). The frontend
    merges these into the existing peer-share discover grid and shows Buy vs
    Open accordingly.
    """
    uid = str(current_user.id)
    rows = (
        await db.execute(
            select(MarketplaceListing, Project, Organization)
            .join(Project, Project.id == MarketplaceListing.project_id)
            .join(Organization, Organization.id == MarketplaceListing.vendor_org_id)
            .where(MarketplaceListing.published.is_(True))
            .order_by(MarketplaceListing.created_at.desc())
        )
    ).all()

    entitled_pids = set(
        (
            await db.execute(
                select(MarketplaceEntitlement.project_id).where(
                    MarketplaceEntitlement.user_id == uid,
                    MarketplaceEntitlement.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    out = []
    for listing, project, vendor in rows:
        out.append(
            {
                "source": "vendor",
                "listing_id": listing.id,
                "project_id": project.id,
                "title": project.title,
                "kind": listing.kind or project.kind,
                "vendor_name": vendor.display_name if vendor else None,
                "price_cents": listing.price_cents,
                "currency": listing.currency,
                "entitled": project.id in entitled_pids,
                "owned": str(project.created_by) == uid,
                "grading_mode": listing.grading_mode,
                "offers_human_grading": listing.grading_mode in ("human", "both"),
                "human_grading_price_cents": listing.human_grading_price_cents,
            }
        )
    return out


@router.get("/listings/{listing_id}")
async def get_listing(
    listing_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Buy-page detail for a single listing (title, price, vendor, access)."""
    listing = await _load_listing(db, listing_id)
    project = (
        await db.execute(select(Project).where(Project.id == listing.project_id))
    ).scalar_one_or_none()
    vendor = (
        await db.execute(
            select(Organization).where(Organization.id == listing.vendor_org_id)
        )
    ).scalar_one_or_none()
    entitled = await get_entitlement_access_async(db, current_user, listing.project_id)
    credits = await _available_credits(db, str(current_user.id), listing.project_id)
    return {
        **_listing_dict(listing),
        "title": project.title if project else None,
        "vendor_name": vendor.display_name if vendor else None,
        "entitled": entitled is not None,
        "owned": bool(project and str(project.created_by) == str(current_user.id)),
        "grading_credits_available": credits,
    }


@router.get("/entitlements")
async def list_entitlements(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The caller's active marketplace entitlements ('My purchases')."""
    uid = str(current_user.id)
    rows = (
        await db.execute(
            select(MarketplaceEntitlement, Project)
            .join(Project, Project.id == MarketplaceEntitlement.project_id)
            .where(
                MarketplaceEntitlement.user_id == uid,
                MarketplaceEntitlement.revoked_at.is_(None),
            )
            .order_by(MarketplaceEntitlement.granted_at.desc())
        )
    ).all()
    return [
        {
            "project_id": ent.project_id,
            "title": project.title,
            "kind": project.kind,
            "source": ent.source,
            "granted_at": ent.granted_at.isoformat() if ent.granted_at else None,
        }
        for ent, project in rows
    ]


@router.get("/grading/credits")
async def list_grading_credits(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The caller's human-grading wallets (per vendor exam)."""
    uid = str(current_user.id)
    rows = (
        await db.execute(
            select(MarketplaceGradingCredit, Project)
            .join(Project, Project.id == MarketplaceGradingCredit.project_id)
            .where(
                MarketplaceGradingCredit.user_id == uid,
                MarketplaceGradingCredit.revoked_at.is_(None),
            )
            .order_by(MarketplaceGradingCredit.created_at.desc())
        )
    ).all()
    return [
        {
            "project_id": c.project_id,
            "title": project.title,
            "total_credits": c.total_credits,
            "used_credits": c.used_credits,
            "available": max(0, (c.total_credits or 0) - (c.used_credits or 0)),
        }
        for c, project in rows
    ]


@router.get("/grading/requests")
async def list_grading_requests(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The caller's own human-grading requests and their status."""
    uid = str(current_user.id)
    rows = (
        await db.execute(
            select(MarketplaceGradingRequest, Project)
            .join(Project, Project.id == MarketplaceGradingRequest.project_id)
            .where(MarketplaceGradingRequest.user_id == uid)
            .order_by(MarketplaceGradingRequest.created_at.desc())
        )
    ).all()
    return [
        {
            "request_id": r.id,
            "project_id": r.project_id,
            "title": project.title,
            "annotation_id": r.annotation_id,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r, project in rows
    ]


@router.get("/grading/queue")
async def vendor_grading_queue(
    organization_id: str = Query(...),
    status_filter: str = Query("pending", alias="status"),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The vendor correctors' grading queue for an org (gated to org correctors).

    Lists student attempts awaiting (or, with ``?status=completed``, already
    given) human grading for the org's exams. The corrector grades each via the
    existing korrektur Falllösung endpoint; the extended layer marks the request
    completed afterwards.
    """
    if not await _is_org_corrector(db, current_user, organization_id):
        raise HTTPException(status_code=403, detail="Not a corrector for this vendor")
    rows = (
        await db.execute(
            select(MarketplaceGradingRequest, Project)
            .join(Project, Project.id == MarketplaceGradingRequest.project_id)
            .where(
                MarketplaceGradingRequest.vendor_org_id == organization_id,
                MarketplaceGradingRequest.status == status_filter,
            )
            .order_by(MarketplaceGradingRequest.created_at.asc())
        )
    ).all()
    return [
        {
            "request_id": r.id,
            "project_id": r.project_id,
            "title": project.title,
            "annotation_id": r.annotation_id,
            "status": r.status,
            "assigned_grader_id": r.assigned_grader_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r, project in rows
    ]


# --------------------------------------------------------------------------- #
# Vendor listing CRUD
# --------------------------------------------------------------------------- #
@router.post("/listings", status_code=201)
async def create_listing(
    body: ListingCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a marketplace listing for a vendor-owned project (vendor editor).

    Requires the caller to be an ORG_ADMIN/CONTRIBUTOR of an org the project
    belongs to, and that org to be an approved vendor. Publishing additionally
    requires the vendor's Stripe account to have ``charges_enabled``.
    """
    project = (
        await db.execute(select(Project).where(Project.id == body.project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.kind not in LISTABLE_KINDS:
        raise HTTPException(
            status_code=400, detail="Only exams and flashcard collections are listable"
        )
    role = await get_effective_project_role_async(db, current_user, project)
    if role not in EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="Not a vendor editor for this item")

    vendor = await _resolve_vendor_org(db, body.project_id)
    if vendor is None:
        raise HTTPException(
            status_code=403,
            detail="This project's organization is not an approved vendor",
        )
    if body.published and not vendor.charges_enabled:
        raise HTTPException(
            status_code=409,
            detail="Complete Stripe onboarding before publishing a paid listing",
        )

    existing = (
        await db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.project_id == body.project_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Listing already exists for project")

    if body.grading_mode in ("human", "both") and body.human_grading_price_cents is None:
        raise HTTPException(
            status_code=400,
            detail="human_grading_price_cents is required when offering human grading",
        )
    # Human grading only applies to exams (a corrector grades a Falllösung).
    if body.grading_mode != "ai" and project.kind != "exam":
        raise HTTPException(
            status_code=400, detail="Human grading is only available for exams"
        )

    listing = MarketplaceListing(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        vendor_org_id=vendor.organization_id,
        kind=project.kind,
        price_cents=body.price_cents,
        currency=body.currency.lower(),
        published=body.published,
        description=body.description,
        grading_mode=body.grading_mode,
        human_grading_price_cents=body.human_grading_price_cents,
        human_grading_quantity=body.human_grading_quantity,
        created_by=str(current_user.id),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return _listing_dict(listing)


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: str,
    body: ListingUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Edit a listing's price / description / published state (vendor editor)."""
    listing = await _load_listing(db, listing_id)
    await _require_listing_editor(db, current_user, listing)

    if body.price_cents is not None:
        listing.price_cents = body.price_cents
    if body.description is not None:
        listing.description = body.description
    if body.grading_mode is not None:
        listing.grading_mode = body.grading_mode
    if body.human_grading_price_cents is not None:
        listing.human_grading_price_cents = body.human_grading_price_cents
    if body.human_grading_quantity is not None:
        listing.human_grading_quantity = body.human_grading_quantity
    if (listing.grading_mode in ("human", "both")
            and listing.human_grading_price_cents is None):
        raise HTTPException(
            status_code=400,
            detail="human_grading_price_cents is required when offering human grading",
        )
    if body.published is not None:
        if body.published and not listing.published:
            vendor = await _resolve_vendor_org(db, listing.project_id)
            if vendor is None or not vendor.charges_enabled:
                raise HTTPException(
                    status_code=409,
                    detail="Complete Stripe onboarding before publishing",
                )
        listing.published = body.published
    await db.commit()
    await db.refresh(listing)
    return _listing_dict(listing)


@router.delete("/listings/{listing_id}", status_code=204)
async def delete_listing(
    listing_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a listing (vendor editor). Existing entitlements are unaffected —
    a buyer keeps access to what they already paid for (entitlement.listing_id
    is SET NULL on delete)."""
    listing = await _load_listing(db, listing_id)
    await _require_listing_editor(db, current_user, listing)
    await db.delete(listing)
    await db.commit()


@router.get("/vendor/account")
async def vendor_account_status(
    organization_id: str = Query(...),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Vendor onboarding/charges status for an org the caller administers.

    Gated to ORG_ADMIN of the org (or superadmin). Returns ``approved=False``
    when the org has no VendorAccount yet (awaiting superadmin approval).
    """
    if not current_user.is_superadmin:
        is_admin = (
            await db.execute(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.user_id == str(current_user.id),
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).first()
        if not is_admin:
            raise HTTPException(status_code=403, detail="Not an admin of this organization")
    va = (
        await db.execute(
            select(VendorAccount).where(
                VendorAccount.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    return _vendor_account_dict(va)


@router.get("/vendor/listings")
async def vendor_listings(
    organization_id: str = Query(...),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """A vendor org's own listings (gated to org correctors/admins)."""
    if not await _is_org_corrector(db, current_user, organization_id):
        raise HTTPException(status_code=403, detail="Not a vendor editor")
    rows = (
        await db.execute(
            select(MarketplaceListing, Project)
            .join(Project, Project.id == MarketplaceListing.project_id)
            .where(MarketplaceListing.vendor_org_id == organization_id)
            .order_by(MarketplaceListing.created_at.desc())
        )
    ).all()
    return [{**_listing_dict(link), "title": project.title} for link, project in rows]


# --------------------------------------------------------------------------- #
# Superadmin: approve / revoke / list vendors
# --------------------------------------------------------------------------- #
@admin_router.get("/vendors")
async def list_vendors(
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """All vendor accounts (superadmin admin panel)."""
    rows = (
        await db.execute(
            select(VendorAccount, Organization)
            .join(Organization, Organization.id == VendorAccount.organization_id)
            .order_by(VendorAccount.created_at.desc())
        )
    ).all()
    return [
        {
            **_vendor_account_dict(va),
            "organization_name": org.display_name if org else None,
        }
        for va, org in rows
    ]


@admin_router.post("/vendors", status_code=201)
async def approve_vendor(
    body: VendorApprove,
    superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Approve an organization as a vendor (superadmin).

    Creating the ``VendorAccount`` row IS the approval; only then may the org's
    admins run Stripe Connect onboarding and publish. Idempotent — re-approving
    returns the existing row.
    """
    org = (
        await db.execute(
            select(Organization).where(Organization.id == body.organization_id)
        )
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = (
        await db.execute(
            select(VendorAccount).where(
                VendorAccount.organization_id == body.organization_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        if body.platform_fee_bps is not None:
            existing.platform_fee_bps = body.platform_fee_bps
            await db.commit()
            await db.refresh(existing)
        return _vendor_account_dict(existing)

    va = VendorAccount(
        id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        approved_at=datetime.now(timezone.utc),
        approved_by=str(superadmin.id),
        platform_fee_bps=body.platform_fee_bps,
        onboarding_status="pending",
    )
    db.add(va)
    await db.commit()
    await db.refresh(va)
    return _vendor_account_dict(va)


@admin_router.delete("/vendors/{organization_id}", status_code=204)
async def revoke_vendor(
    organization_id: str,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke a vendor approval (superadmin). Deleting the VendorAccount blocks
    new publishing; existing entitlements/listings are not cascaded here."""
    va = (
        await db.execute(
            select(VendorAccount).where(
                VendorAccount.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if va:
        await db.delete(va)
        await db.commit()
