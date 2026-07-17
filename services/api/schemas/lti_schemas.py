"""Pydantic shapes for the LTI 1.3 (Moodle) integration.

Generic data shapes over the platform-owned ``lti_*`` tables. The proprietary
LTI protocol logic (OIDC third-party login, id_token validation, deep linking,
AGS grade passback) lives in ``benger_extended`` and reuses these shapes — so
this module must not encode any launch/AGS behaviour.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

INSTRUCTOR_ORG_ROLE_PATTERN = "^(contributor|org_admin|none)$"
REGISTRATION_STATUS_PATTERN = "^(active|disabled)$"


def _require_http_url(value: str) -> str:
    """Reject anything that is not an absolute http(s) URL."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be an absolute http(s) URL")
    return value


class LtiRegistrationCreate(BaseModel):
    """Create shape for a platform (Moodle site) registration."""

    organization_id: str
    name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(max_length=500)
    client_id: str = Field(min_length=1, max_length=255)
    auth_login_url: str = Field(max_length=500)
    auth_token_url: str = Field(max_length=500)
    jwks_uri: str = Field(max_length=500)
    link_existing_users_by_email: bool = True
    instructor_org_role: str = Field(
        "contributor", pattern=INSTRUCTOR_ORG_ROLE_PATTERN
    )
    deployment_ids: List[str] = Field(default_factory=list)

    @field_validator("issuer", "auth_login_url", "auth_token_url", "jwks_uri")
    @classmethod
    def _http_urls_only(cls, v: str) -> str:
        return _require_http_url(v)


class LtiRegistrationUpdate(BaseModel):
    """Partial-update shape for a registration (all fields optional)."""

    organization_id: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    issuer: Optional[str] = Field(None, max_length=500)
    client_id: Optional[str] = Field(None, min_length=1, max_length=255)
    auth_login_url: Optional[str] = Field(None, max_length=500)
    auth_token_url: Optional[str] = Field(None, max_length=500)
    jwks_uri: Optional[str] = Field(None, max_length=500)
    link_existing_users_by_email: Optional[bool] = None
    instructor_org_role: Optional[str] = Field(
        None, pattern=INSTRUCTOR_ORG_ROLE_PATTERN
    )
    status: Optional[str] = Field(None, pattern=REGISTRATION_STATUS_PATTERN)

    @field_validator("issuer", "auth_login_url", "auth_token_url", "jwks_uri")
    @classmethod
    def _http_urls_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _require_http_url(v)


class LtiDeploymentCreate(BaseModel):
    """Body for adding a deployment id to a registration."""

    deployment_id: str = Field(min_length=1, max_length=255)


class LtiDeploymentRead(BaseModel):
    """Read shape for a deployment id under a registration."""

    id: str
    registration_id: str
    deployment_id: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiRegistrationRead(BaseModel):
    """Read shape for a platform registration (with its deployments)."""

    id: str
    organization_id: str
    name: str
    issuer: str
    client_id: str
    auth_login_url: str
    auth_token_url: str
    jwks_uri: str
    link_existing_users_by_email: bool
    instructor_org_role: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deployments: List[LtiDeploymentRead] = Field(default_factory=list)
    deployment_count: int = 0
    # Only populated on the detail endpoint (extra count query).
    resource_link_count: Optional[int] = None

    class Config:
        from_attributes = True


class LtiResourceLinkRead(BaseModel):
    """Read shape for a placed LTI resource link (Moodle activity)."""

    id: str
    registration_id: str
    deployment_id: str
    resource_link_id: str
    project_id: Optional[str] = None
    context_id: Optional[str] = None
    context_title: Optional[str] = None
    resource_title: Optional[str] = None
    lineitem_url: Optional[str] = None
    lineitems_url: Optional[str] = None
    ags_scopes: Optional[List[str]] = None
    sync_ai_grades: bool = True
    linked_by: Optional[str] = None
    linked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiUserLinkRead(BaseModel):
    """Read shape for an LTI identity -> BenGER user mapping."""

    id: str
    registration_id: str
    sub: str
    user_id: str
    claims: Optional[Dict[str, Any]] = None
    consent_at: Optional[datetime] = None
    consent_version: Optional[str] = None
    last_launch_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiGradeSyncRead(BaseModel):
    """Read shape for one grade-passback outbox row."""

    id: str
    resource_link_id: str
    user_id: str
    status: str
    attempts: int
    next_retry_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    last_synced_score: Optional[float] = None
    last_synced_hash: Optional[str] = None
    source_task_evaluation_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiToolConfigRead(BaseModel):
    """The tool-side URLs an LMS admin pastes into Moodle's external-tool
    form, derived from a deployment base URL. The routes themselves are
    served by the extended edition (``/api/lti/*``)."""

    login_url: str
    launch_url: str
    jwks_url: str
    deep_linking_url: str


class LtiRegistrationInviteCreate(BaseModel):
    """Body for minting a one-time LTI Dynamic Registration invite."""

    organization_id: str
    expires_in_days: int = Field(14, ge=1, le=90)


class LtiRegistrationInviteCreated(BaseModel):
    """Create response for an invite — the ONLY place the raw token (and the
    registration URL embedding it) ever appears; only its sha256 is stored."""

    id: str
    organization_id: str
    token: str
    register_url: str
    expires_at: datetime


class LtiRegistrationInviteRead(BaseModel):
    """List shape for an invite. Never carries the raw token or its hash.

    ``status`` is computed: 'used' if consumed, else 'expired' past
    ``expires_at``, else 'pending'.
    """

    id: str
    organization_id: str
    created_at: Optional[datetime] = None
    expires_at: datetime
    used_at: Optional[datetime] = None
    resulting_registration_id: Optional[str] = None
    status: str
