"""Coding projects and code validations (the full API).

A coding project is an ordinary project made from a seeded sample of another
project's answers so they can be coded the Label Studio way: each task shows
one answer (``data.answer``, the full response or one parsed field) with
context copied from its task, the label config is the coding scheme, human
coders annotate it, and a judge system's generations on it are automatic
codes. A code validation compares one code (a text pattern code, a coder
plugin or a judge system) with the human codes of one control and records
the agreement with the code's identity hash; analysis runs accept a code
measure's ``validation`` only for that hash (``services/shared/analysis``).

Routes:

* ``POST /api/projects/{project_id}/coding-projects``: draw a sample of the
  project's answers into a new coding project (edit rights).
* ``GET /api/projects/{project_id}/coding-projects``: the coding projects
  drawn from the project.
* ``GET /api/projects/{project_id}/coding``: how a coding project was drawn
  (404 for any other project).
* ``POST /api/projects/{project_id}/code-validations``: validate a code on a
  coding project (edit rights on it); 202, runs on the ``analysis`` queue.
* ``GET /api/projects/{project_id}/code-validations``: the coding project's
  validations, newest first.
* ``GET /api/code-validations/{code_validation_id}``: one validation with its
  metrics; the per-task codes need full read access to the task content.
"""

from __future__ import annotations

import copy
import logging
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from celery_client import send_task_safe
from database import get_async_db
from models import CodeValidation, CodingProject, Generation, ResponseGeneration
from project_models import Project, Task
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    can_read_all_task_content_async,
    check_project_accessible_async,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["coding"])

MAX_CODING_TASKS = 20000
CANDIDATE_BATCH = 1000
MAX_CONTEXT_FIELDS = 20
MAX_VALUE_MAP = 500


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _invalid(errors: List[str], code: str = "invalid_coding_request") -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": code, "message": "The request is invalid", "errors": errors},
    )


# --------------------------------------------------------------------------
# Coding scheme helpers
# --------------------------------------------------------------------------


def scheme_controls(label_config: str) -> Tuple[List[str], bool]:
    """``(control names, binds $answer)`` of a (validated) label config."""
    from label_config_repeater import ANSWER_CONTROL_TAGS

    try:
        root = ET.fromstring(label_config)
    except ET.ParseError:
        return [], False
    names = [e.get("name") for e in root.iter() if e.tag in ANSWER_CONTROL_TAGS and e.get("name")]
    binds = any(v == "$answer" for e in root.iter() for v in e.attrib.values())
    return names, binds


def _answer_source(raw: Any, errors: List[str]) -> Any:
    if raw is None or raw == "answer":
        return "answer"
    if isinstance(raw, Mapping) and set(raw) == {"field"} and isinstance(raw["field"], str) and raw["field"]:
        return {"field": raw["field"]}
    errors.append("/answer: use \"answer\" (the full response) or {\"field\": \"<control name>\"}")
    return "answer"


def _string_list(raw: Any, where: str, errors: List[str], limit: int = 200) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw) or len(raw) > limit:
        errors.append(f"{where}: must be a list of at most {limit} non-empty strings")
        return []
    return list(dict.fromkeys(raw))


def parse_coding_request(body: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a create-coding-project body (422 with every problem)."""
    from services.label_config.validator import LabelConfigValidator

    errors: List[str] = []
    title = body.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 255:
        errors.append("/title: a non-empty title of at most 255 characters")
    description = body.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 5000):
        errors.append("/description: at most 5000 characters")
    label_config = body.get("label_config")
    if not isinstance(label_config, str) or not label_config.strip():
        errors.append("/label_config: the coding scheme (a label config) is required")
        controls: List[str] = []
    else:
        ok, problems = LabelConfigValidator.validate(label_config)
        controls = []
        if not ok:
            errors.extend(f"/label_config: {p}" for p in problems)
        else:
            controls, binds = scheme_controls(label_config)
            if not controls:
                errors.append("/label_config: the coding scheme has no control to code with")
            if not binds:
                errors.append("/label_config: the coding scheme must show the answer (value=\"$answer\")")
    answer = _answer_source(body.get("answer"), errors)
    context_fields = _string_list(body.get("context_fields"), "/context_fields", errors, MAX_CONTEXT_FIELDS)
    if "answer" in context_fields:
        errors.append("/context_fields: 'answer' is where the coded answer goes")
    sample = body.get("sample")
    if not isinstance(sample, Mapping):
        errors.append("/sample: required, {\"seed\": <int>, \"size\": <int>, ...}")
        sample = {}
    allowed = {"seed", "size", "designs", "systems", "structures"}
    extra = sorted(set(sample) - allowed)
    if extra:
        errors.append(f"/sample: unknown key(s) {', '.join(extra)}")
    seed = sample.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        errors.append("/sample/seed: a whole number >= 0 (the sample is drawn from it)")
    size = sample.get("size")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_CODING_TASKS):
        errors.append(f"/sample/size: a whole number from 1 to {MAX_CODING_TASKS} (omit it for every answer)")
    filters = {
        key: _string_list(sample.get(key), f"/sample/{key}", errors)
        for key in ("designs", "systems", "structures")
        if sample.get(key) is not None
    }
    if errors:
        raise _invalid(errors)
    return {
        "title": title.strip(),
        "description": description,
        "label_config": label_config,
        "answer": answer,
        "context_fields": context_fields,
        "seed": seed,
        "size": size,
        "filters": filters,
    }


# --------------------------------------------------------------------------
# Drawing the sample
# --------------------------------------------------------------------------


def _answer_text(answer_source: Any, response_content: Any, parsed: Any) -> Optional[str]:
    from analysis.codes import text_of
    from analysis.observations import typed_field_values

    if answer_source == "answer":
        text = response_content
    else:
        text = text_of(typed_field_values(parsed).get(answer_source["field"]))
    return text if isinstance(text, str) and text.strip() else None


async def _candidates(db: AsyncSession, project_id: str, filters: Mapping[str, List[str]]) -> List[str]:
    """Completed generations of the project matching the filters."""
    from analysis.db_source import response_metadata_object

    stmt = (
        select(Generation.id, Generation.model_id, Generation.response_metadata)
        .join(Task, Task.id == Generation.task_id)
        .join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
        .where(Task.project_id == project_id)
        .where(Generation.status == "completed")
    )
    if filters.get("designs"):
        stmt = stmt.where(cast(Task.meta, JSONB)["variant"]["design"].astext.in_(filters["designs"]))
    if filters.get("structures"):
        stmt = stmt.where(ResponseGeneration.structure_key.in_(filters["structures"]))
    systems = set(filters.get("systems") or [])
    out = []
    for gid, model_id, metadata in (await db.execute(stmt)).all():
        if systems:
            block = (response_metadata_object(metadata) or {}).get("system")
            key = block.get("key") if isinstance(block, Mapping) else None
            if model_id not in systems and key not in systems:
                continue
        out.append(gid)
    return out


async def _draw(
    db: AsyncSession, request: Mapping[str, Any], candidates: Sequence[str]
) -> List[Dict[str, Any]]:
    """The sample: candidates in seeded rank order, keeping those with a
    usable answer text, until ``size`` (or all) are drawn."""
    from analysis.coding import draw_sample

    ranked = draw_sample(candidates, request["seed"])
    size = request["size"]
    drawn: List[Dict[str, Any]] = []
    for start in range(0, len(ranked), CANDIDATE_BATCH):
        batch = ranked[start : start + CANDIDATE_BATCH]
        ids = [g for g, _ in batch]
        rows = (
            await db.execute(
                select(
                    Generation.id,
                    Generation.task_id,
                    Generation.response_content,
                    Generation.parsed_annotation,
                    Task.data,
                ).join(Task, Task.id == Generation.task_id).where(Generation.id.in_(ids))
            )
        ).all()
        by_id = {r.id: r for r in rows}
        for gid, rank in batch:
            row = by_id.get(gid)
            if row is None:
                continue
            text = _answer_text(request["answer"], row.response_content, row.parsed_annotation)
            if text is None:
                continue
            data = row.data if isinstance(row.data, Mapping) else {}
            drawn.append(
                {
                    "generation_id": gid,
                    "task_id": row.task_id,
                    "rank": rank,
                    "answer": text,
                    "context": {k: data[k] for k in request["context_fields"] if k in data},
                }
            )
            if size is not None and len(drawn) >= size:
                return drawn
    return drawn


def _refresh_summary_sync(project_id: str) -> None:
    from aggregate_summaries import refresh_project_summary
    from database import SessionLocal

    sync_db = SessionLocal()
    try:
        refresh_project_summary(sync_db, project_id)
    finally:
        sync_db.close()


def serialize_coding_project(row: CodingProject, project: Optional[Project] = None, tasks: Optional[int] = None) -> Dict[str, Any]:
    out = {
        "project_id": row.project_id,
        "source_project_id": row.source_project_id,
        "answer": row.answer_source,
        "context_fields": row.context_fields,
        "sample": row.sample,
        "coding_version": row.coding_version,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
    }
    if project is not None:
        out["title"] = project.title
    if tasks is not None:
        out["tasks"] = tasks
    return out


@router.post("/api/projects/{project_id}/coding-projects", status_code=201)
async def create_coding_project(
    project_id: str,
    body: Dict[str, Any] = Body(...),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Draw a seeded sample of the project's answers into a new coding
    project. The new project is private to its creator: it joins none of
    the source's organizations or groups, coders are added through the
    project's members, and a source that requires the Safe Exam Browser
    gives a coding project that requires it too."""
    from analysis.coding import CODING_VERSION, sample_hash

    source = access.project
    if not await can_read_all_task_content_async(db, access.user, source):
        raise HTTPException(status_code=403, detail="Coding projects copy answers: needs full read access")
    request = parse_coding_request(body)
    candidates = await _candidates(db, source.id, request["filters"])
    if request["size"] is None and len(candidates) > MAX_CODING_TASKS:
        raise _invalid(
            [f"/sample/size: {len(candidates)} answers match; a coding project holds at most "
             f"{MAX_CODING_TASKS}, so give a size or narrow the filters"],
            "coding_sample_too_large",
        )
    drawn = await _draw(db, request, candidates)
    if not drawn:
        raise _invalid(["/sample: no completed answer with a usable text matches"], "empty_coding_sample")

    new_id = str(uuid.uuid4())
    project = Project(
        id=new_id,
        title=request["title"],
        description=request["description"],
        created_by=access.user.id,
        label_config=request["label_config"],
        is_private=True,
        is_public=False,
        seb_required=bool(source.seb_required),
        seb_config=copy.deepcopy(source.seb_config) if source.seb_required else None,
    )
    db.add(project)
    await db.flush()
    for i, d in enumerate(drawn):
        db.add(
            Task(
                id=str(uuid.uuid4()),
                project_id=new_id,
                data={"answer": d["answer"], **d["context"]},
                meta={
                    "coding": {
                        "source_project_id": source.id,
                        "source_task_id": d["task_id"],
                        "source_generation_id": d["generation_id"],
                        "answer_source": request["answer"],
                        "sample_seed": request["seed"],
                        "sample_rank": d["rank"],
                    }
                },
                inner_id=i + 1,
                created_by=access.user.id,
            )
        )
    sample = {
        "seed": request["seed"],
        "size": request["size"],
        "filters": request["filters"],
        "candidates": len(candidates),
        "drawn": len(drawn),
        "hash": sample_hash(d["generation_id"] for d in drawn),
    }
    row = CodingProject(
        project_id=new_id,
        source_project_id=source.id,
        answer_source=request["answer"],
        context_fields=request["context_fields"],
        sample=sample,
        coding_version=CODING_VERSION,
        created_by=access.user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    try:
        await run_in_threadpool(_refresh_summary_sync, new_id)
    except Exception as exc:  # noqa: BLE001 - the hourly recompute catches up
        logger.warning("coding project %s: summary refresh failed: %s", new_id, exc)
    return serialize_coding_project(row, project, len(drawn))


@router.get("/api/projects/{project_id}/coding-projects")
async def list_coding_projects(
    project_id: str,
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    """The coding projects drawn from this project that the caller can open."""
    rows = (
        await db.execute(
            select(CodingProject, Project)
            .join(Project, Project.id == CodingProject.project_id)
            .where(CodingProject.source_project_id == project_id)
            .where(Project.deleted_at.is_(None))
            .order_by(CodingProject.created_at.desc(), CodingProject.project_id)
        )
    ).all()
    items = []
    for row, project in rows:
        if await check_project_accessible_async(db, access.user, project.id, project=project):
            items.append(serialize_coding_project(row, project))
    return {"items": items, "total": len(items)}


async def _coding_row(db: AsyncSession, project_id: str) -> CodingProject:
    row = (
        await db.execute(select(CodingProject).where(CodingProject.project_id == project_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not a coding project")
    return row


@router.get("/api/projects/{project_id}/coding")
async def get_coding_project(
    project_id: str,
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    row = await _coding_row(db, project_id)
    tasks = (
        await db.execute(select(func.count()).select_from(Task).where(Task.project_id == project_id))
    ).scalar_one()
    return serialize_coding_project(row, access.project, tasks)


# --------------------------------------------------------------------------
# Code validations
# --------------------------------------------------------------------------


def serialize_validation(v: CodeValidation, *, detail: bool = True, items: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": v.id,
        "project_id": v.project_id,
        "source_project_id": v.source_project_id,
        "name": v.name,
        "status": v.status,
        "control": v.control,
        "code_kind": v.code_kind,
        "code_ref": v.code_ref,
        "code_version": v.code_version,
        "code_hash": v.code_hash,
        "n_items": v.n_items,
        "n_compared": v.n_compared,
        "kappa": v.kappa,
        "observed_agreement": v.observed_agreement,
        "error_message": v.error_message,
        "created_by": v.created_by,
        "created_at": _iso(v.created_at),
        "started_at": _iso(v.started_at),
        "completed_at": _iso(v.completed_at),
    }
    if detail:
        out.update(
            code=v.code,
            normalized_code=v.normalized_code,
            identity=v.identity,
            options=v.options,
            coding_version=v.coding_version,
            metrics=v.metrics,
            warnings=v.warnings,
        )
    if items:
        out["items"] = v.items
    return out


def parse_validation_request(body: Mapping[str, Any], coding: CodingProject, controls: List[str]) -> Dict[str, Any]:
    from analysis.coding import CodingError, normalize_validation_code

    errors: List[str] = []
    control = body.get("control")
    if not isinstance(control, str) or not control:
        errors.append("/control: name the control of the coding scheme the code is compared on")
    elif control not in controls:
        errors.append(f"/control: the coding scheme has no control {control!r} (it has {', '.join(controls) or 'none'})")
    name = body.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
        errors.append("/name: a non-empty name of at most 200 characters")
    missing = body.get("missing", "category")
    if missing not in ("category", "exclude"):
        errors.append("/missing: 'category' (a missing automatic code disagrees) or 'exclude'")
    value_map = body.get("value_map") or {}
    if not isinstance(value_map, Mapping) or len(value_map) > MAX_VALUE_MAP or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in value_map.items()
    ):
        errors.append(f"/value_map: an object of at most {MAX_VALUE_MAP} code values to scheme values (strings)")
        value_map = {}
    normalized = None
    if "code" not in body:
        errors.append("/code: the code to validate is required")
    else:
        try:
            normalized = normalize_validation_code(
                body["code"], coding_project_id=coding.project_id, answer_source=coding.answer_source
            )
        except CodingError as exc:
            errors.extend(exc.errors)
    if errors:
        raise _invalid(errors, "invalid_code_validation")
    if normalized["kind"] == "judge_code":
        normalized.setdefault("field", control)
    return {
        "control": control,
        "name": (name or f"{normalized['kind']} on {control}").strip()[:200],
        "code": body["code"],
        "normalized": normalized,
        "options": {"missing": missing, "value_map": dict(value_map)},
    }


@router.post("/api/projects/{project_id}/code-validations", status_code=202)
async def start_code_validation(
    project_id: str,
    body: Dict[str, Any] = Body(...),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Validate a code on this coding project: ``{"code": {...}, "control":
    "<scheme control>", "name"?, "value_map"?, "missing"?}``."""
    from analysis.coding import CODING_VERSION

    coding = await _coding_row(db, project_id)
    controls, _ = scheme_controls(access.project.label_config or "")
    request = parse_validation_request(body, coding, controls)
    v = CodeValidation(
        project_id=project_id,
        source_project_id=coding.source_project_id,
        created_by=access.user.id,
        name=request["name"],
        status="pending",
        control=request["control"],
        code=request["code"],
        normalized_code=request["normalized"],
        code_kind=request["normalized"]["kind"],
        options=request["options"],
        coding_version=CODING_VERSION,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    try:
        result = send_task_safe("tasks.run_code_validation", args=[v.id])
        v.celery_task_id = getattr(result, "id", None)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - the broker is unreachable
        logger.error("code validation %s could not be queued: %s", v.id, exc)
        v.status = "failed"
        v.error_message = "The analysis queue is unavailable; start the validation again."
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={"code": "analysis_queue_unavailable", "message": v.error_message},
        )
    await db.refresh(v)
    return JSONResponse(
        status_code=202,
        content=serialize_validation(v),
        headers={"Location": f"/api/code-validations/{v.id}"},
    )


@router.get("/api/projects/{project_id}/code-validations")
async def list_code_validations(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(CodeValidation).where(CodeValidation.project_id == project_id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(CodeValidation)
            .where(CodeValidation.project_id == project_id)
            .order_by(CodeValidation.created_at.desc(), CodeValidation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return {"items": [serialize_validation(v, detail=False) for v in rows], "total": total}


async def load_validation_for_read(db: AsyncSession, user, validation_id: str) -> Tuple[CodeValidation, Project]:
    """The validation if the user can read its coding project; 404 otherwise."""
    v = (
        await db.execute(select(CodeValidation).where(CodeValidation.id == validation_id))
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="Code validation not found")
    project = (await db.execute(select(Project).where(Project.id == v.project_id))).scalar_one_or_none()
    if project is None or (project.deleted_at is not None and not user.is_superadmin):
        raise HTTPException(status_code=404, detail="Code validation not found")
    if not await check_project_accessible_async(db, user, project.id, project=project):
        raise HTTPException(status_code=404, detail="Code validation not found")
    return v, project


@router.get("/api/code-validations/{code_validation_id}")
async def get_code_validation(
    code_validation_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """One validation with its metrics; ``items`` (the per-task automatic
    and human codes) only for callers with full read access to the task
    content."""
    v, project = await load_validation_for_read(db, current_user, code_validation_id)
    full = await can_read_all_task_content_async(db, current_user, project)
    return serialize_validation(v, items=full)


# --------------------------------------------------------------------------
# References from analysis specs
# --------------------------------------------------------------------------


async def check_spec_code_references(db: AsyncSession, user, project_id: str, normalized: Mapping[str, Any]) -> List[str]:
    """Problems with the coding projects and validations a spec names: each
    must exist, belong to this project's answers and be readable by the
    caller."""
    errors: List[str] = []
    for mid, m in (normalized.get("measures") or {}).items():
        where = f"/measures/{mid}"
        if m.get("kind") == "judge_code":
            row = (
                await db.execute(select(CodingProject).where(CodingProject.project_id == m["coding_project"]))
            ).scalar_one_or_none()
            if row is None or row.source_project_id != project_id or not await check_project_accessible_async(
                db, user, row.project_id
            ):
                errors.append(f"{where}/coding_project: not a coding project drawn from this project")
        vid = m.get("validation")
        if vid:
            v = (await db.execute(select(CodeValidation).where(CodeValidation.id == vid))).scalar_one_or_none()
            if v is None or v.source_project_id != project_id or not await check_project_accessible_async(
                db, user, v.project_id
            ):
                errors.append(f"{where}/validation: not a validation of this project's answers")
    return errors
