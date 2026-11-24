"""Single source of truth for the "real metric key" noise filter.

Used to be a private helper in `routers/projects/helpers.py`, but the
projects-list, dashboard, leaderboard and worker recompute paths all need
the same predicate to agree on what counts as a "real" metric. Hosting it
here lets both the API (which has /shared on sys.path) and the worker
(ditto) import the same definition without one reaching into the other's
package surface.
"""

import re
from typing import Any, Optional, Tuple

# Metric-key noise stripped out of the "scored (subject, metric) pairs" tally.
# Mirrors the dropdown filter in routers/evaluations/metadata.py so the tile
# and the metric list agree on what counts as a "real" metric.
_METRIC_NOISE_SUFFIXES: Tuple[str, ...] = (
    "_details",
    "_raw",
    "_passed",
    "_grade_points",
    "_response",
)
_METRIC_EXCLUDED_KEYS = frozenset({"raw_score", "error"})

# Sub-metric names that look like noise (end in a suffix above) but are
# registered as displayable standalone metrics in the frontend metric
# registry. Without this override the aggregator + tile counters would drop
# them on the floor and the leaderboard column shows n/a for everyone even
# though the per-row value exists (see aggregate_summaries.py — the
# UNION ALL that lifts grade_points out of `details`).
_METRIC_REGISTERED_OVERRIDES = frozenset(
    {
        "llm_judge_falloesung_grade_points",
        # The rubric judge's twin. Same reason, same consequence: without
        # it a Bewertungsbogen-graded project shows n/a in the Notenpunkte
        # column while every row carries the value.
        "llm_judge_rubric_grade_points",
    }
)


_GRADE_POINTS_SUFFIX = "_grade_points"

# Base metrics whose Notenpunkte twin is a registered standalone metric,
# derived from the overrides so the leaderboard SQL that lifts
# `details.grade_points` (aggregate_summaries.py) and this filter cannot
# disagree on which metrics carry one.
GRADE_POINT_LIFT_BASES: Tuple[str, ...] = tuple(
    sorted(
        key[: -len(_GRADE_POINTS_SUFFIX)]
        for key in _METRIC_REGISTERED_OVERRIDES
        if key.endswith(_GRADE_POINTS_SUFFIX)
    )
)


def metric_key_is_real(key: Optional[str]) -> bool:
    """True for keys that are displayable / aggregatable metrics."""
    if not key or key in _METRIC_EXCLUDED_KEYS:
        return False
    if key in _METRIC_REGISTERED_OVERRIDES:
        return True
    return not key.endswith(_METRIC_NOISE_SUFFIXES)


# Legacy underscore alias — many call sites already use this name.
_metric_key_is_real = metric_key_is_real


def metric_key_counts_as_evaluation(key: Optional[str]) -> bool:
    """True for keys that are an evaluation of their own.

    Narrower than :func:`metric_key_is_real`: a registered override is a
    second view of its base metric (the Notenpunkte of the same judge call),
    so it gets a leaderboard column but must not count as a second
    evaluation. Counting it made every judged answer show up twice in the
    project tile.
    """
    return metric_key_is_real(key) and key not in _METRIC_REGISTERED_OVERRIDES


# ---------------------------------------------------------------------------
# Immediate-evaluation eligibility
# ---------------------------------------------------------------------------
# Metrics that load transformer models (sentence-transformers, BERT, NLI,
# QA/QG pipelines) at compute time. They are fully supported in BATCH
# evaluation — one model load amortizes over many samples on a warm worker —
# but are deliberately excluded from IMMEDIATE (per-submit) evaluation:
#   * a per-submit model load is far too slow for "instant" feedback, and
#   * stacking those loads on the small interactive worker fleet risks OOM.
# The immediate-eval dispatcher filters these out and the modal surfaces them
# as "batch only". Mirrored on the frontend in evaluation-types.ts
# (`immediate_eligible: false`). Lives here because both the API (dispatch
# router) and the worker (defense-in-depth) need the same predicate and both
# have /shared on sys.path.
HEAVY_METRICS = frozenset(
    {
        "bertscore",
        "moverscore",
        "semantic_similarity",
        "factcc",
        "qags",
        "coherence",
    }
)


def details_await_release(details: Any) -> bool:
    """Whether a metric's details hold a result its student may not see yet.

    Two shapes wait for a release: a review whose status is not released
    (``details.review.status`` other than ``"released"``: a re-graded row
    starts as a draft, core 2.83, and the overlay's teacher review writes the
    same key) and a feedback-only judge result (``details.feedback_only``,
    core 2.41) without a released review. A judge that releases on writing,
    or a teacher who released later, stores ``review.status = "released"``.
    A review without a status on any other result is no release state. The
    overlay owns the review workflow; this only reads the stored shape,
    because the attempt-score surfaces and the grading notices live in the
    platform.
    """
    if not isinstance(details, dict):
        return False
    review = details.get("review")
    status = review.get("status") if isinstance(review, dict) else None
    if status is not None:
        return status != "released"
    return details.get("feedback_only") is True


def blob_awaits_release(blob: Any) -> bool:
    """:func:`details_await_release` for a ``{value, method, details}``
    metric blob: such a blob is a draft for the teacher, not a score, so no
    attempt score or student-facing number may read it."""
    return isinstance(blob, dict) and details_await_release(blob.get("details"))


def metric_awaits_release(metrics: Any, key: Any) -> bool:
    """Whether the result of metric ``key`` in a row's metrics awaits its
    release: its blob (:func:`blob_awaits_release`) or, for a flat row, its
    ``<key>_details`` sibling."""
    if not isinstance(metrics, dict):
        return False
    if blob_awaits_release(metrics.get(key)):
        return True
    return isinstance(key, str) and details_await_release(metrics.get(f"{key}_details"))


def is_unreleased_feedback(blob: Any) -> bool:
    """Whether a metric blob is a feedback-only judge result still waiting for
    its release (``details.feedback_only``, core 2.41); the feedback case of
    :func:`blob_awaits_release`."""
    if not isinstance(blob, dict):
        return False
    details = blob.get("details")
    return (
        isinstance(details, dict)
        and details.get("feedback_only") is True
        and details_await_release(details)
    )


def row_awaits_release(metrics: Any) -> bool:
    """Whether a ``task_evaluations`` row holds a result still waiting for its
    release (:func:`details_await_release`), in a metric blob or in the flat
    ``<metric>_details`` sibling of a flat row.

    Its submitter cannot see such a row yet, so no "grading received" notice
    may announce it; the release itself is the moment to tell them. The
    batch notice (``tasks._notify_batch_grading_received``) is stricter in
    SQL: it counts a row with a review only when the judge released it.
    """
    if not isinstance(metrics, dict):
        return False
    for key, blob in metrics.items():
        if blob_awaits_release(blob):
            return True
        if isinstance(key, str) and key.endswith("_details") and details_await_release(blob):
            return True
    return False


def is_heavy_metric(metric_name: Optional[str]) -> bool:
    """True for transformer-model-loading metrics excluded from immediate
    (per-submit) evaluation. See :data:`HEAVY_METRICS`."""
    return bool(metric_name) and metric_name in HEAVY_METRICS


def is_immediate_eligible(metric_name: Optional[str]) -> bool:
    """Whether a metric may run in immediate (post-submit) evaluation.

    Excludes human-graded Korrektur metrics (``korrektur_*`` — scored by a
    person, never computed by the worker) and heavy/semantic metrics; every
    other metric (deterministic + LLM judges) is eligible.
    """
    if not metric_name or metric_name.startswith("korrektur_"):
        return False
    return not is_heavy_metric(metric_name)


# Metrics that grade the prediction alone (codes such as ``text_pattern``).
# A config of one runs once per prediction field, under the reference part
# ``""`` of its ``{config_id}|{pred}|{ref}`` key, whatever reference fields
# it lists. The worker also honours a metric handler's ``reference_free``
# attribute, so an overlay's handler can declare it.
REFERENCE_FREE_METRICS = frozenset({"text_pattern"})

#: Platform metrics that belong to a feature flag (core 2.75): with the flag
#: off for the caller or the run's owner they are neither offered nor run;
#: stored configs naming them stay as they are.
FLAGGED_METRICS = {"text_pattern": "variant_experiments"}


def without_flagged_metrics(configs: Any, is_on) -> list:
    """``configs`` without the entries whose metric belongs to a flag
    ``is_on(name)`` answers False for (:data:`FLAGGED_METRICS`)."""
    kept = []
    for config in configs or []:
        metric = config.get("metric") if isinstance(config, dict) else getattr(config, "metric", None)
        flag = FLAGGED_METRICS.get(metric) if isinstance(metric, str) else None
        if flag is None or is_on(flag):
            kept.append(config)
    return kept


def is_reference_free(metric_name: Optional[str]) -> bool:
    if not metric_name:
        return False
    if metric_name in REFERENCE_FREE_METRICS:
        return True
    try:
        from ml_evaluation import metric_registry
    except ImportError:
        return False
    return bool(getattr(metric_registry.get(metric_name), "reference_free", False))


# Judges that take their reference solution from the task itself rather
# than from the reference field a cell passes them: every reference field
# would send the judge the same input.
JUDGES_WITH_OWN_REFERENCE = frozenset({"llm_judge_falloesung", "llm_judge_rubric"})

_PROMPT_PLACEHOLDER = re.compile(r"\{\{?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}?\}")


def _reference_field_name(ref: str) -> str:
    return ref[5:] if ref.startswith("task.") else ref


def judge_reads_references_itself(config: Any) -> bool:
    """Whether an LLM judge with several reference fields reads them itself.

    True for a judge that takes its reference from the task
    (:data:`JUDGES_WITH_OWN_REFERENCE`) and for one whose prompt template
    names a reference field as a placeholder (``{bewertungsbogen}``): the
    judge sees every reference in one call, so grading the answer once per
    reference field only repeats the same grading. Such a config grades
    once per prediction field (:func:`graded_reference_fields`).
    """
    metric = config.get("metric") or ""
    if not isinstance(metric, str) or not metric.startswith("llm_judge_"):
        return False
    refs = [r for r in config.get("reference_fields") or [] if isinstance(r, str) and r]
    if len(refs) < 2:
        return False
    if metric in JUDGES_WITH_OWN_REFERENCE:
        return True
    template = (config.get("metric_parameters") or {}).get("custom_prompt_template")
    if not isinstance(template, str):
        return False
    names = set(_PROMPT_PLACEHOLDER.findall(template))
    return any(_reference_field_name(ref) in names for ref in refs)


def graded_reference_fields(config: Any) -> list:
    """The reference parts of the field keys a config grades: ``[""]`` for a
    reference-free metric, the first reference field for a judge that reads
    its references itself (:func:`judge_reads_references_itself`; the cell
    falls back to the next one when the first is missing on a task), else
    every one of its ``reference_fields``."""
    if is_reference_free(config.get("metric")):
        return [""]
    refs = list(config.get("reference_fields") or [])
    if refs and judge_reads_references_itself(config):
        return refs[:1]
    return refs
