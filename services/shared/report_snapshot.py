"""Report snapshot builder — the numbers behind a published project report.

A snapshot is computed once (on publish / explicit refresh) and stored in
``project_reports.content["snapshot"]``; the viewer renders it as-is. That
keeps a published benchmark report stable over time and keeps report views
off the hot path: nothing here loads ``task_evaluations.metrics`` rows into
Python. Every number is aggregated in Postgres over a single normalized CTE
(``jsonb_each`` over the metrics blob) — the same table scan that OOM-killed
the API when ``/statistics`` pulled the raw column (2026-07-23) is done by
the database, which only returns a few hundred aggregate rows.

Shape: see ``services/frontend/src/types/report.ts`` (``ReportSnapshot``).

Normalization rules (mirrors ``_coerce_metric_value`` semantics, see
``routers/evaluations/results/_common.py``):
  * ``{"value": x, "details": {...}}`` → ``x``; bare numbers → the number.
  * Judge metrics whose ``value`` is a 0..1 share of a 100-point scheme
    (Falllösung, Korrektur, custom rubric judges) are reported on ``0-100``.
  * Derived companions: ``<metric>_grade_points`` (0-18 Notenpunkte, from
    ``details.grade_points`` or the legacy sibling key) and
    ``<metric>_passed`` (pass rate, from ``details.passed`` / legacy sibling).
  * Sibling audit keys (``*_raw``, ``*_details``, ``*_response``,
    ``raw_score``, ``error``) are never metrics of their own.

Subjects: generations map to their model (``Generation.model_id``); human
submissions map to ``annotator:<user id>`` with the pseudonym display rule
the leaderboards apply. Custom (BYOM) models that are neither official nor
public are excluded unless ``include_private_models`` is set — same rule as
the LLM leaderboard, so a published report cannot leak a private endpoint.
The same rule drops a hidden model from every other section: its generation
counts, the human ratings of its answers and every preference comparison it
took part in. The Analyses section applies it per run instead: a run in
which a hidden model may appear is copied whole but marked member-only, and
the public view leaves it out.

Beyond the metric evaluation, the snapshot holds what a paper about the
project reports (each section is present for every project and stays empty
when the project has nothing of its kind, so the viewer hides it):

  * ``data``: the variant designs (factors, unit, task, unit and cell
    counts, status, hashes) and the provenance of completed imports
    (payload hash and size, mode, declared manifest, no-op repeats).
  * ``generation``: per model the generations, tasks, runs per task, prompt
    structures, refusal, truncation, parse-failure and retry rates and the
    share with a stored request record.
  * ``human_evaluations``: Likert ratings per dimension (overall and per
    model) and preference comparisons (per model and per pair).
  * ``analyses``: the completed single-project analysis runs the author
    put in the report's Analyses section, each with its metadata, the
    estimates its exhibits select (copied, so a published report keeps its
    numbers), whether it is member-only, and the exhibits (forest or table)
    with their filters; ``analyses.code_validations`` holds the validations
    of the codes those runs read (see :func:`_analysis_code_validations`),
    which the viewer shows in the Annotation section.
  * ``reproducibility``: platform versions, label config version and hash,
    prompt structure hashes, models, evaluation configs with the parameter
    snapshots their judge runs used, variant design and import hashes, the
    completed single-project analysis runs with their hashes and versions,
    and ``snapshot_sha256`` (see :func:`snapshot_sha256`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from annotator_agreement import project_annotator_agreement
from human_graded_metrics import scored_run_sql
from user_display import masked_name

logger = logging.getLogger(__name__)

# Judge metrics whose normalized 0..1 value is a share of a 100-point rubric.
_HUNDRED_POINT_METRICS = {
    "llm_judge_falloesung",
    "korrektur_falloesung",
    "llm_judge_custom",
    "korrektur_custom",
    "llm_judge_rubric",
}

# Metric ids the report prefers as the headline metric, best first.
_PRIMARY_PREFERENCE = [
    "llm_judge_falloesung",
    "korrektur_falloesung",
    "llm_judge_rubric",
    "llm_judge_custom",
    "korrektur_custom",
    "korrektur_feedback",
    "llm_judge_lexam",
    "llm_judge_classic",
    "accuracy",
    "exact_match",
    "f1",
    "semantic_similarity",
    "bertscore",
    "rouge",
    "bleu",
    "meteor",
    "chrf",
]

# Platform-side fallback display names (the frontend registry, which the
# extended edition enriches, takes precedence in the viewer).
_METRIC_NAMES = {
    "llm_judge_falloesung": "Falllösung LLM Judge",
    "korrektur_falloesung": "Korrektur (Standard Falllösung)",
    "llm_judge_custom": "Custom LLM Judge",
    "korrektur_custom": "Korrektur (Custom Rubric)",
    # French exam types: value = note / 20 (0-1 scale, never Notenpunkte).
    "korrektur_feedback": "Korrektur (Barème /20)",
    "korrektur_classic": "Korrektur (Classic)",
    "llm_judge_rubric": "LLM Custom Rubric",
    "llm_judge_lexam": "LEXam Judge (DE)",
    "llm_judge_classic": "Classic LLM Judge",
    "bleu": "BLEU",
    "rouge": "ROUGE",
    "meteor": "METEOR",
    "chrf": "chrF",
    "exact_match": "Exact Match",
    "bertscore": "BERTScore",
    "moverscore": "MoverScore",
    "semantic_similarity": "Semantic Similarity",
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "f1": "F1 Score",
    "coherence": "Coherence",
    "factcc": "FactCC",
    "qags": "QAGS",
}

_AUDIT_SUFFIXES = ("_response", "_details", "_raw", "_grade_points", "_passed")
_AUDIT_KEYS = {"raw_score", "error", "method"}

GRADE_BINS = list(range(0, 19))          # 0..18 Notenpunkte
UNIT_BINS = [i / 10 for i in range(10)]  # 0.0 .. 0.9 lower edges
HUNDRED_BINS = [i * 10 for i in range(10)]


def _is_metric_key(key: str) -> bool:
    if key in _AUDIT_KEYS:
        return False
    return not key.endswith(_AUDIT_SUFFIXES)


def _category(metric: str) -> str:
    if metric.startswith("korrektur_"):
        return "human"
    if metric.startswith("llm_judge_"):
        return "llm_judge"
    if metric in {"bertscore", "moverscore", "semantic_similarity"}:
        return "semantic"
    if metric in {"accuracy", "precision", "recall", "f1"}:
        return "classification"
    if metric in {"coherence", "factcc", "qags"}:
        return "factuality"
    return "lexical"


def _scale(metric: str) -> str:
    return "0-100" if metric in _HUNDRED_POINT_METRICS else "0-1"


def _humanize(metric: str) -> str:
    return _METRIC_NAMES.get(metric) or metric.replace("llm_judge_", "").replace("_", " ").title()


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# One normalized row per (evaluation row, metric key). Values and derived
# companions are extracted in SQL; nothing heavy leaves the database.
_VALUES_CTE = """
WITH runs AS (
    SELECT id FROM evaluation_runs
    WHERE project_id = :project_id AND status = 'completed'
),
rows AS (
    SELECT te.id, te.generation_id, te.annotation_id,
           COALESCE(te.evaluation_config_id, '') AS config_id,
           te.metrics::jsonb AS m
    FROM task_evaluations te
    JOIN runs ON runs.id = te.evaluation_id
    WHERE te.metrics IS NOT NULL AND jsonb_typeof(te.metrics::jsonb) = 'object'
),
vals AS (
    SELECT r.id AS row_id, r.generation_id, r.annotation_id, r.config_id,
           j.key AS metric,
           CASE jsonb_typeof(j.value)
                WHEN 'object' THEN CASE WHEN jsonb_typeof(j.value->'value') = 'number'
                                        THEN (j.value->>'value')::float END
                WHEN 'number' THEN (j.value#>>'{}')::float
                ELSE NULL END AS value,
           COALESCE(
                CASE WHEN jsonb_typeof(j.value->'details'->'grade_points') = 'number'
                     THEN (j.value->'details'->>'grade_points')::float END,
                CASE WHEN jsonb_typeof(r.m->(j.key || '_grade_points')) = 'number'
                     THEN (r.m->>(j.key || '_grade_points'))::float END
           ) AS grade_points,
           COALESCE(
                CASE WHEN jsonb_typeof(j.value->'details'->'passed') = 'boolean'
                     THEN (j.value->'details'->>'passed')::boolean::int::float END,
                CASE WHEN jsonb_typeof(r.m->(j.key || '_passed')) = 'number'
                     THEN (r.m->>(j.key || '_passed'))::float
                     WHEN jsonb_typeof(r.m->(j.key || '_passed')) = 'boolean'
                     THEN (r.m->>(j.key || '_passed'))::boolean::int::float END
           ) AS passed
    FROM rows r, jsonb_each(r.m) AS j
    WHERE j.key NOT IN ('raw_score', 'error', 'method')
      AND j.key NOT LIKE '%\\_response'
      AND j.key NOT LIKE '%\\_details'
      AND j.key NOT LIKE '%\\_raw'
      AND j.key NOT LIKE '%\\_grade\\_points'
      AND j.key NOT LIKE '%\\_passed'
      AND (jsonb_typeof(j.value) = 'number'
           OR (jsonb_typeof(j.value) = 'object' AND (j.value ? 'value')))
),
subjects AS (
    SELECT v.*,
           CASE WHEN v.generation_id IS NOT NULL THEN 'model'
                WHEN v.annotation_id IS NOT NULL THEN 'human' END AS kind,
           CASE WHEN v.generation_id IS NOT NULL THEN g.model_id
                WHEN v.annotation_id IS NOT NULL THEN 'annotator:' || a.completed_by END AS subject_id
    FROM vals v
    LEFT JOIN generations g ON g.id = v.generation_id
    LEFT JOIN annotations a ON a.id = v.annotation_id
    WHERE v.value IS NOT NULL
      AND (v.generation_id IS NOT NULL OR v.annotation_id IS NOT NULL)
)
"""

_STATS_SQL = _VALUES_CTE + """
SELECT kind, subject_id, config_id, metric,
       COUNT(*) AS n,
       AVG(value) AS mean, STDDEV_SAMP(value) AS std, MIN(value) AS min, MAX(value) AS max,
       AVG(passed) AS pass_rate,
       COUNT(grade_points) AS gp_n, AVG(grade_points) AS gp_mean,
       STDDEV_SAMP(grade_points) AS gp_std, MIN(grade_points) AS gp_min, MAX(grade_points) AS gp_max
FROM subjects
WHERE subject_id IS NOT NULL
GROUP BY kind, subject_id, config_id, metric
"""

_HIST_SQL = _VALUES_CTE + """
SELECT kind, subject_id, config_id, metric, 'value' AS series,
       LEAST(9, GREATEST(0, FLOOR(value * 10)))::int AS bin, COUNT(*) AS n
FROM subjects WHERE subject_id IS NOT NULL
GROUP BY kind, subject_id, config_id, metric, bin
UNION ALL
SELECT kind, subject_id, config_id, metric, 'grade' AS series,
       LEAST(18, GREATEST(0, FLOOR(grade_points)))::int AS bin, COUNT(*) AS n
FROM subjects WHERE subject_id IS NOT NULL AND grade_points IS NOT NULL
GROUP BY kind, subject_id, config_id, metric, bin
"""

_COUNTS_SQL = """
SELECT
  (SELECT COUNT(*) FROM tasks WHERE project_id = :project_id) AS task_count,
  (SELECT COUNT(*) FROM annotations WHERE project_id = :project_id AND was_cancelled = false) AS annotation_count,
  (SELECT COUNT(DISTINCT completed_by) FROM annotations WHERE project_id = :project_id AND was_cancelled = false) AS participant_count,
  (SELECT COUNT(*) FROM task_evaluations te JOIN evaluation_runs r ON r.id = te.evaluation_id
     WHERE r.project_id = :project_id AND r.status = 'completed'
       AND """ + scored_run_sql("r") + """) AS evaluation_count,
  (SELECT COUNT(*) FROM analysis_runs WHERE project_id = :project_id AND status = 'completed') AS analysis_count
"""

_MODELS_SQL = """
SELECT DISTINCT g.model_id, m.name, m.provider, m.is_official, m.is_public, m.is_active
FROM generations g
JOIN response_generations rg ON rg.id = g.generation_id
LEFT JOIN llm_models m ON m.id = g.model_id
WHERE rg.project_id = :project_id
"""

_PARTICIPANTS_SQL = """
SELECT u.id, u.pseudonym, COUNT(a.id) AS annotation_count
FROM annotations a JOIN users u ON u.id = a.completed_by
WHERE a.project_id = :project_id AND a.was_cancelled = false
GROUP BY u.id, u.pseudonym
"""

_JUDGE_NAMES_SQL = "SELECT id, name FROM llm_models WHERE id = ANY(:ids)"

# Most frequent judge model per evaluation config, from the judge runs that
# produced the rows (fallback when the project config carries no judge_model).
_CONFIG_JUDGES_SQL = """
SELECT config_id, judge_model_id FROM (
    SELECT COALESCE(te.evaluation_config_id, '') AS config_id, jr.judge_model_id, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY COALESCE(te.evaluation_config_id, '') ORDER BY COUNT(*) DESC, jr.judge_model_id) AS rn
    FROM task_evaluations te
    JOIN evaluation_runs r ON r.id = te.evaluation_id
    JOIN evaluation_judge_runs jr ON jr.id = te.judge_run_id
    WHERE r.project_id = :project_id AND r.status = 'completed' AND jr.judge_model_id IS NOT NULL
    GROUP BY 1, 2
) ranked WHERE rn = 1
"""


def model_is_public(model_id: str, catalog: Optional[Dict[str, Any]]) -> bool:
    """The hidden-model rule of every published report: a model with a
    catalog row shows when it is official or public; one without a row shows
    unless it is a custom (``custom-``) endpoint. ``catalog`` is the row's
    ``is_official`` / ``is_public`` mapping, or None without a row."""
    if catalog is None:
        return not str(model_id).startswith("custom-")
    return catalog.get("is_official") is True or catalog.get("is_public") is True


def hidden_model_ids(db: Session, model_ids: Iterable[str]) -> set:
    """The ids among ``model_ids`` a published report must not show (see
    :func:`model_is_public`)."""
    ids = sorted({str(m) for m in model_ids if m})
    if not ids:
        return set()
    rows = db.execute(
        text("SELECT id, is_official, is_public FROM llm_models WHERE id = ANY(:ids)"), {"ids": ids}
    ).mappings().all()
    catalog = {r["id"]: dict(r) for r in rows}
    return {m for m in ids if not model_is_public(m, catalog.get(m))}


def _model_label(model_id: str, catalog_name: Optional[str]) -> str:
    if catalog_name:
        return catalog_name
    # "provider/Model-Name" → "Model-Name"
    return model_id.split("/")[-1]


def _f(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _empty_bins(n: int) -> List[int]:
    return [0] * n


def _rate(part: int, whole: int) -> Optional[float]:
    return None if not whole else part / whole


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

# Keys that describe when and on which build a snapshot was computed rather
# than what it holds; they stay out of ``snapshot_sha256``.
_UNHASHED_TOP_LEVEL = ("generated_at",)
_UNHASHED_REPRODUCIBILITY = ("platform", "snapshot_sha256")

# Significant digits floats are rounded to before hashing, so a mean that
# Postgres sums in another order (last-bit noise) hashes the same.
_HASH_FLOAT_DIGITS = 12


def _hashable(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
        rounded = float(f"{value:.{_HASH_FLOAT_DIGITS}g}")
        # 2.0 and 2 are the same number; hash them the same way.
        return int(rounded) if rounded.is_integer() else rounded
    if isinstance(value, dict):
        return {str(k): _hashable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hashable(v) for v in value]
    return str(value)


def canonical_snapshot_json(snapshot: Dict[str, Any]) -> str:
    """The canonical JSON ``snapshot_sha256`` is computed over: the snapshot
    without ``generated_at``, ``reproducibility.platform`` and the hash
    itself, keys sorted, no whitespace, floats rounded to 12 significant
    digits. A rebuild over unchanged data therefore gives the same text,
    whenever and on whichever build it runs."""
    body = {k: v for k, v in snapshot.items() if k not in _UNHASHED_TOP_LEVEL}
    repro = body.get("reproducibility")
    if isinstance(repro, dict):
        body["reproducibility"] = {k: v for k, v in repro.items() if k not in _UNHASHED_REPRODUCIBILITY}
    return json.dumps(_hashable(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_sha256(snapshot: Dict[str, Any]) -> str:
    """SHA-256 (hex) of :func:`canonical_snapshot_json`."""
    return hashlib.sha256(canonical_snapshot_json(snapshot).encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    text_ = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text_.encode("utf-8")).hexdigest()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _bounded(value: Any, max_bytes: int) -> Dict[str, Any]:
    """A free-form JSON document as ``{"sha256", "content"}``; the content is
    left out (``truncated``) when it is larger than ``max_bytes``, so one
    oversized manifest cannot bloat every report view."""
    text_ = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    out: Dict[str, Any] = {"sha256": hashlib.sha256(text_.encode("utf-8")).hexdigest()}
    if len(text_.encode("utf-8")) <= max_bytes:
        out["content"] = value
    else:
        out["truncated"] = True
    return out


# ---------------------------------------------------------------------------
# Data: variant designs and import provenance
# ---------------------------------------------------------------------------

_DESIGNS_SQL = """
SELECT vd.key, vd.version, vd.status, vd.content_hash, vd.frozen_at, vd.spec, vd.provenance,
       COUNT(t.id) AS task_count,
       COUNT(DISTINCT t.variant_unit) AS unit_count,
       COUNT(DISTINCT t.variant_cell) AS cell_count
FROM variant_designs vd
LEFT JOIN tasks t ON t.project_id = vd.project_id AND t.variant_design = vd.key
WHERE vd.project_id = :project_id
GROUP BY vd.id
ORDER BY vd.key
"""

# Completed imports that wrote (or would have written) the project's data;
# merge previews write nothing and are left out.
_IMPORTS_SQL = """
SELECT ij.id, ij.format, ij.payload_sha256, ij.updated_at,
       ij.duplicate_of_job_id IS NOT NULL AS no_op,
       ij.source_manifest->'payload'->>'byte_size' AS byte_size,
       ij.source_manifest->'import'->>'mode' AS mode,
       ij.source_manifest->'declared' AS declared,
       (SELECT COUNT(*) FROM import_job_tasks jt WHERE jt.import_job_id = ij.id) AS task_count
FROM import_jobs ij
WHERE ij.project_id = :project_id AND ij.status = 'completed'
  AND COALESCE(ij.source_manifest->'import'->>'mode', '') <> 'merge_preview'
ORDER BY ij.created_at, ij.id
LIMIT :limit
"""

_IMPORT_TOTAL_SQL = """
SELECT COUNT(*) FROM import_jobs ij
WHERE ij.project_id = :project_id AND ij.status = 'completed'
  AND COALESCE(ij.source_manifest->'import'->>'mode', '') <> 'merge_preview'
"""

# Imports listed per report; a project imported thousands of times keeps the
# total and the first ones.
MAX_IMPORTS = 200
# Largest declared manifest or design provenance copied into a report.
MAX_FREE_JSON_BYTES = 16 * 1024
# Levels listed per factor.
MAX_FACTOR_LEVELS = 50


def _design_summary(spec: Dict[str, Any]) -> Dict[str, Any]:
    factors = []
    for f in spec.get("factors") or []:
        if not isinstance(f, dict):
            continue
        levels = f.get("levels") if isinstance(f.get("levels"), list) else None
        factors.append({
            "name": f.get("name"),
            "type": f.get("type"),
            "role": f.get("role", "manipulated"),
            "source": f.get("source", "task"),
            "varies": f.get("varies", "within_unit"),
            "levels": levels[:MAX_FACTOR_LEVELS] if levels is not None else None,
            "level_count": len(levels) if levels is not None else None,
        })
    outcomes = [o.get("name") for o in spec.get("outcomes") or [] if isinstance(o, dict) and o.get("name")]
    unit = spec.get("unit") if isinstance(spec.get("unit"), dict) else {}
    return {
        "title": spec.get("title"),
        "unit": unit.get("name"),
        "factors": factors,
        "outcomes": outcomes,
        "declared_cells": len(spec["cells"]) if isinstance(spec.get("cells"), list) else None,
    }


def _build_data_section(db: Session, params: Dict[str, Any], task_count: int) -> Dict[str, Any]:
    designs = []
    for r in db.execute(text(_DESIGNS_SQL), params).mappings().all():
        spec = r["spec"] if isinstance(r["spec"], dict) else {}
        designs.append({
            "key": r["key"],
            "version": int(r["version"]),
            "status": r["status"],
            "content_hash": r["content_hash"],
            "spec_sha256": _sha256_json(spec),
            "frozen_at": _iso(r["frozen_at"]),
            "task_count": int(r["task_count"]),
            "unit_count": int(r["unit_count"]),
            "cell_count": int(r["cell_count"]),
            **_design_summary(spec),
            "provenance": _bounded(r["provenance"], MAX_FREE_JSON_BYTES) if r["provenance"] is not None else None,
        })

    imports = []
    for r in db.execute(text(_IMPORTS_SQL), {**params, "limit": MAX_IMPORTS}).mappings().all():
        byte_size = r["byte_size"]
        imports.append({
            "format": r["format"],
            "mode": r["mode"],
            "completed_at": _iso(r["updated_at"]),
            "payload_sha256": r["payload_sha256"],
            "byte_size": int(byte_size) if byte_size not in (None, "") else None,
            "task_count": int(r["task_count"]),
            "no_op": bool(r["no_op"]),
            "declared_manifest": _bounded(r["declared"], MAX_FREE_JSON_BYTES) if r["declared"] is not None else None,
        })
    import_total = int(db.execute(text(_IMPORT_TOTAL_SQL), params).scalar() or 0)

    return {
        "task_count": task_count,
        "variant_designs": designs,
        "imports": imports,
        "import_count": import_total,
        "imports_truncated": import_total > len(imports),
    }


# ---------------------------------------------------------------------------
# Generation: per-model counts, structures and rates
# ---------------------------------------------------------------------------

_PARSE_ATTEMPTED = "('success', 'failed', 'validation_error')"
_PARSE_FAILED = "('failed', 'validation_error')"

_GENERATION_SQL = f"""
SELECT g.model_id,
       COUNT(*) AS generations,
       COUNT(*) FILTER (WHERE g.status = 'failed') AS failed,
       COUNT(DISTINCT g.task_id) AS tasks,
       MAX(g.run_index) + 1 AS max_runs,
       COUNT(*) FILTER (WHERE g.status <> 'failed' AND g.refusal) AS refusals,
       COUNT(*) FILTER (WHERE g.status <> 'failed' AND g.truncated) AS truncated,
       COUNT(*) FILTER (WHERE g.status <> 'failed' AND g.retried) AS retried,
       COUNT(*) FILTER (WHERE g.parse_status IN {_PARSE_ATTEMPTED}) AS parse_attempted,
       COUNT(*) FILTER (WHERE g.parse_status IN {_PARSE_FAILED}) AS parse_failed,
       COUNT(*) FILTER (WHERE g.request_sha256 IS NOT NULL) AS with_request
FROM generations g
JOIN response_generations rg ON rg.id = g.generation_id
WHERE rg.project_id = :project_id
GROUP BY g.model_id
"""

_STRUCTURES_SQL = """
SELECT g.model_id, COALESCE(rg.structure_key, '') AS structure_key, COUNT(*) AS n
FROM generations g
JOIN response_generations rg ON rg.id = g.generation_id
WHERE rg.project_id = :project_id
GROUP BY 1, 2
"""


def _generation_rates(r: Dict[str, Any]) -> Dict[str, Any]:
    generations = int(r["generations"])
    failed = int(r["failed"])
    completed = generations - failed
    tasks = int(r["tasks"])
    return {
        "generations": generations,
        "completed": completed,
        "failed": failed,
        "tasks": tasks,
        "runs_per_task": (generations / tasks) if tasks else None,
        "max_runs_per_task": int(r["max_runs"]) if r["max_runs"] is not None else None,
        "refusal_rate": _rate(int(r["refusals"]), completed),
        "truncation_rate": _rate(int(r["truncated"]), completed),
        "retry_rate": _rate(int(r["retried"]), completed),
        "parse_attempted": int(r["parse_attempted"]),
        "parse_failure_rate": _rate(int(r["parse_failed"]), int(r["parse_attempted"])),
        "request_record_share": _rate(int(r["with_request"]), generations),
    }


def _build_generation_section(
    db: Session, params: Dict[str, Any], subject_for_model
) -> Dict[str, Any]:
    rows = db.execute(text(_GENERATION_SQL), params).mappings().all()
    structure_rows = db.execute(text(_STRUCTURES_SQL), params).mappings().all()

    structures_by_model: Dict[str, Dict[str, int]] = {}
    for r in structure_rows:
        structures_by_model.setdefault(r["model_id"], {})[r["structure_key"]] = int(r["n"])

    models = []
    totals = {k: 0 for k in ("generations", "failed", "refusals", "truncated", "retried",
                             "parse_attempted", "parse_failed", "with_request")}
    structure_totals: Dict[str, int] = {}
    for r in rows:
        subject = subject_for_model(r["model_id"])
        if subject is None:
            continue
        structures = structures_by_model.get(r["model_id"], {})
        models.append({
            "model_id": subject["id"],
            "label": subject["label"],
            "provider": subject.get("provider"),
            **_generation_rates(r),
            "structures": [
                {"key": key or None, "generations": n}
                for key, n in sorted(structures.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        })
        for key in totals:
            totals[key] += int(r[key])
        for key, n in structures.items():
            structure_totals[key] = structure_totals.get(key, 0) + n
    models.sort(key=lambda m: (m["label"].lower(), m["model_id"]))

    completed = totals["generations"] - totals["failed"]
    return {
        "models": models,
        "structures": [
            {"key": key or None, "generations": n}
            for key, n in sorted(structure_totals.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "totals": {
            "generations": totals["generations"],
            "completed": completed,
            "failed": totals["failed"],
            "refusal_rate": _rate(totals["refusals"], completed),
            "truncation_rate": _rate(totals["truncated"], completed),
            "retry_rate": _rate(totals["retried"], completed),
            "parse_failure_rate": _rate(totals["parse_failed"], totals["parse_attempted"]),
            "request_record_share": _rate(totals["with_request"], totals["generations"]),
        },
    }


# ---------------------------------------------------------------------------
# Human evaluation: Likert ratings and preference comparisons
# ---------------------------------------------------------------------------

LIKERT_SCALE = [1, 2, 3, 4, 5]

_LIKERT_SQL = """
SELECT l.dimension, g.model_id, l.rating, COUNT(*) AS n
FROM likert_scale_evaluations l
JOIN human_evaluation_sessions s ON s.id = l.session_id
LEFT JOIN generations g ON g.id = l.response_id
WHERE s.project_id = :project_id
GROUP BY 1, 2, 3
"""

_PREFERENCE_SQL = """
SELECT ga.model_id AS model_a, gb.model_id AS model_b, p.winner, COUNT(*) AS n
FROM preference_rankings p
JOIN human_evaluation_sessions s ON s.id = p.session_id
LEFT JOIN generations ga ON ga.id = p.response_a_id
LEFT JOIN generations gb ON gb.id = p.response_b_id
WHERE s.project_id = :project_id
GROUP BY 1, 2, 3
"""

# Evaluators per session type, counting only sessions that rated something.
_EVALUATORS_SQL = """
SELECT s.session_type, COUNT(DISTINCT s.evaluator_id) AS evaluators
FROM human_evaluation_sessions s
WHERE s.project_id = :project_id
  AND (EXISTS (SELECT 1 FROM likert_scale_evaluations l WHERE l.session_id = s.id)
       OR EXISTS (SELECT 1 FROM preference_rankings p WHERE p.session_id = s.id))
GROUP BY s.session_type
"""

_DIMENSIONS_SQL = """
SELECT dimension_name, description, display_order
FROM human_evaluation_dimensions
WHERE project_id = :project_id
"""


def _rating_stats(counts: Dict[int, int]) -> Dict[str, Any]:
    n = sum(counts.values())
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "distribution": [0] * len(LIKERT_SCALE)}
    mean = sum(r * c for r, c in counts.items()) / n
    std = None
    if n > 1:
        std = math.sqrt(sum(c * (r - mean) ** 2 for r, c in counts.items()) / (n - 1))
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "distribution": [int(counts.get(r, 0)) for r in LIKERT_SCALE],
    }


def _build_human_evaluation_section(
    db: Session, params: Dict[str, Any], subject_for_model, model_visible
) -> Dict[str, Any]:
    evaluators = {r["session_type"]: int(r["evaluators"]) for r in db.execute(text(_EVALUATORS_SQL), params).mappings().all()}
    dim_meta = {
        r["dimension_name"]: r for r in db.execute(text(_DIMENSIONS_SQL), params).mappings().all()
    }

    # ---- Likert ------------------------------------------------------------
    overall: Dict[str, Dict[int, int]] = {}
    per_model: Dict[str, Dict[str, Dict[int, int]]] = {}
    for r in db.execute(text(_LIKERT_SQL), params).mappings().all():
        model_id = r["model_id"]
        # A rating of a hidden model's answer stays out of every number.
        if model_id is not None and not model_visible(model_id):
            continue
        rating, n = int(r["rating"]), int(r["n"])
        overall.setdefault(r["dimension"], {})[rating] = overall.get(r["dimension"], {}).get(rating, 0) + n
        if model_id is not None:
            cell = per_model.setdefault(r["dimension"], {}).setdefault(model_id, {})
            cell[rating] = cell.get(rating, 0) + n

    def _dim_order(name: str) -> Tuple[int, str]:
        meta = dim_meta.get(name)
        return (int(meta["display_order"]) if meta and meta["display_order"] is not None else 10**6, name)

    dimensions = []
    for name in sorted(overall, key=_dim_order):
        by_model = []
        for model_id, counts in per_model.get(name, {}).items():
            subject = subject_for_model(model_id)
            if subject is None:
                continue
            stats = _rating_stats(counts)
            by_model.append({"model_id": subject["id"], "label": subject["label"], "n": stats["n"],
                             "mean": stats["mean"], "std": stats["std"]})
        by_model.sort(key=lambda m: (-(m["mean"] or 0), m["label"].lower(), m["model_id"]))
        meta = dim_meta.get(name)
        dimensions.append({
            "dimension": name,
            "description": meta["description"] if meta else None,
            **_rating_stats(overall[name]),
            "by_model": by_model,
        })

    # ---- preference ------------------------------------------------------------
    pairs: Dict[Tuple[str, str], Dict[str, int]] = {}
    tally: Dict[str, Dict[str, int]] = {}
    comparisons = 0
    ties = 0
    for r in db.execute(text(_PREFERENCE_SQL), params).mappings().all():
        a, b, winner, n = r["model_a"], r["model_b"], r["winner"], int(r["n"])
        # A comparison with a hidden model is left out whole: its opponent's
        # record would otherwise tell how the hidden model did.
        if (a is not None and not model_visible(a)) or (b is not None and not model_visible(b)):
            continue
        comparisons += n
        if winner == "tie":
            ties += n
        for me, other, won in ((a, b, winner == "a"), (b, a, winner == "b")):
            if me is None:
                continue
            t = tally.setdefault(me, {"comparisons": 0, "wins": 0, "losses": 0, "ties": 0})
            t["comparisons"] += n
            if winner == "tie":
                t["ties"] += n
            elif won:
                t["wins"] += n
            else:
                t["losses"] += n
        if a is not None and b is not None and a != b:
            first, second = sorted((a, b))
            cell = pairs.setdefault((first, second), {"first_wins": 0, "second_wins": 0, "ties": 0})
            if winner == "tie":
                cell["ties"] += n
            elif (winner == "a") == (a == first):
                cell["first_wins"] += n
            else:
                cell["second_wins"] += n

    pref_models = []
    for model_id, t in tally.items():
        subject = subject_for_model(model_id)
        if subject is None:
            continue
        pref_models.append({
            "model_id": subject["id"],
            "label": subject["label"],
            **t,
            "win_rate": _rate(t["wins"], t["comparisons"]),
        })
    pref_models.sort(key=lambda m: (-(m["win_rate"] or 0), m["label"].lower(), m["model_id"]))
    pref_pairs = []
    for (first, second), cell in sorted(pairs.items()):
        s1, s2 = subject_for_model(first), subject_for_model(second)
        if s1 is None or s2 is None:
            continue
        pref_pairs.append({
            "model_a": s1["id"], "label_a": s1["label"],
            "model_b": s2["id"], "label_b": s2["label"],
            "a_wins": cell["first_wins"], "b_wins": cell["second_wins"], "ties": cell["ties"],
        })

    return {
        "likert": {
            "evaluator_count": evaluators.get("likert", 0),
            "rating_count": sum(d["n"] for d in dimensions),
            "scale": LIKERT_SCALE,
            "dimensions": dimensions,
        },
        "preference": {
            "evaluator_count": evaluators.get("preference", 0),
            "comparisons": comparisons,
            "ties": ties,
            "models": pref_models,
            "pairs": pref_pairs,
        },
    }


# ---------------------------------------------------------------------------
# Reproducibility: versions and hashes
# ---------------------------------------------------------------------------

# The parameter snapshots the judge runs of each evaluation config used, per
# generation model so the samples of a hidden model can be left out.
_CONFIG_PARAMS_SQL = """
SELECT COALESCE(te.evaluation_config_id, '') AS config_id, jr.judge_model_id,
       jr.metric_parameters_snapshot AS parameters, g.model_id, COUNT(*) AS n
FROM task_evaluations te
JOIN evaluation_runs r ON r.id = te.evaluation_id
JOIN evaluation_judge_runs jr ON jr.id = te.judge_run_id
LEFT JOIN generations g ON g.id = te.generation_id
WHERE r.project_id = :project_id AND r.status = 'completed'
GROUP BY 1, 2, 3, 4
"""


def _parameter_model_ids(parameters: Any) -> set:
    """The judge model ids a judge run's parameter snapshot names: its
    ``judge_model`` and each ``judges[].judge_model_id`` (the worker stores
    the config's ``metric_parameters`` as is)."""
    if not isinstance(parameters, dict):
        return set()
    ids = {parameters.get("judge_model")}
    judges = parameters.get("judges")
    if isinstance(judges, list):
        ids |= {j.get("judge_model_id") for j in judges if isinstance(j, dict)}
    return {str(m) for m in ids if m}


def _platform_versions() -> Dict[str, Any]:
    from app_version import app_version
    from core_version import CORE_API_VERSION

    return {"app_version": app_version(), "core_api_version": CORE_API_VERSION}


def _build_reproducibility_section(
    db: Session,
    params: Dict[str, Any],
    project: Any,
    *,
    models: List[Dict[str, Any]],
    configs: List[Dict[str, Any]],
    cfg_entries: Dict[str, Dict[str, Any]],
    data: Dict[str, Any],
    generation: Dict[str, Any],
    model_visible,
    hidden_judges,
) -> Dict[str, Any]:
    label_config = getattr(project, "label_config", None) if project else None

    gen_cfg = (getattr(project, "generation_config", None) or {}) if project else {}
    defined = gen_cfg.get("prompt_structures") if isinstance(gen_cfg, dict) else None
    defined = defined if isinstance(defined, dict) else {}
    structures = []
    for s in generation["structures"]:
        key = s["key"]
        definition = defined.get(key) if key else None
        structures.append({
            "key": key,
            "generations": s["generations"],
            # The definition as stored now; edited after the run, it differs
            # from what generated the answers, which the hash makes visible.
            "definition_sha256": _sha256_json(definition) if definition is not None else None,
        })

    param_rows = db.execute(text(_CONFIG_PARAMS_SQL), params).mappings().all()
    hidden = hidden_judges(
        {r["judge_model_id"] for r in param_rows}
        | {m for r in param_rows for m in _parameter_model_ids(r["parameters"])}
    )
    runs_by_key: Dict[Tuple[str, Optional[str], Optional[str]], Dict[str, Any]] = {}
    for r in param_rows:
        # Samples of a hidden model's answers are not counted.
        if r["model_id"] is not None and not model_visible(r["model_id"]):
            continue
        parameters = r["parameters"]
        digest = _sha256_json(parameters) if parameters is not None else None
        # A hidden judge is not named (the same rule as ``configs``), and
        # parameters naming a hidden model keep only their hash.
        judge = None if r["judge_model_id"] in hidden else r["judge_model_id"]
        if r["judge_model_id"] in hidden or _parameter_model_ids(parameters) & hidden:
            parameters = None
        key = (r["config_id"], judge, digest)
        run = runs_by_key.setdefault(key, {
            # Judges are named as in ``configs`` (judge_model, judge_label).
            "judge_model": judge,
            "samples": 0,
            "parameters_sha256": digest,
            "parameters": parameters,
        })
        run["samples"] += int(r["n"])
    params_by_config: Dict[str, List[Dict[str, Any]]] = {}
    for (config_id, _judge, _digest), run in runs_by_key.items():
        params_by_config.setdefault(config_id, []).append(run)
    evaluation_configs = []
    seen = set()
    for c in configs:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        entry = cfg_entries.get(c["id"]) or {}
        runs = sorted(
            params_by_config.get(c["id"], []),
            key=lambda p: (-p["samples"], p["judge_model"] or "", p["parameters_sha256"] or ""),
        )
        evaluation_configs.append({
            "id": c["id"],
            "metric": entry.get("metric") or c["metric"],
            "name": entry.get("display_name"),
            "judge_runs": runs,
        })
    evaluation_configs.sort(key=lambda c: c["id"])

    analysis_runs = []
    eligible_runs = report_analysis_runs(db, params["project_id"])
    member_only = analysis_runs_member_only(db, eligible_runs)
    for r in eligible_runs:
        analysis_runs.append({
            "id": r["id"],
            "name": r["name"],
            "spec_hash": r["spec_hash"],
            "spec_version": r["spec_version"],
            "engine_version": r["engine_version"],
            "frame_hash": r["frame_hash"],
            "frame_sha256": r["frame_sha256"],
            "frame_rows": r["frame_rows"],
            "estimates_count": int(r["estimates_count"] or 0),
            "library_versions": r["library_versions"],
            "lockfile_sha256": r["lockfile_sha256"],
            "seed": int(r["seed"]) if r["seed"] is not None else None,
            "completed_at": _iso(r["completed_at"]),
            "member_only": member_only[r["id"]],
        })

    return {
        "platform": _platform_versions(),
        "label_config": {
            "version": getattr(project, "label_config_version", None) if project else None,
            "sha256": hashlib.sha256(label_config.encode("utf-8")).hexdigest() if label_config else None,
        },
        "models": [
            {"id": m["id"], "provider": m.get("provider"), "label": m["label"]} for m in models
        ],
        "prompt_structures": structures,
        "evaluation_configs": evaluation_configs,
        "variant_designs": [
            {"key": d["key"], "version": d["version"], "status": d["status"],
             "content_hash": d["content_hash"], "spec_sha256": d["spec_sha256"]}
            for d in data["variant_designs"]
        ],
        "imports": [
            {"payload_sha256": i["payload_sha256"], "completed_at": i["completed_at"], "no_op": i["no_op"]}
            for i in data["imports"]
        ],
        "analysis_runs": analysis_runs,
        "snapshot_sha256": None,
    }


# ---------------------------------------------------------------------------
# Analyses: the runs and exhibits the author chose
# ---------------------------------------------------------------------------

# Completed analysis runs of the project, oldest first. A report takes only
# runs that read no further project (``report_analysis_runs``).
_ANALYSIS_RUNS_SQL = """
SELECT id, name, spec_hash, spec_version, engine_version, frame_hash, frame_sha256,
       frame_rows, estimates_count, library_versions, lockfile_sha256, seed, completed_at,
       warnings, normalized_spec, fits, resolved_inputs, codes
FROM analysis_runs
WHERE project_id = :project_id AND status = 'completed'
ORDER BY completed_at, id
"""

_RUN_STATES_SQL = """
SELECT id, project_id, status, normalized_spec FROM analysis_runs WHERE id = ANY(:ids)
"""

ANALYSIS_EXHIBIT_TYPES = ("forest", "table")
EXHIBIT_FILTER_KEYS = ("estimands", "contrasts", "families", "systems")
# The frame columns holding a system key (or the bare model id).
SYSTEM_COLUMNS = ("system", "model_id")
_PARAMETER = re.compile(r"(?:^|:)([^\[\]:]+)\[([^\[\]]*)\]")
MAX_REPORT_ANALYSIS_RUNS = 10
MAX_RUN_EXHIBITS = 12
MAX_FILTER_VALUES = 500
MAX_FILTER_VALUE_LENGTH = 1000
MAX_ANALYSIS_TITLE_LENGTH = 300
MAX_ANALYSIS_TEXT_LENGTH = 20000
# Estimates one run contributes to a report (the union of its exhibits);
# beyond it the run keeps the first ones in engine order and is ``truncated``.
MAX_REPORT_ESTIMATES_PER_RUN = 1000
_EXHIBIT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Why a run an Analyses entry names is not in the snapshot.
RUN_NOT_FOUND = "not_found"            # no run of this project with that id
RUN_NOT_COMPLETED = "not_completed"
RUN_READS_OTHER_PROJECTS = "reads_other_projects"


def report_analysis_runs(db: Session, project_id: str) -> List[Dict[str, Any]]:
    """The completed analysis runs of a project a report may show, oldest
    first: those that read no further project, neither through
    ``inputs.projects`` nor through a stored lookup table of another project
    (``AnalysisRun.input_projects``), because a report must not publish
    another project's numbers."""
    from models import AnalysisRun

    rows = db.execute(text(_ANALYSIS_RUNS_SQL), {"project_id": project_id}).mappings().all()
    return [dict(r) for r in rows if not AnalysisRun.input_projects(r["normalized_spec"], project_id)]


def analysis_run_problems(db: Session, project_id: str, run_ids: Iterable[str]) -> Dict[str, str]:
    """For each of ``run_ids`` that a report of ``project_id`` cannot show,
    the reason (``RUN_NOT_FOUND``, ``RUN_NOT_COMPLETED`` or
    ``RUN_READS_OTHER_PROJECTS``); runs it can show are left out. A run of
    another project counts as not found, so ids cannot be probed."""
    from models import AnalysisRun

    ids = sorted({str(r) for r in run_ids if r})
    if not ids:
        return {}
    found = {r["id"]: r for r in db.execute(text(_RUN_STATES_SQL), {"ids": ids}).mappings().all()}
    problems: Dict[str, str] = {}
    for run_id in ids:
        row = found.get(run_id)
        if row is None or row["project_id"] != project_id:
            problems[run_id] = RUN_NOT_FOUND
        elif row["status"] != "completed":
            problems[run_id] = RUN_NOT_COMPLETED
        elif AnalysisRun.input_projects(row["normalized_spec"], project_id):
            problems[run_id] = RUN_READS_OTHER_PROJECTS
    return problems


class AnalysesSectionError(ValueError):
    """``content.sections.analyses`` does not have the expected shape."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _text_field(value: Any, where: str, limit: int, errors: List[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{where}: must be a string")
        return None
    if len(value) > limit:
        errors.append(f"{where}: at most {limit} characters")
        return None
    return value or None


def _filters(raw: Any, where: str, errors: List[str]) -> Dict[str, List[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object")
        return {}
    out: Dict[str, List[str]] = {}
    for key, values in raw.items():
        if key not in EXHIBIT_FILTER_KEYS:
            errors.append(f"{where}.{key}: unknown filter (known: {', '.join(EXHIBIT_FILTER_KEYS)})")
            continue
        if values is None:
            continue
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            errors.append(f"{where}.{key}: must be a list of strings")
            continue
        if len(values) > MAX_FILTER_VALUES:
            errors.append(f"{where}.{key}: at most {MAX_FILTER_VALUES} values")
            continue
        if any(len(v) > MAX_FILTER_VALUE_LENGTH for v in values):
            errors.append(f"{where}.{key}: values of at most {MAX_FILTER_VALUE_LENGTH} characters")
            continue
        if values:
            out[key] = sorted(set(values))
    return out


def _exhibit(raw: Any, where: str, errors: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object")
        return None
    before = len(errors)
    exhibit_id = raw.get("id")
    if not isinstance(exhibit_id, str) or not _EXHIBIT_ID.match(exhibit_id):
        errors.append(f"{where}.id: 1 to 64 letters, digits, '-' or '_'")
    kind = raw.get("type")
    if kind not in ANALYSIS_EXHIBIT_TYPES:
        errors.append(f"{where}.type: one of {', '.join(ANALYSIS_EXHIBIT_TYPES)}")
    band = raw.get("band", 0)
    if band is not None and (isinstance(band, bool) or not isinstance(band, int) or band < 0):
        errors.append(f"{where}.band: a bound set index (0 or more) or null")
    title = _text_field(raw.get("title"), f"{where}.title", MAX_ANALYSIS_TITLE_LENGTH, errors)
    caption = _text_field(raw.get("caption"), f"{where}.caption", MAX_ANALYSIS_TEXT_LENGTH, errors)
    filters = _filters(raw.get("filters"), f"{where}.filters", errors)
    if len(errors) > before:
        return None
    return {
        "id": exhibit_id,
        "type": kind,
        "title": title,
        "caption": caption,
        "filters": filters,
        # The equivalence bound set a forest draws (``tost`` index); null
        # draws none. A table ignores it.
        "band": band if kind == "forest" else None,
    }


def parse_analyses_section(raw: Any, *, strict: bool = False) -> Dict[str, Any]:
    """``content.sections.analyses`` in its normalized form::

        {"visible": bool, "custom_text": str | None,
         "runs": [{"run_id", "title", "text",
                   "exhibits": [{"id", "type": "forest" | "table", "title",
                                 "caption", "filters": {"estimands",
                                 "contrasts", "families", "systems": [str]},
                                 "band": int | None}]}]}

    Each filter is a list of values (sorted, without repeats); an absent or
    empty one does not restrict. ``strict`` raises
    :class:`AnalysesSectionError` listing every problem (the editor's save);
    otherwise entries with problems are left out (reading stored content)."""
    errors: List[str] = []
    out: Dict[str, Any] = {"visible": True, "custom_text": None, "runs": []}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        if strict:
            raise AnalysesSectionError(["analyses: must be an object"])
        return out
    visible = raw.get("visible", True)
    if not isinstance(visible, bool):
        errors.append("analyses.visible: must be true or false")
        visible = True
    out["visible"] = visible
    out["custom_text"] = _text_field(raw.get("custom_text"), "analyses.custom_text", MAX_ANALYSIS_TEXT_LENGTH, errors)
    runs = raw.get("runs") or []
    if not isinstance(runs, list):
        errors.append("analyses.runs: must be a list")
        runs = []
    if len(runs) > MAX_REPORT_ANALYSIS_RUNS:
        errors.append(f"analyses.runs: at most {MAX_REPORT_ANALYSIS_RUNS} runs")
        runs = runs[:MAX_REPORT_ANALYSIS_RUNS]
    seen_runs: set = set()
    for i, run in enumerate(runs):
        where = f"analyses.runs[{i}]"
        before = len(errors)
        if not isinstance(run, dict):
            errors.append(f"{where}: must be an object")
            continue
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id or len(run_id) > 64:
            errors.append(f"{where}.run_id: an analysis run id")
            continue
        if run_id in seen_runs:
            errors.append(f"{where}.run_id: run {run_id} is listed twice")
            continue
        seen_runs.add(run_id)
        title = _text_field(run.get("title"), f"{where}.title", MAX_ANALYSIS_TITLE_LENGTH, errors)
        body = _text_field(run.get("text"), f"{where}.text", MAX_ANALYSIS_TEXT_LENGTH, errors)
        raw_exhibits = run.get("exhibits") or []
        if not isinstance(raw_exhibits, list):
            errors.append(f"{where}.exhibits: must be a list")
            raw_exhibits = []
        if len(raw_exhibits) > MAX_RUN_EXHIBITS:
            errors.append(f"{where}.exhibits: at most {MAX_RUN_EXHIBITS} exhibits")
            raw_exhibits = raw_exhibits[:MAX_RUN_EXHIBITS]
        exhibits: List[Dict[str, Any]] = []
        seen_exhibits: set = set()
        for j, raw_exhibit in enumerate(raw_exhibits):
            exhibit = _exhibit(raw_exhibit, f"{where}.exhibits[{j}]", errors)
            if exhibit is None:
                continue
            if exhibit["id"] in seen_exhibits:
                errors.append(f"{where}.exhibits[{j}].id: {exhibit['id']} is used twice")
                continue
            seen_exhibits.add(exhibit["id"])
            exhibits.append(exhibit)
        if strict and len(errors) > before:
            continue
        out["runs"].append({"run_id": run_id, "title": title, "text": body, "exhibits": exhibits})
    if strict and errors:
        raise AnalysesSectionError(errors)
    return out


def estimate_system(estimate: Dict[str, Any]) -> Optional[str]:
    """The system an estimate is scoped to: its ``system`` (or ``model_id``)
    scope value, or None for a pooled estimate or another scope."""
    values = estimate.get("scope_values")
    if isinstance(values, dict):
        for column in SYSTEM_COLUMNS:
            value = values.get(column)
            if value is not None:
                return str(value)
    return None


def _parameter_levels(names: Iterable[Any]) -> set:
    """The (prefix, level) pairs the parameter names ``<prefix>[<level>]``
    name, also inside an interaction ``a[x]:b[y]``."""
    return {(m.group(1), m.group(2)) for n in names if isinstance(n, str) for m in _PARAMETER.finditer(n)}


def _declared_references(terms: Any) -> Dict[str, str]:
    """The references the ``terms`` of a spec declare (factor -> level)."""
    out: Dict[str, str] = {}
    for term in terms if isinstance(terms, list) else []:
        if isinstance(term, dict) and term.get("dummies") and term.get("reference") is not None:
            out[str(term["dummies"])] = str(term["reference"])
        elif isinstance(term, dict):
            out.update(_declared_references(term.get("interact")))
    return out


def _weight_keys(contrast: Dict[str, Any]) -> Tuple[List[str], set]:
    """(parameter names, system levels) a spec contrast refers to: the keys
    of its weights (of numerator and denominator for a ratio), and for an
    average marginal effect over a system column its level and reference."""
    if contrast.get("kind") == "ame":
        if contrast.get("column") in SYSTEM_COLUMNS:
            return [], {str(contrast[k]) for k in ("level", "reference") if contrast.get(k) is not None}
        return [], set()
    parts = [contrast.get("numerator"), contrast.get("denominator")] if contrast.get("kind") == "ratio" else [contrast]
    return [k for part in parts if isinstance(part, dict) and isinstance(part.get("weights"), dict)
            for k in part["weights"]], set()


def estimate_systems(estimate: Dict[str, Any], spec: Any, fits: Any = None) -> set:
    """The systems an estimate involves: the one it is scoped to plus every
    system level its contrast or joint test names in the run's normalized
    ``spec``: the weight keys of a listed contrast (the contrast id itself
    when the spec lists none, as for ``terms``), the rows, parameters (as
    matched against its fit's parameters in ``fits``) or contrasts of a
    joint test, and the level and reference of a paired treatment over a
    system column. A ``system`` or ``model_id`` parameter is measured
    against the reference level of its dummy coding, which is involved too:
    the one its fit recorded (``references``), or for a run whose fits
    record none the one the spec declares. Bradley-Terry strengths
    (``strength[<level>]`` and its reference) count as systems when the fit
    recorded ``players_are_systems``. The editor's preview applies the same
    rule (``estimateSystems`` in
    ``services/frontend/src/lib/reports/analyses.ts``)."""
    systems: set = set()
    scoped = estimate_system(estimate)
    if scoped is not None:
        systems.add(scoped)
    estimands = spec.get("estimands") if isinstance(spec, dict) else None
    est = next((e for e in estimands or [] if isinstance(e, dict) and e.get("id") == estimate.get("estimand_id")), {})
    treat = est.get("treatment")
    if isinstance(treat, dict) and treat.get("factor") in SYSTEM_COLUMNS:
        systems |= {str(treat[k]) for k in ("level", "reference") if treat.get(k) is not None}
    listed = est.get("contrasts") if isinstance(est.get("contrasts"), list) else []
    by_id = {c.get("id"): c for c in listed if isinstance(c, dict)}
    cid = estimate.get("contrast_id")
    fit = next((f for f in (fits if isinstance(fits, list) else []) if isinstance(f, dict)
                and f.get("estimand") == estimate.get("estimand_id") and f.get("scope") == estimate.get("scope")), None)
    if fit is not None and isinstance(fit.get("references"), dict):
        references = {str(k): str(v) for k, v in fit["references"].items() if v is not None}
    else:
        references = _declared_references(est.get("terms"))
    prefixes = set(SYSTEM_COLUMNS) | ({"strength"} if fit is not None and fit.get("players_are_systems") is True else set())
    names: List[Any] = []
    contrasts: List[Dict[str, Any]] = []
    test = None
    if estimate.get("kind") == "wald":
        test = next((t for t in est.get("joint_tests") or [] if isinstance(t, dict) and t.get("id") == cid), None)
    if test is None:
        if cid in by_id:
            contrasts.append(by_id[cid])
        else:
            names.append(cid)
    elif isinstance(test.get("rows"), list):
        names += [k for row in test["rows"] if isinstance(row, dict) for k in row]
    elif isinstance(test.get("parameters"), list):
        patterns = [p for p in test["parameters"] if isinstance(p, str)]
        names += [p for p in patterns if "*" not in p]
        compiled = [re.compile(".*".join(re.escape(part) for part in p.split("*")) + r"\Z") for p in patterns]
        if fit is not None:
            names += [n for n in fit.get("parameters") or [] if isinstance(n, str) and any(c.match(n) for c in compiled)]
    else:
        for ref in test.get("contrasts") or []:
            if ref in by_id:
                contrasts.append(by_id[ref])
            else:
                names.append(ref)
    for contrast in contrasts:
        keys, levels = _weight_keys(contrast)
        names += keys
        systems |= levels
    named = {(prefix, level) for prefix, level in _parameter_levels(names) if prefix in prefixes}
    return systems | {level for _, level in named} | {references[p] for p, _ in named if p in references}


def exhibit_selects(estimate: Dict[str, Any], filters: Dict[str, List[str]], systems: Iterable[str]) -> bool:
    """Whether an exhibit with ``filters`` shows ``estimate``, whose involved
    systems (:func:`estimate_systems`) are ``systems``: every given filter
    holds. Estimands and contrasts match ``estimand_id`` and
    ``contrast_id``; families match any family the estimate belongs to; a
    systems filter keeps an estimate exactly when it involves at least one
    system and all of them are listed, so a pooled estimate involving no
    system shows only without a systems filter. The editor's preview
    applies the same rule (``exhibitSelects`` in
    ``services/frontend/src/lib/reports/analyses.ts``)."""
    estimands = filters.get("estimands")
    if estimands and estimate.get("estimand_id") not in estimands:
        return False
    contrasts = filters.get("contrasts")
    if contrasts and estimate.get("contrast_id") not in contrasts:
        return False
    families = filters.get("families")
    if families:
        member = {estimate.get("family")} | {
            a.get("family") for a in estimate.get("adjustments") or [] if isinstance(a, dict)
        }
        if not member & set(families):
            return False
    allowed = filters.get("systems")
    if allowed:
        involved = set(systems)
        if not involved or not involved <= set(allowed):
            return False
    return True


_RUN_SCOPE_VALUES_SQL = """
SELECT DISTINCT run_id, scope_values FROM analysis_estimates
WHERE run_id = ANY(:ids) AND scope_values IS NOT NULL
"""


def _run_model_ids(run: Dict[str, Any], scope_values: Iterable[Any]) -> Optional[set]:
    """Every model id that may appear in a run: the models of its frame
    (``resolved_inputs.models``, the ``model_id`` values and the model part
    of every system key), every level its fits name (parameters,
    ``references``, Bradley-Terry ``players``) and every scope value of its
    estimates, each as the part before ``@``. None when the run does not
    record its frame's models (runs made before it did)."""
    resolved = run.get("resolved_inputs")
    models = resolved.get("models") if isinstance(resolved, dict) else None
    if not isinstance(models, list):
        return None
    values: set = {str(m) for m in models if m is not None}
    for fit in run.get("fits") if isinstance(run.get("fits"), list) else []:
        if not isinstance(fit, dict):
            continue
        values |= {level for _, level in _parameter_levels(fit.get("parameters") or [])}
        if isinstance(fit.get("references"), dict):
            values |= {str(v) for v in fit["references"].values() if v is not None}
        values |= {str(p) for p in fit.get("players") or [] if p is not None}
    for scope in scope_values:
        if isinstance(scope, dict):
            values |= {str(v) for v in scope.values() if v is not None}
    return {v.split("@", 1)[0] for v in values}


def analysis_runs_member_only(db: Session, runs: Iterable[Dict[str, Any]]) -> Dict[str, bool]:
    """For each run (rows of :func:`report_analysis_runs`), whether it is
    member-only: a hidden model (:func:`model_is_public`) may appear in it
    (:func:`_run_model_ids`), or which models do cannot be established. A
    public report never shows a member-only run."""
    runs = list(runs)
    if not runs:
        return {}
    scopes: Dict[str, List[Any]] = {}
    for row in db.execute(text(_RUN_SCOPE_VALUES_SQL), {"ids": [r["id"] for r in runs]}).mappings().all():
        scopes.setdefault(row["run_id"], []).append(row["scope_values"])
    ids = {r["id"]: _run_model_ids(r, scopes.get(r["id"], [])) for r in runs}
    hidden = hidden_model_ids(db, {m for models in ids.values() if models for m in models})
    return {run_id: models is None or bool(models & hidden) for run_id, models in ids.items()}


def has_member_only_analyses(snapshot: Any) -> bool:
    """Whether a snapshot's Analyses section holds a member-only run, which
    a public report must not show."""
    analyses = snapshot.get("analyses") if isinstance(snapshot, dict) else None
    runs = analyses.get("runs") if isinstance(analyses, dict) else None
    return any(isinstance(r, dict) and r.get("member_only") is not False for r in runs or [])


def _finite(value: Any) -> Any:
    # Postgres float columns hold NaN and infinities, JSONB does not.
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _run_estimates(db: Session, run_id: str) -> List[Dict[str, Any]]:
    from models import AnalysisEstimate

    columns = [c.name for c in AnalysisEstimate.__table__.columns if c.name not in ("id", "run_id")]
    rows = (
        db.query(AnalysisEstimate)
        .filter(AnalysisEstimate.run_id == run_id)
        .order_by(AnalysisEstimate.position)
        .all()
    )
    return [{name: _finite(getattr(r, name)) for name in columns} for r in rows]


def _families(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The multiplicity families of the shown estimates with their method
    and size (from the estimates' adjustments)."""
    families: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for adjustment in row.get("adjustments") or []:
            if isinstance(adjustment, dict) and adjustment.get("family"):
                families.setdefault(adjustment["family"], {
                    "family": adjustment["family"],
                    "method": adjustment.get("method"),
                    "size": adjustment.get("size"),
                })
    return [families[k] for k in sorted(families)]


# Fields of a code validation's agreement copied into a report.
_KAPPA_FIELDS = ("n", "kappa", "observed_agreement", "expected_agreement")
_COUNT_FIELDS = ("items", "compared", "ties", "no_human_code", "missing_automatic", "missing")


def _code_records(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    codes = run.get("codes")
    return [c for c in codes if isinstance(c, dict)] if isinstance(codes, list) else []


def _judge_model(identity: Any) -> Optional[str]:
    if isinstance(identity, dict) and identity.get("kind") == "judge_code" and identity.get("system"):
        return str(identity["system"]).split("@", 1)[0]
    return None


def _analysis_code_validations(
    db: Session, runs: List[Dict[str, Any]], can_open_project: Optional[Callable[[str], bool]] = None
) -> List[Dict[str, Any]]:
    """The validations behind the codes the report's runs read, one entry per
    validation in the order the runs name them.

    Each entry is the validation the run accepted (``analysis_runs.codes``:
    the code's kind, ref, version and hash, kappa, observed agreement and the
    compared items, frozen when the run ran) and, when the stored row exists
    and ``can_open_project`` grants its coding project (the access of
    ``GET /api/code-validations/{id}`` for the author building the snapshot;
    without it no detail is copied), its name and the agreement detail
    (``code_validations.metrics``: expected agreement, counts, the
    categories with precision, recall and F1, the confusion matrix and the
    agreement between the human coders, without the per-coder rows, which
    name coders). ``used_by`` lists the runs and measures that read it. A
    validation is member-only when every run reading it is, or when it
    validates a hidden model's judge codes (:func:`model_is_public`); the
    public view leaves it out. Codes a run read without a validation
    (exploratory families) are not listed."""
    from models import CodeValidation

    entries: Dict[str, Dict[str, Any]] = {}
    for run in runs:
        for record in _code_records(run):
            accepted = record.get("validation")
            if not isinstance(accepted, dict) or not accepted.get("id"):
                continue
            vid = str(accepted["id"])
            entry = entries.get(vid)
            if entry is None:
                entry = entries[vid] = {
                    "id": vid,
                    "name": None,
                    "control": accepted.get("control"),
                    "code_kind": record.get("kind"),
                    "code_ref": record.get("ref"),
                    "code_version": record.get("version"),
                    "code_hash": record.get("hash"),
                    "kappa": _finite(accepted.get("kappa")),
                    "observed_agreement": _finite(accepted.get("observed_agreement")),
                    "compared": accepted.get("compared"),
                    "completed_at": accepted.get("completed_at"),
                    "detail": False,
                    "used_by": [],
                    "_runs": [],
                    "_judge": _judge_model(record),
                }
            entry["used_by"].append({"run_id": run["id"], "measure": record.get("measure")})
            entry["_runs"].append(run.get("member_only") is not False)
    if not entries:
        return []
    rows = {v.id: v for v in db.query(CodeValidation).filter(CodeValidation.id.in_(sorted(entries))).all()}
    hidden = hidden_model_ids(
        db, {m for m in [e["_judge"] for e in entries.values()] + [_judge_model(r.identity) for r in rows.values()] if m}
    )
    out: List[Dict[str, Any]] = []
    for vid, entry in entries.items():
        row = rows.get(vid)
        judge = {entry.pop("_judge")}
        member_runs = entry.pop("_runs")
        if row is not None:
            judge.add(_judge_model(row.identity))
        if row is not None and (can_open_project is None or not can_open_project(row.project_id)):
            row = None
        metrics = row.metrics if row is not None and isinstance(row.metrics, dict) else None
        if row is not None:
            entry["name"] = row.name
            entry["coding_version"] = row.coding_version
        if metrics is not None:
            main = metrics.get("automatic_vs_reference") if isinstance(metrics.get("automatic_vs_reference"), dict) else {}
            between = metrics.get("between_coders") if isinstance(metrics.get("between_coders"), dict) else None
            entry.update({
                "detail": True,
                "agreement": {k: _finite(main.get(k)) for k in _KAPPA_FIELDS},
                "counts": {k: metrics.get(k) for k in _COUNT_FIELDS},
                "categories": [str(c) for c in metrics.get("categories") or []],
                "per_category": main.get("per_category") if isinstance(main.get("per_category"), dict) else {},
                "confusion": main.get("confusion") if isinstance(main.get("confusion"), dict) else {},
                "between_coders": None if between is None else {
                    "coders": between.get("coders"),
                    "items": between.get("items"),
                    "fleiss_kappa": _finite(between.get("fleiss_kappa")),
                    "percent_agreement": _finite(between.get("percent_agreement")),
                },
            })
        entry["member_only"] = all(member_runs) or bool(judge & hidden)
        out.append(entry)
    return out


def _build_analyses_section(
    db: Session,
    project_id: str,
    config: Dict[str, Any],
    can_open_project: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """The runs the Analyses section names, in the author's order, each with
    its metadata, whether it is member-only
    (:func:`analysis_runs_member_only`), the estimates its exhibits select
    and every exhibit with the positions of its estimates. Estimates are
    copied whole, so the published report keeps its numbers whatever
    happens to the live tables; the public view leaves member-only runs out
    (:func:`public_snapshot`). A run the report cannot show is listed in
    ``omitted`` with the reason."""
    if not config["runs"]:
        return {"runs": [], "omitted": [], "code_validations": []}
    eligible = {r["id"]: r for r in report_analysis_runs(db, project_id)}
    problems = analysis_run_problems(db, project_id, [rc["run_id"] for rc in config["runs"] if rc["run_id"] not in eligible])

    member_only = analysis_runs_member_only(db, [eligible[rc["run_id"]] for rc in config["runs"] if rc["run_id"] in eligible])

    runs: List[Dict[str, Any]] = []
    omitted: List[Dict[str, Any]] = []
    for rc in config["runs"]:
        run = eligible.get(rc["run_id"])
        if run is None:
            omitted.append({"run_id": rc["run_id"], "reason": problems.get(rc["run_id"], RUN_NOT_FOUND)})
            continue
        shown = [(e, estimate_systems(e, run["normalized_spec"], run["fits"])) for e in _run_estimates(db, run["id"])]
        exhibits = []
        selected: set = set()
        for ex in rc["exhibits"]:
            positions = [e["position"] for e, systems in shown if exhibit_selects(e, ex["filters"], systems)]
            selected.update(positions)
            exhibits.append({
                "id": ex["id"],
                "type": ex["type"],
                "filters": ex["filters"],
                "band": ex["band"],
                "row_count": len(positions),
                "positions": positions,
            })
        kept = set(sorted(selected)[:MAX_REPORT_ESTIMATES_PER_RUN])
        for ex in exhibits:
            ex["positions"] = [p for p in ex["positions"] if p in kept]
        rows = [e for e, _ in shown if e["position"] in kept]
        warnings = run.get("warnings") if isinstance(run.get("warnings"), list) else []
        runs.append({
            "id": run["id"],
            "name": run["name"],
            "spec_hash": run["spec_hash"],
            "spec_version": run["spec_version"],
            "engine_version": run["engine_version"],
            "frame_hash": run["frame_hash"],
            "frame_sha256": run["frame_sha256"],
            "frame_rows": run["frame_rows"],
            "estimates_count": int(run["estimates_count"] or 0),
            "completed_at": _iso(run["completed_at"]),
            "member_only": member_only[run["id"]],
            "warnings": [str(w) for w in warnings],
            "families": _families(rows),
            "truncated": len(selected) > MAX_REPORT_ESTIMATES_PER_RUN,
            "estimates": rows,
            "exhibits": exhibits,
        })
    shown_runs = [{**r, "codes": eligible[r["id"]].get("codes")} for r in runs]
    return {"runs": runs, "omitted": omitted, "code_validations": _analysis_code_validations(db, shown_runs, can_open_project)}


# ---------------------------------------------------------------------------
# Reader view
# ---------------------------------------------------------------------------

def _without(doc: Any, key: str) -> Any:
    return {k: v for k, v in doc.items() if k != key} if isinstance(doc, dict) else doc


def _map_list(container: Dict[str, Any], key: str, fn) -> Dict[str, Any]:
    items = container.get(key)
    if not isinstance(items, list):
        return container
    return {**container, key: [fn(i) if isinstance(i, dict) else i for i in items]}


def public_snapshot(snapshot: Any) -> Any:
    """The snapshot as served to a reader outside the project (a public
    report read anonymously or by a non-member): judge run parameters,
    declared import manifests and design provenance keep their SHA-256 but
    lose their content (custom judge prompts, rubrics, author manifests),
    the reproducibility list and the Analyses section leave out every
    member-only run (:func:`analysis_runs_member_only`; a run not marked
    public counts as one), and the Analyses section its list of runs it
    could not show (the author's note to fix). The stored snapshot stays
    whole; the served hash is computed over the served body
    (:func:`with_served_hash`)."""
    if not isinstance(snapshot, dict):
        return snapshot
    out = dict(snapshot)
    if isinstance(out.get("data"), dict):
        data = _map_list(out["data"], "variant_designs",
                         lambda d: {**d, "provenance": _without(d.get("provenance"), "content")})
        out["data"] = _map_list(data, "imports",
                                lambda i: {**i, "declared_manifest": _without(i["declared_manifest"], "content")}
                                if "declared_manifest" in i else i)
    if isinstance(out.get("reproducibility"), dict):
        reproducibility = _map_list(
            out["reproducibility"], "evaluation_configs",
            lambda c: _map_list(c, "judge_runs", lambda r: _without(r, "parameters")),
        )
        if isinstance(reproducibility.get("analysis_runs"), list):
            reproducibility = {
                **reproducibility,
                "analysis_runs": [r for r in reproducibility["analysis_runs"]
                                  if isinstance(r, dict) and r.get("member_only") is False],
            }
        out["reproducibility"] = reproducibility
    if isinstance(out.get("analyses"), dict):
        analyses = _without(out["analyses"], "omitted")
        if isinstance(analyses.get("runs"), list):
            analyses["runs"] = [r for r in analyses["runs"] if isinstance(r, dict) and r.get("member_only") is False]
        if isinstance(analyses.get("code_validations"), list):
            public_runs = {r.get("id") for r in analyses.get("runs") or [] if isinstance(r, dict)}
            analyses["code_validations"] = [
                {**v, "used_by": [u for u in v.get("used_by") or [] if isinstance(u, dict) and u.get("run_id") in public_runs]}
                for v in analyses["code_validations"]
                if isinstance(v, dict) and v.get("member_only") is False
            ]
        out["analyses"] = analyses
    return out


def apply_section_visibility(
    snapshot: Optional[Dict[str, Any]], sections: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """The snapshot as a report with these sections may serve it.

    With ``sections.annotations.show_agreement`` off, the annotator agreement
    is ``None``. With ``sections.annotations.show_participants`` off, the
    participant list is empty and the annotator agreement keeps its aggregate
    numbers but drops the per-pair rows, which name and score individual
    annotators; ``statistics.participant_count`` stays. With
    ``sections.annotations.show_code_validations`` off, the Analyses
    section's ``code_validations`` list is empty."""
    if not isinstance(snapshot, dict):
        return snapshot
    annotations = (sections or {}).get("annotations") or {}
    served = dict(snapshot)
    if annotations.get("show_agreement") is False and "annotator_agreement" in served:
        served["annotator_agreement"] = None
    analyses = served.get("analyses")
    if annotations.get("show_code_validations") is False and isinstance(analyses, dict):
        served["analyses"] = {**analyses, "code_validations": []}
    if annotations.get("show_participants") is False:
        served["participants"] = []
        agreement = served.get("annotator_agreement")
        if agreement:
            controls = [{**c, "pairs": []} for c in agreement.get("controls") or []]
            served["annotator_agreement"] = {**agreement, "controls": controls}
    return served


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

#: Snapshot parts of the variant_experiments flag (core 2.75): top-level
#: keys, ``statistics`` keys, and inside the report_paper parts the lists
#: and fields of features that flag covers (variant designs, analysis runs,
#: import provenance, refusal, retry and request record shares).
EXPERIMENT_SNAPSHOT_KEYS: Tuple[str, ...] = ("analyses", "annotator_agreement")
EXPERIMENT_STATISTICS_KEYS: Tuple[str, ...] = ("analysis_count",)
EXPERIMENT_LIST_KEYS: Dict[str, Tuple[str, ...]] = {
    "data": ("variant_designs",),
    "reproducibility": ("variant_designs", "analysis_runs"),
}
EXPERIMENT_IMPORT_FIELDS: Tuple[str, ...] = (
    "payload_sha256", "mode", "byte_size", "task_count", "no_op", "declared_manifest",
)
EXPERIMENT_GENERATION_FIELDS: Tuple[str, ...] = (
    "refusal_rate", "retry_rate", "request_record_share",
)

#: Snapshot parts of the report_paper flag (core 2.75): the report as the
#: project's paper.
PAPER_SNAPSHOT_KEYS: Tuple[str, ...] = ("data", "generation", "human_evaluations", "reproducibility")


def _drop(container: Any, keys: Iterable[str]) -> Any:
    if not isinstance(container, dict):
        return container
    return {k: v for k, v in container.items() if k not in keys}


def _without_experiment_values(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    out = _drop(snapshot, EXPERIMENT_SNAPSHOT_KEYS)
    if isinstance(out.get("statistics"), dict):
        out["statistics"] = _drop(out["statistics"], EXPERIMENT_STATISTICS_KEYS)
    for part, keys in EXPERIMENT_LIST_KEYS.items():
        if isinstance(out.get(part), dict):
            out[part] = {**out[part], **{k: [] for k in keys if k in out[part]}}
    for part in ("data", "reproducibility"):
        if isinstance(out.get(part), dict):
            out[part] = _map_list(out[part], "imports", lambda i: _drop(i, EXPERIMENT_IMPORT_FIELDS))
    if isinstance(out.get("generation"), dict):
        generation = _map_list(out["generation"], "models", lambda m: _drop(m, EXPERIMENT_GENERATION_FIELDS))
        if isinstance(generation.get("totals"), dict):
            generation = {**generation, "totals": _drop(generation["totals"], EXPERIMENT_GENERATION_FIELDS)}
        out["generation"] = generation
    return out


def gated_snapshot(
    snapshot: Optional[Dict[str, Any]], *, variant_experiments: bool, report_paper: bool
) -> Optional[Dict[str, Any]]:
    """``snapshot`` without the parts of the flags that are off (a copy; the
    stored snapshot is not changed): without report_paper none of
    :data:`PAPER_SNAPSHOT_KEYS`, without variant_experiments none of the
    parts listed with :data:`EXPERIMENT_SNAPSHOT_KEYS`. The hash is left as
    it is; serving computes it over what a reader gets
    (:func:`with_served_hash`)."""
    if not isinstance(snapshot, dict):
        return snapshot
    out = dict(snapshot)
    if not report_paper:
        out = _drop(out, PAPER_SNAPSHOT_KEYS)
    if not variant_experiments:
        out = _without_experiment_values(out)
    return out


def with_served_hash(stored: Any, served: Any) -> Any:
    """``served`` (the snapshot as one reader gets it, after every part left
    out for that reader) with ``reproducibility.snapshot_sha256`` computed
    over it when it differs from ``stored``, so the hash a reader gets
    verifies against the data that reader gets; unchanged, it keeps the
    stored hash."""
    if not isinstance(served, dict) or served == stored:
        return served
    if not isinstance(served.get("reproducibility"), dict):
        return served
    out = {**served, "reproducibility": {**served["reproducibility"], "snapshot_sha256": None}}
    out["reproducibility"]["snapshot_sha256"] = snapshot_sha256(out)
    return out


def _flag_scoped(name: str) -> bool:
    from feature_flags.scope import scoped_flag

    return scoped_flag(name)


def build_report_snapshot(
    db: Session,
    project_id: str,
    *,
    include_private_models: bool = False,
    now: Optional[datetime] = None,
    variant_experiments: Optional[bool] = None,
    report_paper: Optional[bool] = None,
    analyses: Any = None,
    can_open_project: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Compute the full report snapshot for a project (see module docstring).

    ``analyses`` is the report's ``content.sections.analyses`` (see
    :func:`parse_analyses_section`): the runs and exhibits whose estimates
    the snapshot copies. ``can_open_project`` tells whether the author
    building the snapshot can open a project (by id); a code validation's
    detail is copied only from a coding project it grants
    (:func:`_analysis_code_validations`).

    ``variant_experiments`` and ``report_paper`` (None: the request or job
    context decides, ``feature_flags.scope``) add the parts of those flags;
    without them the snapshot is built as :func:`gated_snapshot` serves it."""
    from feature_flags.registry import REPORT_PAPER, VARIANT_EXPERIMENTS

    if variant_experiments is None:
        variant_experiments = _flag_scoped(VARIANT_EXPERIMENTS)
    if report_paper is None:
        report_paper = _flag_scoped(REPORT_PAPER)
    from project_models import Project

    params = {"project_id": project_id}

    counts = db.execute(text(_COUNTS_SQL), params).mappings().one()
    model_rows = db.execute(text(_MODELS_SQL), params).mappings().all()
    participant_rows = db.execute(text(_PARTICIPANTS_SQL), params).mappings().all()
    stat_rows = db.execute(text(_STATS_SQL), params).mappings().all()
    hist_rows = db.execute(text(_HIST_SQL), params).mappings().all()

    # ---- subjects -------------------------------------------------------
    model_info: Dict[str, Dict[str, Any]] = {}
    hidden_models: set = set()
    for r in model_rows:
        is_custom = r["is_official"] is not True and (r["name"] is None or str(r["model_id"]).startswith("custom-"))
        catalog_row = None if r["name"] is None else {"is_official": r["is_official"], "is_public": r["is_public"]}
        visible = model_is_public(r["model_id"], catalog_row)
        if not visible and not include_private_models:
            hidden_models.add(r["model_id"])
            continue
        model_info[r["model_id"]] = {
            "id": r["model_id"],
            "kind": "model",
            "label": _model_label(r["model_id"], r["name"]),
            "provider": r["provider"],
            "is_custom": bool(is_custom),
        }

    participants = []
    human_labels: Dict[str, str] = {}
    for r in participant_rows:
        # The snapshot is frozen into a published, possibly public report:
        # the pseudonym, never the real name or login name. The old rule fell
        # back to those for people who had switched their pseudonym off.
        label = masked_name(user_id=r["id"], pseudonym=r["pseudonym"])
        human_labels[f"annotator:{r['id']}"] = label
        participants.append({"id": r["id"], "label": label, "annotation_count": int(r["annotation_count"])})
    # Every list is sorted to a total order, ties broken by id, so a rebuild
    # over unchanged data gives the same snapshot (and snapshot_sha256).
    participants.sort(key=lambda p: (-p["annotation_count"], p["label"], p["id"]))

    def _subject(kind: str, subject_id: str) -> Optional[Dict[str, Any]]:
        if kind == "model":
            info = model_info.get(subject_id)
            if info is None:
                if subject_id in hidden_models:
                    return None
                # Generation with no catalog row and no rg link: still a model.
                info = {"id": subject_id, "kind": "model", "label": _model_label(subject_id, None), "provider": None, "is_custom": subject_id.startswith("custom-")}
                if info["is_custom"] and not include_private_models:
                    return None
                model_info[subject_id] = info
            return info
        return {"id": subject_id, "kind": "human", "label": human_labels.get(subject_id, "Teilnehmer:in")}

    def _model_subject(model_id: str) -> Optional[Dict[str, Any]]:
        """The subject of a model for the sections after the evaluation, or
        None when the model is hidden; unlike ``_subject`` it never adds a
        model to the report's model list."""
        info = model_info.get(model_id)
        if info is not None:
            return info
        if model_id in hidden_models:
            return None
        is_custom = str(model_id).startswith("custom-")
        if is_custom and not include_private_models:
            return None
        return {"id": model_id, "kind": "model", "label": _model_label(model_id, None), "provider": None, "is_custom": is_custom}

    # ---- series -----------------------------------------------------------
    series_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    metrics_seen: Dict[str, bool] = {}   # metric -> has grade points
    passed_seen: set = set()
    config_n: Dict[Tuple[str, str], int] = {}
    for r in stat_rows:
        subject = _subject(r["kind"], r["subject_id"])
        if subject is None:
            continue
        metric = r["metric"]
        key = (subject["id"], r["config_id"])
        row = series_map.setdefault(key, {"subject": subject, "config_id": r["config_id"], "metrics": {}})
        factor = 100.0 if _scale(metric) == "0-100" else 1.0
        stats = {
            "mean": float(r["mean"]) * factor,
            "n": int(r["n"]),
            "std": None if r["std"] is None else float(r["std"]) * factor,
            "min": None if r["min"] is None else float(r["min"]) * factor,
            "max": None if r["max"] is None else float(r["max"]) * factor,
            "pass_rate": _f(r["pass_rate"]),
        }
        row["metrics"][metric] = stats
        metrics_seen.setdefault(metric, False)
        if r["pass_rate"] is not None:
            passed_seen.add(metric)
            row["metrics"][f"{metric}_passed"] = {"mean": float(r["pass_rate"]), "n": int(r["n"])}
        if r["gp_n"] and int(r["gp_n"]) > 0:
            metrics_seen[metric] = True
            row["metrics"][f"{metric}_grade_points"] = {
                "mean": float(r["gp_mean"]),
                "n": int(r["gp_n"]),
                "std": _f(r["gp_std"]),
                "min": _f(r["gp_min"]),
                "max": _f(r["gp_max"]),
            }
        config_n[(r["config_id"], metric)] = config_n.get((r["config_id"], metric), 0) + int(r["n"])

    series = sorted(series_map.values(), key=lambda s: (s["subject"]["kind"], s["subject"]["label"].lower(), s["subject"]["id"], s["config_id"]))

    # ---- methods ------------------------------------------------------------
    methods: List[Dict[str, Any]] = []
    for metric, has_gp in sorted(metrics_seen.items(), key=lambda kv: (_PRIMARY_PREFERENCE.index(kv[0]) if kv[0] in _PRIMARY_PREFERENCE else 99, kv[0])):
        methods.append({"id": metric, "name": _humanize(metric), "category": _category(metric), "scale": _scale(metric), "higher_is_better": True})
        if has_gp:
            methods.append({"id": f"{metric}_grade_points", "name": f"Notenpunkte ({_humanize(metric)})", "category": _category(metric), "scale": "0-18", "higher_is_better": True, "derived": True})
        if metric in passed_seen:
            methods.append({"id": f"{metric}_passed", "name": f"Bestanden ({_humanize(metric)})", "category": _category(metric), "scale": "0-1", "higher_is_better": True, "derived": True})

    # ---- configs ------------------------------------------------------------
    project = db.query(Project).filter(Project.id == project_id).first()
    eval_cfg = (getattr(project, "evaluation_config", None) or {}) if project else {}
    cfg_entries = {c.get("id"): c for c in (eval_cfg.get("evaluation_configs") or []) if isinstance(c, dict)}
    run_judges = {r["config_id"]: r["judge_model_id"] for r in db.execute(text(_CONFIG_JUDGES_SQL), params).mappings().all()}

    def _judge_for(cid: str) -> Optional[str]:
        entry = cfg_entries.get(cid) or {}
        return (entry.get("metric_parameters") or {}).get("judge_model") or run_judges.get(cid)

    def _hidden_judges(ids: Iterable[Optional[str]]) -> set:
        return set() if include_private_models else hidden_model_ids(db, ids)

    judge_ids = sorted({_judge_for(cid) for (cid, _m) in config_n if _judge_for(cid)})
    hidden_judges = _hidden_judges(judge_ids)
    judge_names: Dict[str, str] = {}
    if judge_ids:
        judge_names = {r["id"]: r["name"] for r in db.execute(text(_JUDGE_NAMES_SQL), {"ids": judge_ids}).mappings().all()}
    configs: List[Dict[str, Any]] = []
    for (cid, metric), n in sorted(config_n.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])):
        entry = cfg_entries.get(cid) or {}
        judge = _judge_for(cid) if metric.startswith("llm_judge_") else None
        if judge in hidden_judges:
            judge = None
        configs.append({
            "id": cid,
            "metric": metric,
            "judge_model": judge,
            "judge_label": judge_names.get(judge, _model_label(judge, None)) if judge else None,
            "name": entry.get("display_name"),
            "n": n,
        })

    primary_metric = next((m for m in _PRIMARY_PREFERENCE if m in metrics_seen), min(metrics_seen) if metrics_seen else None)
    primary_config_id = None
    if primary_metric:
        candidates = [c for c in configs if c["metric"] == primary_metric]
        if candidates:
            primary_config_id = max(candidates, key=lambda c: c["n"])["id"]
    grade_metric = f"{primary_metric}_grade_points" if primary_metric and metrics_seen.get(primary_metric) else None

    # ---- distributions --------------------------------------------------------
    dist_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in hist_rows:
        subject = _subject(r["kind"], r["subject_id"])
        if subject is None:
            continue
        metric = r["metric"]
        if r["series"] == "grade":
            key = (f"{metric}_grade_points", r["config_id"], "0-18")
            bins = GRADE_BINS
        else:
            scale = _scale(metric)
            key = (metric, r["config_id"], scale)
            bins = HUNDRED_BINS if scale == "0-100" else UNIT_BINS
        d = dist_map.setdefault(key, {
            "metric": key[0], "config_id": r["config_id"], "scale": key[2], "bins": list(bins),
            "by_kind": {"model": _empty_bins(len(bins)), "human": _empty_bins(len(bins))},
            "by_subject": {},
        })
        b = int(r["bin"]); n = int(r["n"])
        d["by_kind"][subject["kind"]][b] += n
        # Per-subject histograms only for the headline metrics (size: a
        # benchmark with dozens of annotators × metrics would otherwise
        # store hundreds of KB nobody renders).
        if key[0] in (primary_metric, grade_metric):
            d["by_subject"].setdefault(subject["id"], _empty_bins(len(bins)))[b] += n
    distributions = sorted(dist_map.values(), key=lambda d: (d["metric"] != grade_metric, d["metric"] != primary_metric, d["metric"], d["config_id"]))

    models = sorted(model_info.values(), key=lambda m: (m["label"].lower(), m["id"]))
    snapshot = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "statistics": {
            "task_count": int(counts["task_count"]),
            "annotation_count": int(counts["annotation_count"]),
            "participant_count": int(counts["participant_count"]),
            "model_count": len(model_info),
            "evaluation_count": int(counts["evaluation_count"]),
            "analysis_count": int(counts["analysis_count"]),
        },
        "methods": methods,
        "configs": configs,
        "primary_metric": primary_metric,
        "primary_config_id": primary_config_id,
        "grade_metric": grade_metric,
        "series": series,
        "distributions": distributions,
        "participants": participants,
        "models": models,
    }
    if variant_experiments:
        # Inter-annotator agreement per control over tasks with two or more
        # annotators (``annotator_agreement``); ``None`` without overlap.
        snapshot["annotator_agreement"] = project_annotator_agreement(db, project_id)
        snapshot["analyses"] = _build_analyses_section(
            db, project_id, parse_analyses_section(analyses), can_open_project
        )
    if report_paper:
        # ---- data, generation, human evaluation, reproducibility ----------
        data = _build_data_section(db, params, int(counts["task_count"]))
        generation = _build_generation_section(db, params, _model_subject)
        snapshot["data"] = data
        snapshot["generation"] = generation
        snapshot["human_evaluations"] = _build_human_evaluation_section(
            db, params, _model_subject, lambda model_id: _model_subject(model_id) is not None
        )
        snapshot["reproducibility"] = _build_reproducibility_section(
            db, params, project,
            models=models, configs=configs, cfg_entries=cfg_entries, data=data,
            generation=generation,
            model_visible=lambda model_id: _model_subject(model_id) is not None,
            hidden_judges=_hidden_judges,
        )
    snapshot = gated_snapshot(snapshot, variant_experiments=variant_experiments, report_paper=report_paper)
    if isinstance(snapshot.get("reproducibility"), dict):
        snapshot["reproducibility"]["snapshot_sha256"] = snapshot_sha256(snapshot)
    return snapshot
