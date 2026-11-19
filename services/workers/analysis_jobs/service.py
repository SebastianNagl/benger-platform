"""Run one analysis: frame from the database, engine, estimates to the database.

``tasks.run_analysis(run_id)`` calls :func:`run_analysis_impl`:

1. claim the run (``pending`` or a ``running`` row left by a dead worker;
   a finished run is left alone, so a redelivered message is a no-op);
2. check that every further project of the run (input projects, owners of
   stored lookup tables) still exists and is not deleted, here and again
   before the results are stored, so a purge in between fails the run;
   read the observations of the run's project and spec, and of every
   further project of a cross-project frame
   (:func:`analysis.db_source.iter_run_observations`), load the stored
   lookup tables the spec names (:func:`analysis.db_source.load_lookup_tables`),
   with the answers' texts and the coding projects' judge codes when code
   measures need them (the overlays' coder plugins are loaded first), and
   build the frame; every code measure's validation is checked (a
   confirmatory family needs one per code it reads,
   :func:`analysis_jobs.coding.check_code_validations`);
3. fit every estimand (:func:`analysis.runner.run_spec`);
4. store the frame as Parquet under ``analysis/`` with its content hash and
   write one ``analysis_estimates`` row per estimate, replacing any rows a
   dead worker left;
5. record versions (engine, numeric libraries, the workers' lockfile hash),
   the resolved inputs (further projects, lookup tables with their content
   hashes), the identity of every code measure (``codes``), counts, per-fit
   summaries, warnings and timings, and mark the run ``completed``.

A spec or data problem the engine can name (an unknown column, a text
outcome, a measure that does not evaluate) fails the run with that message.
Anything else fails it with a generic message pointing at the server log,
since exception texts can carry SQL or hosts.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import extension_activation

logger = logging.getLogger(__name__)

LOCKFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uv.lock")
PARQUET_TYPE = "application/vnd.apache.parquet"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lockfile_sha256(path: str = LOCKFILE) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def library_versions() -> Dict[str, str]:
    import numpy
    import pandas
    import pyarrow
    import scipy
    import statsmodels

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
        "pyarrow": pyarrow.__version__,
    }


def public_error(exc: BaseException, run_id: str) -> str:
    """What the run reports: the engine's own message for problems of the
    spec or the data, a pointer to the log for everything else."""
    from analysis.codes import CodeError
    from analysis.coders import CoderError
    from analysis.coding import CodingError
    from analysis.frame import FrameError
    from analysis.measures import MeasureError
    from analysis.ols import EngineError
    from analysis.spec import SpecError
    from analysis_jobs.coding import CodeValidationError

    if isinstance(
        exc,
        (CodeError, CoderError, CodingError, CodeValidationError, EngineError, FrameError, MeasureError, SpecError),
    ):
        return str(exc)[:4000]
    return (
        "The analysis failed because of an internal error. The server log has "
        f"the details under analysis run {run_id}."
    )


def _estimate_row(run_id: str, row: Dict[str, Any]):
    from models import AnalysisEstimate

    keys = (
        "position", "estimand_id", "contrast_id", "estimator", "kind", "outcome", "scope",
        "scope_values", "status", "message", "estimate", "std_error", "statistic", "df",
        "p_value", "null_value", "ci_level", "ci_lower", "ci_upper", "equivalent", "tost",
        "mde", "ratio", "family", "p_adjusted", "adjustments", "n_obs", "n_clusters",
        "k_params", "conventions",
    )
    values = {k: row.get(k) for k in keys}
    values["kind"] = values["kind"] or "linear"
    values["scope"] = values["scope"] or "pooled"
    return AnalysisEstimate(run_id=run_id, **values)


def _claim(db, run_id: str):
    from models import AnalysisRun

    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id)
        .with_for_update()
        .first()
    )
    if run is None or run.status not in ("pending", "running"):
        db.rollback()
        return None
    run.status = "running"
    run.started_at = _now()
    run.error_message = None
    db.commit()
    return run


def _fail(db, run_id: str, message: str) -> None:
    from models import AnalysisRun

    db.rollback()
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if run is None or run.status not in ("pending", "running"):
        db.rollback()
        return
    run.status = "failed"
    run.error_message = message
    run.completed_at = _now()
    db.commit()


def run_analysis_impl(run_id: str, *, session_factory=None, storage=None) -> Dict[str, Any]:
    if session_factory is None:
        from database import SessionLocal as session_factory  # noqa: N813
    db = session_factory()
    try:
        run = _claim(db, run_id)
        if run is None:
            logger.info("run_analysis: run %s is missing or finished; nothing to do", run_id)
            return {"run_id": run_id, "status": "skipped"}
        # Analyses belong to variant_experiments (core 2.71): a run whose
        # owner has the flag off is not computed; it ends failed with the
        # platform's feature-disabled message, its spec stays stored.
        from feature_flags import FEATURE_DISABLED_MESSAGE, VARIANT_EXPERIMENTS
        from feature_flags.worker import feature_disabled_result, flag_enabled_or_default

        if not flag_enabled_or_default(db, run.created_by, VARIANT_EXPERIMENTS):
            _fail(db, run_id, FEATURE_DISABLED_MESSAGE)
            return {"run_id": run_id, **feature_disabled_result(VARIANT_EXPERIMENTS)}
        try:
            with extension_activation.use_context(
                user_id=run.created_by, project_id=run.project_id, kind=extension_activation.KIND_TASK
            ):
                return _execute(db, run, storage)
        except Exception as exc:  # noqa: BLE001 - every failure ends the run
            logger.error("run_analysis: run %s failed: %s", run_id, exc, exc_info=True)
            _fail(db, run_id, public_error(exc, run_id))
            return {"run_id": run_id, "status": "failed"}
    finally:
        db.close()


def _execute(db, run, storage) -> Dict[str, Any]:
    from analysis.codes import CodeInputs
    from analysis.coders import coder_registry, load_overlay_coders
    from analysis.db_source import (
        check_input_projects,
        code_needs,
        iter_run_observations,
        load_judge_values,
        load_lookup_tables,
    )
    from analysis.frame import build_frame, frame_sha256, to_parquet
    from analysis.runner import run_spec
    from analysis.version import ENGINE_VERSION
    from analysis_jobs.coding import check_code_validations
    from models import AnalysisEstimate

    t0 = time.perf_counter()
    spec = run.normalized_spec
    source_counts: Dict[str, int] = {}
    check_input_projects(db, run)
    db.commit()
    with_text, judges = code_needs(spec)
    if any(m.get("kind") == "coder" for m in (spec.get("measures") or {}).values()):
        load_overlay_coders()
    observations = list(
        iter_run_observations(db, run.project_id, spec["inputs"], source_counts, with_text=with_text)
    )
    lookup_tables, resolved_lookups = load_lookup_tables(db, run.project_id, spec.get("lookups") or [])
    judge_values, judge_stats = load_judge_values(db, run.project_id, judges)
    t_read = time.perf_counter()
    built = build_frame(
        observations,
        spec,
        lookup_tables=lookup_tables,
        home_project=run.project_id,
        codes=CodeInputs(judge_values=judge_values, judge_stats=judge_stats, coders=coder_registry),
    )
    codes = check_code_validations(db, run.project_id, spec, built.codes)
    frame = built.frame
    frame_hash = built.hash
    parquet = to_parquet(
        frame, metadata={"benger.spec_hash": run.spec_hash, "benger.analysis_run": run.id}
    )
    t_frame = time.perf_counter()
    result = run_spec(frame, spec)
    t_fit = time.perf_counter()
    # Stored only once the estimates exist and deleted again when the run
    # cannot be recorded, so a run that fails leaves no object behind.
    if storage is None:
        from storage.object_storage import object_storage as storage
    stored = storage.upload_file(
        parquet,
        filename=f"frame-{run.id}.parquet",
        file_type="analysis",
        content_type=PARQUET_TYPE,
        metadata={"analysis_run": run.id, "frame_hash": frame_hash},
    )
    t_store = time.perf_counter()

    try:
        check_input_projects(db, run)
        db.query(AnalysisEstimate).filter(AnalysisEstimate.run_id == run.id).delete(
            synchronize_session=False
        )
        db.add_all([_estimate_row(run.id, row) for row in result.estimates])
        counts = dict(built.counts)
        counts.update(source_counts)
        counts["rows_in_filter"] = result.rows_in_filter
        run.frame_hash = frame_hash
        run.frame_object_key = stored["file_key"]
        run.frame_sha256 = frame_sha256(parquet)
        run.frame_bytes = len(parquet)
        run.frame_rows = int(len(frame))
        run.frame_counts = counts
        run.engine_version = ENGINE_VERSION
        run.library_versions = library_versions()
        run.lockfile_sha256 = lockfile_sha256()
        run.resolved_inputs = {
            "projects": [p["project_id"] for p in spec["inputs"].get("projects") or []],
            "lookups": resolved_lookups,
        }
        run.fits = result.fits
        run.codes = codes or None
        run.warnings = built.warnings + result.warnings
        run.estimates_count = len(result.estimates)
        run.timings = {
            "read_s": round(t_read - t0, 6),
            "frame_s": round(t_frame - t_read, 6),
            "fit_s": round(t_fit - t_frame, 6),
            "store_s": round(t_store - t_fit, 6),
            "total_s": round(time.perf_counter() - t0, 6),
        }
        run.status = "completed"
        run.completed_at = _now()
        db.commit()
    except Exception:
        try:
            storage.delete_file(stored["file_key"])
        except Exception:  # noqa: BLE001 - the run failure is what is reported
            logger.error("run_analysis: run %s left frame %s behind", run.id, stored["file_key"], exc_info=True)
        raise
    logger.info(
        "run_analysis: run %s completed: %d rows, %d estimates, frame %s",
        run.id, len(frame), len(result.estimates), frame_hash[:12],
    )
    return {"run_id": run.id, "status": "completed", "estimates": len(result.estimates), "frame_hash": frame_hash}


def fail_escaped_run(run_id: str, exc: BaseException, *, session_factory=None) -> Dict[str, Any]:
    """Mark a run failed when the task body raised before its own handler
    (a lazy import, opening the session)."""
    logger.error("run_analysis: run %s raised outside its handler: %s", run_id, exc, exc_info=True)
    try:
        if session_factory is None:
            from database import SessionLocal as session_factory  # noqa: N813
        db = session_factory()
        try:
            _fail(db, run_id, public_error(exc, run_id))
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("run_analysis: could not mark run %s failed", run_id)
    return {"run_id": run_id, "status": "failed"}
