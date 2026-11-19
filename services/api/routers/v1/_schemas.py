"""Response models of the public API (they define /api/v1/openapi.json).

Field additions are non-breaking; removing or renaming a field needs a new
API version (docs/public-api.md, "Versioning").
"""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(_Model):
    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable explanation (English)")
    request_id: Optional[str] = Field(None, description="Echoes the X-Request-ID header")
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(_Model):
    error: ErrorBody


class Page(_Model, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = Field(
        None, description="Cursor of the next page; null on the last page"
    )


class OrganizationRef(_Model):
    id: str
    name: str
    slug: str


class GroupRef(_Model):
    id: str
    name: str


class RateLimit(_Model):
    per_minute: Optional[int] = None
    per_day: Optional[int] = None


class PrincipalOut(_Model):
    kind: Literal["session", "api_key"]
    key_prefix: Optional[str] = None
    scopes: List[str] = Field(
        ..., description='Granted scopes including implied ones; ["*"] for a session'
    )
    project_ids: Optional[List[str]] = Field(
        None, description="Project allowlist of the key; null means no allowlist"
    )
    organization: Optional[OrganizationRef] = None
    group: Optional[GroupRef] = None
    expires_at: Optional[str] = None
    rate_limit: RateLimit


class UserOut(_Model):
    id: str
    username: str
    name: Optional[str] = None
    is_service_account: bool = False


class MeResponse(_Model):
    principal: PrincipalOut
    user: UserOut


class AnswerField(_Model):
    name: str
    type: str
    to_name: Optional[str] = None
    options: Optional[List[str]] = None


class ProjectAccessOut(_Model):
    tier: str = Field(..., description="full, participant or attempted")
    effective_role: Optional[str] = Field(
        None, description="ORG_ADMIN, CONTRIBUTOR, ANNOTATOR or null"
    )
    blinded: bool = Field(
        ..., description="Whether task data is reduced to the label-config-bound fields"
    )


class ProjectOut(_Model):
    id: str
    title: str
    description: Optional[str] = None
    kind: Optional[str] = None
    task_count: int
    bound_fields: List[str] = Field(
        ..., description="task.data keys the label config renders (always visible)"
    )
    answer_fields: List[AnswerField] = Field(
        ..., description="Fields of the label config that take an answer"
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    access: ProjectAccessOut


class TaskOut(_Model):
    id: str
    inner_id: int
    data: Any = Field(
        ..., description="task.data; reduced to bound_fields when the project is blinded"
    )
    meta: Any = Field(
        None,
        description="task.meta; blinded callers get only tags and public benchmark descriptors",
    )
    updated_at: Optional[str] = None


class ExportCreate(_Model):
    format: Literal[
        "json", "ndjson", "ndjson_gz", "csv", "tsv", "comprehensive", "label_studio"
    ] = "json"
    task_ids: Optional[List[str]] = Field(
        None, description="Restrict the export to these tasks (json format only)"
    )


class ExportJobOut(_Model):
    id: str
    project_id: str
    format: Optional[str] = None
    status: str
    progress: Optional[int] = None
    byte_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None
    download_url: Optional[str] = Field(
        None, description="Path of the download endpoint once the job completed"
    )


class AnalysisRunOut(_Model):
    id: str
    project_id: str
    name: str
    status: str = Field(..., description="pending, running, completed or failed")
    spec_hash: str = Field(..., description="SHA-256 of the normalized spec")
    spec_version: int
    engine_version: str
    frame_hash: Optional[str] = Field(None, description="Content hash of the frame the run read")
    frame_rows: Optional[int] = None
    estimates_count: int
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class AnalysisRunDetailOut(AnalysisRunOut):
    normalized_spec: Dict[str, Any] = Field(
        ..., description="The spec with every default and inference convention filled in"
    )
    frame_sha256: Optional[str] = Field(None, description="SHA-256 of the stored Parquet snapshot")
    frame_counts: Optional[Dict[str, Any]] = None
    library_versions: Optional[Dict[str, Any]] = None
    lockfile_sha256: Optional[str] = None
    seed: Optional[int] = None
    fits: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[str]] = None


class AnalysisEstimateOut(_Model):
    position: int
    estimand_id: str
    contrast_id: Optional[str] = None
    estimator: str
    kind: str = Field(..., description="linear or ratio")
    outcome: str
    scope: str = Field(..., description='"pooled" or "<column>=<value>[|...]"')
    scope_values: Optional[Dict[str, Any]] = None
    status: str = Field(
        ..., description="ok, degenerate, negative_variance, not_estimable or error"
    )
    message: Optional[str] = None
    estimate: Optional[float] = None
    std_error: Optional[float] = None
    statistic: Optional[float] = None
    df: Optional[int] = None
    p_value: Optional[float] = None
    null_value: Optional[float] = None
    ci_level: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    equivalent: Optional[bool] = Field(
        None, description="Equivalence (TOST) result of the first bound set"
    )
    tost: Optional[List[Dict[str, Any]]] = None
    mde: Optional[Dict[str, Any]] = None
    ratio: Optional[Dict[str, Any]] = None
    family: Optional[str] = None
    p_adjusted: Optional[float] = Field(None, description="Adjusted p-value in `family`")
    adjustments: Optional[List[Dict[str, Any]]] = None
    n_obs: Optional[int] = None
    n_clusters: Optional[List[int]] = None
    k_params: Optional[int] = None
    conventions: Optional[Dict[str, Any]] = None


ERROR_RESPONSES: Dict[int, Dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "Missing, invalid, expired or revoked key"},
    403: {"model": ErrorEnvelope, "description": "Insufficient scope or role"},
    429: {"model": ErrorEnvelope, "description": "Rate limit exceeded"},
}
