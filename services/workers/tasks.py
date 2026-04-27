import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

import redis
from celery import Celery
from dotenv import load_dotenv

# Import response parser for LLM response parsing
from response_parser import ResponseParser

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

# Add current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import database and models at top level to avoid import issues in worker processes
try:
    from database import SessionLocal

    # Prompt import removed in Issue #759 - use generation_structure instead
    from models import LLMModel as DBLLMModel
    from models import LLMResponse as DBLLMResponse  # Individual LLM responses
    from models import ProjectReport as DBProjectReport  # For report updates
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
    except ImportError:
        # Mock notification service for testing
        def notify_task_completed(*args, **kwargs):
            return {"status": "mock", "notification_sent": False}

        class NotificationService:
            @staticmethod
            def create_notification(*args, **kwargs):
                return []

        class NotificationType:
            EVALUATION_COMPLETED = "evaluation_completed"
            EVALUATION_FAILED = "evaluation_failed"

        HAS_NOTIFICATION_SERVICE = False

    # NOTE: Label Studio and annotation storage services removed
    # Using native annotation system now

    # Native annotation system in use

    # Import digest service
    try:
        from digest_service import DigestService
    except ImportError:
        # Mock DigestService for testing
        class DigestService:
            @staticmethod
            async def process_all_digests(db):
                return {"total_users": 0, "digests_sent": 0, "errors": 0}

            @staticmethod
            async def process_digest_for_user(db, user):
                return True

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
    logger.error(f"❌ Failed to import database/models: {e}")

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
    logger.error(f"❌ Failed to import AI services: {e}")

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

app.conf.beat_schedule = {
    # Process daily digests
    "process-daily-digests": {
        "task": "digest.process_all_digests",
        "schedule": crontab(hour=8, minute=0),  # Daily at 8:00 AM
    },
}

app.conf.timezone = "UTC"

# Task routing configuration for different queues
app.conf.task_routes = {
    'emails.*': {'queue': 'emails'},
    'digest.*': {'queue': 'emails'},
    'tasks.*': {'queue': 'default'},
}

# Rate limiting for email tasks to prevent overwhelming mail server
app.conf.task_annotations = {
    'emails.send_invitation': {'rate_limit': '30/m'},  # 30 invitations per minute
    'emails.send_bulk_invitations': {'rate_limit': '5/m'},  # 5 bulk operations per minute
    'digest.process_all_digests': {'rate_limit': '10/h'},  # 10 digest runs per hour
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
        from project_models import Annotation, AnnotationTimerSession, Project, Task

        session = db.query(AnnotationTimerSession).filter(
            AnnotationTimerSession.id == session_id
        ).first()

        if not session:
            return {"status": "skipped", "reason": "session not found"}
        if session.completed_at:
            return {"status": "skipped", "reason": "already completed"}

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
                key_source = f"org {organization_id}" if organization_id else f"user {user_id}"
                logger.info(f"Using API key from {key_source} for {model.provider}")
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
                key_context = f"organization settings" if organization_id else "profile settings"
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

                        # Temperature/max_tokens resolution priority:
                        # 1. System defaults (lowest)
                        # 2. Project defaults from generation_config.selected_configuration.parameters
                        # 3. Per-model config from generation_config.selected_configuration.model_configs
                        # 4. Prompt metadata (highest)

                        # Start with system defaults
                        temperature = 0.0
                        max_tokens = 1500

                        # Second priority: Project defaults
                        project_params = selected_config_for_model.get("parameters", {})
                        if "temperature" in project_params:
                            temperature = project_params["temperature"]
                            logger.info(f"📋 Using project default temperature: {temperature}")
                        if "max_tokens" in project_params:
                            max_tokens = project_params["max_tokens"]

                        # Third priority: Per-model config overrides project defaults
                        if model_config:
                            logger.info(f"📋 Found model_config for {model_id}: {model_config}")
                            # Check for temperature in model config (direct field)
                            if "temperature" in model_config:
                                temperature = model_config["temperature"]
                                logger.info(f"🔧 Using per-model temperature: {temperature}")
                            # Also check nested generation_config for backward compatibility
                            elif "generation_config" in model_config:
                                if "temperature" in model_config["generation_config"]:
                                    temperature = model_config["generation_config"]["temperature"]
                                    logger.info(
                                        f"🔧 Using per-model temperature (nested): {temperature}"
                                    )

                            # Check for max_tokens in model config
                            if "max_tokens" in model_config:
                                max_tokens = model_config["max_tokens"]
                            elif "generation_config" in model_config:
                                if "max_tokens" in model_config["generation_config"]:
                                    max_tokens = model_config["generation_config"]["max_tokens"]

                        # Fourth priority: Prompt metadata (highest)
                        if (
                            hasattr(instruction_prompt, "prompt_metadata")
                            and instruction_prompt.prompt_metadata
                        ):
                            if "temperature" in instruction_prompt.prompt_metadata:
                                temperature = instruction_prompt.prompt_metadata["temperature"]
                                logger.info(
                                    f"🔥 Using temperature from prompt metadata: {temperature}"
                                )
                            if "max_tokens" in instruction_prompt.prompt_metadata:
                                max_tokens = instruction_prompt.prompt_metadata["max_tokens"]

                        # Extract reasoning/thinking config from model_config
                        reasoning_kwargs = {}
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

                        # Apply model-specific parameter constraints
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
                                    temperature = required_temp
                            else:
                                # Clamp to allowed min/max range
                                min_temp = temp_config.get('min')
                                max_temp = temp_config.get('max')
                                if min_temp is not None and temperature < min_temp:
                                    logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to min {min_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    temperature = min_temp
                                if max_temp is not None and temperature > max_temp:
                                    logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to max {max_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    temperature = max_temp

                        logger.info(
                            f"🌡️ Final temperature: {temperature}, max_tokens: {max_tokens} for model {model_id}"
                        )

                        # Capture resolved parameters for provenance
                        if _captured_parameters is None:
                            _captured_parameters = {
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                **reasoning_kwargs,
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
                                f"ℹ️ Skipping parsing - no label_config configured for project"
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

                    except Exception as e:
                        _last_error = str(e)
                        logger.error(
                            f"❌ Failed to generate response for task {task_data['id']}, prompt {prompt_id}: {_last_error}"
                        )
                        continue

            # Update generation status based on actual results
            # If no responses were generated but some were expected, mark as failed
            if responses_generated == 0 and total_expected > 0:
                generation.status = "failed"
                generation.error_message = _last_error or "Unknown error"
            else:
                generation.status = "completed"
            generation.completed_at = datetime.now()
            generation.responses_generated = responses_generated
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

            # Trigger notification for completion
            try:
                if project and HAS_DATABASE:
                    # Get project's organization for notification from ProjectOrganization table
                    from project_models import ProjectOrganization

                    project_org = (
                        db.query(ProjectOrganization.organization_id)
                        .filter(ProjectOrganization.project_id == project_id)
                        .first()
                    )
                    org_id = project_org[0] if project_org else None

                    notify_task_completed(
                        task_id=project_id,
                        task_name=project.title,
                        user_id=user_id,
                        completion_type="llm_generation",
                        organization_id=org_id,
                    )
                    logger.info(f"✅ Notification sent for project {project_id} completion")
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
            # Update generation status to failed
            try:
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


@app.task(bind=True, name="digest.process_all_digests")
async def process_all_digests_task(self) -> Dict[str, Any]:
    """
    Celery task to process email digests for all users

    This task is designed to be run on a schedule (e.g., daily) to send
    digest emails to users who have enabled digest notifications.

    Returns:
        Dictionary with processing statistics
    """
    logger.info("🔄 Starting digest processing task")

    if not HAS_DATABASE:
        logger.error("❌ Database not available for digest processing")
        return {"status": "error", "message": "Database not available"}

    db = SessionLocal()

    try:
        # Process all digests using the digest service
        stats = await DigestService.process_all_digests(db)

        logger.info(
            f"✅ Digest processing completed: "
            f"{stats['digests_sent']}/{stats['total_users']} digests sent"
        )

        return {
            "status": "success",
            "message": f"Processed digests for {stats['total_users']} users",
            "stats": stats,
        }

    except Exception as e:
        logger.error(f"❌ Error processing digests: {str(e)}")
        return {"status": "error", "message": f"Digest processing failed: {str(e)}"}

    finally:
        db.close()


@app.task(bind=True, name="digest.send_test_digest")
async def send_test_digest_task(self, user_id: str) -> Dict[str, Any]:
    """
    Celery task to send a test digest to a specific user

    Args:
        user_id: ID of the user to send test digest to

    Returns:
        Dictionary with result status
    """
    logger.info(f"🔄 Sending test digest to user {user_id}")

    if not HAS_DATABASE:
        logger.error("❌ Database not available for test digest")
        return {"status": "error", "message": "Database not available"}

    db = SessionLocal()

    try:
        # Get user
        from models import User

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return {"status": "error", "message": f"User {user_id} not found"}

        # Process digest for this user
        success = await DigestService.process_digest_for_user(db, user)

        if success:
            logger.info(f"✅ Test digest sent successfully to {user.email}")
            return {"status": "success", "message": f"Test digest sent to {user.email}"}
        else:
            logger.warning(
                f"⚠️ Test digest not sent to {user.email} (no notifications or digest disabled)"
            )
            return {
                "status": "skipped",
                "message": f"No digest sent to {user.email} (no new notifications or digest disabled)",
            }

    except Exception as e:
        logger.error(f"❌ Error sending test digest to user {user_id}: {str(e)}")
        return {"status": "error", "message": f"Test digest failed: {str(e)}"}

    finally:
        db.close()


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
        from sendgrid_client import SendGridClient

        client = SendGridClient()

        subject = f"Invitation to join {organization_name} on BenGER"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>You're invited to join {organization_name}</h2>
            <p>{inviter_name} has invited you to join {organization_name} as a {role} on BenGER.</p>
            <p>BenGER is a comprehensive evaluation framework for Large Language Models in the German legal domain.</p>
            <p style="margin: 30px 0;">
                <a href="{invitation_url}" style="background-color: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                    Accept Invitation
                </a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="color: #007bff;">{invitation_url}</p>
            <p style="color: #666; font-size: 12px; margin-top: 30px;">
                This invitation will expire in 7 days. If you did not expect this invitation, you can safely ignore this email.
            </p>
        </body>
        </html>
        """

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
        else:
            error_msg = result.get("error", "Unknown SendGrid error")
            logger.error(f"Failed to send invitation email to {to_email}: {error_msg}")
            raise RuntimeError(f"SendGrid error: {error_msg}")

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

    Returns:
        Dictionary with generation results
    """
    structure_info = f" with structure '{structure_key}'" if structure_key else ""
    logger.info(f"🎯 Starting generation for task {task_id} with model {model_id}{structure_info}")

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
                generation_id, config_data, model_id, user_id, structure_key, organization_id
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

        # Try to update generation status
        try:
            db = SessionLocal()
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

            # Initialize LLM Judge evaluator if any configs use llm_judge metrics
            llm_judge_evaluators = {}  # Config ID -> evaluator instance
            for config in enabled_configs:
                metric = config.get("metric", "")
                if metric.startswith("llm_judge_"):
                    config_id = config.get("id", "unknown")
                    params = config.get("metric_parameters", {})
                    # Get triggered_by user ID from eval_metadata
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

                    try:
                        from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user

                        # Determine provider from judge_model
                        judge_model = params.get("judge_model", "gpt-4o")
                        provider = _get_provider_from_model(judge_model)

                        llm_judge = create_llm_judge_for_user(
                            db=db,
                            user_id=triggered_by,
                            provider=provider,
                            judge_model=judge_model,
                            temperature=params.get("temperature", 0.0),
                            max_tokens=params.get("max_tokens", 500),
                            criteria=params.get("dimensions"),
                            custom_criteria=params.get("custom_criteria"),
                            custom_prompt_template=params.get("custom_prompt_template"),
                            answer_type=params.get("answer_type"),
                            field_mappings=params.get("field_mappings"),
                            score_scale=params.get("score_scale", "1-5"),
                            organization_id=organization_id,
                        )

                        e2e_test_mode = os.environ.get("E2E_TEST_MODE") == "true"
                        if llm_judge.ai_service or e2e_test_mode:
                            llm_judge_evaluators[config_id] = llm_judge
                            key_source = f"org {organization_id}" if organization_id else f"user {triggered_by}"
                            mode = " (mock/E2E)" if not llm_judge.ai_service else ""
                            logger.info(
                                f"Initialized LLM judge for config {config_id} with model {judge_model} (key via {key_source}){mode}"
                            )
                        else:
                            logger.warning(
                                f"LLM judge for config {config_id} has no AI service - skipping"
                            )
                    except Exception as e:
                        if os.environ.get("E2E_TEST_MODE") == "true":
                            # In E2E test mode, create evaluator without AI service (returns mock scores)
                            from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

                            llm_judge = LLMJudgeEvaluator(
                                criteria=params.get("dimensions") if params else None,
                                score_scale="0-1",  # Mock always returns 0-1
                            )
                            llm_judge_evaluators[config_id] = llm_judge
                            logger.info(
                                f"Using mock LLM judge for E2E test config {config_id} (init failed: {e})"
                            )
                        else:
                            logger.error(f"Failed to initialize LLM judge for config {config_id}: {e}")

            # Load tasks with annotations
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

            logger.info(f"Loaded {len(tasks)} tasks for evaluation")

            # Pre-compute expected field keys from enabled configs
            all_expected_field_keys = {
                f"{c.get('id', 'unknown')}|{pf}|{rf}"
                for c in enabled_configs
                for pf in c.get("prediction_fields", [])
                for rf in c.get("reference_fields", [])
            }

            # Bulk-load successfully evaluated (generation_id, field_name) pairs
            # Checks ALL evaluation runs (not just current) so interrupted runs can be resumed
            # field_name includes config_id so different configs won't collide
            evaluated_by_gen: dict[str, set[str]] = {}
            if evaluate_missing_only:
                task_id_list = [t.id for t in tasks]
                existing = (
                    db.query(
                        TaskEvaluation.generation_id,
                        TaskEvaluation.field_name,
                        TaskEvaluation.metrics,
                    )
                    .filter(
                        TaskEvaluation.task_id.in_(task_id_list),
                        TaskEvaluation.generation_id.isnot(None),
                    )
                    .all()
                )
                for r in existing:
                    has_score = any(
                        k != "error" and isinstance(v, (int, float))
                        for k, v in (r.metrics or {}).items()
                    )
                    if has_score:
                        evaluated_by_gen.setdefault(r.generation_id, set()).add(r.field_name)
                logger.info(
                    f"Loaded existing evaluations: {sum(len(v) for v in evaluated_by_gen.values())} "
                    f"results across {len(evaluated_by_gen)} generations"
                )

            # Build field configs for SampleEvaluator
            field_configs = {}
            metric_parameters = {}
            for config in enabled_configs:
                config_id = config.get("id", "unknown")
                metric = config.get("metric", "")
                params = config.get("metric_parameters", {})

                # For each prediction-reference field pair
                for pred_field in config.get("prediction_fields", []):
                    for ref_field in config.get("reference_fields", []):
                        field_key = f"{config_id}|{pred_field}|{ref_field}"
                        field_configs[field_key] = {"type": "text"}
                        if params:
                            metric_parameters[field_key] = {metric: params}

            sample_evaluator = SampleEvaluator(evaluation_id, field_configs, metric_parameters)

            # Process tasks
            sample_results = []
            aggregate_metrics = {}
            samples_evaluated = 0
            samples_passed = 0
            samples_failed = 0

            # Check if any config uses annotation fields (not task.* fields)
            uses_annotation_fields = any(
                any(not ref.startswith("task.") for ref in config.get("reference_fields", []))
                for config in enabled_configs
            )

            for task in tasks:
                # Get annotations (ground truth) - only needed if using annotation reference fields
                ground_truth_annotation = None
                if uses_annotation_fields:
                    annotations = db.query(Annotation).filter(Annotation.task_id == task.id).all()
                    if annotations:
                        ground_truth_annotation = annotations[0]

                # Get generations for this task
                # Check if any config uses __all_model__ - if so, include failed parses too
                # (we can use raw response_content as prediction)
                uses_all_model = any(
                    "__all_model__" in config.get("prediction_fields", [])
                    for config in enabled_configs
                )

                generations_query = db.query(Generation).filter(Generation.task_id == task.id)

                # Only filter by parse_status if not using __all_model__
                if not uses_all_model:
                    generations_query = generations_query.filter(
                        Generation.parse_status == "success"
                    )

                # Filter by label_config_version if specified
                if label_config_version:
                    generations_query = generations_query.filter(
                        Generation.label_config_version == label_config_version
                    )

                # Filter by model_ids if specified (for single-cell re-evaluation)
                if model_ids:
                    generations_query = generations_query.filter(
                        Generation.model_id.in_(model_ids)
                    )

                generations = generations_query.all()

                if not generations:
                    logger.debug(f"Task {task.id} has no generations, skipping")
                    continue

                # Evaluate each generation against each config
                for generation in generations:
                    # Skip fully-evaluated generations (all configs done)
                    if evaluate_missing_only:
                        gen_done = evaluated_by_gen.get(generation.id, set())
                        if all_expected_field_keys and all_expected_field_keys.issubset(gen_done):
                            logger.info(
                                f"Skipping fully-evaluated generation {generation.id} "
                                f"(model: {generation.model_id})"
                            )
                            continue

                    for config in enabled_configs:
                        config_id = config.get("id", "unknown")
                        metric = config.get("metric", "")
                        prediction_fields = config.get("prediction_fields", [])
                        reference_fields = config.get("reference_fields", [])

                        # Evaluate each field pair
                        for pred_field in prediction_fields:
                            # Skip human annotation fields — handled in annotation section below
                            if pred_field.startswith("human:") or pred_field == "__all_human__":
                                continue

                            for ref_field in reference_fields:
                                field_key = f"{config_id}|{pred_field}|{ref_field}"

                                # Skip already-evaluated config+field pairs
                                if evaluate_missing_only and field_key in evaluated_by_gen.get(generation.id, set()):
                                    continue

                                # Extract ground truth - from task.data if prefixed with "task."
                                if ref_field.startswith("task."):
                                    # Extract from task.data (e.g., "task.binary_solution" -> task.data['binary_solution'])
                                    data_field = ref_field[5:]  # Remove "task." prefix
                                    ground_truth = task.data.get(data_field) if task.data else None
                                elif ground_truth_annotation:
                                    # Extract from annotation
                                    ground_truth = _extract_field_value_from_annotation(
                                        ground_truth_annotation.result or [], ref_field
                                    )
                                    # Fallback: check task.data if not found in annotation
                                    # (matches immediate evaluation behavior at line ~2955)
                                    if ground_truth is None and task.data and ref_field in task.data:
                                        ground_truth = task.data.get(ref_field)
                                else:
                                    # No annotation — try task.data directly
                                    ground_truth = task.data.get(ref_field) if task.data else None
                                if ground_truth is None:
                                    logger.warning(
                                        f"Evaluation skip: reference field '{ref_field}' not found "
                                        f"for task {task.id} (config {config_id})"
                                    )
                                    continue

                                # Strip model: prefix for extraction from parsed_annotation
                                base_field = pred_field
                                if pred_field.startswith("model:"):
                                    base_field = pred_field[6:]

                                # Extract prediction from generation
                                # Handle special __all_model__ field - use raw response_content
                                if pred_field == "__all_model__":
                                    prediction = generation.response_content
                                else:
                                    prediction = _extract_field_value_from_parsed_annotation(
                                        generation.parsed_annotation, base_field
                                    )
                                    # Fallback to response_content if parsed_annotation is empty/null
                                    if prediction is None and generation.response_content:
                                        prediction = generation.response_content
                                if prediction is None:
                                    logger.warning(
                                        f"Evaluation skip: prediction field '{pred_field}' not found "
                                        f"for task {task.id}, model {generation.model_id} (config {config_id})"
                                    )
                                    continue

                                # Evaluate this sample
                                # Allow unparsed generations when using __all_model__ (raw response_content)
                                allow_unparsed = pred_field == "__all_model__"
                                try:
                                    # Check if this is an LLM Judge metric
                                    if (
                                        metric.startswith("llm_judge_")
                                        and config_id in llm_judge_evaluators
                                    ):
                                        llm_judge = llm_judge_evaluators[config_id]
                                        # Get context from task data
                                        context = (
                                            _get_insensitive(task.data, "text")
                                            or _get_insensitive(task.data, "input")
                                            or _get_insensitive(task.data, "sachverhalt")
                                            or ""
                                        )

                                        # Falloesung: override ground_truth from task data
                                        eval_ground_truth = str(ground_truth) if ground_truth else ""
                                        if metric == "llm_judge_falloesung" and task.data:
                                            muster = _get_insensitive(task.data, "musterloesung") or _get_insensitive(task.data, "musterlösung")
                                            if muster:
                                                eval_ground_truth = str(muster)

                                        # Determine criterion from metric name
                                        criterion = metric.replace("llm_judge_", "")
                                        if criterion == "custom":
                                            criterion = "correctness"  # Default criterion for custom prompts
                                        elif criterion == "overall":
                                            criterion = (
                                                "correctness"  # Use correctness as main criterion
                                            )

                                        # Call LLM Judge evaluator
                                        result = llm_judge._evaluate_single_criterion(
                                            context=context,
                                            ground_truth=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            criterion=criterion,
                                            task_data=task.data,
                                        )

                                        # Extract prompt provenance before metric processing
                                        judge_prompts = (
                                            result.pop("_judge_prompts_used", None)
                                            if result
                                            else None
                                        )

                                        # Extract score from result
                                        raw_score = None
                                        if result is not None:
                                            raw_score = result["score"]

                                        # Normalize score to 0-1 range
                                        error_msg = None
                                        if raw_score is not None:
                                            if llm_judge.score_scale == "0-1":
                                                score = raw_score  # Already 0-1
                                            elif llm_judge.score_scale == "0-100":
                                                score = raw_score / 100.0  # Convert 0-100 to 0-1
                                            else:
                                                score = (raw_score - 1) / 4  # Convert 1-5 to 0-1
                                        else:
                                            # API failure - don't assign 0.0 as that conflates
                                            # with legitimate low scores
                                            score = None
                                            error_msg = "LLM judge evaluation failed"
                                            logger.warning(
                                                f"LLM judge returned None for task {task.id}, "
                                                f"field {field_key}"
                                            )

                                        # Create sample result with full LLM response
                                        import uuid

                                        sample_result = {
                                            "id": str(uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "task_id": task.id,
                                            "generation_id": generation.id,
                                            "field_name": field_key,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000]
                                            if ground_truth
                                            else "",
                                            "prediction": str(prediction)[:1000]
                                            if prediction
                                            else "",
                                            "metrics": {
                                                metric: score,
                                                "raw_score": raw_score,
                                                f"{metric}_response": result,  # Store ENTIRE LLM response
                                                # Extra Falloesung metrics
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
                                        }
                                    else:
                                        # Use standard SampleEvaluator for non-LLM metrics
                                        sample_result = sample_evaluator.evaluate_sample(
                                            task_id=task.id,
                                            field_name=field_key,
                                            ground_truth=ground_truth,
                                            prediction=prediction,
                                            metrics_to_compute=[metric],
                                            generation_id=generation.id,
                                            parse_status=generation.parse_status,
                                            allow_unparsed=allow_unparsed,
                                        )

                                    sample_results.append(sample_result)
                                    samples_evaluated += 1

                                    if sample_result["passed"]:
                                        samples_passed += 1
                                    else:
                                        samples_failed += 1

                                    # Accumulate primary metric score only (not raw_score or sub-metrics)
                                    metric_key = f"{field_key}|{metric}"
                                    primary_value = sample_result["metrics"].get(metric)
                                    if primary_value is not None and isinstance(
                                        primary_value, (int, float)
                                    ):
                                        if metric_key not in aggregate_metrics:
                                            aggregate_metrics[metric_key] = []
                                        aggregate_metrics[metric_key].append(primary_value)

                                    # Aggregate Falloesung sub-metrics under their own keys
                                    for suffix in ("_grade_points", "_passed"):
                                        sub_key_name = f"{metric}{suffix}"
                                        sub_value = sample_result["metrics"].get(sub_key_name)
                                        if sub_value is not None and isinstance(
                                            sub_value, (int, float)
                                        ):
                                            sub_metric_key = f"{field_key}|{sub_key_name}"
                                            if sub_metric_key not in aggregate_metrics:
                                                aggregate_metrics[sub_metric_key] = []
                                            aggregate_metrics[sub_metric_key].append(sub_value)

                                    # Commit each result immediately so the frontend
                                    # can show live progress via SSE stream
                                    if sample_results:
                                        for result in sample_results:
                                            db.add(TaskEvaluation(**result))
                                        evaluation.samples_evaluated = samples_evaluated
                                        evaluation.has_sample_results = True
                                        db.commit()
                                        sample_results = []

                                except ValueError as e:
                                    logger.warning(f"Skipping sample: {e}")
                                    continue
                                except Exception as e:
                                    logger.error(f"Error evaluating sample: {e}")
                                    import uuid as _uuid
                                    sample_results.append({
                                        "id": str(_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "task_id": task.id,
                                        "generation_id": generation.id,
                                        "field_name": field_key,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": {},
                                        "passed": False,
                                        "error_message": str(e),
                                    })
                                    samples_evaluated += 1
                                    samples_failed += 1
                                    continue

            # Evaluate human annotations for configs with human: fields or __all_human__
            # Also handles backward compat: llm_judge_falloesung with unprefixed prediction fields
            from annotation_utils import extract_all_field_values as _extract_all_fields
            import uuid as _ann_uuid

            # Pre-load all annotations once (avoids N+1 queries per config x task)
            task_id_list = [t.id for t in tasks]
            all_annotations = db.query(Annotation).filter(
                Annotation.task_id.in_(task_id_list),
                Annotation.was_cancelled == False,
            ).all()
            annotations_by_task: dict[str, list] = {}
            for ann in all_annotations:
                annotations_by_task.setdefault(ann.task_id, []).append(ann)

            # Pre-load existing annotation evaluations once (shared across all configs)
            evaluated_by_ann: dict[str, set[str]] = {}
            if evaluate_missing_only:
                existing_ann = (
                    db.query(
                        TaskEvaluation.annotation_id,
                        TaskEvaluation.field_name,
                        TaskEvaluation.metrics,
                    )
                    .filter(
                        TaskEvaluation.task_id.in_(task_id_list),
                        TaskEvaluation.annotation_id.isnot(None),
                    )
                    .all()
                )
                for r in existing_ann:
                    has_score = any(
                        k != "error" and isinstance(v, (int, float))
                        for k, v in (r.metrics or {}).items()
                    )
                    if has_score:
                        evaluated_by_ann.setdefault(r.annotation_id, set()).add(r.field_name)

            for config in enabled_configs:
                config_id = config.get("id", "unknown")
                metric = config.get("metric", "")
                prediction_fields = config.get("prediction_fields", [])
                reference_fields = config.get("reference_fields", [])

                # Collect human prediction fields from this config
                human_pred_fields = []
                for pf in prediction_fields:
                    if pf.startswith("human:"):
                        human_pred_fields.append(("human:" + pf[6:], pf[6:]))  # (prefixed, base)
                    elif pf == "__all_human__":
                        human_pred_fields.append(("__all_human__", "__all_human__"))

                # Backward compat: llm_judge_falloesung with unprefixed fields evaluates annotations
                if not human_pred_fields and metric == "llm_judge_falloesung":
                    for pf in prediction_fields:
                        if not pf.startswith("model:") and pf not in ("__all_model__", "__all_human__"):
                            human_pred_fields.append((f"human:{pf}", pf))

                if not human_pred_fields:
                    continue

                logger.info(f"Evaluating human annotations for config {config_id} (metric: {metric})...")

                # Ground truth cache per (task_id, ref_field) — same for all annotations
                gt_cache: dict[tuple, any] = {}

                for task in tasks:
                    annotations = annotations_by_task.get(task.id, [])

                    for annotation in annotations:
                        for pred_field_prefixed, base_field in human_pred_fields:
                            # Extract prediction from annotation
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

                                    # Skip already-evaluated (using pre-loaded set)
                                    if evaluate_missing_only and field_key in evaluated_by_ann.get(annotation.id, set()):
                                        continue

                                    # Extract ground truth (cached per task+ref_field)
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
                                        if metric.startswith("llm_judge_") and config_id in llm_judge_evaluators:
                                            llm_judge = llm_judge_evaluators[config_id]
                                            context = (
                                                _get_insensitive(task.data, "text")
                                                or _get_insensitive(task.data, "input")
                                                or _get_insensitive(task.data, "sachverhalt")
                                                or ""
                                            ) if task.data else ""

                                            eval_ground_truth = str(ground_truth) if ground_truth else ""
                                            if metric == "llm_judge_falloesung" and task.data:
                                                muster = _get_insensitive(task.data, "musterloesung") or _get_insensitive(task.data, "musterlösung")
                                                if muster:
                                                    eval_ground_truth = str(muster)

                                            criterion = metric.replace("llm_judge_", "")
                                            if criterion == "custom":
                                                criterion = "correctness"
                                            elif criterion == "overall":
                                                criterion = "correctness"

                                            result = llm_judge._evaluate_single_criterion(
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

                                            raw_score = result["score"] if result is not None else None
                                            error_msg = None
                                            if raw_score is not None:
                                                if llm_judge.score_scale == "0-1":
                                                    score = raw_score
                                                elif llm_judge.score_scale == "0-100":
                                                    score = raw_score / 100.0
                                                else:
                                                    score = (raw_score - 1) / 4
                                            else:
                                                score = None
                                                error_msg = "LLM judge evaluation failed"

                                            annotation_result = {
                                                "id": str(_ann_uuid.uuid4()),
                                                "evaluation_id": evaluation_id,
                                                "task_id": task.id,
                                                "generation_id": None,
                                                "annotation_id": annotation.id,
                                                "field_name": field_key,
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
                                            }
                                        else:
                                            # Standard metric (ROUGE, BLEU, etc.)
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

                                        sample_results.append(annotation_result)
                                        samples_evaluated += 1
                                        if annotation_result.get("passed"):
                                            samples_passed += 1
                                        else:
                                            samples_failed += 1

                                        # Accumulate primary metric only (match generation loop pattern)
                                        metric_key = f"{field_key}|{metric}"
                                        primary_value = annotation_result.get("metrics", {}).get(metric)
                                        if primary_value is not None and isinstance(primary_value, (int, float)):
                                            if metric_key not in aggregate_metrics:
                                                aggregate_metrics[metric_key] = []
                                            aggregate_metrics[metric_key].append(primary_value)

                                        # Aggregate Falloesung sub-metrics
                                        for suffix in ("_grade_points", "_passed"):
                                            sub_key_name = f"{metric}{suffix}"
                                            sub_value = annotation_result.get("metrics", {}).get(sub_key_name)
                                            if sub_value is not None and isinstance(sub_value, (int, float)):
                                                sub_metric_key = f"{field_key}|{sub_key_name}"
                                                if sub_metric_key not in aggregate_metrics:
                                                    aggregate_metrics[sub_metric_key] = []
                                                aggregate_metrics[sub_metric_key].append(sub_value)

                                        # Commit each result immediately so the frontend
                                        # can show live progress via SSE stream
                                        if sample_results:
                                            for sr in sample_results:
                                                db.add(TaskEvaluation(**sr))
                                            evaluation.samples_evaluated = samples_evaluated
                                            evaluation.has_sample_results = True
                                            db.commit()
                                            sample_results = []

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
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": {},
                                            "passed": False,
                                            "error_message": str(e),
                                        })
                                        samples_evaluated += 1
                                        samples_failed += 1

            # Store remaining sample results (not yet stored in batches)
            if sample_results:
                for result in sample_results:
                    sample_record = TaskEvaluation(**result)
                    db.add(sample_record)
                db.commit()
                logger.info(f"📦 Stored final batch of {len(sample_results)} results")

            # Compute aggregate metrics
            final_metrics = {}
            for metric_key, values in aggregate_metrics.items():
                if values:
                    final_metrics[metric_key] = sum(values) / len(values)

            # Update evaluation record
            evaluation.status = "completed"
            evaluation.completed_at = datetime.now()
            evaluation.samples_evaluated = samples_evaluated
            evaluation.metrics = final_metrics
            evaluation.has_sample_results = True
            evaluation.eval_metadata = {
                **evaluation.eval_metadata,
                "samples_passed": samples_passed,
                "samples_failed": samples_failed,
                "configs_evaluated": len(enabled_configs),
                "pass_rate": samples_passed / samples_evaluated if samples_evaluated > 0 else 0,
                # Persist actual judge models used (config_id -> model name)
                **({"judge_models": {
                    cid: ev.judge_model for cid, ev in llm_judge_evaluators.items()
                }} if llm_judge_evaluators else {}),
            }
            db.commit()

            # Update report evaluation section
            try:
                api_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api')
                if api_dir not in sys.path:
                    sys.path.insert(0, api_dir)
                from report_service import update_report_evaluation_section

                update_report_evaluation_section(db, project_id)
                logger.info(f"✅ Updated report evaluation section for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to update report evaluation section: {e}")

            logger.info(
                f"✅ Multi-field evaluation completed: {samples_evaluated} samples, "
                f"pass rate: {samples_passed/samples_evaluated:.2%}"
                if samples_evaluated > 0
                else "✅ Multi-field evaluation completed: 0 samples"
            )

            # Create notification for evaluation completion
            try:
                triggered_by = (
                    evaluation.eval_metadata.get("triggered_by")
                    if evaluation.eval_metadata
                    else None
                )
                if triggered_by:
                    pass_rate = samples_passed / samples_evaluated if samples_evaluated > 0 else 0
                    NotificationService.create_notification(
                        db=db,
                        user_ids=[triggered_by],
                        notification_type=NotificationType.EVALUATION_COMPLETED,
                        title="Evaluation Complete",
                        message=f"Evaluation completed: {samples_evaluated} samples evaluated ({pass_rate:.0%} pass rate)",
                        data={
                            "project_id": project_id,
                            "evaluation_id": evaluation_id,
                            "samples_evaluated": samples_evaluated,
                            "samples_passed": samples_passed,
                            "pass_rate": pass_rate,
                        },
                    )
                    logger.info(f"📬 Created completion notification for user {triggered_by}")
            except Exception as notif_err:
                logger.error(f"Failed to create completion notification: {notif_err}")

            return {
                "status": "success",
                "evaluation_id": evaluation_id,
                "project_id": project_id,
                "samples_evaluated": samples_evaluated,
                "samples_passed": samples_passed,
                "samples_failed": samples_failed,
                "pass_rate": samples_passed / samples_evaluated if samples_evaluated > 0 else 0,
                "metrics": final_metrics,
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


def _ensure_immediate_eval_run(db, immediate_eval_id, project_id, user_id):
    """Get or create the EvaluationRun for immediate evaluations, backfilling metadata if needed."""
    from models import EvaluationRun

    existing_run = db.query(EvaluationRun).filter(
        EvaluationRun.id == immediate_eval_id
    ).first()
    if not existing_run:
        meta = _immediate_eval_metadata()
        immediate_run = EvaluationRun(
            id=immediate_eval_id,
            project_id=project_id,
            model_id="immediate",
            evaluation_type_ids=["llm_judge_falloesung"],
            status="completed",
            created_by=user_id,
            **meta,
        )
        db.add(immediate_run)
        db.flush()
    elif not existing_run.eval_metadata:
        # Backfill metadata on records that predate this fix
        from sqlalchemy.orm.attributes import flag_modified
        meta = _immediate_eval_metadata()
        existing_run.eval_metadata = meta["eval_metadata"]
        existing_run.metrics = meta["metrics"]
        flag_modified(existing_run, "eval_metadata")
        flag_modified(existing_run, "metrics")
        db.flush()


def _persist_immediate_eval_error(
    db, evaluation_record_id, project_id, task_id,
    annotation_id, user_id, field_name, musterloesung, prediction, error_msg,
    **kwargs,
):
    """Persist an error record for immediate evaluation so polling endpoint can detect failure."""
    from models import TaskEvaluation

    immediate_eval_id = f"immediate_{project_id}"
    # If caller provides an explicit eval_run_id, use it; otherwise fall back to shared ID
    eval_run_id = kwargs.get("eval_run_id", immediate_eval_id)
    if eval_run_id == immediate_eval_id:
        _ensure_immediate_eval_run(db, immediate_eval_id, project_id, user_id)

    error_record = TaskEvaluation(
        id=evaluation_record_id,
        evaluation_id=eval_run_id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=None,
        field_name=field_name,
        answer_type="long_text",
        ground_truth=musterloesung if musterloesung else "",
        prediction=prediction if prediction else "",
        metrics={"error": True},
        passed=False,
        error_message=error_msg,
    )
    db.add(error_record)
    db.commit()
    logger.info(f"[Falloesung Celery] Persisted error record {evaluation_record_id}")


@app.task(name="tasks.run_immediate_falloesung", bind=True)
def run_immediate_falloesung(
    self,
    evaluation_record_id: str,
    project_id: str,
    task_id: str,
    annotation_id: str,
    user_id: str,
    judge_model: str,
    sachverhalt: str,
    musterloesung: str,
    prediction: str,
    field_name: str = "loesung",
    metric_parameters: Optional[Dict[str, Any]] = None,
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Falllösung LLM judge evaluation asynchronously via Celery.

    Dispatched from the API immediate evaluation endpoint to avoid blocking
    the API worker during the 5-15s LLM call.

    Returns result dict with score, grade_points, passed, dimensions.
    """
    import time
    import uuid

    from falloesung_constants import (
        FALLOESUNG_PROMPT_TEMPLATE,
        FALLOESUNG_SYSTEM_PROMPT,
        parse_falloesung_response,
    )

    params = metric_parameters or {}
    temperature = params.get("temperature", 0.0)
    max_tokens = params.get("max_tokens", 4096)
    thinking_budget = params.get("thinking_budget")
    reasoning_effort = params.get("reasoning_effort")
    max_retries = 3

    db = SessionLocal()
    try:
        from models import EvaluationRun, TaskEvaluation

        provider = _get_provider_from_model(judge_model)

        if not HAS_AI_SERVICES:
            logger.error("[Falloesung Celery] AI services not available")
            return {"status": "error", "message": "AI services not available"}

        try:
            ai_service = user_aware_ai_service.get_ai_service_for_user(
                db, user_id, provider, organization_id=organization_id
            )
        except Exception as e:
            logger.error(f"[Falloesung Celery] Failed to create AI service: {e}")
            return {"status": "error", "message": f"API key error: {e}"}

        if ai_service is None:
            msg = f"No API key found for provider '{provider}'"
            if organization_id:
                msg += f" (org: {organization_id})"
            else:
                msg += f" (user: {user_id})"
            logger.error(f"[Falloesung Celery] {msg}")
            # Persist error record so polling endpoint can detect failure
            _persist_immediate_eval_error(
                db, evaluation_record_id, project_id, task_id,
                annotation_id, user_id, field_name, musterloesung, prediction, msg
            )
            return {"status": "error", "evaluation_record_id": evaluation_record_id, "message": msg}

        prompt = FALLOESUNG_PROMPT_TEMPLATE.format(
            context=sachverhalt or "(Kein Sachverhalt angegeben)",
            ground_truth=musterloesung or "(Keine Musterlösung angegeben)",
            prediction=prediction or "(Keine Studierendenlösung angegeben)",
        )

        result = None
        for attempt in range(max_retries):
            try:
                extra_kwargs = {}
                if thinking_budget:
                    extra_kwargs["thinking_budget"] = thinking_budget
                if reasoning_effort:
                    extra_kwargs["reasoning_effort"] = reasoning_effort

                logger.info(f"[Falloesung Celery] Calling {provider}/{judge_model} (attempt {attempt + 1})")
                response = ai_service.generate(
                    prompt=prompt,
                    system_prompt=FALLOESUNG_SYSTEM_PROMPT,
                    model_name=judge_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **extra_kwargs,
                )

                if not response.get("success"):
                    logger.warning(f"[Falloesung Celery] LLM call failed: {response.get('error')}")
                    continue

                content = response.get("content", "")
                logger.info(f"[Falloesung Celery] Got response ({len(content)} chars)")
                result = parse_falloesung_response(content)

                if result is not None:
                    logger.info(
                        f"[Falloesung Celery] Score: {result['total_score']}/100, "
                        f"Grade: {result['grade_points']}/18, Passed: {result['passed']}"
                    )
                    break
            except Exception as e:
                logger.warning(f"[Falloesung Celery] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))

        if result is None:
            _persist_immediate_eval_error(
                db, evaluation_record_id, project_id, task_id,
                annotation_id, user_id, field_name, musterloesung, prediction,
                "All evaluation attempts failed"
            )
            return {"status": "error", "evaluation_record_id": evaluation_record_id, "message": "All evaluation attempts failed"}

        # Persist TaskEvaluation
        total_score = result.get("score", 0)
        normalized_score = total_score / 100.0
        immediate_eval_id = f"immediate_{project_id}"

        _ensure_immediate_eval_run(db, immediate_eval_id, project_id, user_id)

        eval_record = TaskEvaluation(
            id=evaluation_record_id,
            evaluation_id=immediate_eval_id,
            task_id=task_id,
            annotation_id=annotation_id,
            generation_id=None,
            field_name=field_name,
            answer_type="long_text",
            ground_truth=musterloesung if musterloesung else "",
            prediction=prediction if prediction else "",
            metrics={
                "llm_judge_falloesung": normalized_score,
                "llm_judge_falloesung_raw": total_score,
                "llm_judge_falloesung_grade_points": result.get("grade_points", 0),
                "llm_judge_falloesung_passed": 1.0 if result.get("passed") else 0.0,
                "llm_judge_falloesung_details": result,
            },
            passed=result.get("passed", False),
        )
        db.add(eval_record)
        db.commit()
        logger.info(f"[Falloesung Celery] Persisted TaskEvaluation {evaluation_record_id}")

        return {
            "status": "completed",
            "evaluation_record_id": evaluation_record_id,
            "result": result,
            "total_score": total_score,
            "grade_points": result.get("grade_points", 0),
            "passed": result.get("passed", False),
        }

    except Exception as e:
        logger.error(f"[Falloesung Celery] Task failed: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


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

    db = SessionLocal()
    try:
        from models import EvaluationRun, TaskEvaluation

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
            },
            metrics={},
        )
        db.add(eval_run)
        db.flush()

        results = []

        for eval_cfg in evaluation_configs:
            metric_type = eval_cfg.get("metric", "")
            pred_fields = eval_cfg.get("prediction_fields", [])
            ref_fields = eval_cfg.get("reference_fields", [])
            metric_params = eval_cfg.get("metric_parameters", {})

            # Extract prediction and reference values
            prediction_value = None
            reference_value = None

            for pf in pred_fields:
                if pf in annotation_results:
                    prediction_value = annotation_results[pf]
                    break

            for rf in ref_fields:
                if rf.startswith("task."):
                    data_field = rf[5:]
                    reference_value = task_data.get(data_field) if task_data else None
                elif rf in task_data:
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
                    # Delegate to falloesung-specific logic
                    result = _evaluate_falloesung_single(
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
                    )
                    results.append(result)

                elif metric_type.startswith("llm_judge_"):
                    # Other LLM judge metrics — use LLMJudgeEvaluator
                    result = _evaluate_llm_judge_single(
                        db=db,
                        record_id=record_id,
                        immediate_eval_id=dispatch_eval_id,
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
                    )
                    results.append(result)

                else:
                    # Deterministic metrics — use SampleEvaluator with real implementations
                    from ml_evaluation.sample_evaluator import SampleEvaluator

                    field_configs = {field_name: {"type": "text"}}
                    param_configs = {field_name: {metric_type: metric_params}} if metric_params else {}
                    evaluator = SampleEvaluator(record_id, field_configs, param_configs)

                    score = evaluator._compute_metric(
                        metric_name=metric_type,
                        ground_truth=reference_value,
                        prediction=prediction_value,
                        answer_type="text",
                        parameters=metric_params or None,
                    )

                    eval_record = TaskEvaluation(
                        id=record_id,
                        evaluation_id=dispatch_eval_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        generation_id=None,
                        field_name=field_name,
                        answer_type="text",
                        ground_truth=str(reference_value) if reference_value else "",
                        prediction=str(prediction_value) if prediction_value else "",
                        metrics={
                            metric_type: float(score),
                            "raw_score": float(score),
                        },
                        passed=float(score) >= 0.5,
                    )
                    db.add(eval_record)
                    db.commit()

                    results.append({
                        "status": "completed",
                        "record_id": record_id,
                        "metric": metric_type,
                        "score": float(score),
                    })

            except Exception as e:
                logger.error(f"[SingleSampleEval] {metric_type} failed: {e}")
                _persist_immediate_eval_error(
                    db, record_id, project_id, task_id,
                    annotation_id, user_id or "system", field_name,
                    str(reference_value) if reference_value else "",
                    str(prediction_value) if prediction_value else "",
                    str(e),
                    eval_run_id=dispatch_eval_id,
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


def _evaluate_falloesung_single(
    db, record_id, immediate_eval_id, project_id, task_id,
    annotation_id, user_id, field_name, prediction, task_data,
    metric_params, organization_id,
):
    """Run Falllösung LLM judge evaluation for a single sample."""
    import time

    from falloesung_constants import (
        FALLOESUNG_PROMPT_TEMPLATE,
        FALLOESUNG_SYSTEM_PROMPT,
        parse_falloesung_response,
    )
    from models import TaskEvaluation

    params = metric_params or {}
    judge_model = params.get("judge_model", "gpt-4o")
    temperature = params.get("temperature", 0.0)
    max_tokens = params.get("max_tokens", 4096)
    thinking_budget = params.get("thinking_budget")
    reasoning_effort = params.get("reasoning_effort")

    sachverhalt = _get_insensitive(task_data, "sachverhalt") if task_data else ""
    musterloesung = ""
    if task_data:
        musterloesung = str(
            _get_insensitive(task_data, "musterloesung")
            or _get_insensitive(task_data, "musterlösung")
            or ""
        )

    provider = _get_provider_from_model(judge_model)

    if not HAS_AI_SERVICES:
        raise RuntimeError("AI services not available")

    ai_service = user_aware_ai_service.get_ai_service_for_user(
        db, user_id, provider, organization_id=organization_id
    )
    if ai_service is None:
        raise RuntimeError(f"No API key found for provider '{provider}'")

    prompt = FALLOESUNG_PROMPT_TEMPLATE.format(
        context=sachverhalt or "(Kein Sachverhalt angegeben)",
        ground_truth=musterloesung or "(Keine Musterlösung angegeben)",
        prediction=prediction or "(Keine Studierendenlösung angegeben)",
    )

    result = None
    for attempt in range(3):
        try:
            extra_kwargs = {}
            if thinking_budget:
                extra_kwargs["thinking_budget"] = thinking_budget
            if reasoning_effort:
                extra_kwargs["reasoning_effort"] = reasoning_effort

            response = ai_service.generate(
                prompt=prompt,
                system_prompt=FALLOESUNG_SYSTEM_PROMPT,
                model_name=judge_model,
                max_tokens=max_tokens,
                temperature=temperature,
                **extra_kwargs,
            )

            if not response.get("success"):
                continue

            content = response.get("content", "")
            result = parse_falloesung_response(content)
            if result is not None:
                break
        except Exception as e:
            logger.warning(f"[Falloesung] Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(1 * (attempt + 1))

    if result is None:
        raise RuntimeError("All Falllösung evaluation attempts failed")

    total_score = result.get("score", 0)
    normalized_score = total_score / 100.0

    eval_record = TaskEvaluation(
        id=record_id,
        evaluation_id=immediate_eval_id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=None,
        field_name=field_name,
        answer_type="long_text",
        ground_truth=musterloesung,
        prediction=prediction,
        metrics={
            "llm_judge_falloesung": normalized_score,
            "llm_judge_falloesung_raw": total_score,
            "llm_judge_falloesung_grade_points": result.get("grade_points", 0),
            "llm_judge_falloesung_passed": 1.0 if result.get("passed") else 0.0,
            "llm_judge_falloesung_details": result,
        },
        passed=result.get("passed", False),
    )
    db.add(eval_record)
    db.commit()

    return {
        "status": "completed",
        "record_id": record_id,
        "metric": "llm_judge_falloesung",
        "score": normalized_score,
        "grade_points": result.get("grade_points", 0),
        "passed": result.get("passed", False),
    }


def _evaluate_llm_judge_single(
    db, record_id, immediate_eval_id, project_id, task_id,
    annotation_id, user_id, field_name, metric_type, prediction,
    reference, metric_params, organization_id,
):
    """Run generic LLM judge evaluation for a single sample."""
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from models import TaskEvaluation

    params = metric_params or {}
    judge_model = params.get("judge_model", "gpt-4o")
    provider = _get_provider_from_model(judge_model)

    llm_judge = create_llm_judge_for_user(
        db=db,
        user_id=user_id,
        provider=provider,
        judge_model=judge_model,
        temperature=params.get("temperature", 0.0),
        max_tokens=params.get("max_tokens", 500),
        criteria=params.get("dimensions"),
        custom_criteria=params.get("custom_criteria"),
        custom_prompt_template=params.get("custom_prompt_template"),
        answer_type=params.get("answer_type"),
        field_mappings=params.get("field_mappings"),
        score_scale=params.get("score_scale", "1-5"),
        organization_id=organization_id,
    )

    if not llm_judge.ai_service:
        raise RuntimeError(f"No AI service available for LLM judge ({provider})")

    result = llm_judge.evaluate_single(
        prediction=prediction,
        reference=reference,
    )

    score = result.get("overall_score", 0.0)
    eval_record = TaskEvaluation(
        id=record_id,
        evaluation_id=immediate_eval_id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=None,
        field_name=field_name,
        answer_type="text",
        ground_truth=reference,
        prediction=prediction,
        metrics={
            metric_type: float(score),
            f"{metric_type}_details": result,
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
