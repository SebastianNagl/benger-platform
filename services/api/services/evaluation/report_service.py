"""
Report service for progressive report building and management

This service handles:
- Auto-creation of report drafts when projects are created
- Progressive population of report sections as project advances
- Report publishing validation
- Statistics aggregation for report data
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import EvaluationRun, EvaluationType, Generation, ResponseGeneration, TaskEvaluation, User
from project_models import Annotation, Project, Task
from report_models import ProjectReport


def generate_uuid() -> str:
    """Generate a UUID string"""
    return str(uuid.uuid4())


def _resolve_per_model_metrics(db: Session, evaluation_ids: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Resolve per-model averaged metrics from TaskEvaluation rows.

    Two sources are merged so reports cover both LLM-generated outputs and
    human-annotation evaluations (the latter back the human leaderboard):

    1. Generation-based rows: join TaskEvaluation.generation_id -> Generation.model_id.
    2. Annotation-based rows (generation_id IS NULL, annotation_id IS NOT NULL):
       look up the annotator via Annotation.completed_by -> User and synthesize
       model_id = "annotator:<display>" using the same pseudonym rule the
       leaderboard applies.

    Returns: {model_id: {metric_name: avg_value, ...}, ...}
    """
    if not evaluation_ids:
        return {}

    gen_rows = (
        db.query(Generation.model_id, TaskEvaluation.metrics)
        .join(TaskEvaluation, TaskEvaluation.generation_id == Generation.id)
        .filter(TaskEvaluation.evaluation_id.in_(evaluation_ids))
        .all()
    )

    ann_rows = (
        db.query(
            TaskEvaluation.metrics,
            User.username,
            User.name,
            User.pseudonym,
            User.use_pseudonym,
        )
        .join(Annotation, TaskEvaluation.annotation_id == Annotation.id)
        .join(User, Annotation.completed_by == User.id)
        .filter(
            TaskEvaluation.evaluation_id.in_(evaluation_ids),
            TaskEvaluation.generation_id.is_(None),
            TaskEvaluation.annotation_id.isnot(None),
        )
        .all()
    )

    model_values: Dict[str, Dict[str, List[float]]] = {}

    def _add(model_id: Optional[str], metrics: Optional[dict]) -> None:
        if not model_id or model_id == "unknown" or not metrics:
            return
        bucket = model_values.setdefault(model_id, {})
        for metric_name, value in metrics.items():
            # Skip audit fields that aren't user-facing scores.
            if metric_name == "raw_score" or metric_name.endswith("_response"):
                continue
            if value is not None and isinstance(value, (int, float)):
                bucket.setdefault(metric_name, []).append(float(value))

    for model_id, metrics in gen_rows:
        _add(model_id, metrics)

    for metrics, username, name, pseudonym, use_pseudonym in ann_rows:
        display = pseudonym if (use_pseudonym and pseudonym) else (name or username)
        _add(f"annotator:{display}", metrics)

    return {
        model_id: {m: sum(vs) / len(vs) for m, vs in metric_lists.items() if vs}
        for model_id, metric_lists in model_values.items()
    }


def create_initial_report_draft(db: Session, project_id: str, user_id: str) -> ProjectReport:
    """
    Create initial report draft when project is created

    This creates a report with only the project_info section populated.
    Other sections are marked as 'pending' and will be populated as the
    project progresses.

    Args:
        db: Database session
        project_id: ID of the project
        user_id: ID of the user creating the project

    Returns:
        ProjectReport: The created report draft
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Create initial content with only project_info populated
    initial_content = {
        "sections": {
            "project_info": {
                "title": f"In Project {project.title} We investigated {project.description or 'various aspects'}",
                "description": project.description or "",
                "custom_title": None,
                "custom_description": None,
                "status": "completed",
                "editable": True,
                "visible": True,
            },
            "data": {"status": "pending", "editable": True, "visible": True},
            "annotations": {"status": "pending", "editable": True, "visible": True},
            "generation": {"status": "pending", "editable": True, "visible": True},
            "evaluation": {"status": "pending", "editable": True, "visible": True},
        },
        "metadata": {
            "last_auto_update": datetime.utcnow().isoformat(),
            "sections_completed": ["project_info"],
            "can_publish": False,
        },
    }

    report = ProjectReport(
        id=generate_uuid(),
        project_id=project_id,
        content=initial_content,
        is_published=False,
        created_by=user_id,
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report


def update_report_data_section(db: Session, project_id: str) -> Optional[ProjectReport]:
    """
    Update data section when tasks are imported

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        ProjectReport: Updated report, or None if report doesn't exist
    """
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return None

    task_count = db.query(Task).filter(Task.project_id == project_id).count()

    # Preserve custom text if it exists
    existing_data = report.content.get("sections", {}).get("data", {})
    custom_text = existing_data.get("custom_text")

    report.content["sections"]["data"] = {
        "task_count": task_count,
        "custom_text": custom_text,
        "show_count": True,
        "status": "completed",
        "editable": True,
        "visible": True,
    }

    _update_metadata(report, "data")
    db.commit()
    db.refresh(report)

    return report


def update_report_annotations_section(db: Session, project_id: str) -> Optional[ProjectReport]:
    """
    Update annotations section when annotations are completed

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        ProjectReport: Updated report, or None if report doesn't exist
    """
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return None

    # Get annotation statistics
    annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .count()
    )

    # Get participants with their contribution counts
    participants_data = (
        db.query(Annotation.completed_by, User.username, func.count(Annotation.id).label('count'))
        .join(User, Annotation.completed_by == User.id)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .group_by(Annotation.completed_by, User.username)
        .all()
    )

    participants = [{"id": p[0], "name": p[1], "count": p[2]} for p in participants_data]

    # Preserve custom text if it exists
    existing_annotations = report.content.get("sections", {}).get("annotations", {})
    custom_text = existing_annotations.get("custom_text")
    acknowledgment_text = existing_annotations.get("acknowledgment_text")

    report.content["sections"]["annotations"] = {
        "annotation_count": annotation_count,
        "participants": participants,
        "custom_text": custom_text,
        "show_count": True,
        "show_participants": True,
        "acknowledgment_text": acknowledgment_text,
        "status": "completed",
        "editable": True,
        "visible": True,
    }

    _update_metadata(report, "annotations")
    db.commit()
    db.refresh(report)

    return report


def update_report_generation_section(db: Session, project_id: str) -> Optional[ProjectReport]:
    """
    Update generation section when generations are completed

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        ProjectReport: Updated report, or None if report doesn't exist
    """
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return None

    # Get unique models from generations for this project
    models = (
        db.query(Generation.model_id)
        .join(ResponseGeneration, Generation.generation_id == ResponseGeneration.id)
        .filter(ResponseGeneration.project_id == project_id)
        .distinct()
        .all()
    )

    model_ids = [m[0] for m in models]

    # Preserve custom text if it exists
    existing_generation = report.content.get("sections", {}).get("generation", {})
    custom_text = existing_generation.get("custom_text")
    show_config = existing_generation.get("show_config", False)

    report.content["sections"]["generation"] = {
        "models": model_ids,
        "custom_text": custom_text,
        "show_models": True,
        "show_config": show_config,
        "status": "completed",
        "editable": True,
        "visible": True,
    }

    _update_metadata(report, "generation")
    db.commit()
    db.refresh(report)

    return report


def update_report_evaluation_section(db: Session, project_id: str) -> Optional[ProjectReport]:
    """
    Update evaluation section when evaluations are completed
    Also enables publishing if all sections are complete

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        ProjectReport: Updated report, or None if report doesn't exist
    """
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return None

    # Get completed evaluations for this project
    evaluations = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
        .all()
    )

    # Extract methods and metrics
    methods = []
    metrics = {}

    for eval in evaluations:
        if eval.evaluation_type_ids:
            methods.extend(eval.evaluation_type_ids)

    # Resolve actual per-model metrics from TaskEvaluation -> Generation
    evaluation_ids = [e.id for e in evaluations]
    resolved = _resolve_per_model_metrics(db, evaluation_ids)
    if resolved:
        metrics = resolved
    else:
        # Fall back to EvaluationRun.model_id for direct evaluations
        for eval in evaluations:
            if eval.metrics and eval.model_id != "unknown":
                if eval.model_id not in metrics:
                    metrics[eval.model_id] = {}
                metrics[eval.model_id].update(eval.metrics)

    methods = list(set(methods))  # Remove duplicates

    # Preserve custom text if it exists
    existing_evaluation = report.content.get("sections", {}).get("evaluation", {})
    custom_interpretation = existing_evaluation.get("custom_interpretation")
    conclusions = existing_evaluation.get("conclusions")
    charts_config = existing_evaluation.get("charts_config", {})

    report.content["sections"]["evaluation"] = {
        "methods": methods,
        "metrics": metrics,
        "charts_config": charts_config,
        "custom_interpretation": custom_interpretation,
        "conclusions": conclusions,
        "status": "completed",
        "editable": True,
        "visible": True,
    }

    _update_metadata(report, "evaluation")

    # Check if all sections are complete and enable publishing
    can_publish, _ = can_publish_report(db, project_id)
    report.content["metadata"]["can_publish"] = can_publish

    db.commit()
    db.refresh(report)

    return report


def _update_metadata(report: ProjectReport, section_name: str):
    """
    Update report metadata after a section is completed

    Args:
        report: The report to update
        section_name: Name of the section that was completed
    """
    metadata = report.content.get("metadata", {})
    metadata["last_auto_update"] = datetime.utcnow().isoformat()

    sections_completed = metadata.get("sections_completed", [])
    if section_name not in sections_completed:
        sections_completed.append(section_name)
    metadata["sections_completed"] = sections_completed

    report.content["metadata"] = metadata

    # Flag the JSONB column as modified so SQLAlchemy detects the change
    flag_modified(report, "content")


def can_publish_report(db: Session, project_id: str) -> Tuple[bool, str]:
    """
    Check if a project report can be published

    A report can be published if:
    1. Report exists
    2. Project has tasks (data section)
    3. Project has generations
    4. Project has evaluations

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        Tuple of (can_publish: bool, reason: str)
    """
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return False, "Report not found"

    # Check if project has tasks
    task_count = db.query(Task).filter(Task.project_id == project_id).count()
    if task_count == 0:
        return False, "Project must have tasks"

    # Check if project has generations
    generation_count = (
        db.query(Generation)
        .join(Generation.generation)
        .filter(Generation.generation.has(project_id=project_id))
        .count()
    )

    if generation_count == 0:
        return False, "Project must have LLM generations"

    # Check if project has evaluations
    evaluation_count = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
        .count()
    )
    if evaluation_count == 0:
        return False, "Project must have completed evaluations"

    return True, "All requirements met"


def get_report_statistics(db: Session, project_id: str) -> Dict:
    """
    Aggregate project statistics for report display

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        Dict with task_count, annotation_count, participant_count, model_count
    """
    task_count = db.query(Task).filter(Task.project_id == project_id).count()

    annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .count()
    )

    participant_count = (
        db.query(Annotation.completed_by)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .distinct()
        .count()
    )

    model_count = (
        db.query(Generation.model_id)
        .join(Generation.generation)
        .filter(Generation.generation.has(project_id=project_id))
        .distinct()
        .count()
    )

    return {
        "task_count": task_count,
        "annotation_count": annotation_count,
        "participant_count": participant_count,
        "model_count": model_count,
    }


def get_report_participants(db: Session, project_id: str) -> List[Dict]:
    """
    Get unique annotators with contribution statistics

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        List of dicts with id, username, annotation_count
    """
    participants = (
        db.query(User.id, User.username, func.count(Annotation.id).label('annotation_count'))
        .join(Annotation, Annotation.completed_by == User.id)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .group_by(User.id, User.username)
        .all()
    )

    return [
        {"id": p.id, "username": p.username, "annotation_count": p.annotation_count}
        for p in participants
    ]


def get_report_models(db: Session, project_id: str) -> List[str]:
    """
    Get models used in generations for this project

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        List of model IDs
    """
    from models import ResponseGeneration

    models = (
        db.query(Generation.model_id)
        .join(ResponseGeneration, Generation.generation_id == ResponseGeneration.id)
        .filter(ResponseGeneration.project_id == project_id)
        .distinct()
        .all()
    )

    return [m[0] for m in models]


def get_evaluation_charts_data(db: Session, project_id: str) -> Dict:
    """
    Get evaluation metrics formatted for charts

    Aggregates metrics by model and evaluation method for visualization

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        Dict with structure: {
            "by_model": {
                "model_id": {"metric_name": value, ...},
                ...
            },
            "by_method": {
                "method_name": {"model_id": value, ...},
                ...
            },
            "metric_metadata": {
                "metric_name": {"higher_is_better": bool, "range": [min, max]},
                ...
            }
        }
    """
    # Get completed evaluations for this project
    evaluations = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
        .all()
    )

    by_model = {}
    by_method = {}
    metric_names_seen = set()

    # Resolve actual per-model metrics from TaskEvaluation -> Generation
    evaluation_ids = [e.id for e in evaluations]
    resolved = _resolve_per_model_metrics(db, evaluation_ids)

    if resolved:
        for model_id, model_metrics in resolved.items():
            by_model[model_id] = model_metrics
            for metric_name, value in model_metrics.items():
                metric_names_seen.add(metric_name)
                if metric_name not in by_method:
                    by_method[metric_name] = {}
                by_method[metric_name][model_id] = value
    else:
        # Fall back to EvaluationRun.model_id for direct evaluations
        for eval in evaluations:
            model_id = eval.model_id
            if model_id == "unknown":
                continue
            if model_id not in by_model:
                by_model[model_id] = {}
            if eval.metrics:
                by_model[model_id].update(eval.metrics)
                for metric_name, value in eval.metrics.items():
                    metric_names_seen.add(metric_name)
                    if metric_name not in by_method:
                        by_method[metric_name] = {}
                    by_method[metric_name][model_id] = value

    # Build metric metadata from EvaluationType table
    metric_metadata = {}
    if metric_names_seen:
        # Query EvaluationType for metadata about the metrics we found
        eval_types = db.query(EvaluationType).filter(EvaluationType.id.in_(metric_names_seen)).all()
        for et in eval_types:
            metric_metadata[et.id] = {
                "higher_is_better": et.higher_is_better,
                "range": [et.value_range.get("min", 0), et.value_range.get("max", 1)]
                if et.value_range
                else [0, 1],
                "name": et.name,
                "category": et.category,
            }

    # For metrics not in EvaluationType, provide sensible defaults based on naming conventions
    for metric_name in metric_names_seen:
        if metric_name not in metric_metadata:
            # LLM Judge metrics typically use 1-5 scale
            if metric_name.startswith("llm_judge_"):
                if metric_name == "llm_judge_pairwise":
                    metric_metadata[metric_name] = {
                        "higher_is_better": True,
                        "range": [0, 1],
                        "name": metric_name.replace("_", " ").title(),
                        "category": "llm_judge",
                    }
                else:
                    metric_metadata[metric_name] = {
                        "higher_is_better": True,
                        "range": [1, 5],
                        "name": metric_name.replace("llm_judge_", "").replace("_", " ").title(),
                        "category": "llm_judge",
                    }
            else:
                # Default to 0-1 scale for QA metrics
                metric_metadata[metric_name] = {
                    "higher_is_better": True,
                    "range": [0, 1],
                    "name": metric_name.replace("_", " ").title(),
                    "category": "qa",
                }

    return {"by_model": by_model, "by_method": by_method, "metric_metadata": metric_metadata}


def create_or_update_report_from_existing_data(
    db: Session, project_id: str, user_id: str
) -> ProjectReport:
    """
    Create or update report for existing project with all current data

    This function is used to retroactively create reports for projects that
    existed before the report system was implemented. It analyzes the project's
    current state and populates all applicable report sections.

    Args:
        db: Database session
        project_id: ID of the project
        user_id: ID of the user requesting the report (for created_by if new)

    Returns:
        ProjectReport: The created or updated report
    """
    # Check if report already exists
    existing_report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if existing_report:
        # Report exists, update all sections with current data
        report = existing_report
    else:
        # Create new report
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        report = ProjectReport(
            id=generate_uuid(),
            project_id=project_id,
            content={"sections": {}, "metadata": {}},
            is_published=False,
            created_by=user_id,
        )
        db.add(report)

    # Get current project state
    project = db.query(Project).filter(Project.id == project_id).first()
    task_count = db.query(Task).filter(Task.project_id == project_id).count()
    annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .count()
    )
    # Generation doesn't have direct project_id - join through ResponseGeneration
    generation_count = (
        db.query(Generation)
        .join(ResponseGeneration, Generation.generation_id == ResponseGeneration.id)
        .filter(ResponseGeneration.project_id == project_id)
        .count()
    )
    evaluation_count = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
        .count()
    )

    # Initialize content structure
    content = report.content or {"sections": {}, "metadata": {}}
    sections_completed = []

    # 1. Project Info Section (always present)
    content["sections"]["project_info"] = {
        "title": f"In Project {project.title} We investigated {project.description or 'various aspects'}",
        "description": project.description or "",
        "custom_title": content.get("sections", {}).get("project_info", {}).get("custom_title"),
        "custom_description": content.get("sections", {})
        .get("project_info", {})
        .get("custom_description"),
        "status": "completed",
        "editable": True,
        "visible": True,
    }
    sections_completed.append("project_info")

    # 2. Data Section
    if task_count > 0:
        content["sections"]["data"] = {
            "task_count": task_count,
            "custom_text": content.get("sections", {}).get("data", {}).get("custom_text"),
            "show_count": True,
            "status": "completed",
            "editable": True,
            "visible": True,
        }
        sections_completed.append("data")
    else:
        content["sections"]["data"] = {"status": "pending", "editable": True, "visible": True}

    # 3. Annotations Section
    if annotation_count > 0:
        participants = get_report_participants(db, project_id)
        content["sections"]["annotations"] = {
            "annotation_count": annotation_count,
            "participants": participants,
            "custom_text": content.get("sections", {}).get("annotations", {}).get("custom_text"),
            "acknowledgment_text": content.get("sections", {})
            .get("annotations", {})
            .get("acknowledgment_text"),
            "show_count": True,
            "show_participants": True,
            "status": "completed",
            "editable": True,
            "visible": True,
        }
        sections_completed.append("annotations")
    else:
        content["sections"]["annotations"] = {
            "status": "pending",
            "editable": True,
            "visible": True,
        }

    # 4. Generation Section
    if generation_count > 0:
        models = get_report_models(db, project_id)
        content["sections"]["generation"] = {
            "models": models,
            "custom_text": content.get("sections", {}).get("generation", {}).get("custom_text"),
            "show_models": True,
            "show_config": False,
            "status": "completed",
            "editable": True,
            "visible": True,
        }
        sections_completed.append("generation")
    else:
        content["sections"]["generation"] = {
            "status": "pending",
            "editable": True,
            "visible": True,
        }

    # 5. Evaluation Section
    if evaluation_count > 0:
        # Get evaluation data
        evaluations = (
            db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
            .all()
        )
        methods = []
        metrics = {}
        for eval in evaluations:
            if eval.evaluation_type_ids:
                methods.extend(eval.evaluation_type_ids)
        methods = list(set(methods))

        # Resolve actual per-model metrics from TaskEvaluation -> Generation
        evaluation_ids = [e.id for e in evaluations]
        resolved = _resolve_per_model_metrics(db, evaluation_ids)
        if resolved:
            metrics = resolved
        else:
            for eval in evaluations:
                if eval.metrics and eval.model_id != "unknown":
                    if eval.model_id not in metrics:
                        metrics[eval.model_id] = {}
                    metrics[eval.model_id].update(eval.metrics)

        content["sections"]["evaluation"] = {
            "methods": methods,
            "metrics": metrics,
            "charts_config": content.get("sections", {})
            .get("evaluation", {})
            .get("charts_config", {}),
            "custom_interpretation": content.get("sections", {})
            .get("evaluation", {})
            .get("custom_interpretation"),
            "conclusions": content.get("sections", {}).get("evaluation", {}).get("conclusions"),
            "status": "completed",
            "editable": True,
            "visible": True,
        }
        sections_completed.append("evaluation")
    else:
        content["sections"]["evaluation"] = {
            "status": "pending",
            "editable": True,
            "visible": True,
        }

    # Update metadata
    content["metadata"] = {
        "last_auto_update": datetime.utcnow().isoformat(),
        "sections_completed": sections_completed,
        "can_publish": all(s in sections_completed for s in ["data", "generation", "evaluation"]),
    }

    report.content = content
    report.updated_at = datetime.utcnow()
    # Flag the JSONB column as modified so SQLAlchemy detects the change
    flag_modified(report, "content")

    db.commit()
    db.refresh(report)

    return report
