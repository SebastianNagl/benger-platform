"""
Evaluation metadata, statistics, and significance endpoints.

This package was split from a single ``metadata.py`` module. The public
import surface is preserved: ``from routers.evaluations.metadata import router``
yields the same ``APIRouter`` with the same five routes, and every handler /
Pydantic model is re-exported at the package level so existing
``from routers.evaluations.metadata import <name>`` imports and
``routers.evaluations.metadata.<name>`` attribute access keep resolving.
"""

from ._common import (
    router,
    StatisticsRequest,
    MetricStatistics,
    PairwiseComparison,
    ModelStatistics,
    FieldStatistics,
    RawScore,
    RunsAggregate,
    TaskConsistency,
    JudgeAgreement,
    PerRunMean,
    StatisticsResponse,
    # Shared infra re-exported for completeness / back-compat patch targets.
    check_project_accessible,
    get_org_context_from_request,
    logger,
)

# Import the concern submodules so their @router decorators register the
# routes onto the shared `router` instance.
from . import models_methods  # noqa: E402
from . import history  # noqa: E402
from . import significance  # noqa: E402
from . import statistics  # noqa: E402

# Re-export the handlers by name so callers that did
# `from routers.evaluations.metadata import get_evaluated_models` (and the
# attribute-access equivalent) keep working.
from .models_methods import (  # noqa: E402
    get_evaluated_models,
    get_configured_methods,
)
from .history import get_evaluation_history  # noqa: E402
from .significance import get_significance_tests  # noqa: E402
from .statistics import compute_project_statistics  # noqa: E402

__all__ = [
    "router",
    # Handlers
    "get_evaluated_models",
    "get_configured_methods",
    "get_evaluation_history",
    "get_significance_tests",
    "compute_project_statistics",
    # Pydantic models
    "StatisticsRequest",
    "MetricStatistics",
    "PairwiseComparison",
    "ModelStatistics",
    "FieldStatistics",
    "RawScore",
    "RunsAggregate",
    "TaskConsistency",
    "JudgeAgreement",
    "PerRunMean",
    "StatisticsResponse",
    # Shared infra
    "check_project_accessible",
    "get_org_context_from_request",
    "logger",
]
