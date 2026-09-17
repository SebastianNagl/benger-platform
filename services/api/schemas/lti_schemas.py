"""Pydantic shapes for the LTI 1.3 (LMS) integration.

Generic data shapes over the platform-owned ``lti_*`` tables. The proprietary
LTI protocol logic (OIDC third-party login, id_token validation, deep linking,
AGS grade passback) lives in ``benger_extended`` and reuses these shapes — so
this module must not encode any launch/AGS behaviour.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

INSTRUCTOR_ORG_ROLE_PATTERN = "^(contributor|org_admin|none)$"
STUDENT_ORG_ROLE_PATTERN = "^(annotator|none)$"
REGISTRATION_STATUS_PATTERN = "^(active|disabled)$"
# Advisory vendor tag; drives admin-UI presets/warnings + diagnostics only.
LMS_FAMILY_PATTERN = "^(moodle|ilias)$"

# Public host a connection's tool URLs use. Base URLs are resolved from the
# environment by ``shared/public_hosts.py``; existing rows use the
# student-locked host.
ToolHost = Literal["student_locked", "main"]
DEFAULT_TOOL_HOST: ToolHost = "student_locked"
# How an LMS identity reached its account (``lti_user_links.link_method``).
LinkMethod = Literal["provisioned", "login_proof", "email_proof", "legacy_email"]
# State of the tool-created AI grade column on a resource link.
AiLineitemStatus = Literal["ready", "unavailable", "error", "deleted"]
# LMS column a grade-sync row feeds.
GradeSyncKind = Literal["final", "ai"]


def _require_http_url(value: str) -> str:
    """Reject anything that is not an absolute http(s) URL."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be an absolute http(s) URL")
    return value


class LtiRegistrationCreate(BaseModel):
    """Create shape for a platform (LMS installation) registration."""

    organization_id: str
    name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(max_length=500)
    client_id: str = Field(min_length=1, max_length=255)
    auth_login_url: str = Field(max_length=500)
    auth_token_url: str = Field(max_length=500)
    jwks_uri: str = Field(max_length=500)
    lms_family: Optional[str] = Field(None, pattern=LMS_FAMILY_PATTERN)
    link_existing_users_by_email: bool = True
    instructor_org_role: str = Field("contributor", pattern=INSTRUCTOR_ORG_ROLE_PATTERN)
    student_org_role: str = Field("annotator", pattern=STUDENT_ORG_ROLE_PATTERN)
    # Optional group scope (org → group → user layer): a group-scoped
    # registration provisions launched users into the group and links
    # launched projects with the group's visibility. Must reference an
    # active group of the registration's org.
    group_id: Optional[str] = None
    deployment_ids: List[str] = Field(default_factory=list)
    # Public host of the tool URLs; omitted = the deployment's default host.
    tool_host: Optional[ToolHost] = None

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
    lms_family: Optional[str] = Field(None, pattern=LMS_FAMILY_PATTERN)
    link_existing_users_by_email: Optional[bool] = None
    instructor_org_role: Optional[str] = Field(
        None, pattern=INSTRUCTOR_ORG_ROLE_PATTERN
    )
    student_org_role: Optional[str] = Field(None, pattern=STUDENT_ORG_ROLE_PATTERN)
    group_id: Optional[str] = None
    status: Optional[str] = Field(None, pattern=REGISTRATION_STATUS_PATTERN)
    tool_host: Optional[ToolHost] = None

    @field_validator("issuer", "auth_login_url", "auth_token_url", "jwks_uri")
    @classmethod
    def _http_urls_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _require_http_url(v)


class LtiDeploymentCreate(BaseModel):
    """Body for adding a deployment id to a registration."""

    deployment_id: str = Field(min_length=1, max_length=255)


class LtiDeploymentStatusUpdate(BaseModel):
    """Body for switching one deployment on or off."""

    status: Literal["active", "disabled"]


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
    lms_family: Optional[str] = None
    link_existing_users_by_email: bool
    instructor_org_role: str
    student_org_role: str
    group_id: Optional[str] = None
    status: str
    tool_host: ToolHost = DEFAULT_TOOL_HOST
    # Base URL of ``tool_host`` in this deployment; None when that host is
    # not configured here.
    tool_base_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deployments: List[LtiDeploymentRead] = Field(default_factory=list)
    deployment_count: int = 0
    # Only populated on the detail endpoint (extra count queries).
    resource_link_count: Optional[int] = None
    # LMS identities currently linked to an account (unlinked ones excluded).
    user_link_count: Optional[int] = None
    # Bound resource links whose launches never carried an AGS lineitem —
    # activities that cannot receive grades (e.g. an ILIAS provider without
    # "Advanced Grading Services"). Populated on list + detail so the org
    # panel can warn before the first grade push fails.
    resource_links_missing_ags: int = 0

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
    ai_lineitem_url: Optional[str] = None
    ai_lineitem_status: Optional[AiLineitemStatus] = None
    ai_lineitem_error: Optional[str] = None
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
    research_consent_at: Optional[datetime] = None
    link_method: Optional[LinkMethod] = None
    unlinked_at: Optional[datetime] = None
    last_launch_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiGradeSyncRead(BaseModel):
    """Read shape for one grade-passback outbox row."""

    id: str
    resource_link_id: str
    user_id: str
    kind: GradeSyncKind = "final"
    status: str
    attempts: int
    next_retry_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    last_synced_score: Optional[float] = None
    last_synced_hash: Optional[str] = None
    last_synced_source: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    source_task_evaluation_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LtiGradeSyncAdminRead(LtiGradeSyncRead):
    """An outbox row with the context an admin needs to act on it.

    ``student_name`` is only filled for viewers who may see real names
    (org admins and superadmins); everyone else gets the pseudonym only.
    """

    registration_id: Optional[str] = None
    registration_name: Optional[str] = None
    organization_id: Optional[str] = None
    context_title: Optional[str] = None
    resource_title: Optional[str] = None
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    student_pseudonym: Optional[str] = None
    student_name: Optional[str] = None


class LtiGradeSyncRetryRead(LtiGradeSyncAdminRead):
    """Retry response: the reset row plus whether the push was queued now
    (False means the next sweep sends it)."""

    dispatched: bool = False


class LtiToolConfigRead(BaseModel):
    """The tool-side URLs an LMS admin pastes into their LMS's external-tool
    form, derived from the connection's tool host. The routes themselves are
    served by the extended edition (``/api/lti/*``).

    Deliberately does NOT advertise a deep-linking URL: the tool rejects
    ``LtiDeepLinkingRequest`` launches (content binding happens via the
    instructor-launch picker instead), so publishing such a URL would point
    LMS admins at a route that does not exist."""

    login_url: str
    launch_url: str
    jwks_url: str
    tool_host: Optional[ToolHost] = None
    base_url: Optional[str] = None


class LtiToolHostRead(BaseModel):
    """One public host a connection's tool URLs can use.

    ``label`` is the bare host name; product names are left to the UI.
    """

    key: ToolHost
    label: str
    host: str
    base_url: str
    is_default: bool


class LtiResourceLinkProjectRead(BaseModel):
    """The exam an LMS activity opens, as far as the admin list shows it."""

    id: str
    title: Optional[str] = None
    task_count: int = 0
    deleted: bool = False


class LtiResourceLinkAdminRead(BaseModel):
    """One LMS activity of a connection, for the org admin view."""

    id: str
    deployment_id: str
    resource_link_id: str
    context_id: Optional[str] = None
    context_title: Optional[str] = None
    resource_title: Optional[str] = None
    project: Optional[LtiResourceLinkProjectRead] = None
    linked_by_display: Optional[str] = None
    linked_at: Optional[datetime] = None
    # The launch carried a grade column (AGS line item) for this activity.
    grades_supported: bool = False
    # The launch carried the activity's line item container, which the tool
    # needs to find or create its own AI grade column.
    lineitems_available: bool = False
    # Scopes the LMS granted; ``column_management`` is True when they include
    # the read-write line item scope (the tool may create its own column).
    granted_scopes: List[str] = Field(default_factory=list)
    column_management: bool = False
    sync_ai_grades: bool = True
    ai_lineitem_status: Optional[AiLineitemStatus] = None
    ai_lineitem_error: Optional[str] = None
    # Consented participants (learners) and teachers seen on this activity.
    participant_count: int = 0
    instructor_count: int = 0
    last_launch_at: Optional[datetime] = None
    # Grade transfer rows by status, over all columns.
    sync_counts: Dict[str, int] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class LtiUserLinkAdminRead(BaseModel):
    """One LMS identity of a connection, for the org admin view.

    ``name`` and ``email`` are only filled for viewers who may see real names;
    the pseudonym is always present when the account has one. The claims
    snapshot is never returned.
    """

    id: str
    user_id: str
    sub: str
    pseudonym: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    # instructor | learner | None (unknown)
    role: Optional[str] = None
    link_method: Optional[LinkMethod] = None
    provisioned_account: bool = False
    consent_at: Optional[datetime] = None
    consent_version: Optional[str] = None
    research_consent_at: Optional[datetime] = None
    last_launch_at: Optional[datetime] = None
    unlinked_at: Optional[datetime] = None
    anonymized: bool = False
    created_at: Optional[datetime] = None


class LtiUserLinkAdminPage(BaseModel):
    """A page of LMS identities."""

    items: List[LtiUserLinkAdminRead] = Field(default_factory=list)
    total: int = 0
    limit: int
    offset: int


class LtiAdminEventRead(BaseModel):
    """One entry of a connection's or an organization's LMS history."""

    id: str
    organization_id: str
    registration_id: Optional[str] = None
    registration_name: Optional[str] = None
    # Group scope of the entry (None = org-wide).
    group_id: Optional[str] = None
    actor_user_id: Optional[str] = None
    actor_display: Optional[str] = None
    actor_kind: str
    action: str
    changes: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class LtiRegistrationInviteCreate(BaseModel):
    """Body for minting a one-time LTI Dynamic Registration invite."""

    organization_id: str
    # Optional group scope carried into the auto-created registration.
    group_id: Optional[str] = None
    expires_in_days: int = Field(14, ge=1, le=90)
    # Public host of the invite URL and of the resulting connection;
    # omitted = the deployment's default host.
    tool_host: Optional[ToolHost] = None


class LtiRegistrationInviteCreated(BaseModel):
    """Create response for an invite — the ONLY place the raw token (and the
    registration URL embedding it) ever appears; only its sha256 is stored."""

    id: str
    organization_id: str
    group_id: Optional[str] = None
    tool_host: ToolHost = DEFAULT_TOOL_HOST
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
    group_id: Optional[str] = None
    tool_host: ToolHost = DEFAULT_TOOL_HOST
    created_at: Optional[datetime] = None
    expires_at: datetime
    used_at: Optional[datetime] = None
    resulting_registration_id: Optional[str] = None
    status: str
