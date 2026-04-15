"""
Feature Flag Schemas
Pydantic models for feature flag requests and responses
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FeatureFlagCreate(BaseModel):
    """Request model for creating a feature flag"""

    name: str = Field(..., min_length=1, max_length=100, description="Unique feature flag name")
    description: Optional[str] = Field(
        None, max_length=500, description="Description of the feature flag"
    )
    is_enabled: bool = Field(False, description="Whether the flag is enabled by default")
    target_criteria: Optional[Dict[str, Any]] = Field(
        None, description="Targeting criteria for the flag"
    )
    configuration: Optional[Dict[str, Any]] = Field(
        None, description="Additional configuration for the flag"
    )


class FeatureFlagUpdate(BaseModel):
    """Request model for updating a feature flag"""

    description: Optional[str] = Field(None, max_length=500)
    is_enabled: Optional[bool] = None
    target_criteria: Optional[Dict[str, Any]] = None
    configuration: Optional[Dict[str, Any]] = None


class FeatureFlagResponse(BaseModel):
    """Response model for feature flag"""

    id: str
    name: str
    description: Optional[str]
    is_enabled: bool
    configuration: Optional[Dict[str, Any]]
    created_by: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True
        from_attributes = True


class FeatureFlagStatusResponse(BaseModel):
    """Response model for feature flag status"""

    flag_name: str
    is_enabled: bool
    source: str = "global"  # Now always "global" since we removed overrides

    class Config:
        orm_mode = True
