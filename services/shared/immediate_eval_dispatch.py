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
``None`` when the project has no eligible immediate config or the annotation
has no answer any config can grade. Strictly additive —
only INSERTs an ``EvaluationRun`` and dispatches a Celery task.

Blocked gradings: the extended edition can refuse a grading before dispatch
(optional hook ``benger_extended.workers.get_grading_block_fn``, e.g. when no
one may pay for it). Such a grading gets ONE failed immediate run carrying
``eval_metadata.billing_block`` (reason, ``checked_at``) and no Celery task;
later attempts refresh that run instead of adding rows. Once the hook stops
blocking, the next attempt dispatches normally and stamps
``billing_block.superseded_by`` on the old run. The hourly sweep therefore
costs one lookup per blocked annotation until the block is lifted.

Held sheet judges: a Bewertungsbogen judge (``llm_judge_rubric``) on a task
without a usable sheet (``task_rubric_resolution``) is not dispatched, so it
writes no error row. The other configs of the grading still run (the held
ones are listed in ``eval_metadata.held_configs``). When nothing else is left
to grade, the grading is recorded as blocked with reason ``rubric_missing``
(same mechanism as a billing block, so the hourly sweep retries it without
the attempt cap), and :func:`dispatch_waiting_gradings` grades the waiting
answers of a task as soon as its sheet is usable.

This module lives in ``/shared`` so the api (hook, endpoint, CLI) and the
workers (auto-submit, sweep) import the same logic. It avoids importing any
api-only module at top level — the Celery dispatch is resolved lazily so it
works in both the api and worker processes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import celery_queues
from metric_filters import is_immediate_eligible
from models import EvaluationRun, TaskEvaluation
from project_models import Annotation, Project, Task
from task_rubric_resolution import RUBRIC_MISSING, split_held_rubric_judges

logger = logging.getLogger(__name__)

BILLING_BLOCK_KEY = "billing_block"

#: ``eval_metadata`` key listing the sheet judges a dispatched run left out.
HELD_CONFIGS_KEY = "held_configs"

#: Trigger stamped on runs that :func:`dispatch_waiting_gradings` starts.
RUBRIC_READY_TRIGGER = "rubric_ready"


def _select_immediate_configs(db, user_id, configs, project=None):
    """Extension hook: let the extended edition narrow the dispatched configs
    for one grading (e.g. pick the billing-tier judge from a free/paid pair).

    ``project`` gives the selector the billing context (e.g. an org that
    covers the grading picks the paid judge regardless of the solver's tier).

    Community edition has no such hook → returns ``configs`` unchanged. This
    makes tier-selection uniform across every server-side trigger that funnels
    through ``ensure_immediate_evaluation`` (submit hook, timer auto-submit,
    recovery sweep), so the expected-config list written below already reflects
    the single config that will run. Best-effort — never breaks dispatch.
    """
    if not configs or user_id is None:
        return configs
    import extension_registry

    # A package refused at the handshake runs no code (a direct import would
    # still find it). Billing selection is ALWAYS-gated: the runtime switch
    # does not change which judge a grading uses.
    if extension_registry.is_refused("benger_extended"):
        return configs
    try:
        from benger_extended.billing.policy import select_tier_config

        return select_tier_config(db, user_id, configs, project=project)
    except ImportError:
        return configs
    except Exception:
        logger.exception("immediate-eval config selector failed; keeping all configs")
        return configs


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
    """True if a TaskEvaluation.metrics blob carries a non-error grading for
    any eligible metric.

    A written feedback-only result (``details.feedback_only``, core 2.41)
    counts even though its ``value`` stays null until a teacher releases it:
    the grading is done and only waits for its release. ``evaluation_planning``
    applies the same rule to "missing only" re-runs. Without it the hourly
    sweep took every held-back draft for ungraded and graded it again each
    hour until its attempt cap.
    """
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
            details = v.get("details")
            if isinstance(details, dict) and details.get("feedback_only") is True:
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


def _has_answer(value) -> bool:
    """True if a parsed annotation value is something a metric can grade.

    Whitespace-only text counts as empty. Numbers count (a rating of 0 is an
    answer), booleans and empty containers do not.
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return True
    return bool(value)


def resolve_human_prediction(config, annotation_results: dict):
    """The annotation value ``config`` grades, or None if there is none.

    ``annotation_results`` is the ``{from_name: value}`` map from
    :func:`parse_annotation_results`. ``prediction_fields`` entries may be a
    bare field name, ``human:<field>``, ``__all_human__`` (every non-empty
    field, joined), or a model-side selector (``model:<field>``,
    ``__all_model__``). Immediate evaluation grades one human submission and
    has no model generations, so model-side selectors never resolve.

    Single source for the worker (which skips a config without a value) and
    the dispatcher (which does not dispatch when no config has one).
    """
    return resolve_human_prediction_field(config, annotation_results)[1]


def resolve_human_prediction_field(config, annotation_results: dict):
    """``(selector, value)`` of the answer ``config`` grades, else
    ``(None, None)``.

    ``selector`` is the ``prediction_fields`` entry that resolved, as the
    config spells it: the grading row records it as its field, so a config
    that lists a model-side selector first (``["__all_model__",
    "human:loesung"]``) labels the row with the answer field it graded.
    """
    results = annotation_results or {}
    for pf in (config or {}).get("prediction_fields") or []:
        if not isinstance(pf, str):
            continue
        if pf.startswith("model:") or pf == "__all_model__":
            continue
        if pf == "__all_human__":
            parts = [f"{k}: {v}" for k, v in results.items() if _has_answer(v)]
            value = "\n\n".join(parts) if parts else None
        else:
            key = pf.split(":", 1)[1] if pf.startswith("human:") else pf
            value = results.get(key)
        if _has_answer(value):
            return pf, value
    return None, None


def gradable_configs(configs, annotation_results: dict) -> list:
    """The configs that find an answer to grade in ``annotation_results``.

    Empty when the submission is empty, lacks the graded field, or every
    config reads model generations only. Dispatching then produces a run
    with no grade, so callers treat that as "nothing to grade".
    """
    return [
        c for c in configs or []
        if resolve_human_prediction(c, annotation_results) is not None
    ]


def resolve_org(db, project, user_id) -> Optional[str]:
    """Org to attribute the run to. Thin delegate kept for its importers —
    ``org_resolution.resolve_dispatch_org_for_project`` is the single source
    of truth (active membership wins; superadmins get the first-org fallback;
    ordinary non-members resolve to ``None`` → personal key)."""
    from org_resolution import resolve_dispatch_org_for_project

    return resolve_dispatch_org_for_project(db, user_id, project)


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


def _recent_blocked_annotations(db, project_id, recent) -> list:
    """The ``recent`` annotations whose newest immediate run is an open
    billing block (the grading was already attempted and refused)."""
    if not recent:
        return []
    wanted = {str(a.id) for a in recent}
    submitters = {str(a.completed_by) for a in recent if a.completed_by}
    if not submitters:
        return []
    runs = (
        db.query(EvaluationRun.eval_metadata)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.created_by.in_(submitters),
        )
        .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        .all()
    )
    seen: set = set()
    blocked: set = set()
    for (meta,) in runs:
        if not isinstance(meta, dict):
            continue
        aid = str(meta.get("annotation_id") or "")
        if aid not in wanted or aid in seen:
            continue
        seen.add(aid)  # only the newest run of the annotation decides
        if _open_block(meta) is not None:
            blocked.add(aid)
    return [a for a in recent if str(a.id) in blocked]


def scan_ungraded(db, project, *, cutoff=None):
    """Find annotations on ``project`` that have no eligible immediate grade.

    Returns ``(candidates, partials)`` where:
      * ``candidate``  = ``(annotation, task)`` with ZERO eligible real-score rows,
      * ``partial``    = ``(annotation, present_metrics, missing_metrics)``,
        reported only (re-dispatching risks duplicating the present metric).

    ``cutoff`` (a tz-aware datetime) excludes submits newer than it so an
    in-flight client eval isn't raced. A newer submit whose latest immediate
    run is an open billing block is kept: its grading already ran once and
    was refused, so there is nothing to race, and the sweep dispatches it as
    soon as the block is lifted. Shared by the recovery CLI and the hourly
    sweep so both agree on what "ungraded" means.

    An annotation with nothing to grade (see :func:`gradable_configs`) is
    not a candidate. A run for it would finish without a grade, so the
    sweep would dispatch it again every hour, forever.
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
        anns = q.filter(Annotation.created_at < cutoff).all()
        recent = q.filter(Annotation.created_at >= cutoff).all()
        anns.extend(_recent_blocked_annotations(db, project.id, recent))
    else:
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
            if not gradable_configs(cfgs, parse_annotation_results(a)):
                continue
            task = tasks_by_id.get(a.task_id)
            if task is not None:
                candidates.append((a, task))
        elif present < elig:
            partials.append((a, present, elig - present))
    return candidates, partials


# A run only blocks a new attempt while it is genuinely still in flight.
# A run that FINISHED (completed/cancelled/paused) without producing a real
# grade must not block: callers check ``_graded_run_id`` first, so reaching
# here with a finished run means the attempt ended without a usable grade —
# the errored-grading case. Treating those as in-flight (status != 'failed')
# pinned the annotation forever: the retrigger endpoint answered "already in
# progress" and the hourly sweep skipped it, so a transient judge outage was
# unrecoverable without hand-editing the row.
IN_FLIGHT_RUN_STATUSES = ("pending", "queued", "running")

# How often the hourly sweep retries one annotation whose sweep runs all
# ended without a grade (a transient judge outage, a bad key). After that
# the sweep leaves it alone; a manual retrigger still works because it does
# not go through this cap. Billing-blocked runs do not count: a blocked
# grading keeps one run and is retried until the block is lifted.
SWEEP_TRIGGER = "sweep_missing_immediate_evals"
SWEEP_MAX_ATTEMPTS = 6


def sweep_attempt_counts(db, project_id) -> dict:
    """``{annotation_id: n}``: finished sweep runs per annotation of a project.

    Callers only look up annotations without a grade, so every counted run
    is a sweep attempt that produced none.
    """
    rows = (
        db.query(EvaluationRun.eval_metadata)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.status.notin_(IN_FLIGHT_RUN_STATUSES),
            EvaluationRun.eval_metadata["trigger"].as_string() == SWEEP_TRIGGER,
        )
        .all()
    )
    counts: dict = {}
    for (meta,) in rows:
        if not isinstance(meta, dict) or meta.get(BILLING_BLOCK_KEY):
            continue
        aid = str(meta.get("annotation_id") or "")
        if aid:
            counts[aid] = counts.get(aid, 0) + 1
    return counts


def _existing_immediate_run(db, project_id, annotation):
    """An immediate EvaluationRun still IN FLIGHT for this annotation, else
    None. ``eval_metadata`` is a generic JSON column, so we filter in
    Python over the submitter's own immediate runs (a handful — keyed by
    ``created_by`` to keep the scan cheap during a large exam)."""
    runs = (
        db.query(EvaluationRun)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.created_by == str(annotation.completed_by),
            EvaluationRun.status.in_(IN_FLIGHT_RUN_STATUSES),
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
# Blocked gradings (billing policy refused the grading before dispatch).
# --------------------------------------------------------------------------- #
def normalize_billing_block(block) -> Optional[dict]:
    """A billing block as a dict with at least ``reason``, or None.

    Accepts what a policy may return: None/empty (not blocked), a dict
    (``code``, ``reason``, providers, ...), or a bare reason string.
    """
    if not block:
        return None
    if isinstance(block, dict):
        out = dict(block)
        out["reason"] = str(out.get("reason") or out.get("code") or "blocked")
        return out
    return {"reason": str(block)}


def _grading_block(db, project, user_id, configs) -> Optional[dict]:
    """Extension hook: why this grading must not be dispatched, else None.

    Community edition (or no package with the hook): None. Every package's
    hook is asked in BENGER_EXTENSIONS order and the first block wins. A
    failing hook is logged and treated as "not blocked"; the worker's
    dispatch policy still gets the final say. Each hook runs inside a
    savepoint so a failed query cannot poison the caller's session.
    """
    import extension_registry

    for package, getter in extension_registry.worker_attrs("get_grading_block_fn"):
        try:
            block_fn = getter()
            if block_fn is None:
                continue
            with db.begin_nested():
                block = block_fn(db, project=project, user_id=user_id, configs=configs)
        except Exception:
            logger.exception(
                "grading block hook of %s failed for project %s; dispatching normally",
                package,
                getattr(project, "id", None),
            )
            continue
        block = normalize_billing_block(block)
        if block is not None:
            return block
    return None


def _open_block(meta) -> Optional[dict]:
    """The run's billing block if it is still the current one."""
    if not isinstance(meta, dict):
        return None
    block = meta.get(BILLING_BLOCK_KEY)
    if isinstance(block, dict) and not block.get("superseded_by"):
        return block
    return None


def latest_blocked_run(db, project_id, annotation):
    """The current blocked immediate run of ``annotation``, else None.

    Same scan pattern as ``_existing_immediate_run``: the submitter's failed
    immediate runs, newest first, matched on the stamped ``annotation_id``;
    a run whose block was superseded by a later dispatch does not count.
    """
    runs = (
        db.query(EvaluationRun)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.created_by == str(annotation.completed_by),
            EvaluationRun.status == "failed",
        )
        .order_by(EvaluationRun.created_at.desc())
        .limit(50)
        .all()
    )
    aid = str(annotation.id)
    for r in runs:
        meta = r.eval_metadata or {}
        if (
            isinstance(meta, dict)
            and str(meta.get("annotation_id")) == aid
            and _open_block(meta) is not None
        ):
            return r
    return None


def _run_metadata(annotation, cfgs, trigger: str) -> dict:
    return {
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


def record_blocked_immediate_run(
    db,
    project,
    annotation,
    *,
    user_id=None,
    configs=None,
    block,
    trigger: str = "annotation_submit",
) -> str:
    """Record that ``annotation`` cannot be graded yet; return the run id.

    Refreshes the current blocked run (new reason, ``checked_at``) when one
    exists, otherwise inserts a failed immediate ``EvaluationRun`` with the
    usual metadata plus ``billing_block``. Never dispatches. Commits.

    The run always belongs to the annotation's submitter, whatever
    ``user_id`` the caller passes: ``latest_blocked_run`` finds it by that
    owner, so repeated attempts refresh one row instead of adding more.
    """
    from sqlalchemy.orm.attributes import flag_modified

    block = normalize_billing_block(block) or {"reason": "blocked"}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    message = f"billing_blocked:{block['reason']}"[:500]

    existing = latest_blocked_run(db, project.id, annotation)
    if existing is not None:
        meta = dict(existing.eval_metadata or {})
        previous = meta.get(BILLING_BLOCK_KEY) or {}
        meta[BILLING_BLOCK_KEY] = {
            **block,
            "first_blocked_at": previous.get("first_blocked_at")
            or previous.get("checked_at")
            or now_iso,
            "checked_at": now_iso,
        }
        meta["error"] = message
        existing.eval_metadata = meta
        existing.error_message = message
        flag_modified(existing, "eval_metadata")
        db.commit()
        return str(existing.id)

    cfgs = configs if configs is not None else eligible_configs(project)
    run_id = str(uuid.uuid4())
    meta = _run_metadata(annotation, cfgs, trigger)
    meta[BILLING_BLOCK_KEY] = {
        **block,
        "first_blocked_at": now_iso,
        "checked_at": now_iso,
    }
    meta["error"] = message
    db.add(
        EvaluationRun(
            id=run_id,
            project_id=str(project.id),
            model_id="immediate",
            evaluation_type_ids=[c.get("metric", "") for c in cfgs],
            status="failed",
            created_by=str(annotation.completed_by or user_id),
            eval_metadata=meta,
            metrics={},
            error_message=message,
            completed_at=now,
        )
    )
    db.commit()
    return run_id


# --------------------------------------------------------------------------- #
# Held sheet judges (no usable Bewertungsbogen yet).
# --------------------------------------------------------------------------- #
def held_configs_metadata(held) -> list:
    """``eval_metadata.held_configs``: the sheet judges a grading left out."""
    return [
        {
            "id": c.get("id", c.get("metric", "")),
            "metric": c.get("metric", ""),
            "display_name": c.get("display_name", c.get("metric", "")),
            "reason": RUBRIC_MISSING,
        }
        for c in held or []
    ]


def rubric_missing_block(task, held) -> dict:
    """The block of a grading that waits for the task's sheet."""
    return {
        "code": RUBRIC_MISSING,
        "reason": RUBRIC_MISSING,
        "task_id": str(task.id),
        "held_configs": held_configs_metadata(held),
    }


def split_held_configs(db, project, task, configs):
    """``(kept, held)`` of ``configs`` for one grading of ``task``.

    For dispatchers that build their own run (the extended ``/immediate``
    endpoint): the same rule :func:`ensure_immediate_evaluation` applies.
    """
    return split_held_rubric_judges(
        db,
        task,
        configs,
        review_required=bool(getattr(project, "rubric_review_required", False)),
    )


def _waiting_annotation_ids(db, project_id) -> set:
    """Annotations of a project whose newest immediate run is a held
    (``rubric_missing``) grading."""
    runs = (
        db.query(EvaluationRun.eval_metadata)
        .filter(
            EvaluationRun.project_id == str(project_id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.status == "failed",
            EvaluationRun.eval_metadata[BILLING_BLOCK_KEY]["reason"].as_string()
            == RUBRIC_MISSING,
        )
        .all()
    )
    out: set = set()
    for (meta,) in runs:
        if _open_block(meta) is not None:
            aid = str((meta or {}).get("annotation_id") or "")
            if aid:
                out.add(aid)
    return out


def dispatch_waiting_gradings(db, task_id, *, trigger: str = RUBRIC_READY_TRIGGER) -> dict:
    """Grade the answers of ``task_id`` that wait for its sheet.

    Call after a sheet of the task became usable (confirmed and active).
    Every waiting answer goes through :func:`ensure_immediate_evaluation_outcome`
    again, so the usual rules hold: an answer that got a grade meanwhile is
    left alone, a sheet that is still missing keeps the answer waiting, a
    billing block is recorded instead of a dispatch. Commits per answer; a
    failing answer is logged and does not stop the others. The hourly sweep
    stays the backstop. Returns counts (``waiting``, ``dispatched``,
    ``blocked``, ``other``, ``failed``).
    """
    counts = {"waiting": 0, "dispatched": 0, "blocked": 0, "other": 0, "failed": 0}
    task = db.query(Task).filter(Task.id == str(task_id)).first()
    if task is None:
        return counts
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if (
        project is None
        or getattr(project, "deleted_at", None) is not None
        or not getattr(project, "immediate_evaluation_enabled", False)
    ):
        return counts
    waiting = _waiting_annotation_ids(db, project.id)
    if not waiting:
        return counts
    annotations = (
        db.query(Annotation)
        .filter(
            Annotation.id.in_(waiting),
            Annotation.task_id == task.id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .order_by(Annotation.created_at)
        .all()
    )
    counts["waiting"] = len(annotations)
    for annotation in annotations:
        try:
            outcome = ensure_immediate_evaluation_outcome(
                db, project, task, annotation, trigger=trigger
            )
        except Exception:
            logger.exception(
                "[immediate-eval] waiting grading of annotation %s failed", annotation.id
            )
            db.rollback()
            counts["failed"] += 1
            continue
        if outcome.status == OUTCOME_DISPATCHED:
            counts["dispatched"] += 1
        elif outcome.status == OUTCOME_BLOCKED:
            counts["blocked"] += 1
        else:
            counts["other"] += 1
    logger.info("[immediate-eval] waiting gradings of task %s: %s", task.id, counts)
    return counts


DISPATCH_WAITING_TASK = "tasks.dispatch_waiting_gradings"


def queue_waiting_gradings(task_id) -> None:
    """Queue :func:`dispatch_waiting_gradings` for ``task_id`` on a worker.

    For request handlers (the confirm of a sheet), so the request does not
    wait for every answer of a large exam. Call after the commit that made
    the sheet usable.
    """
    _dispatch_task(
        DISPATCH_WAITING_TASK,
        {"task_id": str(task_id)},
        celery_queues.queue_for(DISPATCH_WAITING_TASK),
    )


# --------------------------------------------------------------------------- #
# Will anything grade this answer again?
# --------------------------------------------------------------------------- #
RETRY_HELD = "held"
RETRY_SWEEP = "retrying"
RETRY_EXHAUSTED = "exhausted"
RETRY_NONE = "none"


def grading_retry_state(db, project, annotation) -> dict:
    """Whether an answer without a grade will still be graded by itself.

    ``state``:

    - ``held``: the newest immediate run is an open block (``reason`` says
      why, e.g. ``rubric_missing``); the sweep retries it until the block is
      lifted, without the attempt cap;
    - ``retrying``: the sweep will try again (``attempts`` of
      ``max_attempts`` used);
    - ``exhausted``: the sweep stopped after ``max_attempts``; only a manual
      retrigger grades it now;
    - ``none``: nothing grades it automatically (no immediate grading on the
      project, the project is deleted, or the sweep skips the answer because
      no configured grader has anything in it to grade).

    Says nothing about an answer that already has a grade; callers ask only
    for ungraded ones.
    """
    state = {
        "state": RETRY_NONE,
        "reason": None,
        "attempts": 0,
        "max_attempts": SWEEP_MAX_ATTEMPTS,
    }
    if (
        project is None
        or getattr(project, "deleted_at", None) is not None
        or not getattr(project, "immediate_evaluation_enabled", False)
    ):
        return state
    cfgs = eligible_configs(project)
    if not cfgs or not gradable_configs(cfgs, parse_annotation_results(annotation)):
        return state
    blocked = latest_blocked_run(db, project.id, annotation)
    if blocked is not None:
        block = _open_block(blocked.eval_metadata) or {}
        state.update(state=RETRY_HELD, reason=block.get("reason"))
        return state
    attempts = (
        db.query(EvaluationRun.eval_metadata)
        .filter(
            EvaluationRun.project_id == str(project.id),
            EvaluationRun.model_id == "immediate",
            EvaluationRun.status.notin_(IN_FLIGHT_RUN_STATUSES),
            EvaluationRun.eval_metadata["trigger"].as_string() == SWEEP_TRIGGER,
            EvaluationRun.eval_metadata["annotation_id"].as_string() == str(annotation.id),
        )
        .all()
    )
    used = sum(
        1 for (meta,) in attempts if isinstance(meta, dict) and not meta.get(BILLING_BLOCK_KEY)
    )
    state["attempts"] = used
    state["state"] = RETRY_EXHAUSTED if used >= SWEEP_MAX_ATTEMPTS else RETRY_SWEEP
    return state


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
OUTCOME_NO_CONFIGS = "no_configs"
OUTCOME_GRADED = "graded"
OUTCOME_IN_FLIGHT = "in_flight"
OUTCOME_TOO_RECENT = "too_recent"
OUTCOME_BLOCKED = "blocked"
OUTCOME_DISPATCHED = "dispatched"
OUTCOME_NOTHING_TO_GRADE = "nothing_to_grade"


@dataclass(frozen=True)
class EnsureOutcome:
    """What ``ensure_immediate_evaluation`` did for one annotation."""

    run_id: Optional[str]
    status: str


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

    Returns the EvaluationRun id (existing grade's run, an in-flight run, a
    blocked run, or a newly-dispatched one), or ``None`` when there is nothing
    eligible to grade, no answer to grade, or (with ``min_age_minutes`` set)
    the submit is too recent to act on.
    """
    return ensure_immediate_evaluation_outcome(
        db,
        project,
        task,
        annotation,
        user_id=user_id,
        configs=configs,
        trigger=trigger,
        min_age_minutes=min_age_minutes,
    ).run_id


def ensure_immediate_evaluation_outcome(
    db,
    project,
    task,
    annotation,
    *,
    user_id=None,
    configs=None,
    trigger: str = "annotation_submit",
    min_age_minutes: int = 0,
) -> EnsureOutcome:
    """:func:`ensure_immediate_evaluation`, also saying which branch ran."""
    cfgs = configs if configs is not None else eligible_configs(project)
    # Narrow a free/paid judge pair to the solver's tier BEFORE the expected
    # list is stamped, so all server-side triggers agree on the one config that
    # runs (community: no-op). ``user_id`` falls back to the annotation author.
    cfgs = _select_immediate_configs(
        db, user_id or getattr(annotation, "completed_by", None), cfgs, project=project
    )
    if not cfgs:
        return EnsureOutcome(None, OUTCOME_NO_CONFIGS)
    elig = eligible_metrics(cfgs)

    # Already graded → never re-dispatch; surface the grading run.
    graded = _graded_run_id(db, annotation.id, elig)
    if graded is not None:
        return EnsureOutcome(graded, OUTCOME_GRADED)

    # A run is already in flight for this annotation → attach to it.
    existing = _existing_immediate_run(db, project.id, annotation)
    if existing is not None:
        return EnsureOutcome(str(existing.id), OUTCOME_IN_FLIGHT)

    # No config finds an answer (empty submission, missing field, or only
    # model-side configs): a run would finish without a grade. Don't start
    # one. The /immediate endpoint still dispatches its own run when a
    # student asks, so the results modal shows the methods as skipped.
    annotation_results = parse_annotation_results(annotation)
    if not gradable_configs(cfgs, annotation_results):
        logger.info(
            "[immediate-eval] nothing to grade annotation=%s trigger=%s",
            annotation.id,
            trigger,
        )
        return EnsureOutcome(None, OUTCOME_NOTHING_TO_GRADE)

    # Sweep/backfill only: don't race an in-flight client eval on a fresh submit.
    if min_age_minutes:
        created = getattr(annotation, "created_at", None)
        if created is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)
            try:
                if created > cutoff:
                    return EnsureOutcome(None, OUTCOME_TOO_RECENT)
            except TypeError:
                # naive vs aware datetime — be permissive and proceed.
                pass

    user = str(user_id or annotation.completed_by)

    # A sheet judge without a usable Bewertungsbogen would only write an
    # error row. Leave it out; when nothing else is left to grade, hold the
    # whole grading until the sheet is there.
    all_cfgs = cfgs
    cfgs, held = split_held_rubric_judges(
        db,
        task,
        cfgs,
        review_required=bool(getattr(project, "rubric_review_required", False)),
    )
    if held and not gradable_configs(cfgs, annotation_results):
        run_id = record_blocked_immediate_run(
            db,
            project,
            annotation,
            user_id=user,
            configs=all_cfgs,
            block=rubric_missing_block(task, held),
            trigger=trigger,
        )
        logger.info(
            "[immediate-eval] held run=%s annotation=%s trigger=%s reason=%s",
            run_id,
            annotation.id,
            trigger,
            RUBRIC_MISSING,
        )
        return EnsureOutcome(run_id, OUTCOME_BLOCKED)

    # Billing may refuse the grading (extended edition). Keep one failed run
    # with the reason instead of dispatching a task that cannot run.
    block = _grading_block(db, project, user, cfgs)
    if block is not None:
        run_id = record_blocked_immediate_run(
            db,
            project,
            annotation,
            user_id=user,
            configs=cfgs,
            block=block,
            trigger=trigger,
        )
        logger.info(
            "[immediate-eval] blocked run=%s annotation=%s trigger=%s reason=%s",
            run_id,
            annotation.id,
            trigger,
            block.get("reason"),
        )
        return EnsureOutcome(run_id, OUTCOME_BLOCKED)

    eval_record_id = str(uuid.uuid4())
    meta = _run_metadata(annotation, cfgs, trigger)
    if held:
        meta[HELD_CONFIGS_KEY] = held_configs_metadata(held)
    prior_block = latest_blocked_run(db, project.id, annotation)
    if prior_block is not None:
        from sqlalchemy.orm.attributes import flag_modified

        prior_meta = dict(prior_block.eval_metadata or {})
        prior_meta[BILLING_BLOCK_KEY] = {
            **(prior_meta.get(BILLING_BLOCK_KEY) or {}),
            "superseded_by": eval_record_id,
        }
        prior_block.eval_metadata = prior_meta
        flag_modified(prior_block, "eval_metadata")
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

    try:
        _dispatch_task(
            "tasks.run_single_sample_evaluation",
            {
                "evaluation_record_id": eval_record_id,
                "project_id": str(project.id),
                "task_id": str(task.id),
                "annotation_id": str(annotation.id),
                "evaluation_configs": [dict(c) for c in cfgs],
                "annotation_results": annotation_results,
                "task_data": task.data or {},
                "organization_id": resolve_org(db, project, annotation.completed_by),
                "user_id": user,
            },
            # Sourced from the routing table rather than hardcoded, but still
            # passed explicitly: the last fallback below goes through
            # `celery.current_app`, which in a bare worker/script context may
            # carry no task_routes at all.
            celery_queues.queue_for("tasks.run_single_sample_evaluation"),
        )
    except Exception:
        # The run row is already committed as "running". If the dispatch itself
        # failed (broker down), leaving it "running" would make
        # `_existing_immediate_run` treat it as in-flight forever and block the
        # hourly sweep from ever retrying this annotation. Flip it to "failed"
        # so recovery picks it up, then re-raise for the caller to log.
        try:
            stuck = (
                db.query(EvaluationRun)
                .filter(EvaluationRun.id == eval_record_id)
                .first()
            )
            if stuck is not None:
                stuck.status = "failed"
                stuck.error_message = "immediate-eval dispatch failed"
                db.commit()
        except Exception:
            db.rollback()
        raise

    logger.info(
        "[immediate-eval] dispatched run=%s annotation=%s trigger=%s metrics=%s",
        eval_record_id,
        annotation.id,
        trigger,
        sorted(elig),
    )
    return EnsureOutcome(eval_record_id, OUTCOME_DISPATCHED)
