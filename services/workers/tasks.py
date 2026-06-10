import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import redis
from celery import Celery
from dotenv import load_dotenv
from sqlalchemy.exc import DBAPIError, OperationalError

# Import response parser for LLM response parsing
from response_parser import ResponseParser


# ─────────────────────────────────────────────────────────────────────────────
# System-wide parameter defaults — deepest fallback tier in the resolution
# chain. Anything missing from user_per_model / user_project / prompt_metadata
# / model.recommended_parameters falls back to these. Centralized so the
# "what's the deepest default for X" question has exactly one answer.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_DEFAULTS: Dict[str, Any] = {
    "temperature": 0.0,    # deterministic by default for benchmark reproducibility
    "max_tokens": 1500,    # small enough to keep cost low when nobody overrides
    "seed": 42,            # historical default kept for back-compat
    "top_p": 1.0,
}


def _clamp_temperature_to_constraint(
    temperature: Optional[float],
    parameter_constraints: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    """Apply per-model temperature constraints AFTER tier resolution.

    Returns ``(clamped_value, clamped_from)`` where ``clamped_from`` is the
    pre-clamp value when clamping was applied, else None. Used by both the
    generation pipeline and the judge pipeline so they enforce the same
    constraint (e.g. Claude Opus 4.7 / GPT-5 series temperature=1.0
    required, DeepSeek-R1 min=0.6).
    """
    # Defensive: callers may pass a Mock or other non-dict object (e.g. from
    # tests that don't model the catalog row exactly). Treat anything that
    # doesn't look like a dict as "no constraints".
    if not parameter_constraints or not isinstance(parameter_constraints, dict):
        return temperature, None
    temp_config = parameter_constraints.get("temperature") or {}
    if not isinstance(temp_config, dict):
        return temperature, None
    # Fixed-temperature models: coerce to required_value.
    if not temp_config.get("supported", True):
        required = temp_config.get("required_value")
        if required is not None and temperature != required:
            return required, temperature
        return temperature, None
    # Range models: clamp to [min, max].
    pre = temperature
    min_temp = temp_config.get("min")
    max_temp = temp_config.get("max")
    if temperature is not None and min_temp is not None and temperature < min_temp:
        return min_temp, pre
    if temperature is not None and max_temp is not None and temperature > max_temp:
        return max_temp, pre
    return temperature, None


def _resolve_param(
    key: str,
    mode: str,                           # "generation" or "evaluation"
    model_recommended: Optional[Dict[str, Any]],   # model.recommended_parameters
    project_cfg: Optional[Dict[str, Any]],
    per_model_cfg: Optional[Dict[str, Any]],
    prompt_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, str, Any]:
    """Resolve a single param value through the priority tiers, returning
    (final_value, source_tag, recommended_at_trigger_time).

    Priority (highest → lowest):
        1. prompt_metadata[key]              source="prompt_metadata"
        2. per_model_cfg[key]                source="user_per_model"
        3. project_cfg[key]                  source="user_project"
        4. model_recommended[mode][key]      source="recommended"
        5. model_recommended["default"][key] source="recommended"
        6. SYSTEM_DEFAULTS[key]              source="system"

    `recommended_at_trigger_time` is the recommended value that WOULD have
    been used (mode-specific first, then default block) regardless of which
    tier ultimately won. Recorded in provenance so analysts can later spot
    "user overrode the recommendation by 0.3" without re-reading the YAML
    at the point in time the run fired. Returns None if the model has no
    recommendation for this key in either block.

    Constraint clamping (`parameter_constraints.required_value`,
    `min`/`max`) is applied by the caller AFTER this helper returns — those
    are guardrails, not part of the precedence chain.
    """
    rec_default = (model_recommended or {}).get("default") or {}
    rec_mode = (model_recommended or {}).get(mode) or {}
    recommended_at_trigger = rec_mode.get(key, rec_default.get(key))

    if prompt_meta and key in prompt_meta:
        return (prompt_meta[key], "prompt_metadata", recommended_at_trigger)
    if per_model_cfg and key in per_model_cfg:
        return (per_model_cfg[key], "user_per_model", recommended_at_trigger)
    if project_cfg and key in project_cfg:
        return (project_cfg[key], "user_project", recommended_at_trigger)
    if key in rec_mode:
        return (rec_mode[key], "recommended", recommended_at_trigger)
    if key in rec_default:
        return (rec_default[key], "recommended", recommended_at_trigger)
    return (SYSTEM_DEFAULTS.get(key), "system", recommended_at_trigger)


# Logger konfigurieren (must be before database imports)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_insensitive(d: dict, key: str, default=""):
    """Get a value from dict with case-insensitive key lookup. Prefers exact match."""
    if key in d:
        return d[key]
    lower = key.lower()
    for k in d:
        if k.lower() == lower:
            return d[k]
    return default


def _llm_judge_columns_from_result(result: Optional[dict]) -> dict:
    """Phase 6.6: pull the eight academic-rigor column values + raw_output
    out of an LLM-judge ``result`` dict (which carries ``_call_metadata``
    and ``_raw_output`` after the evaluator change).

    Returns a kwargs dict suitable for splatting into the ``TaskEvaluation``
    constructor. Empty dict for non-LLM-judge results so deterministic
    metrics keep writing a row with NULL columns.
    """
    if not result or not isinstance(result, dict):
        return {}
    call_meta = result.get("_call_metadata") or {}
    if not isinstance(call_meta, dict):
        return {}
    return {
        "seed": call_meta.get("seed"),
        "finish_reason": call_meta.get("finish_reason"),
        "truncated": bool(call_meta.get("truncated", False)),
        "refusal": bool(call_meta.get("refusal", False)),
        "error_type": call_meta.get("error_type"),
        "latency_ms": call_meta.get("response_time_ms"),
        "input_tokens": call_meta.get("input_tokens"),
        "output_tokens": call_meta.get("output_tokens"),
        "raw_output": result.get("_raw_output"),
    }


def _build_multidim_judge_row_metrics(
    multidim: Optional[dict],
    metric: str,
    error_msg: Optional[str],
) -> tuple[dict, Optional[float]]:
    """Build the canonical ``TaskEvaluation.metrics`` dict for a multi-dim LLM judge row.

    Mirrors the shape produced by the immediate-eval path in
    ``_evaluate_llm_judge_single`` so bulk-eval and immediate-eval rows
    are queryable with the same JSON path. Returns ``(metrics_dict, normalized_value)``
    where ``normalized_value`` is in ``[0, 1]`` (total_score / total_max)
    or ``None`` on error / missing scores.

    For error cases the metrics blob still carries the metric key with
    ``value=None`` and the ``error`` message, so downstream consumers
    (``_row_has_score`` / ``_row_is_terminal_error``) treat it as a
    terminal failure instead of an unscored row.
    """
    if not multidim or multidim.get("error") or "scores" not in multidim:
        return (
            {
                metric: {
                    "value": None,
                    "method": metric,
                    "details": {
                        "raw_output": (multidim or {}).get("_raw_output", ""),
                        "call_metadata": (multidim or {}).get("_call_metadata", {}),
                    },
                    "error": (
                        error_msg
                        or (multidim or {}).get("error_message")
                        or "multi-dim LLM judge produced no scores"
                    ),
                },
            },
            None,
        )

    total = float(multidim.get("total_score") or 0.0)
    total_max = float(multidim.get("total_max") or 0.0)
    normalized = total / total_max if total_max > 0 else 0.0
    return (
        {
            metric: {
                "value": float(normalized),
                "method": metric,
                "details": {
                    "scores": multidim["scores"],
                    "total_score": total,
                    "total_max": total_max,
                    "overall_assessment": multidim.get("overall_assessment", ""),
                    "call_metadata": multidim.get("_call_metadata", {}),
                    "raw_output": multidim.get("_raw_output", ""),
                },
                "error": None,
            },
            "raw_score": float(normalized),
        },
        float(normalized),
    )


def _row_has_score(metrics: dict | None) -> bool:
    """A TaskEvaluation row counts as 'already evaluated' if any non-error
    metric carries a numeric value — either as a bare float (legacy shape)
    or under the unified ``{value, method, details, error}`` dict produced
    by SampleEvaluator after the academic-rigor overhaul.

    Without the dict-aware branch, every recently persisted row reads as
    "missing" and ``evaluate_missing_only=True`` silently re-runs every
    successful evaluation — burning API quota and shifting scores via LLM
    nondeterminism. Mirrors ``_coerce_metric_value`` from
    ``services/api/routers/evaluations/results.py``; kept duplicated rather
    than imported across the worker / API package boundary.
    """
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, dict):
            inner = v.get("value")
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return True
    return False


def _row_is_terminal_error(metrics: dict | None) -> bool:
    """A row that's been tried and failed in a non-recoverable way must NOT
    be re-tried on the next ``evaluate_missing_only=True`` run. The worker
    writes such rows with the unified ``{value: None, ..., error: "<msg>"}``
    blob shape, OR with a non-None top-level ``error_message`` on the row.

    Without this gate, every retry would re-attempt the same hopeless target,
    accumulate another stub row each time, and (if it's an LLM judge call)
    burn API budget on a call we already know fails. Pairs with
    ``_row_has_score`` — both must be considered when populating the
    "already evaluated" set in missing-only logic.
    """
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, dict) and v.get("error"):
            return True
    return False


def _normalize_field_key(field_name: str | None, *, is_annotation: bool) -> str | None:
    """Normalize a stored ``TaskEvaluation.field_name`` to the canonical
    pipe format ``{config_id}|{pred_field}|{ref_field}`` so missing-only
    matching tolerates legacy colon-separated rows and rows missing the
    ``human:`` annotation prefix.

    The worker has changed the separator from ``:`` to ``|`` and the
    annotation prefix convention at least once; without this normalization,
    rows persisted before the change get classified as "missing" and
    re-evaluated on every missing-only run — wasting API quota and
    polluting score history with duplicates under the new format.

    Bare legacy names (e.g. ``'loesung'``) without a separator are returned
    unchanged: recovering ``config_id`` requires project context that this
    helper doesn't have. The matching backfill ``migrate_field_names.py``
    should be run once per project to bring those rows up to canonical.
    """
    if not field_name:
        return field_name
    if "|" in field_name:
        parts = field_name.split("|")
    elif ":" in field_name:
        parts = field_name.split(":")
    else:
        return field_name  # bare legacy — caller should have backfilled
    if len(parts) != 3:
        return field_name
    cfg, pred, ref = parts
    if is_annotation and not pred.startswith("human:") and not pred.startswith("model:"):
        pred = f"human:{pred}"
    return f"{cfg}|{pred}|{ref}"


# Add current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Add /shared to sys.path early so top-level imports like `report_models`
# resolve before the ai_services block below. Mirrors api/main.py:29-33.
_shared_dir = (
    "/shared"
    if os.path.exists("/shared")
    else os.path.join(os.path.dirname(os.path.dirname(current_dir)), "shared")
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

# Import database and models at top level to avoid import issues in worker processes
try:
    from database import SessionLocal

    # Prompt import removed in Issue #759 - use generation_structure instead
    from models import LLMModel as DBLLMModel
    # Same table as `generations` — formerly the worker had a separate
    # LLMResponse class definition mapping to the same __tablename__, but
    # with /shared/models.py canonical, the API's `Generation` class is
    # the single definition. The DBLLMResponse alias is preserved so
    # callsites below don't have to change.
    from models import Generation as DBLLMResponse
    # Eagerly register project_models on the Base metadata BEFORE importing
    # report_models, so SQLAlchemy can resolve the `relationship("Project")`
    # back-reference declared on ProjectReport. Without this, the first
    # `db.query(DBProjectReport)` call (line ~1888 in generate_llm_responses)
    # raises InvalidRequestError: "expression 'Project' failed to locate a
    # name" because the worker's lazy project_models imports inside other
    # task bodies hadn't run yet.
    import project_models  # noqa: F401 — side-effect import
    from report_models import ProjectReport as DBProjectReport  # /shared — single source of truth
    from models import ResponseGeneration as DBResponseGeneration

    # DBTask removed - old task system cleanup
    # Note: project_models imported below to avoid circular imports
    # Note: DefaultConfigService removed (Issue #759)
    # Prompts are now defined inline or via generation_structure
    # Import notification service from API
    # Add parent directory to path to import from API
    api_dir = os.path.join(os.path.dirname(current_dir), "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)

    try:
        from models import NotificationType
        from notification_service import NotificationService, notify_task_completed

        HAS_NOTIFICATION_SERVICE = True
    except ImportError as _notif_imp_err:
        # Log loudly (not silently) so a real import bug in prod shows
        # up in worker logs instead of silently returning empty
        # notification lists — which is what hid the worker
        # NotificationService email-dispatch gap until 2026-05-19.
        logger.error(
            "❌ notification_service not importable — worker will accept "
            "create_notification calls but return [] and emit no events. "
            "Reason: %s",
            _notif_imp_err,
            exc_info=True,
        )

        def notify_task_completed(*args, **kwargs):
            return {"status": "mock", "notification_sent": False}

        class NotificationService:
            @staticmethod
            def create_notification(*args, **kwargs):
                return []

        class NotificationType:
            EVALUATION_COMPLETED = "evaluation_completed"
            EVALUATION_FAILED = "evaluation_failed"
            LLM_GENERATION_COMPLETED = "llm_generation_completed"

        HAS_NOTIFICATION_SERVICE = False

    # NOTE: Label Studio and annotation storage services removed
    # Using native annotation system now

    # Native annotation system in use

    # Import GenerationStructureParser for safe field interpolation (Issue #507, #519)
    try:
        from generation_structure_parser import GenerationStructureParser

        HAS_GENERATION_PARSER = True
        logger.info("✅ GenerationStructureParser imported successfully")
    except ImportError as e:
        logger.warning(f"⚠️ GenerationStructureParser not available: {e}")
        HAS_GENERATION_PARSER = False

    HAS_DATABASE = True
    logger.info("✅ Database and models imported successfully")
except ImportError as e:
    # In any non-test environment a worker without SessionLocal can't do
    # its job — every task body would hit a Mock that returns None / []
    # and pretend success. Log CRITICAL with stack so the gap is obvious;
    # also refuse to start in production/staging where the only correct
    # response is "fix it and redeploy", not "limp along returning mocks".
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "staging"):
        logger.critical(
            "❌ Failed to import database/models in production — refusing to start. %s",
            e,
            exc_info=True,
        )
        raise
    logger.critical(
        "❌ Failed to import database/models — falling back to in-memory mocks. "
        "Every task will return success-shaped data without touching the DB. "
        "Reason: %s",
        e,
        exc_info=True,
    )

    # Mock classes for testing
    class SessionLocal:
        def __init__(self):
            pass

        def query(self, model):
            return MockQuery()

        def commit(self):
            pass

        def close(self):
            pass

    class MockQuery:
        def filter(self, *args):
            return self

        def first(self):
            return None

        def all(self):
            return []

    class DBResponseGeneration:
        pass

    class DBLLMResponse:
        pass

    # DBPrompt mock removed in Issue #759 - use generation_structure instead

    class DBLLMModel:
        pass

    class DBProjectReport:
        pass

    HAS_DATABASE = False

# Import AI services from shared module to avoid duplication
try:
    # Add shared directory to path
    # In Docker container, shared services are mounted at /shared
    shared_dir = (
        "/shared"
        if os.path.exists("/shared")
        else os.path.join(os.path.dirname(os.path.dirname(current_dir)), "shared")
    )
    if shared_dir not in sys.path:
        sys.path.insert(0, shared_dir)

    from ai_services import (
        AnthropicService,
        DeepInfraService,
        GoogleService,
        OpenAIService,
        user_aware_ai_service,
    )

    HAS_AI_SERVICES = True
    logger.info("✅ AI services imported successfully from shared module")
except ImportError as e:
    # AI services are required for generation/evaluation tasks. Mirror the
    # SessionLocal fail-fast pattern above so a real import bug in prod
    # doesn't silently degrade every model call to a mock "response".
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "staging"):
        logger.critical(
            "❌ Failed to import AI services in production — refusing to start. %s",
            e,
            exc_info=True,
        )
        raise
    logger.critical(
        "❌ Failed to import AI services — generation/evaluation tasks will "
        "return mock 'Mock <provider> response' strings without ever calling "
        "the model. Reason: %s",
        e,
        exc_info=True,
    )

    # Mock classes for testing
    class OpenAIService:
        def is_available(self):
            return False

        async def generate_response(self, **kwargs):
            return {"response": "Mock OpenAI response", "tokens": 10, "cost": 0.001}

    class AnthropicService:
        def is_available(self):
            return False

        async def generate_response(self, **kwargs):
            return {"response": "Mock Anthropic response", "tokens": 10, "cost": 0.001}

    class GoogleService:
        def is_available(self):
            return False

        async def generate_response(self, **kwargs):
            return {"response": "Mock Google response", "tokens": 10, "cost": 0.001}

    class DeepInfraService:
        def is_available(self):
            return False

        async def generate_response(self, **kwargs):
            return {"response": "Mock DeepInfra response", "tokens": 10, "cost": 0.001}

    user_aware_ai_service = None
    HAS_AI_SERVICES = False

# Native annotation system configuration
# See Issue #108 and ADR-001 for migration details

try:
    from ml_evaluation import evaluator_registry
except ImportError:

    class MockEvaluatorRegistry:
        def get_supported_task_types(self):
            return ["qa", "qa_reasoning"]

        def get_supported_metrics(self, task_type):
            return ["accuracy", "precision", "recall"]

    evaluator_registry = MockEvaluatorRegistry()

# Umgebungsvariablen laden
load_dotenv()


def extract_label_config_fields(label_config: str) -> List[str]:
    """
    Extract annotation field names from Label Studio XML config.
    These field names should match the output field names from LLM responses.
    """
    from xml.etree import ElementTree

    fields = []
    try:
        root = ElementTree.fromstring(label_config)
        for elem in root.iter():
            # Only include annotation output elements (not data display elements like Header/Text)
            if elem.tag in ["TextArea", "Choices", "Rating", "Number"]:
                name = elem.get("name")
                if name:
                    fields.append(name)
    except Exception as e:
        logger.warning(f"Could not parse label_config for field extraction: {e}")
    return fields


# Celery-App initialisieren
app = Celery("tasks")

# Celery Beat Schedule for periodic tasks
from celery.schedules import crontab

# Beat schedule. `process-daily-digests` was removed with the email-digest
# feature (User-model columns commented out in models.py).
#
# `recompute-aggregates`: refresh the precomputed leaderboard + project
# summary tables. The API endpoints read these tables instead of scanning
# task_evaluations on every request (OOMed prod 2026-05-19). Migration 051
# introduced the tables; see services/shared/aggregate_summaries.py for
# the SQL.
#
# Cadence history:
# - 12h (initial): cheap, occasionally stale tiles after annotation rounds.
# - 1h (2026-05-20): tightened after Phase 6.2 routed the projects list
#   through project_summaries; users complained tiles lagged half a day.
# - 2x/day at 10:00 + 22:00 UTC (= 12:00 + 00:00 CEST) (this PR): leaderboards
#   are a research-grade scorecard, not a live tile — a noticeable user
#   refresh window is the right contract. Hourly runs were also adding
#   load without value once the leaderboards moved to TanStack-cached
#   reads with 30s staleTime on the client. Note: during winter (CET) the
#   runs effectively become 11:00 + 23:00 local; the leaderboards page
#   shows a static hint that copy-locks the schedule to CEST.
#
# Event-driven recompute on EvaluationRun finalize was also removed in
# the same change (search for `recompute_aggregates_after_finalize` — the
# `app.send_task` call in the finalize handler is gone).
app.conf.beat_schedule = {
    "recompute-aggregates": {
        "task": "tasks.recompute_aggregates",
        "schedule": crontab(minute=0, hour="10,22"),
        "args": (),
        "kwargs": {},
        "options": {"queue": "default"},
    },
}

app.conf.timezone = "UTC"

# Task routing configuration for different queues
app.conf.task_routes = {
    'emails.*': {'queue': 'emails'},
    'tasks.*': {'queue': 'default'},
}

# Rate limiting for email tasks to prevent overwhelming mail server
app.conf.task_annotations = {
    'emails.send_invitation': {'rate_limit': '30/m'},  # 30 invitations per minute
    'emails.send_bulk_invitations': {'rate_limit': '5/m'},  # 5 bulk operations per minute
}

# Build Redis URLs - prefer REDIS_URI for production compatibility
redis_uri = os.getenv("REDIS_URI")

if redis_uri:
    # Use REDIS_URI directly if provided (production environment)
    broker_url = redis_uri
    result_backend = redis_uri
else:
    # Fall back to building URL from components (development environment)
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")

    if redis_password:
        broker_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
        result_backend = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
    else:
        broker_url = f"redis://{redis_host}:{redis_port}/0"
        result_backend = f"redis://{redis_host}:{redis_port}/0"

app.conf.broker_url = os.getenv("CELERY_BROKER_URL", broker_url)
app.conf.result_backend = os.getenv("CELERY_RESULT_BACKEND", result_backend)


# ---- Progress pub/sub (workers → API WebSocket clients) ---------------------
#
# Per-cell evaluation and per-row generation commits broadcast on a
# project-scoped Redis channel. The API-side WS handlers
# (routers/evaluations/ws.py, routers/generation.py) subscribe to that
# channel and forward each message as a `tick` to the connected browser,
# which then re-fetches the cell/row view. This replaces the prior
# 2-second `count(*)` polling loop on the API side and gives the user
# near-instant cell-by-cell feedback.
#
# Failure is best-effort: a Redis hiccup must never fail the underlying
# DB commit. The publisher uses a lazy, process-local client built from
# the Celery broker URL (already resolved above).
_progress_redis_client: Optional["redis.Redis"] = None


def _get_progress_redis():
    """Return a lazily-built Redis client for progress publishing.

    Reuses the Celery broker URL so worker pods need no additional config
    or secret. Returns `None` if redis is unavailable for any reason —
    callers must tolerate this and proceed (the commit path is more
    important than the broadcast).
    """
    global _progress_redis_client
    if _progress_redis_client is not None:
        return _progress_redis_client
    try:
        _progress_redis_client = redis.Redis.from_url(
            app.conf.broker_url,
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        return _progress_redis_client
    except Exception as e:
        logger.warning(f"progress redis client init failed: {e}")
        return None


def _publish_progress(channel: str, payload: Dict[str, Any]) -> None:
    """Publish a progress event on `channel`. No-op on any error."""
    client = _get_progress_redis()
    if client is None:
        return
    try:
        client.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning(f"progress publish to {channel} failed: {e}")


def _extract_field_value_from_annotation(annotation_results: List[Dict], field_name: str) -> Any:
    """Extract value for a specific field from annotation results."""
    from annotation_utils import extract_field_value
    return extract_field_value(annotation_results, field_name)


def _extract_field_value_from_parsed_annotation(
    parsed_annotation: List[Dict], field_name: str
) -> Any:
    """Extract value for a specific field from parsed_annotation (Label Studio format)."""
    from annotation_utils import extract_field_value
    return extract_field_value(parsed_annotation, field_name)


@app.task(name="tasks.get_supported_metrics")
def get_supported_metrics(task_type: str = None) -> Dict[str, Any]:
    """
    Get supported metrics for a task type or all task types.

    Args:
        task_type: Specific task type (optional)

    Returns:
        Dictionary with supported metrics
    """
    try:
        if task_type:
            metrics = evaluator_registry.get_supported_metrics(task_type)
            return {"status": "success", "task_type": task_type, "metrics": metrics}
        else:
            # Get metrics for all supported task types
            all_metrics = {}
            for task_type in evaluator_registry.get_supported_task_types():
                all_metrics[task_type] = evaluator_registry.get_supported_metrics(task_type)

            return {
                "status": "success",
                "supported_task_types": evaluator_registry.get_supported_task_types(),
                "metrics_by_task_type": all_metrics,
            }

    except Exception as e:
        logger.error(f"Error getting supported metrics: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.task(name="tasks.cleanup_project_data")
def cleanup_project_data(project_id: str) -> Dict[str, Any]:
    """Clean up project data from Redis (updated for project-based system)."""
    try:
        # Use test Redis database (db=1) when testing
        if os.getenv("TESTING") == "true":
            redis_url = "redis://localhost:6379/1"
        else:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)

        # Clean up project data (updated for new project-based system)
        keys_to_delete = [
            f"project:{project_id}",  # New project-based key format
            f"task:{project_id}",  # Legacy key format for backward compatibility
        ]

        deleted_keys = 0
        for key in keys_to_delete:
            result = r.delete(key)
            deleted_keys += result

        logger.info(f"Cleaned up project data for {project_id}")
        return {"status": "success", "project_id": project_id, "deleted_keys": deleted_keys}
    except Exception as e:
        logger.error(f"Error cleaning up project data: {str(e)}")
        return {"status": "error", "project_id": project_id, "message": str(e)}


@app.task(name="tasks.auto_submit_expired_timer")
def auto_submit_expired_timer(session_id: str) -> Dict[str, Any]:
    """Server-side auto-submit when a strict timer expires.

    Scheduled at timer session creation with eta = started_at + time_limit_seconds.
    If the client already submitted (user was present), this is a no-op.
    """
    if not HAS_DATABASE:
        return {"status": "error", "message": "Database not available"}

    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        from project_models import Annotation, TimerSession, Project, Task

        session = db.query(TimerSession).filter(
            TimerSession.id == session_id
        ).first()

        if not session:
            return {"status": "skipped", "reason": "session not found"}
        if session.completed_at:
            return {"status": "skipped", "reason": "already completed"}

        # Issue #30 PR 3: korrektur timer sessions (target_type in
        # ('annotation', 'generation')) expire WITHOUT auto-creating a grade.
        # Korrektur is qualitative — auto-submitting a half-filled rubric as
        # the final score would corrupt the IRR analysis. Expiry just stops
        # the client countdown; the grader can still finish + submit via the
        # normal endpoint, or skip. Strict-mode blocking of post-expiry
        # submission can be added later if a project ever needs it.
        if session.target_type and session.target_type != "task":
            from datetime import datetime, timezone
            session.completed_at = datetime.now(timezone.utc)
            session.auto_submitted = True
            db.commit()
            return {
                "status": "expired_korrektur",
                "reason": "korrektur sessions don't auto-grade",
            }

        # Check if user already has an annotation for this task (client beat us)
        existing = db.query(Annotation).filter(
            Annotation.task_id == session.task_id,
            Annotation.completed_by == session.user_id,
        ).first()
        if existing:
            now = datetime.now(timezone.utc)
            session.completed_at = now
            session.auto_submitted = True
            db.commit()
            return {"status": "skipped", "reason": "annotation already exists"}

        # Use draft if available: try timer session first, then task_drafts table
        result = session.draft_result
        if not result:
            from project_models import TaskDraft
            draft = db.query(TaskDraft).filter(
                TaskDraft.task_id == session.task_id,
                TaskDraft.user_id == session.user_id,
            ).first()
            result = draft.draft_result if draft and draft.draft_result else []

        import uuid
        now = datetime.now(timezone.utc)

        annotation = Annotation(
            id=str(uuid.uuid4()),
            task_id=session.task_id,
            project_id=session.project_id,
            completed_by=session.user_id,
            result=result,
            auto_submitted=True,
            lead_time=float(session.time_limit_seconds),
        )
        db.add(annotation)

        # Update task counters
        task = db.query(Task).filter(Task.id == session.task_id).first()
        if task and result and len(result) > 0:
            task.total_annotations = (task.total_annotations or 0) + 1
            project = db.query(Project).filter(Project.id == session.project_id).first()
            if project:
                from sqlalchemy import String, cast, func
                non_cancelled = db.query(Annotation).filter(
                    Annotation.task_id == session.task_id,
                    Annotation.was_cancelled == False,
                    Annotation.result.isnot(None),
                    func.length(cast(Annotation.result, String)) > 2,
                ).count() + 1  # +1 for the annotation being created
                if non_cancelled >= project.min_annotations_per_task:
                    task.is_labeled = True

        # Complete the timer session
        session.completed_at = now
        session.auto_submitted = True
        db.commit()

        logger.info(f"Server-side auto-submit for session {session_id}: annotation {annotation.id}")
        return {"status": "submitted", "annotation_id": annotation.id}

    except Exception as e:
        db.rollback()
        logger.error(f"Auto-submit failed for session {session_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@app.task(name="tasks.generate_synthetic_data")
def generate_synthetic_data(task_id: str, num_samples: int = 10) -> Dict[str, Any]:
    """Generate synthetic data for a task."""
    try:
        # This would normally use a real LLM to generate data
        synthetic_data = []

        for i in range(num_samples):
            synthetic_data.append(
                {
                    "text": f"Generated legal text sample {i + 1} for task {task_id}",
                    "label": "contract" if i % 2 == 0 else "agreement",
                }
            )

        logger.info(f"Generated {num_samples} synthetic samples for task {task_id}")
        return {
            "status": "success",
            "task_id": task_id,
            "generated_count": num_samples,
            "data": synthetic_data,
        }

    except Exception as e:
        logger.error(f"Error generating synthetic data: {str(e)}")
        return {"status": "error", "task_id": task_id, "message": str(e)}


# Evaluation processing happens via run_evaluation().


# Additional functions for performance tests
def generate_classification_samples(num_samples: int = 100) -> List[Dict[str, Any]]:
    """Generate classification samples for performance testing."""
    import random

    samples = []
    categories = ["contract", "agreement", "legal_opinion", "judgment", "statute"]

    for i in range(num_samples):
        samples.append(
            {
                "id": i,
                "text": f"Legal document sample {i + 1} with some complex legal language and terminology.",
                "category": random.choice(categories),
                "confidence": random.uniform(0.6, 0.95),
            }
        )

    return samples


@app.task(name="tasks.generate_llm_responses")
def generate_llm_responses(
    generation_id: str,
    config_data: dict,
    model_id: str,
    user_id: str,
    structure_key: str = None,
    organization_id: str = None,
    run_index: int = 0,
) -> Dict[str, Any]:
    """
    Generate LLM responses asynchronously using Celery

    Args:
        generation_id: Unique identifier for this generation run
        config_data: Task evaluation configuration data
        model_id: ID of the model to use for generation
        user_id: ID of the user who initiated the generation (for API key lookup)
        structure_key: Key for prompt structure in generation_config.prompt_structures (Issue #762)
        organization_id: Optional org context for API key resolution (Issue #1180)
        run_index: Multi-run trial index (migration 041). Stamped on the
            child Generation row; the parent ResponseGeneration aggregates
            via runs_completed/runs_failed counters bumped at the end of
            this function.

    Returns:
        Dictionary with generation results
    """
    logger.info(f"🚀 Starting real LLM generation for model {model_id}, generation {generation_id}")

    try:
        # Import additional modules needed for generation
        import asyncio
        import json
        import uuid
        from datetime import datetime

        # Check if database is available
        if not HAS_DATABASE:
            raise Exception("Database not available - check database connection")

        # Create database session
        db = SessionLocal()

        try:
            # Get generation record
            generation = (
                db.query(DBResponseGeneration)
                .filter(DBResponseGeneration.id == generation_id)
                .first()
            )
            if not generation:
                raise Exception(f"Generation record {generation_id} not found")

            # Check if generation was cancelled before we start (e.g., by a new "all" mode run)
            if generation.status == "cancelled":
                logger.info(f"⏭️ Skipping cancelled generation {generation_id}")
                return {
                    "status": "skipped",
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": "Generation was cancelled before processing",
                }

            # Store structure_key if provided (Issue #762)
            if structure_key:
                generation.structure_key = structure_key
                logger.info(f"🔑 Using prompt structure: {structure_key}")

            # Update status to running
            generation.status = "running"
            generation.started_at = datetime.now()
            db.commit()

            logger.info(f"🤖 Starting real LLM generation for model {model_id}")

            # Get project details first
            from project_models import Project

            project_id = config_data.get(
                "project_id", config_data.get("task_id")
            )  # Support both keys for compatibility
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise Exception(f"Project {project_id} not found")

            # Issue #762: Fetch prompt structure from generation_config if structure_key provided
            generation_structure = None
            if structure_key and project.generation_config:
                prompt_structures = project.generation_config.get("prompt_structures", [])
                # Handle both list format (new) and dict format (legacy)
                if isinstance(prompt_structures, list):
                    # List format: find structure by key or numeric index
                    # First try to find by key
                    for ps in prompt_structures:
                        if ps.get("key") == structure_key:
                            generation_structure = ps.get("structure", ps)
                            logger.info(
                                f"✅ Loaded prompt structure '{structure_key}' from generation_config (list format)"
                            )
                            break
                    # If not found by key, try numeric index
                    if not generation_structure:
                        try:
                            idx = int(structure_key)
                            if 0 <= idx < len(prompt_structures):
                                ps = prompt_structures[idx]
                                generation_structure = ps.get("structure", ps)
                                logger.info(
                                    f"✅ Loaded prompt structure at index {idx} from generation_config (list format)"
                                )
                        except (ValueError, TypeError):
                            pass
                    if not generation_structure:
                        available_keys = [
                            ps.get("key", str(i)) for i, ps in enumerate(prompt_structures)
                        ]
                        raise Exception(
                            f"Prompt structure '{structure_key}' not found in project generation_config. "
                            f"Available structures: {available_keys}"
                        )
                elif isinstance(prompt_structures, dict):
                    # Legacy dict format
                    if structure_key in prompt_structures:
                        generation_structure = prompt_structures[structure_key]
                        logger.info(
                            f"✅ Loaded prompt structure '{structure_key}' from generation_config (dict format)"
                        )
                    else:
                        raise Exception(
                            f"Prompt structure '{structure_key}' not found in project generation_config. "
                            f"Available structures: {list(prompt_structures.keys())}"
                        )

            # Default prompts (overridden by generation_structure if configured)
            # Note: DefaultConfigService removed in Issue #759, using hardcoded defaults
            system_prompt = "Sie sind ein erfahrener Jurist mit Expertise im deutschen Zivilrecht und Arbeitsrecht. Analysieren Sie rechtliche Sachverhalte präzise und fundiert."
            instruction_prompt_text = "Beantworten Sie die Frage mit 'Ja' oder 'Nein' und geben Sie anschließend eine ausführliche rechtliche Begründung. Format: Antwort: <Ja/Nein> Begründung: <ausführliche Begründung>"

            # Create instruction_prompts list for iteration (single default prompt)
            instruction_prompts = [
                {
                    "id": "default_instruction",
                    "prompt_text": instruction_prompt_text,
                    "prompt_name": "Default Legal Analysis",
                }
            ]

            # Get task data directly from database
            # Issue #762: Use the specific task_id from generation record, not all project tasks
            try:
                from project_models import Task as ProjectTask

                # Query only the specific task for this generation
                task_id = generation.task_id
                task = (
                    db.query(ProjectTask)
                    .filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
                    .first()
                )

                if not task:
                    raise Exception(f"Task {task_id} not found in project {project_id}")

                # Convert to dictionary format expected by generation code
                tasks_data = [
                    {
                        "id": task.id,
                        "project_id": task.project_id,
                        "data": task.data,  # JSONB field containing task data
                        "meta": task.meta,
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                    }
                ]

            except Exception as e:
                logger.error(f"Error loading task data from database: {e}")
                raise Exception(f"Failed to load task data from database: {str(e)}")

            if not tasks_data:
                raise Exception("No task data found in native annotation system")

            # Get model info
            model = db.query(DBLLMModel).filter(DBLLMModel.id == model_id).first()
            if not model:
                raise Exception(f"Model {model_id} not found")

            # Check if AI services are available
            if not HAS_AI_SERVICES:
                raise Exception("AI services not available - check service imports")

            # Initialize user-aware AI service based on model provider and user's/org's API keys
            try:
                ai_service = user_aware_ai_service.get_ai_service_for_user(
                    db, user_id, model.provider, organization_id=organization_id
                )
                # Read the actual resolution route off the service so the log
                # reflects which key path the resolver took, not just whether
                # an org_id was passed (issue #82).
                route = (
                    getattr(ai_service, "_key_resolution_route", "user_key")
                    if ai_service
                    else "unresolved"
                )
                logger.info(
                    f"Using API key via {route} "
                    f"(org_context={organization_id}, user={user_id}) for {model.provider}"
                )
            except Exception as e:
                error_msg = str(e)
                if (
                    "no API key configured" in error_msg.lower()
                    or "api key not found" in error_msg.lower()
                ):
                    logger.error(f"❌ User {user_id} has no API key configured for {model.provider}")
                    raise Exception(
                        f"API key required: User must configure {model.provider} API key in profile settings to use this model"
                    )
                else:
                    logger.error(
                        f"❌ Failed to get user-aware AI service for user {user_id}, provider {model.provider}: {e}"
                    )
                    # Security fix: No fallback to global API keys - user must configure their own keys
                    raise Exception(
                        f"API key error: Unable to initialize {model.provider} service for user {user_id}. "
                        f"Please check your API key configuration in profile settings. Error: {error_msg}"
                    )

            if ai_service is None:
                key_context = "organization settings" if organization_id else "profile settings"
                raise Exception(
                    f"No {model.provider} API key configured. Please add your API key in {key_context} to use this model."
                )

            if not ai_service.is_available():
                raise Exception(
                    f"AI service for {model.provider} is not available - check API key configuration"
                )

            # Use model.id for API calls - it contains the actual API identifier
            # model.id = API model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            # model.name = display name (e.g., "GPT-4o", "Claude 3.5 Sonnet")
            api_model_name = model.id

            responses_generated = 0
            total_expected = len(tasks_data) * len(instruction_prompts)

            logger.info(
                f"🎯 Expected to generate: {total_expected} responses ({len(tasks_data)} tasks × {len(instruction_prompts)} prompts)"
            )

            # Rate limiting configuration (Issue #482)
            import time

            # Rate limits per provider (requests per minute)
            RATE_LIMITS = {
                "OpenAI": 60,  # 60 requests per minute for GPT models
                "Anthropic": 50,  # 50 requests per minute for Claude
                "Google": 60,  # 60 requests per minute for Gemini
                "DeepInfra": 100,  # Higher limit for open models
                "Meta": 100,  # Same as DeepInfra
                "Grok": 60,  # xAI
                "Mistral": 60,  # Mistral AI
                "Cohere": 100,  # Cohere - higher limit
            }

            # Get rate limit for this provider
            provider_rate_limit = RATE_LIMITS.get(model.provider, 60)

            # Calculate minimum delay between requests (in seconds)
            min_delay = 60.0 / provider_rate_limit

            # Allow configuration override from config_data
            if "rate_limit_delay" in config_data:
                min_delay = config_data["rate_limit_delay"]

            logger.info(
                f"⏱️ Rate limiting: {provider_rate_limit} req/min, {min_delay:.2f}s delay between requests"
            )

            last_request_time = 0

            # Capture prompt templates for provenance
            # Use the generation_structure (what the user configures) as source of truth
            if generation_structure:
                # Extract template string from structure fields
                # Fields can be either a dict with "template" key or a plain string
                sys_field = generation_structure.get("system_prompt")
                instr_field = generation_structure.get("instruction_prompt")
                _captured_prompt_templates = {
                    "system_prompt": sys_field.get("template", system_prompt) if isinstance(sys_field, dict) else (sys_field or system_prompt),
                    "instruction_prompt": instr_field.get("template", instruction_prompt_text) if isinstance(instr_field, dict) else (instr_field or instruction_prompt_text),
                }
            else:
                _captured_prompt_templates = {
                    "system_prompt": system_prompt,
                    "instruction_prompt": instruction_prompt_text,
                }
            _captured_prompt_json = json.dumps(
                _captured_prompt_templates, ensure_ascii=False, sort_keys=True
            )
            _captured_parameters = None
            _last_error = None

            # Generate responses for each task and prompt combination
            for task_data in tasks_data:
                task_content = task_data.get("data", {})

                for instruction_prompt in instruction_prompts:
                    try:
                        # Handle both database objects and dict objects
                        if hasattr(instruction_prompt, "id"):
                            # Database object
                            prompt_id = instruction_prompt.id
                            prompt_text = instruction_prompt.prompt_text
                            prompt_name = instruction_prompt.prompt_name
                        else:
                            # Dict object (fallback)
                            prompt_id = instruction_prompt["id"]
                            prompt_text = instruction_prompt["prompt_text"]
                            prompt_name = instruction_prompt["prompt_name"]

                        # Check if response already exists (unless force_rerun is True)
                        force_rerun = config_data.get("force_rerun", False)

                        if not force_rerun:
                            # Check for existing completed response with prompt provenance
                            # Single query: join to get both response and stored prompt
                            existing = (
                                db.query(
                                    DBLLMResponse.id,
                                    DBResponseGeneration.prompt_used,
                                )
                                .join(
                                    DBResponseGeneration,
                                    DBLLMResponse.generation_id == DBResponseGeneration.id,
                                )
                                .filter(
                                    DBLLMResponse.task_id == task_data["id"],
                                    DBLLMResponse.model_id == model_id,
                                    DBResponseGeneration.structure_key == structure_key,
                                    DBLLMResponse.status == "completed",
                                )
                                .order_by(DBLLMResponse.created_at.desc())
                                .first()
                            )

                            if existing:
                                _, stored_prompt = existing
                                if stored_prompt is None or stored_prompt == _captured_prompt_json:
                                    logger.info(
                                        f"⏭️ Skipping existing response for task {task_data['id']}, "
                                        f"prompt {'unchanged' if stored_prompt else 'legacy'}"
                                    )
                                    continue
                                else:
                                    logger.info(
                                        f"🔄 Prompt changed for task {task_data['id']}, regenerating"
                                    )
                        else:
                            logger.info(
                                f"🔄 Force regenerating response for task {task_data['id']}, prompt {prompt_id}"
                            )

                        # Prepare the prompt - use safe field interpolation if enabled (Issue #507)
                        user_prompt = prompt_text

                        # Use safe generation structure parsing if available (Issue #507, #519, #762)
                        if HAS_GENERATION_PARSER and generation_structure:
                            logger.info(
                                f"🔒 Using generation structure '{structure_key}' for task {task_data['id']}"
                            )
                            try:
                                parser = GenerationStructureParser()
                                # Process the generation structure to filter task data
                                # V2 returns (prompts_dict, filtered_data)
                                prompts, filtered_data = parser.process_generation_structure(
                                    task_data=task_content,
                                    generation_structure=generation_structure,
                                    fallback_instruction=prompt_text,
                                )

                                # Use generated prompts if available
                                if 'system_prompt' in prompts:
                                    system_prompt = prompts['system_prompt']
                                    logger.info(
                                        f"✅ Using structured system prompt for task {task_data['id']}"
                                    )

                                if 'instruction_prompt' in prompts:
                                    user_prompt = prompts['instruction_prompt']
                                    logger.info(
                                        f"✅ Applied generation structure '{structure_key}' for task {task_data['id']}"
                                    )
                                else:
                                    # Fallback to original prompt if no instruction generated
                                    user_prompt = prompt_text
                                    logger.info(
                                        f"⚠️ No instruction prompt generated, using fallback for task {task_data['id']}"
                                    )

                            except Exception as e:
                                logger.error(
                                    f"Error applying generation structure '{structure_key}': {e}"
                                )
                                # Fall back to original behavior on error
                                for key, value in task_content.items():
                                    placeholder = f"{{{key}}}"
                                    if placeholder in user_prompt:
                                        user_prompt = user_prompt.replace(placeholder, str(value))
                        else:
                            # Original behavior - simple interpolation
                            for key, value in task_content.items():
                                placeholder = f"{{{key}}}"
                                if placeholder in user_prompt:
                                    user_prompt = user_prompt.replace(placeholder, str(value))

                        logger.info(
                            f"🎯 Generating response for task {task_data['id']}, model {model_id}, prompt {prompt_id}"
                        )

                        # Extract generation config for this model from PROJECT (not config_data)
                        # project.generation_config.selected_configuration.model_configs
                        project_gen_config = project.generation_config or {}
                        selected_config_for_model = project_gen_config.get(
                            "selected_configuration", {}
                        )
                        model_config = selected_config_for_model.get("model_configs", {}).get(
                            model_id, {}
                        )

                        # Tiered parameter resolution via the shared
                        # `_resolve_param` helper (see top of this file).
                        # Returns (value, source_tag, recommended_at_trigger)
                        # per key so the provenance snapshot below can record
                        # what the recommended value was at trigger time even
                        # when a user override won — making "user deviated
                        # from provider's recommendation" auditable post-hoc.
                        project_params = selected_config_for_model.get("parameters", {})

                        # Per-model overrides may live either flat on
                        # model_config or nested under model_config.generation_config
                        # (legacy shape kept for backward-compat). Flatten so
                        # the resolver only has to look one place.
                        per_model_flat: Dict[str, Any] = {}
                        if model_config:
                            for _k in ("temperature", "max_tokens", "seed", "top_p"):
                                if _k in model_config:
                                    per_model_flat[_k] = model_config[_k]
                                elif (
                                    isinstance(model_config.get("generation_config"), dict)
                                    and _k in model_config["generation_config"]
                                ):
                                    per_model_flat[_k] = model_config["generation_config"][_k]

                        prompt_meta_dict = (
                            instruction_prompt.prompt_metadata
                            if (
                                hasattr(instruction_prompt, "prompt_metadata")
                                and instruction_prompt.prompt_metadata
                            )
                            else None
                        )

                        model_recommended = (
                            getattr(model, "recommended_parameters", None) or None
                        )

                        _provenance: Dict[str, Dict[str, Any]] = {}

                        def _resolve(key: str) -> Any:
                            value, source, rec_at_trigger = _resolve_param(
                                key=key,
                                mode="generation",
                                model_recommended=model_recommended,
                                project_cfg=project_params,
                                per_model_cfg=per_model_flat,
                                prompt_meta=prompt_meta_dict,
                            )
                            _provenance[key] = {
                                "value": value,
                                "source": source,
                                "recommended_at_trigger": rec_at_trigger,
                            }
                            return value

                        temperature = _resolve("temperature")
                        max_tokens = _resolve("max_tokens")
                        seed = _resolve("seed")
                        if _provenance["temperature"]["source"] != "system":
                            logger.info(
                                f"🌡️ temperature={temperature} from "
                                f"{_provenance['temperature']['source']} "
                                f"(recommended at trigger: {_provenance['temperature']['recommended_at_trigger']})"
                            )

                        # Multi-run variance: when this is one of N>1 trials
                        # (run_index > 0 or runs_requested > 1), perturb the seed
                        # by run_index. Without this, OpenAI's seed parameter
                        # makes every trial deterministic-identical even at
                        # temperature=1.0 — defeating the purpose of variance
                        # studies. Run 0 keeps the user's chosen seed for
                        # reproducibility; runs 1..N-1 get seed+run_index.
                        # If the user explicitly wants identical seeds across
                        # runs (a sanity check), they can pin seed via
                        # generation_config and set runs_per_task = 1.
                        try:
                            _rr = int(getattr(generation, "runs_requested", 1) or 1)
                        except (TypeError, ValueError):
                            _rr = 1
                        if _rr > 1 and run_index > 0:
                            _seed_pre = seed
                            seed = (seed or 0) + run_index
                            logger.info(
                                f"🎲 Multi-run trial {run_index}/{_rr}: "
                                f"seed perturbed to {seed} for variance"
                            )
                            # Record the actual seed sent to the API in
                            # provenance, plus the pre-perturbation value
                            # so an analyst can see the variance offset.
                            if "seed" in _provenance:
                                _provenance["seed"]["value"] = seed
                                _provenance["seed"]["multi_run_offset"] = run_index
                                _provenance["seed"]["pre_perturbation"] = _seed_pre

                        # Extract reasoning/thinking config from model_config.
                        # Phase 6.6: also forward `seed` here so all four
                        # ai_service.generate{,_structured}() call sites
                        # below receive it via **reasoning_kwargs without
                        # needing per-site changes.
                        reasoning_kwargs = {"seed": seed}
                        if model_config:
                            # OpenAI o-series: reasoning_effort
                            if "reasoning_effort" in model_config:
                                reasoning_kwargs["reasoning_effort"] = model_config[
                                    "reasoning_effort"
                                ]
                            # Anthropic/Qwen: thinking_budget
                            if "thinking_budget" in model_config:
                                reasoning_kwargs["thinking_budget"] = model_config[
                                    "thinking_budget"
                                ]
                            # Mistral: prompt_mode
                            if "prompt_mode" in model_config:
                                reasoning_kwargs["prompt_mode"] = model_config["prompt_mode"]
                            # Cohere: thinking_token_budget
                            if "thinking_token_budget" in model_config:
                                reasoning_kwargs["thinking_token_budget"] = model_config[
                                    "thinking_token_budget"
                                ]

                        # Apply model-specific parameter constraints (final
                        # guardrail after the precedence chain). Clamping
                        # also patches `_provenance.temperature.value` so
                        # the snapshot reflects what was actually sent to
                        # the LLM, not the user's pre-clamp choice — but
                        # `source` and `recommended_at_trigger` are kept
                        # so analysts can still see "user tried X, model
                        # forced Y".
                        if hasattr(model, 'parameter_constraints') and model.parameter_constraints:
                            constraints = model.parameter_constraints
                            temp_config = constraints.get('temperature', {})

                            # Fixed temperature (e.g., GPT-5 series, o-series)
                            if not temp_config.get('supported', True):
                                required_temp = temp_config.get('required_value')
                                if required_temp is not None:
                                    if temperature != required_temp:
                                        logger.info(
                                            f"🔒 Overriding temperature to {required_temp} for {api_model_name} (model requirement)"
                                        )
                                        _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = required_temp
                                    _provenance["temperature"]["value"] = temperature
                            else:
                                # Clamp to allowed min/max range
                                min_temp = temp_config.get('min')
                                max_temp = temp_config.get('max')
                                if min_temp is not None and temperature < min_temp:
                                    logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to min {min_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = min_temp
                                    _provenance["temperature"]["value"] = temperature
                                if max_temp is not None and temperature > max_temp:
                                    logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to max {max_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = max_temp
                                    _provenance["temperature"]["value"] = temperature

                        logger.info(
                            f"🌡️ Final temperature: {temperature}, max_tokens: {max_tokens} for model {model_id}"
                        )

                        # Capture resolved parameters for provenance.
                        # `_param_provenance` records (value, source,
                        # recommended_at_trigger) per key so analysts can
                        # group runs by which tier won (system / recommended
                        # / user_*) and detect deviation from provider
                        # recommendations even after the YAML changes.
                        if _captured_parameters is None:
                            _captured_parameters = {
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                **reasoning_kwargs,
                                "_param_provenance": _provenance,
                            }

                        # Apply rate limiting (Issue #482)
                        current_time = time.time()
                        time_since_last = current_time - last_request_time

                        if time_since_last < min_delay:
                            sleep_time = min_delay - time_since_last
                            logger.info(f"⏳ Rate limiting: sleeping for {sleep_time:.2f}s")
                            time.sleep(sleep_time)

                        # Update last request time after the delay
                        last_request_time = time.time()

                        # Generate JSON schema from label_config for structured output
                        json_schema = None
                        use_structured_output = False
                        if project.label_config:
                            try:
                                from ai_services import generate_json_schema_from_label_config

                                json_schema = generate_json_schema_from_label_config(
                                    project.label_config
                                )
                                if json_schema.get("properties"):
                                    use_structured_output = True
                                    logger.info(
                                        f"📋 Generated JSON schema for structured output: {list(json_schema['properties'].keys())}"
                                    )
                            except Exception as schema_error:
                                logger.warning(f"⚠️ Could not generate JSON schema: {schema_error}")

                        # Extract field names from label_config and append output schema to prompt
                        # This ensures LLM produces fields matching annotation field names
                        if project.label_config:
                            output_fields = extract_label_config_fields(project.label_config)
                            if output_fields:
                                output_schema = {
                                    field: "<your response>" for field in output_fields
                                }
                                schema_instruction = (
                                    "\n\n---\n"
                                    "IMPORTANT: Respond ONLY with valid JSON using these exact field names:\n"
                                    f"```json\n{json.dumps(output_schema, indent=2)}\n```"
                                )
                                user_prompt = user_prompt + schema_instruction
                                logger.info(
                                    f"📋 Appended output schema instruction with fields: {output_fields}"
                                )

                        # Generate response using appropriate AI service
                        if use_structured_output and hasattr(ai_service, 'generate_structured'):
                            # Use structured output for guaranteed JSON responses
                            logger.info(
                                f"🔧 Using structured output generation for {model.provider}"
                            )

                            # Use user_prompt directly - it already contains interpolated fields from prompt structure
                            # DO NOT append task_content here as it contains sensitive fields (binary_solution, reasoning)
                            final_prompt = user_prompt

                            # Check if service has async or sync generate_structured
                            if asyncio.iscoroutinefunction(ai_service.generate_structured):

                                async def generate_structured_response():
                                    return await ai_service.generate_structured(
                                        prompt=final_prompt,
                                        system_prompt=system_prompt,
                                        json_schema=json_schema,
                                        model_name=api_model_name,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        **reasoning_kwargs,
                                    )

                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    response_data = loop.run_until_complete(
                                        generate_structured_response()
                                    )
                                finally:
                                    loop.close()
                            else:
                                # Sync version
                                response_data = ai_service.generate_structured(
                                    prompt=final_prompt,
                                    system_prompt=system_prompt,
                                    json_schema=json_schema,
                                    model_name=api_model_name,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    **reasoning_kwargs,
                                )
                        else:
                            # Standard text generation (no structured output)
                            logger.info(f"🔧 Using standard generate for {model.provider}")

                            if asyncio.iscoroutinefunction(ai_service.generate):

                                async def generate_response():
                                    return await ai_service.generate(
                                        prompt=user_prompt,
                                        system_prompt=system_prompt,
                                        model_name=api_model_name,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        **reasoning_kwargs,
                                    )

                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    response_data = loop.run_until_complete(
                                        generate_response()
                                    )
                                finally:
                                    loop.close()
                            else:
                                response_data = ai_service.generate(
                                    prompt=user_prompt,
                                    system_prompt=system_prompt,
                                    model_name=api_model_name,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    **reasoning_kwargs,
                                )

                        # Extract response content and metadata
                        logger.info(f"🔍 Raw response_data keys: {list(response_data.keys())}")
                        logger.info(f"🔍 Raw response_data: {response_data}")

                        # Check if AI service reported an error (e.g., 503, rate limit, safety block)
                        if not response_data.get("success", True):
                            raw_error = response_data.get("error", "Unknown AI service error")
                            # Try to extract the human-readable message from API error JSON
                            match = re.search(r"'message':\s*'([^']+)'", str(raw_error))
                            error_msg = match.group(1) if match else str(raw_error)
                            raise Exception(error_msg)

                        if "response_text" in response_data:
                            response_text = response_data["response_text"]
                            usage_stats = {
                                "prompt_tokens": response_data.get("prompt_tokens", 0),
                                "completion_tokens": response_data.get("completion_tokens", 0),
                                "total_tokens": response_data.get("total_tokens", 0),
                                "cost_usd": response_data.get("cost_usd", 0.0),
                            }
                            metadata = {
                                "prompt_id": prompt_id,
                                "prompt_name": prompt_name,
                                "temperature": response_data.get("temperature", 0.0),
                                "provider": response_data.get("provider", model.provider),
                                "system_prompt": system_prompt,
                                "instruction_prompt": user_prompt,
                                # Phase 6.1+6.2+6.5: merge AI-service-side audit
                                # trail (requested/actual temperature, retry
                                # history, provider route, billed user/org)
                                # so it lands on Generation rows alongside
                                # the worker-side metadata. The service-side
                                # dict can't override worker-set keys above.
                                **{
                                    k: v
                                    for k, v in (response_data.get("metadata") or {}).items()
                                    if k not in {
                                        "prompt_id", "prompt_name",
                                        "system_prompt", "instruction_prompt",
                                    }
                                },
                                # Issue #82: stamp the key-resolution audit
                                # fields directly off the service so every
                                # provider (not just openai) lands them.
                                "key_resolution_route": getattr(ai_service, "_key_resolution_route", None),
                                "provider_name": getattr(ai_service, "_provider_name", None),
                                "invocation_user_id": getattr(ai_service, "_invocation_user_id", None),
                                "invocation_organization_id": getattr(ai_service, "_invocation_organization_id", None),
                            }
                            logger.info(
                                f"✅ Using response_text format, content length: {len(response_text)}"
                            )
                        elif "content" in response_data:
                            # OpenAI format
                            response_text = response_data["content"]
                            usage_stats = response_data.get("usage", {})
                            metadata = {
                                "prompt_id": prompt_id,
                                "prompt_name": prompt_name,
                                "temperature": response_data.get("temperature", 0.0),
                                "provider": model.provider,
                                "system_prompt": system_prompt,
                                "instruction_prompt": user_prompt,
                                # Same merge as above (Phase 6 audit trail).
                                **{
                                    k: v
                                    for k, v in (response_data.get("metadata") or {}).items()
                                    if k not in {
                                        "prompt_id", "prompt_name",
                                        "system_prompt", "instruction_prompt",
                                    }
                                },
                                # Issue #82: same key-resolution audit fields.
                                "key_resolution_route": getattr(ai_service, "_key_resolution_route", None),
                                "provider_name": getattr(ai_service, "_provider_name", None),
                                "invocation_user_id": getattr(ai_service, "_invocation_user_id", None),
                                "invocation_organization_id": getattr(ai_service, "_invocation_organization_id", None),
                            }
                            logger.info(
                                f"✅ Using content format, content length: {len(response_text)}"
                            )
                        else:
                            logger.error(
                                f"❌ Unexpected response format - available keys: {list(response_data.keys())}"
                            )
                            raise Exception(f"Unexpected response format: {response_data}")

                        # Reject empty responses from any provider
                        if not response_text or not response_text.strip():
                            raise Exception(
                                f"AI service returned empty response for {model_id}"
                            )

                        logger.info(
                            f"📝 Final response_text length: {len(response_text)}"
                        )
                        logger.info(
                            f"📝 Response preview: {response_text[:100] if response_text else 'EMPTY'}"
                        )
                        logger.info(f"📊 Usage stats: {usage_stats}")

                        # Parse LLM response to structured format
                        parse_result = None
                        parsed_annotation = None
                        parse_status = "pending"
                        parse_error = None
                        parse_metadata = {}
                        final_status = "completed"

                        # Check existing parse attempts for retry limiting
                        existing_attempts = (
                            db.query(DBLLMResponse)
                            .filter(
                                DBLLMResponse.task_id == task_data["id"],
                                DBLLMResponse.model_id == model_id,
                            )
                            .count()
                        )

                        MAX_PARSE_RETRIES = 3

                        # Attempt parsing if we have label_config (structured output responses are JSON)
                        # generation_structure is optional - ResponseParser can auto-derive schema from label_config
                        if project.label_config:
                            try:
                                logger.info(f"🔍 Parsing LLM response for task {task_data['id']}")
                                # Use empty dict if no generation_structure (parser auto-derives from label_config)
                                parser = ResponseParser(
                                    generation_structure=generation_structure or {},
                                    label_config=project.label_config,
                                )
                                # Pass source text for span position calculation (Issue #964)
                                source_text = task_content.get("text") if task_content else None
                                parse_result = parser.parse(response_text, source_text=source_text)

                                parse_status = parse_result.status
                                parse_error = parse_result.error
                                parsed_annotation = parse_result.parsed_annotation

                                logger.info(f"📋 Parse status: {parse_status}")
                                if parse_status == "success":
                                    logger.info(
                                        f"✅ Successfully parsed response with {len(parsed_annotation)} fields"
                                    )
                                else:
                                    logger.warning(f"⚠️ Parse failed: {parse_error}")

                            except Exception as e:
                                logger.error(f"❌ Error during parsing: {str(e)}")
                                parse_status = "failed"
                                parse_error = f"Parser exception: {str(e)}"
                        else:
                            logger.info(
                                "ℹ️ Skipping parsing - no label_config configured for project"
                            )

                        # Determine final status based on parse result and retry count
                        if parse_status != "success" and existing_attempts >= MAX_PARSE_RETRIES:
                            final_status = "parse_failed_max_retries"
                            logger.warning(
                                f"🚫 Max parse retries ({MAX_PARSE_RETRIES}) reached for task {task_data['id']}"
                            )
                        elif parse_status != "success":
                            final_status = "parse_failed"
                            logger.info(
                                f"🔄 Parse failed, will retry (attempt {existing_attempts + 1}/{MAX_PARSE_RETRIES})"
                            )
                        else:
                            final_status = "completed"

                        # Build parse metadata
                        parse_metadata = {
                            "retry_count": existing_attempts + 1,
                            "last_attempt": datetime.now().isoformat(),
                            "max_retries_reached": existing_attempts >= MAX_PARSE_RETRIES,
                        }

                        # Save response to database
                        case_data_with_id = {
                            "text": str(task_content),
                            "task_item_id": task_data[
                                "id"
                            ],  # Native annotation system task item ID
                            "original_task_data": task_data,
                        }

                        # Phase 6.6: pull the academic-rigor fields out of
                        # the merged metadata dict + usage stats so the
                        # discrete columns (migration 040) and the JSON
                        # blob stay in sync. None defaults are fine for
                        # any provider that doesn't surface a given field.
                        llm_response = DBLLMResponse(
                            id=str(uuid.uuid4()),
                            generation_id=generation_id,
                            task_id=task_data["id"],  # Use actual task ID, not project ID
                            model_id=model_id,
                            # prompt_id removed - prompts table dropped in issue #759
                            case_data=json.dumps(case_data_with_id),
                            response_content=response_text,
                            usage_stats=usage_stats,
                            response_metadata=json.dumps(metadata),
                            # Migration 041: trial index within parent fan-out
                            run_index=run_index,
                            # Phase 6.6 columns.
                            seed=metadata.get("seed"),
                            finish_reason=metadata.get("finish_reason"),
                            truncated=bool(metadata.get("truncated", False)),
                            refusal=bool(metadata.get("refusal", False)),
                            error_type=metadata.get("error_type"),
                            latency_ms=metadata.get("response_time_ms"),
                            input_tokens=usage_stats.get("prompt_tokens") if isinstance(usage_stats, dict) else None,
                            output_tokens=usage_stats.get("completion_tokens") if isinstance(usage_stats, dict) else None,
                            # Parse results
                            parsed_annotation=parsed_annotation,
                            parse_status=parse_status,
                            parse_error=parse_error,
                            parse_metadata=parse_metadata,
                            # Label config versioning
                            label_config_version=project.label_config_version,
                            label_config_snapshot=project.label_config,
                            status=final_status,
                            created_at=datetime.now(),
                        )

                        db.add(llm_response)
                        responses_generated += 1

                        logger.info(
                            f"✅ Generated response {responses_generated}/{total_expected} for task {task_data['id']}"
                        )

                        # Update generation progress every 10 responses or at end
                        if responses_generated % 10 == 0 or responses_generated == total_expected:
                            generation.responses_generated = responses_generated

                        # Commit after each response to avoid losing work
                        db.commit()

                        # Broadcast on the same throttle as the counter update
                        # — every 10 rows or at end. The API-side WS handler
                        # forwards this to GenerationTaskList / GenerationProgress
                        # which then re-fetches the row list. The handler used
                        # to poll for the same thing every 2 s; pub/sub lets us
                        # drop that polling load entirely.
                        if (
                            responses_generated % 10 == 0
                            or responses_generated == total_expected
                        ):
                            _publish_progress(
                                f"generation:progress:{project_id}",
                                {
                                    "type": "progress",
                                    "generation_id": generation.id,
                                    "model_id": model_id,
                                    "responses_generated": responses_generated,
                                    "total_expected": total_expected,
                                    "status": "running"
                                    if responses_generated < total_expected
                                    else "completed",
                                },
                            )

                    except Exception as e:
                        _last_error = str(e)
                        logger.error(
                            f"❌ Failed to generate response for task {task_data['id']}, prompt {prompt_id}: {_last_error}"
                        )
                        continue

            # Multi-run aggregation (migration 041): bump the parent counter
            # for this trial, then derive parent status from the totals. For
            # single-run (runs_requested=1) this is identical to the legacy
            # behavior; for N>1 the parent goes to "completed" only after all
            # successful trials, and to "failed" on the first trial failure
            # (per the multi-run UX decision).
            from sqlalchemy import text as _sql_text

            trial_failed = responses_generated == 0 and total_expected > 0

            if trial_failed:
                db.execute(
                    _sql_text(
                        "UPDATE response_generations SET runs_failed = runs_failed + 1 "
                        "WHERE id = :gid"
                    ),
                    {"gid": generation_id},
                )
            else:
                db.execute(
                    _sql_text(
                        "UPDATE response_generations SET runs_completed = runs_completed + 1 "
                        "WHERE id = :gid"
                    ),
                    {"gid": generation_id},
                )

            db.refresh(generation)

            # Defensive int coercion: legacy ResponseGeneration rows may not
            # carry the multi-run counters yet (and unit tests use bare Mocks
            # which auto-vivify attrs as MagicMock). Treat missing/non-int
            # values as 0/1 so comparisons don't crash.
            def _as_int(v: Any, default: int) -> int:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return default
            _runs_failed = _as_int(getattr(generation, "runs_failed", 0), 0)
            _runs_completed = _as_int(getattr(generation, "runs_completed", 0), 0)
            _runs_requested = _as_int(getattr(generation, "runs_requested", 1), 1)

            if _runs_failed > 0:
                generation.status = "failed"
                generation.error_message = _last_error or generation.error_message or "Trial failed"
                generation.completed_at = datetime.now()
            elif _runs_completed >= _runs_requested:
                generation.status = "completed"
                generation.completed_at = datetime.now()
            else:
                # More trials pending — leave status as "running" and don't
                # set completed_at yet.
                generation.status = "running"

            generation.responses_generated = (generation.responses_generated or 0) + responses_generated
            metadata = {
                "total_expected": total_expected,
                "successful": responses_generated,
                "failed": total_expected - responses_generated,
                "model_provider": model.provider,
                "api_model_name": api_model_name,
            }
            # Add structure_key to metadata if provided (Issue #762)
            if structure_key:
                metadata["structure_key"] = structure_key
            generation.generation_metadata = json.dumps(metadata)

            # Store prompt provenance and parameters
            if _captured_prompt_templates:
                generation.prompt_used = json.dumps(
                    _captured_prompt_templates,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            if _captured_parameters:
                generation.parameters = _captured_parameters

            db.commit()

            # Update report generation section after generation completion (Issue #770)
            try:
                report = (
                    db.query(DBProjectReport)
                    .filter(DBProjectReport.project_id == project_id)
                    .first()
                )
                if report:
                    # Get unique models from generations for this project
                    models = (
                        db.query(DBLLMResponse.model_id)
                        .join(
                            DBResponseGeneration,
                            DBLLMResponse.generation_id == DBResponseGeneration.id,
                        )
                        .filter(DBResponseGeneration.project_id == project_id)
                        .distinct()
                        .all()
                    )
                    model_ids = [m[0] for m in models]

                    # Preserve custom text if it exists
                    existing_generation = report.content.get("sections", {}).get("generation", {})
                    custom_text = existing_generation.get("custom_text")
                    show_config = existing_generation.get("show_config", False)

                    # Update report content
                    if "sections" not in report.content:
                        report.content["sections"] = {}
                    report.content["sections"]["generation"] = {
                        "models": model_ids,
                        "custom_text": custom_text,
                        "show_models": True,
                        "show_config": show_config,
                        "status": "completed",
                        "editable": True,
                        "visible": True,
                    }

                    # Update metadata
                    if "metadata" not in report.content:
                        report.content["metadata"] = {}
                    report.content["metadata"]["last_auto_update"] = datetime.now().isoformat()
                    if "sections_completed" not in report.content["metadata"]:
                        report.content["metadata"]["sections_completed"] = []
                    if "generation" not in report.content["metadata"]["sections_completed"]:
                        report.content["metadata"]["sections_completed"].append("generation")

                    # Mark content as modified for SQLAlchemy to detect the change
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(report, "content")
                    db.commit()
                    logger.info(f"✅ Updated report generation section for project {project_id}")
                else:
                    logger.debug(
                        f"No report found for project {project_id} - skipping report update"
                    )
            except Exception as e:
                logger.error(f"Failed to update report generation section: {e}")
                # Don't fail the generation operation

            logger.info(
                f"🎉 Generation completed: {responses_generated}/{total_expected} successful"
            )

            # Trigger notification for completion. Writes a real DB
            # notification (via NotificationService) carrying generation_id
            # so the frontend NotificationDropdown can route the click to
            # /generations/{id}. The legacy notify_task_completed log stub
            # was previously called here too as belt-and-suspenders; removed
            # because emitting two side effects per event was just noise
            # (the stub doesn't write to the DB, only logs).
            try:
                if project and HAS_DATABASE and user_id:
                    NotificationService.create_notification(
                        db=db,
                        user_ids=[user_id],
                        notification_type=NotificationType.LLM_GENERATION_COMPLETED,
                        title="Generation Complete",
                        message=(
                            f"Generation completed for {project.title}: "
                            f"{responses_generated}/{total_expected} responses"
                        ),
                        data={
                            "project_id": project_id,
                            "generation_id": generation_id,
                            "model_id": model_id,
                            "responses_generated": responses_generated,
                            "total_expected": total_expected,
                        },
                    )
                    logger.info(
                        f"✅ Notification sent for generation {generation_id} (project {project_id})"
                    )
            except Exception as notification_error:
                logger.warning(f"⚠️ Failed to send notification: {notification_error}")

            # Note: Bidirectional sync will be handled by the periodic sync task every 10 minutes

            # Return status reflecting actual outcome
            if responses_generated == 0 and total_expected > 0:
                return {
                    "status": "failed",
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": f"Generation failed: 0/{total_expected} responses - all attempts failed",
                    "responses_generated": 0,
                    "total_expected": total_expected,
                }

            return {
                "status": "success",
                "generation_id": generation_id,
                "model_id": model_id,
                "message": f"Generation completed successfully: {responses_generated}/{total_expected} responses",
                "responses_generated": responses_generated,
                "total_expected": total_expected,
            }

        except Exception as e:
            # Update generation status to failed and bump runs_failed counter
            # so the multi-run aggregator agrees this trial failed (matches the
            # success path's atomic counter update above).
            try:
                from sqlalchemy import text as _sql_text

                db.execute(
                    _sql_text(
                        "UPDATE response_generations SET runs_failed = runs_failed + 1 "
                        "WHERE id = :gid"
                    ),
                    {"gid": generation_id},
                )
                generation = (
                    db.query(DBResponseGeneration)
                    .filter(DBResponseGeneration.id == generation_id)
                    .first()
                )
                if generation:
                    generation.status = "failed"
                    generation.error_message = str(e)
                    generation.completed_at = datetime.now()
                    db.commit()
            except Exception as db_error:
                logger.error(f"❌ Failed to update generation status: {str(db_error)}")

            logger.error(f"❌ Generation failed for {generation_id}: {str(e)}")
            raise

        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Async generation failed for {generation_id}: {str(e)}")
        return {
            "status": "error",
            "generation_id": generation_id,
            "model_id": model_id,
            "message": str(e),
        }


# digest.process_all_digests and digest.send_test_digest tasks were
# removed here — the underlying email-digest feature was deleted at the
# User model level (see models.py around line 223), so both tasks could
# only ever AttributeError at runtime. The matching beat schedule entry,
# the digest_service.py module, and the celery-beat scheduler container
# in docker-compose are all gone too. Reviving needs the User columns
# (enable_email_digest, digest_frequency, digest_time, digest_days,
# last_digest_sent) plus a digest.html email template (also missing).


# Email tasks for invitation system


@app.task(
    name="emails.send_invitation",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
)
def send_invitation_email_task(
    self,
    invitation_id: str,
    to_email: str,
    inviter_name: str,
    organization_name: str,
    invitation_url: str,
    role: str,
) -> Dict[str, Any]:
    """
    Send organization invitation email via Celery

    Args:
        invitation_id: ID of the invitation record
        to_email: Recipient email
        inviter_name: Name of person sending invitation
        organization_name: Organization name
        invitation_url: URL to accept invitation
        role: Role being offered

    Returns:
        Dictionary with send status
    """
    logger.info(f"Sending invitation email to {to_email} for {organization_name}")

    try:
        from email_service import email_service
        from sendgrid_client import SendGridClient

        client = SendGridClient()

        subject, html_body = email_service.build_invitation_email(
            organization_name=organization_name,
            inviter_name=inviter_name,
            role=role,
            invitation_url=invitation_url,
        )

        result = client.send_message(
            to=[to_email],
            subject=subject,
            html_body=html_body,
            disable_tracking=True,
        )

        if result.get("status") == "success":
            logger.info(f"Invitation email sent successfully to {to_email}")
            return {
                "status": "success",
                "invitation_id": invitation_id,
                "recipient": to_email,
                "organization": organization_name,
                "message_id": result.get("message_id", "unknown"),
            }

        # Differentiate retryable vs permanent SendGrid failures. Without
        # this every 400 (malformed recipient), 401 (bad API key), 403
        # (suspended account), etc. burned three full 60s-spaced retries
        # via autoretry_for=(Exception,) + max_retries=3, occupying the
        # rate-limited (30/m) emails queue. 429 stays retryable — that's
        # SendGrid asking us to back off.
        status_code = result.get("status_code")
        error_msg = result.get("error", "Unknown SendGrid error")
        if status_code is not None and 400 <= status_code < 500 and status_code != 429:
            logger.error(
                f"Permanent SendGrid {status_code} for {to_email}; not retrying: {error_msg}"
            )
            return {
                "status": "failed_permanent",
                "invitation_id": invitation_id,
                "recipient": to_email,
                "status_code": status_code,
                "error": error_msg,
            }

        logger.error(
            f"Retryable SendGrid failure for {to_email} (status_code={status_code}): {error_msg}"
        )
        raise RuntimeError(f"SendGrid error: {error_msg}")

    except RuntimeError:
        # Already classified as retryable above — let autoretry_for see it.
        raise
    except Exception as e:
        logger.error(f"Error sending invitation email to {to_email}: {str(e)}")
        raise


@app.task(name="emails.send_bulk_invitations")
def send_bulk_invitations_task(invitations_data: List[Dict]) -> Dict[str, Any]:
    """
    Send multiple invitation emails with rate limiting

    Args:
        invitations_data: List of invitation dictionaries with email details

    Returns:
        Dictionary with bulk send statistics
    """
    logger.info(f"📨 Processing bulk invitations: {len(invitations_data)} recipients")

    sent = 0
    failed = 0
    results = []

    for idx, invitation in enumerate(invitations_data):
        try:
            # Queue individual invitation with progressive delay to avoid overwhelming mail server
            result = send_invitation_email_task.apply_async(
                args=[
                    invitation.get('invitation_id'),
                    invitation.get('to_email'),
                    invitation.get('inviter_name'),
                    invitation.get('organization_name'),
                    invitation.get('invitation_url'),
                    invitation.get('role'),
                ],
                countdown=idx * 2,  # 2 second delay between emails
            )
            sent += 1
            results.append(
                {"email": invitation.get('to_email'), "task_id": result.id, "status": "queued"}
            )
            logger.info(
                f"📮 Queued invitation {sent}/{len(invitations_data)} for {invitation.get('to_email')}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to queue invitation for {invitation.get('to_email')}: {e}")
            failed += 1
            results.append(
                {"email": invitation.get('to_email'), "status": "failed", "error": str(e)}
            )

    logger.info(f"✅ Bulk invitation processing complete: {sent} queued, {failed} failed")

    return {"sent": sent, "failed": failed, "total": len(invitations_data), "results": results}


@app.task(
    name="emails.send_notification_batch",
    autoretry_for=(OperationalError, DBAPIError),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def send_notification_batch_task(notification_data: List[Dict]) -> Dict[str, Any]:
    """Send a batch of in-app-notification emails.

    Replaces the prior pattern in `notification_service.create_notification`
    where `asyncio.create_task(_send_email_notifications(db, ...))` ran the
    sync `requests.post` SendGrid call on the API event loop and reused the
    request-scoped DB session in a fire-and-forget task. Both were
    catastrophic under fan-out (notify_project_created → every org member +
    every superadmin); see 2026-05-18 postmortem.

    Owns its own DB session. Per-recipient SendGrid failures (4xx/5xx) are
    swallowed and counted as `failed` so one bad address doesn't tank the
    whole batch. Task-level retry is narrowed to transient DB errors
    (OperationalError / DBAPIError) — previously `autoretry_for=(Exception,)`
    would burn 3 retries × 60s on any non-DB outer failure
    (ImportError, SendGrid client init crash, …) that no amount of
    retrying would ever fix.
    """
    if not notification_data:
        return {"sent": 0, "failed": 0, "skipped": 0}

    sent = failed = skipped = 0
    db = SessionLocal()
    try:
        from email_service import email_service
        from models import Notification, User
        try:
            from email_validation import is_valid_email
        except ImportError:
            def is_valid_email(e: str) -> bool:
                return "@" in (e or "") and "." in (e or "")

        for notif_dict in notification_data:
            try:
                user = db.query(User).filter(User.id == notif_dict["user_id"]).first()
                if not user or not user.email:
                    skipped += 1
                    continue

                if not is_valid_email(user.email):
                    logger.warning(
                        f"Skipping notification for user {user.id} — invalid email: {user.email}"
                    )
                    skipped += 1
                    continue

                if HAS_NOTIFICATION_SERVICE and not NotificationService._user_wants_channel(
                    db, user.id, notif_dict["type"], "email"
                ):
                    skipped += 1
                    continue

                # Hydrate a minimal Notification ORM object — only the
                # attributes the template path reads. We pass an unattached
                # instance, never add it to the session.
                notif = Notification(
                    id=notif_dict.get("id"),
                    user_id=notif_dict["user_id"],
                    type=notif_dict["type"],
                    title=notif_dict.get("title", ""),
                    message=notif_dict.get("message", ""),
                    data=notif_dict.get("data") or {},
                )

                # `send_notification_email` is `async` but the underlying
                # SendGrid call is sync. Run via asyncio.run on the worker
                # process — Celery doesn't have an event loop by default.
                import asyncio as _aio
                ok = _aio.run(
                    email_service.send_notification_email(
                        user_email=user.email,
                        notification=notif,
                        context={"user_name": getattr(user, "name", None)},
                    )
                )
                if ok:
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(
                    f"Notification email failed for {notif_dict.get('user_id')}: {e}"
                )
                failed += 1
    finally:
        db.close()

    logger.info(
        f"📬 send_notification_batch: {sent} sent, {failed} failed, {skipped} skipped"
    )
    return {"sent": sent, "failed": failed, "skipped": skipped, "total": len(notification_data)}


# Label Studio tasks removed - using native annotation system

# NOTE: Label Studio sync function removed - using native annotation system


@app.task(name="tasks.generate_response")
def generate_response(
    generation_id: str,
    project_id: str,
    task_id: str,
    model_id: str,
    structure_key: str = None,
    force_rerun: bool = False,
    organization_id: str = None,
    run_index: int = 0,
) -> Dict[str, Any]:
    """
    Generate response for a specific task-model combination.
    Bridge task for the new generation pipeline that matches the API call signature.

    Args:
        generation_id: Unique identifier for this generation run
        project_id: ID of the project
        task_id: ID of the specific task
        model_id: ID of the model to use for generation
        structure_key: Optional prompt structure key (Issue #762)
        force_rerun: If True, regenerate even if response already exists
        organization_id: Optional org context for API key resolution (Issue #1180)
        run_index: Zero-indexed trial number within the parent ResponseGeneration's
            fan-out (migration 041). One Celery task per run_index; the parent
            ResponseGeneration aggregates progress via runs_completed/runs_failed.

    Returns:
        Dictionary with generation results
    """
    structure_info = f" with structure '{structure_key}'" if structure_key else ""
    logger.info(
        f"🎯 Starting generation for task {task_id} with model {model_id}{structure_info} (run {run_index})"
    )

    try:
        # Import modules
        from datetime import datetime

        from models import ResponseGeneration as DBResponseGeneration

        # Import Task from project_models to avoid table conflict
        from project_models import Task

        # Check database availability
        if not HAS_DATABASE:
            raise Exception("Database not available - check database connection")

        # Create database session
        db = SessionLocal()

        try:
            # Get the generation record
            generation = (
                db.query(DBResponseGeneration)
                .filter(DBResponseGeneration.id == generation_id)
                .first()
            )

            if not generation:
                raise Exception(f"Generation {generation_id} not found")

            # Guard against duplicate execution (e.g., Celery message redelivery)
            if generation.status in ("completed", "cancelled"):
                logger.info(
                    f"⏭️ Skipping generation {generation_id} - already {generation.status}"
                )
                return {
                    "status": generation.status,
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": f"Generation already {generation.status}, skipping duplicate execution",
                }

            # Note: status="running" is set by generate_llm_responses (line 575)
            # which is also callable as a standalone Celery task

            # Get the task
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise Exception(f"Task {task_id} not found")

            # Get the project
            from project_models import Project

            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise Exception(f"Project {project_id} not found")

            # Build config_data for generate_llm_responses
            # Note: prompts and parameters are resolved from project.generation_config
            # and generation_structure inside generate_llm_responses, not from config_data
            config_data = {
                "project_id": project_id,
                "force_rerun": force_rerun,
            }

            # Get user ID from generation record
            user_id = generation.created_by

            # Call generate_llm_responses directly (not via Celery)
            # It uses its own DB session and commits all changes (status,
            # error_message, prompt_used, parameters) to the generation record.
            result = generate_llm_responses(
                generation_id, config_data, model_id, user_id, structure_key, organization_id,
                run_index=run_index,
            )

            # Refresh to pick up all changes committed by generate_llm_responses
            # (which uses a separate DB session)
            db.refresh(generation)

            logger.info(
                f"✅ Completed generation for task {task_id} with status: {generation.status}"
            )
            return result

        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Error in generate_response: {str(e)}")

        # Try to update generation status. For multi-run we also bump the
        # runs_failed counter (migration 041) so the parent's aggregate matches
        # reality even when the trial died before generate_llm_responses ran.
        try:
            from sqlalchemy import text as _sql_text

            db = SessionLocal()
            db.execute(
                _sql_text(
                    "UPDATE response_generations SET runs_failed = runs_failed + 1 "
                    "WHERE id = :gid"
                ),
                {"gid": generation_id},
            )
            generation = (
                db.query(DBResponseGeneration)
                .filter(DBResponseGeneration.id == generation_id)
                .first()
            )
            if generation and generation.status not in ("completed", "cancelled"):
                generation.status = "failed"
                generation.error_message = str(e)
                generation.completed_at = datetime.now()
                db.commit()
            db.close()
        except Exception as db_error:
            logger.error(f"❌ Failed to update generation status: {str(db_error)}")

        return {
            "status": "error",
            "message": f"Generation failed: {str(e)}",
            "generation_id": generation_id,
        }


# =============================================================================
# Evaluation Task (Issue #763)
# =============================================================================


@app.task(name="tasks.run_evaluation")
def run_evaluation(
    evaluation_id: str,
    project_id: str,
    evaluation_configs: List[Dict[str, Any]],
    batch_size: int = 100,
    label_config_version: Optional[str] = None,
    evaluate_missing_only: bool = False,
    organization_id: Optional[str] = None,
    task_ids: Optional[List[str]] = None,
    model_ids: Optional[List[str]] = None,
    annotator_user_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run evaluation based on configured field mappings.

    This task processes evaluations where users configure N:M mappings between
    prediction fields (from LLM generations) and reference fields (from annotations).

    Args:
        evaluation_id: Database ID of Evaluation record
        project_id: Project to evaluate
        evaluation_configs: List of evaluation configurations, each containing:
            - id: Config identifier
            - metric: Metric name (bleu, rouge, bertscore, etc.)
            - prediction_fields: List of fields containing predictions
            - reference_fields: List of fields containing ground truth
            - metric_parameters: Optional dict of metric-specific parameters
            - enabled: Whether this config is active
        batch_size: Number of samples to process per batch
        label_config_version: Optional version filter for generations

    Returns:
        Dictionary with evaluation results and statistics
    """
    version_filter_msg = (
        f" (label_config_version={label_config_version})" if label_config_version else ""
    )
    logger.info(
        f"🎯 Starting evaluation for project {project_id}, "
        f"evaluation {evaluation_id}{version_filter_msg}"
    )
    # E3: surface scope filters at the start of the run so debugging
    # "why did this score only N cells" needs only the log, not the
    # eval_metadata blob. Cheap (just lengths), fires once per run.
    if task_ids or model_ids or annotator_user_ids:
        logger.info(
            f"[evaluation {evaluation_id}] scope filters active: "
            f"task_ids={len(task_ids) if task_ids else 0}, "
            f"model_ids={len(model_ids) if model_ids else 0}, "
            f"annotator_user_ids={len(annotator_user_ids) if annotator_user_ids else 0}"
        )

    try:
        from datetime import datetime

        from ml_evaluation.sample_evaluator import SampleEvaluator

        db = SessionLocal()

        try:
            # Import models here to avoid circular imports
            from models import EvaluationRun, TaskEvaluation, Generation
            from project_models import Annotation, Project, Task

            # Update evaluation status to running
            evaluation = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id).first()
            if not evaluation:
                return {
                    "status": "error",
                    "message": f"Evaluation {evaluation_id} not found",
                    "evaluation_id": evaluation_id,
                }

            evaluation.status = "running"
            evaluation.started_at = datetime.now()
            db.commit()

            # Load project
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                evaluation.status = "failed"
                evaluation.error_message = f"Project {project_id} not found"
                db.commit()
                return {
                    "status": "error",
                    "message": f"Project {project_id} not found",
                    "evaluation_id": evaluation_id,
                }

            # Filter enabled configs
            enabled_configs = [c for c in evaluation_configs if c.get("enabled", True)]
            if not enabled_configs:
                evaluation.status = "failed"
                evaluation.error_message = "No enabled evaluation configurations"
                db.commit()
                return {
                    "status": "error",
                    "message": "No enabled evaluation configurations",
                    "evaluation_id": evaluation_id,
                }

            # Probe the task set up-front so we can short-circuit before
            # creating any EvaluationJudgeRun rows. Avoids leaving orphan
            # judge_runs behind when the project has no tasks at all.
            _probe_tasks_query = db.query(Task).filter(Task.project_id == project_id)
            if task_ids:
                _probe_tasks_query = _probe_tasks_query.filter(Task.id.in_(task_ids))
            _probe_tasks_count = _probe_tasks_query.limit(1).all()
            if not _probe_tasks_count:
                evaluation.status = "failed"
                evaluation.error_message = "No tasks found in project"
                db.commit()
                return {
                    "status": "error",
                    "message": "No tasks found in project",
                    "evaluation_id": evaluation_id,
                }

            # ── Resolve judge config to (judge_model_id, run_index) pairs ──
            # The `metric_parameters.judges` shape (migration 042) is a list of
            # `{judge_model_id, runs}` entries: supports same-model multi-run
            # AND judge ensembles under one schema. Migration 042 backfilled
            # any pre-existing `judge_model` keys to this shape; the soft
            # fallback below covers projects whose evaluation_config wasn't
            # touched since the migration ran.
            #
            # For each (config, judge_model, run_index) we:
            #   1. Insert one `EvaluationJudgeRun` row (status=running).
            #   2. Instantiate one `LLMJudgeEvaluator` scoped to that judge.
            #   3. Stash both in `judge_runs_by_config[config_id]` so the
            #      per-task loop can iterate and emit one TaskEvaluation per
            #      judge_run.
            # At the end of evaluation we walk the list and mark each judge_run
            # `completed`/`failed`; the parent EvaluationRun status is then
            # aggregated from these children.
            from models import EvaluationJudgeRun
            import uuid as _uuid_judge

            def _resolve_judges(params: Dict[str, Any]) -> List[Dict[str, Any]]:
                judges = params.get("judges")
                if isinstance(judges, list) and judges:
                    return judges
                legacy = params.get("judge_model", "gpt-4o")
                runs = int(params.get("runs_per_judge", 1) or 1)
                return [{"judge_model_id": legacy, "runs": runs}]

            # Cache (judge_model_id, run_index) -> judge_run_id within this
            # evaluation so multiple metrics that share the same judge reuse
            # the same EvaluationJudgeRun row instead of colliding on the
            # uq_evaluation_judge_runs unique constraint.
            _judge_run_cache: Dict[tuple, str] = {}

            def _create_judge_run(judge_model_id: Optional[str], run_index: int,
                                  params_snapshot: Optional[Dict[str, Any]]) -> str:
                cache_key = (judge_model_id, run_index)
                if cache_key in _judge_run_cache:
                    return _judge_run_cache[cache_key]
                existing = db.query(EvaluationJudgeRun).filter(
                    EvaluationJudgeRun.evaluation_id == evaluation_id,
                    EvaluationJudgeRun.judge_model_id == judge_model_id,
                    EvaluationJudgeRun.run_index == run_index,
                ).first()
                if existing:
                    # Reusing a judge_run a prior cancel left terminal
                    # (status='failed'/'cancelled') — e.g. a missing-only resume
                    # into the same EvaluationRun. Revive it to 'running' so it
                    # reflects the in-progress regrade and the finalizer
                    # reconciles it from produced rows rather than carrying a
                    # stale terminal status into this run.
                    if existing.status in ("failed", "cancelled"):
                        existing.status = "running"
                        existing.error_message = None
                        existing.completed_at = None
                        existing.started_at = datetime.now()
                        db.commit()
                    _judge_run_cache[cache_key] = existing.id
                    return existing.id
                jr_id = str(_uuid_judge.uuid4())
                jr = EvaluationJudgeRun(
                    id=jr_id,
                    evaluation_id=evaluation_id,
                    judge_model_id=judge_model_id,
                    run_index=run_index,
                    status="running",
                    started_at=datetime.now(),
                    metric_parameters_snapshot=params_snapshot or None,
                )
                db.add(jr)
                db.commit()
                _judge_run_cache[cache_key] = jr_id
                return jr_id

            # judge_runs_by_config[config_id] = list of dicts with keys:
            #   judge_model_id, run_index, judge_run_id, evaluator (or None)
            #
            # Order matters — preserves the user-configured judges list so the
            # UI's "first judge" / "second judge" labelling stays stable.
            judge_runs_by_config: Dict[str, List[Dict[str, Any]]] = {}
            # Legacy single-judge dicts kept for guard logic + backwards-compat
            # in code paths that haven't been ported to iterate `judge_runs_by_config`
            # yet (e.g. annotation-evaluation and immediate-eval paths). They
            # always point at the FIRST judge_run for the config.
            llm_judge_evaluators: Dict[str, Any] = {}
            llm_judge_run_ids: Dict[str, str] = {}
            default_judge_run_id: Optional[str] = None

            for config in enabled_configs:
                metric = config.get("metric", "")
                if metric.startswith("llm_judge_"):
                    config_id = config.get("id", "unknown")
                    params = config.get("metric_parameters", {})
                    judges_list = _resolve_judges(params)

                    triggered_by = (
                        evaluation.eval_metadata.get("triggered_by")
                        if evaluation.eval_metadata
                        else None
                    )
                    if not triggered_by:
                        logger.warning(
                            f"LLM judge config {config_id} has no triggered_by user - skipping"
                        )
                        continue

                    judge_runs_by_config.setdefault(config_id, [])

                    # One EvaluationJudgeRun + one evaluator per (judge, run).
                    for judge_entry in judges_list:
                        judge_model = judge_entry.get("judge_model_id") or "gpt-4o"
                        runs = max(1, int(judge_entry.get("runs", 1) or 1))
                        # Tiered parameter resolution for judges (mode='evaluation').
                        # Pulls model.recommended_parameters from the catalog so
                        # the judge call honors provider-recommended defaults
                        # when metric_parameters doesn't pin a value. Snapshots
                        # the same _param_provenance shape into the judge_run
                        # for academic-rigor traceability.
                        judge_model_obj = (
                            db.query(DBLLMModel).filter(DBLLMModel.id == judge_model).first()
                        )
                        judge_recommended = (
                            getattr(judge_model_obj, "recommended_parameters", None) or None
                        )
                        for run_index in range(runs):
                            judge_provenance: Dict[str, Dict[str, Any]] = {}

                            def _resolve_judge(key: str, fallback_default: Any = None):
                                value, source, rec_at_trigger = _resolve_param(
                                    key=key,
                                    mode="evaluation",
                                    model_recommended=judge_recommended,
                                    project_cfg=None,        # eval defaults are per-config
                                    per_model_cfg=params,    # metric_parameters wins
                                )
                                if value is None and fallback_default is not None:
                                    value = fallback_default
                                judge_provenance[key] = {
                                    "value": value,
                                    "source": source,
                                    "recommended_at_trigger": rec_at_trigger,
                                }
                                return value

                            judge_temp = _resolve_judge("temperature", 0.0)
                            judge_max_tokens = _resolve_judge("max_tokens", 500)
                            judge_seed_base = _resolve_judge("seed", 42)
                            # Apply per-model temperature constraint (e.g. Opus
                            # 4.7 requires 1.0, GPT-5 forces 1.0, DeepSeek-R1
                            # min 0.6). Mirror of the generation-side clamp so
                            # the judge call respects the same hard limits.
                            judge_constraints = (
                                getattr(judge_model_obj, "parameter_constraints", None) or None
                            )
                            judge_temp, _temp_clamped_from = _clamp_temperature_to_constraint(
                                judge_temp, judge_constraints
                            )
                            if _temp_clamped_from is not None and "temperature" in judge_provenance:
                                judge_provenance["temperature"]["clamped_from"] = _temp_clamped_from
                                judge_provenance["temperature"]["value"] = judge_temp
                            judge_seed = int(judge_seed_base or 42) + run_index
                            # Record the actual seed sent to the judge in
                            # provenance, plus the pre-perturbation base
                            # so an analyst can see the multi-run offset.
                            if "seed" in judge_provenance and run_index > 0:
                                judge_provenance["seed"]["value"] = judge_seed
                                judge_provenance["seed"]["multi_run_offset"] = run_index
                                judge_provenance["seed"]["pre_perturbation"] = judge_seed_base

                            jr_id = _create_judge_run(
                                judge_model_id=judge_model,
                                run_index=run_index,
                                params_snapshot={
                                    **params,
                                    "_resolved_judge": judge_model,
                                    "_run_index": run_index,
                                    "_param_provenance": judge_provenance,
                                },
                            )
                            evaluator = None
                            try:
                                from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user

                                provider = _get_provider_from_model(judge_model)
                                evaluator = create_llm_judge_for_user(
                                    db=db,
                                    user_id=triggered_by,
                                    provider=provider,
                                    judge_model=judge_model,
                                    temperature=judge_temp,
                                    max_tokens=judge_max_tokens,
                                    criteria=params.get("dimensions"),
                                    custom_criteria=params.get("custom_criteria"),
                                    custom_prompt_template=params.get("custom_prompt_template"),
                                    answer_type=params.get("answer_type"),
                                    field_mappings=params.get("field_mappings"),
                                    score_scale=params.get("score_scale", "1-5"),
                                    organization_id=organization_id,
                                    seed=judge_seed,
                                )
                                e2e_test_mode = os.environ.get("E2E_TEST_MODE") == "true"
                                if not (evaluator.ai_service or e2e_test_mode):
                                    logger.warning(
                                        f"LLM judge for config {config_id} judge {judge_model} run {run_index} has no AI service - judge_run will be marked failed"
                                    )
                                    evaluator = None
                                else:
                                    key_source = f"org {organization_id}" if organization_id else f"user {triggered_by}"
                                    mode = " (mock/E2E)" if not evaluator.ai_service else ""
                                    logger.info(
                                        f"Initialized LLM judge for config {config_id} model {judge_model} run {run_index} (key via {key_source}){mode}"
                                    )
                            except Exception as init_err:
                                if os.environ.get("E2E_TEST_MODE") == "true":
                                    from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

                                    evaluator = LLMJudgeEvaluator(
                                        criteria=params.get("dimensions") if params else None,
                                        score_scale="0-1",
                                    )
                                    logger.info(
                                        f"Using mock LLM judge for E2E test config {config_id} {judge_model} run {run_index} (init failed: {init_err})"
                                    )
                                else:
                                    logger.error(
                                        f"Failed to initialize LLM judge for config {config_id} {judge_model} run {run_index}: {init_err}"
                                    )

                            if evaluator is None:
                                # Mark this judge_run failed up front so the
                                # parent aggregator sees the truth.
                                _jr = db.query(EvaluationJudgeRun).filter(
                                    EvaluationJudgeRun.id == jr_id
                                ).first()
                                if _jr:
                                    _jr.status = "failed"
                                    _jr.error_message = "judge initialization failed"
                                    _jr.completed_at = datetime.now()
                                    db.commit()

                            # Stash the construction kwargs alongside the
                            # in-memory evaluator. Sub-tasks (post-fan-out)
                            # need to re-instantiate the evaluator per worker
                            # process via `create_llm_judge_for_user` — they
                            # can't be passed the already-built evaluator
                            # instance (not picklable across Celery). The
                            # orchestrator is the one place all the param
                            # resolution (`_resolve_judge`, temperature
                            # clamping, per-run seed perturbation) happens;
                            # stashing the resolved kwargs here threads the
                            # decision through to sub-tasks unchanged.
                            judge_evaluator_kwargs = {
                                "judge_model": judge_model,
                                "provider": provider,
                                "temperature": judge_temp,
                                "max_tokens": judge_max_tokens,
                                "criteria": params.get("dimensions"),
                                "custom_criteria": params.get("custom_criteria"),
                                "custom_prompt_template": params.get("custom_prompt_template"),
                                "answer_type": params.get("answer_type"),
                                "field_mappings": params.get("field_mappings"),
                                "score_scale": params.get("score_scale", "1-5"),
                                "thinking_budget": params.get("thinking_budget"),
                                "reasoning_effort": params.get("reasoning_effort"),
                                "seed": judge_seed,
                            }
                            judge_runs_by_config[config_id].append({
                                "judge_model_id": judge_model,
                                "run_index": run_index,
                                "judge_run_id": jr_id,
                                "evaluator": evaluator,
                                "judge_evaluator_kwargs": judge_evaluator_kwargs,
                            })

                    # Populate legacy single-judge maps from the first
                    # successfully-initialized judge_run for backwards-compat
                    # with code paths that still index by config_id (the guard
                    # at the top of the per-task loop, the annotation-eval and
                    # immediate-eval paths). Skips configs whose every judge
                    # failed to init — the guard then writes a terminal-error
                    # row instead of silently corrupting the run.
                    for entry in judge_runs_by_config.get(config_id, []):
                        if entry["evaluator"] is not None:
                            llm_judge_evaluators[config_id] = entry["evaluator"]
                            llm_judge_run_ids[config_id] = entry["judge_run_id"]
                            break
                else:
                    if default_judge_run_id is None:
                        default_judge_run_id = _create_judge_run(
                            judge_model_id=None,
                            run_index=0,
                            params_snapshot=None,
                        )

            # ── Work-unit enumeration ───────────────────────────────────────────
            #
            # Replaces the prior in-process loop that did the actual evaluation
            # work. The orchestrator now ONLY enumerates what's left to do
            # (tasks × generations and tasks × annotations after applying
            # scope filters + `evaluate_missing_only` skip set), then
            # dispatches one Celery sub-task per cell via a chord. Cell
            # sub-tasks run in parallel across the worker pool; the chord
            # callback (`finalize_evaluation_run`) aggregates child statuses
            # and computes the final metrics dict exactly once when every
            # header sub-task has finished.

            # Load tasks (same filters as the legacy body)
            tasks_query = db.query(Task).filter(Task.project_id == project_id)
            if task_ids:
                tasks_query = tasks_query.filter(Task.id.in_(task_ids))
            tasks = tasks_query.limit(batch_size * 10).all()

            if not tasks:
                evaluation.status = "failed"
                evaluation.error_message = "No tasks found in project"
                db.commit()
                return {
                    "status": "error",
                    "message": "No tasks found in project",
                    "evaluation_id": evaluation_id,
                }

            logger.info(f"Loaded {len(tasks)} tasks for evaluation enumeration")

            # Pre-compute expected field keys (same as legacy 2747-2753).
            all_expected_field_keys = {
                f"{c.get('id', 'unknown')}|{pf}|{rf}"
                for c in enabled_configs
                for pf in c.get("prediction_fields", [])
                for rf in c.get("reference_fields", [])
            }

            # Pre-load the gen-side missing-only skip set (same query as
            # legacy 2755-2794 — terminal-error rows count as "tried" to
            # avoid hopeless retries).
            evaluated_by_gen: Dict[str, set] = {}
            if evaluate_missing_only:
                task_id_list = [t.id for t in tasks]
                existing = (
                    db.query(
                        TaskEvaluation.generation_id,
                        TaskEvaluation.field_name,
                        TaskEvaluation.metrics,
                    )
                    .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
                    .filter(
                        TaskEvaluation.task_id.in_(task_id_list),
                        TaskEvaluation.generation_id.isnot(None),
                        EvaluationRun.status.in_(("completed", "running", "pending", "cancelled")),
                    )
                    .all()
                )
                for r in existing:
                    if _row_has_score(r.metrics) or _row_is_terminal_error(r.metrics):
                        evaluated_by_gen.setdefault(r.generation_id, set()).add(
                            _normalize_field_key(r.field_name, is_annotation=False)
                        )
                logger.info(
                    f"Loaded existing gen evaluations: {sum(len(v) for v in evaluated_by_gen.values())} "
                    f"results across {len(evaluated_by_gen)} generations"
                )

            # Enumerate generation cells.
            uses_all_model = any(
                "__all_model__" in c.get("prediction_fields", []) for c in enabled_configs
            )
            gen_cells: List[tuple] = []  # (task_id, generation_id, already_done_field_keys)
            for task in tasks:
                generations_query = db.query(Generation).filter(Generation.task_id == task.id)
                if not uses_all_model:
                    generations_query = generations_query.filter(
                        Generation.parse_status == "success"
                    )
                if label_config_version:
                    generations_query = generations_query.filter(
                        Generation.label_config_version == label_config_version
                    )
                if model_ids:
                    generations_query = generations_query.filter(
                        Generation.model_id.in_(model_ids)
                    )
                generations = generations_query.all()
                for gen in generations:
                    gen_done = evaluated_by_gen.get(gen.id, set())
                    if evaluate_missing_only:
                        if all_expected_field_keys and all_expected_field_keys.issubset(gen_done):
                            # Fully evaluated already; nothing to dispatch for this cell.
                            continue
                    # Pass the per-cell already-done set to the sub-task so it
                    # can skip already-evaluated field_keys WITHOUT firing the
                    # LLM judge call (ON CONFLICT DO NOTHING would catch the
                    # INSERT but the LLM call would already have happened).
                    gen_cells.append((task.id, gen.id, sorted(gen_done) if gen_done else []))

            # Annotation-side enumeration. The legacy body at ~3357-3412
            # pre-loaded all annotations once (with the annotator_user_ids
            # scope filter applied) and the existing-annotation-eval set
            # for dedup. We keep that pattern, just used for enumeration
            # instead of in-place iteration.
            ann_cells: List[tuple] = []  # (task_id, annotation_id)
            has_human_config = False
            try:
                from eval_field_classification import classify_pred_fields as _classify_pf

                for c in enabled_configs:
                    metric = c.get("metric", "")
                    if metric.startswith("korrektur_"):
                        continue
                    human_pfs, _ = _classify_pf(metric, c.get("prediction_fields", []))
                    if human_pfs:
                        has_human_config = True
                        break
            except Exception:
                has_human_config = False

            if has_human_config:
                task_id_list = [t.id for t in tasks]
                ann_query = db.query(Annotation).filter(
                    Annotation.task_id.in_(task_id_list),
                    Annotation.was_cancelled == False,  # noqa: E712
                )
                if annotator_user_ids:
                    ann_pre_count = ann_query.count()
                    ann_query = ann_query.filter(
                        Annotation.completed_by.in_(annotator_user_ids)
                    )
                all_annotations = ann_query.all()
                if annotator_user_ids:
                    logger.info(
                        f"[evaluation {evaluation_id}] annotator_user_ids filter active "
                        f"({len(annotator_user_ids)} ids); annotation pool reduced from "
                        f"{ann_pre_count} to {len(all_annotations)}"
                    )

                evaluated_by_ann: Dict[str, set] = {}
                if evaluate_missing_only:
                    existing_ann = (
                        db.query(
                            TaskEvaluation.annotation_id,
                            TaskEvaluation.field_name,
                            TaskEvaluation.metrics,
                        )
                        .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
                        .filter(
                            TaskEvaluation.task_id.in_(task_id_list),
                            TaskEvaluation.annotation_id.isnot(None),
                            EvaluationRun.status.in_(("completed", "running", "pending", "cancelled")),
                        )
                        .all()
                    )
                    for r in existing_ann:
                        if _row_has_score(r.metrics) or _row_is_terminal_error(r.metrics):
                            evaluated_by_ann.setdefault(r.annotation_id, set()).add(
                                _normalize_field_key(r.field_name, is_annotation=True)
                            )

                for ann in all_annotations:
                    ann_done = evaluated_by_ann.get(ann.id, set())
                    if evaluate_missing_only:
                        if all_expected_field_keys and all_expected_field_keys.issubset(ann_done):
                            continue
                    ann_cells.append((ann.task_id, ann.id, sorted(ann_done) if ann_done else []))

            # ── Build serialized judge_run_ids_by_config for Celery kwargs ────
            # The full `judge_runs_by_config` dict (built upstream during judge
            # setup, lines 2516-2724) carries non-serializable `evaluator`
            # instances. Sub-tasks reconstruct evaluators per-process via
            # `_reconstruct_judge_evaluators_for_cell` — orchestrator only
            # needs to pass the IDs they should attach to.
            judge_run_ids_by_config_serializable = {
                cid: [
                    {
                        "judge_model_id": e.get("judge_model_id"),
                        "run_index": e.get("run_index"),
                        "judge_run_id": e.get("judge_run_id"),
                        # Threaded through to sub-tasks so each worker process
                        # can re-instantiate the LLMJudgeEvaluator without
                        # redoing param resolution. See orchestrator's
                        # judge-init block for the source of these values.
                        "judge_evaluator_kwargs": e.get("judge_evaluator_kwargs"),
                    }
                    for e in entries
                ]
                for cid, entries in judge_runs_by_config.items()
            }

            # Persist dispatch metadata so finalize can find judge_run IDs
            # when building the `judges_by_config` summary.
            cells_dispatched = len(gen_cells) + len(ann_cells)
            from sqlalchemy.orm.attributes import flag_modified

            evaluation.eval_metadata = {
                **(evaluation.eval_metadata or {}),
                "dispatched_at": datetime.now().isoformat(),
                "cells_dispatched": cells_dispatched,
                "judge_run_ids_by_config": judge_run_ids_by_config_serializable,
                "gen_cells_dispatched": len(gen_cells),
                "ann_cells_dispatched": len(ann_cells),
            }
            flag_modified(evaluation, "eval_metadata")
            db.commit()

            # Nothing to do — short-circuit (e.g. all targets already done in
            # `missing-only` mode, or no generations exist for the project yet).
            if cells_dispatched == 0:
                evaluation.status = "completed"
                evaluation.completed_at = datetime.now()
                evaluation.samples_evaluated = 0
                evaluation.has_sample_results = True
                evaluation.metrics = {}
                eval_meta_after = evaluation.eval_metadata or {}
                eval_meta_after.update({
                    "samples_passed": 0,
                    "samples_failed": 0,
                    "pass_rate": 0,
                    "any_judge_failed": False,
                    "note": "no cells to dispatch (missing-only short-circuit)",
                })
                evaluation.eval_metadata = eval_meta_after
                flag_modified(evaluation, "eval_metadata")
                db.commit()
                logger.info(
                    f"Eval {evaluation_id} short-circuited: 0 cells to dispatch"
                )
                return {
                    "status": "success",
                    "evaluation_id": evaluation_id,
                    "cells_dispatched": 0,
                    "samples_evaluated": 0,
                }

            # ── Chord dispatch ────────────────────────────────────────────────
            # One Celery sub-task per cell, all dispatched to the dedicated
            # `evaluation` queue. The chord callback `finalize_evaluation_run`
            # runs exactly once after every header sub-task finishes (success
            # or failure — chord doesn't gate on success).
            from celery import chord

            triggered_by = (
                evaluation.eval_metadata.get("triggered_by")
                if evaluation.eval_metadata else None
            )

            header_sigs = []
            for (cell_task_id, cell_gen_id, cell_already_done) in gen_cells:
                header_sigs.append(
                    evaluate_generation_cell.signature(
                        kwargs={
                            "evaluation_id": evaluation_id,
                            "task_id": cell_task_id,
                            "generation_id": cell_gen_id,
                            "project_id": project_id,
                            "configs_for_cell": enabled_configs,
                            "judge_run_ids_by_config": judge_run_ids_by_config_serializable,
                            "default_judge_run_id": default_judge_run_id,
                            "organization_id": organization_id,
                            "triggered_by_user_id": triggered_by,
                            "label_config_version": label_config_version,
                            "already_evaluated_field_keys": cell_already_done,
                        },
                        queue="evaluation",
                    )
                )
            for (cell_task_id, cell_ann_id, cell_already_done) in ann_cells:
                header_sigs.append(
                    evaluate_annotation_cell.signature(
                        kwargs={
                            "evaluation_id": evaluation_id,
                            "task_id": cell_task_id,
                            "annotation_id": cell_ann_id,
                            "project_id": project_id,
                            "configs_for_cell": enabled_configs,
                            "judge_run_ids_by_config": judge_run_ids_by_config_serializable,
                            "default_judge_run_id": default_judge_run_id,
                            "organization_id": organization_id,
                            "triggered_by_user_id": triggered_by,
                            "already_evaluated_field_keys": cell_already_done,
                        },
                        queue="evaluation",
                    )
                )

            # Final cancel check just before chord dispatch. The
            # orchestrator's setup phase (judge_run creation, work-unit
            # enumeration, missing-only preload) can run for ~25 s on a
            # ZJS-scale eval; an admin or operator hitting Cancel during
            # that window should stop us BEFORE we fan out 6940 sub-tasks
            # that each immediately short-circuit on their own
            # parent-status check. Saves Celery message churn + worker
            # CPU for no useful work.
            db.refresh(evaluation)
            if evaluation.status in ("cancelled", "failed", "completed"):
                logger.info(
                    f"Eval {evaluation_id} reached terminal status "
                    f"'{evaluation.status}' during orchestrator setup; "
                    "skipping chord dispatch."
                )
                return {
                    "status": "cancelled_before_dispatch",
                    "evaluation_id": evaluation_id,
                    "current_status": evaluation.status,
                    "cells_would_have_dispatched": cells_dispatched,
                }

            callback_sig = finalize_evaluation_run.signature(
                kwargs={"evaluation_id": evaluation_id},
                queue="evaluation",
            )

            chord_result = chord(header_sigs)(callback_sig)

            logger.info(
                f"✅ Dispatched {len(header_sigs)} eval cell sub-tasks for evaluation "
                f"{evaluation_id} (gen: {len(gen_cells)}, ann: {len(ann_cells)}); "
                f"chord callback id={chord_result.id}"
            )

            return {
                "status": "dispatched",
                "evaluation_id": evaluation_id,
                "project_id": project_id,
                "cells_dispatched": cells_dispatched,
                "gen_cells": len(gen_cells),
                "ann_cells": len(ann_cells),
                "chord_id": chord_result.id,
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in run_evaluation: {e}", exc_info=True)

        # Update evaluation status to failed
        try:
            db = SessionLocal()
            from datetime import datetime

            from models import EvaluationRun

            evaluation = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id).first()
            if evaluation:
                evaluation.status = "failed"
                evaluation.error_message = str(e)
                evaluation.completed_at = datetime.now()
                db.commit()

                # Create notification for evaluation failure
                try:
                    triggered_by = (
                        evaluation.eval_metadata.get("triggered_by")
                        if evaluation.eval_metadata
                        else None
                    )
                    if triggered_by:
                        NotificationService.create_notification(
                            db=db,
                            user_ids=[triggered_by],
                            notification_type=NotificationType.EVALUATION_FAILED,
                            title="Evaluation Failed",
                            message=f"Evaluation failed: {str(e)[:100]}",
                            data={
                                "project_id": project_id,
                                "evaluation_id": evaluation_id,
                                "error": str(e),
                            },
                        )
                        logger.info(f"📬 Created failure notification for user {triggered_by}")
                except Exception as notif_err:
                    logger.error(f"Failed to create failure notification: {notif_err}")

            db.close()
        except Exception as update_error:
            logger.error(f"Failed to update evaluation status: {update_error}")

        return {
            "status": "error",
            "message": str(e),
            "evaluation_id": evaluation_id,
        }


# Backward-compatible alias so in-flight Celery messages with the old task name still work
run_multi_field_evaluation = app.task(name="tasks.run_multi_field_evaluation")(run_evaluation)


def _get_provider_from_model(model_id: str) -> str:
    """Determine LLM provider from model ID."""
    from ai_services.provider_capabilities import get_provider_from_model
    return get_provider_from_model(model_id)


# =============================================================================
# Immediate Falllösung Evaluation Task
# =============================================================================


def _immediate_eval_metadata():
    """Return standard eval_metadata and metrics for immediate EvaluationRun records."""
    return {
        "metrics": {"llm_judge_falloesung": True},
        "eval_metadata": {
            "evaluation_type": "llm_judge",
            "evaluation_configs": [{
                "id": "immediate_llm_judge_falloesung",
                "metric": "llm_judge_falloesung",
                "display_name": "LLM Judge Falllösung",
                "enabled": True,
            }],
        },
    }


# Phase 5: Falllösung Celery task + persistence helpers moved to
# benger-extended/benger_extended/workers/falloesung_tasks.py.
# Registered into this Celery app via
# benger_extended.workers.register_tasks(app) at worker startup
# (see worker bootstrap at the bottom of this file).


# =============================================================================
# Unified Single-Sample Evaluation Task
# =============================================================================


@app.task(name="tasks.run_single_sample_evaluation", bind=True)
def run_single_sample_evaluation(
    self,
    evaluation_record_id: str,
    project_id: str,
    task_id: str,
    annotation_id: str,
    evaluation_configs: List[Dict[str, Any]],
    annotation_results: Dict[str, Any],
    task_data: Dict[str, Any],
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run evaluation for a single annotation against configured metrics via Celery.

    This is the unified immediate evaluation task that replaces both the synchronous
    compute_metric_value() approximations and the specialized run_immediate_falloesung task.
    All metrics use real implementations (NLTK BLEU, rouge-score, bert-score, etc.).

    Args:
        evaluation_record_id: UUID for the TaskEvaluation record
        project_id: Project ID
        task_id: Task ID
        annotation_id: Annotation ID
        evaluation_configs: List of evaluation config dicts with metric, prediction_fields, reference_fields
        annotation_results: Dict mapping from_name -> extracted annotation value
        task_data: Task data dict for reference field lookup
        organization_id: Organization ID for API key resolution
        user_id: User ID for API key resolution
    """
    import time
    import uuid
    from datetime import datetime

    db = SessionLocal()
    try:
        from models import EvaluationRun, TaskEvaluation
        from project_models import Project

        # Phase 6.4: snapshot the project's schema state at run-start so
        # historical evaluations stay reproducible even if label_config or
        # evaluation_config is edited later. Without this, a paper citing
        # a benchmark score has no way to reconstruct which schema
        # produced the number.
        project_for_snapshot = (
            db.query(Project).filter(Project.id == project_id).first()
        )
        run_provenance: Dict[str, Any] = {}
        if project_for_snapshot is not None:
            run_provenance = {
                "label_config_version": getattr(
                    project_for_snapshot, "label_config_version", None
                ),
                "evaluation_config_snapshot": project_for_snapshot.evaluation_config,
                "worker_image_tag": os.environ.get("WORKER_IMAGE_TAG", "unknown"),
                "spacy_de_model_version": "de_core_news_md@3.7.0",
            }

        # Create a per-dispatch EvaluationRun so polling can find all results
        dispatch_eval_id = evaluation_record_id
        eval_run = EvaluationRun(
            id=dispatch_eval_id,
            project_id=project_id,
            model_id="immediate",
            evaluation_type_ids=[c.get("metric", "") for c in evaluation_configs],
            status="running",
            created_by=user_id or "system",
            eval_metadata={
                "evaluation_type": "immediate",
                "expected_config_count": len(evaluation_configs),
                "configs": [
                    {"metric": c.get("metric", ""), "display_name": c.get("display_name", c.get("metric", ""))}
                    for c in evaluation_configs
                ],
                **run_provenance,
            },
            metrics={},
        )
        db.add(eval_run)
        db.flush()

        # Migration 042: every TaskEvaluation row needs a judge_run_id (will
        # be NOT NULL after migration 043). Immediate eval is single-judge
        # per call by design, so create one catch-all judge_run for the
        # whole dispatch and stamp it on every row. judge_model_id is null
        # for deterministic metrics; for LLM judge metrics it's filled in
        # below per (config, judge) pair.
        from models import EvaluationJudgeRun

        default_judge_run = EvaluationJudgeRun(
            id=str(uuid.uuid4()),
            evaluation_id=dispatch_eval_id,
            judge_model_id=None,
            run_index=0,
            status="running",
            started_at=datetime.now(),
        )
        db.add(default_judge_run)
        db.flush()
        default_judge_run_id = default_judge_run.id

        # Per-config LLM judge_runs: created lazily as we encounter llm_judge_*
        # metrics. Keyed by config_id so multiple LLM-judge configs each get
        # their own row (one per judge model).
        per_config_judge_run_id: Dict[str, str] = {}

        # Cache (judge_model_id, run_index) -> jr_id within this dispatch so
        # configs that share the same judge reuse the same EvaluationJudgeRun
        # instead of colliding on uq_evaluation_judge_runs.
        _dispatch_judge_run_cache: Dict[tuple, str] = {}

        def _get_or_create_judge_run_for_config(cfg: Dict[str, Any]) -> str:
            cid = cfg.get("id", "unknown")
            if cid in per_config_judge_run_id:
                return per_config_judge_run_id[cid]
            params = cfg.get("metric_parameters") or {}
            judge_model = params.get("judge_model")
            judges = params.get("judges")
            if isinstance(judges, list) and judges:
                judge_model = judges[0].get("judge_model_id") or judge_model
            cache_key = (judge_model, 0)
            if cache_key in _dispatch_judge_run_cache:
                jr_id = _dispatch_judge_run_cache[cache_key]
                per_config_judge_run_id[cid] = jr_id
                return jr_id
            existing = db.query(EvaluationJudgeRun).filter(
                EvaluationJudgeRun.evaluation_id == dispatch_eval_id,
                EvaluationJudgeRun.judge_model_id == judge_model,
                EvaluationJudgeRun.run_index == 0,
            ).first()
            if existing:
                # See _create_judge_run: revive a judge_run a prior cancel left
                # terminal so a resume regrades into a 'running' row, not a stale
                # 'failed'/'cancelled' one the finalizer would misread.
                if existing.status in ("failed", "cancelled"):
                    existing.status = "running"
                    existing.error_message = None
                    existing.completed_at = None
                    existing.started_at = datetime.now()
                    db.commit()
                _dispatch_judge_run_cache[cache_key] = existing.id
                per_config_judge_run_id[cid] = existing.id
                return existing.id
            # Same tiered resolution as run_evaluation, applied to the
            # immediate-eval / single-sample dispatch path so judge_runs
            # created here also capture _param_provenance for academic-
            # rigor traceability.
            judge_model_obj = (
                db.query(DBLLMModel).filter(DBLLMModel.id == judge_model).first()
                if judge_model
                else None
            )
            judge_recommended = (
                getattr(judge_model_obj, "recommended_parameters", None) or None
            )
            judge_provenance: Dict[str, Dict[str, Any]] = {}

            def _resolve_for_jr(key: str):
                value, source, rec_at_trigger = _resolve_param(
                    key=key,
                    mode="evaluation",
                    model_recommended=judge_recommended,
                    project_cfg=None,
                    per_model_cfg=params,
                )
                judge_provenance[key] = {
                    "value": value,
                    "source": source,
                    "recommended_at_trigger": rec_at_trigger,
                }
                return value

            for _k in ("temperature", "max_tokens", "seed"):
                _resolve_for_jr(_k)

            snapshot = dict(params) if params else {}
            snapshot["_param_provenance"] = judge_provenance

            jr = EvaluationJudgeRun(
                id=str(uuid.uuid4()),
                evaluation_id=dispatch_eval_id,
                judge_model_id=judge_model,
                run_index=0,
                status="running",
                started_at=datetime.now(),
                metric_parameters_snapshot=snapshot,
            )
            db.add(jr)
            db.flush()
            _dispatch_judge_run_cache[cache_key] = jr.id
            per_config_judge_run_id[cid] = jr.id
            return jr.id

        results = []

        for eval_cfg in evaluation_configs:
            metric_type = eval_cfg.get("metric", "")
            pred_fields = eval_cfg.get("prediction_fields", [])
            ref_fields = eval_cfg.get("reference_fields", [])
            metric_params = eval_cfg.get("metric_parameters", {})

            # Korrektur (Classic / Standard Falllösung) is human-graded —
            # the score is persisted directly by the API when a corrector
            # submits, never computed by this worker. Skip it from the
            # dispatch loop entirely so we don't try (and fail) to compare
            # a non-existent prediction against a non-existent reference.
            if metric_type.startswith("korrektur_"):
                continue

            # Extract prediction and reference values.
            #
            # `prediction_fields` carries either a literal field name, a
            # `human:<field>` / `model:<field>` prefixed name (matching the
            # EvaluationBuilder's specifiers), or the bulk selectors
            # `__all_human__` / `__all_model__`. `annotation_results` is
            # keyed by raw `from_name`, so we strip prefixes and expand the
            # `__all_human__` selector before lookup.
            prediction_value = None
            reference_value = None

            def _resolve_human_field(pf: str):
                if pf == "__all_human__":
                    if not annotation_results:
                        return None
                    return "\n\n".join(
                        f"{k}: {v}" for k, v in annotation_results.items() if v
                    )
                key = pf.split(":", 1)[1] if pf.startswith("human:") else pf
                return annotation_results.get(key)

            for pf in pred_fields:
                if pf.startswith("model:") or pf == "__all_model__":
                    # Single-sample immediate eval has no model generations to
                    # evaluate against — only human annotations. Skip.
                    continue
                value = _resolve_human_field(pf)
                if value:
                    prediction_value = value
                    break

            for rf in ref_fields:
                if rf.startswith("task."):
                    data_field = rf[5:]
                    reference_value = task_data.get(data_field) if task_data else None
                elif task_data and rf in task_data:
                    reference_value = task_data.get(rf)
                if reference_value is not None:
                    break

            if prediction_value is None:
                logger.warning(f"[SingleSampleEval] Skipping {metric_type} - no prediction value")
                continue

            field_name = pred_fields[0] if pred_fields else "field"
            record_id = str(uuid.uuid4())

            try:
                if metric_type == "llm_judge_falloesung":
                    # Phase 5: Delegate to extended-registered Falllösung
                    # compute. Platform code never imports the function
                    # directly — it asks the extended package to provide
                    # one. Community edition (no benger_extended) raises
                    # an informative error rather than crashing.
                    try:
                        from benger_extended.workers import (
                            get_falloesung_compute_fn,
                        )
                    except ImportError as exc:
                        raise RuntimeError(
                            "Metric 'llm_judge_falloesung' requires the "
                            "benger_extended package; it is not installed "
                            "in this worker. Configure the project to use "
                            "a different LLM-judge metric or load the "
                            "extended edition."
                        ) from exc
                    falloesung_fn = get_falloesung_compute_fn()
                    judge_run_id = _get_or_create_judge_run_for_config(eval_cfg)
                    # Pass judge_run_id when the extended fn supports it;
                    # older extended packages won't accept the kwarg, so we
                    # introspect first and fall back gracefully.
                    import inspect as _inspect
                    fn_params = set(_inspect.signature(falloesung_fn).parameters.keys())
                    extra = {"judge_run_id": judge_run_id} if "judge_run_id" in fn_params else {}
                    result = falloesung_fn(
                        db=db,
                        record_id=record_id,
                        immediate_eval_id=dispatch_eval_id,
                        project_id=project_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        user_id=user_id,
                        field_name=field_name,
                        prediction=str(prediction_value),
                        task_data=task_data,
                        metric_params=metric_params,
                        organization_id=organization_id,
                        **extra,
                    )
                    results.append(result)

                elif metric_type.startswith("llm_judge_"):
                    # Other LLM judge metrics — use LLMJudgeEvaluator. Pass
                    # the per-config judge_run so this row's judge_run_id
                    # points at the right (single) judge for the config.
                    judge_run_id = _get_or_create_judge_run_for_config(eval_cfg)
                    result = _evaluate_llm_judge_single(
                        db=db,
                        record_id=record_id,
                        immediate_eval_id=dispatch_eval_id,
                        judge_run_id=judge_run_id,
                        project_id=project_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        user_id=user_id,
                        field_name=field_name,
                        metric_type=metric_type,
                        prediction=str(prediction_value),
                        reference=str(reference_value) if reference_value else "",
                        metric_params=metric_params,
                        organization_id=organization_id,
                        # Issue #111 / migration 057: thread the config id
                        # down so the persisted row carries it discretely.
                        evaluation_config_id=eval_cfg.get("id"),
                    )
                    results.append(result)

                else:
                    # Deterministic metrics — use SampleEvaluator with real implementations
                    from ml_evaluation.sample_evaluator import SampleEvaluator
                    from ml_evaluation import extract_value

                    field_configs = {field_name: {"type": "text"}}
                    param_configs = {field_name: {metric_type: metric_params}} if metric_params else {}
                    evaluator = SampleEvaluator(record_id, field_configs, param_configs)

                    # Phase 2: rich result dict with provenance. The legacy
                    # consumer (passed=score>=0.5 etc.) extracts the bare
                    # value via the shared shim; the persisted record now
                    # stores the full audit trail under metric_type.
                    metric_result = evaluator._compute_metric_with_details(
                        metric_name=metric_type,
                        ground_truth=reference_value,
                        prediction=prediction_value,
                        answer_type="text",
                        parameters=metric_params or None,
                    )
                    score_value = extract_value(metric_result) or 0.0

                    eval_record = TaskEvaluation(
                        id=record_id,
                        evaluation_id=dispatch_eval_id,
                        # Migration 042: deterministic metrics use the
                        # default judge_run (judge_model_id=None) created
                        # for this dispatch.
                        judge_run_id=default_judge_run_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        generation_id=None,
                        field_name=field_name,
                        # Issue #111 / migration 057: store the config id
                        # discretely so downstream readers don't have to
                        # parse field_name. Immediate-eval writes a bare
                        # field_name, so this column is the only place
                        # the config id survives.
                        evaluation_config_id=eval_cfg.get("id"),
                        answer_type="text",
                        ground_truth=str(reference_value) if reference_value else "",
                        prediction=str(prediction_value) if prediction_value else "",
                        metrics={
                            metric_type: metric_result,  # Full {value, details, ...}
                            "raw_score": float(score_value),
                        },
                        passed=float(score_value) >= 0.5,
                    )
                    db.add(eval_record)
                    db.commit()

                    results.append({
                        "status": "completed",
                        "record_id": record_id,
                        "metric": metric_type,
                        "score": float(score_value),
                        "details": metric_result.get("details") if isinstance(metric_result, dict) else None,
                    })

            except Exception as e:
                logger.error(f"[SingleSampleEval] {metric_type} failed: {e}")
                # Phase 5: error persistence helper moved to extended.
                # Falllösung-specific failures use the extended helper;
                # everything else logs the error and proceeds (the
                # generic LLM judge / deterministic-metric paths don't
                # need a per-failure DB record — the worker-level error
                # is enough). For Falllösung specifically, defer to the
                # extended helper if present.
                if metric_type == "llm_judge_falloesung":
                    try:
                        from benger_extended.workers.falloesung_tasks import (
                            _persist_falloesung_eval_error,
                        )
                        _persist_falloesung_eval_error(
                            db, record_id, project_id, task_id,
                            annotation_id, user_id or "system", field_name,
                            str(reference_value) if reference_value else "",
                            str(prediction_value) if prediction_value else "",
                            str(e),
                            eval_run_id=dispatch_eval_id,
                        )
                    except ImportError:
                        # Community edition — best effort, just log.
                        logger.warning(
                            "Falllösung error persistence skipped; "
                            "benger_extended not installed"
                        )
                results.append({
                    "status": "error",
                    "record_id": record_id,
                    "metric": metric_type,
                    "error": str(e),
                })

        # Mark the dispatch run as completed and aggregate metrics
        eval_run = db.query(EvaluationRun).filter(EvaluationRun.id == dispatch_eval_id).first()
        if eval_run:
            eval_run.status = "completed"

            # Aggregate TaskEvaluation scores into EvaluationRun.metrics
            # so the comparison table on /evaluations can display them
            task_evals = db.query(TaskEvaluation).filter(
                TaskEvaluation.evaluation_id == dispatch_eval_id
            ).all()

            if task_evals:
                from collections import defaultdict
                metric_scores = defaultdict(list)
                skip_suffixes = ("_details", "_response", "_raw", "_passed")
                for te in task_evals:
                    field_name = te.field_name or "annotation"
                    for metric_name, score in (te.metrics or {}).items():
                        if isinstance(score, (int, float)) and metric_name != "raw_score" and not any(metric_name.endswith(s) for s in skip_suffixes):
                            metric_scores[(field_name, metric_name)].append(score)

                aggregated = {}
                for (field_name, metric_name), scores in metric_scores.items():
                    # Key format: config_id:pred_field:ref_field:metric_name
                    key = f"{metric_name}:{field_name}:reference:{metric_name}"
                    aggregated[key] = sum(scores) / len(scores)

                eval_run.metrics = aggregated
                eval_run.samples_evaluated = len(task_evals)

                # Normalize eval_metadata to include evaluation_configs with full structure
                if eval_run.eval_metadata and "configs" in eval_run.eval_metadata and "evaluation_configs" not in eval_run.eval_metadata:
                    eval_run.eval_metadata = {
                        **eval_run.eval_metadata,
                        "evaluation_configs": [
                            {
                                "id": c.get("metric", ""),
                                "metric": c.get("metric", ""),
                                "display_name": c.get("display_name", c.get("metric", "")),
                                "prediction_fields": [],
                                "reference_fields": [],
                                "enabled": True,
                            }
                            for c in eval_run.eval_metadata["configs"]
                        ],
                    }

            db.commit()

        return {
            "status": "completed",
            "evaluation_record_id": evaluation_record_id,
            "results": results,
        }

    except Exception as e:
        logger.error(f"[SingleSampleEval] Task failed: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# Phase 5: _evaluate_falloesung_single moved to
# benger-extended/benger_extended/workers/falloesung_tasks.evaluate_falloesung_single
# and dispatched via the metric registry hook. See the
# llm_judge_falloesung branch in run_single_sample_evaluation above.


def _evaluate_llm_judge_single(
    db, record_id, immediate_eval_id, project_id, task_id,
    annotation_id, user_id, field_name, metric_type, prediction,
    reference, metric_params, organization_id,
    judge_run_id: Optional[str] = None,
    evaluation_config_id: Optional[str] = None,
):
    """Run generic LLM judge evaluation for a single sample.

    Args:
        judge_run_id: EvaluationJudgeRun id this row belongs to (migration 042).
            Optional for backwards compatibility with any caller that hasn't
            been updated; passing None leaves the column NULL until the
            judge_run_id NOT NULL migration lands.
        evaluation_config_id: Issue #111 / migration 057 — the evaluation
            config id this row belongs to, persisted discretely so
            downstream readers don't parse ``field_name``. Optional for
            backward compatibility; older callers leave it NULL.
    """
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from models import TaskEvaluation

    params = metric_params or {}
    judge_model = params.get("judge_model", "gpt-4o")
    provider = _get_provider_from_model(judge_model)

    # Tiered parameter resolution for the judge call (mode='evaluation').
    # Same precedence as generation but with metric_parameters as the
    # user_per_model tier. Catalog `recommended_parameters` becomes the
    # third tier so a judge call honors provider-recommended defaults
    # whenever metric_parameters doesn't pin a value.
    judge_model_obj = (
        db.query(DBLLMModel).filter(DBLLMModel.id == judge_model).first()
    )
    judge_recommended = (
        getattr(judge_model_obj, "recommended_parameters", None) or None
    )

    def _resolve_judge(key: str, fallback_default: Any = None):
        value, _source, _rec = _resolve_param(
            key=key,
            mode="evaluation",
            model_recommended=judge_recommended,
            project_cfg=None,
            per_model_cfg=params,
        )
        return value if value is not None else fallback_default

    # Apply per-model temperature constraint (e.g. Opus 4.7 → 1.0, GPT-5
    # → 1.0, DeepSeek-R1 min 0.6). Mirror of the generation-side clamp.
    judge_constraints = (
        getattr(judge_model_obj, "parameter_constraints", None) or None
    )
    _judge_temp, _ = _clamp_temperature_to_constraint(
        _resolve_judge("temperature", 0.0), judge_constraints
    )

    llm_judge = create_llm_judge_for_user(
        db=db,
        user_id=user_id,
        provider=provider,
        judge_model=judge_model,
        temperature=_judge_temp,
        max_tokens=_resolve_judge("max_tokens", 500),
        criteria=params.get("dimensions"),
        custom_criteria=params.get("custom_criteria"),
        custom_prompt_template=params.get("custom_prompt_template"),
        answer_type=params.get("answer_type"),
        field_mappings=params.get("field_mappings"),
        score_scale=params.get("score_scale", "1-5"),
        organization_id=organization_id,
        seed=_resolve_judge("seed", 42),
    )

    if not llm_judge.ai_service:
        raise RuntimeError(f"No AI service available for LLM judge ({provider})")

    # Multi-dim single-call mode: when custom_criteria carries max_score on
    # any dimension, the user's prompt is expected to score every dimension
    # in one LLM call (Grundprinzipien-style 4-dim rubric). Skip the
    # per-criterion fan-out and persist per-dim scores under
    # metrics[<metric>].details.scores.
    if llm_judge.is_multidim_mode():
        from project_models import Task as ProjectTask, Annotation
        from annotation_utils import extract_all_field_values
        task_row = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
        task_data = (task_row.data if task_row else {}) or {}

        # Flatten the model/annotation output so the prompt can reference
        # individual fields by name (e.g. {{kurzantwort}}, {{begruendung}})
        # without forcing the user to write field_mappings for every one.
        # Branches by whichever target the eval is grading.
        field_outputs: Dict[str, Any] = {}
        if annotation_id:
            ann_row = db.query(Annotation).filter(Annotation.id == annotation_id).first()
            if ann_row and ann_row.result:
                field_outputs = extract_all_field_values(ann_row.result)
        # Generation case: parsed_annotation lives on the generation row
        # already in label-studio shape, so the same flattener works.
        gen_id_from_meta = (metric_params or {}).get("generation_id")
        if not field_outputs and gen_id_from_meta:
            gen_row = db.query(DBLLMResponse).filter(DBLLMResponse.id == gen_id_from_meta).first()
            parsed = getattr(gen_row, "parsed_annotation", None) if gen_row else None
            if parsed:
                field_outputs = extract_all_field_values(parsed)

        multidim = llm_judge._evaluate_multidim_single_call(
            context="",
            ground_truth=reference,
            prediction=prediction,
            task_data=task_data,
            field_outputs=field_outputs,
        )
        if multidim is None or multidim.get("error") or "scores" not in multidim:
            err_msg = (
                (multidim or {}).get("error_message") or "multi-dim LLM judge produced no scores"
            )
            raise RuntimeError(err_msg)

        total = float(multidim.get("total_score") or 0.0)
        total_max = float(multidim.get("total_max") or 0.0)
        normalized = total / total_max if total_max > 0 else 0.0
        eval_record = TaskEvaluation(
            id=record_id,
            evaluation_id=immediate_eval_id,
            judge_run_id=judge_run_id,
            task_id=task_id,
            annotation_id=annotation_id,
            generation_id=None,
            field_name=field_name,
            # Issue #111 / migration 057: discrete carrier of the config id.
            evaluation_config_id=evaluation_config_id,
            answer_type="text",
            ground_truth=reference,
            prediction=prediction,
            metrics={
                metric_type: {
                    "value": float(normalized),
                    "method": metric_type,
                    "details": {
                        "scores": multidim["scores"],
                        "total_score": total,
                        "total_max": total_max,
                        "overall_assessment": multidim.get("overall_assessment", ""),
                        "call_metadata": multidim.get("_call_metadata", {}),
                        "raw_output": multidim.get("_raw_output", ""),
                    },
                    "error": None,
                },
                "raw_score": float(normalized),
            },
            judge_prompts_used=multidim.get("_judge_prompts_used"),
            passed=float(normalized) >= 0.5,
        )
        db.add(eval_record)
        db.commit()
        return {
            "status": "completed",
            "record_id": record_id,
            "metric": metric_type,
            "score": float(normalized),
            "total_score": total,
            "total_max": total_max,
        }

    # Derive the per-criterion key from the metric name. `llm_judge_helpfulness`
    # → criterion `helpfulness`. `llm_judge_classic` / `llm_judge_custom`
    # don't carry a single criterion in the name; fall back to the first
    # configured criterion on the evaluator.
    criterion = (
        metric_type.replace("llm_judge_", "")
        if metric_type.startswith("llm_judge_") and metric_type != "llm_judge_classic"
        and metric_type != "llm_judge_custom"
        else (llm_judge.criteria[0] if llm_judge.criteria else "helpfulness")
    )

    # Use the per-criterion path directly: this is the same call evaluate()
    # makes internally per (sample, criterion). The previous code called
    # llm_judge.evaluate_single(...) which never existed on LLMJudgeEvaluator
    # and would crash any non-Falllösung llm_judge metric in immediate-eval.
    raw = llm_judge._evaluate_single_criterion(
        context="",
        ground_truth=reference,
        prediction=prediction,
        criterion=criterion,
        task_data={},
    )
    if raw is None or raw.get("error") or "score" not in raw:
        err_msg = (
            (raw or {}).get("error_message") or f"LLM judge produced no score for {criterion}"
        )
        raise RuntimeError(err_msg)

    raw_score = float(raw["score"])
    # Normalize to 0..1 the same way evaluate() does for the bulk path.
    score = raw_score if llm_judge.score_scale == "0-1" else (raw_score - 1) / 4
    eval_record = TaskEvaluation(
        id=record_id,
        evaluation_id=immediate_eval_id,
        judge_run_id=judge_run_id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=None,
        field_name=field_name,
        # Issue #111 / migration 057: discrete carrier of the config id.
        evaluation_config_id=evaluation_config_id,
        answer_type="text",
        ground_truth=reference,
        prediction=prediction,
        metrics={
            metric_type: float(score),
            f"{metric_type}_details": raw,
            "raw_score": float(score),
        },
        passed=float(score) >= 0.5,
    )
    db.add(eval_record)
    db.commit()

    return {
        "status": "completed",
        "record_id": record_id,
        "metric": metric_type,
        "score": float(score),
    }


# =============================================================================
# Worker bootstrap: load extended Celery tasks if available
# =============================================================================
#
# Phase 5 of the academic-rigor overhaul. The extended package ships
# additional Celery tasks (e.g. tasks.run_immediate_falloesung) and metric
# handlers (llm_judge_falloesung). They register themselves into THIS
# Celery app via two hooks. Community edition (no benger_extended) is a
# clean no-op via the outer ImportError handler.
#
# The version handshake mirrors services/api/extensions.py so a mismatched
# extended package surfaces loudly at startup, not in a silent dispatch
# error during evaluation.
from core_version import CORE_API_VERSION as _WORKER_CORE_API_VERSION  # noqa: E402
from core_version import extended_required as _extended_required  # noqa: E402

try:
    import benger_extended  # noqa: F401

    _ext_compatible = True
    if hasattr(benger_extended, "COMPATIBLE_CORE_VERSIONS"):
        if _WORKER_CORE_API_VERSION not in benger_extended.COMPATIBLE_CORE_VERSIONS:
            if _extended_required():
                raise RuntimeError(
                    "Worker: benger_extended core-version mismatch — needs "
                    f"{benger_extended.COMPATIBLE_CORE_VERSIONS}, core is "
                    f"{_WORKER_CORE_API_VERSION}. BENGER_REQUIRE_EXTENDED is "
                    "set — refusing to start with extended tasks disabled."
                )
            logger.error(
                "Worker: benger_extended core-version mismatch — needs %s, "
                "core is %s. Extended tasks NOT registered.",
                benger_extended.COMPATIBLE_CORE_VERSIONS,
                _WORKER_CORE_API_VERSION,
            )
            _ext_compatible = False

    if _ext_compatible:
        from benger_extended.workers import register_tasks as _ext_register_tasks

        _ext_register_tasks(app)
        logger.info("Worker: benger_extended Celery tasks registered")
        # NOTE: register_metric_handlers is wired through
        # ml_evaluation/__init__.py at module-import time (Phase 1) so
        # the registry is already populated by the time the worker
        # starts dispatching. We do NOT re-register here — that would
        # replace the handler with itself and emit a noisy warning.
except ImportError as _ext_import_error:
    if _extended_required():
        raise RuntimeError(
            "BENGER_REQUIRE_EXTENDED is set but the benger_extended package "
            f"failed to import in the worker: {_ext_import_error}. Refusing "
            "to start as community edition."
        ) from _ext_import_error
    logger.info("Worker: community edition (no benger_extended package)")


# =============================================================================
# Per-cell evaluation fan-out (Phase 4 of the eval-parallelization refactor)
#
# `tasks.run_evaluation` is an ORCHESTRATOR. It does the heavy setup
# (status flip, project load, judge_run pre-creation, sample_evaluator
# preparation), enumerates the work units (one per task×generation and
# one per task×annotation), and dispatches each as a per-cell Celery
# sub-task via `chord(group(...))(finalize_evaluation_run)`. Cell
# sub-tasks run in parallel across the worker pool. The chord callback
# `finalize_evaluation_run` aggregates child judge-run statuses, recomputes
# the metrics dict from `TaskEvaluation` rows, and sets the parent's
# terminal status — exactly once when every header sub-task has finished.
#
# Concurrency hazards and their mitigations:
#   * `EvaluationJudgeRun` UQ races → orchestrator pre-creates all
#     judge_run rows before dispatch; sub-tasks never call _create_judge_run.
#   * Evaluator cache thrashing → each sub-task instantiates its own
#     `LLMJudgeEvaluator` per process; `SampleEvaluator` global model
#     caches in `ml_evaluation/sample_evaluator.py` are process-local
#     so the first cell per worker pays the load cost and the rest are free.
#   * `evaluate_missing_only` double-eval → orchestrator pre-filters
#     `configs_for_cell` against the existing-evaluations set; the partial
#     unique index from migration 048 plus `ON CONFLICT DO NOTHING` at
#     insert time is the defense-in-depth against concurrent triggers.
#   * `samples_evaluated` lost updates → SQL `UPDATE ... SET col = col + :n`
#     from each sub-task; Postgres serializes on the row.
#   * Parent status finalization race → Celery chord callback fires
#     exactly once after every sub-task terminates (success or failure).
# =============================================================================


def _reconstruct_judge_evaluators_for_cell(
    *,
    configs_for_cell: List[Dict[str, Any]],
    judge_run_ids_by_config: Dict[str, List[Dict[str, Any]]],
    triggered_by_user_id: str,
    organization_id: Optional[str],
    db,
) -> tuple:
    """Per-sub-task reconstruction of LLMJudgeEvaluator instances.

    Mirrors the orchestrator's judge-evaluator init block (formerly at
    `tasks.py` ~lines 2641-2661) but operates with judge_run_ids the
    orchestrator already created (no `_create_judge_run` calls — those
    happen exactly once in the orchestrator). Each call constructs fresh
    instances in the sub-task's process; safe to call from multiple
    workers concurrently because there's no shared state.

    Returns (judge_runs_by_config, llm_judge_evaluators) where:
      - judge_runs_by_config[cid] = list of {judge_model_id, run_index,
        judge_run_id, evaluator} dicts (evaluator may be None if init
        failed for that judge)
      - llm_judge_evaluators[cid] = the FIRST initialized evaluator for
        the config (for the legacy guard branches that still consult it
        in scalar form)
    """
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user

    judge_runs_by_config: Dict[str, List[Dict[str, Any]]] = {}
    llm_judge_evaluators: Dict[str, Any] = {}

    for config in configs_for_cell:
        metric = config.get("metric", "")
        if not metric.startswith("llm_judge_"):
            continue
        config_id = config.get("id", "unknown")
        entries = judge_run_ids_by_config.get(config_id, []) or []
        judge_runs_by_config.setdefault(config_id, [])

        for entry in entries:
            judge_model_id = entry["judge_model_id"]
            run_index = entry["run_index"]
            judge_run_id = entry["judge_run_id"]
            # The orchestrator stashed the fully-resolved construction
            # kwargs at trigger time (`_resolve_judge` chain, temperature
            # clamp, seed perturbation). Sub-tasks just unpack them; we
            # never recompute or re-resolve here so a divergence between
            # orchestrator + sub-task param logic is impossible.
            construct_kwargs = entry.get("judge_evaluator_kwargs") or {}

            try:
                evaluator = create_llm_judge_for_user(
                    db=db,
                    user_id=triggered_by_user_id,
                    organization_id=organization_id,
                    **construct_kwargs,
                )
            except Exception as init_err:
                logger.warning(
                    f"Sub-task: failed to init judge {judge_model_id} run {run_index} "
                    f"for config {config_id}: {init_err}"
                )
                evaluator = None

            judge_runs_by_config[config_id].append({
                "judge_model_id": judge_model_id,
                "run_index": run_index,
                "judge_run_id": judge_run_id,
                "evaluator": evaluator,
            })
            if evaluator is not None and config_id not in llm_judge_evaluators:
                llm_judge_evaluators[config_id] = evaluator

    return judge_runs_by_config, llm_judge_evaluators


def _build_sample_evaluator_for_cell(
    evaluation_id: str,
    configs_for_cell: List[Dict[str, Any]],
):
    """Per-sub-task SampleEvaluator construction.

    Lifted from the orchestrator's `field_configs` / `metric_parameters`
    build at `tasks.py` ~lines 2796-2812. Each sub-task builds its own
    instance, but the underlying transformer model caches in
    `sample_evaluator.py` are module-level, so only the first sub-task
    per worker process actually loads BERTScore/MoverScore/etc. weights.
    """
    from ml_evaluation.sample_evaluator import SampleEvaluator

    field_configs: Dict[str, Dict[str, str]] = {}
    metric_parameters: Dict[str, Dict[str, Any]] = {}
    for config in configs_for_cell:
        config_id = config.get("id", "unknown")
        metric = config.get("metric", "")
        params = config.get("metric_parameters", {})
        for pred_field in config.get("prediction_fields", []):
            for ref_field in config.get("reference_fields", []):
                field_key = f"{config_id}|{pred_field}|{ref_field}"
                field_configs[field_key] = {"type": "text"}
                if params:
                    metric_parameters[field_key] = {metric: params}
    return SampleEvaluator(evaluation_id, field_configs, metric_parameters)


# 7-day TTL covers even pathologically slow evals (concurrency=1 with
# 90s LLM judge timeouts compounding); a 1-day TTL would expire mid-run
# and let a poison cell reset to "first attempt" exactly when it should
# be bailed.
_CELL_ATTEMPT_TTL_SECS = 7 * 86400
_CELL_ATTEMPT_LIMIT = 3

# Whitelist of failure-reason buckets the classifier can emit. Anything
# off this list lands in `"other"` so a misbehaving LLM SDK emitting
# one new exception class per call can't grow `failures_by_reason`
# unboundedly inside the parent's JSON column.
_FAILURE_REASON_BUCKETS = frozenset({
    "rate_limit",
    "timeout",
    "content_policy",
    "quota_exceeded",
    "poison_cell_max_attempts",
    "other",
})


def _record_cell_attempt(evaluation_id: str, cell_key: str) -> int:
    """Per-cell attempt counter in Redis, used as a poison-cell guard.

    With `acks_late=True` + `reject_on_worker_lost=True` on the cell
    sub-tasks, a cell that deterministically crashes the worker (e.g.
    deterministic OOM on a 50KB generation with all embedding metrics)
    would be redelivered indefinitely — `max_retries` only counts
    explicit `self.retry()` calls, not broker-level redeliveries. This
    counter caps that loop: after `_CELL_ATTEMPT_LIMIT` redeliveries
    the sub-task records the failure reason and short-circuits, the
    chord still completes, and the parent run finalizes without
    burning unbounded LLM/judge quota.

    Falls back to "first attempt" on Redis error rather than blocking
    the eval; a Redis outage shouldn't fail-open into burning quota
    long-term, but during the outage we'd rather process normally.
    """
    try:
        client = redis.from_url(app.conf.broker_url)
        key = f"benger:cell_attempts:{evaluation_id}:{cell_key}"
        n = client.incr(key)
        client.expire(key, _CELL_ATTEMPT_TTL_SECS)
        return int(n)
    except Exception as ex:
        logger.warning(f"_record_cell_attempt redis error: {ex}; treating as first attempt")
        return 1


def _record_cell_failure_reason(db, evaluation_id: str, reason: str) -> None:
    """Increment `eval_metadata.failures_by_reason[reason]` so the UI
    can surface *why* cells silently failed (rate-limit, judge timeout,
    poison cell, etc.) instead of just `samples_failed=N` with no
    breakdown. Uses `jsonb_set(... , create_missing=true)` so the
    nested object is created on first failure of any kind.

    Skips entirely when the parent is already terminal, mirroring the
    `_bump_evaluation_counters` guard."""
    from sqlalchemy import text as _text

    db.execute(
        _text(
            """
            UPDATE evaluation_runs
               SET eval_metadata = (
                 jsonb_set(
                   COALESCE(eval_metadata::jsonb, '{}'::jsonb),
                   ARRAY['failures_by_reason', :reason],
                   to_jsonb(
                     COALESCE(
                       (eval_metadata::jsonb->'failures_by_reason'->>:reason)::int,
                       0
                     ) + 1
                   ),
                   true
                 )
               )::json
             WHERE id = :evaluation_id
               AND status NOT IN ('completed', 'failed', 'cancelled')
            """
        ),
        {"evaluation_id": evaluation_id, "reason": reason},
    )


def _classify_cell_failure(exc: BaseException) -> str:
    """Bucket a cell exception into one of `_FAILURE_REASON_BUCKETS`.

    Whitelist-only — unknown exception types map to `"other"` rather
    than leak their class name into `eval_metadata.failures_by_reason`,
    which would let a misbehaving SDK grow the JSON object unboundedly.

    Exception-name match is anchored on substring (`endswith` /
    suffix) so `EnumerateError` doesn't false-positive into
    `rate_limit` just because "rate" appears inside "enumerate".
    """
    cls_name = type(exc).__name__
    cls_lower = cls_name.lower()
    msg = str(exc).lower()
    # Known LLM-provider error class names typically end with the
    # canonical suffix (RateLimitError, TimeoutError, ContentPolicyViolationError).
    if (
        cls_lower.endswith("ratelimiterror")
        or cls_lower.endswith("ratelimit")
        or "rate limit" in msg
        or "rate_limit" in msg
        or "429" in msg
    ):
        return "rate_limit"
    if cls_lower.endswith("timeouterror") or cls_lower.endswith("timeout"):
        return "timeout"
    if "content" in msg and ("policy" in msg or "filter" in msg):
        return "content_policy"
    if "quota" in msg and ("exceeded" in msg or "limit" in msg):
        return "quota_exceeded"
    return "other"


def _bulk_upsert_task_evaluations(
    db, rows: List[Dict[str, Any]]
) -> Tuple[int, int, int]:
    """Insert TaskEvaluation rows with `ON CONFLICT DO NOTHING` against
    the partial unique index `uq_task_evaluations_cell` from migration 048.

    Returns `(rows_actually_inserted, passed_count, failed_count)` —
    counts derived from `RETURNING passed` so the caller can bump parent
    counters by the *real* number of rows that landed, not by the number
    requested. On a Celery message redelivery, all rows hit conflict and
    `(0, 0, 0)` is returned: the redelivered task contributes nothing to
    `samples_evaluated` / `samples_passed` / `samples_failed`, eliminating
    the double-bump race that an unconditional `samples_evaluated += N`
    would have on retry.

    SQLAlchemy's bare `ON CONFLICT DO NOTHING` (no `index_elements`)
    catches any unique-constraint violation. The only partial unique
    index on this table is `uq_task_evaluations_cell` (migration 048);
    UUID PKs are generated fresh per insert so PK collisions are
    statistically impossible. If a future migration adds another unique
    index here, tighten this to `index_where=` to pin the conflict
    target.
    """
    if not rows:
        return (0, 0, 0)
    from collections import defaultdict
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from models import TaskEvaluation

    # The cell sub-task's `sample_results` mixes rows from
    # `SampleEvaluator.evaluate_sample()` (which return full payloads
    # incl. `confidence_score`/`processing_time_ms`) with hand-built
    # error/judge dicts that omit those keys. Two Postgres failure
    # modes if we pass mixed shapes to one multi-row INSERT:
    #
    #   1. SQLAlchemy uses the FIRST row's key set as the column
    #      list and rejects later rows that drop a column with:
    #        "INSERT value for column X is explicitly rendered as a
    #         bound parameter in the VALUES clause; a Python-side
    #         value or SQL expression is required"
    #
    #   2. If we union-fill missing keys with None to satisfy (1),
    #      we override Postgres' server defaults for NOT NULL columns
    #      like `truncated` (server_default=false) and `refusal`
    #      (server_default=false). The explicit NULL fails the
    #      NOT NULL constraint.
    #
    # Fix: group rows by their column keyset, then one multi-row
    # INSERT per group. Each group has a consistent column list,
    # server defaults still apply to columns NO row in the group
    # provides, and `ON CONFLICT DO NOTHING` + `RETURNING passed`
    # work per-group exactly as before.
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(sorted(r.keys()))].append(r)

    n_inserted = n_passed = 0
    for _, group_rows in groups.items():
        stmt = (
            pg_insert(TaskEvaluation.__table__)
            .values(group_rows)
            .on_conflict_do_nothing()
            .returning(TaskEvaluation.__table__.c.passed)
        )
        result = db.execute(stmt)
        returned = result.fetchall()
        n_inserted += len(returned)
        n_passed += sum(1 for r in returned if r.passed)
    n_failed = n_inserted - n_passed
    return (n_inserted, n_passed, n_failed)


def _bump_evaluation_counters(
    db,
    *,
    evaluation_id: str,
    samples_evaluated: int,
    samples_passed: int,
    samples_failed: int,
) -> None:
    """Atomic SQL UPDATE that bumps the parent EvaluationRun's counters.

    Postgres serializes row-level UPDATEs on `id = :evaluation_id`, so
    concurrent sub-task bumps don't lose updates. `samples_passed` and
    `samples_failed` live inside the `eval_metadata` blob; bump them
    with `jsonb_set` + `coalesce` so a missing key starts from 0. The
    column is typed `json` (legacy), and Postgres 18 with FIPS-enforced
    OpenSSL refuses implicit `json`↔`jsonb` coercion — so cast
    explicitly: `eval_metadata::jsonb` for the read side, then
    `(... )::json` to write back.
    """
    from sqlalchemy import text as _text

    if samples_evaluated == 0 and samples_passed == 0 and samples_failed == 0:
        return
    # The `status NOT IN ('completed','failed','cancelled')` filter is
    # the TOCTOU guard for finalize: once the chord callback marks the
    # parent terminal, any late sub-task bump (e.g. from a Celery
    # message redelivery after the chord backend's barrier released)
    # becomes a no-op (rowcount=0) instead of clobbering the finalized
    # counters or resurrecting `eval_metadata`. Also covers the
    # admin-cancels-mid-run case — once status='cancelled' lands, no
    # further per-cell work mutates the parent row.
    db.execute(
        _text(
            """
            UPDATE evaluation_runs
               SET samples_evaluated = COALESCE(samples_evaluated, 0) + :n,
                   eval_metadata = (
                       jsonb_set(
                           jsonb_set(
                               COALESCE(eval_metadata::jsonb, '{}'::jsonb),
                               '{samples_passed}',
                               to_jsonb(COALESCE((eval_metadata->>'samples_passed')::int, 0) + :p)
                           ),
                           '{samples_failed}',
                           to_jsonb(COALESCE((eval_metadata->>'samples_failed')::int, 0) + :f)
                       )
                   )::json,
                   has_sample_results = true
             WHERE id = :evaluation_id
               AND status NOT IN ('completed', 'failed', 'cancelled')
            """
        ),
        {
            "n": samples_evaluated,
            "p": samples_passed,
            "f": samples_failed,
            "evaluation_id": evaluation_id,
        },
    )


@app.task(
    name="tasks.evaluate_generation_cell",
    bind=True,
    max_retries=2,
    acks_late=True,
    reject_on_worker_lost=True,
)
def evaluate_generation_cell(
    self,
    evaluation_id: str,
    task_id: str,
    generation_id: str,
    project_id: str,
    configs_for_cell: List[Dict[str, Any]],
    judge_run_ids_by_config: Dict[str, List[Dict[str, Any]]],
    default_judge_run_id: str,
    organization_id: Optional[str],
    triggered_by_user_id: str,
    label_config_version: Optional[str] = None,
    already_evaluated_field_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Per-(task, generation) sub-task dispatched by the eval orchestrator.

    Loads the generation, task (and ground-truth annotation when needed),
    reconstructs its own LLM judge evaluators per process, runs all
    `configs_for_cell` × field_pairs × judges, and writes the resulting
    TaskEvaluation rows via `ON CONFLICT DO NOTHING` so retries are
    idempotent. At the end, atomically bumps the parent EvaluationRun's
    `samples_evaluated`/`samples_passed`/`samples_failed` counters.

    Returns a small breadcrumb dict for the chord header; the finalizer
    doesn't consume the return value — it reads from the DB.
    """
    import uuid as _gen_uuid
    from datetime import datetime as _dt

    db = SessionLocal()
    try:
        from models import EvaluationRun, Generation, TaskEvaluation
        from project_models import Annotation, Task

        # Parent-status short-circuit. The legacy bundled task checked
        # `EvaluationRun.status` at the top of each iteration and bailed
        # if the user/admin cancelled mid-run; with chord fan-out, the
        # ~6940 cells are already in-flight when cancel happens, so each
        # sub-task must re-check itself or the cancellation does nothing
        # but mark the parent terminal. Avoid burning LLM quota on
        # cancelled work.
        parent_status = db.query(EvaluationRun.status).filter(
            EvaluationRun.id == evaluation_id
        ).scalar()
        if parent_status in ("cancelled", "failed", "completed"):
            return {"status": "skipped", "reason": f"parent_{parent_status}",
                    "evaluation_id": evaluation_id, "generation_id": generation_id}

        # Poison-cell guard: cap broker-level redeliveries via Redis
        # counter so a deterministic-OOM cell doesn't loop forever.
        attempts = _record_cell_attempt(evaluation_id, f"gen:{generation_id}")
        if attempts > _CELL_ATTEMPT_LIMIT:
            logger.error(
                f"evaluate_generation_cell: poison cell — gen {generation_id} "
                f"hit attempt #{attempts} for eval {evaluation_id}; bailing"
            )
            _record_cell_failure_reason(db, evaluation_id, "poison_cell_max_attempts")
            _bump_evaluation_counters(
                db, evaluation_id=evaluation_id,
                samples_evaluated=0, samples_passed=0, samples_failed=1,
            )
            db.commit()
            return {"status": "poisoned", "evaluation_id": evaluation_id,
                    "generation_id": generation_id, "attempts": attempts}

        gen = db.query(Generation).filter(Generation.id == generation_id).first()
        if not gen:
            logger.warning(
                f"evaluate_generation_cell: generation {generation_id} not found; "
                f"skipping (eval {evaluation_id})"
            )
            return {"status": "skipped", "reason": "generation_not_found",
                    "evaluation_id": evaluation_id, "generation_id": generation_id}
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning(
                f"evaluate_generation_cell: task {task_id} not found; skipping"
            )
            return {"status": "skipped", "reason": "task_not_found",
                    "evaluation_id": evaluation_id, "task_id": task_id}

        uses_annotation_fields = any(
            any(not ref.startswith("task.") for ref in c.get("reference_fields", []))
            for c in configs_for_cell
        )
        ground_truth_annotation = None
        if uses_annotation_fields:
            ann = (
                db.query(Annotation)
                .filter(Annotation.task_id == task_id, Annotation.was_cancelled == False)  # noqa: E712
                .first()
            )
            ground_truth_annotation = ann

        # Reconstruct evaluators + sample_evaluator scoped to this cell's configs.
        judge_runs_by_config, llm_judge_evaluators = _reconstruct_judge_evaluators_for_cell(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id,
            db=db,
        )
        sample_evaluator = _build_sample_evaluator_for_cell(evaluation_id, configs_for_cell)

        # Pre-normalize the orchestrator-supplied "already done" set so the
        # per-field-pair skip check below is a cheap set membership lookup
        # instead of re-normalizing each iteration. Skipping here avoids the
        # wasted LLM-judge call that would otherwise happen (the ON CONFLICT
        # DO NOTHING insert would drop the row, but the LLM call already
        # happened — burning quota). Mirror of the legacy skip at
        # ex-`tasks.py:2906-2909`.
        _already_done_normalized = {
            _normalize_field_key(fk, is_annotation=False)
            for fk in (already_evaluated_field_keys or [])
        }

        # Local accumulators (returned to caller via counter bump at end).
        sample_results: List[Dict[str, Any]] = []
        local_samples_evaluated = 0
        local_samples_passed = 0
        local_samples_failed = 0

        # Inner loop — lifted from orchestrator's per-generation block at
        # ex-`tasks.py` ~lines 2882-3355. Logic preserved as-is except for:
        #   * `evaluation_id` is a closure capture (not orchestrator-local)
        #   * `evaluation.samples_evaluated = ...` per-batch commits removed
        #     (counter bump happens atomically at end via _bump_evaluation_counters)
        #   * Sample rows are accumulated and bulk-upserted at end
        for config in configs_for_cell:
            config_id = config.get("id", "unknown")
            metric = config.get("metric", "")
            prediction_fields = config.get("prediction_fields", [])
            reference_fields = config.get("reference_fields", [])

            if metric.startswith("korrektur_"):
                continue

            for pred_field in prediction_fields:
                if pred_field.startswith("human:") or pred_field == "__all_human__":
                    continue

                for ref_field in reference_fields:
                    field_key = f"{config_id}|{pred_field}|{ref_field}"

                    # Per-field-pair skip when this cell already has a row
                    # for this (config, pred, ref). Lifted from legacy
                    # ex-`tasks.py:2906-2909`. Without this, partial-cell
                    # retries would re-call the LLM judge for already-done
                    # field_keys (ON CONFLICT only stops the INSERT, not
                    # the upstream LLM call).
                    if _normalize_field_key(field_key, is_annotation=False) in _already_done_normalized:
                        continue

                    # Ground truth extraction.
                    if ref_field.startswith("task."):
                        data_field = ref_field[5:]
                        ground_truth = task.data.get(data_field) if task.data else None
                    elif ground_truth_annotation:
                        ground_truth = _extract_field_value_from_annotation(
                            ground_truth_annotation.result or [], ref_field
                        )
                        if ground_truth is None and task.data and ref_field in task.data:
                            ground_truth = task.data.get(ref_field)
                    else:
                        ground_truth = task.data.get(ref_field) if task.data else None
                    if ground_truth is None:
                        logger.warning(
                            f"Evaluation skip: reference field '{ref_field}' not found "
                            f"for task {task.id} (config {config_id})"
                        )
                        continue

                    # Prediction extraction.
                    base_field = pred_field
                    if pred_field.startswith("model:"):
                        base_field = pred_field[6:]
                    if pred_field == "__all_model__":
                        prediction = gen.response_content
                    else:
                        prediction = _extract_field_value_from_parsed_annotation(
                            gen.parsed_annotation, base_field
                        )
                        if prediction is None and gen.response_content:
                            prediction = gen.response_content
                    if prediction is None:
                        logger.warning(
                            f"Evaluation skip: prediction field '{pred_field}' not found "
                            f"for task {task.id}, model {gen.model_id} (config {config_id})"
                        )
                        continue

                    allow_unparsed = pred_field == "__all_model__"
                    try:
                        # Terminal-error row when an llm_judge_* config has no init'd evaluator.
                        if metric.startswith("llm_judge_") and config_id not in llm_judge_evaluators:
                            sample_results.append({
                                "id": str(_gen_uuid.uuid4()),
                                "evaluation_id": evaluation_id,
                                "judge_run_id": default_judge_run_id,
                                "task_id": task.id,
                                "generation_id": gen.id,
                                "field_name": field_key,
                                "evaluation_config_id": config_id,
                                "answer_type": "text",
                                "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                "prediction": str(prediction)[:1000] if prediction else "",
                                "metrics": {
                                    metric: {
                                        "value": None,
                                        "method": metric,
                                        "error": (
                                            "LLM judge evaluator not initialized for config "
                                            f"{config_id} — likely missing API key for the "
                                            "triggering user/org. Run skipped this metric."
                                        ),
                                        "details": {},
                                    },
                                },
                                "passed": False,
                                "error_message": (
                                    f"LLM judge evaluator not initialized for config {config_id}"
                                ),
                            })
                            local_samples_evaluated += 1
                            local_samples_failed += 1
                            continue

                        if metric.startswith("llm_judge_") and config_id in llm_judge_evaluators:
                            # ── Multi-judge / multi-run fan-out (intra-cell) ──
                            per_judge_results: List[Dict[str, Any]] = []
                            context = (
                                _get_insensitive(task.data, "text")
                                or _get_insensitive(task.data, "input")
                                or _get_insensitive(task.data, "sachverhalt")
                                or ""
                            )
                            eval_ground_truth = str(ground_truth) if ground_truth else ""
                            if metric == "llm_judge_falloesung" and task.data:
                                muster = (
                                    _get_insensitive(task.data, "musterloesung")
                                    or _get_insensitive(task.data, "musterlösung")
                                )
                                if muster:
                                    eval_ground_truth = str(muster)

                            criterion = metric.replace("llm_judge_", "")
                            if criterion in ("custom", "overall"):
                                criterion = "correctness"

                            for jr_entry in judge_runs_by_config.get(config_id, []):
                                jr_evaluator = jr_entry["evaluator"]
                                jr_id = jr_entry["judge_run_id"]
                                jr_judge_model = jr_entry["judge_model_id"]
                                jr_run_index = jr_entry["run_index"]

                                if jr_evaluator is None:
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": {
                                            metric: {
                                                "value": None,
                                                "method": metric,
                                                "error": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                                "details": {},
                                            },
                                        },
                                        "passed": False,
                                        "error_message": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                    })
                                    continue

                                multidim_mode = (
                                    metric != "llm_judge_falloesung"
                                    and getattr(jr_evaluator, "is_multidim_mode", lambda: False)()
                                )

                                if metric == "llm_judge_falloesung":
                                    try:
                                        from benger_extended.workers import (
                                            get_falloesung_bulk_compute_fn,
                                        )
                                    except ImportError as exc:
                                        raise RuntimeError(
                                            "Metric 'llm_judge_falloesung' requires the "
                                            "benger_extended package; it is not installed."
                                        ) from exc
                                    falloesung_bulk_fn = get_falloesung_bulk_compute_fn()
                                    sachverhalt = (
                                        _get_insensitive(task.data, "sachverhalt")
                                        if task.data
                                        else ""
                                    )
                                    result = falloesung_bulk_fn(
                                        ai_service=jr_evaluator.ai_service,
                                        judge_model=jr_evaluator.judge_model,
                                        temperature=jr_evaluator.temperature,
                                        max_tokens=jr_evaluator.max_tokens,
                                        sachverhalt=str(sachverhalt) if sachverhalt else "",
                                        musterloesung=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        thinking_budget=getattr(jr_evaluator, "thinking_budget", None),
                                        reasoning_effort=getattr(jr_evaluator, "reasoning_effort", None),
                                    )
                                elif multidim_mode:
                                    # Flatten the model's per-field output
                                    # (parsed_annotation is in label-studio
                                    # shape) so the user's prompt can
                                    # reference {{kurzantwort}} /
                                    # {{begruendung}} directly without
                                    # field_mappings.
                                    from annotation_utils import extract_all_field_values
                                    gen_field_outputs = (
                                        extract_all_field_values(gen.parsed_annotation)
                                        if getattr(gen, "parsed_annotation", None)
                                        else {}
                                    )
                                    result = jr_evaluator._evaluate_multidim_single_call(
                                        context=context,
                                        ground_truth=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        task_data=task.data,
                                        field_outputs=gen_field_outputs,
                                    )
                                else:
                                    result = jr_evaluator._evaluate_single_criterion(
                                        context=context,
                                        ground_truth=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        criterion=criterion,
                                        task_data=task.data,
                                    )

                                judge_prompts = (
                                    result.pop("_judge_prompts_used", None)
                                    if result
                                    else None
                                )

                                if multidim_mode:
                                    error_msg = (
                                        result.get("error_message")
                                        if result and result.get("error")
                                        else None
                                    )
                                    metrics_dict, normalized = _build_multidim_judge_row_metrics(
                                        result, metric, error_msg,
                                    )
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": metrics_dict,
                                        "passed": (normalized or 0.0) >= 0.5,
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **_llm_judge_columns_from_result(result),
                                    })
                                    continue

                                raw_score = result.get("score") if result is not None else None
                                error_msg = None
                                if raw_score is not None:
                                    if jr_evaluator.score_scale == "0-1":
                                        score = raw_score
                                    elif jr_evaluator.score_scale == "0-100":
                                        score = raw_score / 100.0
                                    else:
                                        score = (raw_score - 1) / 4
                                else:
                                    score = None
                                    error_msg = (
                                        (result.get("error_message") if result else None)
                                        or "LLM judge evaluation failed"
                                    )
                                    logger.warning(
                                        f"LLM judge {jr_judge_model} run {jr_run_index} returned None "
                                        f"for task {task.id}, field {field_key}"
                                    )

                                if metric == "llm_judge_falloesung":
                                    from benger_extended.workers.falloesung_tasks import (
                                        build_falloesung_row_dict,
                                    )
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "annotation_id": None,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **build_falloesung_row_dict(result=result, error_message=error_msg),
                                    })
                                else:
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": {
                                            metric: score,
                                            "raw_score": raw_score,
                                            f"{metric}_response": result,
                                            **(
                                                {f"{metric}_grade_points": result["grade_points"]}
                                                if result and result.get("grade_points") is not None
                                                else {}
                                            ),
                                            **(
                                                {f"{metric}_passed": 1.0 if result["passed"] else 0.0}
                                                if result and "passed" in result
                                                else {}
                                            ),
                                        },
                                        "passed": (
                                            result.get("passed", score > 0.5)
                                            if result and "passed" in result
                                            else (score > 0.5 if score is not None else False)
                                        ),
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **_llm_judge_columns_from_result(result),
                                    })

                            for sr in per_judge_results:
                                sample_results.append(sr)
                                local_samples_evaluated += 1
                                if sr["passed"]:
                                    local_samples_passed += 1
                                else:
                                    local_samples_failed += 1
                            continue

                        # Deterministic metric (BLEU/ROUGE/METEOR/etc.) — SampleEvaluator path.
                        sample_result = sample_evaluator.evaluate_sample(
                            task_id=task.id,
                            field_name=field_key,
                            ground_truth=ground_truth,
                            prediction=prediction,
                            metrics_to_compute=[metric],
                            generation_id=gen.id,
                            parse_status=gen.parse_status,
                            allow_unparsed=allow_unparsed,
                        )
                        if isinstance(sample_result, dict):
                            sample_result["judge_run_id"] = default_judge_run_id
                            # Issue #111 / migration 057: discrete config-id carrier.
                            sample_result["evaluation_config_id"] = config_id

                        sample_results.append(sample_result)
                        local_samples_evaluated += 1
                        if sample_result.get("passed"):
                            local_samples_passed += 1
                        else:
                            local_samples_failed += 1

                    except ValueError as e:
                        logger.warning(f"Skipping sample: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Error evaluating sample: {e}")
                        sample_results.append({
                            "id": str(_gen_uuid.uuid4()),
                            "evaluation_id": evaluation_id,
                            "judge_run_id": default_judge_run_id,
                            "task_id": task.id,
                            "generation_id": gen.id,
                            "field_name": field_key,
                            "evaluation_config_id": config_id,
                            "answer_type": "text",
                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                            "prediction": str(prediction)[:1000] if prediction else "",
                            "metrics": {},
                            "passed": False,
                            "error_message": str(e),
                        })
                        local_samples_evaluated += 1
                        local_samples_failed += 1

        # Bulk upsert + atomic counter bump. One commit per sub-task.
        # Bump by the *actually inserted* row count (from RETURNING),
        # not by the locally-tallied counts. On Celery message
        # redelivery, all rows conflict and `n_inserted == 0`, so the
        # redelivered task contributes nothing to the parent counters
        # — defense against the `acks_late=True` double-bump path.
        n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations(db, sample_results)
        _bump_evaluation_counters(
            db,
            evaluation_id=evaluation_id,
            samples_evaluated=n_inserted,
            samples_passed=n_passed,
            samples_failed=n_failed,
        )
        db.commit()
        # Tell the API WS handler this cell landed so it can push a
        # `tick` to connected EvaluationResults clients. The handler
        # subscribes to `evaluation:progress:{project_id}` and re-fetches
        # the task-model view on each tick.
        if n_inserted > 0:
            _publish_progress(
                f"evaluation:progress:{project_id}",
                {
                    "type": "cell_complete",
                    "evaluation_id": evaluation_id,
                    "task_id": task_id,
                    "generation_id": generation_id,
                    "samples_added": n_inserted,
                },
            )
        return {
            "status": "ok",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "generation_id": generation_id,
            "samples_added": n_inserted,
            "samples_passed": n_passed,
            "samples_failed": n_failed,
        }
    except Exception as e:
        logger.error(
            f"evaluate_generation_cell failed (eval {evaluation_id}, gen {generation_id}): {e}",
            exc_info=True,
        )
        db.rollback()
        # Don't propagate — the chord finalizer must still fire. Best-effort
        # increment of `samples_failed` and record the failure reason so
        # the UI can surface *why* the cell silently produced no row.
        try:
            _record_cell_failure_reason(db, evaluation_id, _classify_cell_failure(e))
            _bump_evaluation_counters(
                db,
                evaluation_id=evaluation_id,
                samples_evaluated=0,
                samples_passed=0,
                samples_failed=1,
            )
            db.commit()
        except Exception as bump_err:
            logger.error(f"Failed to bump failed counter: {bump_err}")
        return {
            "status": "error",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "generation_id": generation_id,
            "error": str(e),
        }
    finally:
        db.close()


@app.task(
    name="tasks.evaluate_annotation_cell",
    bind=True,
    max_retries=2,
    acks_late=True,
    reject_on_worker_lost=True,
)
def evaluate_annotation_cell(
    self,
    evaluation_id: str,
    task_id: str,
    annotation_id: str,
    project_id: str,
    configs_for_cell: List[Dict[str, Any]],
    judge_run_ids_by_config: Dict[str, List[Dict[str, Any]]],
    default_judge_run_id: str,
    organization_id: Optional[str],
    triggered_by_user_id: str,
    already_evaluated_field_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Per-(task, annotation) sub-task dispatched by the eval orchestrator.

    Mirror of `evaluate_generation_cell` for the human-annotation
    evaluation path (configs whose `prediction_fields` contain
    `human:<field>` or `__all_human__`). Same structure: load + reconstruct
    + run inner block + bulk upsert + atomic counter bump.
    """
    import uuid as _ann_uuid
    from datetime import datetime as _dt

    db = SessionLocal()
    try:
        from models import EvaluationRun, TaskEvaluation
        from project_models import Annotation, Task
        from annotation_utils import extract_all_field_values as _extract_all_fields
        from eval_field_classification import classify_pred_fields

        # Parent-status short-circuit — mirror of evaluate_generation_cell.
        parent_status = db.query(EvaluationRun.status).filter(
            EvaluationRun.id == evaluation_id
        ).scalar()
        if parent_status in ("cancelled", "failed", "completed"):
            return {"status": "skipped", "reason": f"parent_{parent_status}",
                    "evaluation_id": evaluation_id, "annotation_id": annotation_id}

        # Poison-cell guard — mirror of evaluate_generation_cell.
        attempts = _record_cell_attempt(evaluation_id, f"ann:{annotation_id}")
        if attempts > _CELL_ATTEMPT_LIMIT:
            logger.error(
                f"evaluate_annotation_cell: poison cell — ann {annotation_id} "
                f"hit attempt #{attempts} for eval {evaluation_id}; bailing"
            )
            _record_cell_failure_reason(db, evaluation_id, "poison_cell_max_attempts")
            _bump_evaluation_counters(
                db, evaluation_id=evaluation_id,
                samples_evaluated=0, samples_passed=0, samples_failed=1,
            )
            db.commit()
            return {"status": "poisoned", "evaluation_id": evaluation_id,
                    "annotation_id": annotation_id, "attempts": attempts}

        annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
        if not annotation:
            logger.warning(
                f"evaluate_annotation_cell: annotation {annotation_id} not found; skipping"
            )
            return {"status": "skipped", "reason": "annotation_not_found",
                    "evaluation_id": evaluation_id, "annotation_id": annotation_id}
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning(f"evaluate_annotation_cell: task {task_id} not found; skipping")
            return {"status": "skipped", "reason": "task_not_found",
                    "evaluation_id": evaluation_id, "task_id": task_id}

        judge_runs_by_config, llm_judge_evaluators = _reconstruct_judge_evaluators_for_cell(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id,
            db=db,
        )
        sample_evaluator = _build_sample_evaluator_for_cell(evaluation_id, configs_for_cell)

        # Pre-normalize per-cell already-done set (annotation-side mirror of
        # the generation-side skip). Same rationale — avoid the wasted
        # LLM-judge call on partial-cell retries.
        _already_done_normalized = {
            _normalize_field_key(fk, is_annotation=True)
            for fk in (already_evaluated_field_keys or [])
        }

        sample_results: List[Dict[str, Any]] = []
        local_samples_evaluated = 0
        local_samples_passed = 0
        local_samples_failed = 0
        gt_cache: Dict[tuple, Any] = {}

        for config in configs_for_cell:
            config_id = config.get("id", "unknown")
            metric = config.get("metric", "")
            prediction_fields = config.get("prediction_fields", [])
            reference_fields = config.get("reference_fields", [])

            if metric.startswith("korrektur_"):
                continue

            human_fields_raw, _llm_fields = classify_pred_fields(metric, prediction_fields)
            human_pred_fields = []
            for pf in human_fields_raw:
                if pf == "__all_human__":
                    human_pred_fields.append(("__all_human__", "__all_human__"))
                elif pf.startswith("human:"):
                    human_pred_fields.append((pf, pf[6:]))
                else:
                    human_pred_fields.append((f"human:{pf}", pf))

            if not human_pred_fields:
                continue

            for pred_field_prefixed, base_field in human_pred_fields:
                # Extract prediction from THIS annotation.
                if base_field == "__all_human__":
                    all_values = _extract_all_fields(annotation.result or [])
                    field_predictions = [
                        (f"human:{fn}", v) for fn, v in all_values.items()
                        if isinstance(v, str)
                    ]
                else:
                    value = _extract_field_value_from_annotation(
                        annotation.result or [], base_field
                    )
                    field_predictions = [(pred_field_prefixed, value)] if value else []

                for actual_pred_field, prediction in field_predictions:
                    for ref_field in reference_fields:
                        field_key = f"{config_id}|{actual_pred_field}|{ref_field}"

                        # Per-field-pair skip — mirror of legacy
                        # ex-`tasks.py:3485-3488`. Same wasted-LLM-call
                        # rationale as the gen-side sub-task.
                        if _normalize_field_key(field_key, is_annotation=True) in _already_done_normalized:
                            continue

                        gt_key = (task.id, ref_field)
                        if gt_key not in gt_cache:
                            if ref_field.startswith("task."):
                                data_field = ref_field[5:]
                                gt_cache[gt_key] = task.data.get(data_field) if task.data else None
                            else:
                                gt_cache[gt_key] = task.data.get(ref_field) if task.data else None
                        ground_truth = gt_cache[gt_key]
                        if ground_truth is None:
                            continue

                        try:
                            if metric.startswith("llm_judge_") and config_id not in llm_judge_evaluators:
                                sample_results.append({
                                    "id": str(_ann_uuid.uuid4()),
                                    "evaluation_id": evaluation_id,
                                    "judge_run_id": default_judge_run_id,
                                    "task_id": task.id,
                                    "generation_id": None,
                                    "annotation_id": annotation.id,
                                    "field_name": field_key,
                                    "evaluation_config_id": config_id,
                                    "answer_type": "text",
                                    "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                    "prediction": str(prediction)[:1000] if prediction else "",
                                    "metrics": {
                                        metric: {
                                            "value": None,
                                            "method": metric,
                                            "error": (
                                                "LLM judge evaluator not initialized for config "
                                                f"{config_id}"
                                            ),
                                            "details": {},
                                        },
                                    },
                                    "passed": False,
                                    "error_message": (
                                        f"LLM judge evaluator not initialized for config {config_id}"
                                    ),
                                })
                                local_samples_evaluated += 1
                                local_samples_failed += 1
                                continue

                            if metric.startswith("llm_judge_") and config_id in llm_judge_evaluators:
                                context = (
                                    _get_insensitive(task.data, "text")
                                    or _get_insensitive(task.data, "input")
                                    or _get_insensitive(task.data, "sachverhalt")
                                    or ""
                                ) if task.data else ""
                                eval_ground_truth = str(ground_truth) if ground_truth else ""
                                if metric == "llm_judge_falloesung" and task.data:
                                    muster = (
                                        _get_insensitive(task.data, "musterloesung")
                                        or _get_insensitive(task.data, "musterlösung")
                                    )
                                    if muster:
                                        eval_ground_truth = str(muster)
                                criterion = metric.replace("llm_judge_", "")
                                if criterion in ("custom", "overall"):
                                    criterion = "correctness"

                                per_judge_results: List[Dict[str, Any]] = []
                                for jr_entry in judge_runs_by_config.get(config_id, []):
                                    jr_evaluator = jr_entry["evaluator"]
                                    jr_id = jr_entry["judge_run_id"]
                                    jr_judge_model = jr_entry["judge_model_id"]
                                    jr_run_index = jr_entry["run_index"]

                                    if jr_evaluator is None:
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": {
                                                metric: {
                                                    "value": None,
                                                    "method": metric,
                                                    "error": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                                    "details": {},
                                                },
                                            },
                                            "passed": False,
                                            "error_message": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                        })
                                        continue

                                    multidim_mode = (
                                        metric != "llm_judge_falloesung"
                                        and getattr(jr_evaluator, "is_multidim_mode", lambda: False)()
                                    )

                                    if metric == "llm_judge_falloesung":
                                        try:
                                            from benger_extended.workers import (
                                                get_falloesung_bulk_compute_fn,
                                            )
                                        except ImportError as exc:
                                            raise RuntimeError(
                                                "Metric 'llm_judge_falloesung' requires the "
                                                "benger_extended package; it is not installed."
                                            ) from exc
                                        falloesung_bulk_fn = get_falloesung_bulk_compute_fn()
                                        sachverhalt = (
                                            _get_insensitive(task.data, "sachverhalt")
                                            if task.data
                                            else ""
                                        )
                                        result = falloesung_bulk_fn(
                                            ai_service=jr_evaluator.ai_service,
                                            judge_model=jr_evaluator.judge_model,
                                            temperature=jr_evaluator.temperature,
                                            max_tokens=jr_evaluator.max_tokens,
                                            sachverhalt=str(sachverhalt) if sachverhalt else "",
                                            musterloesung=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            thinking_budget=getattr(jr_evaluator, "thinking_budget", None),
                                            reasoning_effort=getattr(jr_evaluator, "reasoning_effort", None),
                                        )
                                    elif multidim_mode:
                                        # Same as the gen-cell side: flatten
                                        # the human annotator's per-field
                                        # outputs so the user's prompt can
                                        # reference {{kurzantwort}} /
                                        # {{begruendung}} directly.
                                        from annotation_utils import extract_all_field_values
                                        ann_field_outputs = (
                                            extract_all_field_values(annotation.result)
                                            if getattr(annotation, "result", None)
                                            else {}
                                        )
                                        result = jr_evaluator._evaluate_multidim_single_call(
                                            context=context,
                                            ground_truth=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            task_data=task.data,
                                            field_outputs=ann_field_outputs,
                                        )
                                    else:
                                        result = jr_evaluator._evaluate_single_criterion(
                                            context=context,
                                            ground_truth=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            criterion=criterion,
                                            task_data=task.data,
                                        )

                                    judge_prompts = (
                                        result.pop("_judge_prompts_used", None)
                                        if result
                                        else None
                                    )

                                    if multidim_mode:
                                        error_msg = (
                                            result.get("error_message")
                                            if result and result.get("error")
                                            else None
                                        )
                                        metrics_dict, normalized = _build_multidim_judge_row_metrics(
                                            result, metric, error_msg,
                                        )
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": metrics_dict,
                                            "passed": (normalized or 0.0) >= 0.5,
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **_llm_judge_columns_from_result(result),
                                        })
                                        continue

                                    raw_score = result.get("score") if result is not None else None
                                    error_msg = None
                                    if raw_score is not None:
                                        if jr_evaluator.score_scale == "0-1":
                                            score = raw_score
                                        elif jr_evaluator.score_scale == "0-100":
                                            score = raw_score / 100.0
                                        else:
                                            score = (raw_score - 1) / 4
                                    else:
                                        score = None
                                        error_msg = (
                                            (result.get("error_message") if result else None)
                                            or "LLM judge evaluation failed"
                                        )

                                    if metric == "llm_judge_falloesung":
                                        from benger_extended.workers.falloesung_tasks import (
                                            build_falloesung_row_dict,
                                        )
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **build_falloesung_row_dict(result=result, error_message=error_msg),
                                        })
                                    else:
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": {
                                                metric: score,
                                                "raw_score": raw_score,
                                                f"{metric}_response": result,
                                                **(
                                                    {f"{metric}_grade_points": result["grade_points"]}
                                                    if result and result.get("grade_points") is not None
                                                    else {}
                                                ),
                                                **(
                                                    {f"{metric}_passed": 1.0 if result["passed"] else 0.0}
                                                    if result and "passed" in result
                                                    else {}
                                                ),
                                            },
                                            "passed": (
                                                result.get("passed", score > 0.5)
                                                if result and "passed" in result
                                                else (score > 0.5 if score is not None else False)
                                            ),
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **_llm_judge_columns_from_result(result),
                                        })

                                for sr in per_judge_results:
                                    sample_results.append(sr)
                                    local_samples_evaluated += 1
                                    if sr["passed"]:
                                        local_samples_passed += 1
                                    else:
                                        local_samples_failed += 1
                                continue

                            # Deterministic annotation metric.
                            annotation_result = sample_evaluator.evaluate_sample(
                                task_id=task.id,
                                field_name=field_key,
                                ground_truth=ground_truth,
                                prediction=prediction,
                                metrics_to_compute=[metric],
                                annotation_id=annotation.id,
                            )
                            annotation_result["annotation_id"] = annotation.id
                            annotation_result["generation_id"] = None
                            if isinstance(annotation_result, dict):
                                annotation_result["judge_run_id"] = default_judge_run_id
                                # Issue #111 / migration 057: discrete config-id carrier.
                                annotation_result["evaluation_config_id"] = config_id

                            sample_results.append(annotation_result)
                            local_samples_evaluated += 1
                            if annotation_result.get("passed"):
                                local_samples_passed += 1
                            else:
                                local_samples_failed += 1

                        except ValueError as e:
                            logger.warning(f"Skipping annotation sample: {e}")
                            continue
                        except Exception as e:
                            logger.warning(
                                f"Annotation eval failed for annotation {annotation.id}: {e}"
                            )
                            sample_results.append({
                                "id": str(_ann_uuid.uuid4()),
                                "evaluation_id": evaluation_id,
                                "judge_run_id": default_judge_run_id,
                                "task_id": task.id,
                                "generation_id": None,
                                "annotation_id": annotation.id,
                                "field_name": field_key,
                                "evaluation_config_id": config_id,
                                "answer_type": "text",
                                "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                "prediction": str(prediction)[:1000] if prediction else "",
                                "metrics": {},
                                "passed": False,
                                "error_message": str(e),
                            })
                            local_samples_evaluated += 1
                            local_samples_failed += 1

        # Bump by RETURNING-derived counts — see gen sub-task for rationale.
        n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations(db, sample_results)
        _bump_evaluation_counters(
            db,
            evaluation_id=evaluation_id,
            samples_evaluated=n_inserted,
            samples_passed=n_passed,
            samples_failed=n_failed,
        )
        db.commit()
        # Same as the gen cell — broadcast so the API WS pushes a tick.
        if n_inserted > 0:
            _publish_progress(
                f"evaluation:progress:{project_id}",
                {
                    "type": "cell_complete",
                    "evaluation_id": evaluation_id,
                    "task_id": task_id,
                    "annotation_id": annotation_id,
                    "samples_added": n_inserted,
                },
            )
        return {
            "status": "ok",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "annotation_id": annotation_id,
            "samples_added": n_inserted,
            "samples_passed": n_passed,
            "samples_failed": n_failed,
        }
    except Exception as e:
        logger.error(
            f"evaluate_annotation_cell failed (eval {evaluation_id}, ann {annotation_id}): {e}",
            exc_info=True,
        )
        db.rollback()
        try:
            _record_cell_failure_reason(db, evaluation_id, _classify_cell_failure(e))
            _bump_evaluation_counters(
                db,
                evaluation_id=evaluation_id,
                samples_evaluated=0,
                samples_passed=0,
                samples_failed=1,
            )
            db.commit()
        except Exception as bump_err:
            logger.error(f"Failed to bump failed counter: {bump_err}")
        return {
            "status": "error",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "annotation_id": annotation_id,
            "error": str(e),
        }
    finally:
        db.close()


@app.task(
    name="tasks.finalize_evaluation_run",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def finalize_evaluation_run(
    self,
    _sub_task_results: Any,
    evaluation_id: str,
) -> Dict[str, Any]:
    """Chord callback — runs exactly once after every cell sub-task finishes.

    Aggregates per-judge_run statuses from `TaskEvaluation` row counts,
    recomputes the `metrics` dict (mean of per-cell primary values), sets
    the parent `EvaluationRun.status` (`completed` if any judge produced
    rows, `failed` otherwise), and fires the report-section update and
    user notification — both of which used to live at the end of the
    monolithic `run_evaluation`.

    Idempotent: re-entry on a terminal evaluation is a no-op (chord
    callbacks can be redelivered if the worker dies).

    The leading `_sub_task_results` positional is the Celery chord
    convention — header sub-task return values are passed as the first
    arg; we don't consume them (we read from DB).
    """
    from datetime import datetime as _dt
    from sqlalchemy import text as _text

    db = SessionLocal()
    try:
        from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

        evaluation = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id).first()
        if not evaluation:
            logger.warning(f"finalize_evaluation_run: eval {evaluation_id} not found")
            return {"status": "skipped", "reason": "evaluation_not_found"}

        if evaluation.status in ("completed", "failed", "cancelled"):
            logger.info(
                f"finalize_evaluation_run: eval {evaluation_id} already terminal "
                f"({evaluation.status}); no-op"
            )
            return {"status": "noop", "reason": "already_terminal",
                    "evaluation_id": evaluation_id, "current_status": evaluation.status}

        # Walk EvaluationJudgeRun children — lifted from ex-`tasks.py:3870-3893`.
        child_runs = db.query(EvaluationJudgeRun).filter(
            EvaluationJudgeRun.evaluation_id == evaluation_id
        ).all()
        any_child_failed = False
        any_child_completed = False
        for child in child_runs:
            # Derive each judge_run's terminal status from the rows it actually
            # produced, never from its current status field — that field can be
            # stale. A missing-only resume into the SAME EvaluationRun (the
            # supported way to continue a cancelled run) reuses the cancelled
            # attempt's judge_run, which the cancel left marked 'failed'. The
            # resume then grades every cell under that very row. An early skip on
            # status=='failed' here would strand it as failed and flip the whole
            # parent to 'failed'/'all judge_runs failed' despite a complete,
            # valid grade — which is exactly the bug that forced a manual status
            # fix. Row count is authoritative: rows>0 means it graded; rows==0
            # means it produced nothing (covers the legitimate up-front "no AI
            # service" failure, which never writes any rows).
            child_rows = db.query(TaskEvaluation).filter(
                TaskEvaluation.judge_run_id == child.id
            ).count()
            child.samples_evaluated = child_rows
            child.completed_at = _dt.now()
            if child_rows > 0:
                child.status = "completed"
                child.error_message = None
                any_child_completed = True
            else:
                child.status = "failed"
                child.error_message = child.error_message or "no rows produced"
                any_child_failed = True
        db.commit()

        # Recompute aggregate metrics from TaskEvaluation rows.
        # Replaces the orchestrator's per-iteration `aggregate_metrics`
        # accumulator; one SQL pass instead of in-memory state-sharing
        # between sub-tasks (which we deliberately avoided).
        rows = db.execute(
            _text(
                """
                SELECT field_name, metrics
                FROM task_evaluations
                WHERE evaluation_id = :eid
                """
            ),
            {"eid": evaluation_id},
        ).all()
        aggregate_metrics: Dict[str, List[float]] = {}
        for r in rows:
            field_name = r[0]
            metrics_blob = r[1] or {}
            for metric_name, metric_value in metrics_blob.items():
                # Same shape handling as the orchestrator's old aggregator:
                # llm_judge_falloesung uses nested {value, method, details}
                # whereas other metrics expose the value at the top level.
                if isinstance(metric_value, dict):
                    primary = metric_value.get("value")
                else:
                    primary = metric_value
                if primary is None or not isinstance(primary, (int, float)):
                    # Numeric sub-metrics like `_grade_points` and `_passed`
                    # are stored as their own top-level keys; pick them up
                    # if they're numeric.
                    continue
                key = f"{field_name}|{metric_name}"
                aggregate_metrics.setdefault(key, []).append(float(primary))
        final_metrics: Dict[str, float] = {}
        for k, vals in aggregate_metrics.items():
            if vals:
                final_metrics[k] = sum(vals) / len(vals)

        # Re-read parent counter (incrementally bumped by sub-tasks).
        db.refresh(evaluation)
        samples_evaluated_total = int(evaluation.samples_evaluated or 0)
        meta = evaluation.eval_metadata or {}
        samples_passed_total = int(meta.get("samples_passed", 0) or 0)
        samples_failed_total = int(meta.get("samples_failed", 0) or 0)

        # Final parent status — mirror of ex-`tasks.py:3896` policy.
        evaluation.status = "completed" if any_child_completed else "failed"
        if not any_child_completed:
            evaluation.error_message = (
                "no judge_run produced any rows"
                if not child_runs
                else "all judge_runs failed"
            )
        evaluation.completed_at = _dt.now()
        evaluation.metrics = final_metrics
        evaluation.has_sample_results = True

        # judges_by_config summary — see ex-`tasks.py:3914-3934`.
        child_status_by_id = {c.id: c for c in child_runs}
        judge_models_summary: Dict[str, List[Dict[str, Any]]] = {}
        for cid, entries in (meta.get("judge_run_ids_by_config") or {}).items():
            judge_models_summary[cid] = [
                {
                    "judge_model_id": e["judge_model_id"],
                    "run_index": e["run_index"],
                    "judge_run_id": e["judge_run_id"],
                    "status": (
                        child_status_by_id[e["judge_run_id"]].status
                        if e["judge_run_id"] in child_status_by_id
                        else None
                    ),
                    "samples_evaluated": (
                        child_status_by_id[e["judge_run_id"]].samples_evaluated
                        if e["judge_run_id"] in child_status_by_id
                        else None
                    ),
                }
                for e in entries
            ]

        evaluation.eval_metadata = {
            **(meta or {}),
            "samples_passed": samples_passed_total,
            "samples_failed": samples_failed_total,
            "pass_rate": (
                samples_passed_total / samples_evaluated_total
                if samples_evaluated_total > 0 else 0
            ),
            "any_judge_failed": any_child_failed,
            **({"judges_by_config": judge_models_summary} if judge_models_summary else {}),
        }
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(evaluation, "eval_metadata")
        db.commit()

        # Event-driven recompute removed: leaderboards refresh on a fixed
        # 12:00 + 00:00 CEST schedule (see app.conf.beat_schedule above).
        # Users see a static "updated twice daily" hint on the page so the
        # contract is explicit. Reintroduce a send_task here if a future
        # surface needs sub-12h freshness — but coalesce via the Redis lock
        # the recompute task already takes.

        # Report section update — lifted from ex-`tasks.py:3956-3958`.
        # report_service lives in /shared so both API and workers import it
        # via top-level name. The previous code hacked services/api/ onto
        # sys.path from the worker container at runtime, but the worker
        # image has no api/ sibling, so the import always failed and the
        # report's evaluation section silently never auto-refreshed.
        try:
            from report_service import update_report_evaluation_section

            update_report_evaluation_section(db, evaluation.project_id)
            logger.info(f"✅ Updated report evaluation section for project {evaluation.project_id}")
        except Exception as e:
            logger.error(f"Failed to update report evaluation section: {e}")

        # Notification — lifted from ex-`tasks.py:3970-3995`.
        try:
            triggered_by = (
                evaluation.eval_metadata.get("triggered_by")
                if evaluation.eval_metadata
                else None
            )
            if triggered_by:
                NotificationService.create_notification(
                    db=db,
                    user_ids=[triggered_by],
                    notification_type=NotificationType.EVALUATION_COMPLETED,
                    title="Evaluation Completed"
                    if evaluation.status == "completed"
                    else "Evaluation Failed",
                    message=(
                        f"Evaluation completed: {samples_evaluated_total} samples evaluated, "
                        f"pass rate {samples_passed_total/samples_evaluated_total:.1%}"
                        if evaluation.status == "completed" and samples_evaluated_total > 0
                        else f"Evaluation {evaluation.status}"
                    ),
                    data={
                        "project_id": evaluation.project_id,
                        "evaluation_id": evaluation_id,
                        "samples_evaluated": samples_evaluated_total,
                        "pass_rate": (
                            samples_passed_total / samples_evaluated_total
                            if samples_evaluated_total > 0 else 0
                        ),
                    },
                )
        except Exception as notif_err:
            logger.error(f"Failed to create completion notification: {notif_err}")

        logger.info(
            f"✅ finalize_evaluation_run: eval {evaluation_id} → {evaluation.status} "
            f"({samples_evaluated_total} samples, "
            f"{samples_passed_total/samples_evaluated_total:.2%} pass rate)"
            if samples_evaluated_total > 0
            else f"✅ finalize_evaluation_run: eval {evaluation_id} → {evaluation.status} (0 samples)"
        )

        return {
            "status": "success",
            "evaluation_id": evaluation_id,
            "final_status": evaluation.status,
            "samples_evaluated": samples_evaluated_total,
            "samples_passed": samples_passed_total,
            "samples_failed": samples_failed_total,
            "metrics": final_metrics,
        }
    except Exception as e:
        logger.error(f"finalize_evaluation_run failed for {evaluation_id}: {e}", exc_info=True)
        # Last-ditch: mark eval failed so it doesn't sit in 'running' forever.
        try:
            db.rollback()
            from models import EvaluationRun
            ev = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id).first()
            if ev and ev.status not in ("completed", "failed", "cancelled"):
                from datetime import datetime as _dt2
                ev.status = "failed"
                ev.error_message = f"finalize_evaluation_run crashed: {str(e)[:500]}"
                ev.completed_at = _dt2.now()
                db.commit()
        except Exception:
            pass
        return {"status": "error", "evaluation_id": evaluation_id, "error": str(e)}
    finally:
        db.close()


@app.task(name="tasks.recompute_aggregates", bind=True)
def recompute_aggregates(self):
    """Refresh the precomputed leaderboard + project-summary tables.

    Runs every 12h via beat (see `app.conf.beat_schedule` above) and can be
    triggered ad-hoc. Coalesces concurrent runs with a Redis lock so a burst
    of triggers collapses to a single execution.

    The heavy SQL lives in `services/api/services/aggregate_summaries.py`;
    this is the Celery entry point. Total wall time on prod-scale data
    (333 evaluation_runs / 60k task_evaluations) should be well under a
    minute in the worker pod.
    """
    # aggregate_summaries lives in /shared (moved 2026-05-20 — see module
    # docstring). Worker has /shared on sys.path via the early bootstrap
    # block in this file; before the move this import resolved to a
    # nonexistent `services/` package and the task silently ModuleNotFound'd
    # on every beat, leaving project_summaries empty in every environment.
    from datetime import datetime as _dt

    from aggregate_summaries import (
        recompute_llm_leaderboard_scores,
        recompute_project_summaries,
    )

    lock_key = "lock:recompute_aggregates"
    lock_ttl_seconds = 600  # 10 min — generous ceiling on a normal run

    try:
        rc = redis.from_url(broker_url)
    except Exception as exc:
        logger.warning(
            "recompute_aggregates: redis unavailable for coalescing lock (%s); "
            "proceeding without dedup",
            exc,
        )
        rc = None

    have_lock = False
    if rc is not None:
        # SET NX EX -- only this caller proceeds if no other run is in flight.
        have_lock = bool(rc.set(lock_key, "1", nx=True, ex=lock_ttl_seconds))
        if not have_lock:
            logger.info("recompute_aggregates: another run holds the lock; skipping")
            return {"status": "skipped", "reason": "another_run_in_progress"}

    db = SessionLocal()
    try:
        started = _dt.now()
        ps_upserts = recompute_project_summaries(db)
        lls_upserts = recompute_llm_leaderboard_scores(db)
        elapsed = (_dt.now() - started).total_seconds()
        logger.info(
            "recompute_aggregates: project_summaries=%d llm_leaderboard_scores=%d elapsed=%.1fs",
            ps_upserts,
            lls_upserts,
            elapsed,
        )
        return {
            "status": "success",
            "project_summaries_upserted": ps_upserts,
            "llm_leaderboard_scores_upserted": lls_upserts,
            "elapsed_seconds": elapsed,
        }
    except Exception as exc:
        logger.error("recompute_aggregates failed: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
        if rc is not None and have_lock:
            try:
                rc.delete(lock_key)
            except Exception:
                pass


@app.task(name="tasks.update_report_annotations_async", bind=True)
def update_report_annotations_async(self, project_id: str):
    """Refresh a project's report annotation section off the request thread.

    The API dispatches this on every POST /annotations. Without coalescing,
    a 20-annotator burst yields 20 identical-shape COUNT + GROUP BY recomputes
    — wasteful and queue-saturating. We use the leader/follower pattern:

    * Leader: SETNX a per-project Redis lock; if we get it, run the compute.
    * Follower: if we can't get the lock, set a `pending` flag and return.
    * Tail check: the leader inspects the `pending` flag on its way out;
      if set, re-enqueue itself once so the most recent submit is reflected.

    Result: at most one in-flight recompute per project, with a guaranteed
    final run that observes the latest submitted state. Bounded queue
    pressure regardless of submit rate.
    """
    from report_service import update_report_annotations_section

    lock_key = f"lock:report_annotations:{project_id}"
    pending_key = f"pending:report_annotations:{project_id}"
    lock_ttl_seconds = 60  # generous ceiling on a single-project recompute

    try:
        rc = redis.from_url(app.conf.broker_url)
    except Exception as exc:
        logger.warning(
            "update_report_annotations_async: redis unavailable (%s); "
            "proceeding without coalescing",
            exc,
        )
        rc = None

    have_lock = False
    if rc is not None:
        have_lock = bool(rc.set(lock_key, "1", nx=True, ex=lock_ttl_seconds))
        if not have_lock:
            # Another task holds the lock for this project. Record that a
            # newer event arrived so the holder re-runs on its way out.
            try:
                rc.set(pending_key, "1", ex=lock_ttl_seconds * 2)
            except Exception:
                pass
            return {"status": "skipped", "project_id": project_id}

    db = SessionLocal()
    try:
        update_report_annotations_section(db, project_id)
        result: dict = {"status": "ok", "project_id": project_id}
    except Exception as exc:
        logger.error("update_report_annotations_async failed: %s", exc)
        result = {"status": "error", "project_id": project_id, "error": str(exc)}
    finally:
        db.close()

    if rc is not None and have_lock:
        try:
            # Tail check: did a follower mark this project dirty while we ran?
            # If so, fire one more pass so the latest submit is reflected.
            had_pending = bool(rc.delete(pending_key))
        except Exception:
            had_pending = False
        try:
            rc.delete(lock_key)
        except Exception:
            pass
        if had_pending:
            try:
                app.send_task(
                    "tasks.update_report_annotations_async",
                    args=[project_id],
                    queue="default",
                )
            except Exception as exc:
                logger.warning(
                    "update_report_annotations_async: re-enqueue failed: %s", exc
                )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Async project export → object storage (issue #158)
#
# The synchronous GET /export streamed the whole project through the API
# request thread; on the Benchathon project (~400MB of JSON) that OOMKilled
# the benger-api pod (exit 137, both replicas). This task moves the bulk data
# plane off the request path: it streams the same export generator
# chunk-by-chunk into object storage as a multipart upload, so worker peak RAM
# is bounded by one ~8MB part plus one generator batch regardless of project
# size. The client later downloads via a presigned URL (see the
# /exports/{job_id}/download endpoint), bypassing the API and the browser-RAM
# Blob entirely.
# ─────────────────────────────────────────────────────────────────────────────

# S3/MinIO require every multipart part EXCEPT the last to be >= 5MB. We buffer
# to 8MB before flushing a part; 8MB x 10_000 parts (the S3 part-count ceiling)
# = 80GB, far beyond any realistic export.
_EXPORT_PART_SIZE = 8 * 1024 * 1024


@app.task(
    name="tasks.export_project",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def export_project(self, job_id: str) -> Dict[str, Any]:
    """Stream a project export into object storage as a multipart upload.

    Reads the ExportJob row, picks the streaming generator for its format, and
    pushes the bytes to storage in ~8MB parts. On success the row is marked
    completed with the object_key, byte_size, and a 7-day expiry; on failure
    the in-flight multipart upload is aborted and the row marked failed.

    Idempotent: a job already past `running` (completed/failed) is skipped, so
    an acks_late redelivery of a finished job is a no-op. A job left `running`
    by a crashed worker IS re-run — that's the crash-recovery path.
    """
    from datetime import datetime, timedelta, timezone

    from export_stream import (
        EXPORT_FORMAT_MEDIA_TYPES,
        export_format_is_gzipped,
        select_export_generator,
    )
    from models import ExportJob, JobStatus
    from project_models import Project
    from storage.object_storage import object_storage

    db = SessionLocal()
    upload_id = None
    file_key = None
    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if job is None:
            logger.error("export_project: job %s not found", job_id)
            return {"status": "error", "error": "job_not_found", "job_id": job_id}

        if job.status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            logger.info(
                "export_project: job %s already in status %s; skipping",
                job_id,
                job.status,
            )
            return {"status": "skipped", "job_id": job_id, "job_status": job.status}

        project = (
            db.query(Project).filter(Project.id == job.project_id).first()
        )
        if project is None:
            job.status = JobStatus.FAILED.value
            job.error_message = "project_not_found"
            db.commit()
            return {"status": "error", "error": "project_not_found", "job_id": job_id}

        fmt = job.format or "json"
        channel = f"export:progress:{job.project_id}"

        job.status = JobStatus.RUNNING.value
        db.commit()
        _publish_progress(
            channel,
            {"job_id": job_id, "status": "running", "progress": 0, "bytes": 0},
        )

        media_type, ext = EXPORT_FORMAT_MEDIA_TYPES.get(
            fmt, ("application/octet-stream", "dat")
        )
        safe_title = (project.title or "project").replace(" ", "_")
        filename = f"{safe_title}_export.{ext}"

        upload = object_storage.create_multipart_upload(
            filename=filename,
            file_type="exports",
            user_id=job.requested_by,
            content_type=media_type,
        )
        upload_id = upload["upload_id"]
        file_key = upload["file_key"]

        # task_ids restricts a json export to a selected/filtered subset; NULL is
        # a whole-project export. select_export_generator rejects a subset for any
        # non-json format, but create_export_job already guards that at 422.
        generator = select_export_generator(db, project, fmt, task_ids=job.task_ids)

        buffer = bytearray()
        parts: List[Dict[str, Any]] = []
        part_number = 1
        total_bytes = 0

        # gzip-compress on the fly for gzipped formats. zlib with wbits
        # 16+MAX_WBITS emits a standard gzip member; .compress() may buffer and
        # return b"", with the remainder flushed once the generator is drained.
        # total_bytes tracks the *stored* (compressed) byte count so the job's
        # byte_size is accurate even before complete_multipart_upload reports it.
        compressor = None
        if export_format_is_gzipped(fmt):
            import zlib
            compressor = zlib.compressobj(6, zlib.DEFLATED, zlib.MAX_WBITS | 16)

        def _flush_part() -> None:
            nonlocal buffer, part_number
            if not buffer:
                return
            etag = object_storage.upload_part(
                file_key, upload_id, part_number, bytes(buffer)
            )
            parts.append({"PartNumber": part_number, "ETag": etag})
            part_number += 1
            buffer = bytearray()

        def _consume(data: bytes) -> None:
            nonlocal total_bytes
            if compressor is not None:
                data = compressor.compress(data)
            if not data:
                return
            buffer.extend(data)
            total_bytes += len(data)

        for chunk in generator:
            if not chunk:
                continue
            raw = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
            _consume(raw)
            if len(buffer) >= _EXPORT_PART_SIZE:
                _flush_part()
                _publish_progress(
                    channel,
                    {
                        "job_id": job_id,
                        "status": "running",
                        "progress": 0,
                        "bytes": total_bytes,
                    },
                )

        # Drain the compressor's internal buffer into the final part(s).
        if compressor is not None:
            tail = compressor.flush()
            if tail:
                buffer.extend(tail)
                total_bytes += len(tail)

        # Final flush — the last part may be < 5MB (S3 only constrains
        # non-final parts), so a small export ends up as a single short part.
        _flush_part()

        result_info = object_storage.complete_multipart_upload(
            file_key, upload_id, parts
        )
        byte_size = result_info.get("size", total_bytes)

        job.status = JobStatus.COMPLETED.value
        job.object_key = file_key
        job.byte_size = byte_size
        job.progress = 100
        job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        job.error_message = None
        db.commit()

        _publish_progress(
            channel,
            {
                "job_id": job_id,
                "status": "completed",
                "progress": 100,
                "bytes": byte_size,
            },
        )
        logger.info(
            "export_project: job %s completed (%s bytes, key=%s)",
            job_id,
            byte_size,
            file_key,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "object_key": file_key,
            "byte_size": byte_size,
        }

    except Exception as exc:
        logger.error(
            "export_project: job %s failed: %s", job_id, exc, exc_info=True
        )
        # Abort the in-flight upload so no orphaned parts accrue storage cost.
        if upload_id and file_key:
            object_storage.abort_multipart_upload(file_key, upload_id)
        try:
            db.rollback()
            from models import ExportJob, JobStatus

            job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
            if job is not None:
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)[:2000]
                db.commit()
                _publish_progress(
                    f"export:progress:{job.project_id}",
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "progress": job.progress or 0,
                    },
                )
        except Exception as inner:
            logger.error(
                "export_project: failed to mark job %s failed: %s", job_id, inner
            )
        return {"status": "error", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()


# Spool the downloaded import artifact in RAM up to this size, then spill to
# disk — mirrors the API endpoint's _IMPORT_SPOOL_THRESHOLD so the worker's peak
# heap during download stays bounded the same way.
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024


@app.task(
    name="tasks.import_project",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def import_project(self, job_id: str) -> Dict[str, Any]:
    """Download an uploaded import artifact and stream-import it into the DB.

    The inverse of ``export_project``: reads the ImportJob row, downloads its
    object_key from storage into a seekable spool, then runs the same shared
    streaming driver the synchronous endpoints use. ``project_id`` set ⇒ nested
    (label-studio, into the existing project); ``project_id`` None ⇒ flat
    comprehensive (creates a new project). The driver parses with ijson and
    inserts in flush-batched passes, so import memory stays O(batch).

    Idempotent: a job already past `running` is skipped (acks_late redelivery of
    a finished job is a no-op); a job left `running` by a crashed worker IS
    re-run — its single end-of-import commit means a crashed run left nothing
    partial behind.
    """
    import tempfile
    from datetime import datetime, timedelta, timezone

    from import_stream import (
        ImportValidationError,
        run_full_project_import,
        run_nested_import,
    )
    from models import ImportJob, JobStatus
    from storage.object_storage import object_storage

    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is None:
            logger.error("import_project: job %s not found", job_id)
            return {"status": "error", "error": "job_not_found", "job_id": job_id}

        if job.status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            logger.info(
                "import_project: job %s already in status %s; skipping",
                job_id,
                job.status,
            )
            return {"status": "skipped", "job_id": job_id, "job_status": job.status}

        # project_id is set for the nested (into-existing-project) format and
        # None for the comprehensive (creates-project) format. The progress
        # channel for a project-less import is keyed by job id instead.
        channel = f"import:progress:{job.project_id or job_id}"
        requested_by = job.requested_by
        object_key = job.object_key
        project_id = job.project_id

        job.status = JobStatus.RUNNING.value
        db.commit()
        _publish_progress(
            channel,
            {"job_id": job_id, "status": "running", "progress": 0},
        )

        spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
        try:
            object_storage.download_to_fileobj(object_key, spooled)
            byte_size = spooled.tell()
            spooled.seek(0)

            if project_id:
                result = run_nested_import(db, project_id, spooled, requested_by)
                detected_format = "nested"
            else:
                result = run_full_project_import(db, spooled, requested_by)
                detected_format = "comprehensive"
        finally:
            spooled.close()

        # run_full_project_import creates the project; capture its id so the
        # status row and download/poll URLs resolve to the created project.
        result_project_id = (result or {}).get("project_id")

        job.status = JobStatus.COMPLETED.value
        job.format = detected_format
        job.byte_size = byte_size
        job.progress = 100
        job.result = result
        if result_project_id and not job.project_id:
            job.project_id = result_project_id
        job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        job.error_message = None
        db.commit()

        _publish_progress(
            f"import:progress:{job.project_id or job_id}",
            {"job_id": job_id, "status": "completed", "progress": 100},
        )
        logger.info(
            "import_project: job %s completed (%s bytes, format=%s, project=%s)",
            job_id,
            byte_size,
            detected_format,
            job.project_id,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "project_id": job.project_id,
            "byte_size": byte_size,
        }

    except ImportValidationError as exc:
        # Malformed / mistyped payload — a client error, not a worker fault. The
        # driver already rolled back nothing was committed; record the 4xx detail.
        logger.warning(
            "import_project: job %s validation failed (%s): %s",
            job_id,
            exc.status_code,
            exc.detail,
        )
        _fail_import_job(db, job_id, f"{exc.status_code}: {exc.detail}")
        return {"status": "error", "job_id": job_id, "error": exc.detail}
    except Exception as exc:
        logger.error(
            "import_project: job %s failed: %s", job_id, exc, exc_info=True
        )
        _fail_import_job(db, job_id, str(exc))
        return {"status": "error", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()


def _fail_import_job(db, job_id: str, message: str) -> None:
    """Roll back and mark an ImportJob failed, publishing a final progress event."""
    from models import ImportJob, JobStatus

    try:
        db.rollback()
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error_message = message[:2000]
            db.commit()
            _publish_progress(
                f"import:progress:{job.project_id or job_id}",
                {
                    "job_id": job_id,
                    "status": "failed",
                    "progress": job.progress or 0,
                },
            )
    except Exception as inner:
        logger.error(
            "import_project: failed to mark job %s failed: %s", job_id, inner
        )
