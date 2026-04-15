"""
Shared helper functions for projects API.

These functions provide common operations used across multiple project endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationConfig,
    HumanEvaluationResult,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from project_schemas import ProjectResponse


def calculate_project_stats(db: Session, project_id: str, response: ProjectResponse) -> None:
    """Calculate and set project statistics on a response object

    NOTE: For batch operations (e.g., list_projects), use calculate_project_stats_batch
    instead to avoid N+1 query problem.
    """
    from project_models import Annotation

    response.task_count = db.query(Task).filter(Task.project_id == project_id).count()
    # Count annotations that aren't cancelled
    response.annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .count()
    )
    response.completed_tasks_count = (
        db.query(Task).filter(Task.project_id == project_id, Task.is_labeled == True).count()
    )

    # Calculate progress based on Label Studio approach
    if response.task_count > 0:
        response.progress_percentage = min(
            100.0, (response.completed_tasks_count / response.task_count) * 100
        )
    else:
        response.progress_percentage = 0.0


def calculate_project_stats_batch(db: Session, project_ids: List[str]) -> Dict[str, Dict[str, int]]:
    """Calculate project statistics for multiple projects using optimized queries.

    Replaces N+1 query pattern with 2 aggregation queries.
    - Before: 1 + (N × 3) queries for N projects
    - After: 2 queries total (99.3% reduction for 100 projects)

    Args:
        db: Database session
        project_ids: List of project IDs to fetch stats for

    Returns:
        Dict mapping project_id to stats dict with keys:
        - task_count
        - completed_tasks_count
        - annotation_count
    """
    from project_models import Annotation

    if not project_ids:
        return {}

    # Query 1: Task and completed task stats using aggregation
    task_stats_query = (
        db.query(
            Task.project_id,
            func.count(Task.id).label('task_count'),
            func.sum(case((Task.is_labeled == True, 1), else_=0)).label('completed_tasks_count'),
        )
        .filter(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    )

    # Query 2: Annotation stats using aggregation
    # Only count completed annotations (non-cancelled, with actual results - not draft-only)
    annotation_stats_query = (
        db.query(Annotation.project_id, func.count(Annotation.id).label('annotation_count'))
        .filter(
            Annotation.project_id.in_(project_ids),
            Annotation.was_cancelled == False,
            # Exclude draft-only annotations (empty result but has draft)
            Annotation.result != None,
            func.jsonb_array_length(Annotation.result) > 0,
        )
        .group_by(Annotation.project_id)
    )

    # Execute queries
    task_stats = task_stats_query.all()
    annotation_stats = annotation_stats_query.all()

    # Build stats lookup dictionary
    stats_map = {}

    # Initialize all projects with zero stats
    for project_id in project_ids:
        stats_map[project_id] = {'task_count': 0, 'completed_tasks_count': 0, 'annotation_count': 0}

    # Populate task stats
    for stat in task_stats:
        stats_map[stat.project_id]['task_count'] = stat.task_count or 0
        stats_map[stat.project_id]['completed_tasks_count'] = stat.completed_tasks_count or 0

    # Populate annotation stats
    for stat in annotation_stats:
        stats_map[stat.project_id]['annotation_count'] = stat.annotation_count or 0

    return stats_map


def calculate_generation_stats(db: Session, project: Project, response: ProjectResponse) -> None:
    """Calculate and set generation-related statistics for the /generation page"""

    # 1. Check if project has generation_config with prompt structures (Issue #762)
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)

    # For backward compatibility, generation_prompts_ready now checks prompt structures
    response.generation_prompts_ready = bool(prompt_structures)

    # 3. Count configured models in generation_config (single source of truth)
    response.generation_models_count = 0
    if (
        project.generation_config
        and project.generation_config.get('selected_configuration')
        and project.generation_config['selected_configuration'].get('models')
    ):
        response.generation_models_count = len(
            project.generation_config['selected_configuration']['models']
        )

    # 4. Check if generation is complete for all tasks and all models
    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        # Get all task IDs for this project
        project_task_ids = [
            task.id for task in db.query(Task.id).filter(Task.project_id == project.id).all()
        ]

        if project_task_ids:
            # Count completed generations for tasks in this project
            completed_generations = (
                db.query(ResponseGeneration)
                .filter(
                    ResponseGeneration.task_id.in_(project_task_ids),
                    ResponseGeneration.status == 'completed',
                )
                .count()
            )

            expected_generations = response.task_count * response.generation_models_count
            response.generation_completed = completed_generations >= expected_generations


def get_user_with_memberships(db: Session, user_id: str) -> User:
    """Get user with organization memberships loaded"""
    return (
        db.query(User)
        .options(joinedload(User.organization_memberships))
        .filter(User.id == user_id)
        .first()
    )


def get_accessible_project_ids(
    db: Session,
    user,
    org_context: Optional[str] = None,
) -> Optional[List[str]]:
    """Get project IDs accessible to a user based on organization context.

    Args:
        db: Database session
        user: Current authenticated user (auth_module User or DB User)
        org_context: Value of X-Organization-Context header.
                     "private" or None = user's private projects only
                     org_id string = projects in that org

    Returns:
        List of accessible project IDs, or None for superadmins (no filter needed).
    """
    if user.is_superadmin:
        return None

    if not org_context or org_context == "private":
        rows = (
            db.query(Project.id)
            .filter(
                Project.is_private == True,
                Project.created_by == str(user.id),
            )
            .all()
        )
        return [r.id for r in rows]

    # Org mode: verify membership then get org projects
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_org_ids = []
    if user_with_memberships and user_with_memberships.organization_memberships:
        user_org_ids = [
            m.organization_id for m in user_with_memberships.organization_memberships if m.is_active
        ]

    if org_context not in user_org_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    rows = (
        db.query(ProjectOrganization.project_id)
        .filter(ProjectOrganization.organization_id == org_context)
        .all()
    )
    return [r.project_id for r in rows]


def get_org_context_from_request(request: Request) -> Optional[str]:
    """Extract organization context from request.

    Checks request.state (set by OrgContextMiddleware) first,
    falls back to X-Organization-Context header.
    """
    if hasattr(request, "state") and hasattr(request.state, "organization_context"):
        return request.state.organization_context
    return request.headers.get("X-Organization-Context")


def check_project_accessible(
    db: Session,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> bool:
    """Check if a user can access a specific project.

    Args:
        db: Database session
        user: Current authenticated user
        project_id: Project to check access for
        org_context: Value of X-Organization-Context header.
            When provided, enforces context-aware checking:
            - "private" -> only creator's own private projects
            - org_id -> project must belong to that org, user must be member
            When None, falls back to legacy behavior (any org membership).
        project: Optional pre-loaded Project object to avoid redundant DB query.
    """
    if user.is_superadmin:
        return True

    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    # Context-aware mode
    if org_context is not None:
        if org_context == "private":
            # Private mode: only user's own private projects
            return (
                getattr(project, "is_private", False)
                and str(user.id) == str(project.created_by)
            )

        # Org mode: project must belong to this specific org
        # AND user must be an active member of this org
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        ]
        if org_context not in project_org_ids:
            return False

        user_with_memberships = get_user_with_memberships(db, str(user.id))
        if not user_with_memberships or not user_with_memberships.organization_memberships:
            return False

        return any(
            m.organization_id == org_context and m.is_active
            for m in user_with_memberships.organization_memberships
        )

    # Legacy mode (org_context=None): backward compatibility
    if getattr(project, "is_private", False):
        return str(user.id) == str(project.created_by)

    project_org_ids = [
        r.organization_id
        for r in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    ]
    if not project_org_ids:
        return str(user.id) == str(project.created_by)

    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return False

    user_org_ids = {
        m.organization_id for m in user_with_memberships.organization_memberships if m.is_active
    }
    return bool(user_org_ids & set(project_org_ids))


def check_task_assigned_to_user(
    db: Session,
    user,
    task_id: str,
    project: Project,
) -> bool:
    """Check if a task is assigned to the user when in manual/auto assignment mode.

    Aligned with Label Studio Enterprise: unassigned tasks should be invisible
    to annotators (404), not forbidden (403). Callers decide the HTTP status.

    Returns True if:
    - Project assignment_mode is 'open' (no restrictions)
    - User is superadmin
    - User's org role is not ANNOTATOR (admins/contributors bypass)
    - User has an active assignment for this task

    Returns False only when an annotator tries to access an unassigned task
    in manual/auto mode.
    """
    if getattr(project, "assignment_mode", "open") == "open":
        return True

    if user.is_superadmin:
        return True

    # Resolve user role from org memberships
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_role = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .all()
        ]
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    # Non-annotator roles (admin, contributor) bypass assignment checks
    if user_role and user_role.upper() not in ["ANNOTATOR"]:
        return True

    # Check if user has any assignment for this task (including completed)
    # Completed assignments still grant read access so annotators can review their work
    assignment = (
        db.query(TaskAssignment)
        .filter(
            TaskAssignment.task_id == task_id,
            TaskAssignment.user_id == str(user.id),
            TaskAssignment.status.in_(["assigned", "in_progress", "completed"]),
        )
        .first()
    )
    return assignment is not None


def check_user_can_edit_project(
    db: Session,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Check if a user can edit a project (creator, superadmin, or allowed org role).

    Used for project updates, bulk task operations, and other write actions.
    Does NOT check project accessibility — call check_project_accessible first.
    """
    if user.is_superadmin:
        return True

    # Check if user is the project creator
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and str(project.created_by) == str(user.id):
        return True

    # Check org role
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if user_with_memberships and user_with_memberships.organization_memberships:
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        ]
        for membership in user_with_memberships.organization_memberships:
            if (
                membership.organization_id in project_org_ids
                and membership.is_active
                and membership.role in allowed_roles
            ):
                return True

    return False


async def require_project_access(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Project:
    """FastAPI dependency: load project and verify access based on org context."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")
    return project


def get_project_organizations(db: Session, project_id: str) -> List[Dict[str, Any]]:
    """Get all organizations assigned to a project"""
    project_orgs = (
        db.query(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )

    return [
        {
            "id": po.organization.id,
            "name": po.organization.name,
        }
        for po in project_orgs
        if po.organization  # Filter out any with missing organization references
    ]


def get_comprehensive_project_data(db: Session, project_id: str) -> Dict[str, Any]:
    """
    Export complete project data including all related entities.

    Returns comprehensive project export data including:
    - Project configuration
    - All tasks with metadata
    - All annotations
    - All LLM generations
    - All evaluations
    - Project members and assignments
    - All prompts and generation jobs
    """
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Convert project to dict
    project_data = {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "label_config": project.label_config,
        # Note: generation_structure removed in Issue #762 - now in generation_config.prompt_structures
        "expert_instruction": project.expert_instruction,
        "show_instruction": project.show_instruction,
        "show_skip_button": project.show_skip_button,
        "enable_empty_annotation": project.enable_empty_annotation,
        "created_by": project.created_by,
        "organization_id": (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .first()[0]
            if db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .first()
            else None
        ),
        "min_annotations_per_task": project.min_annotations_per_task,
        "is_published": project.is_published,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        # Issue #817: Add missing fields for full roundtrip capability
        "generation_config": project.generation_config,  # Contains prompt_structures and selected models
        "evaluation_config": project.evaluation_config,  # Contains evaluation methods per field
        "label_config_version": project.label_config_version,
        "label_config_history": project.label_config_history,
        "maximum_annotations": project.maximum_annotations,
        "assignment_mode": project.assignment_mode,
        "show_submit_button": project.show_submit_button,
        "require_comment_on_skip": project.require_comment_on_skip,
        "require_confirm_before_submit": project.require_confirm_before_submit,
        "is_archived": project.is_archived,
        "questionnaire_enabled": project.questionnaire_enabled,
        "questionnaire_config": project.questionnaire_config,
        "randomize_task_order": project.randomize_task_order,
    }

    # Get all tasks
    tasks = db.query(Task).filter(Task.project_id == project_id).all()

    # Get generation counts per task (calculated, not stored)
    task_ids = [task.id for task in tasks]
    generation_counts = {}
    if task_ids:
        gen_counts = (
            db.query(Generation.task_id, func.count(Generation.id))
            .filter(Generation.task_id.in_(task_ids))
            .group_by(Generation.task_id)
            .all()
        )
        generation_counts = {task_id: count for task_id, count in gen_counts}

    from routers.projects.serializers import (
        serialize_annotation,
        serialize_evaluation_run,
        serialize_generation,
        serialize_task,
        serialize_task_evaluation,
    )

    tasks_data = []
    for task in tasks:
        task_data = serialize_task(
            task, mode="full",
            total_generations=generation_counts.get(task.id, 0),
        )
        tasks_data.append(task_data)

    # Get all annotations
    annotations = db.query(Annotation).filter(Annotation.project_id == project_id).all()
    annotations_data = [
        serialize_annotation(ann, mode="full") for ann in annotations
    ]

    # Note: Predictions export removed - predictions table dropped in migration 411540fa6c40
    # predictions = db.query(Prediction).join(Task).filter(Task.project_id == project_id).all()
    predictions_data = []  # Empty list for backward compatibility in export format
    # for prediction in predictions:
    #     prediction_data = {
    #         "id": prediction.id,
    #         "task_id": prediction.task_id,
    #         "result": prediction.result,
    #         "score": prediction.score,
    #         "model_version": prediction.model_version,
    #         "model_name": prediction.model_name,
    #         "model_backend": prediction.model_backend,
    #         "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
    #     }
    #     predictions_data.append(prediction_data)

    # Get task IDs for querying generations
    task_ids = [task.id for task in tasks]

    # Get all generations for project tasks
    generations_data = []
    if task_ids:
        generations = db.query(Generation).filter(Generation.task_id.in_(task_ids)).all()
        generations_data = [
            serialize_generation(gen, mode="full") for gen in generations
        ]

    # Get all response generations for project tasks
    response_generations_data = []
    if task_ids:
        response_generations = (
            db.query(ResponseGeneration).filter(ResponseGeneration.task_id.in_(task_ids)).all()
        )
        for resp_gen in response_generations:
            resp_gen_data = {
                "id": resp_gen.id,
                "task_id": resp_gen.task_id,
                "model_id": resp_gen.model_id,
                "config_id": resp_gen.config_id,
                "status": resp_gen.status,
                "responses_generated": resp_gen.responses_generated,
                "error_message": resp_gen.error_message,
                "generation_metadata": resp_gen.generation_metadata,
                "created_by": resp_gen.created_by,
                "created_at": resp_gen.created_at.isoformat() if resp_gen.created_at else None,
                "started_at": resp_gen.started_at.isoformat() if resp_gen.started_at else None,
                "completed_at": resp_gen.completed_at.isoformat()
                if resp_gen.completed_at
                else None,
            }
            response_generations_data.append(resp_gen_data)

    # Get all evaluations for this project
    evaluations_data = []
    evaluations = db.query(EvaluationRun).filter(EvaluationRun.project_id == project_id).all()
    if evaluations:
        evaluations_data = [
            serialize_evaluation_run(er, mode="full") for er in evaluations
        ]

    # Get all evaluation metrics
    evaluation_metrics_data = []
    if evaluations_data:
        evaluation_ids = [e["id"] for e in evaluations_data]
        eval_metrics = (
            db.query(EvaluationRunMetric)
            .filter(EvaluationRunMetric.evaluation_id.in_(evaluation_ids))
            .all()
        )
        for metric in eval_metrics:
            metric_data = {
                "id": metric.id,
                "evaluation_id": metric.evaluation_id,
                "evaluation_type_id": metric.evaluation_type_id,
                "value": metric.value,
                "created_at": metric.created_at.isoformat() if metric.created_at else None,
            }
            evaluation_metrics_data.append(metric_data)

    # Get all task evaluations (per-task evaluation results)
    task_evaluations_data = []
    if evaluations_data:
        evaluation_ids = [e["id"] for e in evaluations_data]
        task_evals = (
            db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id.in_(evaluation_ids))
            .all()
        )
        task_evaluations_data = [
            serialize_task_evaluation(te, mode="full") for te in task_evals
        ]

    # Get human evaluation configs for project tasks
    human_evaluation_configs_data = []
    if task_ids:
        human_configs = (
            db.query(HumanEvaluationConfig)
            .filter(HumanEvaluationConfig.task_id.in_(task_ids))
            .all()
        )
        for config in human_configs:
            config_data = {
                "id": config.id,
                "task_id": config.task_id,
                "evaluation_project_id": config.evaluation_project_id,
                "evaluator_count": config.evaluator_count,
                "randomization_seed": config.randomization_seed,
                "blinding_enabled": config.blinding_enabled,
                "include_human_responses": config.include_human_responses,
                "status": config.status,
                "created_at": config.created_at.isoformat() if config.created_at else None,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None,
            }
            human_evaluation_configs_data.append(config_data)

    # Get human evaluation sessions for this project
    human_evaluation_sessions_data = []
    human_sessions = (
        db.query(HumanEvaluationSession)
        .filter(HumanEvaluationSession.project_id == project_id)
        .all()
    )
    for session in human_sessions:
        session_data = {
            "id": session.id,
            "project_id": session.project_id,
            "evaluator_id": session.evaluator_id,
            "session_type": session.session_type,
            "items_evaluated": session.items_evaluated,
            "total_items": session.total_items,
            "status": session.status,
            "session_config": session.session_config,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }
        human_evaluation_sessions_data.append(session_data)

    # Get human evaluation results for project tasks
    human_evaluation_results_data = []
    if human_evaluation_configs_data:
        config_ids = [c["id"] for c in human_evaluation_configs_data]
        human_results = (
            db.query(HumanEvaluationResult)
            .filter(HumanEvaluationResult.config_id.in_(config_ids))
            .all()
        )
        for result in human_results:
            result_data = {
                "id": result.id,
                "config_id": result.config_id,
                "task_id": result.task_id,
                "response_id": result.response_id,
                "evaluator_id": result.evaluator_id,
                "correctness_score": result.correctness_score,
                "completeness_score": result.completeness_score,
                "style_score": result.style_score,
                "usability_score": result.usability_score,
                "comments": result.comments,
                "evaluation_time_seconds": result.evaluation_time_seconds,
                "created_at": result.created_at.isoformat() if result.created_at else None,
            }
            human_evaluation_results_data.append(result_data)

    # Get preference rankings for project tasks
    preference_rankings_data = []
    if human_evaluation_sessions_data:
        session_ids = [s["id"] for s in human_evaluation_sessions_data]
        rankings = (
            db.query(PreferenceRanking).filter(PreferenceRanking.session_id.in_(session_ids)).all()
        )
        for ranking in rankings:
            ranking_data = {
                "id": ranking.id,
                "session_id": ranking.session_id,
                "task_id": ranking.task_id,
                "response_a_id": ranking.response_a_id,
                "response_b_id": ranking.response_b_id,
                "winner": ranking.winner,
                "confidence": ranking.confidence,
                "reasoning": ranking.reasoning,
                "time_spent_seconds": ranking.time_spent_seconds,
                "created_at": ranking.created_at.isoformat() if ranking.created_at else None,
            }
            preference_rankings_data.append(ranking_data)

    # Get likert scale evaluations for project tasks
    likert_scale_evaluations_data = []
    if human_evaluation_sessions_data:
        session_ids = [s["id"] for s in human_evaluation_sessions_data]
        likert_evals = (
            db.query(LikertScaleEvaluation)
            .filter(LikertScaleEvaluation.session_id.in_(session_ids))
            .all()
        )
        for likert in likert_evals:
            likert_data = {
                "id": likert.id,
                "session_id": likert.session_id,
                "task_id": likert.task_id,
                "response_id": likert.response_id,
                "dimension": likert.dimension,
                "rating": likert.rating,
                "comment": likert.comment,
                "time_spent_seconds": likert.time_spent_seconds,
                "created_at": likert.created_at.isoformat() if likert.created_at else None,
            }
            likert_scale_evaluations_data.append(likert_data)

    # Get project members
    project_members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    project_members_data = []
    for member in project_members:
        member_data = {
            "id": member.id,
            "project_id": member.project_id,
            "user_id": member.user_id,
            "role": member.role,
            "is_active": member.is_active,
            "created_at": member.created_at.isoformat() if member.created_at else None,
            "updated_at": member.updated_at.isoformat() if member.updated_at else None,
        }
        project_members_data.append(member_data)

    # Get task assignments (join through Task table since TaskAssignment doesn't have project_id directly)
    task_assignments = (
        db.query(TaskAssignment).join(Task).filter(Task.project_id == project_id).all()
    )
    task_assignments_data = []
    for assignment in task_assignments:
        assignment_data = {
            "id": assignment.id,
            "task_id": assignment.task_id,
            "user_id": assignment.user_id,
            "assigned_by": assignment.assigned_by,
            "status": assignment.status,
            "priority": assignment.priority,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            "notes": assignment.notes,
            "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
            "started_at": assignment.started_at.isoformat() if assignment.started_at else None,
            "completed_at": assignment.completed_at.isoformat()
            if assignment.completed_at
            else None,
        }
        task_assignments_data.append(assignment_data)

    # Prompts are now handled by generation_structure field in projects table (see issue #759)
    # The prompts table and Prompt model have been removed

    # Get post-annotation questionnaire responses (Issue #1208)
    post_annotation_responses = (
        db.query(PostAnnotationResponse)
        .filter(PostAnnotationResponse.project_id == project_id)
        .all()
    )
    post_annotation_responses_data = []
    for response in post_annotation_responses:
        response_data = {
            "id": response.id,
            "annotation_id": response.annotation_id,
            "task_id": response.task_id,
            "project_id": response.project_id,
            "user_id": response.user_id,
            "result": response.result,
            "created_at": response.created_at.isoformat() if response.created_at else None,
        }
        post_annotation_responses_data.append(response_data)

    # Get user reference data for import mapping
    user_ids = set()
    if project.created_by:
        user_ids.add(project.created_by)
    for task in tasks:
        if task.created_by:
            user_ids.add(task.created_by)
        if task.updated_by:
            user_ids.add(task.updated_by)
    for annotation in annotations:
        if annotation.completed_by:
            user_ids.add(annotation.completed_by)
    for member in project_members:
        if member.user_id:
            user_ids.add(member.user_id)
    for assignment in task_assignments:
        if assignment.user_id:
            user_ids.add(assignment.user_id)
        if assignment.assigned_by:
            user_ids.add(assignment.assigned_by)
    for par in post_annotation_responses:
        if par.user_id:
            user_ids.add(par.user_id)

    users_data = []
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        for user in users:
            user_data = {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "name": user.name,
                "is_active": user.is_active,
                "is_superadmin": user.is_superadmin,
            }
            users_data.append(user_data)

    # Calculate statistics
    statistics = {
        "total_tasks": len(tasks_data),
        "total_annotations": len(annotations_data),
        "total_generations": len(generations_data),
        # Note: total_predictions removed - predictions table deprecated
        "total_evaluations": len(evaluations_data),
        "total_evaluation_metrics": len(evaluation_metrics_data),
        "total_task_evaluations": len(task_evaluations_data),
        "total_human_evaluation_configs": len(human_evaluation_configs_data),
        "total_human_evaluation_sessions": len(human_evaluation_sessions_data),
        "total_human_evaluation_results": len(human_evaluation_results_data),
        "total_preference_rankings": len(preference_rankings_data),
        "total_likert_scale_evaluations": len(likert_scale_evaluations_data),
        "total_members": len(project_members_data),
        "total_assignments": len(task_assignments_data),
        "total_post_annotation_responses": len(post_annotation_responses_data),
    }

    return {
        "format_version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "exported_by": project.created_by,
        # Core project data
        "project": project_data,
        "tasks": tasks_data,
        "annotations": annotations_data,
        "generations": generations_data,
        "predictions": predictions_data,
        # Configuration data
        # Note: prompts removed - now handled by generation_structure (issue #759)
        "response_generations": response_generations_data,
        # User and assignment data
        "project_members": project_members_data,
        "task_assignments": task_assignments_data,
        "users": users_data,
        # Evaluation data
        "evaluations": evaluations_data,
        "evaluation_metrics": evaluation_metrics_data,
        "task_evaluations": task_evaluations_data,
        "human_evaluation_configs": human_evaluation_configs_data,
        "human_evaluation_sessions": human_evaluation_sessions_data,
        "human_evaluation_results": human_evaluation_results_data,
        "preference_rankings": preference_rankings_data,
        "likert_scale_evaluations": likert_scale_evaluations_data,
        # Post-annotation questionnaire data (Issue #1208)
        "post_annotation_responses": post_annotation_responses_data,
        # Statistics
        "statistics": statistics,
    }
