"""API endpoints for org-level S3 storage connections (cloud imports).

Mirrors ``routers/org_api_keys.py``: async DB lane, the same inline org
permission helpers, and strict response masking — the secret key NEVER
appears in any response in any form, the access key only as a 4-char hint.
The S3 work itself lives in the shared
``org_storage_connection_service`` (also used by the import worker); its
blocking boto3 calls run in the threadpool so they don't stall the event
loop.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import org_storage_connection_service as storage_conn_service
from auth_module import User, require_user
from database import get_async_db
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrgStorageConnection,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["Organization Storage Connections"])


async def _require_org_admin(user: User, org_id: str, db: AsyncSession):
    """Raise 403 if user cannot manage the organization.

    Same inline membership lookup as ``routers.org_api_keys._require_org_admin``
    (superadmin or active ORG_ADMIN membership) on the async lane.
    """
    if user.is_superadmin:
        return

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this organization",
        )


async def _require_org_member(user: User, org_id: str, db: AsyncSession):
    """Raise 403 if user is not a member of the organization (or superadmin)."""
    if user.is_superadmin:
        return

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


async def _require_org_exists(org_id: str, db: AsyncSession):
    """Raise 404 if organization does not exist."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


async def _load_connection(
    db: AsyncSession, org_id: str, conn_id: str
) -> OrgStorageConnection:
    """Fetch a connection scoped to the org, or 404.

    Org mismatch is a 404 (not 403) so connection-id existence doesn't leak
    across organizations.
    """
    result = await db.execute(
        select(OrgStorageConnection).where(OrgStorageConnection.id == conn_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage connection not found",
        )
    return conn


def _serialize_connection(conn: OrgStorageConnection) -> dict:
    """Metadata-only view. Secrets NEVER leave the server; the access key id
    surfaces only as a last-4 hint."""
    return {
        "id": conn.id,
        "organization_id": conn.organization_id,
        "name": conn.name,
        "endpoint_url": conn.endpoint_url,
        "bucket": conn.bucket,
        "prefix": conn.prefix or "",
        "region": conn.region,
        "use_ssl": conn.use_ssl,
        "access_key_hint": storage_conn_service.access_key_hint(
            conn.encrypted_access_key
        ),
        "created_by": conn.created_by,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
    }


def _validated_endpoint_url(data: dict) -> Optional[str]:
    """Extract + validate ``endpoint_url`` from a request body (400 on bad)."""
    endpoint_url = data.get("endpoint_url")
    if endpoint_url is not None and not isinstance(endpoint_url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="endpoint_url must be a string or null",
        )
    endpoint_url = (endpoint_url or "").strip() or None
    try:
        storage_conn_service.validate_endpoint_url(endpoint_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return endpoint_url


def _required_str(data: dict, field: str, max_length: Optional[int] = None) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is required",
        )
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} must be at most {max_length} characters",
        )
    return value


def _encrypt_or_400(value: str, field: str) -> str:
    encrypted = storage_conn_service.encrypt_secret(value)
    if not encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} could not be stored; check its format",
        )
    return encrypted


async def _name_taken(
    db: AsyncSession, org_id: str, name: str, exclude_id: Optional[str] = None
) -> bool:
    stmt = select(OrgStorageConnection.id).where(
        OrgStorageConnection.organization_id == org_id,
        OrgStorageConnection.name == name,
    )
    if exclude_id:
        stmt = stmt.where(OrgStorageConnection.id != exclude_id)
    result = await db.execute(stmt)
    return result.first() is not None


# ===== CRUD =====


@router.get("/{org_id}/storage-connections")
async def list_storage_connections(
    org_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List the org's storage connections (metadata only). Any member."""
    await _require_org_exists(org_id, db)
    await _require_org_member(current_user, org_id, db)

    result = await db.execute(
        select(OrgStorageConnection)
        .where(OrgStorageConnection.organization_id == org_id)
        .order_by(OrgStorageConnection.created_at)
    )
    return [_serialize_connection(c) for c in result.scalars().all()]


@router.post("/{org_id}/storage-connections", status_code=201)
async def create_storage_connection(
    org_id: str,
    data: dict,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a storage connection. Admin only.

    Body: ``{name, endpoint_url?, bucket, prefix?, region?, use_ssl?,
    access_key, secret_key}``. Credentials are encrypted at rest and never
    returned.
    """
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    data = data or {}
    name = _required_str(data, "name", max_length=255)
    bucket = _required_str(data, "bucket")
    access_key = _required_str(data, "access_key")
    secret_key = _required_str(data, "secret_key")
    endpoint_url = _validated_endpoint_url(data)
    prefix = data.get("prefix") or ""
    if not isinstance(prefix, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="prefix must be a string"
        )
    region = data.get("region") or None
    use_ssl = bool(data.get("use_ssl", True))

    if await _name_taken(db, org_id, name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A storage connection with this name already exists",
        )

    conn = OrgStorageConnection(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        name=name,
        endpoint_url=endpoint_url,
        bucket=bucket,
        prefix=prefix,
        region=region,
        use_ssl=use_ssl,
        encrypted_access_key=_encrypt_or_400(access_key, "access_key"),
        encrypted_secret_key=_encrypt_or_400(secret_key, "secret_key"),
        created_by=current_user.id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _serialize_connection(conn)


@router.put("/{org_id}/storage-connections/{conn_id}")
async def update_storage_connection(
    org_id: str,
    conn_id: str,
    data: dict,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update a storage connection. Admin only.

    Credential fields are optional — omitted credentials keep the stored
    values. ``endpoint_url: null`` explicitly resets to the AWS default.
    """
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)
    conn = await _load_connection(db, org_id, conn_id)

    data = data or {}
    if "name" in data:
        name = _required_str(data, "name", max_length=255)
        if await _name_taken(db, org_id, name, exclude_id=conn.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A storage connection with this name already exists",
            )
        conn.name = name
    if "endpoint_url" in data:
        conn.endpoint_url = _validated_endpoint_url(data)
    if "bucket" in data:
        conn.bucket = _required_str(data, "bucket")
    if "prefix" in data:
        prefix = data.get("prefix") or ""
        if not isinstance(prefix, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="prefix must be a string",
            )
        conn.prefix = prefix
    if "region" in data:
        conn.region = data.get("region") or None
    if "use_ssl" in data:
        conn.use_ssl = bool(data.get("use_ssl"))
    if data.get("access_key"):
        conn.encrypted_access_key = _encrypt_or_400(
            _required_str(data, "access_key"), "access_key"
        )
    if data.get("secret_key"):
        conn.encrypted_secret_key = _encrypt_or_400(
            _required_str(data, "secret_key"), "secret_key"
        )

    await db.commit()
    await db.refresh(conn)
    return _serialize_connection(conn)


@router.delete("/{org_id}/storage-connections/{conn_id}")
async def delete_storage_connection(
    org_id: str,
    conn_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a storage connection. Admin only.

    Past cloud-import jobs keep their history row — the FK is SET NULL.
    """
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)
    conn = await _load_connection(db, org_id, conn_id)

    await db.delete(conn)
    await db.commit()
    return {"message": "Storage connection deleted"}


# ===== Connection tests =====


class _UnsavedParams:
    """Attribute view over unsaved connection params for the shared service."""

    def __init__(self, data: dict):
        self.endpoint_url = data.get("endpoint_url") or None
        self.bucket = data.get("bucket")
        self.prefix = data.get("prefix") or ""
        self.region = data.get("region") or None
        self.use_ssl = bool(data.get("use_ssl", True))
        self.encrypted_access_key = None
        self.encrypted_secret_key = None


@router.post("/{org_id}/storage-connections/test")
async def test_unsaved_storage_connection(
    org_id: str,
    data: dict,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Test unsaved connection params (pre-save "Test connection"). Admin only."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    data = data or {}
    bucket = _required_str(data, "bucket")  # noqa: F841 — validates presence
    access_key = _required_str(data, "access_key")
    secret_key = _required_str(data, "secret_key")
    _validated_endpoint_url(data)

    result = await run_in_threadpool(
        storage_conn_service.test_connection,
        _UnsavedParams(data),
        access_key=access_key,
        secret_key=secret_key,
    )
    return {
        "status": "success" if result["ok"] else "error",
        "message": result["message"],
    }


@router.post("/{org_id}/storage-connections/{conn_id}/test")
async def test_saved_storage_connection(
    org_id: str,
    conn_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Test a saved connection with its stored credentials. Admin only."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)
    conn = await _load_connection(db, org_id, conn_id)

    result = await run_in_threadpool(storage_conn_service.test_connection, conn)
    return {
        "status": "success" if result["ok"] else "error",
        "message": result["message"],
    }


# ===== Server-side browse =====


@router.get("/{org_id}/storage-connections/{conn_id}/objects")
async def browse_storage_connection(
    org_id: str,
    conn_id: str,
    prefix: Optional[str] = Query(None),
    continuation_token: Optional[str] = Query(None),
    max_results: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Browse one listing page of the connected bucket. Any org member.

    Server-side only — the browser never talks to the customer bucket and
    never sees credentials. The requested prefix is jailed to the
    connection's configured prefix (400 on escape attempts).
    """
    await _require_org_exists(org_id, db)
    await _require_org_member(current_user, org_id, db)
    conn = await _load_connection(db, org_id, conn_id)

    try:
        return await run_in_threadpool(
            storage_conn_service.list_objects,
            conn,
            prefix=prefix,
            continuation_token=continuation_token,
            max_keys=max_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.warning(
            "Storage browse failed for connection %s: %s", conn_id, type(exc).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not list objects on the storage connection",
        )
