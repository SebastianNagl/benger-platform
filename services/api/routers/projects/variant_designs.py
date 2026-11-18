"""Variant designs of a project (CORE 2.56): generic CRUD, checks, freeze,
export and import.

A design declares a variant experiment (factors, unit, slots, outcome, gold
and invariance bindings; ``schemas/variant_design.schema.json``); each task's
place in it is ``task.meta.variant``. The rules live in ``variant_designs``
(pure) and ``variant_design_guard`` (database); this module only routes.

Access: reading a design needs the full-data tier of the project (the roles
that see ``task.meta`` unblinded; a design tells which tasks are twins, so a
blinded annotator never reads it). Writing needs project edit rights.
Refusals carry ``{"detail": {"code", "message", "problems"?}}``.
"""

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import variant_designs as vd
from database import get_async_db
from project_models import Task, VariantDesign
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.tasks.blinding import annotator_bound_fields_or_none_async
from variant_design_guard import (
    VariantDesignError,
    export_document,
    freeze_design,
    new_design_row,
    run_checks,
    serialize_design,
    update_design_spec,
)

router = APIRouter()

_BASE = "/{project_id}/variant-designs"


class VariantDesignCreate(BaseModel):
    key: str = Field(..., description="Key of the design in the project (meta.variant.design)")
    spec: Dict[str, Any] = Field(..., description="schemas/variant_design.schema.json")
    provenance: Optional[Dict[str, Any]] = None


class VariantDesignUpdate(BaseModel):
    spec: Dict[str, Any]
    expected_version: Optional[int] = Field(
        None, description="Refuse with 409 unless the stored version is this one"
    )
    provenance: Optional[Dict[str, Any]] = None


class VariantDesignImport(BaseModel):
    """An export document (``GET .../export``); imported as a draft."""

    format: str
    key: str
    spec: Dict[str, Any]
    version: Optional[int] = None
    status: Optional[str] = None
    content_hash: Optional[str] = None
    frozen_at: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None


async def _require_read(db: AsyncSession, access: ProjectAccess) -> None:
    if await annotator_bound_fields_or_none_async(db, access.user, access.project) is not None:
        raise HTTPException(status_code=403, detail="Access denied")


async def _load(db: AsyncSession, project_id: str, key: str) -> VariantDesign:
    row = (
        await db.execute(
            select(VariantDesign).where(
                VariantDesign.project_id == project_id, VariantDesign.key == key
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise VariantDesignError(404, "variant_design_not_found", f"No variant design {key!r}.")
    return row


async def _task_counts(db: AsyncSession, project_id: str) -> Dict[str, int]:
    rows = await db.execute(
        select(Task.variant_design, func.count(Task.id))
        .where(Task.project_id == project_id, Task.variant_design.isnot(None))
        .group_by(Task.variant_design)
    )
    return {key: count for key, count in rows.all()}


async def _run(db: AsyncSession, work: Callable[[Any], Any]) -> Any:
    """Run the shared sync service ``work(session)`` on the request's own
    session and connection (``run_sync``) and commit. The checks stream the
    tasks of a design with a server-side cursor."""
    try:
        result = await db.run_sync(work)
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


async def _create(
    db: AsyncSession, project_id: str, user_id: str, key: str, spec, provenance, version=1
) -> Dict[str, Any]:
    exists = (
        await db.execute(
            select(VariantDesign.id).where(
                VariantDesign.project_id == project_id, VariantDesign.key == key
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise VariantDesignError(
            409, "variant_design_exists", f"The project already has a variant design {key!r}."
        )
    row = new_design_row(
        project_id, key, spec, created_by=user_id, provenance=provenance, version=version
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise VariantDesignError(
            409, "variant_design_exists", f"The project already has a variant design {key!r}."
        )
    await db.refresh(row)
    return serialize_design(row, task_count=0)


@router.get(_BASE)
async def list_variant_designs(
    project_id: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """The project's variant designs with their task counts."""
    await _require_read(db, access)
    rows = (
        await db.execute(
            select(VariantDesign)
            .where(VariantDesign.project_id == project_id)
            .order_by(VariantDesign.key)
        )
    ).scalars().all()
    counts = await _task_counts(db, project_id)
    return {"items": [serialize_design(r, task_count=counts.get(r.key, 0)) for r in rows]}


@router.post(_BASE, status_code=201)
async def create_variant_design(
    project_id: str,
    body: VariantDesignCreate,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
):
    """Create a draft design. 422 with ``problems`` when key or spec is invalid."""
    return await _create(db, project_id, str(access.user.id), body.key, body.spec, body.provenance)


@router.post(f"{_BASE}/import", status_code=201)
async def import_variant_design(
    project_id: str,
    body: VariantDesignImport,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
):
    """Create a draft from an export document. A frozen export arrives as a
    draft: its tasks come with a project or task import, which freezes it
    again when it carries the design (and the hash must then match)."""
    if body.format != vd.EXPORT_FORMAT:
        raise VariantDesignError(
            422,
            "variant_design_format",
            f"Expected an export document of format {vd.EXPORT_FORMAT!r}.",
        )
    return await _create(
        db,
        project_id,
        str(access.user.id),
        body.key,
        body.spec,
        body.provenance,
        version=body.version or 1,
    )


@router.get(f"{_BASE}/{{key}}")
async def get_variant_design(
    project_id: str,
    key: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    await _require_read(db, access)
    row = await _load(db, project_id, key)
    counts = await _task_counts(db, project_id)
    return serialize_design(row, task_count=counts.get(key, 0))


@router.get(f"{_BASE}/{{key}}/export")
async def export_variant_design(
    project_id: str,
    key: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """The design as a portable document (the assignments travel with the
    tasks in ``meta.variant``)."""
    await _require_read(db, access)
    return export_document(await _load(db, project_id, key))


@router.put(f"{_BASE}/{{key}}")
async def update_variant_design(
    project_id: str,
    key: str,
    body: VariantDesignUpdate,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
):
    """Replace the spec of a draft (the version goes up by one). 409 on a
    frozen design or a version mismatch; 422 when the spec is invalid or a
    task already in the design does not fit it."""
    await _load(db, project_id, key)
    sent = body.model_fields_set

    def _work(sync_db):
        row = update_design_spec(
            sync_db,
            project_id,
            key,
            body.spec,
            expected_version=body.expected_version,
            provenance=body.provenance,
            set_provenance="provenance" in sent,
        )
        return serialize_design(row)

    return await _run(db, _work)


@router.delete(f"{_BASE}/{{key}}", status_code=204)
async def delete_variant_design(
    project_id: str,
    key: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
):
    """Delete a draft that no task names. A frozen design is kept for good."""
    row = await _load(db, project_id, key)
    if row.status == vd.STATUS_FROZEN:
        raise VariantDesignError(
            409, "variant_design_frozen", f"The variant design {key!r} is frozen."
        )
    count = (await _task_counts(db, project_id)).get(key, 0)
    if count:
        raise VariantDesignError(
            409,
            "variant_design_in_use",
            f"{count} task(s) name the variant design {key!r}; remove their "
            "meta.variant or delete them first.",
            task_count=count,
        )
    await db.delete(row)
    await db.commit()


@router.post(f"{_BASE}/{{key}}/check")
async def check_variant_design(
    project_id: str,
    key: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """Run the assignment, balance and span-invariance checks without
    changing anything; ``content_hash`` is what a freeze would record."""
    await _require_read(db, access)
    await _load(db, project_id, key)

    def _work(sync_db):
        from variant_design_guard import load_design

        report, digest = run_checks(sync_db, load_design(sync_db, project_id, key))
        return {"report": report, "content_hash": digest}

    return await _run(db, _work)


@router.post(f"{_BASE}/{{key}}/freeze")
async def freeze_variant_design(
    project_id: str,
    key: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
):
    """Freeze the design when every check passes: records the content hash
    and makes the tasks' ``data`` and ``meta.variant`` read-only (409 on any
    later edit). 409 with the report when a check fails."""
    await _load(db, project_id, key)
    user_id = str(access.user.id)

    def _work(sync_db):
        row, report = freeze_design(sync_db, project_id, key, user_id)
        return {"design": serialize_design(row), "report": report}

    return await _run(db, _work)
