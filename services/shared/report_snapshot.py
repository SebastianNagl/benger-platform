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
took part in.

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
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

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
     WHERE r.project_id = :project_id AND r.status = 'completed') AS evaluation_count
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
           ROW_NUMBER() OVER (PARTITION BY COALESCE(te.evaluation_config_id, '') ORDER BY COUNT(*) DESC) AS rn
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

# Completed analysis runs that read this project only: a cross-project run
# (``inputs.projects``) would publish numbers of another project.
_ANALYSIS_RUNS_SQL = """
SELECT id, name, spec_hash, spec_version, engine_version, frame_hash, frame_sha256,
       frame_rows, estimates_count, library_versions, lockfile_sha256, seed, completed_at
FROM analysis_runs
WHERE project_id = :project_id AND status = 'completed'
  AND COALESCE(jsonb_array_length(
        CASE WHEN jsonb_typeof(normalized_spec->'inputs'->'projects') = 'array'
             THEN normalized_spec->'inputs'->'projects' END), 0) = 0
ORDER BY completed_at, id
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
    for r in db.execute(text(_ANALYSIS_RUNS_SQL), params).mappings().all():
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
    lose their content (custom judge prompts, rubrics, author manifests).
    The stored snapshot and its ``snapshot_sha256`` stay whole."""
    if not isinstance(snapshot, dict):
        return snapshot
    out = dict(snapshot)
    if isinstance(out.get("data"), dict):
        data = _map_list(out["data"], "variant_designs",
                         lambda d: {**d, "provenance": _without(d.get("provenance"), "content")})
        out["data"] = _map_list(data, "imports",
                                lambda i: {**i, "declared_manifest": _without(i.get("declared_manifest"), "content")})
    if isinstance(out.get("reproducibility"), dict):
        out["reproducibility"] = _map_list(
            out["reproducibility"], "evaluation_configs",
            lambda c: _map_list(c, "judge_runs", lambda r: _without(r, "parameters")),
        )
    return out


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_report_snapshot(
    db: Session,
    project_id: str,
    *,
    include_private_models: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compute the full report snapshot for a project (see module docstring)."""
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

    # ---- data, generation, human evaluation, reproducibility --------------
    models = sorted(model_info.values(), key=lambda m: (m["label"].lower(), m["id"]))
    data = _build_data_section(db, params, int(counts["task_count"]))
    generation = _build_generation_section(db, params, _model_subject)
    human_evaluations = _build_human_evaluation_section(
        db, params, _model_subject, lambda model_id: _model_subject(model_id) is not None
    )
    reproducibility = _build_reproducibility_section(
        db, params, project,
        models=models, configs=configs, cfg_entries=cfg_entries, data=data, generation=generation,
        model_visible=lambda model_id: _model_subject(model_id) is not None,
        hidden_judges=_hidden_judges,
    )

    snapshot = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "statistics": {
            "task_count": int(counts["task_count"]),
            "annotation_count": int(counts["annotation_count"]),
            "participant_count": int(counts["participant_count"]),
            "model_count": len(model_info),
            "evaluation_count": int(counts["evaluation_count"]),
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
        "data": data,
        "generation": generation,
        "human_evaluations": human_evaluations,
        "reproducibility": reproducibility,
    }
    reproducibility["snapshot_sha256"] = snapshot_sha256(snapshot)
    return snapshot
