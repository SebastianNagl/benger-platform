"""Streaming, memory-bounded project-import drivers (issue #158).

Single source of truth for parsing and inserting both project-import payload
formats. Lives under /shared so BOTH the API import endpoints and the Celery
import worker call the exact same code, the way export_stream is shared for the
export side.

It deliberately avoids any FastAPI / Pydantic import: the workers container
carries sqlalchemy + ijson + boto3 only (no fastapi, no pydantic), so a /shared
module that pulled those in would fail to import there. Client-correctable
problems are raised as ``ImportValidationError`` (carrying the HTTP status the
endpoints used to raise); the API layer rebuilds the matching ``HTTPException``,
and the worker records the message on the job row.

Two drivers, mirroring the two endpoints:

- ``run_nested_import(db, project_id, fileobj, user_id)`` — the nested
  Label-Studio payload imported into an *existing* project (``POST /import``).
- ``run_full_project_import(db, fileobj, user_id)`` — the flat comprehensive
  payload that *creates* a new project (``POST /import-project``).

Both take a seekable binary file object already filled with the upload body
(``SpooledTemporaryFile`` / ``io.BytesIO``); the caller streams the request body
or downloads the storage object into one first. Memory stays O(batch): only a
whitelist of small top-level fields is materialized; every big array is streamed
one element at a time and the session identity map is flushed + expunged every
``_IMPORT_BATCH`` rows.
"""

import gzip
import json
import logging
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, Iterator, Optional, Set, Tuple

import ijson
from ijson.common import ObjectBuilder
from sqlalchemy.orm import joinedload

# models must be imported before project_models so the User mapper is registered
# when project_models' relationships resolve (see benger-platform CLAUDE.md).
from models import (
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
from project_models import (
    Annotation,
    KorrekturComment,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from serializers import _parse_iso

logger = logging.getLogger(__name__)

# Spool incoming import bodies in RAM up to this size; spill to disk above it.
# Keeps small imports allocation-free while bounding peak heap on multi-MB
# imports — the API-side mirror of the proxy's response-streaming fix (GH #68).
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024

# Flush + expunge inserted rows every N tasks so the SQLAlchemy identity map
# (and thus peak heap) stays O(batch) instead of O(file) during a large import.
_IMPORT_BATCH = 200

# Small top-level keys of the nested (Label-Studio) import payload that are safe
# to fully materialize. The big `data` array is streamed separately via
# iter_array, never built into RAM. Mirrors the optional fields the endpoint's
# ProjectImportData schema used to validate.
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

# Opening ijson events that begin a JSON value, used to classify each top-level
# key (so callers can assert e.g. ``data`` is an array → 422 otherwise).
_VALUE_OPENING_EVENTS = frozenset(
    {"start_map", "start_array", "null", "boolean", "number", "string"}
)


class ImportValidationError(Exception):
    """A client-correctable import problem (maps to an HTTP 4xx).

    Carries the HTTP status + detail so the API endpoints can rebuild the exact
    ``HTTPException`` they used to raise, while keeping this /shared module free
    of any FastAPI dependency (the workers container has no fastapi installed).
    The worker records ``detail`` on the failed job row instead.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def read_top_object(
    fileobj, include_keys: Set[str]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Stream a top-level JSON object once, building only ``include_keys``.

    Returns ``(values, kinds)``:
      - ``values[k]`` is the fully-built Python value for each ``k`` in
        ``include_keys`` that is present in the document.
      - ``kinds[k]`` is the opening ijson event (``"start_array"``,
        ``"start_map"``, ``"string"``, ``"number"``, ``"boolean"``, ``"null"``)
        for *every* top-level key, including ones not in ``include_keys``. This
        lets callers validate structure (e.g. that ``data`` is an array)
        without materializing it.

    Keys outside ``include_keys`` are parsed-through and discarded, so memory
    stays bounded by the size of the included (small) values, not the file.

    Raises ``ijson.JSONError`` (incl. ``IncompleteJSONError``) on malformed
    JSON. A non-object top level (e.g. a bare array) yields empty results — the
    caller can treat a missing required key as the error.
    """
    fileobj.seek(0)
    values: Dict[str, Any] = {}
    kinds: Dict[str, str] = {}
    current_key = None
    builder = None
    awaiting_open = False

    def _flush_current():
        nonlocal current_key, builder
        if current_key is not None and builder is not None:
            values[current_key] = getattr(builder, "value", None)
        current_key = None
        builder = None

    # use_float=True parses JSON numbers as float, matching json.load. Without
    # it ijson yields decimal.Decimal, which psycopg2 cannot serialize into a
    # JSON/JSONB column ("Object of type Decimal is not JSON serializable").
    for prefix, event, value in ijson.parse(fileobj, use_float=True):
        if prefix == "" and event == "map_key":
            # New top-level key: close out the previous one.
            _flush_current()
            current_key = value
            awaiting_open = True
            builder = ObjectBuilder() if value in include_keys else None
            continue
        if prefix == "" and event in ("start_map", "end_map"):
            # The outer object's own braces. end_map closes the last key.
            if event == "end_map":
                _flush_current()
            continue
        # Any other event belongs to the current top-level key's value.
        if awaiting_open and current_key is not None and event in _VALUE_OPENING_EVENTS:
            kinds[current_key] = event
            awaiting_open = False
        if builder is not None:
            builder.event(event, value)

    return values, kinds


def iter_array(fileobj, path: str) -> Iterator[Any]:
    """Yield elements of a top-level array one at a time.

    ``path`` is an ijson item path such as ``"data.item"`` or ``"tasks.item"``.
    Re-seeks to the start so the same spooled file can be streamed in multiple
    independent passes (e.g. a user-id pre-pass then the main insert pass).
    """
    fileobj.seek(0)
    # use_float=True: see read_top_object — keep float semantics so values land
    # in JSON columns without a Decimal serialization error.
    yield from ijson.items(fileobj, path, use_float=True)


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


def convert_from_label_studio_format(results: list) -> list:
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


class _NestedTopFields:
    """Type-checked view of the nested import payload's small top-level fields.

    The pure-python replacement for the endpoint's ``ProjectImportData`` Pydantic
    model (which can't be imported in the workers container). Validates the same
    field types the schema did — ``meta`` an object, the side-arrays lists — and
    raises ``ImportValidationError(422)`` on a mismatch, matching the old 422.
    The big ``data`` array is never passed here; it is streamed separately.
    """

    _OPTIONAL_LIST_KEYS = (
        "evaluation_runs",
        "human_evaluation_configs",
        "human_evaluation_sessions",
        "human_evaluation_results",
        "preference_rankings",
        "likert_scale_evaluations",
        "korrektur_comments",
    )

    def __init__(self, top_obj: Dict[str, Any]):
        meta = top_obj.get("meta")
        if meta is not None and not isinstance(meta, dict):
            raise ImportValidationError(422, "Field 'meta' must be an object")
        self.meta = meta
        for key in self._OPTIONAL_LIST_KEYS:
            value = top_obj.get(key)
            if value is not None and not isinstance(value, list):
                raise ImportValidationError(422, f"Field '{key}' must be a list")
            setattr(self, key, value)


def run_nested_import(db, project_id: str, fileobj, user_id: str) -> dict:
    """Import a nested Label-Studio payload into an existing project.

    Streams ``fileobj`` (a seekable spool already filled with the body) and
    inserts tasks/annotations/generations/evaluations into ``project_id``,
    committing once at the end. Does NOT roll back on failure — the caller owns
    transaction cleanup (the endpoint rolls back + maps exceptions to HTTP; the
    worker rolls back + marks the job failed). Raises ``ImportValidationError``
    for malformed / mistyped payloads (HTTP 422 equivalent).

    A gzip-compressed upload is inflated transparently before parsing so a
    gzipped Label-Studio body imports like a plain one.
    """
    fileobj = _maybe_decompress(fileobj)

    created_tasks = 0
    created_annotations = 0
    created_generations = 0
    created_questionnaire_responses = 0
    created_evaluation_runs = 0
    created_task_evaluations = 0
    total_items = 0
    task_id_mapping: Dict[str, str] = {}
    generation_id_mapping: Dict[str, str] = {}  # old generation id -> new generation id
    annotation_id_mapping: Dict[str, str] = {}  # old annotation id -> new annotation id

    # Build the small top-level fields (meta, evaluation_runs, the human-eval
    # arrays, korrektur_comments); the big `data` array is parsed-through and
    # discarded here, then streamed below. Malformed JSON → 422 (matches the
    # old json.load behaviour); `data` missing / not a list → 422 (matches the
    # old Pydantic List[...] requirement).
    try:
        top_obj, kinds = read_top_object(fileobj, _NESTED_SMALL_KEYS)
    except ijson.JSONError as exc:
        raise ImportValidationError(422, f"Invalid JSON body: {exc}")
    if kinds.get("data") != "start_array":
        raise ImportValidationError(
            422, "Field 'data' is required and must be a list"
        )
    # Validate the small fields' types exactly as ProjectImportData did
    # (the streamed `data` items are dict-checked per row below).
    data = _NestedTopFields(top_obj)

    # Import evaluation runs first so task evaluations can reference them
    evaluation_run_id_mapping: Dict[str, str] = {}  # old er id -> new er id
    # Migration 043: TaskEvaluation.judge_run_id is NOT NULL. Legacy exports
    # pre-date the column; create one synthetic catch-all judge_run per imported
    # EvaluationRun (mirroring 043's backfill) so TaskEvaluations without an
    # explicit judge_run_id can attach.
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
                created_by=er_data.get("created_by", user_id),
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

    # Create stub users for any referenced user IDs that don't exist locally.
    # This preserves original annotator IDs from the export. Cheap streaming
    # pre-pass over `data` reading only annotator ids (one task at a time).
    import_user_ids = set()
    for item in iter_array(fileobj, "data.item"):
        if isinstance(item, dict):
            for ann in item.get("annotations", []):
                if ann.get("completed_by"):
                    import_user_ids.add(ann["completed_by"])
                if ann.get("reviewed_by"):
                    import_user_ids.add(ann["reviewed_by"])
    if import_user_ids:
        existing_ids = {
            u.id for u in db.query(User.id).filter(User.id.in_(import_user_ids)).all()
        }
        missing_ids = import_user_ids - existing_ids
        for uid in missing_ids:
            stub = User(
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

    for item in iter_array(fileobj, "data.item"):
        # The old Pydantic List[Dict] rejected non-dict items with a 422;
        # preserve that now that items are validated one-at-a-time.
        if not isinstance(item, dict):
            raise ImportValidationError(
                422, "Each entry in 'data' must be an object"
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
                completed_by=ann_data.get("completed_by", user_id),
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
                    user_id=ann_data.get("completed_by", user_id),
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
                        created_by=user_id,
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
                        # Migration 042: forward judge_run_id when the export
                        # carries it. Older exports pre-date the field; fall back
                        # to the synthetic catch-all judge_run created above for
                        # this evaluation_run (mirrors migration 043's backfill).
                        judge_run_id=eval_data.get("judge_run_id")
                            or evaluation_run_judge_run.get(new_er_id),  # noqa: E131
                    )
                    db.add(te)
                    created_task_evaluations += 1

        # Import task-level evaluations (annotation/ground-truth evals without
        # generation). Flush so any pending Annotation rows from earlier in this
        # iteration are visible when the TaskEvaluation FK to annotations is
        # validated at commit.
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

        # Bound peak heap: once a batch of tasks is inserted, flush so the rows
        # hit the DB, then drop them from the session identity map. Everything
        # downstream cross-references via string id maps (not ORM objects), so
        # detaching is safe and keeps memory O(batch), not O(file).
        if created_tasks % _IMPORT_BATCH == 0:
            db.flush()
            db.expunge_all()

    # Top-level human-evaluation import (mirrors clone path). Skip silently if
    # the payload doesn't carry any of these arrays — backward-compatible with
    # older exports.
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
            evaluator_id=session.get("evaluator_id", user_id),
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

    # Korrektur threaded comments (parents first, then replies, so parent_id can
    # be remapped without forward references).
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
            # We don't track per-row TaskEvaluation id mapping (rows get fresh
            # UUIDs); leave as-is so the user can re-link manually if needed.
            # Most korrektur comments target annotations.
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
            created_by=c.get("created_by", user_id),
        ))

    # Commit everything atomically
    db.commit()

    # Update report data section after task import (Issue #770). Best-effort:
    # lazy-import so a worker that can't import report_service still finishes.
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


class _FullImportContext:
    """Mutable shared state threaded through the per-entity insert helpers.

    The comprehensive importer remaps every FK from the export's old ids to the
    freshly-minted ids of the imported project. ``id_mappings`` holds those
    old→new dicts; ``task_counter``/``te_seen``/``comment_id_mapping`` are the
    running counters/lookup the passes mutate. Extracted so the legacy multi-pass
    importer (``run_full_project_import``) and the single-pass NDJSON importer
    (``run_ndjson_import``) drive the *same* insert logic — multi-pass calls a
    helper once per array element, single-pass calls it once per typed line.
    """

    __slots__ = (
        "db",
        "user_id",
        "new_project_id",
        "id_mappings",
        "user_email_to_id",
        "task_counter",
        "te_seen",
        "comment_id_mapping",
        "catchall_judge_runs",
    )

    def __init__(self, db, user_id: str):
        self.db = db
        self.user_id = user_id
        self.new_project_id: Optional[str] = None
        self.id_mappings: Dict[str, Dict] = {
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
            "judge_runs": {},
            "evaluation_metrics": {},
            "human_evaluation_configs": {},
            "human_evaluation_sessions": {},
            "human_evaluation_results": {},
            "preference_rankings": {},
            "likert_scale_evaluations": {},
            "post_annotation_responses": {},
        }
        self.user_email_to_id: Dict[str, str] = {}
        self.task_counter = 1
        self.te_seen = 0
        self.comment_id_mapping: Dict[str, str] = {}
        # evaluation_run new-id -> synthetic catch-all judge-run id. Lazily
        # populated when a task_evaluation references no (or an unmapped)
        # judge_run_id, mirroring migration 043's NOT NULL backfill.
        self.catchall_judge_runs: Dict[str, str] = {}


def _insert_user(ctx: _FullImportContext, user_data: dict) -> None:
    """Map an exported user to an existing user (by email) or the importer.

    No row is inserted — imported projects reuse the importing org's users.
    Populates ``id_mappings["users"]`` so downstream FKs (created_by, etc.) can
    be remapped.
    """
    old_user_id = user_data.get("id", str(uuid.uuid4()))
    email = user_data.get("email")

    if email:
        existing_user = ctx.db.query(User).filter(User.email == email).first()
        if existing_user:
            ctx.id_mappings["users"][old_user_id] = existing_user.id
            ctx.user_email_to_id[email] = existing_user.id
        else:
            # For now, map to current importing user as fallback
            ctx.id_mappings["users"][old_user_id] = ctx.user_id
            ctx.user_email_to_id[email] = ctx.user_id
    else:
        # No email, map to current user
        ctx.id_mappings["users"][old_user_id] = ctx.user_id


def _insert_task(ctx: _FullImportContext, task_data: dict) -> None:
    old_task_id = task_data.get("id", str(uuid.uuid4()))
    new_task_id = str(uuid.uuid4())
    ctx.id_mappings["tasks"][old_task_id] = new_task_id

    created_by = ctx.id_mappings["users"].get(task_data.get("created_by"), ctx.user_id)
    updated_by = ctx.id_mappings["users"].get(task_data.get("updated_by"))

    new_task = Task(
        id=new_task_id,
        project_id=ctx.new_project_id,
        inner_id=ctx.task_counter,  # Recalculate inner IDs
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

    ctx.db.add(new_task)
    ctx.task_counter += 1


def _insert_annotation(ctx: _FullImportContext, annotation_data: dict) -> None:
    old_annotation_id = annotation_data.get("id", str(uuid.uuid4()))
    new_annotation_id = str(uuid.uuid4())
    ctx.id_mappings["annotations"][old_annotation_id] = new_annotation_id

    task_id = ctx.id_mappings["tasks"].get(annotation_data.get("task_id"))
    completed_by = ctx.id_mappings["users"].get(
        annotation_data.get("completed_by"), ctx.user_id
    )
    if task_id:  # Only import if task exists
        # Issue #964: Convert Label Studio span annotations to BenGER format
        imported_result = convert_from_label_studio_format(
            annotation_data.get("result", [])
        )
        new_annotation = Annotation(
            id=new_annotation_id,
            task_id=task_id,
            project_id=ctx.new_project_id,
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
            reviewed_by=ctx.id_mappings["users"].get(
                annotation_data.get("reviewed_by"),
                annotation_data.get("reviewed_by"),
            ),
            reviewed_at=_parse_iso(annotation_data.get("reviewed_at")),
            review_result=annotation_data.get("review_result"),
            review_annotation=annotation_data.get("review_annotation"),
            review_comment=annotation_data.get("review_comment"),
        )

        ctx.db.add(new_annotation)


def _insert_response_generation(ctx: _FullImportContext, resp_gen_data: dict) -> None:
    old_resp_gen_id = resp_gen_data.get("id", str(uuid.uuid4()))
    new_resp_gen_id = str(uuid.uuid4())
    ctx.id_mappings["response_generations"][old_resp_gen_id] = new_resp_gen_id

    task_id = ctx.id_mappings["tasks"].get(resp_gen_data.get("task_id"))
    created_by = ctx.id_mappings["users"].get(resp_gen_data.get("created_by"), ctx.user_id)

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

        ctx.db.add(new_resp_gen)


def _insert_generation(ctx: _FullImportContext, generation_data: dict) -> None:
    old_generation_id = generation_data.get("id", str(uuid.uuid4()))
    new_generation_id = str(uuid.uuid4())
    ctx.id_mappings["generations"][old_generation_id] = new_generation_id

    task_id = ctx.id_mappings["tasks"].get(generation_data.get("task_id"))
    generation_id = ctx.id_mappings["response_generations"].get(
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

        ctx.db.add(new_generation)


def _insert_evaluation(ctx: _FullImportContext, evaluation_data: dict) -> None:
    old_evaluation_id = evaluation_data.get("id", str(uuid.uuid4()))
    new_evaluation_id = str(uuid.uuid4())
    ctx.id_mappings["evaluations"][old_evaluation_id] = new_evaluation_id

    created_by = ctx.id_mappings["users"].get(
        evaluation_data.get("created_by"), ctx.user_id
    )

    new_evaluation = EvaluationRun(
        id=new_evaluation_id,
        project_id=ctx.new_project_id,
        task_id=ctx.id_mappings["tasks"].get(evaluation_data.get("task_id")),
        model_id=evaluation_data.get("model_id"),
        evaluation_type_ids=evaluation_data.get("evaluation_type_ids", []),
        metrics=evaluation_data.get("metrics", {}),
        eval_metadata=evaluation_data.get("eval_metadata"),
        status=evaluation_data.get("status", "completed"),
        error_message=evaluation_data.get("error_message"),
        samples_evaluated=evaluation_data.get("samples_evaluated"),
        created_by=created_by,
    )

    ctx.db.add(new_evaluation)


def _insert_evaluation_metric(ctx: _FullImportContext, metric_data: dict) -> None:
    old_metric_id = metric_data.get("id", str(uuid.uuid4()))
    new_metric_id = str(uuid.uuid4())
    ctx.id_mappings["evaluation_metrics"][old_metric_id] = new_metric_id

    evaluation_id = ctx.id_mappings["evaluations"].get(metric_data.get("evaluation_id"))

    if evaluation_id:  # Only import if evaluation exists
        new_metric = EvaluationRunMetric(
            id=new_metric_id,
            evaluation_id=evaluation_id,
            evaluation_type_id=metric_data.get("evaluation_type_id"),
            value=metric_data.get("value", 0.0),
        )

        ctx.db.add(new_metric)


def _insert_evaluation_judge_run(ctx: _FullImportContext, jr_data: dict) -> None:
    # Recreate the per-judge-run child (migration 042) so TaskEvaluation.judge_run_id
    # (NOT NULL since 043) can be remapped to a real row in the imported project.
    evaluation_id = ctx.id_mappings["evaluations"].get(jr_data.get("evaluation_id"))
    if not evaluation_id:  # parent evaluation run wasn't imported; skip
        return
    old_jr_id = jr_data.get("id", str(uuid.uuid4()))
    new_jr_id = str(uuid.uuid4())
    ctx.id_mappings["judge_runs"][old_jr_id] = new_jr_id
    ctx.db.add(EvaluationJudgeRun(
        id=new_jr_id,
        evaluation_id=evaluation_id,
        judge_model_id=jr_data.get("judge_model_id"),
        run_index=jr_data.get("run_index", 0),
        status=jr_data.get("status", "completed"),
        samples_evaluated=jr_data.get("samples_evaluated"),
        error_message=jr_data.get("error_message"),
        metric_parameters_snapshot=jr_data.get("metric_parameters_snapshot"),
    ))


def _get_or_create_catchall_judge_run(
    ctx: _FullImportContext, evaluation_id: str
) -> str:
    # Legacy exports (and any task_evaluation whose judge_run_id didn't resolve)
    # have no judge-run row to attach to. Mirror migration 043's backfill: one
    # synthetic catch-all judge run per evaluation run, created on first need.
    existing = ctx.catchall_judge_runs.get(evaluation_id)
    if existing:
        return existing
    jr_id = str(uuid.uuid4())
    ctx.db.add(EvaluationJudgeRun(
        id=jr_id,
        evaluation_id=evaluation_id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    ))
    ctx.catchall_judge_runs[evaluation_id] = jr_id
    return jr_id


def _insert_task_evaluation(ctx: _FullImportContext, te_data: dict) -> None:
    # te_seen counts every row in the payload (imported or skipped) to reproduce
    # the old len(import_data["task_evaluations"]) stat without holding the array.
    ctx.te_seen += 1
    te_data.get("id", str(uuid.uuid4()))
    new_te_id = str(uuid.uuid4())

    evaluation_id = ctx.id_mappings["evaluations"].get(te_data.get("evaluation_id"))
    task_id = ctx.id_mappings["tasks"].get(te_data.get("task_id"))
    generation_id = ctx.id_mappings["generations"].get(te_data.get("generation_id"))

    if evaluation_id and task_id:
        # Resolve judge_run_id (NOT NULL since migration 043). Prefer the
        # remapped real judge run exported alongside the task_evaluation; fall
        # back to a synthetic catch-all when the payload carried no judge_run_id
        # or referenced one that wasn't imported (legacy exports).
        judge_run_id = (
            ctx.id_mappings["judge_runs"].get(te_data.get("judge_run_id"))
            if te_data.get("judge_run_id") else None
        )
        if judge_run_id is None:
            judge_run_id = _get_or_create_catchall_judge_run(ctx, evaluation_id)

        new_te = TaskEvaluation(
            id=new_te_id,
            evaluation_id=evaluation_id,
            task_id=task_id,
            generation_id=generation_id,
            annotation_id=ctx.id_mappings["annotations"].get(
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
            judge_run_id=judge_run_id,
        )

        ctx.db.add(new_te)


def _insert_human_evaluation_config(ctx: _FullImportContext, config_data: dict) -> None:
    old_config_id = config_data.get("id", str(uuid.uuid4()))
    new_config_id = str(uuid.uuid4())
    ctx.id_mappings["human_evaluation_configs"][old_config_id] = new_config_id

    task_id = ctx.id_mappings["tasks"].get(config_data.get("task_id"))

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

        ctx.db.add(new_config)


def _insert_human_evaluation_session(ctx: _FullImportContext, session_data: dict) -> None:
    old_session_id = session_data.get("id", str(uuid.uuid4()))
    new_session_id = str(uuid.uuid4())
    ctx.id_mappings["human_evaluation_sessions"][old_session_id] = new_session_id

    evaluator_id = ctx.id_mappings["users"].get(
        session_data.get("evaluator_id"), ctx.user_id
    )

    new_session = HumanEvaluationSession(
        id=new_session_id,
        project_id=ctx.new_project_id,
        evaluator_id=evaluator_id,
        session_type=session_data.get("session_type", "likert"),
        items_evaluated=session_data.get("items_evaluated", 0),
        total_items=session_data.get("total_items"),
        status=session_data.get("status", "active"),
        session_config=session_data.get("session_config"),
    )

    ctx.db.add(new_session)


def _insert_human_evaluation_result(ctx: _FullImportContext, result_data: dict) -> None:
    old_result_id = result_data.get("id", str(uuid.uuid4()))
    new_result_id = str(uuid.uuid4())
    ctx.id_mappings["human_evaluation_results"][old_result_id] = new_result_id

    config_id = ctx.id_mappings["human_evaluation_configs"].get(result_data.get("config_id"))
    task_id = ctx.id_mappings["tasks"].get(result_data.get("task_id"))

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

        ctx.db.add(new_result)


def _insert_preference_ranking(ctx: _FullImportContext, ranking_data: dict) -> None:
    old_ranking_id = ranking_data.get("id", str(uuid.uuid4()))
    new_ranking_id = str(uuid.uuid4())
    ctx.id_mappings["preference_rankings"][old_ranking_id] = new_ranking_id

    session_id = ctx.id_mappings["human_evaluation_sessions"].get(
        ranking_data.get("session_id")
    )
    task_id = ctx.id_mappings["tasks"].get(ranking_data.get("task_id"))

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

        ctx.db.add(new_ranking)


def _insert_likert_scale_evaluation(ctx: _FullImportContext, likert_data: dict) -> None:
    old_likert_id = likert_data.get("id", str(uuid.uuid4()))
    new_likert_id = str(uuid.uuid4())
    ctx.id_mappings["likert_scale_evaluations"][old_likert_id] = new_likert_id

    session_id = ctx.id_mappings["human_evaluation_sessions"].get(likert_data.get("session_id"))
    task_id = ctx.id_mappings["tasks"].get(likert_data.get("task_id"))

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

        ctx.db.add(new_likert)


def _insert_korrektur_comment(ctx: _FullImportContext, c: dict) -> None:
    """Insert one Korrektur comment. Relies on parents being inserted before
    replies (the caller streams roots first, then replies) so ``parent_id`` can
    be remapped via ``comment_id_mapping`` without a forward reference.
    """
    target_type = c.get("target_type")
    old_target_id = c.get("target_id")
    new_target_id: Any = old_target_id
    if target_type == "annotation":
        new_target_id = ctx.id_mappings["annotations"].get(old_target_id, old_target_id)
    elif target_type == "generation":
        new_target_id = ctx.id_mappings["generations"].get(old_target_id, old_target_id)
    elif target_type == "evaluation":
        # Per-row TaskEvaluation mapping isn't tracked; leave as-is.
        new_target_id = old_target_id
    new_id = str(uuid.uuid4())
    old_id = c.get("id")
    if old_id:
        ctx.comment_id_mapping[old_id] = new_id
    new_task_id = ctx.id_mappings["tasks"].get(c.get("task_id"))
    if not new_task_id:
        return
    ctx.db.add(KorrekturComment(
        id=new_id,
        project_id=ctx.new_project_id,
        task_id=new_task_id,
        target_type=target_type,
        target_id=new_target_id,
        parent_id=ctx.comment_id_mapping.get(c.get("parent_id")),
        text=c.get("text", ""),
        highlight_start=c.get("highlight_start"),
        highlight_end=c.get("highlight_end"),
        highlight_text=c.get("highlight_text"),
        highlight_label=c.get("highlight_label"),
        is_resolved=c.get("is_resolved", False),
        resolved_at=_parse_iso(c.get("resolved_at")),
        resolved_by=ctx.id_mappings["users"].get(
            c.get("resolved_by"), c.get("resolved_by")
        ),
        created_by=ctx.id_mappings["users"].get(
            c.get("created_by"), ctx.user_id
        ),
    ))


def _insert_project_member(ctx: _FullImportContext, member_data: dict) -> None:
    old_member_id = member_data.get("id", str(uuid.uuid4()))
    new_member_id = str(uuid.uuid4())
    ctx.id_mappings["project_members"][old_member_id] = new_member_id

    member_user_id = ctx.id_mappings["users"].get(member_data.get("user_id"))

    if member_user_id:  # Only import if user mapping exists
        # Check if membership already exists
        existing_member = (
            ctx.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == ctx.new_project_id,
                ProjectMember.user_id == member_user_id,
            )
            .first()
        )

        if not existing_member:
            new_member = ProjectMember(
                id=new_member_id,
                project_id=ctx.new_project_id,
                user_id=member_user_id,
                role=member_data.get("role", "annotator"),
                is_active=member_data.get("is_active", True),
            )

            ctx.db.add(new_member)


def _insert_task_assignment(ctx: _FullImportContext, assignment_data: dict) -> None:
    old_assignment_id = assignment_data.get("id", str(uuid.uuid4()))
    new_assignment_id = str(uuid.uuid4())
    ctx.id_mappings["task_assignments"][old_assignment_id] = new_assignment_id

    task_id = ctx.id_mappings["tasks"].get(assignment_data.get("task_id"))
    assignment_user_id = ctx.id_mappings["users"].get(assignment_data.get("user_id"))
    assigned_by = ctx.id_mappings["users"].get(
        assignment_data.get("assigned_by"), ctx.user_id
    )

    if task_id and assignment_user_id:  # Only import if both mappings exist
        new_assignment = TaskAssignment(
            id=new_assignment_id,
            project_id=ctx.new_project_id,
            task_id=task_id,
            user_id=assignment_user_id,
            assigned_by=assigned_by,
            status=assignment_data.get("status", "assigned"),
        )

        ctx.db.add(new_assignment)


def _insert_post_annotation_response(ctx: _FullImportContext, par_data: dict) -> None:
    old_par_id = par_data.get("id", str(uuid.uuid4()))
    new_par_id = str(uuid.uuid4())
    ctx.id_mappings["post_annotation_responses"][old_par_id] = new_par_id

    annotation_id = ctx.id_mappings["annotations"].get(par_data.get("annotation_id"))
    task_id = ctx.id_mappings["tasks"].get(par_data.get("task_id"))
    par_user_id = ctx.id_mappings["users"].get(par_data.get("user_id"), ctx.user_id)

    if annotation_id and task_id:
        new_par = PostAnnotationResponse(
            id=new_par_id,
            annotation_id=annotation_id,
            task_id=task_id,
            project_id=ctx.new_project_id,
            user_id=par_user_id,
            result=par_data.get("result", []),
        )

        ctx.db.add(new_par)


def _create_imported_project(
    ctx: _FullImportContext, project_data: dict, new_title: str
):
    """Create the new Project row (+ ProjectOrganization) from project_data.

    Shared by the multi-pass and NDJSON importers. Sets ``ctx.new_project_id``
    and records the old→new project id mapping. Raises ``ImportValidationError``
    (400) when the importing user has no active organization to own the project.
    """
    # Get user's primary organization for the imported project
    user_with_memberships = (
        ctx.db.query(User)
        .options(joinedload(User.organization_memberships))
        .filter(User.id == ctx.user_id)
        .first()
    )
    if not user_with_memberships or not user_with_memberships.organization_memberships:
        raise ImportValidationError(
            400, "User must belong to an organization to import projects"
        )

    # Use the first active organization membership
    primary_membership = next(
        (m for m in user_with_memberships.organization_memberships if m.is_active), None
    )
    if not primary_membership:
        raise ImportValidationError(
            400, "User must have an active organization membership"
        )

    new_project_id = str(uuid.uuid4())
    # Only add to mappings if the original project had an ID
    original_project_id = project_data.get("id")
    if original_project_id:
        ctx.id_mappings["projects"][original_project_id] = new_project_id

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
        created_by=ctx.user_id,  # Current user is creator of imported project
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

    ctx.db.add(new_project)
    ctx.db.flush()  # Flush so FK references to project work

    # Create ProjectOrganization entry for the imported project
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=new_project_id,
        organization_id=primary_membership.organization_id,
        assigned_by=ctx.user_id,
    )
    ctx.db.add(project_org)

    ctx.new_project_id = new_project_id


def _notify_project_imported(ctx: "_FullImportContext", new_title: str) -> None:
    """Best-effort 'project created' notification for a freshly-imported project.

    Lazy-imports notification_service so a worker that can't import it still
    finishes the import, and swallows every error so a notification failure can
    never fail an otherwise-successful import. Resolves the creator name and the
    owning organization (always set by _create_imported_project) to satisfy the
    notify_project_created(db, project_id, title, creator_name, org_id) signature
    — the previous 2-arg call raised TypeError and silently dropped the notice.
    """
    try:
        from notification_service import notify_project_created

        creator = ctx.db.query(User).filter(User.id == ctx.user_id).first()
        project_org = (
            ctx.db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == ctx.new_project_id)
            .first()
        )
        if project_org is None:
            return
        notify_project_created(
            db=ctx.db,
            project_id=ctx.new_project_id,
            project_title=new_title,
            creator_name=creator.name if creator else "",
            organization_id=project_org.organization_id,
        )
    except Exception as e:
        logger.warning(f"Failed to send project import notification: {e}")


def _build_full_import_stats(
    ctx: _FullImportContext,
    *,
    original_project_id,
    original_title: str,
    new_title: str,
) -> dict:
    """Assemble the import-statistics summary from the context's id_mappings."""
    return {
        "project_created": True,
        "original_project_id": original_project_id,
        "new_project_id": ctx.new_project_id,
        "original_title": original_title,
        "new_title": new_title,
        "imported_counts": {
            "tasks": len(ctx.id_mappings["tasks"]),
            "annotations": len(ctx.id_mappings["annotations"]),
            "predictions": len(ctx.id_mappings["predictions"]),
            "generations": len(ctx.id_mappings["generations"]),
            "response_generations": len(ctx.id_mappings["response_generations"]),
            "evaluations": len(ctx.id_mappings["evaluations"]),
            "evaluation_metrics": len(ctx.id_mappings["evaluation_metrics"]),
            "task_evaluations": ctx.te_seen,
            "human_evaluation_configs": len(ctx.id_mappings["human_evaluation_configs"]),
            "human_evaluation_sessions": len(ctx.id_mappings["human_evaluation_sessions"]),
            "human_evaluation_results": len(ctx.id_mappings["human_evaluation_results"]),
            "preference_rankings": len(ctx.id_mappings["preference_rankings"]),
            "likert_scale_evaluations": len(ctx.id_mappings["likert_scale_evaluations"]),
            "prompts": len(ctx.id_mappings["prompts"]),
            "project_members": len(ctx.id_mappings["project_members"]),
            "task_assignments": len(ctx.id_mappings["task_assignments"]),
            "post_annotation_responses": len(ctx.id_mappings["post_annotation_responses"]),
        },
    }


# Maps an NDJSON record's ``_type`` to the per-entity insert helper. ``meta`` and
# ``end`` are framing records handled inline (project creation / completeness
# check), not entity inserts, so they are deliberately absent here.
_NDJSON_INSERT_DISPATCH = {
    "user": _insert_user,
    "task": _insert_task,
    "annotation": _insert_annotation,
    "response_generation": _insert_response_generation,
    "generation": _insert_generation,
    "evaluation": _insert_evaluation,
    "evaluation_metric": _insert_evaluation_metric,
    "evaluation_judge_run": _insert_evaluation_judge_run,
    "task_evaluation": _insert_task_evaluation,
    "human_evaluation_config": _insert_human_evaluation_config,
    "human_evaluation_session": _insert_human_evaluation_session,
    "human_evaluation_result": _insert_human_evaluation_result,
    "preference_ranking": _insert_preference_ranking,
    "likert_scale_evaluation": _insert_likert_scale_evaluation,
    "korrektur_comment": _insert_korrektur_comment,
    "project_member": _insert_project_member,
    "task_assignment": _insert_task_assignment,
    "post_annotation_response": _insert_post_annotation_response,
}

# Bound how far first-line detection reads so a huge legacy compact-JSON file
# (whose first "line" is the whole document) can't be slurped into RAM just to
# decide the format. A real NDJSON meta record terminates well within this.
_NDJSON_DETECT_MAX = 1024 * 1024


def _iter_ndjson_records(fileobj) -> Iterator[Any]:
    """Yield one parsed JSON value per non-empty line of ``fileobj``.

    Re-seeks to the start, then streams line by line so peak heap stays bounded
    by the largest single record, never the whole file. Decodes bytes lines as
    UTF-8. ``json.loads`` errors (a corrupt / truncated line) propagate to the
    caller, which maps them to ``ImportValidationError``.
    """
    fileobj.seek(0)
    for raw in fileobj:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        line = raw.strip()
        if not line:
            continue
        yield json.loads(line)


# gzip member magic. A gzipped export (format "ndjson_gz") is stored as an
# opaque .gz blob, so the importer must inflate it before sniffing the format.
_GZIP_MAGIC = b"\x1f\x8b"
# Match the endpoint/worker spool threshold so a decompressed body spills to
# disk past 4MB instead of ballooning resident memory.
_DECOMPRESS_SPOOL_THRESHOLD = 4 * 1024 * 1024


def _maybe_decompress(fileobj):
    """Return a seekable plain-bytes stream, inflating gzip transparently.

    Detects a gzip member by its 2-byte magic and, when present, stream-inflates
    the whole body into a fresh ``SpooledTemporaryFile`` (spills to disk past the
    threshold) so the downstream multi-pass importer can re-seek repeatedly
    without re-inflating from the top each pass. Non-gzip input is returned
    untouched (seeked to 0). Used so a ``ndjson_gz`` export round-trips through
    the same import code as the uncompressed formats.
    """
    fileobj.seek(0)
    magic = fileobj.read(2)
    fileobj.seek(0)
    if magic != _GZIP_MAGIC:
        return fileobj
    out = tempfile.SpooledTemporaryFile(
        max_size=_DECOMPRESS_SPOOL_THRESHOLD, mode="w+b"
    )
    with gzip.GzipFile(fileobj=fileobj, mode="rb") as gz:
        shutil.copyfileobj(gz, out, length=1024 * 1024)
    out.seek(0)
    return out


def _is_ndjson_stream(fileobj) -> bool:
    """Return True if ``fileobj`` looks like our NDJSON typed-record export.

    Reads at most the first line (capped at ``_NDJSON_DETECT_MAX`` bytes so a
    newline-free legacy JSON body isn't fully read) and treats it as NDJSON only
    when it parses to a JSON object carrying a truthy ``_type``. Always seeks
    back to 0 so the chosen importer starts from the top. A legacy single-object
    JSON either fails to parse within the cap (pretty-printed → first line is
    ``{``) or parses without ``_type`` (compact) — both fall through to False.
    """
    fileobj.seek(0)
    first = fileobj.readline(_NDJSON_DETECT_MAX)
    fileobj.seek(0)
    if not first:
        return False
    if isinstance(first, bytes):
        try:
            first = first.decode("utf-8")
        except UnicodeDecodeError:
            return False
    first = first.strip()
    if not first:
        return False
    try:
        obj = json.loads(first)
    except ValueError:
        return False
    return isinstance(obj, dict) and bool(obj.get("_type"))


def run_ndjson_import(db, fileobj, user_id: str) -> dict:
    """Import an NDJSON typed-record comprehensive payload in a single pass.

    The NDJSON format frames the same comprehensive data as
    ``run_full_project_import`` but as one JSON object per line: a leading
    ``{"_type":"meta",...,"project":{...}}`` record, then flat entity records
    emitted in FK-dependency order (users → tasks → annotations → …), then a
    trailing ``{"_type":"end","statistics":{...},"export_complete":true}``
    record. Because records arrive in dependency order, a single forward pass
    suffices: each entity record is dispatched to the same ``_insert_<entity>``
    helper the multi-pass importer uses, so insert behaviour is identical.

    The trailing ``end`` record is the structural completeness check that
    replaces the legacy byte-tail sentinel — a stream that ends without it is
    treated as truncated and raises ``ImportValidationError(400)`` before the
    commit, so a partial import never lands. Does NOT roll back on failure — the
    caller owns transaction cleanup, matching ``run_full_project_import``.
    """
    records = _iter_ndjson_records(fileobj)

    # First record must be the meta header carrying the project + version.
    try:
        meta = next(records)
    except StopIteration:
        raise ImportValidationError(400, "Empty NDJSON export")
    except ValueError as exc:
        raise ImportValidationError(400, f"Invalid JSON format: {exc}")

    if not isinstance(meta, dict) or meta.get("_type") != "meta":
        raise ImportValidationError(
            400, "NDJSON export must start with a meta record"
        )

    format_version = meta.get("format_version", "1.0.0")
    if not str(format_version).startswith("1."):
        raise ImportValidationError(400, "Unsupported export format version")

    project_data = meta.get("project") or {}
    if not project_data:
        raise ImportValidationError(400, "No project data found in export")

    # Handle project name conflicts (same rename loop as the multi-pass path).
    original_title = project_data.get("title", "Imported Project")
    new_title = original_title
    counter = 1
    while db.query(Project).filter(Project.title == new_title).first():
        new_title = f"{original_title} ({counter})"
        counter += 1

    ctx = _FullImportContext(db, user_id)
    # Create the project (+ ProjectOrganization). Raises 400 if the importing
    # user has no active organization. Sets ctx.new_project_id.
    _create_imported_project(ctx, project_data, new_title)

    saw_end = False
    inserted = 0
    try:
        for record in records:
            if not isinstance(record, dict):
                raise ImportValidationError(
                    400, "Each NDJSON record must be an object"
                )
            rtype = record.get("_type")
            if rtype == "end":
                saw_end = True
                break
            if rtype == "meta":
                raise ImportValidationError(
                    400, "Unexpected second meta record in NDJSON export"
                )
            handler = _NDJSON_INSERT_DISPATCH.get(rtype)
            if handler is None:
                # Unknown record types are skipped for forward compatibility,
                # the way an unrecognized top-level array key simply isn't
                # streamed by the multi-pass importer.
                continue
            handler(ctx, record)
            inserted += 1
            # Bound heap O(batch): flush so rows hit the DB, then detach them
            # from the identity map. Cross-references travel via ctx id maps
            # (strings), never live ORM objects, so expunging is safe.
            if inserted % _IMPORT_BATCH == 0:
                db.flush()
                db.expunge_all()
    except ValueError as exc:
        # A corrupt / truncated line mid-stream → treat as a malformed export.
        raise ImportValidationError(400, f"Invalid JSON in NDJSON record: {exc}")

    if not saw_end:
        raise ImportValidationError(
            400, "Truncated NDJSON export: missing end record"
        )

    db.commit()

    _notify_project_imported(ctx, new_title)

    import_stats = _build_full_import_stats(
        ctx,
        original_project_id=project_data.get("id"),
        original_title=original_title,
        new_title=new_title,
    )

    return {
        "message": "Project imported successfully",
        "project_id": ctx.new_project_id,
        "project_title": new_title,
        "project_url": f"/projects/{ctx.new_project_id}",
        "statistics": import_stats,
    }


def run_full_project_import(db, fileobj, user_id: str) -> dict:
    """Import a flat comprehensive payload, creating a NEW project.

    Streams ``fileobj`` (a seekable spool already filled with the inner JSON;
    the caller extracts a ``.zip`` into it first) in FK-dependency order and
    commits once. Does NOT roll back on failure — the caller owns transaction
    cleanup. Raises ``ImportValidationError`` (HTTP 400 equivalent) for an
    unsupported version, missing project data, malformed JSON, or a user with no
    organization to own the imported project.

    Detects the serialization first: an NDJSON typed-record body (first line is a
    JSON object with a ``_type``) is handed to the single-pass
    ``run_ndjson_import``; everything else is treated as the legacy single-object
    JSON and streamed with the ijson multi-pass below. Legacy readers are kept
    indefinitely so users can always re-import older exports.

    A gzip-compressed body (the "ndjson_gz" export) is inflated transparently to
    a seekable spool before format detection, so .gz, NDJSON, and legacy JSON all
    funnel through this one entry point.
    """
    fileobj = _maybe_decompress(fileobj)

    if _is_ndjson_stream(fileobj):
        return run_ndjson_import(db, fileobj, user_id)

    # One streaming pass builds only the small top-level fields; malformed JSON
    # surfaces here (read_top_object parses through the whole document) and maps
    # to the same 400 the old json.load raised.
    try:
        top_obj, _kinds = read_top_object(fileobj, {"format_version", "project"})
    except ijson.JSONError:
        raise ImportValidationError(400, "Invalid JSON format")

    # Validate format version
    format_version = top_obj.get("format_version", "1.0.0")
    if not format_version.startswith("1."):
        raise ImportValidationError(400, "Unsupported export format version")

    # Extract project data
    project_data = top_obj.get("project", {})
    if not project_data:
        raise ImportValidationError(400, "No project data found in export")

    # Handle project name conflicts
    original_title = project_data.get("title", "Imported Project")
    new_title = original_title
    counter = 1

    while db.query(Project).filter(Project.title == new_title).first():
        new_title = f"{original_title} ({counter})"
        counter += 1

    # Stream the per-entity passes through the shared insert helpers so this
    # multi-pass importer and the single-pass NDJSON importer drive identical
    # insert logic. ctx carries the old→new id maps + running counters across
    # passes; every pass re-seeks the spool and streams one element at a time,
    # flushing + expunging every _IMPORT_BATCH rows to keep heap O(batch).
    ctx = _FullImportContext(db, user_id)

    # Map users to existing users (by email) or the importing user. No user rows
    # are inserted — imported projects reuse the importing org's users.
    for user_data in _stream_rows(db, fileobj, "users.item"):
        _insert_user(ctx, user_data)

    # Create the new project (+ ProjectOrganization). Raises 400 if the importing
    # user has no active organization. Sets ctx.new_project_id.
    _create_imported_project(ctx, project_data, new_title)

    # FK-dependency-ordered passes.
    for task_data in _stream_rows(db, fileobj, "tasks.item"):
        _insert_task(ctx, task_data)

    for annotation_data in _stream_rows(db, fileobj, "annotations.item"):
        _insert_annotation(ctx, annotation_data)

    # Note: Predictions import removed - predictions table dropped in migration 411540fa6c40
    # Prompts import removed - prompts table dropped in issue #759

    for resp_gen_data in _stream_rows(db, fileobj, "response_generations.item"):
        _insert_response_generation(ctx, resp_gen_data)

    for generation_data in _stream_rows(db, fileobj, "generations.item"):
        _insert_generation(ctx, generation_data)

    for evaluation_data in _stream_rows(db, fileobj, "evaluations.item"):
        _insert_evaluation(ctx, evaluation_data)

    for metric_data in _stream_rows(db, fileobj, "evaluation_metrics.item"):
        _insert_evaluation_metric(ctx, metric_data)

    # Judge runs before task_evaluations: the latter FK-reference them and the
    # column is NOT NULL (migration 043).
    for jr_data in _stream_rows(db, fileobj, "evaluation_judge_runs.item"):
        _insert_evaluation_judge_run(ctx, jr_data)

    for te_data in _stream_rows(db, fileobj, "task_evaluations.item"):
        _insert_task_evaluation(ctx, te_data)

    for config_data in _stream_rows(db, fileobj, "human_evaluation_configs.item"):
        _insert_human_evaluation_config(ctx, config_data)

    for session_data in _stream_rows(db, fileobj, "human_evaluation_sessions.item"):
        _insert_human_evaluation_session(ctx, session_data)

    for result_data in _stream_rows(db, fileobj, "human_evaluation_results.item"):
        _insert_human_evaluation_result(ctx, result_data)

    for ranking_data in _stream_rows(db, fileobj, "preference_rankings.item"):
        _insert_preference_ranking(ctx, ranking_data)

    for likert_data in _stream_rows(db, fileobj, "likert_scale_evaluations.item"):
        _insert_likert_scale_evaluation(ctx, likert_data)

    # Korrektur threaded comments: parents first, then replies, so parent_id can
    # be remapped without a forward reference. Two streaming passes (roots, then
    # replies) replace the old in-memory list+sort, which couldn't scale to a
    # huge comment array.
    def _korrektur_parents_then_replies():
        for c in _stream_rows(db, fileobj, "korrektur_comments.item"):
            if not c.get("parent_id"):
                yield c
        for c in _stream_rows(db, fileobj, "korrektur_comments.item"):
            if c.get("parent_id"):
                yield c

    for c in _korrektur_parents_then_replies():
        _insert_korrektur_comment(ctx, c)

    for member_data in _stream_rows(db, fileobj, "project_members.item"):
        _insert_project_member(ctx, member_data)

    for assignment_data in _stream_rows(db, fileobj, "task_assignments.item"):
        _insert_task_assignment(ctx, assignment_data)

    for par_data in _stream_rows(db, fileobj, "post_annotation_responses.item"):
        _insert_post_annotation_response(ctx, par_data)

    # Commit all changes
    db.commit()

    _notify_project_imported(ctx, new_title)

    import_stats = _build_full_import_stats(
        ctx,
        original_project_id=project_data.get("id"),
        original_title=original_title,
        new_title=new_title,
    )

    return {
        "message": "Project imported successfully",
        "project_id": ctx.new_project_id,
        "project_title": new_title,
        "project_url": f"/projects/{ctx.new_project_id}",
        "statistics": import_stats,
    }
