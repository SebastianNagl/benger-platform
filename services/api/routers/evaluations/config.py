"""
Evaluation configuration management endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import extensions
from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_db
from evaluation_config import update_project_evaluation_config as generate_evaluation_config
from project_models import Project
from routers.evaluations.helpers import extract_metric_name
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

logger = logging.getLogger(__name__)


def _derive_evaluation_configs_from_selected_methods(
    selected_methods: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Derive evaluation_configs from legacy selected_methods format.

    Bridges projects configured before the N:M field evaluation system
    was introduced. Each selected automated metric becomes an evaluation config
    entry with the field's mapping preserved.
    """
    configs: List[Dict[str, Any]] = []
    for field_name, selections in selected_methods.items():
        if not isinstance(selections, dict):
            continue
        automated = selections.get("automated", [])
        field_mapping = selections.get("field_mapping", {})
        pred_field = field_mapping.get("prediction_field", field_name)
        ref_field = field_mapping.get("reference_field", field_name)

        for metric in automated:
            metric_name = metric if isinstance(metric, str) else metric.get("name", "")
            metric_params = metric.get("parameters") if isinstance(metric, dict) else None
            if not metric_name:
                continue
            entry: Dict[str, Any] = {
                "id": f"{field_name}_{metric_name}",
                "metric": metric_name,
                "display_name": metric_name.replace("_", " ").title(),
                "prediction_fields": [pred_field],
                "reference_fields": [ref_field],
                "enabled": True,
            }
            if metric_params:
                entry["metric_parameters"] = metric_params
            configs.append(entry)
    return configs


router = APIRouter()


# ============= LLM Judge Field Types Models =============


class FieldTypeInfo(BaseModel):
    """Field type information with LLM judge criteria recommendations."""

    type: str  # Answer type: span_selection, choices, text, rating, numeric
    tag: str  # Label Studio tag: Labels, Choices, TextArea, Rating, Number
    recommended_criteria: List[str]  # LLM judge criteria for this type


class FieldTypesResponse(BaseModel):
    """Response model for field types endpoint."""

    project_id: str
    field_types: Dict[str, FieldTypeInfo]


# ============= Endpoints =============


@router.get("/projects/{project_id}/evaluation-config")
async def get_project_evaluation_config(
    project_id: str,
    request: Request,
    force_regenerate: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get evaluation configuration for a project.

    Users can view evaluation config if they are superadmin or member of org assigned to project.

    If no configuration exists, it will be generated based on the project's label_config.
    """
    try:
        # Verify project exists and user has access
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Check if user can view this project's evaluation config
        org_context = get_org_context_from_request(request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view evaluation config for this project",
            )

        # Check if evaluation config exists or needs regeneration
        # Regenerate if:
        # 1. Config doesn't exist, OR
        # 2. Force regenerate requested, OR
        # 3. Label config version has ACTUALLY changed (not just missing from old config)
        existing_config_version = (
            project.evaluation_config.get("label_config_version")
            if project.evaluation_config
            else None
        )
        needs_regeneration = (
            not project.evaluation_config
            or force_regenerate
            or (
                project.label_config_version
                and existing_config_version is not None
                and existing_config_version != project.label_config_version
            )
        )

        # If old config has no label_config_version, stamp it without regenerating
        # This preserves user selections from configs created before version tracking
        if (
            project.evaluation_config
            and not force_regenerate
            and existing_config_version is None
            and project.label_config_version
        ):
            from sqlalchemy.orm.attributes import flag_modified

            project.evaluation_config["label_config_version"] = project.label_config_version
            flag_modified(project, "evaluation_config")
            db.commit()

        if needs_regeneration:
            # Generate config based on label_config or return empty structure
            if project.label_config:
                # Preserve existing selected methods if regenerating
                existing_config = (
                    project.evaluation_config
                    if (force_regenerate or project.evaluation_config)
                    else None
                )
                project.evaluation_config = generate_evaluation_config(
                    project_id=project_id,
                    label_config=project.label_config,
                    existing_config=existing_config,
                    label_config_version=project.label_config_version,
                )
                db.commit()
            else:
                # Return empty config structure if no label_config
                return {
                    "detected_answer_types": [],
                    "available_methods": {},
                    "selected_methods": {},
                    "last_updated": None,
                }

        # Lazy migration: derive evaluation_configs from selected_methods
        # for legacy projects that only have the older per-field config format
        config = project.evaluation_config
        if config and config.get("selected_methods") and not config.get("evaluation_configs"):
            from sqlalchemy.orm.attributes import flag_modified

            derived = _derive_evaluation_configs_from_selected_methods(config["selected_methods"])
            if derived:
                config["evaluation_configs"] = derived
                flag_modified(project, "evaluation_config")
                db.commit()

        return config

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch evaluation config: {str(e)}",
        )


@router.put("/projects/{project_id}/evaluation-config")
async def update_project_evaluation_config(
    project_id: str,
    config: Dict[str, Any],
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Update evaluation configuration for a project.

    This endpoint is used to save the user's selection of which evaluation methods to run.
    """
    try:
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        # Validate selected methods against available methods
        if "selected_methods" in config and "available_methods" in config:
            # Get all available field names from detected answer types
            available_field_names = set()
            if "detected_answer_types" in config:
                for answer_type in config["detected_answer_types"]:
                    available_field_names.add(answer_type.get("name", ""))
                    to_name = answer_type.get("to_name", "")
                    if to_name:
                        available_field_names.add(to_name)

            for field_name, selections in config["selected_methods"].items():
                if field_name not in config["available_methods"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Field '{field_name}' not found in available methods",
                    )

                available = config["available_methods"][field_name]

                # Validate field mappings if present
                if "field_mapping" in selections:
                    field_mapping = selections["field_mapping"]
                    pred_field = field_mapping.get("prediction_field", "")
                    ref_field = field_mapping.get("reference_field", "")

                    # Validate that mapped fields exist in available fields
                    if pred_field and pred_field not in available_field_names:
                        logger.warning(
                            f"Prediction field '{pred_field}' not found in detected answer types for field '{field_name}'"
                        )
                    if ref_field and ref_field not in available_field_names:
                        logger.warning(
                            f"Reference field '{ref_field}' not found in detected answer types for field '{field_name}'"
                        )

                # Validate automated metrics
                for metric in selections.get("automated", []):
                    metric_name = extract_metric_name(metric)
                    if metric_name not in available["available_metrics"]:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Metric '{metric_name}' not available for field '{field_name}'",
                        )

                # Validate human evaluation methods
                for method in selections.get("human", []):
                    method_name = extract_metric_name(method)
                    if method_name not in available["available_human"]:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Human evaluation method '{method_name}' not available for field '{field_name}'",
                        )

        # Update the evaluation config
        # IMPORTANT: Include label_config_version to prevent unnecessary regeneration on GET
        # Without this, the GET endpoint will regenerate the config on every page reload,
        # losing the user's selected methods (Issue #794 follow-up)
        config["label_config_version"] = project.label_config_version
        project.evaluation_config = config

        # Let extended derive any proprietary project fields (e.g. Korrektur)
        # from the new evaluation_configs. Hook is a no-op when extended is
        # not loaded.
        extensions.run_after_eval_config_save(db, project, config)

        # CRITICAL: Mark JSONB column as modified for SQLAlchemy
        # Without this, SQLAlchemy won't detect the mutation and won't persist changes
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(project, "evaluation_config")

        db.commit()
        db.refresh(project)

        return {"message": "Evaluation configuration updated successfully", "config": config}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update evaluation config: {str(e)}",
        )


@router.get("/projects/{project_id}/detect-answer-types")
async def detect_answer_types(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Detect answer types from the project's label configuration.

    This endpoint analyzes the label_config and returns detected answer types
    with their applicable evaluation methods.
    """
    try:
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

        if not project.label_config:
            return {
                "project_id": project_id,
                "detected_types": [],
                "message": "No label configuration found",
            }

        # Generate evaluation config based on label_config
        config = generate_evaluation_config(
            project_id=project_id,
            label_config=project.label_config,
            existing_config=project.evaluation_config,
        )

        return {
            "project_id": project_id,
            "detected_types": config["detected_answer_types"],
            "available_methods": config["available_methods"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect answer types: {str(e)}",
        )


@router.get("/projects/{project_id}/field-types", response_model=FieldTypesResponse)
async def get_field_types_for_llm_judge(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get field types with recommended LLM judge criteria for a project.

    This endpoint is used by the LLM-as-Judge configuration UI to:
    1. Auto-detect answer types when a field is selected
    2. Recommend appropriate evaluation criteria for each type
    3. Display type badges on field selection

    Returns:
        FieldTypesResponse with field_types mapping field names to their type info
    """
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        if not project.label_config:
            return FieldTypesResponse(
                project_id=project_id,
                field_types={},
            )

        # Generate evaluation config to get field types
        config = generate_evaluation_config(
            project_id=project_id,
            label_config=project.label_config,
            existing_config=project.evaluation_config,
        )

        # Build field types mapping with LLM judge criteria
        field_types = {}
        for field_name, field_info in config.get("available_methods", {}).items():
            field_types[field_name] = FieldTypeInfo(
                type=field_info.get("type", "custom"),
                tag=field_info.get("tag", "unknown"),
                recommended_criteria=field_info.get("llm_judge_criteria", []),
            )

        return FieldTypesResponse(
            project_id=project_id,
            field_types=field_types,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get field types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get field types: {str(e)}",
        )
