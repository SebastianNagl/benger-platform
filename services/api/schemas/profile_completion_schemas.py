"""
Profile completion models for invitation-based user onboarding
and mandatory profile system (Issue #1206)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ProfileCompletionRequest(BaseModel):
    """Request model for completing user profile after invitation"""

    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., min_length=8, description="User password")
    name: Optional[str] = Field(None, description="Display name (optional)")


class ProfileCompletionResponse(BaseModel):
    """Response after successful profile completion"""

    success: bool
    message: str
    user_id: str
    username: str
    email: str
    profile_completed: bool
    redirect_url: Optional[str] = None


class ProfileStatusResponse(BaseModel):
    """Response for profile completion status check"""

    user_id: str
    email: str
    profile_completed: bool
    created_via_invitation: bool
    has_password: bool
    needs_profile_completion: bool
    message: Optional[str] = None


class EmailVerificationEnhancedResponse(BaseModel):
    """Enhanced email verification response with user type info"""

    success: bool
    message: str
    user_type: str  # 'invited' or 'self_registered'
    profile_completed: bool
    redirect_url: Optional[str] = None
    invitation_info: Optional[dict] = None  # Organization name, role, etc.


# === Issue #1206: Mandatory profile system models ===


class MandatoryProfileStatusResponse(BaseModel):
    """Response for mandatory profile completion and re-confirmation status"""

    mandatory_profile_completed: bool
    confirmation_due: bool
    confirmation_due_date: Optional[str] = None
    missing_fields: List[str] = []


class ProfileConfirmationResponse(BaseModel):
    """Response after profile re-confirmation"""

    success: bool
    confirmed_at: str
    message: str


class ProfileHistoryEntry(BaseModel):
    """Single profile history entry for audit trail"""

    id: str
    changed_at: str
    change_type: str
    snapshot: dict
    changed_fields: List[str]
