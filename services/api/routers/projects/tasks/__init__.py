"""Task management endpoints (package).

Split from the former single-module ``routers/projects/tasks.py``. The router
and shared helpers live in ``_common``; handlers are grouped by concern into
submodules. Every handler and the public ``extract_fields_from_data`` helper are
re-exported here so ``from routers.projects.tasks import X`` and
``routers.projects.tasks.X`` continue to resolve exactly as before.
"""

from ._common import (  # noqa: F401
    router,
    check_project_accessible,
    check_task_assigned_to_user,
    check_user_can_edit_project,
    check_user_can_edit_task_data,
    get_org_context_from_request,
    get_user_with_memberships,
)

from . import (  # noqa: F401
    export,
    fields,
    listing,
    metadata_ops,
    mutations,
)

# Re-export handlers by name so existing imports/patches keep resolving.
from .listing import (  # noqa: F401
    get_next_task,
    get_task,
    list_project_tasks,
)
from .metadata_ops import (  # noqa: F401
    bulk_update_task_metadata,
    update_task_metadata,
)
from .mutations import (  # noqa: F401
    bulk_archive_tasks,
    bulk_delete_tasks,
    skip_task,
    update_task_data,
)
from .export import (  # noqa: F401
    bulk_export_tasks,
)
from .fields import (  # noqa: F401
    SENSITIVE_FIELD_PATTERNS,
    extract_fields_from_data,
    get_task_data_fields,
)

__all__ = [
    "router",
    "check_project_accessible",
    "check_task_assigned_to_user",
    "check_user_can_edit_project",
    "check_user_can_edit_task_data",
    "get_org_context_from_request",
    "get_user_with_memberships",
    "list_project_tasks",
    "get_next_task",
    "get_task",
    "update_task_metadata",
    "bulk_update_task_metadata",
    "update_task_data",
    "bulk_delete_tasks",
    "bulk_archive_tasks",
    "skip_task",
    "bulk_export_tasks",
    "get_task_data_fields",
    "extract_fields_from_data",
    "SENSITIVE_FIELD_PATTERNS",
]
