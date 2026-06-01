"""Project import and export endpoints."""

import csv
import io
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import ijson

# Spool incoming import bodies in RAM up to this size; spill to disk above it.
# Keeps small imports allocation-free (no disk hit, no regression vs the
# previous Pydantic auto-parse path) while bounding peak heap on multi-MB
# imports — the API-side mirror of the proxy's response-streaming fix (GH #68).
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024

# Flush + expunge inserted rows every N tasks so the SQLAlchemy identity map
# (and thus peak heap) stays O(batch) instead of O(file) during a large import.
_IMPORT_BATCH = 200

# Small top-level keys of the nested (Label-Studio) import payload that are safe
# to fully materialize. The big `data` array is streamed separately via
# iter_array, never built into RAM. Mirrors ProjectImportData's optional fields.
_NESTED_SMALL_KEYS = frozenset({
    "meta",
    "evaluation_runs",
    "human_evaluation_configs",
    "human_evaluation_sessions",
    "human_evaluation_results",
    "preference_rankings",
    "likert_scale_evaluations",
    "korrektur_comments",
})

logger = logging.getLogger(__name__)


def _stream_rows(db, spooled, path: str, batch: int = _IMPORT_BATCH):
    """Yield each element of a top-level array in the spooled JSON one at a time.

    Every ``batch`` rows the session is flushed then expunged so the SQLAlchemy
    identity map (and thus peak heap) stays O(batch) rather than O(file) on a
    multi-GB import. Flushing *before* expunging is load-bearing: it guarantees
    any rows still pending from an earlier entity loop are INSERTed (rather than
    silently dropped by ``expunge_all``) before a later loop's children
    FK-reference them. Cross-references travel via string id maps, never live
    ORM objects, so detaching the just-inserted rows is safe.
    """
    n = 0
    for row in iter_array(spooled, path):
        yield row
        n += 1
        if n % batch == 0:
            db.flush()
            db.expunge_all()


def _logged_export_stream(
    chunk_iter: Iterator[str],
    *,
    project_id: str,
    user_id: str,
    export_format: str,
    counts: Optional[dict] = None,
) -> Iterator[bytes]:
    """Wrap an export chunk generator to emit start/completion/abort logs.

    Yields UTF-8 *bytes* (encoding once here, so the byte tally is exact and
    Starlette doesn't re-encode the str). A client disconnect surfaces as
    GeneratorExit when the response is torn down mid-flight — logged as a
    distinct WARNING from an internal error so aborted/partial downloads are
    diagnosable. Before this, the 2026-05-31 Benchathon export OOMKilled the
    pod and truncated silently with no server-side trace at all.
    """
    started = time.monotonic()
    total_bytes = 0
    logger.info(
        "export start project=%s user=%s format=%s counts=%s",
        project_id, user_id, export_format, counts or {},
    )
    try:
        for chunk in chunk_iter:
            data = chunk.encode("utf-8")
            total_bytes += len(data)
            yield data
    except GeneratorExit:
        logger.warning(
            "export aborted (client disconnect) project=%s user=%s format=%s "
            "bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )
        raise
    except Exception:
        logger.exception(
            "export failed project=%s user=%s format=%s bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )
        raise
    else:
        logger.info(
            "export complete project=%s user=%s format=%s bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )


# Issue #964: Span annotation format conversion functions
def convert_to_label_studio_format(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert BenGER annotation format to Label Studio format for export.
    Flattens span annotations: one result with spans array -> multiple results.

    BenGER format:
    {"from_name": "label", "type": "labels", "value": {"spans": [...]}}

    Label Studio format:
    [{"id": "span-1", "from_name": "label", "type": "labels", "value": {"start": 0, "end": 10, ...}}]
    """
    if not results or not isinstance(results, list):
        return results

    output = []
    for result in results:
        # Handle span/labels type with nested spans array
        if result.get("type") == "labels" and isinstance(result.get("value"), dict):
            spans = result["value"].get("spans", [])
            if spans and isinstance(spans, list):
                # Flatten: create one result per span
                for span in spans:
                    output.append(
                        {
                            "id": span.get("id", str(uuid.uuid4())),
                            "from_name": result.get("from_name"),
                            "to_name": result.get("to_name"),
                            "type": "labels",
                            "value": {
                                "start": span.get("start"),
                                "end": span.get("end"),
                                "text": span.get("text", ""),
                                "labels": span.get("labels", []),
                            },
                        }
                    )
            else:
                # No spans array, pass through as-is
                output.append(result)
        else:
            # Non-span annotations pass through unchanged
            output.append(result)

    return output


def convert_from_label_studio_format(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Label Studio format to BenGER internal format for import.
    Consolidates span annotations: multiple results -> one result with spans array.

    Label Studio format:
    [{"id": "span-1", "from_name": "label", "type": "labels", "value": {"start": 0, "end": 10, ...}}]

    BenGER format:
    {"from_name": "label", "type": "labels", "value": {"spans": [...]}}
    """
    if not results or not isinstance(results, list):
        return results

    output = []
    span_groups: Dict[str, Dict[str, Any]] = {}

    for result in results:
        # Check if this is a Label Studio span annotation (labels type with value.start)
        if (
            result.get("type") == "labels"
            and isinstance(result.get("value"), dict)
            and result["value"].get("start") is not None
            and result["value"].get("end") is not None
        ):
            # Group by from_name + to_name
            from_name = result.get("from_name", "")
            to_name = result.get("to_name", "")
            key = f"{from_name}:{to_name}"

            if key not in span_groups:
                span_groups[key] = {
                    "from_name": from_name,
                    "to_name": to_name,
                    "type": "labels",
                    "value": {"spans": []},
                }

            span_groups[key]["value"]["spans"].append(
                {
                    "id": result.get("id", str(uuid.uuid4())),
                    "start": result["value"].get("start"),
                    "end": result["value"].get("end"),
                    "text": result["value"].get("text", ""),
                    "labels": result["value"].get("labels", []),
                }
            )
        elif result.get("type") == "labels" and isinstance(result.get("value"), dict):
            # Check if already in BenGER format (has spans array)
            if "spans" in result.get("value", {}):
                output.append(result)
            else:
                # Other labels format, pass through
                output.append(result)
        else:
            # Non-span annotations pass through unchanged
            output.append(result)

    # Add consolidated span groups to output
    for group in span_groups.values():
        output.append(group)

    return output


from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from auth_module import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from database import get_db  # noqa: E402
from routers.projects._export_stream import (  # noqa: E402
    stream_comprehensive_project_data_json,
    stream_export_flat_csv,
    stream_export_json,
    stream_export_label_studio,
    stream_export_txt,
)
from routers.projects._import_stream import (  # noqa: E402
    iter_array,
    read_top_object,
)
from routers.projects.serializers import _parse_iso  # noqa: E402
from models import (  # noqa: E402
    EvaluationJudgeRun,
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationConfig,
    HumanEvaluationResult,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from notification_service import notify_project_created  # noqa: E402
from project_models import (  # noqa: E402
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from project_schemas import ProjectImportData  # noqa: E402
from routers.projects.helpers import (  # noqa: E402
    check_project_accessible,
    check_project_write_access,
    get_org_context_from_request,
    get_user_with_memberships,
)

router = APIRouter()


@router.post("/{project_id}/import")
async def import_project_data(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Import tasks and annotations into an existing project.

    Supports Label Studio format with BenGER extensions.
    """
    # Stream the request body to a SpooledTemporaryFile and parse it
    # *incrementally* with ijson instead of json.load-ing the whole payload —
    # a 583MB export balloons to 2-4GB resident and OOM-kills the pod
    # (issue #158). One cheap pass (read_top_object) materializes only the
    # small top-level fields; the big `data` array is streamed task-by-task
    # via iter_array below, so peak heap stays O(batch) not O(file). The spool
    # outlives the parse passes and is closed in the import block's finally.
    spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)

    created_tasks = 0
    created_annotations = 0
    created_generations = 0
    created_questionnaire_responses = 0
    created_evaluation_runs = 0
    created_task_evaluations = 0
    total_items = 0
    task_id_mapping = {}
    generation_id_mapping = {}  # old generation id -> new generation id
    annotation_id_mapping: Dict[str, str] = {}  # old annotation id -> new annotation id

    try:
        async for chunk in request.stream():
            spooled.write(chunk)

        # Build the small top-level fields (meta, evaluation_runs, the human-eval
        # arrays, korrektur_comments); the big `data` array is parsed-through and
        # discarded here, then streamed below. Malformed JSON → 422 (matches the
        # old json.load behaviour); `data` missing / not a list → 422 (matches
        # the old Pydantic List[...] requirement).
        try:
            top_obj, kinds = read_top_object(spooled, _NESTED_SMALL_KEYS)
        except ijson.JSONError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON body: {exc}")
        if kinds.get("data") != "start_array":
            raise HTTPException(
                status_code=422,
                detail="Field 'data' is required and must be a list",
            )
        # Validate the small fields' types exactly as ProjectImportData did
        # (the streamed `data` items are dict-checked per row below).
        try:
            data = ProjectImportData.model_validate({**top_obj, "data": []})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        # Importing tasks is a write/contribute action — require ORG_ADMIN or
        # CONTRIBUTOR effective role. Public-tier ANNOTATOR visitors are blocked.
        if not check_project_write_access(db, current_user, project_id):
            raise HTTPException(
                status_code=403,
                detail="Only contributors or admins can import tasks into this project",
            )

        # Import evaluation runs first so task evaluations can reference them
        evaluation_run_id_mapping = {}  # old er id -> new er id
        # Migration 043: TaskEvaluation.judge_run_id is NOT NULL. Legacy
        # exports pre-date the column; create one synthetic catch-all
        # judge_run per imported EvaluationRun (mirroring 043's backfill)
        # so TaskEvaluations without an explicit judge_run_id can attach.
        evaluation_run_judge_run: Dict[str, str] = {}  # new er id -> jr id
        if data.evaluation_runs:
            for er_data in data.evaluation_runs:
                old_er_id = er_data.get("id")
                new_er_id = str(uuid.uuid4())
                er = EvaluationRun(
                    id=new_er_id,
                    project_id=project_id,
                    task_id=None,  # Not tied to a single task in data import
                    model_id=er_data.get("model_id", "unknown"),
                    evaluation_type_ids=er_data.get("evaluation_type_ids"),
                    metrics=er_data.get("metrics"),
                    eval_metadata=er_data.get("eval_metadata"),
                    status=er_data.get("status", "completed"),
                    error_message=er_data.get("error_message"),
                    samples_evaluated=er_data.get("samples_evaluated"),
                    created_by=er_data.get("created_by", current_user.id),
                )
                db.add(er)
                jr_id = str(uuid.uuid4())
                db.add(EvaluationJudgeRun(
                    id=jr_id, evaluation_id=new_er_id, judge_model_id=None,
                    run_index=0, status="completed",
                ))
                evaluation_run_judge_run[new_er_id] = jr_id
                created_evaluation_runs += 1
                if old_er_id:
                    evaluation_run_id_mapping[old_er_id] = new_er_id

        # Create stub users for any referenced user IDs that don't exist locally
        # This preserves original annotator IDs from the export. Cheap streaming
        # pre-pass over `data` reading only annotator ids (one task at a time).
        from models import User as DBUser
        import_user_ids = set()
        for item in iter_array(spooled, "data.item"):
            if isinstance(item, dict):
                for ann in item.get("annotations", []):
                    if ann.get("completed_by"):
                        import_user_ids.add(ann["completed_by"])
                    if ann.get("reviewed_by"):
                        import_user_ids.add(ann["reviewed_by"])
        if import_user_ids:
            existing_ids = {u.id for u in db.query(DBUser.id).filter(DBUser.id.in_(import_user_ids)).all()}
            missing_ids = import_user_ids - existing_ids
            for uid in missing_ids:
                stub = DBUser(
                    id=uid,
                    username=f"imported-{uid[:8]}",
                    email=f"imported-{uid[:8]}@import.local",
                    name=f"Imported User {uid[:8]}",
                    email_verified=True,
                )
                db.add(stub)
            if missing_ids:
                db.flush()
                logger.info(f"Created {len(missing_ids)} stub users for imported annotations")

        for item in iter_array(spooled, "data.item"):
            # The old Pydantic List[Dict] rejected non-dict items with a 422;
            # preserve that now that items are validated one-at-a-time.
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=422,
                    detail="Each entry in 'data' must be an object",
                )
            total_items += 1
            # Handle Label Studio format
            task_data = item
            task_meta = data.meta or {}
            annotations_to_import = []
            generations_to_import = []
            task_level_evaluations = []
            original_task_id = None

            # If item has 'data' field, it's Label Studio format
            if isinstance(item, dict) and "data" in item:
                task_data = item["data"]
                original_task_id = item.get("id")  # Store original ID for mapping

                # Merge item meta with global meta, item meta takes precedence
                if "meta" in item and item["meta"]:
                    task_meta = {**task_meta, **item["meta"]}

                # Extract annotations if present
                if "annotations" in item and isinstance(item["annotations"], list):
                    annotations_to_import = item["annotations"]

                # Extract generations if present (BenGER extension)
                if "generations" in item and isinstance(item["generations"], list):
                    generations_to_import = item["generations"]

                # Extract task-level evaluations if present
                if "evaluations" in item and isinstance(item["evaluations"], list):
                    task_level_evaluations = item["evaluations"]

            # No longer add generation prompts - using generation structure instead (Issue #519)
            # The prompts are now configured at project level via generation_config.prompt_structures

            # Create task with flexible data structure
            task_id = str(uuid.uuid4())

            # Handle inner_id - must be integer, extract from string if possible
            inner_id_value = created_tasks + 1  # Default to sequential numbering
            if original_task_id and isinstance(original_task_id, str):
                # Try to extract numeric part from strings like "task-001"
                import re

                numeric_match = re.search(r'\d+', original_task_id)
                if numeric_match:
                    try:
                        inner_id_value = int(numeric_match.group())
                    except ValueError:
                        pass
            elif isinstance(original_task_id, int):
                inner_id_value = original_task_id

            task = Task(
                id=task_id,
                project_id=project_id,
                data=task_data,
                meta=task_meta,
                inner_id=inner_id_value,  # Integer value for database
            )
            db.add(task)
            created_tasks += 1

            # Store ID mapping for cross-references
            if original_task_id:
                task_id_mapping[original_task_id] = task_id

            # Import annotations for this task
            for ann_data in annotations_to_import:
                # Issue #964: Convert Label Studio span annotations to BenGER format
                imported_result = convert_from_label_studio_format(ann_data.get("result", []))
                annotation_id = str(uuid.uuid4())
                original_annotation_id = ann_data.get("id")
                if original_annotation_id:
                    annotation_id_mapping[original_annotation_id] = annotation_id
                annotation = Annotation(
                    id=annotation_id,
                    task_id=task_id,
                    project_id=project_id,
                    result=imported_result,
                    completed_by=ann_data.get("completed_by", current_user.id),
                    was_cancelled=ann_data.get("was_cancelled", False),
                    ground_truth=ann_data.get("ground_truth", False),
                    lead_time=ann_data.get("lead_time"),
                    draft=ann_data.get("draft"),
                    prediction_scores=ann_data.get("prediction"),
                    # Alternating-instruction + AI-assist provenance.
                    instruction_variant=ann_data.get("instruction_variant"),
                    auto_submitted=ann_data.get("auto_submitted", False),
                    ai_assisted=ann_data.get("ai_assisted", False),
                    # Review trail.
                    reviewed_by=ann_data.get("reviewed_by"),
                    reviewed_at=_parse_iso(ann_data.get("reviewed_at")),
                    review_result=ann_data.get("review_result"),
                    review_annotation=ann_data.get("review_annotation"),
                    review_comment=ann_data.get("review_comment"),
                    # Enhanced timing (Issue #1208).
                    active_duration_ms=ann_data.get("active_duration_ms"),
                    focused_duration_ms=ann_data.get("focused_duration_ms"),
                    tab_switches=ann_data.get("tab_switches", 0),
                )
                db.add(annotation)
                created_annotations += 1

                # Import questionnaire response if present
                qr_data = ann_data.get("questionnaire_response")
                if qr_data and isinstance(qr_data, dict) and qr_data.get("result"):
                    qr = PostAnnotationResponse(
                        id=str(uuid.uuid4()),
                        annotation_id=annotation_id,
                        task_id=task_id,
                        project_id=project_id,
                        user_id=ann_data.get("completed_by", current_user.id),
                        result=qr_data["result"],
                    )
                    db.add(qr)
                    created_questionnaire_responses += 1

            # Flush so the new annotation rows land before TaskEvaluation rows
            # FK-reference them (SQLAlchemy's auto-ordering doesn't catch this
            # because there's no ORM relationship declared between the two).
            if annotations_to_import:
                db.flush()

            # Import generations for this task (BenGER extension)
            if generations_to_import:
                # Create ResponseGeneration records first, grouped by model
                # This maintains the job-tracking workflow structure
                model_response_generations = {}

                for gen_data in generations_to_import:
                    model_id = gen_data.get("model_id", "unknown")

                    # Create one ResponseGeneration per model per task
                    if model_id not in model_response_generations:
                        response_gen_id = str(uuid.uuid4())
                        response_generation = ResponseGeneration(
                            id=response_gen_id,
                            task_id=task_id,
                            project_id=project_id,
                            model_id=model_id,
                            config_id="import-default",  # Default config for imported data
                            status="completed",  # Imported generations are completed
                            responses_generated=1,
                            created_by=current_user.id,
                            completed_at=datetime.utcnow(),
                        )
                        db.add(response_generation)
                        model_response_generations[model_id] = response_gen_id

                # Now create Generation records with proper generation_id references.
                # Migration 041 added a unique constraint on (generation_id, run_index)
                # — multiple gens sharing a parent (same model_id) must have distinct
                # run_index values, so count children per parent as we go.
                run_index_per_parent: dict[str, int] = {}
                for gen_data in generations_to_import:
                    model_id = gen_data.get("model_id", "unknown")
                    response_gen_id = model_response_generations[model_id]
                    run_index = run_index_per_parent.get(response_gen_id, 0)
                    run_index_per_parent[response_gen_id] = run_index + 1

                    new_gen_id = str(uuid.uuid4())
                    original_gen_id = gen_data.get("id")
                    generation = Generation(
                        id=new_gen_id,
                        generation_id=response_gen_id,  # Link to ResponseGeneration
                        run_index=run_index,
                        task_id=task_id,
                        model_id=model_id,
                        response_content=gen_data.get("response_content", ""),
                        # prompt_id removed in issue #759 - prompts now in project.generation_config (issue #817)
                        case_data=gen_data.get("case_data", json.dumps(task_data)),
                        response_metadata=gen_data.get("response_metadata"),
                        status=gen_data.get("status", "completed"),
                        usage_stats=gen_data.get("usage_stats"),
                        error_message=gen_data.get("error_message"),
                        # Parse provenance + label-config snapshot for full re-import.
                        parse_status=gen_data.get("parse_status", "pending"),
                        parse_error=gen_data.get("parse_error"),
                        parsed_annotation=gen_data.get("parsed_annotation"),
                        parse_metadata=gen_data.get("parse_metadata"),
                        label_config_version=gen_data.get("label_config_version"),
                        label_config_snapshot=gen_data.get("label_config_snapshot"),
                    )
                    db.add(generation)
                    created_generations += 1

                    # Track ID mapping for evaluation import
                    if original_gen_id:
                        generation_id_mapping[original_gen_id] = new_gen_id

                    # Import generation-nested evaluations. Flush so the new
                    # Generation row is in the DB before the FK from
                    # TaskEvaluation.generation_id is checked at commit time.
                    if gen_data.get("evaluations"):
                        db.flush()
                    for eval_data in gen_data.get("evaluations", []):
                        te_id = str(uuid.uuid4())
                        eval_run_id = eval_data.get("evaluation_run_id") or eval_data.get("evaluation_id")
                        new_er_id = evaluation_run_id_mapping.get(eval_run_id, eval_run_id)
                        te = TaskEvaluation(
                            id=te_id,
                            evaluation_id=new_er_id,
                            task_id=task_id,
                            generation_id=new_gen_id,
                            annotation_id=annotation_id_mapping.get(eval_data.get("annotation_id")),
                            field_name=eval_data.get("field_name"),
                            answer_type=eval_data.get("answer_type"),
                            ground_truth=eval_data.get("ground_truth"),
                            prediction=eval_data.get("prediction"),
                            metrics=eval_data.get("metrics"),
                            passed=eval_data.get("passed"),
                            confidence_score=eval_data.get("confidence_score"),
                            error_message=eval_data.get("error_message"),
                            processing_time_ms=eval_data.get("processing_time_ms"),
                            judge_prompts_used=eval_data.get("judge_prompts_used"),
                            # Migration 042: forward judge_run_id when the
                            # export carries it. Older exports pre-date the
                            # field; fall back to the synthetic catch-all
                            # judge_run created above for this evaluation_run
                            # (mirrors migration 043's backfill).
                            judge_run_id=eval_data.get("judge_run_id")
                                or evaluation_run_judge_run.get(new_er_id),  # noqa: E131
                        )
                        db.add(te)
                        created_task_evaluations += 1

            # Import task-level evaluations (annotation/ground-truth evals
            # without generation). Flush so any pending Annotation rows from
            # earlier in this iteration are visible when the TaskEvaluation
            # FK to annotations is validated at commit.
            if task_level_evaluations:
                db.flush()
            for eval_data in task_level_evaluations:
                te_id = str(uuid.uuid4())
                eval_run_id = eval_data.get("evaluation_run_id") or eval_data.get("evaluation_id")
                new_er_id = evaluation_run_id_mapping.get(eval_run_id, eval_run_id)
                te = TaskEvaluation(
                    id=te_id,
                    evaluation_id=new_er_id,
                    task_id=task_id,
                    generation_id=None,
                    # Map annotation_id through the mapping built during annotation
                    # creation; falls back to None if the annotation is not in the
                    # payload (the row will then be invisible to per-annotator
                    # aggregation but stays attached to the evaluation_run).
                    annotation_id=annotation_id_mapping.get(eval_data.get("annotation_id")),
                    field_name=eval_data.get("field_name"),
                    answer_type=eval_data.get("answer_type"),
                    ground_truth=eval_data.get("ground_truth"),
                    prediction=eval_data.get("prediction"),
                    metrics=eval_data.get("metrics"),
                    passed=eval_data.get("passed"),
                    confidence_score=eval_data.get("confidence_score"),
                    error_message=eval_data.get("error_message"),
                    processing_time_ms=eval_data.get("processing_time_ms"),
                    judge_prompts_used=eval_data.get("judge_prompts_used"),
                    # Migration 042: see comment on the generation-attached path above.
                    judge_run_id=eval_data.get("judge_run_id")
                        or evaluation_run_judge_run.get(new_er_id),  # noqa: E131
                )
                db.add(te)
                created_task_evaluations += 1

            # Bound peak heap: once a batch of tasks is inserted, flush so the
            # rows hit the DB, then drop them from the session identity map.
            # Everything downstream cross-references via string id maps (not ORM
            # objects), so detaching is safe and keeps memory O(batch), not
            # O(file), for a multi-GB import.
            if created_tasks % _IMPORT_BATCH == 0:
                db.flush()
                db.expunge_all()

        # Top-level human-evaluation import (mirrors clone path).
        # Skip silently if the payload doesn't carry any of these arrays —
        # backward-compatible with older exports.
        human_eval_config_id_mapping: Dict[str, str] = {}
        human_eval_session_id_mapping: Dict[str, str] = {}
        for cfg in (data.human_evaluation_configs or []):
            new_cfg_id = str(uuid.uuid4())
            old_cfg_id = cfg.get("id")
            if old_cfg_id:
                human_eval_config_id_mapping[old_cfg_id] = new_cfg_id
            db.add(HumanEvaluationConfig(
                id=new_cfg_id,
                task_id=task_id_mapping.get(cfg.get("task_id"), cfg.get("task_id")),
                evaluation_project_id=cfg.get("evaluation_project_id"),
                evaluator_count=cfg.get("evaluator_count", 3),
                randomization_seed=cfg.get("randomization_seed"),
                blinding_enabled=cfg.get("blinding_enabled", True),
                include_human_responses=cfg.get("include_human_responses", False),
                status=cfg.get("status", "pending"),
            ))

        for session in (data.human_evaluation_sessions or []):
            new_session_id = str(uuid.uuid4())
            old_session_id = session.get("id")
            if old_session_id:
                human_eval_session_id_mapping[old_session_id] = new_session_id
            db.add(HumanEvaluationSession(
                id=new_session_id,
                project_id=project_id,
                evaluator_id=session.get("evaluator_id", current_user.id),
                session_type=session.get("session_type", "likert"),
                items_evaluated=session.get("items_evaluated", 0),
                total_items=session.get("total_items"),
                status=session.get("status", "active"),
                session_config=session.get("session_config"),
            ))

        for result in (data.human_evaluation_results or []):
            cfg_id = human_eval_config_id_mapping.get(result.get("config_id"))
            if not cfg_id:
                continue  # orphan result without a mapped config
            db.add(HumanEvaluationResult(
                id=str(uuid.uuid4()),
                config_id=cfg_id,
                task_id=task_id_mapping.get(result.get("task_id"), result.get("task_id")),
                response_id=result.get("response_id"),
                evaluator_id=result.get("evaluator_id"),
                correctness_score=result.get("correctness_score", 0),
                completeness_score=result.get("completeness_score", 0),
                style_score=result.get("style_score", 0),
                usability_score=result.get("usability_score", 0),
                comments=result.get("comments"),
                evaluation_time_seconds=result.get("evaluation_time_seconds"),
            ))

        for ranking in (data.preference_rankings or []):
            session_id = human_eval_session_id_mapping.get(ranking.get("session_id"))
            if not session_id:
                continue
            db.add(PreferenceRanking(
                id=str(uuid.uuid4()),
                session_id=session_id,
                task_id=task_id_mapping.get(ranking.get("task_id"), ranking.get("task_id")),
                response_a_id=ranking.get("response_a_id"),
                response_b_id=ranking.get("response_b_id"),
                winner=ranking.get("winner", "tie"),
                confidence=ranking.get("confidence"),
                reasoning=ranking.get("reasoning"),
                time_spent_seconds=ranking.get("time_spent_seconds"),
            ))

        for likert in (data.likert_scale_evaluations or []):
            session_id = human_eval_session_id_mapping.get(likert.get("session_id"))
            if not session_id:
                continue
            db.add(LikertScaleEvaluation(
                id=str(uuid.uuid4()),
                session_id=session_id,
                task_id=task_id_mapping.get(likert.get("task_id"), likert.get("task_id")),
                response_id=likert.get("response_id"),
                dimension=likert.get("dimension"),
                rating=likert.get("rating", 0),
                comment=likert.get("comment"),
                time_spent_seconds=likert.get("time_spent_seconds"),
            ))

        # Korrektur threaded comments (parents first, then replies, so
        # parent_id can be remapped without forward references).
        from project_models import KorrekturComment
        comment_id_mapping: Dict[str, str] = {}
        comments_payload = list(data.korrektur_comments or [])
        comments_payload.sort(key=lambda c: 1 if c.get("parent_id") else 0)
        for c in comments_payload:
            target_type = c.get("target_type")
            old_target_id = c.get("target_id")
            new_target_id: Any = old_target_id
            if target_type == "annotation":
                new_target_id = annotation_id_mapping.get(old_target_id, old_target_id)
            elif target_type == "generation":
                new_target_id = generation_id_mapping.get(old_target_id, old_target_id)
            elif target_type == "evaluation":
                # We don't track per-row TaskEvaluation id mapping (rows get
                # fresh UUIDs); leave as-is so the user can re-link manually
                # if needed. Most korrektur comments target annotations.
                new_target_id = old_target_id
            new_id = str(uuid.uuid4())
            old_id = c.get("id")
            if old_id:
                comment_id_mapping[old_id] = new_id
            db.add(KorrekturComment(
                id=new_id,
                project_id=project_id,
                task_id=task_id_mapping.get(c.get("task_id"), c.get("task_id")),
                target_type=target_type,
                target_id=new_target_id,
                parent_id=comment_id_mapping.get(c.get("parent_id")),
                text=c.get("text", ""),
                highlight_start=c.get("highlight_start"),
                highlight_end=c.get("highlight_end"),
                highlight_text=c.get("highlight_text"),
                highlight_label=c.get("highlight_label"),
                is_resolved=c.get("is_resolved", False),
                resolved_at=_parse_iso(c.get("resolved_at")),
                resolved_by=c.get("resolved_by"),
                created_by=c.get("created_by", current_user.id),
            ))

        # Commit everything atomically
        db.commit()

        # Update report data section after task import (Issue #770)
        try:
            from report_service import update_report_data_section

            update_report_data_section(db, project_id)
            logger.info(f"✅ Updated report data section for project {project_id}")
        except Exception as e:
            logger.error(f"Failed to update report data section: {e}")
            # Don't fail the import operation

        return {
            "created_tasks": created_tasks,
            "created_annotations": created_annotations,
            "created_generations": created_generations,
            "created_questionnaire_responses": created_questionnaire_responses,
            "created_evaluation_runs": created_evaluation_runs,
            "created_task_evaluations": created_task_evaluations,
            "total_items": total_items,
            "project_id": project_id,
            "task_id_mapping": task_id_mapping,  # Return mapping for debugging/reference
        }

    except HTTPException:
        # Validation / access / per-item errors keep their status code; roll
        # back any rows flushed before the failure so nothing partial commits.
        db.rollback()
        raise
    except Exception as e:
        # Rollback on any error
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to import data: {str(e)}")
    finally:
        spooled.close()


@router.get("/{project_id}/export")
async def export_project(
    project_id: str,
    request: Request,
    format: str = Query("json", pattern="^(json|csv|tsv|txt|label_studio)$"),
    download: bool = Query(True),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Export project data and annotations in various formats"""

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # JSON path streams via the shared helper. The legacy in-memory builder
    # below loaded the entire project (tasks + annotations + generations +
    # task_evaluations) into one dict and json.dumps()-ed it, which peaked
    # past the 3Gi API memory limit on the Benchathon project (~8k
    # task_evaluations, ~400 MB output) and OOMKilled the pod mid-response.
    # CSV/TSV/TXT/label_studio still use the legacy path — each has a
    # per-row shape its own tests assert on and a separate refactor.
    if format == "json":
        # All count queries pass whole-model classes (not column attributes
        # or joins) so they stay mockable in the existing unit tests and
        # issue cheap COUNT(*) round-trips. Task / EvaluationRun rows are
        # small and we need their IDs for the in_() filters anyway, so we
        # load them; Annotation / Generation / TaskEvaluation use .count()
        # to avoid pulling row bodies for what is just a header tally.
        project_tasks_for_counts = (
            db.query(Task).filter(Task.project_id == project_id).all()
        )
        task_id_list = [t.id for t in project_tasks_for_counts]
        evaluation_runs_for_counts = (
            db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .all()
        )
        eval_run_ids_for_counts = [er.id for er in evaluation_runs_for_counts]

        task_count = len(project_tasks_for_counts)
        annotation_count = (
            db.query(Annotation).filter(Annotation.project_id == project_id).count()
        )
        generation_count = (
            db.query(Generation).filter(Generation.task_id.in_(task_id_list)).count()
            if task_id_list
            else 0
        )
        task_evaluation_count = (
            db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id.in_(eval_run_ids_for_counts))
            .count()
            if eval_run_ids_for_counts
            else 0
        )

        header_fields = {
            "project": {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "created_at": (
                    project.created_at.isoformat() if project.created_at else None
                ),
                "task_count": task_count,
                "annotation_count": annotation_count,
                "generation_count": generation_count,
                "evaluation_run_count": len(eval_run_ids_for_counts),
                "task_evaluation_count": task_evaluation_count,
                "label_config": project.label_config,
            },
        }

        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_export.json"
            headers["Content-Disposition"] = f"attachment; filename={filename}"

        return StreamingResponse(
            _logged_export_stream(
                stream_export_json(
                    db, project_id, task_ids=None, header_fields=header_fields
                ),
                project_id=project_id,
                user_id=current_user.id,
                export_format="json",
                counts={
                    "tasks": task_count,
                    "annotations": annotation_count,
                    "generations": generation_count,
                    "evaluation_runs": len(eval_run_ids_for_counts),
                    "task_evaluations": task_evaluation_count,
                },
            ),
            media_type="application/json",
            headers=headers,
        )

    if format in ("csv", "tsv"):
        delimiter = "," if format == "csv" else "\t"
        media_type = "text/csv" if format == "csv" else "text/tab-separated-values"
        ext = "csv" if format == "csv" else "tsv"
        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_export.{ext}"
            headers["Content-Disposition"] = f"attachment; filename={filename}"
        return StreamingResponse(
            _logged_export_stream(
                stream_export_flat_csv(db, project_id, delimiter=delimiter),
                project_id=project_id,
                user_id=current_user.id,
                export_format=format,
            ),
            media_type=media_type,
            headers=headers,
        )

    if format == "label_studio":
        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_label_studio.json"
            headers["Content-Disposition"] = f"attachment; filename={filename}"
        return StreamingResponse(
            _logged_export_stream(
                stream_export_label_studio(db, project_id),
                project_id=project_id,
                user_id=current_user.id,
                export_format="label_studio",
            ),
            media_type="application/json",
            headers=headers,
        )

    # txt — the only remaining format (json/csv/tsv/label_studio short-circuit
    # above). Streamed too so peak memory stays bounded; the Query() pattern
    # rejects anything else before we ever reach this point.
    headers = {}
    if download:
        filename = f"{project.title.replace(' ', '_')}_export.txt"
        headers["Content-Disposition"] = f"attachment; filename={filename}"
    return StreamingResponse(
        _logged_export_stream(
            stream_export_txt(db, project_id, project.title, project.description),
            project_id=project_id,
            user_id=current_user.id,
            export_format="txt",
        ),
        media_type="text/plain",
        headers=headers,
    )



@router.post("/bulk-export")
async def bulk_export_projects(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk export multiple projects"""

    project_ids = data.get("project_ids", [])
    format = data.get("format", "json")
    include_data = data.get("include_data", True)

    org_context = get_org_context_from_request(request)

    export_data = {
        "projects": [],
        "exported_at": datetime.now().isoformat(),
        "format": format,
    }

    for project_id in project_ids:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            continue

        # Check access permission via org-context-aware helper
        if not check_project_accessible(db, current_user, project_id, org_context):
            continue

        # Calculate counts dynamically
        task_count = db.query(Task).filter(Task.project_id == project.id).count()
        annotation_count = (
            db.query(Annotation)
            .filter(Annotation.project_id == project.id, Annotation.was_cancelled == False)  # noqa: E712
            .count()
        )

        project_data = {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "created_at": (project.created_at.isoformat() if project.created_at else None),
            "created_by": project.created_by,
            "task_count": task_count,
            "annotation_count": annotation_count,
            "label_config": project.label_config,
            "expert_instruction": project.expert_instruction,
        }

        if include_data:
            # Include tasks and annotations
            tasks = db.query(Task).filter(Task.project_id == project_id).all()
            # NOTE: Annotation table doesn't exist yet - returning empty list
            annotations = (
                []
            )  # db.query(Annotation).filter(Annotation.project_id == project_id).all()

            project_data["tasks"] = []
            for task in tasks:
                task_data = {
                    "id": task.id,
                    "data": task.data,
                    "meta": task.meta,
                    "is_labeled": task.is_labeled,
                    "created_at": (task.created_at.isoformat() if task.created_at else None),
                }

                # Add annotations for this task
                task_annotations = [a for a in annotations if a.task_id == task.id]
                task_data["annotations"] = []
                for ann in task_annotations:
                    task_data["annotations"].append(
                        {
                            "id": ann.id,
                            "result": ann.result,
                            "completed_by": ann.completed_by,
                            "created_at": (ann.created_at.isoformat() if ann.created_at else None),
                            "was_cancelled": ann.was_cancelled,
                        }
                    )

                project_data["tasks"].append(task_data)

        export_data["projects"].append(project_data)

    # Format the response
    if format == "json":
        content = json.dumps(export_data, indent=2)
        media_type = "application/json"
        filename = f"projects_bulk_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    elif format == "csv":
        # For CSV, we'll create a simplified flat structure
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "project_id",
                "project_title",
                "description",
                "task_count",
                "annotation_count",
                "created_at",
            ]
        )

        # Data rows
        for project in export_data["projects"]:
            writer.writerow(
                [
                    project["id"],
                    project["title"],
                    project.get("description", ""),
                    project["task_count"],
                    project["annotation_count"],
                    project["created_at"],
                ]
            )

        content = output.getvalue()
        media_type = "text/csv"
        filename = f"projects_bulk_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/bulk-export-full")
async def bulk_export_full_projects(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Export complete projects as individual JSON files in a ZIP archive.

    This endpoint provides full project migration capabilities by exporting
    all project data including tasks, annotations, generations, evaluations,
    and user assignments.

    Request body:
    {
        "project_ids": ["project-1", "project-2", ...]
    }

    Returns: ZIP file containing individual project JSON files
    """
    project_ids = data.get("project_ids", [])
    if not project_ids:
        raise HTTPException(status_code=400, detail="No project IDs provided")

    org_context = get_org_context_from_request(request)

    print(f"[EXPORT DEBUG] Received project_ids: {project_ids}")
    print(
        f"[EXPORT DEBUG] Current user: {current_user.email}, is_superadmin: {current_user.is_superadmin}"
    )

    # Write the ZIP to a tempfile on disk and stream each project's JSON
    # directly into its zip entry via `json.dump`, which writes chunks as it
    # walks the object tree. Previous revisions held the full zip in a
    # BytesIO AND `json.dumps()`-d each project's dict into a giant string
    # before adding it — for a Benchathon-sized project that's ~3× the
    # row-set's RAM and OOMKilled the API pod on 2026-05-31. With the
    # on-disk zip + incremental writer, peak memory now scales with one
    # project's Python dict, not with N projects' serialized output.
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"benger_projects_export_{timestamp}.zip"
    zip_fd = tempfile.NamedTemporaryFile(
        prefix="benger-bulk-export-full-", suffix=".zip", delete=False
    )
    zip_path = zip_fd.name
    zip_fd.close()  # FileResponse opens it; we just needed the path.

    exported_count = 0
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for project_id in project_ids:
                try:
                    print(f"[EXPORT DEBUG] Processing project_id: {project_id}")

                    project = db.query(Project).filter(Project.id == project_id).first()
                    if not project:
                        print(f"[EXPORT DEBUG] Project {project_id} not found in database")
                        continue

                    if not check_project_accessible(db, current_user, project_id, org_context):
                        print(f"[EXPORT DEBUG] Access denied for project {project_id}, skipping")
                        continue

                    print(f"[EXPORT DEBUG] Streaming comprehensive data for project {project_id}")

                    safe_title = "".join(
                        c for c in project.title if c.isalnum() or c in (' ', '-', '_')
                    ).rstrip()
                    safe_title = safe_title[:50]
                    entry_name = f"{safe_title}_{project_id[:8]}.json"

                    # Stream each project's JSON straight into its zip entry
                    # via `stream_comprehensive_project_data_json` — the helper
                    # yields chunks with `yield_per` so the full clone payload
                    # (tasks + annotations + generations + task_evaluations
                    # in mode="full") never lives in RAM as one dict. zip.open(
                    # ..., 'w') returns a binary writer; we encode each text
                    # chunk to UTF-8 and write directly so we don't stack a
                    # TextIOWrapper buffer on top of zip's deflate stream.
                    with zip_file.open(entry_name, 'w') as raw_entry:
                        for chunk in stream_comprehensive_project_data_json(
                            db, project_id
                        ):
                            raw_entry.write(chunk.encode("utf-8"))

                    exported_count += 1

                except Exception as e:
                    print(f"[EXPORT DEBUG] Error exporting project {project_id}: {str(e)}")
                    import traceback

                    print(f"[EXPORT DEBUG] Traceback: {traceback.format_exc()}")
                    continue
    except BaseException:
        # If anything blows up mid-build, don't leak the tempfile.
        try:
            os.unlink(zip_path)
        except OSError:
            pass
        raise

    if exported_count == 0:
        try:
            os.unlink(zip_path)
        except OSError:
            pass
        raise HTTPException(status_code=404, detail="No projects could be exported")

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_filename,
        background=BackgroundTask(os.unlink, zip_path),
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
    )


@router.post("/import-project")
async def import_full_project(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Import a complete project from a comprehensive export JSON file.

    This endpoint creates a new project with all associated data including:
    - Project configuration
    - All tasks with metadata
    - All annotations
    - All LLM generations
    - All evaluations
    - Project members and assignments (mapped to current users)

    Handles conflicts by:
    - Auto-renaming project if name exists
    - Generating new UUIDs for all entities
    - Mapping users to existing users by email (or creating placeholders)

    Returns: Created project information with import statistics
    """
    get_org_context_from_request(request)
    # Extract the upload into a seekable spool, then parse it *incrementally*
    # with ijson instead of json.load-ing the whole document — a 583MB
    # comprehensive export balloons to 2-4GB resident and OOM-kills the pod
    # (issue #158). read_top_object materializes only the small top-level
    # `project`/`format_version`; every big array (tasks, annotations,
    # generations, evaluations, …) is streamed row-by-row via _stream_rows in
    # FK-dependency order, so peak heap stays O(batch) not O(file). zip inner
    # streams are non-seekable, so we copy the inner JSON into the spool with a
    # bounded buffer (shutil.copyfileobj) rather than reading it whole.
    spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
    try:
        if file.filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(file.file, 'r') as zip_file:
                    json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                    if not json_files:
                        raise HTTPException(
                            status_code=400, detail="ZIP file contains no JSON files"
                        )
                    # Use first JSON file found (for single project import)
                    with zip_file.open(json_files[0]) as inner_json:
                        shutil.copyfileobj(inner_json, spooled)
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Invalid ZIP file format")
        elif file.filename.endswith('.json'):
            shutil.copyfileobj(file.file, spooled)
        else:
            raise HTTPException(status_code=400, detail="Only JSON and ZIP files are supported")

        # One streaming pass builds only the small top-level fields; malformed
        # JSON surfaces here (read_top_object parses through the whole document)
        # and maps to the same 400 the old json.load raised.
        try:
            top_obj, _kinds = read_top_object(spooled, {"format_version", "project"})
        except ijson.JSONError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        # Validate format version
        format_version = top_obj.get("format_version", "1.0.0")
        if not format_version.startswith("1."):
            raise HTTPException(status_code=400, detail="Unsupported export format version")

        # Extract project data
        project_data = top_obj.get("project", {})
        if not project_data:
            raise HTTPException(status_code=400, detail="No project data found in export")

        # Handle project name conflicts
        original_title = project_data.get("title", "Imported Project")
        new_title = original_title
        counter = 1

        while db.query(Project).filter(Project.title == new_title).first():
            new_title = f"{original_title} ({counter})"
            counter += 1

        # Create ID mappings for all entities
        id_mappings: Dict[str, Dict] = {
            "projects": {},
            "tasks": {},
            "users": {},
            "annotations": {},
            "predictions": {},
            "generations": {},
            "response_generations": {},
            "prompts": {},
            "project_members": {},
            "task_assignments": {},
            "evaluations": {},
            "evaluation_metrics": {},
            "human_evaluation_configs": {},
            "human_evaluation_sessions": {},
            "human_evaluation_results": {},
            "preference_rankings": {},
            "likert_scale_evaluations": {},
            "post_annotation_responses": {},
        }

        # Map users to existing users or create placeholder mappings
        user_email_to_id = {}

        for user_data in _stream_rows(db, spooled, "users.item"):
            old_user_id = user_data.get("id", str(uuid.uuid4()))
            email = user_data.get("email")

            if email:
                # Try to find existing user by email
                existing_user = db.query(User).filter(User.email == email).first()
                if existing_user:
                    id_mappings["users"][old_user_id] = existing_user.id
                    user_email_to_id[email] = existing_user.id
                else:
                    # For now, map to current importing user as fallback
                    id_mappings["users"][old_user_id] = current_user.id
                    user_email_to_id[email] = current_user.id
            else:
                # No email, map to current user
                id_mappings["users"][old_user_id] = current_user.id

        # Get user's primary organization for the imported project
        user_with_memberships = get_user_with_memberships(db, current_user.id)
        if not user_with_memberships or not user_with_memberships.organization_memberships:
            raise HTTPException(
                status_code=400, detail="User must belong to an organization to import projects"
            )

        # Use the first active organization membership
        primary_membership = next(
            (m for m in user_with_memberships.organization_memberships if m.is_active), None
        )
        if not primary_membership:
            raise HTTPException(
                status_code=400, detail="User must have an active organization membership"
            )

        # Create new project
        new_project_id = str(uuid.uuid4())
        # Only add to mappings if the original project had an ID
        original_project_id = project_data.get("id")
        if original_project_id:
            id_mappings["projects"][original_project_id] = new_project_id

        new_project = Project(
            id=new_project_id,
            title=new_title,
            description=project_data.get("description"),
            label_config=project_data.get("label_config"),
            # Note: generation_structure removed in Issue #762 - now in generation_config.prompt_structures
            expert_instruction=project_data.get("expert_instruction"),
            show_instruction=project_data.get("show_instruction", True),
            show_skip_button=project_data.get("show_skip_button", True),
            enable_empty_annotation=project_data.get("enable_empty_annotation", True),
            created_by=current_user.id,  # Current user is creator of imported project
            # organization_id removed - now handled via ProjectOrganization table
            min_annotations_per_task=project_data.get("min_annotations_per_task", 1),
            is_published=project_data.get("is_published", False),
            # Issue #817: Add missing fields for full roundtrip capability
            generation_config=project_data.get("generation_config"),
            evaluation_config=project_data.get("evaluation_config"),
            label_config_version=project_data.get("label_config_version"),
            label_config_history=project_data.get("label_config_history"),
            maximum_annotations=project_data.get("maximum_annotations", 1),
            assignment_mode=project_data.get("assignment_mode", "open"),
            show_submit_button=project_data.get("show_submit_button", True),
            require_comment_on_skip=project_data.get("require_comment_on_skip", False),
            require_confirm_before_submit=project_data.get("require_confirm_before_submit", False),
            is_archived=False,  # Always import as active project
            questionnaire_enabled=project_data.get("questionnaire_enabled", False),
            questionnaire_config=project_data.get("questionnaire_config"),
            randomize_task_order=project_data.get("randomize_task_order", False),
            # Alternating-instruction feature.
            instructions_always_visible=project_data.get(
                "instructions_always_visible", False
            ),
            conditional_instructions=project_data.get("conditional_instructions"),
            # Review workflow.
            review_enabled=project_data.get("review_enabled", False),
            review_mode=project_data.get("review_mode", "in_place"),
            allow_self_review=project_data.get("allow_self_review", False),
            # Korrektur (human-correction) feature.
            korrektur_enabled=project_data.get("korrektur_enabled", False),
            korrektur_config=project_data.get("korrektur_config"),
        )

        db.add(new_project)
        db.flush()  # Flush so FK references to project work

        # Create ProjectOrganization entry for the imported project
        project_org = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=new_project_id,
            organization_id=primary_membership.organization_id,
            assigned_by=current_user.id,
        )
        db.add(project_org)

        # Import tasks
        task_counter = 1

        for task_data in _stream_rows(db, spooled, "tasks.item"):
            old_task_id = task_data.get("id", str(uuid.uuid4()))
            new_task_id = str(uuid.uuid4())
            id_mappings["tasks"][old_task_id] = new_task_id

            # Map user IDs
            created_by = id_mappings["users"].get(task_data.get("created_by"), current_user.id)
            updated_by = id_mappings["users"].get(task_data.get("updated_by"))

            new_task = Task(
                id=new_task_id,
                project_id=new_project_id,
                inner_id=task_counter,  # Recalculate inner IDs
                data=task_data.get("data", {}),
                meta=task_data.get("meta"),
                created_by=created_by,
                updated_by=updated_by,
                is_labeled=task_data.get("is_labeled", False),
                total_annotations=task_data.get("total_annotations", 0),
                cancelled_annotations=task_data.get("cancelled_annotations", 0),
                comment_count=task_data.get("comment_count", 0),
                unresolved_comment_count=task_data.get("unresolved_comment_count", 0),
                comment_authors=task_data.get("comment_authors"),
                file_upload_id=task_data.get("file_upload_id"),
            )

            db.add(new_task)
            task_counter += 1

        # Import annotations
        for annotation_data in _stream_rows(db, spooled, "annotations.item"):
            old_annotation_id = annotation_data.get("id", str(uuid.uuid4()))
            new_annotation_id = str(uuid.uuid4())
            id_mappings["annotations"][old_annotation_id] = new_annotation_id

            # Map IDs
            task_id = id_mappings["tasks"].get(annotation_data.get("task_id"))
            completed_by = id_mappings["users"].get(
                annotation_data.get("completed_by"), current_user.id
            )
            if task_id:  # Only import if task exists
                # Issue #964: Convert Label Studio span annotations to BenGER format
                imported_result = convert_from_label_studio_format(
                    annotation_data.get("result", [])
                )
                new_annotation = Annotation(
                    id=new_annotation_id,
                    task_id=task_id,
                    project_id=new_project_id,
                    result=imported_result,
                    draft=annotation_data.get("draft"),
                    was_cancelled=annotation_data.get("was_cancelled", False),
                    lead_time=annotation_data.get("lead_time"),
                    completed_by=completed_by,
                    ground_truth=annotation_data.get("ground_truth", False),
                    prediction_scores=annotation_data.get("prediction_scores"),
                    # Enhanced timing (Issue #1208)
                    active_duration_ms=annotation_data.get("active_duration_ms"),
                    focused_duration_ms=annotation_data.get("focused_duration_ms"),
                    tab_switches=annotation_data.get("tab_switches", 0),
                    # Alternating-instruction + AI-assist provenance.
                    instruction_variant=annotation_data.get("instruction_variant"),
                    auto_submitted=annotation_data.get("auto_submitted", False),
                    ai_assisted=annotation_data.get("ai_assisted", False),
                    # Review trail.
                    reviewed_by=id_mappings["users"].get(
                        annotation_data.get("reviewed_by"),
                        annotation_data.get("reviewed_by"),
                    ),
                    reviewed_at=_parse_iso(annotation_data.get("reviewed_at")),
                    review_result=annotation_data.get("review_result"),
                    review_annotation=annotation_data.get("review_annotation"),
                    review_comment=annotation_data.get("review_comment"),
                )

                db.add(new_annotation)

        # Note: Predictions import removed - predictions table dropped in migration 411540fa6c40

        # Prompts import removed - prompts table dropped in issue #759
        # Prompt functionality now handled by generation_structure field

        # Import response generations
        for resp_gen_data in _stream_rows(db, spooled, "response_generations.item"):
            old_resp_gen_id = resp_gen_data.get("id", str(uuid.uuid4()))
            new_resp_gen_id = str(uuid.uuid4())
            id_mappings["response_generations"][old_resp_gen_id] = new_resp_gen_id

            task_id = id_mappings["tasks"].get(resp_gen_data.get("task_id"))
            created_by = id_mappings["users"].get(resp_gen_data.get("created_by"), current_user.id)

            if task_id:  # Only import if task exists
                new_resp_gen = ResponseGeneration(
                    id=new_resp_gen_id,
                    task_id=task_id,
                    model_id=resp_gen_data.get("model_id"),
                    config_id=resp_gen_data.get("config_id"),
                    status=resp_gen_data.get("status", "completed"),
                    responses_generated=resp_gen_data.get("responses_generated", 0),
                    error_message=resp_gen_data.get("error_message"),
                    generation_metadata=resp_gen_data.get("generation_metadata"),
                    created_by=created_by,
                )

                db.add(new_resp_gen)

        # Import generations
        for generation_data in _stream_rows(db, spooled, "generations.item"):
            old_generation_id = generation_data.get("id", str(uuid.uuid4()))
            new_generation_id = str(uuid.uuid4())
            id_mappings["generations"][old_generation_id] = new_generation_id

            task_id = id_mappings["tasks"].get(generation_data.get("task_id"))
            generation_id = id_mappings["response_generations"].get(
                generation_data.get("generation_id")
            )
            # prompt_id removed in issue #759 - prompts now in project.generation_config (issue #817)

            if task_id and generation_id:  # Only import if required relations exist
                new_generation = Generation(
                    id=new_generation_id,
                    generation_id=generation_id,
                    task_id=task_id,
                    model_id=generation_data.get("model_id"),
                    # prompt_id removed in issue #759 - prompts now in project.generation_config (issue #817)
                    case_data=generation_data.get("case_data"),
                    response_content=generation_data.get("response_content"),
                    usage_stats=generation_data.get("usage_stats"),
                    response_metadata=generation_data.get("response_metadata"),
                    status=generation_data.get("status", "completed"),
                    error_message=generation_data.get("error_message"),
                    # Parse provenance + label-config snapshot.
                    parse_status=generation_data.get("parse_status", "pending"),
                    parse_error=generation_data.get("parse_error"),
                    parsed_annotation=generation_data.get("parsed_annotation"),
                    parse_metadata=generation_data.get("parse_metadata"),
                    label_config_version=generation_data.get("label_config_version"),
                    label_config_snapshot=generation_data.get("label_config_snapshot"),
                )

                db.add(new_generation)

        # Import evaluations (evaluation runs are project-level)
        for evaluation_data in _stream_rows(db, spooled, "evaluations.item"):
            old_evaluation_id = evaluation_data.get("id", str(uuid.uuid4()))
            new_evaluation_id = str(uuid.uuid4())
            id_mappings["evaluations"][old_evaluation_id] = new_evaluation_id

            created_by = id_mappings["users"].get(
                evaluation_data.get("created_by"), current_user.id
            )

            new_evaluation = EvaluationRun(
                id=new_evaluation_id,
                project_id=new_project_id,
                task_id=id_mappings["tasks"].get(evaluation_data.get("task_id")),
                model_id=evaluation_data.get("model_id"),
                evaluation_type_ids=evaluation_data.get("evaluation_type_ids", []),
                metrics=evaluation_data.get("metrics", {}),
                eval_metadata=evaluation_data.get("eval_metadata"),
                status=evaluation_data.get("status", "completed"),
                error_message=evaluation_data.get("error_message"),
                samples_evaluated=evaluation_data.get("samples_evaluated"),
                created_by=created_by,
            )

            db.add(new_evaluation)

        # Import evaluation metrics
        for metric_data in _stream_rows(db, spooled, "evaluation_metrics.item"):
            old_metric_id = metric_data.get("id", str(uuid.uuid4()))
            new_metric_id = str(uuid.uuid4())
            id_mappings["evaluation_metrics"][old_metric_id] = new_metric_id

            evaluation_id = id_mappings["evaluations"].get(metric_data.get("evaluation_id"))

            if evaluation_id:  # Only import if evaluation exists
                new_metric = EvaluationRunMetric(
                    id=new_metric_id,
                    evaluation_id=evaluation_id,
                    evaluation_type_id=metric_data.get("evaluation_type_id"),
                    value=metric_data.get("value", 0.0),
                )

                db.add(new_metric)

        # Import task evaluations (per-task evaluation results). te_seen counts
        # every row in the payload (imported or skipped) to reproduce the old
        # len(import_data["task_evaluations"]) stat without holding the array.
        te_seen = 0
        for te_data in _stream_rows(db, spooled, "task_evaluations.item"):
            te_seen += 1
            te_data.get("id", str(uuid.uuid4()))
            new_te_id = str(uuid.uuid4())

            evaluation_id = id_mappings["evaluations"].get(te_data.get("evaluation_id"))
            task_id = id_mappings["tasks"].get(te_data.get("task_id"))
            generation_id = id_mappings["generations"].get(te_data.get("generation_id"))

            if evaluation_id and task_id:
                new_te = TaskEvaluation(
                    id=new_te_id,
                    evaluation_id=evaluation_id,
                    task_id=task_id,
                    generation_id=generation_id,
                    annotation_id=id_mappings["annotations"].get(
                        te_data.get("annotation_id")
                    ),
                    field_name=te_data.get("field_name"),
                    answer_type=te_data.get("answer_type"),
                    ground_truth=te_data.get("ground_truth"),
                    prediction=te_data.get("prediction"),
                    metrics=te_data.get("metrics"),
                    passed=te_data.get("passed"),
                    confidence_score=te_data.get("confidence_score"),
                    error_message=te_data.get("error_message"),
                    processing_time_ms=te_data.get("processing_time_ms"),
                    judge_prompts_used=te_data.get("judge_prompts_used"),
                    # Migration 042: forward judge_run_id when present in
                    # the import payload. Older exports leave it None until
                    # migration 043 backfills.
                    judge_run_id=id_mappings.get("judge_runs", {}).get(
                        te_data.get("judge_run_id")
                    ) if te_data.get("judge_run_id") else None,
                )

                db.add(new_te)

        # Import human evaluation configs
        for config_data in _stream_rows(db, spooled, "human_evaluation_configs.item"):
            old_config_id = config_data.get("id", str(uuid.uuid4()))
            new_config_id = str(uuid.uuid4())
            id_mappings["human_evaluation_configs"][old_config_id] = new_config_id

            task_id = id_mappings["tasks"].get(config_data.get("task_id"))

            if task_id:  # Only import if task exists
                new_config = HumanEvaluationConfig(
                    id=new_config_id,
                    task_id=task_id,
                    evaluation_project_id=config_data.get("evaluation_project_id"),
                    evaluator_count=config_data.get("evaluator_count", 3),
                    randomization_seed=config_data.get("randomization_seed"),
                    blinding_enabled=config_data.get("blinding_enabled", True),
                    include_human_responses=config_data.get("include_human_responses", False),
                    status=config_data.get("status", "pending"),
                )

                db.add(new_config)

        # Import human evaluation sessions
        for session_data in _stream_rows(db, spooled, "human_evaluation_sessions.item"):
            old_session_id = session_data.get("id", str(uuid.uuid4()))
            new_session_id = str(uuid.uuid4())
            id_mappings["human_evaluation_sessions"][old_session_id] = new_session_id

            evaluator_id = id_mappings["users"].get(
                session_data.get("evaluator_id"), current_user.id
            )

            new_session = HumanEvaluationSession(
                id=new_session_id,
                project_id=new_project_id,
                evaluator_id=evaluator_id,
                session_type=session_data.get("session_type", "likert"),
                items_evaluated=session_data.get("items_evaluated", 0),
                total_items=session_data.get("total_items"),
                status=session_data.get("status", "active"),
                session_config=session_data.get("session_config"),
            )

            db.add(new_session)

        # Import human evaluation results
        for result_data in _stream_rows(db, spooled, "human_evaluation_results.item"):
            old_result_id = result_data.get("id", str(uuid.uuid4()))
            new_result_id = str(uuid.uuid4())
            id_mappings["human_evaluation_results"][old_result_id] = new_result_id

            config_id = id_mappings["human_evaluation_configs"].get(result_data.get("config_id"))
            task_id = id_mappings["tasks"].get(result_data.get("task_id"))

            if config_id:  # Only import if config exists
                new_result = HumanEvaluationResult(
                    id=new_result_id,
                    config_id=config_id,
                    task_id=task_id,
                    response_id=result_data.get("response_id"),
                    evaluator_id=result_data.get("evaluator_id"),
                    correctness_score=result_data.get("correctness_score", 3),
                    completeness_score=result_data.get("completeness_score", 3),
                    style_score=result_data.get("style_score", 3),
                    usability_score=result_data.get("usability_score", 3),
                    comments=result_data.get("comments"),
                    evaluation_time_seconds=result_data.get("evaluation_time_seconds"),
                )

                db.add(new_result)

        # Import preference rankings
        for ranking_data in _stream_rows(db, spooled, "preference_rankings.item"):
            old_ranking_id = ranking_data.get("id", str(uuid.uuid4()))
            new_ranking_id = str(uuid.uuid4())
            id_mappings["preference_rankings"][old_ranking_id] = new_ranking_id

            session_id = id_mappings["human_evaluation_sessions"].get(
                ranking_data.get("session_id")
            )
            task_id = id_mappings["tasks"].get(ranking_data.get("task_id"))

            if session_id and task_id:  # Only import if both exist
                new_ranking = PreferenceRanking(
                    id=new_ranking_id,
                    session_id=session_id,
                    task_id=task_id,
                    response_a_id=ranking_data.get("response_a_id"),
                    response_b_id=ranking_data.get("response_b_id"),
                    winner=ranking_data.get("winner", "tie"),
                    confidence=ranking_data.get("confidence"),
                    reasoning=ranking_data.get("reasoning"),
                    time_spent_seconds=ranking_data.get("time_spent_seconds"),
                )

                db.add(new_ranking)

        # Import likert scale evaluations
        for likert_data in _stream_rows(db, spooled, "likert_scale_evaluations.item"):
            old_likert_id = likert_data.get("id", str(uuid.uuid4()))
            new_likert_id = str(uuid.uuid4())
            id_mappings["likert_scale_evaluations"][old_likert_id] = new_likert_id

            session_id = id_mappings["human_evaluation_sessions"].get(likert_data.get("session_id"))
            task_id = id_mappings["tasks"].get(likert_data.get("task_id"))

            if session_id and task_id:  # Only import if both exist
                new_likert = LikertScaleEvaluation(
                    id=new_likert_id,
                    session_id=session_id,
                    task_id=task_id,
                    response_id=likert_data.get("response_id"),
                    dimension=likert_data.get("dimension", "overall"),
                    rating=likert_data.get("rating", 3),
                    comment=likert_data.get("comment"),
                    time_spent_seconds=likert_data.get("time_spent_seconds"),
                )

                db.add(new_likert)

        # Import Korrektur threaded comments. Parents first, then replies, so
        # parent_id can be remapped without forward references. Two streaming
        # passes (roots, then replies) replace the old in-memory list+sort,
        # which couldn't scale to a huge comment array.
        from project_models import KorrekturComment
        comment_id_mapping: Dict[str, str] = {}

        def _korrektur_parents_then_replies():
            for c in _stream_rows(db, spooled, "korrektur_comments.item"):
                if not c.get("parent_id"):
                    yield c
            for c in _stream_rows(db, spooled, "korrektur_comments.item"):
                if c.get("parent_id"):
                    yield c

        for c in _korrektur_parents_then_replies():
            target_type = c.get("target_type")
            old_target_id = c.get("target_id")
            new_target_id: Any = old_target_id
            if target_type == "annotation":
                new_target_id = id_mappings["annotations"].get(old_target_id, old_target_id)
            elif target_type == "generation":
                new_target_id = id_mappings["generations"].get(old_target_id, old_target_id)
            elif target_type == "evaluation":
                # Per-row TaskEvaluation mapping isn't tracked; leave as-is.
                new_target_id = old_target_id
            new_id = str(uuid.uuid4())
            old_id = c.get("id")
            if old_id:
                comment_id_mapping[old_id] = new_id
            new_task_id = id_mappings["tasks"].get(c.get("task_id"))
            if not new_task_id:
                continue
            db.add(KorrekturComment(
                id=new_id,
                project_id=new_project_id,
                task_id=new_task_id,
                target_type=target_type,
                target_id=new_target_id,
                parent_id=comment_id_mapping.get(c.get("parent_id")),
                text=c.get("text", ""),
                highlight_start=c.get("highlight_start"),
                highlight_end=c.get("highlight_end"),
                highlight_text=c.get("highlight_text"),
                highlight_label=c.get("highlight_label"),
                is_resolved=c.get("is_resolved", False),
                resolved_at=_parse_iso(c.get("resolved_at")),
                resolved_by=id_mappings["users"].get(
                    c.get("resolved_by"), c.get("resolved_by")
                ),
                created_by=id_mappings["users"].get(
                    c.get("created_by"), current_user.id
                ),
            ))

        # Import project members (map to existing users)
        for member_data in _stream_rows(db, spooled, "project_members.item"):
            old_member_id = member_data.get("id", str(uuid.uuid4()))
            new_member_id = str(uuid.uuid4())
            id_mappings["project_members"][old_member_id] = new_member_id

            user_id = id_mappings["users"].get(member_data.get("user_id"))

            if user_id:  # Only import if user mapping exists
                # Check if membership already exists
                existing_member = (
                    db.query(ProjectMember)
                    .filter(
                        ProjectMember.project_id == new_project_id, ProjectMember.user_id == user_id
                    )
                    .first()
                )

                if not existing_member:
                    new_member = ProjectMember(
                        id=new_member_id,
                        project_id=new_project_id,
                        user_id=user_id,
                        role=member_data.get("role", "annotator"),
                        is_active=member_data.get("is_active", True),
                    )

                    db.add(new_member)

        # Import task assignments
        for assignment_data in _stream_rows(db, spooled, "task_assignments.item"):
            old_assignment_id = assignment_data.get("id", str(uuid.uuid4()))
            new_assignment_id = str(uuid.uuid4())
            id_mappings["task_assignments"][old_assignment_id] = new_assignment_id

            task_id = id_mappings["tasks"].get(assignment_data.get("task_id"))
            user_id = id_mappings["users"].get(assignment_data.get("user_id"))
            assigned_by = id_mappings["users"].get(
                assignment_data.get("assigned_by"), current_user.id
            )

            if task_id and user_id:  # Only import if both mappings exist
                new_assignment = TaskAssignment(
                    id=new_assignment_id,
                    project_id=new_project_id,
                    task_id=task_id,
                    user_id=user_id,
                    assigned_by=assigned_by,
                    status=assignment_data.get("status", "assigned"),
                )

                db.add(new_assignment)

        # Import post-annotation questionnaire responses (Issue #1208)
        for par_data in _stream_rows(db, spooled, "post_annotation_responses.item"):
            old_par_id = par_data.get("id", str(uuid.uuid4()))
            new_par_id = str(uuid.uuid4())
            id_mappings["post_annotation_responses"][old_par_id] = new_par_id

            annotation_id = id_mappings["annotations"].get(par_data.get("annotation_id"))
            task_id = id_mappings["tasks"].get(par_data.get("task_id"))
            user_id = id_mappings["users"].get(par_data.get("user_id"), current_user.id)

            if annotation_id and task_id:
                new_par = PostAnnotationResponse(
                    id=new_par_id,
                    annotation_id=annotation_id,
                    task_id=task_id,
                    project_id=new_project_id,
                    user_id=user_id,
                    result=par_data.get("result", []),
                )

                db.add(new_par)

        # Commit all changes
        db.commit()

        # Send notification
        try:
            notify_project_created(new_project_id, current_user.id)
        except Exception as e:
            # Don't fail import if notification fails
            print(f"Failed to send project import notification: {e}")

        # Calculate import statistics
        import_stats = {
            "project_created": True,
            "original_project_id": original_project_id,
            "new_project_id": new_project_id,
            "original_title": original_title,
            "new_title": new_title,
            "imported_counts": {
                "tasks": len(id_mappings["tasks"]),
                "annotations": len(id_mappings["annotations"]),
                "predictions": len(id_mappings["predictions"]),
                "generations": len(id_mappings["generations"]),
                "response_generations": len(id_mappings["response_generations"]),
                "evaluations": len(id_mappings["evaluations"]),
                "evaluation_metrics": len(id_mappings["evaluation_metrics"]),
                "task_evaluations": te_seen,
                "human_evaluation_configs": len(id_mappings["human_evaluation_configs"]),
                "human_evaluation_sessions": len(id_mappings["human_evaluation_sessions"]),
                "human_evaluation_results": len(id_mappings["human_evaluation_results"]),
                "preference_rankings": len(id_mappings["preference_rankings"]),
                "likert_scale_evaluations": len(id_mappings["likert_scale_evaluations"]),
                "prompts": len(id_mappings["prompts"]),
                "project_members": len(id_mappings["project_members"]),
                "task_assignments": len(id_mappings["task_assignments"]),
                "post_annotation_responses": len(id_mappings["post_annotation_responses"]),
            },
        }

        return {
            "message": "Project imported successfully",
            "project_id": new_project_id,
            "project_title": new_title,
            "project_url": f"/projects/{new_project_id}",
            "statistics": import_stats,
        }

    except HTTPException:
        # Validation / access errors keep their status; roll back any rows
        # flushed by an earlier batch so a partial project can't persist.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        spooled.close()
