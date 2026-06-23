"""
Organization management API endpoints — shared deps.

This package was split out of the former single-file ``routers/organizations.py``
(Tier 2.4 router decomposition). ``_common`` holds the shared imports, the
``router`` instance, the permission helpers, and the Pydantic schemas. The
endpoint handlers live in the sibling concern modules (``crud``, ``members``,
``manage``) and are aggregated in ``__init__``.
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from auth_module import get_current_user, require_user
from auth_module.user_service import delete_user as delete_user_service
from database import get_db
from models import Organization, OrganizationMembership, OrganizationRole, User

# Performance monitoring removed - cleanup

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def can_manage_organization(user: User, organization_id: str, db: Session) -> bool:
    """Check if user can manage the specified organization"""
    if not user:
        return False

    if user.is_superadmin:
        return True

    # Check if user is admin of the specific organization
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    return membership is not None


def can_create_organization(user: User, db: Session) -> bool:
    """Check if user can create organizations (superadmin or org admin of any organization)"""
    if not user:
        return False

    if user.is_superadmin:
        return True

    # Check if user is an admin of any organization
    admin_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    return admin_membership is not None


# Pydantic models for API
class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    settings: Optional[dict] = {}


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class OrganizationResponse(OrganizationBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    member_count: Optional[int] = None
    role: Optional[OrganizationRole] = None  # User's role in this organization

    class Config:
        from_attributes = True


class OrganizationMemberResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    role: OrganizationRole
    is_active: bool
    joined_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    email_verified: Optional[bool] = None
    email_verification_method: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateMemberRole(BaseModel):
    role: OrganizationRole


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (crud / members / manage) no longer need to repeat
# an explicit import block just to dodge F405 — this single list documents the
# full shared surface once. It is the FULL set of public names this module
# re-exports via ``*`` (every import above plus the module-level helpers,
# ``router`` and the Pydantic schemas), so the star binding is unchanged.
__all__ = [
    # stdlib / typing
    "datetime",
    "List",
    "Optional",
    "uuid4",
    # fastapi
    "APIRouter",
    "Depends",
    "HTTPException",
    "Query",
    "status",
    # pydantic
    "BaseModel",
    "Field",
    # sqlalchemy
    "func",
    "text",
    "Session",
    # auth_module
    "get_current_user",
    "require_user",
    "delete_user_service",
    # database
    "get_db",
    # models
    "Organization",
    "OrganizationMembership",
    "OrganizationRole",
    "User",
    # this module — helpers, router and schemas
    "router",
    "can_manage_organization",
    "can_create_organization",
    "OrganizationBase",
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "OrganizationMemberResponse",
    "UpdateMemberRole",
]
