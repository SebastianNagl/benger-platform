"""
Schemas package for BenGER API

Consolidates all Pydantic schema definitions
"""

from schemas.billing_schemas import (
    GradingUsageEventRead,
    InvoiceSummary,
    StudentSubscriptionRead,
    UsageSummary,
)
from schemas.lti_schemas import (
    LtiDeploymentCreate,
    LtiDeploymentRead,
    LtiGradeSyncRead,
    LtiRegistrationCreate,
    LtiRegistrationRead,
    LtiRegistrationUpdate,
    LtiResourceLinkRead,
    LtiToolConfigRead,
    LtiUserLinkRead,
)
from schemas.template_schemas import (
    TaskTemplateBase,
    TaskTemplateCreate,
    TaskTemplateResponse,
    TaskTemplateUpdate,
    TemplateCategoryResponse,
    TemplateImportExport,
    TemplateListResponse,
    TemplateRatingCreate,
    TemplateRatingResponse,
    TemplateSharingCreate,
    TemplateSharingResponse,
    TemplateUsageStats,
    TemplateVersionBase,
    TemplateVersionResponse,
)

__all__ = [
    # Template schemas
    "TaskTemplateBase",
    "TaskTemplateCreate",
    "TaskTemplateUpdate",
    "TaskTemplateResponse",
    "TemplateListResponse",
    "TemplateVersionBase",
    "TemplateVersionResponse",
    "TemplateSharingCreate",
    "TemplateSharingResponse",
    "TemplateRatingCreate",
    "TemplateRatingResponse",
    "TemplateCategoryResponse",
    "TemplateUsageStats",
    "TemplateImportExport",
    # Billing schemas
    "StudentSubscriptionRead",
    "GradingUsageEventRead",
    "UsageSummary",
    "InvoiceSummary",
    # LTI 1.3 (Moodle integration) schemas
    "LtiRegistrationCreate",
    "LtiRegistrationUpdate",
    "LtiRegistrationRead",
    "LtiDeploymentCreate",
    "LtiDeploymentRead",
    "LtiResourceLinkRead",
    "LtiUserLinkRead",
    "LtiGradeSyncRead",
    "LtiToolConfigRead",
]
