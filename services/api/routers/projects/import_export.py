"""Project import and export endpoints."""

import csv
import io
import json
import logging
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


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


from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import (
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
from notification_service import notify_project_created
from project_models import (
    Annotation,
    FeedbackComment,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from project_schemas import ProjectImportData
from routers.projects.helpers import check_project_accessible, get_comprehensive_project_data, get_org_context_from_request, get_user_with_memberships

router = APIRouter()


@router.post("/{project_id}/import")
async def import_project_data(
    project_id: str,
    data: ProjectImportData,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Import tasks and annotations into an existing project.

    Supports Label Studio format with BenGER extensions.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    created_tasks = 0
    created_annotations = 0
    created_generations = 0
    created_questionnaire_responses = 0
    created_evaluation_runs = 0
    created_task_evaluations = 0
    task_id_mapping = {}
    generation_id_mapping = {}  # old generation id -> new generation id

    try:
        # Import evaluation runs first so task evaluations can reference them
        evaluation_run_id_mapping = {}  # old er id -> new er id
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
                created_evaluation_runs += 1
                if old_er_id:
                    evaluation_run_id_mapping[old_er_id] = new_er_id

        for item in data.data:
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
                    reviewed_by=ann_data.get("reviewed_by"),
                    review_result=ann_data.get("review_result"),
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

                # Now create Generation records with proper generation_id references
                for gen_data in generations_to_import:
                    model_id = gen_data.get("model_id", "unknown")
                    response_gen_id = model_response_generations[model_id]

                    new_gen_id = str(uuid.uuid4())
                    original_gen_id = gen_data.get("id")
                    generation = Generation(
                        id=new_gen_id,
                        generation_id=response_gen_id,  # Link to ResponseGeneration
                        task_id=task_id,
                        model_id=model_id,
                        response_content=gen_data.get("response_content", ""),
                        # prompt_id removed in issue #759 - prompts now in project.generation_config (issue #817)
                        case_data=gen_data.get("case_data", json.dumps(task_data)),
                        response_metadata=gen_data.get("response_metadata"),
                        status="completed",  # Imported generations are completed
                    )
                    db.add(generation)
                    created_generations += 1

                    # Track ID mapping for evaluation import
                    if original_gen_id:
                        generation_id_mapping[original_gen_id] = new_gen_id

                    # Import generation-nested evaluations
                    for eval_data in gen_data.get("evaluations", []):
                        te_id = str(uuid.uuid4())
                        eval_run_id = eval_data.get("evaluation_run_id") or eval_data.get("evaluation_id")
                        te = TaskEvaluation(
                            id=te_id,
                            evaluation_id=evaluation_run_id_mapping.get(eval_run_id, eval_run_id),
                            task_id=task_id,
                            generation_id=new_gen_id,
                            field_name=eval_data.get("field_name"),
                            answer_type=eval_data.get("answer_type"),
                            ground_truth=eval_data.get("ground_truth"),
                            prediction=eval_data.get("prediction"),
                            metrics=eval_data.get("metrics"),
                            passed=eval_data.get("passed"),
                            confidence_score=eval_data.get("confidence_score"),
                            error_message=eval_data.get("error_message"),
                            processing_time_ms=eval_data.get("processing_time_ms"),
                        )
                        db.add(te)
                        created_task_evaluations += 1

            # Import task-level evaluations (annotation/ground-truth evals without generation)
            for eval_data in task_level_evaluations:
                te_id = str(uuid.uuid4())
                eval_run_id = eval_data.get("evaluation_run_id") or eval_data.get("evaluation_id")
                te = TaskEvaluation(
                    id=te_id,
                    evaluation_id=evaluation_run_id_mapping.get(eval_run_id, eval_run_id),
                    task_id=task_id,
                    generation_id=None,
                    field_name=eval_data.get("field_name"),
                    answer_type=eval_data.get("answer_type"),
                    ground_truth=eval_data.get("ground_truth"),
                    prediction=eval_data.get("prediction"),
                    metrics=eval_data.get("metrics"),
                    passed=eval_data.get("passed"),
                    confidence_score=eval_data.get("confidence_score"),
                    error_message=eval_data.get("error_message"),
                    processing_time_ms=eval_data.get("processing_time_ms"),
                )
                db.add(te)
                created_task_evaluations += 1

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
            "total_items": len(data.data),
            "project_id": project_id,
            "task_id_mapping": task_id_mapping,  # Return mapping for debugging/reference
        }

    except Exception as e:
        # Rollback on any error
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to import data: {str(e)}")


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

    # Get all tasks with annotations and generations
    tasks = db.query(Task).filter(Task.project_id == project_id).all()

    # Get all annotations for this project
    annotations = db.query(Annotation).filter(Annotation.project_id == project_id).all()

    # Get all generations for this project's tasks
    task_ids = [task.id for task in tasks]
    generations = (
        db.query(Generation).filter(Generation.task_id.in_(task_ids)).all() if task_ids else []
    )

    # Get all questionnaire responses for this project
    questionnaire_responses = (
        db.query(PostAnnotationResponse)
        .filter(PostAnnotationResponse.project_id == project_id)
        .all()
    )
    # Build lookup by annotation_id for O(1) access
    qr_by_annotation = {qr.annotation_id: qr for qr in questionnaire_responses}

    # Get all evaluation runs and per-task evaluations for this project
    evaluation_runs = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .all()
    )
    eval_run_ids = [er.id for er in evaluation_runs]
    task_evaluations = (
        db.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id.in_(eval_run_ids))
        .all()
        if eval_run_ids
        else []
    )

    from routers.projects.serializers import (
        build_evaluation_indexes,
        build_judge_model_lookup,
        serialize_annotation,
        serialize_evaluation_run,
        serialize_generation,
        serialize_task,
        serialize_task_evaluation,
    )

    eval_run_by_id = {er.id: er for er in evaluation_runs}
    judge_model_lookup = build_judge_model_lookup(evaluation_runs)
    te_by_task, te_by_generation = build_evaluation_indexes(task_evaluations)

    # Build export data
    export_data = {
        "project": {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "created_at": (project.created_at.isoformat() if project.created_at else None),
            "task_count": len(tasks),
            "annotation_count": len(annotations),
            "generation_count": len(generations),
            "evaluation_run_count": len(evaluation_runs),
            "task_evaluation_count": len(task_evaluations),
            "label_config": project.label_config,
        },
        "evaluation_runs": [
            serialize_evaluation_run(er, mode="data") for er in evaluation_runs
        ],
        "tasks": [],
    }

    # Add tasks with annotations and generations
    for task in tasks:
        task_data = serialize_task(task, mode="data")
        task_data["annotations"] = []
        task_data["generations"] = []
        task_data["evaluations"] = []

        # Add annotations for this task
        task_annotations = [a for a in annotations if a.task_id == task.id]
        for ann in task_annotations:
            qr = qr_by_annotation.get(ann.id)
            task_data["annotations"].append(
                serialize_annotation(ann, mode="data", questionnaire_response=qr)
            )

        # Add generations for this task (with nested evaluations)
        task_generations = [g for g in generations if g.task_id == task.id]
        for gen in task_generations:
            gen_evals = te_by_generation.get(gen.id, [])
            eval_dicts = [
                serialize_task_evaluation(
                    te, mode="data",
                    eval_run=eval_run_by_id.get(te.evaluation_id),
                    judge_model_lookup=judge_model_lookup,
                )
                for te in gen_evals
            ]
            task_data["generations"].append(
                serialize_generation(gen, mode="data", evaluations=eval_dicts)
            )

        # Add task-level evaluations (annotation/ground-truth evals without a generation)
        for te in te_by_task.get(task.id, []):
            if te.generation_id is not None:
                continue  # Already nested under the generation above
            task_data["evaluations"].append(
                serialize_task_evaluation(
                    te, mode="data",
                    eval_run=eval_run_by_id.get(te.evaluation_id),
                    judge_model_lookup=judge_model_lookup,
                )
            )

        export_data["tasks"].append(task_data)

    # Format the data based on requested format
    if format == "json":
        content = json.dumps(export_data, indent=2)
        media_type = "application/json"
        filename = f"{project.title.replace(' ', '_')}_export.json"

    elif format == "csv":
        # Flatten data for CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header with generation, questionnaire, and evaluation columns
        csv_headers = [
            "task_id",
            "task_data",
            "annotation_id",
            "annotation_result",
            "annotation_completed_by",
            "annotation_created_at",
            "questionnaire_response",
            "generation_id",
            "generation_model",
            "generation_content",
            "generation_created_at",
            "evaluation_field",
            "evaluation_metrics",
            "evaluation_passed",
        ]
        writer.writerow(csv_headers)

        # Data rows
        for task in export_data["tasks"]:
            has_data = task["annotations"] or task["generations"] or task["evaluations"]
            if has_data:
                max_items = max(
                    len(task["annotations"]),
                    len(task["generations"]),
                    len(task["evaluations"]),
                    1,
                )
                for i in range(max_items):
                    ann = task["annotations"][i] if i < len(task["annotations"]) else None
                    gen = task["generations"][i] if i < len(task["generations"]) else None
                    ev = task["evaluations"][i] if i < len(task["evaluations"]) else None

                    writer.writerow(
                        [
                            task["id"],
                            json.dumps(task["data"]),
                            ann["id"] if ann else "",
                            json.dumps(ann["result"]) if ann else "",
                            ann["completed_by"] if ann else "",
                            ann["created_at"] if ann else "",
                            json.dumps(ann["questionnaire_response"]) if ann and ann.get("questionnaire_response") else "",
                            gen["id"] if gen else "",
                            gen["model_id"] if gen else "",
                            gen["response_content"] if gen else "",
                            gen["created_at"] if gen else "",
                            ev["field_name"] if ev else "",
                            json.dumps(ev["metrics"]) if ev else "",
                            ev["passed"] if ev else "",
                        ]
                    )
            else:
                # Task with no data
                writer.writerow(
                    [task["id"], json.dumps(task["data"])] + [""] * 12
                )

        content = output.getvalue()
        media_type = "text/csv"
        filename = f"{project.title.replace(' ', '_')}_export.csv"

    elif format == "tsv":
        # Similar to CSV but tab-separated
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")

        # Header with generation, questionnaire, and evaluation columns
        tsv_headers = [
            "task_id",
            "task_data",
            "annotation_id",
            "annotation_result",
            "annotation_completed_by",
            "annotation_created_at",
            "questionnaire_response",
            "generation_id",
            "generation_model",
            "generation_content",
            "generation_created_at",
            "evaluation_field",
            "evaluation_metrics",
            "evaluation_passed",
        ]
        writer.writerow(tsv_headers)

        # Data rows
        for task in export_data["tasks"]:
            has_data = task["annotations"] or task["generations"] or task["evaluations"]
            if has_data:
                max_items = max(
                    len(task["annotations"]),
                    len(task["generations"]),
                    len(task["evaluations"]),
                    1,
                )
                for i in range(max_items):
                    ann = task["annotations"][i] if i < len(task["annotations"]) else None
                    gen = task["generations"][i] if i < len(task["generations"]) else None
                    ev = task["evaluations"][i] if i < len(task["evaluations"]) else None

                    writer.writerow(
                        [
                            task["id"],
                            json.dumps(task["data"]),
                            ann["id"] if ann else "",
                            json.dumps(ann["result"]) if ann else "",
                            ann["completed_by"] if ann else "",
                            ann["created_at"] if ann else "",
                            json.dumps(ann["questionnaire_response"]) if ann and ann.get("questionnaire_response") else "",
                            gen["id"] if gen else "",
                            gen["model_id"] if gen else "",
                            gen["response_content"] if gen else "",
                            gen["created_at"] if gen else "",
                            ev["field_name"] if ev else "",
                            json.dumps(ev["metrics"]) if ev else "",
                            ev["passed"] if ev else "",
                        ]
                    )
            else:
                # Task with no data
                writer.writerow(
                    [task["id"], json.dumps(task["data"])] + [""] * 12
                )

        content = output.getvalue()
        media_type = "text/tab-separated-values"
        filename = f"{project.title.replace(' ', '_')}_export.tsv"

    elif format == "label_studio":
        # Label Studio JSON format with BenGER extensions
        ls_data = []

        for task in tasks:
            # Get annotations for this task
            task_annotations = [a for a in annotations if a.task_id == task.id]

            # Get generations for this task
            task_generations = [g for g in generations if g.task_id == task.id]

            # Build Label Studio compatible task object
            ls_task = {
                "id": task.inner_id or task.id,  # Use inner_id for Label Studio compatibility
                "data": task.data,
                "annotations": [],
                "predictions": [],  # Label Studio predictions field
                "meta": task.meta or {},  # Include metadata
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "is_labeled": task.is_labeled,
                "project": project_id,
            }

            # Add annotations in Label Studio format
            for ann in task_annotations:
                # Issue #964: Convert span annotations to Label Studio format
                converted_result = convert_to_label_studio_format(ann.result)
                ls_annotation = {
                    "id": ann.id,
                    "completed_by": ann.completed_by,
                    "result": converted_result,
                    "was_cancelled": ann.was_cancelled,
                    "ground_truth": ann.ground_truth,
                    "created_at": ann.created_at.isoformat() if ann.created_at else None,
                    "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
                    "lead_time": ann.lead_time,
                    "task": task.inner_id or task.id,
                    "project": project_id,
                }

                # Add optional fields if present
                if ann.draft:
                    ls_annotation["draft"] = ann.draft
                if ann.prediction_scores:
                    ls_annotation["prediction"] = ann.prediction_scores
                if ann.reviewed_by:
                    ls_annotation["reviewed_by"] = ann.reviewed_by
                if ann.reviewed_at:
                    ls_annotation["reviewed_at"] = ann.reviewed_at.isoformat()
                if ann.review_result:
                    ls_annotation["review_result"] = ann.review_result

                # Add questionnaire response if present
                qr = qr_by_annotation.get(ann.id)
                if qr:
                    ls_annotation["questionnaire_response"] = {
                        "result": qr.result,
                        "created_at": qr.created_at.isoformat() if qr.created_at else None,
                    }

                ls_task["annotations"].append(ls_annotation)

            # Add generations as a BenGER-specific extension
            if task_generations:
                ls_task["generations"] = []
                for gen in task_generations:
                    ls_generation = {
                        "id": gen.id,
                        "model_id": gen.model_id,
                        "response_content": gen.response_content,
                        # prompt_id removed in issue #759 - prompts now in project.generation_config (issue #817)
                        "case_data": gen.case_data,
                        "created_at": gen.created_at.isoformat() if gen.created_at else None,
                        "response_metadata": gen.response_metadata,
                    }
                    ls_task["generations"].append(ls_generation)

            # Add evaluations as a BenGER-specific extension
            task_evals = te_by_task.get(task.id, [])
            if task_evals:
                ls_task["evaluations"] = []
                for te in task_evals:
                    ls_task["evaluations"].append(
                        {
                            "id": te.id,
                            "evaluation_id": te.evaluation_id,
                            "generation_id": te.generation_id,
                            "field_name": te.field_name,
                            "answer_type": te.answer_type,
                            "ground_truth": te.ground_truth,
                            "prediction": te.prediction,
                            "metrics": te.metrics,
                            "passed": te.passed,
                            "confidence_score": te.confidence_score,
                            "created_at": te.created_at.isoformat() if te.created_at else None,
                        }
                    )

            ls_data.append(ls_task)

        content = json.dumps(ls_data, indent=2, ensure_ascii=False)
        media_type = "application/json"
        filename = f"{project.title.replace(' ', '_')}_label_studio.json"

    else:
        # Plain text format
        lines = []
        lines.append(f"Project: {project.title}")
        lines.append(f"Description: {project.description or 'None'}")
        lines.append(f"Total Tasks: {len(tasks)}")
        lines.append(f"Total Annotations: {len(annotations)}")
        lines.append("-" * 50)

        for task in export_data["tasks"]:
            lines.append(f"\nTask {task['id']}:")
            lines.append(f"Data: {json.dumps(task['data'])}")
            if task["annotations"]:
                lines.append(f"Annotations ({len(task['annotations'])}):")
                for ann in task["annotations"]:
                    lines.append(f"  - {ann['id']}: {json.dumps(ann['result'])}")
                    if ann.get("questionnaire_response"):
                        lines.append(f"    Questionnaire: {json.dumps(ann['questionnaire_response']['result'])}")
            else:
                lines.append("No annotations")
            if task["evaluations"]:
                lines.append(f"Evaluations ({len(task['evaluations'])}):")
                for ev in task["evaluations"]:
                    lines.append(f"  - {ev['field_name']}: passed={ev['passed']} metrics={json.dumps(ev['metrics'])}")

        content = "\n".join(lines)
        media_type = "text/plain"
        filename = f"{project.title.replace(' ', '_')}_export.txt"

    # Return response
    headers = {}
    if download:
        headers["Content-Disposition"] = f"attachment; filename={filename}"

    return Response(content=content, media_type=media_type, headers=headers)


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
            .filter(Annotation.project_id == project.id, Annotation.was_cancelled == False)
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

    # Create ZIP archive in memory
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        exported_count = 0

        for project_id in project_ids:
            try:
                print(f"[EXPORT DEBUG] Processing project_id: {project_id}")

                # Check if project exists and user has access
                project = db.query(Project).filter(Project.id == project_id).first()
                if not project:
                    print(f"[EXPORT DEBUG] Project {project_id} not found in database")
                    continue

                # Check access permission via org-context-aware helper
                if not check_project_accessible(db, current_user, project_id, org_context):
                    print(f"[EXPORT DEBUG] Access denied for project {project_id}, skipping")
                    continue

                # Get comprehensive project data
                print(f"[EXPORT DEBUG] Getting comprehensive data for project {project_id}")
                project_export_data = get_comprehensive_project_data(db, project_id)

                # Create filename from project title
                safe_title = "".join(
                    c for c in project.title if c.isalnum() or c in (' ', '-', '_')
                ).rstrip()
                safe_title = safe_title[:50]  # Limit filename length
                filename = f"{safe_title}_{project_id[:8]}.json"

                # Add to ZIP
                project_json = json.dumps(project_export_data, indent=2, ensure_ascii=False)
                zip_file.writestr(filename, project_json)

                exported_count += 1

            except Exception as e:
                # Log error but continue with other projects
                print(f"[EXPORT DEBUG] Error exporting project {project_id}: {str(e)}")
                import traceback

                print(f"[EXPORT DEBUG] Traceback: {traceback.format_exc()}")
                continue

    if exported_count == 0:
        raise HTTPException(status_code=404, detail="No projects could be exported")

    # Prepare ZIP for download
    zip_buffer.seek(0)
    zip_content = zip_buffer.getvalue()

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"benger_projects_export_{timestamp}.zip"

    return Response(
        content=zip_content,
        media_type="application/zip",
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
    org_context = get_org_context_from_request(request)
    try:
        # Read and validate file - accept both JSON and ZIP files
        if file.filename.endswith('.zip'):
            # Handle ZIP file - extract JSON from within
            zip_content = await file.read()
            try:
                with zipfile.ZipFile(BytesIO(zip_content), 'r') as zip_file:
                    json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                    if not json_files:
                        raise HTTPException(
                            status_code=400, detail="ZIP file contains no JSON files"
                        )
                    # Use first JSON file found (for single project import)
                    content = zip_file.read(json_files[0])
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Invalid ZIP file format")
        elif file.filename.endswith('.json'):
            content = await file.read()
        else:
            raise HTTPException(status_code=400, detail="Only JSON and ZIP files are supported")

        try:
            import_data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        # Validate format version
        format_version = import_data.get("format_version", "1.0.0")
        if not format_version.startswith("1."):
            raise HTTPException(status_code=400, detail="Unsupported export format version")

        # Extract project data
        project_data = import_data.get("project", {})
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
            "feedback_comments": {},
        }

        # Map users to existing users or create placeholder mappings
        users_data = import_data.get("users", [])
        user_email_to_id = {}

        for user_data in users_data:
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
            # Timer and questionnaire settings (Issue #1208)
            immediate_evaluation_enabled=project_data.get("immediate_evaluation_enabled", False),
            annotation_time_limit_enabled=project_data.get("annotation_time_limit_enabled", False),
            annotation_time_limit_seconds=project_data.get("annotation_time_limit_seconds"),
            strict_timer_enabled=project_data.get("strict_timer_enabled", False),
            questionnaire_enabled=project_data.get("questionnaire_enabled", False),
            questionnaire_config=project_data.get("questionnaire_config"),
            randomize_task_order=project_data.get("randomize_task_order", False),
            # Feedback settings
            feedback_enabled=project_data.get("feedback_enabled", False),
            feedback_config=project_data.get("feedback_config"),
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
        tasks_data = import_data.get("tasks", [])
        task_counter = 1

        for task_data in tasks_data:
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
        annotations_data = import_data.get("annotations", [])
        for annotation_data in annotations_data:
            old_annotation_id = annotation_data.get("id", str(uuid.uuid4()))
            new_annotation_id = str(uuid.uuid4())
            id_mappings["annotations"][old_annotation_id] = new_annotation_id

            # Map IDs
            task_id = id_mappings["tasks"].get(annotation_data.get("task_id"))
            completed_by = id_mappings["users"].get(
                annotation_data.get("completed_by"), current_user.id
            )
            reviewed_by = id_mappings["users"].get(annotation_data.get("reviewed_by"))

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
                    reviewed_by=reviewed_by,
                    review_result=annotation_data.get("review_result"),
                    # Enhanced timing (Issue #1208)
                    active_duration_ms=annotation_data.get("active_duration_ms"),
                    focused_duration_ms=annotation_data.get("focused_duration_ms"),
                    tab_switches=annotation_data.get("tab_switches", 0),
                    auto_submitted=annotation_data.get("auto_submitted", False),
                )

                db.add(new_annotation)

        # Note: Predictions import removed - predictions table dropped in migration 411540fa6c40

        # Prompts import removed - prompts table dropped in issue #759
        # Prompt functionality now handled by generation_structure field

        # Import response generations
        response_generations_data = import_data.get("response_generations", [])
        for resp_gen_data in response_generations_data:
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
        generations_data = import_data.get("generations", [])
        for generation_data in generations_data:
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
                )

                db.add(new_generation)

        # Import evaluations (evaluation runs are project-level)
        evaluations_data = import_data.get("evaluations", [])
        for evaluation_data in evaluations_data:
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
        evaluation_metrics_data = import_data.get("evaluation_metrics", [])
        for metric_data in evaluation_metrics_data:
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

        # Import task evaluations (per-task evaluation results)
        task_evaluations_data = import_data.get("task_evaluations", [])
        for te_data in task_evaluations_data:
            old_te_id = te_data.get("id", str(uuid.uuid4()))
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
                    field_name=te_data.get("field_name"),
                    answer_type=te_data.get("answer_type"),
                    ground_truth=te_data.get("ground_truth"),
                    prediction=te_data.get("prediction"),
                    metrics=te_data.get("metrics"),
                    passed=te_data.get("passed"),
                    confidence_score=te_data.get("confidence_score"),
                    error_message=te_data.get("error_message"),
                    processing_time_ms=te_data.get("processing_time_ms"),
                )

                db.add(new_te)

        # Import human evaluation configs
        human_evaluation_configs_data = import_data.get("human_evaluation_configs", [])
        for config_data in human_evaluation_configs_data:
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
        human_evaluation_sessions_data = import_data.get("human_evaluation_sessions", [])
        for session_data in human_evaluation_sessions_data:
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
        human_evaluation_results_data = import_data.get("human_evaluation_results", [])
        for result_data in human_evaluation_results_data:
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
        preference_rankings_data = import_data.get("preference_rankings", [])
        for ranking_data in preference_rankings_data:
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
        likert_scale_evaluations_data = import_data.get("likert_scale_evaluations", [])
        for likert_data in likert_scale_evaluations_data:
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

        # Import project members (map to existing users)
        project_members_data = import_data.get("project_members", [])
        for member_data in project_members_data:
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
        task_assignments_data = import_data.get("task_assignments", [])
        for assignment_data in task_assignments_data:
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
        post_annotation_responses_data = import_data.get("post_annotation_responses", [])
        for par_data in post_annotation_responses_data:
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

        # Import feedback comments (two passes: create, then set parent_id)
        feedback_comments_data = import_data.get("feedback_comments", [])
        for fc_data in feedback_comments_data:
            old_fc_id = fc_data.get("id", str(uuid.uuid4()))
            new_fc_id = str(uuid.uuid4())
            id_mappings["feedback_comments"][old_fc_id] = new_fc_id

            task_id = id_mappings["tasks"].get(fc_data.get("task_id"))
            if not task_id:
                continue

            # Map target_id based on target_type
            target_type = fc_data.get("target_type", "annotation")
            target_id = fc_data.get("target_id")
            if target_type == "annotation":
                target_id = id_mappings["annotations"].get(target_id, target_id)
            elif target_type == "generation":
                target_id = id_mappings["generations"].get(target_id, target_id)
            # evaluation target_ids don't have a dedicated mapping key,
            # but task_evaluations are recreated with new IDs during import.
            # We skip remapping for evaluations since they may not map 1:1.

            user_id = id_mappings["users"].get(fc_data.get("created_by"), current_user.id)
            resolved_by = None
            if fc_data.get("resolved_by"):
                resolved_by = id_mappings["users"].get(fc_data["resolved_by"])

            resolved_at = None
            if fc_data.get("resolved_at"):
                try:
                    resolved_at = datetime.fromisoformat(fc_data["resolved_at"])
                except (ValueError, TypeError):
                    pass

            new_fc = FeedbackComment(
                id=new_fc_id,
                project_id=new_project_id,
                task_id=task_id,
                target_type=target_type,
                target_id=target_id,
                parent_id=None,  # Set in second pass
                text=fc_data.get("text", ""),
                highlight_start=fc_data.get("highlight_start"),
                highlight_end=fc_data.get("highlight_end"),
                highlight_text=fc_data.get("highlight_text"),
                highlight_label=fc_data.get("highlight_label"),
                is_resolved=fc_data.get("is_resolved", False),
                resolved_at=resolved_at,
                resolved_by=resolved_by,
                created_by=user_id,
            )
            db.add(new_fc)

        db.flush()

        # Second pass: set parent_id references for threaded comments
        for fc_data in feedback_comments_data:
            if fc_data.get("parent_id"):
                old_id = fc_data.get("id")
                new_id = id_mappings["feedback_comments"].get(old_id)
                new_parent_id = id_mappings["feedback_comments"].get(fc_data["parent_id"])
                if new_id and new_parent_id:
                    db.query(FeedbackComment).filter(
                        FeedbackComment.id == new_id
                    ).update({FeedbackComment.parent_id: new_parent_id})

        # Update denormalized feedback counts on imported tasks
        for old_task_id, new_task_id in id_mappings["tasks"].items():
            count = (
                db.query(FeedbackComment)
                .filter(FeedbackComment.task_id == new_task_id)
                .count()
            )
            if count > 0:
                unresolved = (
                    db.query(FeedbackComment)
                    .filter(
                        FeedbackComment.task_id == new_task_id,
                        FeedbackComment.is_resolved == False,
                    )
                    .count()
                )
                db.query(Task).filter(Task.id == new_task_id).update({
                    Task.feedback_count: count,
                    Task.unresolved_feedback_count: unresolved,
                })

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
                "task_evaluations": len(import_data.get("task_evaluations", [])),
                "human_evaluation_configs": len(id_mappings["human_evaluation_configs"]),
                "human_evaluation_sessions": len(id_mappings["human_evaluation_sessions"]),
                "human_evaluation_results": len(id_mappings["human_evaluation_results"]),
                "preference_rankings": len(id_mappings["preference_rankings"]),
                "likert_scale_evaluations": len(id_mappings["likert_scale_evaluations"]),
                "prompts": len(id_mappings["prompts"]),
                "project_members": len(id_mappings["project_members"]),
                "task_assignments": len(id_mappings["task_assignments"]),
                "post_annotation_responses": len(id_mappings["post_annotation_responses"]),
                "feedback_comments": len(id_mappings["feedback_comments"]),
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
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
