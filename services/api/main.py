"""
BenGER API v3.0.1 - Refactored with Router Architecture
Main application file with clean separation of concerns.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add shared directory to path for AI services
shared_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"
)
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)

# Centralized configuration
from app.core.config import get_settings

settings = get_settings()
ENVIRONMENT = settings.environment

# Centralized Celery client for task dispatch
from celery_client import get_celery_app

celery_app = get_celery_app()


_STARTUP_INIT_FLAG = "/tmp/.benger_startup_init_done"
_LLM_SEED_FLAG_DIR = "/tmp"  # files: .benger_llm_seed_<hash8>.done


def _seed_llm_models_if_changed(db) -> None:
    """Re-run the LLM model seed iff llm_models.yaml content hash changed.

    Each content hash gets its own flag file in /tmp; an unchanged YAML
    means the flag for that hash already exists and we skip. Editing the
    YAML produces a new hash and forces the seed to re-run on next startup.

    Failures here propagate — the API should not boot reporting healthy
    when the model catalog seed silently failed.
    """
    import glob
    from database import initialize_llm_models
    from seeds.llm_models_loader import load_catalog

    catalog = load_catalog()
    short_hash = catalog.content_hash[:8]
    flag = f"{_LLM_SEED_FLAG_DIR}/.benger_llm_seed_{short_hash}.done"

    if os.path.exists(flag):
        logger.info("LLM seed v%s already applied — skipping", short_hash)
        return

    # Clean up flags for previous catalog versions so /tmp doesn't accumulate
    for stale in glob.glob(f"{_LLM_SEED_FLAG_DIR}/.benger_llm_seed_*.done"):
        try:
            os.remove(stale)
        except OSError:
            pass

    initialize_llm_models(db)  # logs its own one-line summary
    try:
        with open(flag, "w") as f:
            f.write(catalog.content_hash)
    except OSError as e:
        logger.warning("Could not write LLM seed flag %s: %s", flag, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    from app.core.schema_validator import ValidationMode, create_validator_from_env
    from auth_module import initialize_database
    from database import (
        SessionLocal,
        initialize_task_types_and_evaluation_types,
    )
    from websocket_clustering import cluster_manager

    is_reload = os.path.exists(_STARTUP_INIT_FLAG)

    # Skip database initialization in test mode
    if not settings.testing:
        if is_reload:
            logger.info("Hot-reload detected - skipping heavy initialization")
            database_available = True
        else:
            logger.info("Initializing database...")

            # Add robust error handling for database connection
            database_available = False
            try:
                # Use Alembic for database migrations instead of create_all()
                from sqlalchemy import create_engine

                from alembic import command
                from alembic.config import Config
                from alembic.runtime.migration import MigrationContext

                # Run migrations
                alembic_cfg = Config("/app/alembic.ini")
                alembic_cfg.set_main_option(
                    "sqlalchemy.url",
                    settings.database_url,
                )

                try:
                    # Check current revision
                    engine = create_engine(
                        settings.database_url
                    )

                    with engine.connect() as conn:
                        context = MigrationContext.configure(conn)
                        current_rev = context.get_current_revision()

                    if current_rev is None:
                        logger.info("No migrations found, running initial setup...")
                        command.upgrade(alembic_cfg, "head")
                        logger.info("Database schema created via Alembic migrations")
                    else:
                        logger.info(f"Current migration: {current_rev}")
                        # Check if we need to upgrade
                        command.upgrade(alembic_cfg, "head")
                        logger.info("Database migrations up to date")

                except Exception as migration_error:
                    logger.warning(f"Migration error (non-fatal): {migration_error}")
                    # Don't fail startup if migrations have issues - log and continue

                logger.info("Database connection established")
                database_available = True

                # Perform schema validation
                logger.info("Validating database schema...")
                validator = create_validator_from_env()
                validation_result = validator.validate()

                if validation_result.is_valid:
                    logger.info(validation_result.get_summary())
                else:
                    logger.info(validation_result.get_summary())
                    for error in validation_result.errors:
                        logger.error(f"  {error}")
                    for warning in validation_result.warnings:
                        logger.warning(f"  {warning}")

                    # In strict mode, refuse to start with schema errors
                    if validator.mode == ValidationMode.STRICT and not validation_result.is_valid:
                        raise RuntimeError(
                            f"Schema validation failed with {len(validation_result.errors)} errors. "
                            "Set SCHEMA_VALIDATION_MODE=lenient to start anyway."
                        )

                # Check type consistency
                type_result = validator.check_type_consistency()
                if not type_result.is_valid:
                    logger.warning("Type consistency issues detected:")
                    for error in type_result.errors:
                        logger.error(f"  {error}")

                # Check migration history
                migration_result = validator.check_migration_history()
                if not migration_result.is_valid:
                    logger.warning("Migration history issues detected:")
                    for error in migration_result.errors:
                        logger.error(f"  {error}")

            except RuntimeError:
                raise  # Re-raise schema validation errors
            except Exception as db_init_error:
                logger.error(f"Database initialization failed: {db_init_error}")
                logger.warning("API will start but database-dependent features may not work")
    else:
        logger.info("Test mode detected - skipping database initialization")
        database_available = False

    if database_available and not is_reload:
        # Initialize demo users and task types/evaluation types
        db = SessionLocal()
        try:
            initialize_database(db)
            initialize_task_types_and_evaluation_types(db)
            logger.info("Database initialization complete!")

            # Initialize database performance optimizations
            try:
                from database_optimization import DatabaseOptimizer

                from database import engine

                DatabaseOptimizer.create_missing_indexes(engine)
                logger.info("Database performance optimizations applied")
            except Exception as opt_error:
                logger.warning(f"Database optimization warning: {opt_error}")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
        finally:
            db.close()

    # LLM model seed runs on EVERY startup but is gated by the YAML content
    # hash, so it only does work when llm_models.yaml has actually changed.
    # Intentionally not wrapped in try/except: a failed seed must surface.
    if database_available and not settings.testing:
        db = SessionLocal()
        try:
            _seed_llm_models_if_changed(db)
        finally:
            db.close()

    # Mark init as done so subsequent hot-reloads skip heavy initialization
    if not settings.testing and not is_reload:
        try:
            with open(_STARTUP_INIT_FLAG, "w") as f:
                f.write("1")
        except OSError:
            pass

    # Initialize WebSocket clustering (skip in test mode)
    if not settings.testing:
        try:
            await asyncio.wait_for(cluster_manager.initialize(), timeout=10.0)
            logger.info("WebSocket clustering initialized")
        except asyncio.TimeoutError:
            logger.warning("WebSocket clustering timed out after 10s (single-instance mode)")
        except Exception as e:
            logger.warning(f"WebSocket clustering initialization failed: {e}")
            logger.info("   (Single-instance WebSocket mode will be used)")
    else:
        logger.info("⏭️  WebSocket clustering skipped (test mode)")

    # Log FRONTEND_URL configuration for verification
    logger.info(f"📧 Email verification configured with FRONTEND_URL: {settings.frontend_url}")
    if settings.frontend_url == "http://localhost:3000" and settings.is_production:
        logger.warning(
            "⚠️  WARNING: FRONTEND_URL is using default value in production environment!"
        )

    logger.info("🚀 API startup complete - server is ready to accept requests")

    yield

    # Shutdown
    # Note: reload flag in /tmp persists within the container but is cleared
    # on container recreation (docker-compose down + up)
    logger.info("Shutting down BenGER API...")


# Create FastAPI app
app = FastAPI(
    title="BenGER API",
    description="""
    ## BenGER - Comprehensive LLM Evaluation Framework for German Legal Domain

    BenGER (Benchmark for German Legal Reasoning) provides a complete evaluation platform for Large Language Models 
    in the German legal domain. It features:

    ### 🏗️ **Core Features**
    - **Native Annotation System**: Self-contained annotation with real-time collaboration
    - **Multi-task Support**: QA, QAR, and human evaluation workflows  
    - **LLM Integration**: Support for OpenAI, Anthropic, Google, and DeepInfra models
    - **Organization Management**: Multi-organization support for collaborative research
    - **Advanced Analytics**: Performance metrics, quality control, and benchmarking

    ### 🔐 **Authentication**
    - JWT-based authentication with refresh tokens
    - Role-based access control (superadmin, org_admin, contributor, annotator, user)
    - Organization-scoped permissions

    ### 📊 **Project Management**
    - Universal template system for flexible task configuration
    - Batch processing and bulk operations
    - Real-time status tracking and notifications
    - Export/import in multiple formats (JSON, CSV, XML, TSV)

    ### 🎯 **Annotation Workflows**
    - Native annotation system with WebSocket real-time collaboration
    - Quality control with inter-annotator agreement metrics
    - Multi-stage approval processes
    - Comprehensive version control and audit trails

    **Version**: 3.0.1 (Refactored Architecture)  
    **Environment**: {environment}
    """.format(
        environment=ENVIRONMENT
    ),
    version=settings.api_version,
    lifespan=lifespan,
    root_path=settings.api_root_path,
)

# Configure CORS with regex to support wildcard subdomains
# Matches: benger.localhost, *.benger.localhost, what-a-benger.net, *.what-a-benger.net, localhost:*
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(([a-z0-9-]+\.)?benger\.localhost|([a-z0-9-]+\.)?what-a-benger\.net|localhost(:\d+)?)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization", "X-Organization-Context", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["Content-Length"],
)

# Organization context resolution middleware (resolves X-Organization-Slug to org ID)
from middleware.org_context import OrgContextMiddleware

app.add_middleware(OrgContextMiddleware)


# Reject obviously oversized request bodies before they consume backend
# memory. Legal-corpus imports legitimately need tens of megabytes (the
# zjs.json corpus is 22 MB / 562 cases); cap is set well above that so
# normal use is unaffected. A hostile or buggy client sending GBs of JSON
# would otherwise OOM the API container before any router code runs.
_MAX_BODY_BYTES = 100 * 1024 * 1024  # 100 MB

@app.middleware("http")
async def reject_oversized_requests(request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _MAX_BODY_BYTES:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body exceeds the {_MAX_BODY_BYTES // (1024 * 1024)} MB "
                            "limit. For very large data imports, split the payload into "
                            "smaller batches and POST each batch separately."
                        )
                    },
                )
        except ValueError:
            pass
    return await call_next(request)

# Import and include routers

# Other routers
from routers.api_keys import router as api_key_router
from routers.feature_flags import router as feature_flags_router
from routers.file_uploads import router as file_upload_router
from routers.invitations import router as invitations_router
from routers.org_api_keys import router as org_api_key_router
from routers.organizations import router as organizations_router

# Core domain routers
from routers.auth import router as auth_router
from routers.dashboard import router as dashboard_router

# Utility routers
from routers.evaluations import router as evaluations_router
from routers.generation import router as generation_router
from routers.generation import ws_router as generation_ws_router
from routers.generation_task_list import router as generation_task_list_router
from routers.health import router as health_router
from routers.leaderboards import router as leaderboards_router

# Legacy routers
from routers.legacy.debug import router as debug_router
from routers.llm_models import router as llm_models_router
from routers.notifications import router as notifications_router
from routers.projects import router as projects_router
from routers.prompt_structures import router as prompt_structures_router
from routers.reports import router as reports_router
from routers.storage import router as storage_router
from routers.tasks import router as tasks_router

# Test seeding router (only active in test/dev environments)
# Test seeding endpoints (guarded by environment check + superadmin auth)
from routers.test_seeding import router as test_seeding_router

from routers.users import router as users_router

# Include all routers
app.include_router(health_router)  # Health checks first
app.include_router(auth_router)  # Auth endpoints
app.include_router(users_router)  # User management
app.include_router(dashboard_router)  # Dashboard statistics
app.include_router(tasks_router)  # Global tasks management
app.include_router(evaluations_router)  # Evaluation endpoints
app.include_router(reports_router)  # Report publishing (Issue #770)
app.include_router(llm_models_router)  # LLM models
app.include_router(generation_router)  # Generation and prompts
app.include_router(generation_ws_router)  # WebSocket for generation progress updates
app.include_router(generation_task_list_router)  # Generation task list (Issue #495)
app.include_router(prompt_structures_router)  # Prompt structures (Issue #762)
app.include_router(storage_router)  # Storage and CDN
app.include_router(organizations_router)  # Organizations
app.include_router(invitations_router)  # Invitations
app.include_router(feature_flags_router)  # Feature flags
app.include_router(notifications_router)  # Notifications
app.include_router(debug_router)  # Debug endpoints
app.include_router(api_key_router)  # API key management
from routers.llm_models_admin import router as llm_models_admin_router
app.include_router(llm_models_admin_router)  # Superadmin: reseed/inspect llm catalog
app.include_router(org_api_key_router)  # Organization API key management (Issue #1180)
app.include_router(file_upload_router)  # File uploads
app.include_router(projects_router)  # Projects API
app.include_router(leaderboards_router)  # Leaderboards for annotation performance (Issue #790)
app.include_router(test_seeding_router)  # Test seeding endpoints (guarded by env check + superadmin)

# Load extended features if available
from extensions import load_extended, get_extended_routers

if load_extended():
    for router, kwargs in get_extended_routers():
        app.include_router(router, **kwargs)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to BenGER API",
        "version": "3.0.1",
        "environment": ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Default config endpoints (minimal implementation to avoid breaking UI)
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db


@app.get("/api/defaults/config/{task_type}")
async def get_default_config(
    task_type: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get default configuration for a specific task type.

    This endpoint provides temperature and other configuration defaults
    for the frontend to use as fallbacks.
    """
    # Validate task type
    valid_task_types = ["qa", "qa_reasoning", "multiple_choice", "generation"]
    if task_type not in valid_task_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task type. Must be one of: {', '.join(valid_task_types)}",
        )

    # Default config functionality has been removed
    # Return default config to avoid breaking the UI
    config = {
        "task_type": task_type,
        "temperature": 0,  # Default fallback
        "max_tokens": 500,  # Default fallback
        "generation_config": {"temperature": 0, "max_tokens": 500},
    }
    return config


@app.get("/api/defaults/config")
async def get_all_default_configs(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """
    Get default configurations for all task types.

    This endpoint provides temperature and other configuration defaults
    for all task types that the frontend can use.
    """
    # Default config functionality has been removed
    # Return default configs to avoid breaking the UI
    task_types = ["qa", "qa_reasoning", "multiple_choice", "generation"]
    configs = {}
    for task_type in task_types:
        configs[task_type] = {
            "task_type": task_type,
            "temperature": 0,  # Default fallback
            "max_tokens": 500,  # Default fallback
            "generation_config": {"temperature": 0, "max_tokens": 500},
        }
    return configs


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred",
            "type": type(exc).__name__,
            "message": str(exc) if ENVIRONMENT == "development" else "Internal server error",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
