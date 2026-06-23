"""
Metric distribution and confusion-matrix endpoints.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.get("/{evaluation_id}/metrics/{metric_name}/distribution")
async def get_metric_distribution(
    evaluation_id: str,
    metric_name: str,
    request: Request,
    field_name: Optional[str] = Query(None, description="Filter by field name"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
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
        eval_result = await db.execute(
            select(DBEvaluationRun).where(DBEvaluationRun.id == evaluation_id)
        )
        evaluation = eval_result.scalar_one_or_none()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Build query
        query = select(TaskEvaluation).where(
            TaskEvaluation.evaluation_id == evaluation_id
        )

        if field_name:
            query = query.where(TaskEvaluation.field_name == field_name)

        samples = (await db.execute(query)).scalars().all()

        if not samples:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No samples found for this evaluation",
            )

        # Extract metric values. Use _coerce_metric_value because metrics
        # can be in either the legacy flat shape (bare float at the top
        # level) OR the canonical nested shape ({value, method, details,
        # error}). Falloesung's immediate-eval rows are nested; bulk-eval
        # rows are flat — a direct float() cast would crash on nested
        # rows. _coerce_metric_value tries .value first, then .total_score
        # / .score (legacy korrektur), then bare float fallback, so it
        # handles all shapes uniformly.
        values = []
        for sample in samples:
            if sample.metrics and metric_name in sample.metrics:
                coerced = _coerce_metric_value(sample.metrics[metric_name])
                if coerced is not None:
                    values.append(coerced)

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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Generate confusion matrix for classification metrics.

    Only works for fields with discrete class predictions.
    """
    try:
        from models import TaskEvaluation
        from schemas.evaluation_schemas import ConfusionMatrix

        # Verify evaluation exists
        eval_result = await db.execute(
            select(DBEvaluationRun).where(DBEvaluationRun.id == evaluation_id)
        )
        evaluation = eval_result.scalar_one_or_none()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Get all samples for this field
        samples = (
            (
                await db.execute(
                    select(TaskEvaluation).where(
                        TaskEvaluation.evaluation_id == evaluation_id,
                        TaskEvaluation.field_name == field_name,
                    )
                )
            )
            .scalars()
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
