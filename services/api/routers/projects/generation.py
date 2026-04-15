"""LLM generation endpoints for projects."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.authorization import auth_service
from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

router = APIRouter()


@router.get("/{project_id}/generation-config", response_model=dict)
def get_generation_config(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_user),
):
    """Get generation configuration for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check view permissions
    from app.core.authorization import Permission

    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_VIEW, db, org_context=get_org_context_from_request(request)):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to view this project's generation config",
        )

    # Return config with available options
    if not project.generation_config:
        return {
            "available_options": {
                "models": {
                    "openai": ["gpt-4o", "gpt-3.5-turbo"],
                    "anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229"],
                },
                "presentation_modes": ["label_config", "template", "raw_json", "auto"],
            },
        }

    return {
        "available_options": {
            "models": {
                "openai": ["gpt-4o", "gpt-3.5-turbo"],
                "anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229"],
            },
            "presentation_modes": ["label_config", "template", "raw_json", "auto"],
        },
        "selected_configuration": project.generation_config.get("selected_configuration"),
    }


@router.put("/{project_id}/generation-config", response_model=dict)
def update_generation_config(
    project_id: str,
    config: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_user),
):
    """Update generation configuration for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permissions
    from app.core.authorization import Permission

    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_EDIT, db, org_context=get_org_context_from_request(request)):
        raise HTTPException(
            status_code=403, detail="You don't have permission to edit this project"
        )

    # Update config
    project.generation_config = config
    flag_modified(project, "generation_config")
    db.commit()

    return {"message": "Generation configuration updated successfully", "config": config}


@router.delete("/{project_id}/generation-config", status_code=204)
def clear_generation_config(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_user),
):
    """Clear generation configuration for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permissions
    from app.core.authorization import Permission

    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_EDIT, db, org_context=get_org_context_from_request(request)):
        raise HTTPException(
            status_code=403, detail="You don't have permission to edit this project"
        )

    project.generation_config = None
    flag_modified(project, "generation_config")
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/generation-status", response_model=dict)
def get_project_generation_status(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_user),
):
    """Get all generations for a project"""
    # Check project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    generations = (
        db.query(DBResponseGeneration)
        .filter(DBResponseGeneration.project_id == project_id)
        .order_by(DBResponseGeneration.started_at.desc())
        .all()
    )

    if not generations:
        return {"generations": [], "is_running": False, "latest_status": None}

    is_running = any(g.status in ["pending", "running"] for g in generations)

    return {
        "generations": [
            {
                "id": g.id,
                "model_id": g.model_id,
                "status": g.status,
                "started_at": g.started_at.isoformat() if g.started_at else None,
                "completed_at": g.completed_at.isoformat() if g.completed_at else None,
                "error_message": g.error_message,
            }
            for g in generations
        ],
        "is_running": is_running,
        "latest_status": generations[0].status if generations else None,
    }
