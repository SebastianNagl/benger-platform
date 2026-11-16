"""JSON shape of a ``rubric_generation_jobs`` row (Bewertungsbogen generation job).

One serializer for every reader: the platform superadmin list
(``GET /api/admin/rubric-generation-jobs``, ``routers/rubric_generation_jobs_admin.py``)
and the extended per-task read in its Bewertungsbogen router. Every column of
:class:`project_models.RubricGenerationJob` is returned as stored (datetimes
as ISO 8601 with offset, ``attempt_errors`` and ``details`` as JSON), plus the
display fields the caller joined; those are ``None`` when the row or the join
is gone (projects, tasks, users and organizations are ``SET NULL``).

Pure (attribute access only), safe for the api and the workers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from project_models import RubricGenerationJob

#: Column names in table order, the keys of a serialized job besides the
#: display fields.
RUBRIC_GENERATION_JOB_COLUMNS = tuple(c.name for c in RubricGenerationJob.__table__.columns)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_rubric_generation_job(
    job: Any,
    *,
    project_title: Optional[str] = None,
    task_inner_id: Optional[int] = None,
    user_label: Optional[str] = None,
    organization_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Every column of ``job`` as JSON, plus ``project_title``,
    ``task_inner_id``, ``user_label`` (who started it, as the caller may show
    them) and ``organization_name``."""
    out = {name: _json_value(getattr(job, name, None)) for name in RUBRIC_GENERATION_JOB_COLUMNS}
    out.update(
        project_title=project_title,
        task_inner_id=task_inner_id,
        user_label=user_label,
        organization_name=organization_name,
    )
    return out
