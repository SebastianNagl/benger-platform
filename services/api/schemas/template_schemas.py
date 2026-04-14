"""
Pydantic schemas for template API

Issue #219: Schema definitions for template CRUD, versioning, and sharing
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskTemplateBase(BaseModel):
    """Base schema for task templates"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., description="Template category (qa, classification, etc.)")
    schema: Dict[str, Any] = Field(..., description="JSON schema defining the template")
    tags: Optional[List[str]] = Field(default_factory=list)
    preview_image_url: Optional[str] = None
    template_metadata: Optional[Dict[str, Any]] = None


class TaskTemplateCreate(TaskTemplateBase):
    """Schema for creating a new template"""

    parent_template_id: Optional[str] = None
    organization_id: Optional[str] = None
    is_public: bool = Field(default=False)
    semantic_version: str = Field(default="1.0.0", pattern="^\d+\.\d+\.\d+$")
    version_notes: Optional[str] = None


class TaskTemplateUpdate(BaseModel):
    """Schema for updating a template"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    preview_image_url: Optional[str] = None
    template_metadata: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None
    version_notes: Optional[str] = None
    is_major_version: Optional[bool] = Field(default=False)


class TaskTemplateResponse(TaskTemplateBase):
    """Schema for template responses"""

    id: str
    parent_template_id: Optional[str]
    organization_id: Optional[str]
    semantic_version: str
    version_notes: Optional[str]
    is_active: bool
    is_system: bool
    is_public: bool
    usage_count: int
    rating: Optional[float]
    rating_count: int
    last_used_at: Optional[datetime]
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]

    # Relationships
    creator: Optional[Dict[str, Any]] = None
    organization: Optional[Dict[str, Any]] = None
    parent_template: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Response schema for template lists with pagination"""

    items: List[TaskTemplateResponse]
    total: int
    skip: int
    limit: int


class TemplateVersionBase(BaseModel):
    """Base schema for template versions"""

    version: str = Field(..., pattern="^\d+\.\d+\.\d+$")
    schema: Dict[str, Any]
    version_notes: Optional[str] = None
    is_major_version: bool = Field(default=False)


class TemplateVersionResponse(TemplateVersionBase):
    """Response schema for template versions"""

    id: str
    template_id: str
    created_by: str
    created_at: datetime
    parent_version_id: Optional[str]

    class Config:
        from_attributes = True


class TemplateSharingCreate(BaseModel):
    """Schema for sharing a template"""

    shared_with_organization_id: str
    permission: str = Field(..., pattern="^(view|use|edit)$")
    expires_at: Optional[datetime] = None


class TemplateSharingResponse(BaseModel):
    """Response schema for template sharing"""

    id: str
    template_id: str
    shared_with_organization_id: str
    permission: str
    shared_by: str
    shared_at: datetime
    expires_at: Optional[datetime]

    # Relationships
    template: Optional[Dict[str, Any]] = None
    shared_with_organization: Optional[Dict[str, Any]] = None
    shared_by_user: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TemplateRatingCreate(BaseModel):
    """Schema for rating a template"""

    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = Field(None, max_length=1000)


class TemplateRatingResponse(BaseModel):
    """Response schema for template ratings"""

    id: str
    template_id: str
    user_id: str
    rating: int
    review: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    # Relationships
    user: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TemplateCategoryResponse(BaseModel):
    """Response schema for template categories"""

    id: str
    name: str
    display_name: str
    description: Optional[str]
    icon: Optional[str]
    parent_category_id: Optional[str]
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class TemplateUsageStats(BaseModel):
    """Statistics for template usage"""

    template_id: str
    total_uses: int
    unique_users: int
    average_rating: Optional[float]
    total_ratings: int
    last_30_days_uses: int
    top_organizations: List[Dict[str, Any]]


class TemplateImportExport(BaseModel):
    """Schema for template import/export"""

    template: TaskTemplateBase
    versions: List[TemplateVersionBase]
    category: Optional[TemplateCategoryResponse]
    export_date: datetime = Field(default_factory=datetime.utcnow)
    format_version: str = Field(default="1.0")
