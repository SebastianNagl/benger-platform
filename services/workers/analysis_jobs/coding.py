"""Codes in the workers: validations of codes and the check that analysis runs
only use validated codes where it matters.

``tasks.run_code_validation(validation_id)`` calls
:func:`run_code_validation_impl`:

1. claim the validation (``pending`` or a ``running`` row a dead worker left;
   a finished one is left alone, so a redelivered message is a no-op);
2. read the coding project's tasks (``data.answer``, ``meta.coding``), the
   human codes of the validated control (non-cancelled annotations) and,
   for codes that need them, the source tasks and source answers;
3. compute the automatic code of every task: a text pattern code on the
   shown answer with the source task's literals, a coder plugin with the
   source answer's fields, task data and design factors, or the judge
   system's generation on the coding task;
4. compute the agreement (:func:`analysis.coding.validation_metrics`) and
   store it with the code's identity hash and the per-task codes.

:func:`check_code_validations` is the analysis-run side: every code measure
an estimand of a confirmatory family reads needs a ``validation``, and every
validation a measure names must be a completed validation, drawn from the
run's project, of a code with the measure's identity hash.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

import extension_activation

logger = logging.getLogger(__name__)

MAX_STORED_ITEMS = 20000
TASK_BATCH = 500


class CodeValidationError(ValueError):
    """An analysis run reads a code without the validation it needs."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def check_code_validations(
    db, project_id: str, spec: Mapping[str, Any], frame_codes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """The run's code records with the accepted validations filled in.
    Raises :class:`CodeValidationError` naming every code that lacks one."""
    from analysis.codes import confirmatory_code_measures
    from models import CodeValidation

    required = confirmatory_code_measures(spec)
    errors: List[str] = []
    out: List[Dict[str, Any]] = []
    for record in frame_codes:
        rec = dict(record)
        mid = rec["measure"]
        vid = rec.pop("validation", None)
        if mid in required:
            rec["confirmatory_estimands"] = required[mid]
        if not vid:
            if mid in required:
                errors.append(
                    f"measure {mid!r} is a code read by the confirmatory estimand(s) "
                    f"{', '.join(required[mid])} and names no validation; validate it on a "
                    "coding project and set 'validation', or mark the family exploratory"
                )
            out.append(rec)
            continue
        v = db.query(CodeValidation).filter(CodeValidation.id == vid).first()
        if v is None or v.source_project_id != project_id:
            errors.append(f"measure {mid!r}: validation {vid!r} is not a validation of this project's answers")
        elif v.status != "completed":
            errors.append(f"measure {mid!r}: validation {vid!r} is {v.status}, not completed")
        elif not v.n_compared or v.kappa is None:
            errors.append(
                f"measure {mid!r}: validation {vid!r} compared {v.n_compared or 0} item(s) and has no "
                "kappa, so it is no evidence of agreement; validate the code on coded items"
            )
        elif v.code_hash != rec["hash"]:
            errors.append(
                f"measure {mid!r}: validation {vid!r} validated another code "
                f"({v.code_ref}, hash {str(v.code_hash)[:12]}) than this measure "
                f"({rec.get('ref')}, hash {rec['hash'][:12]})"
            )
        else:
            rec["validation"] = {
                "id": v.id,
                "coding_project_id": v.project_id,
                "control": v.control,
                "kappa": v.kappa,
                "observed_agreement": v.observed_agreement,
                "compared": v.n_compared,
                "completed_at": _iso(v.completed_at),
            }
        out.append(rec)
    if errors:
        raise CodeValidationError("; ".join(errors))
    return out


# --------------------------------------------------------------------------
# Running a validation
# --------------------------------------------------------------------------


def _claim(db, validation_id: str):
    from models import CodeValidation

    v = (
        db.query(CodeValidation)
        .filter(CodeValidation.id == validation_id)
        .with_for_update()
        .first()
    )
    if v is None or v.status not in ("pending", "running"):
        db.rollback()
        return None
    v.status = "running"
    v.started_at = _now()
    v.error_message = None
    db.commit()
    return v


def _fail(db, validation_id: str, message: str) -> None:
    from models import CodeValidation

    db.rollback()
    v = db.query(CodeValidation).filter(CodeValidation.id == validation_id).first()
    if v is None or v.status not in ("pending", "running"):
        db.rollback()
        return
    v.status = "failed"
    v.error_message = message
    v.completed_at = _now()
    db.commit()


def public_error(exc: BaseException, validation_id: str) -> str:
    from analysis.codes import CodeError
    from analysis.coders import CoderError
    from analysis.coding import CodingError

    if isinstance(exc, (CodeError, CoderError, CodingError)):
        return str(exc)[:4000]
    return (
        "The validation failed because of an internal error. The server log has "
        f"the details under code validation {validation_id}."
    )


def _by_ids(db, model, column, ids: List[str], *cols):
    from sqlalchemy import select

    out = {}
    ids = sorted(set(i for i in ids if i))
    for start in range(0, len(ids), TASK_BATCH):
        batch = ids[start : start + TASK_BATCH]
        for row in db.execute(select(column, *cols).where(column.in_(batch))):
            out[row[0]] = row[1:] if len(cols) > 1 else row[1]
    return out


def _coding_tasks(db, coding_project_id: str) -> List[Dict[str, Any]]:
    from sqlalchemy import select

    from project_models import Task

    tasks = []
    rows = db.execute(
        select(Task.id, Task.data, Task.meta).where(Task.project_id == coding_project_id).order_by(Task.inner_id, Task.id)
    ).all()
    for task_id, data, meta in rows:
        block = meta.get("coding") if isinstance(meta, Mapping) else None
        if not isinstance(block, Mapping):
            continue
        answer = (data or {}).get("answer") if isinstance(data, Mapping) else None
        tasks.append(
            {
                "task_id": task_id,
                "answer": answer if isinstance(answer, str) else None,
                "source_task_id": block.get("source_task_id"),
                "source_generation_id": block.get("source_generation_id"),
            }
        )
    return tasks


def _human_codes(db, task_ids: List[str], control: str, warnings: List[str]) -> Dict[str, Dict[str, Optional[str]]]:
    from sqlalchemy import select

    from analysis.coding import code_label
    from analysis.observations import typed_field_values
    from project_models import Annotation

    out: Dict[str, Dict[str, Optional[str]]] = {}
    multi = 0
    for start in range(0, len(task_ids), TASK_BATCH):
        batch = task_ids[start : start + TASK_BATCH]
        rows = db.execute(
            select(Annotation.task_id, Annotation.completed_by, Annotation.result)
            .where(Annotation.task_id.in_(batch))
            .where(Annotation.was_cancelled == False)  # noqa: E712
            .order_by(Annotation.task_id, Annotation.created_at, Annotation.id)
        )
        for task_id, coder, result in rows:
            value = typed_field_values(result).get(control)
            if isinstance(value, (list, tuple)) and len(value) > 1:
                multi += 1
                continue
            label = code_label(value)
            if label is None:
                continue
            out.setdefault(task_id, {})[coder] = label
    if multi:
        warnings.append(f"{multi} human code(s) of {control!r} chose more than one value and were left out")
    return out


def _automatic_codes(db, v, coding, tasks: List[Dict[str, Any]], warnings: List[str]):
    """``({coding task id: raw value}, identity)``."""
    from analysis.codes import code_identity
    from analysis.coders import CoderContext, coder_registry, load_overlay_coders
    from analysis.db_source import coding_generation_values
    from analysis.observations import typed_field_values, variant_of_task_meta
    from analysis.text_patterns import CompiledPatternSet
    from models import Generation
    from project_models import Task

    code = v.normalized_code
    kind = code["kind"]
    if kind == "judge_code":
        field = code.get("field") or v.control
        code = {**code, "field": field}
        values, stats = coding_generation_values(
            db,
            [t["task_id"] for t in tasks],
            field=field,
            system=code["system"],
            structure=code.get("structure"),
            run_index=int(code.get("run_index", 0)),
        )
        identity = code_identity(code)
        identity["coding"] = stats
        for key in ("no_answer", "ambiguous", "unparsed"):
            if stats.get(key):
                warnings.append(f"{stats[key]} coding task(s) have {key.replace('_', ' ')} from {code['system']}")
        return values, identity

    source_tasks = _by_ids(db, Task, Task.id, [t["source_task_id"] for t in tasks], Task.data, Task.meta)
    if kind == "text_pattern":
        compiled = CompiledPatternSet(code["set"])
        values = {}
        for t in tasks:
            data = (source_tasks.get(t["source_task_id"]) or ({}, None))[0] or {}
            values[t["task_id"]] = compiled.code(code["code"], t["answer"], data)
        return values, code_identity(code)

    load_overlay_coders()
    entry = coder_registry.resolve(code["coder"], code.get("version"))
    if code["output"] not in entry.outputs:
        from analysis.codes import CodeError

        raise CodeError(f"coder {entry.ref} has no output {code['output']!r}")
    parsed = _by_ids(
        db, Generation, Generation.id, [t["source_generation_id"] for t in tasks], Generation.parsed_annotation
    )
    values = {}
    for t in tasks:
        data, meta = source_tasks.get(t["source_task_id"]) or ({}, None)
        variant = variant_of_task_meta(meta) or {}
        context = CoderContext(
            fields=typed_field_values(parsed.get(t["source_generation_id"])),
            task_data=data or {},
            factors=variant.get("factors") or {},
            parameters=code.get("parameters") or {},
        )
        values[t["task_id"]] = entry.run(t["answer"], context).get(code["output"])
    return values, code_identity(code, coder=entry)


def _execute(db, v) -> Dict[str, Any]:
    from analysis.coding import CODING_VERSION, CodingError, code_label, validation_metrics
    from models import CodeValidation, CodingProject

    warnings: List[str] = []
    coding = db.query(CodingProject).filter(CodingProject.project_id == v.project_id).first()
    if coding is None:
        raise CodingError(["the project is not a coding project"])
    tasks = _coding_tasks(db, v.project_id)
    task_ids = [t["task_id"] for t in tasks]
    human = _human_codes(db, task_ids, v.control, warnings)
    raw, identity = _automatic_codes(db, v, coding, tasks, warnings)
    value_map = (v.options or {}).get("value_map") or {}
    items = []
    for t in tasks:
        items.append(
            {
                "task_id": t["task_id"],
                "source_generation_id": t["source_generation_id"],
                "automatic": code_label(raw.get(t["task_id"]), value_map),
                "human": human.get(t["task_id"], {}),
            }
        )
    metrics = validation_metrics(items, missing=(v.options or {}).get("missing", "category"))
    if not metrics["compared"]:
        raise CodingError(["no coding task has both a human and a usable reference code"])
    main = metrics["automatic_vs_reference"]
    v.identity = identity
    ref = identity.get("ref")
    v.code_ref = ref[: CodeValidation.code_ref.type.length] if ref else None
    v.code_version = identity.get("version")
    v.code_hash = identity["hash"]
    v.metrics = metrics
    v.items = items[:MAX_STORED_ITEMS]
    if len(items) > MAX_STORED_ITEMS:
        warnings.append(f"only the first {MAX_STORED_ITEMS} of {len(items)} items are stored")
    v.n_items = len(items)
    v.n_compared = metrics["compared"]
    v.kappa = main.get("kappa")
    v.observed_agreement = main.get("observed_agreement")
    v.coding_version = CODING_VERSION
    v.warnings = warnings
    v.status = "completed"
    v.completed_at = _now()
    db.commit()
    logger.info(
        "run_code_validation: %s completed: %d items, %d compared, kappa %s",
        v.id, len(items), metrics["compared"], v.kappa,
    )
    return {"validation_id": v.id, "status": "completed", "compared": metrics["compared"], "kappa": v.kappa}


def run_code_validation_impl(validation_id: str, *, session_factory=None) -> Dict[str, Any]:
    if session_factory is None:
        from database import SessionLocal as session_factory  # noqa: N813
    db = session_factory()
    try:
        v = _claim(db, validation_id)
        if v is None:
            logger.info("run_code_validation: %s is missing or finished; nothing to do", validation_id)
            return {"validation_id": validation_id, "status": "skipped"}
        # Coding validation belongs to variant_experiments (core 2.70).
        from feature_flags import FEATURE_DISABLED_MESSAGE, VARIANT_EXPERIMENTS
        from feature_flags.worker import feature_disabled_result, flag_enabled_or_default

        if not flag_enabled_or_default(db, v.created_by, VARIANT_EXPERIMENTS):
            _fail(db, validation_id, FEATURE_DISABLED_MESSAGE)
            return {"validation_id": validation_id, **feature_disabled_result(VARIANT_EXPERIMENTS)}
        try:
            with extension_activation.use_context(
                user_id=v.created_by, project_id=v.project_id, kind=extension_activation.KIND_TASK
            ):
                return _execute(db, v)
        except Exception as exc:  # noqa: BLE001 - every failure ends the validation
            logger.error("run_code_validation: %s failed: %s", validation_id, exc, exc_info=True)
            _fail(db, validation_id, public_error(exc, validation_id))
            return {"validation_id": validation_id, "status": "failed"}
    finally:
        db.close()


def fail_escaped_validation(validation_id: str, exc: BaseException, *, session_factory=None) -> Dict[str, Any]:
    logger.error("run_code_validation: %s raised outside its handler: %s", validation_id, exc, exc_info=True)
    try:
        if session_factory is None:
            from database import SessionLocal as session_factory  # noqa: N813
        db = session_factory()
        try:
            _fail(db, validation_id, public_error(exc, validation_id))
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("run_code_validation: could not mark %s failed", validation_id)
    return {"validation_id": validation_id, "status": "failed"}
