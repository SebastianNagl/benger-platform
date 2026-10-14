"""Request and response shapes of the access-key management API
(``routers/access_keys.py``). The secret appears only in
:class:`AccessKeyCreated`, once."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_PROJECT_IDS = 500


class _KeyFields(BaseModel):
    project_ids: Optional[List[str]] = Field(
        None,
        description="Projects the key may see; null = every project its principal can see",
        max_length=MAX_PROJECT_IDS,
    )
    expires_at: Optional[datetime] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=100_000)
    rate_limit_per_day: Optional[int] = Field(None, ge=1, le=100_000_000)


class AccessKeyCreate(_KeyFields):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: List[str] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class OrgAccessKeyCreate(AccessKeyCreate):
    org_role: Literal["ANNOTATOR", "CONTRIBUTOR"] = "ANNOTATOR"
    group_id: Optional[str] = None


class AccessKeyUpdate(_KeyFields):
    """Only the fields sent are changed; an explicit null clears
    ``project_ids``, ``expires_at`` or a limit."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)


class AccessKeyRevoke(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class AccessKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    owner_type: str
    user_id: str
    organization_id: Optional[str] = None
    group_id: Optional[str] = None
    org_role: Optional[str] = None
    scopes: List[str]
    project_ids: Optional[List[str]] = None
    environment: str
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoke_reason: Optional[str] = None
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_day: Optional[int] = None
    created_by: str
    created_at: Optional[datetime] = None
    status: Literal["active", "revoked", "expired"]


class AccessKeyCreated(BaseModel):
    key: AccessKeyOut
    secret: str = Field(..., description="The full key. Shown once; store it now.")


class AccessKeyPage(BaseModel):
    items: List[AccessKeyOut]
    next_cursor: Optional[str] = None


class UsageSummaryItem(BaseModel):
    day: Optional[str] = None
    method: Optional[str] = None
    route: Optional[str] = None
    requests: int
    errors: int
    avg_duration_ms: Optional[float] = None


class UsageSummary(BaseModel):
    key_id: str
    from_: datetime = Field(..., alias="from")
    to: datetime
    granularity: Literal["day", "route"]
    total_requests: int
    total_errors: int
    items: List[UsageSummaryItem]

    model_config = {"populate_by_name": True}


class UsageEventOut(BaseModel):
    id: int
    api_key_id: Optional[str] = None
    key_prefix: str
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    method: Optional[str] = None
    route: Optional[str] = None
    project_id: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    scope_used: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_bytes: Optional[int] = None
    response_bytes: Optional[int] = None
    created_at: datetime


class UsageEventPage(BaseModel):
    items: List[UsageEventOut]
    next_cursor: Optional[int] = None


class ScopeCatalog(BaseModel):
    scopes: List[Dict[str, Any]]
    presets: Dict[str, List[str]]
