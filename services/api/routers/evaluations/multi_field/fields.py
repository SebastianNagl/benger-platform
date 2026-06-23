"""Available-fields endpoint (GET /projects/{project_id}/available-fields)."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.get("/projects/{project_id}/available-fields", response_model=AvailableFieldsResponse)
async def get_available_fields(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get available fields for evaluation mapping in a project.

    Returns categorized fields:
    - model_response_fields: Fields from LLM generations
    - human_annotation_fields: Fields from human annotations
    - reference_fields: Ground truth/reference fields
    """
    try:
        from models import Generation

        # Verify project exists
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Verify user has access to the project
        org_context = get_org_context_from_request(request)
        if not await auth_service.check_project_access_async(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this project",
            )

        from services.label_config.parser import LabelConfigParser

        model_fields = set()
        human_fields = set()
        reference_fields = set()

        # Extract human annotation fields directly from label_config (most reliable source)
        if project.label_config:
            label_config_fields = LabelConfigParser.extract_field_names(project.label_config)
            human_fields.update(label_config_fields)

        # Also check evaluation_config for reference fields (to_name mappings)
        if project.evaluation_config:
            detected_types = project.evaluation_config.get("detected_answer_types", [])
            for answer_type in detected_types:
                to_name = answer_type.get("to_name", "")
                if to_name:
                    reference_fields.add(to_name)

        # Extract distinct model fields from ALL successful generations
        from sqlalchemy import text as sa_text
        try:
            model_field_rows = (
                await db.execute(
                    select(
                        func.jsonb_array_elements(Generation.parsed_annotation)
                        .op('->>')(sa_text("'from_name'"))
                        .label("fn")
                    )
                    .join(Task, Generation.task_id == Task.id)
                    .where(
                        Task.project_id == project_id,
                        Generation.parse_status == "success",
                        Generation.parsed_annotation != None,  # noqa: E711
                    )
                    .distinct()
                )
            ).all()
            for row in model_field_rows:
                if row.fn:
                    model_fields.add(row.fn)
        except Exception:
            # Fallback: sample a single generation (for DBs without jsonb support)
            sample_gen = (
                (
                    await db.execute(
                        select(Generation)
                        .join(Task, Generation.task_id == Task.id)
                        .where(Task.project_id == project_id, Generation.parse_status == "success")
                    )
                )
                .scalars()
                .first()
            )
            if sample_gen and sample_gen.parsed_annotation:
                for result in sample_gen.parsed_annotation:
                    from_name = result.get("from_name", "")
                    if from_name:
                        model_fields.add(from_name)

        # Reference fields come from the task data (the project's source rows).
        # Skip internal/system fields that start with underscore.
        #
        # Historically we also walked an existing annotation here to derive
        # `from_name`/`to_name` values, but that propagated stale field names
        # forward when the project's `label_config` was edited (the old field
        # would keep showing up as a selectable option). The label_config is
        # the single source of truth for which annotation fields exist now —
        # we only need it for human_annotation_fields.
        sample_task = (
            (await db.execute(select(Task).where(Task.project_id == project_id)))
            .scalars()
            .first()
        )
        if sample_task and sample_task.data and isinstance(sample_task.data, dict):
            for field_name, field_value in sample_task.data.items():
                if not field_name.startswith("_") and isinstance(field_value, (str, list)):
                    reference_fields.add(field_name)

        all_fields = model_fields | human_fields | reference_fields

        return AvailableFieldsResponse(
            model_response_fields=list(model_fields),
            human_annotation_fields=list(human_fields),
            reference_fields=list(reference_fields),
            all_fields=list(all_fields),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available fields: {str(e)}",
        )

