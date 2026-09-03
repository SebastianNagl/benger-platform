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
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

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
SELECT u.id, u.username, u.name, u.pseudonym, u.use_pseudonym, COUNT(a.id) AS annotation_count
FROM annotations a JOIN users u ON u.id = a.completed_by
WHERE a.project_id = :project_id AND a.was_cancelled = false
GROUP BY u.id, u.username, u.name, u.pseudonym, u.use_pseudonym
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


def _display_name(username: str, name: Optional[str], pseudonym: Optional[str], use_pseudonym: bool) -> str:
    """Same rule as the leaderboards: pseudonym when the user opted in (default), else name/username."""
    if use_pseudonym and pseudonym:
        return pseudonym
    return name or username


def _model_label(model_id: str, catalog_name: Optional[str]) -> str:
    if catalog_name:
        return catalog_name
    # "provider/Model-Name" → "Model-Name"
    return model_id.split("/")[-1]


def _f(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _empty_bins(n: int) -> List[int]:
    return [0] * n


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
        visible = r["is_official"] is True or r["is_public"] is True or (r["name"] is None and not str(r["model_id"]).startswith("custom-"))
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
        label = _display_name(r["username"], r["name"], r["pseudonym"], bool(r["use_pseudonym"]))
        human_labels[f"annotator:{r['id']}"] = label
        participants.append({"id": r["id"], "label": label, "annotation_count": int(r["annotation_count"])})
    participants.sort(key=lambda p: (-p["annotation_count"], p["label"]))

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

    series = sorted(series_map.values(), key=lambda s: (s["subject"]["kind"], s["subject"]["label"].lower(), s["config_id"]))

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

    judge_ids = sorted({_judge_for(cid) for (cid, _m) in config_n if _judge_for(cid)})
    judge_names: Dict[str, str] = {}
    if judge_ids:
        judge_names = {r["id"]: r["name"] for r in db.execute(text(_JUDGE_NAMES_SQL), {"ids": judge_ids}).mappings().all()}
    configs: List[Dict[str, Any]] = []
    for (cid, metric), n in sorted(config_n.items(), key=lambda kv: -kv[1]):
        entry = cfg_entries.get(cid) or {}
        judge = _judge_for(cid) if metric.startswith("llm_judge_") else None
        configs.append({
            "id": cid,
            "metric": metric,
            "judge_model": judge,
            "judge_label": judge_names.get(judge, _model_label(judge, None)) if judge else None,
            "name": entry.get("display_name"),
            "n": n,
        })

    primary_metric = next((m for m in _PRIMARY_PREFERENCE if m in metrics_seen), next(iter(metrics_seen), None))
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

    return {
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
        "models": sorted(model_info.values(), key=lambda m: m["label"].lower()),
    }
