"""
Evaluation configuration validation endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from project_models import Project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate-config")
async def validate_evaluation_config(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Validate alignment between generation_config and evaluation_config.

    Ensures that output fields from generation match input fields for evaluation.
    """
    try:
        from schemas.evaluation_schemas import ConfigValidationResult

        # Get project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        errors = []
        warnings = []

        # Extract generation fields
        generation_fields = []
        if project.generation_config:
            prompt_structures = project.generation_config.get("prompt_structures", [])
            for structure in prompt_structures:
                if "output_fields" in structure:
                    generation_fields.extend(structure["output_fields"])

        # Extract evaluation fields
        evaluation_fields = []
        if project.evaluation_config:
            detected_types = project.evaluation_config.get("detected_answer_types", [])
            evaluation_fields = [at["name"] for at in detected_types]

        # Find matches and mismatches
        generation_set = set(generation_fields)
        evaluation_set = set(evaluation_fields)

        matched_fields = list(generation_set & evaluation_set)
        missing_in_evaluation = list(generation_set - evaluation_set)
        missing_in_generation = list(evaluation_set - generation_set)

        # Generate errors and warnings
        if missing_in_evaluation:
            warnings.append(
                f"Generation produces fields not configured for evaluation: {', '.join(missing_in_evaluation)}"
            )

        if missing_in_generation:
            errors.append(
                f"Evaluation expects fields not produced by generation: {', '.join(missing_in_generation)}"
            )

        if not matched_fields:
            errors.append("No overlapping fields between generation and evaluation configurations")

        return ConfigValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            generation_fields=generation_fields,
            evaluation_fields=evaluation_fields,
            matched_fields=matched_fields,
            missing_in_evaluation=missing_in_evaluation,
            missing_in_generation=missing_in_generation,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate config: {str(e)}",
        )
