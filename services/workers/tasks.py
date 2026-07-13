import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import redis
from dotenv import load_dotenv
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError


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


def _pred_field_matches(row_field_name: str | None, config_pred_field: str) -> bool:
    """Does a stored *bare* ``TaskEvaluation.field_name`` correspond to a
    config's ``prediction_fields`` entry, for missing-only key reconstruction?

    Immediate eval persists the BARE prediction field as ``field_name`` (e.g.
    ``"human:loesung"`` or ``"loesung"`` — see the immediate-eval block in
    ``run_single_sample_evaluation``), whereas the missing-only matcher keys on
    the 3-part ``{config_id}|{pred}|{ref}`` form. 3-part rows are already handled
    by :func:`_normalize_field_key`; this helper only bridges the bare form so a
    row whose ``evaluation_config_id`` is known can be mapped back to the exact
    expected key. The ``human:``/``model:`` role prefix is tolerated on either
    side so a bare ``"loesung"`` row matches a ``"human:loesung"`` config field.
    """
    if not row_field_name:
        return False
    # 3-part rows are the _normalize_field_key path, not this one.
    if "|" in row_field_name:
        return False

    def _strip_role(s: str) -> str:
        if s in ("__all_human__", "__all_model__"):
            return s
        if s.startswith("human:") or s.startswith("model:"):
            return s.split(":", 1)[1]
        return s

    if row_field_name == config_pred_field:
        return True
    return _strip_role(row_field_name) == _strip_role(config_pred_field)


def _reconstruct_expected_keys(row, configs_by_id: dict) -> set:
    """Expected-key strings an existing ``TaskEvaluation`` row satisfies, derived
    from its discrete ``evaluation_config_id`` (Issue #111 / migration 057).

    Immediate eval stores a bare ``field_name`` that the 3-part missing-only
    matcher misses, but it also stores ``evaluation_config_id``; from that we
    rebuild the exact ``{config_id}|{pred}|{ref}`` strings that
    ``all_expected_field_keys`` is built from, so an immediate-graded unit counts
    as "done" without changing what immediate writes. Returns an empty set when
    the row carries no config id, or a config id not among the current run's
    configs (a re-saved config gets a new id — those rows aren't recognized).

    Wildcard prediction fields (``__all_human__``/``__all_model__``) are skipped:
    the expected set holds the literal wildcard string while rows hold the
    expanded field, so wildcard configs are a pre-existing missing-only
    limitation this must not silently change.
    """
    keys: set = set()
    cfg = configs_by_id.get(getattr(row, "evaluation_config_id", None))
    if not cfg:
        return keys
    for pf in cfg.get("prediction_fields", []):
        if pf in ("__all_human__", "__all_model__"):
            continue
        if _pred_field_matches(row.field_name, pf):
            for rf in cfg.get("reference_fields", []):
                keys.add(f"{cfg.get('id', 'unknown')}|{pf}|{rf}")
    return keys


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
        from generation_structure_parser import GenerationStructureParser  # noqa: F401  (availability probe)

        HAS_GENERATION_PARSER = True
        logger.info("✅ GenerationStructureParser imported successfully")
    except ImportError as e:
        logger.warning(f"⚠️ GenerationStructureParser not available: {e}")
        HAS_GENERATION_PARSER = False

    # Bind ResponseParser at module scope so the generation service's
    # ``tasks.ResponseParser(...)`` call resolves. The original top-level
    # ``from response_parser import ResponseParser`` was dropped when the parse
    # logic moved into ``generation/llm_generation_service.py`` during the tasks.py
    # decomposition — which SILENTLY broke ALL structured-output parsing: every
    # ``tasks.ResponseParser(...)`` raised AttributeError, swallowed by the
    # service's ``except Exception`` as ``parse_status="failed"`` / a per-row
    # "module 'tasks' has no attribute 'ResponseParser'" error.
    from response_parser import ResponseParser  # noqa: F401

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


# The Celery app + its config live in worker_celery so task modules can import
# `app` without importing all of tasks.py (breaks the cell_evaluator import
# cycle). The worker is still launched as `celery -A tasks`: re-exporting `app`
# here keeps the -A target and all `tasks.*` registered names unchanged.
from worker_celery import app  # noqa: E402,F401


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


def _dispatch_immediate_eval(db, annotation) -> None:
    """Fire the immediate (KI-Votum) evaluation for a server-auto-submitted
    annotation, so an absent student's grade is produced at submit time rather
    than waiting for the hourly missing-only sweep.

    No-op unless the project has ``immediate_evaluation_enabled`` AND an eligible
    metric, so it is inert in the community edition (no immediate metrics). The
    underlying ``ensure_immediate_evaluation`` is an idempotent get-or-create, so
    this never double-dispatches even when the present-student client path also
    fired it. Never raises — an eval-dispatch failure must not fail auto-submit.
    """
    try:
        from project_models import Project, Task

        project = (
            db.query(Project).filter(Project.id == annotation.project_id).first()
        )
        if not project or not getattr(project, "immediate_evaluation_enabled", False):
            return
        task = db.query(Task).filter(Task.id == annotation.task_id).first()
        if not task:
            return
        from immediate_eval_dispatch import ensure_immediate_evaluation

        ensure_immediate_evaluation(
            db,
            project,
            task,
            annotation,
            user_id=annotation.completed_by,
            trigger="timer_auto_submit",
        )
    except Exception as e:  # noqa: BLE001 — dispatch must never fail auto-submit
        logger.warning(
            f"immediate-eval dispatch on auto-submit failed "
            f"(annotation {getattr(annotation, 'id', None)}): {e}"
        )


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

        # Serialize against the client auto-submit using the SAME advisory key
        # the /annotations endpoint uses, so a present student's client POST and
        # this worker can't both INSERT a row for this (task, user). The partial
        # unique index uq_annotations_active_task_user is the hard backstop if
        # the lock is ever bypassed (handled below) — this task name is
        # registered by BOTH platform and the extended overlay, so which
        # implementation wins (and whether it locks) is non-deterministic.
        from sqlalchemy import text as _sql_text
        db.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"annsubmit:{session.task_id}:{session.user_id}"},
        )

        # Check if user already has an active annotation for this task (client
        # beat us). Fire the immediate eval on it too: the present-student
        # client path also dispatches, but ensure_immediate_evaluation is an
        # idempotent get-or-create, so this never double-grades.
        existing = db.query(Annotation).filter(
            Annotation.task_id == session.task_id,
            Annotation.completed_by == session.user_id,
            Annotation.was_cancelled == False,  # noqa: E712
        ).first()
        if existing:
            now = datetime.now(timezone.utc)
            session.completed_at = now
            session.auto_submitted = True
            db.commit()
            _dispatch_immediate_eval(db, existing)
            return {"status": "skipped", "reason": "annotation already exists"}

        # Timed access window: don't finalize a draft into an annotation once the
        # project's window has closed — "immutable after close". Close the timer
        # session so it isn't retried.
        from project_window import project_writes_allowed

        project = db.query(Project).filter(Project.id == session.project_id).first()
        if project is not None and not project_writes_allowed(project):
            session.completed_at = datetime.now(timezone.utc)
            session.auto_submitted = True
            db.commit()
            logger.info(
                "auto_submit_expired_timer: project window closed for %s; "
                "skipped auto-submit for session %s",
                session.project_id,
                session_id,
            )
            return {"status": "skipped", "reason": "project window closed"}

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
            # `project` already loaded above for the window check.
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
        try:
            db.commit()
        except IntegrityError:
            # Lost the INSERT race to the client despite the advisory lock (a
            # bypassed/duplicate worker registration can skip it). The client's
            # row is authoritative: adopt it, complete the session, and fire the
            # eval on the surviving annotation.
            db.rollback()
            session = db.query(TimerSession).filter(
                TimerSession.id == session_id
            ).first()
            existing = (
                db.query(Annotation).filter(
                    Annotation.task_id == session.task_id,
                    Annotation.completed_by == session.user_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                ).first()
                if session
                else None
            )
            if session and not session.completed_at:
                session.completed_at = datetime.now(timezone.utc)
                session.auto_submitted = True
                db.commit()
            if existing:
                _dispatch_immediate_eval(db, existing)
            return {"status": "skipped", "reason": "client beat us (integrity)"}

        logger.info(f"Server-side auto-submit for session {session_id}: annotation {annotation.id}")
        _dispatch_immediate_eval(db, annotation)
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
    return generate_llm_responses_impl(
        generation_id,
        config_data,
        model_id,
        user_id,
        structure_key,
        organization_id,
        run_index,
    )


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
    host: str = None,
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

        from mailer.branding import resolve_email_brand

        brand = resolve_email_brand(host)

        subject, html_body = email_service.build_invitation_email(
            organization_name=organization_name,
            inviter_name=inviter_name,
            role=role,
            invitation_url=invitation_url,
            brand_name=brand.name,
            brand_tagline=brand.tagline,
            language=brand.default_language,
        )

        result = client.send_message(
            to=[to_email],
            subject=subject,
            html_body=html_body,
            from_address=brand.from_address,
            from_name=brand.from_name,
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
                kwargs={'host': invitation.get('host')},
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
    return generate_response_impl(
        generation_id,
        project_id,
        task_id,
        model_id,
        structure_key,
        force_rerun,
        organization_id,
        run_index,
    )


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

            # Index configs by id so missing-only can reconstruct expected keys
            # for rows that carry the discrete `evaluation_config_id` (Issue #111)
            # but a bare `field_name` — i.e. immediate-eval rows, which the 3-part
            # `_normalize_field_key` matcher alone never recognizes. See
            # `_reconstruct_expected_keys`.
            configs_by_id = {c.get("id", "unknown"): c for c in enabled_configs}

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
                        TaskEvaluation.evaluation_config_id,
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
                        done = evaluated_by_gen.setdefault(r.generation_id, set())
                        done.add(_normalize_field_key(r.field_name, is_annotation=False))
                        # Also recognize bare-field_name rows (immediate eval) via
                        # their discrete evaluation_config_id.
                        done |= _reconstruct_expected_keys(r, configs_by_id)
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
                            TaskEvaluation.evaluation_config_id,
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
                            done = evaluated_by_ann.setdefault(r.annotation_id, set())
                            done.add(_normalize_field_key(r.field_name, is_annotation=True))
                            # Also recognize bare-field_name rows (immediate eval)
                            # via their discrete evaluation_config_id.
                            done |= _reconstruct_expected_keys(r, configs_by_id)

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


def _get_grading_dispatch_policy_fn():
    """Extension hook: per-grading dispatch policy (extended edition only).

    The extended edition can re-route which org's API key a grading resolves
    against and override judge models per grading (e.g. subscription-tier
    models) — and that policy must see EVERY dispatch path (client-fired
    immediate eval, the annotation-submit hook, timer auto-submit, the
    recovery sweep), which all funnel through run_single_sample_evaluation.
    Community edition: returns None (no-op).
    """
    try:
        from benger_extended.workers import get_grading_dispatch_policy_fn

        return get_grading_dispatch_policy_fn()
    except (ImportError, AttributeError):
        return None


def _run_grading_finalize_hook(evaluation_run_id: str, success: bool) -> None:
    """Extension hook: settle the grading's metered-billing ledger row.

    Called once the run is terminal. Path-B dispatches (submit hook, timer
    auto-submit, sweep) have no status poller, so the worker is the only
    place that reliably observes completion. The extended implementation
    opens its own DB session and never raises. Community edition: no-op.
    """
    try:
        from benger_extended.workers import get_grading_finalize_fn

        finalize_fn = get_grading_finalize_fn()
    except (ImportError, AttributeError):
        return
    if finalize_fn is None:
        return
    try:
        finalize_fn(evaluation_run_id, success)
    except Exception as finalize_err:  # defensive — billing must not kill evals
        logger.error(
            f"[SingleSampleEval] grading finalize hook failed for "
            f"{evaluation_run_id}: {finalize_err}"
        )


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

        # Immediate eval runs deterministic metrics + LLM judges only.
        # Human-graded Korrektur (scored by a person) and heavy/semantic
        # metrics (transformer-model loads — too slow for instant feedback,
        # OOM risk on the interactive fleet) are filtered out. The dispatcher
        # already excludes them; doing it here too guarantees expected ==
        # actual so the polling endpoint's completion detection is exact.
        from metric_filters import is_immediate_eligible

        eligible_configs = [
            c for c in evaluation_configs if is_immediate_eligible(c.get("metric", ""))
        ]

        # Per-dispatch EvaluationRun. The API pre-creates this row at dispatch
        # (so polling finds the expected method list immediately); get-or-create
        # here so the worker is robust whether or not it already exists. The
        # worker additionally stamps run_provenance (worker image tag, schema
        # snapshot) which the API can't know.
        from sqlalchemy.orm.attributes import flag_modified

        dispatch_eval_id = evaluation_record_id
        configs_meta = [
            {
                "id": c.get("id", c.get("metric", "")),
                "metric": c.get("metric", ""),
                "display_name": c.get("display_name", c.get("metric", "")),
            }
            for c in eligible_configs
        ]
        eval_run = (
            db.query(EvaluationRun).filter(EvaluationRun.id == dispatch_eval_id).first()
        )
        if eval_run is None:
            eval_run = EvaluationRun(
                id=dispatch_eval_id,
                project_id=project_id,
                model_id="immediate",
                evaluation_type_ids=[c.get("metric", "") for c in eligible_configs],
                status="running",
                created_by=user_id or "system",
                eval_metadata={
                    "evaluation_type": "immediate",
                    "expected_config_count": len(eligible_configs),
                    "configs": configs_meta,
                    **run_provenance,
                },
                metrics={},
            )
            db.add(eval_run)
            db.flush()
        else:
            # Pre-created by the API — fold in worker-only provenance and make
            # sure the expected-config list is present for completion detection.
            meta = dict(eval_run.eval_metadata or {})
            meta.update(run_provenance)
            meta.setdefault("evaluation_type", "immediate")
            if not meta.get("configs"):
                meta["configs"] = configs_meta
                meta["expected_config_count"] = len(eligible_configs)
            eval_run.eval_metadata = meta
            eval_run.status = "running"
            flag_modified(eval_run, "eval_metadata")
            db.flush()

        # Extension hook: grading dispatch policy (see helper above). Runs
        # BEFORE judge runs / jobs are built so an overridden judge model is
        # what actually grades AND what EvaluationJudgeRun.judge_model_id
        # records. On policy failure we log and keep the dispatched values —
        # a metered grading then fails loud on key resolution rather than
        # silently spending the wrong key.
        _policy_fn = _get_grading_dispatch_policy_fn()
        if _policy_fn is not None:
            try:
                organization_id, eligible_configs = _policy_fn(
                    db,
                    project=project_for_snapshot,
                    user_id=user_id,
                    organization_id=organization_id,
                    configs=eligible_configs,
                    evaluation_run_id=dispatch_eval_id,
                    eval_metadata=eval_run.eval_metadata or {},
                )
            except Exception as policy_err:  # defensive — see comment above
                logger.error(
                    f"[SingleSampleEval] grading dispatch policy failed for "
                    f"{dispatch_eval_id}: {policy_err}"
                )

        # Every TaskEvaluation row needs a judge_run_id (NOT NULL since
        # migration 043). CRITICAL: the unique constraint uq_task_evaluations_cell
        # keys on (evaluation_id, judge_run_id, generation_id, annotation_id,
        # field_name, created_by). Immediate eval writes a BARE field_name and
        # all configs grade the SAME annotation, so every config here shares
        # (annotation_id, field_name) — the ONLY field left to differentiate
        # rows is judge_run_id. So each config gets its OWN judge_run with a
        # distinct run_index; sharing one catch-all judge_run would make the
        # 2nd+ config on a field collide and silently drop. (Batch eval instead
        # encodes the config id into field_name; immediate keeps the bare name
        # so the modal can group by the real field.)
        from models import EvaluationJudgeRun

        # Per-dispatch cache so a config resolved once (or revisited on a retry
        # within the same dispatch) reuses the judge_run it already created
        # instead of issuing a second INSERT.
        _judge_run_by_idx: Dict[int, str] = {}

        def _get_or_create_judge_run_for_config(cfg: Dict[str, Any], idx: int) -> str:
            if idx in _judge_run_by_idx:
                return _judge_run_by_idx[idx]
            params = cfg.get("metric_parameters") or {}
            judge_model = params.get("judge_model")
            judges = params.get("judges")
            if isinstance(judges, list) and judges:
                judge_model = judges[0].get("judge_model_id") or judge_model

            # run_index doubles as a per-config disambiguator: each config gets a
            # distinct (evaluation_id, judge_model_id, run_index), hence a
            # distinct judge_run_id — what keeps the per-row
            # uq_task_evaluations_cell from colliding across configs. Look first
            # for a judge_run a prior dispatch already created for THIS config
            # (a resume reuses the same dispatch_eval_id), so we don't violate
            # uq_evaluation_judge_runs by re-inserting the same triple.
            existing = db.query(EvaluationJudgeRun).filter(
                EvaluationJudgeRun.evaluation_id == dispatch_eval_id,
                EvaluationJudgeRun.judge_model_id == judge_model,
                EvaluationJudgeRun.run_index == idx,
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
                _judge_run_by_idx[idx] = existing.id
                return existing.id

            # LLM-judge configs capture the same _param_provenance snapshot as
            # run_evaluation (academic-rigor traceability). Deterministic
            # metrics have no judge model, so they skip that resolution and
            # store judge_model_id=NULL.
            snapshot = None
            if judge_model:
                judge_model_obj = (
                    db.query(DBLLMModel).filter(DBLLMModel.id == judge_model).first()
                )
                judge_recommended = (
                    getattr(judge_model_obj, "recommended_parameters", None) or None
                )
                judge_provenance: Dict[str, Dict[str, Any]] = {}
                for _k in ("temperature", "max_tokens", "seed"):
                    value, source, rec_at_trigger = _resolve_param(
                        key=_k,
                        mode="evaluation",
                        model_recommended=judge_recommended,
                        project_cfg=None,
                        per_model_cfg=params,
                    )
                    judge_provenance[_k] = {
                        "value": value,
                        "source": source,
                        "recommended_at_trigger": rec_at_trigger,
                    }
                snapshot = dict(params)
                snapshot["_param_provenance"] = judge_provenance

            jr = EvaluationJudgeRun(
                id=str(uuid.uuid4()),
                evaluation_id=dispatch_eval_id,
                judge_model_id=judge_model,  # None for deterministic metrics
                run_index=idx,
                status="running",
                started_at=datetime.now(),
                metric_parameters_snapshot=snapshot,
            )
            db.add(jr)
            db.flush()
            _judge_run_by_idx[idx] = jr.id
            return jr.id

        # ---- Resolve each config into a self-contained job (main session) ----
        #
        # Everything that needs THIS session (judge_run get-or-create, which
        # races under parallelism) is done here, serially, before fan-out.
        # Prediction/reference resolution needs no DB, so it happens here too.
        # `prediction_fields` carries a literal field name, a
        # `human:<field>` / `model:<field>` prefix, or the bulk selectors
        # `__all_human__` / `__all_model__`. `annotation_results` is keyed by
        # raw `from_name`, so we strip prefixes and expand `__all_human__`.
        def _resolve_human_field(pf: str):
            if pf == "__all_human__":
                if not annotation_results:
                    return None
                return "\n\n".join(
                    f"{k}: {v}" for k, v in annotation_results.items() if v
                )
            key = pf.split(":", 1)[1] if pf.startswith("human:") else pf
            return annotation_results.get(key)

        jobs: List[Dict[str, Any]] = []
        for idx, eval_cfg in enumerate(eligible_configs):
            metric_type = eval_cfg.get("metric", "")
            pred_fields = eval_cfg.get("prediction_fields", [])
            ref_fields = eval_cfg.get("reference_fields", [])
            metric_params = eval_cfg.get("metric_parameters", {})

            prediction_value = None
            reference_value = None
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

            # Each config gets its OWN judge_run (distinct run_index) so the
            # per-row uq_task_evaluations_cell stays unique even though every
            # config grades the same annotation+field. Created here in the main
            # session (committed before fan-out) so worker threads resolve the FK.
            judge_run_id = _get_or_create_judge_run_for_config(eval_cfg, idx)

            jobs.append({
                "metric_type": metric_type,
                "metric_params": metric_params,
                "field_name": pred_fields[0] if pred_fields else "field",
                "prediction_value": prediction_value,
                "reference_value": reference_value,
                "judge_run_id": judge_run_id,
                "evaluation_config_id": eval_cfg.get("id"),
                "record_id": str(uuid.uuid4()),
            })

        # Commit the setup rows (EvaluationRun, default + per-config judge_runs)
        # so the worker threads' own sessions can resolve them as FK targets.
        db.commit()

        # ---- Fan out: each job computes + persists in its OWN session on a
        # worker thread. LLM judges are I/O-bound, so wall-clock ≈ slowest
        # job, not the sum — which keeps a multi-method submit inside the
        # frontend's poll budget. Heavy/semantic metrics are already gated
        # out, so no transformer-model loads land on these threads. ----
        results = []
        if jobs:
            from concurrent.futures import ThreadPoolExecutor

            max_workers = min(len(jobs), 8)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(
                        _run_immediate_config_job,
                        job=job,
                        dispatch_eval_id=dispatch_eval_id,
                        project_id=project_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        organization_id=organization_id,
                        user_id=user_id,
                        task_data=task_data,
                    )
                    for job in jobs
                ]
                for fut in futures:
                    try:
                        results.append(fut.result())
                    except Exception as e:  # defensive — the job fn catches its own
                        logger.error(f"[SingleSampleEval] config job crashed: {e}")
                        results.append({"status": "error", "error": str(e)})

        # Mark the dispatch run as completed and aggregate metrics
        eval_run = db.query(EvaluationRun).filter(EvaluationRun.id == dispatch_eval_id).first()
        if eval_run:
            eval_run.status = "completed"

            # Aggregate TaskEvaluation scores into EvaluationRun.metrics
            # so the comparison table on /evaluations can display them.
            # Re-query in this session — the rows were written by the worker
            # threads' sessions and committed.
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
                        if metric_name == "raw_score" or any(metric_name.endswith(s) for s in skip_suffixes):
                            continue
                        # Unified shape {value, method, details}: pull the
                        # numeric `value`. Legacy bare floats pass straight
                        # through. Anything else (None/str/dict-without-value)
                        # is not aggregatable.
                        if isinstance(score, dict):
                            inner = score.get("value")
                            if isinstance(inner, (int, float)):
                                metric_scores[(field_name, metric_name)].append(inner)
                        elif isinstance(score, (int, float)):
                            metric_scores[(field_name, metric_name)].append(score)

                aggregated = {}
                for (field_name, metric_name), scores in metric_scores.items():
                    # `f"{field_name}|{metric_name}"` is the key shape the
                    # /evaluations comparison table already parses for batch
                    # runs, so it renders immediate runs with no extra parser.
                    # Note this rollup is a lossy SUMMARY, not byte-parity with
                    # batch: batch encodes the config id into field_name, so two
                    # configs grading the same field with the same metric stay
                    # distinct there, whereas here they average into one bucket.
                    # The per-config breakdown is preserved in the TaskEvaluation
                    # rows (and surfaced per-method by the modal); this map is
                    # only the headline number for the comparison table.
                    key = f"{field_name}|{metric_name}"
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

        _run_grading_finalize_hook(
            dispatch_eval_id,
            not any(
                isinstance(r, dict) and r.get("status") == "error" for r in results
            ),
        )

        return {
            "status": "completed",
            "evaluation_record_id": evaluation_record_id,
            "results": results,
        }

    except Exception as e:
        logger.error(f"[SingleSampleEval] Task failed: {e}")
        db.rollback()
        _run_grading_finalize_hook(evaluation_record_id, False)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# Phase 5: _evaluate_falloesung_single moved to
# benger-extended/benger_extended/workers/falloesung_tasks.evaluate_falloesung_single
# and dispatched via the metric registry hook. See the
# llm_judge_falloesung branch in run_single_sample_evaluation above.


def _run_immediate_config_job(
    *,
    job: Dict[str, Any],
    dispatch_eval_id: str,
    project_id: str,
    task_id: str,
    annotation_id: Optional[str],
    organization_id: Optional[str],
    user_id: Optional[str],
    task_data: Dict[str, Any],
) -> Dict[str, Any]:
    return _run_immediate_config_job_impl(
        job=job,
        dispatch_eval_id=dispatch_eval_id,
        project_id=project_id,
        task_id=task_id,
        annotation_id=annotation_id,
        organization_id=organization_id,
        user_id=user_id,
        task_data=task_data,
    )


def _evaluate_llm_judge_single(
    db, record_id, immediate_eval_id, project_id, task_id,
    annotation_id, user_id, field_name, metric_type, prediction,
    reference, metric_params, organization_id,
    judge_run_id: Optional[str] = None,
    evaluation_config_id: Optional[str] = None,
):
    return _evaluate_llm_judge_single_impl(
        db, record_id, immediate_eval_id, project_id, task_id,
        annotation_id, user_id, field_name, metric_type, prediction,
        reference, metric_params, organization_id,
        judge_run_id=judge_run_id,
        evaluation_config_id=evaluation_config_id,
    )


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
    breakdown.

    Two nested `jsonb_set` calls are required, NOT one: Postgres'
    `create_missing=true` only creates the *leaf* key — it cannot create a
    missing intermediate parent. A single `jsonb_set(.., {failures_by_reason,
    <reason>}, .., true)` against an eval_metadata that has no
    `failures_by_reason` key is a SILENT NO-OP (it returns the input
    unchanged), so the FIRST failure of any kind was never recorded. The
    inner `jsonb_set` seeds the parent object (`failures_by_reason` ←
    COALESCE(existing, '{}')) so the outer one can then set the leaf.

    Skips entirely when the parent is already terminal, mirroring the
    `_bump_evaluation_counters` guard."""
    from sqlalchemy import text as _text

    db.execute(
        _text(
            """
            UPDATE evaluation_runs
               SET eval_metadata = (
                 jsonb_set(
                   -- Ensure the failures_by_reason parent object exists first;
                   -- jsonb_set can't auto-create a missing intermediate path.
                   jsonb_set(
                     COALESCE(eval_metadata::jsonb, '{}'::jsonb),
                     ARRAY['failures_by_reason'],
                     COALESCE(eval_metadata::jsonb->'failures_by_reason', '{}'::jsonb),
                     true
                   ),
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
    from evaluation.cell_evaluator import evaluate_generation_cell_impl
    return evaluate_generation_cell_impl(self, evaluation_id, task_id, generation_id, project_id, configs_for_cell, judge_run_ids_by_config, default_judge_run_id, organization_id, triggered_by_user_id, label_config_version, already_evaluated_field_keys)


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
    from evaluation.cell_evaluator import evaluate_annotation_cell_impl
    return evaluate_annotation_cell_impl(self, evaluation_id, task_id, annotation_id, project_id, configs_for_cell, judge_run_ids_by_config, default_judge_run_id, organization_id, triggered_by_user_id, already_evaluated_field_keys)


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

    Runs hourly via beat (see `app.conf.beat_schedule`) and can be triggered
    ad-hoc. Coalesces concurrent runs with a Redis lock so a burst of triggers
    collapses to a single execution.

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
        rc = redis.from_url(app.conf.broker_url)
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


@app.task(name="tasks.sweep_missing_immediate_evals", bind=True)
def sweep_missing_immediate_evals(self, min_age_minutes: int = 15):
    """Hourly server-side backstop for the client-fired KI-Votum.

    Immediate evaluation is normally produced on submit (the on_annotation_created
    hook, the strict-timer auto-submit worker, or the client POST). This sweep is
    the last safety net: it scans every immediate-eval project and re-dispatches a
    grade for any annotation that still has none (lost client POST, worker crash,
    etc.). Idempotent — ``ensure_immediate_evaluation`` skips annotations that
    already carry a grade or an in-flight run. ``min_age_minutes`` skips very
    recent submits (via the scan cutoff) so an in-flight client eval isn't raced.
    """
    from datetime import datetime as _dt
    from datetime import timedelta, timezone

    from immediate_eval_dispatch import ensure_immediate_evaluation, scan_ungraded
    from project_models import Project

    db = SessionLocal()
    cutoff = _dt.now(timezone.utc) - timedelta(minutes=min_age_minutes)
    scanned_projects = dispatched = 0
    try:
        projects = (
            db.query(Project)
            .filter(Project.immediate_evaluation_enabled == True)  # noqa: E712
            .all()
        )
        for project in projects:
            candidates, _partials = scan_ungraded(db, project, cutoff=cutoff)
            if not candidates:
                continue
            scanned_projects += 1
            for annotation, task in candidates:
                try:
                    # cutoff already applied in scan_ungraded → no min-age here.
                    rid = ensure_immediate_evaluation(
                        db, project, task, annotation,
                        trigger="sweep_missing_immediate_evals",
                    )
                    if rid:
                        dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "sweep_missing_immediate_evals: annotation %s failed: %s",
                        annotation.id, exc,
                    )
                    db.rollback()
        logger.info(
            "sweep_missing_immediate_evals: projects_with_gaps=%d dispatched=%d",
            scanned_projects, dispatched,
        )
        return {"status": "success", "projects_with_gaps": scanned_projects, "dispatched": dispatched}
    except Exception as exc:
        logger.error("sweep_missing_immediate_evals failed: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()


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

@app.task(
    name="tasks.export_project",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def export_project(self, job_id: str) -> Dict[str, Any]:
    return export_project_impl(self, job_id)


@app.task(
    name="tasks.import_project",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def import_project(self, job_id: str) -> Dict[str, Any]:
    return import_project_impl(self, job_id)


def _fail_import_job(db, job_id: str, message: str) -> None:
    return _fail_import_job_impl(db, job_id, message)


# ─────────────────────────────────────────────────────────────────────────────
# Extracted implementations (structural decomposition of this module).
#
# These submodules `import tasks` and reach back into this module's globals
# (SessionLocal, logger, monkeypatched helpers, …) at call time, so the
# decorated wrappers above stay the public Celery surface while the bodies
# live in cohesive submodules. Imported at the bottom — after `app`,
# `SessionLocal`, and every helper the bodies reference is defined — so the
# circular `import tasks` inside each submodule resolves against a fully
# initialized module object. Top-level package names (`generation`,
# `evaluation`, `project`) resolve because `services/workers/` is on sys.path.
# ─────────────────────────────────────────────────────────────────────────────
from generation.llm_generation_service import (  # noqa: E402
    generate_llm_responses_impl,
    generate_response_impl,
)
from evaluation.orchestration import _run_immediate_config_job_impl  # noqa: E402
from evaluation.judge_evaluator import _evaluate_llm_judge_single_impl  # noqa: E402
from project.export_import_service import (  # noqa: E402
    export_project_impl,
    import_project_impl,
    _fail_import_job_impl,
)
