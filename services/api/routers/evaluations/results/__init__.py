"""
Evaluation results package.

Split from the former single-file ``routers/evaluations/results.py`` into a
package. Submodules register their handlers on the shared ``router`` instance
defined in ``_common``; importing the submodules below performs that
registration. The ``router`` is then re-exported (along with every handler and
helper) so existing imports keep working:

    from routers.evaluations.results import router
    from routers.evaluations.results import get_evaluation_results, _extract_primary_score

Submodule layout:
- ``core``           — list results, export, per-sample listing
- ``distributions``  — metric distribution, confusion matrix
- ``by_task_model``  — by-task-model, project aggregation, sample-result
"""

# Shared instance + helpers
from ._common import (  # noqa: F401
    router,
    logger,
    check_project_accessible,
    get_org_context_from_request,
    _METRIC_METADATA_SUFFIXES,
    _coerce_metric_value,
    _extract_primary_score,
)

# Import submodules to register their handlers on `router`.
from . import core  # noqa: F401,E402
from . import distributions  # noqa: F401,E402
from . import by_task_model  # noqa: F401,E402

# Re-export handlers + local helpers by name so
# `from routers.evaluations.results import X` and
# `routers.evaluations.results.X` keep resolving.
from .core import (  # noqa: F401,E402
    get_evaluation_results,
    export_evaluation_results,
    get_evaluation_samples,
)
from .distributions import (  # noqa: F401,E402
    get_metric_distribution,
    get_confusion_matrix,
)
from .by_task_model import (  # noqa: F401,E402
    get_results_by_task_model,
    get_project_results_by_task_model,
    get_sample_result_by_task_model,
    _get_task_data_availability,
    _task_preview_rows,
    _build_all_tasks_response,
)
