"""Re-parse stored generations with the current response parser.

Generation parses an answer once, when it is written
(``services/workers/generation/llm_generation_service.py``). When the parser
later learns to read more answers (the ``answer``/``reasoning`` key aliases
of ``response_parser.ENGLISH_KEY_ALIASES``), answers already stored keep
their old parse result. This route re-reads given stored answers with the
parser exactly as a new answer gets it: the project's current label config,
the prompt structure the generation ran with, the task's text as span
source. ``response_content`` is never changed, so an answer the parser
cannot read (invalid JSON, misspelled keys) stays unparsed.

A changed result supersedes the previous one: the previous parse fields are
kept in ``parse_metadata["reparse_history"]`` with who re-parsed and when.
An answer whose result does not change is not written, so calling the route
again is a no-op. Scores computed from the old parse are not touched;
re-run the evaluations for these generations through the evaluation routes.
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annotation_utils import extract_all_field_values
from auth_module import require_superadmin
from auth_module.models import User as AuthUser
from database import get_async_db
from feature_flags.deps import flag_on
from feature_flags.registry import VARIANT_EXPERIMENTS
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project, Task
from generation_fidelity import answer_format, render_answer_schema
from response_parser import ResponseParser, find_prompt_structure

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_REPARSE_IDS = 1000

#: Row statuses that only record the parse outcome; generation sets them from
#: the parse status (``completed`` on success, else ``parse_failed`` or, after
#: the retry limit, ``parse_failed_max_retries``). Other statuses (a failed
#: call, a cancelled run) are left as they are.
_PARSE_ROW_STATUSES = {"completed", "parse_failed", "parse_failed_max_retries"}


class ReparseRequest(BaseModel):
    generation_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_REPARSE_IDS,
        description="Ids of stored generations (one answer each) of this project.",
    )
    dry_run: bool = Field(
        False, description="Report the old and new parse result without writing."
    )

    @field_validator("generation_ids")
    @classmethod
    def _dedupe(cls, ids: List[str]) -> List[str]:
        return list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))


class ParseState(BaseModel):
    parse_status: Optional[str] = None
    parse_error: Optional[str] = None
    status: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    mapped_keys: Dict[str, str] = Field(default_factory=dict)


class ReparseItem(BaseModel):
    generation_id: str
    outcome: Literal["changed", "unchanged", "not_found", "skipped"]
    reason: Optional[str] = None
    before: Optional[ParseState] = None
    after: Optional[ParseState] = None


class ReparseResponse(BaseModel):
    project_id: str
    dry_run: bool
    changed: int
    unchanged: int
    not_found: int
    skipped: int
    results: List[ReparseItem]


def _fields(parsed_annotation: Any) -> Dict[str, Any]:
    if not isinstance(parsed_annotation, list):
        return {}
    try:
        return extract_all_field_values(parsed_annotation)
    except Exception:  # a malformed stored annotation still reports
        return {}


def _mapped_keys(parse_metadata: Any) -> Dict[str, str]:
    if isinstance(parse_metadata, dict) and isinstance(parse_metadata.get("mapped_keys"), dict):
        return dict(parse_metadata["mapped_keys"])
    return {}


def _without_span_ids(value: Any) -> Any:
    """The annotation without the random ids the parser gives new spans, so
    re-parsing a span answer twice compares equal."""
    if isinstance(value, list):
        return [_without_span_ids(v) for v in value]
    if isinstance(value, dict):
        return {
            k: _without_span_ids(v)
            for k, v in value.items()
            if not (k == "id" and isinstance(v, str) and v.startswith("span-"))
        }
    return value


def _new_row_status(old_status: Optional[str], parse_status: str) -> Optional[str]:
    if old_status not in _PARSE_ROW_STATUSES:
        return old_status
    if parse_status == "success":
        return "completed"
    return old_status if old_status != "completed" else "parse_failed"


@router.post("/{project_id}/generations/reparse", response_model=ReparseResponse)
async def reparse_generations(
    project_id: str,
    body: ReparseRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: AuthUser = Depends(require_superadmin),
) -> ReparseResponse:
    """Re-parse stored generations of a project with the current parser.

    Superadmin only (an access key needs ``admin:platform``). With
    ``dry_run`` nothing is written. Otherwise each generation whose parse
    result changes gets the new ``parsed_annotation``, ``parse_status``,
    ``parse_error`` and ``mapped_keys``, the row status follows the parse
    status as in generation, and the previous values are appended to
    ``parse_metadata["reparse_history"]``.
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None or getattr(project, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.label_config:
        raise HTTPException(
            status_code=422,
            detail="The project has no label config, so its answers are not parsed.",
        )

    query = (
        select(DBGeneration, DBResponseGeneration.structure_key)
        .join(DBResponseGeneration, DBGeneration.generation_id == DBResponseGeneration.id)
        .where(
            DBGeneration.id.in_(body.generation_ids),
            DBResponseGeneration.project_id == project_id,
        )
    )
    if not body.dry_run:
        query = query.with_for_update(of=DBGeneration)
    rows = {gen.id: (gen, key) for gen, key in (await db.execute(query)).all()}

    task_ids = {gen.task_id for gen, _ in rows.values() if gen.task_id}
    task_data: Dict[str, Any] = {}
    if task_ids:
        for tid, data in (
            await db.execute(select(Task.id, Task.data).where(Task.id.in_(task_ids)))
        ).all():
            task_data[tid] = data

    parsers: Dict[Optional[str], ResponseParser] = {}
    now = datetime.now(timezone.utc).isoformat()
    # Parse as generation does for this caller: with variant_experiments off
    # (core 2.71) without the answer-format options and the per-item parsing.
    experiments = await flag_on(db, current_user, VARIANT_EXPERIMENTS)
    results: List[ReparseItem] = []

    for gid in body.generation_ids:
        if gid not in rows:
            results.append(ReparseItem(generation_id=gid, outcome="not_found"))
            continue
        gen, structure_key = rows[gid]
        before = ParseState(
            parse_status=gen.parse_status,
            parse_error=gen.parse_error,
            status=gen.status,
            fields=_fields(gen.parsed_annotation),
            mapped_keys=_mapped_keys(gen.parse_metadata),
        )

        if structure_key not in parsers:
            structure: Optional[Dict] = {}
            if structure_key:
                structure = find_prompt_structure(project.generation_config, structure_key)
            if structure is None:
                parsers[structure_key] = None
            else:
                parsers[structure_key] = ResponseParser(
                    generation_structure=structure or {},
                    label_config=project.label_config,
                    variant_experiments=experiments,
                )
        parser = parsers[structure_key]
        if parser is None:
            results.append(
                ReparseItem(
                    generation_id=gid,
                    outcome="skipped",
                    reason=f"Prompt structure '{structure_key}' is no longer in the project",
                    before=before,
                )
            )
            continue

        data = task_data.get(gen.task_id)
        source_text = data.get("text") if isinstance(data, dict) else None
        try:
            # A structure whose answer keys depend on the task is read with
            # the keys rendered for this task, as generation did.
            answer_schema = (
                answer_format(parser.generation_structure).answer_schema if experiments else None
            )
            if answer_schema:
                parser = ResponseParser(
                    generation_structure=parser.generation_structure,
                    label_config=project.label_config,
                    answer_keys=render_answer_schema(
                        answer_schema, data if isinstance(data, dict) else {}
                    ),
                    variant_experiments=experiments,
                )
            parsed = parser.parse(
                gen.response_content or "",
                source_text=source_text,
                task_data=data if isinstance(data, dict) else {},
            )
            new_annotation = parsed.parsed_annotation
            new_status, new_error = parsed.status, parsed.error
            new_mapped = dict(parsed.mapped_keys or {})
            new_mapped_values = dict(getattr(parsed, "mapped_values", None) or {})
        except Exception as e:  # as in generation: a parser crash is a failed parse
            new_annotation, new_status = None, "failed"
            new_error, new_mapped = f"Parser exception: {str(e)}", {}
            new_mapped_values = {}

        after = ParseState(
            parse_status=new_status,
            parse_error=new_error,
            status=_new_row_status(gen.status, new_status),
            fields=_fields(new_annotation),
            mapped_keys=new_mapped,
        )
        unchanged = (
            _without_span_ids(new_annotation) == _without_span_ids(gen.parsed_annotation)
            and new_status == gen.parse_status
            and new_error == gen.parse_error
            and new_mapped == before.mapped_keys
            and after.status == gen.status
        )
        if unchanged:
            results.append(
                ReparseItem(generation_id=gid, outcome="unchanged", before=before, after=after)
            )
            continue

        results.append(
            ReparseItem(generation_id=gid, outcome="changed", before=before, after=after)
        )
        if body.dry_run:
            continue

        metadata = (
            copy.deepcopy(gen.parse_metadata) if isinstance(gen.parse_metadata, dict) else {}
        )
        history = metadata.get("reparse_history")
        history = list(history) if isinstance(history, list) else []
        history.append(
            {
                "reparsed_at": now,
                "reparsed_by": current_user.id,
                "superseded": {
                    "parsed_annotation": copy.deepcopy(gen.parsed_annotation),
                    "parse_status": gen.parse_status,
                    "parse_error": gen.parse_error,
                    "status": gen.status,
                    "mapped_keys": before.mapped_keys,
                    "label_config_version": gen.label_config_version,
                    "label_config_snapshot": gen.label_config_snapshot,
                },
            }
        )
        metadata["reparse_history"] = history
        if new_mapped:
            metadata["mapped_keys"] = new_mapped
        else:
            metadata.pop("mapped_keys", None)
        if new_mapped_values:
            metadata["mapped_values"] = new_mapped_values
        else:
            metadata.pop("mapped_values", None)

        gen.parsed_annotation = new_annotation
        gen.parse_status = new_status
        gen.parse_error = new_error
        gen.status = after.status
        gen.parse_metadata = metadata
        gen.label_config_version = project.label_config_version
        gen.label_config_snapshot = project.label_config

    if not body.dry_run:
        await db.commit()
        logger.info(
            "Re-parsed generations of project %s by %s: %s",
            project_id,
            current_user.id,
            {r.generation_id: r.outcome for r in results},
        )

    counts = {k: sum(1 for r in results if r.outcome == k) for k in ("changed", "unchanged", "not_found", "skipped")}
    return ReparseResponse(project_id=project_id, dry_run=body.dry_run, results=results, **counts)
