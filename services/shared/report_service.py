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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from metric_values import coerce_metric_value
from models import (
    AnalysisRun,
    EvaluationRun,
    EvaluationType,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, Task
from report_models import ProjectReport
from report_snapshot import hidden_model_ids
from user_display import masked_name


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
       model_id = "annotator:<pseudonym>" (never a real or login name: the
       result is stored in a report that can be public).

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
            User.id,
            User.pseudonym,
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

    # Stored in the report, which can be public: the pseudonym, never the
    # real name or login name (the old fallback for people who switched
    # their pseudonym off).
    for metrics, annotator_id, pseudonym in ann_rows:
        _add(f"annotator:{masked_name(user_id=annotator_id, pseudonym=pseudonym)}", metrics)

    # The result is stored in the report's content, which a public report
    # serves whole: hidden (private custom) models stay out, as in the snapshot.
    hidden = hidden_model_ids(db, (m for m, _ in gen_rows))
    return {
        model_id: {m: sum(vs) / len(vs) for m, vs in metric_lists.items() if vs}
        for model_id, metric_lists in model_values.items()
        if model_id not in hidden
    }


def _run_level_metrics(db: Session, evaluations: List[EvaluationRun]) -> Dict[str, Dict[str, float]]:
    """Fallback per-model metrics from ``EvaluationRun.model_id`` (direct
    evaluations without task rows), hidden (private custom) models left out
    like everywhere else in a report."""
    hidden = hidden_model_ids(db, (e.model_id for e in evaluations))
    metrics: Dict[str, Dict[str, float]] = {}
    for run in evaluations:
        if run.metrics and run.model_id != "unknown" and run.model_id not in hidden:
            metrics.setdefault(run.model_id, {}).update(run.metrics)
    return metrics


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
                "title": project.title,
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


def _show_agreement_setting(annotations: Any) -> Dict[str, Any]:
    """The ``show_agreement`` key of the annotations section: kept or
    defaulted while the variant_experiments flag is on in this context
    (core 2.74), absent otherwise, as before annotator agreement existed."""
    from feature_flags.registry import VARIANT_EXPERIMENTS
    from feature_flags.scope import scoped_flag

    annotations = annotations if isinstance(annotations, dict) else {}
    if not scoped_flag(VARIANT_EXPERIMENTS):
        return {"show_agreement": annotations["show_agreement"]} if "show_agreement" in annotations else {}
    return {"show_agreement": annotations.get("show_agreement", True)}


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
    # A report is published and can be public, and its whole `content` is
    # served to anonymous visitors. People appear in it by pseudonym, never by
    # login name or real name: until 2026-09-21 this wrote `User.username`.
    participants_data = (
        db.query(Annotation.completed_by, User.pseudonym, func.count(Annotation.id).label('count'))
        .join(User, Annotation.completed_by == User.id)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .group_by(Annotation.completed_by, User.pseudonym)
        .all()
    )

    participants = [
        {"id": p[0], "name": masked_name(user_id=p[0], pseudonym=p[1]), "count": p[2]}
        for p in participants_data
    ]

    # Preserve custom text if it exists
    existing_annotations = report.content.get("sections", {}).get("annotations", {})
    custom_text = existing_annotations.get("custom_text")
    acknowledgment_text = existing_annotations.get("acknowledgment_text")

    report.content["sections"]["annotations"] = {
        "annotation_count": annotation_count,
        "participants": participants,
        "custom_text": custom_text,
        "show_count": True,
        "show_participants": existing_annotations.get("show_participants", True),
        **_show_agreement_setting(existing_annotations),
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
        metrics = _run_level_metrics(db, evaluations)

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


# Reasons ``can_publish_report`` gives; the frontend maps them to messages.
REASON_NO_REPORT = "Report not found"
REASON_NO_TASKS = "Project must have tasks"
REASON_NO_RESULTS = "Project must have annotations, generations, evaluations or analyses"
REASON_ANALYSIS_RUNS = (
    "Every run in the Analyses section must be a completed analysis run of this project "
    "that reads no other project"
)
REASON_OK = "All requirements met"


def _has_results(db: Session, project_id: str) -> bool:
    """Whether the project has anything a report can be about: annotations,
    generations, completed evaluation runs or completed analysis runs."""
    from models import AnalysisRun

    checks = (
        db.query(Annotation.id).filter(
            Annotation.project_id == project_id, Annotation.was_cancelled == False  # noqa: E712
        ),
        db.query(Generation.id)
        .join(ResponseGeneration, Generation.generation_id == ResponseGeneration.id)
        .filter(ResponseGeneration.project_id == project_id),
        db.query(EvaluationRun.id).filter(
            EvaluationRun.project_id == project_id, EvaluationRun.status == "completed"
        ),
        db.query(AnalysisRun.id).filter(
            AnalysisRun.project_id == project_id, AnalysisRun.status == "completed"
        ),
    )
    return any(db.query(q.exists()).scalar() for q in checks)


def can_publish_report(db: Session, project_id: str) -> Tuple[bool, str]:
    """
    Check if a project report can be published

    A report can be published when it exists, the project has tasks, and the
    project has at least one result of any kind: annotations, generations,
    completed evaluation runs or completed analysis runs. So an annotation
    study, a human evaluation without generations and an analysis-only
    project can publish too; the report's sections without data hide
    themselves. Every run the Analyses section names must be one the report
    can show (``report_snapshot.analysis_run_problems``).

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        Tuple of (can_publish: bool, reason: str)
    """
    from report_snapshot import analysis_run_problems, parse_analyses_section

    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        return False, REASON_NO_REPORT
    ok, reason = can_publish_project(db, project_id)
    if not ok or not _paper_rules():
        # Without variant_experiments a snapshot has no Analyses section, so
        # its runs do not count.
        return ok, reason
    content = report.content if isinstance(report.content, dict) else {}
    sections = content.get("sections") if isinstance(content.get("sections"), dict) else {}
    analyses = parse_analyses_section(sections.get("analyses"))
    if analysis_run_problems(db, project_id, [r["run_id"] for r in analyses["runs"]]):
        return False, REASON_ANALYSIS_RUNS
    return True, REASON_OK


# The rule before reports covered the whole project (variant_experiments
# off, core 2.74): tasks, LLM generations and completed evaluations.
REASON_NO_GENERATIONS = "Project must have LLM generations"
REASON_NO_EVALUATIONS = "Project must have completed evaluations"


def _can_publish_project_classic(db: Session, project_id: str) -> Tuple[bool, str]:
    task_count = db.query(Task).filter(Task.project_id == project_id).count()
    if task_count == 0:
        return False, REASON_NO_TASKS
    generation_count = (
        db.query(Generation)
        .join(Generation.generation)
        .filter(Generation.generation.has(project_id=project_id))
        .count()
    )
    if generation_count == 0:
        return False, REASON_NO_GENERATIONS
    evaluation_count = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id, EvaluationRun.status == "completed")
        .count()
    )
    if evaluation_count == 0:
        return False, REASON_NO_EVALUATIONS
    return True, REASON_OK


def _paper_rules() -> bool:
    """Whether the report as project paper (variant_experiments, core 2.74)
    applies in this request or job context."""
    from feature_flags.registry import VARIANT_EXPERIMENTS
    from feature_flags.scope import scoped_flag

    return scoped_flag(VARIANT_EXPERIMENTS)


def can_publish_project(db: Session, project_id: str) -> Tuple[bool, str]:
    """The data half of :func:`can_publish_report` (no report row needed).

    With variant_experiments off in this context the rule is the one before
    (:func:`_can_publish_project_classic`)."""
    if not _paper_rules():
        return _can_publish_project_classic(db, project_id)
    has_tasks = db.query(db.query(Task.id).filter(Task.project_id == project_id).exists()).scalar()
    if not has_tasks:
        return False, REASON_NO_TASKS
    if not _has_results(db, project_id):
        return False, REASON_NO_RESULTS
    return True, REASON_OK


def get_report_statistics(db: Session, project_id: str) -> Dict:
    """
    Aggregate project statistics for report display

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        Dict with task_count, annotation_count, participant_count,
        model_count and analysis_count (completed analysis runs)
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

    analysis_count = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project_id, AnalysisRun.status == "completed")
        .count()
    )

    return {
        "task_count": task_count,
        "annotation_count": annotation_count,
        "participant_count": participant_count,
        "model_count": model_count,
        "analysis_count": analysis_count,
    }


def get_report_statistics_batch(
    db: Session, project_ids: List[str]
) -> Dict[str, Dict[str, int]]:
    """Per-project statistics for a list of project ids in 5 grouped queries.

    Replaces the per-project fan-out used by `list_published_reports`
    (5 × N round-trips for the list view → 5 round-trips total). Same keys
    and values as :func:`get_report_statistics`.
    """
    if not project_ids:
        return {}

    zeros = {
        "task_count": 0,
        "annotation_count": 0,
        "participant_count": 0,
        "model_count": 0,
        "analysis_count": 0,
    }
    out: Dict[str, Dict[str, int]] = {pid: dict(zeros) for pid in project_ids}

    task_rows = (
        db.query(Task.project_id, func.count(Task.id))
        .filter(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
        .all()
    )
    for pid, c in task_rows:
        out[pid]["task_count"] = int(c or 0)

    ann_rows = (
        db.query(Annotation.project_id, func.count(Annotation.id))
        .filter(
            Annotation.project_id.in_(project_ids),
            Annotation.was_cancelled == False,
        )
        .group_by(Annotation.project_id)
        .all()
    )
    for pid, c in ann_rows:
        out[pid]["annotation_count"] = int(c or 0)

    participant_rows = (
        db.query(
            Annotation.project_id,
            func.count(func.distinct(Annotation.completed_by)),
        )
        .filter(
            Annotation.project_id.in_(project_ids),
            Annotation.was_cancelled == False,
        )
        .group_by(Annotation.project_id)
        .all()
    )
    for pid, c in participant_rows:
        out[pid]["participant_count"] = int(c or 0)

    model_rows = (
        db.query(
            ResponseGeneration.project_id,
            func.count(func.distinct(Generation.model_id)),
        )
        .join(Generation, Generation.generation_id == ResponseGeneration.id)
        .filter(ResponseGeneration.project_id.in_(project_ids))
        .group_by(ResponseGeneration.project_id)
        .all()
    )
    for pid, c in model_rows:
        out[pid]["model_count"] = int(c or 0)

    analysis_rows = (
        db.query(AnalysisRun.project_id, func.count(AnalysisRun.id))
        .filter(
            AnalysisRun.project_id.in_(project_ids),
            AnalysisRun.status == "completed",
        )
        .group_by(AnalysisRun.project_id)
        .all()
    )
    for pid, c in analysis_rows:
        out[pid]["analysis_count"] = int(c or 0)

    return out


def get_report_participants(db: Session, project_id: str) -> List[Dict]:
    """
    Get unique annotators with contribution statistics

    Args:
        db: Database session
        project_id: ID of the project

    Returns:
        List of dicts with id, name (the pseudonym, never the login name or
        real name: the list is stored in a report that can be public) and
        annotation_count
    """
    participants = (
        db.query(User.id, User.pseudonym, func.count(Annotation.id).label('annotation_count'))
        .join(Annotation, Annotation.completed_by == User.id)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)
        .group_by(User.id, User.pseudonym)
        .all()
    )

    return [
        {
            "id": p.id,
            "name": masked_name(user_id=p.id, pseudonym=p.pseudonym),
            "annotation_count": p.annotation_count,
        }
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

    # Stored in the report's content (public reports serve it whole): no
    # hidden (private custom) models, as in the snapshot.
    ids = [m[0] for m in models]
    hidden = hidden_model_ids(db, ids)
    return [m for m in ids if m not in hidden]


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
                    by_method.setdefault(metric_name, {})
                    # Phase 2: report's by_method matrix expects a numeric
                    # cell; coerce both legacy floats and {value, details}
                    # dicts to a number. Fall back to the raw value (may be
                    # None / non-numeric) if coercion can't extract one.
                    coerced = coerce_metric_value(value)
                    by_method[metric_name][model_id] = (
                        coerced if coerced is not None else value
                    )

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
        "title": project.title,
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
            "show_participants": content.get("sections", {})
            .get("annotations", {})
            .get("show_participants", True),
            **_show_agreement_setting(content.get("sections", {}).get("annotations", {})),
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
            metrics = _run_level_metrics(db, evaluations)

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
        "can_publish": (
            can_publish_project(db, project_id)[0]
            if _paper_rules()
            else all(s in sections_completed for s in ["data", "generation", "evaluation"])
        ),
    }

    report.content = content
    report.updated_at = datetime.utcnow()
    # Flag the JSONB column as modified so SQLAlchemy detects the change
    flag_modified(report, "content")

    # flush() (not commit()) so the caller owns the transaction boundary. When
    # this runs via the async reports.py `db.run_sync(...)` bridge, a commit()
    # here would commit the *outer async request transaction* (the bridged sync
    # session shares its connection) — the caller now issues the commit
    # explicitly. Direct sync callers (tests) read the flushed row in-session.
    db.flush()
    db.refresh(report)

    return report
