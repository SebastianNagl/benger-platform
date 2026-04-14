"""
Schemas package for BenGER API

Consolidates all Pydantic schema definitions
"""

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
]
