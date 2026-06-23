"""
Evaluation run endpoints (N:M field mapping).

This package was split out of a single ``multi_field.py`` module. The
public surface is unchanged: ``from routers.evaluations.multi_field import
router`` still yields the same router with the same six routes, and every
handler / helper / model is re-exported here so existing
``from routers.evaluations.multi_field import <name>`` imports (including
the ``inspect.getsource`` source-pinned tests) keep resolving.

Submodule layout:
- ``_common``  — shared imports, ``router``, all request/response models
- ``run``      — POST /run                         (run_evaluation)
- ``cancel``   — POST /run/{id}/cancel + cancel-all (_cancel_runs + handlers)
- ``fields``   — GET  /projects/{id}/available-fields
- ``results``  — GET  /run/results/...             (+ _resolve_scope_block)
"""

from ._common import (  # noqa: F401
    router,
    logger,
    EvaluationConfigItem,
    EvaluationRunRequest,
    EvaluationRunResponse,
    AvailableFieldsResponse,
    CancelEvaluationResponse,
)

# Importing the submodules registers their handlers onto the shared
# ``router`` (via the ``@router.<method>`` decorators) at import time.
from . import run  # noqa: F401,E402
from . import cancel  # noqa: F401,E402
from . import fields  # noqa: F401,E402
from . import results  # noqa: F401,E402

# Re-export handlers + helpers by name so direct imports keep working.
from .run import run_evaluation  # noqa: F401,E402
from .cancel import (  # noqa: F401,E402
    _cancel_runs,
    cancel_evaluation_run,
    cancel_all_project_evaluations,
)
from .fields import get_available_fields  # noqa: F401,E402
from .results import (  # noqa: F401,E402
    _resolve_scope_block,
    get_project_evaluation_results,
    get_evaluation_run_results,
)

__all__ = [
    "router",
    "logger",
    "EvaluationConfigItem",
    "EvaluationRunRequest",
    "EvaluationRunResponse",
    "AvailableFieldsResponse",
    "CancelEvaluationResponse",
    "run_evaluation",
    "_cancel_runs",
    "cancel_evaluation_run",
    "cancel_all_project_evaluations",
    "get_available_fields",
    "_resolve_scope_block",
    "get_project_evaluation_results",
    "get_evaluation_run_results",
]
