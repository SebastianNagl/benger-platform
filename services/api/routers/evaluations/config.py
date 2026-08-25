"""
Evaluation configuration management endpoints.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import extensions
from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_async_db, get_db
from services.evaluation.config import update_project_evaluation_config as generate_evaluation_config
from project_models import Project
from routers.evaluations.helpers import extract_metric_name
from routers.projects.helpers import (
    check_project_accessible,
    check_project_accessible_async,
    get_org_context_from_request,
)
from utils.json_merge import deep_merge_dicts

logger = logging.getLogger(__name__)


def _stored_config_version(project: Project):
    return (
        project.evaluation_config.get("label_config_version")
        if project.evaluation_config
        else None
    )


def _needs_version_stamp(project: Project, force_regenerate: bool) -> bool:
    """Old config predates version tracking — stamp it without regenerating."""
    return bool(
        project.evaluation_config
        and not force_regenerate
        and _stored_config_version(project) is None
        and project.label_config_version
    )


def _needs_regeneration(project: Project, force_regenerate: bool) -> bool:
    """Config missing, regeneration forced, or label config actually changed."""
    stored_version = _stored_config_version(project)
    return bool(
        not project.evaluation_config
        or force_regenerate
        or (
            project.label_config_version
            and stored_version is not None
            and stored_version != project.label_config_version
        )
    )


def _needs_lazy_migration(project: Project) -> bool:
    """Legacy per-field config without the newer evaluation_configs list."""
    config = project.evaluation_config
    return bool(config and config.get("selected_methods") and not config.get("evaluation_configs"))


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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get evaluation configuration for a project.

    Users can view evaluation config if they are superadmin or member of org assigned to project.

    If no configuration exists, it will be generated based on the project's label_config.
    """
    try:
        # Verify project exists and user has access
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Check if user can view this project's evaluation config
        org_context = get_org_context_from_request(request)
        if not await auth_service.check_project_access_async(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view evaluation config for this project",
            )

        # This GET has three derivation-write paths (version stamp,
        # regeneration, lazy migration). The hot read path stays lock-free;
        # when any write may be needed, the row is re-read FOR UPDATE and the
        # conditions re-checked on the refreshed state, so these writes can't
        # clobber a concurrent config PUT/PATCH (issue #291).
        if (
            _needs_version_stamp(project, force_regenerate)
            or _needs_regeneration(project, force_regenerate)
            or _needs_lazy_migration(project)
        ):
            locked = await db.execute(
                select(Project)
                .where(Project.id == project_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            project = locked.scalar_one()

        from sqlalchemy.orm.attributes import flag_modified

        # If old config has no label_config_version, stamp it without regenerating
        # This preserves user selections from configs created before version tracking
        if _needs_version_stamp(project, force_regenerate):
            project.evaluation_config["label_config_version"] = project.label_config_version
            flag_modified(project, "evaluation_config")
            await db.commit()

        if _needs_regeneration(project, force_regenerate):
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
                await db.commit()
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
        if _needs_lazy_migration(project):
            derived = _derive_evaluation_configs_from_selected_methods(config["selected_methods"])
            if derived:
                config["evaluation_configs"] = derived
                flag_modified(project, "evaluation_config")
                await db.commit()

        return config

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch evaluation config: {str(e)}",
        )


def validate_evaluation_config_entries(eval_configs_list) -> None:
    """Per-entry validation of ``evaluation_configs`` (raises HTTPException 422).

    The single source of truth for what a valid entry looks like — used by
    the eval-config PUT below, and importable by extension code that writes
    eval configs through other paths (e.g. the Bewertungsbogen setup) so
    their tests can pin that written configs stay PUT-able.
    """
    if not isinstance(eval_configs_list, list):
        return
    for cfg in eval_configs_list:
        if not isinstance(cfg, dict):
            continue
        mp = cfg.get("metric_parameters")
        if not isinstance(mp, dict):
            continue
        # metric_parameters.judges shape: list of
        # {judge_model_id: str, runs: int (1..25)}.
        judges = mp.get("judges")
        if judges is not None:
            if not isinstance(judges, list) or not judges:
                raise HTTPException(
                    status_code=422,
                    detail="metric_parameters.judges must be a non-empty list",
                )
            for j in judges:
                if not isinstance(j, dict):
                    raise HTTPException(
                        status_code=422,
                        detail="each judges entry must be {judge_model_id: str, runs: int}",
                    )
                if not isinstance(j.get("judge_model_id"), str) or not j["judge_model_id"]:
                    raise HTTPException(
                        status_code=422,
                        detail="judges[].judge_model_id must be a non-empty string",
                    )
                runs = j.get("runs", 1)
                if not isinstance(runs, int) or runs < 1 or runs > 25:
                    raise HTTPException(
                        status_code=422,
                        detail="judges[].runs must be an integer between 1 and 25",
                    )

        # Phase 7 consolidation guard: Falllösung's prompt template
        # hardcodes a 0–100 raw rubric (10 dimensions summing to 100).
        # If a config sets score_scale to anything else, the worker's
        # score-scale ladder produces nonsense (e.g. score_scale="1-5"
        # would compute (75 - 1) / 4 = 18.5 from a 75/100 raw score).
        # Reject at config-save time so the misconfiguration fails
        # loud here instead of silently mis-grading every cell at
        # eval time.
        if cfg.get("metric") == "llm_judge_falloesung":
            score_scale = mp.get("score_scale")
            if score_scale is not None and score_scale != "0-100":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "llm_judge_falloesung requires "
                        "metric_parameters.score_scale='0-100' "
                        "(falloesung's prompt is a fixed 0–100 "
                        f"rubric); got {score_scale!r}"
                    ),
                )

        # llm_judge_rubric grades against per-task Bewertungsbogen
        # rows generated from a project prompt structure. Both the
        # generator model and the prompt reference are required —
        # without them the generate-missing-rubrics flow has nothing
        # to run — and the grading prompt template must exist because
        # multi-dim mode fails without one (the wizard editor and the
        # extended setup endpoint write a default; API callers must
        # supply their own).
        if cfg.get("metric") == "llm_judge_rubric":
            for key, label in (
                ("rubric_generator_model_id", "the rubric-generator model id"),
                ("rubric_prompt_key", "the generation_config.prompt_structures key"),
                ("custom_prompt_template", "the grading prompt template"),
            ):
                value = mp.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"llm_judge_rubric requires metric_parameters.{key} "
                            f"({label}) as a non-empty string"
                        ),
                    )
            if mp.get("custom_criteria"):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "llm_judge_rubric resolves its criteria from the "
                        "task's Bewertungsbogen; metric_parameters."
                        "custom_criteria must be empty (use llm_judge_custom "
                        "for config-level criteria)"
                    ),
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

    The body is deep-merged into the stored ``evaluation_config`` document
    (same contract as ``PATCH /projects/{id}``): nested dicts merge
    recursively, lists are replaced wholesale, explicit nulls delete keys.
    Clients therefore send only the keys they own — e.g. the project page
    sends ``{"evaluation_configs": [...]}`` — and sibling keys survive
    (issue #289).
    """
    try:
        # Verify project exists. FOR UPDATE: the deep-merge below is a
        # read-merge-write on the JSONB column; the row lock serializes
        # concurrent writers (issue #291)
        project = db.query(Project).filter(Project.id == project_id).with_for_update().first()
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

        # Validate runs_per_task at project-default level (multi-run for
        # non-judge or single-judge metrics). Bounded for the same fat-finger
        # reason as the generation router.
        if "runs_per_task" in config:
            rpt = config["runs_per_task"]
            if not isinstance(rpt, int) or rpt < 1 or rpt > 25:
                raise HTTPException(
                    status_code=422,
                    detail="evaluation_config.runs_per_task must be an integer between 1 and 25",
                )

        # Validate every evaluation_config entry (judges shape + per-metric
        # rules) — extracted so extension code that WRITES eval configs
        # outside this PUT (e.g. the Bewertungsbogen setup) can round-trip
        # the same rules in its tests.
        eval_configs_list = config.get("evaluation_configs") or config.get("multi_field_evaluations") or []
        validate_evaluation_config_entries(eval_configs_list)

        # Deep-merge the body into the stored config — same contract as
        # PATCH /projects/{id} (crud.py): nested dicts merge recursively,
        # lists are replaced wholesale, explicit nulls delete keys. Lets
        # callers send minimal bodies (e.g. only evaluation_configs) without
        # clobbering sibling keys a concurrent eval-defaults PATCH wrote
        # (issue #289 lost-update).
        merged = deep_merge_dicts(project.evaluation_config or {}, config)

        # IMPORTANT: Include label_config_version to prevent unnecessary regeneration on GET
        # Without this, the GET endpoint will regenerate the config on every page reload,
        # losing the user's selected methods (Issue #794 follow-up)
        merged["label_config_version"] = project.label_config_version
        project.evaluation_config = merged

        # Let extended derive any proprietary project fields (e.g. Korrektur)
        # from the new evaluation_configs. Hook is a no-op when extended is
        # not loaded. Receives the merged doc — the config as saved.
        extensions.run_after_eval_config_save(db, project, merged)

        # CRITICAL: Mark JSONB column as modified for SQLAlchemy
        # Without this, SQLAlchemy won't detect the mutation and won't persist changes
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(project, "evaluation_config")

        db.commit()
        db.refresh(project)

        return {"message": "Evaluation configuration updated successfully", "config": merged}

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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Detect answer types from the project's label configuration.

    This endpoint analyzes the label_config and returns detected answer types
    with their applicable evaluation methods.
    """
    try:
        # Get project
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, project_id, org_context):
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
    db: AsyncSession = Depends(get_async_db),
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
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, project_id, org_context):
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
