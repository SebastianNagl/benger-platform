"""
Database models for BenGER API
"""

import os
import uuid
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Handle SQLite compatibility for testing
if "sqlite" in os.environ.get("DATABASE_URL", "sqlite:///:memory:").lower():
    # Use Text for ARRAY columns when using SQLite
    def ARRAY(column_type):
        from sqlalchemy import Text

        return Text

    # Use JSON for JSONB when using SQLite
    from sqlalchemy import JSON as JSONB
else:
    from sqlalchemy.dialects.postgresql import JSONB

from database import Base

# Association tables have been removed - relationships are now stored as JSON arrays in Task model


# UserRole enum removed - replaced with is_superadmin boolean flag


class OrganizationRole(str, Enum):
    """User roles within an organization - standardized across all organizations

    Available roles:
    - ORG_ADMIN: Can manage organization and invite users
    - CONTRIBUTOR: Can create and manage tasks
    - ANNOTATOR: Can annotate tasks

    Usage:
        from models import OrganizationRole
        role = OrganizationRole.ORG_ADMIN
        # Do NOT use strings like 'org_admin' or 'ORG_ADMIN'
    """

    ORG_ADMIN = "ORG_ADMIN"  # Can manage organization and invite users
    CONTRIBUTOR = "CONTRIBUTOR"  # Can create and manage tasks
    ANNOTATOR = "ANNOTATOR"  # Can annotate tasks

    @classmethod
    def get_valid_roles(cls) -> list[str]:
        """Get list of valid role values for validation and error messages"""
        return [role.value for role in cls]

    @classmethod
    def from_string(cls, role_str: str) -> "OrganizationRole":
        """Convert string to OrganizationRole enum with better error message

        Args:
            role_str: String representation of role

        Returns:
            OrganizationRole enum value

        Raises:
            ValueError: If role_str is not a valid role with helpful message
        """
        try:
            return cls(role_str.upper())
        except ValueError:
            valid_roles = cls.get_valid_roles()
            raise ValueError(
                f"Invalid organization role '{role_str}'. "
                f"Valid roles are: {', '.join(valid_roles)}"
            )

    @classmethod
    def is_valid_role(cls, role_str: str) -> bool:
        """Check if a string is a valid organization role

        Args:
            role_str: String to validate

        Returns:
            True if valid role, False otherwise
        """
        try:
            cls(role_str.upper())
            return True
        except ValueError:
            return False


# TaskVisibility enum removed - now using simple strings "public" or "private"


class LegalExpertiseLevel(str, Enum):
    """Legal expertise level for annotator background tracking in human baseline groups"""

    LAYPERSON = "layperson"
    LAW_STUDENT = "law_student"
    REFERENDAR = "referendar"
    GRADUATED_NO_PRACTICE = "graduated_no_practice"
    PRACTICING_LAWYER = "practicing_lawyer"
    JUDGE_PROFESSOR = "judge_professor"


class GermanProficiency(str, Enum):
    """German language proficiency level (CEFR scale)"""

    NATIVE = "native"
    C2 = "c2"
    C1 = "c1"
    B2 = "b2"
    BELOW_B2 = "below_b2"


class DegreeProgramType(str, Enum):
    """Type of law degree program"""

    STAATSEXAMEN = "staatsexamen"
    LLB = "llb"
    LLM = "llm"
    PROMOTION = "promotion"
    NOT_APPLICABLE = "not_applicable"


class Gender(str, Enum):
    """Gender options for demographic data collection (Issue #1206)"""

    MAENNLICH = "maennlich"
    WEIBLICH = "weiblich"
    DIVERS = "divers"
    KEINE_ANGABE = "keine_angabe"


class User(Base):
    """User database model"""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)  # Email verification status
    email_verification_token = Column(
        String(512), nullable=True, index=True
    )  # JWT token for email verification
    email_verification_sent_at = Column(
        DateTime(timezone=True), nullable=True
    )  # Track when verification email was sent

    # Admin verification tracking fields
    email_verified_by_id = Column(
        String, ForeignKey("users.id"), nullable=True
    )  # User who verified the email (for admin verification)
    email_verified_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When the email was verified
    email_verification_method = Column(
        String, nullable=True, default="self"
    )  # How email was verified: 'self', 'admin', 'system'

    # Password reset fields
    password_reset_token = Column(
        String(512), nullable=True, index=True
    )  # Token for password reset
    password_reset_expires = Column(
        DateTime(timezone=True), nullable=True
    )  # Expiry time for reset token
    password_set = Column(
        Boolean, server_default="false", nullable=False
    )  # Flag to track if user has set password

    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=True)  # Now nullable for invited users
    is_superadmin = Column(Boolean, default=False, nullable=False)  # Global admin flag

    # Invitation onboarding tracking fields
    invitation_token = Column(String(255), nullable=True, index=True)  # Token from invitation
    invitation_expires_at = Column(
        DateTime(timezone=True), nullable=True
    )  # Expiry time for invitation token
    profile_completed = Column(
        Boolean, default=True, nullable=False
    )  # False for invited users until profile setup
    created_via_invitation = Column(
        Boolean, default=False, nullable=False
    )  # Track invitation-based users

    # default_organization_id removed - users can be in multiple orgs with different roles
    is_active = Column(Boolean, default=True, nullable=False)

    # Pseudonymization fields (GDPR-compliant privacy, EDPB Guidelines 01/2025)
    pseudonym = Column(
        String(100), unique=True, index=True, nullable=True
    )  # Unique pseudonym for privacy-first leaderboards and annotations
    use_pseudonym = Column(
        Boolean, default=True, nullable=False
    )  # User preference: True = show pseudonym, False = show real name

    # User-provided API keys (encrypted)
    encrypted_openai_api_key = Column(Text, nullable=True)
    encrypted_anthropic_api_key = Column(Text, nullable=True)
    encrypted_google_api_key = Column(Text, nullable=True)
    encrypted_deepinfra_api_key = Column(Text, nullable=True)
    # New providers added in migration 007
    encrypted_grok_api_key = Column(Text, nullable=True)
    encrypted_mistral_api_key = Column(Text, nullable=True)
    encrypted_cohere_api_key = Column(Text, nullable=True)

    # Notification preferences (timezone only)
    timezone = Column(
        String, nullable=True, default="UTC"
    )  # User's timezone (e.g., "America/New_York")

    # NOTE: Quiet hours and email digest features have been removed
    # These fields are kept commented for potential future use:
    # quiet_hours_start = Column(String, nullable=True)
    # quiet_hours_end = Column(String, nullable=True)
    # enable_quiet_hours = Column(Boolean, default=False, nullable=False)
    # enable_email_digest = Column(Boolean, default=False, nullable=False)
    # digest_frequency = Column(String, nullable=True, default="daily")
    # digest_time = Column(String, nullable=True, default="09:00")
    # digest_days = Column(String, nullable=True)
    # last_digest_sent = Column(DateTime(timezone=True), nullable=True)

    # Demographic and professional information
    age = Column(Integer, nullable=True)
    job = Column(Text, nullable=True)
    years_of_experience = Column(Integer, nullable=True)

    # Legal expertise fields (structured enums for research stratification)
    # Note: values_callable ensures SQLAlchemy uses enum .value (lowercase) not .name (uppercase)
    legal_expertise_level = Column(
        SQLEnum(LegalExpertiseLevel, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    german_proficiency = Column(
        SQLEnum(GermanProficiency, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    degree_program_type = Column(
        SQLEnum(DegreeProgramType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    current_semester = Column(Integer, nullable=True)  # Only for students (1-20)
    legal_specializations = Column(JSON, nullable=True)  # Array of legal specialization strings

    # German state exam fields
    german_state_exams_count = Column(Integer, nullable=True)  # 0, 1, or 2
    german_state_exams_data = Column(JSON, nullable=True)  # Array of exam details

    # Issue #1206: Mandatory demographic & psychometric profile fields
    gender = Column(String(20), nullable=True)
    subjective_competence_civil = Column(Integer, nullable=True)  # Likert 1-7
    subjective_competence_public = Column(Integer, nullable=True)  # Likert 1-7
    subjective_competence_criminal = Column(Integer, nullable=True)  # Likert 1-7
    grade_zwischenpruefung = Column(Numeric(4, 2), nullable=True)
    grade_vorgeruecktenubung = Column(Numeric(4, 2), nullable=True)
    grade_first_staatsexamen = Column(Numeric(4, 2), nullable=True)
    grade_second_staatsexamen = Column(Numeric(4, 2), nullable=True)
    ati_s_scores = Column(JSON, nullable=True)  # ATI-S psychometric scale (4 items, int 1-7)
    ptt_a_scores = Column(JSON, nullable=True)  # PTT-A psychometric scale (4 items, int 1-7)
    ki_experience_scores = Column(JSON, nullable=True)  # KI-Erfahrung scale (4 items, int 1-7)
    mandatory_profile_completed = Column(Boolean, nullable=False, default=False, server_default="false")
    profile_confirmed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # created_tasks relationship removed
    organization_memberships = relationship("OrganizationMembership", back_populates="user")
    sent_invitations = relationship(
        "Invitation", foreign_keys="Invitation.invited_by", back_populates="inviter"
    )
    # Note: ignored_enterprise_projects relationship removed in migration 411540fa6c40

    # Email verification relationship
    email_verified_by = relationship(
        "User",
        foreign_keys=[email_verified_by_id],
        remote_side=[id],
        backref="verified_emails",
    )

    # Native annotation system relationships removed - migrated to project_models.py

    # Feature flag relationships
    created_feature_flags = relationship("FeatureFlag", back_populates="creator")

    # Issue #1206: profile history relationship
    profile_history = relationship("UserProfileHistory", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class UserProfileHistory(Base):
    """Tracks profile changes for research audit trails (Issue #1206)"""

    __tablename__ = "user_profile_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    change_type = Column(String(50), nullable=False)  # 'profile_update', 'confirmation', 'signup'
    snapshot = Column(JSON, nullable=False)  # Full profile snapshot at time of change
    changed_fields = Column(JSON, nullable=False)  # List of fields that changed

    user = relationship("User", back_populates="profile_history")


class RefreshToken(Base):
    """Refresh token model for persistent authentication"""

    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)  # Hashed refresh token
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String, nullable=True)  # Browser/device identification
    ip_address = Column(String, nullable=True)  # IP address for security tracking

    # Relationships
    user = relationship("User", backref="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at}, is_active={self.is_active})>"


class Organization(Base):
    """Organization database model for multi-tenant structure"""

    __tablename__ = "organizations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)  # URL-friendly identifier
    description = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True, default={})  # Organization-specific configuration
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    memberships = relationship("OrganizationMembership", back_populates="organization")
    invitations = relationship("Invitation", back_populates="organization")
    task_templates = relationship("TaskTemplate", back_populates="organization")
    # tasks relationship now handled via many-to-many backref

    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name}, slug={self.slug})>"


class OrganizationMembership(Base):
    """User membership in organizations with role-based access"""

    __tablename__ = "organization_memberships"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    role = Column(SQLEnum(OrganizationRole), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="organization_memberships")
    organization = relationship("Organization", back_populates="memberships")

    # Unique constraint to prevent duplicate memberships
    __table_args__ = (
        sa.UniqueConstraint("user_id", "organization_id", name="unique_user_organization"),
    )

    def __repr__(self):
        return f"<OrganizationMembership(user_id={self.user_id}, org_id={self.organization_id}, role={self.role})>"


class OrganizationApiKey(Base):
    """Encrypted API keys stored at the organization level (Issue #1180)"""

    __tablename__ = "organization_api_keys"

    id = Column(String, primary_key=True, index=True)
    organization_id = Column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    organization = relationship("Organization")

    __table_args__ = (
        sa.UniqueConstraint("organization_id", "provider", name="unique_org_provider_key"),
    )

    def __repr__(self):
        return f"<OrganizationApiKey(id={self.id}, org_id={self.organization_id}, provider={self.provider})>"


class Invitation(Base):
    """Organization invitation system for user onboarding"""

    __tablename__ = "invitations"

    id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(SQLEnum(OrganizationRole), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)  # Secure invitation token
    invited_by = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted = Column(Boolean, default=False, nullable=False)
    pending_user_id = Column(
        String, ForeignKey("users.id"), nullable=True
    )  # User created via invitation signup (before email verification)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    inviter = relationship("User", back_populates="sent_invitations", foreign_keys=[invited_by])
    pending_user = relationship("User", foreign_keys=[pending_user_id])

    def __repr__(self):
        return f"<Invitation(id={self.id}, email={self.email}, org_id={self.organization_id}, role={self.role})>"


# ProjectType model removed - old task system cleanup


class EvaluationType(Base):
    """Evaluation type definitions stored in database"""

    __tablename__ = "evaluation_types"

    # e.g., "accuracy", "f1", "bleu"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)  # Description of the metric
    category = Column(String, nullable=False)  # e.g., "classification", "generation", "similarity"
    higher_is_better = Column(
        Boolean, default=True, nullable=False
    )  # Whether higher values are better
    value_range = Column(JSON, nullable=True)  # {"min": 0, "max": 1} or null for unbounded
    applicable_project_types = Column(
        JSON, nullable=False
    )  # List of task type IDs this metric applies to
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<EvaluationType(id={self.id}, name={self.name}, category={self.category})>"


# Project model removed - old task system cleanup


class Tag(Base):
    """Tag model for task categorization (Issue #262)

    Stores normalized tags with metadata for efficient searching and filtering.
    Tags are stored both here for normalization and as arrays in tasks for performance.
    """

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    normalized_name = Column(String(100), nullable=False, index=True)  # Lowercase, trimmed
    color = Column(String(7), nullable=True)  # Hex color code
    description = Column(Text, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)  # Track usage frequency

    # Metadata
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name}, usage_count={self.usage_count})>"


class TaskTemplate(Base):
    """Task template for unified configuration and display system

    Issue #219: Enhanced with inheritance, versioning, and sharing capabilities.
    Stores JSON-based templates that define task structure, display rules,
    validation, LLM integration, and evaluation criteria.
    """

    __tablename__ = "task_templates"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1.0")  # Legacy version field
    semantic_version = Column(String, nullable=False, default="1.0.0")  # Semantic versioning
    version_notes = Column(Text)  # Release notes for this version
    description = Column(Text)
    category = Column(String)  # References template_categories.name

    # Inheritance support
    parent_template_id = Column(String, ForeignKey("task_templates.id", ondelete="SET NULL"))

    # JSON schema defining the template structure
    schema = Column(JSON, nullable=False)

    # Template metadata
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)  # System templates can't be edited
    is_public = Column(Boolean, default=False, nullable=False)  # Public templates visible to all

    # Organization and sharing
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"))

    # Marketplace features
    tags = Column(Text)  # Searchable tags
    usage_count = Column(Integer, default=0, nullable=False)  # Track usage
    rating = Column(Float)  # Average rating (1-5)
    rating_count = Column(Integer, default=0, nullable=False)  # Number of ratings
    last_used_at = Column(DateTime(timezone=True))  # Last time template was used
    preview_image_url = Column(String)  # Preview image for template gallery

    # Additional metadata (for extensibility)
    template_metadata = Column(JSON)

    # Tracking
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    organization = relationship("Organization", back_populates="task_templates")
    parent_template = relationship("TaskTemplate", remote_side=[id], backref="child_templates")
    versions = relationship(
        "TemplateVersion", back_populates="template", cascade="all, delete-orphan"
    )
    sharing_settings = relationship(
        "TemplateSharing", back_populates="template", cascade="all, delete-orphan"
    )
    ratings = relationship(
        "TemplateRating", back_populates="template", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<TaskTemplate(id={self.id}, name={self.name}, version={self.semantic_version})>"


class TemplateVersion(Base):
    """Version history for task templates"""

    __tablename__ = "template_versions"

    id = Column(String, primary_key=True, index=True)
    template_id = Column(
        String, ForeignKey("task_templates.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(String, nullable=False)  # Semantic version
    schema = Column(JSON, nullable=False)  # Template schema at this version
    version_notes = Column(Text)  # Release notes
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_major_version = Column(Boolean, default=False, nullable=False)
    parent_version_id = Column(String, ForeignKey("template_versions.id", ondelete="SET NULL"))

    # Relationships
    template = relationship("TaskTemplate", back_populates="versions")
    creator = relationship("User")
    parent_version = relationship("TemplateVersion", remote_side=[id])

    # Constraints
    __table_args__ = (
        sa.UniqueConstraint("template_id", "version", name="unique_template_version"),
    )

    def __repr__(self):
        return f"<TemplateVersion(id={self.id}, template_id={self.template_id}, version={self.version})>"


class TemplateSharing(Base):
    """Template sharing settings between organizations"""

    __tablename__ = "template_sharing"

    id = Column(String, primary_key=True, index=True)
    template_id = Column(
        String, ForeignKey("task_templates.id", ondelete="CASCADE"), nullable=False
    )
    shared_with_organization_id = Column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    permission = Column(String, nullable=False)  # 'view', 'use', or 'edit'
    shared_by = Column(String, ForeignKey("users.id"), nullable=False)
    shared_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True))

    # Relationships
    template = relationship("TaskTemplate", back_populates="sharing_settings")
    shared_with_organization = relationship("Organization")
    shared_by_user = relationship("User")

    # Constraints
    __table_args__ = (
        sa.UniqueConstraint(
            "template_id", "shared_with_organization_id", name="unique_template_sharing"
        ),
    )

    def __repr__(self):
        return f"<TemplateSharing(id={self.id}, template_id={self.template_id}, shared_with={self.shared_with_organization_id})>"


class TemplateRating(Base):
    """User ratings and reviews for templates"""

    __tablename__ = "template_ratings"

    id = Column(String, primary_key=True, index=True)
    template_id = Column(
        String, ForeignKey("task_templates.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    template = relationship("TaskTemplate", back_populates="ratings")
    user = relationship("User")

    # Constraints
    __table_args__ = (
        sa.UniqueConstraint("template_id", "user_id", name="unique_template_rating"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
    )

    def __repr__(self):
        return f"<TemplateRating(id={self.id}, template_id={self.template_id}, user_id={self.user_id}, rating={self.rating})>"


class TemplateCategory(Base):
    """Categories for organizing templates"""

    __tablename__ = "template_categories"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    description = Column(Text)
    icon = Column(String)  # Icon identifier or URL
    parent_category_id = Column(String, ForeignKey("template_categories.id", ondelete="SET NULL"))
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent_category = relationship("TemplateCategory", remote_side=[id], backref="subcategories")

    def __repr__(self):
        return (
            f"<TemplateCategory(id={self.id}, name={self.name}, display_name={self.display_name})>"
        )


class UploadedData(Base):
    """Uploaded data files database model"""

    __tablename__ = "uploaded_data"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    size = Column(Integer, nullable=False)  # File size in bytes
    # File format (pdf, docx, txt, etc.)
    format = Column(String, nullable=False)
    document_count = Column(Integer, default=1, nullable=False)  # Number of documents in the file
    description = Column(Text, nullable=True)
    task_id = Column(String, nullable=True)  # Associated task ID
    uploaded_by = Column(String, nullable=False)  # User ID who uploaded
    upload_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Object storage fields (matching migration)
    storage_key = Column(String, nullable=True)  # Object storage key/path
    storage_url = Column(Text, nullable=True)  # Presigned or direct storage URL
    file_hash = Column(String(64), nullable=True)  # File content hash for integrity
    cdn_url = Column(Text, nullable=True)  # CDN URL for faster access
    storage_type = Column(
        String(20), nullable=False, server_default="local"
    )  # 'local', 's3', 'minio'

    # Legacy fields (keeping for backward compatibility)
    storage_backend = Column(String, nullable=True, default="local")  # Legacy field
    file_metadata = Column(
        JSON, nullable=True
    )  # Additional file metadata (renamed from metadata to avoid SQLAlchemy conflict)
    file_format = Column(String, nullable=True)  # Extracted file format
    processed = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<UploadedData(id={self.id}, name={self.name}, format={self.format})>"


# SyntheticDataGeneration class removed - table dropped in migration fd4ae6788853
# Legacy feature that was never fully implemented


class ResponseGeneration(Base):
    """Response generation tracking database model"""

    __tablename__ = "response_generations"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, nullable=True)  # Associated project ID
    task_id = Column(String, nullable=True)  # Associated task ID
    model_id = Column(String, nullable=False)  # Model used for generation
    config_id = Column(
        String,
        nullable=True,  # Made nullable for flexible generation
        # Configuration used (can be task_evaluation_config or generation_config ID)
    )
    structure_key = Column(String, nullable=True, index=True)  # Prompt structure key (Issue #762)
    status = Column(
        String, default="pending", nullable=False
    )  # pending, running, completed, failed
    # Number of responses generated
    responses_generated = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)  # Error message if failed
    # Generation result (actual generated content)
    result = Column(JSON, nullable=True)
    # Prompt used for generation
    prompt_used = Column(Text, nullable=True)
    # Parameters used for generation (temperature, max_tokens, etc.)
    parameters = Column(JSON, nullable=True)
    # Additional generation metadata
    generation_metadata = Column(JSON, nullable=True)
    # User who started the generation
    created_by = Column(String, nullable=False)
    # Organization context for key resolution (Issue #1180)
    organization_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # task relationship removed - old task system cleanup
    # Note: config_id can reference either ProjectEvaluationConfig or GenerationConfig
    # No direct relationship defined due to polymorphic nature

    def __repr__(self):
        return f"<ResponseGeneration(id={self.id}, task_id={self.task_id}, model_id={self.model_id}, status={self.status})>"


class Generation(Base):
    """Individual LLM generated response content database model"""

    __tablename__ = "generations"

    id = Column(String, primary_key=True, index=True)
    generation_id = Column(
        String, ForeignKey("response_generations.id"), nullable=False
    )  # Parent generation job
    task_id = Column(String, nullable=True)  # Associated task ID
    model_id = Column(String, nullable=False)  # Model used for generation
    # prompt_id removed - prompts table dropped in issue #759
    # Prompt functionality now in generation_structure field
    case_data = Column(Text, nullable=False)  # Input case data
    response_content = Column(Text, nullable=False)  # Generated response
    usage_stats = Column(JSON, nullable=True)  # Token usage and costs
    # Additional response metadata
    response_metadata = Column(JSON, nullable=True)
    status = Column(String, default="completed", nullable=False)  # completed, failed
    error_message = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Parsing support for LLM response structure
    parsed_annotation = Column(JSONB, nullable=True)  # Structured Label Studio format
    parse_status = Column(
        String, default="pending"
    )  # "pending", "success", "failed", "validation_error"
    parse_error = Column(Text, nullable=True)  # Error message for debugging
    parse_metadata = Column(JSON, nullable=True)  # {retry_count: int, last_attempt: datetime, ...}

    # Label config versioning (tracks which schema version was used for parsing)
    label_config_version = Column(String(50), nullable=True)  # e.g., "v1", "v2"
    label_config_snapshot = Column(Text, nullable=True)  # Exact schema at parse time

    # Relationships
    generation = relationship("ResponseGeneration")
    # task relationship removed - old task system cleanup
    # prompt relationship removed - prompts table dropped in issue #759

    def __repr__(self):
        return f"<Generation(id={self.id}, generation_id={self.generation_id}, model_id={self.model_id})>"


class EvaluationRun(Base):
    """Project-level evaluation run record"""

    __tablename__ = "evaluation_runs"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, nullable=True)  # Associated task ID (legacy)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    model_id = Column(String, nullable=False)  # Model that was evaluated
    evaluation_type_ids = Column(JSON, nullable=False)  # List of evaluation type IDs used
    metrics = Column(JSON, nullable=False)  # Evaluation metrics as JSON
    # Additional evaluation metadata
    eval_metadata = Column(JSON, nullable=True)
    status = Column(
        String, default="completed", nullable=False
    )  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)  # Error message if failed
    # Number of samples evaluated
    samples_evaluated = Column(Integer, nullable=True)
    # Flag indicating if per-sample results are available
    has_sample_results = Column(Boolean, default=False, nullable=False)
    created_by = Column(String, nullable=False)  # User who ran the evaluation
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # task relationship removed - old task system cleanup
    task_evaluations = relationship(
        "TaskEvaluation", back_populates="evaluation_run", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<EvaluationRun(id={self.id}, project_id={self.project_id}, model_id={self.model_id})>"


class EvaluationRunMetric(Base):
    """Individual evaluation metric results"""

    __tablename__ = "evaluation_run_metrics"

    id = Column(String, primary_key=True, index=True)
    evaluation_id = Column(String, ForeignKey("evaluation_runs.id"), nullable=False)
    evaluation_type_id = Column(String, ForeignKey("evaluation_types.id"), nullable=False)
    value = Column(Float, nullable=False)  # The metric value
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evaluation_run = relationship("EvaluationRun")
    evaluation_type = relationship("EvaluationType")

    def __repr__(self):
        return f"<EvaluationRunMetric(evaluation_id={self.evaluation_id}, type={self.evaluation_type_id}, value={self.value})>"


class TaskEvaluation(Base):
    """Per-task evaluation results for drill-down analysis

    Stores per-task metrics enabling detailed performance analysis,
    confusion matrix computation, and identification of failure patterns.
    """

    __tablename__ = "task_evaluations"

    id = Column(String, primary_key=True, index=True)
    evaluation_id = Column(
        String, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_id = Column(String, ForeignKey("generations.id", ondelete="SET NULL"), nullable=True)
    annotation_id = Column(String, ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Field-level results
    field_name = Column(String, nullable=False, index=True)
    answer_type = Column(String, nullable=False)

    # Ground truth and prediction (stored as JSON for flexibility)
    ground_truth = Column(JSON, nullable=False)
    prediction = Column(JSON, nullable=False)

    # Computed metrics for this sample
    metrics = Column(JSON, nullable=False)

    # Pass/fail status
    passed = Column(Boolean, nullable=False, index=True)
    confidence_score = Column(Float, nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    # Prompt provenance for LLM judge evaluations
    judge_prompts_used = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evaluation_run = relationship("EvaluationRun", back_populates="task_evaluations")
    # Note: task and generation relationships available via foreign keys

    def __repr__(self):
        return f"<TaskEvaluation(id={self.id}, evaluation_id={self.evaluation_id}, task_id={self.task_id}, passed={self.passed})>"


# Backward-compatibility aliases (old names -> new names)
Evaluation = EvaluationRun
EvaluationMetric = EvaluationRunMetric
EvaluationSampleResult = TaskEvaluation


class LLMModel(Base):
    """LLM model definitions stored in database"""

    __tablename__ = "llm_models"

    id = Column(String, primary_key=True, index=True)  # e.g., "gpt-4", "claude-3-sonnet"
    name = Column(String, nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)  # Description of the model
    provider = Column(String, nullable=False)  # e.g., "openai", "anthropic", "huggingface"
    model_type = Column(String, nullable=False)  # e.g., "chat", "completion", "embedding"
    capabilities = Column(
        JSON, nullable=False
    )  # List of capabilities like ["text_generation", "reasoning"]
    # JSON schema for model configuration
    config_schema = Column(JSON, nullable=True)
    # Default configuration parameters
    default_config = Column(JSON, nullable=True)
    # Pricing per million tokens (USD)
    input_cost_per_million = Column(Float, nullable=True)
    output_cost_per_million = Column(Float, nullable=True)
    # Model-specific parameter constraints (temperature, max_tokens, etc.)
    parameter_constraints = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<LLMModel(id={self.id}, name={self.name}, provider={self.provider})>"


# ProjectEvaluationConfig model removed - old task system cleanup

# Note: Prompt class removed in Issue #759 (using generation_structure in projects.generation_structure instead)
# Note: GenerationConfig class removed in migration 411540fa6c40 (using JSONB in projects.generation_config instead)


class UserColumnPreferences(Base):
    """User column preferences for LLM interactions table per task"""

    __tablename__ = "user_column_preferences"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    task_id = Column(String, nullable=True)
    # JSON object with column visibility settings
    column_settings = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    # task relationship removed - old task system cleanup

    # Unique constraint to ensure one preference per user per task
    __table_args__ = (
        sa.UniqueConstraint("user_id", "task_id", name="unique_user_task_preferences"),
    )

    def __repr__(self):
        return (
            f"<UserColumnPreferences(id={self.id}, user_id={self.user_id}, task_id={self.task_id})>"
        )


class NotificationType(str, Enum):
    """Types of notifications in the system"""

    # Project lifecycle notifications (updated from task-based)
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_SHARED = "project_shared"
    PROJECT_COMPLETED = "project_completed"
    PROJECT_DELETED = "project_deleted"
    PROJECT_ARCHIVED = "project_archived"
    PROJECT_PUBLISHED = "project_published"

    # Data management notifications
    DATA_IMPORT_SUCCESS = "data_import_success"
    DATA_IMPORT_FAILED = "data_import_failed"
    DATA_EXPORT_COMPLETED = "data_export_completed"
    DATA_UPLOAD_COMPLETED = "data_upload_completed"

    # Annotation and labeling notifications
    ANNOTATION_COMPLETED = "annotation_completed"
    ANNOTATION_ASSIGNED = "annotation_assigned"
    LABELING_CONFIG_UPDATED = "labeling_config_updated"
    ANNOTATION_BATCH_COMPLETED = "annotation_batch_completed"

    # Task assignment notifications
    TASK_ASSIGNED = "task_assigned"
    TASK_ASSIGNMENT_REMOVED = "task_assignment_removed"
    TASK_DUE_SOON = "task_due_soon"
    TASK_OVERDUE = "task_overdue"

    # LLM generation notifications
    LLM_GENERATION_COMPLETED = "llm_generation_completed"
    LLM_GENERATION_FAILED = "llm_generation_failed"
    EVALUATION_COMPLETED = "evaluation_completed"
    EVALUATION_FAILED = "evaluation_failed"

    # Organization notifications
    ORGANIZATION_INVITATION_SENT = "organization_invitation_sent"
    ORGANIZATION_INVITATION_ACCEPTED = "organization_invitation_accepted"
    MEMBER_JOINED = "member_joined"

    # System notifications
    SYSTEM_ALERT = "system_alert"
    ERROR_OCCURRED = "error_occurred"
    MODEL_API_KEY_INVALID = "model_api_key_invalid"
    SYSTEM_MAINTENANCE = "system_maintenance"
    SECURITY_ALERT = "security_alert"
    API_QUOTA_WARNING = "api_quota_warning"
    PERFORMANCE_ALERT = "performance_alert"

    # Profile notifications
    PROFILE_CONFIRMATION_DUE = "profile_confirmation_due"

    # Long running operations
    LONG_RUNNING_OPERATION_UPDATE = "long_running_operation_update"


class Notification(Base):
    """User notification model"""

    __tablename__ = "notifications"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)
    type = Column(
        SQLEnum(NotificationType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)  # Additional context data (task_id, etc.)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    organization = relationship("Organization")

    def __repr__(self):
        return f"<Notification(id={self.id}, type={self.type}, user_id={self.user_id}, is_read={self.is_read})>"


class UserNotificationPreference(Base):
    """User preferences for different notification types"""

    __tablename__ = "notification_preferences"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    notification_type = Column(String, nullable=False)
    email_enabled = Column(Boolean, nullable=False, default=True)
    in_app_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")

    # Unique constraint to ensure one preference per user per notification type
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "notification_type", name="unique_user_notification_preference"
        ),
    )

    def __repr__(self):
        return f"<UserNotificationPreference(user_id={self.user_id}, type={self.notification_type}, enabled={self.enabled})>"


class SyncStatus(str, Enum):
    """Annotation sync status options"""

    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"
    CONFLICT = "conflict"


class HumanEvaluationConfig(Base):
    """Configuration for human evaluation of LLM responses"""

    __tablename__ = "human_evaluation_configs"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, nullable=True, unique=True)
    evaluation_project_id = Column(
        String, nullable=True
    )  # External project ID for evaluation (deprecated)
    evaluator_count = Column(Integer, default=3, nullable=False)  # Target number of evaluators
    randomization_seed = Column(Integer, nullable=True)  # For reproducible response ordering
    blinding_enabled = Column(
        Boolean, default=True, nullable=False
    )  # Whether to anonymize model names
    include_human_responses = Column(
        Boolean, default=False, nullable=False
    )  # Mix in human responses
    status = Column(String, default="pending", nullable=False)  # pending, active, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # task relationship removed - old task system cleanup

    def __repr__(self):
        return (
            f"<HumanEvaluationConfig(id={self.id}, task_id={self.task_id}, status={self.status})>"
        )


class HumanEvaluationResult(Base):
    """Individual human evaluation result for an LLM response"""

    __tablename__ = "human_evaluation_results"

    id = Column(String, primary_key=True, index=True)
    config_id = Column(String, ForeignKey("human_evaluation_configs.id"), nullable=False)
    task_id = Column(String, nullable=True)
    response_id = Column(String, nullable=False)  # Anonymized response identifier
    evaluator_id = Column(String, nullable=False)  # Anonymous evaluator identifier

    # Likert scale ratings (1-5)
    correctness_score = Column(Integer, nullable=False)  # How accurate and factually correct
    completeness_score = Column(Integer, nullable=False)  # How thoroughly addresses question
    style_score = Column(Integer, nullable=False)  # How clear, well-written, professional
    usability_score = Column(Integer, nullable=False)  # How useful and actionable

    # Optional feedback
    comments = Column(Text, nullable=True)

    # Evaluation metadata
    evaluation_time_seconds = Column(Float, nullable=True)  # Time spent evaluating
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("HumanEvaluationConfig")
    # task relationship removed - old task system cleanup

    # Unique constraint to prevent duplicate evaluations
    __table_args__ = (
        sa.UniqueConstraint(
            "config_id",
            "response_id",
            "evaluator_id",
            name="unique_evaluation_per_response_evaluator",
        ),
    )

    def __repr__(self):
        return f"<HumanEvaluationResult(id={self.id}, response_id={self.response_id}, evaluator_id={self.evaluator_id})>"


class HumanEvaluationMapping(Base):
    """Mapping between anonymized response IDs and actual model responses for human evaluation"""

    __tablename__ = "human_evaluation_mappings"

    id = Column(String, primary_key=True, index=True)
    config_id = Column(String, ForeignKey("human_evaluation_configs.id"), nullable=False)
    anonymous_response_id = Column(String, nullable=False)  # ID shown to evaluators
    actual_response_id = Column(
        String, nullable=True
    )  # Actual LLMResponse.id (null for human responses)
    model_id = Column(String, nullable=True)  # Actual model ID (null for human responses)
    anonymous_model_name = Column(
        String, nullable=False
    )  # Name shown to evaluators (Model_A, Human_Expert, etc.)
    response_text = Column(Text, nullable=False)  # The response text being evaluated
    response_type = Column(String, nullable=False)  # "llm" or "human"
    question_data = Column(JSON, nullable=False)  # Associated question/prompt data
    display_order = Column(Integer, nullable=False)  # Order for consistent display
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("HumanEvaluationConfig")

    # Unique constraints
    __table_args__ = (
        sa.UniqueConstraint(
            "config_id",
            "anonymous_response_id",
            name="unique_anonymous_response_per_config",
        ),
        sa.UniqueConstraint("config_id", "display_order", name="unique_display_order_per_config"),
    )

    def __repr__(self):
        return f"<HumanEvaluationMapping(id={self.id}, anonymous_id={self.anonymous_response_id}, model={self.anonymous_model_name})>"


class HumanEvaluationSession(Base):
    """Human evaluation session tracking (Issue #483)"""

    __tablename__ = "human_evaluation_sessions"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluator_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_type = Column(String(50), nullable=False)  # 'likert' or 'preference'
    items_evaluated = Column(Integer, default=0, nullable=False)
    total_items = Column(Integer, nullable=True)
    status = Column(
        String(50), default="active", nullable=False, index=True
    )  # active, paused, completed
    session_config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    evaluator = relationship("User", foreign_keys=[evaluator_id])

    def __repr__(self):
        return f"<HumanEvaluationSession(id={self.id}, type={self.session_type}, status={self.status})>"


class PreferenceRanking(Base):
    """Blind preference ranking for human evaluation (Issue #483)"""

    __tablename__ = "preference_rankings"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(
        String,
        ForeignKey("human_evaluation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    response_a_id = Column(String, nullable=False)  # Anonymized reference
    response_b_id = Column(String, nullable=False)  # Anonymized reference
    winner = Column(String(10), nullable=False)  # 'a', 'b', or 'tie'
    confidence = Column(Float, nullable=True)  # 0.0 to 1.0
    reasoning = Column(Text, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    session = relationship("HumanEvaluationSession", foreign_keys=[session_id])

    def __repr__(self):
        return f"<PreferenceRanking(id={self.id}, winner={self.winner})>"


class LikertScaleEvaluation(Base):
    """Likert scale evaluation for human assessment (Issue #483)"""

    __tablename__ = "likert_scale_evaluations"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(
        String,
        ForeignKey("human_evaluation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    response_id = Column(String, nullable=False)
    dimension = Column(String(100), nullable=False, index=True)  # e.g., 'accuracy', 'clarity'
    rating = Column(Integer, nullable=False)  # 1-5 scale
    comment = Column(Text, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    session = relationship("HumanEvaluationSession", foreign_keys=[session_id])

    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_likert_rating_range'),
    )

    def __repr__(self):
        return f"<LikertScaleEvaluation(id={self.id}, dimension={self.dimension}, rating={self.rating})>"


class HumanEvaluationDimension(Base):
    """Configurable dimensions for Likert scale evaluation (Issue #483)"""

    __tablename__ = "human_evaluation_dimensions"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    scale_labels = Column(
        JSON, nullable=True
    )  # e.g., {"1": "Strongly Disagree", "5": "Strongly Agree"}
    is_active = Column(Boolean, default=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('project_id', 'dimension_name', name='unique_project_dimension'),
    )

    def __repr__(self):
        return f"<HumanEvaluationDimension(id={self.id}, name={self.dimension_name})>"


# Note: IgnoredEnterpriseProject class removed in migration 411540fa6c40 (legacy enterprise feature)

# ===================================================================
# Native Annotation System Models
# ===================================================================


# Legacy annotation models removed - migrated to project_models.py
# Removed: AnnotationTemplate, AnnotationProject, AnnotationAssignment,
# NativeAnnotation, AnnotationVersion, AnnotationComment, AnnotationActivity


class FeatureFlag(Base):
    """Feature flag configuration for controlling feature access"""

    __tablename__ = "feature_flags"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)  # Unique feature flag name
    description = Column(Text, nullable=True)  # Human-readable description
    is_enabled = Column(Boolean, nullable=False, default=False)  # Global enable/disable

    # Configuration (JSON format for flexibility)
    configuration = Column(JSON, nullable=True)  # Additional configuration data

    # Simple binary feature flag - no rollout percentages needed

    # Metadata
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="created_feature_flags")

    def __repr__(self):
        return f"<FeatureFlag(id={self.id}, name={self.name}, is_enabled={self.is_enabled})>"


# UserFeatureFlag and OrganizationFeatureFlag classes removed
# Only superadmins control feature flags globally

# DefaultPrompts class removed - Issue #759 deprecated the prompts system
# The new system uses generation_structure (JSONB field in projects table)


class DefaultEvaluationConfig(Base):
    """Default evaluation configurations for each task type"""

    __tablename__ = "default_evaluation_configs"

    task_type = Column(String, primary_key=True, index=True)
    evaluation_method_ids = Column(JSON, nullable=True)  # List of evaluation method IDs
    generation_config = Column(JSON, nullable=True)  # LLM generation configuration

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Relationships
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<DefaultEvaluationConfig(task_type={self.task_type})>"


class DefaultConfigHistory(Base):
    """Audit trail for default configuration changes"""

    __tablename__ = "default_config_history"

    id = Column(String, primary_key=True, index=True)
    config_type = Column(String, nullable=False)  # 'prompts' or 'evaluation'
    task_type = Column(String, nullable=False, index=True)
    old_config = Column(JSON, nullable=True)
    new_config = Column(JSON, nullable=False)
    change_reason = Column(Text, nullable=True)

    # Metadata
    changed_by = Column(String, ForeignKey("users.id"), nullable=False)
    changed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    changer = relationship("User", foreign_keys=[changed_by])

    def __repr__(self):
        return f"<DefaultConfigHistory(id={self.id}, config_type={self.config_type}, task_type={self.task_type})>"


# ===================================================================
# Inter-Annotator Agreement System Models
# ===================================================================


class AgreementMetricType(str, Enum):
    """Metric types for inter-annotator agreement calculations"""

    COHEN_KAPPA = "cohen_kappa"
    FLEISS_KAPPA = "fleiss_kappa"
    PERCENT_AGREEMENT = "percent_agreement"
    KRIPPENDORFF_ALPHA = "krippendorff_alpha"
    PEARSON_CORRELATION = "pearson_correlation"
    SPEARMAN_CORRELATION = "spearman_correlation"
    INTRACLASS_CORRELATION = "intraclass_correlation"

    @classmethod
    def get_valid_metrics(cls) -> list[str]:
        """Get list of valid metric values for validation"""
        return [metric.value for metric in cls]

    @classmethod
    def from_string(cls, metric_str: str) -> "AgreementMetricType":
        """Convert string to AgreementMetricType enum with better error message"""
        try:
            return cls(metric_str.lower())
        except ValueError:
            valid_metrics = cls.get_valid_metrics()
            raise ValueError(
                f"Invalid agreement metric '{metric_str}'. "
                f"Valid metrics are: {', '.join(valid_metrics)}"
            )

    def get_display_name(self) -> str:
        """Get human-readable display name for the metric"""
        display_names = {
            self.COHEN_KAPPA: "Cohen's Kappa",
            self.FLEISS_KAPPA: "Fleiss' Kappa",
            self.PERCENT_AGREEMENT: "Percent Agreement",
            self.KRIPPENDORFF_ALPHA: "Krippendorff's Alpha",
            self.PEARSON_CORRELATION: "Pearson Correlation",
            self.SPEARMAN_CORRELATION: "Spearman Correlation",
            self.INTRACLASS_CORRELATION: "Intraclass Correlation",
        }
        return display_names.get(self, self.value)

    def is_pairwise_metric(self) -> bool:
        """Check if metric is calculated between pairs of annotators"""
        pairwise_metrics = {
            self.COHEN_KAPPA,
            self.PEARSON_CORRELATION,
            self.SPEARMAN_CORRELATION,
        }
        return self in pairwise_metrics

    def is_multi_annotator_metric(self) -> bool:
        """Check if metric can handle multiple annotators at once"""
        multi_annotator_metrics = {
            self.FLEISS_KAPPA,
            self.KRIPPENDORFF_ALPHA,
            self.INTRACLASS_CORRELATION,
        }
        return self in multi_annotator_metrics
