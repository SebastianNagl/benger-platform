"""
Authentication-related Pydantic models for API requests and responses
"""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

# Import existing auth models for consistency
from auth_module import Token, TokenData, User, UserCreate, UserLogin


class UserUpdate(BaseModel):
    """Model for updating user profile information (Issue #1206)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")

    # Pseudonymization privacy preference (Issue #790)
    use_pseudonym: Optional[bool] = Field(None)

    # Demographic and professional information
    age: Optional[int] = Field(None, ge=1, le=150, description="Age")
    job: Optional[str] = Field(None, max_length=200, description="Job/Profession")
    years_of_experience: Optional[int] = Field(None, ge=0, le=100)

    # Legal expertise fields
    legal_expertise_level: Optional[str] = Field(None)
    german_proficiency: Optional[str] = Field(None)
    degree_program_type: Optional[str] = Field(None)
    current_semester: Optional[int] = Field(None, ge=1, le=20)
    legal_specializations: Optional[List[str]] = Field(None)

    # German state exam fields
    german_state_exams_count: Optional[int] = Field(None, ge=0, le=2)
    german_state_exams_data: Optional[List[dict]] = Field(None)

    # Gender (Issue #1206)
    gender: Optional[str] = Field(None)

    # Subjective competence (Issue #1206)
    subjective_competence_civil: Optional[int] = Field(None, ge=1, le=7)
    subjective_competence_public: Optional[int] = Field(None, ge=1, le=7)
    subjective_competence_criminal: Optional[int] = Field(None, ge=1, le=7)

    # Objective grades (Issue #1206)
    grade_zwischenpruefung: Optional[float] = None
    grade_vorgeruecktenubung: Optional[float] = None
    grade_first_staatsexamen: Optional[float] = None
    grade_second_staatsexamen: Optional[float] = None

    # Psychometric scales (Issue #1206)
    ati_s_scores: Optional[dict] = None
    ptt_a_scores: Optional[dict] = None
    ki_experience_scores: Optional[dict] = None


class PasswordUpdate(BaseModel):
    """Model for password change"""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=6, description="New password")
    confirm_password: str = Field(..., description="Confirm new password")


class PasswordResetRequest(BaseModel):
    """Model for requesting a password reset"""

    email: EmailStr = Field(..., description="Email address to send reset link to")
    language: Optional[str] = Field("en", description="Language for email template (en or de)")


class PasswordResetConfirm(BaseModel):
    """Model for confirming a password reset with token"""

    token: str = Field(..., description="Password reset token from email")
    new_password: str = Field(..., min_length=6, description="New password")
    confirm_password: str = Field(..., description="Confirm new password")


class EmailVerificationRequest(BaseModel):
    """Model for email verification"""

    token: str = Field(..., description="Email verification token")


class ResendVerificationRequest(BaseModel):
    """Model for resending email verification"""

    email: EmailStr = Field(..., description="Email address to resend verification to")
    language: Optional[str] = Field("en", description="Language for email template (en or de)")


class UserProfile(BaseModel):
    """Model for user profile response (Issue #1206)"""

    id: str
    username: str
    email: str
    name: str
    role: Optional[str] = None
    is_superadmin: bool
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Pseudonymization fields (Issue #790)
    pseudonym: Optional[str] = Field(None)
    use_pseudonym: bool = Field(True)

    # Demographic and professional information
    age: Optional[int] = None
    job: Optional[str] = None
    years_of_experience: Optional[int] = None

    # Legal expertise fields
    legal_expertise_level: Optional[str] = None
    german_proficiency: Optional[str] = None
    degree_program_type: Optional[str] = None
    current_semester: Optional[int] = None
    legal_specializations: Optional[List[str]] = None

    # German state exam fields
    german_state_exams_count: Optional[int] = None
    german_state_exams_data: Optional[List[dict]] = None

    # Gender (Issue #1206)
    gender: Optional[str] = None

    # Subjective competence (Issue #1206)
    subjective_competence_civil: Optional[int] = None
    subjective_competence_public: Optional[int] = None
    subjective_competence_criminal: Optional[int] = None

    # Objective grades (Issue #1206)
    grade_zwischenpruefung: Optional[float] = None
    grade_vorgeruecktenubung: Optional[float] = None
    grade_first_staatsexamen: Optional[float] = None
    grade_second_staatsexamen: Optional[float] = None

    # Psychometric scales (Issue #1206)
    ati_s_scores: Optional[dict] = None
    ptt_a_scores: Optional[dict] = None
    ki_experience_scores: Optional[dict] = None

    # Mandatory profile tracking (Issue #1206)
    mandatory_profile_completed: Optional[bool] = None
    profile_confirmed_at: Optional[str] = None

    class Config:
        from_attributes = True


__all__ = [
    "User",
    "UserCreate",
    "UserLogin",
    "UserUpdate",
    "PasswordUpdate",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "EmailVerificationRequest",
    "ResendVerificationRequest",
    "UserProfile",
    "Token",
    "TokenData",
]
