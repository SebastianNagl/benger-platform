"""
Authentication-related Pydantic models for API requests and responses
"""

from typing import List, Literal, Optional

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


class UiModeUpdate(BaseModel):
    """Single-field body for the lightweight view-mode preference endpoint.

    Deliberately NOT folded into ``UserUpdate``: that path runs
    ``update_user_profile`` which snapshots profile history and stamps
    ``profile_confirmed_at`` / ``mandatory_profile_completed`` — heavy side
    effects that must not fire when a student flips the student/expert toggle
    (issue #35). ``None`` clears the stored preference.
    """

    preferred_ui_mode: Optional[Literal["student", "expert"]] = Field(None)


class ExamLayoutPrefs(BaseModel):
    """Canonical exam-interface layout object stored in users.exam_layout_prefs.

    ``mode`` is required; the panel positions default so a minimal
    ``{"mode": ...}`` body validates to the full canonical shape. The stored
    value is always the complete ``model_dump()`` — unknown request keys are
    dropped by validation (default ``extra='ignore'``, deploy-skew tolerant),
    so the column only ever holds exactly these four keys. The case has no
    ``"none"``: the exam text is mandatory.
    """

    mode: Literal["classic", "modern"]
    case_position: Literal["left", "right"] = "left"
    notes_position: Literal["left", "right", "none"] = "right"
    outline_position: Literal["left", "right", "none"] = "right"


class ExamLayoutUpdate(BaseModel):
    """Single-field body for ``PUT /auth/me/exam-layout``.

    Deliberately NOT folded into ``UserUpdate`` (same rationale as
    ``UiModeUpdate`` above): ``PUT /profile`` runs ``update_user_profile``
    which snapshots profile history and stamps ``profile_confirmed_at`` /
    ``mandatory_profile_completed`` — side effects that must not fire on a UI
    preference change. ``None`` clears the stored preference (column NULL =
    classic default). Purely a display preference — never an authorization or
    exam-integrity input.
    """

    exam_layout_prefs: Optional[ExamLayoutPrefs] = Field(None)


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


class AccountActivationRequest(BaseModel):
    """Request the "Konto aktivieren" mail (passwordless LTI accounts).

    ``email`` is required iff the account's current address is unroutable
    (synthetic ``@lti.invalid``) — it parks in ``pending_activation_email``
    and is adopted only when the link is clicked. Accounts with a routable
    address omit it (resend semantics)."""

    email: Optional[EmailStr] = Field(
        None, description="Target address for sub-only accounts"
    )


class AccountActivateConfirm(BaseModel):
    """Confirm activation: set the first password via the mailed token."""

    token: str = Field(..., description="Activation token from email")
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

    # Preferred UI mode (extended student experience, issue #35). A persisted
    # default hint the frontend reads on load; gating is always recomputed.
    preferred_ui_mode: Optional[str] = None
    # Vertretbar plan-choice greeting (extended): ISO timestamp once the student
    # has chosen; NULL until then. The modal reads this from /auth/me.
    vertretbar_onboarding_completed_at: Optional[str] = None
    # Exam interface layout preference (extended). The complete stored object
    # (see ExamLayoutPrefs) or None. Loose dict on read: write-side strictness
    # lives in ExamLayoutUpdate; a legacy/odd row must never 500 the profile.
    exam_layout_prefs: Optional[dict] = None

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
