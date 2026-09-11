"""Bring stored Notenpunkte onto the project's CURRENT Notenschlüssel.

The exam-level Notenschlüssel (``project.evaluation_config.grade_scale``,
contract v2) is editable after the fact, but a grade is computed once at
grading time and persisted into ``TaskEvaluation.metrics``. Changing the key
therefore leaves every older grading on the old curve — the same submission
can end up with two different Notenpunkte depending on when it was graded.

This module is the scan + rewrite that closes that gap. It is deliberately
generic platform code: it walks rows of platform tables, recomputes a derived
number with the shared helpers in ``rubric_structure`` and writes it back.
Metric names appear only as STRING KEYS (a precedence list for picking the
row's headline grade); no proprietary grading logic lives here.

Scope rule — recompute only what is ALREADY a grade
---------------------------------------------------
A metric blob is in scope when its ``details`` carries a numeric
``grade_points``. Legacy ``llm_judge_custom`` rows store totals but never a
grade; minting one for them would invent an assessment that nobody made.

Points and total per blob (the two grading lanes name them differently)::

    points = details.total_score ?? details.raw_score
    total  = rubric.total_points (when a rubric is referenced) ??
             details.total_max ?? 100.0

and the grade is ``rubric_structure.grade_for_rubric(rubric, points, total,
project.evaluation_config)`` — the exact call every writer makes
(``workers/evaluation/{cell,judge}_evaluator.py``, the extended Korrektur
grader), so a recomputed row is bit-identical to a freshly graded one.

What is written back, per row:

* ``details.grade_points``
* ``details.passed`` — refreshed where the writer put it, added only when
  the grade itself moved
* ``details.grade_scale_source`` — only when the key already exists (the
  writers set it; a stale one would misreport which key won)
* the sibling metrics ``<metric>_grade_points`` / ``<metric>_passed``, only
  when they already exist (bulk + immediate judge rows carry them)
* ``TaskEvaluation.passed`` from the row's headline grade

What is NEVER touched: ``details.judge_response``, ``raw_output``, ``scores``,
``call_metadata`` and everything else that records what a model or a human
actually produced. That is evidence, not a derived value.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import EvaluationRun, TaskEvaluation
from project_models import Project, TaskRubric
from rubric_structure import grade_for_rubric

logger = logging.getLogger(__name__)

# Falllösung grading runs on a 0–100 raw scale, where a blob carries no
# ``total_max`` at all; 100 is then the total, not a guess.
DEFAULT_TOTAL_POINTS = 100.0

# SQL prefilter: only rows that already carry a grade somewhere in their
# metrics blob can be in scope, and on a benchmark project those are a tiny
# minority. The jsonpath match runs in Postgres so the drift read never
# streams a project's whole (large, raw_output-carrying) metrics column.
_HAS_GRADE_POINTS = text("task_evaluations.metrics @? '$.*.details.grade_points'")

# Which blob's grade is the ROW's grade when a row somehow carries several.
# String keys only — a hook list, not grading logic. Mirrors the headline
# order of ``shared/report_snapshot._PRIMARY_PREFERENCE``; anything not
# listed sorts after it, alphabetically, so the pick is deterministic.
_ROW_GRADE_PRECEDENCE: Tuple[str, ...] = (
    "llm_judge_falloesung",
    "korrektur_falloesung",
    "llm_judge_rubric",
    "llm_judge_custom",
    "korrektur_custom",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class _RowPlan:
    """The rewritten metrics blob of one row that is off the current key."""

    row_id: str
    metrics: Dict[str, Any]
    passed: bool


@dataclass
class _Scan:
    graded: int = 0
    scanned_rows: int = 0
    plans: List[_RowPlan] = field(default_factory=list)
    sources: Set[str] = field(default_factory=set)


def _blob_points_and_total(details: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """``(points, fallback_total)`` of an in-scope blob, or ``None``.

    ``total_score`` is the rubric lane (``llm_judge_rubric``,
    ``korrektur_custom``), ``raw_score`` the Falllösung lane
    (``llm_judge_falloesung``, ``korrektur_falloesung``, a 0–100 scale that
    stores no total).
    """
    points = details.get("total_score")
    if not _is_number(points):
        points = details.get("raw_score")
    if not _is_number(points):
        return None
    total = details.get("total_max")
    if not _is_number(total) or float(total) <= 0:
        total = DEFAULT_TOTAL_POINTS
    return float(points), float(total)


def _row_grade_key(keys: List[str]) -> str:
    """The in-scope metric key whose grade is the row's grade."""

    def sort_key(key: str) -> Tuple[int, str]:
        try:
            return (_ROW_GRADE_PRECEDENCE.index(key), key)
        except ValueError:
            return (len(_ROW_GRADE_PRECEDENCE), key)

    return sorted(keys, key=sort_key)[0]


def _plan_row(
    metrics: Any,
    row_passed: Any,
    project_config: Any,
    rubrics: Dict[str, TaskRubric],
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[bool], Set[str]]:
    """``(in_scope, new_metrics, new_row_passed, scale_sources)`` for one row.

    ``new_metrics`` / ``new_row_passed`` are ``None`` when nothing changed —
    a row whose stored grade already matches the current key is NOT stale.
    """
    sources: Set[str] = set()
    if not isinstance(metrics, dict):
        return False, None, None, sources

    updated = copy.deepcopy(metrics)
    changed = False
    in_scope = False
    graded_keys: List[str] = []
    passed_by_key: Dict[str, bool] = {}

    for key, blob in updated.items():
        if not isinstance(blob, dict):
            continue
        details = blob.get("details")
        if not isinstance(details, dict):
            continue
        stored_grade = details.get("grade_points")
        if not _is_number(stored_grade):
            continue
        # From here on the blob IS a grade: it counts toward `graded` even
        # when it cannot be recomputed.
        in_scope = True
        measured = _blob_points_and_total(details)
        if measured is None:
            continue
        points, fallback_total = measured
        rubric = rubrics.get(details.get("rubric_id"))
        grade, passed, source = grade_for_rubric(rubric, points, fallback_total, project_config)
        sources.add(source)
        graded_keys.append(key)
        passed_by_key[key] = passed

        grade_changed = int(stored_grade) != int(grade)
        if grade_changed:
            details["grade_points"] = int(grade)
            changed = True
        # The blob's own pass flag follows the grade. Refreshed where the
        # writer put it; only ADDED when the grade itself moved, so a row
        # that merely predates the flag is not reported as "off the key".
        if "passed" in details:
            if details["passed"] != passed:
                details["passed"] = passed
                changed = True
        elif grade_changed:
            details["passed"] = passed
        # Derived provenance — refreshed, never invented.
        if "grade_scale_source" in details and details["grade_scale_source"] != source:
            details["grade_scale_source"] = source
            changed = True

        # Sibling metrics of the bulk / immediate judge rows. Only rewritten
        # where the writer put them; a row without them never grows them.
        sibling_grade = f"{key}_grade_points"
        if sibling_grade in updated and updated[sibling_grade] != float(grade):
            updated[sibling_grade] = float(grade)
            changed = True
        sibling_passed = f"{key}_passed"
        if sibling_passed in updated:
            flag = 1.0 if passed else 0.0
            if updated[sibling_passed] != flag:
                updated[sibling_passed] = flag
                changed = True

    if not in_scope:
        return False, None, None, sources

    new_row_passed = None
    if graded_keys:
        new_row_passed = passed_by_key[_row_grade_key(graded_keys)]
        if bool(row_passed) != new_row_passed:
            changed = True

    if not changed:
        return True, None, None, sources
    return True, updated, (new_row_passed if new_row_passed is not None else bool(row_passed)), sources


def _load_rubrics(db: Session, rubric_ids: Set[str]) -> Dict[str, TaskRubric]:
    """Every referenced Bewertungsbogen in ONE query (never per row)."""
    ids = [rid for rid in rubric_ids if isinstance(rid, str) and rid]
    if not ids:
        return {}
    rows = db.execute(select(TaskRubric).where(TaskRubric.id.in_(ids))).scalars().all()
    return {row.id: row for row in rows}


def _scan(db: Session, project: Project) -> _Scan:
    """Walk the project's graded rows and plan the rewrite of the stale ones."""
    rows = db.execute(
        select(TaskEvaluation.id, TaskEvaluation.metrics, TaskEvaluation.passed)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .where(EvaluationRun.project_id == project.id)
        .where(_HAS_GRADE_POINTS)
    ).all()

    rubric_ids: Set[str] = set()
    for _row_id, metrics, _passed in rows:
        if not isinstance(metrics, dict):
            continue
        for blob in metrics.values():
            if isinstance(blob, dict) and isinstance(blob.get("details"), dict):
                rubric_id = blob["details"].get("rubric_id")
                if isinstance(rubric_id, str):
                    rubric_ids.add(rubric_id)
    rubrics = _load_rubrics(db, rubric_ids)

    project_config = project.evaluation_config
    scan = _Scan(scanned_rows=len(rows))
    for row_id, metrics, passed in rows:
        in_scope, new_metrics, new_passed, sources = _plan_row(
            metrics, passed, project_config, rubrics
        )
        scan.sources |= sources
        if not in_scope:
            continue
        scan.graded += 1
        if new_metrics is not None:
            scan.plans.append(_RowPlan(row_id=row_id, metrics=new_metrics, passed=bool(new_passed)))
    return scan


def _scale_source(project: Project, scan: _Scan) -> str:
    """Which step of ``resolve_grade_scale`` governs this project's grades."""
    config = project.evaluation_config
    if isinstance(config, dict) and isinstance(config.get("grade_scale"), dict):
        return "project"
    if "rubric" in scan.sources:
        return "rubric"
    return "default"


def grade_scale_drift(db: Session, project: Project) -> Dict[str, Any]:
    """How many stored gradings are off the project's current Notenschlüssel.

    ``{"stale": int, "graded": int, "scale_source": "project"|"rubric"|
    "default"}`` — ``graded`` counts rows that carry a grade at all,
    ``stale`` the subset whose stored grade (or pass flag) differs from what
    the current key produces. Read-only.
    """
    scan = _scan(db, project)
    return {
        "stale": len(scan.plans),
        "graded": scan.graded,
        "scale_source": _scale_source(project, scan),
    }


def recompute_grade_scale(db: Session, project: Project) -> Dict[str, Any]:
    """Rewrite every stale grading onto the project's current Notenschlüssel.

    ``{"updated": int, "scanned": int}`` — ``scanned`` counts the rows that
    carry a grade, ``updated`` those actually rewritten. Idempotent: a second
    call over an unchanged key updates nothing. Commits once.
    """
    scan = _scan(db, project)
    if not scan.plans:
        return {"updated": 0, "scanned": scan.graded}

    by_id = {plan.row_id: plan for plan in scan.plans}
    records = (
        db.execute(select(TaskEvaluation).where(TaskEvaluation.id.in_(list(by_id)))).scalars().all()
    )
    updated = 0
    for record in records:
        plan = by_id.get(record.id)
        if plan is None:  # pragma: no cover - ids come straight from the scan
            continue
        record.metrics = plan.metrics
        record.passed = plan.passed
        # Native JSONB column: the whole document is reassigned, but the
        # explicit flag keeps this correct if a caller ever mutates in place.
        flag_modified(record, "metrics")
        updated += 1
    db.commit()
    logger.info(
        "grade scale recompute: project=%s updated=%s of %s graded rows",
        project.id,
        updated,
        scan.graded,
    )
    return {"updated": updated, "scanned": scan.graded}
