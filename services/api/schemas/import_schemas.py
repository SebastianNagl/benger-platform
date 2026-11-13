"""Request and response shapes of the async project import API
(``routers/projects/import_export.py``): creating an import job and the job
a client polls.

A malformed body answers 400 like every other refused import option, not
FastAPI's 422 (see ``Coded400Route`` in the router).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

_MODEL_ID_MAP_DESCRIPTION = (
    "Model id in the export -> model id on this deployment. Custom models get "
    "a new id on every deployment, so their results only land under the right "
    "model through this map. Every target must already exist here."
)


class _ImportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_key: str = Field(
        ...,
        description="Key returned by the matching upload-url endpoint, after the file was uploaded to it",
    )
    model_id_map: Optional[Dict[str, str]] = Field(None, description=_MODEL_ID_MAP_DESCRIPTION)


class ProjectImportJobRequest(_ImportRequest):
    """Body of ``POST /api/projects/{project_id}/imports``."""

    mode: Literal["nested", "merge"] = Field(
        "nested",
        description=(
            "nested: the Project data page's task export, imported as new tasks. "
            "merge: a full project export of this project or a copy of it; only "
            "its generation and evaluation results this project does not hold "
            "yet are added (model_id_map applies to merge only)."
        ),
    )
    dry_run: bool = Field(
        False,
        description=(
            "merge only: preview the merge. The job runs the merge and rolls it "
            "back, writing nothing, and completes with format merge_preview; its "
            "result.statistics holds matched_tasks, added_counts, "
            "skipped_present_counts, models (every model id of the file, what it "
            "maps to and whether it exists here), unknown_models (ids a merge "
            "refuses until they are mapped) and available_models (models the "
            "caller may map to)."
        ),
    )


class FullImportJobRequest(_ImportRequest):
    """Body of ``POST /api/projects/project-imports`` (creates a new project)."""

    organization_id: Optional[str] = Field(
        None, description="Organization that will own the new project; without it the project is private"
    )
    organization_group_id: Optional[str] = Field(
        None, description="Attach the project through this group of organization_id"
    )


class ImportJobAccepted(BaseModel):
    job_id: str
    status: str


class ImportJobStatus(BaseModel):
    """An import job as its poll endpoint returns it."""

    job_id: str
    project_id: Optional[str] = Field(
        None, description="Set once the job created or targeted a project"
    )
    format: Optional[str] = None
    status: str = Field(..., description="pending, running, completed or failed")
    progress: Optional[int] = None
    byte_size: Optional[int] = None
    error_message: Optional[str] = None
    error_status: Optional[int] = Field(
        None, description="HTTP-style status of a refused import (400, 403, 404, 409, 413, 422)"
    )
    error_code: Optional[str] = Field(
        None,
        description=(
            "Stable token of a refused import a client can map to its own message, "
            "e.g. merge_task_mismatch, merge_unknown_models, task_export_not_project, "
            "import_too_large"
        ),
    )
    result: Optional[Dict[str, Any]] = Field(
        None, description="The importer's result: project_id, project_url and statistics"
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None


class ImportErrorBody(BaseModel):
    detail: Any = Field(
        ..., description="A message, or {code, message} for a refusal a client can map"
    )


IMPORT_ERROR_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    400: {"model": ImportErrorBody, "description": "Malformed body or refused option"},
    403: {"model": ImportErrorBody, "description": "No write access, or not allowed to import into the organization"},
    404: {"model": ImportErrorBody, "description": "Project or organization not found"},
    503: {"model": ImportErrorBody, "description": "Import queue unavailable, retry"},
}

# "<status>: <code>: message" or "<status>: message", as the worker records a
# refused import on the job row.
_ERROR_PREFIX = re.compile(r"^(\d{3}): (?:([a-z][a-z0-9_]*): )?")


def split_job_error(message: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """``(status, code)`` of a job's ``error_message``; ``(None, None)`` for a
    worker fault, which carries neither."""
    match = _ERROR_PREFIX.match(message or "")
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)
