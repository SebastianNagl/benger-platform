"""Shared, idempotent server-side dispatch of immediate ("KI-Votum") evaluations.

Immediate evaluation grades a single annotation right after it is submitted.
Historically it was fired ONLY by the client — the labeling page POSTs
``/immediate`` then polls. If that POST never landed (tab closed on a
strict-timer auto-submit, a network blip, or a server-side auto-submit that
never reaches the browser at all), the annotation got no grade and nothing ever
retried it.

``ensure_immediate_evaluation`` is the single, idempotent entry point that every
server-side trigger calls so a grade is produced for *every* submit:
  * ``on_annotation_created`` hook  — manual + client-present auto-submit,
  * ``auto_submit_expired_timer`` worker — absent-student timer expiry,
  * the ``/immediate`` endpoint — get-or-create; the present student polls it,
  * the hourly ``sweep_missing_immediate_evals`` beat task — backstop,
  * the ``recover_missing_immediate_evals`` CLI — one-off backfill.

Exactly-once per annotation: a dispatch is skipped when the annotation already
carries a real eligible-metric score OR a non-failed immediate ``EvaluationRun``
already references it (matched via the ``annotation_id`` stamped into
``eval_metadata``). Returns the ``EvaluationRun`` id (existing or new), or
``None`` when the project has no eligible immediate config. Strictly additive —
only INSERTs an ``EvaluationRun`` and dispatches a Celery task.

This module lives in ``/shared`` so the api (hook, endpoint, CLI) and the
workers (auto-submit, sweep) import the same logic. It avoids importing any
api-only module at top level — the Celery dispatch is resolved lazily so it
works in both the api and worker processes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from metric_filters import is_immediate_eligible
from models import EvaluationRun, OrganizationMembership, TaskEvaluation
from project_models import Annotation, Task

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Eligibility + annotation-shape helpers (lifted from the recovery CLI so the
# script and the live path share one definition).
# --------------------------------------------------------------------------- #
def eligible_configs(project) -> list:
    """Enabled, immediate-eligible evaluation configs for a project.

    Mirrors the ``/immediate`` endpoint's eligibility filter. Does NOT expand
    the ``selected_methods`` shorthand (that derivation lives in an api-only
    module); callers that need it — currently only the endpoint — compute their
    own config list and pass it via ``configs=``.
    """
    cfg = project.evaluation_config or {}
    configs = cfg.get("evaluation_configs") or cfg.get("multi_field_evaluations") or []
    return [
        c
        for c in configs
        if c.get("enabled", True) and is_immediate_eligible(c.get("metric", ""))
    ]


def eligible_metrics(configs) -> set:
    return {c.get("metric", "") for c in configs}


def row_has_real_score_for(metrics, elig_metrics: set) -> bool:
    """True if a TaskEvaluation.metrics blob carries a non-error score for any
    eligible metric."""
    if not isinstance(metrics, dict):
        return False
    for m in elig_metrics:
        if m not in metrics:
            continue
        v = metrics[m]
        if isinstance(v, dict):
            if v.get("error"):
                continue
            if v.get("value") is not None:
                return True
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
    return False


def parse_annotation_results(annotation) -> dict:
    """annotation.result (Label-Studio regions) -> {from_name: value}. Identical
    shape handling to the ``/immediate`` endpoint."""
    out: dict = {}
    res = annotation.result
    if not (res and isinstance(res, list)):
        return out
    for region in res:
        if not isinstance(region, dict):
            continue
        from_name = region.get("from_name")
        if not from_name:
            continue
        value = region.get("value", {})
        region_type = region.get("type", "")
        if isinstance(value, str):
            out[from_name] = value
            continue
        if isinstance(value, dict) and "markdown" in value:
            out[from_name] = value["markdown"]
            continue
        if region_type == "textarea":
            texts = value.get("text", [])
            out[from_name] = "\n".join(texts) if isinstance(texts, list) else str(texts)
        elif region_type == "choices":
            choices = value.get("choices", [])
            out[from_name] = choices[0] if len(choices) == 1 else choices
        elif region_type == "rating":
            out[from_name] = value.get("rating")
        elif "text" in value:
            texts = value["text"]
            out[from_name] = "\n".join(texts) if isinstance(texts, list) else str(texts)
        else:
            for v in value.values():
                if v:
                    out[from_name] = v if isinstance(v, str) else str(v)
                    break
    return out


def resolve_org(db, project, user_id) -> Optional[str]:
    """Org to attribute the run to — the submitter's membership in one of the
    project's orgs, else the project's first org. Mirrors
    ``resolve_user_org_for_project`` without importing the api router."""
    if not project.organizations:
        return None
    org_ids = {str(o.id) for o in project.organizations}
    m = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(org_ids),
        )
        .first()
    )
    if m:
        return str(m.organization_id)
    return str(project.organizations[0].id)


# --------------------------------------------------------------------------- #
# Idempotency lookups.
# --------------------------------------------------------------------------- #
def _graded_run_id(db, annotation_id, elig_metrics: set) -> Optional[str]:
    """If the annotation already has a real eligible-metric grade, return the
    EvaluationRun id that produced it (so callers can surface the existing
    result), else None."""
    rows = (
        db.query(TaskEvaluation.evaluation_id, TaskEvaluation.metrics)
        .filter(TaskEvaluation.annotation_id == annotation_id)
        .all()
    )
    for run_id, m in rows:
        if row_has_real_score_for(m, elig_metrics):
            return str(run_id) if run_id else None
    return None


def scan_ungraded(db, project, *, cutoff=None):
    """Find annotations on ``project`` that have no eligible immediate grade.

    Returns ``(candidates, partials)`` where:
      * ``candidate``  = ``(annotation, task)`` with ZERO eligible real-score rows,
      * ``partial``    = ``(annotation, present_metrics, missing_metrics)``,
        reported only (re-dispatching risks duplicating the present metric).

    ``cutoff`` (a tz-aware datetime) excludes submits newer than it so an
    in-flight client eval isn't raced. Shared by the recovery CLI and the
    hourly sweep so both agree on what "ungraded" means.
    """
    cfgs = eligible_configs(project)
    if not cfgs:
        return [], []
    elig = eligible_metrics(cfgs)

    q = db.query(Annotation).filter(
        Annotation.project_id == project.id,
        Annotation.was_cancelled == False,  # noqa: E712
        Annotation.result.isnot(None),
    )
    if cutoff is not None:
        q = q.filter(Annotation.created_at < cutoff)
    anns = q.all()
    if not anns:
        return [], []

    tasks_by_id = {
        t.id: t
        for t in db.query(Task).filter(Task.id.in_({a.task_id for a in anns})).all()
    }
    candidates, partials = [], []
    for a in anns:
        rows = (
            db.query(TaskEvaluation.metrics)
            .filter(TaskEvaluation.annotation_id == a.id)
            .all()
        )
        present = set()
        for (m,) in rows:
            if row_has_real_score_for(m, elig):
                if isinstance(m, dict):
                    present |= {k for k in m.keys() if k in elig}
        if not present:
            task = tasks_by_id.get(a.task_id)
            if task is not None:
                candidates.append((a, task))
        elif present < elig:
            partials.append((a, present, elig - present))
    return candidates, partials


def _existing_immediate_run(db, project_id, annotation):
    """A non-failed immediate EvaluationRun already created for this annotation,
    else None. ``eval_metadata`` is a generic JSON column, so we filter in
    Python over the submitter's own immediate runs (a handful — keyed by
    ``created_by`` to keep the scan cheap during a large exam)."""
    runs = (
        db.query(EvaluationRun)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.created_by == str(annotation.completed_by),
            EvaluationRun.status != "failed",
        )
        .order_by(EvaluationRun.created_at.desc())
        .limit(50)
        .all()
    )
    aid = str(annotation.id)
    for r in runs:
        meta = r.eval_metadata or {}
        if isinstance(meta, dict) and str(meta.get("annotation_id")) == aid:
            return r
    return None


# --------------------------------------------------------------------------- #
# Portable Celery dispatch (api: send_task_safe; worker: worker_celery.app).
# --------------------------------------------------------------------------- #
def _dispatch_task(task_name: str, kwargs: dict, queue: str):
    try:
        from celery_client import send_task_safe  # api process

        return send_task_safe(task_name, kwargs=kwargs, queue=queue)
    except Exception:
        pass
    try:
        from worker_celery import app as _app  # worker process

        return _app.send_task(task_name, kwargs=kwargs, queue=queue)
    except Exception:
        from celery import current_app

        return current_app.send_task(task_name, kwargs=kwargs, queue=queue)


# --------------------------------------------------------------------------- #
# The single entry point.
# --------------------------------------------------------------------------- #
def ensure_immediate_evaluation(
    db,
    project,
    task,
    annotation,
    *,
    user_id=None,
    configs=None,
    trigger: str = "annotation_submit",
    min_age_minutes: int = 0,
) -> Optional[str]:
    """Idempotently ensure an immediate evaluation exists for ``annotation``.

    Returns the EvaluationRun id (existing grade's run, an in-flight run, or a
    newly-dispatched one), or ``None`` when there is nothing eligible to grade
    (or, with ``min_age_minutes`` set, when the submit is too recent to act on).
    """
    cfgs = configs if configs is not None else eligible_configs(project)
    if not cfgs:
        return None
    elig = eligible_metrics(cfgs)

    # Already graded → never re-dispatch; surface the grading run.
    graded = _graded_run_id(db, annotation.id, elig)
    if graded is not None:
        return graded

    # A run is already in flight for this annotation → attach to it.
    existing = _existing_immediate_run(db, project.id, annotation)
    if existing is not None:
        return str(existing.id)

    # Sweep/backfill only: don't race an in-flight client eval on a fresh submit.
    if min_age_minutes:
        created = getattr(annotation, "created_at", None)
        if created is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)
            try:
                if created > cutoff:
                    return None
            except TypeError:
                # naive vs aware datetime — be permissive and proceed.
                pass

    user = str(user_id or annotation.completed_by)
    eval_record_id = str(uuid.uuid4())
    meta = {
        "evaluation_type": "immediate",
        "trigger": trigger,
        # annotation_id makes get-or-create race-free across hook/endpoint/worker.
        "annotation_id": str(annotation.id),
        "expected_config_count": len(cfgs),
        "configs": [
            {
                "id": c.get("id", c.get("metric", "")),
                "metric": c.get("metric", ""),
                "display_name": c.get("display_name", c.get("metric", "")),
            }
            for c in cfgs
        ],
    }
    db.add(
        EvaluationRun(
            id=eval_record_id,
            project_id=str(project.id),
            model_id="immediate",
            evaluation_type_ids=[c.get("metric", "") for c in cfgs],
            status="running",
            created_by=user,
            eval_metadata=meta,
            metrics={},
        )
    )
    db.commit()

    _dispatch_task(
        "tasks.run_single_sample_evaluation",
        {
            "evaluation_record_id": eval_record_id,
            "project_id": str(project.id),
            "task_id": str(task.id),
            "annotation_id": str(annotation.id),
            "evaluation_configs": [dict(c) for c in cfgs],
            "annotation_results": parse_annotation_results(annotation),
            "task_data": task.data or {},
            "organization_id": resolve_org(db, project, annotation.completed_by),
            "user_id": user,
        },
        "celery",
    )
    logger.info(
        "[immediate-eval] dispatched run=%s annotation=%s trigger=%s metrics=%s",
        eval_record_id,
        annotation.id,
        trigger,
        sorted(elig),
    )
    return eval_record_id
