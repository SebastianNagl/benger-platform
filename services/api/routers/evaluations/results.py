"""
Evaluation results, per-sample analysis, and export endpoints.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import HumanEvaluationSession, LikertScaleEvaluation, PreferenceRanking
from project_models import Annotation, Project, Task
from routers.evaluations.helpers import EvaluationResultsResponse, resolve_user_org_for_project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Score Extraction Helper =============


# Known metadata-suffix keys that should never be treated as primary scores.
# Used by both the explicit llm_judge_* matcher and the generic fallback.
_METRIC_METADATA_SUFFIXES = (
    "_response",      # LLM judge raw text
    "_passed",        # boolean cast to 0/1
    "_details",       # nested explanation dict
    "_raw",           # raw pre-aggregation array
    "_grade_points",  # Falloesung grade-points sub-metric
)


def _extract_primary_score(metrics: Optional[Dict[str, Any]]) -> Optional[float]:
    """Extract the primary display score from a TaskEvaluation metrics dict.

    Each TaskEvaluation row corresponds to ONE config x ONE (pred, ref) pair x
    ONE metric, so the primary score is the single non-metadata numeric value
    in the dict.

    Precedence (handles multi-metric edge cases first, then generic fallback):
    1. llm_judge_custom (pinned for backwards-compat)
    2. Any llm_judge_* numeric key (excluding metadata suffixes)
    3. korrektur_falloesung (human-graded total score)
    4. score, overall_score (legacy keys)
    5. Generic: first non-metadata, non-error numeric value (covers
       bleu, rouge, meteor, exact_match, accuracy, f1, etc.)
    """
    if not metrics:
        return None

    # 1. Custom LLM judge
    if "llm_judge_custom" in metrics:
        val = metrics["llm_judge_custom"]
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)

    # 2. Any llm_judge_* numeric key
    for key, val in metrics.items():
        if (
            key.startswith("llm_judge_")
            and isinstance(val, (int, float))
            and not isinstance(val, bool)
            and not key.endswith(_METRIC_METADATA_SUFFIXES)
        ):
            return float(val)

    # 3. Domain-specific human-graded metric: takes precedence over generic
    # `score` / `overall_score` so projects using Falllosung-grade headline it.
    if (
        "korrektur_falloesung" in metrics
        and isinstance(metrics["korrektur_falloesung"], (int, float))
        and not isinstance(metrics["korrektur_falloesung"], bool)
    ):
        return float(metrics["korrektur_falloesung"])

    # 4. Legacy generic keys
    if (
        "score" in metrics
        and isinstance(metrics["score"], (int, float))
        and not isinstance(metrics["score"], bool)
    ):
        return float(metrics["score"])
    if (
        "overall_score" in metrics
        and isinstance(metrics["overall_score"], (int, float))
        and not isinstance(metrics["overall_score"], bool)
    ):
        return float(metrics["overall_score"])

    # 5. Generic fallback: first non-metadata, non-error numeric value.
    # Covers BLEU, ROUGE, exact_match, METEOR, etc. -- each TaskEvaluation row
    # holds the result of one config x one (pred, ref) pair x one metric, so
    # exactly one such value is present.
    for key, val in metrics.items():
        if key == "error":
            continue
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        if key.endswith(_METRIC_METADATA_SUFFIXES):
            continue
        return float(val)

    return None




# ============= Endpoints =============


@router.get("/results/{project_id}", response_model=List[EvaluationResultsResponse])
async def get_evaluation_results(
    project_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    include_human: bool = Query(True),
    include_automated: bool = Query(True),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get evaluation results for a project.

    Returns both automated and human evaluation results.
    """
    # Check project access
    if not check_project_accessible(db, current_user, project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        results = []

        # Get automated evaluation results
        if include_automated:
            automated_evals = (
                db.query(DBEvaluationRun)
                .filter(DBEvaluationRun.project_id == project_id)
                .order_by(DBEvaluationRun.created_at.desc())
                .limit(limit)
                .all()
            )

            for eval in automated_evals:
                results.append(
                    EvaluationResultsResponse(
                        project_id=project_id,
                        results={
                            "type": "automated",
                            "metrics": eval.metrics,
                            "status": eval.status,
                            "samples_evaluated": eval.samples_evaluated,
                        },
                        metadata=eval.eval_metadata or {},
                        created_at=eval.created_at,
                    )
                )

        # Get human evaluation results
        if include_human:
            # Aggregate Likert scale results
            likert_results = (
                db.query(
                    LikertScaleEvaluation.dimension,
                    func.avg(LikertScaleEvaluation.rating).label("avg_rating"),
                    func.count(LikertScaleEvaluation.id).label("count"),
                )
                .join(
                    HumanEvaluationSession,
                    LikertScaleEvaluation.session_id == HumanEvaluationSession.id,
                )
                .filter(HumanEvaluationSession.project_id == project_id)
                .group_by(LikertScaleEvaluation.dimension)
                .all()
            )

            if likert_results:
                likert_data = {
                    result.dimension: {
                        "average_rating": float(result.avg_rating),
                        "count": result.count,
                    }
                    for result in likert_results
                }

                results.append(
                    EvaluationResultsResponse(
                        project_id=project_id,
                        results={"type": "human_likert", "dimensions": likert_data},
                        metadata={"aggregation": "average"},
                        created_at=datetime.now(),
                    )
                )

            # Aggregate preference ranking results
            preference_results = (
                db.query(PreferenceRanking.winner, func.count(PreferenceRanking.id).label("count"))
                .join(
                    HumanEvaluationSession,
                    PreferenceRanking.session_id == HumanEvaluationSession.id,
                )
                .filter(HumanEvaluationSession.project_id == project_id)
                .group_by(PreferenceRanking.winner)
                .all()
            )

            if preference_results:
                preference_data = {result.winner: result.count for result in preference_results}

                total_comparisons = sum(preference_data.values())
                preference_percentages = {
                    winner: (count / total_comparisons * 100)
                    for winner, count in preference_data.items()
                }

                results.append(
                    EvaluationResultsResponse(
                        project_id=project_id,
                        results={
                            "type": "human_preference",
                            "counts": preference_data,
                            "percentages": preference_percentages,
                            "total_comparisons": total_comparisons,
                        },
                        metadata={"aggregation": "count"},
                        created_at=datetime.now(),
                    )
                )

        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation results: {str(e)}",
        )


@router.post("/export/{project_id}")
async def export_evaluation_results(
    project_id: str,
    request: Request,
    format: str = Query("json", regex="^(json|csv)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Export evaluation results in various formats.
    """
    # Check project access
    if not check_project_accessible(db, current_user, project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        # Get all evaluation data
        results = await get_evaluation_results(
            project_id=project_id,
            request=request,
            limit=1000,  # Get all results for export
            include_human=True,
            include_automated=True,
            current_user=current_user,
            db=db,
        )

        if format == "json":
            # Return JSON directly
            return {
                "project_id": project_id,
                "exported_at": datetime.now().isoformat(),
                "results": [r.dict() for r in results],
            }

        elif format == "csv":
            # Convert to CSV format
            import csv
            import io

            output = io.StringIO()

            if results:
                # Create CSV with flattened structure
                fieldnames = ["timestamp", "type", "metric", "value"]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()

                for result in results:
                    base_row = {
                        "timestamp": result.created_at.isoformat(),
                        "type": result.results.get("type", "unknown"),
                    }

                    # Flatten metrics
                    if "metrics" in result.results:
                        for metric, value in result.results["metrics"].items():
                            writer.writerow({**base_row, "metric": metric, "value": value})
                    elif "dimensions" in result.results:
                        for dimension, data in result.results["dimensions"].items():
                            writer.writerow(
                                {
                                    **base_row,
                                    "metric": f"{dimension}_avg",
                                    "value": data.get("average_rating", 0),
                                }
                            )
                    elif "percentages" in result.results:
                        for winner, percentage in result.results["percentages"].items():
                            writer.writerow(
                                {**base_row, "metric": f"preference_{winner}", "value": percentage}
                            )

            from fastapi.responses import Response

            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=evaluation_results_{project_id}.csv"
                },
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export evaluation results: {str(e)}",
        )


@router.get("/{evaluation_id}/samples")
async def get_evaluation_samples(
    evaluation_id: str,
    request: Request,
    field_name: Optional[str] = Query(None, description="Filter by field name"),
    passed: Optional[bool] = Query(None, description="Filter by pass/fail status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get per-sample evaluation results with filtering and pagination.

    Enables drill-down analysis of evaluation performance at the sample level.
    """
    try:
        from models import TaskEvaluation
        from schemas.evaluation_schemas import SampleEvaluationListResponse
        from schemas.evaluation_schemas import SampleEvaluationResult as SampleResultSchema

        # Verify evaluation exists and user has access
        evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Build query
        query = db.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id == evaluation_id
        )

        # Apply filters
        if field_name:
            query = query.filter(TaskEvaluation.field_name == field_name)
        if passed is not None:
            query = query.filter(TaskEvaluation.passed == passed)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        samples = (
            query.order_by(TaskEvaluation.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        # Convert to response models
        sample_results = [SampleResultSchema.from_orm(s) for s in samples]

        return SampleEvaluationListResponse(
            items=sample_results,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(offset + page_size) < total,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation samples: {str(e)}",
        )


@router.get("/{evaluation_id}/metrics/{metric_name}/distribution")
async def get_metric_distribution(
    evaluation_id: str,
    metric_name: str,
    request: Request,
    field_name: Optional[str] = Query(None, description="Filter by field name"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get distribution statistics for a specific metric across all samples.

    Returns mean, median, std, quartiles, and histogram data for visualization.
    """
    try:
        import statistics

        from models import TaskEvaluation
        from schemas.evaluation_schemas import MetricDistribution

        # Verify evaluation exists
        evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Build query
        query = db.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id == evaluation_id
        )

        if field_name:
            query = query.filter(TaskEvaluation.field_name == field_name)

        samples = query.all()

        if not samples:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No samples found for this evaluation",
            )

        # Extract metric values
        values = []
        for sample in samples:
            if sample.metrics and metric_name in sample.metrics:
                value = sample.metrics[metric_name]
                if value is not None:
                    values.append(float(value))

        if not values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric '{metric_name}' not found in samples",
            )

        # Calculate statistics
        values_sorted = sorted(values)
        mean_val = statistics.mean(values)
        median_val = statistics.median(values)
        std_val = statistics.stdev(values) if len(values) > 1 else 0.0

        # Calculate quartiles
        q1 = statistics.quantiles(values, n=4)[0] if len(values) >= 4 else values_sorted[0]
        q2 = median_val
        q3 = statistics.quantiles(values, n=4)[2] if len(values) >= 4 else values_sorted[-1]

        # Create histogram (10 buckets)
        min_val = min(values)
        max_val = max(values)
        bucket_size = (max_val - min_val) / 10 if max_val > min_val else 1

        histogram = {}
        for i in range(10):
            bucket_start = min_val + i * bucket_size
            bucket_end = min_val + (i + 1) * bucket_size
            bucket_label = f"{bucket_start:.2f}-{bucket_end:.2f}"
            count = sum(
                1 for v in values if bucket_start <= v < bucket_end or (i == 9 and v == bucket_end)
            )
            histogram[bucket_label] = count

        return MetricDistribution(
            metric_name=metric_name,
            mean=mean_val,
            median=median_val,
            std=std_val,
            min=min_val,
            max=max_val,
            quartiles={"q1": q1, "q2": q2, "q3": q3},
            histogram=histogram,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metric distribution: {str(e)}",
        )


@router.get("/{evaluation_id}/confusion-matrix")
async def get_confusion_matrix(
    evaluation_id: str,
    request: Request,
    field_name: str = Query(..., description="Field name for classification"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Generate confusion matrix for classification metrics.

    Only works for fields with discrete class predictions.
    """
    try:
        from models import TaskEvaluation
        from schemas.evaluation_schemas import ConfusionMatrix

        # Verify evaluation exists
        evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Get all samples for this field
        samples = (
            db.query(TaskEvaluation)
            .filter(
                TaskEvaluation.evaluation_id == evaluation_id,
                TaskEvaluation.field_name == field_name,
            )
            .all()
        )

        if not samples:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No samples found for field '{field_name}'",
            )

        # Extract all unique labels
        all_labels = set()
        predictions_data = []

        for sample in samples:
            gt = sample.ground_truth.get("value") if sample.ground_truth else None
            pred = sample.prediction.get("value") if sample.prediction else None

            if gt is not None and pred is not None:
                gt_str = str(gt).strip().lower()
                pred_str = str(pred).strip().lower()
                all_labels.add(gt_str)
                all_labels.add(pred_str)
                predictions_data.append((gt_str, pred_str))

        if not predictions_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid ground truth/prediction pairs found",
            )

        # Sort labels for consistent ordering
        labels = sorted(list(all_labels))
        label_to_idx = {label: idx for idx, label in enumerate(labels)}

        # Build confusion matrix
        n = len(labels)
        matrix = [[0 for _ in range(n)] for _ in range(n)]

        for gt, pred in predictions_data:
            gt_idx = label_to_idx[gt]
            pred_idx = label_to_idx[pred]
            matrix[gt_idx][pred_idx] += 1

        # Calculate metrics per class
        precision_per_class = {}
        recall_per_class = {}
        f1_per_class = {}

        for i, label in enumerate(labels):
            # Precision: TP / (TP + FP)
            tp = matrix[i][i]
            fp = sum(matrix[j][i] for j in range(n) if j != i)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            precision_per_class[label] = precision

            # Recall: TP / (TP + FN)
            fn = sum(matrix[i][j] for j in range(n) if j != i)
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            recall_per_class[label] = recall

            # F1: 2 * (precision * recall) / (precision + recall)
            f1 = (
                2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            )
            f1_per_class[label] = f1

        # Overall accuracy
        total_correct = sum(matrix[i][i] for i in range(n))
        total = sum(sum(row) for row in matrix)
        accuracy = total_correct / total if total > 0 else 0.0

        return ConfusionMatrix(
            field_name=field_name,
            labels=labels,
            matrix=matrix,
            accuracy=accuracy,
            precision_per_class=precision_per_class,
            recall_per_class=recall_per_class,
            f1_per_class=f1_per_class,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate confusion matrix: {str(e)}",
        )


@router.get("/{evaluation_id}/results/by-task-model")
async def get_results_by_task_model(
    evaluation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get evaluation results grouped by task and model.

    Returns a matrix of scores for each task-model combination,
    enabling detailed comparison of model performance across tasks.
    """
    try:
        from models import TaskEvaluation
        from models import Generation as GenerationModel
        from models import LLMModel

        # Verify evaluation exists
        evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Get sample results with dedup: latest per (generation_id, field_name)
        ranked_results = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.metrics,
                TaskEvaluation.passed,
                TaskEvaluation.generation_id,
                GenerationModel.model_id,
                func.row_number()
                .over(
                    partition_by=[TaskEvaluation.generation_id, TaskEvaluation.field_name],
                    order_by=TaskEvaluation.created_at.desc(),
                )
                .label("rn"),
            )
            .join(
                GenerationModel,
                TaskEvaluation.generation_id == GenerationModel.id,
            )
            .filter(TaskEvaluation.evaluation_id == evaluation_id)
            .subquery()
        )
        sample_results = (
            db.query(
                ranked_results.c.task_id,
                ranked_results.c.metrics,
                ranked_results.c.passed,
                ranked_results.c.generation_id,
                ranked_results.c.model_id,
            )
            .filter(ranked_results.c.rn == 1)
            .all()
        )

        # Query 2: Get annotation-based evaluation results
        from models import User as DBUser

        annotation_eval_results = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.annotation_id,
                TaskEvaluation.field_name,
                TaskEvaluation.metrics,
                TaskEvaluation.created_at,
            )
            .filter(
                TaskEvaluation.evaluation_id == evaluation_id,
                TaskEvaluation.generation_id == None,  # noqa: E711
                TaskEvaluation.annotation_id != None,  # noqa: E711
            )
            .all()
        )

        if not sample_results and not annotation_eval_results:
            return {
                "evaluation_id": evaluation_id,
                "models": [],
                "model_names": {},
                "tasks": [],
                "summary": {},
            }

        # Get all unique model_ids
        model_ids = list(set(r.model_id for r in sample_results if r.model_id))

        # Get model display names from LLMModel table
        llm_models = db.query(LLMModel).filter(LLMModel.id.in_(model_ids)).all() if model_ids else []
        model_name_map = {m.id: m.name for m in llm_models}

        # For models not in LLMModel table, use the model_id as the name
        for model_id in model_ids:
            if model_id not in model_name_map:
                model_name_map[model_id] = model_id

        # Get task data for previews
        all_task_ids = list(set(
            [r.task_id for r in sample_results if r.task_id]
            + [r.task_id for r in annotation_eval_results if r.task_id]
        ))
        tasks_data = db.query(Task).filter(Task.id.in_(all_task_ids)).all() if all_task_ids else []
        task_preview_map = {}
        for task in tasks_data:
            preview = ""
            if task.data:
                text = task.data.get("text", "") or task.data.get("content", "")
                if text:
                    preview = text[:100] + "..." if len(text) > 100 else text
            task_preview_map[task.id] = preview

        # Build task-model score matrix
        task_model_scores = {}  # {task_id: {model_id: score}}
        model_scores_list = {model_id: [] for model_id in model_ids}  # For averages

        for result in sample_results:
            task_id = result.task_id
            model_id = result.model_id

            if not task_id or not model_id:
                continue

            if task_id not in task_model_scores:
                task_model_scores[task_id] = {}

            score = _extract_primary_score(result.metrics)

            if score is not None:
                task_model_scores[task_id][model_id] = score
                model_scores_list[model_id].append(score)

        # Process annotation-based results as synthetic annotator "models"
        if annotation_eval_results:
            annotation_ids = list(set(r.annotation_id for r in annotation_eval_results if r.annotation_id))
            if annotation_ids:
                annotations_with_users = (
                    db.query(
                        Annotation.id,
                        DBUser.username,
                        DBUser.name,
                        DBUser.pseudonym,
                        DBUser.use_pseudonym,
                    )
                    .join(DBUser, Annotation.completed_by == DBUser.id)
                    .filter(Annotation.id.in_(annotation_ids))
                    .all()
                )
                # Mirror the leaderboard's pseudonym resolution
                # (benger_extended/api/routers/leaderboards_human.py:168) so
                # annotators with use_pseudonym=true display under their
                # pseudonym instead of their real name/username.
                annotator_name_map = {
                    a.id: (
                        a.pseudonym
                        if (a.use_pseudonym and a.pseudonym)
                        else (a.name or a.username)
                    )
                    for a in annotations_with_users
                }

                # Deduplicate: keep latest per (task_id, annotation_id, field_name)
                seen_task_annotations: dict = {}
                for r in sorted(annotation_eval_results, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc)):
                    seen_task_annotations[(r.task_id, r.annotation_id, r.field_name)] = r

                for r in seen_task_annotations.values():
                    display = annotator_name_map.get(r.annotation_id, "Unknown")
                    synthetic_model_id = f"annotator:{display}"
                    score = _extract_primary_score(r.metrics)

                    if score is not None:
                        if synthetic_model_id not in model_scores_list:
                            model_scores_list[synthetic_model_id] = []
                            model_ids.append(synthetic_model_id)
                        model_name_map[synthetic_model_id] = f"Annotator: {display}"

                        if r.task_id not in task_model_scores:
                            task_model_scores[r.task_id] = {}
                        task_model_scores[r.task_id][synthetic_model_id] = score
                        model_scores_list[synthetic_model_id].append(score)

        # Build response
        tasks_response = []
        for task_id in all_task_ids:
            scores = task_model_scores.get(task_id, {})
            if scores:
                tasks_response.append(
                    {
                        "task_id": task_id,
                        "task_preview": task_preview_map.get(task_id, ""),
                        "scores": scores,
                    }
                )

        # Sort tasks by task_id for consistent ordering
        tasks_response.sort(key=lambda x: x["task_id"])

        # Calculate model summaries
        summary = {}
        for model_id in model_ids:
            scores = model_scores_list[model_id]
            if scores:
                summary[model_id] = {
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                    "model_name": model_name_map.get(model_id, model_id),
                }

        # Sort models by average score descending
        sorted_models = sorted(
            model_ids, key=lambda m: summary.get(m, {}).get("avg", 0), reverse=True
        )

        return {
            "evaluation_id": evaluation_id,
            "models": sorted_models,
            "model_names": model_name_map,
            "tasks": tasks_response,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get results by task/model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get results by task/model: {str(e)}",
        )


def _get_task_data_availability(db, task_ids: list) -> tuple:
    """Return (tasks_with_annotations, generation_models_by_task) for the given task IDs."""
    from models import Generation as GenerationModel

    tasks_with_annotations: set = set()
    generation_model_by_task: dict = {}

    if task_ids:
        annotated = (
            db.query(Annotation.task_id)
            .filter(
                Annotation.task_id.in_(task_ids),
                Annotation.was_cancelled == False,  # noqa: E712
            )
            .distinct()
            .all()
        )
        tasks_with_annotations = {r[0] for r in annotated}

        gen_rows = (
            db.query(GenerationModel.task_id, GenerationModel.model_id)
            .filter(GenerationModel.task_id.in_(task_ids))
            .distinct()
            .all()
        )
        for row in gen_rows:
            generation_model_by_task.setdefault(row.task_id, set()).add(row.model_id)

    return tasks_with_annotations, generation_model_by_task


def _build_all_tasks_response(db, project_id: str) -> list:
    """Build task list with data availability info for all tasks in a project."""
    all_tasks = db.query(Task.id, Task.data).filter(Task.project_id == project_id).all()
    all_task_ids = [t.id for t in all_tasks]
    tasks_with_annotations, gen_model_by_task = _get_task_data_availability(db, all_task_ids)

    return [
        {
            "task_id": t.id,
            "task_preview": _get_task_preview(t.data),
            "scores": {},
            "has_annotation": t.id in tasks_with_annotations,
            "generation_models": list(gen_model_by_task.get(t.id, set())),
        }
        for t in all_tasks
    ]


def _get_task_preview(task_data: dict) -> str:
    """Extract a short preview string from task data."""
    if not task_data:
        return ""
    for key in ["input", "text", "question", "prompt", "content"]:
        if key in task_data:
            return str(task_data[key])[:100]
    for v in task_data.values():
        if isinstance(v, str):
            return v[:100]
    return ""


@router.get("/projects/{project_id}/results/by-task-model")
async def get_project_results_by_task_model(
    project_id: str,
    request: Request,
    evaluation_ids: Optional[str] = Query(None, description="Comma-separated evaluation run IDs to filter by"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get aggregated evaluation results across ALL completed evaluations for a project.

    Uses generation_id as the natural key to deduplicate results:
    - If a generation was evaluated in multiple runs, uses the LATEST result
    - Aggregates results from ALL completed evaluations (evaluation/llm_judge types)
    """
    from sqlalchemy import func

    from models import TaskEvaluation
    from models import Generation as GenerationModel
    from models import LLMModel

    try:
        # Verify project exists and user has access
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Get completed evaluations for this project, optionally filtered by IDs
        eval_query = db.query(DBEvaluationRun.id).filter(
            DBEvaluationRun.project_id == project_id,
            DBEvaluationRun.status == "completed",
        )
        if evaluation_ids:
            filter_ids = [eid.strip() for eid in evaluation_ids.split(",") if eid.strip()]
            if filter_ids:
                eval_query = eval_query.filter(DBEvaluationRun.id.in_(filter_ids))
        completed_evals = eval_query.all()
        completed_eval_ids = [e.id for e in completed_evals]

        if not completed_eval_ids:
            return {
                "project_id": project_id,
                "models": [],
                "model_names": {},
                "tasks": _build_all_tasks_response(db, project_id),
                "summary": {},
            }

        # Subquery: rank results by (generation_id, field_name), ordered by created_at DESC
        # Keeps the latest result per generation per config/field combination
        ranked_results = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.generation_id,
                TaskEvaluation.metrics,
                GenerationModel.model_id,
                func.row_number()
                .over(
                    partition_by=[TaskEvaluation.generation_id, TaskEvaluation.field_name],
                    order_by=TaskEvaluation.created_at.desc(),
                )
                .label("rn"),
            )
            .join(
                GenerationModel,
                TaskEvaluation.generation_id == GenerationModel.id,
            )
            .filter(TaskEvaluation.evaluation_id.in_(completed_eval_ids))
            .subquery()
        )

        # Filter to only the latest result per generation (rn = 1)
        sample_results = (
            db.query(
                ranked_results.c.task_id,
                ranked_results.c.generation_id,
                ranked_results.c.metrics,
                ranked_results.c.model_id,
            )
            .filter(ranked_results.c.rn == 1)
            .all()
        )

        # Query 2: Get annotation-based evaluation results (generation_id IS NULL)
        from models import User as DBUser
        from models import TaskEvaluation as TE2

        annotation_eval_results = (
            db.query(
                TE2.task_id,
                TE2.annotation_id,
                TE2.field_name,
                TE2.metrics,
                TE2.created_at,
            )
            .filter(
                TE2.evaluation_id.in_(completed_eval_ids),
                TE2.generation_id == None,  # noqa: E711
                TE2.annotation_id != None,  # noqa: E711
            )
            .all()
        )

        if not sample_results and not annotation_eval_results:
            return {
                "project_id": project_id,
                "models": [],
                "model_names": {},
                "tasks": _build_all_tasks_response(db, project_id),
                "summary": {},
            }

        # Get unique model_ids and their display names
        model_ids = list(set(r.model_id for r in sample_results if r.model_id))

        # Get model display names from LLMModel table
        llm_models = db.query(LLMModel).filter(LLMModel.id.in_(model_ids)).all() if model_ids else []
        model_name_map = {m.id: m.name for m in llm_models}

        # For models not in LLMModel table, use the model_id as the name
        for model_id in model_ids:
            if model_id not in model_name_map:
                model_name_map[model_id] = model_id

        # Build task-model score matrix
        # Structure: {task_id: {model_id: score, ...}, ...}
        task_scores: dict = {}
        task_previews: dict = {}
        model_scores: dict = {mid: [] for mid in model_ids}

        for result in sample_results:
            task_id = result.task_id
            model_id = result.model_id
            metrics = result.metrics or {}

            score = _extract_primary_score(metrics)

            if score is not None and model_id:
                if task_id not in task_scores:
                    task_scores[task_id] = {}
                task_scores[task_id][model_id] = score
                model_scores[model_id].append(score)

        # Process annotation-based results: add as synthetic annotator "models"
        if annotation_eval_results:
            annotation_ids = list(set(r.annotation_id for r in annotation_eval_results if r.annotation_id))
            if annotation_ids:
                annotations_with_users = (
                    db.query(
                        Annotation.id,
                        DBUser.username,
                        DBUser.name,
                        DBUser.pseudonym,
                        DBUser.use_pseudonym,
                    )
                    .join(DBUser, Annotation.completed_by == DBUser.id)
                    .filter(Annotation.id.in_(annotation_ids))
                    .all()
                )
                # Mirror the leaderboard pseudonym resolution so users with
                # use_pseudonym=true display under their pseudonym.
                annotator_name_map = {
                    a.id: (
                        a.pseudonym
                        if (a.use_pseudonym and a.pseudonym)
                        else (a.name or a.username)
                    )
                    for a in annotations_with_users
                }

                # Deduplicate: keep latest per (task_id, annotation_id, field_name)
                seen_task_annotations: dict = {}
                for r in sorted(annotation_eval_results, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc)):
                    seen_task_annotations[(r.task_id, r.annotation_id, r.field_name)] = r

                for r in seen_task_annotations.values():
                    display = annotator_name_map.get(r.annotation_id, "Unknown")
                    synthetic_model_id = f"annotator:{display}"
                    score = _extract_primary_score(r.metrics)

                    if score is not None:
                        if synthetic_model_id not in model_scores:
                            model_scores[synthetic_model_id] = []
                            model_ids.append(synthetic_model_id)
                        model_name_map[synthetic_model_id] = f"Annotator: {display}"

                        if r.task_id not in task_scores:
                            task_scores[r.task_id] = {}
                        task_scores[r.task_id][synthetic_model_id] = score
                        model_scores[synthetic_model_id].append(score)

        # Get ALL project tasks (not just evaluated ones) so unevaluated tasks show as n/a
        all_project_tasks = db.query(Task.id, Task.data).filter(Task.project_id == project_id).all()
        all_task_ids = [t.id for t in all_project_tasks]
        for task in all_project_tasks:
            task_previews[task.id] = _get_task_preview(task.data)

        # Get data availability for clickable n/a cells
        tasks_with_annotations, generation_model_by_task = _get_task_data_availability(db, all_task_ids)

        # Sort models by average score (descending)
        model_avgs = {
            mid: sum(scores) / len(scores) if scores else 0 for mid, scores in model_scores.items()
        }
        sorted_models = sorted(model_avgs.keys(), key=lambda m: model_avgs[m], reverse=True)

        # Build response - include ALL project tasks, not just evaluated ones
        tasks_response = []
        for task in all_project_tasks:
            gen_models = generation_model_by_task.get(task.id, set())
            tasks_response.append(
                {
                    "task_id": task.id,
                    "task_preview": task_previews.get(task.id, ""),
                    "scores": task_scores.get(task.id, {}),
                    "has_annotation": task.id in tasks_with_annotations,
                    "generation_models": list(gen_models),
                }
            )

        # Build summary
        summary = {}
        for model_id in sorted_models:
            scores = model_scores[model_id]
            if scores:
                summary[model_id] = {
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                    "model_name": model_name_map.get(model_id, model_id),
                }

        return {
            "project_id": project_id,
            "models": sorted_models,
            "model_names": model_name_map,
            "tasks": tasks_response,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get project results by task/model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project results by task/model: {str(e)}",
        )





@router.get("/sample-result")
async def get_sample_result_by_task_model(
    request: Request,
    task_id: str = Query(..., description="Task ID"),
    model_id: str = Query(..., description="Model ID"),
    include_history: bool = Query(True, description="Include all historical results. When false, deduplicate to latest per field_name."),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get evaluation sample results for a specific task and model combination.

    Returns all evaluation sample results where the generation was produced by
    the specified model for the specified task. Includes metrics, ground truth,
    prediction, and evaluation metadata.
    """
    try:
        from models import TaskEvaluation
        from models import Generation as GenerationModel

        # Resolve project from task and check access
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, task.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        if model_id.startswith("annotator:"):
            # Annotation-based evaluation: look up by annotator username
            from models import User as DBUser

            username = model_id.split(":", 1)[1]
            user = db.query(DBUser).filter(DBUser.username == username).first()

            if user:
                sample_results = (
                    db.query(TaskEvaluation)
                    .join(Annotation, TaskEvaluation.annotation_id == Annotation.id)
                    .filter(
                        TaskEvaluation.task_id == task_id,
                        Annotation.completed_by == user.id,
                        TaskEvaluation.generation_id == None,  # noqa: E711
                    )
                    .order_by(TaskEvaluation.created_at.desc())
                    .all()
                )
            else:
                sample_results = []
        else:
            # Generation-based evaluation: join on Generation model
            sample_results = (
                db.query(TaskEvaluation)
                .join(
                    GenerationModel,
                    TaskEvaluation.generation_id == GenerationModel.id,
                )
                .filter(
                    TaskEvaluation.task_id == task_id,
                    GenerationModel.model_id == model_id,
                )
                .order_by(TaskEvaluation.created_at.desc())
                .all()
            )

        if not sample_results:
            return {
                "task_id": task_id,
                "model_id": model_id,
                "results": [],
                "message": "No evaluation results found for this task and model",
            }

        # Deduplicate to latest per field_name when history is off
        # Results are already ordered by created_at desc, so first per field wins
        if not include_history:
            seen_fields = set()
            deduplicated = []
            for sr in sample_results:
                if sr.field_name not in seen_fields:
                    seen_fields.add(sr.field_name)
                    deduplicated.append(sr)
            sample_results = deduplicated

        # Build response with full evaluation details
        # Batch-load evaluation runs to avoid N+1 queries
        eval_ids = list(set(sr.evaluation_id for sr in sample_results if sr.evaluation_id))
        eval_map = {e.id: e for e in db.query(DBEvaluationRun).filter(DBEvaluationRun.id.in_(eval_ids)).all()} if eval_ids else {}

        results = []
        for sr in sample_results:
            evaluation = eval_map.get(sr.evaluation_id)

            result_data = {
                "id": sr.id,
                "evaluation_id": sr.evaluation_id,
                "field_name": sr.field_name,
                "answer_type": sr.answer_type,
                "ground_truth": sr.ground_truth,
                "prediction": sr.prediction,
                "metrics": sr.metrics,
                "passed": sr.passed,
                "confidence_score": sr.confidence_score,
                "error_message": sr.error_message,
                "processing_time_ms": sr.processing_time_ms,
                "created_at": sr.created_at.isoformat() if sr.created_at else None,
            }

            # Add evaluation context if available
            if evaluation:
                result_data["evaluation_context"] = {
                    "evaluation_type": (evaluation.eval_metadata or {}).get("evaluation_type"),
                    "status": evaluation.status,
                    "eval_metadata": evaluation.eval_metadata,
                }

            results.append(result_data)

        return {
            "task_id": task_id,
            "model_id": model_id,
            "results": results,
            "total_count": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sample result: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation sample result: {str(e)}",
        )
