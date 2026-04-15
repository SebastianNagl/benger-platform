"""
Test data seeding endpoints for E2E testing.

These endpoints allow E2E tests to seed mock generation and evaluation data
without requiring actual LLM API calls.

IMPORTANT: These endpoints should only be available in test environments.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_module import User, require_superadmin
from database import get_db

logger = logging.getLogger(__name__)

# Only enable in test environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
TEST_SEEDING_ENABLED = ENVIRONMENT in ("test", "development", "e2e")

router = APIRouter(prefix="/api/test", tags=["test-seeding"])


# ============= Request/Response Models =============


class MockGenerationRequest(BaseModel):
    """Request to create mock generation data"""
    project_id: str = Field(..., description="Project ID")
    task_id: str = Field(..., description="Task ID")
    model_id: str = Field(..., description="Model ID (e.g., 'gpt-4-turbo')")
    output: str = Field(..., description="Mock generation output text")


class MockGenerationsRequest(BaseModel):
    """Request to create multiple mock generations"""
    project_id: str = Field(..., description="Project ID")
    generations: List[Dict[str, Any]] = Field(
        ...,
        description="List of generations: [{task_id, model_id, output}, ...]"
    )


class MockAnnotationsRequest(BaseModel):
    """Request to create multiple mock annotations"""
    project_id: str = Field(..., description="Project ID")
    annotations: List[Dict[str, Any]] = Field(
        ...,
        description="List of annotations: [{task_id, result, annotator_username?}, ...]"
    )


class MockEvaluationRequest(BaseModel):
    """Request to create mock evaluation data with sample results"""
    project_id: str = Field(..., description="Project ID")
    evaluation_name: str = Field(default="E2E Test Evaluation", description="Evaluation name")
    results: List[Dict[str, Any]] = Field(
        ...,
        description="List of results: [{generation_id, metric, score}, ...]"
    )


class SeedResponse(BaseModel):
    """Response from seeding operations"""
    success: bool
    message: str
    created_count: int = 0
    ids: List[str] = []


# ============= Endpoints =============


def _check_test_environment():
    """Check if test seeding is enabled"""
    if not TEST_SEEDING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test seeding endpoints are only available in test environments",
        )


def _build_parsed_annotation(output: str, gen_data: Dict[str, Any]) -> list:
    """Build parsed_annotation in the correct format based on output content.

    Detects span/NER JSON output (array of objects with start/end fields)
    and stores it in Labels format. Falls back to textarea format otherwise.
    """
    # Allow explicit format override via gen_data
    annotation_type = gen_data.get("annotation_type")
    from_name = gen_data.get("from_name", "label")
    to_name = gen_data.get("to_name", "text")

    if annotation_type == "labels":
        # Explicit span format
        try:
            spans_data = json.loads(output) if isinstance(output, str) else output
            if isinstance(spans_data, list):
                return [_build_span_annotation(spans_data, from_name, to_name)]
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Auto-detect: try parsing as JSON array with start/end fields
    if not annotation_type:
        try:
            parsed = json.loads(output) if isinstance(output, str) else None
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                if "start" in parsed[0] and "end" in parsed[0]:
                    return [_build_span_annotation(parsed, from_name, to_name)]
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Default: textarea/markdown format
    # Use from_name/to_name from gen_data if provided, otherwise default to answer/question
    default_from = gen_data.get("from_name", "answer")
    default_to = gen_data.get("to_name", "question")
    # Detect markdown content (multi-paragraph or explicit type)
    if annotation_type == "markdown":
        return [{"from_name": default_from, "to_name": default_to, "type": "markdown", "value": {"markdown": output}}]
    return [{"from_name": default_from, "to_name": default_to, "type": "textarea", "value": {"text": [output]}}]


def _build_span_annotation(spans_data: list, from_name: str, to_name: str) -> dict:
    """Convert a list of span dicts to BenGER Labels annotation format."""
    spans = []
    for s in spans_data:
        span: Dict[str, Any] = {"start": s.get("start", 0), "end": s.get("end", 0)}
        if "text" in s:
            span["text"] = s["text"]
        if "label" in s:
            span["labels"] = [s["label"]]
        elif "labels" in s:
            span["labels"] = s["labels"]
        spans.append(span)
    return {"from_name": from_name, "to_name": to_name, "type": "labels", "value": {"spans": spans}}


@router.post("/seed/generations", response_model=SeedResponse)
async def seed_mock_generations(
    request: MockGenerationsRequest,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Seed mock generation data for E2E testing.

    Creates Generation and ResponseGeneration records without calling actual LLMs.
    Only available in test environments and requires superadmin.
    """
    _check_test_environment()

    try:
        from models import Generation, ResponseGeneration
        from project_models import Project, Task

        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        created_ids = []

        # Group generations by model for creating ResponseGeneration records
        by_model: Dict[str, List[Dict]] = {}
        for gen in request.generations:
            model_id = gen.get("model_id", "unknown")
            if model_id not in by_model:
                by_model[model_id] = []
            by_model[model_id].append(gen)

        # Create generations for each model
        for model_id, model_gens in by_model.items():
            # Create parent ResponseGeneration job
            response_gen_id = str(uuid.uuid4())
            response_gen = ResponseGeneration(
                id=response_gen_id,
                project_id=request.project_id,
                model_id=model_id,
                status="completed",
                responses_generated=len(model_gens),
                created_by=current_user.id,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            db.add(response_gen)

            # Create individual Generation records
            for gen_data in model_gens:
                task_id = gen_data.get("task_id")
                output = gen_data.get("output", "")

                # Verify task exists
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task:
                    logger.warning(f"Task {task_id} not found, skipping generation")
                    continue

                generation_id = str(uuid.uuid4())

                # Detect span/NER output format and build appropriate parsed_annotation
                parsed_annotation = _build_parsed_annotation(output, gen_data)

                generation = Generation(
                    id=generation_id,
                    generation_id=response_gen_id,
                    task_id=task_id,
                    model_id=model_id,
                    case_data=str(task.data) if task.data else "",
                    response_content=output,
                    status="completed",
                    parse_status="success",
                    parsed_annotation=parsed_annotation,
                    usage_stats={"prompt_tokens": 50, "completion_tokens": len(output.split())},
                    created_at=datetime.utcnow(),
                )
                db.add(generation)
                created_ids.append(generation_id)

        db.commit()

        return SeedResponse(
            success=True,
            message=f"Created {len(created_ids)} mock generations for {len(by_model)} models",
            created_count=len(created_ids),
            ids=created_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding generations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding generations: {str(e)}",
        )


@router.post("/seed/annotations", response_model=SeedResponse)
async def seed_mock_annotations(
    request: MockAnnotationsRequest,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Seed mock annotation data for E2E testing.

    Creates Annotation records for tasks without triggering validation/counter logic.
    Only available in test environments and requires superadmin.
    """
    _check_test_environment()

    try:
        from project_models import Annotation, Project, Task

        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        # Cache user lookups for multi-annotator support
        user_cache: Dict[str, str] = {}  # username -> user_id

        created_ids = []

        for ann_data in request.annotations:
            task_id = ann_data.get("task_id")
            result = ann_data.get("result", [])
            annotator_username = ann_data.get("annotator_username")

            # Verify task exists
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.warning(f"Task {task_id} not found, skipping annotation")
                continue

            # Determine annotator user ID
            if annotator_username:
                if annotator_username not in user_cache:
                    # Import User model from models (not auth_module)
                    from models import User as UserModel
                    annotator = db.query(UserModel).filter(UserModel.username == annotator_username).first()
                    if annotator:
                        user_cache[annotator_username] = annotator.id
                    else:
                        logger.warning(f"User '{annotator_username}' not found, using current user")
                        user_cache[annotator_username] = current_user.id
                completed_by = user_cache[annotator_username]
            else:
                completed_by = current_user.id

            annotation_id = str(uuid.uuid4())
            annotation = Annotation(
                id=annotation_id,
                task_id=task_id,
                project_id=request.project_id,
                completed_by=completed_by,
                result=result,
                was_cancelled=False,
                created_at=datetime.utcnow(),
            )
            db.add(annotation)
            created_ids.append(annotation_id)

            # Update task counters
            task.total_annotations = (task.total_annotations or 0) + 1
            if result and len(result) > 0:
                task.is_labeled = True

        db.commit()

        return SeedResponse(
            success=True,
            message=f"Created {len(created_ids)} mock annotations",
            created_count=len(created_ids),
            ids=created_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding annotations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding annotations: {str(e)}",
        )


@router.post("/seed/evaluation", response_model=SeedResponse)
async def seed_mock_evaluation(
    request: MockEvaluationRequest,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Seed mock evaluation data with sample results for E2E testing.

    Creates Evaluation and EvaluationSampleResult records without running actual metrics.
    Only available in test environments and requires superadmin.
    """
    _check_test_environment()

    try:
        from models import Evaluation, EvaluationSampleResult, Generation
        from project_models import Project

        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        # Group results by model to create per-model Evaluation records
        by_model: Dict[str, List[Dict]] = {}
        for result_data in request.results:
            generation_id = result_data.get("generation_id")
            # Get generation to find model_id
            generation = db.query(Generation).filter(Generation.id == generation_id).first()
            if not generation:
                logger.warning(f"Generation {generation_id} not found, skipping result")
                continue
            model_id = generation.model_id
            if model_id not in by_model:
                by_model[model_id] = []
            by_model[model_id].append({**result_data, "generation": generation})

        created_count = 0
        evaluation_ids = []

        # Create Evaluation + sample results per model
        for model_id, model_results in by_model.items():
            evaluation_id = str(uuid.uuid4())

            # Compute aggregate metrics for the evaluation
            scores = [r.get("score", 0.5) for r in model_results]
            avg_score = sum(scores) / len(scores) if scores else 0.0

            evaluation = Evaluation(
                id=evaluation_id,
                project_id=request.project_id,
                model_id=model_id,
                evaluation_type_ids=["llm_judge_custom"],  # JSON list of evaluation type IDs
                metrics={"llm_judge_custom": avg_score, "accuracy": avg_score},  # Aggregate metrics
                status="completed",
                samples_evaluated=len(model_results),
                has_sample_results=True,
                created_by=current_user.id,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            db.add(evaluation)
            evaluation_ids.append(evaluation_id)

            # Create EvaluationSampleResult records
            for result_data in model_results:
                generation = result_data["generation"]
                metric = result_data.get("metric", "llm_judge_custom")
                score = result_data.get("score", 0.5)

                sample_result = EvaluationSampleResult(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation_id,
                    task_id=generation.task_id,
                    generation_id=generation.id,
                    field_name="answer",
                    answer_type="text",  # Required field
                    ground_truth={"value": "Reference answer"},  # JSON field
                    prediction={"value": generation.response_content or ""},  # JSON field
                    metrics={metric: score},  # JSON dict of metrics
                    passed=score >= 0.5,
                    created_at=datetime.utcnow(),
                )
                db.add(sample_result)
                created_count += 1

        db.commit()

        return SeedResponse(
            success=True,
            message=f"Created {len(evaluation_ids)} evaluations with {created_count} sample results",
            created_count=created_count,
            ids=evaluation_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding evaluation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding evaluation: {str(e)}",
        )


@router.delete("/cleanup/{project_id}", response_model=SeedResponse)
async def cleanup_test_project(
    project_id: str,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Clean up a test project and all its data.

    Deletes project, tasks, annotations, generations, and evaluations.
    Only available in test environments and requires superadmin.
    """
    _check_test_environment()

    try:
        from models import Evaluation, EvaluationSampleResult, Generation, ResponseGeneration
        from project_models import Annotation, Project, Task

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return SeedResponse(
                success=True,
                message="Project already deleted or not found",
                created_count=0,
                ids=[],
            )

        # Get task IDs for this project
        task_ids = [t.id for t in db.query(Task.id).filter(Task.project_id == project_id).all()]

        deleted_count = 0

        # Delete evaluation sample results
        if task_ids:
            deleted = db.query(EvaluationSampleResult).filter(
                EvaluationSampleResult.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            deleted_count += deleted

        # Delete evaluations
        deleted = db.query(Evaluation).filter(
            Evaluation.project_id == project_id
        ).delete(synchronize_session=False)
        deleted_count += deleted

        # Delete generations
        if task_ids:
            deleted = db.query(Generation).filter(
                Generation.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            deleted_count += deleted

        # Delete response generations
        deleted = db.query(ResponseGeneration).filter(
            ResponseGeneration.project_id == project_id
        ).delete(synchronize_session=False)
        deleted_count += deleted

        # Delete annotations
        if task_ids:
            deleted = db.query(Annotation).filter(
                Annotation.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            deleted_count += deleted

        # Delete tasks
        deleted = db.query(Task).filter(
            Task.project_id == project_id
        ).delete(synchronize_session=False)
        deleted_count += deleted

        # Delete project
        db.delete(project)
        deleted_count += 1

        db.commit()

        return SeedResponse(
            success=True,
            message=f"Cleaned up project and {deleted_count} related records",
            created_count=deleted_count,
            ids=[project_id],
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error cleaning up project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cleaning up project: {str(e)}",
        )


@router.post("/force-profile-overdue")
async def force_profile_overdue(
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Force the current user's profile_confirmed_at to a past date so
    confirmation_due becomes true. Only available in test environments.
    """
    _check_test_environment()

    try:
        from models import User as UserModel

        db_user = db.query(UserModel).filter(UserModel.id == current_user.id).first()
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        db_user.profile_confirmed_at = datetime(2020, 1, 1)
        db.commit()
        db.refresh(db_user)

        return {
            "success": True,
            "profile_confirmed_at": str(db_user.profile_confirmed_at),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error forcing profile overdue: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}",
        )


@router.get("/status")
async def test_seeding_status():
    """Check if test seeding endpoints are enabled"""
    return {
        "enabled": TEST_SEEDING_ENABLED,
        "environment": ENVIRONMENT,
        "message": "Test seeding is enabled" if TEST_SEEDING_ENABLED else "Test seeding is disabled",
    }
