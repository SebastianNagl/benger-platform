"""
Evaluations API router - modular structure.

This module aggregates all evaluation-related endpoints into sub-routers:
- status: Evaluation status, SSE streaming, evaluation types
- config: Configuration management
- human: Human evaluation sessions (Likert, preference)
- results: Results, per-sample analysis, export, immediate evaluation
- multi_field: Evaluation run endpoints (N:M field mapping)
- metadata: Evaluated models, configured methods, history, significance, statistics
- validation: Configuration validation
"""

from fastapi import APIRouter

# Import all sub-routers
from routers.evaluations import (
    config,
    human,
    metadata,
    multi_field,
    results,
    status,
    validation,
)

# Create main router with prefix
router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

# Include all sub-routers
# Order matters for route matching - more specific routes first

# Status, types, and SSE streaming
router.include_router(status.router)

# Configuration management
router.include_router(config.router)

# Human evaluation sessions
router.include_router(human.router)

# Results and analysis
router.include_router(results.router)

# Evaluation run endpoints
router.include_router(multi_field.router)

# Metadata, statistics, significance
router.include_router(metadata.router)

# Configuration validation
router.include_router(validation.router)

# Backward-compatible re-exports for test files that import from routers.evaluations directly
from auth_module import require_user  # noqa: F401 - re-exported for test dependency overrides
from routers.evaluations.helpers import extract_metric_name, get_evaluation_types_for_task_type
