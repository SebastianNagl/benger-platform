"""
Authentication models for BenGER API

Consolidated Pydantic models for authentication, user management, and token handling.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """User model for API responses"""

    id: str
    username: str
    email: str
    email_verified: bool = False
    name: str
    is_superadmin: bool = False
    is_active: bool = True
    created_at: datetime
    organizations: Optional[List[dict]] = None  # User's organization memberships

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """User creation model with legal expertise fields for research stratification"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)
    is_superadmin: bool = False
    invitation_token: Optional[str] = Field(None, description="Optional invitation token")

    # Legal expertise fields (required at signup for human baseline groups)
    legal_expertise_level: str = Field(
        ...,
        description="Legal expertise level (layperson, law_student, referendar, graduated_no_practice, practicing_lawyer, judge_professor)",
    )
    german_proficiency: str = Field(
        ..., description="German language proficiency (native, c2, c1, b2, below_b2)"
    )
    degree_program_type: Optional[str] = Field(
        None,
        description="Degree program type (staatsexamen, llb, llm, promotion, not_applicable)",
    )
    current_semester: Optional[int] = Field(
        None, ge=1, le=20, description="Current semester (only for students)"
    )
    legal_specializations: Optional[List[str]] = Field(
        None,
        description="Legal specialization areas (civil_law, criminal_law, public_administrative_law, eu_international_law, tax_law, labor_law, ip_law, other)",
    )

    # Mandatory profile fields (collected during registration steps 3-5)
    gender: Optional[str] = None
    age: Optional[int] = Field(None, ge=1, le=120)
    job: Optional[str] = None
    years_of_experience: Optional[int] = Field(None, ge=0)
    subjective_competence_civil: Optional[int] = Field(None, ge=1, le=7)
    subjective_competence_public: Optional[int] = Field(None, ge=1, le=7)
    subjective_competence_criminal: Optional[int] = Field(None, ge=1, le=7)
    grade_zwischenpruefung: Optional[float] = None
    grade_vorgeruecktenubung: Optional[float] = None
    grade_first_staatsexamen: Optional[float] = None
    grade_second_staatsexamen: Optional[float] = None
    ati_s_scores: Optional[dict] = None
    ptt_a_scores: Optional[dict] = None
    ki_experience_scores: Optional[dict] = None


class UserCreateWithInvitation(BaseModel):
    """User creation model with invitation token and legal expertise fields"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)
    invitation_token: str = Field(..., description="Invitation token from organization invite")

    # Legal expertise fields (required at signup for human baseline groups)
    legal_expertise_level: str = Field(
        ...,
        description="Legal expertise level (layperson, law_student, referendar, graduated_no_practice, practicing_lawyer, judge_professor)",
    )
    german_proficiency: str = Field(
        ..., description="German language proficiency (native, c2, c1, b2, below_b2)"
    )
    degree_program_type: Optional[str] = Field(
        None,
        description="Degree program type (staatsexamen, llb, llm, promotion, not_applicable)",
    )
    current_semester: Optional[int] = Field(
        None, ge=1, le=20, description="Current semester (only for students)"
    )
    legal_specializations: Optional[List[str]] = Field(
        None,
        description="Legal specialization areas (civil_law, criminal_law, public_administrative_law, eu_international_law, tax_law, labor_law, ip_law, other)",
    )


class UserLogin(BaseModel):
    """Login credentials"""

    username: str
    password: str


class UserUpdate(BaseModel):
    """Model for updating user profile information"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")

    # Demographic and professional information
    age: Optional[int] = Field(None, ge=1, le=150, description="Age")
    job: Optional[str] = Field(None, max_length=200, description="Job/Profession")
    years_of_experience: Optional[int] = Field(
        None, ge=0, le=100, description="Years of work experience"
    )

    # Legal expertise fields (structured enums for research stratification)
    legal_expertise_level: Optional[str] = Field(
        None,
        description="Legal expertise level (layperson, law_student, referendar, graduated_no_practice, practicing_lawyer, judge_professor)",
    )
    german_proficiency: Optional[str] = Field(
        None, description="German language proficiency (native, c2, c1, b2, below_b2)"
    )
    degree_program_type: Optional[str] = Field(
        None,
        description="Degree program type (staatsexamen, llb, llm, promotion, not_applicable)",
    )
    current_semester: Optional[int] = Field(
        None, ge=1, le=20, description="Current semester (only for students)"
    )
    legal_specializations: Optional[List[str]] = Field(
        None,
        description="Legal specialization areas (civil_law, criminal_law, public_administrative_law, eu_international_law, tax_law, labor_law, ip_law, other)",
    )

    # German state exam fields
    german_state_exams_count: Optional[int] = Field(
        None, ge=0, le=2, description="Number of German state exams completed"
    )
    german_state_exams_data: Optional[List[dict]] = Field(
        None, description="German state exam details"
    )


class PasswordUpdate(BaseModel):
    """Model for password change"""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=6, description="New password")
    confirm_password: str = Field(..., description="Confirm new password")


class UserProfile(BaseModel):
    """Model for user profile response"""

    id: str
    username: str
    email: str
    name: str
    role: Optional[str] = None  # None for users without organization membership
    is_superadmin: bool
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Demographic and professional information
    age: Optional[int] = None
    job: Optional[str] = None
    years_of_experience: Optional[int] = None

    # Legal expertise fields (structured enums)
    legal_expertise_level: Optional[str] = None
    german_proficiency: Optional[str] = None
    degree_program_type: Optional[str] = None
    current_semester: Optional[int] = None
    legal_specializations: Optional[List[str]] = None

    # German state exam fields
    german_state_exams_count: Optional[int] = None
    german_state_exams_data: Optional[List[dict]] = None

    # Leaderboard pseudonym fields (Issue #790)
    pseudonym: Optional[str] = None
    use_pseudonym: Optional[bool] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response with optional refresh token"""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: int
    user: User


class TokenData(BaseModel):
    """Token payload data"""

    username: Optional[str] = None
    user_id: Optional[str] = None
    is_superadmin: Optional[bool] = None
