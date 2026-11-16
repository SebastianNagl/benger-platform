"""Relabel stored evaluation runs with the models their rows graded.

A finished run is labelled from its rows (``label_run_from_rows`` in
``services/shared/evaluation_run_models.py``): ``model_id`` names the one
model whose generations the rows graded, else ``"unknown"``, and
``eval_metadata["evaluated_model_ids"]`` lists the graded models. Runs that
finished before that rule carry older labels: ``"unknown"`` on runs that
graded one model, and the project's most common model on runs that graded
several models or another one. This route applies the same rule to stored
runs.

The previous ``model_id`` and ``eval_metadata`` of a changed run are kept in
``eval_metadata["relabel_history"]`` with who relabelled it and when, and the
revert mode restores them. A run that graded no generation (a run over
submitted answers), a run that has not finished, and the human-graded and
immediate runs are left alone.
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Literal

from auth_module.dependencies import require_superadmin
from database import get_db
from evaluation_run_models import (
    RELABEL_HISTORY_KEY,
    graded_model_counts_by_run,
    label_run_from_rows,
    relabel_history,
    run_model_label,
)
from fastapi import APIRouter, Depends, HTTPException
from models import EvaluationRun, User
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/evaluation-runs", tags=["admin", "evaluations"])

MAX_RELABEL_RUN_IDS = 5000

#: Run states after which no row is added any more.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _never_relabelled(model_id: str | None) -> bool:
    """Labels of runs the worker never labels from rows: the human grading
    singletons, legacy per-user human runs, immediate-eval runs and the
    synthetic annotator labels."""
    return model_id in ("human", "immediate") or (
        isinstance(model_id, str) and model_id.startswith(("human:", "annotator:"))
    )


class RelabelRequest(BaseModel):
    project_id: str | None = Field(
        None,
        description="Relabel the runs of this project (with run_ids: only those of them).",
    )
    run_ids: list[str] | None = Field(
        None,
        min_length=1,
        max_length=MAX_RELABEL_RUN_IDS,
        description="Relabel these runs (of any project, or of project_id when given).",
    )
    dry_run: bool = Field(
        True, description="Report the old and new label without writing."
    )
    revert: bool = Field(
        False,
        description="Undo the last relabel of each run instead of relabelling it.",
    )

    @field_validator("run_ids")
    @classmethod
    def _dedupe(cls, ids: list[str] | None) -> list[str] | None:
        if ids is None:
            return None
        return list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))

    @model_validator(mode="after")
    def _scope(self) -> "RelabelRequest":
        if not self.project_id and not self.run_ids:
            raise ValueError("Give project_id, run_ids or both.")
        return self


class RunLabel(BaseModel):
    model_id: str | None = None
    evaluated_model_ids: list[str] | None = None
    evaluated_model_id: str | None = None


class RelabelItem(BaseModel):
    run_id: str
    project_id: str | None = None
    status: str | None = None
    outcome: Literal[
        "changed", "unchanged", "no_graded_generations", "skipped", "not_found"
    ]
    reason: str | None = None
    #: Rows per graded model, most rows first.
    graded_rows: dict[str, int] = Field(default_factory=dict)
    before: RunLabel | None = None
    after: RunLabel | None = None


class RelabelResponse(BaseModel):
    dry_run: bool
    revert: bool
    changed: int
    unchanged: int
    no_graded_generations: int
    skipped: int
    not_found: int
    results: list[RelabelItem]


def _label(model_id, eval_metadata) -> RunLabel:
    meta = eval_metadata if isinstance(eval_metadata, dict) else {}
    ids = meta.get("evaluated_model_ids")
    return RunLabel(
        model_id=model_id,
        evaluated_model_ids=list(ids) if isinstance(ids, list) else None,
        evaluated_model_id=meta.get("evaluated_model_id"),
    )


def _relabel(
    db: Session,
    run: EvaluationRun,
    graded: list[str],
    dry_run: bool,
    user_id: str,
    now: str,
) -> RelabelItem:
    before = _label(run.model_id, run.eval_metadata)
    new_label = run_model_label(graded)
    after = RunLabel(
        model_id=new_label,
        evaluated_model_ids=list(graded),
        evaluated_model_id=new_label,
    )
    if after == before:
        return RelabelItem(
            run_id=run.id, outcome="unchanged", before=before, after=after
        )
    item = RelabelItem(run_id=run.id, outcome="changed", before=before, after=after)
    if dry_run:
        return item

    previous_meta = (
        copy.deepcopy(run.eval_metadata) if isinstance(run.eval_metadata, dict) else {}
    )
    history = relabel_history(previous_meta)
    previous_meta.pop(RELABEL_HISTORY_KEY, None)
    entry = {
        "relabeled_at": now,
        "relabeled_by": user_id,
        "superseded": {"model_id": run.model_id, "eval_metadata": previous_meta},
        "applied": after.model_dump(),
    }
    label_run_from_rows(db, run, graded=graded)
    run.eval_metadata = {**run.eval_metadata, RELABEL_HISTORY_KEY: [*history, entry]}
    flag_modified(run, "eval_metadata")
    return item


def _revert(run: EvaluationRun, dry_run: bool) -> RelabelItem:
    before = _label(run.model_id, run.eval_metadata)
    history = relabel_history(run.eval_metadata)
    if not history:
        return RelabelItem(
            run_id=run.id,
            outcome="skipped",
            reason="The run was never relabelled.",
            before=before,
        )
    last = history[-1]
    applied = RunLabel(**(last.get("applied") or {}))
    if applied != before:
        return RelabelItem(
            run_id=run.id,
            outcome="skipped",
            reason="The run's label changed after its last relabel; not reverted.",
            before=before,
            after=applied,
        )
    superseded = last.get("superseded") or {}
    restored_meta = copy.deepcopy(superseded.get("eval_metadata"))
    restored_meta = restored_meta if isinstance(restored_meta, dict) else {}
    if history[:-1]:
        restored_meta[RELABEL_HISTORY_KEY] = history[:-1]
    after = _label(superseded.get("model_id"), restored_meta)
    item = RelabelItem(run_id=run.id, outcome="changed", before=before, after=after)
    if dry_run:
        return item
    run.model_id = superseded.get("model_id")
    run.eval_metadata = restored_meta
    flag_modified(run, "eval_metadata")
    return item


@router.post("/relabel", response_model=RelabelResponse)
def relabel_evaluation_runs(
    body: RelabelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
) -> RelabelResponse:
    """Label stored runs with the models their rows graded, or undo that.

    Superadmin only (an access key needs ``admin:platform``). ``dry_run``
    defaults to true and writes nothing. A changed run gets the label a run
    finishing now would get, and its previous ``model_id`` and
    ``eval_metadata`` are appended to ``eval_metadata["relabel_history"]``
    with ``relabeled_at`` and ``relabeled_by``. ``revert`` restores the
    state before the last relabel. Calling either again is a no-op.
    """
    query = db.query(EvaluationRun)
    if body.project_id:
        query = query.filter(EvaluationRun.project_id == body.project_id)
    if body.run_ids:
        query = query.filter(EvaluationRun.id.in_(body.run_ids))
    if not body.dry_run:
        query = query.with_for_update()
    runs = query.order_by(EvaluationRun.created_at, EvaluationRun.id).all()
    if body.project_id and not body.run_ids and not runs:
        raise HTTPException(
            status_code=404, detail="The project has no evaluation runs."
        )

    counts = {} if body.revert else graded_model_counts_by_run(db, [r.id for r in runs])
    now = datetime.now(timezone.utc).isoformat()
    results: list[RelabelItem] = []
    for run in runs:
        graded_rows = dict(counts.get(run.id, []))
        if body.revert:
            item = _revert(run, body.dry_run)
        elif run.status not in _TERMINAL_STATUSES:
            item = RelabelItem(
                run_id=run.id,
                outcome="skipped",
                reason="The run has not finished; it is labelled when it does.",
                before=_label(run.model_id, run.eval_metadata),
            )
        elif _never_relabelled(run.model_id):
            item = RelabelItem(
                run_id=run.id,
                outcome="skipped",
                reason="Human-graded and immediate runs keep their label.",
                before=_label(run.model_id, run.eval_metadata),
            )
        elif not graded_rows:
            item = RelabelItem(
                run_id=run.id,
                outcome="no_graded_generations",
                before=_label(run.model_id, run.eval_metadata),
            )
        else:
            item = _relabel(
                db, run, list(graded_rows), body.dry_run, current_user.id, now
            )
        item.project_id = run.project_id
        item.status = run.status
        item.graded_rows = graded_rows
        results.append(item)

    found = {r.id for r in runs}
    for run_id in body.run_ids or []:
        if run_id not in found:
            results.append(RelabelItem(run_id=run_id, outcome="not_found"))

    if not body.dry_run:
        db.commit()
        logger.info(
            "%s evaluation runs by %s: %s",
            "Reverted relabel of" if body.revert else "Relabelled",
            current_user.id,
            {r.run_id: r.outcome for r in results if r.outcome == "changed"},
        )

    tally = {
        k: sum(1 for r in results if r.outcome == k)
        for k in (
            "changed",
            "unchanged",
            "no_graded_generations",
            "skipped",
            "not_found",
        )
    }
    return RelabelResponse(
        dry_run=body.dry_run, revert=body.revert, results=results, **tally
    )
