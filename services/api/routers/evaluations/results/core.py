"""
Evaluation results listing, export, and per-sample listing endpoints.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.get("/results/{project_id}", response_model=List[EvaluationResultsResponse])
async def get_evaluation_results(
    project_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    include_human: bool = Query(True),
    include_automated: bool = Query(True),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get evaluation results for a project.

    Returns both automated and human evaluation results.
    """
    # Check project access
    if not await check_project_accessible_async(db, current_user, project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        results = []

        # Get automated evaluation results
        if include_automated:
            automated_evals = (
                (
                    await db.execute(
                        select(DBEvaluationRun)
                        .where(DBEvaluationRun.project_id == project_id)
                        .order_by(DBEvaluationRun.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
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
                await db.execute(
                    select(
                        LikertScaleEvaluation.dimension,
                        func.avg(LikertScaleEvaluation.rating).label("avg_rating"),
                        func.count(LikertScaleEvaluation.id).label("count"),
                    )
                    .join(
                        HumanEvaluationSession,
                        LikertScaleEvaluation.session_id == HumanEvaluationSession.id,
                    )
                    .where(HumanEvaluationSession.project_id == project_id)
                    .group_by(LikertScaleEvaluation.dimension)
                )
            ).all()

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
                await db.execute(
                    select(
                        PreferenceRanking.winner,
                        func.count(PreferenceRanking.id).label("count"),
                    )
                    .join(
                        HumanEvaluationSession,
                        PreferenceRanking.session_id == HumanEvaluationSession.id,
                    )
                    .where(HumanEvaluationSession.project_id == project_id)
                    .group_by(PreferenceRanking.winner)
                )
            ).all()

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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Export evaluation results in various formats.
    """
    # Check project access
    if not await check_project_accessible_async(db, current_user, project_id, get_org_context_from_request(request)):
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
    db: AsyncSession = Depends(get_async_db),
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

        # Build the shared filter conditions for both the count and the page.
        conditions = [TaskEvaluation.evaluation_id == evaluation_id]
        if field_name:
            conditions.append(TaskEvaluation.field_name == field_name)
        if passed is not None:
            conditions.append(TaskEvaluation.passed == passed)

        # Get total count
        total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(TaskEvaluation)
                    .where(*conditions)
                )
            ).scalar()
            or 0
        )

        # Apply pagination
        offset = (page - 1) * page_size
        samples = (
            (
                await db.execute(
                    select(TaskEvaluation)
                    .where(*conditions)
                    .order_by(TaskEvaluation.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            )
            .scalars()
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
