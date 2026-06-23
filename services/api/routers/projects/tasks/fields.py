"""Task data field discovery endpoint + field extraction helper."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


SENSITIVE_FIELD_PATTERNS = {
    "annotations",
    "annotation",
    "reference_answer",
    "reference",
    "ground_truth",
    "correct_answer",
    "expected_output",
    "label",
    "labels",
    "gold_standard",
}


def extract_fields_from_data(data: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    """
    Recursively extract field paths from task data.

    Args:
        data: Task data dictionary
        prefix: Current path prefix for nested fields

    Returns:
        List of field info dictionaries
    """
    fields = []

    if not isinstance(data, dict):
        return fields

    for key, value in data.items():
        # Skip sensitive fields
        if key.lower() in SENSITIVE_FIELD_PATTERNS:
            continue

        full_path = f"${prefix}.{key}" if prefix else f"${key}"
        display_name = key.replace("_", " ").title()

        # Determine data type and sample value
        if isinstance(value, str):
            data_type = "string"
            sample = value[:100] + "..." if len(value) > 100 else value
        elif isinstance(value, dict):
            data_type = "object"
            sample = "{...}"
            # Recursively extract nested fields
            nested_prefix = f"{prefix}.{key}" if prefix else key
            nested_fields = extract_fields_from_data(value, nested_prefix)
            fields.extend(nested_fields)
        elif isinstance(value, list):
            data_type = "array"
            sample = f"[{len(value)} items]"
        elif isinstance(value, (int, float)):
            data_type = "number"
            sample = str(value)
        elif isinstance(value, bool):
            data_type = "boolean"
            sample = str(value)
        else:
            data_type = "unknown"
            sample = str(value)[:50] if value else None

        fields.append(
            {
                "path": full_path,
                "display_name": display_name,
                "sample_value": sample,
                "data_type": data_type,
                "is_nested": bool(prefix),
            }
        )

    return fields


@router.get("/{project_id}/task-fields")
async def get_task_data_fields(
    project_id: str,
    request: Request,
    sample_count: int = Query(default=5, ge=1, le=20),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Discover available fields from task data for field mapping.

    Scans sample tasks in the project to find all available field names,
    including nested fields (e.g., $context.jurisdiction, $prompts.prompt_clean).

    Filters out sensitive fields like ground_truth, annotations, etc.

    Reusable endpoint for:
    - LLM Judge field mapping
    - Generation prompt structures
    - Annotation configuration (reference panel)

    Args:
        project_id: Project to scan
        sample_count: Number of tasks to sample (default 5, max 20)

    Returns:
        TaskFieldsResponse with discovered fields and sample data
    """
    # Verify project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get sample tasks
    tasks = (
        await db.execute(
            select(Task).where(Task.project_id == project_id).limit(sample_count)
        )
    ).scalars().all()

    if not tasks:
        return {
            "project_id": project_id,
            "fields": [],
            "sample_task_count": 0,
        }

    # Aggregate fields from all sample tasks
    all_fields: Dict[str, Dict[str, Any]] = {}

    for task in tasks:
        if not task.data:
            continue

        task_fields = extract_fields_from_data(task.data)

        for field in task_fields:
            # Keep first sample value encountered
            if field["path"] not in all_fields:
                all_fields[field["path"]] = field

    # Sort fields: top-level first, then nested, alphabetically within each group
    sorted_fields = sorted(all_fields.values(), key=lambda f: (f["is_nested"], f["path"]))

    return {
        "project_id": project_id,
        "fields": sorted_fields,
        "sample_task_count": len(tasks),
    }
