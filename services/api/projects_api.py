"""
Backward-compatible shim for the old monolithic projects_api module.

The original projects_api.py was split into routers/projects/ submodules during
an architecture cleanup. This shim re-exports all public symbols so that existing
test files that import from `projects_api` (or patch `projects_api.X`) continue
to work without modification.

NOTE: This file exists solely for backward compatibility with tests.
New code should import directly from the routers/projects/ submodules.
"""

import uuid  # noqa: F401 -- tests patch projects_api.uuid.uuid4

from sqlalchemy.orm import Session  # noqa: F401 -- tests patch projects_api.Session

from auth_module import require_user  # noqa: F401 -- tests patch projects_api.require_user
from database import get_db  # noqa: F401 -- tests patch projects_api.get_db
from project_models import (  # noqa: F401 -- tests patch these model classes
    Annotation,
    ProjectOrganization,
    Task,
)

# ---------------------------------------------------------------------------
# Re-exported helper functions (routers/projects/helpers.py)
# ---------------------------------------------------------------------------
from routers.projects.helpers import (  # noqa: F401
    calculate_generation_stats,
    calculate_project_stats_batch,
    get_comprehensive_project_data,
    get_project_organizations,
    get_user_with_memberships,
)

# ---------------------------------------------------------------------------
# Re-exported endpoint functions (routers/projects/import_export.py)
# ---------------------------------------------------------------------------
from routers.projects.import_export import import_project_data  # noqa: F401

# Alias: the function was renamed from import_data -> import_project_data.
# Tests still reference the old name.
import_data = import_project_data

# ---------------------------------------------------------------------------
# Re-exported endpoint functions (routers/projects/tasks.py)
# ---------------------------------------------------------------------------
from routers.projects.tasks import get_next_task  # noqa: F401
